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

    # Overhead fund projects (PDF, DPF) belong on the overhead topics, not this one —
    # Accounts has no project for them (see docs/pdf-project-implementation.md §5.4). No
    # overhead *batch* producer exists yet, so refuse loudly rather than publish rows that
    # would silently dead-letter. Reached only if a PO commit adjustment is ever raised on
    # an overhead project.
    from ..overhead import is_overhead_project

    overhead_rows = [i.projectNumber for i in items if is_overhead_project(getattr(i, "projectNumber", None))]
    if overhead_rows:
        message = (
            f"Batch contains overhead fund project(s) {sorted(set(overhead_rows))}, which must "
            "go to overhead-commit-batch-events. No overhead batch producer exists yet."
        )
        log_producer_event(
            "ACCOUNT_HEAD_COMMIT_BATCH", doc_name,
            TOPIC_COMMIT_BATCH, "VALIDATION_FAILED", message,
        )
        frappe.log_error(message, "Overhead Commit Batch - Unsupported")
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
