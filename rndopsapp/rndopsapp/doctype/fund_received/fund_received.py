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
# def save_fund_received(doc_data):
#     """Saves the Fund Received data from the React form."""
#     try:
#         data = json.loads(doc_data)
#         print("Received data for Fund Received:", data)  # Debug log
        
#         # Create new Fund Received document
#         new_doc = frappe.new_doc("Fund Received")
        
#         # Map the form data to doctype fields
#         field_mapping = {
#             'prjreg_title': 'prjreg_title',
#             'sanction_ref_no': 'sanction_ref_no', 
#             'prj_type': 'prj_type',
#             'fund_received_amt': 'fund_received_amt',
#             'bank_account': 'bank_account',
#             'gst_invoice_issued': 'gst_invoice_issued',
#             'invoice_no': 'invoice_no'
#         }
        
#         # Update document with mapped data
#         for form_field, doctype_field in field_mapping.items():
#             if form_field in data and data[form_field] not in [None, ""]:
#                 new_doc.set(doctype_field, data[form_field])
        
#         # Handle child tables - FILTER OUT EMPTY ROWS
#         if 'fund_transactions' in data:
#             for transaction in data['fund_transactions']:
#                 # Only add rows that have at least transaction_number OR amount > 0
#                 if (transaction.get('transaction_number') not in [None, ""] or 
#                     transaction.get('amount', 0) > 0):
#                     new_doc.append('fund_transactions', {
#                         'transaction_number': transaction.get('transaction_number') or "",
#                         'transaction_date': transaction.get('transaction_date'),
#                         'amount': transaction.get('amount', 0)
#                     })
        
#         if 'received_amt_breakup' in data:
#             for breakup in data['received_amt_breakup']:
#                 # Only add rows that have at least account_head OR amount_received > 0
#                 if (breakup.get('account_head') not in [None, ""] or 
#                     breakup.get('amount_received', 0) > 0):
#                     new_doc.append('received_amt_breakup', {
#                         'account_head': breakup.get('account_head') or "",
#                         'amount_received': breakup.get('amount_received', 0),
#                         'budget_year': breakup.get('budget_year', 1),
#                         'remarks': breakup.get('remarks') or ""
#                     })
        
#         # Save the document
#         new_doc.insert(ignore_permissions=True)
#         frappe.db.commit()

#         print(f"Successfully created Fund Received: {new_doc.name}")  # Debug log
#         return {"status": "success", "docname": new_doc.name}
        
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Fund Received Save Error")
#         frappe.db.rollback()
#         frappe.throw(f"Failed to save Fund Received: {str(e)}")
# # import frappe


@frappe.whitelist()
def save_fund_received(doc_data):
    """Saves the Fund Received data from the React form."""
    try:
        data = json.loads(doc_data)
        print("Received data for Fund Received:", data)  # Debug log
        
        # Create new Fund Received document
        new_doc = frappe.new_doc("Fund Received")
        
        # Map the form data to doctype fields
        field_mapping = {
            'prjreg_title': 'prjreg_title',
            'sanction_ref_no': 'sanction_ref_no', 
            'prj_type': 'prj_type',
            'fund_received_amt': 'fund_received_amt',
            'bank_account': 'bank_account',
            'gst_invoice_issued': 'gst_invoice_issued',
            'invoice_no': 'invoice_no'
        }
        
        # Update document with mapped data
        for form_field, doctype_field in field_mapping.items():
            if form_field in data and data[form_field] not in [None, ""]:
                new_doc.set(doctype_field, data[form_field])
        
        # Handle child tables - FILTER OUT EMPTY ROWS
        if 'fund_transactions' in data:
            for transaction in data['fund_transactions']:
                # Only add rows that have at least transaction_number OR amount > 0
                if (transaction.get('transaction_number') not in [None, ""] or 
                    transaction.get('amount', 0) > 0):
                    
                    # Handle file attachment if present
                    attachment_data = {}
                    if transaction.get('file_data') and transaction.get('file_name'):
                        # Save the file and get the file URL
                        file_doc = save_file(
                            fname=transaction.get('file_name'),
                            content=transaction.get('file_data'),
                            dt="Fund Received",
                            dn=new_doc.name,
                            folder="Home/Attachments"
                        )
                        if file_doc:
                            attachment_data['attachment'] = file_doc.file_url
                    
                    new_doc.append('fund_transactions', {
                        'transaction_number': transaction.get('transaction_number') or "",
                        'transaction_date': transaction.get('transaction_date'),
                        'amount': transaction.get('amount', 0),
                        **attachment_data
                    })
        
        if 'received_amt_breakup' in data:
            for breakup in data['received_amt_breakup']:
                # Only add rows that have at least account_head OR amount_received > 0
                if (breakup.get('account_head') not in [None, ""] or 
                    breakup.get('amount_received', 0) > 0):
                    new_doc.append('received_amt_breakup', {
                        'account_head': breakup.get('account_head') or "",
                        'amount_received': breakup.get('amount_received', 0),
                        'budget_year': breakup.get('budget_year', 1),
                        'remarks': breakup.get('remarks') or ""
                    })
        
        # Save the document
        new_doc.insert(ignore_permissions=True)
        frappe.db.commit()

        print(f"Successfully created Fund Received: {new_doc.name}")  # Debug log
        return {"status": "success", "docname": new_doc.name}
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Fund Received Save Error")
        frappe.db.rollback()
        frappe.throw(f"Failed to save Fund Received: {str(e)}")

def save_file(fname, content, dt, dn, folder=None):
    """Save base64 file content as a File document"""
    try:
        import base64
        from frappe.utils.file_manager import save_file
        
        # Decode base64 content
        file_content = base64.b64decode(content)
        
        # Save the file
        file_doc = save_file(
            fname=fname,
            content=file_content,
            dt=dt,
            dn=dn,
            folder=folder,
            is_private=0
        )
        
        return file_doc
    except Exception as e:
        print(f"Error saving file {fname}: {str(e)}")
        return None




# jimmy added
@frappe.whitelist()
def get_fund_received_fields(doc_name=None):
	"""
	API to return Fund Received field metadata and prefill data
	based on a Project Registration ref number (doc_name).
	"""
	fund_received_meta = frappe.get_meta("Fund Received")

	fields = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
		}
		for f in fund_received_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_project_data = {}

	if not doc_name:
		frappe.throw("Project ref number (doc_name) is required.")

	# Clean input
	doc_name = str(doc_name).strip('"').strip("'")

	# Fetch Project Registration
	project_doc = frappe.db.get_value(
		"Project Registration", doc_name, ["name", "project_title", "project_type"], as_dict=True
	)

	if not project_doc:
		frappe.throw(f"Project Registration '{doc_name}' not found.")

	related_project_data = project_doc
	prefill_data["prjreg_refnum"] = project_doc.name

	# Fetch Fund Sanction linked to this project
	sanctions = frappe.get_all(
		"Fund Sanction",
		filters={"refnum_prj_num": project_doc.name},
		fields=["name as value", "sanctioned_letter_no as label", "project_proposal", "refnum_prj_num"],
	)

	# Only prefill if Fund Sanction ref matches project
	if sanctions:
		# If there’s exactly one sanction, prefill related fields
		if len(sanctions) == 1:
			sanction_doc = frappe.get_doc("Fund Sanction", sanctions[0]["value"])
			prefill_data.update(
				{
					"sanction_ref_no": sanction_doc.name,
					"project_proposal": sanction_doc.project_proposal,
					# Add more fields from sanction if needed
					# "sanctioned_amount": sanction_doc.sanctioned_amount,
					# "sanction_date": sanction_doc.sanction_date
				}
			)

	# Link options for dropdowns
	link_options["prjreg_refnum"] = [{"value": project_doc.name, "label": project_doc.project_title}]
	link_options["sanction_ref_no"] = sanctions
	link_options["amended_from"] = frappe.get_all("Fund Received", fields=["name as value"])

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_project_data": related_project_data,
	}

