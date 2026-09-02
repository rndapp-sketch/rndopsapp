# Copyright (c) 2025, rndops and contributors
# Kafka Producer Module - All producer modules for Kafka events

from .project_registration import (
    ProjectDataDTO,
    ProjectEventDTO,
    ProjectRegistrationMapper,
    ProjectRegistrationValidator,
    ProjectRegistrationProducer,
    publish_project_registration,
)

from .fund_sanction import (
    FundSanctionDTO,
    BudgetBreakupDTO,
    FundSanctionMapper,
    FundSanctionValidator,
    FundSanctionProducer,
    publish_fund_sanction,
)

from .fund_received import (
    FundReceivedDTO,
    FundBudgetBreakupDTO,
    TransactionDetailsDTO,
    FundReceivedMapper,
    FundReceivedValidator,
    FundReceivedProducer,
    publish_fund_received,
)

from .deposit_slip import (
    publish_deposit_slip,
    DepositSlipProducer,
)

__all__ = [
    # Project Registration
    'ProjectDataDTO',
    'ProjectEventDTO',
    'ProjectRegistrationMapper',
    'ProjectRegistrationValidator',
    'ProjectRegistrationProducer',
    'publish_project_registration',

    # Fund Sanction
    'FundSanctionDTO',
    'BudgetBreakupDTO',
    'FundSanctionMapper',
    'FundSanctionValidator',
    'FundSanctionProducer',
    'publish_fund_sanction',

    # Fund Received
    'FundReceivedDTO',
    'FundBudgetBreakupDTO',
    'TransactionDetailsDTO',
    'FundReceivedMapper',
    'FundReceivedValidator',
    'FundReceivedProducer',
    'publish_fund_received',

    # Deposit Slip
    'publish_deposit_slip',
    'DepositSlipProducer',
]
