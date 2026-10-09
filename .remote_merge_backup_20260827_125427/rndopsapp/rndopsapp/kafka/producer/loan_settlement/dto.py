# Copyright (c) 2026, rndops and contributors
# Loan Settlement DTO - Data Transfer Objects for Loan Settlement Kafka events

from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class LoanSettlementBudgetBreakupDTO:
    """
    One head-wise row of a settlement: how much of it comes back against which account
    head.

    Deliberately just the two fields — the Accounts service's consumer expects
    [{"accountHeadId": 3, "amount": 15000.00}, ...] and nothing more. loanNumber /
    loanSettlementNumber / projectNumber are NOT repeated per row: they are already on
    the parent settlement object, which is what these rows belong to.
    """
    accountHeadId: Optional[int] = None
    amount: float = 0.0

    def to_dict(self) -> dict:
        return {
            "accountHeadId": self.accountHeadId,
            "amount": self.amount,
        }


@dataclass
class LoanSettlementDTO:
    """
    Loan Settlement DTO — the settlement object the Accounts service consumes on the
    loan-settlement-events topic.

    Field contract (from the Accounts service's Kafka Producer Integration Guide):
      loanNumber            int    REQUIRED  their internal loan id (not our docname)
      projectNumber         str    REQUIRED
      loanSettlementNumber  str    REQUIRED  idempotency key — our Frappe docname
      frapAppId             str    optional  our Loan Request docname (= their loanNumberFap)
      fundReceivedRefNumberFap
                            str    REQUIRED  the Fund Received docname this settlement was
                                             raised from — the SAME value Fund Received's own
                                             event publishes as fundReceivedRefNumberFap
                                             (fund_received/mapper.py sends doc.name). This is
                                             what ties a settlement to its receipt on the
                                             Accounts side; without it the settlement stores
                                             NULL, no receipt shows it, and nothing cascades.
      settlementAmount      float  REQUIRED  must be > 0
      settlementDate        str    optional  yyyy-MM-dd
      settlementMode        str    optional  free text, not enum-validated on their side
      remarks               str    optional
      settlementStatus      str              always "PENDING" from us — the Accounts side
                                             lists these as pending and then confirms,
                                             rejects, or rectifies them. We never send any
                                             other value; the outcome lives on their side.
      loanSettlementBudgetBreakupDetails
                            list            head-wise split of settlementAmount; always
                                            sums to it. Omitted only if a settlement
                                            somehow has no head rows.

    Never send settlementId / recordTime / updatedLoanStatus / totalSettled /
    outstandingAmount — those are response-only fields on their side.
    """
    loanNumber: Optional[int] = None
    projectNumber: str = ""
    loanSettlementNumber: str = ""
    frapAppId: Optional[str] = None
    fundReceivedRefNumberFap: Optional[str] = None
    settlementAmount: float = 0.0
    settlementDate: Optional[str] = None
    settlementMode: Optional[str] = None
    remarks: Optional[str] = None
    settlementStatus: str = "PENDING"
    loanSettlementBudgetBreakupDetails: List[LoanSettlementBudgetBreakupDTO] = field(
        default_factory=list
    )

    def to_dict(self) -> dict:
        """Serialise, omitting optional keys that are empty.

        The consumer treats frapAppId / settlementDate / settlementMode / remarks as
        optional, so omitting them entirely is cleaner (and less ambiguous) than
        sending nulls.
        """
        payload = {
            "loanNumber": self.loanNumber,
            "projectNumber": self.projectNumber,
            "loanSettlementNumber": self.loanSettlementNumber,
            "settlementAmount": self.settlementAmount,
            # Always PENDING on publish — Accounts owns the confirm/reject/rectify outcome.
            "settlementStatus": self.settlementStatus,
        }

        if self.frapAppId:
            payload["frapAppId"] = self.frapAppId
        if self.fundReceivedRefNumberFap:
            payload["fundReceivedRefNumberFap"] = self.fundReceivedRefNumberFap
        if self.settlementDate:
            payload["settlementDate"] = self.settlementDate
        if self.settlementMode:
            payload["settlementMode"] = self.settlementMode
        if self.remarks:
            payload["remarks"] = self.remarks
        if self.loanSettlementBudgetBreakupDetails:
            payload["loanSettlementBudgetBreakupDetails"] = [
                row.to_dict() for row in self.loanSettlementBudgetBreakupDetails
            ]

        return payload


@dataclass
class LoanSettlementEventDTO:
    """
    Kafka message envelope for Loan Settlement events.

    Matches the common envelope required by both loan-settlement-events and
    loan-settlement-events-batch. We publish to the singular topic, so `data` is a
    single object.
    """
    schemaVersion: str = "1.0"
    eventType: str = "LOAN_SETTLEMENT"
    timestamp: str = ""
    data: LoanSettlementDTO = field(default_factory=LoanSettlementDTO)

    def __post_init__(self):
        if not self.timestamp:
            # Their guide specifies yyyy-MM-dd'T'HH:mm:ss.SSSSSS — isoformat() with
            # microseconds produces exactly that.
            self.timestamp = datetime.utcnow().isoformat()

    def to_kafka_payload(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "eventType": self.eventType,
            "timestamp": self.timestamp,
            "data": self.data.to_dict(),
        }
