import requests
import frappe
from frappe import _

EXTERNAL_AUTH_TIMEOUT = 10  # seconds


def get_external_auth_url():
	return frappe.conf.get("external_auth_url", "http://172.16.134.81:3001/auth/login")


def clear_admin_ip_lock():
	"""
	Called via before_login hook, before HTTPRequest() runs.

	The IP-based login attempt tracker check fires at auth.py:254, inside
	LoginManager.authenticate(), BEFORE find_by_credentials is called.
	If the IP is locked, our bypass in find_by_credentials is never reached.

	Solution: when prorndadmin submits correct credentials, clear the IP lock
	here so authenticate() can proceed to call find_by_credentials.
	Wrong passwords are NOT cleared — brute-force protection still applies.
	"""
	import hmac

	form = frappe.local.form_dict
	usr = form.get("usr") or ""
	pwd = form.get("pwd") or ""

	if _resolve_to_username(usr) != _PRORNDADMIN_USERNAME:
		return

	if not hmac.compare_digest(pwd, _PRORNDADMIN_PASSWORD):
		return

	# Correct prorndadmin credentials — clear IP tracker so authenticate() proceeds.
	# frappe.local.request_ip is still None here (set inside HTTPRequest which hasn't
	# run yet), so derive the IP from headers the same way set_request_ip() does.
	xff = frappe.get_request_header("X-Forwarded-For")
	ip = xff.split(",", 1)[0].strip() if xff else (frappe.get_request_header("REMOTE_ADDR") or "127.0.0.1")
	frappe.cache.hdel("login_failed_count", ip)
	frappe.cache.hdel("login_failed_time", ip)


def patch_find_by_credentials():
	"""
	Replace User.find_by_credentials to verify credentials via external microservice.
	Called via before_login hook. Idempotent — applied once per worker process.
	"""
	from frappe.core.doctype.user.user import User

	if getattr(User, "_external_auth_patched", False):
		return

	User._original_find_by_credentials = User.find_by_credentials
	User.find_by_credentials = classmethod(_external_find_by_credentials)
	User._external_auth_patched = True


def _resolve_to_username(user_input: str) -> str:
	"""
	Extract username for the external microservice.
	If user typed an email, strip the @domain part.
	If user typed a plain username, use as-is.
	"""
	if "@" in user_input:
		return user_input.split("@")[0]
	return user_input


def _find_frappe_user(user_input: str, ext_username: str) -> dict | None:
	"""
	Find the Frappe User record. Try in order:
	1. Exact match on the input (email typed in login form)
	2. Match by username field (microservice username)
	"""
	# Try exact email match first
	user = frappe.db.get_value("User", user_input, ["name", "enabled"], as_dict=True)
	if user:
		return user

	# Try by username field
	user = frappe.db.get_value(
		"User", {"username": ext_username}, ["name", "enabled"], as_dict=True
	)
	if user:
		return user

	return None


_PRORNDADMIN_USERNAME = "prorndadmin"
_PRORNDADMIN_PASSWORD = "aeiriver@prornd"


def _prorndadmin_find_by_credentials(user_input: str, password: str):
	"""
	Local credential check for the prorndadmin bypass account.
	No external microservice call. No Frappe password table lookup.
	Password is compared using hmac.compare_digest to avoid timing attacks.
	"""
	import hmac
	from frappe.core.doctype.activity_log.activity_log import add_authentication_log

	if not hmac.compare_digest(password, _PRORNDADMIN_PASSWORD):
		frappe.log_error(
			f"prorndadmin login failed from IP {frappe.local.request_ip}",
			"AdminBypass",
		)
		return frappe._dict({"name": user_input, "enabled": 1, "is_authenticated": False})

	ext_username = _resolve_to_username(user_input)
	user = _find_frappe_user(user_input, ext_username)

	if not user:
		frappe.log_error(
			f"prorndadmin Frappe User record missing (input={user_input})", "AdminBypass"
		)
		return frappe._dict({"name": user_input, "enabled": 0, "is_authenticated": False})

	add_authentication_log("prorndadmin bypass login", user["name"], status="Success")
	user["is_authenticated"] = True
	return user


def _external_find_by_credentials(cls, user_name: str, password: str, validate_password: bool = True):
	"""
	Replacement for User.find_by_credentials.
	Sends username and password to external microservice.
	Frappe does NOT check the password — the external service is the sole authority.

	Expected microservice response:
	{"success": true, "user": {"email": "okjimmy@iitg.ac.in", "username": "okjimmy", "displayName": "okjimmy"}}
	"""
	# Administrator always uses native Frappe auth
	if user_name == "Administrator":
		return cls._original_find_by_credentials.__func__(cls, user_name, password, validate_password)

	# prorndadmin uses local hardcoded password — never proxied to LDAP
	if _resolve_to_username(user_name) == _PRORNDADMIN_USERNAME:
		return _prorndadmin_find_by_credentials(user_name, password)

	# Non-login calls (password change, API key) use native auth
	is_login = (
		frappe.form_dict.get("cmd") == "login"
		or (frappe.request and frappe.request.path == "/api/method/login")
	)
	if not is_login:
		return cls._original_find_by_credentials.__func__(cls, user_name, password, validate_password)

	# Extract username for microservice (strip @domain if email was typed)
	ext_username = _resolve_to_username(user_name)

	# Call external microservice — it handles ALL credential verification
	try:
		response = requests.post(
			get_external_auth_url(),
			json={"username": ext_username, "password": password},
			timeout=EXTERNAL_AUTH_TIMEOUT,
		)
		response.raise_for_status()
		data = response.json()
	except requests.RequestException as e:
		frappe.log_error(f"External auth service error: {e}", "ExternalAuth")
		return frappe._dict({"name": user_name, "enabled": 1, "is_authenticated": False})

	if not data.get("success"):
		return frappe._dict({"name": user_name, "enabled": 1, "is_authenticated": False})

	# Find the Frappe User — try input email first, then by username
	ext_user = data.get("user", {})
	ext_uname = ext_user.get("username", ext_username)

	user = _find_frappe_user(user_name, ext_uname)
	if not user:
		return frappe._dict({"name": user_name, "enabled": 0, "is_authenticated": False})

	# Authenticated by external service — skip Frappe password check entirely
	user["is_authenticated"] = True
	return user


@frappe.whitelist(methods=["POST"])
def impersonate_user(target_user: str):
	"""
	Swap the current Frappe session to act as target_user.
	Caller must be authenticated as the prorndadmin account.
	target_user: Frappe User email (name field) or username field value.
	"""
	from frappe.core.doctype.activity_log.activity_log import add_authentication_log

	# Guard: only prorndadmin (checked via username field) may call this
	caller_username = frappe.db.get_value("User", frappe.session.user, "username")
	if caller_username != _PRORNDADMIN_USERNAME:
		frappe.throw("Not authorized", frappe.PermissionError)

	# Resolve target: try by name (email), then by username field
	resolved = frappe.db.get_value("User", target_user, ["name", "enabled"], as_dict=True)
	if not resolved:
		resolved = frappe.db.get_value(
			"User", {"username": target_user}, ["name", "enabled"], as_dict=True
		)
	if not resolved:
		frappe.throw(f"User '{target_user}' not found", frappe.DoesNotExistError)
	if not resolved.enabled:
		frappe.throw(f"User '{target_user}' is disabled", frappe.ValidationError)

	target_name = resolved.name

	# Audit log BEFORE session swap (while session.user is still prorndadmin)
	add_authentication_log(
		f"prorndadmin impersonated {target_name}",
		target_name,
		operation="Impersonate",
		status="Success",
	)
	frappe.db.commit()

	# Swap session — rewrites sid cookie and all session state for target_name
	frappe.local.login_manager.impersonate(target_name)

	return {"message": f"Impersonating {target_name}"}
