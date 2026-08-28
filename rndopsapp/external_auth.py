import requests
import frappe
from frappe import _
from rndopsapp.config import EXTERNAL_AUTH_URL

EXTERNAL_AUTH_TIMEOUT = 10  # seconds


def get_external_auth_url():
	return frappe.conf.get("external_auth_url", EXTERNAL_AUTH_URL)


def get_client_ip():
	"""
	Real client IP, preferring the proxy-set headers (X-Forwarded-For, then X-Real-IP)
	over the raw socket address. frappe.local.request_ip is unset during before_login
	(HTTPRequest hasn't run yet), so this falls back to reading headers directly the
	same way clear_admin_ip_lock does.
	"""
	ip = getattr(frappe.local, "request_ip", None)
	if ip:
		return ip
	xff = frappe.get_request_header("X-Forwarded-For")
	if xff:
		return xff.split(",", 1)[0].strip()
	real_ip = frappe.get_request_header("X-Real-IP")
	if real_ip:
		return real_ip.strip()
	return frappe.get_request_header("REMOTE_ADDR") or "Unknown"


def get_client_reported_ip():
	"""
	IP the frontend claims for itself (e.g. resolved via a public IP-echo service),
	sent as `client_ip` on the login POST. Client-supplied and therefore spoofable —
	stored only as a secondary, informational field. `ip_address` (server-derived)
	remains the authoritative value for audit purposes.
	"""
	value = frappe.local.form_dict.get("client_ip")
	return value.strip() if value else None


def log_admin_access(
	user,
	event_type,
	target_user=None,
	status="Success",
	details=None,
	action_doctype=None,
	action_docname=None,
	action_type=None,
):
	"""Audit trail for the prorndadmin bypass account: login attempts, impersonation,
	logout, and (when action_doctype is given) individual document actions taken
	while impersonating someone."""
	try:
		log = frappe.new_doc("ProRnd Admin Access Log")
		log.timestamp = frappe.utils.now_datetime()
		log.user = user
		log.event_type = event_type
		log.target_user = target_user
		log.status = status
		log.action_doctype = action_doctype
		log.action_docname = action_docname
		log.action_type = action_type
		log.ip_address = get_client_ip()
		log.client_reported_ip = get_client_reported_ip()
		log.user_agent = frappe.get_request_header("User-Agent") or ""
		log.details = details or ""
		log.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ProRnd Admin Access Log failed")


_IMPERSONATED_DOC_EVENTS = {
	"after_insert": "Insert",
	"on_update": "Update",
	"on_submit": "Submit",
	"on_cancel": "Cancel",
	"on_trash": "Delete",
}


def log_impersonated_action(doc, method):
	"""
	doc_events hook, registered for "*" (every doctype) on after_insert/on_update/
	on_submit/on_cancel/on_trash. Only ever logs anything if the CURRENT session is
	an active impersonation — i.e. frappe.session.data.impersonated_by is set by
	LoginManager.impersonate() (see auth.py:350). Records which doctype/document
	prorndadmin touched while wearing another user's identity, so impersonation
	sessions are auditable action-by-action, not just as a single opaque login.
	"""
	# frappe.session.data is None during the login flow itself (e.g. the Activity Log
	# row that add_authentication_log() inserts on every login attempt, before session
	# boot has populated .data) — guard so login isn't broken by this audit hook.
	impersonated_by = (frappe.session.data or {}).get("impersonated_by")
	if not impersonated_by:
		return
	if doc.doctype == "ProRnd Admin Access Log":
		return

	action = _IMPERSONATED_DOC_EVENTS.get(method, method)
	log_admin_access(
		user=impersonated_by,
		event_type="Document Action",
		target_user=frappe.session.user,
		status="Success",
		details=f"{impersonated_by} (as {frappe.session.user}) {action} {doc.doctype} {doc.name}",
		action_doctype=doc.doctype,
		action_docname=doc.name,
		action_type=action,
	)


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
	ip = get_client_ip()
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


def _resolve_verification_staff_user(user_input: str) -> str | None:
	"""If user_input resolves to a Frappe User whose only login purpose is the
	Project Verification portal (has the 'Verification Staff' role), return their
	Frappe User name so native auth can be used. Otherwise None.

	Uses frappe.permissions.get_roles() directly rather than the frappe.get_roles()
	convenience wrapper: this runs during before_login, before any session exists,
	and frappe.get_roles() unconditionally returns ["Guest"] whenever
	frappe.local.session isn't set yet — silently ignoring the username argument."""
	import frappe.permissions

	name = frappe.db.get_value("User", user_input, "name")
	if not name:
		return None
	if "Verification Staff" in frappe.permissions.get_roles(name):
		return name
	return None


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
			f"prorndadmin login failed from IP {get_client_ip()}",
			"AdminBypass",
		)
		log_admin_access(
			user=user_input,
			event_type="Login",
			status="Failed",
			details=f"Invalid prorndadmin password for input '{user_input}'",
		)
		return frappe._dict({"name": user_input, "enabled": 1, "is_authenticated": False})

	ext_username = _resolve_to_username(user_input)
	user = _find_frappe_user(user_input, ext_username)

	if not user:
		frappe.log_error(
			f"prorndadmin Frappe User record missing (input={user_input})", "AdminBypass"
		)
		log_admin_access(
			user=user_input,
			event_type="Login",
			status="Failed",
			details=f"Frappe User record missing for input '{user_input}'",
		)
		return frappe._dict({"name": user_input, "enabled": 0, "is_authenticated": False})

	add_authentication_log("prorndadmin bypass login", user["name"], status="Success")
	log_admin_access(
		user=user["name"],
		event_type="Login",
		status="Success",
		details=f"prorndadmin bypass login as {user['name']}",
	)
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

	# Verification Staff are portal-only accounts with no presence in the external
	# microservice (they're not IITG SSO identities) — check their Frappe-stored
	# password natively instead of proxying, same as Administrator above.
	verification_user = _resolve_verification_staff_user(user_name)
	if verification_user:
		return cls._original_find_by_credentials.__func__(cls, verification_user, password, validate_password)

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
	log_admin_access(
		user=frappe.session.user,
		event_type="Impersonate",
		target_user=target_name,
		status="Success",
		details=f"{frappe.session.user} impersonated {target_name}",
	)
	frappe.db.commit()

	# Swap session — rewrites sid cookie and all session state for target_name
	frappe.local.login_manager.impersonate(target_name)

	return {"message": f"Impersonating {target_name}"}


def log_admin_logout(login_manager=None, **kwargs):
	"""
	on_logout hook. Frappe flags impersonated sessions via set_impersonated(), stashing
	the original user in session data — use that to attribute the logout back to
	prorndadmin even though frappe.session.user is the impersonated account by then.
	"""
	impersonated_by = frappe.session.data.get("impersonated_by")
	if impersonated_by:
		log_admin_access(
			user=impersonated_by,
			event_type="Logout",
			target_user=frappe.session.user,
			status="Success",
			details=f"{impersonated_by} ended impersonation of {frappe.session.user}",
		)
		return

	username = frappe.db.get_value("User", frappe.session.user, "username")
	if username == _PRORNDADMIN_USERNAME:
		log_admin_access(
			user=frappe.session.user,
			event_type="Logout",
			status="Success",
			details="prorndadmin logged out",
		)
