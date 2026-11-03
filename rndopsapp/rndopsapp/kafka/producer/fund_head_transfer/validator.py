# Copyright (c) 2026, rndops and contributors
# Fund Head Transfer Validator - Validates the DTO before publishing

from typing import List

import frappe

from .dto import FundHeadTransferDTO, FundHeadTransferEventDTO


class ValidationError(Exception):
    pass


class FundHeadTransferValidator:
    """
    Required: transferRefNumber, projectNumber, fundReceivedRefNumberFap, both head ids
    (and different), amount > 0.

    Run before the transfer is approved as well as before publishing, so a transfer the
    Accounts service could not accept is refused at approval instead of being approved in
    Frappe and then never reaching the ledger.
    """

    @staticmethod
    def validate_required_fields(dto: FundHeadTransferDTO) -> List[str]:
        errors = []
        if not dto.transferRefNumber:
            errors.append("transferRefNumber is required")
        if not dto.projectNumber:
            errors.append("projectNumber is required")
        if not dto.fundReceivedRefNumberFap:
            errors.append(
                "fundReceivedRefNumberFap is required — no published Fund Received on this "
                "project credited the head the money is being transferred from"
            )
        if not dto.fromAccountHeadId:
            errors.append("fromAccountHeadId is required — the source head has no ledger id")
        if not dto.toAccountHeadId:
            errors.append("toAccountHeadId is required — the destination head has no ledger id")
        if dto.fromAccountHeadId and dto.fromAccountHeadId == dto.toAccountHeadId:
            errors.append("fromAccountHeadId and toAccountHeadId must differ")
        return errors

    @staticmethod
    def validate_numeric_fields(dto: FundHeadTransferDTO) -> List[str]:
        errors = []
        if dto.amount is None or dto.amount <= 0:
            errors.append("amount must be greater than zero")
        return errors

    @classmethod
    def validate(cls, dto: FundHeadTransferDTO, raise_exception: bool = True) -> List[str]:
        errors = cls.validate_required_fields(dto) + cls.validate_numeric_fields(dto)
        if errors and raise_exception:
            msg = "Fund Head Transfer DTO Validation Failed:\n" + "\n".join(f"  - {e}" for e in errors)
            frappe.log_error(msg, "Fund Head Transfer DTO Validation Error")
            raise ValidationError(msg)
        return errors

    @classmethod
    def validate_event(cls, event: FundHeadTransferEventDTO, raise_exception: bool = True) -> List[str]:
        errors = []
        if not event.schemaVersion:
            errors.append("schemaVersion is required")
        if not event.eventType:
            errors.append("eventType is required")
        errors.extend(cls.validate(event.data, raise_exception=False))

        if errors and raise_exception:
            msg = "Fund Head Transfer Event Validation Failed:\n" + "\n".join(f"  - {e}" for e in errors)
            frappe.log_error(msg, "Fund Head Transfer Event Validation Error")
            raise ValidationError(msg)
        return errors
