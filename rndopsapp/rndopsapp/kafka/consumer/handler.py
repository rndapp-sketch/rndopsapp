# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Master Handler - Routes messages to topic-specific handlers

import frappe
from .fund_received import handle_fund_received_update
from .deposit_slip import handle_deposit_slip_update
from .payment_dlq import handle_account_head_payment_dlq_error
from .sanction_dlq.consumer import handle_fund_sanction_dlq_error
from .fund_received_dlq.consumer import handle_fund_received_dlq_error
from .deposit_slip_dlq.consumer import handle_deposit_slip_dlq_error
from .commit_dlq.consumer import handle_account_head_commit_dlq_error
from .loan_request_dlq.consumer import handle_loan_request_dlq_error
from ..config import (
    TOPIC_ACCOUNTS_FUND_RECEIVED,
    TOPIC_DEPOSIT_SLIP_UPDATE,
    TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ,
    TOPIC_SANCTION_DLQ,
    TOPIC_FUND_RECEIVED_DLQ,
    TOPIC_DEPOSIT_SLIP_DLQ,
    TOPIC_ACCOUNT_HEAD_COMMIT_DLQ,
    TOPIC_LOAN_REQUEST_DLQ,
)


# Topic to Handler Mapping
TOPIC_HANDLERS = {
    TOPIC_ACCOUNTS_FUND_RECEIVED: handle_fund_received_update,
    TOPIC_DEPOSIT_SLIP_UPDATE: handle_deposit_slip_update,
    TOPIC_ACCOUNT_HEAD_PAYMENT_DLQ: handle_account_head_payment_dlq_error,
    TOPIC_SANCTION_DLQ: handle_fund_sanction_dlq_error,
    TOPIC_FUND_RECEIVED_DLQ: handle_fund_received_dlq_error,
    TOPIC_DEPOSIT_SLIP_DLQ: handle_deposit_slip_dlq_error,
    TOPIC_ACCOUNT_HEAD_COMMIT_DLQ: handle_account_head_commit_dlq_error,
    TOPIC_LOAN_REQUEST_DLQ: handle_loan_request_dlq_error,
}


def process_message(topic: str, message_payload: dict) -> bool:
    """
    Routes a message to its appropriate handler based on topic.

    Args:
        topic: The Kafka topic the message came from
        message_payload: The deserialized message payload (dict)

    Returns:
        bool: True if processed successfully, False otherwise
    """
    handler = TOPIC_HANDLERS.get(topic)
    if handler:
        try:
            return handler(message_payload)
        except Exception as e:
            frappe.log_error(
                f"Error in handler for topic {topic}: {str(e)}",
                "Kafka Consumer Handler Execution Error"
            )
            return False
    else:
        # This shouldn't happen if topics are correctly subscribed
        frappe.log_error(
            f"No handler found for topic: {topic}",
            "Kafka Consumer Unknown Topic"
        )
        return False
