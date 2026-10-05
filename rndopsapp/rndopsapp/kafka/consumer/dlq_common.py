# Copyright (c) 2026, rndops and contributors
# Shared helpers for the DLQ consumers (sanction_dlq, fund_received_dlq,
# deposit_slip_dlq, loan_request_dlq, commit_dlq).
#
# account-head-commit's DLQ consumer reverts a "Kafka Commit Staging" row
# instead of a workflow_state, since the ~9 doctypes that feed staging have
# no captured "previous state" to revert to (see commit_dlq/) — but it still
# uses notify_ledger_rejection() below to alert the document owner.

import frappe
from typing import Optional

# Dedicated system user (User doctype, enabled=0, login disabled) so
# ledger-driven comments/notifications are attributed to "Account Portal"
# rather than "Administrator" — every DLQ consumer runs in a background
# thread under the Administrator session, but this content originates from
# the external ledger, not an actual admin action. Same convention as
# kafka/consumer/fund_received/mapper.py::ACCOUNT_PORTAL_USER and the
# "Account Portal" comments merged into api.py::get_project_activity.
ACCOUNT_PORTAL_USER = 'account.portal@rndopsapp.local'


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


def notify_ledger_rejection(reference_doctype: str, reference_name: str, error_message: str) -> None:
    """
    Alerts a document's owner that the external ledger rejected something
    published on its behalf, via a Comment (audit trail) + Notification Log
    (bell-icon alert) — same pattern as
    kafka/consumer/fund_received/mapper.py::_notify_ledger_status_change,
    generalized for any doctype. Used by commit_dlq, whose ~9 source
    doctypes (Travel, TA/DA Settlement, Miscellaneous Commit, etc.) have no
    workflow_state to revert, so this is the only signal the owner gets that
    their already-"Approved" document was actually rejected downstream.

    Best-effort: every failure is caught and logged, never raised — a
    notification failure must not fail DLQ processing of the Kafka message.
    """
    if not reference_doctype or not reference_name:
        return

    message = f"The external ledger rejected this. {error_message}".strip()

    try:
        comment = frappe.get_doc({
            'doctype': 'Comment',
            'comment_type': 'Comment',
            'reference_doctype': reference_doctype,
            'reference_name': reference_name,
            'content': f"[Ledger Status] {message}",
            'owner': ACCOUNT_PORTAL_USER,
        })
        comment.insert(ignore_permissions=True)
        # insert() only pre-fills owner when unset — force it in case a
        # future frappe version starts overwriting an explicitly-set one.
        if comment.owner != ACCOUNT_PORTAL_USER:
            frappe.db.set_value('Comment', comment.name, 'owner', ACCOUNT_PORTAL_USER)
    except Exception:
        frappe.log_error(
            f"Failed to add ledger-rejection comment on {reference_doctype} {reference_name}",
            "DLQ Ledger Rejection Notify Error",
        )

    try:
        owner = frappe.db.get_value(reference_doctype, reference_name, 'owner')
        if owner and owner not in ('Administrator', 'Guest'):
            from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
            enqueue_create_notification([owner], {
                'type': 'Alert',
                'document_type': reference_doctype,
                'document_name': reference_name,
                'subject': f"{reference_doctype} {reference_name}: {message}",
                'from_user': ACCOUNT_PORTAL_USER,
            })
    except Exception:
        frappe.log_error(
            f"Failed to notify owner of ledger rejection on {reference_doctype} {reference_name}",
            "DLQ Ledger Rejection Notify Error",
        )
