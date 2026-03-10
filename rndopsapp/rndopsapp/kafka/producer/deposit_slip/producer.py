# Copyright (c) 2025, rndops and contributors
# Deposit Slip Producer - Main entry point for publishing Deposit Slip events to Kafka
# Routes to either Research or Consultancy publisher based on doctype

import frappe
from datetime import datetime

from .research import (
    ResearchDepositSlipMapper,
    ResearchDepositSlipValidator,
    ValidationError as ResearchValidationError,
)
from .consultancy import (
    ConsultancyDepositSlipMapper,
    ConsultancyDepositSlipValidator,
    ValidationError as ConsultancyValidationError,
)
from ...config import TOPIC_DEPOSIT_SLIP, TOPIC_DEPOSIT_SLIP_DLQ, SCHEMA_VERSION_DEPOSIT_SLIP
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


# Doctype categorization
CONSULTANCY_DOCTYPES = [
    "D Consultancy Deposit Slip",
    "E Non Routine Deposit Slip",
    "T Testing Deposit Slip",
    "Other Event Deposit Slip",
]

RESEARCH_DOCTYPES = [
    "Research Deposit Slip",
    "Research Consultancy Deposit Slip",
]


class DepositSlipProducer:
    """
    Main producer for Deposit Slip events.
    Routes to appropriate submodule (Research or Consultancy) based on doctype.
    """

    TOPIC = TOPIC_DEPOSIT_SLIP
    DLQ_TOPIC = TOPIC_DEPOSIT_SLIP_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_DEPOSIT_SLIP

    @classmethod
    def is_consultancy_doctype(cls, doctype: str) -> bool:
        """Check if doctype is a Consultancy type."""
        return doctype in CONSULTANCY_DOCTYPES

    @classmethod
    def is_research_doctype(cls, doctype: str) -> bool:
        """Check if doctype is a Research type (default)."""
        return doctype in RESEARCH_DOCTYPES or doctype not in CONSULTANCY_DOCTYPES

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Main entry point - routes to appropriate publisher based on doctype.

        Args:
            doc: Deposit Slip Frappe document
            validate: Whether to validate before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successful, False otherwise
        """
        doctype = getattr(doc, 'doctype', '')

        if cls.is_consultancy_doctype(doctype):
            return cls.publish_consultancy(doc, validate=validate, log_errors=log_errors)
        else:
            return cls.publish_research(doc, validate=validate, log_errors=log_errors)

    @classmethod
    def publish_research(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Publish Research Deposit Slip to Kafka.

        Args:
            doc: Research Deposit Slip Frappe document
            validate: Whether to validate before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successful, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "DEPOSIT_SLIP_RESEARCH",
                doc.name,
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "DEPOSIT_SLIP_RESEARCH",
                doc.name,
                cls.TOPIC,
                "STARTED",
                "Beginning publish process"
            )

            # Map to event DTO
            event = ResearchDepositSlipMapper.map_to_event(doc)

            # Validate
            if validate:
                try:
                    # Validate the DTO (event.data), not the event envelope
                    ResearchDepositSlipValidator.validate(event.data, raise_exception=True)
                    log_producer_event(
                        "DEPOSIT_SLIP_RESEARCH",
                        doc.name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ResearchValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "DEPOSIT_SLIP_RESEARCH",
                            doc.name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    return False

            # Convert to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Get partition key
            project_number = event.data.projectNumber or doc.name

            # Publish
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=project_number
            )

            if result:
                log_producer_event(
                    "DEPOSIT_SLIP_RESEARCH",
                    doc.name,
                    cls.TOPIC,
                    "SUCCESS",
                    f"Successfully published | projectNumber={project_number}"
                )
            else:
                log_producer_event(
                    "DEPOSIT_SLIP_RESEARCH",
                    doc.name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing research deposit slip: {str(e)}"
            log_error(error_msg, "DEPOSIT_SLIP_RESEARCH_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Deposit Slip Kafka Error")
            return False

    @classmethod
    def publish_consultancy(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Publish Consultancy Deposit Slip to Kafka.

        Args:
            doc: Consultancy Deposit Slip Frappe document (D, E, T, Other Event)
            validate: Whether to validate before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successful, False otherwise
        """
        doctype = doc.doctype
        category = ConsultancyDepositSlipMapper.get_category(doctype)

        if not is_kafka_available():
            log_producer_event(
                f"DEPOSIT_SLIP_{category}",
                doc.name,
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                f"DEPOSIT_SLIP_{category}",
                doc.name,
                cls.TOPIC,
                "STARTED",
                f"Beginning publish process | doctype={doctype}"
            )

            # Map to event DTO
            event = ConsultancyDepositSlipMapper.map_to_event(doc)

            # Validate
            if validate:
                try:
                    # Validate the DTO (event.data), not the event envelope
                    ConsultancyDepositSlipValidator.validate(event.data, raise_exception=True)
                    log_producer_event(
                        f"DEPOSIT_SLIP_{category}",
                        doc.name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ConsultancyValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            f"DEPOSIT_SLIP_{category}",
                            doc.name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    return False

            # Convert to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Get partition key
            project_number = event.data.projectNumber or doc.name

            # Publish
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=project_number
            )

            if result:
                log_producer_event(
                    f"DEPOSIT_SLIP_{category}",
                    doc.name,
                    cls.TOPIC,
                    "SUCCESS",
                    f"Successfully published | projectNumber={project_number}"
                )
            else:
                log_producer_event(
                    f"DEPOSIT_SLIP_{category}",
                    doc.name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing consultancy deposit slip: {str(e)}"
            log_error(error_msg, f"DEPOSIT_SLIP_{category}_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Deposit Slip Kafka Error")
            return False

    @classmethod
    def dry_run(cls, doc) -> dict:
        """
        Perform a dry run without actually publishing to Kafka.

        Args:
            doc: Deposit Slip Frappe document

        Returns:
            dict: Contains validation results and payload preview
        """
        doctype = getattr(doc, 'doctype', '')

        try:
            if cls.is_consultancy_doctype(doctype):
                event = ConsultancyDepositSlipMapper.map_to_event(doc)
                # Validate the DTO (event.data), not the event envelope
                validation_errors = ConsultancyDepositSlipValidator.validate(
                    event.data, raise_exception=False
                )
            else:
                event = ResearchDepositSlipMapper.map_to_event(doc)
                # Validate the DTO (event.data), not the event envelope
                validation_errors = ResearchDepositSlipValidator.validate(
                    event.data, raise_exception=False
                )

            kafka_payload = event.to_kafka_payload()

            result = {
                "valid": len(validation_errors) == 0,
                "validation_errors": validation_errors,
                "dto": event.data.to_dict(),
                "kafka_payload": kafka_payload,
                "topic": cls.TOPIC,
                "dlq_topic": cls.DLQ_TOPIC,
                "doctype": doctype,
                "category": event.eventType
            }

            if result["valid"]:
                print(f"[OK] [DEPOSIT SLIP] Dry run successful")
            else:
                print(f"[ERROR] [DEPOSIT SLIP] Dry run found validation errors:")
                for error in validation_errors:
                    print(f"   - {error}")

            return result

        except Exception as e:
            error_msg = f"Error during dry run: {str(e)}"
            log_error(error_msg, "DRY_RUN_ERROR")
            return {
                "valid": False,
                "error": error_msg,
                "validation_errors": [error_msg]
            }


def publish_deposit_slip(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish Deposit Slip.
    Routes to appropriate publisher based on doctype.

    Args:
        doc: Deposit Slip Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors

    Returns:
        bool: True if successful, False otherwise
    """
    return DepositSlipProducer.publish(doc, validate=validate, log_errors=log_errors)
