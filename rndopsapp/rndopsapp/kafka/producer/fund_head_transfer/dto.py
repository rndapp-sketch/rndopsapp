# Copyright (c) 2026, rndops and contributors
# Fund Head Transfer DTO - Data Transfer Objects for head-to-head transfer Kafka events

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class FundHeadTransferDTO:
    """
    An approved Acc Head to Head Fund Transfer, as the Accounts service consumes it on
    the fund-head-transfer-events topic.

      transferRefNumber         str    REQUIRED  our Frappe docname — the idempotency key
      projectNumber             str    REQUIRED
      fundReceivedRefNumberFap  str    REQUIRED  the Fund Received docname the moved money
                                                 came in on — the SAME value Fund Received's
                                                 own event publishes (fund_received/mapper.py
                                                 sends doc.name). See the mapper for which
                                                 receipt is chosen when there are several.
      fromAccountHeadId         int    REQUIRED  ledger id of the head money leaves
      toAccountHeadId           int    REQUIRED  ledger id of the head money goes to
      amount                    float  REQUIRED  must be > 0
      reason                    str    optional  the applicant's justification
      transferredBy             str    optional  applicant webmail
      transferredAt             str    optional  yyyy-MM-ddTHH:mm:ss, when it was approved
    """
    transferRefNumber: str = ""
    projectNumber: str = ""
    fundReceivedRefNumberFap: Optional[str] = None
    fromAccountHeadId: Optional[int] = None
    toAccountHeadId: Optional[int] = None
    amount: float = 0.0
    reason: Optional[str] = None
    transferredBy: Optional[str] = None
    transferredAt: Optional[str] = None

    def to_dict(self) -> dict:
        payload = {
            "transferRefNumber": self.transferRefNumber,
            "projectNumber": self.projectNumber,
            "fundReceivedRefNumberFap": self.fundReceivedRefNumberFap,
            "fromAccountHeadId": self.fromAccountHeadId,
            "toAccountHeadId": self.toAccountHeadId,
            "amount": self.amount,
        }

        # Optional keys are omitted when empty rather than sent as nulls.
        if self.reason:
            payload["reason"] = self.reason
        if self.transferredBy:
            payload["transferredBy"] = self.transferredBy
        if self.transferredAt:
            payload["transferredAt"] = self.transferredAt

        return payload


@dataclass
class FundHeadTransferEventDTO:
    """Kafka message envelope for Fund Head Transfer events."""
    schemaVersion: str = "1.0"
    eventType: str = "FUND_HEAD_TRANSFER"
    timestamp: str = ""
    data: FundHeadTransferDTO = field(default_factory=FundHeadTransferDTO)

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
