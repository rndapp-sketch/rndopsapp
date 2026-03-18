import frappe
from rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium import save_disbursal_of_honorarium_data

def run_test():
    frappe.init(site="prornd.local")
    frappe.connect()
    
    # Simulate payload
    payload = {
        "applying_for_self_or_other": "Self",
        "project_name": "2026022501MeiTy000555",
        "project_number": "26C0556BSBESP0391xxLS"
    }
    
    try:
        res = save_disbursal_of_honorarium_data({"data": frappe.as_json(payload)})
        print("Save Result:", res)
        # Check if saved correctly
        if res.get("status") == "success":
            doc = frappe.get_doc("Disbursal of Honorarium", res["docname"])
            print("Saved Project Name:", doc.project_name)
            print("Saved Project Number:", doc.project_number)
            
            # Delete the test doc
            frappe.delete_doc("Disbursal of Honorarium", doc.name)
            frappe.db.commit()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    run_test()
