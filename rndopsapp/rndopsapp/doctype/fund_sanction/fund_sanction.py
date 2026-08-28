# # # Copyright (c) 2025, rndops and contributors
# # # For license information, please see license.txt

import base64
import datetime

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt
from rndopsapp.file_handler import get_file_category_for_doctype
from rndopsapp.minio import get_rnd_file_service
from rndopsapp.rndopsapp.doctype.project_registration.project_registration import notify_mattermost
from rndopsapp.rndopsapp.kafka.producer import publish_fund_sanction as publish_sanction
from rndopsapp.rndopsapp.kafka.utils import record_publish_state
from rndopsapp.rndopsapp.kafka.config import TOPIC_SANCTION
from rndopsapp.static_config import ACCOUNT_PORTAL_SANCTION_DETAILS

# from frappe.workflow.doctype.workflow.workflow import get_workflow_name


class FundSanction(Document):
	def before_save(self):
		self.sync_sanction_workflow_status()

	def before_submit(self):
		self.sync_sanction_workflow_status()

	def before_update_after_submit(self):
		# Workflow transitions on an already-submitted doc (docstatus staying 1) route
		# through this hook instead of before_save — without it, sanction_workflow_status
		# goes stale on every transition after the doc is first submitted.
		self.sync_sanction_workflow_status()

	def sync_sanction_workflow_status(self):
		if self.workflow_state:
			self.sanction_workflow_status = self.workflow_state

	def validate(self):
		self.validate_unique_sanctioned_letter_no()

	def validate_unique_sanctioned_letter_no(self):
		"""Block save if another Fund Sanction already uses this sanctioned_letter_no."""
		if not self.sanctioned_letter_no:
			return
		duplicate = frappe.db.get_value(
			"Fund Sanction",
			{
				"sanctioned_letter_no": self.sanctioned_letter_no,
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if duplicate:
			frappe.throw(
				_(
					"Sanctioned Letter No '{0}' is already used in Fund Sanction {1}. "
					"It must be unique."
				).format(self.sanctioned_letter_no, duplicate),
				title=_("Duplicate Sanctioned Letter No"),
			)


def get_unique_sanctioned_letter_no(letter_no):
	"""Generate a unique sanctioned_letter_no by appending an auto-incrementing
	-SL00001 style suffix until no Fund Sanction uses the candidate."""
	counter = 1
	while True:
		candidate = f"{letter_no}-SL{counter:05d}"
		if not frappe.db.exists("Fund Sanction", {"sanctioned_letter_no": candidate}):
			return candidate
		counter += 1


@frappe.whitelist()
def check_sanctioned_letter_no(sanctioned_letter_no, docname=None):
	"""Realtime duplicate check for sanctioned_letter_no.

	Args:
		sanctioned_letter_no: the value to check.
		docname: optional — current Fund Sanction name, excluded from the
			check so editing a doc doesn't flag itself as a duplicate.

	Returns:
		is_duplicate False  -> the value is free to use.
		is_duplicate True   -> includes the conflicting doc and a unique
			`suggested` value like "LTR123-SL00001" (suffix auto-increments).
	"""
	letter_no = (sanctioned_letter_no or "").strip()
	if not letter_no:
		return {"status": "error", "message": "sanctioned_letter_no is required"}

	filters = {"sanctioned_letter_no": letter_no}
	if docname:
		filters["name"] = ["!=", docname]

	existing = frappe.db.get_value("Fund Sanction", filters, "name")
	if not existing:
		return {
			"status": "success",
			"is_duplicate": False,
			"sanctioned_letter_no": letter_no,
		}

	return {
		"status": "success",
		"is_duplicate": True,
		"existing_doc": existing,
		"suggested": get_unique_sanctioned_letter_no(letter_no),
	}


API_URL = ACCOUNT_PORTAL_SANCTION_DETAILS


def send_sanction_details_to_api(doc):
	"""
	Prepare and send Fund Sanction data to the external API endpoint.
	Uses exact match: Budget Head.budget_head == row.account_head -> fetch numeric id.
	Prints every step to the terminal for debug visibility.
	"""
	print("\n=== SEND SANCTION DETAILS TO API START ===")
	try:
		# Build base payload
		payload = {
			"projectNumber": getattr(doc, "refnum_prj_num", None),
			"sanctionLetterNo": getattr(doc, "sanctioned_letter_no", None),
			"sanctionLetterDate": str(getattr(doc, "sanctioned_letter_date"))
			if getattr(doc, "sanctioned_letter_date", None)
			else None,
			"totalSanctionAmount": flt(getattr(doc, "total_sanctioned_amount", 0) or 0.0),
			# include top-level totals if present on the doc
			"totalFirstYearBudget": flt(getattr(doc, "total_first_year_budget", 0) or 0.0),
			"totalSecondYearBudget": flt(getattr(doc, "total_second_year_budget", 0) or 0.0),
			"totalThirdYearBudget": flt(getattr(doc, "total_third_year_budget", 0) or 0.0),
			"totalFourthYearBudget": flt(getattr(doc, "total_fourth_year_budget", 0) or 0.0),
			"totalFifthYearBudget": flt(getattr(doc, "total_fifth_year_budget", 0) or 0.0),
			"budgetBreakups": [],
		}

		print("[PAYLOAD-BASE]", payload)

		# Build budgetBreakups list using exact match lookups
		print("[STEP] Building budgetBreakups with exact Budget Head.id lookup...")
		for row in getattr(doc, "sanctioned_budget_breakup", []) or []:
			raw_ah = (getattr(row, "account_head", "") or "").strip()
			print(f"   > Processing row idx={getattr(row, 'idx', '<no-idx>')} account_head='{raw_ah}'")

			# Exact match lookup: Budget Head where budget_head == raw_ah
			try:
				account_head_id = frappe.db.get_value("Budget Head", {"budget_head": raw_ah}, "id")
			except Exception as e:
				print(f"     - DB lookup error for '{raw_ah}': {e}")
				account_head_id = None

			# Coerce to int if possible, else keep None
			if account_head_id not in (None, ""):
				try:
					account_head_id = int(account_head_id)
				except Exception:
					# If can't coerce, set None to avoid sending strings
					print(
						f"     - Warning: account_head_id for '{raw_ah}' is not integer: {account_head_id}; setting to None"
					)
					account_head_id = None

			print(f"     - Mapped '{raw_ah}' -> accountHeadId={account_head_id}")

			# Collect per-year budgets (coerce to float via flt)
			first = flt(getattr(row, "first_year_budget", 0) or 0)
			second = flt(getattr(row, "second_year_budget", 0) or 0)
			third = flt(getattr(row, "third_year_budget", 0) or 0)
			fourth = flt(getattr(row, "fourth_year_budget", 0) or 0)
			fifth = flt(getattr(row, "fifth_year_budget", 0) or 0)
			total = first + second + third + fourth + fifth

			bh_payload = {
				"accountHeadId": account_head_id,
				"accountHeadAmount": flt(total),
				"firstYearBudget": flt(first),
				"secondYearBudget": flt(second),
				"thirdYearBudget": flt(third),
				"fourthYearBudget": flt(fourth),
				"fifthYearBudget": flt(fifth),
			}

			payload["budgetBreakups"].append(bh_payload)
			print(f"     - appended budgetBreakup: {bh_payload}")

		print("[FINAL PAYLOAD]", payload)

		# POST to external API
		print("[STEP] Sending POST to API:", API_URL)
		try:
			response = requests.post(API_URL, json=payload, timeout=15)
			print("     - HTTP status:", response.status_code)
			try:
				print("     - response JSON:", response.json())
			except Exception:
				print("     - response text:", response.text)

			if response.status_code == 200:
				frappe.logger().info(f"✅ Sanction details sent successfully: {response.text}")
			else:
				frappe.log_error(
					f"Failed to send sanction details. Status: {response.status_code}, Response: {response.text}",
					"Send Sanction Details API Error",
				)
		except requests.exceptions.RequestException as re:
			print("     - RequestException while posting:", re)
			frappe.log_error(frappe.get_traceback(), "Send Sanction Details RequestException")

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Send Sanction Details Exception")
		print(f"❌ Error preparing/sending sanction details: {e}")
	finally:
		print("=== SEND SANCTION DETAILS TO API END ===\n")


# Whitelisted method to fetch budget details from Project Proposal
@frappe.whitelist()
def get_project_proposal_budget_details(project_proposal_name):
	try:
		if not project_proposal_name:
			frappe.throw("Project Proposal name is required to fetch budget details.")

		project_proposal = frappe.get_doc("Project Proposal", project_proposal_name)

		return {
			"proposed_budget_breakup": project_proposal.get("proposed_budget_breakup", []),
			"total_first_year_budget": project_proposal.total_first_year_budget,
			"total_second_year_budget": project_proposal.total_second_year_budget,
			"total_third_year_budget": project_proposal.total_third_year_budget,
			"total_fourth_year_budget": project_proposal.total_fourth_year_budget,
			"total_fifth_year_budget": project_proposal.total_fifth_year_budget,
			"grand_total_proposal": project_proposal.grand_total_proposal,
			"total_budget_amount": project_proposal.total_budget_amount,  # <-- Added this field
		}

	except frappe.DoesNotExistError:
		frappe.log_error(
			f"Project Proposal {project_proposal_name} not found.", "Fund Sanction Budget Fetch Error"
		)
		frappe.throw(f"Project Proposal '{project_proposal_name}' not found.")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Budget Fetch Error")
		frappe.throw(f"An error occurred while fetching budget details: {e}")



# @frappe.whitelist()
# def save_fund_sanction_data(data):
# 	"""
# 	Save Fund Sanction form data to the backend.
# 	Expects 'data' as a JSON string from frontend.
# 	"""
# 	import json

# 	try:
# 		# Parse JSON string if needed
# 		if isinstance(data, str):
# 			data = json.loads(data)

# 		# Create or update Fund Sanction document
# 		docname = data.get("name")  # If editing an existing doc
# 		if docname:
# 			fs_doc = frappe.get_doc("Fund Sanction", docname)
# 		else:
# 			fs_doc = frappe.new_doc("Fund Sanction")

# 		# Map simple fields
# 		simple_fields = [
# 			"amended_from",
# 			"project_proposal",
# 			"total_sanctioned_amount",
# 			"sanctioned_letter_no",
# 			"sanctioned_letter_date",
# 			"total_first_year_budget_1",
# 			"total_second_year_budget_1",
# 			"total_third_year_budget_1",
# 			"total_fourth_year_budget_1",
# 			"total_fifth_year_budget_1",
# 			"grand_total_proposal_1",
# 			"have_fund_details",
# 			"project_type_linked",
# 			"is_gst_invoice_issued",
# 			"invoice_details",
# 			"amount_received",
# 			"iitg_bank_account_number",
# 		]

# 		for field in simple_fields:
# 			if field in data:
# 				setattr(fs_doc, field, data[field] if data[field] != "null" else None)

# 		# Handle child tables
# 		child_tables = {
# 			"sanctioned_budget_breakup": "Sanctioned Budget Breakup",
# 			"fund_transactions": "Fund Transactions",
# 			"received_amount_breakup": "Received Amount Breakup",
# 		}

# 		for field, child_doctype in child_tables.items():
# 			if field in data:
# 				items = json.loads(data[field]) if isinstance(data[field], str) else data[field]
# 				fs_doc.set(field, [])  # clear existing child table
# 				for item in items:
# 					child = fs_doc.append(field, item)

# 		# Handle file attachments
# 		if "sanction_related_files_meta" in data:
# 			files_meta = json.loads(data["sanction_related_files_meta"])
# 			for fmeta in files_meta:
# 				# If file content comes as file_0, file_1, etc.
# 				file_key = f"file_{files_meta.index(fmeta)}"
# 				file_data = data.get(file_key)
# 				if file_data:
# 					# Save file in Frappe file system
# 					file_doc = frappe.get_doc(
# 						{
# 							"doctype": "File",
# 							"file_name": fmeta.get("description", f"file_{file_key}"),
# 							"attached_to_doctype": "Fund Sanction",
# 							"attached_to_name": fs_doc.name,
# 							"content": file_data,  # file content in base64
# 						}
# 					)
# 					file_doc.insert()

# 		fs_doc.save()
# 		frappe.db.commit()
# 		return {"status": "success", "name": fs_doc.name}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), _("Error saving Fund Sanction"))
# 		return {"status": "error", "message": str(e)}




@frappe.whitelist(allow_guest=True)
def get_fund_sanction_form_data(project_proposal=None):
	import frappe
	from frappe import _

	doctype_name = "Fund Sanction"

	# set to None or [] to fetch ALL doctype fields
	allowed_fieldnames = None

	try:
		meta = frappe.get_meta(doctype_name, cached=False)

		fields = []
		for f in meta.fields:
			if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
				continue

			if allowed_fieldnames and f.fieldname not in allowed_fieldnames:
				continue

			fields.append(
				{
					"fieldname": f.fieldname,
					"label": _(f.label),
					"fieldtype": f.fieldtype,
					"default": f.default,
					"mandatory": bool(f.reqd),
					"read_only": bool(f.read_only),
					"hidden": bool(f.hidden),
					"description": _(f.description) if f.description else None,
					"options": f.options,
				}
			)

		prefill_data = {}
		if project_proposal:
			prefill_data["project_proposal"] = project_proposal
			prefill_data["refnum_prj_num"] = project_proposal

		link_options = {}
		for field in fields:
			if field["fieldtype"] == "Link" and field["options"]:
				try:
					linked_doctype = field["options"]
					title_field = frappe.get_meta(linked_doctype).get_title_field()
					options_list = frappe.get_list(
						linked_doctype,
						fields=["name", title_field],
						limit_page_length=1000,
						ignore_permissions=True,
					)
					link_options[field["fieldname"]] = [
						{"value": d["name"], "label": d.get(title_field, d["name"])} for d in options_list
					]
				except Exception:
					link_options[field["fieldname"]] = []

		return {"fields": fields, "prefill_data": prefill_data, "link_options": link_options}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching fund sanction form data"))
		return {"error": str(e)}



@frappe.whitelist()
def save_fund_sanction_data(files=None, **data):
	"""
	Save Fund Sanction data (parent + child tables), skipping all
	ERPNext link validations and saving only file paths.
	"""
	import json
	import os

	# --- Debug: dump raw incoming payload so we can see what the frontend sends ---
	try:
		_dir = os.path.dirname(__file__)
		_ts = datetime.datetime.now().isoformat()
		with open(os.path.join(_dir, "fund_sanction_save.log"), "a") as _lf:
			_lf.write(f"\n{'=' * 60}\n[{_ts}] save_fund_sanction_data called\n")
			_lf.write(f"files param type: {type(files).__name__}\n")
			if isinstance(files, str):
				_lf.write(f"files (string, {len(files)} chars, preview): {files[:300]}\n")
			elif isinstance(files, list):
				_lf.write(f"files (list of {len(files)})\n")
			else:
				_lf.write(f"files: {files!r}\n")
			_lf.write(f"data keys: {list(data.keys())}\n")
			try:
				form_keys = list(frappe.form_dict.keys()) if getattr(frappe, "form_dict", None) else []
				_lf.write(f"frappe.form_dict keys: {form_keys}\n")
				req_files = getattr(frappe.request, "files", None)
				if req_files:
					_lf.write(f"frappe.request.files keys: {list(req_files.keys())}\n")
			except Exception as _e:
				_lf.write(f"form_dict/request inspect error: {_e}\n")
			_lf.write(f"{'=' * 60}\n")
	except Exception:
		pass

	is_new = False  # Initialize is_new flag
	uploaded_file_urls = []  # Collected MinIO URLs for the Mattermost success log

	try:
		# Extract child tables and flags
		budget_data = data.pop("sanctioned_budget_breakup", [])
		files_data = data.pop("sanction_related_files", [])
		submit = data.pop("submit", False)

		# --- Handle files payload (tolerant of several key names / shapes) ---
		# Frontend may send base64 uploads under any of: files, files_payload,
		# file_data, attachments. Some clients also embed base64 fields inside
		# sanction_related_files rows — we pick those up too as a fallback.
		def _coerce_list(val):
			if not val:
				return None
			if isinstance(val, str):
				try:
					parsed = json.loads(val)
				except Exception:
					return None
				val = parsed
			if isinstance(val, list):
				return val
			return None

		files_payload = _coerce_list(files)
		for candidate_key in ("files", "files_payload", "file_data", "attachments"):
			if files_payload:
				break
			files_payload = _coerce_list(data.pop(candidate_key, None))

		# Fallback: promote base64 fields embedded in sanction_related_files rows
		if not files_payload and isinstance(files_data, list):
			embedded = []
			for row in files_data:
				if not isinstance(row, dict):
					continue
				content_b64 = row.get("content") or row.get("file_data") or row.get("data")
				if not content_b64:
					continue
				embedded.append({
					"filename": row.get("filename") or row.get("file_name") or row.get("description"),
					"content": content_b64,
					"description": row.get("description"),
					"is_private": row.get("is_private", 1),
				})
			if embedded:
				files_payload = embedded

		print(f"\nIncoming Fund Sanction save request. Keys: {list(data.keys())}")
		print(
			f"Budget rows: {len(budget_data)}, File rows: {len(files_data)}, "
			f"files_payload type={type(files_payload).__name__} "
			f"count={len(files_payload) if isinstance(files_payload, list) else 0}"
		)
		if isinstance(files_payload, list) and files_payload:
			_first = files_payload[0]
			if isinstance(_first, dict):
				_preview = {k: (str(v)[:40] + "…") if isinstance(v, str) and len(v) > 40 else v
							for k, v in _first.items()}
				print(f"[DEBUG] first file entry: {_preview}")

		# project_reg anchors uploaded files under the Project Registration's
		# MinIO directory (e.g. Project_Registration/<project_reg>/fund_sanction/...).
		project_reg = data.pop("project_reg", None)
		data.pop("project_no", None)

		# --- START EDIT BY MKY ---
		# Date: 2026-05-19
		# Time: 16:35 IST
		# Description: Auto-detect existing draft to prevent duplication when frontend does not pass name
		if not data.get("name") and data.get("project_proposal"):
			existing_draft = frappe.db.get_value(
				"Fund Sanction",
				{
					"project_proposal": data.get("project_proposal"),
					"docstatus": 0,
					"owner": frappe.session.user
				},
				"name",
				order_by="creation desc"
			)
			if existing_draft:
				data["name"] = existing_draft
				print(f"🔄 Found existing draft {existing_draft} for project {data.get('project_proposal')}. Updating instead of creating a new one.")
		# --- END EDIT BY MKY ---

		# Enforce unique sanctioned_letter_no (doc.save below runs with
		# ignore_validate, so the doctype-level check would be skipped)
		letter_no = (data.get("sanctioned_letter_no") or "").strip()
		if letter_no:
			dup_filters = {"sanctioned_letter_no": letter_no}
			if data.get("name"):
				dup_filters["name"] = ["!=", data.get("name")]
			duplicate = frappe.db.get_value("Fund Sanction", dup_filters, "name")
			if duplicate:
				frappe.throw(
					_(
						"Sanctioned Letter No '{0}' is already used in Fund Sanction {1}. "
						"It must be unique."
					).format(letter_no, duplicate),
					title=_("Duplicate Sanctioned Letter No"),
				)

		# Create or fetch the main Fund Sanction document
		previous_workflow_state_for_kafka = None
		if data.get("name"):
			# Logic for updating an existing document
			doc = frappe.get_doc("Fund Sanction", data.get("name"))
			previous_workflow_state_for_kafka = doc.workflow_state
			doc.update(data)
			doc.set("sanctioned_budget_breakup", [])
			doc.set("sanction_related_files", [])
		else:
			# Logic for creating a new document
			is_new = True
			data["doctype"] = "Fund Sanction"
			doc = frappe.get_doc(data)

			# --- MODIFICATION: Set initial workflow state for new documents ---
			doc.workflow_state = "Draft"
			doc.sanction_workflow_status = "Draft"
			print("✨ New document detected. Setting workflow status to 'Draft'.")

		# Disable validation and permission checks
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.flags.ignore_validate_update_after_submit = True

		# --- Save main document first ---
		doc.save(ignore_permissions=True)
		print(f"✅ Parent doc saved: {doc.name}")

		# --- Add budget breakup rows (raw data, no validation) ---
		if budget_data:
			for row in budget_data:
				# Remove possible invalid link keys
				row.pop("account_head_name", None)
				doc.append("sanctioned_budget_breakup", row)
			print(f"✅ Added {len(budget_data)} budget rows")

		# --- Add file rows (path only) ---
		# Note: This logic assumes the frontend sends a direct URL in 'sanction_file'.
		if files_data:
			for f in files_data:
				file_path = f.get("sanction_file")
				if not file_path:
					continue
				doc.append(
					"sanction_related_files",
					{"description": f.get("description"), "sanction_file": file_path},
				)
			print(f"✅ Added {len(files_data)} sanction file rows")

		# --- Save again with children ---
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)
		print("✅ Second save complete")

		# --- Handle new file uploads (Base64) → MinIO, mirrors save_project_draft ---
		if files_payload and isinstance(files_payload, list):
			file_service = get_rnd_file_service()
			for f in files_payload:
				try:
					filename = f.get("filename") or f.get("file_name") or f.get("name")
					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
					is_private = int(f.get("is_private") or 1)
					description = f.get("description") or filename

					if not (filename and content_b64):
						continue

					if content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					file_content = base64.b64decode(content_b64)

					# Route files under the Project Registration's MinIO directory:
					#   Project_Registration/<project_reg>/fund_sanction/<filename>
					# Falls through to doc.project_proposal if project_reg wasn't sent.
					target_doctype = "Project Registration"
					target_docname = project_reg or doc.project_proposal
					fieldname_hint = f.get("fieldname")
					if fieldname_hint:
						folder = get_file_category_for_doctype(target_doctype, fieldname_hint)
					else:
						folder = "fund_sanction"

					upload_result = file_service.save_file(
						filename=filename,
						content=file_content,
						is_private=bool(is_private),
						doctype=target_doctype,
						docname=target_docname,
						folder=folder,
					)

					if upload_result.get("status"):
						file_url = upload_result.get("data", {}).get("file_url")
						doc.append("sanction_related_files", {
							"description": description,
							"sanction_file": file_url,
						})
						if file_url:
							uploaded_file_urls.append(file_url)
						frappe.logger().info(
							f"File uploaded to MinIO: {filename} -> {file_url}"
						)
					else:
						frappe.log_error(
							f"MinIO upload failed: {upload_result.get('message')}",
							f"save_fund_sanction_data: file upload error for {filename}",
						)

				except Exception as fe:
					frappe.log_error(
						frappe.get_traceback(),
						f"save_fund_sanction_data: file upload error for {f.get('filename')}",
					)
					continue

			# Save again to update child table with new files
			doc.flags.ignore_validate = True
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			frappe.db.commit()

		# --- Submit if requested ---
		if submit:
			doc.submit()
			print("✅ Submitted successfully")

		# --- ✅ Send data to external API (Kafka) only when Sanction Approved ---
		kafka_success = False
		if doc.workflow_state == "Sanction Approved":
			try:
				record_publish_state(
					"Fund Sanction", doc.name, TOPIC_SANCTION,
					previous_workflow_state_for_kafka, doc.workflow_state,
				)
				kafka_success = publish_sanction(doc)
				if kafka_success:
					frappe.msgprint(_("Sanction data synced successfully to external system."), indicator="green")
					notify_mattermost(
						"```\n"
						"┌──────────────────────────────────────────────┐\n"
						"│  📡 [Kafka Publish] SUCCESS                   │\n"
						"├──────────────────────────────────────────────┤\n"
						f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
						f" Docname  : {doc.name}\n"
						f" State    : {doc.workflow_state}\n"
						f" User     : {frappe.session.user}\n"
						"└──────────────────────────────────────────────┘\n"
						"```"
					)
				else:
					# Rollback: Delete if newly created, otherwise log error
					notify_mattermost(
						"```\n"
						"┌──────────────────────────────────────────────┐\n"
						"│  ⚠️ [Kafka Publish] FAILED                    │\n"
						"├──────────────────────────────────────────────┤\n"
						f" Time     : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
						f" Docname  : {doc.name}\n"
						f" State    : {doc.workflow_state}\n"
						f" User     : {frappe.session.user}\n"
						f" Rollback : {'yes (new doc)' if is_new else 'no (kept local)'}\n"
						"└──────────────────────────────────────────────┘\n"
						"```",
						urgent=True,
					)
					if is_new:
						doc.delete(ignore_permissions=True)
						frappe.db.rollback()
						frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
					else:
						frappe.db.set_value(
							"Fund Sanction", doc.name, "workflow_state",
							previous_workflow_state_for_kafka, update_modified=False,
						)
						frappe.db.commit()
						frappe.throw(
							_("Kafka sync failed. Approval was not applied; workflow state reverted to '{0}'.")
							.format(previous_workflow_state_for_kafka)
						)
			except frappe.ValidationError:
				raise  # Re-raise validation errors from frappe.throw
			except Exception as e:
				_kafka_tb = frappe.get_traceback()
				frappe.log_error(_kafka_tb, "Fund Sanction Kafka Sync Error")
				notify_mattermost(
					"```\n"
					"┌──────────────────────────────────────────────┐\n"
					"│  ❌ [Kafka Publish] EXCEPTION                 │\n"
					"├──────────────────────────────────────────────┤\n"
					f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
					f" Docname   : {doc.name}\n"
					f" State     : {doc.workflow_state}\n"
					f" User      : {frappe.session.user}\n"
					f" Exception : {type(e).__name__}: {str(e)}\n"
					"└──────────────────────────────────────────────┘\n"
					f"---TRACEBACK---\n{_kafka_tb}\n"
					"```",
					urgent=True,
				)
				if is_new:
					doc.delete(ignore_permissions=True)
					frappe.db.rollback()
					frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
				else:
					frappe.db.set_value(
						"Fund Sanction", doc.name, "workflow_state",
						previous_workflow_state_for_kafka, update_modified=False,
					)
					frappe.db.commit()
					frappe.throw(
						_("Kafka sync failed. Approval was not applied; workflow state reverted to '{0}'.")
						.format(previous_workflow_state_for_kafka)
					)

		frappe.db.commit()

		if uploaded_file_urls:
			files_block = "\n".join(f"   • {u}" for u in uploaded_file_urls)
		else:
			files_block = "   (no new uploads)"

		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  ✅ [save_fund_sanction_data] SUCCESS        │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time    : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Docname : {doc.name}\n"
			f" State   : {doc.workflow_state}\n"
			f" User    : {frappe.session.user}\n"
			f" Kafka   : {'synced' if kafka_success else 'skipped' if doc.workflow_state != 'Sanction Approved' else 'failed'}\n"
			f" Files ({len(uploaded_file_urls)}):\n"
			f"{files_block}\n"
			"└──────────────────────────────────────────────┘\n"
			"```"
		)

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		_tb = frappe.get_traceback()
		frappe.db.rollback()
		frappe.log_error(_tb, "Fund Sanction Save Error")
		notify_mattermost(
			"```\n"
			"┌──────────────────────────────────────────────┐\n"
			"│  ❌ [save_fund_sanction_data] ERROR          │\n"
			"├──────────────────────────────────────────────┤\n"
			f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
			f" Exception : {type(e).__name__}: {str(e)}\n"
			f" User      : {frappe.session.user}\n"
			"└──────────────────────────────────────────────┘\n"
			f"---TRACEBACK---\n{_tb}\n"
			"```",
			urgent=True,
		)
		frappe.throw(f"An error occurred while saving the Fund Sanction: {str(e)}")


@frappe.whitelist()
def get_sanctions_for_project(project_name):
	"""
	Retrieves all Fund Sanction documents for a project,
	and embeds the content of any attached files as a Base64 string.
	"""
	if not project_name:
		return []

	sanction_names = frappe.get_all("Fund Sanction", filters={"project_proposal": project_name}, pluck="name")

	if not sanction_names:
		return []

	sanctions_list = []
	for name in sanction_names:
		# Get the full document as a dictionary
		doc_dict = frappe.get_doc("Fund Sanction", name).as_dict()

		# --- NEW: Process the child table for files ---
		# Check if the 'sanction_related_files' table exists and has entries
		if doc_dict.get("sanction_related_files"):
			# Loop through each file attached to this sanction document
			for file_info in doc_dict.get("sanction_related_files"):
				try:
					# Get the File document from the file_url
					file_url = file_info.get("sanction_file")
					if not file_url:
						continue

					# The actual file document contains the content
					file_doc = frappe.get_doc("File", {"file_url": file_url})

					# Get the raw binary content of the file
					file_content = file_doc.get_content()

					# Encode the binary content into a Base64 string (as utf-8 text)
					base64_content = base64.b64encode(file_content).decode("utf-8")

					# Add the base64 content as a new key to the file's dictionary
					# We also include the file_name for convenience on the frontend
					file_info["file_name"] = file_doc.file_name
					file_info["file_data"] = base64_content

				except Exception as e:
					# If a file is missing from disk or another error occurs, log it
					# and continue without crashing the whole API call.
					print(f"Could not read file for URL {file_url}: {e}")
					file_info["file_data"] = None  # Indicate that the file content is missing

		sanctions_list.append(doc_dict)

	return sanctions_list


@frappe.whitelist()
def get_fund_sanction_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Fund Sanction", docname)
	user_roles = frappe.get_roles(frappe.session.user)

	# Fetch the workflow for this doctype
	workflow_name = "fund_sanction_workflow"
	
	if not frappe.db.exists("Workflow", workflow_name):
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	workflow_field = workflow.workflow_state_field or "workflow_state"
	current_state = doc.get(workflow_field) or "Draft"
	
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
def perform_fund_sanction_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.
	"""
	try:
		doc = frappe.get_doc("Fund Sanction", docname)

		# Fetch the workflow for this doctype
		workflow_name = "fund_sanction_workflow"
		
		if not frappe.db.exists("Workflow", workflow_name):
			frappe.throw(f"Workflow '{workflow_name}' not found.")

		workflow = frappe.get_doc("Workflow", workflow_name)
		workflow_field = workflow.workflow_state_field or "workflow_state"
		current_state = doc.get(workflow_field) or "Draft"

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
		doc.set(workflow_field, next_state)
		doc.set("sanction_workflow_status", next_state) # Keep legacy field in sync if needed
		
		# Check if next state requires submission (docstatus=1)
		# We check the 'states' table in Workflow to see if doc_status should be 1
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		new_docstatus = int(state_doc.doc_status or 0) if state_doc else 0

		workflow_field = workflow.workflow_state_field or "workflow_state"
		update_fields = {
			workflow_field: next_state,
			"sanction_workflow_status": next_state
		}

		if new_docstatus != int(doc.docstatus):
			update_fields["docstatus"] = new_docstatus

		if (
			state_doc
			and getattr(state_doc, "update_field", None)
			and state_doc.update_field != workflow_field
			and state_doc.update_value is not None
		):
			update_fields[state_doc.update_field] = state_doc.update_value

		# Gate: when this transition reaches 'Sanction Approved', the Kafka publish
		# must succeed BEFORE the state change below is committed. On failure we
		# throw without writing anything, so the document stays in '{current_state}'
		# and the frontend receives a real error instead of a silent "success".
		kafka_status = None
		if next_state == "Sanction Approved":
			print(f"[FS_ACTION] State is 'Sanction Approved' — publishing to Kafka for {docname}")
			try:
				record_publish_state(
					"Fund Sanction", docname, TOPIC_SANCTION,
					current_state, next_state,
				)
				kafka_success = publish_sanction(doc)
			except Exception as ke:
				print(f"[FS_ACTION] Kafka publish EXCEPTION for {docname}: {ke}")
				frappe.log_error(frappe.get_traceback(), f"Fund Sanction Kafka Exception for {docname}")
				frappe.throw(
					_("Cannot approve: Kafka sync failed ({0}). No changes were applied; state remains '{1}'.")
					.format(str(ke), current_state)
				)

			if not kafka_success:
				print(f"[FS_ACTION] Kafka publish FAILED for {docname}")
				frappe.log_error(
					f"Kafka publish failed after Sanction Approved for {docname}",
					"Fund Sanction Kafka Error",
				)
				frappe.throw(
					_("Cannot approve: Kafka sync returned False (check validation errors in the Error Log). "
					  "No changes were applied; state remains '{0}'.").format(current_state)
				)

			kafka_status = "success"
			print(f"[FS_ACTION] Kafka publish SUCCESS for {docname}")

		frappe.db.set_value(
			"Fund Sanction",
			docname,
			update_fields,
			update_modified=True,
		)

		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		frappe.db.commit()

		result = {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_fund_sanction_workflow_actions(docname),
		}
		if kafka_status:
			result["kafka_status"] = kafka_status
		return result

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Action Error")
		return {"status": "error", "message": str(e)}


# --- START EDIT BY MKY ---
# Date: 2026-05-19
# Time: 16:35 IST
# Description: Fix typo in submit_fund_sanction (profund_sanctionject_no -> project_no, save__data -> save_fund_sanction_data) and pass sanction_name to data
@frappe.whitelist()
def submit_fund_sanction(sanction_name=None, save=None, files=None, project_reg=None, project_no=None, **data):
	"""
	Submit a Fund Sanction document using Workflow transitions.
	If save is True, it first saves the document using the provided data.
	"""
	if save in [True, "true", "True", "1", 1]:
		# Pass explicit parameters back into data for save_fund_sanction_data
		if project_reg is not None:
			data["project_reg"] = project_reg
		if project_no is not None:
			data["project_no"] = project_no
		if sanction_name:
			data["name"] = sanction_name
		res = save_fund_sanction_data(files, **data)
		if isinstance(res, dict) and res.get("status") == "success":
			sanction_name = res.get("docname") or res.get("name")
		else:
			return res

	if not sanction_name:
		frappe.throw("Sanction name is required to submit.")

	return perform_fund_sanction_action(sanction_name, "Submit")
# --- END EDIT BY MKY ---


@frappe.whitelist()
def update_sanctioned_budget_breakup(docname, rows, username=None):
    """
    Update or insert rows in the sanctioned_budget_breakup child table of a Fund Sanction.
    Works on both draft and submitted documents.

    Args:
        docname (str): Fund Sanction document name.
        rows (list | str): List of row dicts with keys:
            - account_head (str)
            - head (str)               — alias for account_head
            - years (list[float])      — [yr1, yr2, yr3, yr4, yr5] shorthand
            - first_year_budget … fifth_year_budget (float)
        username (str, optional): When provided, the document workflow state is preserved
            as-is. When omitted, the document is reset to Draft.
    """
    import json as _json

    CHILD_DOCTYPE = "Project Sanctioned Budget"
    CHILD_FIELD   = "sanctioned_budget_breakup"
    YEAR_FIELDS   = [
        "first_year_budget",
        "second_year_budget",
        "third_year_budget",
        "fourth_year_budget",
        "fifth_year_budget",
    ]

    try:
        print(f"[SBB_UPDATE] START docname={docname} user={frappe.session.user}")

        if not docname:
            return {"status": "error", "message": "Document name is required"}

        if isinstance(rows, str):
            rows = _json.loads(rows)

        if not isinstance(rows, list):
            print(f"[SBB_UPDATE] rows is not a list: {type(rows)}")
            return {"status": "error", "message": "'rows' must be a list"}

        print(f"[SBB_UPDATE] rows count={len(rows)}")

        doc = frappe.get_doc("Fund Sanction", docname)
        print(f"[SBB_UPDATE] doc fetched: owner={doc.owner} docstatus={doc.docstatus} workflow_state={doc.workflow_state}")

        # Pre-process all rows
        processed_rows = []
        for idx, row_data in enumerate(rows):
            d = row_data.copy() if isinstance(row_data, dict) else {}

            if "head" in d:
                d["account_head"] = d.pop("head")

            if isinstance(d.get("account_head"), dict):
                ah = d["account_head"]
                d["account_head"] = ah.get("value") or ah.get("name") or None

            years_array = d.pop("years", []) or []
            for i, amount in enumerate(years_array):
                if i < len(YEAR_FIELDS):
                    d[YEAR_FIELDS[i]] = flt(amount)

            row_total = sum(flt(d.get(f, 0)) for f in YEAR_FIELDS)
            d["total_proposal_of_heads"] = row_total
            d["idx"] = idx + 1
            processed_rows.append(d)
            print(f"[SBB_UPDATE] row[{idx}] processed: account_head={d.get('account_head')} total={row_total}")

        # Build sets of identifiers present in the incoming payload
        incoming_names        = {r.get("name") for r in processed_rows if r.get("name")}
        incoming_account_heads = {r.get("account_head") for r in processed_rows if r.get("account_head")}

        now = frappe.utils.now()
        keep_state = bool(username)
        print(f"[SBB_UPDATE] session_user={frappe.session.user} username={username} keep_state={keep_state}")

        if doc.docstatus == 1:
            print(f"[SBB_UPDATE] SUBMITTED: using direct DB update")

            existing_rows = frappe.db.get_all(
                CHILD_DOCTYPE,
                filters={"parent": docname, "parentfield": CHILD_FIELD, "parenttype": "Fund Sanction"},
                fields=["name", "account_head"],
            )
            by_account_head = {r["account_head"]: r["name"] for r in existing_rows}
            by_name        = {r["name"]: r["name"] for r in existing_rows}
            print(f"[SBB_UPDATE] existing rows: {[r['account_head'] for r in existing_rows]}")

            # Delete rows that are no longer in the incoming list
            for r in existing_rows:
                if r["name"] not in incoming_names and r["account_head"] not in incoming_account_heads:
                    frappe.db.delete(CHILD_DOCTYPE, {"name": r["name"]})
                    print(f"[SBB_UPDATE] deleted row {r['name']} (account_head={r['account_head']})")

            for row in processed_rows:
                existing_name = by_name.get(row.get("name")) or by_account_head.get(row.get("account_head"))
                set_vals = {k: v for k, v in row.items() if k not in ("name", "idx")}
                set_vals.update({"modified": now, "modified_by": frappe.session.user})

                if existing_name:
                    frappe.db.set_value(CHILD_DOCTYPE, existing_name, set_vals, update_modified=False)
                    print(f"[SBB_UPDATE] updated {existing_name} (account_head={row.get('account_head')})")
                else:
                    child = frappe.get_doc({
                        "doctype": CHILD_DOCTYPE,
                        "parent": docname,
                        "parentfield": CHILD_FIELD,
                        "parenttype": "Fund Sanction",
                        "creation": now,
                        "owner": frappe.session.user,
                        **row,
                    })
                    child.db_insert()
                    print(f"[SBB_UPDATE] inserted new row idx={row['idx']} (account_head={row.get('account_head')})")

            # Compute total from remaining rows after deletions and updates
            all_rows = frappe.db.get_all(
                CHILD_DOCTYPE,
                filters={"parent": docname, "parentfield": CHILD_FIELD, "parenttype": "Fund Sanction"},
                fields=["total_proposal_of_heads"],
            )
            total_sanctioned = sum(flt(r.get("total_proposal_of_heads", 0)) for r in all_rows)
            print(f"[SBB_UPDATE] total_sanctioned_amount={total_sanctioned}")

            if keep_state:
                frappe.db.set_value(
                    "Fund Sanction", docname,
                    {"total_sanctioned_amount": total_sanctioned},
                    update_modified=True,
                )
                print(f"[SBB_UPDATE] staff,RnD user — workflow_state kept as '{doc.workflow_state}' (no draft reset)")
            else:
                frappe.db.set_value(
                    "Fund Sanction", docname,
                    {
                        "workflow_state": "Draft",
                        "sanction_workflow_status": "Draft",
                        "docstatus": 0,
                        "total_sanctioned_amount": total_sanctioned,
                    },
                    update_modified=True,
                )
                print(f"[SBB_UPDATE] workflow reset to Draft (submitted → draft)")

        else:
            if keep_state:
                print(f"[SBB_UPDATE] DRAFT + staff,RnD: using direct DB update (skip doc.save to avoid workflow validation)")

                existing_rows = frappe.db.get_all(
                    CHILD_DOCTYPE,
                    filters={"parent": docname, "parentfield": CHILD_FIELD, "parenttype": "Fund Sanction"},
                    fields=["name", "account_head"],
                )
                by_account_head = {r["account_head"]: r["name"] for r in existing_rows}
                by_name         = {r["name"]: r["name"] for r in existing_rows}
                print(f"[SBB_UPDATE] existing rows: {[r['account_head'] for r in existing_rows]}")

                for r in existing_rows:
                    if r["name"] not in incoming_names and r["account_head"] not in incoming_account_heads:
                        frappe.db.delete(CHILD_DOCTYPE, {"name": r["name"]})
                        print(f"[SBB_UPDATE] deleted row {r['name']} (account_head={r['account_head']})")

                for row in processed_rows:
                    existing_name = by_name.get(row.get("name")) or by_account_head.get(row.get("account_head"))
                    set_vals = {k: v for k, v in row.items() if k not in ("name", "idx")}
                    set_vals.update({"modified": now, "modified_by": frappe.session.user})

                    if existing_name:
                        frappe.db.set_value(CHILD_DOCTYPE, existing_name, set_vals, update_modified=False)
                        print(f"[SBB_UPDATE] updated {existing_name} (account_head={row.get('account_head')})")
                    else:
                        child = frappe.get_doc({
                            "doctype": CHILD_DOCTYPE,
                            "parent": docname,
                            "parentfield": CHILD_FIELD,
                            "parenttype": "Fund Sanction",
                            "creation": now,
                            "owner": frappe.session.user,
                            **row,
                        })
                        child.db_insert()
                        print(f"[SBB_UPDATE] inserted new row idx={row['idx']} (account_head={row.get('account_head')})")

                all_rows = frappe.db.get_all(
                    CHILD_DOCTYPE,
                    filters={"parent": docname, "parentfield": CHILD_FIELD, "parenttype": "Fund Sanction"},
                    fields=["total_proposal_of_heads"],
                )
                total_sanctioned = sum(flt(r.get("total_proposal_of_heads", 0)) for r in all_rows)
                frappe.db.set_value(
                    "Fund Sanction", docname,
                    {"total_sanctioned_amount": total_sanctioned},
                    update_modified=True,
                )
                print(f"[SBB_UPDATE] staff,RnD draft: total={total_sanctioned}, workflow_state kept as '{doc.workflow_state}'")

            else:
                print(f"[SBB_UPDATE] DRAFT: using doc.save()")

                # Remove rows from the in-memory table that are not in the incoming list;
                # Frappe's doc.save() will delete them from DB automatically.
                kept = []
                for r in doc.sanctioned_budget_breakup:
                    if r.name in incoming_names or r.account_head in incoming_account_heads:
                        kept.append(r)
                    else:
                        print(f"[SBB_UPDATE] removing row {r.name} (account_head={r.account_head})")
                doc.sanctioned_budget_breakup = kept

                existing_by_ah   = {r.account_head: r for r in doc.sanctioned_budget_breakup}
                existing_by_name = {r.name: r for r in doc.sanctioned_budget_breakup}

                for row in processed_rows:
                    existing_row = existing_by_name.get(row.get("name")) or existing_by_ah.get(row.get("account_head"))
                    if existing_row:
                        for k, v in row.items():
                            if k not in ("name", "idx"):
                                existing_row.set(k, v)
                        print(f"[SBB_UPDATE] updated in-memory row (account_head={row.get('account_head')})")
                    else:
                        doc.append(CHILD_FIELD, row)
                        print(f"[SBB_UPDATE] appended new row (account_head={row.get('account_head')})")

                total_sanctioned = sum(flt(r.total_proposal_of_heads) for r in doc.sanctioned_budget_breakup)
                doc.total_sanctioned_amount = total_sanctioned
                doc.workflow_state = "Draft"
                doc.sanction_workflow_status = "Draft"
                doc.flags.ignore_validate = True
                doc.flags.ignore_mandatory = True
                doc.validate_workflow = lambda: None
                doc.save(ignore_permissions=True)
                print(f"[SBB_UPDATE] doc saved with workflow reset to Draft")

        frappe.db.commit()
        print(f"[SBB_UPDATE] COMMITTED successfully")

        return {
            "status": "success",
            "docname": docname,
            "workflow_state": doc.workflow_state,
            "rows_updated": len(rows),
            "total_sanctioned_amount": total_sanctioned,
        }

    except frappe.DoesNotExistError:
        print(f"[SBB_UPDATE] DoesNotExist: {docname}")
        return {"status": "error", "message": f"Fund Sanction '{docname}' not found"}
    except Exception as e:
        import traceback as _tb
        tb = _tb.format_exc()
        print(f"[SBB_UPDATE] EXCEPTION: {e}\n{tb}")
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"Update Sanctioned Budget Breakup Error for {docname}")
        return {"status": "error", "message": str(e), "traceback": tb}


@frappe.whitelist()
def update_fund_sanction_files(docname, files=None, existing_files=None, project_reg=None, replace=False):
	"""
	Upload new files (Base64 → MinIO) and/or update the sanction_related_files
	child table of an existing Fund Sanction document.

	Args:
		docname       (str):        Fund Sanction name to update.
		files         (list|str):   New files as base64 objects — same shape as
		                            save_fund_sanction_data: [{filename, content,
		                            description, is_private, fieldname}, ...].
		existing_files (list|str):  Rows that already have a MinIO URL and should
		                            be kept / updated: [{description, sanction_file}, ...].
		                            Ignored when replace=True (the table is rebuilt
		                            from existing_files + newly uploaded files).
		project_reg   (str):        Project Registration name for MinIO path routing
		                            (falls back to doc.project_proposal if omitted).
		replace       (bool|str):   When truthy, clear the child table first then
		                            repopulate from existing_files + new uploads.
		                            Default False (append-only).
	"""
	import json

	def _coerce_list(val):
		if not val:
			return []
		if isinstance(val, str):
			try:
				val = json.loads(val)
			except Exception:
				return []
		return val if isinstance(val, list) else []

	replace = replace in (True, "true", "True", "1", 1)
	files_payload = _coerce_list(files)
	existing_rows = _coerce_list(existing_files)
	uploaded_file_urls = []

	try:
		if not docname:
			frappe.throw("docname is required")

		doc = frappe.get_doc("Fund Sanction", docname)

		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_validate_update_after_submit = True

		if replace:
			doc.set("sanction_related_files", [])

		# Re-add / keep existing file rows
		for row in existing_rows:
			file_url = row.get("sanction_file")
			if not file_url:
				continue
			doc.append("sanction_related_files", {
				"description": row.get("description") or file_url,
				"sanction_file": file_url,
			})

		# Upload new base64 files → MinIO
		if files_payload:
			file_service = get_rnd_file_service()
			target_doctype = "Project Registration"
			target_docname = project_reg or doc.project_proposal

			for f in files_payload:
				try:
					filename = f.get("filename") or f.get("file_name") or f.get("name")
					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
					is_private = int(f.get("is_private") or 1)
					description = f.get("description") or filename

					if not (filename and content_b64):
						continue

					if content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					file_content = base64.b64decode(content_b64)

					fieldname_hint = f.get("fieldname")
					if fieldname_hint:
						folder = get_file_category_for_doctype(target_doctype, fieldname_hint)
					else:
						folder = "fund_sanction"

					upload_result = file_service.save_file(
						filename=filename,
						content=file_content,
						is_private=bool(is_private),
						doctype=target_doctype,
						docname=target_docname,
						folder=folder,
					)

					if upload_result.get("status"):
						file_url = upload_result.get("data", {}).get("file_url")
						doc.append("sanction_related_files", {
							"description": description,
							"sanction_file": file_url,
						})
						if file_url:
							uploaded_file_urls.append(file_url)
						frappe.logger().info(f"File uploaded to MinIO: {filename} -> {file_url}")
					else:
						frappe.log_error(
							f"MinIO upload failed: {upload_result.get('message')}",
							f"update_fund_sanction_files: upload error for {filename}",
						)

				except Exception as fe:
					frappe.log_error(
						frappe.get_traceback(),
						f"update_fund_sanction_files: upload error for {f.get('filename')}",
					)
					continue

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {
			"status": "success",
			"docname": docname,
			"uploaded_files": uploaded_file_urls,
			"total_file_rows": len(doc.sanction_related_files),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update_fund_sanction_files error for {docname}")
		frappe.throw(f"Failed to update files for Fund Sanction: {str(e)}")
