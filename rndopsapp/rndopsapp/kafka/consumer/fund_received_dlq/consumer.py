# Copyright (c) 2026, rndops and contributors
# Fund Received DLQ Consumer Handler - records fund-received-events-dlq failures
# and reverts the Fund Received document's workflow_state.

import frappe

from .dto import FundReceivedDlqEventDTO
from .mapper import FundReceivedDlqMapper
from ...logs import log_consumer_event, log_error

TOPIC = "fund-received-events-dlq"


class FundReceivedDlqConsumerHandler:

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = FundReceivedDlqEventDTO.from_kafka_message(message)
            identifier = dto.fund_received_ref_number_fap or dto.project_number or "unknown"

            log_consumer_event(
                "FUND_RECEIVED_DLQ", identifier, TOPIC, "RECEIVED",
                f"projectNumber={dto.project_number}"
            )

            result = FundReceivedDlqMapper.handle(dto)
            frappe.db.commit()

            log_consumer_event(
                "FUND_RECEIVED_DLQ", identifier, TOPIC,
                "SUCCESS" if result else "FAILED"
            )
            return result

        except Exception as e:
            error_msg = f"Error processing fund-received-events-dlq message: {str(e)}"
            log_error(error_msg, "FUND_RECEIVED_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Fund Received DLQ Consumer Error")
            return False


def handle_fund_received_dlq_error(message) -> bool:
    """Convenience function to handle a fund-received-events-dlq message."""
    return FundReceivedDlqConsumerHandler.handle(message)
