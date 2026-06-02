# START MKY 2026-06-01 11:38:00 IST - Listing client scripts for debugging
import frappe

def run():
    print("=== CLIENT SCRIPTS ===")
    scripts = frappe.get_all("Client Script", fields=["name", "dt", "enabled"])
    for s in scripts:
        print(s)
        # If any client script is for Recruitment or AccountHeadPayment, let's print its content
        if "recruitment" in str(s.dt).lower() or "payment" in str(s.dt).lower() or "salary" in str(s.dt).lower():
            doc = frappe.get_doc("Client Script", s.name)
            print(f"--- Script for {s.dt} ({s.name}) ---")
            print(doc.script)
            print("---------------------------------")
            
    print("=== SALARY STAGING RECORDS ===")
    records = frappe.get_all("Salary Staging", fields=["name", "salary_year_month"])
    for r in records:
        print(r)
# END MKY
