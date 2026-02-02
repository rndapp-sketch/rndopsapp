# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip DTO
# Common DTOs merged directly into this file

from typing import List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


# ==========================================
# Common DTOs (Credit Distribution only - no GST for Research)
# ==========================================

@dataclass
class CreditDistributionSwfDTO:
    """Staff Welfare Fund Credit Distribution DTO"""
    swfPercentage: float = 0.0
    swfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class CreditDistributionPdfDTO:
    """Principal Development Fund Credit Distribution DTO"""
    employeeId: str = ""
    departmentId: Optional[int] = None
    pdfPercentage: float = 0.0
    pdfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class CreditDistributionDpfDTO:
    """Departmental Fund Credit Distribution DTO"""
    departmentId: Optional[int] = None
    dpfPercentage: float = 0.0
    dpfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class CreditDistributionIdfDTO:
    """Infrastructure Development Fund Credit Distribution DTO"""
    idfPercentage: float = 0.0
    idfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class CreditDistributionStwfDTO:
    """Student Welfare Fund Credit Distribution DTO"""
    stwfPercentage: float = 0.0
    stwfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)


# ==========================================
# Research Deposit Slip DTO
# ==========================================

@dataclass
class ResearchDepositSlipDTO:
    """
    Research Deposit Slip DTO.
    Matches the JSON format expected by the accounts system for RESEARCH category.
    """
    # Basic fields
    projectNumber: str = ""
    fundReceivedRefNumber: int = 0
    slipNumber: str = ""
    depositSlipRefNumFab: str = ""  # Frappe deposit slip document name
    category: str = "RESEARCH"  # Always "RESEARCH" for this DTO
    ecsAccountNo: str = ""
    bankName: str = ""
    bmrNumber: str = ""

    # Amount fields
    amountReceived: float = 0.0
    amountInclusiveGst: float = 0.0
    gstType: str = "NOGST"  # "NOGST", "CGST_SGST", or "IGST"
    finalGstAmount: float = 0.0
    finalTotalAmount: float = 0.0
    totalOverheadPercentage: float = 0.0
    totalOverheadAmount: float = 0.0
    netProjectAmount: float = 0.0

    # Date fields (ISO 8601 format)
    depositDate: str = ""
    createdAt: str = ""
    updatedAt: str = ""

    # Audit fields
    createdBy: str = ""
    updatedBy: str = ""
    status: str = "APPROVED"

    # ECS dates
    ecsDates: List[str] = field(default_factory=list)

    # Credit distributions
    creditDistributionSwf: Optional[CreditDistributionSwfDTO] = None
    creditDistributionPdf: List[CreditDistributionPdfDTO] = field(default_factory=list)
    creditDistributionDpf: List[CreditDistributionDpfDTO] = field(default_factory=list)
    creditDistributionIdf: Optional[CreditDistributionIdfDTO] = None
    creditDistributionStwf: Optional[CreditDistributionStwfDTO] = None

    def to_dict(self) -> dict:
        """
        Convert DTO to dictionary for JSON serialization.
        Matches the required Kafka payload structure exactly.
        """
        data = {
            "projectNumber": self.projectNumber,
            "fundReceivedRefNumber": self.fundReceivedRefNumber,
            "slipNumber": self.slipNumber,
            "depositSlipRefNumFab": self.depositSlipRefNumFab,
            "category": self.category,
            "ecsAccountNo": self.ecsAccountNo,
            "bankName": self.bankName,
            "bmrNumber": self.bmrNumber,
            "amountReceived": self.amountReceived,
            "amountInclusiveGst": self.amountInclusiveGst,
            "gstType": self.gstType,
            "finalGstAmount": self.finalGstAmount,
            "finalTotalAmount": self.finalTotalAmount,
            "totalOverheadPercentage": self.totalOverheadPercentage,
            "totalOverheadAmount": self.totalOverheadAmount,
            "netProjectAmount": self.netProjectAmount,
            "depositDate": self.depositDate,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "createdBy": self.createdBy,
            "updatedBy": self.updatedBy,
            "status": self.status,
            "ecsDates": self.ecsDates,
        }

        # Add fundReceivedRefNumberFap if set by mapper (links deposit slip to fund received by doc name)
        # if hasattr(self, 'fundReceivedRefNumberFap') and self.fundReceivedRefNumberFap:
        #     data["fundReceivedRefNumberFap"] = self.fundReceivedRefNumberFap

        # Add credit distributions
        if self.creditDistributionSwf:
            data["creditDistributionSwf"] = self.creditDistributionSwf.to_dict()

        if self.creditDistributionPdf:
            data["creditDistributionPdf"] = [pdf.to_dict() for pdf in self.creditDistributionPdf]

        if self.creditDistributionDpf:
            data["creditDistributionDpf"] = [dpf.to_dict() for dpf in self.creditDistributionDpf]

        if self.creditDistributionIdf:
            data["creditDistributionIdf"] = self.creditDistributionIdf.to_dict()

        if self.creditDistributionStwf:
            data["creditDistributionStwf"] = self.creditDistributionStwf.to_dict()

        return data

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
            "eventType": "DEPOSIT_SLIP",
            "timestamp": datetime.utcnow().isoformat(),
            "data": self.to_dict()
        }
