# Copyright (c) 2026, rndops and contributors
# Sanction DLQ Consumer DTO - parses messages landing on fund-sanction-events-dlq

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SanctionDlqEventDTO:
    """
    Represents a message on fund-sanction-events-dlq. The external ledger
    microservice's Fund Sanction consumer republishes the *original*
    fund-sanction-events envelope unchanged when it can't process it — no
    error reason is included (confirmed from real DLQ payloads sampled from
    the cluster), unlike account-head-payment-events-dlq's DTO.
    """
    event_type: str = ""
    project_number: Optional[str] = None
    sanction_letter_no: Optional[str] = None
    total_sanction_amount: Optional[float] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "SanctionDlqEventDTO":
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")

        if isinstance(message, str):
            try:
                message = json.loads(message)
            except (ValueError, TypeError):
                return cls(raw_payload={"raw_text": message})

        if not isinstance(message, dict):
            return cls()

        data = message.get("data") or {}
        return cls(
            event_type=message.get("eventType") or "",
            project_number=data.get("projectNumber"),
            sanction_letter_no=data.get("sanctionLetterNo"),
            total_sanction_amount=data.get("totalSanctionAmount"),
            raw_payload=message,
        )
