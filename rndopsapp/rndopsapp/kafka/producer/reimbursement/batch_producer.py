# Copyright (c) 2026, rndops and contributors
# Batch producer for Account Head Commit batch events

import frappe
from typing import List, Optional

from .batch_dto import AccountHeadCommitBatchItemDTO, AccountHeadCommitBatchEvent
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error

TOPIC_COMMIT_BATCH     = "account-head-commit-batch-events"
TOPIC_COMMIT_BATCH_DLQ = "account-head-commit-batch-events-dlq"


def publish_commit_batch(
    doc_name: str,
    items: List[AccountHeadCommitBatchItemDTO],
    partition_key: Optional[str] = None,
) -> bool:
    """
    Publish a list of AccountHeadCommitBatchItemDTO items as a single batch
    Kafka event to ``account-head-commit-batch-events``.

    Args:
        doc_name:      Frappe document name used for logging.
        items:         Commit rows to include in the batch.
        partition_key: Kafka partition key (defaults to doc_name).

    Returns:
        True if the message was delivered, False otherwise.
    """
    if not is_kafka_available():
        log_producer_event(
            "ACCOUNT_HEAD_COMMIT_BATCH", doc_name,
            TOPIC_COMMIT_BATCH, "SKIPPED", "Kafka not available",
        )
        return False

    if not items:
        log_producer_event(
            "ACCOUNT_HEAD_COMMIT_BATCH", doc_name,
            TOPIC_COMMIT_BATCH, "SKIPPED", "Empty batch — nothing to publish",
        )
        return False

    try:
        log_producer_event(
            "ACCOUNT_HEAD_COMMIT_BATCH", doc_name,
            TOPIC_COMMIT_BATCH, "STARTED", f"{len(items)} item(s)",
        )

        event         = AccountHeadCommitBatchEvent(items=items)
        kafka_payload = event.to_kafka_payload()

        result = publish_message(
            TOPIC_COMMIT_BATCH,
            kafka_payload,
            doc_name,
            TOPIC_COMMIT_BATCH_DLQ,
            key=partition_key or doc_name,
        )

        log_producer_event(
            "ACCOUNT_HEAD_COMMIT_BATCH", doc_name,
            TOPIC_COMMIT_BATCH,
            "SUCCESS" if result else "FAILED",
            f"{len(items)} item(s)",
        )
        return result

    except Exception as e:
        log_error(f"Error publishing batch commit: {e}", "ACCOUNT_HEAD_COMMIT_BATCH_ERROR", exc_info=True)
        frappe.log_error(str(e), "Account Head Commit Batch Kafka Error")
        return False
