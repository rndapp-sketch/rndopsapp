# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip Consumer Module

from .dto import (
    ResearchDepositSlipUpdateDTO,
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)
from .mapper import ResearchDepositSlipConsumerMapper


__all__ = [
    # DTOs
    "ResearchDepositSlipUpdateDTO",
    "GstDetailsDTO",
    "CreditDistributionSwfDTO",
    "CreditDistributionPdfDTO",
    "CreditDistributionDpfDTO",
    "CreditDistributionIdfDTO",
    "CreditDistributionStwfDTO",
    # Mapper
    "ResearchDepositSlipConsumerMapper",
]
