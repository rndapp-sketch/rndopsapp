# Copyright (c) 2025, rndops and contributors
# Kafka Utilities - Shared utilities for Kafka operations

import json
import time
import threading
import frappe
import requests
from datetime import datetime, date
from typing import Optional, Any
from rndopsapp.static_config import MATTERMOST_POSTS_URL

# --- MATTERMOST CONFIG ---
_MM_URL = MATTERMOST_POSTS_URL
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
# Default is production's "kafka logs" channel; Testing overrides this in the
# gitignored rndopsapp/local_settings.py so its noise stays out of production.
_MM_KAFKA_CHANNEL = "yh7piky97iycjrdytia1hqy99a"  # "kafka logs" channel

try:
    from rndopsapp.local_settings import MM_KAFKA_CHANNEL as _MM_KAFKA_CHANNEL
except ImportError:
    pass


def mm_notify(message: str):
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

from .config import (
    KAFKA_BOOTSTRAP_SERVERS,
    PRODUCER_MAX_RETRIES,
    PRODUCER_RETRY_DELAY_SECONDS,
    PRODUCER_ACKS,
    PRODUCER_RETRIES,
    PRODUCER_LINGER_MS,
)
from .logs import log_producer_event, log_error, log_debug

# Check if Kafka is available
try:
    from kafka import KafkaProducer
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

# Singleton Producer Instance
_producer = None


def is_kafka_available() -> bool:
    """Check if Kafka library is available."""
    return KAFKA_AVAILABLE


def get_producer():
    """
    Returns a singleton KafkaProducer instance.
    Reuses the same connection for all messages.

    Returns:
        KafkaProducer or None if not available
    """
    global _producer

    if not KAFKA_AVAILABLE:
        log_error("kafka-python library not installed", "KAFKA_IMPORT_ERROR")
        return None

    if _producer is not None:
        return _producer

    try:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            acks=PRODUCER_ACKS,
            retries=PRODUCER_RETRIES,
            linger_ms=PRODUCER_LINGER_MS
        )
        log_debug(f"Kafka Producer connected to {KAFKA_BOOTSTRAP_SERVERS}")
        return _producer
    except Exception as e:
        log_error(f"Failed to connect to Kafka: {str(e)}", "KAFKA_CONNECTION_ERROR")
        frappe.log_error(f"Failed to connect to Kafka: {str(e)}", "Kafka Connection Error")
        return None


def reset_producer():
    """Reset the singleton producer instance (useful for reconnection)."""
    global _producer
    _producer = None


def publish_message(
    topic: str,
    payload: dict,
    doc_name: str,
    dlq_topic: Optional[str] = None,
    key: Optional[str] = None
) -> bool:
    """
    Publish a message to a Kafka topic with retry and DLQ support.

    Args:
        topic: Primary Kafka topic
        payload: Message payload (will be JSON serialized)
        doc_name: Document name for logging
        dlq_topic: Dead Letter Queue topic for failed messages
        key: Partitioning key (use project number for ordering)

    Returns:
        bool: True if successful, False otherwise
    """
    global _producer

    producer = get_producer()
    if not producer:
        log_producer_event("PUBLISH", doc_name, topic, "FAILED", "Producer not available")
        log_publish_data(
            topic, payload, doc_name, key, "FAILED", "kafka.utils",
            attempts=0, error="Producer not available",
        )
        return False

    # Prepare the key
    kafka_key = str(key).encode('utf-8') if key else None

    # Attempt publication with retries
    last_error = None
    for attempt in range(PRODUCER_MAX_RETRIES):
        try:
            # send() is asynchronous; it returns a future
            future = producer.send(topic, key=kafka_key, value=payload)

            # .get() makes it synchronous, waiting for broker acknowledgment
            record_metadata = future.get(timeout=10)

            log_producer_event(
                "PUBLISH",
                doc_name,
                topic,
                "SUCCESS",
                f"Partition: {record_metadata.partition} | Offset: {record_metadata.offset}"
            )
            log_publish_data(
                topic, payload, doc_name, key, "SUCCESS", "kafka.utils",
                attempts=attempt + 1,
                partition=record_metadata.partition,
                offset=record_metadata.offset,
            )
            return True

        except Exception as e:
            last_error = e
            error_details = f"Attempt {attempt + 1}/{PRODUCER_MAX_RETRIES} failed: {str(e)}"
            log_producer_event("PUBLISH", doc_name, topic, "RETRY", error_details)

            if attempt < PRODUCER_MAX_RETRIES - 1:
                # Exponential backoff
                time.sleep(PRODUCER_RETRY_DELAY_SECONDS * (2 ** attempt))
                # Reset producer on error to force fresh connection
                _producer = None
                producer = get_producer()
                if not producer:
                    break

    # All retries failed - send to DLQ
    sent_to_dlq = False
    if dlq_topic:
        try:
            producer = get_producer()
            if producer:
                dlq_payload = {
                    "originalTopic": topic,
                    "failedAt": datetime.utcnow().isoformat(),
                    "retryCount": PRODUCER_MAX_RETRIES,
                    "error": str(last_error) if last_error else "Unknown Error",
                    "payload": payload
                }
                future = producer.send(dlq_topic, key=kafka_key, value=dlq_payload)
                future.get(timeout=10)
                log_producer_event(
                    "DLQ",
                    doc_name,
                    dlq_topic,
                    "SUCCESS",
                    f"Sent to DLQ after {PRODUCER_MAX_RETRIES} attempts"
                )
                sent_to_dlq = True
        except Exception as dlq_error:
            log_error(
                f"CRITICAL: Failed to send to DLQ {dlq_topic}: {str(dlq_error)}",
                "DLQ_ERROR"
            )

    log_producer_event("PUBLISH", doc_name, topic, "FAILED", str(last_error))
    log_publish_data(
        topic, payload, doc_name, key, "FAILED", "kafka.utils",
        attempts=PRODUCER_MAX_RETRIES, error=str(last_error), sent_to_dlq=sent_to_dlq,
    )
    return False


def record_publish_state(
    reference_doctype: str,
    reference_name: str,
    topic: str,
    previous_state: Optional[str],
    published_state: Optional[str],
) -> None:
    """
    Captures the workflow_state a document had immediately before it's
    published to Kafka, so an async DLQ consumer — which runs long after this
    save transaction and can't call get_doc_before_save() itself — knows what
    to revert to if the downstream ledger service rejects the event.

    Call this right before publish_message()/publish_*, using the same
    old_state/previous_state each caller already computes for its own
    on_update logic. Skipped when there's no real transition to revert
    (brand new documents, or republishing the same state).
    """
    if not previous_state or previous_state == published_state:
        return
    try:
        frappe.get_doc({
            "doctype": "Kafka Publish State Log",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "topic": topic,
            "previous_workflow_state": previous_state,
            "published_state": published_state,
            "status": "PUBLISHED",
        }).insert(ignore_permissions=True)
    except Exception as e:
        log_error(
            f"Failed to record publish state for {reference_doctype} {reference_name}: {e}",
            "PUBLISH_STATE_LOG_ERROR",
        )


# --- PUBLISH DATA LOG ---

# Keys under which the DTOs / payloads carry the project number (all DTOs use projectNumber
# inside "data"; the others are for older payloads built by hand).
_PROJECT_NUMBER_KEYS = ("projectNumber", "projectNo", "project_number", "project_no", "project_name")


def extract_project_number(payload: Any, key: Optional[str] = None) -> Optional[str]:
    """Project number of a published message: the first projectNumber-style value found in the
    payload (the "data" envelope first), else the Kafka partition key, which callers set to
    the project number for ordering."""

    def search(obj, depth):
        if depth > 3:
            return None
        if isinstance(obj, dict):
            for k in _PROJECT_NUMBER_KEYS:
                value = obj.get(k)
                if isinstance(value, (str, int)) and str(value).strip():
                    return str(value).strip()
            nested = obj.get("data")
            ordered = ([nested] if isinstance(nested, (dict, list)) else []) + [
                v for k, v in obj.items() if k != "data" and isinstance(v, (dict, list))
            ]
            for value in ordered:
                found = search(value, depth + 1)
                if found:
                    return found
        elif isinstance(obj, list):
            for value in obj[:20]:
                found = search(value, depth + 1)
                if found:
                    return found
        return None

    found = search(payload, 0)
    if found:
        return found
    return str(key).strip() if key not in (None, "") else None


def log_publish_data(
    topic: str,
    payload: Any,
    doc_name: Optional[str],
    key: Optional[str],
    status: str,
    source: str,
    attempts: int = 1,
    partition: Optional[int] = None,
    offset: Optional[int] = None,
    error: Optional[str] = None,
    sent_to_dlq: bool = False,
) -> None:
    """Save a copy of what was handed to Kafka as a "Kafka Publish Data Log" row: the exact
    payload, topic, key, project number, and whether it was delivered (SUCCESS) or every
    attempt failed (FAILED).

    Called by both publish_message() implementations. Never raises: logging must not break a
    publish. The row is written straight to the table (no document hooks) so the app-wide
    "*" doc events don't fire for it, and it joins the caller's transaction like
    record_publish_state does.
    """
    try:
        doc = frappe.get_doc(
            {
                "doctype": "Kafka Publish Data Log",
                "project_number": extract_project_number(payload, key),
                "topic": topic,
                "event_type": payload.get("eventType") if isinstance(payload, dict) else None,
                "status": status,
                "reference_name": doc_name,
                "kafka_key": str(key) if key not in (None, "") else None,
                "source": source,
                "attempts": attempts,
                "partition": partition,
                "offset": str(offset) if offset is not None else None,
                "sent_to_dlq": 1 if sent_to_dlq else 0,
                "error_message": (error or None) and str(error)[:1000],
                "payload": json.dumps(payload, default=str, indent=1),
            }
        )
        doc.name = frappe.generate_hash(length=10)
        doc.set_user_and_timestamp()
        doc.db_insert()
    except Exception as e:
        log_error(
            f"Failed to log published message for {doc_name} on {topic}: {e}",
            "PUBLISH_DATA_LOG_ERROR",
        )


# --- CONSUME DATA LOG ---

CONSUME_REASON_LIMIT = 1500
CONSUME_LOG_LIMIT = 8000


def _own_db_connection():
    """A second, short-lived database connection for the current site, independent of
    frappe.db and whatever transaction the handler has open."""
    from frappe.database import get_db

    conf = frappe.local.conf
    return get_db(
        socket=conf.db_socket,
        host=conf.db_host,
        port=conf.db_port,
        user=conf.db_name,
        password=conf.db_password,
        cur_db_name=conf.db_name,
    )


def consume_failure_reason(events: list, exception: Optional[BaseException] = None):
    """(error_type, reason) for a message that failed: the exception, else what the handler
    itself reported (failed events / errors), else an honest "no reason reported"."""
    if exception is not None:
        return "EXCEPTION", f"{type(exception).__name__}: {exception}"[:CONSUME_REASON_LIMIT]

    reasons, types = [], []
    for e in events:
        failed = e["kind"] == "error" or e["status"] in ("FAILED", "ERROR")
        if failed and e["message"] and e["type"] != "CONSUME" and e["message"] not in reasons:
            reasons.append(e["message"])
            if e["kind"] == "error" and e["type"] not in types:
                types.append(e["type"])
    if reasons:
        return (types[0] if types else "HANDLER_FAILED"), "; ".join(reasons)[:CONSUME_REASON_LIMIT]
    return "HANDLER_FAILED", "The handler returned False without reporting a reason."


def log_consume_data(
    topic: str,
    payload: Any,
    success: bool,
    partition: Optional[int] = None,
    offset: Optional[int] = None,
    events: Optional[list] = None,
    exception: Optional[BaseException] = None,
    handler: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error_type: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> None:
    """Save a copy of a consumed message as a "Kafka Consumer Data Log" row: the payload,
    whether it was processed, the reason when not, and what the handler reported meanwhile.

    Written through its own connection and committed there, so the row survives whatever the
    handler did with its transaction (commit, rollback, or left open with partial work) and
    saving it never commits that work. Never raises: logging must not break consuming.
    """
    events = events or []
    db = None
    try:
        # A handler can accept a message (return True, so Kafka moves on) yet have done
        # nothing with it, e.g. "Document not found". That is SKIPPED, not a plain success.
        skipped = [e for e in events if e["status"] == "SKIPPED" and e["type"] != "CONSUME"]
        status = "SUCCESS" if success else "FAILED"
        if success and skipped:
            status = "SKIPPED"
            error_type = "SKIPPED"
            failure_reason = "; ".join(
                f"{e['doc'] + ': ' if e['doc'] and e['doc'] != 'N/A' else ''}{e['message']}" for e in skipped if e["message"]
            )[:CONSUME_REASON_LIMIT] or "The handler skipped this message."
        elif not success and not failure_reason:
            error_type, failure_reason = consume_failure_reason(events, exception)

        reference_name = next((e["doc"] for e in events if e["doc"] and e["doc"] != "N/A"), None)
        process_log = "\n".join(
            f"[{e['status']}] {e['type']}" + (f" doc={e['doc']}" if e["doc"] else "") + (f" | {e['message']}" if e["message"] else "")
            for e in events
        )
        now = frappe.utils.now()
        row = {
            "name": frappe.generate_hash(length=10),
            "creation": now,
            "modified": now,
            "modified_by": "Administrator",
            "owner": "Administrator",
            "project_number": extract_project_number(payload),
            "topic": topic,
            "event_type": payload.get("eventType") if isinstance(payload, dict) else None,
            "status": status,
            "reference_name": reference_name,
            "handler": handler,
            "is_dlq": 1 if str(topic).endswith("-dlq") else 0,
            # Int columns are NOT NULL in Frappe, so an unknown value is stored as 0
            "partition": partition if partition is not None else 0,
            "offset": str(offset) if offset is not None else None,
            "duration_ms": duration_ms if duration_ms is not None else 0,
            "error_type": error_type if status != "SUCCESS" else None,
            "failure_reason": failure_reason if status != "SUCCESS" else None,
            "processing_log": process_log[:CONSUME_LOG_LIMIT] or None,
            "payload": json.dumps(payload, default=str, indent=1),
        }
        columns = ", ".join(f"`{c}`" for c in row)
        placeholders = ", ".join(f"%({c})s" for c in row)

        db = _own_db_connection()
        db.sql(f"INSERT INTO `tabKafka Consumer Data Log` ({columns}) VALUES ({placeholders})", row)
        db.commit()
    except Exception as e:
        log_error(
            f"Failed to log consumed message on {topic} (partition {partition}, offset {offset}): {e}",
            "CONSUME_DATA_LOG_ERROR",
        )
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


# --- DATE UTILITIES ---

def fmt_date(d: Any) -> Optional[str]:
    """
    Format dates in ISO 8601 format with T separator.

    Args:
        d: Date value (can be datetime, date, or string)

    Returns:
        str: ISO 8601 formatted date string or None if None
    """
    if not d:
        return None
    date_str = str(d)
    return date_str.replace(' ', 'T')


def parse_date(value: Any) -> Optional[date]:
    """
    Parse various date formats to date object.

    Args:
        value: Date value (datetime, date, string, or list)

    Returns:
        date: Parsed date object or None
    """
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value)

    if isinstance(value, list) and len(value) >= 3:
        return date(value[0], value[1], value[2])

    return None


def parse_datetime(value: Any) -> Optional[datetime]:
    """
    Parse various datetime formats to datetime object.

    Args:
        value: Datetime value (datetime, string, or list)

    Returns:
        datetime: Parsed datetime object or None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(value)

    if isinstance(value, list):
        while len(value) < 6:
            value.append(0)
        return datetime(
            value[0], value[1], value[2],
            value[3], value[4], value[5]
        )

    return None


# --- DATABASE UTILITIES ---

def get_department_id(dept_link: Optional[str]) -> Optional[int]:
    """
    Get department ID from Department_prornd doctype.

    Args:
        dept_link: Department document name

    Returns:
        int or None: Department ID if found
    """
    if not dept_link:
        return None
    try:
        return frappe.db.get_value("Department_prornd", dept_link, "dept_id")
    except Exception:
        return None


def get_funding_agency_id(funding_agency_link: Optional[str]) -> Optional[str]:
    """
    Get funding agency ID from fundingagency_ doctype.

    Args:
        funding_agency_link: Funding agency document name

    Returns:
        str or None: Funding agency ID if found
    """
    if not funding_agency_link:
        return None
    try:
        return frappe.db.get_value("fundingagency_", funding_agency_link, "funding_agency_id")
    except Exception:
        return None


def resolve_budget_head_name(value) -> Optional[str]:
    """
    Resolve any of the three forms `account_head` is found in across the data
    set to a canonical Budget Head document name.

    `Project Received Budget.account_head` is declared as a Link to Budget Head,
    but real rows hold one of:
      1. the Budget Head docname       (e.g. "h1lhg99vfq") — set via the UI
      2. the numeric Budget Head `id`  (e.g. "1")          — historically written
         by the Kafka consumer's update_budget_breakup, which stored the
         incoming `accountHeadId` verbatim into this Link field
      3. the raw label                 (e.g. "Overhead")   — legacy/manual rows

    Anything that resolves is returned as the docname; unresolvable input
    returns None so callers can decide whether to skip or throw.

    Args:
        value: docname, numeric id, or budget_head label

    Returns:
        str or None: Budget Head document name if resolvable
    """
    if value in (None, ""):
        return None

    value_str = str(value).strip()

    try:
        # 1. Already a docname
        if frappe.db.exists("Budget Head", value_str):
            return value_str

        # 2. Numeric Budget Head id
        if value_str.isdigit():
            by_id = frappe.db.get_value("Budget Head", {"id": int(value_str)}, "name")
            if by_id:
                return by_id

        # 3. budget_head label
        by_label = frappe.db.get_value("Budget Head", {"budget_head": value_str}, "name")
        if by_label:
            return by_label

        return None
    except Exception:
        return None


def get_budget_head_id(account_head: Optional[str]) -> Optional[int]:
    """
    Get budget head ID from Budget Head doctype.

    Args:
        account_head: Budget Head document name, numeric id, or budget_head
            field value

    Returns:
        int or None: Budget Head ID if found
    """
    if not account_head:
        return None

    try:
        # Fast path: the value is already the numeric id (as written into
        # account_head by the Kafka consumer). Confirm it maps to a real
        # Budget Head before trusting it.
        account_head_str = str(account_head).strip()
        if account_head_str.isdigit():
            confirmed = frappe.db.get_value("Budget Head", {"id": int(account_head_str)}, "id")
            if confirmed:
                return confirmed

        # Try direct lookup by name
        account_head_id = frappe.db.get_value("Budget Head", account_head, "id")

        # Fallback: try filtering by 'budget_head' field
        if not account_head_id:
            account_head_id = frappe.db.get_value(
                "Budget Head",
                {"budget_head": account_head},
                "id"
            )

        # Fallback 2: Try plural/singular variations
        if not account_head_id:
            if account_head.endswith("s"):
                account_head_id = frappe.db.get_value(
                    "Budget Head",
                    {"budget_head": account_head[:-1]},
                    "id"
                )
            else:
                account_head_id = frappe.db.get_value(
                    "Budget Head",
                    {"budget_head": account_head + "s"},
                    "id"
                )

        return account_head_id
    except Exception:
        return None


def get_fund_received_ref_number(fund_received_ref: Optional[str]) -> int:
    """
    Get fund received reference number from Fund Received document.

    Args:
        fund_received_ref: Fund Received document name

    Returns:
        int: Fund received reference number or 0 if not found
    """
    if not fund_received_ref:
        return 0
    try:
        val = frappe.db.get_value("Fund Received", fund_received_ref, "fund_received_ref_number")
        return int(val) if val else 0
    except Exception:
        return 0


def get_project_number(doc) -> str:
    """
    Get project number from document.

    Args:
        doc: Frappe document with project_title or project_number field

    Returns:
        str: Project number
    """
    project_number = getattr(doc, 'project_number', '') or ""
    if not project_number and getattr(doc, 'project_title', None):
        try:
            project_number = frappe.db.get_value(
                "Project Registration",
                doc.project_title,
                "name"
            ) or doc.project_title
        except Exception:
            project_number = doc.project_title or ""
    return project_number


def determine_gst_type(doc) -> str:
    """
    Determine GST type from document fields.

    Args:
        doc: Frappe document with GST-related fields

    Returns:
        str: "NOGST", "CGST_SGST", or "IGST"
    """
    from frappe.utils import flt

    cgst_amount = flt(getattr(doc, 'cgst_9', 0))
    sgst_amount = flt(getattr(doc, 'sgst_9', 0))
    igst_amount = flt(getattr(doc, 'igst_18', 0) or getattr(doc, 'igst_18_on_consultancy', 0))
    total_gst = flt(getattr(doc, 'total_gst', 0))

    if total_gst > 0 or cgst_amount > 0 or sgst_amount > 0 or igst_amount > 0:
        if cgst_amount > 0 or sgst_amount > 0:
            return "CGST_SGST"
        else:
            return "IGST"
    return "NOGST"


# --- VALIDATION UTILITIES ---

def validate_required_fields(data: dict, required_fields: list, doc_name: str) -> tuple:
    """
    Validates that required fields are present and not empty.

    Args:
        data: Data dictionary to validate
        required_fields: List of required field names
        doc_name: Document name for error logging

    Returns:
        tuple: (is_valid, error_message)
    """
    missing_fields = []
    for field in required_fields:
        value = data.get(field) if isinstance(data, dict) else getattr(data, field, None)
        if value is None or value == "":
            missing_fields.append(field)

    if missing_fields:
        error_msg = f"Missing required fields for {doc_name}: {', '.join(missing_fields)}"
        log_error(error_msg, "VALIDATION_ERROR")
        return False, error_msg

    return True, None
