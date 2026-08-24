# Copyright (c) 2026, rndops and contributors
# Loan Request DLQ Consumer Handler - records loan-request-event-dlq failures
# and reverts the Loan Request document's workflow_state.

import frappe

from .dto import LoanRequestDlqEventDTO
from .mapper import LoanRequestDlqMapper
from ...logs import log_consumer_event, log_error

TOPIC = "loan-request-event-dlq"


class LoanRequestDlqConsumerHandler:

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = LoanRequestDlqEventDTO.from_kafka_message(message)
            identifier = dto.project_number or "unknown"

            log_consumer_event(
                "LOAN_REQUEST_DLQ", identifier, TOPIC, "RECEIVED",
                f"loanType={dto.loan_type} loanAmount={dto.loan_amount}"
            )

            result = LoanRequestDlqMapper.handle(dto)
            frappe.db.commit()

            log_consumer_event(
                "LOAN_REQUEST_DLQ", identifier, TOPIC,
                "SUCCESS" if result else "FAILED"
            )
            return result

        except Exception as e:
            error_msg = f"Error processing loan-request-event-dlq message: {str(e)}"
            log_error(error_msg, "LOAN_REQUEST_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Loan Request DLQ Consumer Error")
            return False


def handle_loan_request_dlq_error(message) -> bool:
    """Convenience function to handle a loan-request-event-dlq message."""
    return LoanRequestDlqConsumerHandler.handle(message)
