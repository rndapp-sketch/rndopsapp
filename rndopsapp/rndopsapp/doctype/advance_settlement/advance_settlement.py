# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document


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


class AdvanceSettlement(Document):
	def validate(self):
		self.resolve_project_code()
		self.calculate_total()

	def resolve_project_code(self):
		"""Resolve project_code to the actual project_no from Project Registration."""
		project_ref = self.project_name or self.project_code
		if not project_ref:
			return

		if frappe.db.exists("Project Registration", project_ref):
			project_no = frappe.db.get_value("Project Registration", project_ref, "project_no")
			if project_no:
				self.project_code = project_no

	def calculate_total(self):
		total = 0
		for row in self.expenditure_details:
			total += row.amount_in_rs or 0
		self.total_amount = total


@frappe.whitelist()
def get_advance_settlement_fields(doc_name=None):
	"""
	API to return Advance Settlement field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	Includes client scripts and child table metadata.
	"""
	doctype_name = "Advance Settlement"
	meta = frappe.get_meta(doctype_name)

	fields = []
	link_fields = []
	child_table_meta = {}

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
					child_fields.append(
						{
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
							"fetch_if_empty": cf.fetch_if_empty,
							"in_list_view": cf.in_list_view,
							"columns": cf.columns,
							"depends_on": cf.depends_on,
							"mandatory_depends_on": cf.mandatory_depends_on,
							"read_only_depends_on": cf.read_only_depends_on,
							"depends_on_eval": extract_eval_expression(cf.depends_on),
							"mandatory_depends_on_eval": extract_eval_expression(cf.mandatory_depends_on),
							"read_only_depends_on_eval": extract_eval_expression(cf.read_only_depends_on),
						}
					)
				child_table_meta[f.fieldname] = {"doctype": f.options, "fields": child_fields}
			except Exception as e:
				frappe.log_error(
					f"Error fetching child table meta for {f.options}: {str(e)}", "Child Table Meta Error"
				)

	prefill_data = {}
	link_options = {}
	related_data = {}

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Advance Settlement document for editing
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
			if not prefill_data.get("webmail_id"):
				prefill_data["webmail_id"] = user_data.name
			if not prefill_data.get("applicant_name"):
				prefill_data["applicant_name"] = user_data.full_name
			if not prefill_data.get("designation"):
				prefill_data["designation"] = user_data.designation_name
			if not prefill_data.get("department"):
				prefill_data["department"] = user_data.department_name

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
					limit_page_length=500,
				)
			else:
				link_options[fieldname] = frappe.get_all(
					linked_doctype, fields=["name as value", f"{title_field} as label"], limit_page_length=500
				)
		except Exception:
			link_options[fieldname] = frappe.get_all(
				linked_doctype, fields=["name as value", "name as label"], limit_page_length=500
			)

	# Department options (explicit)
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["department"] = departments
	except Exception:
		link_options["department"] = []

	# Designation options (from User doctype - get unique designations)
	try:
		designations_raw = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["designation"],
			limit_page_length=1000,
		)
		unique_designations = list(
			set(d.get("designation") for d in designations_raw if d.get("designation"))
		)
		designations = [{"value": d, "label": d} for d in sorted(unique_designations)]
		link_options["designation"] = designations
	except Exception:
		link_options["designation"] = []

	# Fetch Client Scripts from Frappe (stored in database)
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script", filters={"dt": doctype_name, "enabled": 1}, fields=["name", "script", "view"]
		)
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"client_scripts": client_scripts,
		"child_table_meta": child_table_meta,
	}


@frappe.whitelist()
def get_user_details_advance_settlement(user_email):
	"""
	Fetches details for a specific user to populate form fields.
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
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details for Advance Settlement"))
		frappe.throw(_("An error occurred while fetching user details."))


@frappe.whitelist()
def save_advance_settlement(doc_data):
	"""Saves or updates the Advance Settlement data from the React form.
	Handles file uploads for Attach fields.
	"""
	from frappe.utils.file_manager import save_file

	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Advance Settlement:", data)  # Debug log

		doc_name = data.get("name")
		is_new = False
		doctype_name = "Advance Settlement"

		# 1. Initialize Document
		if doc_name and frappe.db.exists(doctype_name, doc_name):
			doc = frappe.get_doc(doctype_name, doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc(doctype_name)
			is_new = True

		meta = frappe.get_meta(doctype_name)

		# --- Resolve project_name: frontend may send project title instead of document name ---
		raw_project_name = data.get("project_name")
		if raw_project_name and not frappe.db.exists("Project Registration", raw_project_name):
			# Try to find by project_title
			found_name = frappe.db.get_value(
				"Project Registration", {"project_title": raw_project_name}, "name"
			)
			if found_name:
				data["project_name"] = found_name

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
		if is_new:
			doc.insert(ignore_mandatory=True)
			print(f"Created new Advance Settlement doc: {doc.name}")
		else:
			doc.save(ignore_permissions=True)
			print(f"Updated existing Advance Settlement doc: {doc.name}")

		# 4. Second Pass: Process Files and Tables (Now we have doc.name)
		for fieldname, value in file_fields:
			df = meta.get_field(fieldname)

			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])  # Clear existing
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
										doctype_name,
										doc.name,  # Attach to parent
										decode=True,
										is_private=1,
										df=cf.fieldname,
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
							doctype_name,
							doc.name,
							decode=True,
							is_private=1,
							df=fieldname,
						)
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

		print(f"Successfully finalized Advance Settlement: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Advance Settlement Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Advance Settlement: {str(e)}")


# @frappe.whitelist()
# def submit_advance_settlement(docname=None):
# 	"""
# 	Submit an Advance Settlement document.
# 	"""
# 	if not docname:
# 		docname = frappe.form_dict.get("name") or frappe.form_dict.get("docname") or frappe.form_dict.get("doc_name")

# 	if not docname:
# 		frappe.throw(_("Advance Settlement Name is required for submission."))

# 	try:
# 		doc = frappe.get_doc("Advance Settlement", docname)

# 		if doc.docstatus == 0:
# 			doc.flags.ignore_permissions = True
# 			doc.submit()
# 			frappe.db.commit()
# 			return {
# 				"status": "success",
# 				"message": f"Advance Settlement '{docname}' submitted successfully.",
# 				"docname": docname,
# 				"docstatus": doc.docstatus,
# 			}
# 		elif doc.docstatus == 1:
# 			return {
# 				"status": "info",
# 				"message": f"Advance Settlement '{docname}' is already submitted.",
# 				"docname": docname,
# 				"docstatus": doc.docstatus,
# 			}
# 		else:
# 			return {
# 				"status": "error",
# 				"message": f"Advance Settlement '{docname}' is cancelled and cannot be submitted.",
# 				"docname": docname,
# 				"docstatus": doc.docstatus,
# 			}

# 	except Exception as e:
# 		frappe.db.rollback()
# 		frappe.log_error(frappe.get_traceback(), "Advance Settlement Submit Error")
# 		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_advance_settlement(docname=None):
	"""
	Submit an Advance Settlement document via workflow action.
	Uses perform_advance_settlement_action to properly transition
	both workflow_state and docstatus together.
	"""
	if not docname:
		docname = (
			frappe.form_dict.get("name")
			or frappe.form_dict.get("docname")
			or frappe.form_dict.get("doc_name")
		)

	if not docname:
		frappe.throw(_("Advance Settlement Name is required for submission."))

	try:
		doc = frappe.get_doc("Advance Settlement", docname)

		if doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Advance Settlement '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 2:
			return {
				"status": "error",
				"message": f"Advance Settlement '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

		# Use workflow action instead of doc.submit() so that
		# workflow_state and docstatus transition together
		result = perform_advance_settlement_action(docname, "Submit")

		if result.get("status") == "success":
			return {
				"status": "success",
				"message": f"Advance Settlement '{docname}' submitted successfully.",
				"docname": docname,
				"workflow_state": result.get("workflow_state"),
			}
		else:
			return result

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Advance Settlement Submit Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_advance_settlement_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Advance Settlement", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": "Advance Settlement", "is_active": 1}, "name"
	)

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
def perform_advance_settlement_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Advance Settlement", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.db.get_value(
			"Workflow", {"document_type": "Advance Settlement", "is_active": 1}, "name"
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for Advance Settlement."))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				transition = t
				break

		if not next_state:
			frappe.throw(_(f"No valid transition found for action '{action}' from state '{current_state}'."))

		# Update workflow state
		doc.workflow_state = next_state

		# Check if next state requires submission (docstatus=1)
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.flags.ignore_permissions = True
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
			"next_actions": get_advance_settlement_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Advance Settlement Action Error")
		return {"status": "error", "message": str(e)}


# ==========================================
# Kafka Commit & Payment Publishing - [Manish Added this (20-02-2026)]
# ==========================================

from frappe.utils import flt, today

from rndopsapp.rndopsapp.kafka.producer.reimbursement import (
	publish_commit as kafka_publish_commit,
)
from rndopsapp.rndopsapp.kafka.producer.reimbursement import (
	publish_payment as kafka_publish_payment,
)


@frappe.whitelist()
def submit_advance_settlement_commit(
	name, frapAppId, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None
):
	"""
	Submit commit data for an Advance Settlement document to Kafka.

	Args:
		name: Advance Settlement document name
		frapAppId: Frap App ID for the ledger system
		project_name: Project number (Link to Project Registration)
		commit_amount: Commit amount (always provided by the caller)
		budget_head: Budget head name or ID
		bmr: BMR number (optional)
		bill_amount: Bill amount (optional)

	Returns:
		dict: {status, message, kafka_payload}
	"""
	try:
		doc = frappe.get_doc("Advance Settlement", name)

		# Generate the event to get the payload for the response
		from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import AccountHeadCommitMapper

		event = AccountHeadCommitMapper.map_to_event(
			doc=doc,
			commit_amount=flt(commit_amount),
			budget_head=budget_head,
			project_name=project_name,
			bmr=bmr,
			bill_amount=flt(bill_amount) if bill_amount else None,
			frap_app_id=frapAppId,
			ref_details=refDetails,
		)
		kafka_payload = event.to_kafka_payload()

		success = kafka_publish_commit(
			doc=doc,
			commit_amount=flt(commit_amount),
			budget_head=budget_head,
			project_name=project_name,
			bmr=bmr,
			bill_amount=flt(bill_amount) if bill_amount else None,
			frap_app_id=frapAppId,
			ref_details=refDetails,
		)

		if success:
			return {
				"status": "success",
				"message": "Advance Settlement commit published to Kafka",
				"kafka_payload": kafka_payload,
			}
		else:
			return {
				"status": "error",
				"message": "Failed to publish Advance Settlement commit",
				"kafka_payload": kafka_payload,
			}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Advance Settlement Commit Kafka Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_advance_settlement_payment(
	name=None, project_name=None, payment_amount=None, budget_head=None, bmr=None, refDetails=None
):
	"""
	Submit payment data for an Advance Settlement to Kafka.
	Creates or updates an AccountHeadPayment document and publishes to Kafka.

	Args:
		name: AccountHeadPayment document name (optional, creates new if not provided)
		project_name: Project reference number
		payment_amount: Payment amount (always provided by the caller)
		budget_head: Budget head name or ID
		bmr: BMR number (optional)

	Returns:
		dict: {status, message, name, data, kafka_payload}
	"""
	try:
		# Normalize name
		if not name or name in ("None", "null", "undefined", ""):
			name = None

		doc = None
		if name:
			try:
				doc = frappe.get_doc("AccountHeadPayment", name)
			except frappe.DoesNotExistError:
				pass

		# Create new document if not found
		is_new = False
		if not doc:
			is_new = True
			doc = frappe.new_doc("AccountHeadPayment")

		# Populate fields
		if project_name:
			doc.project_ref_number = project_name
		doc.payment_amount = flt(payment_amount) if payment_amount else doc.payment_amount
		if budget_head:
			# Resolve Budget Head to valid Link Name (PK)
			resolved_budget_head = budget_head
			if not frappe.db.exists("Budget Head", budget_head):
				found_name = frappe.db.get_value("Budget Head", {"budget_head": budget_head}, "name")
				if not found_name:
					found_name = frappe.db.get_value("Budget Head", {"id": budget_head}, "name")
				if found_name:
					resolved_budget_head = found_name
			doc.budget_head = resolved_budget_head
		if bmr:
			doc.payment_bmr = bmr

		# Populate from form_dict if available
		for field in [
			"payment_date",
			"payment_particular",
			"payment_reference_details",
			"payment_status",
			"bank_transaction_number",
			"bank_transaction_date",
			"commit_id",
		]:
			if field in frappe.form_dict:
				doc.set(field, frappe.form_dict[field])

		# Defaults
		if not doc.payment_status:
			doc.payment_status = "PENDING"
		if not doc.payment_date:
			doc.payment_date = today()

		# Validate required fields for new documents
		if is_new:
			if not doc.project_ref_number:
				print("[ADVANCE_PAYMENT] Failed: no project_ref_number")
				return {"status": "error", "message": "Project Reference Number is required"}
			if not doc.budget_head:
				print("[ADVANCE_PAYMENT] Failed: no budget_head")
				return {"status": "error", "message": "Budget Head is required"}

		# Save
		doc.flags.ignore_permissions = True
		print(f"[ADVANCE_PAYMENT] Saving doc. is_new={is_new} doc.name={doc.name}")
		if is_new:
			doc.insert()
		else:
			doc.save()
		print(f"[ADVANCE_PAYMENT] Saved doc. doc.name={doc.name}")

		# Generate the event to get the payload for the response
		from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import AccountHeadPaymentMapper

		event = AccountHeadPaymentMapper.map_to_event(
			doc=doc,
			project_name=None,
			payment_amount=None,
			budget_head=None,
			bmr=None,
			ref_details=refDetails,
		)
		kafka_payload = event.to_kafka_payload()
		print(f"[ADVANCE_PAYMENT] Generated Kafka payload: {kafka_payload}")

		# Publish to Kafka
		print("[ADVANCE_PAYMENT] Calling kafka_publish_payment...")
		success = kafka_publish_payment(
			doc=doc,
			project_name=None,
			payment_amount=None,
			budget_head=None,
			bmr=None,
			ref_details=refDetails,
		)
		print(f"[ADVANCE_PAYMENT] kafka_publish_payment returned {success}")

		if success:
			return {
				"status": "success",
				"message": "Advance Settlement payment published to Kafka",
				"name": doc.name,
				"data": doc.as_dict(),
				"kafka_payload": kafka_payload,
			}
		else:
			return {
				"status": "error",
				"message": "Failed to publish Advance Settlement payment",
				"name": doc.name,
				"data": doc.as_dict(),
				"kafka_payload": kafka_payload,
			}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Advance Settlement Payment Kafka Error")
		return {"status": "error", "message": str(e)}
