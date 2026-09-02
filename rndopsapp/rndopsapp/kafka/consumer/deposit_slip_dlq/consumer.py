# Copyright (c) 2026, rndops and contributors
# Deposit Slip DLQ Consumer Handler - records deposit-slip-events-dlq failures
# and reverts the source deposit slip document's workflow_state.

import frappe

from .dto import DepositSlipDlqEventDTO
from .mapper import DepositSlipDlqMapper
from ...logs import log_consumer_event, log_error

TOPIC = "deposit-slip-events-dlq"


class DepositSlipDlqConsumerHandler:

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = DepositSlipDlqEventDTO.from_kafka_message(message)
            identifier = dto.deposit_slip_ref_num_fab or dto.slip_number or dto.project_number or "unknown"

            log_consumer_event(
                "DEPOSIT_SLIP_DLQ", identifier, TOPIC, "RECEIVED",
                f"category={dto.category} projectNumber={dto.project_number}"
            )

            result = DepositSlipDlqMapper.handle(dto)
            frappe.db.commit()

            log_consumer_event(
                "DEPOSIT_SLIP_DLQ", identifier, TOPIC,
                "SUCCESS" if result else "FAILED"
            )
            return result

        except Exception as e:
            error_msg = f"Error processing deposit-slip-events-dlq message: {str(e)}"
            log_error(error_msg, "DEPOSIT_SLIP_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Deposit Slip DLQ Consumer Error")
            return False


def handle_deposit_slip_dlq_error(message) -> bool:
    """Convenience function to handle a deposit-slip-events-dlq message."""
    return DepositSlipDlqConsumerHandler.handle(message)
