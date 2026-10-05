# Copyright (c) 2026, rndops and contributors
# DLQ Control API - backend for the /kafka_dlq_control admin page.
#
# Four things this exposes, matching the page's four panels:
#   - View   -> list_* against our own log doctypes (Kafka Event DLQ Log,
#               Kafka Publish State Log, Kafka Payment DLQ Log, failed
#               Kafka Commit Staging rows).
#   - Check  -> get_dlq_topic_stats(), a read-only peek at the real Kafka
#               DLQ topics (message counts), same technique used to
#               investigate this in the first place: enable_auto_commit=False,
#               no group_id, nothing committed.
#   - Manage -> retry_commit_staging(), republishes one FAILED "Kafka Commit
#               Staging" row via the same kafka_publish_commit() path
#               commitPayment.py already uses.
#   - Clear  -> clear_dlq_logs(), deletes rows from our own log doctypes
#               ONLY. It never touches the actual Kafka topics/messages -
#               there is no "delete from Kafka" here, deliberately: purging
#               broker data is a separate, far more dangerous operation this
#               page does not attempt.

import json
import frappe

from .config import (
    TOPIC_PROJECT_DLQ,
    TOPIC_SANCTION_DLQ,
    TOPIC_FUND_RECEIVED_DLQ,
    TOPIC_DEPOSIT_SLIP_DLQ,
    TOPIC_LOAN_REQUEST_DLQ,
    TOPIC_ACCOUNT_HEAD_COMMIT_DLQ,
    TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ,
    KAFKA_BOOTSTRAP_SERVERS,
)

# Topics this page reports on. Includes the batch/loan-settlement DLQ topics
# even though they have no consumer yet (see kafka/DLQ_HANDLING_AND_REVERT.md
# §7) - "Check" should still show whether they've started accumulating
# messages, which is exactly the signal that would justify building a
# consumer for them.
ALL_DLQ_TOPICS_FOR_STATS = [
    TOPIC_PROJECT_DLQ,
    TOPIC_SANCTION_DLQ,
    TOPIC_FUND_RECEIVED_DLQ,
    TOPIC_DEPOSIT_SLIP_DLQ,
    TOPIC_LOAN_REQUEST_DLQ,
    TOPIC_ACCOUNT_HEAD_COMMIT_DLQ,
    TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ,
    "account-head-commit-batch-events-dlq",
    "account-head-payment-batch-events-dlq",
    "loan-settlement-events-batch-dlq",
]

# Doctypes clear_dlq_logs() is allowed to touch. Deliberately not
# frappe.whitelist-exposed as a raw doctype string from the caller beyond
# this allowlist - never delete anything else.
CLEARABLE_DOCTYPES = [
    "Kafka Event DLQ Log",
    "Kafka Publish State Log",
    "Kafka Payment DLQ Log",
]


def _require_system_manager():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can perform this action.", frappe.PermissionError)


# --- VIEW ---
#
# Every list_* below returns a "why" field: a plain-English explanation of
# what happened to that row, computed server-side so the page doesn't have
# to re-derive it. Where the source system genuinely doesn't tell us why
# (the 5 producer-owned DLQ topics carry no error reason at all - see
# kafka/DLQ_HANDLING_AND_REVERT.md §2.1) the "why" says so explicitly
# instead of leaving a blank the UI could be misread as a bug.

def _why_for_event_row(row: dict) -> str:
    if row.get("reverted"):
        if row.get("previous_workflow_state"):
            return (
                f"Downstream ledger service rejected this event after it was published. "
                f"workflow_state reverted to '{row['previous_workflow_state']}'."
            )
        return (
            "Downstream ledger service rejected this event after it was published. "
            "Matching 'Kafka Commit Staging' row marked FAILED (see the Failed Commit Staging tab)."
        )
    if not row.get("reference_doctype"):
        return (
            "Could not resolve this event to a document from the identifiers in the payload "
            "(project number / reference number didn't match anything) — nothing was reverted."
        )
    return (
        "Resolved to a document, but no matching 'Kafka Publish State Log' entry was found to "
        "revert from — nothing was changed. (Note: the ledger service doesn't send an error reason "
        "on this topic, only the rejected event itself.)"
    )


@frappe.whitelist()
def list_event_dlq_logs(source_topic=None, reference_doctype=None, reverted=None, limit=100):
    """Kafka Event DLQ Log rows - sanction/fund-received/deposit-slip/loan-request/commit DLQ hits."""
    filters = {}
    if source_topic:
        filters["source_topic"] = source_topic
    if reference_doctype:
        filters["reference_doctype"] = reference_doctype
    if reverted not in (None, ""):
        filters["reverted"] = 1 if str(reverted) in ("1", "true", "True") else 0

    rows = frappe.get_all(
        "Kafka Event DLQ Log",
        filters=filters,
        fields=[
            "name", "source_topic", "event_type", "reference_doctype", "reference_name",
            "project_number", "previous_workflow_state", "reverted", "raw_payload", "creation",
        ],
        order_by="creation desc",
        limit_page_length=int(limit),
        ignore_permissions=True,
    )
    for row in rows:
        row["why"] = _why_for_event_row(row)
    return {"status": "success", "data": rows}


@frappe.whitelist()
def list_publish_state_logs(status=None, reference_doctype=None, limit=100):
    """Kafka Publish State Log rows - the previous-state capture written right before each publish."""
    filters = {}
    if status:
        filters["status"] = status
    if reference_doctype:
        filters["reference_doctype"] = reference_doctype

    rows = frappe.get_all(
        "Kafka Publish State Log",
        filters=filters,
        fields=[
            "name", "reference_doctype", "reference_name", "topic", "status",
            "previous_workflow_state", "published_state", "error_message", "creation",
        ],
        order_by="creation desc",
        limit_page_length=int(limit),
        ignore_permissions=True,
    )
    for row in rows:
        if row.get("status") == "DLQ_REVERTED":
            row["why"] = (
                f"A DLQ event arrived for this document/topic after it was published, so it was "
                f"reverted from '{row.get('published_state')}' back to '{row.get('previous_workflow_state')}'. "
                f"See the Event DLQ Log tab for the triggering event."
            )
        else:
            row["why"] = "Still the last-known-good publish — no DLQ event has reverted it (yet)."
    return {"status": "success", "data": rows}


@frappe.whitelist()
def list_payment_dlq_logs(limit=100):
    """Kafka Payment DLQ Log rows - unfiltered admin view (the widget-facing
    commitPayment.get_account_head_payment_dlq_errors requires project/budget
    head filters; this doesn't)."""
    rows = frappe.get_all(
        "Kafka Payment DLQ Log",
        fields=[
            "name", "error_type", "error_message", "project_number", "account_head_id",
            "reference_doctype", "reference_name", "failed_at", "raw_payload", "creation",
        ],
        order_by="creation desc",
        limit_page_length=int(limit),
        ignore_permissions=True,
    )
    for row in rows:
        row["why"] = row.get("error_message") or (
            "Ledger service rejected this payment but sent no error message with it "
            f"(error_type={row.get('error_type') or 'unknown'})."
        )
    return {"status": "success", "data": rows}


@frappe.whitelist()
def list_failed_commit_staging(limit=100):
    """Kafka Commit Staging rows currently FAILED - candidates for Manage -> Retry."""
    rows = frappe.get_all(
        "Kafka Commit Staging",
        filters={"status": "FAILED"},
        fields=["name", "reference_doctype", "reference_name", "error_message", "payload", "modified"],
        order_by="modified desc",
        limit_page_length=int(limit),
        ignore_permissions=True,
    )
    for row in rows:
        row["why"] = row.get("error_message") or "Marked FAILED, but no error message was recorded."
    return {"status": "success", "data": rows}


# --- CHECK ---

@frappe.whitelist()
def get_dlq_topic_stats():
    """
    Read-only peek at real message counts on every known DLQ topic.
    Mirrors the technique used to investigate this feature in the first
    place: no group_id, enable_auto_commit=False, nothing ever committed -
    this cannot advance any consumer's offset or drop a message.
    """
    try:
        from kafka import KafkaConsumer
        from kafka.structs import TopicPartition
    except ImportError:
        return {"status": "error", "message": "kafka-python not installed on this server"}

    try:
        consumer = KafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            enable_auto_commit=False,
            consumer_timeout_ms=5000,
        )
    except Exception as e:
        return {"status": "error", "message": f"Could not connect to Kafka: {e}"}

    results = []
    try:
        for topic in ALL_DLQ_TOPICS_FOR_STATS:
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                results.append({"topic": topic, "exists": False, "message_count": 0})
                continue
            tps = [TopicPartition(topic, p) for p in partitions]
            beginning = consumer.beginning_offsets(tps)
            end = consumer.end_offsets(tps)
            total = sum(end[tp] - beginning[tp] for tp in tps)
            results.append({
                "topic": topic,
                "exists": True,
                "partitions": len(tps),
                "message_count": total,
            })
    finally:
        consumer.close()

    return {"status": "success", "data": results}


# --- MANAGE ---

@frappe.whitelist()
def retry_commit_staging(staging_name):
    """
    Re-publish one FAILED "Kafka Commit Staging" row - the same republish
    path commitPayment.manually_publish_staged_commit already implements,
    just resolved from the staging row's own name instead of requiring the
    caller to already know its reference_doctype/reference_name.
    """
    _require_system_manager()

    staging = frappe.get_doc("Kafka Commit Staging", staging_name)
    if staging.status not in ("FAILED", "PENDING_APPROVAL"):
        return {"status": "error", "message": f"Staging row is '{staging.status}', not FAILED/PENDING_APPROVAL - nothing to retry."}

    from ..commitPayment import manually_publish_staged_commit
    return manually_publish_staged_commit(staging.reference_name, staging.reference_doctype)


# --- CLEAR ---

@frappe.whitelist()
def clear_dlq_logs(doctype, filters=None):
    """
    Deletes rows from our own DLQ log/audit doctypes only - never touches
    the actual Kafka topics or messages. Restricted to System Manager and to
    CLEARABLE_DOCTYPES so this can't be pointed at an arbitrary doctype.
    """
    _require_system_manager()

    if doctype not in CLEARABLE_DOCTYPES:
        frappe.throw(f"'{doctype}' cannot be cleared from this page.")

    parsed_filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

    names = frappe.get_all(doctype, filters=parsed_filters, pluck="name", limit_page_length=0)
    for name in names:
        frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
    frappe.db.commit()

    return {"status": "success", "deleted": len(names)}
