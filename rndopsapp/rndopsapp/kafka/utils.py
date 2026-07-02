# Copyright (c) 2025, rndops and contributors
# Kafka Utilities - Shared utilities for Kafka operations

import json
import time
import threading
import frappe
import requests
from datetime import datetime, date
from typing import Optional, Any

# --- MATTERMOST CONFIG ---
_MM_URL = "http://172.16.135.118:8065/api/v4/posts"
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_KAFKA_CHANNEL = "yh7piky97iycjrdytia1hqy99a"  # "kafka logs" channel


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
        except Exception as dlq_error:
            log_error(
                f"CRITICAL: Failed to send to DLQ {dlq_topic}: {str(dlq_error)}",
                "DLQ_ERROR"
            )

    log_producer_event("PUBLISH", doc_name, topic, "FAILED", str(last_error))
    return False


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


def get_budget_head_id(account_head: Optional[str]) -> Optional[int]:
    """
    Get budget head ID from Budget Head doctype.

    Args:
        account_head: Budget Head document name or budget_head field value

    Returns:
        int or None: Budget Head ID if found
    """
    if not account_head:
        return None

    try:
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
