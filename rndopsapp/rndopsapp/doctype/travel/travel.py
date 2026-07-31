# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


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


class Travel(Document):
	pass


@frappe.whitelist()
def get_travel_fields(doc_name=None):
	"""
	API to return Travel field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Includes client scripts and child table metadata.
	"""
	doctype_name = "Travel"
	travel_meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}

	for f in travel_meta.get("fields"):
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
			"fetch_from": f.fetch_from,
			"fetch_if_empty": f.fetch_if_empty,
			# Eval expressions for frontend conditional logic
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			# Extract eval expression for easier frontend parsing
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}
		fields.append(field_data)

		# Collect Link fields for dynamic options
		if f.fieldtype == "Link" and f.options:
			link_fields.append({"fieldname": f.fieldname, "options": f.options})

		# Fetch child table metadata for Table fields
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.get("fields"):
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": cf.options,
						"mandatory": cf.reqd,
						"hidden": cf.hidden,
						"read_only": cf.read_only,
						"description": cf.description,
						"default": cf.default,
						"fetch_from": cf.fetch_from,
						"in_list_view": cf.in_list_view,
						"columns": cf.columns,
						"depends_on": cf.depends_on,
						"depends_on_eval": extract_eval_expression(cf.depends_on),
					})
				child_table_meta[f.fieldname] = {
					"doctype": f.options,
					"fields": child_fields
				}
			except Exception:
				pass

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Travel document for editing
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			related_data = doc.as_dict()
			prefill_data = doc.as_dict()

	# Prefill current user data
	current_user = frappe.session.user
	if current_user and current_user != "Guest":
		user_data = frappe.db.get_value(
			"User",
			current_user,
			["name", "full_name", "designation_name", "department_name"],
			as_dict=True,
		)
		if user_data:
			if not prefill_data.get("webmail_id_travel"):
				prefill_data["webmail_id_travel"] = user_data.name
			if not prefill_data.get("applicant_name_travel"):
				prefill_data["applicant_name_travel"] = user_data.full_name
			if not prefill_data.get("designation_travel"):
				prefill_data["designation_travel"] = user_data.designation_name
			if not prefill_data.get("department_travel"):
				prefill_data["department_travel"] = user_data.department_name

	# ===== Link options for dropdowns =====
	# Dynamically get link options for all Link fields
	for link_field in link_fields:
		fieldname = link_field["fieldname"]
		linked_doctype = link_field["options"]

		try:
			linked_meta = frappe.get_meta(linked_doctype)
			title_field = linked_meta.title_field or "name"

			if linked_doctype == "User":
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					filters={"enabled": 1},
					fields=["name as value", "full_name as label"],
					limit_page_length=500
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype,
					fields=["name as value", f"{title_field} as label"],
					limit_page_length=500
				)
		except Exception:
			link_options[fieldname] = frappe.get_all(
				linked_doctype,
				fields=["name as value", "name as label"],
				limit_page_length=500
			)

	# Other-PI dropdown: restrict to Permanent Employees (all PIs are Permanent Employees)
	try:
		from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import _get_permanent_employee_options
		link_options["travel_other_pi_id"] = _get_permanent_employee_options()
	except Exception:
		pass

	# Department options (explicit)
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["department_travel"] = departments
	except Exception:
		link_options["department_travel"] = []

	# Designation options (from User doctype - get unique designations)
	try:
		designations_raw = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["designation"],
			limit_page_length=1000,
		)
		unique_designations = list(set(
			d.get("designation") for d in designations_raw 
			if d.get("designation")
		))
		designations = [{"value": d, "label": d} for d in sorted(unique_designations)]
		link_options["designation_travel"] = designations
	except Exception:
		link_options["designation_travel"] = []

	# Fetch Client Scripts from Frappe (stored in database)
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": doctype_name, "enabled": 1},
			fields=["name", "script", "view"]
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view
			})
	except Exception:
		pass

	# Inject live SCL balance into the HTML field so React sees real data.
	# For an existing document, the balance must be computed for the actual
	# traveler (doc.webmail_id_travel) — not the person currently viewing the
	# page. Otherwise an approver (HoD/HoS/etc.) opening someone else's Travel
	# request sees their own (usually non-existent) SCL eligibility instead of
	# the applicant's, even though the applicant correctly filled it in.
	scl_target_user = (related_data.get("webmail_id_travel") if doc_name else None) or current_user
	scl_html = _build_scl_balance_html(scl_target_user)
	for f in fields:
		if f["fieldname"] == "travel_leave_balance_html":
			f["options"] = scl_html
			break

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"client_scripts": client_scripts,
		"child_table_meta": child_table_meta,
		"scl_balance": _get_raw_scl_balance(scl_target_user),
	}


@frappe.whitelist()
def get_user_details_travel(user_email):
	"""
	Fetches details for a specific user to populate travel form fields.
	Returns the user document with resolved department name and designation.
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))

	try:
		user_email = str(user_email).strip('"').strip("'")
		user_doc = frappe.get_doc("User", user_email)
		user_dict = user_doc.as_dict()

		# Resolve department_name ID to actual department name from Department_prornd
		dept_link = user_dict.get("department_name")
		if dept_link:
			try:
				dept_doc = frappe.get_doc("Department_prornd", dept_link)
				user_dict["department_name"] = dept_doc.dept_name
			except Exception:
				pass  # Keep original value if lookup fails

		# Resolve designation_name if needed
		designation_link = user_dict.get("designation_name")
		if designation_link:
			user_dict["designation_name"] = designation_link

		return user_dict
	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details for Travel"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def get_special_leave_balance_for_travel(employee=None):
	"""
	Thin proxy so the Travel form can call a single endpoint.
	Delegates to the canonical implementation in special_leave_balance.py.
	"""
	from rndopsapp.rndopsapp.doctype.special_leave_balance.special_leave_balance import (
		get_special_leave_balance,
	)
	return get_special_leave_balance(employee)


def _get_raw_scl_balance(employee):
	"""Return raw SCL balance dict for the employee (no throw on error)."""
	try:
		from rndopsapp.rndopsapp.doctype.special_leave_balance.special_leave_balance import (
			get_special_leave_balance,
		)
		return get_special_leave_balance(employee)
	except Exception:
		return {"is_eligible": False}


def _build_scl_balance_html(employee):
	"""Build the HTML string for the SCL balance card shown in the Travel form."""
	data = _get_raw_scl_balance(employee)

	if not data or not data.get("is_eligible"):
		return """
		<div style="border:1px solid #d1d8dd;padding:12px;border-radius:6px;background:#f9f9f9;">
			<strong>Special Casual Leave (SCL)</strong><br>
			<span style="color:#888;">Not eligible for SCL.</span>
		</div>"""

	available = data.get("available_balance", 0)
	total    = data.get("total_credited", 0)
	utilized = data.get("utilized_balance", 0)
	year     = data.get("year", "")
	color    = "#1a7f37" if available > 0 else "#cf1322"
	icon     = "✅" if available > 0 else "⚠️"
	exhausted_msg = ""
	if available == 0:
		exhausted_msg = f"""
		<div style="margin-top:8px;padding:6px 10px;background:#fff1f0;
		            border-radius:4px;color:#cf1322;font-size:12px;">
			You have exhausted your SCL quota for {year}.
		</div>"""

	return f"""
	<div style="border:1px solid #d1d8dd;padding:12px;border-radius:6px;background:#fff;">
		<strong style="font-size:14px;">Special Casual Leave (SCL) — {year}</strong>
		<table style="margin-top:8px;width:100%;border-collapse:collapse;font-size:13px;">
			<tr>
				<td style="padding:2px 8px 2px 0;color:#555;">Total Credited</td>
				<td style="padding:2px 0;font-weight:600;">{total} days</td>
			</tr>
			<tr>
				<td style="padding:2px 8px 2px 0;color:#555;">Utilized</td>
				<td style="padding:2px 0;font-weight:600;">{utilized} days</td>
			</tr>
			<tr>
				<td style="padding:2px 8px 2px 0;color:#555;">Available</td>
				<td style="padding:2px 0;font-weight:700;color:{color};">{available} days {icon}</td>
			</tr>
		</table>
		{exhausted_msg}
	</div>"""


@frappe.whitelist()
def save_travel(doc_data):
	"""Saves or updates the Travel data from the React form.
	Handles file uploads for Attach fields.
	"""
	from frappe.utils.file_manager import save_file
	
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Travel:", data)  # Debug log

		doc_name = data.get("name")
		is_new = False
		
		# 1. Initialize Document
		if doc_name and frappe.db.exists("Travel", doc_name):
			doc = frappe.get_doc("Travel", doc_name)
			if doc.workflow_state != "Draft":
				frappe.throw(_("Cannot edit a document that is already under review or approved."))
			# Fix documents incorrectly submitted via the old doc.submit() path.
			if doc.docstatus == 1:
				frappe.db.set_value("Travel", doc_name, "docstatus", 0)
				doc.docstatus = 0
		else:
			doc = frappe.new_doc("Travel")
			is_new = True

		meta = frappe.get_meta("Travel")
		
		# 2. First Pass: Set standard fields (non-files) to ensure we can insert if new
		file_fields = []
		
		for fieldname, value in data.items():
			if fieldname in ["name", "doctype", "docstatus"]:
				continue

			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)
			
			if df.fieldtype in ["Attach", "Attach Image"]:
				file_fields.append((fieldname, value))
			elif df.fieldtype == "Table":
				# We typically process tables after insert too if they contain files
				file_fields.append((fieldname, value))
			else:
				if value not in [None, ""]:
					doc.set(fieldname, value)

		# 3. Create/Save Initial Document to get Name (if new)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_version = True
		if is_new:
			doc.insert(ignore_mandatory=True)
			print(f"Created new Travel doc: {doc.name}")
		else:
			doc.save(ignore_permissions=True)
			print(f"Updated existing Travel doc: {doc.name}")

		# 4. Second Pass: Process Files and Tables (Now we have doc.name)
		for fieldname, value in file_fields:
			df = meta.get_field(fieldname)
			
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, []) # Clear existing
				child_meta = frappe.get_meta(df.options)
				
				for child_row in value:
					row_dict = child_row.copy()
					
					# Handle files in child row
					for cf in child_meta.fields:
						if cf.fieldtype in ["Attach", "Attach Image"] and row_dict.get(cf.fieldname):
							f_val = row_dict[cf.fieldname]
							
							if isinstance(f_val, dict) and f_val.get("file_data"):
								try:
									saved_file = save_file(
										f_val.get("file_name", "attachment"),
										f_val["file_data"],
										"Travel",
										doc.name, # Attach to parent
										decode=True,
										is_private=1,
										df=cf.fieldname
									)
									row_dict[cf.fieldname] = saved_file.file_url
									print(f"Child table file saved: {saved_file.file_url}")
								except Exception as e:
									frappe.log_error(f"Child File Error: {e}")
									
					doc.append(fieldname, row_dict)
					
			elif df.fieldtype in ["Attach", "Attach Image"]:
				if isinstance(value, dict) and value.get("file_data"):
					try:
						print(f"Uploading file for {fieldname}...")
						saved_file = save_file(
							value.get("file_name", "attachment"),
							value["file_data"],
							"Travel",
							doc.name,
							decode=True,
							is_private=1,
							df=fieldname
						)
						# Explicitly update the field in DB immediately? No, doc.save() will do it.
						doc.set(fieldname, saved_file.file_url)
						print(f"Set {fieldname} to {saved_file.file_url}")
					except Exception as e:
						frappe.log_error(f"File Upload Error for {fieldname}: {str(e)}")
						print(f"Error uploading {fieldname}: {e}")
				
				elif isinstance(value, str):
					# Keep existing URL
					doc.set(fieldname, value)

		# 5. Final Save to persist file URLs and Table data
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully finalized Travel: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except frappe.ValidationError:
		frappe.db.rollback()
		raise
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Travel Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Travel: {str(e)}")


@frappe.whitelist()
def submit_travel(docname):
	"""
	Apply the 'Submit' workflow transition on a Travel document (Draft → Pending Approval).
	Does not call doc.submit() — the workflow keeps docstatus=0 throughout.
	"""
	from frappe.model.workflow import get_workflow, get_transitions

	try:
		doc = frappe.get_doc("Travel", docname)

		if doc.workflow_state != "Draft":
			return {
				"status": "info",
				"message": f"Travel '{docname}' is already submitted (state: {doc.workflow_state}).",
				"docname": docname,
				"workflow_state": doc.workflow_state,
			}

		# Fix documents incorrectly left with docstatus=1 by the old doc.submit() path.
		# All workflow states have doc_status=0 so the document must stay as draft.
		# Must update the DB first and reload so check_docstatus_transition sees 0→0.
		if doc.docstatus == 1:
			frappe.db.sql("UPDATE `tabTravel` SET docstatus=0 WHERE name=%s", docname)
			doc = frappe.get_doc("Travel", docname)

		workflow = get_workflow("Travel")
		transitions = get_transitions(doc, workflow)

		# Other-PI flow: the travel is charged to a project owned by a different
		# PI, so route it to that PI (Pending Other PI) instead of the normal chain.
		is_other_pi = (doc.get("travel_other_pi") or "").strip() == "Other"
		if is_other_pi and not doc.get("travel_other_pi_id"):
			frappe.throw(_("Please select the Other PI before submitting."))

		if is_other_pi:
			transition = next(
				(t for t in transitions
				 if t["action"] == "Submit" and t["next_state"] == "Pending Other PI"),
				None,
			)
		else:
			transition = next(
				(t for t in transitions
				 if t["action"] == "Submit" and t["next_state"] != "Pending Other PI"),
				None,
			)

		if not transition:
			frappe.throw(_("Submit action is not available for your role on this document."))

		next_state = next(s for s in workflow.states if s.state == transition["next_state"])

		doc.set(workflow.workflow_state_field, next_state.state)
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)
		doc.add_comment("Workflow", _(next_state.state))

		frappe.db.commit()
		return {
			"status": "success",
			"message": f"Travel '{docname}' submitted successfully.",
			"docname": docname,
			"workflow_state": doc.workflow_state,
		}

	except frappe.ValidationError:
		frappe.db.rollback()
		raise
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Travel Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_travel_commit_details(docname):
	"""
	Returns commit-related fields for the Travel pending task page UI.
	Called by the frontend when rendering the Staff's commit form on the Pending Task page.
	Frontend should call submit_commit_data + perform_travel_action('Forward') on commit.
	"""
	if not frappe.db.exists("Travel", docname):
		frappe.throw(_("Travel document not found."))

	doc = frappe.get_doc("Travel", docname)

	# Resolve project number from project registration
	project_number = None
	if doc.travel_project_title:
		project_number = frappe.db.get_value(
			"Project Registration", doc.travel_project_title, "project_no"
		)

	# account_head is now a Link to Budget Head — use directly
	budget_head = doc.account_head or None

	# Resolve moduleId from Module Registry for "Travel"
	module_id = frappe.db.get_value(
		"Module Registry Item",
		{"doctype_name": "Travel", "parent": "pending-task"},
		"mod_vis"
	) or 7

	return {
		"docname": docname,
		"workflow_state": doc.workflow_state,
		"applicant_name": doc.applicant_name_travel,
		"webmail_id": doc.webmail_id_travel,
		"project_name": doc.travel_project_title,
		"project_number": project_number,
		"total_estimate": doc.total_estimate,
		"budget_head": budget_head,
		"account_head": doc.account_head,
		"do_you_need_advance": doc.do_you_need_advance,
		"from_date": str(doc.from_date) if doc.from_date else None,
		"to_date": str(doc.to_date) if doc.to_date else None,
		"nature_of_travel": doc.nature_of_travel,
		"purpose_of_visit": doc.purpose_of_visit,
		"module_id": module_id,
	}


@frappe.whitelist()
def get_travel_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	from frappe.model.workflow import is_transition_condition_satisfied

	doc = frappe.get_doc("Travel", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	# workflow_name = frappe.db.get_value(
	# 	"Workflow",
	# 	{"document_type": "Travel", "is_active": 1},
	# 	"name"
	# )
	workflow_name = "Travel_Workflow"

	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		# Check roles on the transition
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		# User can perform action if they have allowed role
		if not (any(role in user_roles for role in transition_roles) or "System Manager" in user_roles):
			continue

		# e.g. the Director-approval branch is gated on doc.nature_of_travel ==
		# "International" (see docs/travel-director-approval-implementation.md)
		if not is_transition_condition_satisfied(transition, doc):
			continue

		allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def get_travel_pi_projects(pi=None):
	"""Projects owned by the (session) PI — used by the Other-PI approval step."""
	from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import get_pi_projects
	return get_pi_projects(pi)


@frappe.whitelist()
def get_travel_project_account_heads(project_name):
	"""Account heads for a given project — used by the Other-PI approval step."""
	from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import get_project_account_heads
	return get_project_account_heads(project_name)


@frappe.whitelist()
def perform_travel_action(docname, action, extra_data=None):
	"""
	Executes the selected workflow action and updates the document state.
	On 'Approved' state, publishes staged commit data to Kafka (two-phase commit pattern).

	extra_data (optional JSON/dict): when the Other PI acts from the
	'Pending Other PI' state they choose which of their own projects to charge
	and the account head — passed here and persisted onto the document.
	"""
	from frappe.model.workflow import is_transition_condition_satisfied

	try:
		doc = frappe.get_doc("Travel", docname)
		current_state = doc.workflow_state or "Draft"

		# Only the specifically-assigned Other PI (or a System Manager) may act on a
		# travel parked in 'Pending Other PI' — the 'Permanent Employee' role on the
		# transition is not enough on its own.
		if current_state == "Pending Other PI":
			is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
			assigned_pi = (doc.get("travel_other_pi_id") or "").lower()
			if not is_system_manager and assigned_pi != (frappe.session.user or "").lower():
				frappe.throw(_("You are not authorised to act on this travel application."))

		# Fetch the workflow for this doctype
		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Travel", "is_active": 1},
			"name"
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for Travel."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		# Get current user roles
		user_roles = frappe.get_roles(frappe.session.user)

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				# Check if user has permission for this specific transition
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]

				if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
					continue

				# e.g. Director approval only applies when doc.nature_of_travel ==
				# "International", and the final Approve from "Pending Director
				# Approval" requires doc.director_signed_pdf to be set (see
				# docs/travel-director-approval-implementation.md). A transition
				# whose condition fails is treated as not found, same as a role
				# mismatch — this is what actually prevents the action, not just
				# the frontend hiding the button.
				if not is_transition_condition_satisfied(t, doc):
					continue

				next_state = t.next_state
				transition = t
				break

		if not next_state:
			frappe.throw(_(f"No valid transition found for action '{action}' from state '{current_state}'."))

		# Other-PI approval: the PI charges the travel to one of THEIR OWN projects
		# and picks that project's account head. Validate ownership + head, then persist.
		if current_state == "Pending Other PI" and action in ("Forward", "Approve"):
			from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import (
				get_pi_projects,
				get_project_account_heads,
			)
			if isinstance(extra_data, str):
				extra_data = json.loads(extra_data or "{}")
			extra_data = extra_data or {}

			project_name = (extra_data.get("project_name") or "").strip()
			account_head = (extra_data.get("account_head") or "").strip()
			if not project_name or not account_head:
				frappe.throw(_("Please select a project and account head before approving."))

			# project must belong to the acting PI
			owns = next((p for p in get_pi_projects() if p.get("value") == project_name), None)
			if not owns:
				frappe.throw(_("Selected project does not belong to you."))

			# head must be one of that project's account heads
			valid_heads = {h["value"].lower() for h in get_project_account_heads(project_name)}
			if account_head.lower() not in valid_heads:
				frappe.throw(_("Selected account head is not valid for this project."))

			# resolve the head label to a Budget Head master record if one exists,
			# otherwise fall back to the free-text account head note.
			if frappe.db.exists("Budget Head", account_head):
				bh_name = account_head
			else:
				bh_name = frappe.db.get_value("Budget Head", {"budget_head": account_head}, "name")
			if bh_name:
				doc.account_head = bh_name
			else:
				doc.account_head = frappe.db.get_value("Budget Head", {"budget_head": "Other"}, "name") or None

			doc.travel_project_title = project_name
			doc.travel_project_number = owns.get("project_no") or owns.get("project_number")

		# Update workflow state
		doc.workflow_state = next_state

		# Check if next state requires submission (docstatus=1)
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		# --- Special Casual Leave deduction on Approval ---
		if next_state == "Approved" and doc.travel_special_casual_leave == "Required":
			_deduct_scl_on_approval(doc)

		# Kafka publish on Dean / Associate Dean approval
		if next_state == "Approved":
			frappe.logger().info(f"[Travel Kafka] Approval triggered for {docname}. Searching for staged commits.")
			try:
				from rndopsapp.rndopsapp.kafka.producer.reimbursement import publish_commit as kafka_publish_commit
				staging_docs = frappe.get_all("Kafka Commit Staging", filters={
					"reference_doctype": "Travel",
					"reference_name": docname,
					"status": ["in", ["PENDING_APPROVAL", "FAILED"]]
				})
				frappe.logger().info(f"[Travel Kafka] Found {len(staging_docs)} staged commit(s) for {docname}.")
				if not staging_docs:
					all_staging = frappe.get_all("Kafka Commit Staging", filters={
						"reference_doctype": "Travel",
						"reference_name": docname,
					}, fields=["name", "status", "creation"])
					frappe.log_error(
						f"[Travel Kafka] No PENDING_APPROVAL/FAILED staging records found for {docname}. "
						f"All staging records for this doc: {all_staging}. "
						f"Ensure submit_commit_data was called before the staff Forward action.",
						"Travel Kafka - No Staging Record"
					)
				for st in staging_docs:
					staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
					try:
						payload = json.loads(staging_doc.payload)
						frappe.logger().info(
							f"[Travel Kafka] Publishing staging record {staging_doc.name} for {docname}. "
							f"Payload keys: {list(payload.keys())}, commit_amount={payload.get('commit_amount')}, "
							f"budget_head={payload.get('budget_head')}, project_name={payload.get('project_name')}"
						)
						success = kafka_publish_commit(
							doc=doc,
							commit_amount=payload.get("commit_amount"),
							budget_head=payload.get("budget_head"),
							project_name=payload.get("project_name"),
							bmr=payload.get("bmr"),
							bill_amount=payload.get("bill_amount"),
							frap_app_id=payload.get("frap_app_id"),
							ref_details=payload.get("ref_details"),
							commit_particular=payload.get("commit_particular")
						)
						if success:
							staging_doc.db_set("status", "PUBLISHED")
						else:
							staging_doc.db_set("status", "FAILED")
							staging_doc.db_set("error_message", "kafka_publish_commit returned False")
							frappe.log_error(
								f"[Travel Kafka] kafka_publish_commit returned False for staging {staging_doc.name}",
								"Travel Kafka - Publish Failed"
							)
					except Exception as e:
						frappe.log_error(frappe.get_traceback(), f"[Travel Kafka] Exception processing staging {staging_doc.name} for {docname}")
						staging_doc.db_set("status", "FAILED")
						staging_doc.db_set("error_message", str(e))
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), f"[Travel Kafka] Outer exception for {docname}")

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_travel_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Travel Action Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# SCL helpers
# ---------------------------------------------------------------------------

def _calculate_scl_days(doc):
	"""Return the number of SCL days requested in this Travel doc."""
	if not doc.travel_leave_from_date or not doc.travel_leave_to_date:
		return 0
	delta = date_diff(doc.travel_leave_to_date, doc.travel_leave_from_date)
	return max(0, delta + 1)


def _deduct_scl_on_approval(doc):
	"""
	Called when a Travel application moves to Approved and SCL is Required.
	Deducts days from the employee's special_leave_balance for the year of
	travel_leave_from_date (or current year as fallback).
	Logs a warning in Frappe error log if balance is insufficient but does
	NOT block approval — raise frappe.throw() here if you prefer hard block.
	"""
	from rndopsapp.rndopsapp.doctype.special_leave_balance.special_leave_balance import deduct_leaves

	employee = doc.webmail_id_travel
	if not employee:
		frappe.log_error(
			f"[SCL] Cannot deduct: webmail_id_travel is empty on Travel {doc.name}",
			"SCL Deduction Warning"
		)
		return

	days = _calculate_scl_days(doc)
	if days <= 0:
		frappe.log_error(
			f"[SCL] Cannot deduct: leave dates missing or invalid on Travel {doc.name}",
			"SCL Deduction Warning"
		)
		return

	# Use the year of the leave start date
	year = getdate(doc.travel_leave_from_date).year

	success = deduct_leaves(
		employee=employee,
		year=year,
		days=days,
		reference_doctype="Travel",
		reference_name=doc.name,
	)

	if not success:
		# Warn in error log; optionally notify approver
		frappe.log_error(
			f"[SCL] Insufficient balance for {employee} in {year}. "
			f"Requested {days} days but balance is exhausted. Travel: {doc.name}",
			"SCL Insufficient Balance"
		)
		# --- Uncomment the line below to HARD BLOCK approval instead of warning ---
		# frappe.throw(_(f"Insufficient Special Casual Leave balance. Requested {days} days exceeds available balance."))
	else:
		frappe.logger().info(
			f"[SCL] Deducted {days} day(s) from {employee} ({year}) for Travel {doc.name}"
		)


@frappe.whitelist()
def cancel_travel_scl(docname):
	"""
	Reverses the SCL deduction when a Travel application is cancelled.
	Call this from the frontend cancel flow after cancelling the doc.
	"""
	from rndopsapp.rndopsapp.doctype.special_leave_balance.special_leave_balance import reverse_leaves

	if not frappe.db.exists("Travel", docname):
		return {"status": "error", "message": "Travel document not found."}

	doc = frappe.get_doc("Travel", docname)

	if doc.travel_special_casual_leave != "Required":
		return {"status": "skipped", "message": "SCL was not required for this travel."}

	employee = doc.webmail_id_travel
	days = _calculate_scl_days(doc)

	if not employee or days <= 0:
		return {"status": "skipped", "message": "No valid employee/dates to reverse."}

	year = getdate(doc.travel_leave_from_date).year

	reverse_leaves(
		employee=employee,
		year=year,
		days=days,
		reference_doctype="Travel",
		reference_name=docname,
	)

	return {
		"status": "success",
		"message": f"Reversed {days} SCL day(s) for {employee} ({year}).",
	}


# ---------------------------------------------------------------------------
# Director Approval (International travel) — see
# docs/travel-director-approval-implementation.md for the full design.
#
# This is a real Workflow branch (state "Pending Director Approval", added by
# rndopsapp.patchs.add_travel_director_approval_workflow), not a flag on the
# doctype: the Dean's "Send for Director Approval" and "Approve" actions are
# ordinary transitions in Travel_Workflow, gated by `condition` expressions
# (see is_transition_condition_satisfied usage in get_travel_workflow_actions /
# perform_travel_action above). The only Travel-specific field this flow needs
# is director_signed_pdf (Attach, hidden from the applicant's form).
# ---------------------------------------------------------------------------

DIRECTOR_UPLOAD_ROLES = ["staff, RnD", "RnD Staff", "R&D Staff", "System Manager"]


@frappe.whitelist()
def attach_director_pdf_travel(docname, file_url):
	"""Called by staff, RnD after the Director signs the printed review copy."""
	if not frappe.db.exists("Travel", docname):
		frappe.throw(_("Travel document not found."))

	user_roles = frappe.get_roles(frappe.session.user)
	if not any(role in user_roles for role in DIRECTOR_UPLOAD_ROLES):
		frappe.throw(_("You are not permitted to perform this action."), frappe.PermissionError)

	if not file_url:
		frappe.throw(_("No file was uploaded."))

	doc = frappe.get_doc("Travel", docname)

	if doc.workflow_state != "Pending Director Approval":
		frappe.throw(_("This application is not currently awaiting a Director-signed copy."))

	frappe.db.set_value("Travel", docname, "director_signed_pdf", file_url)
	frappe.db.commit()

	return {"status": "success", "director_signed_pdf": file_url}


@frappe.whitelist()
def get_pending_director_uploads_travel():
	"""Return Travel documents awaiting a Director-signed copy, for the staff,
	RnD upload screen (DirectorPdfUpload.tsx)."""
	docs = frappe.get_all(
		"Travel",
		filters={"workflow_state": "Pending Director Approval"},
		fields=[
			"name", "workflow_state", "modified",
			"applicant_name_travel", "travel_project_number",
			"department_travel", "director_signed_pdf",
		],
		order_by="modified desc",
	)
	return {"status": "success", "data": docs}