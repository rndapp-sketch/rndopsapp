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
            limit_page_length=0,
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
            limit_page_length=0,
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
            limit_page_length=0,
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

        # Resolve chairperson_name from chairperson_webmail_id (User lookup)
        # Priority: explicit email in payload → fallback to project head_approver
        chairperson_email = data.get("chairperson_webmail_id")
        if not chairperson_email:
            upfa_project_code = data.get("upfa_project_code")
            if upfa_project_code:
                project = frappe.db.get_value(
                    "Project Registration",
                    {"project_no": upfa_project_code},
                    ["head_approver"],
                    as_dict=True,
                )
                if project and project.get("head_approver"):
                    chairperson_email = project["head_approver"]

        if chairperson_email:
            user = frappe.db.get_value(
                "User",
                chairperson_email,
                ["first_name", "middle_name", "last_name"],
                as_dict=True,
            )
            if user:
                name_parts = [
                    (user.get("first_name") or "").strip(),
                    (user.get("middle_name") or "").strip(),
                    (user.get("last_name") or "").strip(),
                ]
                chairperson_name = " ".join(part for part in name_parts if part)
                frappe.db.set_value(
                    "Recruitment Adhoc Contractual",
                    doc.name,
                    {
                        "chairperson_webmail_id": chairperson_email,
                        "chairperson_name": chairperson_name,
                    },
                )

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


# ============================================================
# EDITED BY MKY | 2026-04-14 12:23 IST
# START OF EDIT — Dynamic Designation Fetching via designation_type
# Replaced complex EmployeeClass→User→Designation chain with a
# direct filter on Designation_prornd.designation_type field.
# Added get_filtered_designations() for dynamic frontend calls.
# ============================================================

@frappe.whitelist(allow_guest=True)
def get_project_staff_designations():
	"""
	Returns a list of designations where designation_type = "Project Staff"
	directly from Designation_prornd doctype.
	"Other" is always appended at the end for custom user input.
	"""
	return get_filtered_designations(designation_type="Project Staff")


@frappe.whitelist(allow_guest=True)
def get_filtered_designations(designation_type=None):
	"""
	Returns designations from Designation_prornd filtered by designation_type.
	If designation_type is not provided, returns all designations.
	"Other" is always appended at the end to allow custom user input.

	Args:
		designation_type (str, optional): e.g. "Project Staff", "Permanent Staff", "Others"

	Returns:
		dict: {"status": "success", "data": [{"value": ..., "label": ...}, ...]}
	"""
	try:
		filters = {}
		if designation_type:
			filters["designation_type"] = designation_type

		designations = frappe.get_all(
			"Designation_prornd",
			filters=filters,
			fields=["name as value", "designation_prornd as label"],
			order_by="designation_prornd asc",
			limit=0,
		)

		data = [
			{"value": item["value"], "label": item.get("label") or item["value"]}
			for item in designations
		]

		# ============================================================
		# EDITED BY MKY | 2026-04-14 15:35 IST
		# START OF EDIT — Quick Entry Prepend
		# Replaced "Other" appended at the end with "CREATE_NEW" prepended at the top.
		# ============================================================
		data.insert(0, {
			"value": "CREATE_NEW",
			"label": "➕ Create New Designation..."
		})
		# END OF EDIT — MKY | 2026-04-14 15:35 IST
		# ============================================================

		return {"status": "success", "data": data}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error in get_filtered_designations")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def update_chairperson_fields(docname, chairperson_webmail_id, chairperson_name):
    """
    Directly updates chairperson_webmail_id and chairperson_name on a
    Recruitment Adhoc Contractual document.
    Restricted to users with the 'Dean, RnD' role.
    """
    print(f"[update_chairperson_fields] Called by: {frappe.session.user}")
    print(f"[update_chairperson_fields] docname={docname}, email={chairperson_webmail_id}, name={chairperson_name}")

    user_roles = frappe.get_roles(frappe.session.user)
    print(f"[update_chairperson_fields] User roles: {user_roles}")

    if "Dean, RnD" not in user_roles:
        print(f"[update_chairperson_fields] Permission denied for user: {frappe.session.user}")
        frappe.throw("Not permitted", frappe.PermissionError)

    try:
        # Derive chairperson_name from User if not explicitly provided
        if not chairperson_name:
            user = frappe.db.get_value(
                "User",
                chairperson_webmail_id,
                ["first_name", "middle_name", "last_name"],
                as_dict=True,
            )
            if user:
                name_parts = [
                    (user.get("first_name") or "").strip(),
                    (user.get("middle_name") or "").strip(),
                    (user.get("last_name") or "").strip(),
                ]
                chairperson_name = " ".join(part for part in name_parts if part)
                print(f"[update_chairperson_fields] Derived name from User: {chairperson_name}")

        print(f"[update_chairperson_fields] Attempting db.set_value on {docname}")
        frappe.db.set_value(
            "Recruitment Adhoc Contractual",
            docname,
            {
                "chairperson_webmail_id": chairperson_webmail_id,
                "chairperson_name": chairperson_name,
            },
        )
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        print(f"[update_chairperson_fields] ERROR: {e}")
        frappe.log_error(frappe.get_traceback(), f"update_chairperson_fields failed for {docname}")
        return {"status": "error", "message": str(e)}
    else:
        print(f"[update_chairperson_fields] Success — chairperson_webmail_id={chairperson_webmail_id}, chairperson_name={chairperson_name}")
        return {
            "status": "success",
            "chairperson_webmail_id": chairperson_webmail_id,
            "chairperson_name": chairperson_name,
        }


# END OF EDIT — MKY | 2026-04-14 12:23 IST
# ============================================================

# ============================================================
# EDITED BY MKY | 2026-04-14 15:35 IST
# START OF EDIT — create_custom_designation for Recruitment Adhoc Contractual
# Mirrors the same logic from project_registration.py.
# Returns status="duplicate" when designation already exists so frontend alerts the user.
# ============================================================
@frappe.whitelist()
def create_custom_designation(designation_name, designation_type="Project Staff"):
	"""
	Checks for an existing designation (case-insensitive).
	Returns status="duplicate" with a message if already present.
	Otherwise creates a new Designation_prornd record and returns status="success".
	"""
	try:
		if not designation_name:
			return {"status": "error", "message": "Designation name is required"}

		designation_name = designation_name.strip()
		# Case-insensitive duplicate check across both name and designation_prornd fields
		existing = frappe.db.sql(
			"""SELECT name, designation_prornd FROM `tabDesignation_prornd`
			WHERE UPPER(designation_prornd)=%s OR UPPER(name)=%s LIMIT 1""",
			(designation_name.upper(), designation_name.upper()),
			as_dict=True
		)

		if existing:
			# Return a distinct "duplicate" status — frontend will alert the user
			return {
				"status": "duplicate",
				"designation_name": existing[0]["name"],
				"message": f"Designation '{existing[0].get('designation_prornd') or existing[0]['name']}' already exists in the system."
			}

		# Create new designation
		new_doc = frappe.get_doc({
			"doctype": "Designation_prornd",
			"designation_prornd": designation_name,
			"designation_type": designation_type
		})
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "designation_name": new_doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"Recruitment Adhoc Contractual Custom Designation Creation Error for {designation_name}")
		return {"status": "error", "message": str(e)}

# END OF EDIT — MKY | 2026-04-14 15:35 IST
# ============================================================


# ============================================================
# EDITED BY MKY | 2026-04-21 IST
# START OF EDIT — Single-field update endpoints
# Each endpoint updates exactly one field on a Recruitment Adhoc
# Contractual document (identified by docname) without touching
# any other field. All four target fields carry allow_on_submit=1
# so updates are safe on submitted documents as well.
# ============================================================

def _update_single_field(docname, fieldname, value):
	"""Internal helper to update a single field on a Recruitment Adhoc Contractual doc."""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Recruitment Adhoc Contractual", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	try:
		frappe.db.set_value("Recruitment Adhoc Contractual", docname, fieldname, value)
		frappe.db.commit()
		return {"status": "success", "docname": docname, fieldname: value}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update {fieldname} failed for {docname}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_walk_in(docname, walk_in):
	"""Update only the walk_in field ('Yes' / 'No' / '')."""
	if walk_in not in ("", "Yes", "No", None):
		return {"status": "error", "message": "walk_in must be 'Yes', 'No', or empty"}
	return _update_single_field(docname, "walk_in", walk_in or "")


@frappe.whitelist()
def update_upfa_interview_date(docname, upfa_interview_date):
	"""Update only the upfa_interview_date field (Date, YYYY-MM-DD)."""
	return _update_single_field(docname, "upfa_interview_date", upfa_interview_date or None)


@frappe.whitelist()
def update_upfa_interview_time(docname, upfa_interview_time):
	"""Update only the upfa_interview_time field (Time, HH:MM:SS)."""
	return _update_single_field(docname, "upfa_interview_time", upfa_interview_time or None)


@frappe.whitelist()
def update_last_date_of_appllication(docname, last_date_of_appllication):
	"""Update only the last_date_of_appllication field (Date, YYYY-MM-DD)."""
	return _update_single_field(docname, "last_date_of_appllication", last_date_of_appllication or None)

# END OF EDIT — MKY | 2026-04-21 IST
# ============================================================
