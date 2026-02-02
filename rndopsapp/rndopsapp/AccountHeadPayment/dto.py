# Copyright (c) 2025, rndops and contributors
# AccountHeadPayment DTO for Kafka Producer

from typing import Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PaymentStatus(Enum):
    """Payment status enum matching accounts system expectations."""
    PENDING = "PENDING"
    PAID = "PAID"
    REJECTED = "REJECTED"
    RECTIFICATION = "RECTIFICATION"


@dataclass
class AccountHeadPaymentDTO:
    """
    AccountHeadPayment DTO for Kafka producer.
    Matches the Java AccountHeadPaymentDto expected by the accounts system.
    """
    # Transaction identifiers
    transactionPaymentNumber: Optional[int] = None
    transactionCommitNumber: int = 0

    # Project and account info
    projectNumber: str = ""
    accountHeadId: int = 0

    # Payment details
    paymentDate: str = ""  # Format: yyyy-MM-dd
    paymentParticular: str = ""
    paymentRefDetails: str = ""
    paymentAmount: float = 0.0
    bmr: str = ""

    # Payment status
    paymentStatus: str = "PENDING"  # PENDING, PAID, REJECTED, RECTIFICATION

    # Bank transaction details
    bankTransactionNumber: str = ""
    bankTransactionDate: str = ""  # Format: yyyy-MM-dd

    def to_dict(self) -> dict:
        """
        Convert DTO to dictionary for JSON serialization.
        """
        return {
            "transactionPaymentNumber": self.transactionPaymentNumber,
            "transactionCommitNumber": self.transactionCommitNumber,
            "projectNumber": self.projectNumber,
            "accountHeadId": self.accountHeadId,
            "paymentDate": self.paymentDate if self.paymentDate else None,
            "paymentParticular": self.paymentParticular,
            "paymentRefDetails": self.paymentRefDetails,
            "paymentAmount": self.paymentAmount,
            "bmr": self.bmr,
            "paymentStatus": self.paymentStatus,
            "bankTransactionNumber": self.bankTransactionNumber,
            "bankTransactionDate": self.bankTransactionDate if self.bankTransactionDate else None,
        }

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        """
        Wrap DTO in Kafka message envelope.

        Args:
            schema_version: Schema version for the payload

        Returns:
            dict: Wrapped payload ready for Kafka publishing
        """
        return {
            "schemaVersion": schema_version,
            "eventType": "ACCOUNT_HEAD_PAYMENT",
            "timestamp": datetime.utcnow().isoformat(),
            "data": self.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountHeadPaymentDTO":
        """
        Create DTO from dictionary.

        Args:
            data: Dictionary with payment data

        Returns:
            AccountHeadPaymentDTO instance
        """
        return cls(
            transactionPaymentNumber=data.get("transactionPaymentNumber"),
            transactionCommitNumber=data.get("transactionCommitNumber", 0),
            projectNumber=data.get("projectNumber", ""),
            accountHeadId=data.get("accountHeadId", 0),
            paymentDate=data.get("paymentDate", ""),
            paymentParticular=data.get("paymentParticular", ""),
            paymentRefDetails=data.get("paymentRefDetails", ""),
            paymentAmount=data.get("paymentAmount", 0.0),
            bmr=data.get("bmr", ""),
            paymentStatus=data.get("paymentStatus", "PENDING"),
            bankTransactionNumber=data.get("bankTransactionNumber", ""),
            bankTransactionDate=data.get("bankTransactionDate", ""),
        )
