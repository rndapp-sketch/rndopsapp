from datetime import datetime, date
from typing import List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


# ======================================================
# COMMON PARSERS (DATE / DATETIME)
# ======================================================

def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    # Already a datetime object
    if isinstance(value, datetime):
        return value

    # ISO-8601 string
    if isinstance(value, str):
        return datetime.fromisoformat(value)

    # [YYYY, MM, DD, HH, MM, SS, nano]
    if isinstance(value, list):
        while len(value) < 6:
            value.append(0)
        return datetime(
            value[0], value[1], value[2],
            value[3], value[4], value[5]
        )

    raise ValueError("Invalid datetime format")


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    # Already a date object
    if isinstance(value, date):
        return value

    # ISO date string
    if isinstance(value, str):
        return date.fromisoformat(value)

    # [YYYY, MM, DD]
    if isinstance(value, list):
        return date(value[0], value[1], value[2])

    raise ValueError("Invalid date format")


# ======================================================
# PROJECT DATA DTO (BUSINESS LOGIC)
# ======================================================

class ProjectDataDTO(BaseModel):
    projectNumber: str
    empId: str
    departmentId: Union[str, int]
    projectType: str
    projectCategory: Optional[str] = None
    fundingAgencyType: str
    fundingAgencyId: Union[str, int]
    projectScheme: str

    totalBudgetAmount: float
    overHeadAmountPercentage: float
    overHeadAmount: float = 0.0
    budgetWithOverHeadAmount: float = 0.0
    gst: float = 0.0
    grandTotal: float = 0.0

    startDate: Optional[date] = None
    completionDate: Optional[date] = None
    durationInDays: str = "0"  # String format, defaults to "0"
    # gstinNumber: Optional[str] = None  # Not needed in Kafka
    # projectImplementationLocation: Optional[str] = None  # Not needed in Kafka
    # verdictDate: Optional[date] = None  # Not needed in Kafka
    durationMonths: str = "0"  # String format, defaults to "0"
    status: str

    applyDate: Optional[datetime] = None
    implementedDeptCentres: List[str] = Field(default_factory=list)

    # -------- DATE NORMALIZATION --------
    @field_validator("startDate", "completionDate", mode="before")  # Removed verdictDate
    @classmethod
    def normalize_date(cls, v):
        return parse_date(v)

    @field_validator("applyDate", mode="before")
    @classmethod
    def normalize_datetime(cls, v):
        return parse_datetime(v)

    # -------- COMMON CALCULATION LOGIC --------
    def calculate_amounts(self, gst_percentage: float = 18.0):
        self.overHeadAmount = (
            self.totalBudgetAmount * self.overHeadAmountPercentage / 100
        )
        self.budgetWithOverHeadAmount = (
            self.totalBudgetAmount + self.overHeadAmount
        )
        self.gst = (
            self.budgetWithOverHeadAmount * gst_percentage / 100
        )
        self.grandTotal = (
            self.budgetWithOverHeadAmount + self.gst
        )


# ======================================================
# EVENT DTO
# ======================================================

class ProjectEventDTO(BaseModel):
    schemaVersion: str
    eventType: str
    timestamp: datetime
    data: ProjectDataDTO

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v):
        return parse_datetime(v)


# ======================================================
# EXAMPLE USAGE (OPTIONAL)
# ======================================================
if __name__ == "__main__":
    import json

    payload = """{
        "schemaVersion": "1.0",
        "eventType": "PROJECT_REGISTRATION",
        "timestamp": [2026,1,2,6,41,0,333169580],
        "data": {
            "projectNumber": "TEST-PRJ-001",
            "empId": "EMP001",
            "departmentId": "DEPT-IT",
            "projectType": "Research",
            "projectCategory": "Internal",
            "fundingAgencyType": "Government",
            "fundingAgencyId": "GOV-001",
            "projectScheme": "SCHEME-A",
            "totalBudgetAmount": 500000,
            "overHeadAmountPercentage": 10,
            "startDate": [2026,1,2],
            "completionDate": [2027,1,2],
            "durationMonths": 12,
            "status": "ACTIVE",
            "applyDate": [2026,1,2,6,41,0,333119164],
            "implementedDeptCentres": ["1", "2"]
        }
    }"""

    event = ProjectEventDTO.model_validate(json.loads(payload))
    event.data.calculate_amounts()

    print(event.model_dump())
