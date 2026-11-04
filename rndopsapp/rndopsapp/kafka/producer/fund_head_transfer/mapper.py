# Copyright (c) 2026, rndops and contributors
# Fund Head Transfer Mapper - Maps an Acc Head to Head Fund Transfer document to DTO

from datetime import datetime
from typing import Optional

import frappe
from frappe.utils import flt, now_datetime

from .dto import FundHeadTransferDTO, FundHeadTransferEventDTO
from ...config import SCHEMA_VERSION_FUND_HEAD_TRANSFER
from ...utils import get_budget_head_id, resolve_budget_head_name


# Fund Received states at or past the point its own event was published
# (PENDING_APPROVAL), i.e. receipts the Accounts service already knows about.
# 'Pending Rectification' is left out: Accounts sent that receipt back, so its
# money is not in the ledger to be moved.
PUBLISHED_FUND_RECEIVED_STATES = (
    "PENDING_APPROVAL",
    "Pending Reconciliation",
    "Pending Misc. Staff Approval(Deposit Slip Pending)",
    "Pending HoS Approval",
    "Approved",
    "Fund Received",
)


def resolve_fund_received_reference(project_name: str, from_head: str) -> Optional[str]:
    """
    The Fund Received a transfer is booked against.

    A transfer moves money between heads, not out of one receipt, so when a project has
    several receipts there is no single right answer. The rule: the most recent published
    Fund Received on the project that credited the head the money is leaving. Its breakup
    rows hold the head as a docname, numeric id or label (§4a.2 of the loan-settlement
    doc), so both sides go through resolve_budget_head_name() before comparing.

    Returns None when no published receipt credited the head — the validator blocks on
    that, since a head nothing was received into has nothing to transfer.
    """
    target = resolve_budget_head_name(from_head)
    if not project_name or not target:
        return None

    receipts = frappe.get_all(
        "Fund Received",
        filters={
            "prjreg_title": project_name,
            "workflow_state": ["in", PUBLISHED_FUND_RECEIVED_STATES],
            "docstatus": ["!=", 2],
        },
        fields=["name"],
        order_by="creation desc",
    )
    for receipt in receipts:
        rows = frappe.get_all(
            "Project Received Budget",
            filters={"parent": receipt.name, "parenttype": "Fund Received"},
            fields=["account_head", "amount_received"],
        )
        if any(
            flt(row.amount_received) > 0 and resolve_budget_head_name(row.account_head) == target
            for row in rows
        ):
            return receipt.name

    return None


class FundHeadTransferMapper:
    """
    Maps an approved Acc Head to Head Fund Transfer to the Accounts service's payload.

    h2h_transfer_from / h2h_transfer_to are Budget Head docnames; the ledger knows heads
    by their numeric id, so both go through get_budget_head_id().
    """

    @classmethod
    def map_to_dto(cls, doc, transferred_at: Optional[datetime] = None) -> FundHeadTransferDTO:
        from_id = get_budget_head_id(doc.h2h_transfer_from)
        to_id = get_budget_head_id(doc.h2h_transfer_to)
        transferred_at = transferred_at or now_datetime()

        return FundHeadTransferDTO(
            transferRefNumber=doc.name,
            projectNumber=doc.h2h_proj_num or "",
            fundReceivedRefNumberFap=resolve_fund_received_reference(
                doc.h2h_proj_code, doc.h2h_transfer_from
            ),
            fromAccountHeadId=int(from_id) if from_id else None,
            toAccountHeadId=int(to_id) if to_id else None,
            amount=round(flt(doc.h2h_amount), 2),
            reason=(doc.h2h_justification or "").strip() or None,
            transferredBy=doc.h2h_app_webmail or None,
            transferredAt=transferred_at.strftime("%Y-%m-%dT%H:%M:%S"),
        )

    @classmethod
    def map_to_event(cls, doc, transferred_at: Optional[datetime] = None) -> FundHeadTransferEventDTO:
        return FundHeadTransferEventDTO(
            schemaVersion=SCHEMA_VERSION_FUND_HEAD_TRANSFER,
            eventType="FUND_HEAD_TRANSFER",
            timestamp=datetime.utcnow().isoformat(),
            data=cls.map_to_dto(doc, transferred_at),
        )
