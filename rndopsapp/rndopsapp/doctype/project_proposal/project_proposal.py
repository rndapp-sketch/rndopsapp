# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_proposal/project_proposal.py


import frappe
from frappe.utils import get_url, nowdate, get_datetime, get_datetime_str, formatdate, now_datetime
from frappe.model.document import Document
from frappe.model.workflow import get_transitions
from frappe.exceptions import ValidationError
from bs4 import BeautifulSoup
from frappe import _
from frappe.utils.file_manager import save_file

class ProjectProposal(Document):
    def validate(self):
        pass
    def on_submit(self):
        pass

@frappe.whitelist()
def get_initial_endorsement_html(docname, print_format):
    """
    Generates HTML and aggressively strips System Scripts/Styles for the Text Editor.
    """
    try:
        doc = frappe.get_doc('Project Proposal', docname)

        if not frappe.db.exists("Print Format", print_format):
            frappe.throw(f"Print Format '{print_format}' does not exist.")

        # 1. Set Flag for Jinja (Hides Logo/Header in the template)
        doc.flags.for_editor = True 

        # 2. Get Raw HTML
        raw_html = frappe.get_print(
            'Project Proposal',
            doc.name,
            print_format=print_format,
            no_letterhead=True 
        )

        # 3. CLEANING PROCESS using BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # Remove ALL <script> tags (This deletes the addEventListener code)
        for script in soup.find_all("script"):
            script.decompose()

        # Optional: Remove <style> tags if you want purely inline styles
        # This prevents Frappe's default CSS from messing up the editor
        for style in soup.find_all("style"):
            style.decompose()

        # 4. Extract only the body content
        # Frappe often wraps output in <html><body>...</body></html>. 
        # We only want what's inside <body>.
        if soup.body:
            clean_html = soup.body.decode_contents()
        else:
            clean_html = str(soup)

        return {"html": clean_html}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in get_initial_endorsement_html")
        frappe.throw(_("Error generating endorsement preview: {0}").format(str(e)))



@frappe.whitelist()
def save_edited_endorsement_and_submit_for_approval(docname, edited_content, print_format):
    """
    Saves the edited endorsement content, updates status to 'Pending Approval',
    generates PDF, and forwards it to the 'Dean, RnD' role via ToDo (No Email).
    """
    try:
        doc = frappe.get_doc('Project Proposal', docname)

        # 1. Update the 'edited_endorsement_content' field
        doc.edited_endorsement_content = edited_content

        # 2. Update endorsement_status
        doc.endorsement_status = 'Pending Approval'
        doc.save(ignore_permissions=True) 

        # 3. Generate PDF and attach it
        try:
            # Use as_pdf=True to get binary PDF data
            pdf_data = frappe.get_print(
                'Project Proposal',
                doc.name,
                print_format=print_format, 
                as_pdf=True,
                no_letterhead=False
            )

            file_name = f"{doc.name}-Endorsement-{get_datetime_str()}.pdf"
            pdf_file = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Project Proposal",
                "attached_to_name": doc.name,
                "attached_to_field": "endorsement_attachment", 
                "content": pdf_data,
                "is_private": 1 
            })
            pdf_file.insert(ignore_permissions=True) 
            frappe.db.commit() 

        except Exception as pdf_error:
            frappe.log_error(frappe.get_traceback(), f"Error generating or attaching PDF for {doc.name}")
            frappe.msgprint(_("Could not generate or attach PDF endorsement. Please check logs."))

        # 4. Forward to Dean, RnD role via ToDo
        dean_rnd_users = frappe.get_list('User', filters={'roles': ['Dean, RnD'], 'enabled': 1}, pluck='name')
        if dean_rnd_users:
            for user_id in dean_rnd_users:
                # Check if a ToDo already exists to avoid duplicates
                exists = frappe.db.exists("ToDo", {
                    "reference_name": doc.name,
                    "reference_type": "Project Proposal",
                    "owner": user_id,
                    "status": "Open"
                })
                if not exists:
                    frappe.get_doc({
                        "doctype": "ToDo",
                        "description": f"Review Endorsement for Project: {doc.project_title}",
                        "assigned_by": frappe.session.user,
                        "owner": user_id,
                        "reference_type": "Project Proposal",
                        "reference_name": doc.name,
                        "status": "Open",
                        "priority": "High"
                    }).insert(ignore_permissions=True)
        else:
            frappe.log_warning(f"No active users found for 'Dean, RnD' role to assign ToDo for {doc.name}")

        frappe.db.commit() 
        return {"success": True, "message": "Endorsement saved and submitted for approval."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in save_edited_endorsement_and_submit_for_approval")
        frappe.db.rollback() 
        frappe.throw(_("Error processing endorsement: {0}").format(str(e)))

@frappe.whitelist()
def process_endorsement(docname, action):
    try:
        doc = frappe.get_doc("Project Proposal", docname)
        
        if action == 'Approved':
            doc.endorsement_status = 'Approved'
            
            # Set Approver Details
            doc.approver_name = frappe.session.user_fullname
            doc.approver_email = frappe.session.user # Important for fetching signature
            doc.approver_date = now_datetime()
            
            doc.save(ignore_permissions=True)
            
            # --- REGENERATE PDF WITH SIGNATURE ---
            # Now that status is 'Approved', the Print Format will render the signature image.
            # We overwrite the previous PDF.
            pdf_data = frappe.get_print(
                'Project Proposal',
                doc.name,
                print_format='Project Endorsement Letterhead', # Ensure name matches exactly
                as_pdf=True,
                no_letterhead=False
            )
            
            file_name = f"{doc.name}-Endorsement-FINAL.pdf"
            
            # Create/Overwrite attachment
            pdf_file = frappe.get_doc({
                "doctype": "File",
                "file_name": file_name,
                "attached_to_doctype": "Project Proposal",
                "attached_to_name": doc.name,
                "attached_to_field": "endorsement_attachment",
                "content": pdf_data,
                "is_private": 1
            })
            pdf_file.insert(ignore_permissions=True)
            
            frappe.msgprint("Project Endorsement Approved and Digitally Signed PDF generated.")
            
        elif action == 'Rejected':
            doc.endorsement_status = 'Rejected'
            doc.save(ignore_permissions=True)
            frappe.msgprint("Project Endorsement Rejected.")
            
        elif action == 'Put Back':
            doc.endorsement_status = 'Put Back'
            # Clear approver details
            doc.approver_name = None
            doc.approver_email = None
            doc.approver_date = None
            doc.save(ignore_permissions=True)
            frappe.msgprint("Project Endorsement Put Back for corrections.")

        frappe.db.commit()
        return {"success": True, "message": f"Endorsement {action} successfully."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Action Error")
        frappe.db.rollback()
        frappe.throw(f"Error processing endorsement action: {e}")        


@frappe.whitelist()
def get_project_proposal_fields(doc_name=None):
	"""
	Return Project Proposal field metadata + prefill data.
	Similar to get_reimbursement_fields but adapted for Project Proposal.
	"""
	doctype_name = "Project Proposal"
	try:
		meta = frappe.get_meta(doctype_name)
	except Exception:
		frappe.throw(_("DocType Project Proposal not found."))

	fields = []
	
	# --- 1. Build Fields List (recurse for child tables) ---
	for f in meta.fields:
		if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
			continue
			
		field_data = {
			"fieldname": f.fieldname,
			"label": _(f.label),
			"fieldtype": f.fieldtype,
			"options": getattr(f, "options", None),
			"mandatory": getattr(f, "reqd", False),
			"hidden": getattr(f, "hidden", False),
			"read_only": getattr(f, "read_only", False),
			"description": getattr(f, "description", "") or "",
			"default": getattr(f, "default", "")
		}
		
		# Child table handling
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.fields:
					if cf.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
						continue
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": _(cf.label),
						"fieldtype": cf.fieldtype,
						"options": getattr(cf, "options", None),
						"mandatory": getattr(cf, "reqd", False),
						"hidden": getattr(cf, "hidden", False),
						"read_only": getattr(cf, "read_only", False),
						"in_list_view": getattr(cf, "in_list_view", False),
						"default": getattr(cf, "default", "")
					})
				field_data["child_fields"] = child_fields
			except Exception:
				pass
				
		fields.append(field_data)

	# --- 2. Link Options (Generic) ---
	link_options = {}
	for f in fields:
		if f["fieldtype"] == "Link" and f["options"]:
			try:
				doctype = f["options"]
				# Skip huge tables unless necessary, or limit them
				if doctype == "[Select]": continue

				# Try to get title field
				linked_meta = frappe.get_meta(doctype)
				title_field = linked_meta.get_title_field() or "name"
				
				# Fetch options
				options_list = frappe.get_list(
					doctype,
					fields=["name", title_field],
					limit_page_length=200,
					order_by=f"{title_field} asc" if title_field != "name" else "name asc"
				)
				
				link_options[f["fieldname"]] = [
					{"value": item["name"], "label": item.get(title_field, item["name"])}
					for item in options_list
				]
			except Exception:
				link_options[f["fieldname"]] = []

	# --- 3. Prefill Logic (User Details) ---
	prefill_data = {}
	if frappe.session.user != "Guest":
		try:
			user_email = frappe.session.user
			user_doc = frappe.get_doc("User", user_email)
			
			# Map User fields to potential Proposal fields
			# Adjust these keys based on actual Project Proposal field names if known.
			# Using standard names from Project Registration as requested.
			prefill_data = {
				"pi_userid": user_email,
				"principal_investigator_name": user_doc.full_name,
				"pi_employee_id": getattr(user_doc, "employee_id", None),
				"designation": getattr(user_doc, "designation_name", None),
				"applicant_department": getattr(user_doc, "department_name", None),
				"email": user_email,
				"applicant_name": user_doc.full_name
			}
		except Exception:
			pass


	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
	}

import json
@frappe.whitelist()
def save_project_proposal(data):
	"""
	Save Project Proposal data (parent + child tables).
	Expects 'data' as a JSON string or dict.
	Supports file uploads for 'Attach' fields if passed as {file_name, file_data}.
	"""
	print("\n=== SAVE PROJECT PROPOSAL START ===")
	try:
		print(f"[DEBUG] Raw data type: {type(data)}")
		if isinstance(data, str):
			print("[DEBUG] Data is string, parsing JSON...")
			data = json.loads(data)
		print(f"[DEBUG] Parsed data keys: {list(data.keys())}")

		docname = data.get("name")
		print(f"[DEBUG] docname from data: {docname}")
		
		if docname:
			print(f"[DEBUG] Fetching existing doc: {docname}")
			doc = frappe.get_doc("Project Proposal", docname)
		else:
			print("[DEBUG] Creating new Project Proposal doc")
			doc = frappe.new_doc("Project Proposal")
		
		print(f"[DEBUG] Doc is_new: {doc.is_new()}, doc.name: {doc.name}")

		# Get metadata to filter valid fields
		meta = frappe.get_meta("Project Proposal")
		print(f"[DEBUG] Got metadata for Project Proposal")
		
		# Iterate over data and set fields
		print("[DEBUG] Starting field iteration...")
		for fieldname, value in data.items():
			if not meta.has_field(fieldname):
				print(f"[DEBUG] Skipping non-existent field: {fieldname}")
				continue
				
			df = meta.get_field(fieldname)
			print(f"[DEBUG] Processing field: {fieldname}, fieldtype: {df.fieldtype}, value type: {type(value)}")
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				print(f"[DEBUG] Processing child table: {fieldname}, rows: {len(value)}")
				# Clear existing rows if updating
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				print(f"[DEBUG] Child doctype: {df.options}")
				
				for idx, child_row in enumerate(value):
					print(f"[DEBUG] Processing child row {idx}: {list(child_row.keys()) if isinstance(child_row, dict) else child_row}")
					
					# Handle Phone fields - clear if invalid
					import re
					print(f"[DEBUG] Checking fields for child row {idx}...")
					for cf in child_meta.fields:
						# print(f"[DEBUG] Checking field {cf.fieldname} ({cf.fieldtype})") # Uncomment if needed, but might be too verbose
						if cf.fieldtype == "Phone" and child_row.get(cf.fieldname):
							phone_val = child_row[cf.fieldname]
							print(f"[DEBUG] Found Phone field '{cf.fieldname}' with value: '{phone_val}'")
							
							# Frappe requires valid phone numbers with country code (starts with +)
							if isinstance(phone_val, str):
								phone_val = phone_val.strip()
								digits_only = re.sub(r'\D', '', phone_val)  # Remove non-digits
								
								if not phone_val:
									print(f"[DEBUG] Phone field '{cf.fieldname}' is empty")
									child_row[cf.fieldname] = "" # Set to empty string to trigger mandatory check if reqd
								elif not phone_val.startswith("+"):
									# No country code - assume +91-
									print(f"[DEBUG] Phone field '{cf.fieldname}' has no country code, prepending +91-: {phone_val}")
									child_row[cf.fieldname] = f"+91-{phone_val}"
								elif len(digits_only) < 6:
									# Has + but not enough digits (e.g., +91- or +91)
									# If it matches the default "+91-", clear it to empty string
									if phone_val == "+91-":
										print(f"[DEBUG] Phone field '{cf.fieldname}' is default '+91-', clearing to empty")
										child_row[cf.fieldname] = ""
									else:
										print(f"[DEBUG] Phone field '{cf.fieldname}' invalid (too few digits: {len(digits_only)}), clearing: {phone_val}")
										child_row[cf.fieldname] = ""
								else:
									print(f"[DEBUG] Phone field '{cf.fieldname}' seems valid: {phone_val}")
							elif not phone_val:
								child_row[cf.fieldname] = ""
					
					# Check for file uploads in child row fields
					for cf in child_meta.fields:
						if cf.fieldtype == "Attach" and child_row.get(cf.fieldname):
							f_val = child_row[cf.fieldname]
							print(f"[DEBUG] Found Attach field in child: {cf.fieldname}, value type: {type(f_val)}")
							if isinstance(f_val, dict) and f_val.get("file_name") and f_val.get("file_data"):
								print(f"[DEBUG] Attempting file upload for child: {f_val.get('file_name')}")
								try:
									saved_file = save_file(
										f_val["file_name"],
										f_val["file_data"],
										df.options, # Child DocType
										None, # Child docs don't have name yet usually, or we attach to parent? 
										# Actually save_file usually attaches to parent if child is not saved.
										# But for new child rows, it's tricky. 
										# Best practice: Attach to parent doc (doc.doctype, doc.name)
										# But if doc is new, it has no name. 
										# If doc is new, we might need to save it first? 
										# Or just save file as unattached (is_private=0) and link URL.
										decode=True,
										is_private=0,
										df=cf.fieldname
									)
									child_row[cf.fieldname] = saved_file.file_url
									print(f"[DEBUG] Child file saved: {saved_file.file_url}")
								except Exception as e:
									print(f"[DEBUG] Child file upload error: {str(e)}")
									frappe.log_error(f"Child Table File Upload Error: {str(e)}")
									child_row[cf.fieldname] = None

					doc.append(fieldname, child_row)
					print(f"[DEBUG] Appended child row {idx} to {fieldname}")
					
			# Handle Attach fields (Base64) - if sent as dict {file_name, file_data}
			elif df.fieldtype == "Attach" and isinstance(value, dict) and value.get("file_data"):
				print(f"[DEBUG] Processing Attach field: {fieldname}, file_name: {value.get('file_name')}")
				try:
					saved_file = save_file(
						value["file_name"],
						value["file_data"],
						doc.doctype,
						doc.name, # If new, this might be None/temp. save_file handles it? 
						# If doc.name is None, save_file might error if attached_to_name is required.
						# However, we can save without attachment or rely on frappe.new_doc behavior.
						# If doc is new, we haven't saved it yet. 
						# Strategy: Save file, get URL, set field.
						decode=True,
						is_private=0,
						df=fieldname
					)
					doc.set(fieldname, saved_file.file_url)
					print(f"[DEBUG] File saved: {saved_file.file_url}")
				except Exception as e:
					print(f"[DEBUG] File upload error: {str(e)}")
					frappe.log_error(f"File Upload Error: {str(e)}")
					# Don't set the field if upload fails
					pass
				
			# Standard fields
			else:
				print(f"[DEBUG] Setting standard field: {fieldname} = {value if not isinstance(value, str) or len(str(value)) < 100 else str(value)[:100] + '...'}")
				doc.set(fieldname, value)

		# Set owner if new
		if doc.is_new():
			print(f"[DEBUG] Setting owner for new doc: {frappe.session.user}")
			doc.owner = frappe.session.user

		print("[DEBUG] Setting flags.ignore_permissions = True")
		doc.flags.ignore_permissions = True
		
		print("[DEBUG] Calling doc.save()...")
		doc.save()
		print(f"[DEBUG] Doc saved successfully: {doc.name}")
		
		print("[DEBUG] Calling frappe.db.commit()...")
		frappe.db.commit()
		print("=== SAVE PROJECT PROPOSAL END (SUCCESS) ===\n")

		return {"status": "success", "docname": doc.name, "message": "Project Proposal saved successfully."}

	except Exception as e:
		print(f"[DEBUG] EXCEPTION: {str(e)}")
		print(f"[DEBUG] Traceback: {frappe.get_traceback()}")
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Proposal Save Error")
		print("=== SAVE PROJECT PROPOSAL END (ERROR) ===\n")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_project_proposal(docname):
	"""
	Submit a Project Proposal document using Workflow transitions.
	"""
	print("\n=== SUBMIT PROJECT PROPOSAL START ===")
	print(f"[DEBUG] docname: {docname}")
	try:
		doc = frappe.get_doc("Project Proposal", docname)
		current_state = doc.workflow_state or "Draft"
		print(f"[DEBUG] Current state: {current_state}")

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Project Proposal"}, "name")
		print(f"[DEBUG] Workflow name: {workflow_name}")
		
		if not workflow_name:
			print("[DEBUG] No workflow found, falling back to standard submit")
			# Fallback to standard submit if no workflow exists
			if doc.docstatus == 0:
				doc.submit()
				print("[DEBUG] Standard submit successful")
				return {"status": "success", "message": "Submitted successfully (No Workflow)", "docname": docname}
			print("[DEBUG] Document already submitted")
			return {"status": "success", "message": "Already submitted", "docname": docname}

		workflow = frappe.get_doc("Workflow", workflow_name)

		# Find the transition for "Submit" action from current state
		action = "Submit for Endorsement" 
		print(f"[DEBUG] Looking for transition for action: {action}")
		
		next_state = None
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				print(f"[DEBUG] Found transition: {current_state} -> {next_state}")
				break
		
		if not next_state:
			print(f"[DEBUG] No transition found for action '{action}' from state '{current_state}'")
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if next state requires submission
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		print(f"[DEBUG] Next state doc_status: {state_doc.doc_status if state_doc else 'None'}")
		
		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			print("[DEBUG] Submitting document...")
			doc.submit()
		else:
			print("[DEBUG] Saving document (no submit)...")
			doc.save(ignore_permissions=True)

		frappe.db.commit()
		print("=== SUBMIT PROJECT PROPOSAL END (SUCCESS) ===\n")

		return {
			"status": "success",
			"message": f"Project Proposal submitted. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state
		}

	except Exception as e:
		print(f"[DEBUG] EXCEPTION: {str(e)}")
		print(f"[DEBUG] Traceback: {frappe.get_traceback()}")
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Proposal Submit Error")
		print("=== SUBMIT PROJECT PROPOSAL END (ERROR) ===\n")
		return {"status": "error", "message": str(e)}
