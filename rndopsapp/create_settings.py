import frappe
from frappe.permissions import add_permission

def execute():
    doctype_name = "ProRnd Workflow Settings"
    if not frappe.db.exists("DocType", doctype_name):
        doc = frappe.new_doc("DocType")
        doc.name = doctype_name
        doc.module = "Rndopsapp"
        doc.custom = 1
        doc.issingle = 1
        
        doc.append("fields", {
            "fieldname": "dp_dean_limit",
            "label": "Direct Purchase Dean Approval Limit",
            "fieldtype": "Currency",
            "default": "200000"
        })
        
        doc.append("fields", {
            "fieldname": "dp_director_limit",
            "label": "Direct Purchase Director Approval Limit",
            "fieldtype": "Currency",
            "default": "1000000"
        })
        
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Grant permissions to System Manager so it can be accessed in Desk UI
        add_permission(doctype_name, "System Manager", 0)
        frappe.db.commit()
        
        print(f"✅ Created {doctype_name} Single Doctype.")
        
        # Set default values just in case
        settings = frappe.get_single(doctype_name)
        settings.dp_dean_limit = 200000
        settings.dp_director_limit = 1000000
        settings.save(ignore_permissions=True)
        frappe.db.commit()
        print("✅ Defaults seeded.")
    else:
        print(f"{doctype_name} already exists.")
