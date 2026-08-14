# Copyright (c) 2026, rndops and contributors
# Commit DLQ Consumer Mapper - resolves the DTO back to a "Kafka Commit Staging"
# row and reverts it, rather than a document workflow_state.
#
# account-head-commit-events is fed by ~9 unrelated doctypes (Travel, TA/DA
# Settlement, Disbursal of Honorarium/Consultancy, Top Up Fellowship,
# Recruitment Adhoc Contractual, Indent General Form, Cancellation Request,
# ICSS PO) via commitPayment.py::check_workflow_and_publish, each staged
# through "Kafka Commit Staging". None of them have a captured "previous
# workflow_state" to revert to (unlike Fund Sanction/Fund Received/Deposit
# Slip), so this flips the existing staging row PUBLISHED -> FAILED instead —
# the same mechanism check_workflow_and_publish already uses for its own
# synchronous failure path — which the frontend already polls via
# commitPayment.get_commit_staging_status.

import frappe
from typing import Optional

from .dto import CommitDlqEventDTO
from ..dlq_common import log_dlq_event
from ...config import TOPIC_ACCOUNT_HEAD_COMMIT_DLQ

STAGING_DOCTYPE = "Kafka Commit Staging"
DLQ_ERROR_MESSAGE = f"Rejected by downstream ledger consumer ({TOPIC_ACCOUNT_HEAD_COMMIT_DLQ})"


class CommitDlqMapper:

    @staticmethod
    def resolve_staging_row(dto: CommitDlqEventDTO) -> Optional[dict]:
        """Best-effort match of the PUBLISHED staging row that produced this
        event, via the frap_app_id stored inside its JSON payload (set by
        commitPayment.py::submit_commit_data)."""
        if not dto.frap_app_id:
            return None

        rows = frappe.db.sql(
            """
            SELECT name, reference_doctype, reference_name
            FROM `tabKafka Commit Staging`
            WHERE status = 'PUBLISHED'
              AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$.frap_app_id')) = %s
            ORDER BY creation DESC
            LIMIT 1
            """,
            (dto.frap_app_id,),
            as_dict=True,
        )
        return rows[0] if rows else None

    @classmethod
    def handle(cls, dto: CommitDlqEventDTO) -> bool:
        staging_row = cls.resolve_staging_row(dto)
        reference_doctype = None
        reference_name = None
        reverted = False

        if staging_row:
            frappe.db.set_value(STAGING_DOCTYPE, staging_row.name, "status", "FAILED")
            frappe.db.set_value(STAGING_DOCTYPE, staging_row.name, "error_message", DLQ_ERROR_MESSAGE)
            frappe.db.commit()
            reference_doctype = staging_row.reference_doctype
            reference_name = staging_row.reference_name
            reverted = True

        log_dlq_event(
            source_topic=TOPIC_ACCOUNT_HEAD_COMMIT_DLQ,
            event_type=dto.event_type or "ACCOUNT_HEAD_COMMIT",
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            project_number=dto.project_number,
            previous_workflow_state=None,
            reverted=reverted,
            raw_payload=dto.raw_payload,
        )
        return True
