import frappe
def print_last_error():
    logs = frappe.get_all("Error Log", fields=["method", "error"], order_by="creation desc", limit=1)
    if logs:
        print("Method:", logs[0].method)
        print("Error:\n", logs[0].error)
    else:
        print("No errors found.")
