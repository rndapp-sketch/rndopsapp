# Copyright (c) 2026, rndops and contributors
# Loan Request DTO - Data Transfer Objects for Loan Request Kafka events

from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class LoanBudgetBreakupDTO:
    """
    Represents a single budget head allocation in the loan breakup.
    """
    accountHeadId: Optional[str] = None
    amount: float = 0.0
    projectNumber: str = ""
    remarks: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LoanRequestDTO:
    """
    Loan Request DTO - Contains all loan request data fields.
    Maps to the payload expected by the accounts system on loan-request-event topic.
    """
    loanStatus: str = "LOAN_APPROVED"
    loanReceivedDate: Optional[str] = None
    projectNumber: str = ""
    loanNumberFap: str = ""
    receivedFrom: str = ""
    loanType: str = ""
    loanAmount: float = 0.0
    depositStatus: str = "PENDING"
    bmr: Optional[str] = None
    bmrDate: Optional[str] = None
    loanBudgetBreakupDetails: List[LoanBudgetBreakupDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "loanStatus": self.loanStatus,
            "loanReceivedDate": self.loanReceivedDate,
            "projectNumber": self.projectNumber,
            "loanNumberFap": self.loanNumberFap,
            "receivedFrom": self.receivedFrom,
            "loanType": self.loanType,
            "loanAmount": self.loanAmount,
            "depositStatus": self.depositStatus,
            "bmr": self.bmr,
            "bmrDate": self.bmrDate,
            "loanBudgetBreakupDetails": [b.to_dict() for b in self.loanBudgetBreakupDetails],
        }


@dataclass
class LoanRequestEventDTO:
    """
    Kafka message envelope for Loan Request events.
    """
    schemaVersion: str = "1.0"
    eventType: str = "LOAN_REQUEST"
    timestamp: str = ""
    data: LoanRequestDTO = field(default_factory=LoanRequestDTO)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_kafka_payload(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "eventType": self.eventType,
            "timestamp": self.timestamp,
            "data": self.data.to_dict(),
        }
