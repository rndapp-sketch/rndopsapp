# Copyright (c) 2026, rndops and contributors
# Fund Received DLQ Consumer Mapper - resolves the DTO back to a Fund Received doc and reverts it

import frappe
from typing import Optional

from .dto import FundReceivedDlqEventDTO
from ..dlq_common import find_publish_state_log, revert_workflow_state, log_dlq_event
from ...config import TOPIC_FUND_RECEIVED, TOPIC_FUND_RECEIVED_DLQ

REFERENCE_DOCTYPE = "Fund Received"


class FundReceivedDlqMapper:

    @staticmethod
    def resolve_reference(dto: FundReceivedDlqEventDTO) -> Optional[str]:
        """
        fundReceivedRefNumberFap is set to doc.name on publish
        (kafka/producer/fund_received/producer.py), so it's an exact match.
        """
        ref = dto.fund_received_ref_number_fap
        if ref and frappe.db.exists(REFERENCE_DOCTYPE, ref):
            return ref
        return None

    @classmethod
    def handle(cls, dto: FundReceivedDlqEventDTO) -> bool:
        reference_name = cls.resolve_reference(dto)
        previous_state = None
        reverted = False

        if reference_name:
            state_log = find_publish_state_log(REFERENCE_DOCTYPE, reference_name, TOPIC_FUND_RECEIVED)
            if state_log and state_log[0].previous_workflow_state:
                previous_state = state_log[0].previous_workflow_state
                revert_workflow_state(REFERENCE_DOCTYPE, reference_name, previous_state, state_log[0].name)
                reverted = True

        log_dlq_event(
            source_topic=TOPIC_FUND_RECEIVED_DLQ,
            event_type=dto.event_type or "FUND_RECEIVED",
            reference_doctype=REFERENCE_DOCTYPE if reference_name else None,
            reference_name=reference_name,
            project_number=dto.project_number,
            previous_workflow_state=previous_state,
            reverted=reverted,
            raw_payload=dto.raw_payload,
        )
        return True
