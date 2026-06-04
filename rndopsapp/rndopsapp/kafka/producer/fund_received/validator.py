# Copyright (c) 2025, rndops and contributors
# Fund Received Validator - Validates Fund Received DTO before publishing

import frappe
from typing import List
from .dto import FundReceivedDTO, FundReceivedEventDTO


class ValidationError(Exception):
    """Custom validation error for Fund Received."""
    pass


class FundReceivedValidator:
    """
    Validator for Fund Received DTO.
    Ensures data integrity before sending to Kafka.
    """

    @staticmethod
    def validate_required_fields(dto: FundReceivedDTO) -> List[str]:
        """
        Validate required fields in FundReceivedDTO.

        Args:
            dto: FundReceivedDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not dto.fundReceivedRefNumberFap:
            errors.append("fundReceivedRefNumberFap is required")

        if not dto.sanctionLetterNo:
            errors.append(
                "sanctionLetterNo is required — consumer cannot locate "
                "ProjectSanctionDetails without it"
            )

        if not dto.sanctionNumber:
            errors.append(
                "sanctionNumber is required — consumer uses this to link "
                "ProjectFundReceivedDetails to the sanction"
            )

        if not dto.projectNumber:
            errors.append("projectNumber is recommended but missing")

        return errors

    @staticmethod
    def validate_numeric_fields(dto: FundReceivedDTO) -> List[str]:
        """
        Validate numeric fields are non-negative.

        Args:
            dto: FundReceivedDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.amountReceived < 0:
            errors.append("amountReceived cannot be negative")

        return errors

    @staticmethod
    def validate_budget_breakups(dto: FundReceivedDTO) -> List[str]:
        """
        Validate budget breakup items.

        Args:
            dto: FundReceivedDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for idx, breakup in enumerate(dto.fundBudgetBreakupList):
            if breakup.amount < 0:
                errors.append(f"fundBudgetBreakupList[{idx}].amount cannot be negative")

        return errors

    @staticmethod
    def validate_transaction_details(dto: FundReceivedDTO) -> List[str]:
        """
        Validate transaction detail items.

        Args:
            dto: FundReceivedDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for idx, txn in enumerate(dto.transactionDetailsList):
            if txn.transactionAmount < 0:
                errors.append(f"transactionDetailsList[{idx}].transactionAmount cannot be negative")

        return errors

    @classmethod
    def validate(cls, dto: FundReceivedDTO, raise_exception: bool = True) -> List[str]:
        """
        Perform complete validation on FundReceivedDTO.

        Args:
            dto: FundReceivedDTO instance to validate
            raise_exception: If True, raises ValidationError on failure

        Returns:
            List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        all_errors = []

        all_errors.extend(cls.validate_required_fields(dto))
        all_errors.extend(cls.validate_numeric_fields(dto))
        all_errors.extend(cls.validate_budget_breakups(dto))
        all_errors.extend(cls.validate_transaction_details(dto))

        # Filter out warnings (non-blocking)
        blocking_errors = [e for e in all_errors if "recommended" not in e.lower()]

        if blocking_errors and raise_exception:
            error_message = "Fund Received DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in blocking_errors])
            frappe.log_error(error_message, "Fund Received DTO Validation Error")
            raise ValidationError(error_message)

        return all_errors

    @classmethod
    def validate_event(cls, event: FundReceivedEventDTO, raise_exception: bool = True) -> List[str]:
        """
        Validate complete FundReceivedEventDTO.

        Args:
            event: FundReceivedEventDTO instance
            raise_exception: If True, raises ValidationError on failure

        Returns:
            List of validation error messages
        """
        errors = []

        if not event.schemaVersion:
            errors.append("schemaVersion is required")

        if not event.eventType:
            errors.append("eventType is required")

        if not event.timestamp:
            errors.append("timestamp is required")

        # Validate the nested data DTO
        data_errors = cls.validate(event.data, raise_exception=False)
        errors.extend(data_errors)

        # Filter out warnings
        blocking_errors = [e for e in errors if "recommended" not in e.lower()]

        if blocking_errors and raise_exception:
            error_message = "Fund Received Event DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in blocking_errors])
            frappe.log_error(error_message, "Fund Received Event DTO Validation Error")
            raise ValidationError(error_message)

        return errors

    @staticmethod
    def validate_and_log(dto: FundReceivedDTO) -> bool:
        """
        Validate DTO and log errors without raising exception.

        Args:
            dto: FundReceivedDTO instance

        Returns:
            bool: True if valid, False if validation errors exist
        """
        try:
            errors = FundReceivedValidator.validate(dto, raise_exception=False)
            blocking_errors = [e for e in errors if "recommended" not in e.lower()]
            if blocking_errors:
                error_message = "Fund Received DTO Validation Failed:\n" + \
                    "\n".join([f"  - {err}" for err in blocking_errors])
                frappe.log_error(error_message, "Fund Received DTO Validation Error")
                print(f"[ERROR] [VALIDATION] {error_message}")
                return False
            return True
        except Exception as e:
            frappe.log_error(str(e), "Fund Received Validation Exception")
            print(f"[ERROR] [VALIDATION] Unexpected error: {str(e)}")
            return False
