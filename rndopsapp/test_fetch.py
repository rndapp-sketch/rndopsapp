import sys
sys.path.append('/home/rndops/Desktop/frappe_dev/prornd/apps/frappe')
import frappe

frappe.init(site='prornd.local', sites_path='/home/rndops/Desktop/frappe_dev/prornd/sites')
frappe.connect()

from rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium import get_disbursal_of_honorarium_by_project

# Set user toAdministrator to bypass permissions check during get_all if necessary
frappe.set_user("Administrator")

res = get_disbursal_of_honorarium_by_project(project_code="26C0556BSBESP0391xxLS")
print("Number of results:", len(res.get("message", [])))
if res.get("message"):
    print("First result name:", res["message"][0].get("name"))
    print("First result project_number:", res["message"][0].get("project_number"))
