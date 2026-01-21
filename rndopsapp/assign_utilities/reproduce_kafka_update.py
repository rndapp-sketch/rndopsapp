
import sys
import os

# Add bench path to sys.path
sys.path.append('/home/prornd/project/frappe_dev/prornd/apps/frappe')
sys.path.append('/home/prornd/project/frappe_dev/prornd/apps/rndopsapp')

import frappe
from rndopsapp.rndopsapp.kafka_consumer import update_fund_received

def simulate_kafka_update():
    frappe.init(site="prornd.local", sites_path="sites")
    frappe.connect()

    # 1. Create a dummy Fund Received doc if not exists
    doc_name = "REC_150126274-prjreg_refnum"
    if not frappe.db.exists("Fund Received", doc_name):
        doc = frappe.new_doc("Fund Received")
        doc.name = doc_name  # Force name if possible, or we rely on autoname
        # Since autoname is expression, we might need to rely on that or force it differently.
        # Actually, let's just create one normally and use its name.
        doc.prjreg_title = frappe.get_last_doc("Project Registration").name
        doc.fund_received_amt = 1000
        doc.workflow_state = "Draft"
        doc.save(ignore_permissions=True)
        doc_name = doc.name
        frappe.db.commit()
        print(f"Created test doc: {doc_name}")
    
    # 2. Simulate Kafka Message Data
    data = {
        "fundReceivedRefNumber": 9999, # Irrelevant if we use FAP ref
        "fundReceivedRefNumberFap": doc_name, # THIS is the key
        "sanctionLetterNo": "ref0001",
        "projectNumber": "2026010801MeiTy000215",
        "amountReceived": 6000.0,
        "iitgAccountNumber": "SBI-0006",
        "depositSlipStatus": False,
        "fundReceivedStatus": "APPROVED",
        "fundBudgetBreakupList": [],
        "transactionDetailsList": []
    }

    print(f"Simulating update for {doc_name} with status APPROVED")

    # 3. Call update function
    updated_doc = update_fund_received(
        fund_received_ref_number=data.get('fundReceivedRefNumber'),
        fund_received_ref_number_fap=data.get('fundReceivedRefNumberFap'),
        sanction_letter_no=data.get('sanctionLetterNo'),
        project_number=data.get('projectNumber'),
        amount_received=data.get('amountReceived'),
        iitg_account_number=data.get('iitgAccountNumber'),
        deposit_slip_status=data.get('depositSlipStatus'),
        fund_received_status=data.get('fundReceivedStatus'),
        timestamp="2026-01-16T12:00:00"
    )

    if updated_doc:
        print(f"Success! Doc updated. Status: {updated_doc.workflow_state}")
        print(f"Amount: {updated_doc.fund_received_amt}")
    else:
        print("Failed to update doc.")

if __name__ == "__main__":
    frappe.connect()
    simulate_kafka_update()
