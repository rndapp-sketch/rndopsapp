
import frappe
import json
import sys
import os

def setup_frappe():
    cwd = os.getcwd()
    print(f"Current Working Directory: {cwd}")
    sites_path = os.path.join(cwd, "sites")
    print(f"Sites Path: {sites_path}")
    if not os.path.exists(sites_path):
        print("Sites directory not found!")
        sys.exit(1)

    os.chdir(sites_path)
    print(f"Changed CWD to: {os.getcwd()}")
        
    try:
        frappe.init(site="prornd.local")
        frappe.connect()
    except Exception as e:
        print(f"Failed to connect to Frappe: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_disbursal_of_honorarium():
    print("\n--- Testing Disbursal of Honorarium ---")
    
    # Import functions directly
    from rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium import (
        get_disbursal_of_honorarium_fields,
        save_disbursal_of_honorarium_data
    )

    # Test get_fields
    print("Testing get_disbursal_of_honorarium_fields...")
    fields_data = get_disbursal_of_honorarium_fields()
    print(f"Fields count: {len(fields_data.get('fields', []))}")
    print(f"Prefill data keys: {list(fields_data.get('prefill_data', {}).keys())}")
    
    # Test save
    print("Testing save_disbursal_of_honorarium_data...")
    data = {
        "applying_for_self_or_other": "Self",
        "total_amount": "1000",
        "table_weoy": [
            {
                "name_of_applicant": "Test Applicant",
                "amount": "1000"
            }
        ]
    }
    try:
        result = save_disbursal_of_honorarium_data(data=json.dumps(data))
        print("Save Result:", result)
        docname = result.get("docname")
        if docname:
             # Verify saved data
            doc = frappe.get_doc("Disbursal of Honorarium", docname)
            print(f"Created Doc: {doc.name}, Total Amount: {doc.total_amount}")
            
            # Clean up (commented out to keep record for manual verify if needed)
            # frappe.delete_doc("Disbursal of Honorarium", docname)
            # print("Deleted test doc")
    except Exception as e:
        print("Save Error:", str(e))


def test_disbursal_of_consultancy():
    print("\n--- Testing Disbursal of Consultancy ---")
    
    # Import functions directly
    from rndopsapp.rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy import (
        get_disbursal_of_consultancy_fields,
        save_disbursal_of_consultancy_data
    )

    # Test get_fields
    print("Testing get_disbursal_of_consultancy_fields...")
    fields_data = get_disbursal_of_consultancy_fields()
    print(f"Fields count: {len(fields_data.get('fields', []))}")
    
    # Test save with calculation
    print("Testing save_disbursal_of_consultancy_data with calculations...")
    data = {
        "project_title": "Test Consultancy Project",
        "total_amount_received": "50000",
        "details_of_disbursal": [
            {
                "disbursal_amount": "10000",
                "disbursal_employee_student": "Employee"
            }
        ]
    }
    try:
        result = save_disbursal_of_consultancy_data(data=json.dumps(data))
        print("Save Result:", result)
        docname = result.get("docname")
        if docname:
            doc = frappe.get_doc("Disbursal of Consultancy", docname)
            print(f"Created Doc: {doc.name}")
            print(f"Total Disbursal: {doc.total_disbursal_amount} (Expected: 10000.0)")
            print(f"Personal Share (70%): {doc.total_personal_share} (Expected: 7000.0)")
            print(f"Institute Share (30%): {doc.total_institute_share} (Expected: 3000.0)")
            print(f"IDF (40% of Inst): {doc.idf} (Expected: 1200.0)")
            
    except Exception as e:
        print("Save Error:", str(e))

if __name__ == "__main__":
    setup_frappe()
    try:
        test_disbursal_of_honorarium()
        test_disbursal_of_consultancy()
    except Exception as e:
        print("Test Runner Error:", str(e))
    finally:
        if frappe.db:
            frappe.db.rollback()
            frappe.destroy()
