# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import sanitize_html
import json
import os
from frappe.model.document import Document


class FundReceived(Document):
	pass


# @frappe.whitelist()
# def get_fund_received_fields(fund_sanction=None):
#     """
#     Returns fields for the Fund Received form.
#     If a fund_sanction docname is provided, it pre-fills key details.
#     """
#     fund_received_meta = frappe.get_meta("Fund Received")
#     fields = [
#         {"fieldname": f.fieldname, "label": f.label, "fieldtype": f.fieldtype, "options": f.options,
#          "mandatory": f.reqd, "hidden": f.hidden, "read_only": f.read_only, "description": f.description}
#         for f in fund_received_meta.get("fields")
#     ]
    
#     prefill_data = {}
#     link_options = {}

#     # If this form is being created from a specific sanction, pre-fill the data
#     if fund_sanction:
#         sanction_doc = frappe.get_doc("Fund Sanction", fund_sanction)
#         prefill_data = {
#             'sanction_ref_no': sanction_doc.name,
#             'prjreg_refnum': sanction_doc.project_proposal,
#             'prj_type': sanction_doc.project_type_linked,
#         }
    
#     # Populate Link options
#     link_options["prjreg_refnum"] = frappe.get_all("Project Registration", fields=["name as value", "project_title as label"])
    
#     # The 'sanction_ref_no' options should ideally be filtered by the selected project.
#     # For now, we'll send all, but this can be enhanced with another API call on project change.
#     link_options["sanction_ref_no"] = frappe.get_all("Fund Sanction", fields=["name as value", "sanctioned_letter_no as label"])

#     return {
#         "fields": fields,
#         "prefill_data": prefill_data,
#         "link_options": link_options,
#     }

@frappe.whitelist()
def get_fund_received_fields(fund_sanction=None):
    """
    Returns fields for the Fund Received form.
    If a fund_sanction docname is provided, it pre-fills key details.
    """
    fund_received_meta = frappe.get_meta("Fund Received")
    
    # --- THIS IS THE CRUCIAL PART ---
    # This loop iterates through ALL fields in your "Fund Received" Doctype
    # and adds them to the list that will be sent to the frontend.
    # It does not filter any out, ensuring all are available.
    fields = [
        {
            "fieldname": f.fieldname, 
            "label": f.label, 
            "fieldtype": f.fieldtype, 
            "options": f.options,
            "mandatory": f.reqd, 
            "hidden": f.hidden, 
            "read_only": f.read_only, 
            "description": f.description
        }
        for f in fund_received_meta.get("fields")
    ]
    # --- END CRUCIAL PART ---
    
    prefill_data = {}
    link_options = {}

    # If this form is being created from a specific sanction, pre-fill the data
    if fund_sanction:
        sanction_doc = frappe.get_doc("Fund Sanction", fund_sanction)
        prefill_data = {
            'sanction_ref_no': sanction_doc.name,
            'prjreg_refnum': sanction_doc.project_proposal,
            'prj_type': sanction_doc.project_type_linked,
        }
    
    # Populate Link options for dropdowns
    link_options["prjreg_refnum"] = frappe.get_all("Project Registration", fields=["name as value", "project_title as label"])
    link_options["sanction_ref_no"] = frappe.get_all("Fund Sanction", fields=["name as value", "sanctioned_letter_no as label"])
    link_options["amended_from"] = frappe.get_all("Fund Received", fields=["name as value"])

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "link_options": link_options,
    }

# You will also need a save method for this Doctype
@frappe.whitelist()
def save_fund_received(doc_data):
    """Saves the Fund Received data from the React form."""
    try:
        data = json.loads(doc_data)
        
        # You would add logic here to handle file attachments (base64 conversion)
        
        new_doc = frappe.new_doc("Fund Received")
        new_doc.update(data)
        new_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {"status": "success", "docname": new_doc.name}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Fund Received Save Error")
        raise e