# Copyright (c) 2026, rndops and contributors
# Sanction DLQ Consumer Handler - records fund-sanction-events-dlq failures and
# reverts the Fund Sanction document's workflow_state.

import frappe

from .dto import SanctionDlqEventDTO
from .mapper import SanctionDlqMapper
from ...logs import log_consumer_event, log_error

TOPIC = "fund-sanction-events-dlq"


class SanctionDlqConsumerHandler:

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = SanctionDlqEventDTO.from_kafka_message(message)
            identifier = dto.project_number or "unknown"

            log_consumer_event(
                "FUND_SANCTION_DLQ", identifier, TOPIC, "RECEIVED",
                f"sanctionLetterNo={dto.sanction_letter_no}"
            )

            result = SanctionDlqMapper.handle(dto)
            frappe.db.commit()

            log_consumer_event(
                "FUND_SANCTION_DLQ", identifier, TOPIC,
                "SUCCESS" if result else "FAILED"
            )
            return result

        except Exception as e:
            error_msg = f"Error processing fund-sanction-events-dlq message: {str(e)}"
            log_error(error_msg, "FUND_SANCTION_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Fund Sanction DLQ Consumer Error")
            return False


def handle_fund_sanction_dlq_error(message) -> bool:
    """Convenience function to handle a fund-sanction-events-dlq message."""
    return SanctionDlqConsumerHandler.handle(message)
