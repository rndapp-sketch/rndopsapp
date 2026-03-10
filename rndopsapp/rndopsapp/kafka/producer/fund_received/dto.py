# Copyright (c) 2025, rndops and contributors
# Fund Received DTO - Data Transfer Objects for Fund Received Kafka events

from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class FundBudgetBreakupDTO:
    """
    Fund Budget Breakup DTO - Represents a single budget head allocation.
    """
    accountHeadId: Optional[str] = None
    amount: float = 0.0
    remarks: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class TransactionDetailsDTO:
    """
    Transaction Details DTO - Represents a single transaction detail.
    """
    uniqueTransactionNumber: str = ""
    transactionReceivedDate: Optional[str] = None
    transactionAmount: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class FundReceivedDTO:
    """
    Fund Received DTO - Contains all fund received data fields.
    Maps to the data payload expected by the accounts system.
    """
    fundReceivedRefNumberFap: str = ""
    sanctionNumber: Optional[str] = None
    sanctionLetterNo: Optional[str] = None
    projectNumber: str = ""
    amountReceived: float = 0.0
    iitgAccountNumber: str = ""
    depositSlipStatus: bool = False
    fundReceivedStatus: str = "PENDING_APPROVAL"
    depositeStatusUpdateTime: str = ""
    fundReceivedStatusUpdateTime: str = ""
    fundBudgetBreakupList: List[FundBudgetBreakupDTO] = field(default_factory=list)
    transactionDetailsList: List[TransactionDetailsDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert DTO to dictionary for JSON serialization."""
        return {
            "fundReceivedRefNumberFap": self.fundReceivedRefNumberFap,
            "sanctionNumber": self.sanctionNumber,
            "sanctionLetterNo": self.sanctionLetterNo,
            "projectNumber": self.projectNumber,
            "amountReceived": self.amountReceived,
            "iitgAccountNumber": self.iitgAccountNumber,
            "depositSlipStatus": self.depositSlipStatus,
            "fundReceivedStatus": self.fundReceivedStatus,
            "depositeStatusUpdateTime": self.depositeStatusUpdateTime,
            "fundReceivedStatusUpdateTime": self.fundReceivedStatusUpdateTime,
            "fundBudgetBreakupList": [b.to_dict() for b in self.fundBudgetBreakupList],
            "transactionDetailsList": [t.to_dict() for t in self.transactionDetailsList]
        }


@dataclass
class FundReceivedEventDTO:
    """
    Fund Received Event DTO - Kafka message envelope for fund received events.
    """
    schemaVersion: str = "1.0"
    eventType: str = "FUND_RECEIVED"
    timestamp: str = ""
    data: FundReceivedDTO = field(default_factory=FundReceivedDTO)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_kafka_payload(self) -> dict:
        """Convert to Kafka-ready payload dictionary."""
        return {
            "schemaVersion": self.schemaVersion,
            "eventType": self.eventType,
            "timestamp": self.timestamp,
            "data": self.data.to_dict()
        }
