# Copyright (c) 2025, rndops and contributors
# Fund Deposits Module - Data Transfer Objects and Services for Deposit Slip Kafka Integration
#
# This module is organized into submodules:
# - common/: Shared DTOs and utilities
# - research/: Research Deposit Slip producer and consumer
# - consultancy/: Consultancy (D, E, T, Other Event) producer and consumer

# ============================================================================
# Common module (shared DTOs and utilities)
# ============================================================================
from .common import (
    # Shared DTOs
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
    # Utilities
    fmt_date,
    get_fund_received_ref_number,
    get_department_id,
    # Child Tables
    DepositSlipChildTableUpdater,
)

# ============================================================================
# Research module
# ============================================================================
from .research import (
    # DTOs
    ResearchDepositSlipDTO,
    ResearchDepositSlipUpdateMessageDTO,
    # Producer
    ResearchDepositSlipMapper,
    ResearchDepositSlipValidator,
    ResearchDepositSlipPublisher,
    publish_research_deposit_slip,
    # Consumer
    ResearchDepositSlipConsumerMapper,
    ResearchDepositSlipConsumerHandler,
    handle_research_deposit_slip_update,
)

# ============================================================================
# Consultancy module (D, E, T, Other Event)
# ============================================================================
from .consultancy import (
    # DTOs
    ConsultancyDepositSlipDTO,
    ConsultancyDDetailsDTO,
    ConsultancyEDetailsDTO,
    ConsultancyTDetailsDTO,
    ConsultancyODetailsDTO,
    ConsultancyDepositSlipUpdateMessageDTO,
    # Producer
    ConsultancyDepositSlipMapper,
    ConsultancyDepositSlipValidator,
    ConsultancyDepositSlipPublisher,
    publish_consultancy_deposit_slip,
    # Consumer
    ConsultancyDepositSlipConsumerMapper,
    ConsultancyDoctypeConfig,
    ConsultancyDepositSlipConsumerHandler,
    handle_consultancy_deposit_slip_update,
)

# ============================================================================
# Backward compatibility - Legacy exports
# (These map to the old mixed module names for compatibility)
# ============================================================================
# Legacy DTO alias
DepositSlipDTO = ResearchDepositSlipDTO

# Legacy publisher alias (routes to research by default)
def publish_deposit_slip(doc, validate=True, log_errors=True):
    """
    Legacy function for backward compatibility.
    Routes to research or consultancy publisher based on doctype.
    """
    doctype = getattr(doc, 'doctype', '')
    consultancy_doctypes = [
        "D Consultancy Deposit Slip",
        "E Non Routine Deposit Slip",
        "T Testing Deposit Slip",
        "Other Event Deposit Slip",
    ]
    if doctype in consultancy_doctypes:
        return publish_consultancy_deposit_slip(doc, validate=validate, log_errors=log_errors)
    else:
        return publish_research_deposit_slip(doc, validate=validate, log_errors=log_errors)

# Legacy validator/mapper aliases
DepositSlipValidator = ResearchDepositSlipValidator
DepositSlipMapper = ResearchDepositSlipMapper
DepositSlipPublisher = ResearchDepositSlipPublisher

# Legacy consumer aliases
DepositSlipUpdateMessageDTO = ResearchDepositSlipUpdateMessageDTO
DepositSlipConsumerValidator = ResearchDepositSlipValidator
DepositSlipConsumerMapper = ResearchDepositSlipConsumerMapper
DepositSlipDoctypeConfig = ConsultancyDoctypeConfig
DepositSlipConsumerHandler = ResearchDepositSlipConsumerHandler
handle_deposit_slip_update = handle_research_deposit_slip_update


__all__ = [
    # ========== Common DTOs ==========
    'GstDetailsDTO',
    'CreditDistributionSwfDTO',
    'CreditDistributionPdfDTO',
    'CreditDistributionDpfDTO',
    'CreditDistributionIdfDTO',
    'CreditDistributionStwfDTO',
    'DepositSlipChildTableUpdater',

    # ========== Research Module ==========
    'ResearchDepositSlipDTO',
    'ResearchDepositSlipUpdateMessageDTO',
    'ResearchDepositSlipMapper',
    'ResearchDepositSlipValidator',
    'ResearchDepositSlipPublisher',
    'publish_research_deposit_slip',
    'ResearchDepositSlipConsumerMapper',
    'ResearchDepositSlipConsumerHandler',
    'handle_research_deposit_slip_update',

    # ========== Consultancy Module ==========
    'ConsultancyDepositSlipDTO',
    'ConsultancyDDetailsDTO',
    'ConsultancyEDetailsDTO',
    'ConsultancyTDetailsDTO',
    'ConsultancyODetailsDTO',
    'ConsultancyDepositSlipUpdateMessageDTO',
    'ConsultancyDepositSlipMapper',
    'ConsultancyDepositSlipValidator',
    'ConsultancyDepositSlipPublisher',
    'publish_consultancy_deposit_slip',
    'ConsultancyDepositSlipConsumerMapper',
    'ConsultancyDoctypeConfig',
    'ConsultancyDepositSlipConsumerHandler',
    'handle_consultancy_deposit_slip_update',

    # ========== Legacy/Backward Compatibility ==========
    'DepositSlipDTO',
    'DepositSlipValidator',
    'DepositSlipMapper',
    'DepositSlipPublisher',
    'publish_deposit_slip',
    'DepositSlipUpdateMessageDTO',
    'DepositSlipConsumerValidator',
    'DepositSlipConsumerMapper',
    'DepositSlipDoctypeConfig',
    'DepositSlipConsumerHandler',
    'handle_deposit_slip_update',
]
