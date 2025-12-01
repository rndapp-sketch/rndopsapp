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


@frappe.whitelist()
def save_project_proposal(data):
	"""
	Save Project Proposal data (parent + child tables).
	Expects 'data' as a JSON string or dict.
	Supports file uploads for 'Attach' fields if passed as {file_name, file_data}.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		docname = data.get("name")
		if docname:
			doc = frappe.get_doc("Project Proposal", docname)
		else:
			doc = frappe.new_doc("Project Proposal")

		# Get metadata to filter valid fields
		meta = frappe.get_meta("Project Proposal")
		
		# Iterate over data and set fields
		for fieldname, value in data.items():
			if not meta.has_field(fieldname):
				continue
				
			df = meta.get_field(fieldname)
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				# Clear existing rows if updating
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				
				for child_row in value:
					# Check for file uploads in child row fields
					for cf in child_meta.fields:
						if cf.fieldtype == "Attach" and child_row.get(cf.fieldname):
							f_val = child_row[cf.fieldname]
							if isinstance(f_val, dict) and f_val.get("file_name") and f_val.get("file_data"):
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
								except Exception as e:
									frappe.log_error(f"Child Table File Upload Error: {str(e)}")
									child_row[cf.fieldname] = None

					doc.append(fieldname, child_row)
					
			# Handle Attach fields (Base64) - if sent as dict {file_name, file_data}
			elif df.fieldtype == "Attach" and isinstance(value, dict) and value.get("file_data"):
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
				except Exception as e:
					frappe.log_error(f"File Upload Error: {str(e)}")
					# Don't set the field if upload fails
					pass
				
			# Standard fields
			else:
				doc.set(fieldname, value)

		# Set owner if new
		if doc.is_new():
			doc.owner = frappe.session.user

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Project Proposal saved successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Proposal Save Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_project_proposal(docname):
	"""
	Submit a Project Proposal document using Workflow transitions.
	"""
	try:
		doc = frappe.get_doc("Project Proposal", docname)
		current_state = doc.workflow_state or "Draft"

		# Fetch the workflow for this doctype
		workflow_name = frappe.get_value("Workflow", {"document_type": "Project Proposal"}, "name")
		
		if not workflow_name:
			# Fallback to standard submit if no workflow exists
			if doc.docstatus == 0:
				doc.submit()
				return {"status": "success", "message": "Submitted successfully (No Workflow)", "docname": docname}
			return {"status": "success", "message": "Already submitted", "docname": docname}

		workflow = frappe.get_doc("Workflow", workflow_name)

		# Find the transition for "Submit" action from current state
		action = "Submit" 
		
		next_state = None
		
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				next_state = t.next_state
				break
		
		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}' from state '{current_state}'.")

		# Update workflow state
		doc.workflow_state = next_state
		
		# Check if next state requires submission
		state_doc = next((s for s in workflow.states if s.state == next_state), None)
		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.submit()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Project Proposal submitted. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Proposal Submit Error")
		return {"status": "error", "message": str(e)}
