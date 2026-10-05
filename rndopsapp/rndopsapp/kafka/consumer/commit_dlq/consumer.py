# Copyright (c) 2026, rndops and contributors
# Commit DLQ Consumer Handler - records account-head-commit-events-dlq
# failures and flips the matching "Kafka Commit Staging" row to FAILED.

import frappe

from .dto import CommitDlqEventDTO
from .mapper import CommitDlqMapper
from ...logs import log_consumer_event, log_error

TOPIC = "account-head-commit-events-dlq"


class CommitDlqConsumerHandler:

    @classmethod
    def handle(cls, message) -> bool:
        try:
            dto = CommitDlqEventDTO.from_kafka_message(message)
            identifier = dto.frap_app_id or dto.project_number or "unknown"

            log_consumer_event(
                "ACCOUNT_HEAD_COMMIT_DLQ", identifier, TOPIC, "RECEIVED",
                f"projectNumber={dto.project_number} accountHeadId={dto.account_head_id}"
            )

            result = CommitDlqMapper.handle(dto)
            frappe.db.commit()

            log_consumer_event(
                "ACCOUNT_HEAD_COMMIT_DLQ", identifier, TOPIC,
                "SUCCESS" if result else "FAILED"
            )
            return result

        except Exception as e:
            error_msg = f"Error processing account-head-commit-events-dlq message: {str(e)}"
            log_error(error_msg, "ACCOUNT_HEAD_COMMIT_DLQ_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Account Head Commit DLQ Consumer Error")
            return False


def handle_account_head_commit_dlq_error(message) -> bool:
    """Convenience function to handle an account-head-commit-events-dlq message."""
    return CommitDlqConsumerHandler.handle(message)
