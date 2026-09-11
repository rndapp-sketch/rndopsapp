# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

DOCTYPE = "Miscellaneous Commit"


class MiscellaneousCommit(Document):
	pass


@frappe.whitelist()
def get_miscellaneous_commit_fields(doc_name=None):
	"""
	Returns field metadata, prefill data, and link options for the
	Miscellaneous Commit doctype. Same pattern as get_loan_request_fields.

	Args:
		doc_name: existing Miscellaneous Commit name to prefill for editing (optional)
	"""
	meta = frappe.get_meta(DOCTYPE)

	# Module dropdown is sourced live from the Module Registry (pending-task) child
	# table, rather than the doctype's own static Select options, so newly
	# registered modules show up here without a doctype change.
	module_names = []
	try:
		mr_parent = frappe.get_all(
			"Module Registry", filters={"page_name": "pending-task"}, fields=["name"], limit_page_length=1
		)
		if mr_parent:
			mr_doc = frappe.get_doc("Module Registry", mr_parent[0].name)
			module_names = sorted({
				row.doctype_name for row in (mr_doc.get("doctype_name") or [])
				if row.doctype_name
			})
	except Exception:
		module_names = []

	fields = []
	for f in meta.get("fields"):
		field_options = f.options
		if f.fieldname == "module":
			field_options = "\n" + "\n".join(module_names)
		fields.append({
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": field_options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			"fetch_from": f.fetch_from,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
		})

	# Prefill from existing doc
	prefill_data = {}
	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		if frappe.db.exists(DOCTYPE, doc_name):
			doc = frappe.get_doc(DOCTYPE, doc_name)
			prefill_data = doc.as_dict()
	else:
		# New doc — prefill applicant details from the logged-in user
		user = frappe.session.user
		user_doc = frappe.db.get_value(
			"User", user, ["department_name", "designation_name"], as_dict=True
		) or {}
		prefill_data = {
			"applicant_webmail": user,
			"applicant_department": user_doc.get("department_name"),
			"applicant_designation": user_doc.get("designation_name"),
		}

	# Link options
	link_options = {}
	try:
		link_options["project_number"] = frappe.get_all(
			"Project Registration",
			fields=["name as value", "project_no as label", "project_title"],
			limit_page_length=0,
		)
	except Exception:
		link_options["project_number"] = []

	try:
		link_options["budget_head"] = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label"],
			limit_page_length=0,
		)
	except Exception:
		link_options["budget_head"] = []

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}


@frappe.whitelist()
def save_miscellaneous_commit(doc_data):
	"""
	Saves or creates a Miscellaneous Commit from the frontend form.

	Args:
		doc_data: JSON string or dict with form field values
	"""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc(DOCTYPE, doc_name)
			if doc.docstatus != 0:
				return {"status": "info", "message": "Cannot edit a submitted or cancelled document."}
		else:
			doc = frappe.new_doc(DOCTYPE)
			doc.applicant_webmail = frappe.session.user

		scalar_fields = [
			"project_number",
			"budget_head",
			"commit_decommit",
			"module",
			"commit_amount",
			"commit_particular",
			"linked_application",
			"applicant_webmail",
			"applicant_department",
			"applicant_designation",
		]
		for field in scalar_fields:
			if field in data and data[field] is not None:
				doc.set(field, data[field])

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Miscellaneous Commit Save Error")
		return {"status": "error", "message": str(frappe.get_traceback(with_context=False))[:140]}


@frappe.whitelist()
def submit_miscellaneous_commit(docname):
	"""
	Submits a Miscellaneous Commit from Draft state via the workflow Submit action.
	The transition actually taken (and therefore the next state) depends on the
	current user's role — see perform_miscellaneous_commit_action / the workflow's
	two "Submit" transitions from Draft (one for "staff, RnD", one for "Permanent Employee").
	"""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.get("workflow_state") or "Draft"

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Miscellaneous Commit '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		return perform_miscellaneous_commit_action(docname, "Submit")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Miscellaneous Commit Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_miscellaneous_commit_workflow_actions(docname):
	"""
	Returns available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.get("workflow_state") or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name"
	)
	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_miscellaneous_commit_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	When multiple transitions share the same (state, action) pair — e.g. Draft/Submit —
	the first transition whose "allowed" role matches the current user's roles wins,
	which is how "staff, RnD" and "Permanent Employee" get routed differently on submit.
	"""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.get("workflow_state") or "Draft"

		workflow_name = frappe.db.get_value(
			"Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name"
		)
		if not workflow_name:
			frappe.throw(_("No active workflow found for Miscellaneous Commit."))

		workflow = frappe.get_doc("Workflow", workflow_name)
		user_roles = frappe.get_roles(frappe.session.user)

		next_state = None
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]
				if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
					next_state = t.next_state
					break

		if not next_state:
			frappe.throw(_(f"No valid transition found for action '{action}' from state '{current_state}'."))

		# Stage this commit for Kafka the moment it's submitted (same "Kafka Commit
		# Staging" mechanism every other application uses via its "Make a Commitment"
		# widget). Publishing itself is NOT done here — it happens automatically via
		# the global doc_events["*"]["on_update"] hook (commitPayment.check_workflow_and_publish,
		# see hooks.py) as soon as this document's workflow_state reaches "Approved",
		# i.e. when Dean approves.
		if action == "Submit":
			from frappe.utils import flt
			from rndopsapp.rndopsapp.commitPayment import submit_commit_data
			from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import get_module_id
			project_no = frappe.db.get_value("Project Registration", doc.project_number, "project_no") or doc.project_number
			# Commit -> positive amount, De-Commit -> negative amount
			signed_amount = flt(doc.commit_amount)
			signed_amount = -abs(signed_amount) if doc.commit_decommit == "De-Commit" else abs(signed_amount)
			resolved_module_id = get_module_id(doc.module) if doc.module else None
			submit_commit_data(
				doctype=DOCTYPE,
				frapAppId=doc.name,
				name=doc.name,
				project_name=project_no,
				commit_amount=signed_amount,
				budget_head=doc.budget_head,
				commitParticular=doc.commit_particular,
				moduleId=resolved_module_id,
				trigger_state="Approved",
			)

		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		# Set workflow_state on the in-memory doc BEFORE submit/cancel/save so that
		# doc_events["*"]["on_update"] (commitPayment.check_workflow_and_publish) sees
		# the NEW state when it fires — frappe.db.set_value/db_set are raw DB writes
		# that bypass on_update entirely, which would silently skip Kafka publishing.
		doc.workflow_state = next_state

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_workflow = True
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_workflow = True
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_miscellaneous_commit_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Miscellaneous Commit Action Error")
		return {"status": "error", "message": str(e)}