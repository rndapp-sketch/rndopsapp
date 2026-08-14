# Copyright (c) 2026, rndops and contributors
# Sanction DLQ Consumer Mapper - resolves the DTO back to a Fund Sanction doc and reverts it

import frappe
from typing import Optional

from .dto import SanctionDlqEventDTO
from ..dlq_common import find_publish_state_log, revert_workflow_state, log_dlq_event
from ...config import TOPIC_SANCTION, TOPIC_SANCTION_DLQ

REFERENCE_DOCTYPE = "Fund Sanction"


class SanctionDlqMapper:

    @staticmethod
    def resolve_reference(dto: SanctionDlqEventDTO) -> Optional[str]:
        """
        Fund Sanction has no single reliable natural key on this payload
        (sanctionLetterNo is free text on some records) — mirrors
        FundSanctionMapper.map_to_event (kafka/producer/fund_sanction/mapper.py),
        which sources projectNumber from refnum_prj_num, falling back to
        project_proposal.
        """
        if not dto.project_number:
            return None

        return frappe.db.get_value(
            "Fund Sanction", {"refnum_prj_num": dto.project_number}, "name", order_by="creation desc"
        ) or frappe.db.get_value(
            "Fund Sanction", {"project_proposal": dto.project_number}, "name", order_by="creation desc"
        )

    @classmethod
    def handle(cls, dto: SanctionDlqEventDTO) -> bool:
        reference_name = cls.resolve_reference(dto)
        previous_state = None
        reverted = False

        if reference_name:
            state_log = find_publish_state_log(REFERENCE_DOCTYPE, reference_name, TOPIC_SANCTION)
            if state_log and state_log[0].previous_workflow_state:
                previous_state = state_log[0].previous_workflow_state
                revert_workflow_state(REFERENCE_DOCTYPE, reference_name, previous_state, state_log[0].name)
                reverted = True

        log_dlq_event(
            source_topic=TOPIC_SANCTION_DLQ,
            event_type=dto.event_type or "FUND_SANCTION",
            reference_doctype=REFERENCE_DOCTYPE if reference_name else None,
            reference_name=reference_name,
            project_number=dto.project_number,
            previous_workflow_state=previous_state,
            reverted=reverted,
            raw_payload=dto.raw_payload,
        )
        return True
