# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


def _extract_eval(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	return expression[5:].strip() if expression.startswith("eval:") else expression


class ProjectStaffDetails(Document):
	def before_insert(self):
		if not self.ps_emp_id:
			self.ps_emp_id = generate_emp_id()


def generate_emp_id():
	from frappe.utils import nowdate

	year = nowdate()[:4]
	series_key = f"{year}PS"

	if not frappe.db.exists("Series", series_key):
		frappe.db.sql("INSERT INTO `tabSeries` (name, current) VALUES (%s, 0)", series_key)

	frappe.db.sql("UPDATE `tabSeries` SET current = current + 1 WHERE name = %s", series_key)
	current = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", series_key)[0][0]

	return f"{series_key}{str(current).zfill(4)}"


@frappe.whitelist()
def get_next_emp_id():
	from frappe.utils import nowdate

	year = nowdate()[:4]
	series_key = f"{year}PS"
	current = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", series_key)
	next_num = (current[0][0] if current else 0) + 1
	return f"{series_key}{str(next_num).zfill(4)}"


@frappe.whitelist()
def get_project_staff_details_fields(doc_name=None):
	"""
	Returns field metadata, prefill data (if doc_name provided), and link options.
	"""
	meta = frappe.get_meta("project_staff_details")

	fields = []
	for f in meta.get("fields"):
		field_data = {
			"fieldname":               f.fieldname,
			"label":                   f.label,
			"fieldtype":               f.fieldtype,
			"options":                 f.options,
			"mandatory":               f.reqd,
			"hidden":                  f.hidden,
			"read_only":               f.read_only,
			"description":             f.description,
			"default":                 f.default,
			"depends_on":              f.depends_on,
			"mandatory_depends_on":    f.mandatory_depends_on,
			"read_only_depends_on":    f.read_only_depends_on,
			"depends_on_eval":         _extract_eval(f.depends_on),
			"mandatory_depends_on_eval":  _extract_eval(f.mandatory_depends_on),
			"read_only_depends_on_eval":  _extract_eval(f.read_only_depends_on),
		}
		if f.fieldtype == "Table" and f.options:
			child_meta = frappe.get_meta(f.options)
			field_data["child_fields"] = [
				{
					"fieldname":    cf.fieldname,
					"label":        cf.label,
					"fieldtype":    cf.fieldtype,
					"options":      cf.options,
					"mandatory":    cf.reqd,
					"hidden":       cf.hidden,
					"read_only":    cf.read_only,
					"in_list_view": cf.in_list_view,
				}
				for cf in child_meta.get("fields")
			]
		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		doc = frappe.get_doc("project_staff_details", doc_name)
		prefill_data = doc.as_dict()

	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "project_staff_details", "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields":         fields,
		"prefill_data":   prefill_data,
		"link_options":   link_options,
		"client_scripts": client_scripts,
	}


@frappe.whitelist()
def save_project_staff_details_data(data):
	"""
	Creates a new Project Staff Details record or updates an existing one.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("project_staff_details", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("project_staff_details")

		field_mapping = [
			"ps_emp_id",
			"ps_first_name",
			"ps_middle_name",
			"ps_last_name",
			"ps_email_id",
			"ps_phone_number",
			"ps_department",
			"ps_designation",
			"ps_date_of_birth",
			"ps_fathers_name",
			"ps_present_address",
			"ps_permanent_address",
			"ps_pan",
			"ps_aadhar_number",
			"ps_blood_group",
			"ps_maritial_status",
			"ps_basic_salary",
			"ps_hra",
			"ps_ma",
			"ps_hostel",
			"ps_citizenship",
			"ps_aon",
			"ps_mro",
		]

		for field in field_mapping:
			if field in data and data[field] not in [None, ""]:
				doc.set(field, data[field])

		# Handle tenure details child table
		tenure_rows = data.get("table_ymed", [])
		if tenure_rows is not None:
			doc.set("table_ymed", [])
			child_fields = [
				"pstd_joining_date",
				"pstd_term_completion_date",
				"pstd_basic_salary",
				"pstd_increment",
				"pstd_hra",
				"pstd_extension_sought",
				"pstd_joining_number",
				"pstd_pi_extension_sought",
				"pstd_staff_extension_sought",
				"pstd_tentative_joining_date",
			]
			for row in tenure_rows:
				doc.append("table_ymed", {f: row.get(f) for f in child_fields if row.get(f) not in [None, ""]})

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Save Error")
		frappe.throw(_("Failed to save Project Staff Details: {0}").format(str(e)))


@frappe.whitelist()
def get_project_staff_details_list(filters=None, limit=100):
	"""
	Returns a paginated list of Project Staff Details records.
	"""
	try:
		parsed_filters = {}
		if filters:
			parsed_filters = json.loads(filters) if isinstance(filters, str) else filters

		records = frappe.get_all(
			"project_staff_details",
			filters=parsed_filters,
			fields=[
				"name",
				"ps_emp_id",
				"ps_first_name",
				"ps_middle_name",
				"ps_last_name",
				"ps_email_id",
				"ps_phone_number",
				"ps_department",
				"ps_designation",
				"ps_date_of_birth",
				"ps_aon",
				"docstatus",
				"modified",
				"creation",
			],
			order_by="modified desc",
			limit=int(limit),
		)
		return {"status": "success", "data": records}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Details List Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_project_staff_details(docname):
	"""
	Deletes a Project Staff Details document (only Draft records).
	"""
	try:
		doc = frappe.get_doc("project_staff_details", docname)

		if doc.docstatus == 1:
			frappe.throw(_("Cannot delete a submitted document. Cancel it first."))

		frappe.delete_doc("project_staff_details", docname, ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "message": _("Record '{0}' deleted successfully.").format(docname)}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Delete Error")
		return {"status": "error", "message": str(e)}
