# Copyright (c) 2026, rndops and contributors
# Loan Settlement Producer - Publishes Loan Settlement events to Kafka

import frappe

from .mapper import LoanSettlementMapper
from .validator import LoanSettlementValidator, ValidationError
from ...config import (
    TOPIC_LOAN_SETTLEMENT,
    TOPIC_LOAN_SETTLEMENT_DLQ,
    SCHEMA_VERSION_LOAN_SETTLEMENT,
)
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


class LoanSettlementProducer:
    """
    Publishes Loan Settlement events to the loan-settlement-events Kafka topic.

    Triggered when a Loan Settlement reaches the 'Processed' workflow state — i.e.
    after staff, RnD has supplied the settlement mode and remarks, so the payload is
    complete in a single message. See docs/loan-settlement-implementation.md §7.

    One message per settlement. The batch topic (loan-settlement-events-batch) is
    deliberately not used: it is all-or-nothing, so one stale loan reference would
    discard every other settlement sent alongside it.
    """

    TOPIC = TOPIC_LOAN_SETTLEMENT
    DLQ_TOPIC = TOPIC_LOAN_SETTLEMENT_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_LOAN_SETTLEMENT

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Publish a Loan Settlement event to Kafka.

        Args:
            doc: Loan Settlement Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "SKIPPED", "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "STARTED", "Beginning publish process"
            )

            if not doc.name:
                log_producer_event(
                    "LOAN_SETTLEMENT", doc.name or "unknown", cls.TOPIC, "FAILED", "Missing doc name"
                )
                return False

            event = LoanSettlementMapper.map_to_event(doc)

            if validate:
                try:
                    LoanSettlementValidator.validate_event(event, raise_exception=True)
                    log_producer_event(
                        "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "VALIDATED", "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "VALIDATION_FAILED", str(ve)
                        )
                    return False

            kafka_payload = event.to_kafka_payload()
            partition_key = event.data.projectNumber or doc.name

            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=partition_key,
            )

            if result:
                log_producer_event(
                    "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "SUCCESS",
                    f"Published | loanNumber={event.data.loanNumber} "
                    f"projectNumber={event.data.projectNumber} "
                    f"amount={event.data.settlementAmount} mode={event.data.settlementMode}"
                )
            else:
                log_producer_event(
                    "LOAN_SETTLEMENT", doc.name, cls.TOPIC, "FAILED", "publish_message returned False"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing loan settlement: {str(e)}"
            log_error(error_msg, "LOAN_SETTLEMENT_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Loan Settlement Kafka Error")
            return False


def publish_loan_settlement(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish a Loan Settlement event to Kafka.

    Args:
        doc: Loan Settlement Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log errors

    Returns:
        bool: True if successful, False otherwise
    """
    return LoanSettlementProducer.publish(doc, validate=validate, log_errors=log_errors)
