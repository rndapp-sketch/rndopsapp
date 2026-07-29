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
_MM_SALARY_CHANNEL = "knetjx859tfu8g3tecr1tu8mne"  # "Salary Module" channel


def _mm_notify(message: str, channel_id: str = _MM_KAFKA_CHANNEL):
    """Fire-and-forget Mattermost notification. Never blocks or raises."""
    def _post():
        try:
            requests.post(
                _MM_URL,
                json={"channel_id": channel_id, "message": message},
                headers={"Authorization": _MM_TOKEN, "Content-Type": "application/json"},
                timeout=(2, 3),
            )
        except Exception:
            pass
    threading.Thread(target=_post, daemon=True).start()


def _mm_notify_salary_json(title: str, data: dict):
    """Post the full salary payload/result as a JSON code block to the Salary Module channel."""
    body = json.dumps(data, default=str, indent=2)
    _mm_notify(f"**{title}**\n```json\n{body}\n```", channel_id=_MM_SALARY_CHANNEL)

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


def _salary_staging_has_ps_emp_id(ps_emp_id, yyyy_month=None):
    filters = {}
    if yyyy_month:
        filters["name"] = yyyy_month

    staged_records = frappe.get_all(
        "Salary Staging",
        filters=filters,
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
def salary_payment_data(ps_emp_id, yyyy_month=None):
    """
    Return active salary tenure data for a Project Staff employee.
    """
    raw_form_dict = dict(frappe.form_dict)
    print(f"[SALARY_PAYMENT_DATA] Raw data received: {raw_form_dict}")
    _mm_notify_salary_json("Salary Payment Data - Raw Request Received", raw_form_dict)

    if not ps_emp_id:
        print("[SALARY_PAYMENT_DATA] ERROR: Employee ID is required")
        _mm_notify(":x: **Salary Payment Data Error**\n**Error:** Employee ID is required", channel_id=_MM_SALARY_CHANNEL)
        return [{"status": "error", "message": "Employee ID is required"}]

    try:
        if yyyy_month and _salary_staging_has_ps_emp_id(ps_emp_id, yyyy_month):
            print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] Already staged for {yyyy_month} — Pending Approval in Account Portal")
            _mm_notify(
                f":information_source: **Salary Already Initiated**\n"
                f"**Employee:** {ps_emp_id}\n"
                f"**Month:** {yyyy_month}",
                channel_id=_MM_SALARY_CHANNEL,
            )
            return [{"status": "Pending Approval in Account Portal", "message": "Salary already initiated"}]

        staff_records = frappe.get_all(
            "Project Staff Details",
            filters={"ps_emp_id": ps_emp_id},
            fields=["name", "scr_id", "project_no"],
        )
        print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] Project Staff Details found: {staff_records}")

        if not staff_records:
            print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] ERROR: No Project Staff Details found")
            _mm_notify(
                f":x: **Salary Payment Data Error**\n"
                f"**Employee:** {ps_emp_id}\n"
                f"**Error:** No Project Staff Details found for the given Employee ID",
                channel_id=_MM_SALARY_CHANNEL,
            )
            return [{
                "status": "error",
                "message": "No Project Staff Details found for the given Employee ID",
            }]

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

            # Fallback: some Project Staff Details records keep the current tenure on the
            # parent doc itself (ps_joining_date / ps_term_completion_date / ps_basic_salary)
            # instead of a table_ymed row — treat that as the tenure when table_ymed is empty.
            if not valid_tenures:
                top_level_completion = staff_doc.get("ps_term_completion_date")
                if top_level_completion:
                    top_level_completion = getdate(top_level_completion)
                    if current_date <= top_level_completion:
                        valid_tenures.append({
                            "joining_date": staff_doc.get("ps_joining_date"),
                            "term_completion_date": top_level_completion,
                            "basic_salary": flt(staff_doc.get("ps_basic_salary")),
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
            print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] ERROR: No active tenure found")
            _mm_notify(
                f":x: **Salary Payment Data Error**\n"
                f"**Employee:** {ps_emp_id}\n"
                f"**Error:** No active tenure found for the given Employee ID",
                channel_id=_MM_SALARY_CHANNEL,
            )
            return [{
                "status": "error",
                "message": "No active tenure found for the given Employee ID",
            }]

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
        print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] scr_id={scr_id} project_no={project_no} recruitment_doc_name={recruitment_doc_name}")

        if not recruitment_doc_name or not frappe.db.exists("Recruitment Adhoc Contractual", recruitment_doc_name):
            print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] No matching Recruitment Adhoc Contractual — returning empty list")
            _mm_notify(
                f":warning: **Salary Payment Data**\n"
                f"**Employee:** {ps_emp_id}\n"
                f"**Info:** No matching Recruitment Adhoc Contractual found (interview_id={interview_id}) — returning empty list",
                channel_id=_MM_SALARY_CHANNEL,
            )
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
                    print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] ERROR fetching Account Head Commits for status={status}")
                    frappe.log_error(
                        frappe.get_traceback(),
                        f"Salary Account Head Commit API Error: {status}"
                    )
                    _mm_notify(
                        f":x: **Salary Payment Data - API Error**\n"
                        f"**Employee:** {ps_emp_id}\n"
                        f"**Status:** {status}\n"
                        f"**Error:** Failed to fetch Account Head Commits",
                        channel_id=_MM_SALARY_CHANNEL,
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

        print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] Returning {len(filtered_records)} filtered record(s)")
        _mm_notify_salary_json(
            f"Salary Payment Data - Response ({ps_emp_id})",
            {"ps_emp_id": ps_emp_id, "yyyy_month": yyyy_month, "count": len(filtered_records), "data": filtered_records},
        )
        return filtered_records

    except Exception as e:
        print(f"[SALARY_PAYMENT_DATA] [{ps_emp_id}] EXCEPTION: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Salary Payment Data Error")
        _mm_notify(
            f":rotating_light: **Salary Payment Data Exception**\n"
            f"**Employee:** {ps_emp_id}\n"
            f"**Month:** {yyyy_month or '-'}\n"
            f"**Error:** {str(e)}",
            channel_id=_MM_SALARY_CHANNEL,
        )
        return [{"status": "error", "message": str(e)}]


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
                    "actualBalance": flt(data.get("availablePaymentAmount", 0)),
                    "committable": flt(data.get("availableCommitAmount", 0))
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


@frappe.whitelist(allow_guest=True)
def get_project_available_amounts_test(project_number):
    """
    TESTING ONLY - guest-accessible clone of get_project_available_amounts.
    Remove before going to production.
    """
    return get_project_available_amounts(project_number)

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
def get_commit_staging_status(reference_name, statuses=None, required_payload_keys=None):
    """
    Read-only lookup used by the "Make a Commitment" widget (CommitPayment.tsx)
    to check whether a commitment has already been staged for `reference_name`.

    "Kafka Commit Staging" is intentionally locked down to System Manager-only
    read permission, so the widget can't query it directly via the REST document
    API (every non-admin role — including staff, RnD who are the ones actually
    submitting — got a 403, silently falling back to "could not verify staging
    status" and showing the submit form even to approvers like Hos, RnD who
    should only ever see what staff, RnD already committed). This whitelisted
    method bypasses that DocType-level restriction for this one safe, read-only
    lookup, filtered to the specific reference_name the caller already has
    document-level access to.
    """
    if not reference_name:
        return {"status": "error", "message": "reference_name is required"}

    filters = {"reference_name": reference_name}
    status_list = frappe.parse_json(statuses) if isinstance(statuses, str) else statuses
    if status_list:
        filters["status"] = ["in", status_list]

    records = frappe.get_all(
        "Kafka Commit Staging",
        filters=filters,
        fields=["name", "payload", "status", "reference_doctype", "reference_name", "creation"],
        order_by="creation desc",
        ignore_permissions=True,
    )

    payload_keys = (
        frappe.parse_json(required_payload_keys)
        if isinstance(required_payload_keys, str)
        else required_payload_keys
    )
    if payload_keys:
        filtered = []
        for row in records:
            try:
                payload = json.loads(row.payload or "{}")
            except Exception:
                continue
            if all(payload.get(k) not in (None, "") for k in payload_keys):
                filtered.append(row)
        records = filtered

    return {"status": "success", "data": records}


@frappe.whitelist()
def submit_commit_data(doctype, frapAppId, name, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None, commitParticular=None, moduleId=None, trigger_state=None):
    """
    Submit commit data by staging it in Kafka Commit Staging.
    Published to Kafka when workflow reaches trigger_state (default: 'Approved').

    moduleId: optional int override sent to Kafka (e.g. 14 for ICSS PO re-commit)
    trigger_state: workflow state that fires publishing (e.g. 'Pending PO Generation' for ICSS)
    """
    resolved_trigger_state = trigger_state or "Approved"
    print(f"[COMMIT_STAGING] submit_commit_data called: doctype={doctype} name={name} frapAppId={frapAppId} project_name={project_name} commit_amount={commit_amount} budget_head={budget_head} bmr={bmr} bill_amount={bill_amount} refDetails={refDetails} commitParticular={commitParticular} moduleId={moduleId} trigger_state={resolved_trigger_state}")
    try:
        # Basic validation
        # `name` may be a staging-only reference key (e.g. "2026062222001260-po") that does
        # not correspond to a real Frappe document.  Use frapAppId for the existence check
        # when it is provided, falling back to name for callers that don't supply frapAppId.
        doc_name_for_lookup = frapAppId if frapAppId else name
        if not frappe.db.exists(doctype, doc_name_for_lookup):
            print(f"[COMMIT_STAGING] ERROR: Document {doctype} {doc_name_for_lookup} not found")
            return {"status": "error", "message": f"Document {doctype} {doc_name_for_lookup} not found"}

        # Build payload — trigger_state and moduleId stored here so check_workflow_and_publish
        # can read them without requiring a separate doctype field.
        payload = {
            "commit_amount": flt(commit_amount),
            "budget_head": budget_head,
            "project_name": project_name,
            "bmr": bmr,
            "bill_amount": flt(bill_amount) if bill_amount else None,
            "frap_app_id": frapAppId,
            "ref_details": refDetails,
            "commit_particular": commitParticular,
            "trigger_state": resolved_trigger_state
        }
        if moduleId is not None:
            payload["moduleId"] = int(moduleId)
        print(f"[COMMIT_STAGING] Payload built: {payload}")

        # Match existing staging row for the same reference + trigger_state so that
        # a PO re-commit (different trigger_state) does not overwrite the initial commit.
        existing_staging = frappe.get_all("Kafka Commit Staging", filters={
            "reference_doctype": doctype,
            "reference_name": name,
            "status": "PENDING_APPROVAL"
        }, fields=["name", "payload"], limit=10)
        print(f"[COMMIT_STAGING] Existing staging docs: {existing_staging}")

        matched = None
        for row in existing_staging:
            try:
                row_payload = json.loads(row.payload or "{}")
                if row_payload.get("trigger_state", "Approved") == resolved_trigger_state:
                    matched = row
                    break
            except Exception:
                pass

        if matched:
            staging_doc = frappe.get_doc("Kafka Commit Staging", matched.name)
            staging_doc.payload = json.dumps(payload)
            staging_doc.save(ignore_permissions=True)
            print(f"[COMMIT_STAGING] Updated existing staging doc: {matched.name}")
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
    Centralized workflow hook to publish staged commit data when the document reaches
    the trigger_state stored inside each Kafka Commit Staging payload.

    Previously gated by a hardcoded applicable_doctypes list.  Now fully dynamic:
    any doctype that stages a row via submit_commit_data will be published here once
    its workflow_state matches the trigger_state in that staging row's payload.
    Default trigger_state is "Approved" (backward-compatible with all existing modules).
    ICSS uses trigger_state="Pending PO Generation".
    """
    current_state = doc.get("workflow_state")
    if not current_state:
        return

    print(f"[CHECK_WORKFLOW] doctype={doc.doctype} name={doc.name} current_state={current_state}")

    doc_before = doc.get_doc_before_save()
    prev_state = doc_before.get("workflow_state") if doc_before else None
    print(f"[CHECK_WORKFLOW] prev_state={prev_state}")

    # Look for all pending/failed staging docs for this document
    staging_docs = frappe.get_all("Kafka Commit Staging", filters={
        "reference_doctype": doc.doctype,
        "reference_name": doc.name,
        "status": ["in", ["PENDING_APPROVAL", "FAILED"]]
    })
    print(f"[CHECK_WORKFLOW] Found {len(staging_docs)} staging doc(s) for {doc.doctype}/{doc.name}")

    if not staging_docs:
        return

    for st in staging_docs:
        staging_doc = frappe.get_doc("Kafka Commit Staging", st.name)
        print(f"[CHECK_WORKFLOW] Processing staging doc: {staging_doc.name} payload={staging_doc.payload}")
        try:
            payload = json.loads(staging_doc.payload)
            print(f"[CHECK_WORKFLOW] Parsed payload: {payload}")

            # Each staging row carries its own trigger_state (default "Approved")
            trigger_state = payload.get("trigger_state") or "Approved"

            if current_state != trigger_state:
                print(f"[CHECK_WORKFLOW] Skipping {staging_doc.name} — state '{current_state}' != trigger '{trigger_state}'")
                continue

            # Idempotency: skip if document was already in trigger_state before this save
            if doc_before and prev_state == trigger_state:
                print(f"[CHECK_WORKFLOW] Skipping {staging_doc.name} — was already '{trigger_state}' (idempotency guard)")
                continue

            # For Indent General Form, resolve project_no from the linked Project Registration
            if doc.doctype == "Indent General Form":
                igf_project_title = doc.get("igf_project_title")
                if igf_project_title:
                    project_no = frappe.db.get_value("Project Registration", igf_project_title, "project_no")
                    if project_no:
                        print(f"[CHECK_WORKFLOW] IGF: resolved project_no={project_no} from igf_project_title={igf_project_title}")
                        payload["project_name"] = project_no

            # Pass moduleId override from payload so ICSS PO re-commit uses module 14
            module_id_override = payload.get("moduleId") or payload.get("module_id")

            # Publish to Kafka
            success = kafka_publish_commit(
                doc=doc,
                commit_amount=payload.get("commit_amount"),
                budget_head=payload.get("budget_head"),
                project_name=payload.get("project_name"),
                bmr=payload.get("bmr"),
                bill_amount=payload.get("bill_amount"),
                frap_app_id=payload.get("frap_app_id"),
                ref_details=payload.get("ref_details"),
                module_id=module_id_override,
                commit_particular=payload.get("commit_particular")
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

            module_id_override = payload.get("moduleId") or payload.get("module_id")

            success = kafka_publish_commit(
                doc=doc,
                commit_amount=payload.get("commit_amount"),
                budget_head=payload.get("budget_head"),
                project_name=payload.get("project_name"),
                bmr=payload.get("bmr"),
                bill_amount=payload.get("bill_amount"),
                frap_app_id=payload.get("frap_app_id"),
                ref_details=payload.get("ref_details"),
                module_id=module_id_override,
                commit_particular=payload.get("commit_particular")
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


def _salary_payload_identity(payload):
    """Best-effort human-readable identifier for a staged salary payload, for logs/alerts."""
    backend = payload.get("salary_backend_details") or {}
    if isinstance(backend, str):
        try:
            backend = json.loads(backend)
        except Exception:
            backend = {}
    user_details = payload.get("salary_user_details") or {}
    if isinstance(user_details, str):
        try:
            user_details = json.loads(user_details)
        except Exception:
            user_details = {}

    emp_id = backend.get("ps_emp_id") or user_details.get("employee_id") or payload.get("frapAppId")
    emp_name = user_details.get("first_name")
    if emp_id and emp_name:
        return f"{emp_name} ({emp_id})"
    return str(emp_id or payload.get("commitParticular") or "unknown")


def _append_salary_staging_record(salary_year_month, payload):
    # START MKY 2026-05-29 12:32:00 IST - Fixed salary_record to store as JSON array (was JSON Lines which fails MariaDB CHECK json_valid() constraint)
    if not salary_year_month:
        return {"status": "error", "message": "salary_year_month is required"}

    identity = _salary_payload_identity(payload)

    # Concurrent submissions for the same salary_year_month race on this
    # read-modify-write (each request reads salary_record before any of the
    # others commit their append, so only the last writer's record survives).
    # A named lock serializes appends per year-month across requests/workers.
    lock_name = f"salary_staging_{salary_year_month}"
    print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Acquiring lock {lock_name!r}...")
    got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_name)[0][0]
    if not got_lock:
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] FAILED to acquire lock after 10s")
        _mm_notify(
            f":x: **Salary Staging Lock Timeout**\n"
            f"**Month:** {salary_year_month}\n"
            f"**Employee:** {identity}\n"
            f"**Error:** Could not acquire `{lock_name}` within 10s — record NOT staged"
        )
        return {"status": "error", "message": "Could not acquire salary staging lock, please retry"}
    print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Lock acquired")

    try:
        created = False
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Attempting to stage")
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Payload keys: {list(payload.keys())}")

        if frappe.db.exists("Salary Staging", salary_year_month):
            print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Existing staging doc found — updating")
            staging_doc = frappe.get_doc("Salary Staging", salary_year_month)

            # Parse existing salary_record as JSON array
            existing_raw = staging_doc.get("salary_record") or "[]"
            try:
                existing_records = json.loads(existing_raw)
                if not isinstance(existing_records, list):
                    existing_records = [existing_records]
            except Exception:
                existing_records = []

            before_count = len(existing_records)
            existing_identities = [_salary_payload_identity(r) for r in existing_records]
            print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Records before append: {before_count} -> {existing_identities}")

            # Append new payload and serialize back as a valid JSON array
            existing_records.append(payload)
            staging_doc.salary_record = json.dumps(existing_records, default=str)
            staging_doc.save(ignore_permissions=True)
            print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Updated staging doc: {staging_doc.name} ({before_count} -> {len(existing_records)} records)")
        else:
            print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] No existing doc — creating new staging doc")
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
            before_count = 0
            print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Inserted new staging doc: {staging_doc.name}")

        frappe.db.commit()
        after_count = before_count + 1
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] db.commit() done. created={created}, total_records={after_count}")

        _mm_notify(
            f":white_check_mark: **Salary Staged**\n"
            f"**Month:** {salary_year_month}\n"
            f"**Employee:** {identity}\n"
            f"**Doc:** {staging_doc.name} ({'created' if created else 'updated'})\n"
            f"**Total records now:** {after_count}"
        )

        return {
            "status": "success",
            "message": "Salary record appended",
            "name": staging_doc.name,
            "created": created,
        }

    except Exception as e:
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] EXCEPTION: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "Append Salary Staging Record Error")
        _mm_notify(
            f":rotating_light: **Salary Staging Exception**\n"
            f"**Month:** {salary_year_month}\n"
            f"**Employee:** {identity}\n"
            f"**Error:** {str(e)}"
        )
        return {"status": "error", "message": str(e)}
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_name)
        print(f"[SALARY_STAGING] [{salary_year_month}] [{identity}] Lock released")
    # END MKY


@frappe.whitelist()
def submit_payment_data(doctype=None, name=None, project_name=None, payment_amount=None, budget_head=None, bmr=None, refDetails=None, frapAppId=None, moduleName=None, salary_year_month=None):
    """
    Create or update an AccountHeadPayment document and publish it to Kafka.

    Accepts values from explicit arguments, falling back to frappe.form_dict
    for fields not passed directly. Both snake_case and camelCase form keys
    are supported (e.g. paymentStatus == payment_status).

    Flow:
        1. Salary/recruitment payments (detected via frapAppId + moduleName):
           - Stages the payment via _append_salary_staging_record.
           - Returns immediately with the staging result; does NOT create an
             AccountHeadPayment document.
        2. All other payments:
           - Loads existing doc if `name` is provided and exists, otherwise
             inserts a new AccountHeadPayment.
           - Resolves project_ref_number: accepts the Frappe PK or project_no;
             looks up the PK when a project_no is passed.
           - Resolves budget_head: accepts the Frappe PK, budget_head label, or
             numeric id; looks up the PK when a label/id is passed.
           - Defaults payment_status to "PENDING" and payment_date to today()
             if not supplied.
           - Publishes the saved document to Kafka topic
             `account-head-payment-events`.
           - Notifies Mattermost on every outcome (success, failure, exception).

    Args:
        doctype (str): Frappe DocType name (e.g. "AccountHeadPayment").
        name (str | None): Frappe document name/ID to update. Pass None,
            "None", "null", or "" to create a new document.
        project_name (str): Project reference number or project_no value.
        payment_amount (float | str): Payment amount.
        budget_head (str): Budget Head PK, label, or numeric id.
        bmr (str): BMR number linked to the payment.
        refDetails (str): Free-text payment reference details.
        frapAppId (str): Frap App identifier; used to detect salary payments.
        moduleName (str): Module name; used together with frapAppId to detect
            salary payments.
        salary_year_month (str): Year-month string (e.g. "2026-06") required
            for salary staging. Falls back to form_dict keys
            salary_year_month / salaryYearMonth / year_month / yearMonth.

    Returns:
        dict: Always returns a dict with at least a "status" key.
            Success  → {"status": "success", "message": str,
                        "name": str, "data": dict}
            Failure  → {"status": "error",   "message": str}
    """
    try:
        print(
            f"[PAYMENT_DEBUG] submit_payment_data called. doctype={doctype} name={name} "
            f"project_name={project_name} payment_amount={payment_amount} budget_head={budget_head} "
            f"bmr={bmr} refDetails={refDetails} frapAppId={frapAppId} moduleName={moduleName} "
            f"salary_year_month={salary_year_month}"
        )
        print(f"[PAYMENT_DEBUG] form_dict keys received: {list(frappe.form_dict.keys())}")
        _mm_notify(
            f":inbox_tray: **submit_payment_data Called**\n"
            f"**DocType:** {doctype}\n"
            f"**Name:** {name}\n"
            f"**Project:** {project_name or '-'}\n"
            f"**Amount:** {payment_amount or '-'}\n"
            f"**Budget Head:** {budget_head or '-'}\n"
            f"**frapAppId:** {frapAppId or '-'}\n"
            f"**moduleName:** {moduleName or '-'}\n"
            f"**salary_year_month:** {salary_year_month or '-'}\n"
            f"**form_dict keys:** {list(frappe.form_dict.keys())}"
        )

        if _is_recruitment_salary_payment(doctype=doctype, frapAppId=frapAppId, moduleName=moduleName):
            # --- Step 1: persist to Salary Staging for audit record ---
            salary_year_month = salary_year_month or _get_form_value(
                "salary_year_month", "salaryYearMonth", "year_month", "yearMonth"
            )
            salary_payload = dict(frappe.form_dict)
            _salary_backend = frappe.form_dict.get("salary_backend_details") or {}
            if isinstance(_salary_backend, str):
                try:
                    import json as _json
                    _salary_backend = _json.loads(_salary_backend)
                except Exception:
                    _salary_backend = {}
            salary_payload.update({
                "doctype": doctype, "name": name,
                "project_name": project_name, "payment_amount": payment_amount,
                "budget_head": budget_head, "bmr": bmr, "refDetails": refDetails,
                "frapAppId": frapAppId, "moduleName": moduleName,
                "salary_year_month": salary_year_month,
                "status": "PENDING_PUBLISH",
                "project_no": _get_form_value("project_no") or _salary_backend.get("project_no"),
                "account_number": _get_form_value("account_number"),
            })
            salary_payload.pop("cmd", None)

            _entry_identity = _salary_payload_identity(salary_payload)
            print(f"[SUBMIT_PAYMENT_DATA] [{salary_year_month}] [{_entry_identity}] Salary payment detected. frapAppId={frapAppId} moduleName={moduleName} doctype={doctype}")
            _mm_notify(
                f":inbox_tray: **Salary Payment Received**\n"
                f"**Month:** {salary_year_month or '-'}\n"
                f"**Employee:** {_entry_identity}\n"
                f"**frapAppId:** {frapAppId}\n"
                f"**Amount:** {payment_amount or '-'}"
            )
            _mm_notify_salary_json("Salary Payment - Before Publish", salary_payload)

            if salary_year_month:
                _append_salary_staging_record(salary_year_month, salary_payload)
            else:
                print(f"[SUBMIT_PAYMENT_DATA] [{_entry_identity}] WARNING: salary_year_month could not be resolved — record was NOT staged")
                _mm_notify(
                    f":warning: **Salary Staging Skipped**\n"
                    f"**Employee:** {_entry_identity}\n"
                    f"**frapAppId:** {frapAppId}\n"
                    f"**Error:** salary_year_month missing/unresolved from request — record NOT written to Salary Staging"
                )

            # --- Step 2: create AccountHeadPayment and publish to Kafka immediately ---
            # Prefer numeric moduleId ("11") so the mapper can cast it directly to int
            _sal_module = _get_form_value("moduleId", "module_id") or str(moduleName or "11")

            # Resolve project reference
            _sal_project = project_name or _get_form_value("project_name", "projectNumber", "project_no")
            if _sal_project and not frappe.db.exists("Project Registration", _sal_project):
                _found = frappe.db.get_value("Project Registration", {"project_no": _sal_project}, "name")
                if _found:
                    _sal_project = _found

            # Resolve budget head
            _sal_bh = budget_head or _get_form_value("budget_head", "accountHeadId", "account_head_id")
            if _sal_bh and not frappe.db.exists("Budget Head", _sal_bh):
                _found = (
                    frappe.db.get_value("Budget Head", {"budget_head": _sal_bh}, "name")
                    or frappe.db.get_value("Budget Head", {"id": _sal_bh}, "name")
                )
                if _found:
                    _sal_bh = _found

            print(f"[PAYMENT_DEBUG] [{salary_year_month}] [{_entry_identity}] Resolved _sal_project={_sal_project!r} _sal_bh={_sal_bh!r}")

            if not _sal_project:
                print(f"[PAYMENT_DEBUG] [{salary_year_month}] [{_entry_identity}] ERROR: project_ref_number could not be resolved")
                _mm_notify(f":x: **Salary Payment Error**\n**frapAppId:** {frapAppId}\n**Error:** project_ref_number is required")
                return {"status": "error", "message": "project_ref_number is required for salary payment"}
            if not _sal_bh:
                print(f"[PAYMENT_DEBUG] [{salary_year_month}] [{_entry_identity}] ERROR: budget_head could not be resolved")
                _mm_notify(f":x: **Salary Payment Error**\n**frapAppId:** {frapAppId}\n**Error:** budget_head is required")
                return {"status": "error", "message": "budget_head is required for salary payment"}

            _sal_doc = frappe.new_doc("AccountHeadPayment")
            _sal_doc.project_ref_number = _sal_project
            _sal_doc.budget_head        = _sal_bh
            _sal_doc.payment_amount     = flt(payment_amount or _get_form_value("payment_amount") or 0)
            _sal_doc.payment_bmr        = bmr or _get_form_value("bmr")
            _sal_doc.payment_particular = (
                _get_form_value("payment_particular", "paymentParticular", "commitParticular")
                or f"Salary payment - {frapAppId}"
            )
            _sal_doc.payment_date   = _get_form_value("payment_date", "commitDate") or today()
            _sal_doc.payment_status = _get_form_value("payment_status", "paymentStatus") or "PENDING"
            _sal_commit_id = _get_form_value("transactionCommitNumber", "commitId")
            if _sal_commit_id and str(_sal_commit_id) not in ("0", "None", "null"):
                _sal_doc.commit_id = _sal_commit_id

            _sal_doc.flags.ignore_permissions = True
            _sal_doc.insert()
            print(f"[PAYMENT_DEBUG] Salary AccountHeadPayment inserted: {_sal_doc.name}")

            _sal_success = kafka_publish_payment(
                doc=_sal_doc,
                project_name=None,
                payment_amount=None,
                budget_head=None,
                bmr=None,
                ref_details=refDetails,
                frap_app_id=frapAppId,
                module_name=_sal_module,
            )
            print(f"[PAYMENT_DEBUG] Salary kafka_publish_payment returned: {_sal_success}")

            _dto_result = _sal_doc.as_dict()
            _dto_result["kafka_publish_success"] = _sal_success

            if _sal_success:
                _mm_notify(
                    f":white_check_mark: **Salary Kafka Published**\n"
                    f"**frapAppId:** {frapAppId}\n"
                    f"**Doc:** {_sal_doc.name}\n"
                    f"**Project:** {_sal_doc.project_ref_number or '-'}\n"
                    f"**Amount:** {_sal_doc.payment_amount or '-'}\n"
                    f"**Budget Head:** {_sal_doc.budget_head or '-'}"
                )
                _mm_notify_salary_json("Salary Payment - After DTO Publish", _dto_result)
                return {
                    "status": "success",
                    "message": "Salary payment published to Kafka",
                    "name": _sal_doc.name,
                    "data": _sal_doc.as_dict(),
                }
            else:
                _mm_notify(
                    f":x: **Salary Kafka FAILED**\n"
                    f"**frapAppId:** {frapAppId}\n"
                    f"**Doc:** {_sal_doc.name}\n"
                    f"**Project:** {_sal_doc.project_ref_number or '-'}"
                )
                _mm_notify_salary_json("Salary Payment - After DTO Publish (FAILED)", _dto_result)
                return {"status": "error", "message": "Failed to publish salary payment to Kafka"}

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
                _mm_notify(
                    f":x: **Payment Validation Error**\n"
                    f"**DocType:** {doctype}\n"
                    f"**Name:** {name}\n"
                    f"**Error:** Project Reference Number is required to create a Payment"
                )
                return {"status": "error", "message": "Project Reference Number is required to create a Payment"}
            if not doc.budget_head:
                _mm_notify(
                    f":x: **Payment Validation Error**\n"
                    f"**DocType:** {doctype}\n"
                    f"**Name:** {name}\n"
                    f"**Error:** Budget Head is required to create a Payment"
                )
                return {"status": "error", "message": "Budget Head is required to create a Payment"}

        # Save document to generate name/ID
        doc.flags.ignore_permissions = True
        print(f"[PAYMENT_DEBUG] Before save. is_new={is_new} doc.name={doc.name}")
        if is_new:
            doc.insert()
        else:
            doc.save()

        print(f"[PAYMENT_DEBUG] After save. doc.name={doc.name}")

        # Pre-flight: verify the two fields the validator requires before hitting Kafka
        from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import (
            resolve_budget_head_id, get_project_number
        )
        _pre_project = get_project_number(doc.project_ref_number)
        _pre_bh_id   = resolve_budget_head_id(doc.budget_head)
        print(f"[PAYMENT_DEBUG] pre-flight projectNumber={_pre_project!r} accountHeadId={_pre_bh_id!r}")

        if not _pre_project:
            msg = f"Cannot publish: project_ref_number '{doc.project_ref_number}' did not resolve to a project number"
            _mm_notify(f":x: **Kafka Payment Pre-flight Failed**\n**Doc:** {doc.name}\n**Error:** {msg}")
            return {"status": "error", "message": msg}

        if _pre_bh_id is None:
            msg = f"Cannot publish: budget_head '{doc.budget_head}' has no integer id/idx — update the Budget Head record"
            _mm_notify(f":x: **Kafka Payment Pre-flight Failed**\n**Doc:** {doc.name}\n**Error:** {msg}")
            return {"status": "error", "message": msg}

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
        _mm_notify(
            f":rotating_light: **submit_payment_data Exception**\n"
            f"**DocType:** {doctype}\n"
            f"**Name:** {name}\n"
            f"**Error:** {str(e)}"
        )
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def publish_salary_staging(salary_year_month):
    """
    Publish all staged salary records for the given year-month to Kafka.

    Reads the Salary Staging document keyed by salary_year_month, iterates
    every record in the salary_record JSON array, creates an AccountHeadPayment
    document for each, and publishes it to Kafka via kafka_publish_payment.

    Each record's status inside the JSON array is updated to "PUBLISHED" or
    "FAILED" after the attempt. The staging document is saved once at the end.

    Args:
        salary_year_month (str): Primary key of the Salary Staging document
            (e.g. "2026_june" or "2026-06").

    Returns:
        dict: {
            "status": "success" | "error",
            "published": int,    # count of records successfully published
            "failed": int,       # count of records that failed
            "skipped": int,      # count of records already published
            "total": int,
            "message": str
        }
    """
    if not salary_year_month:
        return {"status": "error", "message": "salary_year_month is required"}

    if not frappe.db.exists("Salary Staging", salary_year_month):
        return {"status": "error", "message": f"Salary Staging '{salary_year_month}' not found"}

    try:
        staging_doc = frappe.get_doc("Salary Staging", salary_year_month)
        raw = staging_doc.get("salary_record") or "[]"
        try:
            records = json.loads(raw)
            if not isinstance(records, list):
                records = [records]
        except Exception:
            return {"status": "error", "message": "salary_record is not valid JSON"}

        published = failed = skipped = 0

        for idx, record in enumerate(records):
            if record.get("status") == "PUBLISHED":
                skipped += 1
                continue

            # Pull all fields from the staged record
            rec_name       = record.get("name") or None
            rec_project    = record.get("project_name") or record.get("projectNumber")
            rec_amount     = record.get("payment_amount") or record.get("commitAmount")
            rec_bhead      = record.get("budget_head")
            rec_bmr        = record.get("bmr")
            rec_ref        = record.get("refDetails")
            rec_app_id     = record.get("frapAppId")
            # Use moduleId (already an int/digit string) so the mapper can cast it directly
            rec_module_id  = str(record.get("moduleId") or "11")
            rec_particular = record.get("payment_particular") or record.get("commitParticular")
            rec_pay_date   = record.get("payment_date") or record.get("commitDate")
            rec_pay_status = record.get("payment_status") or "PENDING"
            rec_commit_id  = record.get("transactionCommitNumber") or None

            print(f"[SALARY_PUBLISH] Processing record {idx}: frapAppId={rec_app_id} project={rec_project} amount={rec_amount} moduleId={rec_module_id}")

            try:
                # Normalize name — always create a fresh AccountHeadPayment
                if not rec_name or rec_name in ("None", "null", "undefined", ""):
                    rec_name = None

                doc = None
                if rec_name:
                    try:
                        doc = frappe.get_doc("AccountHeadPayment", rec_name)
                    except frappe.DoesNotExistError:
                        pass

                is_new = not doc
                if is_new:
                    doc = frappe.new_doc("AccountHeadPayment")

                # Resolve project_ref_number: accept project_no or Frappe PK
                raw_proj = rec_project
                if raw_proj and not frappe.db.exists("Project Registration", raw_proj):
                    found = frappe.db.get_value("Project Registration", {"project_no": raw_proj}, "name")
                    if found:
                        raw_proj = found
                doc.project_ref_number = raw_proj

                # Resolve budget head: accept name, label, or numeric id string
                raw_bh = rec_bhead
                if raw_bh and not frappe.db.exists("Budget Head", raw_bh):
                    found = (
                        frappe.db.get_value("Budget Head", {"budget_head": raw_bh}, "name")
                        or frappe.db.get_value("Budget Head", {"id": raw_bh}, "name")
                    )
                    if found:
                        raw_bh = found
                doc.budget_head    = raw_bh
                doc.payment_amount = flt(rec_amount or 0)
                doc.payment_bmr    = rec_bmr
                doc.payment_status = rec_pay_status
                doc.payment_date   = rec_pay_date or today()
                if rec_particular:
                    doc.payment_particular = rec_particular
                if rec_commit_id:
                    doc.commit_id = rec_commit_id

                if is_new and not doc.project_ref_number:
                    raise ValueError("project_ref_number is required")
                if is_new and not doc.budget_head:
                    raise ValueError("budget_head is required")

                doc.flags.ignore_permissions = True
                if is_new:
                    doc.insert()
                else:
                    doc.save()

                print(f"[SALARY_PUBLISH] Saved AccountHeadPayment: {doc.name}")

                success = kafka_publish_payment(
                    doc=doc,
                    project_name=None,
                    payment_amount=None,
                    budget_head=None,
                    bmr=None,
                    ref_details=rec_ref,
                    frap_app_id=rec_app_id,
                    module_name=rec_module_id,  # digit string "11" → mapper casts to int 11
                )
                print(f"[SALARY_PUBLISH] kafka_publish_payment returned: {success}")

                if success:
                    records[idx]["status"] = "PUBLISHED"
                    records[idx]["payment_doc"] = doc.name
                    published += 1
                    _mm_notify(
                        f":white_check_mark: **Salary Kafka Published**\n"
                        f"**Staging:** {salary_year_month}\n"
                        f"**Doc:** {doc.name}\n"
                        f"**Project:** {doc.project_ref_number or '-'}\n"
                        f"**Amount:** {doc.payment_amount or '-'}\n"
                        f"**Budget Head:** {doc.budget_head or '-'}"
                    )
                else:
                    records[idx]["status"] = "FAILED"
                    failed += 1
                    _mm_notify(
                        f":x: **Salary Kafka FAILED**\n"
                        f"**Staging:** {salary_year_month}\n"
                        f"**Doc:** {doc.name}\n"
                        f"**Project:** {doc.project_ref_number or '-'}"
                    )

            except Exception as rec_err:
                print(f"[SALARY_PUBLISH] Exception on record {idx}: {str(rec_err)}")
                frappe.log_error(frappe.get_traceback(), f"Salary Publish Record Error [{salary_year_month}][{idx}]")
                records[idx]["status"] = "FAILED"
                records[idx]["error"] = str(rec_err)
                failed += 1
                _mm_notify(
                    f":rotating_light: **Salary Publish Exception**\n"
                    f"**Staging:** {salary_year_month}\n"
                    f"**Record index:** {idx}\n"
                    f"**Error:** {str(rec_err)}"
                )

        # Persist updated statuses back to the staging doc
        staging_doc.salary_record = json.dumps(records, default=str)
        staging_doc.save(ignore_permissions=True)
        frappe.db.commit()

        total = len(records)
        summary = f"total={total} published={published} failed={failed} skipped={skipped}"
        print(f"[SALARY_PUBLISH] Done: {summary}")

        return {
            "status": "success" if failed == 0 else "partial",
            "published": published,
            "failed": failed,
            "skipped": skipped,
            "total": total,
            "message": summary,
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Publish Salary Staging Error")
        _mm_notify(
            f":rotating_light: **publish_salary_staging Exception**\n"
            f"**Staging:** {salary_year_month}\n"
            f"**Error:** {str(e)}"
        )
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

def _get_client_ip():
    try:
        env = frappe.local.request.environ
        forwarded = env.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        return forwarded or env.get("REMOTE_ADDR", "Unknown")
    except Exception:
        return "Unknown"


@frappe.whitelist()
def set_workflow_state(doctype, docname, state, comment=None, override_password=None):
    try:
        from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD

        if override_password != ADMIN_ACTION_PASSWORD:
            return {"status": "error", "message": "Incorrect password. State not changed."}

        if not frappe.db.exists(doctype, docname):
            return {"status": "error", "message": "Document not found"}

        prev_state = frappe.db.get_value(doctype, docname, "workflow_state") or "Unknown"
        user = frappe.session.user
        comment = (comment or "").strip()
        ip = _get_client_ip()

        frappe.db.set_value(doctype, docname, "workflow_state", state, update_modified=False)

        reason_text = f" | Reason: {comment}" if comment else ""
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Workflow",
            "reference_doctype": doctype,
            "reference_name": docname,
            "content": (
                f"[Manual Override] Workflow state changed by {user} "
                f"via Admin Panel: {prev_state} → {state}{reason_text} | IP: {ip}"
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
            "ip": ip,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "set_workflow_state failed")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_workflow_state_history(doctype, docname, limit=30):
    """
    Returns the manual workflow override history for a document,
    parsed from Workflow-type Comments, including the recorded IP address.
    """
    import re

    try:
        comments = frappe.get_all(
            "Comment",
            filters={
                "comment_type": "Workflow",
                "reference_doctype": doctype,
                "reference_name": docname,
            },
            fields=["name", "content", "creation", "owner"],
            order_by="creation desc",
            limit=int(limit),
        )

        history = []
        for c in comments:
            if "[Manual Override]" not in c.content:
                continue

            entry = {
                "creation": str(c.creation),
                "owner": c.owner,
                "from_state": None,
                "to_state": None,
                "ip": None,
                "reason": None,
            }

            # from_state → to_state  (after "Admin Panel: ")
            m = re.search(r"Admin Panel:\s*(.+?)\s*→\s*(.+?)(?:\s*\||$)", c.content)
            if m:
                entry["from_state"] = m.group(1).strip()
                entry["to_state"] = m.group(2).strip()

            # IP address
            m = re.search(r"\|\s*IP:\s*([^\s|]+)", c.content)
            if m:
                entry["ip"] = m.group(1).strip()

            # Reason
            m = re.search(r"\|\s*Reason:\s*(.+?)(?:\s*\|IP:|\s*\|\s*IP:|$)", c.content)
            if m:
                entry["reason"] = m.group(1).strip()

            history.append(entry)

        return {"status": "success", "history": history}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_workflow_state_history failed")
        return {"status": "error", "message": str(e)}


# ============================================================
# SALARY STAGING SEARCH ENDPOINT (Salary View page)
# ============================================================

_SALARY_MONTH_ORDER = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


@frappe.whitelist(allow_guest=True)
def search_salary_records(query=None, year=None, month=None, status=None, page=1, page_size=20):
    """
    Flatten and search Salary Staging records (one row per employee per month).

    Each `Salary Staging` doc is named "{year}_{month}" (e.g. "2026_june") and
    stores its `salary_record` field as a JSON array of commit payloads, each
    carrying a `salary_user_details` block with the employee's pay breakup.
    This flattens all such docs into rows and supports free-text search plus
    year/month/status filters, paginated.

    Args:
        query     (str): Free-form search — matches employee id/name/email,
                          department, designation, project number, year_month.
        year      (str): Optional exact year filter, e.g. "2026".
        month     (str): Optional exact month filter, e.g. "june".
        status    (str): Optional exact status filter, e.g. "PENDING_PUBLISH".
        page      (int): 1-based page number (default 1).
        page_size (int): Results per page (default 20, capped at 200).

    Returns:
        {
            "status": "success",
            "total": <int>,
            "page": <int>,
            "page_size": <int>,
            "results": [ {year_month, year, month, employee_id, employee_name,
                          email, department, designation, basic_salary, hra,
                          working_days, gross_pay, total_deduction, net_pay,
                          status, project_number, commit_date}, ... ],
            "available_year_months": [<all Salary Staging doc names>],
            "available_statuses": [<distinct status values found>],
        }
    """
    try:
        page = max(1, int(page or 1))
        page_size = min(200, max(1, int(page_size or 20)))
        
        name_filters = {}
        if year and month:
            name_filters["name"] = f"{str(year).strip()}_{str(month).strip().lower()}"
        elif year:
            name_filters["name"] = ["like", f"{str(year).strip()}_%"]
        elif month:
            name_filters["name"] = ["like", f"%_{str(month).strip().lower()}"]

        staging_docs = frappe.get_all(
            "Salary Staging",
            filters=name_filters,
            fields=["name", "salary_record"],
            limit_page_length=0,
        )

        dept_cache = {}

        def resolve_dept(dept_id):
            if not dept_id:
                return "—"
            if dept_id not in dept_cache:
                dept_cache[dept_id] = frappe.db.get_value("Department_prornd", dept_id, "dept_name") or dept_id
            return dept_cache[dept_id]

        rows = []
        statuses_seen = set()

        for doc in staging_docs:
            year_month = doc.name
            if "_" in year_month:
                yr, mo = year_month.split("_", 1)
            else:
                yr, mo = year_month, ""

            try:
                records = json.loads(doc.salary_record or "[]")
                if not isinstance(records, list):
                    records = [records]
            except Exception:
                records = []

            for r in records:
                ud = r.get("salary_user_details") or {}
                bd = r.get("salary_backend_details") or {}
                rec_status = r.get("status")
                if rec_status:
                    statuses_seen.add(rec_status)

                rows.append({
                    "year_month": year_month,
                    "year": yr,
                    "month": mo,
                    "employee_id": ud.get("employee_id") or bd.get("ps_emp_id"),
                    "employee_name": ud.get("first_name"),
                    "email": ud.get("email_id"),
                    "department": resolve_dept(ud.get("department")),
                    "designation": ud.get("designation"),
                    "basic_salary": ud.get("basic_salary"),
                    "hra": ud.get("hra"),
                    "working_days": ud.get("working_days"),
                    "gross_pay": ud.get("gross_pay"),
                    "total_deduction": ud.get("total_deduction"),
                    "net_pay": ud.get("net_pay"),
                    "status": rec_status,
                    "project_number": r.get("projectNumber") or bd.get("project_no"),
                    "commit_date": r.get("commitDate"),
                })

        if status:
            rows = [r for r in rows if (r.get("status") or "").lower() == str(status).lower()]

        if query:
            q = str(query).strip().lower()

            def matches(r):
                haystack = [
                    r.get("employee_id"), r.get("employee_name"), r.get("email"),
                    r.get("department"), r.get("designation"), r.get("project_number"),
                    r.get("year_month"),
                ]
                return any(q in str(f).lower() for f in haystack if f)

            rows = [r for r in rows if matches(r)]

        rows.sort(key=lambda r: (
            -(int(r["year"]) if str(r["year"]).isdigit() else 0),
            -_SALARY_MONTH_ORDER.get((r.get("month") or "").lower(), 0),
            (r.get("employee_name") or "").lower(),
        ))

        total = len(rows)
        offset = (page - 1) * page_size
        page_rows = rows[offset: offset + page_size]

        all_year_months = (
            [d.name for d in staging_docs] if not (year or month)
            else [d.name for d in frappe.get_all("Salary Staging", fields=["name"], limit_page_length=0)]
        )

        return {
            "status": "success",
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": page_rows,
            "available_year_months": sorted(all_year_months, reverse=True),
            "available_statuses": sorted(statuses_seen) or ["PENDING_APPROVAL", "PENDING_PUBLISH", "PUBLISHED", "FAILED"],
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "search_salary_records error")
        return {"status": "error", "message": str(e)}
# END OJS


@frappe.whitelist()
def delete_salary_record(year_month=None, employee_id=None, project_number=None, commit_date=None, override_password=None):
    """
    Remove a single employee's entry from a Salary Staging doc's `salary_record`
    JSON array (one Salary Staging doc holds all employees' records for a month,
    so this is a read-modify-write, not a doc-level delete). If the array becomes
    empty, the Salary Staging doc itself is deleted. Password-gated like the other
    Danger Zone actions (set_workflow_state, delete_project_registrations).
    """
    from rndopsapp.delete_projects_tmp import ADMIN_ACTION_PASSWORD

    if override_password != ADMIN_ACTION_PASSWORD:
        return {"status": "error", "message": "Incorrect password. Record not deleted."}

    if not year_month or not employee_id:
        return {"status": "error", "message": "year_month and employee_id are required"}

    if not frappe.db.exists("Salary Staging", year_month):
        return {"status": "error", "message": "Salary Staging record not found"}

    lock_name = f"salary_staging_{year_month}"
    got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_name)[0][0]
    if not got_lock:
        return {"status": "error", "message": "Could not acquire salary staging lock, please retry"}

    try:
        staging_doc = frappe.get_doc("Salary Staging", year_month)
        try:
            records = json.loads(staging_doc.salary_record or "[]")
            if not isinstance(records, list):
                records = [records]
        except Exception:
            records = []

        def matches(r):
            ud = r.get("salary_user_details") or {}
            bd = r.get("salary_backend_details") or {}
            rec_emp_id = ud.get("employee_id") or bd.get("ps_emp_id")
            if str(rec_emp_id) != str(employee_id):
                return False
            if project_number and str(r.get("projectNumber") or bd.get("project_no")) != str(project_number):
                return False
            if commit_date and str(r.get("commitDate")) != str(commit_date):
                return False
            return True

        before_count = len(records)
        remaining = [r for r in records if not matches(r)]
        removed_count = before_count - len(remaining)

        if removed_count == 0:
            return {"status": "error", "message": "No matching record found to delete"}

        user = frappe.session.user
        ip = _get_client_ip()

        if remaining:
            staging_doc.salary_record = json.dumps(remaining, default=str)
            staging_doc.save(ignore_permissions=True)
        else:
            frappe.delete_doc("Salary Staging", year_month, ignore_permissions=True)

        frappe.db.commit()

        _mm_notify(
            f":wastebasket: **Salary Record Deleted**\n"
            f"**Month:** {year_month}\n"
            f"**Employee:** {employee_id}\n"
            f"**Deleted by:** {user}\n"
            f"**IP:** {ip}\n"
            f"**Remaining records in month:** {len(remaining)}"
        )

        return {
            "status": "success",
            "message": f"Deleted {removed_count} record(s) for {employee_id} in {year_month}",
            "removed_count": removed_count,
            "remaining_count": len(remaining),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "delete_salary_record failed")
        return {"status": "error", "message": str(e)}
    finally:
        frappe.db.sql("SELECT RELEASE_LOCK(%s)", lock_name)
