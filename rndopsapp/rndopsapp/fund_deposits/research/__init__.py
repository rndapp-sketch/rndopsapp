# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip Module - Kafka Producer and Consumer

from .dto import ResearchDepositSlipDTO
from .mapper import ResearchDepositSlipMapper
from .validator import ResearchDepositSlipValidator, ValidationError
from .publisher import ResearchDepositSlipPublisher, publish_research_deposit_slip
from .consumer_dto import ResearchDepositSlipUpdateMessageDTO
from .consumer_mapper import ResearchDepositSlipConsumerMapper
from .consumer_handler import ResearchDepositSlipConsumerHandler, handle_research_deposit_slip_update

__all__ = [
    # DTOs
    'ResearchDepositSlipDTO',
    'ResearchDepositSlipUpdateMessageDTO',
    # Producer
    'ResearchDepositSlipMapper',
    'ResearchDepositSlipValidator',
    'ResearchDepositSlipPublisher',
    'publish_research_deposit_slip',
    'ValidationError',
    # Consumer
    'ResearchDepositSlipConsumerMapper',
    'ResearchDepositSlipConsumerHandler',
    'handle_research_deposit_slip_update',
]
