# Copyright (c) 2025, rndops and contributors
# Consultancy Deposit Slip DTOs
# Supports: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT

from typing import List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from ..common.dto_base import (
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)


@dataclass
class ConsultancyDDetailsDTO:
    """
    Consultancy D Details DTO.
    Used for CONSULTANCY_D category with complex financial calculations.
    """
    gstTdsPercentage: float = 0.0
    gstTdsAmount: float = 0.0
    amountReceivedAfterGstTds: float = 0.0
    totalCostX: float = 0.0
    consultancyChargeYPercentage: float = 0.0
    consultancyChargeY: float = 0.0
    operationalChargeZPercentage: float = 0.0
    operationalChargeZ: float = 0.0
    overHeadYPercentage: float = 0.0
    overHeadYAmount: float = 0.0
    overHeadZPercentage: float = 0.0
    overHeadZAmount: float = 0.0
    instituteSharePercentage: float = 0.0
    instituteShare: float = 0.0
    totalOverHeadInstituteShare: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class ConsultancyEDetailsDTO:
    """
    Consultancy E Details DTO.
    Used for CONSULTANCY_E (E Non-Routine) category.
    """
    consultancyFeeX_trainingFee: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class ConsultancyTDetailsDTO:
    """
    Consultancy T Details DTO.
    Used for CONSULTANCY_T (T Testing) category.
    """
    consultancyFeeX_trainingFee: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class ConsultancyODetailsDTO:
    """
    Consultancy O (Other Event) Details DTO.
    Used for OTHER_EVENT category.
    """
    consultancyFeeX_trainingFee: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass
class ConsultancyDepositSlipDTO:
    """
    Consultancy Deposit Slip DTO.
    Supports multiple categories: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT
    """
    # Basic fields
    projectNumber: str = ""
    fundReceivedRefNumber: int = 0
    depositSlipRefNumFab: str = ""
    slipNumber: str = ""
    category: str = "CONSULTANCY_D"  # CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT
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

    # GST details (optional, only when gstType != NOGST)
    gstDetails: Optional[GstDetailsDTO] = None

    # Credit distributions
    creditDistributionSwf: Optional[CreditDistributionSwfDTO] = None
    creditDistributionPdf: List[CreditDistributionPdfDTO] = field(default_factory=list)
    creditDistributionDpf: List[CreditDistributionDpfDTO] = field(default_factory=list)
    creditDistributionIdf: Optional[CreditDistributionIdfDTO] = None
    creditDistributionStwf: Optional[CreditDistributionStwfDTO] = None

    # Category-specific details (only one will be present based on category)
    consultancyDDetails: Optional[ConsultancyDDetailsDTO] = None
    consultancyEDetails: Optional[ConsultancyEDetailsDTO] = None
    consultancyTDetails: Optional[ConsultancyTDetailsDTO] = None
    consultancyODetails: Optional[ConsultancyODetailsDTO] = None

    def to_dict(self) -> dict:
        """
        Convert DTO to dictionary for JSON serialization.
        Handles nested objects and category-specific details properly.
        """
        data = {
            "projectNumber": self.projectNumber,
            "fundReceivedRefNumber": self.fundReceivedRefNumber,
            "depositSlipRefNumFab": self.depositSlipRefNumFab,
            "slipNumber": self.slipNumber,
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

        # Add GST details only if GST is applicable
        if self.gstDetails and self.gstType != "NOGST":
            data["gstDetails"] = self.gstDetails.to_dict()

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

        # Add category-specific details based on category
        if self.category == "CONSULTANCY_D" and self.consultancyDDetails:
            data["consultancyDDetails"] = self.consultancyDDetails.to_dict()
        elif self.category == "CONSULTANCY_E" and self.consultancyEDetails:
            data["consultancyEDetails"] = self.consultancyEDetails.to_dict()
        elif self.category == "CONSULTANCY_T" and self.consultancyTDetails:
            data["consultancyTDetails"] = self.consultancyTDetails.to_dict()
        elif self.category == "OTHER_EVENT" and self.consultancyODetails:
            data["consultancyODetails"] = self.consultancyODetails.to_dict()

        return data

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        """
        Wrap DTO in Kafka message envelope.

        Args:
            schema_version: Schema version for the payload

        Returns:
            dict: Wrapped payload ready for Kafka publishing
        """
        # Determine event type based on category
        event_type = f"DEPOSIT_SLIP_{self.category}"

        return {
            "schemaVersion": schema_version,
            "eventType": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": self.to_dict()
        }
