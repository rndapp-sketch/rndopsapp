# Copyright (c) 2025, rndops and contributors
# AccountHeadPayment Validator

import re
from typing import List, Tuple
from datetime import datetime

from .dto import AccountHeadPaymentDTO, PaymentStatus


class ValidationError(Exception):
    """Custom exception for validation errors."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class AccountHeadPaymentValidator:
    """
    Validator for AccountHeadPaymentDTO.
    Ensures data integrity before sending to Kafka.
    """

    # Valid payment statuses
    VALID_PAYMENT_STATUSES = [status.value for status in PaymentStatus]

    # Date format pattern (yyyy-MM-dd)
    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    @classmethod
    def validate(cls, dto: AccountHeadPaymentDTO) -> Tuple[bool, List[str]]:
        """
        Validate the AccountHeadPaymentDTO.

        Args:
            dto: The DTO to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Required field validations
        errors.extend(cls._validate_required_fields(dto))

        # Payment status validation
        errors.extend(cls._validate_payment_status(dto))

        # Date format validations
        errors.extend(cls._validate_dates(dto))

        # Amount validation
        errors.extend(cls._validate_amounts(dto))

        # Account head ID validation
        errors.extend(cls._validate_account_head_id(dto))

        return len(errors) == 0, errors

    @classmethod
    def validate_or_raise(cls, dto: AccountHeadPaymentDTO) -> None:
        """
        Validate the DTO and raise ValidationError if invalid.

        Args:
            dto: The DTO to validate

        Raises:
            ValidationError: If validation fails
        """
        is_valid, errors = cls.validate(dto)
        if not is_valid:
            raise ValidationError(errors)

    @classmethod
    def _validate_required_fields(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate required fields are present and non-empty."""
        errors = []

        if not dto.projectNumber or not dto.projectNumber.strip():
            errors.append("projectNumber is required")

        if not dto.paymentRefDetails or not dto.paymentRefDetails.strip():
            errors.append("paymentRefDetails is required")

        if not dto.paymentParticular or not dto.paymentParticular.strip():
            errors.append("paymentParticular is required")

        if not dto.paymentDate:
            errors.append("paymentDate is required")

        return errors

    @classmethod
    def _validate_payment_status(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate payment status is one of the allowed values."""
        errors = []

        if dto.paymentStatus not in cls.VALID_PAYMENT_STATUSES:
            errors.append(
                f"paymentStatus must be one of: {', '.join(cls.VALID_PAYMENT_STATUSES)}. "
                f"Got: '{dto.paymentStatus}'"
            )

        return errors

    @classmethod
    def _validate_dates(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate date fields are in correct format (yyyy-MM-dd)."""
        errors = []

        # Validate paymentDate
        if dto.paymentDate:
            if not cls.DATE_PATTERN.match(dto.paymentDate):
                errors.append(
                    f"paymentDate must be in yyyy-MM-dd format. Got: '{dto.paymentDate}'"
                )
            else:
                # Validate it's a valid date
                try:
                    datetime.strptime(dto.paymentDate, "%Y-%m-%d")
                except ValueError:
                    errors.append(f"paymentDate is not a valid date: '{dto.paymentDate}'")

        # Validate bankTransactionDate (optional, but if provided must be valid)
        if dto.bankTransactionDate:
            if not cls.DATE_PATTERN.match(dto.bankTransactionDate):
                errors.append(
                    f"bankTransactionDate must be in yyyy-MM-dd format. Got: '{dto.bankTransactionDate}'"
                )
            else:
                try:
                    datetime.strptime(dto.bankTransactionDate, "%Y-%m-%d")
                except ValueError:
                    errors.append(
                        f"bankTransactionDate is not a valid date: '{dto.bankTransactionDate}'"
                    )

        return errors

    @classmethod
    def _validate_amounts(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate amount fields."""
        errors = []

        if dto.paymentAmount is None:
            errors.append("paymentAmount is required")
        elif dto.paymentAmount < 0:
            errors.append(f"paymentAmount cannot be negative. Got: {dto.paymentAmount}")

        return errors

    @classmethod
    def _validate_account_head_id(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate account head ID."""
        errors = []

        if dto.accountHeadId is None or dto.accountHeadId <= 0:
            errors.append(f"accountHeadId must be a positive integer. Got: {dto.accountHeadId}")

        return errors

    @classmethod
    def _validate_transaction_commit_number(cls, dto: AccountHeadPaymentDTO) -> List[str]:
        """Validate transaction commit number."""
        errors = []

        if dto.transactionCommitNumber is None or dto.transactionCommitNumber <= 0:
            errors.append(
                f"transactionCommitNumber must be a positive integer. Got: {dto.transactionCommitNumber}"
            )

        return errors
