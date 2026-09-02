# Copyright (c) 2026, rndops and contributors
# Loan Request Validator - Validates Loan Request DTO before publishing

import frappe
from typing import List
from .dto import LoanRequestDTO, LoanRequestEventDTO


class ValidationError(Exception):
    pass


class LoanRequestValidator:

    @staticmethod
    def validate_required_fields(dto: LoanRequestDTO) -> List[str]:
        errors = []
        if not dto.loanNumberFap:
            errors.append("loanNumberFap is required")
        if not dto.projectNumber:
            errors.append("projectNumber is recommended but missing")
        if not dto.loanType:
            errors.append("loanType is recommended but missing")
        return errors

    @staticmethod
    def validate_numeric_fields(dto: LoanRequestDTO) -> List[str]:
        errors = []
        if dto.loanAmount < 0:
            errors.append("loanAmount cannot be negative")
        for idx, row in enumerate(dto.loanBudgetBreakupDetails):
            if row.amount < 0:
                errors.append(f"loanBudgetBreakupDetails[{idx}].amount cannot be negative")
        return errors

    @classmethod
    def validate(cls, dto: LoanRequestDTO, raise_exception: bool = True) -> List[str]:
        errors = []
        errors.extend(cls.validate_required_fields(dto))
        errors.extend(cls.validate_numeric_fields(dto))

        blocking = [e for e in errors if "recommended" not in e.lower()]
        if blocking and raise_exception:
            msg = "Loan Request DTO Validation Failed:\n" + "\n".join(f"  - {e}" for e in blocking)
            frappe.log_error(msg, "Loan Request DTO Validation Error")
            raise ValidationError(msg)
        return errors

    @classmethod
    def validate_event(cls, event: LoanRequestEventDTO, raise_exception: bool = True) -> List[str]:
        errors = []
        if not event.schemaVersion:
            errors.append("schemaVersion is required")
        if not event.eventType:
            errors.append("eventType is required")
        errors.extend(cls.validate(event.data, raise_exception=False))

        blocking = [e for e in errors if "recommended" not in e.lower()]
        if blocking and raise_exception:
            msg = "Loan Request Event Validation Failed:\n" + "\n".join(f"  - {e}" for e in blocking)
            frappe.log_error(msg, "Loan Request Event Validation Error")
            raise ValidationError(msg)
        return errors
