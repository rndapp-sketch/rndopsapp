"""Role Delegation Log writer."""

import frappe


def log(event, actual_user, grant=None, result="Success", **details):
	"""
	Insert one log row. The caller commits. `grant` is a Role Delegation document
	or the request's acting context.
	"""
	entry = {
		"event": event,
		"actual_user": actual_user,
		"result": result,
		"ip_address": getattr(frappe.local, "request_ip", None),
		**details,
	}
	if grant:
		entry.setdefault("delegation", grant.get("name"))
		entry.setdefault("delegator", grant.get("delegator"))
		roles = grant.get("roles") or []
		entry.setdefault(
			"delegated_roles",
			", ".join(r if isinstance(r, str) else r.role for r in roles),
		)
	for key, value in entry.items():
		if isinstance(value, str) and key not in ("message", "delegated_roles"):
			entry[key] = value[:140]

	frappe.get_doc({"doctype": "Role Delegation Log", **entry}).insert(
		ignore_permissions=True, ignore_links=True
	)
