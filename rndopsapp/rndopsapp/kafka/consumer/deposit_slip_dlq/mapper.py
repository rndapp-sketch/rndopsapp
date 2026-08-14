# Copyright (c) 2026, rndops and contributors
# Deposit Slip DLQ Consumer Mapper - resolves the DTO back to a deposit slip doc and reverts it

import frappe
from typing import Optional, Tuple

from .dto import DepositSlipDlqEventDTO
from ..dlq_common import find_publish_state_log, revert_workflow_state, log_dlq_event
from ...config import TOPIC_DEPOSIT_SLIP, TOPIC_DEPOSIT_SLIP_DLQ
from ...producer.deposit_slip.producer import CONSULTANCY_DOCTYPES, RESEARCH_DOCTYPES

# Deposit slip doc.name is set as both depositSlipRefNumFab and slipNumber on
# publish (kafka/producer/deposit_slip/{research,consultancy}/mapper.py), but
# the doctype itself isn't echoed back on the DLQ payload, so every known
# deposit-slip doctype is tried.
ALL_DEPOSIT_SLIP_DOCTYPES = RESEARCH_DOCTYPES + CONSULTANCY_DOCTYPES


class DepositSlipDlqMapper:

    @staticmethod
    def resolve_reference(dto: DepositSlipDlqEventDTO) -> Tuple[Optional[str], Optional[str]]:
        """Returns (reference_doctype, reference_name), trying doc.name across
        every known deposit-slip doctype."""
        ref_name = dto.deposit_slip_ref_num_fab or dto.slip_number
        if not ref_name:
            return None, None

        for doctype in ALL_DEPOSIT_SLIP_DOCTYPES:
            if frappe.db.exists(doctype, ref_name):
                return doctype, ref_name

        return None, None

    @classmethod
    def handle(cls, dto: DepositSlipDlqEventDTO) -> bool:
        reference_doctype, reference_name = cls.resolve_reference(dto)
        previous_state = None
        reverted = False

        if reference_doctype and reference_name:
            state_log = find_publish_state_log(reference_doctype, reference_name, TOPIC_DEPOSIT_SLIP)
            if state_log and state_log[0].previous_workflow_state:
                previous_state = state_log[0].previous_workflow_state
                revert_workflow_state(reference_doctype, reference_name, previous_state, state_log[0].name)
                reverted = True

        log_dlq_event(
            source_topic=TOPIC_DEPOSIT_SLIP_DLQ,
            event_type=dto.event_type or "DEPOSIT_SLIP",
            reference_doctype=reference_doctype,
            reference_name=reference_name,
            project_number=dto.project_number,
            previous_workflow_state=previous_state,
            reverted=reverted,
            raw_payload=dto.raw_payload,
        )
        return True
