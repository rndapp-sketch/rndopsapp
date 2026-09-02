# START MKY Edit - Create User API wrapper - 2026-05-19 12:35 IST
# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
API wrapper for the Frappe core `User` DocType, following the standard
endpoint pattern defined in APPS_DOCUMENTATION.md.

Endpoints:
  - get_user_fields(doc_name=None)        : metadata + prefill + link options
  - save_user_data(data)                  : create or update a User
  - get_user_list(filters=None, limit=100): paginated list of Users
  - delete_user(docname)                  : delete a User
"""

import json

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Scalar fields exposed for create/update via save_user_data.
# Intentionally excludes internal/audit fields (creation, modified, last_login,
# reset_password_key, last_active, last_ip, etc.) and password hash fields.
USER_WRITABLE_FIELDS = [
	"email",
	"first_name",
	"middle_name",
	"last_name",
	"username",
	"full_name",
	"enabled",
	"user_type",
	"employee_id",
	"empclass",
	"department_name",
	"designation_name",
	"piheadmentor_user_id",
	"language",
	"time_zone",
	"role_profile_name",
	"send_welcome_email",
	"new_password",
	"desk_theme",
	"mute_sounds",
	"search_bar",
	"notifications",
	"list_sidebar",
	"bulk_actions",
	"view_switcher",
	"form_sidebar",
	"timeline",
	"dashboard",
	"thread_notify",
	"send_me_a_copy",
	"allowed_in_mentions",
	"document_follow_notify",
	"document_follow_frequency",
	"follow_created_documents",
	"follow_commented_documents",
	"follow_liked_documents",
	"follow_assigned_documents",
	"follow_shared_documents",
	"simultaneous_sessions",
	"bypass_restrict_ip_check_if_2fa_enabled",
	"logout_all_sessions",
]

# Child table mapping: parent fieldname -> (child doctype, writable fields)
USER_CHILD_TABLES = {
	"roles": ("Has Role", ["role"]),
	"block_modules": ("Block Module", ["module"]),
	"user_emails": (
		"User Email",
		["email_account", "email_id", "awaiting_password", "enable_outgoing", "enable_incoming", "default_outgoing"],
	),
	"social_logins": ("User Social Login", ["provider", "userid", "username"]),
	"defaults": ("DefaultValue", ["defkey", "defvalue"]),
}


def _extract_eval(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	return expression[5:].strip() if expression.startswith("eval:") else expression


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_user_fields(doc_name=None):
	"""
	Returns User field metadata, prefill data (if doc_name provided),
	link options for dropdowns, and any enabled Client Scripts.
	"""
	meta = frappe.get_meta("User")

	fields = []
	for f in meta.get("fields"):
		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": _extract_eval(f.depends_on),
			"mandatory_depends_on_eval": _extract_eval(f.mandatory_depends_on),
			"read_only_depends_on_eval": _extract_eval(f.read_only_depends_on),
		}

		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				field_data["child_fields"] = [
					{
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": cf.options,
						"mandatory": cf.reqd,
						"hidden": cf.hidden,
						"read_only": cf.read_only,
						"in_list_view": cf.in_list_view,
					}
					for cf in child_meta.get("fields")
				]
			except Exception:
				pass

		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		doc = frappe.get_doc("User", doc_name)
		prefill_data = doc.as_dict()
		# Never leak the password hash
		prefill_data.pop("password", None)
		prefill_data.pop("new_password", None)

	# --- Link options ---
	try:
		link_options["role_profile_name"] = frappe.get_all(
			"Role Profile", fields=["name as value", "role_profile as label"], limit_page_length=0
		)
	except Exception:
		pass

	try:
		link_options["roles"] = frappe.get_all(
			"Role",
			filters={"disabled": 0},
			fields=["name as value", "name as label"],
			limit_page_length=0,
		)
	except Exception:
		pass

	try:
		link_options["department_name"] = frappe.get_all(
			"Department_prornd", fields=["name as value", "name as label"], limit_page_length=0
		)
	except Exception:
		pass

	try:
		link_options["piheadmentor_user_id"] = frappe.get_all(
			"User",
			filters={"enabled": 1, "user_type": "System User"},
			fields=["name as value", "full_name as label"],
			limit_page_length=0,
		)
	except Exception:
		pass

	# Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "User", "enabled": 1},
			fields=["name", "script", "view"],
		)
		for s in scripts:
			client_scripts.append({"name": s.name, "script": s.script, "view": s.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
	}


@frappe.whitelist()
def save_user_data(data):
	"""
	Creates a new User or updates an existing one.
	`name` (email) in the payload signals an update.
	Handles the `roles`, `block_modules`, `user_emails`, `social_logins`
	and `defaults` child tables.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name") or data.get("email")
		if doc_name and frappe.db.exists("User", doc_name):
			doc = frappe.get_doc("User", doc_name)
		else:
			doc = frappe.new_doc("User")
			if not data.get("email"):
				frappe.throw(_("`email` is required to create a new User."))

		# Scalar fields
		for field in USER_WRITABLE_FIELDS:
			if field in data and data[field] is not None:
				doc.set(field, data[field])

		# Child tables
		for parent_field, (child_dt, child_fields) in USER_CHILD_TABLES.items():
			if parent_field not in data:
				continue
			rows = data.get(parent_field) or []
			doc.set(parent_field, [])
			for row in rows:
				if not isinstance(row, dict):
					# Allow shorthand: ["role A", "role B"] for roles/block_modules
					if parent_field == "roles":
						row = {"role": row}
					elif parent_field == "block_modules":
						row = {"module": row}
					else:
						continue
				doc.append(
					parent_field,
					{cf: row.get(cf) for cf in child_fields if row.get(cf) not in [None, ""]},
				)

		if doc.is_new():
			doc.insert(ignore_permissions=True)
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "User Save Error")
		frappe.throw(_("Failed to save User: {0}").format(str(e)))


@frappe.whitelist()
def get_user_list(filters=None, limit=100):
	"""
	Returns a paginated list of Users with key columns suitable for tables.
	"""
	try:
		parsed_filters = {}
		if filters:
			parsed_filters = json.loads(filters) if isinstance(filters, str) else filters

		users = frappe.get_all(
			"User",
			filters=parsed_filters,
			fields=[
				"name",
				"email",
				"username",
				"full_name",
				"first_name",
				"last_name",
				"enabled",
				"user_type",
				"employee_id",
				"department_name",
				"designation_name",
				"role_profile_name",
				"piheadmentor_user_id",
				"language",
				"time_zone",
				"last_login",
				"last_active",
				"modified",
				"creation",
			],
			order_by="modified desc",
			limit=int(limit),
		)
		return {"status": "success", "data": users}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "User List Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_user(docname):
	"""
	Deletes a User. Refuses to delete Administrator / Guest / the current
	logged-in user as a safety net.
	"""
	try:
		if docname in ("Administrator", "Guest"):
			frappe.throw(_("Cannot delete the system user '{0}'.").format(docname))

		if docname == frappe.session.user:
			frappe.throw(_("You cannot delete the currently logged-in user."))

		if not frappe.db.exists("User", docname):
			return {"status": "error", "message": _("User '{0}' not found.").format(docname)}

		frappe.delete_doc("User", docname, ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "message": _("User '{0}' deleted successfully.").format(docname)}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "User Delete Error")
		return {"status": "error", "message": str(e)}
# END MKY Edit - Create User API wrapper - 2026-05-19 12:35 IST
