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
from rndopsapp.rndopsapp.kafka.utils import record_publish_state
from rndopsapp.rndopsapp.kafka.config import TOPIC_FUND_RECEIVED
from rndopsapp.rndopsapp.doctype.project_registration.project_registration import notify_mattermost


class FundReceived(Document):
	def validate(self):
		"""Validate and auto-populate sanction letter details from linked Fund Sanction"""
		self.populate_project_title_from_sanction()
		self.populate_sanction_details()

	def populate_project_title_from_sanction(self):
		"""
		Fallback: if prjreg_title is empty, resolve it from the Fund Sanction
		linked via sanction_ref_no (Fund Sanction.project_proposal is the
		Project Registration link).
		"""
		if getattr(self, 'prjreg_title', None):
			return

		sanction_name = getattr(self, 'sanction_ref_no', None)
		if not sanction_name:
			return

		try:
			project_proposal = frappe.db.get_value("Fund Sanction", sanction_name, "project_proposal")
			if project_proposal:
				self.prjreg_title = project_proposal
				print(f"✅ Resolved prjreg_title '{project_proposal}' for {self.name} via sanction_ref_no '{sanction_name}'")
		except Exception as e:
			frappe.log_error(f"Error resolving prjreg_title from sanction_ref_no for Fund Received: {e}", "Fund Received Validate Error")

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



@frappe.whitelist()
def get_fund_received_by_prjreg(prjreg_title: str = "", limit: int = 190000000, start: int = 0):
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
def save_fund_received(doc_data, prjreg_title=None, project_reg=None):
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

		# ── MinIO upload: main document_upload field ──────────────────────────────
		if data.get("document_upload_data") and data.get("document_upload_name"):
			try:
				from rndopsapp.minio import get_rnd_file_service

				file_data_uri = data["document_upload_data"]
				if file_data_uri.startswith("data:"):
					file_data_uri = file_data_uri.split(",", 1)[1]
				file_bytes = base64.b64decode(file_data_uri)

				upload_result = get_rnd_file_service().save_file(
					filename=data["document_upload_name"],
					content=file_bytes,
					is_private=True,
					doctype="Project Registration",
					docname=project_reg or new_doc.prjreg_title,
					folder="fund_received",
				)

				if upload_result.get("status"):
					new_doc.document_upload = upload_result.get("data", {}).get("file_url")
					print(f"✅ document_upload uploaded to MinIO: {new_doc.document_upload}")
				else:
					frappe.log_error(
						f"MinIO upload failed for document_upload: {upload_result.get('message')}",
						"Fund Received Document Upload"
					)
			except Exception as _upload_err:
				frappe.log_error(frappe.get_traceback(), "Fund Received Document Upload Error")
				print(f"❌ document_upload MinIO error: {_upload_err}")
		# ─────────────────────────────────────────────────────────────────────────

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
						# Save the file to MinIO
						from rndopsapp.minio import get_rnd_file_service
						import base64
						
						file_data_uri = transaction.get("file_data")
						if file_data_uri.startswith("data:"):
							file_data_uri = file_data_uri.split(",", 1)[1]
						file_bytes = base64.b64decode(file_data_uri)
						
						upload_result = get_rnd_file_service().save_file(
							filename=transaction.get("file_name"),
							content=file_bytes,
							is_private=True,
							doctype="Project Registration",
							docname=project_reg or new_doc.prjreg_title,
							folder="fundreceived"
						)
						
						if upload_result.get("status"):
							attachment_data["attachment"] = upload_result.get("data", {}).get("file_url")
						else:
							frappe.log_error(f"File upload failed: {upload_result.get('message')}", "Fund Received File Upload")

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
		url = "http://172.16.134.81:18080/api/fund-received/addFundReceived"
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

	# Pending Rectification / Pending Reconciliation / Rejected are entered
	# only by the Kafka consumer writing workflow_state directly — they have
	# no real "Put Back" Workflow Transition of their own for the loop above
	# to find. put_back_action.py's generic tool can still resolve a target
	# for them via STATE_ALIASES (aliased to PENDING_APPROVAL). Surface
	# "Put Back" here too, gated to staff, RnD — the same role that owns the
	# real "Forward" transition out of Pending Rectification, so whoever can
	# resubmit can also put back — plus RnD Administration/System Manager as
	# the usual admin override.
	from rndopsapp.rndopsapp.put_back_action import STATE_ALIASES
	if (
		"Put Back" not in allowed_actions
		and ("Fund Received", current_state) in STATE_ALIASES
		and (
			"staff, RnD" in user_roles
			or "RnD Administration" in user_roles
			or "System Manager" in user_roles
		)
	):
		allowed_actions.append("Put Back")

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_fund_received_action(docname, action, deposit_slip_data=None, deposit_slip_type=None):
	"""
	Executes the selected workflow action and updates the document state.

	Args:
		docname (str): Name of the Fund Received document.
		action (str): Workflow action to perform.
		deposit_slip_data (json/dict, optional): Data to create a new Deposit Slip
												 if transitioning to HoS Approval.
		deposit_slip_type (str, optional): Explicit deposit slip type from frontend
										   (e.g. 'e_non_routine', 'research', 'd_consultancy').
										   Takes priority over project-type inference.
	"""
	try:
		print("=========================================================================")
		print("DEBUG: perform_fund_received_action called for deposit_slip_data=======>>>>>: ", deposit_slip_data)
		print("=========================================================================")
		doc = frappe.get_doc("Fund Received", docname)
		current_state = doc.workflow_state or "Draft"

		# FIX: Ensure doc has a workflow_state in DB to avoid WorkflowStateError on first save
		if not doc.workflow_state:
			doc.db_set("workflow_state", current_state, update_modified=False)
			doc.workflow_state = current_state

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
		elif not doc.prjreg_title and doc.sanction_ref_no:
			# prjreg_title is empty - resolve via the linked Fund Sanction's project_proposal
			project_proposal = frappe.db.get_value("Fund Sanction", doc.sanction_ref_no, "project_proposal")
			if project_proposal:
				print(f"DEBUG: prjreg_title empty. Resolved '{project_proposal}' via sanction_ref_no '{doc.sanction_ref_no}'.")
				doc.prjreg_title = project_proposal
			else:
				print(f"DEBUG: prjreg_title empty and could not resolve via sanction_ref_no '{doc.sanction_ref_no}'.")


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
		
		# "Put Back" from a Kafka-consumer-only state (Pending Rectification /
		# Pending Reconciliation / Rejected) has no real Workflow Transition row
		# to match below — see get_fund_received_workflow_actions, which surfaces
		# this same action via put_back_action.py's STATE_ALIASES instead. Route
		# it through that generic bypass tool here too, short-circuiting before
		# any of the forward-transition side effects (deposit slip creation,
		# docstatus submit, Kafka publish) that don't apply to a backward move.
		from rndopsapp.rndopsapp.put_back_action import STATE_ALIASES, get_put_back_document_states, set_put_back_workflow_state
		if action == "Put Back" and ("Fund Received", current_state) in STATE_ALIASES:
			user_roles = frappe.get_roles(frappe.session.user)
			# Same role set as the fallback in get_fund_received_workflow_actions
			# above — staff, RnD (owns the real "Forward" out of this state) plus
			# the usual admin override roles.
			if not (
				"staff, RnD" in user_roles
				or "RnD Administration" in user_roles
				or "System Manager" in user_roles
			):
				frappe.throw("You are not permitted to Put Back from this state.", frappe.PermissionError)

			put_back = get_put_back_document_states("Fund Received", docname)
			target_states = put_back.get("states") or []
			if put_back.get("status") != "success" or not target_states:
				frappe.throw(f"No Put Back target available from state '{current_state}'.")

			result = set_put_back_workflow_state(
				"Fund Received", docname, target_states[0], frappe.session.user,
				comment=f"Put Back from {current_state} (via Fund Received workflow actions)",
			)
			if result.get("status") != "success":
				frappe.throw(result.get("message") or "Put Back failed.")

			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Action 'Put Back' completed. New State: {target_states[0]}",
				"docname": docname,
				"workflow_state": target_states[0],
				"next_actions": get_fund_received_workflow_actions(docname),
			}

		# Find all transitions matching current state and action.
		# Multiple rows may exist for the same (state, action) when different roles
		# are each given their own row — but they all target the same next_state.
		# Always pick the first match.
		candidates = [
			t for t in workflow.transitions
			if t.state == current_state and t.action == action
		]

		if not candidates:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		transition = candidates[0]
		print(f"DEBUG: Selected transition: {transition.state} --[{transition.action}]--> {transition.next_state}")

		next_state = transition.next_state

		# --- SIDE EFFECTS BEFORE STATE CHANGE ---

		# 1. Create Deposit Slip if transitioning to 'Pending HoS Approval'
		# Relaxed check: Only care if we are moving TO HoS Approval
		if next_state == "Pending HoS Approval": 
			print(f"DEBUG: Transitioning to HoS Approval. Data present: {bool(deposit_slip_data)}")
			if deposit_slip_data:
				create_deposit_slip_from_data(deposit_slip_data, doc, deposit_slip_type=deposit_slip_type)
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

		try:
			if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
				doc.submit()
			elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
				doc.cancel()
			else:
				doc.save(ignore_permissions=True)
		except Exception as save_err:
			# Save/submit failure must NOT block the workflow state commit.
			# The deposit slip creation (if any) is already in this transaction;
			# we still want to commit the state change so the FR doesn't revert.
			print(f"DEBUG: doc save/submit failed (non-fatal, continuing to commit state): {save_err}")
			frappe.log_error(frappe.get_traceback(), "Fund Received Save/Submit Error (non-fatal)")

		# Force-write state directly in DB — survives even if save/submit above failed
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
				import datetime
				record_publish_state(
					"Fund Received", doc.name, TOPIC_FUND_RECEIVED,
					current_state, next_state,
				)
				success = publish_fund_received(doc)
				if success:
					frappe.msgprint(_("Fund Received data synced to Kafka successfully."), indicator='green')
					notify_mattermost(
						"```\n"
						"┌──────────────────────────────────────────────┐\n"
						"│  📡 [Kafka Publish] Fund Received SUCCESS      │\n"
						"├──────────────────────────────────────────────┤\n"
						f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
						f" Docname  : {doc.name}\n"
						f" State    : {next_state}\n"
						f" User     : {frappe.session.user}\n"
						"└──────────────────────────────────────────────┘\n"
						"```"
					)
				else:
					frappe.msgprint(_("Kafka sync returned False."), indicator='orange')
					notify_mattermost(
						"```\n"
						"┌──────────────────────────────────────────────┐\n"
						"│  ⚠️ [Kafka Publish] Fund Received FAILED       │\n"
						"├──────────────────────────────────────────────┤\n"
						f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
						f" Docname  : {doc.name}\n"
						f" State    : {next_state}\n"
						f" User     : {frappe.session.user}\n"
						"└──────────────────────────────────────────────┘\n"
						"```",
						urgent=True,
					)
			except Exception as k_err:
				import datetime
				print(f"Kafka sync error: {k_err}")
				frappe.log_error(frappe.get_traceback(), "Fund Received Workflow Kafka Sync Error")
				frappe.msgprint(_("Failed to sync with Kafka: {}").format(str(k_err)), indicator='red')
				notify_mattermost(
					"```\n"
					"┌──────────────────────────────────────────────┐\n"
					"│  🔴 [ERROR] Fund Received Kafka Sync           │\n"
					"├──────────────────────────────────────────────┤\n"
					f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
					f" Docname  : {docname}\n"
					f" Action   : {action}\n"
					f" User     : {frappe.session.user}\n"
					f" Error    : {str(k_err)}\n"
					"└──────────────────────────────────────────────┘\n"
					"```",
					urgent=True,
				)

		# 3. When Fund Received is Approved by HoS -> Auto-Approve Deposit Slip & Sync to Kafka
		if next_state == "Approved":
			try:
				import datetime
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

				# Find linked Deposit Slip in any of the potential doctypes.
				# Prefer the one currently waiting for HoS approval (the active DS);
				# multiple deposit slips can exist when the misc staff regenerated
				# after a HoS put-back.  Fall back to the most recently created DS if
				# none is found in "Pending HoS Approval" state.
				ds_name = None
				found_doctype = None

				for dt in deposit_doctypes:
					# First pass: find the active DS waiting for HoS
					# Some deposit slip doctypes have no workflow (no workflow_state column);
					# skip them gracefully — they can never be in "Pending HoS Approval".
					try:
						name = frappe.db.get_value(
							dt,
							{"fund_received_ref": doc.name, "workflow_state": "Pending HoS Approval"},
							"name",
							order_by="creation desc",
						)
					except Exception:
						name = None
					if name:
						ds_name = name
						found_doctype = dt
						break

				if not ds_name:
					# Second pass: fall back to most recently created DS for this FR
					for dt in deposit_doctypes:
						name = frappe.db.get_value(
							dt,
							{"fund_received_ref": doc.name},
							"name",
							order_by="creation desc",
						)
						if name:
							ds_name = name
							found_doctype = dt
							break

				if ds_name and found_doctype:
					print(f"DEBUG: Found linked Deposit Slip {ds_name} of type {found_doctype}. Auto-approving and Syncing...")
					ds_doc = frappe.get_doc(found_doctype, ds_name)

					current_ds_state = ds_doc.get("workflow_state") or ""
					print(f"DEBUG: Current Deposit Slip state: '{current_ds_state}'")

					# Update State to Approved if not already
					# skip_kafka_sync flag tells on_update to skip its own publish
					# so we can publish explicitly below with proper error handling
					if current_ds_state != "Approved":
						ds_doc.workflow_state = "Approved"
						ds_doc.flags.ignore_validate = True
						ds_doc.flags.skip_kafka_sync = True
						ds_doc.save(ignore_permissions=True)
						print(f"DEBUG: Deposit Slip {ds_name} state updated to 'Approved'")

					# Submit if not submitted
					if ds_doc.docstatus == 0:
						ds_doc.flags.ignore_validate = True
						ds_doc.flags.skip_kafka_sync = True
						ds_doc.submit()
						print(f"DEBUG: Deposit Slip {ds_name} submitted")

					# --- Explicit Kafka publish with proper success/failure handling ---
					# Use the canonical publisher that handles all 6 deposit slip types
					# with key-based partitioning and structured logging
					kafka_result = False
					kafka_error = None
					try:
						from rndopsapp.rndopsapp.kafka.producer import publish_deposit_slip
						kafka_result = publish_deposit_slip(ds_doc)
					except Exception as kafka_exc:
						kafka_error = str(kafka_exc)
						kafka_result = False
						print(f"DEBUG: Kafka publish exception: {kafka_exc}")
						print(frappe.get_traceback())
						frappe.log_error(frappe.get_traceback(), "Deposit Slip Kafka Publish Error")

					if kafka_result:
						frappe.msgprint(_(f"Linked {found_doctype} Approved and published to Kafka."), indicator='green')
						print(f"DEBUG: Kafka publish SUCCESS for {ds_name}")
						try:
							notify_mattermost(
								"```\n"
								"┌──────────────────────────────────────────────┐\n"
								"│  ✅ [Kafka Publish] Deposit Slip Approved      │\n"
								"├──────────────────────────────────────────────┤\n"
								f" Time        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
								f" Fund Rcvd   : {doc.name}\n"
								f" Deposit Slip: {ds_name}\n"
								f" Type        : {found_doctype}\n"
								f" User        : {frappe.session.user}\n"
								"└──────────────────────────────────────────────┘\n"
								"```"
							)
						except Exception as mm_exc:
							print(f"DEBUG: Mattermost notify failed (success path): {mm_exc}")
					else:
						err_detail = kafka_error or "publish_deposit_slip returned False (check validation errors in Frappe Error Log)"
						frappe.msgprint(_(f"Deposit Slip approved but Kafka publish failed: {err_detail}"), indicator='orange')
						print(f"DEBUG: Kafka publish FAILED for {ds_name}: {err_detail}")
						try:
							notify_mattermost(
								"```\n"
								"┌──────────────────────────────────────────────┐\n"
								"│  ⚠️ [Kafka Publish] Deposit Slip FAILED        │\n"
								"├──────────────────────────────────────────────┤\n"
								f" Time        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
								f" Fund Rcvd   : {doc.name}\n"
								f" Deposit Slip: {ds_name}\n"
								f" Type        : {found_doctype}\n"
								f" User        : {frappe.session.user}\n"
								f" Error       : {err_detail}\n"
								"└──────────────────────────────────────────────┘\n"
								"```",
								urgent=True,
							)
						except Exception as mm_exc:
							print(f"DEBUG: Mattermost notify failed (failure path): {mm_exc}")
				else:
					print("DEBUG: No linked Deposit Slip found.")

				print("|||||||||||||||||||||||KAFKA end|||||||||||||||||||||||||||||||||")
			except Exception as ds_err:
				import datetime
				print(f"DEBUG: Error auto-processing Deposit Slip: {ds_err}")
				print(frappe.get_traceback())
				frappe.log_error(frappe.get_traceback(), "Auto Deposit Slip Sync Error")
				frappe.msgprint(_("Error processing Deposit Slip: {}").format(str(ds_err)), indicator='red')
				# Ensure FR state is committed even if deposit slip processing failed
				try:
					doc.db_set("workflow_state", next_state)
					frappe.db.commit()
				except Exception:
					pass
				try:
					notify_mattermost(
						"```\n"
						"┌──────────────────────────────────────────────┐\n"
						"│  🔴 [ERROR] Deposit Slip Auto-Approve/Kafka    │\n"
						"├──────────────────────────────────────────────┤\n"
						f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
						f" Docname  : {docname}\n"
						f" Action   : {action}\n"
						f" User     : {frappe.session.user}\n"
						f" Error    : {str(ds_err)}\n"
						"└──────────────────────────────────────────────┘\n"
						"```",
						urgent=True,
					)
				except Exception as mm_exc:
					print(f"DEBUG: Mattermost notify failed (error path): {mm_exc}")
		
		print("DEBUG: End of function success")
		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_fund_received_workflow_actions(docname)
		}

	except Exception as e:
		import datetime
		frappe.db.rollback()
		print(f"DEBUG: Exception in perform_fund_received_action: {e}")
		print(frappe.get_traceback())
		frappe.log_error(frappe.get_traceback(), "Fund Received Action Error")
		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  🔴 [ERROR] Fund Received Action Failed        │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Docname  : {docname}\n"
			f" Action   : {action}\n"
			f" User     : {frappe.session.user}\n"
			f" Error    : {str(e)}\n"
			"└──────────────────────────────────────────────┘\n"
			"```",
			urgent=True,
		)
		return {"status": "error", "message": str(e)}


def create_deposit_slip_from_data(data_json, fund_received_doc, deposit_slip_type=None):
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
		# Priority: 1) explicit deposit_slip_type from frontend  2) 'category' key in data
		# 3) category-specific field keys in data  4) project-type inference (last resort)

		# Map from frontend deposit_slip_type values to internal category keys
		_type_to_category = {
			"e_non_routine":        "E_NON_ROUTINE",
			"d_consultancy":        "D_CONSULTANCY",
			"t_testing":            "T_TESTING",
			"other_event":          "OTHER_EVENT",
			"research":             "RESEARCH",
			"research_consultancy": "CONSULTANCY",
		}

		project_type = None  # kept for log_category_inference below

		if deposit_slip_type and deposit_slip_type.lower() in _type_to_category:
			category = _type_to_category[deposit_slip_type.lower()]
			print(f"Category resolved from deposit_slip_type='{deposit_slip_type}': {category}")
		else:
			category = data.get("category", "")

			# Detect category from category-specific field keys when 'category' is absent
			if not category:
				if data.get("category_e"):
					category = "E_NON_ROUTINE"
				elif data.get("category_d"):
					category = "D_CONSULTANCY"

			# Last resort: infer from project_type on the linked Project Registration
			if not category:
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
								category = "RESEARCH"
						else:
							category = "RESEARCH"
					except Exception as e:
						print(f"Warning: Could not get project type: {e}")
						category = "RESEARCH"
				else:
					category = "RESEARCH"

				print(f"Inferred category from project: {category}")
				log_category_inference(
					fund_received_doc.name,
					fund_received_doc.prjreg_title,
					project_type,
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
			# NOTE: falls back to original key when target field missing (e.g. E Non Routine uses amount_inclusive_of_gst)
			"amount_inclusive_of_gst": "amount_inclusive_gst_capital",
			"amount_inclusive_gst_capital": "amount_inclusive_gst_capital",

			"consultancy_fee_x": "consultancy_fee_x",
			
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
			
			# D Consultancy Deposit Slip specific fields
			"consultancy_title": "consultancy_title",
			"principal_consultant": "principal_consultant",
			"igst_18_on_consultancy": "igst_18_on_consultancy",
			"amount_after_gst_tds": "amount_after_gst_tds",
			"total_cost_x": "total_cost_x",
			"consultancy_charge_y": "consultancy_charge_y",
			"operational_charge_z": "operational_charge_z",
			"idf_percentage": "idf_percentage",
			"iitg_invoice_no": "iitg_invoice_no",

			# Other Event Deposit Slip specific fields
			"event_title": "event_title",
			"principal_organizer": "principal_organizer",
			"gstin_no": "gstin_no",
			"gst_multiplier": "gst_multiplier",
			"gst_amount": "gst_amount",
			"training_fee": "training_fee",
			"gst_final": "gst_final",
			"total": "total",

			# T Testing Deposit Slip specific fields
			"idf_t_testing_fee": "idf_t_testing_fee",
			"dpf_t_testing_fee": "dpf_t_testing_fee",
			"staff_welfare_t_testing_fund": "staff_welfare_t_testing_fund",
			"student_welfare_t_testing_fund": "student_welfare_t_testing_fund",

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
			"staff_welfare_fund_percent": "staff_welfare_fund_percent",
			"student_welfare_fund_percent": "student_welfare_fund_percent",

			# Research Consultancy Deposit Slip specific fields
			"project_number": "project_number",
		}
		
		# Fields to skip (funding_agency is a Link field — validated separately below)
		skip_fields = ["funding_agency"]
		
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
					# If the mapped target field doesn't exist on this doctype, fall back to the original key name
					actual_field = doctype_field
					if (doctype_field != form_field
							and not new_doc.meta.has_field(doctype_field)
							and new_doc.meta.has_field(form_field)):
						actual_field = form_field
					new_doc.set(actual_field, data[form_field])
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

		# Resolve funding_agency: the value may be initials (e.g. "DST") instead of actual fundingagency_ name
		fa_value = new_doc.get("funding_agency")
		if fa_value and not frappe.db.exists("fundingagency_", fa_value):
			# Try to resolve from initials
			actual_fa = frappe.db.get_value("fundingagency_", {"funding_agency_initials": fa_value}, "name")
			new_doc.set("funding_agency", actual_fa)  # None if not found

		# Also resolve funding_agency from the Fund Received's project if still not set
		if not new_doc.get("funding_agency") and fund_received_doc.get("prjreg_title"):
			fa_name = frappe.db.get_value("Project Registration", fund_received_doc.prjreg_title, "funding_agen")
			if fa_name and frappe.db.exists("fundingagency_", fa_name):
				new_doc.set("funding_agency", fa_name)

		new_doc.insert(ignore_permissions=True)
		# Note: No commit here, as it's part of the larger transaction in perform_fund_received_action

		# Force-advance the Fund Received to "Pending HoS Approval" the moment the Deposit
		# Slip actually exists, using the same atomic conditional-UPDATE pattern as the Kafka
		# consumer (never move backward). This is deliberately NOT left to the caller's later
		# doc.save()/db_set: a concurrent stale request (e.g. a lagging "Approve" call reading
		# workflow_state before this transition landed) can otherwise win the race and blindly
		# db_set the Fund Received back to an earlier state after we've already created the
		# slip here — see incident on REC_3107262287-prjreg_refnum (2026-07-31), where exactly
		# that race left the Fund Received stuck one step behind its Deposit Slip.
		_state_priority = {
			'Draft':                                                 0,
			'Pending Misc. Staff Approval':                          1,
			'PENDING_APPROVAL':                                      2,
			'Pending Rectification':                                 2,
			'Pending Reconciliation':                                2,
			'Rejected':                                               2,
			'Pending Misc. Staff Approval(Deposit Slip Pending)':    3,
			'Pending HoS Approval':                                  4,
			'Approved':                                              5,
			'Fund Received':                                         6,
		}
		_target_state = "Pending HoS Approval"
		_allowed_from = [s for s, p in _state_priority.items() if p <= _state_priority[_target_state]]
		_placeholders = ', '.join(['%s'] * len(_allowed_from))
		frappe.db.sql(
			f"""
			UPDATE `tabFund Received`
			SET workflow_state = %s, modified = NOW()
			WHERE name = %s AND workflow_state IN ({_placeholders})
			""",
			[_target_state, fund_received_doc.name] + _allowed_from,
		)
		# Only sync the one field the UPDATE above may have changed — a full reload()
		# would also discard any other in-memory fix-ups the caller made on this doc
		# (e.g. the prjreg_title correction in perform_fund_received_action) before
		# handing it to us, since those haven't been saved yet at this point.
		fund_received_doc.workflow_state = frappe.db.get_value(
			"Fund Received", fund_received_doc.name, "workflow_state"
		)

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
def submit_fund_received(docname=None, save=None, doc_data=None, prjreg_title=None, project_reg=None, project_no=None):
	"""
	Submit a Fund Received document using Workflow transitions.
	If save is True, it first saves the document using the provided data.
	"""
	if save in [True, "true", "True", "1", 1]:
		if not doc_data:
			frappe.throw("doc_data is required when save=True")
		res = save_fund_received(doc_data, prjreg_title, project_reg)
		if isinstance(res, dict) and res.get("status") == "success":
			docname = res.get("docname")
		else:
			return res

	if not docname:
		frappe.throw("Document name is required to submit.")

	return perform_fund_received_action(docname, "Submit")


# ── OJS EDIT START ──────────────────────────────────────────────────────────
# Author      : OJS
# Date        : 2026-06-01
# Time        : 15:29 IST
# Description : New endpoint – update_fund_received
#               Updates an existing Fund Received document.
#               Accepts: bank_account, fund_transactions (with per-row file
#               upload to MinIO), received_amt_breakup, and an optional new
#               document_upload file. All file uploads follow the same MinIO
#               path convention as save_fund_received.
# ────────────────────────────────────────────────────────────────────────────
@frappe.whitelist()
def update_fund_received(docname, doc_data, project_reg=None):
	"""
	Update fields on an existing Fund Received document.

	Expected ``doc_data`` JSON keys (all optional – only supplied keys are
	updated):

	Scalar fields
	─────────────
	  bank_account            – Bank Account Number / Scheme
	  fund_received_amt       – Total fund received amount
	  gst_invoice_issued      – Yes / No
	  invoice_no              – Invoice number (when GST is issued)
	  sanction_ref_no         – Sanction reference number

	Main document file
	──────────────────
	  document_upload_name    – Filename for the supporting document
	  document_upload_data    – Base-64 encoded file content (data-URI ok)

	Sanction Transaction Details  (fund_transactions child table)
	──────────────────────────────────────────────────────────────
	  fund_transactions : list of dicts, each with:
	    transaction_number    – UTR / Grant transaction number (required)
	    transaction_date      – Date string (YYYY-MM-DD)
	    amount                – Amount (₹)
	    file_name             – (optional) filename for row attachment
	    file_data             – (optional) base-64 content for row attachment

	  When provided the ENTIRE child table is replaced (same as save logic).

	Budget Breakup of the Received Amount  (received_amt_breakup child table)
	─────────────────────────────────────────────────────────────────────────
	  received_amt_breakup : list of dicts, each with:
	    account_head          – Budget Head label or doc name
	    amount_received       – Amount (₹)
	    budget_year_funds_receive – (optional, default 1)
	    remarks               – (optional)

	  When provided the ENTIRE child table is replaced.

	Returns
	───────
	  {"status": "success", "docname": "<name>"}  on success.
	  Raises on error.
	"""
	try:
		# ── 1. Parse incoming data ────────────────────────────────────────────
		if isinstance(doc_data, str):
			data = json.loads(doc_data)
		else:
			data = doc_data

		print(f"[update_fund_received] docname={docname}, keys={list(data.keys())}")

		# ── 2. Load the existing document ────────────────────────────────────
		if not frappe.db.exists("Fund Received", docname):
			frappe.throw(f"Fund Received '{docname}' not found.")

		doc = frappe.get_doc("Fund Received", docname)

		# ── 3. Update scalar fields (only if supplied in payload) ─────────────
		scalar_fields = [
			"bank_account",
			"fund_received_amt",
			"gst_invoice_issued",
			"invoice_no",
			"sanction_ref_no",
			"prjreg_title",
		]
		for field in scalar_fields:
			if field in data and data[field] not in [None, ""]:
				doc.set(field, data[field])

		# ── 4. Handle main document_upload file → MinIO ───────────────────────
		if data.get("document_upload_name") and data.get("document_upload_data"):
			try:
				from rndopsapp.minio import get_rnd_file_service

				file_data_uri = data["document_upload_data"]
				if file_data_uri.startswith("data:"):
					file_data_uri = file_data_uri.split(",", 1)[1]
				file_bytes = base64.b64decode(file_data_uri)

				upload_result = get_rnd_file_service().save_file(
					filename=data["document_upload_name"],
					content=file_bytes,
					is_private=True,
					doctype="Project Registration",
					docname=project_reg or doc.prjreg_title,
					folder="fund_received",
				)

				if upload_result.get("status"):
					doc.document_upload = upload_result.get("data", {}).get("file_url")
					print(f"✅ document_upload updated in MinIO: {doc.document_upload}")
				else:
					frappe.log_error(
						f"MinIO upload failed for document_upload (update): {upload_result.get('message')}",
						"Fund Received Update – Document Upload",
					)
			except Exception as _upload_err:
				frappe.log_error(frappe.get_traceback(), "Fund Received Update – Document Upload Error")
				print(f"❌ document_upload MinIO error (update): {_upload_err}")

		# ── 5. Replace fund_transactions child table (Sanction Txn Details) ───
		if "fund_transactions" in data:
			# Build Budget Head lookup (needed for resolving account_head labels)
			doc.set("fund_transactions", [])  # clear existing rows

			for transaction in data["fund_transactions"]:
				# Skip completely empty rows
				if (
					transaction.get("transaction_number") in [None, ""]
					and transaction.get("amount", 0) == 0
				):
					continue

				attachment_url = None

				# Upload per-row attachment to MinIO if provided
				if transaction.get("file_data") and transaction.get("file_name"):
					try:
						from rndopsapp.minio import get_rnd_file_service

						file_data_uri = transaction["file_data"]
						if file_data_uri.startswith("data:"):
							file_data_uri = file_data_uri.split(",", 1)[1]
						file_bytes = base64.b64decode(file_data_uri)

						upload_result = get_rnd_file_service().save_file(
							filename=transaction["file_name"],
							content=file_bytes,
							is_private=True,
							doctype="Project Registration",
							docname=project_reg or doc.prjreg_title,
							folder="fundreceived",
						)

						if upload_result.get("status"):
							attachment_url = upload_result.get("data", {}).get("file_url")
							print(f"✅ fund_transactions row file uploaded: {attachment_url}")
						else:
							frappe.log_error(
								f"MinIO upload failed for transaction row: {upload_result.get('message')}",
								"Fund Received Update – Transaction File Upload",
							)
					except Exception as _trx_err:
						frappe.log_error(
							frappe.get_traceback(),
							"Fund Received Update – Transaction File Upload Error",
						)
						print(f"❌ Transaction row MinIO error: {_trx_err}")

				row_data = {
					"transaction_number": transaction.get("transaction_number") or "",
					"transaction_date": transaction.get("transaction_date"),
					"amount": transaction.get("amount", 0),
				}
				if attachment_url:
					row_data["attachment"] = attachment_url

				doc.append("fund_transactions", row_data)

		# ── 6. Replace received_amt_breakup child table (Budget Breakup) ──────
		if "received_amt_breakup" in data:
			# Build Budget Head label → name lookup
			try:
				budget_heads = frappe.get_all("Budget Head", fields=["name", "budget_head"])
				bh_label_to_name = {b.budget_head: b.name for b in budget_heads}
			except Exception as _bh_err:
				print(f"DEBUG: Error fetching Budget Head lookup (update): {_bh_err}")
				bh_label_to_name = {}

			doc.set("received_amt_breakup", [])  # clear existing rows

			for breakup in data["received_amt_breakup"]:
				if (
					breakup.get("account_head") in [None, ""]
					and breakup.get("amount_received", 0) == 0
				):
					continue

				raw_account_head = breakup.get("account_head") or ""

				# Resolve label to Budget Head document name (same logic as save)
				account_head_name = raw_account_head
				if raw_account_head in bh_label_to_name:
					account_head_name = bh_label_to_name[raw_account_head]
					print(f"DEBUG (update): Resolved account_head '{raw_account_head}' → '{account_head_name}'")
				else:
					for label, name in bh_label_to_name.items():
						if label.lower() == raw_account_head.lower():
							account_head_name = name
							print(
								f"DEBUG (update): Case-insensitive match '{raw_account_head}' → '{account_head_name}'"
							)
							break

				doc.append(
					"received_amt_breakup",
					{
						"account_head": account_head_name,
						"amount_received": breakup.get("amount_received", 0),
						"budget_year_funds_receive": breakup.get("budget_year_funds_receive", 1),
						"remarks": breakup.get("remarks") or "",
					},
				)

		# ── 7. Save and commit ────────────────────────────────────────────────
		# Preserve workflow_state across the save — Frappe may otherwise reset it
		# when override_status is active and docstatus/workflow_state are out of sync.
		current_workflow_state = doc.workflow_state
		doc.flags.ignore_validate = False
		doc.save(ignore_permissions=True)
		# Re-apply the state in case Frappe reset it during save
		if doc.workflow_state != current_workflow_state:
			doc.db_set("workflow_state", current_workflow_state)
		frappe.db.commit()

		print(f"[update_fund_received] Successfully updated: {doc.name}")
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Fund Received Update Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to update Fund Received: {str(e)}")
# ── OJS EDIT END ─────────────────────────────────────────────────────────────
