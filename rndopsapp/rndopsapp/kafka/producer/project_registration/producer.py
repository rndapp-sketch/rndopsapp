# Copyright (c) 2025, rndops and contributors
# Project Registration Producer - Publishes Project Registration events to Kafka

import json
import frappe
from datetime import datetime

from .dto import ProjectDataDTO, ProjectEventDTO
from .mapper import ProjectRegistrationMapper
from .validator import ProjectRegistrationValidator, ValidationError
from ...config import TOPIC_PROJECT, TOPIC_PROJECT_DLQ, SCHEMA_VERSION_PROJECT
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


class ProjectRegistrationProducer:
    """
    Service layer for publishing Project Registration to Kafka.
    Uses DTO pattern for data transformation and validation.
    """

    TOPIC = TOPIC_PROJECT
    DLQ_TOPIC = TOPIC_PROJECT_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_PROJECT

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Main entry point for publishing Project Registration to Kafka.

        Args:
            doc: Project Registration Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "PROJECT_REGISTRATION",
                doc.name,
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "PROJECT_REGISTRATION",
                doc.name,
                cls.TOPIC,
                "STARTED",
                "Beginning publish process"
            )

            # Step 1: Validate required fields on document
            required_fields = ['name', 'pi_employee_id', 'project_type']
            for field in required_fields:
                if not getattr(doc, field, None):
                    error_msg = f"Missing required field: {field}"
                    log_producer_event(
                        "PROJECT_REGISTRATION",
                        doc.name,
                        cls.TOPIC,
                        "FAILED",
                        error_msg
                    )
                    return False

            # Step 2: Map Frappe document to Event DTO
            event = ProjectRegistrationMapper.map_to_event(doc)

            # Step 3: Validate DTO
            if validate:
                try:
                    ProjectRegistrationValidator.validate_event(event, raise_exception=True)
                    log_producer_event(
                        "PROJECT_REGISTRATION",
                        doc.name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "PROJECT_REGISTRATION",
                            doc.name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    return False

            # Step 4: Convert DTO to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Step 5: Publish to Kafka
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=doc.name  # Use project number as partition key
            )

            if result:
                log_producer_event(
                    "PROJECT_REGISTRATION",
                    doc.name,
                    cls.TOPIC,
                    "SUCCESS",
                    "Successfully published to Kafka"
                )
            else:
                log_producer_event(
                    "PROJECT_REGISTRATION",
                    doc.name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing project registration: {str(e)}"
            log_error(error_msg, "PROJECT_REGISTRATION_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Project Registration Kafka Error")
            return False

    @classmethod
    def publish_with_dto(cls, dto: ProjectDataDTO, validate: bool = True) -> bool:
        """
        Publish using a pre-built DTO (useful for testing or custom scenarios).

        Args:
            dto: ProjectDataDTO instance
            validate: Whether to validate the DTO before publishing

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            return False

        try:
            if validate:
                try:
                    ProjectRegistrationValidator.validate(dto, raise_exception=True)
                except ValidationError as ve:
                    log_error(f"Validation failed: {str(ve)}", "VALIDATION_ERROR")
                    return False

            # Build event envelope
            event = ProjectEventDTO(
                schemaVersion=cls.SCHEMA_VERSION,
                eventType="PROJECT_REGISTRATION",
                timestamp=datetime.utcnow(),
                data=dto
            )

            kafka_payload = event.to_kafka_payload()
            key = dto.projectNumber or "unknown"

            return publish_message(cls.TOPIC, kafka_payload, key, cls.DLQ_TOPIC, key=key)

        except Exception as e:
            log_error(f"Error publishing DTO: {str(e)}", "PROJECT_REGISTRATION_ERROR")
            return False

    @classmethod
    def dry_run(cls, doc) -> dict:
        """
        Perform a dry run without actually publishing to Kafka.
        Useful for testing and debugging.

        Args:
            doc: Project Registration Frappe document

        Returns:
            dict: Contains validation results and payload preview
        """
        try:
            event = ProjectRegistrationMapper.map_to_event(doc)
            validation_errors = ProjectRegistrationValidator.validate_event(
                event,
                raise_exception=False
            )
            kafka_payload = event.to_kafka_payload()

            result = {
                "valid": len(validation_errors) == 0,
                "validation_errors": validation_errors,
                "dto": event.data.model_dump(mode="json"),
                "kafka_payload": kafka_payload,
                "topic": cls.TOPIC,
                "dlq_topic": cls.DLQ_TOPIC
            }

            if result["valid"]:
                print(f"[OK] [PROJECT REGISTRATION] Dry run successful - No validation errors")
            else:
                print(f"[ERROR] [PROJECT REGISTRATION] Dry run found {len(validation_errors)} validation errors:")
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


def publish_project_registration(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish Project Registration.

    Args:
        doc: Project Registration Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors

    Returns:
        bool: True if successful, False otherwise
    """
    return ProjectRegistrationProducer.publish(doc, validate=validate, log_errors=log_errors)
