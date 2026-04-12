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
    """
    Returns field metadata, prefill data, and link options for the
    Recruitment Adhoc Contractual form (follows APPS_DOCUMENTATION.md pattern).
    """

    # 1. Fetch Metadata
    meta = frappe.get_meta("Recruitment Adhoc Contractual")
    fields = []
    for f in meta.fields:
        depends_on = getattr(f, "depends_on", None) or ""
        mandatory_depends_on = getattr(f, "mandatory_depends_on", None) or ""
        read_only_depends_on = getattr(f, "read_only_depends_on", None) or ""

        field_data = {
            "fieldname": f.fieldname,
            "label": f.label,
            "fieldtype": f.fieldtype,
            "options": getattr(f, "options", None),
            "mandatory": f.reqd,
            "read_only": f.read_only,
            "hidden": getattr(f, "hidden", 0),
            "description": getattr(f, "description", "") or "",
            "default": getattr(f, "default", None),
            "in_list_view": getattr(f, "in_list_view", 0),
            # Conditional logic for frontend
            "depends_on": depends_on,
            "depends_on_eval": depends_on.replace("eval:", "").strip() if depends_on.startswith("eval:") else None,
            "mandatory_depends_on": mandatory_depends_on,
            "mandatory_depends_on_eval": mandatory_depends_on.replace("eval:", "").strip() if mandatory_depends_on.startswith("eval:") else None,
            "read_only_depends_on": read_only_depends_on,
            "read_only_depends_on_eval": read_only_depends_on.replace("eval:", "").strip() if read_only_depends_on.startswith("eval:") else None,
        }

        # Handle Child Tables: fetch child fields metadata
        if f.fieldtype == "Table" and f.options:
            try:
                child_meta = frappe.get_meta(f.options)
                field_data["child_fields"] = [{
                    "fieldname": cf.fieldname,
                    "label": cf.label,
                    "fieldtype": cf.fieldtype,
                    "options": getattr(cf, "options", None),
                    "mandatory": cf.reqd,
                    "hidden": getattr(cf, "hidden", 0),
                    "read_only": cf.read_only,
                    "in_list_view": getattr(cf, "in_list_view", 0),
                    "depends_on": getattr(cf, "depends_on", None),
                } for cf in child_meta.fields]
            except Exception:
                pass

        fields.append(field_data)

    # 2. Prepare Containers
    prefill_data = {}
    link_options = {}

    # 3. Fetch Data (if doc_name provided) or set new-doc defaults
    if doc_name:
        try:
            doc = frappe.get_doc("Recruitment Adhoc Contractual", doc_name)
            prefill_data = doc.as_dict()
        except Exception:
            pass
    else:
        # New-doc defaults: auto-fill the logged-in user's info
        try:
            current_user = frappe.session.user
            if current_user and current_user not in ["Administrator", "Guest"]:
                prefill_data["webmail_id"] = current_user

                # Try fetching PI head/mentor from the User record
                user_doc = frappe.get_doc("User", current_user)
                head = getattr(user_doc, "piheadmentor_user_id", None)
                if head:
                    prefill_data["head"] = head
        except Exception:
            pass

    # 4. Populate Link Options

    # webmail_id → User (enabled, non-guest)
    try:
        users = frappe.get_all(
            "User",
            filters={"enabled": 1, "user_type": "System User"},
            fields=["name as value", "full_name as label"],
            limit_page_length=500,
        )
        link_options["webmail_id"] = users
        link_options["chairperson_webmail_id"] = users
    except Exception:
        pass

    # upfa_department → Department_prornd
    try:
        departments = frappe.get_all(
            "Department_prornd",
            fields=["name as value", "name as label"],
            limit_page_length=200,
        )
        link_options["upfa_department"] = departments
    except Exception:
        pass

    # amended_from → Recruitment Adhoc Contractual
    try:
        amended_docs = frappe.get_all(
            "Recruitment Adhoc Contractual",
            fields=["name as value", "name as label"],
            limit_page_length=200,
        )
        link_options["amended_from"] = amended_docs
    except Exception:
        pass

    # Project options: fetch projects linked to current user (as PI)
    try:
        current_user = frappe.session.user
        projects = frappe.get_all(
            "Project Registration",
            filters={"pi_webmail_id": current_user},
            fields=[
                "name as value",
                "project_title as label",
                "project_title",
                "project_no",
                "department",
                "project_duration",
            ],
            limit_page_length=200,
            order_by="modified desc",
        )
        link_options["project_registration"] = projects
    except Exception:
        pass

    # 5. Client Scripts
    client_scripts = []
    try:
        scripts = frappe.get_all(
            "Client Script",
            filters={"dt": "Recruitment Adhoc Contractual", "enabled": 1},
            fields=["name", "script", "view"],
        )
        for script in scripts:
            client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
    except Exception:
        pass

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "link_options": link_options,
        "client_scripts": client_scripts,
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

        # fetch_from fields (e.g. `head`) are overwritten by Frappe's ORM during save,
        # so persist the frontend-supplied value directly after save
        if "head" in data and data["head"]:
            frappe.db.set_value("Recruitment Adhoc Contractual", doc.name, "head", data["head"])

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
        error_msg = str(e)
        if getattr(frappe.local, 'message_log', None):
            try:
                messages = [json.loads(msg).get("message", "") if isinstance(msg, str) else msg.get("message", "") for msg in frappe.local.message_log]
                if any(messages):
                    error_msg = " | ".join([m for m in messages if m])
            except Exception:
                pass
                
        if not error_msg:
            error_msg = "Unknown error occurred during workflow transition."
            
        frappe.log_error(frappe.get_traceback(), f"Workflow Action Failed: {action} on {docname}")
        # Provide a more user-friendly error message if it's a known workflow error
        return {"status": "error", "message": error_msg}


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


@frappe.whitelist(allow_guest=True)
def get_project_staff_designations():
	"""
	Returns a list of designations linked to users with an employee class of "Project Staff".
	"""
	try:
		project_staff_empclass_ids = frappe.get_all(
			"EmployeeClass_prornd",
			filters={"empclass_name": ["like", "%Project Staff%"]},
			pluck="name",
			limit=0,
		)

		if not project_staff_empclass_ids:
			return {"status": "success", "data": []}

		project_staff_designations = frappe.get_all(
			"User",
			filters={
				"empclass": ["in", project_staff_empclass_ids],
				"designation_name": ["is", "set"],
			},
			fields=["designation_name"],
			distinct=True,
			pluck="designation_name",
			limit=0,
		)

		if not project_staff_designations:
			return {"status": "success", "data": []}

		placeholders = ", ".join(["%s"] * len(project_staff_designations))
		filtered_designations = frappe.db.sql(
			f"""SELECT name, designation_prornd
			FROM `tabDesignation_prornd`
			WHERE name IN ({placeholders})
			OR designation_prornd IN ({placeholders})""",
			project_staff_designations + project_staff_designations,
			as_dict=True,
		)

		data = [
			{"value": item["name"], "label": item.get("designation_prornd") or item["name"]}
			for item in filtered_designations
		]

		return {"status": "success", "data": data}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error in get_project_staff_designations")
		return {"status": "error", "message": str(e)}
