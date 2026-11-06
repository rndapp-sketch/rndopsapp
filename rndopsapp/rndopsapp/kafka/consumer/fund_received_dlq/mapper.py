# Copyright (c) 2026, rndops and contributors
# Fund Received DLQ Consumer Mapper - resolves the DTO back to a Fund Received doc and reverts it

import frappe
from typing import Optional

from .dto import FundReceivedDlqEventDTO
from ..dlq_common import find_publish_state_log, revert_workflow_state, log_dlq_event
from ..fund_received.mapper import FundReceivedConsumerMapper
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

                # The DLQ can be processed long after the failed publish (hours,
                # in practice — see the consumer's heartbeat-restart churn), so
                # the document may have legitimately moved forward in the
                # meantime via a later, successfully-processed inbound update.
                # Reusing the main consumer's priority table (never move the
                # workflow backward) stops this revert from clobbering that
                # forward progress — same guard class as
                # FundReceivedConsumerMapper.apply_updates, just applied here too.
                current_state = frappe.db.get_value(REFERENCE_DOCTYPE, reference_name, 'workflow_state') or ''
                state_priority = FundReceivedConsumerMapper._STATE_PRIORITY
                current_priority = state_priority.get(current_state, 0)
                previous_priority = state_priority.get(previous_state, 0)

                if current_priority <= previous_priority:
                    revert_workflow_state(REFERENCE_DOCTYPE, reference_name, previous_state, state_log[0].name)
                    reverted = True
                else:
                    frappe.logger().warning(
                        f"[FundReceivedDlqMapper] Skipped revert for {reference_name}: "
                        f"current='{current_state}' (priority {current_priority}) is already ahead of "
                        f"revert target='{previous_state}' (priority {previous_priority})."
                    )

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
