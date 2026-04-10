# Copyright (c) 2025, rndops and contributors
# Fund Received Consumer Handler - Processes Fund Received updates from Kafka

import json
import frappe

from .dto import FundReceivedUpdateDTO
from .mapper import FundReceivedConsumerMapper
from ...logs import log_consumer_event, log_error


class FundReceivedConsumerHandler:
    """
    Handler for Fund Received update messages from Kafka.
    Processes incoming messages and updates Frappe documents.
    """

    @classmethod
    def handle(cls, message: dict) -> bool:
        """
        Main handler for Fund Received update messages.

        Args:
            message: Complete Kafka message (with schemaVersion, eventType, timestamp, data)

        Returns:
            bool: True if processed successfully
        """
        try:
            # Extract message metadata
            schema_version = message.get('schemaVersion', '1.0')
            event_type = message.get('eventType', 'UNKNOWN')
            timestamp = message.get('timestamp')
            data = message.get('data', {})

            # Log received message
            log_consumer_event(
                "FUND_RECEIVED_UPDATE",
                data.get('fundReceivedRefNumberFap', 'unknown'),
                "accounts-fundreceived-update",
                "RECEIVED",
                f"Event: {event_type} | Schema: {schema_version}"
            )

            # Parse message data to DTO
            dto = FundReceivedUpdateDTO.from_kafka_message(data)

            # Find the document
            doc_name = FundReceivedConsumerMapper.find_document(dto)

            if not doc_name:
                log_consumer_event(
                    "FUND_RECEIVED_UPDATE",
                    str(dto.fundReceivedRefNumber or dto.fundReceivedRefNumberFap),
                    "accounts-fundreceived-update",
                    "SKIPPED",
                    "Document not found"
                )
                # Return True to commit offset - document not found is not an error
                return True

            log_consumer_event(
                "FUND_RECEIVED_UPDATE",
                doc_name,
                "accounts-fundreceived-update",
                "PROCESSING",
                f"Found document: {doc_name}"
            )

            # Apply main field updates
            success = FundReceivedConsumerMapper.apply_updates(doc_name, dto)
            if not success:
                log_consumer_event(
                    "FUND_RECEIVED_UPDATE",
                    doc_name,
                    "accounts-fundreceived-update",
                    "FAILED",
                    "Failed to apply main field updates"
                )
                return False

            # Commit main updates before child table updates
            frappe.db.commit()

            # Update budget breakup child table
            if dto.fundBudgetBreakupList:
                success = FundReceivedConsumerMapper.update_budget_breakup(doc_name, dto)
                if not success:
                    log_consumer_event(
                        "FUND_RECEIVED_UPDATE",
                        doc_name,
                        "accounts-fundreceived-update",
                        "WARNING",
                        "Failed to update budget breakup"
                    )

            # Update transaction details child table
            if dto.transactionDetailsList:
                success = FundReceivedConsumerMapper.update_transaction_details(doc_name, dto)
                if not success:
                    log_consumer_event(
                        "FUND_RECEIVED_UPDATE",
                        doc_name,
                        "accounts-fundreceived-update",
                        "WARNING",
                        "Failed to update transaction details"
                    )

            # Final commit
            frappe.db.commit()

            log_consumer_event(
                "FUND_RECEIVED_UPDATE",
                doc_name,
                "accounts-fundreceived-update",
                "SUCCESS",
                "Successfully processed update"
            )

            return True

        except Exception as e:
            error_msg = f"Error processing fund received update: {str(e)}"
            log_error(error_msg, "FUND_RECEIVED_CONSUMER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Kafka Consumer Handler Error")
            return False


def handle_fund_received_update(message: dict) -> bool:
    """
    Convenience function to handle Fund Received update.

    Args:
        message: Complete Kafka message

    Returns:
        bool: True if successful
    """
    return FundReceivedConsumerHandler.handle(message)
