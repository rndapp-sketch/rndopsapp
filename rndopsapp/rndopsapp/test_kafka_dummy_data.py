import sys
import os
import json
from types import ModuleType

# --- Mock Frappe Module ---
# We need to mock frappe before importing kafka_sync because it imports frappe at top level
mock_frappe = ModuleType("frappe")
mock_frappe.log_error = lambda msg, title=None: print(f"FRAPPE LOG ERROR: {title} - {msg}")
mock_frappe.throw = lambda msg: print(f"FRAPPE THROW: {msg}")
mock_frappe._ = lambda x: x

class MockLogger:
    def info(self, msg):
        print(f"FRAPPE LOG INFO: {msg}")
    def warning(self, msg):
        print(f"FRAPPE LOG WARNING: {msg}")

mock_frappe.logger = lambda: MockLogger()

# Mock frappe.db
class MockDB:
    def get_value(self, doctype, name, fieldname):
        if doctype == "Department_prornd" and fieldname == "dept_id":
            return "DEPT-001" # Mocked Department ID
        return None

mock_frappe.db = MockDB()

sys.modules["frappe"] = mock_frappe

# --- Import Kafka Sync ---
# Ensure the current directory is in path to import kafka_sync
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    # Import the module to test
    # We import it as if it were a local module since we are in the same dir
    import kafka_sync
except ImportError:
    # If running from app root, try relative import adjustment
    sys.path.append(os.path.join(current_dir, '..', '..'))
    from rndopsapp.rndopsapp import kafka_sync

# --- Mock Documents ---
class MockDoc(dict):
    """
    A simple mock class that allows access via dot notation (doc.field)
    and behaves like a dictionary.
    """
    def __getattr__(self, key):
        return self.get(key)
    
    def __setattr__(self, key, value):
        self[key] = value

def test_dummy_data():
    print("=== Starting Standalone Dummy Data Test for Kafka Sync ===")
    
    # ---------------------------------------------------------
    # 1. Test Project Registration
    # ---------------------------------------------------------
    print("\n[1] Testing Project Registration Sync...")
    mock_project = MockDoc({
        "name": "PRJ-DUMMY-001",
        "pi_employee_id": "EMP001",
        "applicant_department": "Computer Science",
        "project_type": "Sponsored Research",
        "consultancy_category": "Category A",
        "funding_agency_type": "Government",
        "funding_agen": "DST",
        "funding_agency_schemes": "Scheme X",
        "total_budget_amount": 5000000.0,
        "overhead_percentage_research": 15.0,
        "overhead_research": 750000.0,
        "budget_including_overhead_research": 5750000.0,
        "service_tax_research": 18.0,
        "grand_total_research": 6785000.0,
        "project_duration_months": 24,
        "workflow_state": "Approved",
        "creation": "2025-01-01",
        "implementation_department": [] 
    })
    
    try:
        kafka_sync.publish_project(mock_project)
        print("✅ Project Registration sent successfully.")
    except Exception as e:
        print(f"❌ Project Registration failed: {e}")
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------
    # 2. Test Fund Sanction
    # ---------------------------------------------------------
    print("\n[2] Testing Fund Sanction Sync...")
    
    # Mock Child Rows for Budget Breakup
    budget_row_1 = MockDoc({
        "account_head": "Consumables",
        "total_proposal_of_heads": 100000.0,
        "first_year_budget": 50000.0,
        "second_year_budget": 50000.0,
        "third_year_budget": 0.0,
        "fourth_year_budget": 0.0,
        "fifth_year_budget": 0.0
    })
    
    mock_sanction = MockDoc({
        "name": "SAN-DUMMY-003", # Changed ID
        "refnum_prj_num": "PRJ-DUMMY-003",
        "sanctioned_letter_no": "SAN/2025/003",
        "sanctioned_letter_date": "2025-01-03",
        "total_sanctioned_amount": 300000.0,
        "sanctioned_budget_breakup": [budget_row_1]
    })
    
    try:
        kafka_sync.publish_sanction(mock_sanction)
        print("✅ Fund Sanction sent successfully.")
    except Exception as e:
        print(f"❌ Fund Sanction failed: {e}")
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------
    # 3. Test Fund Received
    # ---------------------------------------------------------
    print("\n[3] Testing Fund Received Sync...")
    
    # Mock Child Rows
    fund_breakup_row = MockDoc({
        "account_head": "Consumables",
        "amount_received": 50000.0,
        "remarks": "First installment"
    })
    
    transaction_row = MockDoc({
        "transaction_number": "UTR456789123",
        "transaction_date": "2025-01-03",
        "amount": 50000.0
    })
    
    mock_fund_received = MockDoc({
        "name": "REC-DUMMY-003",
        "sanction_ref_no": "SAN-DUMMY-003",
        "prjreg_title": "PRJ-DUMMY-003",
        "fund_received_amt": 50000.0,
        "bank_account": "SBI-0003",
        "received_amt_breakup": [fund_breakup_row],
        "fund_transactions": [transaction_row]
    })
    
    try:
        kafka_sync.publish_fund_received(mock_fund_received)
        print("✅ Fund Received sent successfully.")
    except Exception as e:
        print(f"❌ Fund Received failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_dummy_data()
