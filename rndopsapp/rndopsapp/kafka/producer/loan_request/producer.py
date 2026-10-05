# Copyright (c) 2026, rndops and contributors
# Loan Request Producer - Publishes Loan Request approval events to Kafka

import frappe
from datetime import datetime

from .dto import LoanRequestDTO, LoanRequestEventDTO
from .mapper import LoanRequestMapper
from .validator import LoanRequestValidator, ValidationError
from ...config import TOPIC_LOAN_REQUEST, TOPIC_LOAN_REQUEST_DLQ, SCHEMA_VERSION_LOAN_REQUEST
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


class LoanRequestProducer:
    """
    Publishes Loan Request approval events to the loan-request-event Kafka topic.
    Triggered when a Loan Request reaches the 'Approved' workflow state.
    """

    TOPIC = TOPIC_LOAN_REQUEST
    DLQ_TOPIC = TOPIC_LOAN_REQUEST_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_LOAN_REQUEST

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Publish a Loan Request approval event to Kafka.

        Args:
            doc: Loan Request Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "LOAN_REQUEST", doc.name, cls.TOPIC, "SKIPPED", "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "LOAN_REQUEST", doc.name, cls.TOPIC, "STARTED", "Beginning publish process"
            )

            if not doc.name:
                log_producer_event(
                    "LOAN_REQUEST", doc.name or "unknown", cls.TOPIC, "FAILED", "Missing doc name"
                )
                return False

            # Map document to event DTO
            event = LoanRequestMapper.map_to_event(doc)

            # Validate DTO
            if validate:
                try:
                    LoanRequestValidator.validate_event(event, raise_exception=True)
                    log_producer_event(
                        "LOAN_REQUEST", doc.name, cls.TOPIC, "VALIDATED", "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "LOAN_REQUEST", doc.name, cls.TOPIC, "VALIDATION_FAILED", str(ve)
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
                    "LOAN_REQUEST", doc.name, cls.TOPIC, "SUCCESS",
                    f"Published | projectNumber={event.data.projectNumber} loanType={event.data.loanType} amount={event.data.loanAmount}"
                )
            else:
                log_producer_event(
                    "LOAN_REQUEST", doc.name, cls.TOPIC, "FAILED", "publish_message returned False"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing loan request: {str(e)}"
            log_error(error_msg, "LOAN_REQUEST_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Loan Request Kafka Error")
            return False


def publish_loan_request(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish a Loan Request approval event to Kafka.

    Args:
        doc: Loan Request Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log errors

    Returns:
        bool: True if successful, False otherwise
    """
    return LoanRequestProducer.publish(doc, validate=validate, log_errors=log_errors)
