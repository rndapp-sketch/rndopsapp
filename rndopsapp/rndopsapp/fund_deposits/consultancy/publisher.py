# Copyright (c) 2025, rndops and contributors
# Publisher Service for Consultancy Deposit Slip
# Supports: D Consultancy, E Non Routine, T Testing, Other Event

import json
import frappe
from datetime import datetime
from .dto import ConsultancyDepositSlipDTO
from .mapper import ConsultancyDepositSlipMapper
from .validator import ConsultancyDepositSlipValidator, ValidationError


class ConsultancyDepositSlipPublisher:
    """
    Service layer for publishing Consultancy Deposit Slip to Kafka.
    Supports multiple categories: D, E, T, and Other Event.
    """

    TOPIC = 'deposit-slip-events'
    DLQ_TOPIC = 'deposit-slip-events-dlq'
    SCHEMA_VERSION = "1.0"

    @staticmethod
    def publish_message(topic: str, payload: dict, key: str, dlq_topic: str) -> bool:
        """
        Publish message to Kafka topic.
        Wrapper around the existing publish_message function.

        Args:
            topic: Kafka topic name
            payload: Message payload (dict)
            key: Message key
            dlq_topic: Dead letter queue topic

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from rndopsapp.rndopsapp.kafka_sync import publish_message as kafka_publish
            return kafka_publish(topic, payload, key, dlq_topic)
        except Exception as e:
            frappe.log_error(f"Failed to publish message: {str(e)}", "Kafka Publish Error")
            print(f"[ERROR] [KAFKA] Failed to publish message: {str(e)}")
            return False

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True) -> bool:
        """
        Main entry point for publishing Consultancy Deposit Slip to Kafka.
        Auto-detects category from doctype.

        Args:
            doc: Consultancy Deposit Slip Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        try:
            category = ConsultancyDepositSlipMapper.get_category(doc)
            print(f"[CONSULTANCY PUBLISHER] Starting publish for: {doc.name} (Category: {category})")

            # Step 1: Map Frappe document to DTO
            print(f"[CONSULTANCY PUBLISHER] Mapping document to DTO...")
            dto = ConsultancyDepositSlipMapper.map_to_dto(doc)

            # Step 2: Validate DTO
            if validate:
                print(f"[CONSULTANCY PUBLISHER] Validating DTO...")
                try:
                    ConsultancyDepositSlipValidator.validate(dto, raise_exception=True)
                    print(f"[CONSULTANCY PUBLISHER] Validation passed")
                except ValidationError as ve:
                    if log_errors:
                        error_msg = f"Validation failed for {doc.name}: {str(ve)}"
                        frappe.log_error(error_msg, "Consultancy Deposit Slip Validation Error")
                        print(f"[ERROR] [CONSULTANCY PUBLISHER] {error_msg}")
                    return False

            # Step 3: Convert DTO to Kafka payload
            print(f"[CONSULTANCY PUBLISHER] Converting DTO to Kafka payload...")
            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)

            # Step 4: Log payload for debugging
            print(f"[CONSULTANCY PUBLISHER] Sending to topic: {cls.TOPIC}")
            print(f"[CONSULTANCY PUBLISHER] Event type: {kafka_payload['eventType']}")
            print(f"[CONSULTANCY PUBLISHER] Payload preview:")
            print(json.dumps(kafka_payload, indent=2, default=str))

            # Step 5: Publish to Kafka
            print(f"[CONSULTANCY PUBLISHER] Publishing to Kafka...")
            result = cls.publish_message(cls.TOPIC, kafka_payload, doc.name, cls.DLQ_TOPIC)

            if result:
                print(f"[OK] [CONSULTANCY PUBLISHER] Successfully published {doc.name} to Kafka")
            else:
                print(f"[ERROR] [CONSULTANCY PUBLISHER] Failed to publish {doc.name} to Kafka")

            return result

        except Exception as e:
            error_msg = f"Error publishing consultancy deposit slip {doc.name}: {str(e)}"
            frappe.log_error(error_msg, "Consultancy Deposit Slip Publisher Error")
            print(f"[ERROR] [CONSULTANCY PUBLISHER] {error_msg}")
            return False

    @classmethod
    def publish_with_dto(cls, dto: ConsultancyDepositSlipDTO, validate: bool = True) -> bool:
        """
        Publish using a pre-built DTO (useful for testing or custom scenarios).

        Args:
            dto: ConsultancyDepositSlipDTO instance
            validate: Whether to validate the DTO before publishing

        Returns:
            bool: True if successfully published, False otherwise
        """
        try:
            print(f"[CONSULTANCY PUBLISHER] Publishing with custom DTO (Category: {dto.category})...")

            if validate:
                print(f"[CONSULTANCY PUBLISHER] Validating DTO...")
                try:
                    ConsultancyDepositSlipValidator.validate(dto, raise_exception=True)
                    print(f"[CONSULTANCY PUBLISHER] Validation passed")
                except ValidationError as ve:
                    error_msg = f"Validation failed: {str(ve)}"
                    frappe.log_error(error_msg, "Consultancy Deposit Slip Validation Error")
                    print(f"[ERROR] [CONSULTANCY PUBLISHER] {error_msg}")
                    return False

            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)
            key = dto.depositSlipRefNumFab or dto.slipNumber or "unknown"
            result = cls.publish_message(cls.TOPIC, kafka_payload, key, cls.DLQ_TOPIC)

            if result:
                print(f"[OK] [CONSULTANCY PUBLISHER] Successfully published DTO to Kafka")
            else:
                print(f"[ERROR] [CONSULTANCY PUBLISHER] Failed to publish DTO to Kafka")

            return result

        except Exception as e:
            error_msg = f"Error publishing DTO: {str(e)}"
            frappe.log_error(error_msg, "Consultancy Deposit Slip Publisher Error")
            print(f"[ERROR] [CONSULTANCY PUBLISHER] {error_msg}")
            return False

    @classmethod
    def dry_run(cls, doc) -> dict:
        """
        Perform a dry run without actually publishing to Kafka.
        Useful for testing and debugging.

        Args:
            doc: Consultancy Deposit Slip Frappe document

        Returns:
            dict: Contains validation results and payload preview
        """
        try:
            category = ConsultancyDepositSlipMapper.get_category(doc)
            print(f"[DRY RUN] [CONSULTANCY PUBLISHER] Dry run for: {doc.name} (Category: {category})")

            dto = ConsultancyDepositSlipMapper.map_to_dto(doc)
            validation_errors = ConsultancyDepositSlipValidator.validate(dto, raise_exception=False)
            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)

            result = {
                "valid": len(validation_errors) == 0,
                "validation_errors": validation_errors,
                "category": category,
                "gst_type": dto.gstType,
                "dto": dto.to_dict(),
                "kafka_payload": kafka_payload,
                "topic": cls.TOPIC,
                "dlq_topic": cls.DLQ_TOPIC
            }

            if result["valid"]:
                print(f"[OK] [CONSULTANCY PUBLISHER] Dry run successful - No validation errors")
            else:
                print(f"[ERROR] [CONSULTANCY PUBLISHER] Dry run found {len(validation_errors)} validation errors:")
                for error in validation_errors:
                    print(f"   - {error}")

            return result

        except Exception as e:
            error_msg = f"Error during dry run: {str(e)}"
            frappe.log_error(error_msg, "Consultancy Deposit Slip Publisher Dry Run Error")
            print(f"[ERROR] [CONSULTANCY PUBLISHER] {error_msg}")
            return {
                "valid": False,
                "error": error_msg,
                "validation_errors": [error_msg]
            }


def publish_consultancy_deposit_slip(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish Consultancy Deposit Slip.
    Auto-detects category from doctype.

    Args:
        doc: Consultancy Deposit Slip Frappe document (D, E, T, or Other Event)
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors

    Returns:
        bool: True if successful, False otherwise
    """
    return ConsultancyDepositSlipPublisher.publish(doc, validate=validate, log_errors=log_errors)
