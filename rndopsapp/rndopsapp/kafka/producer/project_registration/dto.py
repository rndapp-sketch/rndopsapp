# Copyright (c) 2025, rndops and contributors
# Project Registration DTO - Data Transfer Objects for Project Registration Kafka events

from datetime import datetime, date
from typing import List, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


def parse_datetime(value: Any) -> Optional[datetime]:
    """Parse various datetime formats to datetime object."""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(value)

    if isinstance(value, list):
        while len(value) < 6:
            value.append(0)
        return datetime(
            value[0], value[1], value[2],
            value[3], value[4], value[5]
        )

    raise ValueError("Invalid datetime format")


def parse_date(value: Any) -> Optional[date]:
    """Parse various date formats to date object."""
    if value is None:
        return None

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value)

    if isinstance(value, list) and len(value) >= 3:
        return date(value[0], value[1], value[2])

    raise ValueError("Invalid date format")


class ProjectDataDTO(BaseModel):
    """
    Project Data DTO - Contains all project registration data fields.
    Maps to the data payload expected by the accounts system.
    """
    projectNumber: str
    empId: str
    departmentId: Union[str, int]
    projectType: str
    projectCategory: Optional[str] = None
    fundingAgencyType: str
    fundingAgencyId: Union[str, int]
    projectScheme: str

    # Budget amounts
    totalBudgetAmount: float
    overHeadAmountPercentage: float
    overHeadAmount: float = 0.0
    budgetWithOverHeadAmount: float = 0.0
    gst: float = 0.0
    grandTotal: float = 0.0

    # Dates
    startDate: str = "0000-00-00"
    completionDate: str = "0000-00-00"
    durationInDays: str = "0"
    durationMonths: str = "00"

    # Status
    status: str
    applyDate: Optional[datetime] = None

    # Implementation departments
    implementedDeptCentres: List[str] = Field(default_factory=list)

    @field_validator("startDate", "completionDate", mode="before")
    @classmethod
    def normalize_date(cls, v):
        if v is None or v == "":
            return "0000-00-00"
        if isinstance(v, str):
            return v
        if isinstance(v, date):
            return v.isoformat()
        if isinstance(v, list) and len(v) >= 3:
            return date(v[0], v[1], v[2]).isoformat()
        return "0000-00-00"

    @field_validator("applyDate", mode="before")
    @classmethod
    def normalize_datetime(cls, v):
        return parse_datetime(v)

    def calculate_amounts(self, gst_percentage: float = 18.0):
        """Calculate derived amounts based on total budget and overhead percentage."""
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


class ProjectEventDTO(BaseModel):
    """
    Project Event DTO - Kafka message envelope for project registration events.
    Contains schema version, event type, timestamp and the project data.
    """
    schemaVersion: str
    eventType: str
    timestamp: datetime
    data: ProjectDataDTO

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v):
        return parse_datetime(v)

    def to_kafka_payload(self) -> dict:
        """Convert to Kafka-ready payload dictionary."""
        return self.model_dump(mode="json")
