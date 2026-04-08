# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class LoanRequest(Document):
	pass


@frappe.whitelist()
def get_loan_request_fields(doc_name=None):
	"""
	Returns field metadata, prefill data, link options, and child table meta
	for the Loan Request doctype. Same pattern as get_ta_da_settlement_fields.

	Args:
		doc_name: existing Loan Request name to prefill for editing (optional)
	"""
	doctype_name = "Loan Request"
	meta = frappe.get_meta(doctype_name)

	fields = []
	child_table_fields = {}

	for f in meta.get("fields"):
		fields.append({
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
			"depends_on": f.depends_on,
		})

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
						"in_list_view": cf.in_list_view,
					})
				child_table_fields[f.fieldname] = child_fields
			except Exception:
				pass

	# Prefill from existing doc
	prefill_data = {}
	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		if frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			prefill_data = doc.as_dict()

	# Link options
	link_options = {}

	# Budget Head options for child table rows
	try:
		budget_heads = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label", "id"],
			limit_page_length=100,
		)
		link_options["budget_head"] = budget_heads
	except Exception:
		link_options["budget_head"] = []

	# Project Registration options
	try:
		projects = frappe.get_all(
			"Project Registration",
			fields=["name as value", "project_title as label", "project_no"],
			limit_page_length=500,
		)
		link_options["project_name"] = projects
	except Exception:
		link_options["project_name"] = []

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"child_table_fields": child_table_fields,
	}


@frappe.whitelist()
def save_loan_request(doc_data):
	"""
	Saves or creates a Loan Request from the frontend form.

	Args:
		doc_data: JSON string or dict with form field values
	"""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Loan Request", doc_name)
			if doc.docstatus != 0:
				return {"status": "info", "message": "Cannot edit a submitted or cancelled document."}
		else:
			doc = frappe.new_doc("Loan Request")

		# Scalar fields
		scalar_fields = [
			"self_other",
			"loan_for_webmail_id",
			"loan_for_name",
			"loan_for_department",
			"loan_for_designation",
			"applicant_webmail",
			"applicant_department",
			"applicant_designation",
			"project_name",
			"project_number",
			"loan_account_type",
			"loan_amount",
			"agreement_no_1",
			"agreement_no_2",
		]
		for field in scalar_fields:
			if field in data and data[field] is not None:
				doc.set(field, data[field])

		# witness_attachment — Attach field (may be a URL string or a base64 file dict)
		_pending_witness_file = None
		witness_value = data.get("witness_attachment")
		if witness_value:
			if isinstance(witness_value, dict) and witness_value.get("file_data"):
				# Base64 file sent from frontend — upload to MinIO after insert
				_pending_witness_file = witness_value
			elif isinstance(witness_value, str):
				# Already a URL (re-save or existing doc)
				doc.set("witness_attachment", witness_value)

		# Child table — fund breakup rows
		fund_breakup = data.get("account_head_fund_breakup")
		if isinstance(fund_breakup, list):
			doc.set("account_head_fund_breakup", [])
			for row in fund_breakup:
				if row.get("budget_head") or row.get("account_head_amount"):
					doc.append("account_head_fund_breakup", {
						"budget_head": row.get("budget_head"),
						"account_head_amount": row.get("account_head_amount", 0),
					})

		# Recalculate total from rows (safety — mirrors JS logic)
		rows = doc.get("account_head_fund_breakup") or []
		doc.loan_amount = sum(flt(r.account_head_amount) for r in rows)

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		# Upload witness attachment to MinIO after we have a docname
		witness_url = None
		if _pending_witness_file:
			import base64
			from rndopsapp.minio import get_rnd_file_service
			try:
				file_name = _pending_witness_file.get("file_name", "attachment")
				file_data_str = _pending_witness_file.get("file_data", "")
				# Strip base64 data URI prefix if present (data:...;base64,)
				if "," in file_data_str:
					file_data_str = file_data_str.split(",", 1)[1]
				content = base64.b64decode(file_data_str)

				file_service = get_rnd_file_service()
				file_hash = file_service._hash(content)
				path = file_service._path(
					filename=file_name,
					file_hash=file_hash,
					private=True,
					doctype="Loan_Request",
					docname=doc.name,
					folder="attachments",
					use_hash=False,
				)
				mime = file_service._mime(file_name)
				file_service.storage.upload(path, content, mime)
				witness_url = f"/rnd-files/{path}"
				frappe.db.set_value("Loan Request", doc.name, "witness_attachment", witness_url)
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), "Loan Request Witness Attachment Upload Error")

		frappe.db.commit()
		return {
			"status": "success",
			"docname": doc.name,
			"loan_amount": doc.loan_amount,
			"witness_attachment": witness_url or doc.get("witness_attachment"),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Loan Request Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_loan_request(docname):
	"""
	Submits a Loan Request from Draft state via the workflow Submit action.
	"""
	try:
		doc = frappe.get_doc("Loan Request", docname)
		current_state = doc.workflow_state or "Draft"

		if current_state != "Draft":
			return {
				"status": "info",
				"message": f"Loan Request '{docname}' is already in state '{current_state}'.",
				"docname": docname,
				"workflow_state": current_state,
			}

		return perform_loan_request_action(docname, "Submit")

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Loan Request Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_loan_request_workflow_actions(docname):
	"""
	Returns available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Loan Request", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": "Loan Request", "is_active": 1}, "name"
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
def perform_loan_request_action(docname, action, bmr=None, bmr_date=None):
	"""
	Executes the selected workflow action and updates the document state.
	bmr and bmr_date are accepted when action == "Deposit Loan" (staff at Pending @ Staff (Deposit Loan)).
	They are saved to the document and included in the Kafka payload.
	"""
	try:
		doc = frappe.get_doc("Loan Request", docname)
		current_state = doc.workflow_state or "Draft"

		# Save BMR fields when staff submits the Deposit Loan action
		if action == "Deposit Loan" and current_state == "Pending @ Staff (Deposit Loan)":
			if bmr is not None:
				doc.db_set("bmr", bmr, update_modified=False)
			if bmr_date is not None:
				doc.db_set("bmr_date", bmr_date, update_modified=False)
			# Reload to get updated values for Kafka payload
			doc = frappe.get_doc("Loan Request", docname)

		workflow_name = frappe.db.get_value(
			"Workflow", {"document_type": "Loan Request", "is_active": 1}, "name"
		)
		if not workflow_name:
			frappe.throw(_("No active workflow found for Loan Request."))

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

		doc.workflow_state = next_state
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.flags.ignore_permissions = True
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.flags.ignore_permissions = True
			doc.cancel()
		else:
			doc.db_set("workflow_state", next_state, update_modified=True)

		# Publish to Kafka on Dean / Associate Dean approval
		if next_state == "Approved":
			frappe.logger().info(f"[Loan Request Kafka] Approval triggered for {docname}. Publishing event.")
			try:
				from rndopsapp.rndopsapp.kafka.producer.loan_request import publish_loan_request
				# Reload doc to ensure all fields (including child table) are fresh
				doc = frappe.get_doc("Loan Request", docname)
				success = publish_loan_request(doc)
				if success:
					frappe.logger().info(f"[Loan Request Kafka] Successfully published for {docname}.")
				else:
					frappe.log_error(
						f"[Loan Request Kafka] publish_loan_request returned False for {docname}.",
						"Loan Request Kafka - Publish Failed"
					)
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), f"[Loan Request Kafka] Exception for {docname}")

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_loan_request_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Loan Request Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def upload_witness_attachment(docname):
	"""
	Upload the witness attachment file for a Loan Request to MinIO.
	Saves the file at: rnd-files/Loan_Request/{docname}/attachments/{filename}

	Usage (multipart/form-data):
		frappe.call({
			method: 'rndopsapp.rndopsapp.doctype.loan_request.loan_request.upload_witness_attachment',
			args: { docname },
			file: fileObject,
		})
	"""
	from rndopsapp.minio import get_rnd_file_service

	if "file" in frappe.request.files:
		file_obj = frappe.request.files["file"]
		filename = file_obj.filename
		content = file_obj.stream.read()
	elif frappe.local.uploaded_file:
		content = frappe.local.uploaded_file
		filename = frappe.local.uploaded_filename
	else:
		return {"status": False, "message": "No file attached"}

	try:
		file_service = get_rnd_file_service()

		data = file_service._bytes(content)
		file_hash = file_service._hash(data)
		path = file_service._path(
			filename=filename,
			file_hash=file_hash,
			private=True,
			doctype="Loan_Request",
			docname=docname,
			folder="attachments",
			use_hash=False,
		)
		mime = file_service._mime(filename)

		file_service.storage.upload(path, data, mime)

		full_minio_path = f"/rnd-files/{path}"

		# Persist the URL on the document
		frappe.db.set_value("Loan Request", docname, "witness_attachment", full_minio_path)
		frappe.db.commit()

		return {"status": True, "message": "File uploaded", "data": {"file_url": full_minio_path}}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Loan Request Witness Attachment Upload Error")
		return {"status": False, "message": str(e)}
