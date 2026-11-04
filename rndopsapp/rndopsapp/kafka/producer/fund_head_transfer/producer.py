# Copyright (c) 2026, rndops and contributors
# Fund Head Transfer Producer - Publishes approved head-to-head transfers to Kafka

import frappe

from .mapper import FundHeadTransferMapper
from .validator import FundHeadTransferValidator, ValidationError
from ...config import (
    TOPIC_FUND_HEAD_TRANSFER,
    TOPIC_FUND_HEAD_TRANSFER_DLQ,
    SCHEMA_VERSION_FUND_HEAD_TRANSFER,
)
from ...utils import publish_message, is_kafka_available
from ...logs import log_producer_event, log_error


class FundHeadTransferProducer:
    """
    Publishes an Acc Head to Head Fund Transfer to fund-head-transfer-events when it
    reaches the 'Approved' workflow state. One message per transfer.
    """

    TOPIC = TOPIC_FUND_HEAD_TRANSFER
    DLQ_TOPIC = TOPIC_FUND_HEAD_TRANSFER_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_FUND_HEAD_TRANSFER

    @classmethod
    def publish(cls, doc, validate: bool = True, log_errors: bool = True, transferred_at=None) -> bool:
        """
        Publish a Fund Head Transfer event to Kafka.

        Returns:
            bool: True if successfully published, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "SKIPPED", "Kafka not available"
            )
            return False

        try:
            log_producer_event(
                "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "STARTED", "Beginning publish process"
            )

            event = FundHeadTransferMapper.map_to_event(doc, transferred_at)

            if validate:
                try:
                    FundHeadTransferValidator.validate_event(event, raise_exception=True)
                    log_producer_event(
                        "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "VALIDATED", "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "VALIDATION_FAILED", str(ve)
                        )
                    return False

            result = publish_message(
                cls.TOPIC,
                event.to_kafka_payload(),
                doc.name,
                cls.DLQ_TOPIC,
                key=event.data.projectNumber or doc.name,
            )

            if result:
                log_producer_event(
                    "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "SUCCESS",
                    f"Published | projectNumber={event.data.projectNumber} "
                    f"from={event.data.fromAccountHeadId} to={event.data.toAccountHeadId} "
                    f"amount={event.data.amount} fundReceived={event.data.fundReceivedRefNumberFap}"
                )
            else:
                log_producer_event(
                    "FUND_HEAD_TRANSFER", doc.name, cls.TOPIC, "FAILED", "publish_message returned False"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing fund head transfer: {str(e)}"
            log_error(error_msg, "FUND_HEAD_TRANSFER_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Fund Head Transfer Kafka Error")
            return False


def publish_fund_head_transfer(doc, validate: bool = True, log_errors: bool = True, transferred_at=None) -> bool:
    """Convenience function to publish a Fund Head Transfer event to Kafka."""
    return FundHeadTransferProducer.publish(
        doc, validate=validate, log_errors=log_errors, transferred_at=transferred_at
    )
