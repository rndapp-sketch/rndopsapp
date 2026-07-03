# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class TopUpFellowship(Document):
	pass


def extract_eval_expression(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


@frappe.whitelist()
def get_top_up_fellowship_fields(doc_name=None):
	"""
	Return Top Up Fellowship field metadata + prefill data.
	- doc_name: Project Registration.name (optional). Used to prefill project info.
	"""
	meta = frappe.get_meta("Top Up Fellowship")
	fields = []
	for f in meta.get("fields"):
		# Render "Name of the Student" as a Link-style dropdown populated from User (role=Student)
		fieldtype = f.fieldtype
		if f.fieldname == "name_of_student":
			fieldtype = "Link"

		fields.append(
			{
				"fieldname": f.fieldname,
				"label": f.label,
				"fieldtype": fieldtype,
				"options": getattr(f, "options", None),
				"mandatory": getattr(f, "reqd", False),
				"hidden": getattr(f, "hidden", False),
				"read_only": getattr(f, "read_only", False),
				"description": getattr(f, "description", "") or "",
				"default": getattr(f, "default", None),
				"depends_on": getattr(f, "depends_on", None),
				"mandatory_depends_on": getattr(f, "mandatory_depends_on", None),
				"read_only_depends_on": getattr(f, "read_only_depends_on", None),
				"depends_on_eval": extract_eval_expression(getattr(f, "depends_on", None)),
				"mandatory_depends_on_eval": extract_eval_expression(getattr(f, "mandatory_depends_on", None)),
				"read_only_depends_on_eval": extract_eval_expression(getattr(f, "read_only_depends_on", None)),
			}
		)

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	# Prefill current user's webmail
	try:
		current_user = frappe.session.user
		if current_user and current_user not in ["Administrator", "Guest"]:
			prefill_data["webmail"] = current_user
	except Exception:
		pass

	# Populate Department link options
	try:
		depts = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "department_name as label"],
			limit_page_length=500,
		)
		link_options["dept_centre"] = depts
	except Exception:
		pass

	# Populate Student dropdown for name_of_student (Users with role = Student)
	try:
		student_rows = frappe.get_all(
			"Has Role",
			filters={"role": "Student", "parenttype": "User"},
			fields=["parent"],
			limit_page_length=0,
		)
		emails = list({r.parent for r in student_rows if r.parent})
		if emails:
			users = frappe.get_all(
				"User",
				filters={"name": ["in", emails], "enabled": 1},
				fields=["name", "full_name"],
				limit_page_length=0,
			)
			link_options["name_of_student"] = [
				{"value": u.name, "label": u.full_name or u.name} for u in users
			]
	except Exception:
		pass

	# If a project is provided, attach PI webmail as a hint
	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'").strip()
		try:
			project = frappe.db.get_value(
				"Project Registration",
				doc_name,
				["name", "project_title", "project_number", "pi_webmail"],
				as_dict=True,
			)
			if project:
				related_project_data = project
				if project.get("pi_webmail"):
					prefill_data["pi_webmail"] = project["pi_webmail"]
		except Exception:
			pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}


@frappe.whitelist()
def save_top_up_fellowship_data(data):
	"""Save (insert or update) a Top Up Fellowship document. Expects JSON string or dict."""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if docname:
			doc = frappe.get_doc("Top Up Fellowship", docname)
		else:
			doc = frappe.new_doc("Top Up Fellowship")

		simple_fields = [
			"name_of_student",
			"roll_number",
			"dept_centre",
			"contact_number",
			"account_number",
			"bank_name",
			"ifsc",
			"branch_code",
			"account_holder_name",
			"programme",
			"webmail",
			"pi_webmail",
			"checkbox1",
			"checkbox2",
			"checkbox3",
			"amended_from",
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				if field.startswith("checkbox"):
					doc.set(field, 1 if val in [1, "1", True, "True"] else 0)
				else:
					doc.set(field, val if val != "null" else None)

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_student_details(email):
	"""Return roll number (employee_id) and department for a student User."""
	try:
		if not email:
			return {}
		user = frappe.db.get_value(
			"User",
			email,
			["employee_id", "department_name", "full_name"],
			as_dict=True,
		)
		if not user:
			return {}
		return {
			"roll_number": user.get("employee_id") or "",
			"dept_centre": user.get("department_name") or "",
			"full_name": user.get("full_name") or "",
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship get_student_details")
		return {}


@frappe.whitelist()
def submit_top_up_fellowship(docname):
	"""Submit a Top Up Fellowship document."""
	try:
		doc = frappe.get_doc("Top Up Fellowship", docname)
		doc.flags.ignore_permissions = True
		doc.submit()
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Top Up Fellowship Submit Error")
		return {"status": "error", "message": str(e)}
