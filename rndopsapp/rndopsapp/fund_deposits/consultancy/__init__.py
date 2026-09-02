# Copyright (c) 2025, rndops and contributors
# Consultancy Deposit Slip Module - Kafka Producer and Consumer
# Supports: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT

from .dto import (
    ConsultancyDepositSlipDTO,
    ConsultancyDDetailsDTO,
    ConsultancyEDetailsDTO,
    ConsultancyTDetailsDTO,
    ConsultancyODetailsDTO,
)
from .mapper import ConsultancyDepositSlipMapper
from .validator import ConsultancyDepositSlipValidator, ValidationError
from .publisher import ConsultancyDepositSlipPublisher, publish_consultancy_deposit_slip
from .consumer_dto import ConsultancyDepositSlipUpdateMessageDTO
from .consumer_mapper import ConsultancyDepositSlipConsumerMapper, ConsultancyDoctypeConfig
from .consumer_handler import ConsultancyDepositSlipConsumerHandler, handle_consultancy_deposit_slip_update

__all__ = [
    # DTOs
    'ConsultancyDepositSlipDTO',
    'ConsultancyDDetailsDTO',
    'ConsultancyEDetailsDTO',
    'ConsultancyTDetailsDTO',
    'ConsultancyODetailsDTO',
    'ConsultancyDepositSlipUpdateMessageDTO',
    # Producer
    'ConsultancyDepositSlipMapper',
    'ConsultancyDepositSlipValidator',
    'ConsultancyDepositSlipPublisher',
    'publish_consultancy_deposit_slip',
    'ValidationError',
    # Consumer
    'ConsultancyDepositSlipConsumerMapper',
    'ConsultancyDoctypeConfig',
    'ConsultancyDepositSlipConsumerHandler',
    'handle_consultancy_deposit_slip_update',
]
