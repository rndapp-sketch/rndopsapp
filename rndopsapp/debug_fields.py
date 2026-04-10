
import frappe
import os
import sys

# Add bench path to sys.path
sys.path.append('/home/prornd/project/frappe_dev/prornd/apps/frappe')

# Initialize frappe
frappe.init(site="rndopsapp", sites_path="/home/prornd/project/frappe_dev/prornd/sites")
frappe.connect()

from rndopsapp.rndopsapp.doctype.research_deposit_slip.research_deposit_slip import get_research_deposit_slip_fields
import json

try:
    # Simulate the API call
    result = get_research_deposit_slip_fields()
    
    print("Successfully called get_research_deposit_slip_fields")
    
    if "fields" in result:
        print(f"Number of fields returned: {len(result['fields'])}")
        # Print first few fields to verify structure
        for f in result['fields'][:3]:
            print(f"Field: {f.get('fieldname')}, Label: {f.get('label')}")
            
        # Check if we have specific fields expected by the frontend
        expected_fields = ["project_title", "funding_agency", "total_amount"]
        found_fields = [f.get("fieldname") for f in result['fields']]
        
        missing = [f for f in expected_fields if f not in found_fields]
        if missing:
            print(f"CRITICAL: Missing expected fields: {missing}")
        else:
            print("All sample expected fields found.")
            
        print(json.dumps(result, indent=2, default=str))
    else:
        print("ERROR: 'fields' key missing in response")
        print(result)

except Exception as e:
    print(f"Error executing function: {e}")
    frappe.log_error(frappe.get_traceback(), "Debug Script Error")
