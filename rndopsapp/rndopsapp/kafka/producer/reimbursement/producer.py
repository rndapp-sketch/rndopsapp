# Copyright (c) 2025, rndops and contributors
# Reimbursement Producer - Main entry point for publishing Commit and Payment events to Kafka

import frappe
from typing import Optional

from .mapper import AccountHeadCommitMapper, AccountHeadPaymentMapper
from .validator import AccountHeadCommitValidator, AccountHeadPaymentValidator, ValidationError
from ...config import SCHEMA_VERSION_DEPOSIT_SLIP
from ...utils import publish_message, is_kafka_available, mm_notify
from ...logs import log_producer_event, log_error


# Kafka Topics
TOPIC_COMMIT = 'account-head-commit-events'
TOPIC_PAYMENT = 'account-head-payment-events'
TOPIC_COMMIT_DLQ = 'account-head-commit-events-dlq'
TOPIC_PAYMENT_DLQ = 'account-head-payment-events-dlq'


# ==========================================
# Commit Producer
# ==========================================

class AccountHeadCommitProducer:
    """
    Producer for Account Head Commit events.
    """

    TOPIC = TOPIC_COMMIT
    DLQ_TOPIC = TOPIC_COMMIT_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_DEPOSIT_SLIP

    @classmethod
    def publish(
        cls,
        doc,
        commit_amount: float,
        budget_head,
        project_name: str,
        bmr: Optional[str] = None,
        bill_amount: Optional[float] = None,
        validate: bool = True,
        log_errors: bool = True,
        frap_app_id: Optional[str] = None,
        ref_details: Optional[str] = None,
        module_id: Optional[int] = None,
        commit_particular: Optional[str] = None
    ) -> bool:
        """
        Publish Account Head Commit to Kafka.

        Args:
            doc: Reimbursement Frappe document
            commit_amount: Commit amount
            budget_head: Budget head name or ID
            project_name: Project number
            bmr: BMR number (optional)
            bill_amount: Bill amount (optional)
            validate: Whether to validate before publishing
            log_errors: Whether to log validation errors
            frap_app_id: Frap App ID (optional, defaults to project_name in mapper)
            module_id: optional int override (e.g. 14 for ICSS PO re-commit)
            commit_particular: Explicit particulars string (e.g. staged via
                commitPayment.submit_commit_data). Required for doctypes that
                have no table_bosk/expenditure_details child table, otherwise
                the mapper falls back to a generic "Commitment for {doc.name}".

        Returns:
            bool: True if successful, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "ACCOUNT_HEAD_COMMIT",
                doc.name,
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            mm_notify(
                f":warning: **Kafka Commit SKIPPED** — Kafka not available\n"
                f"**Doc:** {doc.name}\n"
                f"**Topic:** {cls.TOPIC}"
            )
            return False

        try:
            log_producer_event(
                "ACCOUNT_HEAD_COMMIT",
                doc.name,
                cls.TOPIC,
                "STARTED",
                "Beginning publish process"
            )

            # Map to event DTO
            event = AccountHeadCommitMapper.map_to_event(
                doc, commit_amount, budget_head, project_name, bmr, bill_amount, frap_app_id, ref_details, module_id, commit_particular
            )

            # Validate
            if validate:
                try:
                    AccountHeadCommitValidator.validate(event.data, raise_exception=True)
                    log_producer_event(
                        "ACCOUNT_HEAD_COMMIT",
                        doc.name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "ACCOUNT_HEAD_COMMIT",
                            doc.name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    mm_notify(
                        f":x: **Kafka Commit Validation FAILED**\n"
                        f"**Doc:** {doc.name}\n"
                        f"**Topic:** {cls.TOPIC}\n"
                        f"**Error:** {str(ve)}"
                    )
                    return False

            # Convert to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Publish
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc.name,
                cls.DLQ_TOPIC,
                key=project_name
            )

            if result:
                log_producer_event(
                    "ACCOUNT_HEAD_COMMIT",
                    doc.name,
                    cls.TOPIC,
                    "SUCCESS",
                    f"Successfully published | projectNumber={project_name}"
                )
                mm_notify(
                    f":white_check_mark: **Kafka Commit Published**\n"
                    f"**Doc:** {doc.name}\n"
                    f"**Topic:** {cls.TOPIC}\n"
                    f"**Project:** {project_name}"
                )
            else:
                log_producer_event(
                    "ACCOUNT_HEAD_COMMIT",
                    doc.name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )
                mm_notify(
                    f":x: **Kafka Commit FAILED**\n"
                    f"**Doc:** {doc.name}\n"
                    f"**Topic:** {cls.TOPIC}\n"
                    f"**Project:** {project_name}"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing commit: {str(e)}"
            log_error(error_msg, "ACCOUNT_HEAD_COMMIT_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Account Head Commit Kafka Error")
            mm_notify(
                f":rotating_light: **Kafka Commit Exception**\n"
                f"**Doc:** {doc.name}\n"
                f"**Topic:** {cls.TOPIC}\n"
                f"**Error:** {str(e)}"
            )
            return False


# ==========================================
# Payment Producer
# ==========================================

class AccountHeadPaymentProducer:
    """
    Producer for Account Head Payment events.
    """

    TOPIC = TOPIC_PAYMENT
    DLQ_TOPIC = TOPIC_PAYMENT_DLQ
    SCHEMA_VERSION = SCHEMA_VERSION_DEPOSIT_SLIP

    @classmethod
    def publish(
        cls,
        doc,
        project_name: Optional[str] = None,
        payment_amount: Optional[float] = None,
        budget_head=None,
        bmr: Optional[str] = None,
        validate: bool = True,
        log_errors: bool = True,
        ref_details: Optional[str] = None,
        frap_app_id: Optional[str] = None,
        module_name: Optional[str] = None,
        bill_amount: Optional[float] = None
    ) -> bool:
        """
        Publish Account Head Payment to Kafka.

        Args:
            doc: AccountHeadPayment Frappe document
            project_name: Optional override for project_ref_number
            payment_amount: Optional override for payment_amount
            budget_head: Optional override for budget_head
            bmr: Optional override for payment_bmr
            validate: Whether to validate before publishing
            log_errors: Whether to log validation errors
            ref_details: Optional string for reference details
            frap_app_id: Optional override for Frap App ID
            module_name: Optional override for Module Name
            bill_amount: Optional bill amount (defaults to payment_amount in the mapper)

        Returns:
            bool: True if successful, False otherwise
        """
        if not is_kafka_available():
            log_producer_event(
                "ACCOUNT_HEAD_PAYMENT",
                getattr(doc, 'name', 'NEW'),
                cls.TOPIC,
                "SKIPPED",
                "Kafka not available"
            )
            mm_notify(
                f":warning: **Kafka Payment SKIPPED** — Kafka not available\n"
                f"**Doc:** {getattr(doc, 'name', 'NEW')}\n"
                f"**Topic:** {cls.TOPIC}"
            )
            return False

        try:
            doc_name = getattr(doc, 'name', f"NEW-PAYMENT-{frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')}")

            log_producer_event(
                "ACCOUNT_HEAD_PAYMENT",
                doc_name,
                cls.TOPIC,
                "STARTED",
                "Beginning publish process"
            )

            # Map to event DTO
            event = AccountHeadPaymentMapper.map_to_event(
                doc, project_name, payment_amount, budget_head, bmr, ref_details, frap_app_id, module_name, bill_amount
            )

            # Validate
            if validate:
                try:
                    AccountHeadPaymentValidator.validate(event.data, raise_exception=True)
                    log_producer_event(
                        "ACCOUNT_HEAD_PAYMENT",
                        doc_name,
                        cls.TOPIC,
                        "VALIDATED",
                        "DTO validation passed"
                    )
                except ValidationError as ve:
                    if log_errors:
                        log_producer_event(
                            "ACCOUNT_HEAD_PAYMENT",
                            doc_name,
                            cls.TOPIC,
                            "VALIDATION_FAILED",
                            str(ve)
                        )
                    mm_notify(
                        f":x: **Kafka Payment Validation FAILED**\n"
                        f"**Doc:** {doc_name}\n"
                        f"**Topic:** {cls.TOPIC}\n"
                        f"**Error:** {str(ve)}"
                    )
                    return False

            # Convert to Kafka payload
            kafka_payload = event.to_kafka_payload()

            # Get partition key
            partition_key = event.data.projectNumber or doc_name

            # Publish
            result = publish_message(
                cls.TOPIC,
                kafka_payload,
                doc_name,
                cls.DLQ_TOPIC,
                key=partition_key
            )

            if result:
                log_producer_event(
                    "ACCOUNT_HEAD_PAYMENT",
                    doc_name,
                    cls.TOPIC,
                    "SUCCESS",
                    f"Successfully published | projectNumber={partition_key}"
                )
                mm_notify(
                    f":white_check_mark: **Kafka Payment Published**\n"
                    f"**Doc:** {doc_name}\n"
                    f"**Topic:** {cls.TOPIC}\n"
                    f"**Project:** {partition_key}"
                )
            else:
                log_producer_event(
                    "ACCOUNT_HEAD_PAYMENT",
                    doc_name,
                    cls.TOPIC,
                    "FAILED",
                    "Failed to publish to Kafka"
                )
                mm_notify(
                    f":x: **Kafka Payment FAILED**\n"
                    f"**Doc:** {doc_name}\n"
                    f"**Topic:** {cls.TOPIC}\n"
                    f"**Project:** {partition_key}"
                )

            return result

        except Exception as e:
            error_msg = f"Error publishing payment: {str(e)}"
            log_error(error_msg, "ACCOUNT_HEAD_PAYMENT_ERROR", exc_info=True)
            frappe.log_error(error_msg, "Account Head Payment Kafka Error")
            mm_notify(
                f":rotating_light: **Kafka Payment Exception**\n"
                f"**Doc:** {doc_name}\n"
                f"**Topic:** {cls.TOPIC}\n"
                f"**Error:** {str(e)}"
            )
            return False


# ==========================================
# Convenience Functions
# ==========================================

def publish_commit(
    doc,
    commit_amount: float,
    budget_head,
    project_name: str,
    bmr: Optional[str] = None,
    bill_amount: Optional[float] = None,
    validate: bool = True,
    log_errors: bool = True,
    frap_app_id: Optional[str] = None,
    ref_details: Optional[str] = None,
    module_id: Optional[int] = None,
    commit_particular: Optional[str] = None
) -> bool:
    """
    Convenience function to publish Account Head Commit.

    Args:
        doc: Reimbursement Frappe document
        commit_amount: Commit amount
        budget_head: Budget head name or ID
        project_name: Project number
        bmr: BMR number (optional)
        bill_amount: Bill amount (optional)
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors
        frap_app_id: Frap App ID (optional, defaults to project_name in mapper)
        module_id: optional int override (e.g. 14 for ICSS PO re-commit)
        commit_particular: Explicit particulars string, e.g. staged via
            commitPayment.submit_commit_data. Doctypes without a
            table_bosk/expenditure_details child table must pass this.

    Returns:
        bool: True if successful, False otherwise
    """
    return AccountHeadCommitProducer.publish(
        doc, commit_amount, budget_head, project_name, bmr, bill_amount, validate, log_errors, frap_app_id, ref_details, module_id, commit_particular
    )


def publish_payment(
    doc,
    project_name: Optional[str] = None,
    payment_amount: Optional[float] = None,
    budget_head=None,
    bmr: Optional[str] = None,
    validate: bool = True,
    log_errors: bool = True,
    ref_details: Optional[str] = None,
    frap_app_id: Optional[str] = None,
    module_name: Optional[str] = None,
    bill_amount: Optional[float] = None
) -> bool:
    """
    Convenience function to publish Account Head Payment.

    Args:
        doc: AccountHeadPayment Frappe document
        project_name: Optional override for project_ref_number
        payment_amount: Optional override for payment_amount
        budget_head: Optional override for budget_head
        bmr: Optional override for payment_bmr
        validate: Whether to validate before publishing
        log_errors: Whether to log validation errors
        frap_app_id: Frap App ID (optional, defaults to project_name in mapper)
        module_name: Module name (optional)
        bill_amount: Optional bill amount (defaults to payment_amount in the mapper)

    Returns:
        bool: True if successful, False otherwise
    """
    return AccountHeadPaymentProducer.publish(
        doc, project_name, payment_amount, budget_head, bmr, validate, log_errors, ref_details, frap_app_id, module_name, bill_amount
    )
