# Copyright (c) 2025, rndops and contributors
# Deposit Slip Consumer Handler - Main entry point for Deposit Slip updates from Kafka

import frappe

from .research import ResearchDepositSlipUpdateDTO, ResearchDepositSlipConsumerMapper
from .consultancy import ConsultancyDepositSlipUpdateDTO, ConsultancyDepositSlipConsumerMapper
from ...logs import log_consumer_event, log_error


# Categories for routing
RESEARCH_CATEGORIES = ["RESEARCH"]
CONSULTANCY_CATEGORIES = ["D_CONSULTANCY", "E_NON_ROUTINE", "T_TESTING", "OTHER_EVENT"]


class DepositSlipConsumerHandler:
    """
    Main handler for Deposit Slip update messages from Kafka.
    Routes to appropriate submodule (Research or Consultancy) based on category.
    """

    @classmethod
    def is_research_category(cls, category: str) -> bool:
        """Check if category is Research type."""
        return category in RESEARCH_CATEGORIES

    @classmethod
    def is_consultancy_category(cls, category: str) -> bool:
        """Check if category is Consultancy type."""
        return category in CONSULTANCY_CATEGORIES

    @classmethod
    def handle(cls, message: dict) -> bool:
        """
        Main handler for Deposit Slip update messages.

        Args:
            message: Complete Kafka message

        Returns:
            bool: True if processed successfully
        """
        try:
            # Extract message metadata
            schema_version = message.get('schemaVersion', '1.0')
            event_type = message.get('eventType', 'UNKNOWN')
            timestamp = message.get('timestamp')
            data = message.get('data', {})

            # Get category from data
            category = data.get('category', 'RESEARCH')
            deposit_slip_ref = data.get('depositSlipRefNumFab', 'unknown')

            log_consumer_event(
                f"DEPOSIT_SLIP_{category}",
                deposit_slip_ref,
                "accounts-depositslip-update",
                "RECEIVED",
                f"Event: {event_type} | Category: {category}"
            )

            # Route to appropriate handler
            if cls.is_consultancy_category(category):
                return cls.handle_consultancy(data, category, deposit_slip_ref)
            else:
                return cls.handle_research(data, category, deposit_slip_ref)

        except Exception as e:
            error_msg = f"Error processing deposit slip update: {str(e)}"
            log_error(error_msg, "DEPOSIT_SLIP_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Kafka Consumer Handler Error")
            return False

    @classmethod
    def handle_research(cls, data: dict, category: str, deposit_slip_ref: str) -> bool:
        """
        Handle Research Deposit Slip update.

        Args:
            data: Message data payload
            category: Category string
            deposit_slip_ref: Deposit slip reference for logging

        Returns:
            bool: True if successful
        """
        try:
            # Parse to DTO
            dto = ResearchDepositSlipUpdateDTO.from_kafka_message(data)

            # Find document
            doc_name, doctype = ResearchDepositSlipConsumerMapper.find_document(dto)

            if not doc_name:
                log_consumer_event(
                    f"DEPOSIT_SLIP_{category}",
                    deposit_slip_ref,
                    "accounts-depositslip-update",
                    "SKIPPED",
                    "Document not found"
                )
                return True  # Return True to commit offset

            log_consumer_event(
                f"DEPOSIT_SLIP_{category}",
                doc_name,
                "accounts-depositslip-update",
                "PROCESSING",
                f"Found document: {doc_name} ({doctype})"
            )

            # Apply updates
            success = ResearchDepositSlipConsumerMapper.apply_updates(doc_name, doctype, dto)
            if not success:
                log_consumer_event(
                    f"DEPOSIT_SLIP_{category}",
                    doc_name,
                    "accounts-depositslip-update",
                    "FAILED",
                    "Failed to apply updates"
                )
                return False

            # Update credit distributions
            ResearchDepositSlipConsumerMapper.update_credit_distributions(doc_name, doctype, dto)

            # Commit
            frappe.db.commit()

            log_consumer_event(
                f"DEPOSIT_SLIP_{category}",
                doc_name,
                "accounts-depositslip-update",
                "SUCCESS",
                "Successfully processed update"
            )

            return True

        except Exception as e:
            error_msg = f"Error processing research deposit slip update: {str(e)}"
            log_error(error_msg, "DEPOSIT_SLIP_RESEARCH_CONSUMER_ERROR", exc_info=True)
            return False

    @classmethod
    def handle_consultancy(cls, data: dict, category: str, deposit_slip_ref: str) -> bool:
        """
        Handle Consultancy Deposit Slip update.

        Args:
            data: Message data payload
            category: Category string
            deposit_slip_ref: Deposit slip reference for logging

        Returns:
            bool: True if successful
        """
        try:
            # Parse to DTO
            dto = ConsultancyDepositSlipUpdateDTO.from_kafka_message(data)

            # Find document
            doc_name, doctype = ConsultancyDepositSlipConsumerMapper.find_document(dto)

            if not doc_name:
                log_consumer_event(
                    f"DEPOSIT_SLIP_{category}",
                    deposit_slip_ref,
                    "accounts-depositslip-update",
                    "SKIPPED",
                    "Document not found"
                )
                return True  # Return True to commit offset

            log_consumer_event(
                f"DEPOSIT_SLIP_{category}",
                doc_name,
                "accounts-depositslip-update",
                "PROCESSING",
                f"Found document: {doc_name} ({doctype})"
            )

            # Apply updates
            success = ConsultancyDepositSlipConsumerMapper.apply_updates(doc_name, doctype, dto)
            if not success:
                log_consumer_event(
                    f"DEPOSIT_SLIP_{category}",
                    doc_name,
                    "accounts-depositslip-update",
                    "FAILED",
                    "Failed to apply updates"
                )
                return False

            # Update credit distributions
            ConsultancyDepositSlipConsumerMapper.update_credit_distributions(doc_name, doctype, dto)

            # Commit
            frappe.db.commit()

            log_consumer_event(
                f"DEPOSIT_SLIP_{category}",
                doc_name,
                "accounts-depositslip-update",
                "SUCCESS",
                "Successfully processed update"
            )

            return True

        except Exception as e:
            error_msg = f"Error processing consultancy deposit slip update: {str(e)}"
            log_error(error_msg, f"DEPOSIT_SLIP_{category}_CONSUMER_ERROR", exc_info=True)
            return False


def handle_deposit_slip_update(message: dict) -> bool:
    """
    Convenience function to handle Deposit Slip update.

    Args:
        message: Complete Kafka message

    Returns:
        bool: True if successful
    """
    return DepositSlipConsumerHandler.handle(message)
