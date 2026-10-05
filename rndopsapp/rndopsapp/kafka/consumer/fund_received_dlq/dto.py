# Copyright (c) 2026, rndops and contributors
# Fund Received DLQ Consumer DTO - parses messages landing on fund-received-events-dlq

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FundReceivedDlqEventDTO:
    """
    Represents a message on fund-received-events-dlq. The external ledger
    microservice's Fund Received consumer republishes the *original*
    fund-received-events envelope unchanged when it can't process it — no
    error reason is included (confirmed from real DLQ payloads sampled from
    the cluster).
    """
    event_type: str = ""
    project_number: Optional[str] = None
    fund_received_ref_number_fap: Optional[str] = None
    amount_received: Optional[float] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "FundReceivedDlqEventDTO":
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
            fund_received_ref_number_fap=data.get("fundReceivedRefNumberFap"),
            amount_received=data.get("amountReceived"),
            raw_payload=message,
        )
