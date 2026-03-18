# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe.model.workflow import get_transitions

class RecruitmentAdhocContractual(Document):
	pass


@frappe.whitelist()
def get_recruitment_adhoc_contractual_fields(doc_name=None):
    # 1. Fetch Metadata
    meta = frappe.get_meta("Recruitment Adhoc Contractual")
    fields = []
    for f in meta.fields:
        field_data = {
            "fieldname": f.fieldname,
            "label": f.label,
            "fieldtype": f.fieldtype,
            "options": f.options,
            "mandatory": f.reqd,
            "read_only": f.read_only,
            "depends_on": f.depends_on, # For frontend logic
            "depends_on_eval": f.depends_on.replace("eval:", "") if f.depends_on and f.depends_on.startswith("eval:") else None
        }
        
        # Handle Child Tables: Fetch child fields metadata
        if f.fieldtype == "Table":
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [{
                "fieldname": cf.fieldname,
                "label": cf.label,
                "fieldtype": cf.fieldtype,
                "options": cf.options,
                "in_list_view": cf.in_list_view
            } for cf in child_meta.fields]
            
        fields.append(field_data)
    
    # 2. Prepare Containers
    prefill_data = {}
    link_options = {}

    # 3. Fetch Data (if doc_name provided)
    if doc_name:
        doc = frappe.get_doc("Recruitment Adhoc Contractual", doc_name)
        prefill_data = doc.as_dict()
    
    # 5. Client Scripts (CRITICAL: Fetch enabled client scripts for frontend logic)
    client_scripts = []
    try:
        scripts = frappe.get_all("Client Script", filters={"dt": "Recruitment Adhoc Contractual", "enabled": 1}, fields=["name", "script", "view"])
        for script in scripts:
            client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
    except Exception:
        pass

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "link_options": link_options,
        "client_scripts": client_scripts # Return scripts to frontend
    }


@frappe.whitelist()
def save_recruitment_adhoc_contractual_data(data):
    if isinstance(data, str):
        data = json.loads(data)
    
    try:
        # Create or Get Doc
        if data.get("name"):
            doc = frappe.get_doc("Recruitment Adhoc Contractual", data.get("name"))
        else:
            doc = frappe.new_doc("Recruitment Adhoc Contractual")
        
        # Fetch meta to map fields properly
        meta = frappe.get_meta("Recruitment Adhoc Contractual")
        
        # Map Fields
        for f in meta.fields:
            if f.fieldtype != "Table" and f.fieldname in data:
                doc.set(f.fieldname, data[f.fieldname])
        
        if "workflow_state" in data:
            doc.set("workflow_state", data["workflow_state"])
            
        # Handle Child Tables
        for f in meta.fields:
            if f.fieldtype == "Table":
                items_data = data.get(f.fieldname, [])
                if items_data and isinstance(items_data, list):
                    doc.set(f.fieldname, []) # Clear existing
                    for item in items_data:
                        doc.append(f.fieldname, item)
        
        # Save
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_recruitment_adhoc_contractual_workflow_actions(docname):
    """
    Get available workflow actions for the current user based on document state.
    Utilizes standard Frappe workflow transition logic to ensure conditions and roles 
    are handled consistently with the desk view.
    """
    
    
    doc = frappe.get_doc("Recruitment Adhoc Contractual", docname)
    transitions = get_transitions(doc)
    
    # Extract unique action names
    actions = list(dict.fromkeys([t.get("action") for t in transitions]))
    
    return actions


@frappe.whitelist()
def perform_recruitment_adhoc_contractual_action(docname, action):
    """
    Perform a workflow action on the document.
    Uses Frappe's built-in workflow engine for robust transition handling.
    """
    try:
        from frappe.model.workflow import apply_workflow
        
        doc = frappe.get_doc("Recruitment Adhoc Contractual", docname)
        
        # apply_workflow handles transitions, permissions, and status updates
        updated_doc = apply_workflow(doc, action)
        
        frappe.db.commit()
        
        new_state = updated_doc.workflow_state
        
        return {
            "status": "success",
            "message": f"Action '{action}' completed. New State: {new_state}",
            "docname": docname,
            "workflow_state": new_state,
            "next_actions": get_recruitment_adhoc_contractual_workflow_actions(docname)
        }
    except Exception as e:
        frappe.db.rollback()
        # Provide a more user-friendly error message if it's a known workflow error
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_recruitment_adhoc_contractual(docname):
    """
    Submit a Recruitment Adhoc Contractual document using Workflow transitions.
    """
    return perform_recruitment_adhoc_contractual_action(docname, "Submit")


@frappe.whitelist(allow_guest=True)
def get_recruitment_adhoc_contractual_by_webmail(pi_mail=None, project_no=None, webmail_id=None):
	"""
	Get all Recruitment Adhoc Contractual documents for a specific PI mail and project_no.
	"""
	# Handle legacy parameter if passed by frontend
	if webmail_id and not pi_mail:
		pi_mail = webmail_id
		
	try:
		filters = {}
		if pi_mail:
			filters["webmail_id"] = pi_mail
		if project_no:
			filters["upfa_project_code"] = project_no
			
		doc_names = frappe.get_all(
			"Recruitment Adhoc Contractual",
			filters=filters,
			pluck="name"
		)
		
		docs = [frappe.get_doc("Recruitment Adhoc Contractual", name).as_dict() for name in doc_names]
			
		return {
			"status": "success",
			"data": docs
		}
	except Exception as e:
		return {"status": "error", "message": str(e)}
