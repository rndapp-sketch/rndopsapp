# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

from rndopsapp.rndopsapp.form_fields import get_dynamic_form_data
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.html_utils import sanitize_html


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()
	
	return expression


class ProjectStaffExtension(Document):
	def validate(self):
		self.set_fields_from_project_staff_details()

	def set_fields_from_project_staff_details(self):
		if self.ex_emp_id:
			ps_details_name = frappe.db.get_value("Project Staff Details", {"ps_emp_id": self.ex_emp_id}, "name")
			if ps_details_name:
				doc = frappe.get_doc("Project Staff Details", ps_details_name)
				self.ex_last_ex_date = doc.get_date_of_last_extension()

				# Get current details from the newest/latest row
				tenures = doc.get("table_ymed") or []
				valid_tenures = [t for t in tenures if t.pstd_joining_date]
				if valid_tenures:
					from frappe.utils import getdate
					sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
					latest_tenure = sorted_tenures[-1]

					self.ex_doj = doc.ps_joining_date or sorted_tenures[0].pstd_joining_date
					self.ex_date_of_expiry = latest_tenure.pstd_term_completion_date
					self.ex_current_basic = latest_tenure.pstd_basic_salary

	def auto_create_tenure_record(self):
		if not self.ex_emp_id:
			return

		ps_details_name = frappe.db.get_value("Project Staff Details", {"ps_emp_id": self.ex_emp_id}, "name")
		if not ps_details_name:
			frappe.throw(_("Project Staff Details not found for Employee ID {0}").format(self.ex_emp_id))

		parent_doc = frappe.get_doc("Project Staff Details", ps_details_name)

		tenures = parent_doc.get("table_ymed") or []
		valid_tenures = [t for t in tenures if t.pstd_joining_date and t.pstd_term_completion_date]

		if not valid_tenures:
			frappe.throw(_("No existing tenure records found in Project Staff Details."))

		from frappe.utils import getdate, add_days, add_months
		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))

		# Step 1: Calculate Total Months Worked
		total_months = 0
		for t in sorted_tenures:
			d1 = getdate(t.pstd_joining_date)
			d2 = getdate(t.pstd_term_completion_date)
			days = (d2 - d1).days + 1
			total_months += round(days / 30.437)

		# Step 2: Determine New Joining Date
		latest_tenure = sorted_tenures[-1]
		latest_term_completion = getdate(latest_tenure.pstd_term_completion_date)

		if total_months > 0 and total_months % 11 == 0:
			new_joining_date = add_days(latest_term_completion, 3)
		else:
			new_joining_date = add_days(latest_term_completion, 1)

		# Step 3: Calculate New Term Completion Date based on ex_period_staff (Period Of Re-Engagement/Extension Allowed by Staff (Month))
		final_period = self.ex_period_staff
		if not final_period:
			frappe.throw(_("Period Of Re-Engagement/Extension Allowed by Staff (ex_period_staff) is required to calculate Term Completion Date."))

		try:
			extension_period = int(final_period)
		except (ValueError, TypeError):
			frappe.throw(_("Invalid Extension Period: {0}").format(final_period))

		new_term_completion_date = add_days(add_months(new_joining_date, extension_period), -1)

		# Step 4: Calculate New Basic Salary: (Basic in previous tenure row) + (increment_by_staff)
		def _safe_float(val):
			if val is None or val == "":
				return 0.0
			try:
				return float(str(val).replace(",", "").strip())
			except (ValueError, TypeError):
				return 0.0

		prev_basic_val = _safe_float(
			latest_tenure.pstd_basic_salary
			or getattr(self, "ex_current_basic", None)
			or getattr(parent_doc, "ps_basic_salary", None)
		)

		staff_inc = getattr(self, "increment_by_staff", None)
		increment_val = _safe_float(staff_inc)

		calc_basic = prev_basic_val + increment_val
		new_basic_salary = int(calc_basic) if calc_basic.is_integer() else round(calc_basic, 2)

		# Step 5: Update parent current basic salary & append new tenure row to child table (table_ymed)
		parent_doc.ps_basic_salary = new_basic_salary
		parent_doc.append("table_ymed", {
			"pstd_joining_date": new_joining_date,
			"pstd_term_completion_date": new_term_completion_date,
			"pstd_basic_salary": new_basic_salary,
			"pstd_increment": staff_inc or None,
			"pstd_extension_sought": self.ex_period_staff or self.ex_period,
			"pstd_pi_extension_sought": self.ex_period_pi,
			"pstd_staff_extension_sought": self.ex_period_staff,
		})

		parent_doc.flags.ignore_permissions = True
		parent_doc.save()

		# Step 6: Save the new basic pay back to this extension's ex_current_basic field
		self.db_set("ex_current_basic", new_basic_salary)


@frappe.whitelist()
def get_project_staff_extension_fields(doc_name=None):
	"""
	API to return Project Staff Extension field metadata and prefill data.
	"""
	res = get_dynamic_form_data("Project Staff Extension", doc_name)
	fields = res.get("fields", [])
	link_options = res.get("link_options", {})
	prefill_data = res.get("prefill_data", {})

	# Set up dynamic depends_on and read_only expressions on the fields metadata
	for field in fields:
		fn = field["fieldname"]
		
		# 1. Read-only fields
		if fn in [
			"ex_proj_name", "ex_proj_no", "ex_name", "ex_emp_id",
			"ex_designation", "department", "ex_doj", "ex_date_of_expiry",
			"ex_current_basic", "ex_last_ex_date"
		]:
			field["read_only"] = True
			field["read_only_depends_on"] = None
			field["read_only_depends_on_eval"] = None

		# 2. Applicant fields (editable only in Draft)
		elif fn in ["ex_period", "ex_no_of_mon_worked", "ex_no_of_days_worked"]:
			field["read_only_depends_on"] = "eval:doc.workflow_state && doc.workflow_state != 'Draft'"
			field["read_only_depends_on_eval"] = "doc.workflow_state && doc.workflow_state != 'Draft'"

		# 3. PI evaluation fields (editable only in Pending PI Approval for PI role)
		elif fn in ["ex_period_pi", "increment_by_pi"]:
			field["depends_on"] = "eval:doc.workflow_state && doc.workflow_state != 'Draft'"
			field["depends_on_eval"] = "doc.workflow_state && doc.workflow_state != 'Draft'"
			field["read_only_depends_on"] = "eval:doc.workflow_state != 'Pending PI Approval' || !doc._isPI"
			field["read_only_depends_on_eval"] = "doc.workflow_state != 'Pending PI Approval' || !doc._isPI"

		# 4. Staff evaluation fields (editable only in Pending Staff Approval for Staff role)
		elif fn in ["ex_period_staff", "increment_by_staff"]:
			field["depends_on"] = "eval:doc.workflow_state && doc.workflow_state != 'Draft' && doc.workflow_state != 'Pending PI Approval'"
			field["depends_on_eval"] = "doc.workflow_state && doc.workflow_state != 'Draft' && doc.workflow_state != 'Pending PI Approval'"
			field["read_only_depends_on"] = "eval:doc.workflow_state != 'Pending Staff Approval' || !doc._isRnDStaff"
			field["read_only_depends_on_eval"] = "doc.workflow_state != 'Pending Staff Approval' || !doc._isRnDStaff"

		# 5. Conditional field: ex_no_of_days_worked
		if fn == "ex_no_of_days_worked":
			field["depends_on"] = "eval:!doc.ex_no_of_mon_worked || doc.ex_no_of_mon_worked == '0' || parseInt(doc.ex_no_of_mon_worked) < 1"
			field["depends_on_eval"] = "!doc.ex_no_of_mon_worked || doc.ex_no_of_mon_worked == '0' || parseInt(doc.ex_no_of_mon_worked) < 1"

	# Link options for dropdowns
	link_options["amended_from"] = frappe.get_all(
		"Project Staff Extension", fields=["name as value", "name as label"], limit=200,
		ignore_permissions=True,
	)

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}


@frappe.whitelist()
def save_project_staff_extension(doc_data):
	"""Saves or updates the Project Staff Extension data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Project Staff Extension:", data)  # Debug log

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Project Staff Extension", doc_name)
			doc.flags.ignore_permissions = True
			if doc.docstatus == 2:
				frappe.throw(_("Cannot edit a cancelled document."))
			elif doc.docstatus == 1:
				allowed_fields = [
					"ex_period_pi", "increment_by_pi",
					"ex_period_staff", "increment_by_staff"
				]
				for form_field in allowed_fields:
					if form_field in data:
						doc.db_set(form_field, data[form_field])
				frappe.db.commit()
				return {"status": "success", "docname": doc.name}
		else:
			doc = frappe.new_doc("Project Staff Extension")

		field_mapping = {
			"ex_proj_name": "ex_proj_name",
			"ex_proj_no": "ex_proj_no",
			"ex_name": "ex_name",
			"ex_emp_id": "ex_emp_id",
			"ex_designation": "ex_designation",
			"department": "department",
			"ex_doj": "ex_doj",
			"ex_date_of_expiry": "ex_date_of_expiry",
			"ex_last_ex_date": "ex_last_ex_date",
			"ex_no_of_mon_worked": "ex_no_of_mon_worked",
			"ex_no_of_days_worked": "ex_no_of_days_worked",
			"ex_period": "ex_period",
			"ex_current_basic": "ex_current_basic",
			"ex_period_pi": "ex_period_pi",
			"ex_period_staff": "ex_period_staff",
			"increment_by_pi": "increment_by_pi",
			"increment_by_staff": "increment_by_staff",
		}

		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Project Staff Extension: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Extension Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Project Staff Extension: {str(e)}")


@frappe.whitelist()
def submit_project_staff_extension(docname):
	"""
	Submit a Project Staff Extension document.
	"""
	try:
		doc = frappe.get_doc("Project Staff Extension", docname)
		doc.flags.ignore_permissions = True

		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Project Staff Extension '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Project Staff Extension '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Project Staff Extension '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Extension Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_project_staff_extension_list():
	"""
	Fetch all Project Staff Extension documents.
	"""
	try:
		extensions = frappe.get_all(
			"Project Staff Extension",
			fields=[
				"name",
				"ex_name",
				"ex_emp_id",
				"ex_proj_no",
				"ex_proj_name",
				"ex_designation",
				"department",
				"ex_period",
				"workflow_state",
				"docstatus",
				"modified",
				"creation",
				"owner",
			],
			order_by="modified desc",
			ignore_permissions=True,
		)
		return {"status": "success", "data": extensions}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error fetching Project Staff Extension list")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_project_staff_extension_workflow_actions(docname):
	"""
	Returns the workflow actions available to the current user for this document.
	"""
	try:
		doc = frappe.get_doc("Project Staff Extension", docname)
		doc.flags.ignore_permissions = True
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Project Staff Extension", "is_active": 1},
			"name",
		)
		if not workflow_name:
			return {"status": "success", "actions": [], "workflow_state": current_state, "docstatus": doc.docstatus}

		workflow = frappe.get_doc("Workflow", workflow_name)
		allowed_actions = []

		for transition in workflow.get("transitions", []):
			if transition.state != current_state:
				continue
			allowed_roles = transition.get("allowed") or []
			if isinstance(allowed_roles, str):
				allowed_roles = [allowed_roles]
			if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
				allowed_actions.append(transition.action)

		return {
			"status": "success",
			"actions": list(dict.fromkeys(allowed_actions)),
			"workflow_state": current_state,
			"docstatus": doc.docstatus,
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Extension Workflow Actions Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def perform_project_staff_extension_action(docname, action, comment=""):
	"""
	Executes a workflow action on a Project Staff Extension document.
	"""
	try:
		if not comment or not str(comment).strip():
			frappe.throw(_("A comment is required before performing this action."))

		doc = frappe.get_doc("Project Staff Extension", docname)
		doc.flags.ignore_permissions = True
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Project Staff Extension", "is_active": 1},
			"name",
		)
		if not workflow_name:
			frappe.throw(_("No active workflow found for Project Staff Extension."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		for t in workflow.transitions:
			if t.state != current_state or t.action != action:
				continue
			allowed_roles = t.get("allowed") or []
			if isinstance(allowed_roles, str):
				allowed_roles = [allowed_roles]
			if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(_(f"No valid transition found for action '{action}' from state '{current_state}'."))

		# Record comment
		doc.add_comment(
			"Workflow",
			sanitize_html(f"[{action}] {comment}"),
		)

		doc.workflow_state = next_state

		state_meta = next((s for s in workflow.states if s.state == next_state), None)
		if state_meta and int(state_meta.doc_status or 0) == 1 and doc.docstatus == 0:
			doc.flags.ignore_permissions = True
			doc.submit()
		elif state_meta and int(state_meta.doc_status or 0) == 2 and doc.docstatus != 2:
			doc.flags.ignore_permissions = True
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		# Create the tenure record only on final approval, once the staff-entered
		# ex_period_staff / increment_by_staff values are available.
		if next_state == "Approved":
			doc.auto_create_tenure_record()

		frappe.db.commit()

		next_actions_resp = get_project_staff_extension_workflow_actions(docname)
		return {
			"status": "success",
			"message": _(f"Action '{action}' completed. New state: {next_state}"),
			"docname": docname,
			"workflow_state": next_state,
			"docstatus": doc.docstatus,
			"next_actions": next_actions_resp.get("actions", []),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Extension Action Error")
		return {"status": "error", "message": str(e)}