# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

from rndopsapp.rndopsapp.form_fields import get_dynamic_form_data
from rndopsapp.rndopsapp.working_days import add_working_days
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.html_utils import sanitize_html


# ── Extension eligibility policy (IIT-G) ──────────────────────────────────────
# 1. Apply only within the last APPLICATION_WINDOW_MONTHS of the term completion date.
# 2. Total service may not exceed MAX_TOTAL_SERVICE_MONTHS.
# 3. Max grantable extension = MAX_TOTAL_SERVICE_MONTHS - months already worked.
MAX_TOTAL_SERVICE_MONTHS = 33
APPLICATION_WINDOW_MONTHS = 1


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
		self.refresh_new_tenure_preview()

	def before_submit(self):
		# Fires on the applicant's initial submission (docstatus 0 -> 1), which in
		# this workflow is the Draft -> Pending PI Approval transition, as well as
		# the direct-submit fallback. Enforce applicant eligibility here so no
		# submission path (workflow action or raw submit) can bypass it.
		self.validate_applicant_eligibility()

	# ── Eligibility policy helpers ────────────────────────────────────────────
	def get_service_context(self):
		"""Return (total_months_worked, current_term_completion_date) from the
		linked Project Staff Details tenure rows. Falls back to values stored on
		this document when tenure history is unavailable."""
		from frappe.utils import getdate

		total_months = 0
		term_completion = getdate(self.ex_date_of_expiry) if self.ex_date_of_expiry else None

		ps_details_name = None
		if self.ex_emp_id:
			ps_details_name = frappe.db.get_value(
				"Project Staff Details", {"ps_emp_id": self.ex_emp_id}, "name"
			)
		if ps_details_name:
			parent_doc = frappe.get_doc("Project Staff Details", ps_details_name)
			tenures = parent_doc.get("table_ymed") or []
			valid_tenures = [t for t in tenures if t.pstd_joining_date and t.pstd_term_completion_date]
			if valid_tenures:
				sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
				for t in sorted_tenures:
					d1 = getdate(t.pstd_joining_date)
					d2 = getdate(t.pstd_term_completion_date)
					days = (d2 - d1).days + 1
					total_months += round(days / 30.437)
				term_completion = getdate(sorted_tenures[-1].pstd_term_completion_date)

		# Fallback to the applicant-entered months when no tenure history exists.
		if total_months == 0 and self.ex_no_of_mon_worked:
			try:
				total_months = int(float(self.ex_no_of_mon_worked))
			except (ValueError, TypeError):
				pass

		return total_months, term_completion

	def _validate_application_window(self, term_completion):
		"""Rule 1: apply only within the last APPLICATION_WINDOW_MONTHS of the
		(current/new) term completion date."""
		from frappe.utils import getdate, add_months, today, formatdate

		if not term_completion:
			return  # Can't determine the term completion date — don't block.
		window_open = add_months(getdate(term_completion), -APPLICATION_WINDOW_MONTHS)
		if getdate(today()) < getdate(window_open):
			frappe.throw(_(
				"You can apply for an extension only within the last {0} month of your "
				"term completion date ({1}). The application window opens on {2}."
			).format(APPLICATION_WINDOW_MONTHS, formatdate(term_completion), formatdate(window_open)))

	def _validate_service_cap(self, total_months):
		"""Rule 2: total service may not exceed MAX_TOTAL_SERVICE_MONTHS."""
		if total_months > MAX_TOTAL_SERVICE_MONTHS:
			frappe.throw(_(
				"You have already completed {0} months of service, which exceeds the "
				"maximum permissible {1} months. No further extension can be applied for."
			).format(total_months, MAX_TOTAL_SERVICE_MONTHS))
		if total_months >= MAX_TOTAL_SERVICE_MONTHS:
			frappe.throw(_(
				"You have completed the maximum permissible service period of {0} months. "
				"No further extension can be applied for."
			).format(MAX_TOTAL_SERVICE_MONTHS))

	def validate_period_cap(self, period, total_months, label):
		"""Rule 3: months_worked + granted period may not exceed the cap."""
		if period in (None, ""):
			return
		try:
			period_int = int(float(period))
		except (ValueError, TypeError):
			frappe.throw(_("Invalid extension period: {0}").format(period))
		max_allowed = max(0, MAX_TOTAL_SERVICE_MONTHS - total_months)
		if period_int > max_allowed:
			frappe.throw(_(
				"The extension {0} ({1} months) cannot exceed the maximum of {2} month(s) "
				"({3} - {4} already worked). Total service cannot exceed {3} months."
			).format(label, period_int, max_allowed, MAX_TOTAL_SERVICE_MONTHS, total_months))

	def validate_applicant_eligibility(self):
		"""Applicant-stage gate: window + service cap + sought-period cap."""
		total_months, term_completion = self.get_service_context()
		self._validate_application_window(term_completion)
		self._validate_service_cap(total_months)
		self.validate_period_cap(self.ex_period, total_months, _("sought"))

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

	def refresh_new_tenure_preview(self):
		"""Recompute the system-suggested new term dates whenever the
		staff-allowed period changes, and default the editable "final" dates to
		that suggestion the first time — once the staff (or HR) has edited the
		final dates, later re-saves no longer overwrite their edit."""
		if not self.ex_period_staff or not self.ex_emp_id:
			return
		try:
			preview = self.compute_new_tenure_preview()
		except frappe.ValidationError:
			return  # e.g. no tenure history yet — nothing to preview.

		self.ex_computed_new_joining_date = preview["new_joining_date"]
		self.ex_computed_new_completion_date = preview["new_completion_date"]

		if not self.ex_final_new_joining_date:
			self.ex_final_new_joining_date = preview["new_joining_date"]
		if not self.ex_final_new_completion_date:
			self.ex_final_new_completion_date = preview["new_completion_date"]

	def compute_new_tenure_preview(self, period=None, increment=None):
		"""Dry-run computation (no DB writes) of the new tenure start/end dates
		and basic salary that granting `period` months of extension would
		produce, based on this employee's current tenure history. Falls back to
		the staff-approval fields on this doc when period/increment are not
		passed explicitly. Used both to populate the read-only "system
		suggested" fields and by the standalone preview API."""
		if not self.ex_emp_id:
			frappe.throw(_("Employee Id is required to compute the new tenure preview."))
		period = period if period not in (None, "") else self.ex_period_staff
		increment = increment if increment not in (None, "") else self.increment_by_staff
		return compute_new_tenure(self.ex_emp_id, period, increment)

	def auto_create_tenure_record(self):
		if not self.ex_emp_id:
			return

		if not self.ex_period_staff:
			frappe.throw(_("Period Of Re-Engagement/Extension Allowed by Staff (ex_period_staff) is required to calculate Term Completion Date."))

		preview = self.compute_new_tenure_preview()

		# Rule 3 (final guard): the staff-allowed period cannot push total service
		# beyond the cap. total_months here is the prior service (new row not yet added).
		self.validate_period_cap(self.ex_period_staff, preview["total_months_worked"], _("allowed by Staff"))

		# The staff-facing dashboard shows these system-suggested dates and lets
		# the applicant/HR edit them before approval; the edited value (if any)
		# takes precedence over the computed one.
		self.db_set("ex_computed_new_joining_date", preview["new_joining_date"])
		self.db_set("ex_computed_new_completion_date", preview["new_completion_date"])

		new_joining_date = self.ex_final_new_joining_date or preview["new_joining_date"]
		new_term_completion_date = self.ex_final_new_completion_date or preview["new_completion_date"]
		new_basic_salary = preview["new_basic_salary"]

		ps_details_name = frappe.db.get_value("Project Staff Details", {"ps_emp_id": self.ex_emp_id}, "name")
		parent_doc = frappe.get_doc("Project Staff Details", ps_details_name)

		# Update parent current basic salary & append new tenure row to child table (table_ymed)
		parent_doc.ps_basic_salary = new_basic_salary
		parent_doc.append("table_ymed", {
			"pstd_joining_date": new_joining_date,
			"pstd_term_completion_date": new_term_completion_date,
			"pstd_basic_salary": new_basic_salary,
			"pstd_increment": self.increment_by_staff or None,
			"pstd_extension_sought": self.ex_period_staff or self.ex_period,
			"pstd_pi_extension_sought": self.ex_period_pi,
			"pstd_staff_extension_sought": self.ex_period_staff,
			"pstd_scr_id": self.ex_scr_id or None,
		})

		# The parent doc's top-level joining/term-completion dates are what every
		# other module (Salary Module included) reads directly — without this,
		# an approved extension only shows up inside table_ymed and everything
		# else keeps displaying the stale pre-extension date.
		parent_doc.ps_joining_date = new_joining_date
		parent_doc.ps_term_completion_date = new_term_completion_date

		# Record the committee that authorized this extension on the parent
		# record too, mirroring how scr_id is set at initial joining — so the
		# most recent extension's committee is always the one on file.
		if self.ex_scr_id:
			parent_doc.scr_id = self.ex_scr_id

		parent_doc.flags.ignore_permissions = True
		parent_doc.save()

		# Save the new basic pay & the final dates used back onto this extension doc
		self.db_set("ex_current_basic", new_basic_salary)
		self.db_set("ex_final_new_joining_date", new_joining_date)
		self.db_set("ex_final_new_completion_date", new_term_completion_date)


def _safe_float(val):
	if val is None or val == "":
		return 0.0
	try:
		return float(str(val).replace(",", "").strip())
	except (ValueError, TypeError):
		return 0.0


def compute_new_tenure(ex_emp_id, period, increment=None):
	"""Pure computation (no DB writes): returns the new tenure start date, end
	date, and basic salary that would result from granting `period` months of
	extension to the employee `ex_emp_id`, based on their current Project
	Staff Details tenure history. Shared by the doc's own approval-time logic
	and by the standalone preview API used for the staff dashboard."""
	from frappe.utils import getdate, add_days, add_months

	if not ex_emp_id:
		frappe.throw(_("Employee Id is required."))
	if period in (None, ""):
		frappe.throw(_("Extension period (in months) is required."))

	try:
		extension_period = int(float(period))
	except (ValueError, TypeError):
		frappe.throw(_("Invalid Extension Period: {0}").format(period))

	ps_details_name = frappe.db.get_value("Project Staff Details", {"ps_emp_id": ex_emp_id}, "name")
	if not ps_details_name:
		frappe.throw(_("Project Staff Details not found for Employee ID {0}").format(ex_emp_id))

	parent_doc = frappe.get_doc("Project Staff Details", ps_details_name)
	tenures = parent_doc.get("table_ymed") or []
	valid_tenures = [t for t in tenures if t.pstd_joining_date and t.pstd_term_completion_date]
	if not valid_tenures:
		frappe.throw(_("No existing tenure records found in Project Staff Details."))

	sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))

	# Step 1: Calculate Total Months Worked
	total_months = 0
	for t in sorted_tenures:
		d1 = getdate(t.pstd_joining_date)
		d2 = getdate(t.pstd_term_completion_date)
		days = (d2 - d1).days + 1
		total_months += round(days / 30.437)

	# Step 2: Determine New Joining Date. Term gap is 3 working days when total
	# months worked so far is a multiple of 11, otherwise 1 working day —
	# working days skip weekends and institute holidays (see working_days.py).
	latest_tenure = sorted_tenures[-1]
	latest_term_completion = getdate(latest_tenure.pstd_term_completion_date)
	gap_days = 3 if (total_months > 0 and total_months % 11 == 0) else 1
	new_joining_date = add_working_days(latest_term_completion, gap_days)

	# Step 3: Calculate New Term Completion Date based on the granted period
	new_term_completion_date = add_days(add_months(new_joining_date, extension_period), -1)

	# Step 4: Calculate New Basic Salary: (Basic in previous tenure row) + increment
	prev_basic_val = _safe_float(
		latest_tenure.pstd_basic_salary or getattr(parent_doc, "ps_basic_salary", None)
	)
	increment_val = _safe_float(increment)
	calc_basic = prev_basic_val + increment_val
	new_basic_salary = int(calc_basic) if calc_basic.is_integer() else round(calc_basic, 2)

	return {
		"total_months_worked": total_months,
		"gap_days": gap_days,
		"new_joining_date": new_joining_date,
		"new_completion_date": new_term_completion_date,
		"prev_basic_salary": prev_basic_val,
		"new_basic_salary": new_basic_salary,
	}


@frappe.whitelist()
def preview_new_tenure(ex_emp_id, period, increment=None):
	"""Dry-run preview (no DB writes) for the staff dashboard: as the staff
	member types in a number of months (and optional increment), this returns
	the probable new tenure start date, end date, and basic salary so it can
	be displayed before the extension is submitted/approved."""
	return compute_new_tenure(ex_emp_id, period, increment)


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
			"ex_current_basic", "ex_last_ex_date",
			"ex_computed_new_joining_date", "ex_computed_new_completion_date"
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
		elif fn in [
			"ex_period_staff", "increment_by_staff",
			"ex_final_new_joining_date", "ex_final_new_completion_date"
		]:
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
					"ex_period_staff", "increment_by_staff",
					"ex_final_new_joining_date", "ex_final_new_completion_date"
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
			"ex_final_new_joining_date": "ex_final_new_joining_date",
			"ex_final_new_completion_date": "ex_final_new_completion_date",
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
				"ex_doj",
				"ex_date_of_expiry",
				"ex_current_basic",
				"ex_last_ex_date",
				"ex_no_of_mon_worked",
				"ex_no_of_days_worked",
				"ex_period",
				"ex_period_pi",
				"ex_period_staff",
				"increment_by_pi",
				"increment_by_staff",
				"ex_computed_new_joining_date",
				"ex_computed_new_completion_date",
				"ex_final_new_joining_date",
				"ex_final_new_completion_date",
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

		# Per-stage policy gate on positive (forward/approve) transitions. Rejections
		# and cancellations are never blocked by the caps.
		if next_state not in ("Rejected", "Cancelled"):
			if current_state == "Draft":
				# Applicant submission: window + service cap + sought-period cap.
				# Also enforced in before_submit; kept here so the rule holds even if
				# the workflow keeps the doc at doc_status 0 past Draft.
				doc.validate_applicant_eligibility()
			else:
				total_months, _term = doc.get_service_context()
				if current_state == "Pending PI Approval":
					doc.validate_period_cap(doc.ex_period_pi, total_months, _("suggested by PI"))
				elif current_state == "Pending Staff Approval":
					doc.validate_period_cap(doc.ex_period_staff, total_months, _("allowed by Staff"))

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
