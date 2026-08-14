# Copyright (c) 2026, rndops and contributors
# Payment DLQ Consumer Handler - records account-head-payment-events-dlq failures
# so they can be surfaced to the frontend instead of only living in logs/Mattermost.

import frappe

from .dto import PaymentDlqErrorDTO
from .mapper import PaymentDlqErrorMapper
from ...logs import log_consumer_event, log_error


class PaymentDlqConsumerHandler:
    """
    Handler for messages landing on account-head-payment-events-dlq.

    This is not a retry path — by the time a message reaches the DLQ, the
    external ledger microservice has already given up on it. The only job
    here is to make the failure visible: persist it as a "Kafka Payment DLQ
    Log" record (best-effort linked back to the AccountHeadPayment doc) so
    commitPayment.get_account_head_payment_dlq_errors can return it to the
    frontend that submitted the payment.
    """

    TOPIC = "account-head-payment-events-dlq"

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = PaymentDlqErrorDTO.from_kafka_message(message)

            identifier = dto.identifier_raw or f"projectNumber={dto.project_number},accountHeadId={dto.account_head_id}"

            log_consumer_event(
                "ACCOUNT_HEAD_PAYMENT_DLQ",
                identifier,
                cls.TOPIC,
                "RECEIVED",
                f"errorType={dto.error_type} | error={dto.error_message}"
            )

            reference_name = PaymentDlqErrorMapper.resolve_reference(dto)

            PaymentDlqErrorMapper.save_error(dto, reference_name)
            PaymentDlqErrorMapper.revert_payment_status(reference_name)
            frappe.db.commit()

            log_consumer_event(
                "ACCOUNT_HEAD_PAYMENT_DLQ",
                reference_name or identifier,
                cls.TOPIC,
                "SUCCESS",
                "Recorded DLQ error for frontend polling"
            )

            return True

        except Exception as e:
            error_msg = f"Error processing account-head-payment DLQ message: {str(e)}"
            log_error(error_msg, "ACCOUNT_HEAD_PAYMENT_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Kafka Payment DLQ Consumer Error")
            return False


def handle_account_head_payment_dlq_error(message) -> bool:
    """Convenience function to handle an account-head-payment-events-dlq message."""
    return PaymentDlqConsumerHandler.handle(message)
