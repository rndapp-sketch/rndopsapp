# Copyright (c) 2025, rndops and contributors
# Base DTOs shared across Research and Consultancy modules

from typing import Optional
from dataclasses import dataclass, asdict


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
