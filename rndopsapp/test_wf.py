import sys, os
frappe_sites_path = '/home/prornd/project/frappe_dev/prornd'
sys.path.insert(0, os.path.join(frappe_sites_path, 'apps', 'frappe'))
try:
    import frappe
    frappe.init(site='prornd', sites_path=frappe_sites_path)
    frappe.connect()
    wfs = frappe.get_all('Workflow', filters={'document_type': 'Project Registration'}, fields=['name', 'is_active'])
    print(wfs)
    print("Transitions:")
    for wf in wfs:
        doc = frappe.get_doc('Workflow', wf.name)
        for t in doc.transitions:
            print(f"{t.state} -> {t.action} -> {t.next_state} (Rank: {t.condition})")
    frappe.destroy()
except Exception as e:
    import traceback
    traceback.print_exc()
