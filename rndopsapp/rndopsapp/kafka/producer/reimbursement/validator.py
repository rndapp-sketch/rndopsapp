# Copyright (c) 2025, rndops and contributors
# Validator for Reimbursement Commit and Payment DTOs

from typing import List
from .dto import AccountHeadCommitDTO, AccountHeadPaymentDTO


class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass


# ==========================================
# Commit Validator
# ==========================================

class AccountHeadCommitValidator:
    """
    Validator for AccountHeadCommitDTO.
    """

    @staticmethod
    def validate(dto: AccountHeadCommitDTO, raise_exception: bool = False) -> List[str]:
        """
        Validate AccountHeadCommitDTO.

        Args:
            dto: The DTO to validate
            raise_exception: Whether to raise exception on validation failure

        Returns:
            List[str]: List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        errors = []

        # Required fields
        if not dto.projectNumber:
            errors.append("projectNumber is required")

        if dto.accountHeadId is None:
            errors.append("accountHeadId is required")

        if not dto.commitDate:
            errors.append("commitDate is required")

        if dto.commitAmount <= 0:
            errors.append("commitAmount must be greater than 0")

        # Valid status values
        valid_statuses = ["COMMITTED", "PENDING", "CANCELLED"]
        if dto.status and dto.status not in valid_statuses:
            errors.append(f"status must be one of: {', '.join(valid_statuses)}")

        if raise_exception and errors:
            raise ValidationError("; ".join(errors))

        return errors


# ==========================================
# Payment Validator
# ==========================================

class AccountHeadPaymentValidator:
    """
    Validator for AccountHeadPaymentDTO.
    """

    @staticmethod
    def validate(dto: AccountHeadPaymentDTO, raise_exception: bool = False) -> List[str]:
        """
        Validate AccountHeadPaymentDTO.

        Args:
            dto: The DTO to validate
            raise_exception: Whether to raise exception on validation failure

        Returns:
            List[str]: List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        errors = []

        # Required fields
        if not dto.projectNumber:
            errors.append("projectNumber is required")

        if dto.accountHeadId is None:
            errors.append("accountHeadId is required")

        if not dto.paymentDate:
            errors.append("paymentDate is required")

        # Valid payment status values
        valid_statuses = ["PAID", "PENDING", "CANCELLED", "FAILED", "RECTIFICATION", "REJECTED"]
        if dto.paymentStatus and dto.paymentStatus not in valid_statuses:
            errors.append(f"paymentStatus must be one of: {', '.join(valid_statuses)}")

        if raise_exception and errors:
            raise ValidationError("; ".join(errors))

        return errors
