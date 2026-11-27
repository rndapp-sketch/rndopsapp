"""Role delegation grants and profile switching."""

import json

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from rndopsapp.rndopsapp.role_delegation.audit import log
from rndopsapp.rndopsapp.role_delegation.constants import (
	DELEGABLE_ROLES,
	DELEGATE_ROLES,
	SELF_PROFILE,
	SESSION_KEY,
)

DOCTYPE = "Role Delegation"


def is_enabled():
	"""The feature is off unless site_config.json has "allow_role_delegation": 1."""
	return bool(cint(frappe.conf.get("allow_role_delegation")))


def assigned_roles(user):
	"""Roles actually assigned to a user, ignoring any acting profile."""
	return set(
		frappe.get_all("Has Role", filters={"parenttype": "User", "parent": user}, pluck="role")
	)


def is_enabled_system_user(user):
	row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
	return bool(row and row.enabled and row.user_type == "System User")


def grant_state(grant):
	if grant.status == "Revoked":
		return "revoked"
	now = now_datetime()
	if now < get_datetime(grant.from_datetime):
		return "scheduled"
	if now > get_datetime(grant.to_datetime):
		return "expired"
	return "active"


def grant_error(grant, user):
	"""Why `user` cannot use this grant right now, or None if they can."""
	if grant.delegate != user:
		return "This delegation was not given to you."
	state = grant_state(grant)
	if state != "active":
		return f"This delegation is {state}."
	if not (is_enabled_system_user(grant.delegator) and is_enabled_system_user(grant.delegate)):
		return "A user in this delegation is disabled."
	held = assigned_roles(grant.delegator)
	roles = [r.role for r in grant.roles]
	if not roles or any(r not in DELEGABLE_ROLES or r not in held for r in roles):
		return "The delegator no longer holds a delegated role."
	if not assigned_roles(grant.delegate).intersection(DELEGATE_ROLES):
		return "You no longer hold a role that can receive a delegation."
	return None


def load_grant(name):
	if not name or not isinstance(name, str) or not frappe.db.exists(DOCTYPE, name):
		return None
	return frappe.get_doc(DOCTYPE, name)


# ---------------------------------------------------------------- grants


def create_role_delegation(delegate, roles, from_datetime, to_datetime, reason):
	_require_feature()
	_require_login()
	refuse_while_acting()

	if isinstance(roles, str):
		try:
			roles = json.loads(roles)
		except ValueError:
			roles = [roles]
	if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
		frappe.throw(_("roles must be a list of role names."))
	if not (delegate and from_datetime and to_datetime and (reason or "").strip()):
		frappe.throw(_("delegate, roles, from_datetime, to_datetime and reason are required."))

	grant = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"delegator": frappe.session.user,
			"delegate": delegate,
			"roles": [{"role": r} for r in roles],
			"from_datetime": from_datetime,
			"to_datetime": to_datetime,
			"reason": reason.strip(),
		}
	).insert(ignore_permissions=True)
	log("grant", frappe.session.user, grant, message=f"to {grant.delegate}: {grant.reason}")
	return _serialize(grant)


def revoke_role_delegation(delegation):
	_require_feature()
	_require_login()
	refuse_while_acting()

	grant = load_grant(delegation)
	user = frappe.session.user
	allowed = grant and (grant.delegator == user or "System Manager" in frappe.get_roles(user))
	if not allowed:
		frappe.throw(_("You cannot revoke this delegation."), frappe.PermissionError)
	if grant.status == "Revoked":
		frappe.throw(_("This delegation is already revoked."))

	grant.status = "Revoked"
	grant.revoked_by = user
	grant.revoked_at = now_datetime()
	grant.save(ignore_permissions=True)
	log("revoke", user, grant)
	return _serialize(grant)


def get_role_delegations():
	_require_feature()
	_require_login()
	user = frappe.session.user

	def rows(field):
		names = frappe.get_all(DOCTYPE, filters={field: user}, pluck="name", order_by="creation desc")
		return [_serialize(frappe.get_doc(DOCTYPE, n)) for n in names]

	held = assigned_roles(user)
	return {
		"given": rows("delegator"),
		"received": rows("delegate"),
		"delegable_roles": [r for r in DELEGABLE_ROLES if r in held],
	}


def _serialize(grant):
	return {
		"name": grant.name,
		"delegator": grant.delegator,
		"delegator_name": _full_name(grant.delegator),
		"delegate": grant.delegate,
		"delegate_name": _full_name(grant.delegate),
		"roles": [r.role for r in grant.roles],
		"from_datetime": _format(grant.from_datetime),
		"to_datetime": _format(grant.to_datetime),
		"reason": grant.reason,
		"status": grant.status,
		"state": grant_state(grant),
	}


def _full_name(user):
	return frappe.db.get_value("User", user, "full_name") or user


def _format(value):
	return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- switching


def get_acting_profiles():
	_require_login()
	if not is_enabled():
		return {"enabled": False, "current": SELF_PROFILE, "profiles": [_own_profile()]}

	user = frappe.session.user
	current = frappe.local.session.data.get(SESSION_KEY)
	if current:
		grant = load_grant(current)
		error = grant_error(grant, user) if grant else "This delegation no longer exists."
		if error:
			end_acting(error, grant)
			current = None

	profiles = [_own_profile()]
	for name in frappe.get_all(
		DOCTYPE, filters={"delegate": user, "status": "Active"}, pluck="name", order_by="from_datetime"
	):
		grant = frappe.get_doc(DOCTYPE, name)
		if grant_error(grant, user):
			continue
		roles = [r.role for r in grant.roles]
		delegator_name = _full_name(grant.delegator)
		profiles.append(
			{
				"id": grant.name,
				"delegator": grant.delegator,
				"delegator_name": delegator_name,
				"roles": roles,
				"valid_till": _format(grant.to_datetime),
				"label": f"{', '.join(roles)} (for {delegator_name})",
			}
		)
	return {"enabled": True, "current": current or SELF_PROFILE, "profiles": profiles}


def _own_profile():
	return {"id": SELF_PROFILE, "label": "My profile"}


def switch_profile(delegation):
	_require_feature()
	_require_session()
	user = frappe.session.user

	grant = load_grant(delegation)
	error = grant_error(grant, user) if grant else "Delegation not found."
	if error:
		log("denied", user, grant, result="Failed", delegation=str(delegation), message=error)
		frappe.db.commit()
		# One message for "not yours" and "not found", so grant names cannot be probed.
		if not grant or grant.delegate != user:
			error = "Delegation not found."
		frappe.throw(_(error), frappe.PermissionError)

	previous = frappe.local.session.data.get(SESSION_KEY)
	if previous != grant.name:
		if previous:
			log("switch_out", user, load_grant(previous), delegation=previous, message="switched")
		frappe.local.session.data[SESSION_KEY] = grant.name
		log("switch_in", user, grant)
		_save_session()
	return get_acting_profiles()


def switch_to_own_profile():
	"""Always allowed for a logged-in session, whatever the state of the grant."""
	_require_session()
	previous = frappe.local.session.data.get(SESSION_KEY)
	if previous:
		end_acting("manual", load_grant(previous) if is_enabled() else None)
	return get_acting_profiles()


def end_acting(reason, grant=None):
	"""Return the session to the user's own profile and record why. Commits."""
	previous = frappe.local.session.data.pop(SESSION_KEY, None)
	if not previous:
		return
	if is_enabled():
		log("switch_out", frappe.session.user, grant, delegation=previous, message=reason)
	_save_session()


def _save_session():
	frappe.local.session_obj.update(force=True)
	frappe.db.commit()


def on_logout(login_manager=None, **kwargs):
	"""The stored profile dies with the session; this only records it."""
	try:
		previous = (frappe.local.session.data or {}).get(SESSION_KEY)
		if previous and is_enabled():
			log("switch_out", frappe.session.user, load_grant(previous), delegation=previous, message="logout")
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Role delegation logout log failed")


# ---------------------------------------------------------------- guards


def refuse_while_acting():
	if getattr(frappe.local, "role_delegation", None):
		frappe.throw(
			_("Switch back to your own profile to do this."),
			frappe.PermissionError,
		)


def _require_feature():
	if not is_enabled():
		frappe.throw(_("Role delegation is not enabled on this site."), frappe.PermissionError)


def _require_login():
	if frappe.session.user == "Guest":
		frappe.throw(_("You must be logged in."), frappe.PermissionError)


def _require_session():
	_require_login()
	request_has_token = bool(getattr(frappe.local, "request", None)) and bool(
		frappe.get_request_header("Authorization")
	)
	if request_has_token or not getattr(frappe.local, "session_obj", None):
		frappe.throw(_("Switching profile needs a browser login session."), frappe.PermissionError)
