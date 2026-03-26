import frappe

def execute():
    frappe.init(site="prornd")
    frappe.connect()

    doctype_name = "Kafka Commit Staging"

    if frappe.db.exists("DocType", doctype_name):
        print(f"DocType '{doctype_name}' already exists.")
        return

    doc = frappe.get_doc({
        "doctype": "DocType",
        "name": doctype_name,
        "module": "rndopsapp",
        "custom": 1,
        "issingle": 0,
        "istable": 0,
        "fields": [
            {
                "fieldname": "reference_doctype",
                "fieldtype": "Data",
                "label": "Reference DocType",
                "reqd": 1,
                "in_list_view": 1
            },
            {
                "fieldname": "reference_name",
                "fieldtype": "Data",
                "label": "Reference Name",
                "reqd": 1,
                "in_list_view": 1
            },
            {
                "fieldname": "status",
                "fieldtype": "Select",
                "label": "Status",
                "options": "PENDING_APPROVAL\nPUBLISHED\nFAILED",
                "default": "PENDING_APPROVAL",
                "reqd": 1,
                "in_list_view": 1
            },
            {
                "fieldname": "payload",
                "fieldtype": "Code",
                "label": "Payload (JSON)",
                "options": "JSON",
                "reqd": 1
            },
            {
                "fieldname": "error_message",
                "fieldtype": "Small Text",
                "label": "Error Message",
                "read_only": 1
            }
        ],
        "permissions": [
            {
                "role": "System Manager",
                "read": 1,
                "write": 1,
                "create": 1,
                "delete": 1
            }
        ]
    })

    doc.insert()
    print(f"Successfully created custom DocType: '{doctype_name}'")

    frappe.db.commit()

if __name__ == "__main__":
    execute()
