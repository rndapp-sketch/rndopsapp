import frappe
from frappe.model.document import Document
import json
from frappe import _
from frappe.utils.file_manager import save_file


class Reimbursement(Document):
	pass


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
		link_options["reimbursement_for_id"] = users
		# also for applicant_webmail (same source)
		link_options["applicant_webmail"] = users
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
		link_options["reimbursement_for_id"] = users
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
def perform_reimbursement_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Reimbursement", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Reimbursement"}, "name")
		
		if not workflow_name:
			frappe.throw("Workflow not found for Reimbursement.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				transition = t
				break
		
		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

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
		
		next_state = None
		transition = None
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				transition = t
				break
		
		if not next_state:
			# If "Submit" action isn't found, maybe it's "Approve" or something else?
			# For now, let's try to find ANY transition from Draft if action is generic
			# Or just throw error
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
