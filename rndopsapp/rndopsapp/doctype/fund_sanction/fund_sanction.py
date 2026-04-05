# # # Copyright (c) 2025, rndops and contributors
# # # For license information, please see license.txt

# # # import frappe

# # # frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py

# # import frappe
# # import requests
# # from frappe import _
# # from frappe.model.document import Document
# # from frappe.utils import cint, flt
# # from rndopsapp.rndopsapp.kafka.producer import publish_fund_sanction as publish_sanction

# # # from frappe.workflow.doctype.workflow.workflow import get_workflow_name


# # class FundSanction(Document):
# # 	def validate(self):
# # 		# Add any specific validation for Fund Sanction here
# # 		pass


# # API_URL = "http://172.16.135.27:18080/api/sanction-details/addSanctionDetails"


# # def send_sanction_details_to_api(doc):
# # 	"""
# # 	Prepare and send Fund Sanction data to the external API endpoint.
# # 	Uses exact match: Budget Head.budget_head == row.account_head -> fetch numeric id.
# # 	Prints every step to the terminal for debug visibility.
# # 	"""
# # 	print("\n=== SEND SANCTION DETAILS TO API START ===")
# # 	try:
# # 		# Build base payload
# # 		payload = {
# # 			"projectNumber": getattr(doc, "refnum_prj_num", None),
# # 			"sanctionLetterNo": getattr(doc, "sanctioned_letter_no", None),
# # 			"sanctionLetterDate": str(getattr(doc, "sanctioned_letter_date"))
# # 			if getattr(doc, "sanctioned_letter_date", None)
# # 			else None,
# # 			"totalSanctionAmount": flt(getattr(doc, "total_sanctioned_amount", 0) or 0.0),
# # 			# include top-level totals if present on the doc
# # 			"totalFirstYearBudget": flt(getattr(doc, "total_first_year_budget", 0) or 0.0),
# # 			"totalSecondYearBudget": flt(getattr(doc, "total_second_year_budget", 0) or 0.0),
# # 			"totalThirdYearBudget": flt(getattr(doc, "total_third_year_budget", 0) or 0.0),
# # 			"totalFourthYearBudget": flt(getattr(doc, "total_fourth_year_budget", 0) or 0.0),
# # 			"totalFifthYearBudget": flt(getattr(doc, "total_fifth_year_budget", 0) or 0.0),
# # 			"budgetBreakups": [],
# # 		}

# # 		print("[PAYLOAD-BASE]", payload)

# # 		# Build budgetBreakups list using exact match lookups
# # 		print("[STEP] Building budgetBreakups with exact Budget Head.id lookup...")
# # 		for row in getattr(doc, "sanctioned_budget_breakup", []) or []:
# # 			raw_ah = (getattr(row, "account_head", "") or "").strip()
# # 			print(f"   > Processing row idx={getattr(row, 'idx', '<no-idx>')} account_head='{raw_ah}'")

# # 			# Exact match lookup: Budget Head where budget_head == raw_ah
# # 			try:
# # 				account_head_id = frappe.db.get_value("Budget Head", {"budget_head": raw_ah}, "id")
# # 			except Exception as e:
# # 				print(f"     - DB lookup error for '{raw_ah}': {e}")
# # 				account_head_id = None

# # 			# Coerce to int if possible, else keep None
# # 			if account_head_id not in (None, ""):
# # 				try:
# # 					account_head_id = int(account_head_id)
# # 				except Exception:
# # 					# If can't coerce, set None to avoid sending strings
# # 					print(
# # 						f"     - Warning: account_head_id for '{raw_ah}' is not integer: {account_head_id}; setting to None"
# # 					)
# # 					account_head_id = None

# # 			print(f"     - Mapped '{raw_ah}' -> accountHeadId={account_head_id}")

# # 			# Collect per-year budgets (coerce to float via flt)
# # 			first = flt(getattr(row, "first_year_budget", 0) or 0)
# # 			second = flt(getattr(row, "second_year_budget", 0) or 0)
# # 			third = flt(getattr(row, "third_year_budget", 0) or 0)
# # 			fourth = flt(getattr(row, "fourth_year_budget", 0) or 0)
# # 			fifth = flt(getattr(row, "fifth_year_budget", 0) or 0)
# # 			total = first + second + third + fourth + fifth

# # 			bh_payload = {
# # 				"accountHeadId": account_head_id,
# # 				"accountHeadAmount": flt(total),
# # 				"firstYearBudget": flt(first),
# # 				"secondYearBudget": flt(second),
# # 				"thirdYearBudget": flt(third),
# # 				"fourthYearBudget": flt(fourth),
# # 				"fifthYearBudget": flt(fifth),
# # 			}

# # 			payload["budgetBreakups"].append(bh_payload)
# # 			print(f"     - appended budgetBreakup: {bh_payload}")

# # 		print("[FINAL PAYLOAD]", payload)

# # 		# POST to external API
# # 		print("[STEP] Sending POST to API:", API_URL)
# # 		try:
# # 			response = requests.post(API_URL, json=payload, timeout=15)
# # 			print("     - HTTP status:", response.status_code)
# # 			try:
# # 				print("     - response JSON:", response.json())
# # 			except Exception:
# # 				print("     - response text:", response.text)

# # 			if response.status_code == 200:
# # 				frappe.logger().info(f"✅ Sanction details sent successfully: {response.text}")
# # 			else:
# # 				frappe.log_error(
# # 					f"Failed to send sanction details. Status: {response.status_code}, Response: {response.text}",
# # 					"Send Sanction Details API Error",
# # 				)
# # 		except requests.exceptions.RequestException as re:
# # 			print("     - RequestException while posting:", re)
# # 			frappe.log_error(frappe.get_traceback(), "Send Sanction Details RequestException")

# # 	except Exception as e:
# # 		frappe.log_error(frappe.get_traceback(), "Send Sanction Details Exception")
# # 		print(f"❌ Error preparing/sending sanction details: {e}")
# # 	finally:
# # 		print("=== SEND SANCTION DETAILS TO API END ===\n")


# # # Whitelisted method to fetch budget details from Project Proposal
# # @frappe.whitelist()
# # def get_project_proposal_budget_details(project_proposal_name):
# # 	try:
# # 		if not project_proposal_name:
# # 			frappe.throw("Project Proposal name is required to fetch budget details.")

# # 		project_proposal = frappe.get_doc("Project Proposal", project_proposal_name)

# # 		return {
# # 			"proposed_budget_breakup": project_proposal.get("proposed_budget_breakup", []),
# # 			"total_first_year_budget": project_proposal.total_first_year_budget,
# # 			"total_second_year_budget": project_proposal.total_second_year_budget,
# # 			"total_third_year_budget": project_proposal.total_third_year_budget,
# # 			"total_fourth_year_budget": project_proposal.total_fourth_year_budget,
# # 			"total_fifth_year_budget": project_proposal.total_fifth_year_budget,
# # 			"grand_total_proposal": project_proposal.grand_total_proposal,
# # 			"total_budget_amount": project_proposal.total_budget_amount,  # <-- Added this field
# # 		}

# # 	except frappe.DoesNotExistError:
# # 		frappe.log_error(
# # 			f"Project Proposal {project_proposal_name} not found.", "Fund Sanction Budget Fetch Error"
# # 		)
# # 		frappe.throw(f"Project Proposal '{project_proposal_name}' not found.")
# # 	except Exception as e:
# # 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Budget Fetch Error")
# # 		frappe.throw(f"An error occurred while fetching budget details: {e}")



# # @frappe.whitelist()
# # def save_fund_sanction_data(data):
# # 	"""
# # 	Save Fund Sanction form data to the backend.
# # 	Expects 'data' as a JSON string from frontend.
# # 	"""
# # 	import json

# # 	try:
# # 		# Parse JSON string if needed
# # 		if isinstance(data, str):
# # 			data = json.loads(data)

# # 		# Create or update Fund Sanction document
# # 		docname = data.get("name")  # If editing an existing doc
# # 		if docname:
# # 			fs_doc = frappe.get_doc("Fund Sanction", docname)
# # 		else:
# # 			fs_doc = frappe.new_doc("Fund Sanction")

# # 		# Map simple fields
# # 		simple_fields = [
# # 			"amended_from",
# # 			"project_proposal",
# # 			"total_sanctioned_amount",
# # 			"sanctioned_letter_no",
# # 			"sanctioned_letter_date",
# # 			"total_first_year_budget_1",
# # 			"total_second_year_budget_1",
# # 			"total_third_year_budget_1",
# # 			"total_fourth_year_budget_1",
# # 			"total_fifth_year_budget_1",
# # 			"grand_total_proposal_1",
# # 			"have_fund_details",
# # 			"project_type_linked",
# # 			"is_gst_invoice_issued",
# # 			"invoice_details",
# # 			"amount_received",
# # 			"iitg_bank_account_number",
# # 		]

# # 		for field in simple_fields:
# # 			if field in data:
# # 				setattr(fs_doc, field, data[field] if data[field] != "null" else None)

# # 		# Handle child tables
# # 		child_tables = {
# # 			"sanctioned_budget_breakup": "Sanctioned Budget Breakup",
# # 			"fund_transactions": "Fund Transactions",
# # 			"received_amount_breakup": "Received Amount Breakup",
# # 		}

# # 		for field, child_doctype in child_tables.items():
# # 			if field in data:
# # 				items = json.loads(data[field]) if isinstance(data[field], str) else data[field]
# # 				fs_doc.set(field, [])  # clear existing child table
# # 				for item in items:
# # 					child = fs_doc.append(field, item)

# # 		# Handle file attachments
# # 		if "sanction_related_files_meta" in data:
# # 			files_meta = json.loads(data["sanction_related_files_meta"])
# # 			for fmeta in files_meta:
# # 				# If file content comes as file_0, file_1, etc.
# # 				file_key = f"file_{files_meta.index(fmeta)}"
# # 				file_data = data.get(file_key)
# # 				if file_data:
# # 					# Save file in Frappe file system
# # 					file_doc = frappe.get_doc(
# # 						{
# # 							"doctype": "File",
# # 							"file_name": fmeta.get("description", f"file_{file_key}"),
# # 							"attached_to_doctype": "Fund Sanction",
# # 							"attached_to_name": fs_doc.name,
# # 							"content": file_data,  # file content in base64
# # 						}
# # 					)
# # 					file_doc.insert()

# # 		fs_doc.save()
# # 		frappe.db.commit()
# # 		return {"status": "success", "name": fs_doc.name}

# # 	except Exception as e:
# # 		frappe.log_error(frappe.get_traceback(), _("Error saving Fund Sanction"))
# # 		return {"status": "error", "message": str(e)}


# # # @frappe.whitelist()
# # # def submit_fund_sanction(name, action="Submit"):
# # # 	"""
# # # 	Submits an existing Fund Sanction document by applying a workflow action.

# # # 	:param name: The name (ID) of the Fund Sanction document to submit.
# # # 	:param action: The workflow action to apply (e.g., "Submit", "Approve").
# # # 	               Defaults to "Submit". The frontend can pass this.
# # # 	"""
# # # 	try:
# # # 		# 1. Fetch the specified document from the database.
# # # 		doc = frappe.get_doc("Fund Sanction", name)

# # # 		# 2. --- Pre-submission Validation ---
# # # 		#    These checks ensure the action is valid and secure.

# # # 		# Check for user permissions. This is a critical security step.
# # # 		# It checks if the current logged-in user has 'submit' permission.
# # # 		if not doc.has_permission("submit"):
# # # 			frappe.throw("You do not have permission to submit this document.", title="Permission Error")

# # # 		# Ensure the document is in a submittable state (docstatus=0 means it's a Draft).
# # # 		if doc.docstatus != 0:
# # # 			frappe.throw(
# # # 				f"Document {doc.name} cannot be submitted as it is not a Draft.", title="Invalid State"
# # # 			)

# # # 		# Optional but recommended: Check if a workflow is even active for this doctype.
# # # 		workflow_name = get_workflow_name("Fund Sanction")
# # # 		if not workflow_name:
# # # 			frappe.throw(
# # # 				"No active workflow named 'sanction_workflow' found for Fund Sanction.",
# # # 				title="Workflow Not Found",
# # # 			)

# # # 		# 3. --- Apply the Workflow Action ---
# # # 		#    This is the core of the function. It tells the Frappe workflow engine
# # # 		#    to process the transition for the given action.
# # # 		#    The engine will automatically:
# # # 		#      - Check if the 'action' is valid from the current workflow_state.
# # # 		#      - Change the `workflow_state` field (e.g., from 'Draft' to 'Pending Approval').
# # # 		#      - Run any code defined in the workflow transition hooks.
# # # 		#      - If the new state is configured as a "submitted" state (has doc_status=1),
# # # 		#        it will automatically call `doc.submit()` internally.

# # # 		frappe.workflow.apply_workflow(doc, action)

# # # 		# The apply_workflow function modifies the doc in memory, so we save it.
# # # 		doc.save()

# # # 		# 4. Commit the changes to the database.
# # # 		frappe.db.commit()

# # # 		# For debugging: log the successful action
# # # 		frappe.log_message(
# # # 			"Workflow Success",
# # # 			f"Applied action '{action}' to {doc.name}. New state is '{doc.workflow_state}'.",
# # # 		)

# # # 		# 5. Return a success message to the frontend.
# # # 		return {
# # # 			"status": "success",
# # # 			"docname": doc.name,
# # # 			"message": f"Sanction {doc.name} has been submitted successfully.",
# # # 			"new_state": doc.workflow_state,
# # # 		}

# # # 	except Exception as e:
# # # 		# If anything goes wrong, cancel the transaction and log the error.
# # # 		frappe.db.rollback()
# # # 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Workflow Error")
# # # 		# Send a clean, user-friendly error back to the frontend.
# # # 		frappe.throw(f"An error occurred during submission: {str(e)}")




# # @frappe.whitelist(allow_guest=True)
# # def get_fund_sanction_form_data(project_proposal=None):
# # 	import frappe
# # 	from frappe import _

# # 	doctype_name = "Fund Sanction"

# # 	# set to None or [] to fetch ALL doctype fields
# # 	allowed_fieldnames = None

# # 	try:
# # 		meta = frappe.get_meta(doctype_name, cached=False)

# # 		fields = []
# # 		for f in meta.fields:
# # 			if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
# # 				continue

# # 			if allowed_fieldnames and f.fieldname not in allowed_fieldnames:
# # 				continue

# # 			fields.append(
# # 				{
# # 					"fieldname": f.fieldname,
# # 					"label": _(f.label),
# # 					"fieldtype": f.fieldtype,
# # 					"default": f.default,
# # 					"mandatory": bool(f.reqd),
# # 					"read_only": bool(f.read_only),
# # 					"hidden": bool(f.hidden),
# # 					"description": _(f.description) if f.description else None,
# # 					"options": f.options,
# # 				}
# # 			)

# # 		prefill_data = {}
# # 		if project_proposal:
# # 			prefill_data["project_proposal"] = project_proposal
# # 			prefill_data["refnum_prj_num"] = project_proposal

# # 		link_options = {}
# # 		for field in fields:
# # 			if field["fieldtype"] == "Link" and field["options"]:
# # 				try:
# # 					linked_doctype = field["options"]
# # 					title_field = frappe.get_meta(linked_doctype).get_title_field()
# # 					options_list = frappe.get_list(
# # 						linked_doctype,
# # 						fields=["name", title_field],
# # 						limit_page_length=1000,
# # 						ignore_permissions=True,
# # 					)
# # 					link_options[field["fieldname"]] = [
# # 						{"value": d["name"], "label": d.get(title_field, d["name"])} for d in options_list
# # 					]
# # 				except Exception:
# # 					link_options[field["fieldname"]] = []

# # 		return {"fields": fields, "prefill_data": prefill_data, "link_options": link_options}

# # 	except Exception as e:
# # 		frappe.log_error(frappe.get_traceback(), _("Error fetching fund sanction form data"))
# # 		return {"error": str(e)}



# # @frappe.whitelist()
# # def save_fund_sanction_data(files=None, **data):
# # 	"""
# # 	Save Fund Sanction data (parent + child tables), skipping all
# # 	ERPNext link validations and saving only file paths.
# # 	"""
# # 	import json
# # 	import base64

# # 	is_new = False  # Initialize is_new flag

# # 	try:
# # 		# Extract child tables and flags
# # 		budget_data = data.pop("sanctioned_budget_breakup", [])
# # 		files_data = data.pop("sanction_related_files", [])
# # 		submit = data.pop("submit", False)
		
# # 		# Handle files payload from argument or data
# # 		files_payload = files
# # 		if not files_payload:
# # 			files_payload = data.pop("files", None)
			
# # 		if isinstance(files_payload, str):
# # 			try:
# # 				files_payload = json.loads(files_payload)
# # 			except Exception:
# # 				pass

# # 		print(f"\nIncoming Fund Sanction save request. Keys: {list(data.keys())}")
# # 		print(f"Budget rows: {len(budget_data)}, File rows: {len(files_data)}")

# # 		# Extract project_reg if present
# # 		project_reg = data.pop("project_reg", None)
# # 		data.pop("project_no", None)

# # 		# Create or fetch the main Fund Sanction document
# # 		if data.get("name"):
# # 			# Logic for updating an existing document
# # 			doc = frappe.get_doc("Fund Sanction", data.get("name"))
# # 			doc.update(data)
# # 			doc.set("sanctioned_budget_breakup", [])
# # 			doc.set("sanction_related_files", [])
# # 			doc.sanction_workflow_status = "Submitted"
# # 		else:
# # 			# Logic for creating a new document
# # 			is_new = True
# # 			data["doctype"] = "Fund Sanction"
# # 			doc = frappe.get_doc(data)

# # 			# --- MODIFICATION: Set initial workflow state for new documents ---
# # 			doc.sanction_workflow_status = "Draft"
# # 			print("✨ New document detected. Setting workflow status to 'Draft'.")

# # 		# Disable validation and permission checks
# # 		doc.flags.ignore_validate = True
# # 		doc.flags.ignore_mandatory = True
# # 		doc.flags.ignore_links = True

# # 		# --- Save main document first ---
# # 		doc.save(ignore_permissions=True)
# # 		print(f"✅ Parent doc saved: {doc.name}")

# # 		# --- Add budget breakup rows (raw data, no validation) ---
# # 		if budget_data:
# # 			for row in budget_data:
# # 				# Remove possible invalid link keys
# # 				row.pop("account_head_name", None)
# # 				doc.append("sanctioned_budget_breakup", row)
# # 			print(f"✅ Added {len(budget_data)} budget rows")

# # 		# --- Add file rows (path only) ---
# # 		# Note: This logic assumes the frontend sends a direct URL in 'sanction_file'.
# # 		if files_data:
# # 			for f in files_data:
# # 				file_path = f.get("sanction_file")
# # 				if not file_path:
# # 					continue
# # 				doc.append(
# # 					"sanction_related_files",
# # 					{"description": f.get("description"), "sanction_file": file_path},
# # 				)
# # 			print(f"✅ Added {len(files_data)} sanction file rows")

# # 		# --- Save again with children ---
# # 		doc.flags.ignore_validate = True
# # 		doc.save(ignore_permissions=True)
# # 		print("✅ Second save complete")

# # 		# --- Handle new file uploads (Base64) ---
# # 		if files_payload and isinstance(files_payload, list):
# # 			for f in files_payload:
# # 				try:
# # 					filename = f.get("filename") or f.get("file_name") or f.get("name")
# # 					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
# # 					is_private = int(f.get("is_private") or 1)

# # 					if not (filename and content_b64):
# # 						continue

# # 					if content_b64.startswith("data:"):
# # 						content_b64 = content_b64.split(",", 1)[1]

# # 					file_content = base64.b64decode(content_b64)

# # 					from rndopsapp.minio import get_rnd_file_service
					
# # 					upload_result = get_rnd_file_service().save_file(
# # 						filename=filename,
# # 						content=file_content,
# # 						is_private=bool(is_private),
# # 						doctype="Project Registration",
# # 						docname=project_reg or doc.project_proposal,
# # 						folder="sanction"
# # 					)

# # 					if upload_result.get("status"):
# # 						file_url = upload_result.get("data", {}).get("file_url")
# # 						# Also add to sanction_related_files child table if needed
# # 						doc.append("sanction_related_files", {
# # 							"description": filename,
# # 							"sanction_file": file_url
# # 						})
# # 					else:
# # 						frappe.log_error(f"File upload failed: {upload_result.get('message')}", "Fund Sanction File Upload")

# # 				except Exception as fe:
# # 					frappe.log_error(
# # 						frappe.get_traceback(),
# # 						f"save_fund_sanction_data: file upload error for {f.get('filename')}",
# # 					)
# # 					continue
			
# # 			# Save again to update child table with new files
# # 			doc.save(ignore_permissions=True)
# # 			frappe.db.commit()

# # 		# --- Submit if requested ---
# # 		if submit:
# # 			doc.submit()
# # 			print("✅ Submitted successfully")

# # 		# --- ✅ Send data to external API (Kafka) ---
# # 		kafka_success = False
# # 		try:
# # 			kafka_success = publish_sanction(doc)
# # 			if kafka_success:
# # 				frappe.msgprint(_("Sanction data synced successfully to external system."), indicator="green")
# # 			else:
# # 				# Rollback: Delete if newly created, otherwise log error
# # 				if is_new:
# # 					doc.delete(ignore_permissions=True)
# # 					frappe.db.rollback()
# # 					frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
# # 				else:
# # 					frappe.msgprint(_("Warning: Kafka sync failed. Data saved locally but not synced."), indicator="orange")
# # 		except frappe.ValidationError:
# # 			raise  # Re-raise validation errors from frappe.throw
# # 		except Exception as e:
# # 			frappe.log_error(frappe.get_traceback(), "Fund Sanction Kafka Sync Error")
# # 			if is_new:
# # 				doc.delete(ignore_permissions=True)
# # 				frappe.db.rollback()
# # 				frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
# # 			else:
# # 				frappe.msgprint(_("Warning: Kafka sync failed. Check Error Log."), indicator="red")

# # 		frappe.db.commit()
# # 		return {"status": "success", "docname": doc.name}

# # 	except Exception as e:
# # 		frappe.db.rollback()
# # 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
# # 		frappe.throw(f"An error occurred while saving the Fund Sanction: {str(e)}")


# # @frappe.whitelist()
# # def get_sanctions_for_project(project_name):
# # 	"""
# # 	Retrieves all Fund Sanction documents for a project,
# # 	and embeds the content of any attached files as a Base64 string.
# # 	"""
# # 	if not project_name:
# # 		return []

# # 	sanction_names = frappe.get_all("Fund Sanction", filters={"project_proposal": project_name}, pluck="name")

# # 	if not sanction_names:
# # 		return []

# # 	sanctions_list = []
# # 	for name in sanction_names:
# # 		# Get the full document as a dictionary
# # 		doc_dict = frappe.get_doc("Fund Sanction", name).as_dict()

# # 		# --- NEW: Process the child table for files ---
# # 		# Check if the 'sanction_related_files' table exists and has entries
# # 		if doc_dict.get("sanction_related_files"):
# # 			# Loop through each file attached to this sanction document
# # 			for file_info in doc_dict.get("sanction_related_files"):
# # 				try:
# # 					# Get the File document from the file_url
# # 					file_url = file_info.get("sanction_file")
# # 					if not file_url:
# # 						continue

# # 					# The actual file document contains the content
# # 					file_doc = frappe.get_doc("File", {"file_url": file_url})

# # 					# Get the raw binary content of the file
# # 					file_content = file_doc.get_content()

# # 					# Encode the binary content into a Base64 string (as utf-8 text)
# # 					base64_content = base64.b64encode(file_content).decode("utf-8")

# # 					# Add the base64 content as a new key to the file's dictionary
# # 					# We also include the file_name for convenience on the frontend
# # 					file_info["file_name"] = file_doc.file_name
# # 					file_info["file_data"] = base64_content

# # 				except Exception as e:
# # 					# If a file is missing from disk or another error occurs, log it
# # 					# and continue without crashing the whole API call.
# # 					print(f"Could not read file for URL {file_url}: {e}")
# # 					file_info["file_data"] = None  # Indicate that the file content is missing

# # 		sanctions_list.append(doc_dict)

# # 	return sanctions_list


# # @frappe.whitelist()
# # def get_fund_sanction_workflow_actions(docname):
# # 	"""
# # 	Get available workflow actions for the current user based on document state.
# # 	"""
# # 	doc = frappe.get_doc("Fund Sanction", docname)
# # 	current_state = doc.workflow_state or "Draft"
# # 	user_roles = frappe.get_roles(frappe.session.user)

# # 	# Fetch the workflow for this doctype
# # 	workflow_name = "fund_sanction_workflow"
	
# # 	if not frappe.db.exists("Workflow", workflow_name):
# # 		return []

# # 	workflow = frappe.get_doc("Workflow", workflow_name)
# # 	allowed_actions = []

# # 	for transition in workflow.get("transitions", []):
# # 		if transition.state != current_state:
# # 			continue

# # 		# Check roles on the transition
# # 		transition_roles = transition.get("allowed") or []
# # 		if isinstance(transition_roles, str):
# # 			transition_roles = [transition_roles]

# # 		# User can perform action if they have allowed role
# # 		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
# # 			allowed_actions.append(transition.action)

# # 	return list(dict.fromkeys(allowed_actions))


# # @frappe.whitelist()
# # def perform_fund_sanction_action(docname, action):
# # 	"""
# # 	Executes the selected workflow action and updates the document state.
# # 	"""
# # 	try:
# # 		doc = frappe.get_doc("Fund Sanction", docname)
# # 		current_state = doc.workflow_state or "Draft"

# # 		# Fetch the workflow for this doctype
# # 		workflow_name = "fund_sanction_workflow"
		
# # 		if not frappe.db.exists("Workflow", workflow_name):
# # 			frappe.throw(f"Workflow '{workflow_name}' not found.")

# # 		workflow = frappe.get_doc("Workflow", workflow_name)

# # 		next_state = None
# # 		transition = None
		
# # 		for t in workflow.transitions:
# # 			if t.state == current_state and t.action == action:
# # 				next_state = t.next_state
# # 				transition = t
# # 				break
		
# # 		if not next_state:
# # 			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

# # 		# Update workflow state
# # 		doc.workflow_state = next_state
# # 		doc.sanction_workflow_status = next_state # Keep legacy field in sync if needed
		
# # 		# Check if next state requires submission (docstatus=1)
# # 		# We check the 'states' table in Workflow to see if doc_status should be 1
# # 		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		
# # 		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
# # 			doc.submit()
# # 		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
# # 			doc.cancel()
# # 		else:
# # 			doc.save(ignore_permissions=True)

# # 		frappe.db.commit()

# # 		return {
# # 			"status": "success",
# # 			"message": f"Action '{action}' completed. New State: {next_state}",
# # 			"docname": docname,
# # 			"workflow_state": next_state,
# # 			"next_actions": get_fund_sanction_workflow_actions(docname)
# # 		}

# # 	except Exception as e:
# # 		frappe.db.rollback()
# # 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Action Error")
# # 		return {"status": "error", "message": str(e)}


# # @frappe.whitelist()
# # def submit_fund_sanction(sanction_name=None, save=None, files=None, project_reg=None, project_no=None, **data):
# # 	"""
# # 	Submit a Fund Sanction document using Workflow transitions.
# # 	If save is True, it first saves the document using the provided data.
# # 	"""
# # 	if save in [True, "true", "True", "1", 1]:
# # 		# Pass explicit parameters back into data for save_fund_sanction_data
# # 		if project_reg is not None:
# # 			data["project_reg"] = project_reg
# # 		if project_no is not None:
# # 			data["project_no"] = project_no
# # 		res = save_fund_sanction_data(files, **data)
# # 		if isinstance(res, dict) and res.get("status") == "success":
# # 			sanction_name = res.get("docname") or res.get("name")
# # 		else:
# # 			return res

# # 	if not sanction_name:
# # 		frappe.throw("Sanction name is required to submit.")

# # 	return perform_fund_sanction_action(sanction_name, "Submit")




# # -=-=-=-=-=-=-=-=-=-=-=-=-



# # Copyright (c) 2025, rndops and contributors
# # For license information, please see license.txt

# # import frappe

# # frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py

# import frappe
# import requests
# from frappe import _
# from frappe.model.document import Document
# from frappe.utils import cint, flt
# from rndopsapp.rndopsapp.kafka.producer import publish_fund_sanction as publish_sanction

# # from frappe.workflow.doctype.workflow.workflow import get_workflow_name


# class FundSanction(Document):
# 	def validate(self):
# 		# Add any specific validation for Fund Sanction here
# 		pass


# API_URL = "http://172.16.135.27:18080/api/sanction-details/addSanctionDetails"


# def send_sanction_details_to_api(doc):
# 	"""
# 	Prepare and send Fund Sanction data to the external API endpoint.
# 	Uses exact match: Budget Head.budget_head == row.account_head -> fetch numeric id.
# 	Prints every step to the terminal for debug visibility.
# 	"""
# 	print("\n=== SEND SANCTION DETAILS TO API START ===")
# 	try:
# 		# Build base payload
# 		payload = {
# 			"projectNumber": getattr(doc, "refnum_prj_num", None),
# 			"sanctionLetterNo": getattr(doc, "sanctioned_letter_no", None),
# 			"sanctionLetterDate": str(getattr(doc, "sanctioned_letter_date"))
# 			if getattr(doc, "sanctioned_letter_date", None)
# 			else None,
# 			"totalSanctionAmount": flt(getattr(doc, "total_sanctioned_amount", 0) or 0.0),
# 			# include top-level totals if present on the doc
# 			"totalFirstYearBudget": flt(getattr(doc, "total_first_year_budget", 0) or 0.0),
# 			"totalSecondYearBudget": flt(getattr(doc, "total_second_year_budget", 0) or 0.0),
# 			"totalThirdYearBudget": flt(getattr(doc, "total_third_year_budget", 0) or 0.0),
# 			"totalFourthYearBudget": flt(getattr(doc, "total_fourth_year_budget", 0) or 0.0),
# 			"totalFifthYearBudget": flt(getattr(doc, "total_fifth_year_budget", 0) or 0.0),
# 			"budgetBreakups": [],
# 		}

# 		print("[PAYLOAD-BASE]", payload)

# 		# Build budgetBreakups list using exact match lookups
# 		print("[STEP] Building budgetBreakups with exact Budget Head.id lookup...")
# 		for row in getattr(doc, "sanctioned_budget_breakup", []) or []:
# 			raw_ah = (getattr(row, "account_head", "") or "").strip()
# 			print(f"   > Processing row idx={getattr(row, 'idx', '<no-idx>')} account_head='{raw_ah}'")

# 			# Exact match lookup: Budget Head where budget_head == raw_ah
# 			try:
# 				account_head_id = frappe.db.get_value("Budget Head", {"budget_head": raw_ah}, "id")
# 			except Exception as e:
# 				print(f"     - DB lookup error for '{raw_ah}': {e}")
# 				account_head_id = None

# 			# Coerce to int if possible, else keep None
# 			if account_head_id not in (None, ""):
# 				try:
# 					account_head_id = int(account_head_id)
# 				except Exception:
# 					# If can't coerce, set None to avoid sending strings
# 					print(
# 						f"     - Warning: account_head_id for '{raw_ah}' is not integer: {account_head_id}; setting to None"
# 					)
# 					account_head_id = None

# 			print(f"     - Mapped '{raw_ah}' -> accountHeadId={account_head_id}")

# 			# Collect per-year budgets (coerce to float via flt)
# 			first = flt(getattr(row, "first_year_budget", 0) or 0)
# 			second = flt(getattr(row, "second_year_budget", 0) or 0)
# 			third = flt(getattr(row, "third_year_budget", 0) or 0)
# 			fourth = flt(getattr(row, "fourth_year_budget", 0) or 0)
# 			fifth = flt(getattr(row, "fifth_year_budget", 0) or 0)
# 			total = first + second + third + fourth + fifth

# 			bh_payload = {
# 				"accountHeadId": account_head_id,
# 				"accountHeadAmount": flt(total),
# 				"firstYearBudget": flt(first),
# 				"secondYearBudget": flt(second),
# 				"thirdYearBudget": flt(third),
# 				"fourthYearBudget": flt(fourth),
# 				"fifthYearBudget": flt(fifth),
# 			}

# 			payload["budgetBreakups"].append(bh_payload)
# 			print(f"     - appended budgetBreakup: {bh_payload}")

# 		print("[FINAL PAYLOAD]", payload)

# 		# POST to external API
# 		print("[STEP] Sending POST to API:", API_URL)
# 		try:
# 			response = requests.post(API_URL, json=payload, timeout=15)
# 			print("     - HTTP status:", response.status_code)
# 			try:
# 				print("     - response JSON:", response.json())
# 			except Exception:
# 				print("     - response text:", response.text)

# 			if response.status_code == 200:
# 				frappe.logger().info(f"✅ Sanction details sent successfully: {response.text}")
# 			else:
# 				frappe.log_error(
# 					f"Failed to send sanction details. Status: {response.status_code}, Response: {response.text}",
# 					"Send Sanction Details API Error",
# 				)
# 		except requests.exceptions.RequestException as re:
# 			print("     - RequestException while posting:", re)
# 			frappe.log_error(frappe.get_traceback(), "Send Sanction Details RequestException")

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Send Sanction Details Exception")
# 		print(f"❌ Error preparing/sending sanction details: {e}")
# 	finally:
# 		print("=== SEND SANCTION DETAILS TO API END ===\n")


# # Whitelisted method to fetch budget details from Project Proposal
# @frappe.whitelist()
# def get_project_proposal_budget_details(project_proposal_name):
# 	try:
# 		if not project_proposal_name:
# 			frappe.throw("Project Proposal name is required to fetch budget details.")

# 		project_proposal = frappe.get_doc("Project Proposal", project_proposal_name)

# 		return {
# 			"proposed_budget_breakup": project_proposal.get("proposed_budget_breakup", []),
# 			"total_first_year_budget": project_proposal.total_first_year_budget,
# 			"total_second_year_budget": project_proposal.total_second_year_budget,
# 			"total_third_year_budget": project_proposal.total_third_year_budget,
# 			"total_fourth_year_budget": project_proposal.total_fourth_year_budget,
# 			"total_fifth_year_budget": project_proposal.total_fifth_year_budget,
# 			"grand_total_proposal": project_proposal.grand_total_proposal,
# 			"total_budget_amount": project_proposal.total_budget_amount,  # <-- Added this field
# 		}

# 	except frappe.DoesNotExistError:
# 		frappe.log_error(
# 			f"Project Proposal {project_proposal_name} not found.", "Fund Sanction Budget Fetch Error"
# 		)
# 		frappe.throw(f"Project Proposal '{project_proposal_name}' not found.")
# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Budget Fetch Error")
# 		frappe.throw(f"An error occurred while fetching budget details: {e}")



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


# # @frappe.whitelist()
# # def submit_fund_sanction(name, action="Submit"):
# # 	"""
# # 	Submits an existing Fund Sanction document by applying a workflow action.

# # 	:param name: The name (ID) of the Fund Sanction document to submit.
# # 	:param action: The workflow action to apply (e.g., "Submit", "Approve").
# # 	               Defaults to "Submit". The frontend can pass this.
# # 	"""
# # 	try:
# # 		# 1. Fetch the specified document from the database.
# # 		doc = frappe.get_doc("Fund Sanction", name)

# # 		# 2. --- Pre-submission Validation ---
# # 		#    These checks ensure the action is valid and secure.

# # 		# Check for user permissions. This is a critical security step.
# # 		# It checks if the current logged-in user has 'submit' permission.
# # 		if not doc.has_permission("submit"):
# # 			frappe.throw("You do not have permission to submit this document.", title="Permission Error")

# # 		# Ensure the document is in a submittable state (docstatus=0 means it's a Draft).
# # 		if doc.docstatus != 0:
# # 			frappe.throw(
# # 				f"Document {doc.name} cannot be submitted as it is not a Draft.", title="Invalid State"
# # 			)

# # 		# Optional but recommended: Check if a workflow is even active for this doctype.
# # 		workflow_name = get_workflow_name("Fund Sanction")
# # 		if not workflow_name:
# # 			frappe.throw(
# # 				"No active workflow named 'sanction_workflow' found for Fund Sanction.",
# # 				title="Workflow Not Found",
# # 			)

# # 		# 3. --- Apply the Workflow Action ---
# # 		#    This is the core of the function. It tells the Frappe workflow engine
# # 		#    to process the transition for the given action.
# # 		#    The engine will automatically:
# # 		#      - Check if the 'action' is valid from the current workflow_state.
# # 		#      - Change the `workflow_state` field (e.g., from 'Draft' to 'Pending Approval').
# # 		#      - Run any code defined in the workflow transition hooks.
# # 		#      - If the new state is configured as a "submitted" state (has doc_status=1),
# # 		#        it will automatically call `doc.submit()` internally.

# # 		frappe.workflow.apply_workflow(doc, action)

# # 		# The apply_workflow function modifies the doc in memory, so we save it.
# # 		doc.save()

# # 		# 4. Commit the changes to the database.
# # 		frappe.db.commit()

# # 		# For debugging: log the successful action
# # 		frappe.log_message(
# # 			"Workflow Success",
# # 			f"Applied action '{action}' to {doc.name}. New state is '{doc.workflow_state}'.",
# # 		)

# # 		# 5. Return a success message to the frontend.
# # 		return {
# # 			"status": "success",
# # 			"docname": doc.name,
# # 			"message": f"Sanction {doc.name} has been submitted successfully.",
# # 			"new_state": doc.workflow_state,
# # 		}

# # 	except Exception as e:
# # 		# If anything goes wrong, cancel the transaction and log the error.
# # 		frappe.db.rollback()
# # 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Workflow Error")
# # 		# Send a clean, user-friendly error back to the frontend.
# # 		frappe.throw(f"An error occurred during submission: {str(e)}")




# @frappe.whitelist(allow_guest=True)
# def get_fund_sanction_form_data(project_proposal=None):
# 	import frappe
# 	from frappe import _

# 	doctype_name = "Fund Sanction"

# 	# set to None or [] to fetch ALL doctype fields
# 	allowed_fieldnames = None

# 	try:
# 		meta = frappe.get_meta(doctype_name, cached=False)

# 		fields = []
# 		for f in meta.fields:
# 			if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
# 				continue

# 			if allowed_fieldnames and f.fieldname not in allowed_fieldnames:
# 				continue

# 			fields.append(
# 				{
# 					"fieldname": f.fieldname,
# 					"label": _(f.label),
# 					"fieldtype": f.fieldtype,
# 					"default": f.default,
# 					"mandatory": bool(f.reqd),
# 					"read_only": bool(f.read_only),
# 					"hidden": bool(f.hidden),
# 					"description": _(f.description) if f.description else None,
# 					"options": f.options,
# 				}
# 			)

# 		prefill_data = {}
# 		if project_proposal:
# 			prefill_data["project_proposal"] = project_proposal
# 			prefill_data["refnum_prj_num"] = project_proposal

# 		link_options = {}
# 		for field in fields:
# 			if field["fieldtype"] == "Link" and field["options"]:
# 				try:
# 					linked_doctype = field["options"]
# 					title_field = frappe.get_meta(linked_doctype).get_title_field()
# 					options_list = frappe.get_list(
# 						linked_doctype,
# 						fields=["name", title_field],
# 						limit_page_length=1000,
# 						ignore_permissions=True,
# 					)
# 					link_options[field["fieldname"]] = [
# 						{"value": d["name"], "label": d.get(title_field, d["name"])} for d in options_list
# 					]
# 				except Exception:
# 					link_options[field["fieldname"]] = []

# 		return {"fields": fields, "prefill_data": prefill_data, "link_options": link_options}

# 	except Exception as e:
# 		frappe.log_error(frappe.get_traceback(), _("Error fetching fund sanction form data"))
# 		return {"error": str(e)}



# @frappe.whitelist()
# def save_fund_sanction_data(files=None, **data):
# 	"""
# 	Save Fund Sanction data (parent + child tables), skipping all
# 	ERPNext link validations and saving only file paths.
# 	"""
# 	import json
# 	import base64

# 	is_new = False  # Initialize is_new flag

# 	try:
# 		# Extract child tables and flags
# 		budget_data = data.pop("sanctioned_budget_breakup", [])
# 		files_data = data.pop("sanction_related_files", [])
# 		submit = data.pop("submit", False)
		
# 		# Handle files payload from argument or data
# 		files_payload = files
# 		if not files_payload:
# 			files_payload = data.pop("files", None)
			
# 		if isinstance(files_payload, str):
# 			try:
# 				files_payload = json.loads(files_payload)
# 			except Exception:
# 				pass

# 		print(f"\nIncoming Fund Sanction save request. Keys: {list(data.keys())}")
# 		print(f"Budget rows: {len(budget_data)}, File rows: {len(files_data)}")

# 		# Extract project_reg if present
# 		project_reg = data.pop("project_reg", None)
# 		data.pop("project_no", None)

# 		# Create or fetch the main Fund Sanction document
# 		if data.get("name"):
# 			# Logic for updating an existing document
# 			doc = frappe.get_doc("Fund Sanction", data.get("name"))
# 			doc.update(data)
# 			doc.set("sanctioned_budget_breakup", [])
# 			doc.set("sanction_related_files", [])
# 			doc.workflow_state = "Submitted"
# 			doc.sanction_workflow_status = "Submitted"
# 		else:
# 			# Logic for creating a new document
# 			is_new = True
# 			data["doctype"] = "Fund Sanction"
# 			doc = frappe.get_doc(data)

# 			# --- MODIFICATION: Set initial workflow state for new documents ---
# 			doc.workflow_state = "Draft"
# 			doc.sanction_workflow_status = "Draft"
# 			print("✨ New document detected. Setting workflow status to 'Draft'.")

# 		# Disable validation and permission checks
# 		doc.flags.ignore_validate = True
# 		doc.flags.ignore_mandatory = True
# 		doc.flags.ignore_links = True

# 		# --- Save main document first ---
# 		doc.save(ignore_permissions=True)
# 		print(f"✅ Parent doc saved: {doc.name}")

# 		# --- Add budget breakup rows (raw data, no validation) ---
# 		if budget_data:
# 			for row in budget_data:
# 				# Remove possible invalid link keys
# 				row.pop("account_head_name", None)
# 				doc.append("sanctioned_budget_breakup", row)
# 			print(f"✅ Added {len(budget_data)} budget rows")

# 		# --- Add file rows (path only) ---
# 		# Note: This logic assumes the frontend sends a direct URL in 'sanction_file'.
# 		if files_data:
# 			for f in files_data:
# 				file_path = f.get("sanction_file")
# 				if not file_path:
# 					continue
# 				doc.append(
# 					"sanction_related_files",
# 					{"description": f.get("description"), "sanction_file": file_path},
# 				)
# 			print(f"✅ Added {len(files_data)} sanction file rows")

# 		# --- Save again with children ---
# 		doc.flags.ignore_validate = True
# 		doc.save(ignore_permissions=True)
# 		print("✅ Second save complete")

# 		# --- Handle new file uploads (Base64) ---
# 		if files_payload and isinstance(files_payload, list):
# 			for f in files_payload:
# 				try:
# 					filename = f.get("filename") or f.get("file_name") or f.get("name")
# 					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
# 					is_private = int(f.get("is_private") or 1)

# 					if not (filename and content_b64):
# 						continue

# 					if content_b64.startswith("data:"):
# 						content_b64 = content_b64.split(",", 1)[1]

# 					file_content = base64.b64decode(content_b64)

# 					from rndopsapp.minio import get_rnd_file_service
					
# 					upload_result = get_rnd_file_service().save_file(
# 						filename=filename,
# 						content=file_content,
# 						is_private=bool(is_private),
# 						doctype="Project Registration",
# 						docname=project_reg or doc.project_proposal,
# 						folder="sanction"
# 					)

# 					if upload_result.get("status"):
# 						file_url = upload_result.get("data", {}).get("file_url")
# 						# Also add to sanction_related_files child table if needed
# 						doc.append("sanction_related_files", {
# 							"description": filename,
# 							"sanction_file": file_url
# 						})
# 					else:
# 						frappe.log_error(f"File upload failed: {upload_result.get('message')}", "Fund Sanction File Upload")

# 				except Exception as fe:
# 					frappe.log_error(
# 						frappe.get_traceback(),
# 						f"save_fund_sanction_data: file upload error for {f.get('filename')}",
# 					)
# 					continue
			
# 			# Save again to update child table with new files
# 			doc.save(ignore_permissions=True)
# 			frappe.db.commit()

# 		# --- Submit if requested ---
# 		if submit:
# 			doc.submit()
# 			print("✅ Submitted successfully")

# 		# --- ✅ Send data to external API (Kafka) ---
# 		kafka_success = False
# 		try:
# 			kafka_success = publish_sanction(doc)
# 			if kafka_success:
# 				frappe.msgprint(_("Sanction data synced successfully to external system."), indicator="green")
# 			else:
# 				# Rollback: Delete if newly created, otherwise log error
# 				if is_new:
# 					doc.delete(ignore_permissions=True)
# 					frappe.db.rollback()
# 					frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
# 				else:
# 					frappe.msgprint(_("Warning: Kafka sync failed. Data saved locally but not synced."), indicator="orange")
# 		except frappe.ValidationError:
# 			raise  # Re-raise validation errors from frappe.throw
# 		except Exception as e:
# 			frappe.log_error(frappe.get_traceback(), "Fund Sanction Kafka Sync Error")
# 			if is_new:
# 				doc.delete(ignore_permissions=True)
# 				frappe.db.rollback()
# 				frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
# 			else:
# 				frappe.msgprint(_("Warning: Kafka sync failed. Check Error Log."), indicator="red")

# 		frappe.db.commit()
# 		return {"status": "success", "docname": doc.name}

# 	except Exception as e:
# 		frappe.db.rollback()
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
# 		frappe.throw(f"An error occurred while saving the Fund Sanction: {str(e)}")


# @frappe.whitelist()
# def get_sanctions_for_project(project_name):
# 	"""
# 	Retrieves all Fund Sanction documents for a project,
# 	and embeds the content of any attached files as a Base64 string.
# 	"""
# 	if not project_name:
# 		return []

# 	sanction_names = frappe.get_all("Fund Sanction", filters={"project_proposal": project_name}, pluck="name")

# 	if not sanction_names:
# 		return []

# 	sanctions_list = []
# 	for name in sanction_names:
# 		# Get the full document as a dictionary
# 		doc_dict = frappe.get_doc("Fund Sanction", name).as_dict()

# 		# --- NEW: Process the child table for files ---
# 		# Check if the 'sanction_related_files' table exists and has entries
# 		if doc_dict.get("sanction_related_files"):
# 			# Loop through each file attached to this sanction document
# 			for file_info in doc_dict.get("sanction_related_files"):
# 				try:
# 					# Get the File document from the file_url
# 					file_url = file_info.get("sanction_file")
# 					if not file_url:
# 						continue

# 					# The actual file document contains the content
# 					file_doc = frappe.get_doc("File", {"file_url": file_url})

# 					# Get the raw binary content of the file
# 					file_content = file_doc.get_content()

# 					# Encode the binary content into a Base64 string (as utf-8 text)
# 					base64_content = base64.b64encode(file_content).decode("utf-8")

# 					# Add the base64 content as a new key to the file's dictionary
# 					# We also include the file_name for convenience on the frontend
# 					file_info["file_name"] = file_doc.file_name
# 					file_info["file_data"] = base64_content

# 				except Exception as e:
# 					# If a file is missing from disk or another error occurs, log it
# 					# and continue without crashing the whole API call.
# 					print(f"Could not read file for URL {file_url}: {e}")
# 					file_info["file_data"] = None  # Indicate that the file content is missing

# 		sanctions_list.append(doc_dict)

# 	return sanctions_list


# @frappe.whitelist()
# def get_fund_sanction_workflow_actions(docname):
# 	"""
# 	Get available workflow actions for the current user based on document state.
# 	"""
# 	doc = frappe.get_doc("Fund Sanction", docname)
# 	current_state = doc.workflow_state or "Draft"
# 	user_roles = frappe.get_roles(frappe.session.user)

# 	# Fetch the workflow for this doctype
# 	workflow_name = "fund_sanction_workflow"
	
# 	if not frappe.db.exists("Workflow", workflow_name):
# 		return []

# 	workflow = frappe.get_doc("Workflow", workflow_name)
# 	allowed_actions = []

# 	for transition in workflow.get("transitions", []):
# 		if transition.state != current_state:
# 			continue

# 		# Check roles on the transition
# 		transition_roles = transition.get("allowed") or []
# 		if isinstance(transition_roles, str):
# 			transition_roles = [transition_roles]

# 		# User can perform action if they have allowed role
# 		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
# 			allowed_actions.append(transition.action)

# 	return list(dict.fromkeys(allowed_actions))


# @frappe.whitelist()
# def perform_fund_sanction_action(docname, action):
# 	"""
# 	Executes the selected workflow action and updates the document state.
# 	"""
# 	try:
# 		doc = frappe.get_doc("Fund Sanction", docname)
# 		current_state = doc.workflow_state or "Draft"

# 		# Fetch the workflow for this doctype
# 		workflow_name = "fund_sanction_workflow"
		
# 		if not frappe.db.exists("Workflow", workflow_name):
# 			frappe.throw(f"Workflow '{workflow_name}' not found.")

# 		workflow = frappe.get_doc("Workflow", workflow_name)

# 		next_state = None
# 		transition = None
		
# 		for t in workflow.transitions:
# 			if t.state == current_state and t.action == action:
# 				next_state = t.next_state
# 				transition = t
# 				break
		
# 		if not next_state:
# 			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

# 		# Update workflow state
# 		doc.workflow_state = next_state
# 		doc.sanction_workflow_status = next_state # Keep legacy field in sync if needed
		
# 		# Check if next state requires submission (docstatus=1)
# 		# We check the 'states' table in Workflow to see if doc_status should be 1
# 		state_doc = next((s for s in workflow.states if s.state == next_state), None)
# 		new_docstatus = int(state_doc.doc_status or 0) if state_doc else 0

# 		workflow_field = workflow.workflow_state_field or "workflow_state"
# 		update_fields = {
# 			workflow_field: next_state,
# 			"sanction_workflow_status": next_state
# 		}

# 		if new_docstatus != int(doc.docstatus):
# 			update_fields["docstatus"] = new_docstatus

# 		if (
# 			state_doc
# 			and getattr(state_doc, "update_field", None)
# 			and state_doc.update_field != workflow_field
# 			and state_doc.update_value is not None
# 		):
# 			update_fields[state_doc.update_field] = state_doc.update_value

# 		frappe.db.set_value(
# 			"Fund Sanction",
# 			docname,
# 			update_fields,
# 			update_modified=True,
# 		)

# 		doc.reload()
# 		doc.add_comment("Workflow", _(next_state))

# 		frappe.db.commit()

# 		return {
# 			"status": "success",
# 			"message": f"Action '{action}' completed. New State: {next_state}",
# 			"docname": docname,
# 			"workflow_state": next_state,
# 			"next_actions": get_fund_sanction_workflow_actions(docname)
# 		}

# 	except Exception as e:
# 		frappe.db.rollback()
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Action Error")
# 		return {"status": "error", "message": str(e)}


# @frappe.whitelist()
# def submit_fund_sanction(sanction_name=None, save=None, files=None, project_reg=None, project_no=None, **data):
# 	"""
# 	Submit a Fund Sanction document using Workflow transitions.
# 	If save is True, it first saves the document using the provided data.
# 	"""
# 	if save in [True, "true", "True", "1", 1]:
# 		# Pass explicit parameters back into data for save_fund_sanction_data
# 		if project_reg is not None:
# 			data["project_reg"] = project_reg
# 		if project_no is not None:
# 			data["project_no"] = project_no
# 		res = save_fund_sanction_data(files, **data)
# 		if isinstance(res, dict) and res.get("status") == "success":
# 			sanction_name = res.get("docname") or res.get("name")
# 		else:
# 			return res

# 	if not sanction_name:
# 		frappe.throw("Sanction name is required to submit.")

# 	return perform_fund_sanction_action(sanction_name, "Submit")

# /-=-=-==============================================================================



# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe

# frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt
from rndopsapp.rndopsapp.kafka.producer import publish_fund_sanction as publish_sanction

# from frappe.workflow.doctype.workflow.workflow import get_workflow_name


class FundSanction(Document):
	def validate(self):
		# Add any specific validation for Fund Sanction here
		pass


API_URL = "http://172.16.135.27:18080/api/sanction-details/addSanctionDetails"


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



@frappe.whitelist()
def save_fund_sanction_data(data):
	"""
	Save Fund Sanction form data to the backend.
	Expects 'data' as a JSON string from frontend.
	"""
	import json

	try:
		# Parse JSON string if needed
		if isinstance(data, str):
			data = json.loads(data)

		# Create or update Fund Sanction document
		docname = data.get("name")  # If editing an existing doc
		if docname:
			fs_doc = frappe.get_doc("Fund Sanction", docname)
		else:
			fs_doc = frappe.new_doc("Fund Sanction")

		# Map simple fields
		simple_fields = [
			"amended_from",
			"project_proposal",
			"total_sanctioned_amount",
			"sanctioned_letter_no",
			"sanctioned_letter_date",
			"total_first_year_budget_1",
			"total_second_year_budget_1",
			"total_third_year_budget_1",
			"total_fourth_year_budget_1",
			"total_fifth_year_budget_1",
			"grand_total_proposal_1",
			"have_fund_details",
			"project_type_linked",
			"is_gst_invoice_issued",
			"invoice_details",
			"amount_received",
			"iitg_bank_account_number",
		]

		for field in simple_fields:
			if field in data:
				setattr(fs_doc, field, data[field] if data[field] != "null" else None)

		# Handle child tables
		child_tables = {
			"sanctioned_budget_breakup": "Sanctioned Budget Breakup",
			"fund_transactions": "Fund Transactions",
			"received_amount_breakup": "Received Amount Breakup",
		}

		for field, child_doctype in child_tables.items():
			if field in data:
				items = json.loads(data[field]) if isinstance(data[field], str) else data[field]
				fs_doc.set(field, [])  # clear existing child table
				for item in items:
					child = fs_doc.append(field, item)

		# Handle file attachments
		if "sanction_related_files_meta" in data:
			files_meta = json.loads(data["sanction_related_files_meta"])
			for fmeta in files_meta:
				# If file content comes as file_0, file_1, etc.
				file_key = f"file_{files_meta.index(fmeta)}"
				file_data = data.get(file_key)
				if file_data:
					# Save file in Frappe file system
					file_doc = frappe.get_doc(
						{
							"doctype": "File",
							"file_name": fmeta.get("description", f"file_{file_key}"),
							"attached_to_doctype": "Fund Sanction",
							"attached_to_name": fs_doc.name,
							"content": file_data,  # file content in base64
						}
					)
					file_doc.insert()

		fs_doc.save()
		frappe.db.commit()
		return {"status": "success", "name": fs_doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error saving Fund Sanction"))
		return {"status": "error", "message": str(e)}


# @frappe.whitelist()
# def submit_fund_sanction(name, action="Submit"):
# 	"""
# 	Submits an existing Fund Sanction document by applying a workflow action.

# 	:param name: The name (ID) of the Fund Sanction document to submit.
# 	:param action: The workflow action to apply (e.g., "Submit", "Approve").
# 	               Defaults to "Submit". The frontend can pass this.
# 	"""
# 	try:
# 		# 1. Fetch the specified document from the database.
# 		doc = frappe.get_doc("Fund Sanction", name)

# 		# 2. --- Pre-submission Validation ---
# 		#    These checks ensure the action is valid and secure.

# 		# Check for user permissions. This is a critical security step.
# 		# It checks if the current logged-in user has 'submit' permission.
# 		if not doc.has_permission("submit"):
# 			frappe.throw("You do not have permission to submit this document.", title="Permission Error")

# 		# Ensure the document is in a submittable state (docstatus=0 means it's a Draft).
# 		if doc.docstatus != 0:
# 			frappe.throw(
# 				f"Document {doc.name} cannot be submitted as it is not a Draft.", title="Invalid State"
# 			)

# 		# Optional but recommended: Check if a workflow is even active for this doctype.
# 		workflow_name = get_workflow_name("Fund Sanction")
# 		if not workflow_name:
# 			frappe.throw(
# 				"No active workflow named 'sanction_workflow' found for Fund Sanction.",
# 				title="Workflow Not Found",
# 			)

# 		# 3. --- Apply the Workflow Action ---
# 		#    This is the core of the function. It tells the Frappe workflow engine
# 		#    to process the transition for the given action.
# 		#    The engine will automatically:
# 		#      - Check if the 'action' is valid from the current workflow_state.
# 		#      - Change the `workflow_state` field (e.g., from 'Draft' to 'Pending Approval').
# 		#      - Run any code defined in the workflow transition hooks.
# 		#      - If the new state is configured as a "submitted" state (has doc_status=1),
# 		#        it will automatically call `doc.submit()` internally.

# 		frappe.workflow.apply_workflow(doc, action)

# 		# The apply_workflow function modifies the doc in memory, so we save it.
# 		doc.save()

# 		# 4. Commit the changes to the database.
# 		frappe.db.commit()

# 		# For debugging: log the successful action
# 		frappe.log_message(
# 			"Workflow Success",
# 			f"Applied action '{action}' to {doc.name}. New state is '{doc.workflow_state}'.",
# 		)

# 		# 5. Return a success message to the frontend.
# 		return {
# 			"status": "success",
# 			"docname": doc.name,
# 			"message": f"Sanction {doc.name} has been submitted successfully.",
# 			"new_state": doc.workflow_state,
# 		}

# 	except Exception as e:
# 		# If anything goes wrong, cancel the transaction and log the error.
# 		frappe.db.rollback()
# 		frappe.log_error(frappe.get_traceback(), "Fund Sanction Workflow Error")
# 		# Send a clean, user-friendly error back to the frontend.
# 		frappe.throw(f"An error occurred during submission: {str(e)}")




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
	import base64

	is_new = False  # Initialize is_new flag

	try:
		# Extract child tables and flags
		budget_data = data.pop("sanctioned_budget_breakup", [])
		files_data = data.pop("sanction_related_files", [])
		submit = data.pop("submit", False)
		
		# Handle files payload from argument or data
		files_payload = files
		if not files_payload:
			files_payload = data.pop("files", None)
			
		if isinstance(files_payload, str):
			try:
				files_payload = json.loads(files_payload)
			except Exception:
				pass

		print(f"\nIncoming Fund Sanction save request. Keys: {list(data.keys())}")
		print(f"Budget rows: {len(budget_data)}, File rows: {len(files_data)}")

		# Extract project_reg if present
		project_reg = data.pop("project_reg", None)
		data.pop("project_no", None)

		# Create or fetch the main Fund Sanction document
		if data.get("name"):
			# Logic for updating an existing document
			doc = frappe.get_doc("Fund Sanction", data.get("name"))
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

		# --- Handle new file uploads (Base64) ---
		if files_payload and isinstance(files_payload, list):
			for f in files_payload:
				try:
					filename = f.get("filename") or f.get("file_name") or f.get("name")
					content_b64 = f.get("content") or f.get("file_data") or f.get("data") or ""
					is_private = int(f.get("is_private") or 1)

					if not (filename and content_b64):
						continue

					if content_b64.startswith("data:"):
						content_b64 = content_b64.split(",", 1)[1]

					file_content = base64.b64decode(content_b64)

					from rndopsapp.minio import get_rnd_file_service
					
					upload_result = get_rnd_file_service().save_file(
						filename=filename,
						content=file_content,
						is_private=bool(is_private),
						doctype="Project Registration",
						docname=project_reg or doc.project_proposal,
						folder="sanction"
					)

					if upload_result.get("status"):
						file_url = upload_result.get("data", {}).get("file_url")
						# Also add to sanction_related_files child table if needed
						doc.append("sanction_related_files", {
							"description": filename,
							"sanction_file": file_url
						})
					else:
						frappe.log_error(f"File upload failed: {upload_result.get('message')}", "Fund Sanction File Upload")

				except Exception as fe:
					frappe.log_error(
						frappe.get_traceback(),
						f"save_fund_sanction_data: file upload error for {f.get('filename')}",
					)
					continue
			
			# Save again to update child table with new files
			doc.save(ignore_permissions=True)
			frappe.db.commit()

		# --- Submit if requested ---
		if submit:
			doc.submit()
			print("✅ Submitted successfully")

		# --- ✅ Send data to external API (Kafka) ---
		kafka_success = False
		try:
			kafka_success = publish_sanction(doc)
			if kafka_success:
				frappe.msgprint(_("Sanction data synced successfully to external system."), indicator="green")
			else:
				# Rollback: Delete if newly created, otherwise log error
				if is_new:
					doc.delete(ignore_permissions=True)
					frappe.db.rollback()
					frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
				else:
					frappe.msgprint(_("Warning: Kafka sync failed. Data saved locally but not synced."), indicator="orange")
		except frappe.ValidationError:
			raise  # Re-raise validation errors from frappe.throw
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Fund Sanction Kafka Sync Error")
			if is_new:
				doc.delete(ignore_permissions=True)
				frappe.db.rollback()
				frappe.throw(_("Kafka sync failed. Fund Sanction was not saved. Please try again."))
			else:
				frappe.msgprint(_("Warning: Kafka sync failed. Check Error Log."), indicator="red")

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Save Error")
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

		frappe.db.set_value(
			"Fund Sanction",
			docname,
			update_fields,
			update_modified=True,
		)

		doc.reload()
		doc.add_comment("Workflow", _(next_state))

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_fund_sanction_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Action Error")
		return {"status": "error", "message": str(e)}


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
		res = save_fund_sanction_data(files, **data)
		if isinstance(res, dict) and res.get("status") == "success":
			sanction_name = res.get("docname") or res.get("name")
		else:
			return res

	if not sanction_name:
		frappe.throw("Sanction name is required to submit.")

	return perform_fund_sanction_action(sanction_name, "Submit")
