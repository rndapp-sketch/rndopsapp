import frappe
import requests
import json
import threading
from frappe.utils import today, flt
from datetime import datetime
from rndopsapp.rndopsapp.transaction_dto import AccountHeadCommitDTO, AccountHeadPaymentDTO
from rndopsapp.rndopsapp.kafka_sync import publish_message, KAFKA_AVAILABLE

# New Kafka producer imports - sumit
from rndopsapp.rndopsapp.kafka.producer.reimbursement import (
    publish_commit as kafka_publish_commit,
    publish_payment as kafka_publish_payment
)

_MM_URL = "http://172.16.135.118:8065/api/v4/posts"
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_KAFKA_CHANNEL = "yh7piky97iycjrdytia1hqy99a"  # "kafka logs" channel


def _mm_notify(message: str):
    """Fire-and-forget Mattermost notification. Never blocks or raises."""
    def _post():
        try:
            requests.post(
                _MM_URL,
                json={"channel_id": _MM_KAFKA_CHANNEL, "message": message},
                headers={"Authorization": _MM_TOKEN, "Content-Type": "application/json"},
                timeout=(2, 3),
            )
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()

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
def submit_commit_data(doctype, frapAppId, name, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None, commitParticular=None):
    """
    Submit commit data by staging it in Kafka Commit Staging.
    It will be published to Kafka later upon workflow reaching 'Approved' (Dean Approval).
    Works for Reimbursement, Travel, Temporary Advance, Advance Settlement, etc.
    """
    print(f"[COMMIT_STAGING] submit_commit_data called: doctype={doctype} name={name} frapAppId={frapAppId} project_name={project_name} commit_amount={commit_amount} budget_head={budget_head} bmr={bmr} bill_amount={bill_amount} refDetails={refDetails} commitParticular={commitParticular}")
    try:
        # Basic validation
        if not frappe.db.exists(doctype, name):
            print(f"[COMMIT_STAGING] ERROR: Document {doctype} {name} not found")
            return {"status": "error", "message": f"Document {doctype} {name} not found"}

        # Create Payload
        payload = {
            "commit_amount": flt(commit_amount),
            "budget_head": budget_head,
            "project_name": project_name,
            "bmr": bmr,
            "bill_amount": flt(bill_amount) if bill_amount else None,
            "frap_app_id": frapAppId,
            "ref_details": refDetails,
            "commit_particular": commitParticular
        }
        print(f"[COMMIT_STAGING] Payload built: {payload}")

        # Check if a staging doc already exists for this reference
        existing_staging = frappe.get_all("Kafka Commit Staging", filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "status": "PENDING_APPROVAL"
        }, limit=1)
        print(f"[COMMIT_STAGING] Existing staging docs: {existing_staging}")

        if existing_staging:
            staging_doc = frappe.get_doc("Kafka Commit Staging", existing_staging[0].name)
            staging_doc.payload = json.dumps(payload)
            staging_doc.save(ignore_permissions=True)
            print(f"[COMMIT_STAGING] Updated existing staging doc: {existing_staging[0].name}")
        else:
            staging_doc = frappe.get_doc({
                "doctype": "Kafka Commit Staging",
                "reference_doctype": doctype,
                "reference_name": name,
                "payload": json.dumps(payload),
                "status": "PENDING_APPROVAL"
            })
            staging_doc.insert(ignore_permissions=True)
            print(f"[COMMIT_STAGING] Inserted new staging doc: {staging_doc.name}")

        return {"status": "success", "message": "Commit payload staged for Kafka publishing upon approval"}

    except Exception as e:
        print(f"[COMMIT_STAGING] EXCEPTION: {str(e)}")
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
        "TA DA Settlement",
        "Recruitment Adhoc Contractual",
        "Indent General Form"
    ]

    if doc.doctype not in applicable_doctypes:
        return

    current_state = doc.get("workflow_state")
    print(f"[CHECK_WORKFLOW] doctype={doc.doctype} name={doc.name} current_state={current_state}")

    if current_state != "Approved":
        print(f"[CHECK_WORKFLOW] Skipping — state is '{current_state}', not Approved")
        return

    # Idempotency: only publish when transitioning INTO Approved
    doc_before = doc.get_doc_before_save()
    prev_state = doc_before.get("workflow_state") if doc_before else None
    print(f"[CHECK_WORKFLOW] prev_state={prev_state}")
    if doc_before and prev_state == "Approved":
        print(f"[CHECK_WORKFLOW] Skipping — was already Approved before save (idempotency guard)")
        return

    # Look for pending staging docs
    staging_docs = frappe.get_all("Kafka Commit Staging", filters={
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "status": ["in", ["PENDING_APPROVAL", "FAILED"]]
    })
    print(f"[CHECK_WORKFLOW] Found {len(staging_docs)} staging doc(s) for {doc.doctype}/{doc.name}")

    if not staging_docs:
        print(f"[CHECK_WORKFLOW] No staging docs found — nothing to publish")
        return

    for st in staging_docs:
        staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
        print(f"[CHECK_WORKFLOW] Processing staging doc: {staging_doc.name} payload={staging_doc.payload}")
        try:
            payload = json.loads(staging_doc.payload)
            print(f"[CHECK_WORKFLOW] Parsed payload: {payload}")

            # For Indent General Form, resolve project_no from the linked Project Registration
            if doc.doctype == "Indent General Form":
                igf_project_title = doc.get("igf_project_title")
                if igf_project_title:
                    project_no = frappe.db.get_value("Project Registration", igf_project_title, "project_no")
                    if project_no:
                        print(f"[CHECK_WORKFLOW] IGF: resolved project_no={project_no} from igf_project_title={igf_project_title}")
                        payload["project_name"] = project_no

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
            print(f"[CHECK_WORKFLOW] kafka_publish_commit returned: {success}")

            if success:
                staging_doc.db_set("status", "PUBLISHED")
                print(f"[CHECK_WORKFLOW] Staging doc {staging_doc.name} marked PUBLISHED")
                _mm_notify(
                    f":white_check_mark: **Kafka Commit Published**\n"
                    f"**DocType:** {doc.doctype}\n"
                    f"**Doc:** {doc.name}\n"
                    f"**Project:** {payload.get('project_name', '-')}\n"
                    f"**Amount:** {payload.get('commit_amount', '-')}\n"
                    f"**Budget Head:** {payload.get('budget_head', '-')}\n"
                    f"**Staging:** {staging_doc.name}"
                )
            else:
                staging_doc.db_set("status", "FAILED")
                staging_doc.db_set("error_message", "kafka_publish_commit returned False")
                print(f"[CHECK_WORKFLOW] Staging doc {staging_doc.name} marked FAILED (returned False)")
                _mm_notify(
                    f":x: **Kafka Commit FAILED**\n"
                    f"**DocType:** {doc.doctype}\n"
                    f"**Doc:** {doc.name}\n"
                    f"**Project:** {payload.get('project_name', '-')}\n"
                    f"**Staging:** {staging_doc.name}"
                )

        except Exception as e:
            print(f"[CHECK_WORKFLOW] EXCEPTION on staging doc {staging_doc.name}: {str(e)}")
            frappe.log_error(frappe.get_traceback(), "Process Staged Commit Error")
            staging_doc.db_set("status", "FAILED")
            staging_doc.db_set("error_message", str(e))


@frappe.whitelist()
def manually_publish_staged_commit(reference_name, reference_doctype="Recruitment Adhoc Contractual"):
    """
    Manually publish a PENDING_APPROVAL or FAILED Kafka Commit Staging doc to Kafka.
    Use when the document is already Approved but the hook did not fire.
    """
    try:
        doc = frappe.get_doc(reference_doctype, reference_name)
        print(f"[MANUAL_PUBLISH] doctype={reference_doctype} name={reference_name} workflow_state={doc.get('workflow_state')}")

        staging_docs = frappe.get_all("Kafka Commit Staging", filters={
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "status": ["in", ["PENDING_APPROVAL", "FAILED"]]
        })
        print(f"[MANUAL_PUBLISH] Found {len(staging_docs)} staging doc(s)")

        if not staging_docs:
            return {"status": "info", "message": "No pending staging docs found — already published or none exist."}

        results = []
        for st in staging_docs:
            staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
            payload = json.loads(staging_doc.payload)
            print(f"[MANUAL_PUBLISH] Publishing staging doc {staging_doc.name} payload={payload}")

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
            print(f"[MANUAL_PUBLISH] kafka_publish_commit returned: {success}")

            if success:
                staging_doc.db_set("status", "PUBLISHED")
                results.append({"staging": staging_doc.name, "result": "PUBLISHED"})
                _mm_notify(
                    f":white_check_mark: **Kafka Commit Published (Manual)**\n"
                    f"**DocType:** {reference_doctype}\n"
                    f"**Doc:** {reference_name}\n"
                    f"**Project:** {payload.get('project_name', '-')}\n"
                    f"**Amount:** {payload.get('commit_amount', '-')}\n"
                    f"**Staging:** {staging_doc.name}"
                )
            else:
                staging_doc.db_set("status", "FAILED")
                staging_doc.db_set("error_message", "kafka_publish_commit returned False")
                results.append({"staging": staging_doc.name, "result": "FAILED"})
                _mm_notify(
                    f":x: **Kafka Commit FAILED (Manual)**\n"
                    f"**DocType:** {reference_doctype}\n"
                    f"**Doc:** {reference_name}\n"
                    f"**Staging:** {staging_doc.name}"
                )

        frappe.db.commit()
        return {"status": "success", "results": results}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Manual Publish Staged Commit Error")
        print(f"[MANUAL_PUBLISH] EXCEPTION: {str(e)}")
        return {"status": "error", "message": str(e)}


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
            _mm_notify(
                f":white_check_mark: **Kafka Payment Published**\n"
                f"**DocType:** {doctype}\n"
                f"**Doc:** {doc.name}\n"
                f"**Project:** {doc.project_ref_number or '-'}\n"
                f"**Amount:** {doc.payment_amount or '-'}\n"
                f"**Budget Head:** {doc.budget_head or '-'}"
            )
            return {
                "status": "success",
                "message": "Payment published to Kafka",
                "name": doc.name,
                "data": doc.as_dict()
            }
        else:
            _mm_notify(
                f":x: **Kafka Payment FAILED**\n"
                f"**DocType:** {doctype}\n"
                f"**Doc:** {doc.name}\n"
                f"**Project:** {doc.project_ref_number or '-'}"
            )
            return {"status": "error", "message": "Failed to publish payment"}

    except Exception as e:
        print(f"[PAYMENT_DEBUG] Exception in submit_payment_data: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Submit Payment Data Error")
        return {"status": "error", "message": str(e)}

# START MKY 2026-04-23 12:45:00 IST - Added endpoints to fetch workflow states securely
@frappe.whitelist()
def get_workflow_states(doctype):
    try:
        workflows = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, pluck="name")
        if not workflows:
            return {"status": "error", "message": "No active workflow found"}
        
        states = frappe.get_all("Workflow Document State", filters={"parent": workflows[0]}, pluck="state")
        return {"status": "success", "data": list(set(states))}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_document_state(doctype, docname):
    try:
        if not frappe.db.exists(doctype, docname):
            return {"status": "error", "message": "Document not found"}
        state = frappe.db.get_value(doctype, docname, "workflow_state")
        return {"status": "success", "state": state or "Draft / Not Set"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
# END MKY
