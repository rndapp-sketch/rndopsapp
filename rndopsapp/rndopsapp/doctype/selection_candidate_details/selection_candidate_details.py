# Copyright (c) 2026, RnD Operations and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
# EDITED BY OJS | 2026-05-13 15:38 IST
# Description: Removed frappe.model.workflow import
# END OF EDIT — OJS | 2026-05-13 15:38 IST


class SelectionCandidateDetails(Document):
	pass


# ─────────────────────────────────────────────────────────────
# GET FIELDS
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_selection_candidate_details_fields(doc_name=None):
    """
    Returns field metadata, prefill data, and link options for the
    Selection Candidate Details form (follows APPS_DOCUMENTATION.md pattern).
    """

    # 1. Fetch Metadata
    meta = frappe.get_meta("Selection Candidate Details")
    fields = []
    for f in meta.fields:
        depends_on            = getattr(f, "depends_on", None) or ""
        mandatory_depends_on  = getattr(f, "mandatory_depends_on", None) or ""
        read_only_depends_on  = getattr(f, "read_only_depends_on", None) or ""

        field_data = {
            "fieldname":               f.fieldname,
            "label":                   f.label,
            "fieldtype":               f.fieldtype,
            "options":                 getattr(f, "options", None),
            "mandatory":               f.reqd,
            "read_only":               f.read_only,
            "hidden":                  getattr(f, "hidden", 0),
            "description":             getattr(f, "description", "") or "",
            "default":                 getattr(f, "default", None),
            "in_list_view":            getattr(f, "in_list_view", 0),
            "depends_on":              depends_on,
            "depends_on_eval":         depends_on.replace("eval:", "").strip() if depends_on.startswith("eval:") else None,
            "mandatory_depends_on":    mandatory_depends_on,
            "mandatory_depends_on_eval": mandatory_depends_on.replace("eval:", "").strip() if mandatory_depends_on.startswith("eval:") else None,
            "read_only_depends_on":    read_only_depends_on,
            "read_only_depends_on_eval": read_only_depends_on.replace("eval:", "").strip() if read_only_depends_on.startswith("eval:") else None,
        }

        fields.append(field_data)

    # 2. Prepare containers
    prefill_data = {}
    link_options = {}

    # 3. Fetch doc data when editing
    if doc_name:
        try:
            doc = frappe.get_doc("Selection Candidate Details", doc_name)
            prefill_data = doc.as_dict()
        except Exception:
            pass

    # 4. Populate link options

    # interview_id → Recruitment Adhoc Contractual (approved / submitted)
    try:
        interviews = frappe.get_all(
            "Recruitment Adhoc Contractual",
            fields=["name as value", "name as label"],
            limit_page_length=0,
            order_by="modified desc",
        )
        link_options["interview_id"] = interviews
    except Exception:
        pass

    # 5. Client scripts
    client_scripts = []
    try:
        scripts = frappe.get_all(
            "Client Script",
            filters={"dt": "Selection Candidate Details", "enabled": 1},
            fields=["name", "script", "view"],
        )
        for script in scripts:
            client_scripts.append({
                "name":   script.name,
                "script": script.script,
                "view":   script.view,
            })
    except Exception:
        pass

    return {
        "fields":         fields,
        "prefill_data":   prefill_data,
        "link_options":   link_options,
        "client_scripts": client_scripts,
    }


# ─────────────────────────────────────────────────────────────
# SAVE DATA
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def save_selection_candidate_details_data(data):
    """
    Creates a new Selection Candidate Details document or updates an existing
    Draft. Pass `name` in the payload to update.
    """
    if isinstance(data, str):
        data = json.loads(data)

    try:
        if data.get("name"):
            doc = frappe.get_doc("Selection Candidate Details", data["name"])
        else:
            doc = frappe.new_doc("Selection Candidate Details")

        meta = frappe.get_meta("Selection Candidate Details")

        for f in meta.fields:
            if f.fieldtype not in ("Table", "Section Break", "Column Break") and f.fieldname in data:
                doc.set(f.fieldname, data[f.fieldname])

        # EDITED BY OJS | 2026-05-13 15:38 IST
        # Description: Removed workflow_state mapping since workflow is not required
        # END OF EDIT — OJS | 2026-05-13 15:38 IST

        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"save_selection_candidate_details_data failed")
        return {"status": "error", "message": str(e)}


# EDITED BY OJS | 2026-05-13 15:38 IST
# Description: Removed WORKFLOW ACTIONS since Selection Candidate Details only requires save
# END OF EDIT — OJS | 2026-05-13 15:38 IST


# ─────────────────────────────────────────────────────────────
# QUERY HELPERS
# ─────────────────────────────────────────────────────────────

@frappe.whitelist(allow_guest=True)
def get_selection_candidate_details_by_interview(interview_id, selection_status=None):
    """
    Returns all Selection Candidate Details records for a given interview_id.

    Optional filter:
        selection_status  – e.g. "Selected", "Waitlisted", "Rejected"
    """
    try:
        filters = {"interview_id": interview_id}
        if selection_status:
            filters["selection_status"] = selection_status.strip().title()

        doc_names = frappe.get_all(
            "Selection Candidate Details",
            filters=filters,
            pluck="name",
        )

        docs = [frappe.get_doc("Selection Candidate Details", n).as_dict() for n in doc_names]

        return {"status": "success", "data": docs}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_selection_candidate_details_by_application(application_id):
    """Returns the Selection Candidate Details record for a given applicationId."""
    try:
        doc_names = frappe.get_all(
            "Selection Candidate Details",
            filters={"application_id": application_id},
            pluck="name",
        )
        docs = [frappe.get_doc("Selection Candidate Details", n).as_dict() for n in doc_names]
        return {"status": "success", "data": docs}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────
# SINGLE-FIELD UPDATE HELPERS
# ─────────────────────────────────────────────────────────────

def _update_single_field(docname, fieldname, value):
    """Internal helper: update exactly one field on a Selection Candidate Details doc."""
    if not docname:
        return {"status": "error", "message": "docname is required"}

    if not frappe.db.exists("Selection Candidate Details", docname):
        return {"status": "error", "message": f"Document '{docname}' not found"}

    try:
        frappe.db.set_value("Selection Candidate Details", docname, fieldname, value)
        frappe.db.commit()
        return {"status": "success", "docname": docname, fieldname: value}
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), f"update {fieldname} failed for {docname}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_selection_status(docname, selection_status):
    """Update only the selection_status field."""
    return _update_single_field(docname, "selection_status", selection_status)


@frappe.whitelist()
def update_appointment_order_number(docname, appointment_order_number):
    """Update only the appointment_order_number field."""
    return _update_single_field(docname, "appointment_order_number", appointment_order_number)


@frappe.whitelist()
def update_medical_report_number(docname, medical_report_number):
    """Update only the medical_report_number field."""
    return _update_single_field(docname, "medical_report_number", medical_report_number)


@frappe.whitelist()
def update_wl_number(docname, wl_number):
    """Update only the wl_number (waitlist number) field."""
    return _update_single_field(docname, "wl_number", wl_number)
