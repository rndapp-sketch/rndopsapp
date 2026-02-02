# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip Consumer DTO
# Common DTOs merged directly into this file

from typing import List, Optional
from dataclasses import dataclass, field, asdict


# ==========================================
# Common DTOs (merged from common/dto_base.py)
# ==========================================

@dataclass
class GstDetailsDTO:
    """GST Details DTO - Used when GST is applicable (CGST_SGST or IGST)"""
    cgstPercentage: Optional[float] = None
    cgstAmount: Optional[float] = None
    sgstPercentage: Optional[float] = None
    sgstAmount: Optional[float] = None
    igstPercentage: Optional[float] = None
    igstAmount: Optional[float] = None
    totalGstAmount: float = 0.0

    def to_dict(self):
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Optional['GstDetailsDTO']:
        """Create DTO from dictionary"""
        if not data:
            return None
        return cls(
            cgstPercentage=data.get('cgstPercentage'),
            cgstAmount=data.get('cgstAmount'),
            sgstPercentage=data.get('sgstPercentage'),
            sgstAmount=data.get('sgstAmount'),
            igstPercentage=data.get('igstPercentage'),
            igstAmount=data.get('igstAmount'),
            totalGstAmount=float(data.get('totalGstAmount') or 0)
        )


@dataclass
class CreditDistributionSwfDTO:
    """Staff Welfare Fund Credit Distribution DTO"""
    swfPercentage: float = 0.0
    swfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Optional['CreditDistributionSwfDTO']:
        """Create DTO from dictionary"""
        if not data:
            return None
        return cls(
            swfPercentage=float(data.get('swfPercentage', 0)),
            swfAmount=float(data.get('swfAmount', 0))
        )


@dataclass
class CreditDistributionPdfDTO:
    """Principal Development Fund Credit Distribution DTO"""
    employeeId: str = ""
    departmentId: Optional[int] = None
    pdfPercentage: float = 0.0
    pdfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CreditDistributionPdfDTO':
        """Create DTO from dictionary"""
        return cls(
            employeeId=data.get('employeeId', ''),
            departmentId=int(data['departmentId']) if data.get('departmentId') else None,
            pdfPercentage=float(data.get('pdfPercentage', 0)),
            pdfAmount=float(data.get('pdfAmount', 0))
        )


@dataclass
class CreditDistributionDpfDTO:
    """Departmental Fund Credit Distribution DTO"""
    departmentId: Optional[int] = None
    dpfPercentage: float = 0.0
    dpfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'CreditDistributionDpfDTO':
        """Create DTO from dictionary"""
        return cls(
            departmentId=int(data['departmentId']) if data.get('departmentId') else None,
            dpfPercentage=float(data.get('dpfPercentage', 0)),
            dpfAmount=float(data.get('dpfAmount', 0))
        )


@dataclass
class CreditDistributionIdfDTO:
    """Infrastructure Development Fund Credit Distribution DTO"""
    idfPercentage: float = 0.0
    idfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Optional['CreditDistributionIdfDTO']:
        """Create DTO from dictionary"""
        if not data:
            return None
        return cls(
            idfPercentage=float(data.get('idfPercentage', 0)),
            idfAmount=float(data.get('idfAmount', 0))
        )


@dataclass
class CreditDistributionStwfDTO:
    """Student Welfare Fund Credit Distribution DTO"""
    stwfPercentage: float = 0.0
    stwfAmount: float = 0.0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Optional['CreditDistributionStwfDTO']:
        """Create DTO from dictionary"""
        if not data:
            return None
        return cls(
            stwfPercentage=float(data.get('stwfPercentage', 0)),
            stwfAmount=float(data.get('stwfAmount', 0))
        )


# ==========================================
# Research Deposit Slip Update DTO
# ==========================================

@dataclass
class ResearchDepositSlipUpdateDTO:
    """
    Research Deposit Slip Update DTO.
    Represents incoming Kafka message for Research Deposit Slip updates.
    """
    # Primary identifiers
    depositSlipRefNumFab: str = ""
    slipNumber: str = ""
    projectNumber: str = ""
    fundReceivedRefNumber: int = 0

    # Category
    category: str = "RESEARCH"

    # Amount fields
    amountReceived: float = 0.0
    amountInclusiveGst: float = 0.0
    gstType: str = "NOGST"
    finalGstAmount: float = 0.0
    finalTotalAmount: float = 0.0
    totalOverheadPercentage: float = 0.0
    totalOverheadAmount: float = 0.0
    netProjectAmount: float = 0.0

    # Account info
    ecsAccountNo: str = ""
    bankName: str = ""
    bmrNumber: str = ""

    # Status
    status: str = "APPROVED"

    # Audit fields
    createdBy: str = ""
    updatedBy: str = ""

    # Dates
    depositDate: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None

    # ECS dates
    ecsDates: List[str] = field(default_factory=list)

    # GST details (using typed DTO)
    gstDetails: Optional[GstDetailsDTO] = None

    # Credit distributions (using typed DTOs)
    creditDistributionSwf: Optional[CreditDistributionSwfDTO] = None
    creditDistributionPdf: List[CreditDistributionPdfDTO] = field(default_factory=list)
    creditDistributionDpf: List[CreditDistributionDpfDTO] = field(default_factory=list)
    creditDistributionIdf: Optional[CreditDistributionIdfDTO] = None
    creditDistributionStwf: Optional[CreditDistributionStwfDTO] = None

    @classmethod
    def from_kafka_message(cls, data: dict) -> 'ResearchDepositSlipUpdateDTO':
        """Create DTO from Kafka message data."""
        if data is None:
            data = {}

        # Parse GST details
        gst_details = GstDetailsDTO.from_dict(data.get('gstDetails'))

        # Parse credit distributions
        credit_swf = CreditDistributionSwfDTO.from_dict(data.get('creditDistributionSwf'))
        credit_idf = CreditDistributionIdfDTO.from_dict(data.get('creditDistributionIdf'))
        credit_stwf = CreditDistributionStwfDTO.from_dict(data.get('creditDistributionStwf'))

        # Parse PDF list
        pdf_list = []
        for pdf_data in data.get('creditDistributionPdf', []):
            pdf_list.append(CreditDistributionPdfDTO.from_dict(pdf_data))

        # Parse DPF list
        dpf_list = []
        for dpf_data in data.get('creditDistributionDpf', []):
            dpf_list.append(CreditDistributionDpfDTO.from_dict(dpf_data))

        return cls(
            depositSlipRefNumFab=data.get('depositSlipRefNumFab', ''),
            slipNumber=data.get('slipNumber', ''),
            projectNumber=data.get('projectNumber', ''),
            fundReceivedRefNumber=int(data.get('fundReceivedRefNumber', 0)),
            category=data.get('category', 'RESEARCH'),
            amountReceived=float(data.get('amountReceived', 0)),
            amountInclusiveGst=float(data.get('amountInclusiveGst', 0)),
            gstType=data.get('gstType', 'NOGST'),
            finalGstAmount=float(data.get('finalGstAmount', 0)),
            finalTotalAmount=float(data.get('finalTotalAmount', 0)),
            totalOverheadPercentage=float(data.get('totalOverheadPercentage', 0)),
            totalOverheadAmount=float(data.get('totalOverheadAmount', 0)),
            netProjectAmount=float(data.get('netProjectAmount', 0)),
            ecsAccountNo=data.get('ecsAccountNo', ''),
            bankName=data.get('bankName', ''),
            bmrNumber=data.get('bmrNumber', ''),
            status=data.get('status', 'APPROVED'),
            createdBy=data.get('createdBy', ''),
            updatedBy=data.get('updatedBy', ''),
            depositDate=data.get('depositDate'),
            createdAt=data.get('createdAt'),
            updatedAt=data.get('updatedAt'),
            ecsDates=data.get('ecsDates', []),
            gstDetails=gst_details,
            creditDistributionSwf=credit_swf,
            creditDistributionPdf=pdf_list,
            creditDistributionDpf=dpf_list,
            creditDistributionIdf=credit_idf,
            creditDistributionStwf=credit_stwf
        )

    def to_dict(self) -> dict:
        """Convert DTO to dictionary for processing."""
        data = {
            "depositSlipRefNumFab": self.depositSlipRefNumFab,
            "slipNumber": self.slipNumber,
            "projectNumber": self.projectNumber,
            "fundReceivedRefNumber": self.fundReceivedRefNumber,
            "category": self.category,
            "amountReceived": self.amountReceived,
            "amountInclusiveGst": self.amountInclusiveGst,
            "gstType": self.gstType,
            "finalGstAmount": self.finalGstAmount,
            "finalTotalAmount": self.finalTotalAmount,
            "totalOverheadPercentage": self.totalOverheadPercentage,
            "totalOverheadAmount": self.totalOverheadAmount,
            "netProjectAmount": self.netProjectAmount,
            "ecsAccountNo": self.ecsAccountNo,
            "bankName": self.bankName,
            "bmrNumber": self.bmrNumber,
            "status": self.status,
            "createdBy": self.createdBy,
            "updatedBy": self.updatedBy,
            "depositDate": self.depositDate,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "ecsDates": self.ecsDates,
        }

        if self.gstDetails:
            data["gstDetails"] = self.gstDetails.to_dict()

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
