import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

def run():
    doctype = "Fund Sanction"
    fieldname = "workflow_state"

    print(f"Checking Custom Field '{fieldname}' on '{doctype}'...")

    existing = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname})
    if existing:
        print(f"✅ Custom field '{fieldname}' already exists as: {existing}")
    else:
        create_custom_field(doctype, {
            "fieldname": fieldname,
            "label": "Workflow State",
            "fieldtype": "Link",
            "options": "Workflow State",
            "insert_after": "sanction_workflow_status",
            "read_only": 1,
            "allow_on_submit": 1,
            "no_copy": 1,
            "hidden": 0,
            "in_list_view": 0,
        })
        frappe.db.commit()
        print(f"✅ Custom field '{fieldname}' created on '{doctype}'.")

    # Also backfill existing null workflow_state rows from sanction_workflow_status
    print("Backfilling workflow_state from sanction_workflow_status where NULL...")
    frappe.db.sql("""
        UPDATE `tabFund Sanction`
        SET workflow_state = sanction_workflow_status
        WHERE (workflow_state IS NULL OR workflow_state = '')
          AND sanction_workflow_status IS NOT NULL
          AND sanction_workflow_status != ''
    """)
    frappe.db.commit()
    print("✅ Backfill done.")
