# Copyright (c) 2026, rndops and contributors
# Shared helpers for the workflow-state-reverting DLQ consumers
# (sanction_dlq, fund_received_dlq, deposit_slip_dlq, loan_request_dlq).
#
# account-head-commit's DLQ consumer does not use this — it reverts a "Kafka
# Commit Staging" row instead of a workflow_state, since the ~9 doctypes that
# feed staging have no captured "previous state" to revert to (see commit_dlq/).

import frappe
from typing import Optional


def find_publish_state_log(reference_doctype: str, reference_name: str, topic: str) -> list:
    """
    Returns the most recent still-PUBLISHED "Kafka Publish State Log" row for
    this document+topic (as a list of 0 or 1 frappe._dict), or [].

    This is the authoritative source for what workflow_state to revert to — the
    DLQ consumer runs long after the original save transaction, so unlike
    project_registration.py's synchronous revert-on-failure it can't call
    get_doc_before_save() itself. The producer call site captures that instead,
    right before publishing (see e.g. research_deposit_slip.py::on_update).
    """
    if not reference_doctype or not reference_name:
        return []
    return frappe.get_all(
        "Kafka Publish State Log",
        filters={
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "topic": topic,
            "status": "PUBLISHED",
        },
        fields=["name", "previous_workflow_state"],
        order_by="creation desc",
        limit=1,
    )


def revert_workflow_state(
    reference_doctype: str, reference_name: str, previous_state: str, state_log_name: str
):
    """
    Reverts a document's workflow_state after its Kafka event landed on a DLQ,
    mirroring project_registration.py's existing synchronous revert idiom
    (frappe.db.set_value + explicit commit, bypassing validate hooks since the
    document may no longer satisfy the state it's being pulled back from).
    """
    frappe.db.set_value(
        reference_doctype, reference_name, "workflow_state", previous_state, update_modified=False
    )
    frappe.db.set_value("Kafka Publish State Log", state_log_name, "status", "DLQ_REVERTED")
    frappe.db.commit()


def log_dlq_event(
    source_topic: str,
    event_type: str,
    reference_doctype: Optional[str],
    reference_name: Optional[str],
    project_number: Optional[str],
    previous_workflow_state: Optional[str],
    reverted: bool,
    raw_payload: dict,
) -> str:
    """
    Persists every DLQ message for visibility, whether or not it could be
    resolved/reverted, mirroring "Kafka Payment DLQ Log" (kafka/consumer/payment_dlq/).
    """
    log_doc = frappe.get_doc({
        "doctype": "Kafka Event DLQ Log",
        "source_topic": source_topic,
        "event_type": event_type,
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "project_number": project_number,
        "previous_workflow_state": previous_workflow_state,
        "reverted": 1 if reverted else 0,
        "raw_payload": frappe.as_json(raw_payload),
    })
    log_doc.insert(ignore_permissions=True)
    return log_doc.name
