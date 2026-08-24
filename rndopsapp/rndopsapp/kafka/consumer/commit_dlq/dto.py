# Copyright (c) 2026, rndops and contributors
# Commit DLQ Consumer DTO - parses messages landing on account-head-commit-events-dlq

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommitDlqEventDTO:
    """
    Represents a message on account-head-commit-events-dlq. The external
    ledger microservice's AccountHeadCommit consumer republishes the
    *original* account-head-commit-events envelope unchanged when it can't
    process it — no error reason is included (confirmed from real DLQ
    payloads sampled from the cluster).
    """
    event_type: str = ""
    project_number: Optional[str] = None
    account_head_id: Optional[int] = None
    frap_app_id: Optional[str] = None
    commit_amount: Optional[float] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "CommitDlqEventDTO":
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
            account_head_id=data.get("accountHeadId"),
            frap_app_id=data.get("frapAppId"),
            commit_amount=data.get("commitAmount"),
            raw_payload=message,
        )
