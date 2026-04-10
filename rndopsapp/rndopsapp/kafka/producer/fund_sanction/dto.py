# Copyright (c) 2025, rndops and contributors
# Fund Sanction DTO - Data Transfer Objects for Fund Sanction Kafka events

from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class BudgetBreakupDTO:
    """
    Budget Breakup DTO - Represents a single budget head allocation.
    """
    accountHeadId: Optional[int] = None
    accountHeadAmount: float = 0.0
    firstYearBudget: float = 0.0
    secondYearBudget: float = 0.0
    thirdYearBudget: float = 0.0
    fourthYearBudget: float = 0.0
    fifthYearBudget: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class FundSanctionDTO:
    """
    Fund Sanction DTO - Contains all fund sanction data fields.
    Maps to the data payload expected by the accounts system.
    """
    projectNumber: str = ""
    sanctionLetterNo: Optional[str] = None
    sanctionLetterDate: Optional[str] = None
    totalSanctionAmount: float = 0.0
    budgetBreakups: List[BudgetBreakupDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert DTO to dictionary for JSON serialization."""
        return {
            "projectNumber": self.projectNumber,
            "sanctionLetterNo": self.sanctionLetterNo,
            "sanctionLetterDate": self.sanctionLetterDate,
            "totalSanctionAmount": self.totalSanctionAmount,
            "budgetBreakups": [b.to_dict() for b in self.budgetBreakups]
        }


@dataclass
class FundSanctionEventDTO:
    """
    Fund Sanction Event DTO - Kafka message envelope for fund sanction events.
    """
    schemaVersion: str = "1.0"
    eventType: str = "FUND_SANCTION"
    timestamp: str = ""
    data: FundSanctionDTO = field(default_factory=FundSanctionDTO)

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
