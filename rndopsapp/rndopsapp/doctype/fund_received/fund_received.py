# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import base64
import json
import os

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, sanitize_html
from rndopsapp.rndopsapp.kafka_sync import publish_fund_received


class FundReceived(Document):
	def validate(self):
		"""Validate and auto-populate sanction letter details from linked Fund Sanction"""
		self.populate_sanction_details()
	
	def populate_sanction_details(self):
		"""
		Fetch sanction letter number and date from the Fund Sanction 
		linked to this project and populate them on this document.
		"""
		# Use getattr for safe access - fields may not exist on the doctype
		current_letter_no = getattr(self, 'sanctioned_letter_no', None)
		current_letter_date = getattr(self, 'sanctioned_letter_date', None)
		
		# Skip if already populated
		if current_letter_no and current_letter_date:
			return
		
		# Get the project registration number
		project_number = getattr(self, 'prjreg_title', None)
		if not project_number:
			return
		
		try:
			# Find the latest Fund Sanction for this project
			# First try using sanction_ref_no if available
			sanction_name = getattr(self, 'sanction_ref_no', None)
			
			if not sanction_name:
				# Fallback: find Fund Sanction by project registration
				sanction_name = frappe.db.get_value(
					"Fund Sanction",
					{"refnum_prj_num": project_number},
					"name",
					order_by="creation desc"
				)
				
				# Also try project_proposal field
				if not sanction_name:
					sanction_name = frappe.db.get_value(
						"Fund Sanction",
						{"project_proposal": project_number},
						"name",
						order_by="creation desc"
					)
			
			if sanction_name:
				# Fetch sanction letter details
				sanction_doc = frappe.db.get_value(
					"Fund Sanction",
					sanction_name,
					["sanctioned_letter_no", "sanctioned_letter_date"],
					as_dict=True
				)
				
				if sanction_doc:
					# Only set if not already set and field exists on doctype
					if not current_letter_no and sanction_doc.get("sanctioned_letter_no"):
						if hasattr(self, 'sanctioned_letter_no') or 'sanctioned_letter_no' in [f.fieldname for f in self.meta.fields]:
							self.sanctioned_letter_no = sanction_doc.get("sanctioned_letter_no")
					
					if not current_letter_date and sanction_doc.get("sanctioned_letter_date"):
						if hasattr(self, 'sanctioned_letter_date') or 'sanctioned_letter_date' in [f.fieldname for f in self.meta.fields]:
							self.sanctioned_letter_date = sanction_doc.get("sanctioned_letter_date")
					
					# Also set sanction_ref_no if not set
					if not getattr(self, 'sanction_ref_no', None):
						self.sanction_ref_no = sanction_name
					
					print(f"✅ Auto-populated sanction details for {self.name}: letter_no={sanction_doc.get('sanctioned_letter_no')}, date={sanction_doc.get('sanctioned_letter_date')}")
				else:
					print(f"⚠️ Fund Sanction {sanction_name} found but has no letter details")
			else:
				print(f"📋 No Fund Sanction found for project {project_number}")
				
		except Exception as e:
			frappe.log_error(f"Error fetching sanction details for Fund Received: {e}", "Fund Received Validate Error")
			print(f"❌ Error fetching sanction details: {e}")



def save_file(fname, content, dt, dn, folder=None):
	"""Save base64 file content as a File document"""
	try:
		import base64

		from frappe.utils.file_manager import save_file

		# Decode base64 content
		file_content = base64.b64decode(content)

		# Save the file
		file_doc = save_file(fname=fname, content=file_content, dt=dt, dn=dn, folder=folder, is_private=0)

		return file_doc
	except Exception as e:
		print(f"Error saving file {fname}: {str(e)}")
		return None


# jimmy added
@frappe.whitelist()
def get_fund_received_fields(doc_name=None):
	"""
	API to return Fund Received field metadata and prefill data
	based on a Project Registration ref number (doc_name).
	"""
	fund_received_meta = frappe.get_meta("Fund Received")

	fields = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
		}
		for f in fund_received_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	if not doc_name:
		frappe.throw("Project ref number (doc_name) is required.")

	# Clean input
	doc_name = str(doc_name).strip('"').strip("'")

	# Fetch Project Registration
	project_doc = frappe.db.get_value(
		"Project Registration", doc_name, ["name", "project_title", "project_type"], as_dict=True
	)

	if not project_doc:
		frappe.throw(f"Project Registration '{doc_name}' not found.")

	related_project_data = project_doc
	prefill_data["prjreg_refnum"] = project_doc.name

	# Fetch Fund Sanction linked to this project
	sanctions = frappe.get_all(
		"Fund Sanction",
		filters={"refnum_prj_num": project_doc.name},
		fields=["name as value", "sanctioned_letter_no as label", "project_proposal", "refnum_prj_num"],
	)

	# Only prefill if Fund Sanction ref matches project
	if sanctions:
		# If there’s exactly one sanction, prefill related fields
		if len(sanctions) == 1:
			sanction_doc = frappe.get_doc("Fund Sanction", sanctions[0]["value"])
			prefill_data.update(
				{
					"sanction_ref_no": sanction_doc.name,
					"project_proposal": sanction_doc.project_proposal,
					# Add more fields from sanction if needed
					# "sanctioned_amount": sanction_doc.sanctioned_amount,
					# "sanction_date": sanction_doc.sanction_date
				}
			)

	# Link options for dropdowns
	link_options["prjreg_refnum"] = [{"value": project_doc.name, "label": project_doc.project_title}]
	link_options["sanction_ref_no"] = sanctions
	link_options["amended_from"] = frappe.get_all("Fund Received", fields=["name as value"])

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}



@frappe.whitelist(allow_guest=False)
def get_fund_received_by_prjreg(prjreg_title: str = "", limit: int = 200, start: int = 0):
	"""
	Returns Fund Received docs for a given prjreg_title in the format:
	{ "message": [ { ... full doc as dict ... }, ... ] }

	Access:
	  - Trusted gateway (Bruno) may forward X-Internal-Auth header with secret stored as
	    `bruno_internal_secret` in site_config.json to allow gateway access.
	  - Otherwise caller must be authenticated (API token or session).

	Example:
	/api/method/rndopsapp.rndopsapp.doctype.fund_received.fund_received.get_fund_received_by_prjreg?prjreg_title=2025111101DST000103
	"""
	# --- 0) basic arg sanitization / casting ---
	limit = int(cint(limit) or 200)
	start = int(cint(start) or 0)
	prjreg_title = (prjreg_title or "").strip()

	# --- 1) gateway guard: allow Bruno via internal secret header ---
	bruno_secret = frappe.conf.get("bruno_internal_secret")
	hdr = frappe.get_request_header("X-Internal-Auth")

	if hdr == bruno_secret:
		# trusted gateway: allow the request through (even if Guest)
		pass
	else:
		# require authenticated user (API token or logged-in session)
		if not frappe.session.user or frappe.session.user == "Guest":
			frappe.throw(_("Authentication required"), frappe.PermissionError)

	# --- 2) permission check: ensure current user has read permission on Fund Received ---
	# If brokered by Bruno (hdr matched), we skip per-user permission checks.
	if hdr != bruno_secret:
		if not frappe.has_permission("Fund Received", ptype="read", user=frappe.session.user):
			frappe.throw(_("Permission denied"), frappe.PermissionError)

	results = []
	try:
		# Get matching doc names with pagination
		names = frappe.get_all(
			"Fund Received",
			filters={"prjreg_title": prjreg_title},
			fields=["name"],
			limit_start=start,
			limit_page_length=limit,
			order_by="modified desc",
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_fund_received_by_prjreg: failed to query names")
		return {"message": []}

	if not names:
		return {"message": []}

	for row in names:
		name = row.get("name")
		try:
			doc = frappe.get_doc("Fund Received", name)
			# Convert to dict including child tables
			doc_dict = doc.as_dict()

			# OPTIONAL: strip out large or sensitive fields here if you want
			# e.g., remove file binary content; currently keeping fields as-is (document_upload is null in sample)

			# Ensure child tables present even if empty (to match sample shape)
			if "received_amt_breakup" not in doc_dict:
				doc_dict["received_amt_breakup"] = []
			if "fund_transactions" not in doc_dict:
				doc_dict["fund_transactions"] = []

			results.append(doc_dict)
		except Exception:
			# Log but continue with other docs
			frappe.log_error(frappe.get_traceback(), f"get_fund_received_by_prjreg: error loading {name}")
			continue

	return {"message": results}


@frappe.whitelist()
def save_fund_received(doc_data, prjreg_title=None):
	"""Saves the Fund Received data from the React form and forwards to external API (no DB writes for API response)."""
	try:
		data = json.loads(doc_data)
		print(f"Received data for Fund Received: {data}, prjreg_title arg: {prjreg_title}")  # Debug log

		# If prjreg_title is not in data but passed as argument, add it to data
		if "prjreg_title" not in data and prjreg_title:
			data["prjreg_title"] = prjreg_title

		# Create new Fund Received document
		new_doc = frappe.new_doc("Fund Received")

		# Map the form data to doctype fields
		field_mapping = {
			"prjreg_title": "prjreg_title",
			"prjreg_refnum": "prjreg_title",  # Map prjreg_refnum to prjreg_title as fallback
			"sanction_ref_no": "sanction_ref_no",
			"prj_type": "prj_type",
			"fund_received_amt": "fund_received_amt",
			"bank_account": "bank_account",
			"gst_invoice_issued": "gst_invoice_issued",
			"invoice_no": "invoice_no",
			# add any other mappings you need here
		}

		# Update document with mapped data
		# Process prjreg_title first, then prjreg_refnum (so prjreg_title takes precedence if both exist)
		for form_field, doctype_field in field_mapping.items():
			# Skip if already set (for fallback mappings like prjreg_refnum -> prjreg_title)
			current_value = new_doc.get(doctype_field)
			if current_value not in [None, ""]:
				continue
			if form_field in data and data[form_field] not in [None, ""]:
				new_doc.set(doctype_field, data[form_field])

		# Handle child tables - FILTER OUT EMPTY ROWS
		if "fund_transactions" in data:
			for transaction in data["fund_transactions"]:
				# Only add rows that have at least transaction_number OR amount > 0
				if (
					transaction.get("transaction_number") not in [None, ""]
					or transaction.get("amount", 0) > 0
				):
					# Handle file attachment if present
					attachment_data = {}
					if transaction.get("file_data") and transaction.get("file_name"):
						# Save the file and get the file URL
						# save_file must exist in your environment (frappe.utils.file or similar)
						file_doc = save_file(
							fname=transaction.get("file_name"),
							content=transaction.get("file_data"),
							dt="Fund Received",
							dn=new_doc.name,
							folder="Home/Attachments",
						)
						if file_doc:
							attachment_data["attachment"] = file_doc.file_url

					new_doc.append(
						"fund_transactions",
						{
							"transaction_number": transaction.get("transaction_number") or "",
							"transaction_date": transaction.get("transaction_date"),
							"amount": transaction.get("amount", 0),
							**attachment_data,
						},
					)

		if "received_amt_breakup" in data:
			for breakup in data["received_amt_breakup"]:
				# Only add rows that have at least account_head OR amount_received > 0
				if breakup.get("account_head") not in [None, ""] or breakup.get("amount_received", 0) > 0:
					new_doc.append(
						"received_amt_breakup",
						{
							"account_head": breakup.get("account_head") or "",
							"amount_received": breakup.get("amount_received", 0),
							"budget_year_funds_receive": breakup.get("budget_year_funds_receive", 1),
							"remarks": breakup.get("remarks") or "",
						},
					)

		# Save the document
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully created Fund Received: {new_doc.name}")  # Debug log

		# --- Send payload to external API (Kafka) ---
		try:
			success = publish_fund_received(new_doc)
			if success:
				frappe.msgprint(_("Fund Received data synced successfully to external system."), indicator="green")
			else:
				# Rollback: Delete newly created document
				new_doc.delete(ignore_permissions=True)
				frappe.db.rollback()
				frappe.throw(_("Kafka sync failed. Fund Received was not saved. Please try again."))
		except frappe.ValidationError:
			raise  # Re-raise validation errors from frappe.throw
		except Exception as ex:
			# Rollback: Delete newly created document
			frappe.log_error(frappe.get_traceback(), "Fund Received -> Kafka Sync error")
			new_doc.delete(ignore_permissions=True)
			frappe.db.rollback()
			frappe.throw(_("Kafka sync failed. Fund Received was not saved. Please try again."))

		return {"status": "success", "docname": new_doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Fund Received Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Fund Received: {str(e)}")



def send_fund_received_to_api(fund_doc):
	"""
	Prints every step. Resolves accountHeadId from Budget Head.doctype's `id` using the `budget_head` field.
	Normalizes names to handle plural/singular mismatches.
	"""
	print("\n=== SEND FUND RECEIVED TO API START ===")
	try:
		url = "http://172.16.135.27:18080/api/fund-received/addFundReceived"
		print(f"[URL] {url}")

		print("[STEP] Building payload...")

		payload = {
			"sanctionNumber": getattr(fund_doc, "sanction_ref_no", None),
			"projectNumber": getattr(fund_doc, "project_number", None)
			or getattr(fund_doc, "prjreg_title", None),
			"amountReceived": float(getattr(fund_doc, "fund_received_amt", 0) or 0),
			"iitgAccountNumber": getattr(fund_doc, "bank_account", None),
			"depositSlipStatus": bool(getattr(fund_doc, "deposit_slip_status", False) or False),
			"fundReceivedStatus": getattr(fund_doc, "fund_received_status", None) or "PENDING_APPROVAL",
			"fundBudgetBreakupList": [],
			"transactionDetailsList": [],
		}

		print("[PAYLOAD-BASE]", payload)

		# ------------------------------
		# Build budget head name -> id map (one DB hit)
		# ------------------------------
		print("[STEP] Loading Budget Head mapping from DB...")
		try:
			bh_rows = frappe.get_all(
				"Budget Head",
				fields=["budget_head", "id"],
				order_by="id asc",
			)
			print(f"     - fetched {len(bh_rows)} Budget Head rows")
		except Exception as e:
			print("     - ERROR fetching Budget Head:", e)
			bh_rows = []

		def normalize_label(s):
			if s is None:
				return None
			s = str(s).strip().lower()
			# simple plural handling: strip trailing 's' if present and result not empty
			if s.endswith("s") and len(s) > 1:
				s_no_s = s[:-1]
			else:
				s_no_s = s
			return (s, s_no_s)

		# build mapping: normalized -> id
		bh_map = {}
		for r in bh_rows:
			label = r.get("budget_head") or r.get("budget_head")  # defensive
			if label is None:
				continue
			norm1, norm2 = normalize_label(label)
			# prefer exact normalized form first
			if norm1 not in bh_map:
				bh_map[norm1] = r.get("id")
			if norm2 not in bh_map:
				bh_map[norm2] = r.get("id")

		print("     - Budget Head map:", bh_map)

		# ------------------------------
		# Budget breakup mapping (resolve accountHeadId from Budget Head -> id)
		# ------------------------------
		print("[STEP] Mapping budget breakup...")

		if hasattr(fund_doc, "received_amt_breakup"):
			for row in fund_doc.received_amt_breakup:
				row_name = getattr(row, "name", "<no-name>")
				print(f"   > Breakup Row = {row_name}")

				ah = getattr(row, "account_head", None)
				print(f"     - raw account_head value: {ah}")

				account_head_id = None

				# 1) If already int, use it
				if isinstance(ah, int):
					account_head_id = ah
					print(f"     - account_head is int -> {account_head_id}")
				else:
					# 2) Try direct lookup in bh_map using normalization
					norm_candidates = []
					if ah is not None:
						norm_candidates = list(normalize_label(ah))
					for cand in norm_candidates:
						if cand and cand in bh_map:
							account_head_id = bh_map[cand]
							print(f"     - matched budget_head '{cand}' -> id {account_head_id}")
							break

					# 3) If still None, try DB fetch by budget_head exact (defensive)
					if account_head_id is None and ah not in (None, ""):
						try:
							bh_id = frappe.db.get_value("Budget Head", {"budget_head": ah}, "id")
							if bh_id not in (None, ""):
								account_head_id = int(bh_id)
								print(
									f"     - db.get_value matched exact budget_head '{ah}' -> id {account_head_id}"
								)
						except Exception as e:
							print(f"     - db lookup error for budget_head '{ah}': {e}")

					# 4) If still None, try coercing the value to int (strings like "5")
					if account_head_id is None and ah not in (None, ""):
						try:
							coerced = int(str(ah))
							account_head_id = coerced
							print(f"     - coerced account_head to int -> {account_head_id}")
						except Exception:
							print("     - cannot coerce account_head to int; will fallback to None")

				amount = float(getattr(row, "amount_received", 0) or 0)

				payload["fundBudgetBreakupList"].append(
					{
						"accountHeadId": account_head_id,
						"amount": amount,
						"remarks": getattr(row, "remarks", "") or "",
					}
				)

				print(f"     - Final mapped: accountHeadId={account_head_id}, amount={amount}")

		print("[BREAKUP DONE]")

		# ------------------------------
		# Transactions mapping
		# ------------------------------
		print("[STEP] Mapping transactions...")

		if hasattr(fund_doc, "fund_transactions"):
			for trx in fund_doc.fund_transactions:
				print(f"   > Transaction Row = {getattr(trx, 'name', '<no-name>')}")

				trx_data = {
					"uniqueTransactionNumber": getattr(trx, "transaction_number", "") or "",
					"transactionReceivedDate": str(getattr(trx, "transaction_date", None))
					if getattr(trx, "transaction_date", None)
					else None,
					"transactionAmount": float(getattr(trx, "amount", 0) or 0),
				}

				payload["transactionDetailsList"].append(trx_data)
				print(f"     - trx={trx_data}")

		print("[TRANSACTIONS DONE]")
		print("[FINAL PAYLOAD]", payload)

		# ------------------------------
		# API CALL
		# ------------------------------
		print("[STEP] Sending POST request...")

		headers = {"Content-Type": "application/json"}
		resp = requests.post(url, json=payload, headers=headers, timeout=10)

		print(f"[API RESPONSE] Status={resp.status_code}")

		try:
			resp_json = resp.json()
			print("[API RESPONSE JSON]", resp_json)
		except Exception:
			resp_json = resp.text
			print("[API RESPONSE TEXT]", resp_json)

		frappe.logger().info(
			f"Fund Received API -> status={resp.status_code}, doc={getattr(fund_doc, 'name', None)}, response={resp_json}"
		)

		print("=== SEND FUND RECEIVED TO API END ===\n")

		return {
			"ok": resp.status_code in (200, 201),
			"status_code": resp.status_code,
			"response": resp_json,
		}

	except requests.exceptions.RequestException as re:
		print("[ERROR] RequestException:", re)
		frappe.log_error(frappe.get_traceback(), "Fund Received API RequestException")
		return {"ok": False, "error": str(re)}

	except Exception as e:
		print("[ERROR] Exception:", e)
		frappe.log_error(frappe.get_traceback(), "Fund Received API Unknown Error")
		return {"ok": False, "error": str(e)}




@frappe.whitelist()
def get_fund_received_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Fund Received", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = "Fund_Received_Workflow"
	
	if not frappe.db.exists("Workflow", workflow_name):
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
def perform_fund_received_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Fund Received", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = "Fund_Received_Workflow"
		
		if not frappe.db.exists("Workflow", workflow_name):
			frappe.throw(f"Workflow '{workflow_name}' not found.")

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
			"next_actions": get_fund_received_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Fund Received Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_fund_received(docname):
	"""
	Submit a Fund Received document using Workflow transitions.
	"""
	return perform_fund_received_action(docname, "Submit")
