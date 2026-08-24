# Copyright (c) 2026, rndops and contributors
# Loan Request DLQ Consumer DTO - parses messages landing on loan-request-event-dlq

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LoanRequestDlqEventDTO:
    """
    Represents a message on loan-request-event-dlq. Mirrors the other DLQ
    consumers' assumption (confirmed for the topics that have had real
    traffic): the external ledger microservice republishes the *original*
    loan-request-event envelope unchanged when it can't process it, with no
    error reason included.
    """
    event_type: str = ""
    project_number: Optional[str] = None
    loan_type: Optional[str] = None
    loan_amount: Optional[float] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "LoanRequestDlqEventDTO":
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
            loan_type=data.get("loanType"),
            loan_amount=data.get("loanAmount"),
            raw_payload=message,
        )
