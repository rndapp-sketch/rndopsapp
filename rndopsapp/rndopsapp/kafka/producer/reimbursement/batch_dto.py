# Copyright (c) 2026, rndops and contributors
# Batch DTO for Account Head Commit batch publishing

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class AccountHeadCommitBatchItemDTO:
    """One row inside a batch commit event — mirrors the REST batch API body shape."""
    transactionCommitNumber: Optional[int]
    projectNumber: str
    accountHeadId: Optional[int]
    transactionReceivedRefNumber: Optional[int]
    commitDate: str
    commitParticular: str
    refDetails: Optional[int]
    commitAmount: float
    status: str
    billAmount: Optional[float]
    moduleId: Optional[str]
    frapAppId: str

    def to_dict(self) -> dict:
        return {
            "transactionCommitNumber":     self.transactionCommitNumber,
            "projectNumber":               self.projectNumber,
            "accountHeadId":               self.accountHeadId,
            "transactionReceivedRefNumber": self.transactionReceivedRefNumber,
            "commitDate":                  self.commitDate,
            "commitParticular":            self.commitParticular,
            "refDetails":                  self.refDetails,
            "commitAmount":                self.commitAmount,
            "status":                      self.status,
            "billAmount":                  self.billAmount,
            "moduleId":                    self.moduleId,
            "frapAppId":                   self.frapAppId,
        }


@dataclass
class AccountHeadCommitBatchEvent:
    """
    Kafka envelope for a batch of account-head commit items.

    Shape published to topic ``account-head-commit-batch-events``:
    {
        "schemaVersion": "1.0",
        "eventType": "ACCOUNT_HEAD_COMMIT_BATCH",
        "timestamp": "...",
        "data": [ { ...AccountHeadCommitBatchItemDTO... }, ... ]
    }
    """
    items: List[AccountHeadCommitBatchItemDTO]

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        return {
            "schemaVersion": schema_version,
            "eventType":     "ACCOUNT_HEAD_COMMIT_BATCH",
            "timestamp":     datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "data":          [item.to_dict() for item in self.items],
        }
