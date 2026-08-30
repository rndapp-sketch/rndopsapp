# Copyright (c) 2026, rndops and contributors
# Payment DLQ Consumer Mapper - resolves the DTO back to a Frappe AccountHeadPayment doc

import frappe
from typing import Optional

from .dto import PaymentDlqErrorDTO


class PaymentDlqErrorMapper:
    """
    Best-effort reverse lookup from (projectNumber, accountHeadId) back to the
    AccountHeadPayment document that produced them, mirroring
    AccountHeadPaymentMapper.map_to_dto (kafka/producer/reimbursement/mapper.py)
    which is the forward direction of the same mapping.
    """

    @staticmethod
    def resolve_reference(dto: PaymentDlqErrorDTO) -> Optional[str]:
        if not dto.project_number and dto.account_head_id is None:
            return None

        budget_head_name = None
        if dto.account_head_id is not None:
            budget_head_name = (
                frappe.db.get_value("Budget Head", {"id": dto.account_head_id}, "name")
                or frappe.db.get_value("Budget Head", {"idx": dto.account_head_id}, "name")
            )

        project_reg_name = None
        if dto.project_number:
            project_reg_name = frappe.db.get_value(
                "Project Registration", {"project_no": dto.project_number}, "name"
            )
            if not project_reg_name and frappe.db.exists("Project Registration", dto.project_number):
                project_reg_name = dto.project_number

        filters = {}
        if budget_head_name:
            filters["budget_head"] = budget_head_name
        if project_reg_name:
            filters["project_ref_number"] = project_reg_name

        if not filters:
            return None

        return frappe.db.get_value(
            "AccountHeadPayment", filters, "name", order_by="creation desc"
        )

    @staticmethod
    def revert_payment_status(reference_name: Optional[str]):
        """
        Reverts AccountHeadPayment.payment_status to REJECTED — an option
        already defined on that Select field for exactly this scenario
        (doctype/accountheadpayment/accountheadpayment.json) but previously
        unused by any code path. In practice every payment observed reaching
        the DLQ was still sitting at PENDING (the doc is never flipped to
        PAID by anything before the ledger confirms it), so PENDING is
        reverted too — only an already-REJECTED or already-RECTIFICATION row
        is left alone, since those are terminal/manually-handled states.
        """
        if not reference_name:
            return
        current_status = frappe.db.get_value("AccountHeadPayment", reference_name, "payment_status")
        if current_status in ("PAID", "PENDING"):
            frappe.db.set_value("AccountHeadPayment", reference_name, "payment_status", "REJECTED")
            frappe.db.commit()

    @staticmethod
    def save_error(dto: PaymentDlqErrorDTO, reference_name: Optional[str]) -> str:
        """
        Persists the failure as a "Kafka Payment DLQ Log" record so the frontend
        can poll for it via commitPayment.get_account_head_payment_dlq_errors.
        """
        log_doc = frappe.get_doc({
            "doctype": "Kafka Payment DLQ Log",
            "consumer_name": dto.consumer_name,
            "original_topic": dto.original_topic,
            "dlq_topic": dto.dlq_topic,
            "error_type": dto.error_type,
            "error_message": dto.error_message,
            "project_number": dto.project_number,
            "account_head_id": dto.account_head_id,
            "identifier_raw": dto.identifier_raw,
            "failed_at": dto.failed_at,
            "reference_doctype": "AccountHeadPayment" if reference_name else None,
            "reference_name": reference_name,
            "raw_payload": frappe.as_json(dto.raw_payload),
        })
        log_doc.insert(ignore_permissions=True)
        return log_doc.name
