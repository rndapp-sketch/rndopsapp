import frappe
import requests
import json
from frappe.utils import today, flt
from datetime import datetime
from rndopsapp.rndopsapp.transaction_dto import AccountHeadCommitDTO, AccountHeadPaymentDTO
from rndopsapp.rndopsapp.kafka_sync import publish_message, KAFKA_AVAILABLE

# New Kafka producer imports - sumit
from rndopsapp.rndopsapp.kafka.producer.reimbursement import (
    publish_commit as kafka_publish_commit,
    publish_payment as kafka_publish_payment
)

# External API endpoints
LEDGER_API_BASE_URL = "http://172.16.134.81:18080/api/commit-payment-transactions"
ACCOUNT_HEAD_PAYMENTS_API_URL = "http://172.16.134.81:18080/api/account-head-payments"
ACCOUNT_HEAD_COMMIT_API_URL = "http://172.16.134.81:18080/api/account-head-commit"

# Valid commit statuses
VALID_COMMIT_STATUSES = ["SETTLED", "PARTIALLY_PAID", "OVERPAYMENT", "PENDING"]


@frappe.whitelist()
def get_project_available_amounts(project_number):
    """
    Fetch available commit and payment amounts for a project from the external ledger API.
    
    Returns:
        dict: {
            "projectNumber": str,
            "totalFundReceived": float,
            "totalCommitted": float,
            "totalPaid": float,
            "availableCommitAmount": float,  # This is the "Actual Balance"
            "availablePaymentAmount": float  # This is the "Commitable"
        }
    """
    if not project_number:
        return {"status": "error", "message": "Project number is required"}
    
    try:
        api_url = f"{LEDGER_API_BASE_URL}/total-available-amounts?projectNumber={project_number}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "data": {
                    "projectNumber": data.get("projectNumber", project_number),
                    "totalFundReceived": flt(data.get("totalFundReceived", 0)),
                    "totalCommitted": flt(data.get("totalCommitted", 0)),
                    "totalPaid": flt(data.get("totalPaid", 0)),
                    "availableCommitAmount": flt(data.get("availableCommitAmount", 0)),
                    "availablePaymentAmount": flt(data.get("availablePaymentAmount", 0)),
                    # Formatted display values
                    "actualBalance": flt(data.get("availableCommitAmount", 0)),
                    "committable": flt(data.get("availablePaymentAmount", 0))
                }
            }
        else:
            frappe.log_error(
                f"Ledger API Error - Status: {response.status_code}, Response: {response.text}",
                "Get Project Available Amounts API Error"
            )
            return {
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "details": response.text
            }
    
    except requests.exceptions.Timeout:
        frappe.log_error("Ledger API timeout", "Get Project Available Amounts Timeout")
        return {"status": "error", "message": "API request timed out"}
    
    except requests.exceptions.ConnectionError as e:
        frappe.log_error(str(e), "Get Project Available Amounts Connection Error")
        return {"status": "error", "message": "Could not connect to the ledger API"}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Project Available Amounts Error")
        return {"status": "error", "message": str(e)}

# Define topics for commit and payment (assuming these topics based on user request "same for payment also")
# Ideally these should be defined in kafka_sync.py constant list, but for now using string literals or importing if added.
TOPIC_COMMIT = 'account-head-commit-events'
TOPIC_PAYMENT = 'account-head-payment-events'
TOPIC_COMMIT_DLQ = 'account-head-commit-events-dlq'
TOPIC_PAYMENT_DLQ = 'account-head-payment-events-dlq'

# sumit - old function commented out, use submit_commit_kafka instead
# @frappe.whitelist()
# def submit_commit_data(doctype, name, project_name, commit_amount, budget_head, bmr=None):
#     """
#     Endpoint to prepare AND submit commit data from a Frappe document (e.g. Reimbursement).
#     Publishes to Kafka topic 'account-head-commit-events'.
#     """
#     try:
#         doc = frappe.get_doc(doctype, name)
#
#         # Resolve Budget Head ID from name if needed
#         # budget_head input is likely a string name like "Equipments"
#         account_head_id = budget_head
#         if budget_head and isinstance(budget_head, str) and not budget_head.isdigit():
#              # Try to find ID from Budget Head doctype
#              found_id = frappe.db.get_value("Budget Head", {"budget_head": budget_head}, "id")
#              if found_id:
#                   account_head_id = found_id
#
#         # Make sure it's int if possible
#         try:
#             account_head_id = int(account_head_id)
#         except (ValueError, TypeError):
#             pass
#
#         # Mapping logic
#         particulars = getattr(doc, "comment", f"Commitment for {doc.name}")
#         # 2026010801MeiTy000215
#         # projectNumber=project_name,
#         # Construct DTO
#         dto = AccountHeadCommitDTO(
#             transactionCommitNumber=None, # To be generated by backend?
#             projectNumber=project_name,
#             accountHeadId=account_head_id,
#             transactionReceivedRefNumber=8, # Missing info, defaulted to None
#             commitDate=today(),
#             commitParticular=particulars,
#             refDetails=doc.name,
#             commitAmount=flt(commit_amount),
#             status="COMMITTED"
#         )
#
#         payload_data = dto.to_dict()
#
#         # Wrap payload
#         wrapped_payload = {
#             "schemaVersion": "1.0",
#             "eventType": "ACCOUNT_HEAD_COMMIT",
#             "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
#             "data": payload_data
#         }
#
#         # Publish to Kafka
#         if KAFKA_AVAILABLE:
#             # key could be project_name to keep ordering
#             success = publish_message(TOPIC_COMMIT, wrapped_payload, doc.name, TOPIC_COMMIT_DLQ, key=project_name)
#             if success:
#                  return {"status": "success", "message": "Commit data submitted to Kafka", "data": payload_data}
#             else:
#                  return {"status": "error", "message": "Failed to publish commit data to Kafka", "data": payload_data}
#         else:
#             return {"status": "warning", "message": "Kafka not available, changes not synced", "data": payload_data}
#
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Submit Commit Data Error")
#         return {"status": "error", "message": str(e)}

# sumit - old function commented out, use submit_payment_kafka instead
# @frappe.whitelist()
# def submit_payment_data(doctype, name=None, project_name=None, payment_amount=None, budget_head=None, bmr=None):
#     """
#     Endpoint to prepare AND submit payment data from AccountHeadPayment doctype.
#     Publishes to Kafka topic 'account-head-payment-events'.
#
#     Args:
#         doctype: The doctype name (should be 'AccountHeadPayment')
#         name: The document name (Optional if submitting without saving)
#         project_name: Optional override for project_ref_number
#         payment_amount: Optional override for payment_amount
#         budget_head: Optional override for budget_head
#         bmr: Optional override for payment_bmr
#     """
#     try:
#         doc = None
#         if name:
#             try:
#                 doc = frappe.get_doc(doctype, name)
#             except frappe.DoesNotExistError:
#                 pass
#
#         # If doc doesn't exist (not saved yet), use form data
#         if not doc:
#             doc = frappe._dict(frappe.form_dict)
#             if not doc.name:
#                 doc.name = f"NEW-PAYMENT-{frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')}"
#
#         # Extract data from AccountHeadPayment doctype fields
#         project_number = project_name or getattr(doc, "project_ref_number", None)
#         commit_id = getattr(doc, "commit_id", None)
#         payment_date_val = getattr(doc, "payment_date", today())
#         payment_particular = getattr(doc, "payment_particular", f"Payment for {doc.name}")
#         payment_ref_details = getattr(doc, "payment_reference_details", doc.name)
#         payment_amt = payment_amount or getattr(doc, "payment_amount", 0.0)
#         payment_bmr = bmr or getattr(doc, "payment_bmr", None)
#         payment_status = getattr(doc, "payment_status", "PENDING")
#         bank_txn_num = getattr(doc, "bank_transaction_number", None)
#         bank_txn_date = getattr(doc, "bank_transaction_date", today())
#
#         # Resolve Budget Head ID from budget_head field
#         budget_head_value = budget_head or getattr(doc, "budget_head", None)
#         account_head_id = budget_head_value
#
#         if budget_head_value:
#              # If it's a digit, use it directly (as int)
#              if isinstance(budget_head_value, (int, float)) or (isinstance(budget_head_value, str) and budget_head_value.isdigit()):
#                  account_head_id = int(budget_head_value)
#              else:
#                  # It's a non-digit string, likely a name or title
#                  # First try to find by name (PK)
#                  found_id = frappe.db.get_value("Budget Head", budget_head_value, "id")
#                  if not found_id:
#                       # Try by budget_head field
#                       found_id = frappe.db.get_value("Budget Head", {"budget_head": budget_head_value}, "id")
#
#                  if found_id:
#                       account_head_id = found_id
#
#         # Final safety conversion
#         try:
#             account_head_id = int(account_head_id)
#         except (ValueError, TypeError):
#              # If conversion fails, log a warning but proceed (or could default to 0/None)
#              frappe.log_error(f"Could not convert account_head_id '{account_head_id}' to int", "Submit Payment Data Warning")
#              pass
#
#         # Construct DTO
#         dto = AccountHeadPaymentDTO(
#             transactionPaymentNumber=None,  # To be generated by backend
#             transactionCommitNumber=commit_id,
#             projectNumber=project_number,
#             accountHeadId=account_head_id,
#             paymentDate=payment_date_val,
#             paymentParticular=payment_particular,
#             paymentRefDetails=payment_ref_details,
#             paymentAmount=flt(payment_amt),
#             bmr=payment_bmr,
#             paymentStatus=payment_status,
#             bankTransactionNumber=bank_txn_num,
#             bankTransactionDate=bank_txn_date
#         )
#
#         payload_data = dto.to_dict()
#
#         wrapped_payload = {
#             "schemaVersion": "1.0",
#             "eventType": "ACCOUNT_HEAD_PAYMENT",
#             "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f"),
#             "data": payload_data
#         }
#
#         if KAFKA_AVAILABLE:
#             success = publish_message(TOPIC_PAYMENT, wrapped_payload, doc.name, TOPIC_PAYMENT_DLQ, key=project_number)
#             if success:
#                 return {"status": "success", "message": "Payment data submitted to Kafka", "data": payload_data}
#             else:
#                 return {"status": "error", "message": "Failed to publish payment data to Kafka", "data": payload_data}
#         else:
#             return {"status": "warning", "message": "Kafka not available, changes not synced", "data": payload_data}
#
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Submit Payment Data Error")
#         return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_payments_by_account_head(account_head_id):
    """
    Fetch payments by accountHeadId from the external ledger API.
    
    Args:
        account_head_id: The account head ID to fetch payments for
        
    Returns:
        dict: API response with payments data or error
    """
    if not account_head_id:
        return {"status": "error", "message": "Account Head ID is required"}
    
    try:
        api_url = f"{ACCOUNT_HEAD_PAYMENTS_API_URL}/account-head/{account_head_id}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "data": data
            }
        else:
            frappe.log_error(
                f"Get Payments API Error - Status: {response.status_code}, Response: {response.text}",
                "Get Payments By Account Head API Error"
            )
            return {
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "details": response.text
            }
    
    except requests.exceptions.Timeout:
        frappe.log_error("Get Payments API timeout", "Get Payments By Account Head Timeout")
        return {"status": "error", "message": "API request timed out"}
    
    except requests.exceptions.ConnectionError as e:
        frappe.log_error(str(e), "Get Payments By Account Head Connection Error")
        return {"status": "error", "message": "Could not connect to the ledger API"}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Payments By Account Head Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_commits_by_status(status):
    """
    Fetch commits by status from the external ledger API.
    Valid statuses: SETTLED, PARTIALLY_PAID, OVERPAYMENT, PENDING
    
    Args:
        status: The status to filter commits by
        
    Returns:
        dict: API response with commits data or error
    """
    if not status:
        return {"status": "error", "message": "Status is required"}
    
    status = status.upper()
    if status not in VALID_COMMIT_STATUSES:
        return {
            "status": "error", 
            "message": f"Invalid status. Must be one of: {', '.join(VALID_COMMIT_STATUSES)}"
        }
    
    try:
        api_url = f"{ACCOUNT_HEAD_COMMIT_API_URL}/by-status/{status}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "data": data
            }
        else:
            frappe.log_error(
                f"Get Commits By Status API Error - Status: {response.status_code}, Response: {response.text}",
                "Get Commits By Status API Error"
            )
            return {
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "details": response.text
            }
    
    except requests.exceptions.Timeout:
        frappe.log_error("Get Commits By Status API timeout", "Get Commits By Status Timeout")
        return {"status": "error", "message": "API request timed out"}
    
    except requests.exceptions.ConnectionError as e:
        frappe.log_error(str(e), "Get Commits By Status Connection Error")
        return {"status": "error", "message": "Could not connect to the ledger API"}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Commits By Status Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_commits_by_account_head(account_head_id):
    """
    Fetch commits by accountHeadId from the external ledger API.
    
    Args:
        account_head_id: The account head ID to fetch commits for
        
    Returns:
        dict: API response with commits data or error
    """
    if not account_head_id:
        return {"status": "error", "message": "Account Head ID is required"}
    
    try:
        api_url = f"{ACCOUNT_HEAD_COMMIT_API_URL}/by-account-head/{account_head_id}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "data": data
            }
        else:
            frappe.log_error(
                f"Get Commits By Account Head API Error - Status: {response.status_code}, Response: {response.text}",
                "Get Commits By Account Head API Error"
            )
            return {
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "details": response.text
            }
    
    except requests.exceptions.Timeout:
        frappe.log_error("Get Commits By Account Head API timeout", "Get Commits By Account Head Timeout")
        return {"status": "error", "message": "API request timed out"}
    
    except requests.exceptions.ConnectionError as e:
        frappe.log_error(str(e), "Get Commits By Account Head Connection Error")
        return {"status": "error", "message": "Could not connect to the ledger API"}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Commits By Account Head Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_commits_by_account_head_and_status(account_head_id, status):
    """
    Fetch commits by accountHeadId and status from the external ledger API.
    Valid statuses: SETTLED, PARTIALLY_PAID, OVERPAYMENT, PENDING
    
    Args:
        account_head_id: The account head ID to fetch commits for
        status: The status to filter commits by
        
    Returns:
        dict: API response with commits data or error
    """
    if not account_head_id:
        return {"status": "error", "message": "Account Head ID is required"}
    
    if not status:
        return {"status": "error", "message": "Status is required"}
    
    status = status.upper()
    if status not in VALID_COMMIT_STATUSES:
        return {
            "status": "error", 
            "message": f"Invalid status. Must be one of: {', '.join(VALID_COMMIT_STATUSES)}"
        }
    
    try:
        api_url = f"{ACCOUNT_HEAD_COMMIT_API_URL}/by-account-head/{account_head_id}/status/{status}"
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "data": data
            }
        else:
            frappe.log_error(
                f"Get Commits By Account Head and Status API Error - Status: {response.status_code}, Response: {response.text}",
                "Get Commits By Account Head and Status API Error"
            )
            return {
                "status": "error",
                "message": f"API returned status {response.status_code}",
                "details": response.text
            }
    
    except requests.exceptions.Timeout:
        frappe.log_error("Get Commits By Account Head and Status API timeout", "Get Commits By Account Head and Status Timeout")
        return {"status": "error", "message": "API request timed out"}
    
    except requests.exceptions.ConnectionError as e:
        frappe.log_error(str(e), "Get Commits By Account Head and Status Connection Error")
        return {"status": "error", "message": "Could not connect to the ledger API"}
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Commits By Account Head and Status Error")
        return {"status": "error", "message": str(e)}


# ==========================================
# New Kafka Producer Implementation - sumit
# Old implementation is commented above for reference
# ==========================================

@frappe.whitelist()
def submit_commit_data(doctype, frapAppId, name, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None):
    """
    Submit commit data by staging it in Kafka Commit Staging. 
    It will be published to Kafka later upon workflow reaching 'Approved' (Dean Approval).
    Works for Reimbursement, Travel, Temporary Advance, Advance Settlement, etc.
    """
    try:
        # Basic validation
        if not frappe.db.exists(doctype, name):
             return {"status": "error", "message": f"Document {doctype} {name} not found"}
             
        # Create Payload
        payload = {
            "commit_amount": flt(commit_amount),
            "budget_head": budget_head,
            "project_name": project_name,
            "bmr": bmr,
            "bill_amount": flt(bill_amount) if bill_amount else None,
            "frap_app_id": frapAppId,
            "ref_details": refDetails
        }

        # Check if a staging doc already exists for this reference
        existing_staging = frappe.get_all("Kafka Commit Staging", filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "status": "PENDING_APPROVAL"
        }, limit=1)

        if existing_staging:
            staging_doc = frappe.get_doc("Kafka Commit Staging", existing_staging[0].name)
            staging_doc.payload = json.dumps(payload)
            staging_doc.save(ignore_permissions=True)
        else:
            staging_doc = frappe.get_doc({
                "doctype": "Kafka Commit Staging",
                "reference_doctype": doctype,
                "reference_name": name,
                "payload": json.dumps(payload),
                "status": "PENDING_APPROVAL"
            })
            staging_doc.insert(ignore_permissions=True)

        return {"status": "success", "message": "Commit payload staged for Kafka publishing upon approval"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Submit Commit Data Error")
        return {"status": "error", "message": str(e)}


def check_workflow_and_publish(doc, method=None):
    """
    Centralized workflow hook to publish staged commit data when approved by Dean (state: Approved).
    Triggered on_update of documents.
    """
    applicable_doctypes = [
        "Reimbursement",
        "Temporary Advance",
        "Disbursal of Honorarium",
        "Disbursal of Consultancy",
        "Direct Purchase",
        "Advance Settlement",
        "Travel",
        "TA DA Settlement"
    ]
    
    if doc.doctype not in applicable_doctypes:
        return

    # Check if workflow_state changed to exactly "Approved"
    current_state = doc.get("workflow_state")
    if current_state != "Approved":
        return

    # To ensure idempotency (only publish once when transitioning TO Approved)
    doc_before = doc.get_doc_before_save()
    if doc_before and doc_before.get("workflow_state") == "Approved":
        return

    # Look for pending staging docs
    staging_docs = frappe.get_all("Kafka Commit Staging", filters={
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "status": ["in", ["PENDING_APPROVAL", "FAILED"]]
    })

    if not staging_docs:
        return

    for st in staging_docs:
        staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
        try:
            payload = json.loads(staging_doc.payload)
            
            # Publish to Kafka
            success = kafka_publish_commit(
                doc=doc,
                commit_amount=payload.get("commit_amount"),
                budget_head=payload.get("budget_head"),
                project_name=payload.get("project_name"),
                bmr=payload.get("bmr"),
                bill_amount=payload.get("bill_amount"),
                frap_app_id=payload.get("frap_app_id"),
                ref_details=payload.get("ref_details")
            )

            if success:
                staging_doc.db_set("status", "PUBLISHED")
            else:
                staging_doc.db_set("status", "FAILED")
                staging_doc.db_set("error_message", "kafka_publish_commit returned False")

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Process Staged Commit Error")
            staging_doc.db_set("status", "FAILED")
            staging_doc.db_set("error_message", str(e))


@frappe.whitelist()
def submit_payment_data(doctype=None, name=None, project_name=None, payment_amount=None, budget_head=None, bmr=None, refDetails=None, frapAppId=None, moduleName=None):
    """
    Submit payment data using new Kafka producer.
    Works for doctype.
    """
    try:
        # Normalize name: treat "None", "null", empty string as actual None
        if not name or name in ("None", "null", "undefined", ""):
            name = None

        doc = None
        if name:
            try:
                doc = frappe.get_doc(doctype, name)
            except frappe.DoesNotExistError:
                pass

        # If doc doesn't exist (not saved yet), initialize new one
        is_new = False
        if not doc:
            is_new = True
            doc = frappe.new_doc(doctype)
        
        # --- Populate Document Fields ---
        # Helper to prefer explicit arg, then form field, then existing doc value
        def get_val(arg_val, fieldname, default=None):
            if arg_val is not None: 
                return arg_val
            if fieldname in frappe.form_dict:
                return frappe.form_dict[fieldname]
            return getattr(doc, fieldname, default)

        raw_project_ref = get_val(project_name, 'project_ref_number')
        resolved_project_ref = raw_project_ref
        
        if raw_project_ref and not frappe.db.exists("Project Registration", raw_project_ref):
            found_proj = frappe.db.get_value("Project Registration", {"project_no": raw_project_ref}, "name")
            if found_proj:
                resolved_project_ref = found_proj
                
        doc.project_ref_number = resolved_project_ref
        doc.payment_amount = flt(get_val(payment_amount, 'payment_amount', 0))
        
        # Resolve Budget Head to valid Link Name (PK)
        raw_budget_head = get_val(budget_head, 'budget_head')
        resolved_budget_head = raw_budget_head
        
        # If value exists and is not already a valid PK, try to find the PK
        if raw_budget_head and not frappe.db.exists("Budget Head", raw_budget_head):
            # Try by 'budget_head' field (e.g. "Equipments")
            found_name = frappe.db.get_value("Budget Head", {"budget_head": raw_budget_head}, "name")
            if not found_name:
                # Try by 'id' field (if integer passed)
                found_name = frappe.db.get_value("Budget Head", {"id": raw_budget_head}, "name")
            
            if found_name:
                resolved_budget_head = found_name
        
        doc.budget_head = resolved_budget_head
        doc.payment_bmr = get_val(bmr, 'payment_bmr')
        
        # Populate other fields from form_dict if present, supporting camelCase alternatives
        field_map = {
            'payment_particular': ['paymentParticular'],
            'payment_reference_details': ['paymentRefDetails'],
            'payment_status': ['paymentStatus'],
            'bank_transaction_number': ['bankTransactionNumber'],
            'bank_transaction_date': ['bankTransactionDate'],
            'commit_id': ['commitId', 'transactionCommitNumber']
        }
        
        for field in ['payment_date', 'payment_particular', 'payment_reference_details', 
                      'payment_status', 'bank_transaction_number', 'bank_transaction_date', 'commit_id']:
            val = None
            if field in frappe.form_dict:
                val = frappe.form_dict[field]
            elif field in field_map:
                for alt_key in field_map[field]:
                    if alt_key in frappe.form_dict:
                        val = frappe.form_dict[alt_key]
                        break
            
            if val is not None:
                doc.set(field, val)
        
        # Default status if not set
        if not doc.payment_status:
            doc.payment_status = "PENDING"
            
        # Default dates if not set
        if not doc.payment_date:
            doc.payment_date = today()

        # Validate required fields for naming and integrity
        if is_new:
            if not doc.project_ref_number:
                return {"status": "error", "message": "Project Reference Number is required to create a Payment"}
            if not doc.budget_head:
                return {"status": "error", "message": "Budget Head is required to create a Payment"}
            
        # Save document to generate name/ID
        doc.flags.ignore_permissions = True
        print(f"[PAYMENT_DEBUG] Before save. is_new={is_new} doc.name={doc.name}")
        if is_new:
            doc.insert()
        else:
            doc.save()
            
        print(f"[PAYMENT_DEBUG] After save. doc.name={doc.name}")

        # Using the saved document for Kafka publishing
        # We pass explicit args as None to let the mapper use the doc's values we just saved
        print(f"[PAYMENT_DEBUG] Calling kafka_publish_payment for {doc.name}")
        success = kafka_publish_payment(
            doc=doc,
            project_name=None, 
            payment_amount=None,
            budget_head=None,
            bmr=None,
            ref_details=refDetails,
            frap_app_id=frapAppId,
            module_name=moduleName
        )
        print(f"[PAYMENT_DEBUG] kafka_publish_payment returned: {success}")

        if success:
            return {
                "status": "success", 
                "message": "Payment published to Kafka", 
                "name": doc.name,
                "data": doc.as_dict()
            }
        else:
            return {"status": "error", "message": "Failed to publish payment"}

    except Exception as e:
        print(f"[PAYMENT_DEBUG] Exception in submit_payment_data: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Submit Payment Data Error")
        return {"status": "error", "message": str(e)}
