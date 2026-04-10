# Copyright (c) 2025, rndops and contributors
# Reimbursement Commit and Payment DTOs

from typing import Optional
from dataclasses import dataclass, asdict


# ==========================================
# Account Head Commit DTO
# ==========================================

@dataclass
class AccountHeadCommitDTO:
    """
    Account Head Commit DTO for Reimbursement.
    Represents a commitment transaction.
    """
    projectNumber: str = ""
    accountHeadId: Optional[int] = None
    commitAmount: float = 0.0
    commitDate: str = ""
    commitParticular: str = ""
    refDetails: str = ""
    status: str = "COMMITTED"

    # Module information
    frapAppId: str = ""
    moduleId: Optional[int] = None

    # Optional fields
    transactionCommitNumber: Optional[int] = None
    transactionReceivedRefNumber: Optional[int] = None
    billAmount: Optional[float] = None

    def to_dict(self) -> dict:
        """Convert DTO to dictionary for JSON serialization."""
        return {
            "transactionCommitNumber": self.transactionCommitNumber,
            "projectNumber": self.projectNumber,
            "accountHeadId": self.accountHeadId,
            "transactionReceivedRefNumber": self.transactionReceivedRefNumber,
            "commitDate": self.commitDate,
            "commitParticular": self.commitParticular,
            "refDetails": self.refDetails,
            "commitAmount": self.commitAmount,
            "status": self.status,
            # "moduleName": self.moduleName, 
            "frapAppId":self.frapAppId,
            "moduleId": self.moduleId,
            "billAmount": self.billAmount
        }


# ==========================================
# Account Head Payment DTO
# ==========================================

@dataclass
class AccountHeadPaymentDTO:
    """
    Account Head Payment DTO for Reimbursement.
    Represents a payment transaction.
    """
    projectNumber: str = ""
    accountHeadId: Optional[int] = None
    paymentAmount: float = 0.0
    paymentDate: str = ""
    paymentParticular: str = ""
    paymentRefDetails: str = ""
    paymentStatus: str = "PAID"

    # Module information
    frapAppId: str = ""
    moduleId: Optional[int] = None

    # Optional fields
    transactionPaymentNumber: Optional[int] = None
    transactionCommitNumber: Optional[int] = None
    bmr: Optional[str] = None
    bankTransactionNumber: Optional[str] = None
    bankTransactionDate: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert DTO to dictionary for JSON serialization."""
        return {
            "transactionPaymentNumber": self.transactionPaymentNumber,
            "transactionCommitNumber": self.transactionCommitNumber,
            "projectNumber": self.projectNumber,
            "accountHeadId": self.accountHeadId,
            "paymentDate": self.paymentDate,
            "paymentParticular": self.paymentParticular,
            "paymentRefDetails": self.paymentRefDetails,
            "paymentAmount": self.paymentAmount,
            "bmr": self.bmr,
            "paymentStatus": self.paymentStatus,
            "bankTransactionNumber": self.bankTransactionNumber,
            "bankTransactionDate": self.bankTransactionDate,
            "frapAppId":self.frapAppId,
            "moduleId": self.moduleId
        }
