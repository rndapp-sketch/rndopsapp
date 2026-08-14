# Copyright (c) 2026, rndops and contributors
# Loan Request DLQ Consumer Mapper - resolves the DTO back to a Loan Request doc and reverts it

import frappe
from typing import Optional

from .dto import LoanRequestDlqEventDTO
from ..dlq_common import find_publish_state_log, revert_workflow_state, log_dlq_event
from ...config import TOPIC_LOAN_REQUEST, TOPIC_LOAN_REQUEST_DLQ

REFERENCE_DOCTYPE = "Loan Request"


class LoanRequestDlqMapper:

    @staticmethod
    def resolve_reference(dto: LoanRequestDlqEventDTO) -> Optional[str]:
        """
        Mirrors LoanRequestMapper.get_project_number (kafka/producer/loan_request/mapper.py):
        project_number is a Data field set directly on Loan Request.
        """
        if not dto.project_number:
            return None
        return frappe.db.get_value(
            REFERENCE_DOCTYPE, {"project_number": dto.project_number}, "name", order_by="creation desc"
        )

    @classmethod
    def handle(cls, dto: LoanRequestDlqEventDTO) -> bool:
        reference_name = cls.resolve_reference(dto)
        previous_state = None
        reverted = False

        if reference_name:
            state_log = find_publish_state_log(REFERENCE_DOCTYPE, reference_name, TOPIC_LOAN_REQUEST)
            if state_log and state_log[0].previous_workflow_state:
                previous_state = state_log[0].previous_workflow_state
                revert_workflow_state(REFERENCE_DOCTYPE, reference_name, previous_state, state_log[0].name)
                reverted = True

        log_dlq_event(
            source_topic=TOPIC_LOAN_REQUEST_DLQ,
            event_type=dto.event_type or "LOAN_REQUEST",
            reference_doctype=REFERENCE_DOCTYPE if reference_name else None,
            reference_name=reference_name,
            project_number=dto.project_number,
            previous_workflow_state=previous_state,
            reverted=reverted,
            raw_payload=dto.raw_payload,
        )
        return True
