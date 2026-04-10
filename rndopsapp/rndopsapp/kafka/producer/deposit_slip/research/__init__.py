# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip Producer Module

from .dto import (
    ResearchDepositSlipDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)
from .mapper import ResearchDepositSlipMapper
from .validator import ResearchDepositSlipValidator, ValidationError


__all__ = [
    # DTOs
    "ResearchDepositSlipDTO",
    "CreditDistributionSwfDTO",
    "CreditDistributionPdfDTO",
    "CreditDistributionDpfDTO",
    "CreditDistributionIdfDTO",
    "CreditDistributionStwfDTO",
    # Mapper
    "ResearchDepositSlipMapper",
    # Validator
    "ResearchDepositSlipValidator",
    "ValidationError",
]

