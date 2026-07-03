# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
import json
import base64
from frappe.model.document import Document
from frappe.utils.file_manager import save_file
from rndopsapp.minio import get_rnd_file_service


DOCTYPE = "Indent General Form"


class IndentGeneralForm(Document):
	pass

@frappe.whitelist()
def get_indent_general_form_fields(doc_name=None):
    # 1. Fetch Metadata
    meta = frappe.get_meta(DOCTYPE)
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
        doc = frappe.get_doc(DOCTYPE, doc_name)
        prefill_data = doc.as_dict()
    
    # 4. Populate Link Options (e.g. for dropdowns)
    # link_options["some_link_field"] = frappe.get_all("Some Master", fields=["name as value", "title as label"])

    # 5. Client Scripts (CRITICAL: Fetch enabled client scripts for frontend logic)
    client_scripts = []
    try:
        scripts = frappe.get_all("Client Script", filters={"dt": DOCTYPE, "enabled": 1}, fields=["name", "script", "view"])
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
def save_indent_general_form_data(data, files=None, file=None):
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(files, str):
        files = json.loads(files)
    if isinstance(file, str):
        file = json.loads(file)

    # Normalise: support both `files` (list) and legacy `file` (single object)
    if not files:
        files = [file] if file else []
    elif not isinstance(files, list):
        files = [files]

    try:
        # --- Create or Update ---
        docname = data.get("name", "").strip()
        if docname:
            print(f"[IGF] UPDATE existing doc: {docname}")
            doc = frappe.get_doc(DOCTYPE, docname)
        else:
            print(f"[IGF] CREATE new doc")
            doc = frappe.new_doc(DOCTYPE)

        # Map standard fields dynamically (skip Attach fields — set after upload)
        meta = frappe.get_meta(DOCTYPE)
        attach_fields = {f.fieldname for f in meta.fields if f.fieldtype in ("Attach", "Attach Image")}
        valid_fields = [
            f.fieldname for f in meta.fields
            if f.fieldtype not in ["Section Break", "Column Break", "HTML", "Table"]
            and f.fieldname not in attach_fields
        ]
        valid_fields.append("workflow_state")

        for field in valid_fields:
            if field in data:
                doc.set(field, data[field])

        # Handle Child Tables
        table_fields = [f.fieldname for f in meta.fields if f.fieldtype == "Table"]
        for table_field in table_fields:
            items_data = data.get(table_field, [])
            if items_data:
                doc.set(table_field, [])
                for item in items_data:
                    doc.append(table_field, item)

        doc.save(ignore_permissions=True)
        frappe.db.commit()
        print(f"[IGF] Doc saved: {doc.name}")

        # --- Upload files to MinIO and write URLs back to Attach fields ---
        file_urls = []
        failed_files = []
        file_service = get_rnd_file_service()
        attach_field_updates = {}

        # Ordered list of attach fields from meta (positional fallback)
        ordered_attach_fields = [f.fieldname for f in meta.fields if f.fieldtype in ("Attach", "Attach Image")]
        print(f"[IGF] Attach fields in meta order: {ordered_attach_fields}")

        valid_files = [f for f in files if f and f.get("file_name") and f.get("file_data")]

        for idx, f in enumerate(valid_files):
            # Use field_name from file object; fall back to positional attach field
            field_name = f.get("field_name")
            if not field_name and idx < len(ordered_attach_fields):
                field_name = ordered_attach_fields[idx]
            print(f"[IGF] Uploading '{f.get('file_name')}' → field '{field_name}'")

            file_data_uri = f.get("file_data")
            if file_data_uri.startswith("data:"):
                file_data_uri = file_data_uri.split(",", 1)[1]

            file_bytes = base64.b64decode(file_data_uri)
            project_docname = doc.get("igf_project_title") or doc.name

            upload_result = file_service.save_file(
                filename=f.get("file_name"),
                content=file_bytes,
                is_private=True,
                doctype="Project Registration",
                docname=project_docname,
                folder=f"Indent_General_Form/{doc.name}/files",
                use_hash=False
            )

            if upload_result.get("status"):
                file_url = upload_result.get("data", {}).get("file_url")
                file_urls.append({"field_name": field_name, "file_url": file_url})
                if field_name:
                    attach_field_updates[field_name] = file_url
                print(f"[IGF] Upload success: {file_url} → {field_name}")
            else:
                failed_files.append(f.get("file_name"))
                print(f"[IGF] Upload failed: {upload_result.get('message')}")
                frappe.log_error(
                    f"File upload failed for '{f.get('file_name')}': {upload_result.get('message')}",
                    "Indent General Form File Upload Failed"
                )

        # Write uploaded file URLs back to the Attach fields and save
        if attach_field_updates:
            print(f"[IGF] Writing file URLs to Attach fields: {attach_field_updates}")
            reload_doc = frappe.get_doc(DOCTYPE, doc.name)
            for fname, furl in attach_field_updates.items():
                reload_doc.set(fname, furl)
                print(f"[IGF]   {fname} = {furl}")
            reload_doc.save(ignore_permissions=True)
            frappe.db.commit()
            print(f"[IGF] Attach fields saved successfully")

        result = {"status": "success", "docname": doc.name, "file_urls": file_urls}
        if failed_files:
            result["failed_files"] = failed_files
        return result

    except Exception as e:
        frappe.db.rollback()
        print(f"[IGF] ERROR: {e}")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_indent_general_form_workflow_actions(docname):
    wf_name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
    if not wf_name:
        return {"actions": []}

    wf = frappe.get_doc("Workflow", wf_name)
    doc = frappe.get_doc(DOCTYPE, docname)
    current_state = doc.workflow_state

    user_roles = frappe.get_roles(frappe.session.user)
    allowed_actions = []

    for t in wf.transitions:
        if t.state == current_state:
            if not t.allowed or t.allowed in user_roles:
                allowed_actions.append(t.action)

    return {"actions": list(set(allowed_actions)), "current_state": current_state}

@frappe.whitelist()
def perform_indent_general_form_action(docname, action):
    # 1. Get Workflow
    wf_name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name")
    if not wf_name:
        frappe.throw("Invalid Workflow")
        
    wf = frappe.get_doc("Workflow", wf_name)
    
    doc = frappe.get_doc(DOCTYPE, docname)
    current_state = doc.workflow_state or wf.initial_state

    # 2. Find Next State
    next_state = None
    for t in wf.transitions:
        if t.state == current_state and t.action == action:
            next_state = t.next_state
            break

    if not next_state:
        frappe.throw(
            f"Action '{action}' is not valid for current state '{current_state}'. "
            f"Available transitions: {[(t.state, t.action) for t in wf.transitions]}"
        )

    # 3. Update & Save
    doc.workflow_state = next_state
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "next_state": next_state}


# ---------------------------------------------------------------------------
# Dynamic Put-Back Engine (Strategy C test for Indent General Form)
# ---------------------------------------------------------------------------
# Canonical compact config. Replaces N duplicated "Put Back to X" rows in
# the Workflow Transition table. Forward transitions stay in the Workflow doc.

PUT_BACK_TARGETS = {
    # target_key -> next_state
    "Requestor": "Draft",
    "Staff":     "Pending Staff Approval",
    "HoS":       "Pending HoS Approval",
}

PUT_BACK_RULES = {
    # current_state -> who can do it, which targets are reachable
    "Pending Staff Approval": {
        "role": "staff, RnD",
        "targets": ["Requestor"],
    },
    "Pending HoS Approval": {
        "role": "Hos, RnD (Head of Section, RnD)",
        "targets": ["Staff", "Requestor"],
    },
    "Pending Dean Approval": {
        "role": "Dean, RnD",
        "targets": ["HoS", "Staff", "Requestor"],
    },
}


def _user_has_role(required_role):
    roles = frappe.get_roles(frappe.session.user)
    return required_role in roles or "Administrator" in roles


@frappe.whitelist()
def get_available_back_actions(docname):
    """Return the list of put-back actions the current user can perform
    on this doc, given its current workflow_state."""
    if not frappe.db.exists(DOCTYPE, docname):
        return {"actions": [], "error": "Document not found"}

    current_state = frappe.db.get_value(DOCTYPE, docname, "workflow_state")
    rule = PUT_BACK_RULES.get(current_state)
    if not rule or not _user_has_role(rule["role"]):
        return {"actions": [], "current_state": current_state}

    actions = [
        {
            "target": t,
            "label": f"Put Back to {t}",
            "next_state": PUT_BACK_TARGETS[t],
        }
        for t in rule["targets"]
        if t in PUT_BACK_TARGETS
    ]
    return {"actions": actions, "current_state": current_state}


@frappe.whitelist()
def put_back(docname, target):
    """Apply a put-back action. Validates role + from-state + target."""
    if target not in PUT_BACK_TARGETS:
        frappe.throw(f"Unknown put-back target: {target}")

    if not frappe.db.exists(DOCTYPE, docname):
        frappe.throw("Document not found")

    current_state = frappe.db.get_value(DOCTYPE, docname, "workflow_state")
    rule = PUT_BACK_RULES.get(current_state)
    if not rule:
        frappe.throw(f"No put-back actions allowed from state '{current_state}'")

    if target not in rule["targets"]:
        frappe.throw(f"Cannot put back to '{target}' from '{current_state}'")

    if not _user_has_role(rule["role"]):
        frappe.throw(f"Role '{rule['role']}' required to put back from '{current_state}'")

    next_state = PUT_BACK_TARGETS[target]

    # Bypass Frappe's workflow transition validator — that validator requires
    # a matching row in the Workflow Transition table for every (from, to)
    # pair, which is the very duplication this engine is designed to remove.
    # We've already validated role + from-state + target via PUT_BACK_RULES.
    frappe.db.set_value(DOCTYPE, docname, "workflow_state", next_state, update_modified=True)

    # Audit trail: attach a Comment to the doc so the action is visible in
    # the activity log without needing to round-trip through doc.save().
    frappe.get_doc({
        "doctype": "Comment",
        "comment_type": "Workflow",
        "reference_doctype": DOCTYPE,
        "reference_name": docname,
        "content": f"Put back to {target} ({next_state}) by {frappe.session.user} from {current_state}",
    }).insert(ignore_permissions=True)

    frappe.db.commit()

    return {
        "status": "success",
        "from": current_state,
        "to": next_state,
        "target": target,
    }
