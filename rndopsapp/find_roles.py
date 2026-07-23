import frappe

def execute():
    roles = frappe.get_all('Role', pluck='name')
    print("ALL ROLES:")
    for r in sorted(roles):
        print(r)
