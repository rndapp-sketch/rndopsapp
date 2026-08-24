# Copyright (c) 2026, rndops and contributors
# Deposit Slip DLQ Consumer DTO - parses messages landing on deposit-slip-events-dlq

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DepositSlipDlqEventDTO:
    """
    Represents a message on deposit-slip-events-dlq. The external ledger
    microservice's Deposit Slip consumer republishes the *original*
    deposit-slip-events envelope unchanged when it can't process it — no
    error reason is included (confirmed from real DLQ payloads sampled from
    the cluster).
    """
    event_type: str = ""
    project_number: Optional[str] = None
    deposit_slip_ref_num_fab: Optional[str] = None
    slip_number: Optional[str] = None
    category: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "DepositSlipDlqEventDTO":
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
            deposit_slip_ref_num_fab=data.get("depositSlipRefNumFab"),
            slip_number=data.get("slipNumber"),
            category=data.get("category"),
            raw_payload=message,
        )
