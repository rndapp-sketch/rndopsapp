import frappe
from rndopsapp.rndopsapp.doctype.universal_user__.universal_user__ import save_universal_user___data, get_universal_user___fields
import json

def test():
    print("Testing GET fields:")
    fields_resp = get_universal_user___fields()
    print("Fields count:", len(fields_resp.get("fields")))

    print("\nTesting SAVE payload:")
    data = {
      "profile_type_u_r": "Individual",
      "email_u_r": "jane.doe.api.test3@example.com",
      "mobile_number_u_r": "9876543210",
      "status_u_r": "Active",
      "full_name_u_r": "Jane Doe API Test",
      "username_u_r": "jane.doe.test3"
    }
    
    save_resp = save_universal_user___data(data)
    print("Save Response:", save_resp)
    
    docname = save_resp.get("docname")
    print("\nChecking saved doc:")
    doc = frappe.get_doc("Universal User__", docname)
    print(f"Mobile Number Formatted: {doc.mobile_number_u_r}")

test()
