# Copyright (c) 2025, rndops and contributors
# Publisher Service for Research Deposit Slip

import json
import frappe
from datetime import datetime
from .dto import ResearchDepositSlipDTO
from .mapper import ResearchDepositSlipMapper
from .validator import ResearchDepositSlipValidator, ValidationError


class ResearchDepositSlipPublisher:
    """
    Service layer for publishing Research Deposit Slip to Kafka.
    Uses DTO pattern for data transformation and validation.
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
        Main entry point for publishing Research Deposit Slip to Kafka.

        Args:
            doc: Research Deposit Slip Frappe document
            validate: Whether to validate the DTO before publishing
            log_errors: Whether to log validation errors

        Returns:
            bool: True if successfully published, False otherwise
        """
        try:
            print(f"[RESEARCH PUBLISHER] Starting publish for: {doc.name}")

            # Step 1: Map Frappe document to DTO
            print(f"[RESEARCH PUBLISHER] Mapping document to DTO...")
            dto = ResearchDepositSlipMapper.map_to_dto(doc)

            # Step 2: Validate DTO
            if validate:
                print(f"[RESEARCH PUBLISHER] Validating DTO...")
                try:
                    ResearchDepositSlipValidator.validate(dto, raise_exception=True)
                    print(f"[RESEARCH PUBLISHER] Validation passed")
                except ValidationError as ve:
                    if log_errors:
                        error_msg = f"Validation failed for {doc.name}: {str(ve)}"
                        frappe.log_error(error_msg, "Research Deposit Slip Validation Error")
                        print(f"[ERROR] [RESEARCH PUBLISHER] {error_msg}")
                    return False

            # Step 3: Convert DTO to Kafka payload
            print(f"[RESEARCH PUBLISHER] Converting DTO to Kafka payload...")
            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)

            # Step 4: Log payload for debugging
            print(f"[RESEARCH PUBLISHER] Sending to topic: {cls.TOPIC}")
            print(f"[RESEARCH PUBLISHER] Payload preview:")
            print(json.dumps(kafka_payload, indent=2, default=str))

            # Step 5: Publish to Kafka
            print(f"[RESEARCH PUBLISHER] Publishing to Kafka...")
            result = cls.publish_message(cls.TOPIC, kafka_payload, doc.name, cls.DLQ_TOPIC)

            if result:
                print(f"[OK] [RESEARCH PUBLISHER] Successfully published {doc.name} to Kafka")
            else:
                print(f"[ERROR] [RESEARCH PUBLISHER] Failed to publish {doc.name} to Kafka")

            return result

        except Exception as e:
            error_msg = f"Error publishing research deposit slip {doc.name}: {str(e)}"
            frappe.log_error(error_msg, "Research Deposit Slip Publisher Error")
            print(f"[ERROR] [RESEARCH PUBLISHER] {error_msg}")
            return False

    @classmethod
    def publish_with_dto(cls, dto: ResearchDepositSlipDTO, validate: bool = True) -> bool:
        """
        Publish using a pre-built DTO (useful for testing or custom scenarios).

        Args:
            dto: ResearchDepositSlipDTO instance
            validate: Whether to validate the DTO before publishing

        Returns:
            bool: True if successfully published, False otherwise
        """
        try:
            print(f"[RESEARCH PUBLISHER] Publishing with custom DTO...")

            if validate:
                print(f"[RESEARCH PUBLISHER] Validating DTO...")
                try:
                    ResearchDepositSlipValidator.validate(dto, raise_exception=True)
                    print(f"[RESEARCH PUBLISHER] Validation passed")
                except ValidationError as ve:
                    error_msg = f"Validation failed: {str(ve)}"
                    frappe.log_error(error_msg, "Research Deposit Slip Validation Error")
                    print(f"[ERROR] [RESEARCH PUBLISHER] {error_msg}")
                    return False

            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)
            key = dto.depositSlipRefNumFab or dto.slipNumber or "unknown"
            result = cls.publish_message(cls.TOPIC, kafka_payload, key, cls.DLQ_TOPIC)

            if result:
                print(f"[OK] [RESEARCH PUBLISHER] Successfully published DTO to Kafka")
            else:
                print(f"[ERROR] [RESEARCH PUBLISHER] Failed to publish DTO to Kafka")

            return result

        except Exception as e:
            error_msg = f"Error publishing DTO: {str(e)}"
            frappe.log_error(error_msg, "Research Deposit Slip Publisher Error")
            print(f"[ERROR] [RESEARCH PUBLISHER] {error_msg}")
            return False

    @classmethod
    def dry_run(cls, doc) -> dict:
        """
        Perform a dry run without actually publishing to Kafka.
        Useful for testing and debugging.

        Args:
            doc: Research Deposit Slip Frappe document

        Returns:
            dict: Contains validation results and payload preview
        """
        try:
            print(f"[DRY RUN] [RESEARCH PUBLISHER] Dry run for: {doc.name}")

            dto = ResearchDepositSlipMapper.map_to_dto(doc)
            validation_errors = ResearchDepositSlipValidator.validate(dto, raise_exception=False)
            kafka_payload = dto.to_kafka_payload(schema_version=cls.SCHEMA_VERSION)

            result = {
                "valid": len(validation_errors) == 0,
                "validation_errors": validation_errors,
                "dto": dto.to_dict(),
                "kafka_payload": kafka_payload,
                "topic": cls.TOPIC,
                "dlq_topic": cls.DLQ_TOPIC
            }

            if result["valid"]:
                print(f"[OK] [RESEARCH PUBLISHER] Dry run successful - No validation errors")
            else:
                print(f"[ERROR] [RESEARCH PUBLISHER] Dry run found {len(validation_errors)} validation errors:")
                for error in validation_errors:
                    print(f"   - {error}")

            return result

        except Exception as e:
            error_msg = f"Error during dry run: {str(e)}"
            frappe.log_error(error_msg, "Research Deposit Slip Publisher Dry Run Error")
            print(f"[ERROR] [RESEARCH PUBLISHER] {error_msg}")
            return {
                "valid": False,
                "error": error_msg,
                "validation_errors": [error_msg]
            }


def publish_research_deposit_slip(doc, validate: bool = True, log_errors: bool = True) -> bool:
    """
    Convenience function to publish Research Deposit Slip.

    Args:
        doc: Research Deposit Slip Frappe document
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors

    Returns:
        bool: True if successful, False otherwise
    """
    return ResearchDepositSlipPublisher.publish(doc, validate=validate, log_errors=log_errors)
