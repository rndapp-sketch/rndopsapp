# Copyright (c) 2025, rndops and contributors
# Deposit Slip Consumer Module

from .consumer import DepositSlipConsumerHandler, handle_deposit_slip_update

# Import Research module
from .research import (
    ResearchDepositSlipUpdateDTO,
    ResearchDepositSlipConsumerMapper,
)

# Import Consultancy module
from .consultancy import (
    ConsultancyDepositSlipUpdateDTO,
    ConsultancyDepositSlipConsumerMapper,
)

__all__ = [
    # Main handler
    'DepositSlipConsumerHandler',
    'handle_deposit_slip_update',

    # Research
    'ResearchDepositSlipUpdateDTO',
    'ResearchDepositSlipConsumerMapper',

    # Consultancy
    'ConsultancyDepositSlipUpdateDTO',
    'ConsultancyDepositSlipConsumerMapper',
]
