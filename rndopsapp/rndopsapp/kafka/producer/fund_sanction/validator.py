# Copyright (c) 2025, rndops and contributors
# Fund Sanction Validator - Validates Fund Sanction DTO before publishing

import frappe
from typing import List
from .dto import FundSanctionDTO, FundSanctionEventDTO


class ValidationError(Exception):
    """Custom validation error for Fund Sanction."""
    pass


class FundSanctionValidator:
    """
    Validator for Fund Sanction DTO.
    Ensures data integrity before sending to Kafka.
    """

    @staticmethod
    def validate_required_fields(dto: FundSanctionDTO) -> List[str]:
        """
        Validate required fields in FundSanctionDTO.

        Args:
            dto: FundSanctionDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Project number is required (but can be empty in some cases)
        if not dto.projectNumber:
            errors.append("projectNumber is recommended but missing")

        return errors

    @staticmethod
    def validate_numeric_fields(dto: FundSanctionDTO) -> List[str]:
        """
        Validate numeric fields are non-negative.

        Args:
            dto: FundSanctionDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.totalSanctionAmount < 0:
            errors.append("totalSanctionAmount cannot be negative")

        return errors

    @staticmethod
    def validate_budget_breakups(dto: FundSanctionDTO) -> List[str]:
        """
        Validate budget breakup items.

        Args:
            dto: FundSanctionDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        for idx, breakup in enumerate(dto.budgetBreakups):
            if breakup.accountHeadAmount < 0:
                errors.append(f"budgetBreakups[{idx}].accountHeadAmount cannot be negative")

            if breakup.firstYearBudget < 0:
                errors.append(f"budgetBreakups[{idx}].firstYearBudget cannot be negative")

            if breakup.secondYearBudget < 0:
                errors.append(f"budgetBreakups[{idx}].secondYearBudget cannot be negative")

            if breakup.thirdYearBudget < 0:
                errors.append(f"budgetBreakups[{idx}].thirdYearBudget cannot be negative")

            if breakup.fourthYearBudget < 0:
                errors.append(f"budgetBreakups[{idx}].fourthYearBudget cannot be negative")

            if breakup.fifthYearBudget < 0:
                errors.append(f"budgetBreakups[{idx}].fifthYearBudget cannot be negative")

        return errors

    @classmethod
    def validate(cls, dto: FundSanctionDTO, raise_exception: bool = True) -> List[str]:
        """
        Perform complete validation on FundSanctionDTO.

        Args:
            dto: FundSanctionDTO instance to validate
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

        # Filter out warnings (non-blocking)
        blocking_errors = [e for e in all_errors if "recommended" not in e.lower()]

        if blocking_errors and raise_exception:
            error_message = "Fund Sanction DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in blocking_errors])
            frappe.log_error(error_message, "Fund Sanction DTO Validation Error")
            raise ValidationError(error_message)

        return all_errors

    @classmethod
    def validate_event(cls, event: FundSanctionEventDTO, raise_exception: bool = True) -> List[str]:
        """
        Validate complete FundSanctionEventDTO.

        Args:
            event: FundSanctionEventDTO instance
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
            error_message = "Fund Sanction Event DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in blocking_errors])
            frappe.log_error(error_message, "Fund Sanction Event DTO Validation Error")
            raise ValidationError(error_message)

        return errors

    @staticmethod
    def validate_and_log(dto: FundSanctionDTO) -> bool:
        """
        Validate DTO and log errors without raising exception.

        Args:
            dto: FundSanctionDTO instance

        Returns:
            bool: True if valid, False if validation errors exist
        """
        try:
            errors = FundSanctionValidator.validate(dto, raise_exception=False)
            # Only consider blocking errors
            blocking_errors = [e for e in errors if "recommended" not in e.lower()]
            if blocking_errors:
                error_message = "Fund Sanction DTO Validation Failed:\n" + \
                    "\n".join([f"  - {err}" for err in blocking_errors])
                frappe.log_error(error_message, "Fund Sanction DTO Validation Error")
                print(f"[ERROR] [VALIDATION] {error_message}")
                return False
            return True
        except Exception as e:
            frappe.log_error(str(e), "Fund Sanction Validation Exception")
            print(f"[ERROR] [VALIDATION] Unexpected error: {str(e)}")
            return False
