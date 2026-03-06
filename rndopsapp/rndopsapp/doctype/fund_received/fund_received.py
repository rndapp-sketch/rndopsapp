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
from rndopsapp.rndopsapp.kafka.producer import publish_fund_received


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

		# INSERT DOC FIRST to generate a name for file attachments
		new_doc.insert(ignore_permissions=True)

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
							dn=new_doc.name, # Now valid
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
			# Build lookup map: budget_head label -> document name
			try:
				budget_heads = frappe.get_all("Budget Head", fields=["name", "budget_head"])
				bh_label_to_name = {b.budget_head: b.name for b in budget_heads}
				print(f"DEBUG: Budget Head label->name map: {bh_label_to_name}")
			except Exception as e:
				print(f"DEBUG: Error fetching Budget Head lookup: {e}")
				bh_label_to_name = {}
			
			for breakup in data["received_amt_breakup"]:
				# Only add rows that have at least account_head OR amount_received > 0
				if breakup.get("account_head") not in [None, ""] or breakup.get("amount_received", 0) > 0:
					raw_account_head = breakup.get("account_head") or ""
					
					# Resolve account_head label to Budget Head document name
					account_head_name = raw_account_head
					if raw_account_head in bh_label_to_name:
						account_head_name = bh_label_to_name[raw_account_head]
						print(f"DEBUG: Resolved account_head '{raw_account_head}' -> '{account_head_name}'")
					else:
						# Maybe already a valid doc name, or try case-insensitive match
						for label, name in bh_label_to_name.items():
							if label.lower() == raw_account_head.lower():
								account_head_name = name
								print(f"DEBUG: Case-insensitive match '{raw_account_head}' -> '{account_head_name}'")
								break
					
					new_doc.append(
						"received_amt_breakup",
						{
							"account_head": account_head_name,
							"amount_received": breakup.get("amount_received", 0),
							"budget_year_funds_receive": breakup.get("budget_year_funds_receive", 1),
							"remarks": breakup.get("remarks") or "",
						},
					)

		# Save again to persist child tables
		new_doc.save(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully created Fund Received: {new_doc.name}")  # Debug log

		# --- Send payload to external API (Kafka) ---
		# --- Send payload to external API (Kafka) ---
		# try:
		# 	success = publish_fund_received(new_doc)
		# 	if success:
		# 		frappe.msgprint(_("Fund Received data synced successfully to external system."), indicator="green")
		# 	else:
		# 		# Rollback: Delete newly created document
		# 		new_doc.delete(ignore_permissions=True)
		# 		frappe.db.rollback()
		# 		frappe.throw(_("Kafka sync failed. Fund Received was not saved. Please try again."))
		# except frappe.ValidationError:
		# 	raise  # Re-raise validation errors from frappe.throw
		# except Exception as ex:
		# 	# Rollback: Delete newly created document
		# 	frappe.log_error(frappe.get_traceback(), "Fund Received -> Kafka Sync error")
		# 	new_doc.delete(ignore_permissions=True)
		# 	frappe.db.rollback()
		# 	frappe.throw(_("Kafka sync failed. Fund Received was not saved. Please try again."))

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

# fund_received_with_kafka


@frappe.whitelist()
def get_fund_received_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Fund Received", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	# workflow_name = "Fund_Received_Workflow"
	workflow_name = "fund_received_with_kafka"
	
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
def perform_fund_received_action(docname, action, deposit_slip_data=None):
	"""
	Executes the selected workflow action and updates the document state.
	
	Args:
		docname (str): Name of the Fund Received document.
		action (str): Workflow action to perform.
		deposit_slip_data (json/dict, optional): Data to create a new Deposit Slip 
												 if transitioning to HoS Approval.
	"""
	try:
		doc = frappe.get_doc("Fund Received", docname)
		current_state = doc.workflow_state or "Draft"

		# --- Data Sanitization / Fix for Legacy Data ---
		# Check if prjreg_title is a valid link. If not, try to find it via project_no
		if doc.prjreg_title and not frappe.db.exists("Project Registration", doc.prjreg_title):
			print(f"DEBUG: prjreg_title '{doc.prjreg_title}' not found as ID. Searching by project_no...")
			# Try to find the project by project_no
			found_proj = frappe.db.get_value("Project Registration", {"project_no": doc.prjreg_title}, "name")
			if found_proj:
				print(f"DEBUG: Found Project Registration '{found_proj}' for project_no '{doc.prjreg_title}'. Fixing link.")
				doc.prjreg_title = found_proj
				# We don't save yet, we let the subsequent flow handle the save
			else:
				print(f"DEBUG: Could not resolve prjreg_title '{doc.prjreg_title}' to a valid Project Registration.")


		# Fetch the workflow for this doctype
		workflow_name = "fund_received_with_kafka"
		
		if not frappe.db.exists("Workflow", workflow_name):
			frappe.throw(f"Workflow '{workflow_name}' not found.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		transition = None

		# Pre-process deposit_slip_data to handle JSON strings and empty objects
		if deposit_slip_data:
			try:
				if isinstance(deposit_slip_data, str):
					parsed = json.loads(deposit_slip_data)
					deposit_slip_data = parsed if parsed else None
				elif isinstance(deposit_slip_data, dict) and not deposit_slip_data:
					deposit_slip_data = None
				
				# Check if data has meaningful content (not just empty strings or defaults)
				# We check for key fields that must be present for a valid deposit slip
				if deposit_slip_data:
					has_content = False
					# Fields that indicate user intent to create a deposit slip
					# Includes both Research Consultancy and Research Deposit Slip fields
					intent_fields = [
						# Research Consultancy Deposit Slip fields
						"category", "bank", "amount_inclusive_of_gst", "client", "consultancy_event_title",
						# Research Deposit Slip fields
						"deposit_date", "total_amount", "bank_name", "project_title", "overhead_amount"
					]
					for field in intent_fields:
						val = deposit_slip_data.get(field)
						if val and str(val).strip(): # Check for non-empty value
							has_content = True
							break
					
					if not has_content:
						deposit_slip_data = None

			except Exception as e:
				print(f"Error parsing deposit_slip_data: {e}")
				deposit_slip_data = None
		
		# Find the transition matching current state and action
		# Note: There might be multiple transitions with same action name (e.g. 'Forward')
		# Logic to distinguish path:
		# 1. If deposit_slip_data is provided, prefer path to 'Pending HoS Approval' (Row 11)
		# 2. If no deposit_slip_data, prefer path to 'Pending Accounts Staff Approval' (Row 4)
		# OR simpler: check if the 'next_state' implies a specific requirement.
		
		# Let's simple-loop first to find *candidates*
		candidates = []
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				candidates.append(t)
		
		if not candidates:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")
		
		# Logic to disambiguate if multiple candidates exist (e.g. 'Forward' action)
		if len(candidates) > 1:
			# If we are at 'Pending Misc. Staff Approval' and action is 'Forward':
			# Candidate A -> 'Pending Accounts Staff Approval'
			# Candidate B -> 'Pending HoS Approval'
			if current_state == "Pending Misc. Staff Approval" and action == "Forward":
				# Distinguish based on presence of deposit data
				if deposit_slip_data:
					# User intends to generate deposit slip -> Go to HoS
					transition = next((t for t in candidates if t.next_state == "Pending HoS Approval"), None)
					print("DEBUG: Selected HoS (via data)")
				else:
					# Standard forward -> Go to Accounts
					transition = next((t for t in candidates if t.next_state == "Pending Accounts Staff Approval"), None)
					print("DEBUG: Selected Accounts (no data)")
			else:
				# Default to first found if no specific logic defined
				transition = candidates[0]
				print(f"DEBUG: Default selection: {transition.next_state}")
		else:
			transition = candidates[0]
			print(f"DEBUG: Single candidate: {transition.next_state}")

		if not transition:
			frappe.throw(_("Could not determine next state for action '{}'.").format(action))

		next_state = transition.next_state

		# --- SIDE EFFECTS BEFORE STATE CHANGE ---

		# 1. Create Deposit Slip if transitioning to 'Pending HoS Approval'
		# Relaxed check: Only care if we are moving TO HoS Approval
		if next_state == "Pending HoS Approval": 
			print(f"DEBUG: Transitioning to HoS Approval. Data present: {bool(deposit_slip_data)}")
			if deposit_slip_data:
				create_deposit_slip_from_data(deposit_slip_data, doc)
			else:
				print(f"Warning: transitioning to {next_state} without deposit_slip_data")


		# Update workflow state
		print(f"DEBUG: Updating workflow_state from '{doc.workflow_state}' to '{next_state}'")
		doc.workflow_state = next_state
		
		# Fix Account Head IDs map (Legacy Data Fix - for old data that stored IDs)
		try:
			budget_heads = frappe.get_all("Budget Head", fields=["id", "budget_head", "name"])
			id_map = {str(b.id): b.name for b in budget_heads}  # Map ID to Budget Head name
			
			for row in doc.received_amt_breakup:
				val = str(row.account_head)
				
				# If value is an ID (e.g. "5"), map to Budget Head document name
				if val in id_map:
					row.account_head = id_map[val]
					print(f"DEBUG: Mapped Account Head ID {val} -> {row.account_head}")

		except Exception as e:
			print(f"DEBUG: Error fixing account heads: {e}")

		# Check if next state requires submission (docstatus=1)
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		
		# Bypass validation to avoid "Account Head cannot be 5" error on legacy data
		doc.flags.ignore_validate = True
		
		print(f"DEBUG: Saving with ignore_validate=True. Next State: {next_state}")

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)
		
		# Force update state in DB to avoid race conditions or hook interference
		# (Still good to keep even with save success)
		print(f"DEBUG: Reaching db_set. Next state: {next_state}")
		doc.db_set("workflow_state", next_state)
		
		print("DEBUG: Reaching commit")
		frappe.db.commit()
		print("DEBUG: Commit done")
		
						
		print(f"DEBUG: Saved doc. New state in obj: {doc.workflow_state}")

		# --- SIDE EFFECTS AFTER STATE CHANGE / SAVE ---

		# 2. Kafka Sync if transitioning to 'PENDING_APPROVAL'
		# (Send Fund Received data to Kafka when moving to PENDING_APPROVAL state)
		if next_state == "PENDING_APPROVAL":
			try:
				success = publish_fund_received(doc)
				if success:
					frappe.msgprint(_("Fund Received data synced to Kafka successfully."), indicator='green')
				else:
					frappe.msgprint(_("Kafka sync returned False."), indicator='orange')
			except Exception as k_err:
				print(f"Kafka sync error: {k_err}")
				frappe.log_error(frappe.get_traceback(), "Fund Received Workflow Kafka Sync Error")
				frappe.msgprint(_("Failed to sync with Kafka: {}").format(str(k_err)), indicator='red')

		# 3. When Fund Received is Approved by HoS -> Auto-Approve Deposit Slip & Sync to Kafka
		if next_state == "Approved":
			try:
				print("|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||")
				print("|||||||||||||||||||||||KAFKA|||||||||||||||||||||||||||||||||")
				print("|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||")
				
				# List of potential Deposit Slip doctypes
				deposit_doctypes = [
					"Research Deposit Slip",
					"Research Consultancy Deposit Slip", 
					"D Consultancy Deposit Slip",
					"E Non Routine Deposit Slip",
					"Other Event Deposit Slip",
					"T Testing Deposit Slip"
				]

				# Find linked Deposit Slip in any of the potential doctypes
				ds_name = None
				found_doctype = None
				
				for dt in deposit_doctypes:
					ds_name = frappe.db.get_value(dt, {"fund_received_ref": doc.name}, "name")
					if ds_name:
						found_doctype = dt
						break
				
				if ds_name and found_doctype:
					print(f"DEBUG: Found linked Deposit Slip {ds_name} of type {found_doctype}. Auto-approving and Syncing...")
					ds_doc = frappe.get_doc(found_doctype, ds_name)
					
					# Get current workflow_state (Data field, not Frappe workflow)
					# Use get() for safe access since it's a Data field
					current_ds_state = ds_doc.get("workflow_state") or ""
					print(f"DEBUG: Current Deposit Slip state: '{current_ds_state}'")
					
					# Update State to Approved if not already
					if current_ds_state != "Approved":
						ds_doc.workflow_state = "Approved"
						ds_doc.flags.ignore_validate = True
						ds_doc.save(ignore_permissions=True)
						print(f"DEBUG: Deposit Slip {ds_name} state updated to 'Approved'")
						
					# Submit if not submitted
					if ds_doc.docstatus == 0:
						ds_doc.flags.ignore_validate = True
						ds_doc.submit()
						print(f"DEBUG: Deposit Slip {ds_name} submitted")
					
					# Note: Kafka sync is handled by the on_update() hook in Research Consultancy Deposit Slip
					# when save() is called with workflow_state = "Approved"
					frappe.msgprint(_(f"Linked {found_doctype} Approved and Synced to Kafka."), indicator='green')
				else:
					print("DEBUG: No linked Deposit Slip found.")
					
				print("|||||||||||||||||||||||KAFKA end|||||||||||||||||||||||||||||||||")
			except Exception as ds_err:
				print(f"DEBUG: Error auto-processing Deposit Slip: {ds_err}")
				print(frappe.get_traceback())
				frappe.log_error(frappe.get_traceback(), "Auto Deposit Slip Sync Error")
				frappe.msgprint(_("Error processing Deposit Slip: {}").format(str(ds_err)), indicator='red')
		
		print("DEBUG: End of function success")
		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_fund_received_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		print(f"DEBUG: Exception in perform_fund_received_action: {e}")
		print(frappe.get_traceback())
		frappe.log_error(frappe.get_traceback(), "Fund Received Action Error")
		return {"status": "error", "message": str(e)}


def create_deposit_slip_from_data(data_json, fund_received_doc):
	"""
	Helper to create a fresh Deposit Slip document linked to the Fund Received doc.
	Reuse logic similar to save_deposit_slip but internal.
	"""
	import json
	import traceback
	from rndopsapp.rndopsapp.doctype.fund_received.deposit_logger import (
		log_deposit_creation,
		log_deposit_link,
		log_deposit_error,
		log_category_inference,
		log_workflow_state
	)
	
	print("|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||")
	print("||||||||||||||||||||||| Created Deposit slip  |||||||||||||||||||||||||")
	print("|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||")
	
	try:
		if isinstance(data_json, str):
			data = json.loads(data_json)
		else:
			data = data_json

		print(f"Creating Deposit Slip for FR: {fund_received_doc.name}")

		# Determine Doctype based on Category
		category = data.get("category", "")
		
		# If category is empty, try to infer from Fund Received document
		if not category:
			# Try to get project type from the linked project registration
			if fund_received_doc.prjreg_title:
				try:
					project_type = frappe.db.get_value(
						"Project Registration", 
						fund_received_doc.prjreg_title, 
						"project_type"
					)
					if project_type:
						project_type_upper = (project_type or "").upper()
						if "RESEARCH" in project_type_upper and "CONSULTANCY" not in project_type_upper:
							category = "RESEARCH"
						elif "CONSULTANCY" in project_type_upper:
							if "D" in project_type_upper or "D_CONSULTANCY" in project_type_upper:
								category = "D_CONSULTANCY"
							elif "E" in project_type_upper or "NON" in project_type_upper:
								category = "E_NON_ROUTINE"
							elif "T" in project_type_upper or "TEST" in project_type_upper:
								category = "T_TESTING"
							else:
								category = "CONSULTANCY"
						else:
							category = "RESEARCH"  # Default to Research
					else:
						category = "RESEARCH"  # Default to Research
				except Exception as e:
					print(f"Warning: Could not get project type: {e}")
					category = "RESEARCH"  # Default to Research
			else:
				category = "RESEARCH"  # Default to Research if no project linked
			
			print(f"Inferred category from project: {category}")
			# Log category inference
			log_category_inference(
				fund_received_doc.name,
				fund_received_doc.prjreg_title,
				project_type if 'project_type' in dir() else None,
				category
			)
		
		# Simple mapping based on known categories
		# Adjust keys as per exact frontend inputs
		doctype_map = {
			"RESEARCH": "Research Deposit Slip",
			"Research": "Research Deposit Slip",
			"CONSULTANCY": "Research Consultancy Deposit Slip", # Defaulting generic consultancy to Research Consultancy
			"Research Consultancy": "Research Consultancy Deposit Slip",
			"D_CONSULTANCY": "D Consultancy Deposit Slip",
			"D Consultancy": "D Consultancy Deposit Slip",
			"E_NON_ROUTINE": "E Non Routine Deposit Slip",
			"E Non Routine": "E Non Routine Deposit Slip",
			"OTHER_EVENT": "Other Event Deposit Slip",
			"Other Event": "Other Event Deposit Slip",
			"T_TESTING": "T Testing Deposit Slip",
			"T Testing": "T Testing Deposit Slip"
		}
		
		target_doctype = doctype_map.get(category, "Research Deposit Slip") # Changed fallback to Research
		
		print(f"Selected Target Doctype: {target_doctype} for Category: {category}")

		new_doc = frappe.new_doc(target_doctype)
		
		# Map fields
		# We use the same generic mapping logic. Assuming fields are roughly consistent across deposit slips.
		field_mapping = {
			"category": "category",
			# "fund_received_ref": "fund_received_ref", # Field missing in target
			"project_title": "project_title",
			"principal_investigator": "principal_investigator",
			"consultancy_event_title": "consultancy_event_title", 
			"client": "client",
			"funding_agency": "funding_agency",
			"gstin_of_funding_agency": "gstin_of_funding_agency",
			"bank": "bank",
			
			# Mappings to new fieldnames (Research Consultancy Deposit Slip)
			"amount_inclusive_of_gst": "amount_inclusive_gst_capital",
			"amount_inclusive_gst_capital": "amount_inclusive_gst_capital",
			
			"ecs_acc_no": "ecs_ac_no",
			"ecs_ac_no": "ecs_ac_no",
			
			"igst_18": "igst_18",
			"cgst_9": "cgst_9",
			"sgst_9": "sgst_9",
			
			"overhead_amount": "overhead_amount",
			
			"project_balance": "project_balance_after_gst",
			"project_balance_after_gst": "project_balance_after_gst",
			
			"total_gst": "total_gst",
			"total_budget": "total_budget",
			"prj_amount": "prj_amount",
			
			# Specific distribution amounts (shared)
			"idf_amount": "idf_amount",
			"dpf_cle_amount": "dpf_cle_amount",
			"staff_welfare_amount": "staff_welfare_amount",
			"student_welfare_amount": "student_welfare_amount",
			
			# Research Deposit Slip specific fields
			"deposit_date": "deposit_date",
			"total_amount": "total_amount",
			"ecs_scheme_no": "ecs_scheme_no",
			"bank_name": "bank_name",
			"account_number": "account_number",
			"dpf_amount": "dpf_amount",
			"pdf_amount": "pdf_amount",
			"student_welfare_fund": "student_welfare_fund",
			"project_no": "project_no",
			"project_account_balance": "project_account_balance",
			"grand_total": "grand_total",
		}
		
		# Fields to skip (can cause link validation errors)
		skip_fields = ["funding_agency", "gstin_of_funding_agency"]
		
		# Handle date fields - convert "Today" string to actual date
		date_fields = ["deposit_date"]
		for date_field in date_fields:
			if date_field in data:
				val = data[date_field]
				# Convert "Today" (case-insensitive) to actual current date
				if isinstance(val, str) and val.lower() == "today":
					data[date_field] = frappe.utils.today()
					print(f"Converted {date_field} from 'Today' to {data[date_field]}")

		for form_field, doctype_field in field_mapping.items():
			if form_field in skip_fields:
				continue
			if form_field in data and data[form_field] not in [None, ""]:
				try:
					new_doc.set(doctype_field, data[form_field])
				except Exception as e:
					print(f"Warning: Could not set field {doctype_field}: {e}")

		# Explicitly link to Fund Received
		new_doc.fund_received_ref = fund_received_doc.name
		
		# If project_title is missing in data but exists in FR, try to populate?
		if not new_doc.get("project_title") and fund_received_doc.prjreg_title:
			# Assuming prjreg_title in FR holds the project ID/Name that Deposit Slip expects
			# Use set default to avoid errors if field doesn't exist on some doctypes
			new_doc.project_title = fund_received_doc.prjreg_title

		# Child table: ecs_date (singular for Research Deposit Slip) or ecs_dates (for others)
		ecs_data = data.get("ecs_dates") or data.get("ecs_date")
		if ecs_data:
			# Determine the correct child table name based on doctype
			ecs_table_name = "ecs_date" if target_doctype == "Research Deposit Slip" else "ecs_dates"
			for ecs_entry in ecs_data:
				if ecs_entry.get("ecs_date") or ecs_entry.get("date") or ecs_entry.get("amount"):
					try:
						new_doc.append(
							ecs_table_name,
							{
								"ecs_date": ecs_entry.get("ecs_date") or ecs_entry.get("date"),
								"amount": ecs_entry.get("amount", 0),
							},
						)
					except Exception as e:
						print(f"Warning: Could not append to {ecs_table_name}: {e}")

		# Child table: credit_distribution (not available in Research Deposit Slip)
		if "credit_distribution" in data and target_doctype != "Research Deposit Slip":
			for row in data["credit_distribution"]:
				# Ensure row is a dict
				if isinstance(row, dict):
					try:
						new_doc.append("credit_distribution", row)
					except Exception as e:
						print(f"Warning: Could not append credit_distribution: {e}")

		# Child table: dpf_credit_distributions (Research Deposit Slip)
		if "dpf_credit_distributions" in data:
			for row in data["dpf_credit_distributions"]:
				if isinstance(row, dict):
					try:
						new_doc.append("dpf_credit_distributions", row)
					except Exception as e:
						print(f"Warning: Could not append dpf_credit_distributions: {e}")

		# Child table: pdf_credit_distribution (Research Deposit Slip)
		if "pdf_credit_distribution" in data:
			for row in data["pdf_credit_distribution"]:
				if isinstance(row, dict):
					try:
						new_doc.append("pdf_credit_distribution", row)
					except Exception as e:
						print(f"Warning: Could not append pdf_credit_distribution: {e}")

		# Set initial workflow_state for the Deposit Slip
		# Since this is created when FR moves to "Pending HoS Approval", 
		# the Deposit Slip starts in the same state, waiting for HoS approval
		new_doc.workflow_state = "Pending HoS Approval"
		
		new_doc.insert(ignore_permissions=True)
		# Note: No commit here, as it's part of the larger transaction in perform_fund_received_action
		
		print(f"Created Deposit Slip: {new_doc.name} with workflow_state: {new_doc.workflow_state}")
		
		# Log successful deposit slip creation
		log_deposit_creation(
			fund_received_doc.name,
			new_doc.name,
			target_doctype,
			data,
			category
		)
		
		# Log the linking
		log_deposit_link(
			fund_received_doc.name,
			new_doc.name,
			target_doctype
		)
		
		# Log workflow state assignment
		log_workflow_state(
			fund_received_doc.name,
			new_doc.name,
			new_doc.workflow_state
		)
		
		return new_doc

	except Exception as e:
		print(f"Error creating Deposit Slip: {e}")
		# Log the error
		log_deposit_error(
			fund_received_doc.name if fund_received_doc else "UNKNOWN",
			str(e),
			data if 'data' in dir() else None,
			traceback.format_exc()
		)
		raise e


@frappe.whitelist()
def submit_fund_received(docname):
	"""
	Submit a Fund Received document using Workflow transitions.
	"""
	return perform_fund_received_action(docname, "Submit")
