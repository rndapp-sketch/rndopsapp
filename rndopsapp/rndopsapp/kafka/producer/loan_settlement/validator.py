# Copyright (c) 2026, rndops and contributors
# Loan Settlement Validator - Validates Loan Settlement DTO before publishing

from typing import List

import frappe

from .dto import LoanSettlementDTO, LoanSettlementEventDTO


class ValidationError(Exception):
    pass


class LoanSettlementValidator:
    """
    Mirrors the Accounts service's own required-field rules so a bad payload is caught
    here rather than dead-lettered on their side:
      loanNumber, projectNumber, loanSettlementNumber, fundReceivedRefNumberFap
      required; settlementAmount > 0.
    """

    @staticmethod
    def validate_required_fields(dto: LoanSettlementDTO) -> List[str]:
        errors = []
        if not dto.loanNumber:
            errors.append("loanNumber is required")
        if not dto.projectNumber:
            errors.append("projectNumber is required")
        if not dto.loanSettlementNumber:
            errors.append("loanSettlementNumber is required")
        # Blocking, not "recommended". Without it Accounts stores NULL, the receipt
        # never shows the settlement and nothing cascades — and because
        # loanSettlementNumber is an idempotency key on their side, a corrected
        # re-publish would be silently SKIPPED rather than applied. Publishing once
        # without it therefore poisons the settlement permanently. Failing here instead
        # leaves publish_status = "Failed", which is visible and retryable once the
        # Fund Received link exists.
        if not dto.fundReceivedRefNumberFap:
            errors.append(
                "fundReceivedRefNumberFap is required — this settlement is not linked to a "
                "Fund Received yet. Publishing without it cannot be corrected later."
            )
        if not dto.frapAppId:
            errors.append("frapAppId is recommended but missing")
        return errors

    @staticmethod
    def validate_numeric_fields(dto: LoanSettlementDTO) -> List[str]:
        errors = []
        if dto.settlementAmount is None or dto.settlementAmount <= 0:
            errors.append("settlementAmount must be greater than zero")
        return errors

    @classmethod
    def validate(cls, dto: LoanSettlementDTO, raise_exception: bool = True) -> List[str]:
        errors = []
        errors.extend(cls.validate_required_fields(dto))
        errors.extend(cls.validate_numeric_fields(dto))

        blocking = [e for e in errors if "recommended" not in e.lower()]
        if blocking and raise_exception:
            msg = "Loan Settlement DTO Validation Failed:\n" + "\n".join(f"  - {e}" for e in blocking)
            frappe.log_error(msg, "Loan Settlement DTO Validation Error")
            raise ValidationError(msg)
        return errors

    @classmethod
    def validate_event(cls, event: LoanSettlementEventDTO, raise_exception: bool = True) -> List[str]:
        errors = []
        if not event.schemaVersion:
            errors.append("schemaVersion is required")
        if not event.eventType:
            errors.append("eventType is required")
        errors.extend(cls.validate(event.data, raise_exception=False))

        blocking = [e for e in errors if "recommended" not in e.lower()]
        if blocking and raise_exception:
            msg = "Loan Settlement Event Validation Failed:\n" + "\n".join(f"  - {e}" for e in blocking)
            frappe.log_error(msg, "Loan Settlement Event Validation Error")
            raise ValidationError(msg)
        return errors
