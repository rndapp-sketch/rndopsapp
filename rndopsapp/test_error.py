import frappe
def test_error():
    doc = frappe.new_doc("Universal Registration__")
    doc.email_address_u_r = "test@abc.com"
    doc.uploaded_documents_u_r = '[{"document_name_u_r": "PAN", "id_number_u_r": "ABC"}]'
    # Wait, what if it's already a dict but we assign it to a field?
    # doc.some_string_field = {"key": "val"} -> frappe assigns it.
    
    # What if the frontend sends a stringified dictionary for an individual field?
    
    try:
        doc.save(ignore_permissions=True, ignore_version=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
