import frappe
import requests
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from frappe.utils import today, flt, getdate
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
SALARY_COMMIT_STATUSES = ["COMMITTED", "PARTIALLY_PAID", "OVERPAYMENT"]


def _get_project_title_by_number(project_number):
    if not project_number:
        return None

    project_meta = frappe.get_meta("Project Registration")
    project_number_field = "project_number" if project_meta.has_field("project_number") else "project_no"

    return frappe.db.get_value(
        "Project Registration",
        {project_number_field: project_number},
        "project_title"
    )


def _fetch_account_head_commits_by_status(status):
    response = requests.get(
        f"{ACCOUNT_HEAD_COMMIT_API_URL}/by-status/{status}",
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("data", "message", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def _json_contains_ps_emp_id(value, ps_emp_id):
    if isinstance(value, dict):
        if str(value.get("ps_emp_id")) == str(ps_emp_id):
            return True
        return any(_json_contains_ps_emp_id(item, ps_emp_id) for item in value.values())

    if isinstance(value, list):
        return any(_json_contains_ps_emp_id(item, ps_emp_id) for item in value)

    return False


def _salary_staging_has_ps_emp_id(ps_emp_id):
    staged_records = frappe.get_all(
        "Salary Staging",
        fields=["name", "salary_record"],
        limit_page_length=0,
    )

    for staged_record in staged_records:
        salary_record = staged_record.get("salary_record")
        if not salary_record:
            continue

        for line in str(salary_record).splitlines():
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)
            except Exception:
                continue

            if _json_contains_ps_emp_id(payload, ps_emp_id):
                return True

    return False


@frappe.whitelist(allow_guest=True)
def salary_payment_data(ps_emp_id):
    """
    Return active salary tenure data for a Project Staff employee.
    """
    if not ps_emp_id:
        return {"status": "error", "message": "Employee ID is required"}

    try:
        if _salary_staging_has_ps_emp_id(ps_emp_id):
            return {"status": "Pending Approval in Account Portal", "message": "Salary already initiated"}

        staff_records = frappe.get_all(
            "Project Staff Details",
            filters={"ps_emp_id": ps_emp_id},
            fields=["name", "scr_id", "project_no"],
        )

        if not staff_records:
            return {
                "status": "error",
                "message": "No Project Staff Details found for the given Employee ID",
            }

        current_date = getdate(today())
        valid_records = []

        for staff_record in staff_records:
            staff_doc = frappe.get_doc("Project Staff Details", staff_record.name)
            valid_tenures = []

            for tenure in staff_doc.get("table_ymed") or []:
                term_completion_date = tenure.get("pstd_term_completion_date")
                if not term_completion_date:
                    continue

                term_completion_date = getdate(term_completion_date)
                if current_date > term_completion_date:
                    continue

                joining_date = tenure.get("pstd_joining_date")
                basic_salary = flt(tenure.get("pstd_basic_salary"))
                valid_tenures.append({
                    "joining_date": joining_date,
                    "term_completion_date": term_completion_date,
                    "basic_salary": basic_salary,
                })

            if not valid_tenures:
                continue

            latest_tenure = max(
                valid_tenures,
                key=lambda row: (
                    getdate(row.get("joining_date")) if row.get("joining_date") else getdate("1900-01-01"),
                    getdate(row.get("term_completion_date")),
                ),
            )

            valid_records.append({
                "staff_doc": staff_doc,
                "valid_tenures": valid_tenures,
                "latest_tenure": latest_tenure,
            })

        if not valid_records:
            return {
                "status": "error",
                "message": "No active tenure found for the given Employee ID",
            }

        latest_record = max(
            valid_records,
            key=lambda row: (
                getdate(row["latest_tenure"].get("joining_date"))
                if row["latest_tenure"].get("joining_date")
                else getdate("1900-01-01"),
                getdate(row["latest_tenure"].get("term_completion_date")),
            ),
        )

        staff_doc = latest_record["staff_doc"]
        scr_id = staff_doc.get("scr_id")
        project_no = staff_doc.get("project_no")
        interview_id = None

        if scr_id and frappe.db.exists("Selection Committee Report", scr_id):
            interview_id = frappe.db.get_value("Selection Committee Report", scr_id, "interview_id")

        recruitment_doc_name = interview_id
        if not recruitment_doc_name or not frappe.db.exists("Recruitment Adhoc Contractual", recruitment_doc_name):
            return []

        merged_commit_records = []
        with ThreadPoolExecutor(max_workers=len(SALARY_COMMIT_STATUSES)) as executor:
            future_to_status = {
                executor.submit(_fetch_account_head_commits_by_status, status): status
                for status in SALARY_COMMIT_STATUSES
            }

            for future in as_completed(future_to_status):
                status = future_to_status[future]
                try:
                    merged_commit_records.extend(future.result())
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        f"Salary Account Head Commit API Error: {status}"
                    )

        filtered_records = []
        project_title_by_number = {}

        for record in merged_commit_records:
            if not isinstance(record, dict):
                continue

            project_number = record.get("projectNumber")
            if (
                str(record.get("moduleId")) != "11"
                or str(record.get("frapAppId")) != str(recruitment_doc_name)
                or str(project_number) != str(project_no)
            ):
                continue

            if project_number not in project_title_by_number:
                project_title_by_number[project_number] = _get_project_title_by_number(project_number)

            filtered_record = {"projectNumber": project_number}
            filtered_record["projectTitle"] = project_title_by_number.get(project_number)
            filtered_record.update({
                key: value
                for key, value in record.items()
                if key != "projectNumber"
            })
            filtered_records.append(filtered_record)

        return filtered_records

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Salary Payment Data Error")
        return {"status": "error", "message": str(e)}


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
        "Indent General Form",
        "Top Up Fellowship",
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


def _get_form_value(*keys):
    for key in keys:
        value = frappe.form_dict.get(key)
        if value not in (None, "", "None", "null", "undefined"):
            return value
    return None


def _is_recruitment_salary_payment(doctype=None, frapAppId=None, moduleName=None, moduleId=None):
    doctype = doctype or _get_form_value("doctype", "reference_doctype")
    moduleName = moduleName or _get_form_value("moduleName", "module_name")
    moduleId = moduleId or _get_form_value("moduleId", "module_id")
    frapAppId = frapAppId or _get_form_value("frapAppId", "frap_app_id")

    return (
        doctype == "Recruitment Adhoc Contractual"
        or moduleName == "Recruitment Adhoc Contractual"
        or str(moduleName) == "11"
        or str(moduleId) == "11"
        or (frapAppId and frappe.db.exists("Recruitment Adhoc Contractual", frapAppId))
    )


def _append_salary_staging_record(salary_year_month, payload):
    # START MKY 2026-05-29 12:32:00 IST - Fixed salary_record to store as JSON array (was JSON Lines which fails MariaDB CHECK json_valid() constraint)
    if not salary_year_month:
        return {"status": "error", "message": "salary_year_month is required"}

    try:
        created = False
        print(f"[SALARY_STAGING] Attempting to stage salary_year_month={salary_year_month}")
        print(f"[SALARY_STAGING] Payload keys: {list(payload.keys())}")

        if frappe.db.exists("Salary Staging", salary_year_month):
            print(f"[SALARY_STAGING] Existing staging doc found — updating")
            staging_doc = frappe.get_doc("Salary Staging", salary_year_month)

            # Parse existing salary_record as JSON array
            existing_raw = staging_doc.get("salary_record") or "[]"
            try:
                existing_records = json.loads(existing_raw)
                if not isinstance(existing_records, list):
                    existing_records = [existing_records]
            except Exception:
                existing_records = []

            # Append new payload and serialize back as a valid JSON array
            existing_records.append(payload)
            staging_doc.salary_record = json.dumps(existing_records, default=str)
            staging_doc.save(ignore_permissions=True)
            print(f"[SALARY_STAGING] Updated staging doc: {staging_doc.name} (total records: {len(existing_records)})")
        else:
            print(f"[SALARY_STAGING] No existing doc — creating new staging doc")
            # Store as a JSON array with one element so json_valid() constraint passes
            salary_record_json = json.dumps([payload], default=str)
            staging_doc = frappe.get_doc({
                "doctype": "Salary Staging",
                "name": salary_year_month,
                "salary_record": salary_record_json,
            })
            if frappe.get_meta("Salary Staging").has_field("salary_year_month"):
                staging_doc.salary_year_month = salary_year_month
            staging_doc.name = salary_year_month
            staging_doc.flags.name_set = True  # bypass DocType autoname (format:{YYYY}_{MMMM})
            staging_doc.insert(ignore_permissions=True)
            created = True
            print(f"[SALARY_STAGING] Inserted new staging doc: {staging_doc.name}")

        frappe.db.commit()
        print(f"[SALARY_STAGING] db.commit() done. created={created}")

        return {
            "status": "success",
            "message": "Salary record appended",
            "name": staging_doc.name,
            "created": created,
        }

    except Exception as e:
        print(f"[SALARY_STAGING] EXCEPTION: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Append Salary Staging Record Error")
        return {"status": "error", "message": str(e)}
    # END MKY


@frappe.whitelist()
def submit_payment_data(doctype=None, name=None, project_name=None, payment_amount=None, budget_head=None, bmr=None, refDetails=None, frapAppId=None, moduleName=None, salary_year_month=None):
    """
    Submit payment data using new Kafka producer.
    Works for doctype.
    """
    try:
        if _is_recruitment_salary_payment(doctype=doctype, frapAppId=frapAppId, moduleName=moduleName):
            salary_year_month = salary_year_month or _get_form_value(
                "salary_year_month",
                "salaryYearMonth",
                "year_month",
                "yearMonth"
            )
            salary_payload = dict(frappe.form_dict)
            # START OJS 2026-05-29 12:17:00 IST - Added project_no and account_number to salary staging payload
            _salary_backend = frappe.form_dict.get("salary_backend_details") or {}
            if isinstance(_salary_backend, str):
                try:
                    import json as _json
                    _salary_backend = _json.loads(_salary_backend)
                except Exception:
                    _salary_backend = {}

            salary_payload.update({
                "doctype": doctype,
                "name": name,
                "project_name": project_name,
                "payment_amount": payment_amount,
                "budget_head": budget_head,
                "bmr": bmr,
                "refDetails": refDetails,
                "frapAppId": frapAppId,
                "moduleName": moduleName,
                "salary_year_month": salary_year_month,
                "status": "PENDING_APPROVAL",
                "project_no": _get_form_value("project_no") or _salary_backend.get("project_no"),
                "account_number": _get_form_value("account_number"),
            })
            # END OJS
            salary_payload.pop("cmd", None)
            staging_result = _append_salary_staging_record(salary_year_month, salary_payload)
            print(f"[PAYMENT_DEBUG] Salary staging result: {staging_result}")
            if staging_result.get("status") == "error":
                return staging_result
            # START OJS 2026-05-29 12:20:00 IST - Return after successful salary staging; do not fall through to AccountHeadPayment creation
            # return staging_result
            # END OJS

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

# START OJS 2026-04-23 12:45:00 IST - Added endpoints to fetch workflow states securely
@frappe.whitelist()
def get_workflow_states(doctype):
    try:
        # Prefer active workflow; fall back to any workflow for the doctype
        workflows = frappe.get_all("Workflow", filters={"document_type": doctype, "is_active": 1}, pluck="name")
        if not workflows:
            workflows = frappe.get_all("Workflow", filters={"document_type": doctype}, pluck="name")
        if not workflows:
            return {"status": "error", "message": "No workflow found"}

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

@frappe.whitelist()
def set_workflow_state(doctype, docname, state, comment=None):
    try:
        if not frappe.db.exists(doctype, docname):
            return {"status": "error", "message": "Document not found"}

        prev_state = frappe.db.get_value(doctype, docname, "workflow_state") or "Unknown"
        user = frappe.session.user
        comment = (comment or "").strip()

        frappe.db.set_value(doctype, docname, "workflow_state", state, update_modified=False)

        # Activity log comment
        reason_text = f" | Reason: {comment}" if comment else ""
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Workflow",
            "reference_doctype": doctype,
            "reference_name": docname,
            "content": (
                f"[Manual Override] Workflow state changed by {user} "
                f"via Kafka Control: {prev_state} → {state}{reason_text}"
            ),
        }).insert(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "message": f"{docname} → {state}",
            "from_state": prev_state,
            "to_state": state,
            "changed_by": user,
            "comment": comment or None,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "set_workflow_state failed")
        return {"status": "error", "message": str(e)}
# END OJS
