# Copyright (c) 2025, rndops and contributors
# Deposit Slip Producer Module
#
# This module handles deposit slip publishing for both Research and Consultancy types.
# - research/: Research Deposit Slip DTOs, mapper, validator
# - consultancy/: Consultancy Deposit Slip DTOs, mapper, validator (D, E, T, Other Event)

from .producer import DepositSlipProducer, publish_deposit_slip

# Import Research module
from .research import (
    ResearchDepositSlipDTO,
    CreditDistributionSwfDTO as ResearchCreditDistributionDTO,
    ResearchDepositSlipMapper,
    ResearchDepositSlipValidator,
)

# Import Consultancy module
from .consultancy import (
    ConsultancyDepositSlipDTO,
    GstDetailsDTO as ConsultancyGstDetailsDTO,
    CreditDistributionSwfDTO as ConsultancyCreditDistributionDTO,
    ConsultancyDepositSlipMapper,
    ConsultancyDepositSlipValidator,
)

__all__ = [
    # Main producer
    'DepositSlipProducer',
    'publish_deposit_slip',

    # Research
    'ResearchDepositSlipDTO',
    'ResearchCreditDistributionDTO',
    'ResearchDepositSlipMapper',
    'ResearchDepositSlipValidator',

    # Consultancy
    'ConsultancyDepositSlipDTO',
    'ConsultancyGstDetailsDTO',
    'ConsultancyCreditDistributionDTO',
    'ConsultancyDepositSlipMapper',
    'ConsultancyDepositSlipValidator',
]
