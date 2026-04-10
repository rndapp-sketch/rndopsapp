import sys
sys.path.append('/home/rndops/Desktop/frappe_dev/prornd/apps/frappe')
import frappe

frappe.init(site='prornd.local', sites_path='/home/rndops/Desktop/frappe_dev/prornd/sites')
frappe.connect()

# Set user to Administrator to bypass permissions check during get_all if necessary
frappe.set_user("Administrator")

try:
    names = frappe.get_all(
        "Disbursal of Honorarium",
        filters={"project_number": "26C0556BSBESP0391xxLS"},
        fields=["name"],
    )
    print("GET_ALL RESULT:", names)
except Exception as e:
    print("EXCEPTION:", e)

