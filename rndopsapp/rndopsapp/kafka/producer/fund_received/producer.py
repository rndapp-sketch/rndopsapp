# Copyright (c) 2025, rndops and contributors
# Fund Received Producer - Publishes Fund Received events to Kafka

import frappe
from datetime import datetime

from .dto import FundReceivedDTO, FundReceivedEventDTO
from .mapper import FundReceivedMapper
from .validator import FundReceivedValidator, ValidationError
from ...config import TOPIC_FUND_RECEIVED, TOPIC_FUND_RECEIVED_DLQ, SCHEMA_VERSION_FUND_RECEIVED
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


class FundReceivedProducer:
    """
    Service layer for publishing Fund Received to Kafka.
    Uses DTO pattern for data transformation and validation.
    """

    TOPIC = TOPIC_FUND_RECEIVED
    DLQ_TOPIC = TOPIC_FUND_RECEIVED_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_FUND_RECEIVED

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Main entry point for publishing Fund Received to Kafka.

        Args:
            doc: Fund Received Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "FUND_RECEIVED",
                doc.name,
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "FUND_RECEIVED",
                doc.name,
                cls.TOPIC,
                "STARTED",
                "Beginning publish process"
            )

            # Step 1: Validate required fields on document
            if not doc.name:
                log_producer_event(
                    "FUND_RECEIVED",
                    doc.name or "unknown",
                    cls.TOPIC,
                    "FAILED",
                    "Missing doc name"
                )
                return False

            if not getattr(doc, 'prjreg_title', None):
                log_producer_event(
                    "FUND_RECEIVED",
                    doc.name,
                    cls.TOPIC,
                    "WARNING",
                    "prjreg_title is empty"
                )

            # Step 2: Map Frappe document to Event DTO
            event = FundReceivedMapper.map_to_event(doc)

            # Step 3: Validate DTO
            if validate:
                try:
                    FundReceivedValidator.validate_event(event, raise_exception=True)
                    log_producer_event(
                        "FUND_RECEIVED",
                        doc.name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "FUND_RECEIVED",
                            doc.name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    return False

            # Step 4: Convert DTO to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Step 5: Get partition key (use project number for ordering)
            project_number = event.data.projectNumber or doc.name

            # Step 6: Publish to Kafka
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=project_number
            )

            if result:
                log_producer_event(
                    "FUND_RECEIVED",
                    doc.name,
                    cls.TOPIC,
                    "SUCCESS",
                    f"Successfully published to Kafka | projectNumber={project_number}"
                )
            else:
                log_producer_event(
                    "FUND_RECEIVED",
                    doc.name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing fund received: {str(e)}"
            log_error(error_msg, "FUND_RECEIVED_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Fund Received Kafka Error")
            return False

    @classmethod
    def publish_with_dto(cls, dto: FundReceivedDTO, validate: bool = True) -> bool:
        """
        Publish using a pre-built DTO (useful for testing or custom scenarios).

        Args:
            dto: FundReceivedDTO instance
            validate: Whether to validate the DTO before publishing

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            return False

        try:
            if validate:
                try:
                    FundReceivedValidator.validate(dto, raise_exception=True)
                except ValidationError as ve:
                    log_error(f"Validation failed: {str(ve)}", "VALIDATION_ERROR")
                    return False

            # Build event envelope
            event = FundReceivedEventDTO(
                schemaVersion=cls.SCHEMA_VERSION,
                eventType="FUND_RECEIVED",
                timestamp=datetime.utcnow().isoformat(),
                data=dto
            )

            kafka_payload = event.to_kafka_payload()
            key = dto.projectNumber or dto.fundReceivedRefNumberFap or "unknown"

            return publish_message(cls.TOPIC, kafka_payload, key, cls.DLQ_TOPIC, key=key)

        except Exception as e:
            log_error(f"Error publishing DTO: {str(e)}", "FUND_RECEIVED_ERROR")
            return False

    @classmethod
    def dry_run(cls, doc) -> dict:
        """
        Perform a dry run without actually publishing to Kafka.

        Args:
            doc: Fund Received Frappe document

        Returns:
            dict: Contains validation results and payload preview
        """
        try:
            event = FundReceivedMapper.map_to_event(doc)
            validation_errors = FundReceivedValidator.validate_event(
                event,
                raise_exception=False
            )
            kafka_payload = event.to_kafka_payload()

            result = {
                "valid": len([e for e in validation_errors if "recommended" not in e.lower()]) == 0,
                "validation_errors": validation_errors,
                "dto": event.data.to_dict(),
                "kafka_payload": kafka_payload,
                "topic": cls.TOPIC,
                "dlq_topic": cls.DLQ_TOPIC
            }

            if result["valid"]:
                print(f"[OK] [FUND RECEIVED] Dry run successful")
            else:
                print(f"[ERROR] [FUND RECEIVED] Dry run found validation errors:")
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


def publish_fund_received(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish Fund Received.

    Args:
        doc: Fund Received Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors

    Returns:
        bool: True if successful, False otherwise
    """
    return FundReceivedProducer.publish(doc, validate=validate, log_errors=log_errors)
