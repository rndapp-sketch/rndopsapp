import frappe
from frappe.model.document import Document
import json
from frappe import _
from frappe.utils.file_manager import save_file


class Reimbursement(Document):
	pass


def _roles_list(allowed):
	"""Normalise a transition 'allowed' value into a list of role names."""
	if not allowed:
		return []
	if isinstance(allowed, (list, tuple)):
		return [str(r).strip() for r in allowed if str(r).strip()]
	return [part.strip() for part in str(allowed).split(",") if part.strip()]


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()  # Remove 'eval:' prefix
	
	return expression


# reimbursement.py


@frappe.whitelist()
def get_reimbursement_fields(doc_name=None):
	"""
	Return Reimbursement field metadata + prefill data based on a Project Registration ref (doc_name).
	- doc_name: Project Registration.name (preferred). If not provided, minimal defaults returned.
	"""
	# --- fields meta (safe) ---
	meta = frappe.get_meta("Reimbursement")
	fields = []
	for f in meta.get("fields"):
		fields.append(
			{
				"fieldname": f.fieldname,
				"label": f.label,
				"fieldtype": f.fieldtype,
				"options": getattr(f, "options", None),
				"mandatory": getattr(f, "reqd", False),
				"hidden": getattr(f, "hidden", False),
				"read_only": getattr(f, "read_only", False),
				"description": getattr(f, "description", "") or "",
				"default": getattr(f, "default", None),
				# Eval expressions for frontend conditional logic
				"depends_on": getattr(f, "depends_on", None),
				"mandatory_depends_on": getattr(f, "mandatory_depends_on", None),
				"read_only_depends_on": getattr(f, "read_only_depends_on", None),
				# Extract eval expression for easier frontend parsing
				"depends_on_eval": extract_eval_expression(getattr(f, "depends_on", None)),
				"mandatory_depends_on_eval": extract_eval_expression(getattr(f, "mandatory_depends_on", None)),
				"read_only_depends_on_eval": extract_eval_expression(getattr(f, "read_only_depends_on", None)),
			}
		)

		# If field is a Table, fetch its fields too
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.fields:
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": getattr(cf, "options", None),
						"mandatory": getattr(cf, "reqd", False),
						"hidden": getattr(cf, "hidden", False),
						"read_only": getattr(cf, "read_only", False),
						"in_list_view": getattr(cf, "in_list_view", False),
						"depends_on": getattr(cf, "depends_on", None),
						"depends_on_eval": extract_eval_expression(getattr(cf, "depends_on", None)),
					})
				# Append child fields to the parent field definition
				fields[-1]["child_fields"] = child_fields
			except Exception:
				pass

	# --- containers to return ---
	prefill_data = {}
	link_options = {}
	related_project_data = {}

	# quick defaults
	# prefill applicant_webmail as current session user (if a User record exists)
	try:
		current_user = frappe.session.user
		if current_user and current_user not in ["Administrator", "Guest"]:
			prefill_data["applicant_webmail"] = current_user
	except Exception:
		current_user = None

	# If no doc_name provided, return basic meta + some master list options
	if not doc_name:
		# populate some link options lightly
		_safe_populate_link_options(link_options)
		return {
			"fields": fields,
			"prefill_data": prefill_data,
			"link_options": link_options,
			"related_project_data": related_project_data,
		}

	# Clean input
	doc_name = str(doc_name).strip('"').strip("'").strip()

	# --- Fetch Project Registration ---
	try:
		project_doc = frappe.db.get_value(
			"Project Registration",
			doc_name,
			["name", "project_title", "project_type", "project_number"],
			as_dict=True,
		)
	except Exception:
		project_doc = None

	if not project_doc:
		frappe.throw(f"Project Registration '{doc_name}' not found.")

	related_project_data = project_doc
	# Prefill project link fields in Reimbursement doctype:
	# Your doctype has project_name (Link) and project_number (Select). We prefill both where possible.
	prefill_data["project_name"] = project_doc.name
	if project_doc.get("project_number"):
		prefill_data["project_number"] = project_doc.get("project_number")

	# --- Fetch Fund Sanction(s) linked to this project ---
	try:
		sanctions = frappe.get_all(
			"Fund Sanction",
			filters={"refnum_prj_num": project_doc.name},
			fields=["name as value", "sanctioned_letter_no as label", "project_proposal"],
		)
	except Exception:
		sanctions = []

	# If exactly one sanction, prefill a few fields
	if sanctions:
		if len(sanctions) == 1:
			try:
				sanction_doc = frappe.get_doc("Fund Sanction", sanctions[0]["value"])
				prefill_data.update(
					{
						# adjust keys if your Reimbursement field names differ
						"sanction_ref_no": sanction_doc.name,
						"project_proposal": getattr(sanction_doc, "project_proposal", None),
						# "sanctioned_amount": getattr(sanction_doc, "sanctioned_amount", None),
					}
				)
			except Exception:
				# ignore prefill failure
				pass

	# --- Fetch Fund Received entries linked to this project ---
	try:
		fund_received = frappe.get_all(
			"Fund Received",
			filters={"prjreg_refnum": project_doc.name},
			fields=["name as value", "received_date as label", "sanction_ref_no"],
			order_by="received_date desc",
			limit_page_length=200,
		)
	except Exception:
		fund_received = []

	# --- Populate link options ---
	link_options["project_name"] = [{"value": project_doc.name, "label": project_doc.project_title}]
	link_options["project_number"] = [
		{
			"value": project_doc.get("project_number") or "",
			"label": project_doc.get("project_number") or project_doc.project_title,
		}
	]
	link_options["sanction_ref_no"] = sanctions
	link_options["fund_received_ref"] = fund_received

	# Account Heads (Budget Head) - your doctype has account_head Link -> Budget Head
	try:
		accs = frappe.get_all(
			"Budget Head", fields=["name as value", "budget_head as label"], limit_page_length=200
		)
		# If Budget Head doesn't have budget_head, fallback to name
		if accs:
			link_options["account_head"] = [
				{"value": r["value"], "label": r.get("label") or r["value"]} for r in accs
			]
	except Exception:
		# try a generic fallback if Budget Head not present
		try:
			heads = frappe.get_all("Account", fields=["name as value"], limit_page_length=200)
			link_options["account_head"] = [{"value": h["value"], "label": h["value"]} for h in heads]
		except Exception:
			pass

	# Reimbursement -> amended_from options (existing Reimbursement docs)
	try:
		amended = frappe.get_all("Reimbursement", fields=["name as value"], limit_page_length=200)
		link_options["amended_from"] = amended
	except Exception:
		link_options["amended_from"] = []

	# Applicant / PI lists (User)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=200,
		)
		# applicant_webmail = any enabled user; reimbursement_for_id (Other PI)
		# is restricted to Permanent Employees only.
		link_options["applicant_webmail"] = users
		link_options["reimbursement_for_id"] = _get_permanent_employee_options()
	except Exception:
		pass

	# Bank details: no master table given in your schema — some installs might have 'Bank' master
	try:
		banks = frappe.get_all("Bank", fields=["name as value", "bank_name as label"], limit_page_length=200)
		link_options["bank_name"] = banks
	except Exception:
		# leave bank options empty; frontend can still accept typed bank_name
		pass

	# If applicant_webmail present in prefill_data, try fetch department/designation
	try:
		applicant = prefill_data.get("applicant_webmail") or current_user
		if applicant:
			user_doc = frappe.get_doc("User", applicant)
			# If the user Doc exposes department_name / designation_name as in your fetch_froms, include them
			prefill_data["applicant_department"] = getattr(user_doc, "department_name", None) or getattr(
				user_doc, "department", None
			)
			prefill_data["applicant_designation"] = getattr(user_doc, "designation_name", None) or getattr(
				user_doc, "designation", None
			)
	except Exception:
		pass

	# Bank account prefill: attempt to find User bank details in a custom "User Bank" or profile (best-effort)
	try:
		if applicant:
			# example: if you have a doctype "User Bank" linking User -> account details
			ub = frappe.get_all(
				"User Bank",
				filters={"user": applicant},
				fields=["bank_name as label", "account_number as account", "ifsc_code as ifsc"],
				limit_page_length=1,
			)
			if ub:
				prefill_data["bank_name"] = ub[0].get("label")
				prefill_data["bank_account_number"] = ub[0].get("account")
				prefill_data["ifsc_code"] = ub[0].get("ifsc")
	except Exception:
		pass

	# Always include fields metadata and gathered data
	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}


def _get_permanent_employee_options():
	"""
	Return link options (value/label) for all enabled Users holding the
	'Permanent Employee' role. Used for the 'Other PI' selector, since every
	PI is a Permanent Employee.
	"""
	try:
		rows = frappe.get_all(
			"Has Role",
			filters={"role": "Permanent Employee", "parenttype": "User"},
			fields=["parent"],
			limit_page_length=0,
		)
		emails = [r["parent"] for r in rows]
		if not emails:
			return []
		users = frappe.get_all(
			"User",
			filters={"name": ["in", emails], "enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=0,
			order_by="full_name asc",
		)
		# Two accounts can share the same full name (e.g. a personal login and a
		# role account), which makes the picker ambiguous and lets the applicant
		# select the wrong PI. Always show the email alongside the name.
		for u in users:
			name = (u.get("label") or "").strip()
			u["label"] = f"{name} ({u['value']})" if name else u["value"]
		return users
	except Exception:
		return []


def _safe_populate_link_options(link_options):
	"""
	Fill a minimal set of master lists useful to the Reimbursement form when no project provided.
	Kept separate to keep main function focused & readable.
	"""
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=200,
		)
		link_options["applicant_webmail"] = users
		link_options["reimbursement_for_id"] = _get_permanent_employee_options()
	except Exception:
		pass

	try:
		accs = frappe.get_all(
			"Budget Head", fields=["name as value", "budget_head as label"], limit_page_length=200
		)
		# If Budget Head doesn't have budget_head, fallback to name
		if accs:
			link_options["account_head"] = [
				{"value": r["value"], "label": r.get("label") or r["value"]} for r in accs
			]
	except Exception:
		pass

	try:
		projects = frappe.get_all(
			"Project Registration", fields=["name as value", "project_title as label"], limit_page_length=200
		)
		link_options["project_name"] = projects
	except Exception:
		pass


@frappe.whitelist()
def save_reimbursement_data(data):
	"""
	Save Reimbursement data (parent + child tables).
	Expects 'data' as a JSON string or dict.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if docname:
			doc = frappe.get_doc("Reimbursement", docname)
		else:
			doc = frappe.new_doc("Reimbursement")

		# Map simple fields
		simple_fields = [
			"project_number",
			"project_name",
			"account_head",
			"other_head",
			"comment",
			"bank_name",
			"account_holder_name",
			"bank_account_number",
			"ifsc_code",
			"applicant_webmail",
			"applicant_department",
			"applicant_designation",
			"reimbursement_for_id",
			"reimbursement_for_department",
			"reimbursement_for_designation",
			"self_other",
			"dec1",
			"dec2",
			"dec3",
			"dec4",
			"amended_from",
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				# Handle boolean checks coming as strings "0" or "1" or boolean
				if field.startswith("dec"):
					doc.set(field, 1 if val in [1, "1", True, "True"] else 0)
				elif field in ["applicant_department", "reimbursement_for_department"]:
					# If value looks like an ID (random string), try to fetch dept_id
					# User requested to store dept_id (e.g. "10", "1")
					if val:
						val = str(val).strip()
						dept_id = frappe.db.get_value("Department_prornd", val, "dept_id")
						doc.set(field, dept_id or val)
					else:
						doc.set(field, None)

				else:
					doc.set(field, val if val != "null" else None)

		# Handle child table: table_bosk
		items_data = data.get("table_bosk", [])
		if isinstance(items_data, str):
			items_data = json.loads(items_data)

		if items_data:
			doc.set("table_bosk", [])
			for item in items_data:
				# Handle file upload for 'uploads' field
				if item.get("uploads") and isinstance(item["uploads"], dict):
					file_data = item["uploads"]
					if file_data.get("file_name") and file_data.get("file_data"):
						try:
							saved_file = save_file(
								file_data["file_name"],
								file_data["file_data"],
								doc.doctype,
								doc.name,
								decode=True,
								is_private=0,
								df="uploads"
							)
							item["uploads"] = saved_file.file_url
						except Exception as e:
							frappe.log_error(f"Error saving file: {str(e)}", "Reimbursement File Upload")
							# Keep original value or set to None if failed? 
							# For now, let's assume if it fails we might just log it. 
							# Or maybe we should strip the dict so it doesn't error on save?
							item["uploads"] = None

				doc.append("table_bosk", item)

		# Save
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Reimbursement Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def edit_reimbursement(data):
	"""
	Edit Reimbursement data (parent + child tables) only if the document is in Draft state.
	Expects 'data' as a JSON string or dict with 'name' field required.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if not docname:
			frappe.throw(_("Document name is required for editing."))

		doc = frappe.get_doc("Reimbursement", docname)

		# Check if document is in Draft state
		if doc.docstatus != 0:
			frappe.throw(_("Cannot edit a submitted or cancelled document. Document must be in Draft state."))

		# Check workflow state if applicable
		workflow_state = getattr(doc, "workflow_state", None)
		if workflow_state and workflow_state.lower() != "draft":
			frappe.throw(_(f"Cannot edit document in '{workflow_state}' state. Document must be in Draft state."))

		# Map simple fields
		simple_fields = [
			"project_number",
			"project_name",
			"account_head",
			"other_head",
			"comment",
			"bank_name",
			"account_holder_name",
			"bank_account_number",
			"ifsc_code",
			"applicant_webmail",
			"applicant_department",
			"applicant_designation",
			"reimbursement_for_id",
			"reimbursement_for_department",
			"reimbursement_for_designation",
			"self_other",
			"dec1",
			"dec2",
			"dec3",
			"dec4",
			"amended_from",
		]

		for field in simple_fields:
			if field in data:
				val = data[field]
				# Handle boolean checks coming as strings "0" or "1" or boolean
				if field.startswith("dec"):
					doc.set(field, 1 if val in [1, "1", True, "True"] else 0)
				elif field in ["applicant_department", "reimbursement_for_department"]:
					# If value looks like an ID (random string), try to fetch dept_id
					if val:
						val = str(val).strip()
						dept_id = frappe.db.get_value("Department_prornd", val, "dept_id")
						doc.set(field, dept_id or val)
					else:
						doc.set(field, None)
				else:
					doc.set(field, val if val != "null" else None)

		# Handle child table: table_bosk
		items_data = data.get("table_bosk", [])
		if isinstance(items_data, str):
			items_data = json.loads(items_data)

		if items_data:
			doc.set("table_bosk", [])
			for item in items_data:
				# Handle file upload for 'uploads' field
				if item.get("uploads") and isinstance(item["uploads"], dict):
					file_data = item["uploads"]
					if file_data.get("file_name") and file_data.get("file_data"):
						try:
							saved_file = save_file(
								file_data["file_name"],
								file_data["file_data"],
								doc.doctype,
								doc.name,
								decode=True,
								is_private=0,
								df="uploads"
							)
							item["uploads"] = saved_file.file_url
						except Exception as e:
							frappe.log_error(f"Error saving file: {str(e)}", "Reimbursement File Upload")
							item["uploads"] = None

				doc.append("table_bosk", item)

		# Save
		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Reimbursement updated successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Reimbursement Edit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_reimbursement_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Reimbursement", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = frappe.get_value("Workflow", {"document_type": "Reimbursement"}, "name")
	
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
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_reimbursement_action(docname, action, extra_data=None):
	"""
	Executes the selected workflow action and updates the document state.

	extra_data (optional JSON/dict): when the Other PI acts from the
	'Pending PI Approval' state they choose which of their projects to charge
	and the corresponding account head. These are persisted on the document
	before the transition is applied.
	"""
	try:
		doc = frappe.get_doc("Reimbursement", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Reimbursement"}, "name")

		if not workflow_name:
			frappe.throw("Workflow not found for Reimbursement.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		# Only the specifically-assigned PI (or a System Manager) may act on a
		# form parked in 'Pending PI Approval' — the 'Permanent Employee' role is
		# shared by all faculty, so restrict by the reimbursement_for_id field.
		if current_state == "Pending PI Approval":
			is_system_manager = "System Manager" in frappe.get_roles(frappe.session.user)
			assigned_pi = (doc.reimbursement_for_id or "").lower()
			if not is_system_manager and assigned_pi != frappe.session.user.lower():
				frappe.throw("You are not authorised to act on this reimbursement.")

		next_state = None
		transition = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				transition = t
				break

		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# --- Other PI: on Approve, the PI charges one of their own projects. ---
		if current_state == "Pending PI Approval" and action == "Approve":
			if isinstance(extra_data, str):
				extra_data = json.loads(extra_data or "{}")
			extra_data = extra_data or {}

			project_name = (extra_data.get("project_name") or "").strip()
			account_head = (extra_data.get("account_head") or "").strip()

			if not project_name or not account_head:
				frappe.throw("Please select a project and account head before approving.")

			# The project must belong to the acting PI.
			pi_owns = frappe.db.get_value(
				"Project Registration",
				project_name,
				["name", "project_no", "pi_webmail"],
				as_dict=True,
			)
			if not pi_owns or (pi_owns.get("pi_webmail") or "").lower() != frappe.session.user.lower():
				frappe.throw("Selected project does not belong to you.")

			# The account head must be one of the project's sanctioned heads.
			valid_heads = {h["value"].lower() for h in get_project_account_heads(project_name)}
			if account_head.lower() not in valid_heads:
				frappe.throw("Selected account head is not part of the chosen project.")

			doc.project_name = project_name
			doc.project_number = extra_data.get("project_number") or pi_owns.get("project_no")

			# Project budget heads are free-text labels (e.g. "Consumable") and may
			# not exist in the Budget Head master, while Reimbursement.account_head is
			# a Link -> Budget Head. Resolve to a master record where possible;
			# otherwise record the label in the free-text other_head field so the
			# save never fails Link validation.
			bh_name = None
			if frappe.db.exists("Budget Head", account_head):
				bh_name = account_head
			else:
				bh_name = frappe.db.get_value("Budget Head", {"budget_head": account_head}, "name")

			if bh_name:
				doc.account_head = bh_name
				if doc.meta.has_field("other_head"):
					doc.other_head = None
			else:
				doc.account_head = None
				if doc.meta.has_field("other_head"):
					doc.other_head = account_head

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if next state requires submission (docstatus=1)
		# We check the 'states' table in Workflow to see if doc_status should be 1
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		
		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_reimbursement_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Reimbursement Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_reimbursement(docname):
	"""
	Submit a Reimbursement document using Workflow transitions.
	"""
	try:
		doc = frappe.get_doc("Reimbursement", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		# User reported workflow might be inactive or just wants to find it by doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Reimbursement"}, "name")
		print("workflow_name:", workflow_name)
		if not workflow_name:
			# Fallback to standard submit if no workflow exists
			if doc.docstatus == 0:
				doc.submit()
				return {"status": "success", "message": "Submitted successfully (No Workflow)", "docname": docname}
			return {"status": "success", "message": "Already submitted", "docname": docname}

		workflow = frappe.get_doc("Workflow", workflow_name)

		# Find the transition for "Submit" action from current state
		# We assume the action name is "Submit" for the initial submission. 
		# If the user clicks "Submit" on the frontend, we map it to a workflow action.
		action = "Submit"

		# Candidate "Submit" transitions from the current state.
		candidates = [
			t for t in workflow.transitions
			if t.state == current_state and t.action == action
		]

		user_roles = frappe.get_roles(frappe.session.user)
		self_other = str(getattr(doc, "self_other", "") or "Self").strip().lower()

		next_state = None
		transition = None

		if self_other == "other":
			# Applying against another PI's project -> route to that PI first.
			if not doc.reimbursement_for_id:
				frappe.throw("Please select the PI (Other) before submitting.")
			for t in candidates:
				if t.next_state == "Pending PI Approval":
					next_state, transition = t.next_state, t
					break
		else:
			# Self: pick the transition allowed for the applicant's role,
			# never the Other-PI route.
			for t in candidates:
				if t.next_state == "Pending PI Approval":
					continue
				if any(r in user_roles for r in _roles_list(t.allowed)):
					next_state, transition = t.next_state, t
					break
			if not next_state:
				for t in candidates:
					if t.next_state != "Pending PI Approval":
						next_state, transition = t.next_state, t
						break

		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if the next state is a submitted state
		# We can check workflow_state docstatus map, or just check if docstatus should be 1
		# Usually workflow engine handles this if we use frappe.workflow.apply_workflow
		# But here we are doing it manually as per request pattern.
		
		# Let's try to use frappe.workflow.apply_workflow if possible, but the user asked for specific logic.
		# The previous pattern in project_registration was manual.
		
		# Check if next state requires submission
		state_doc = next(s for s in workflow.states if s.state == next_state)
		if state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Reimbursement submitted. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Reimbursement Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_pi_projects(pi=None):
	"""
	Return the list of Project Registration projects for which the given user
	(default: current session user) is the Principal Investigator (pi_webmail).
	Used by the 'Other PI' approval step so the PI can choose which of their
	own projects to charge the reimbursement against.
	"""
	if not pi:
		pi = frappe.session.user

	try:
		projects = frappe.get_all(
			"Project Registration",
			filters={"pi_webmail": pi},
			fields=["name", "project_title", "project_no", "project_number"],
			order_by="modified desc",
			limit_page_length=0,
		)
	except Exception:
		# Fallback if project_number column does not exist
		projects = frappe.get_all(
			"Project Registration",
			filters={"pi_webmail": pi},
			fields=["name", "project_title", "project_no"],
			order_by="modified desc",
			limit_page_length=0,
		)

	options = []
	for p in projects:
		options.append(
			{
				"value": p.get("name"),
				"label": p.get("project_title") or p.get("project_no") or p.get("name"),
				"project_no": p.get("project_no"),
				"project_number": p.get("project_number") or p.get("project_no"),
			}
		)
	return options


@frappe.whitelist()
def get_project_account_heads(project_name):
	"""
	Return the distinct account heads defined in a project's sanctioned budget
	breakup (Project Sanctioned Budget child table). The 'Other PI' can only
	select from these heads when approving a reimbursement against the project.
	"""
	project_name = str(project_name or "").strip().strip('"').strip("'")
	if not project_name:
		return []

	# A project's budget heads may live in either the sanctioned or the proposed
	# budget breakup (both use the 'Project Sanctioned Budget' child doctype), so
	# filter by parent only to capture heads from whichever is populated.
	try:
		rows = frappe.get_all(
			"Project Sanctioned Budget",
			filters={
				"parent": project_name,
				"parenttype": "Project Registration",
			},
			fields=["account_head", "is_total_row"],
			limit_page_length=0,
		)
	except Exception:
		rows = []

	seen = set()
	options = []
	for r in rows:
		head = (r.get("account_head") or "").strip()
		# Skip blank rows and the grand-total row
		if not head or r.get("is_total_row"):
			continue
		if head.lower() in seen:
			continue
		seen.add(head.lower())
		options.append({"value": head, "label": head})
	return options
