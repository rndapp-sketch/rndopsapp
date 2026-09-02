# Copyright (c) 2026, rndops and contributors
# Payment DLQ Consumer DTO - parses failure notices from account-head-payment-events-dlq

import json
from typing import Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class PaymentDlqErrorDTO:
    """
    Represents a processing failure reported by the external ledger
    microservice's "AccountHeadPayment Consumer" on account-head-payment-events,
    after it gives up and pushes the failed event to account-head-payment-events-dlq.

    projectNumber/accountHeadId are the exact identifiers
    AccountHeadPaymentMapper.map_to_dto (kafka/producer/reimbursement/mapper.py)
    sent out on the original event, so they double as the lookup key back to the
    AccountHeadPayment doc that triggered the failure.
    """
    consumer_name: str = ""
    original_topic: str = ""
    dlq_topic: str = ""
    error_type: str = ""
    error_message: str = ""
    project_number: Optional[str] = None
    account_head_id: Optional[int] = None
    identifier_raw: str = ""
    failed_at: Optional[str] = None
    raw_payload: dict = field(default_factory=dict)

    @classmethod
    def from_kafka_message(cls, message) -> "PaymentDlqErrorDTO":
        """
        Accepts either a JSON dict (the expected DLQ message shape) or a raw
        string/bytes value. Falls back to parsing a human-readable
        "Field: value" alert block if the payload isn't JSON, since that is the
        only concrete shape of this error observed so far.
        """
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="replace")

        if isinstance(message, str):
            try:
                message = json.loads(message)
            except (ValueError, TypeError):
                return cls._from_text(message)

        if not isinstance(message, dict):
            return cls()

        identifier = message.get("identifier") or message.get("Identifier")
        project_number, account_head_id = cls._parse_identifier(identifier)

        # Some producers may echo the original event under payload/data instead
        # of (or in addition to) a flattened "identifier" string.
        nested = message.get("payload") or message.get("data") or {}
        if isinstance(nested, dict):
            project_number = project_number or nested.get("projectNumber")
            if account_head_id is None:
                account_head_id = nested.get("accountHeadId")

        return cls(
            consumer_name=message.get("consumer") or message.get("consumerName") or "",
            original_topic=message.get("originalTopic") or message.get("topic") or "",
            dlq_topic=message.get("dlqTopic") or message.get("dlq") or "",
            error_type=message.get("errorType") or message.get("error_type") or "",
            error_message=message.get("error") or message.get("errorMessage") or message.get("message") or "",
            project_number=str(project_number) if project_number not in (None, "") else None,
            account_head_id=cls._to_int(account_head_id),
            identifier_raw=identifier if isinstance(identifier, str) else (json.dumps(identifier) if identifier else ""),
            failed_at=message.get("failedAt") or message.get("time") or message.get("timestamp"),
            raw_payload=message,
        )

    @classmethod
    def _from_text(cls, text: str) -> "PaymentDlqErrorDTO":
        """Fallback parser for the Mattermost-style alert block:

        Consumer: [AccountHeadPayment Consumer]
        Topic: account-head-payment-events
        DLQ: account-head-payment-events-dlq
        Error Type: PROCESSING_ERROR
        Identifier: projectNumber=X,accountHeadId=Y
        Error: <message>
        Time: <timestamp>
        """
        fields = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            fields[key.strip().lower()] = val.strip()

        identifier = fields.get("identifier", "")
        project_number, account_head_id = cls._parse_identifier(identifier)

        return cls(
            consumer_name=fields.get("consumer", "").strip("[]"),
            original_topic=fields.get("topic", ""),
            dlq_topic=fields.get("dlq", ""),
            error_type=fields.get("error type", ""),
            error_message=fields.get("error", ""),
            project_number=project_number,
            account_head_id=cls._to_int(account_head_id),
            identifier_raw=identifier,
            failed_at=fields.get("time"),
            raw_payload={"raw_text": text},
        )

    @staticmethod
    def _parse_identifier(identifier) -> Tuple[Optional[str], Optional[str]]:
        if isinstance(identifier, dict):
            return identifier.get("projectNumber"), identifier.get("accountHeadId")
        if isinstance(identifier, str) and identifier:
            parts = {}
            for chunk in identifier.split(","):
                if "=" in chunk:
                    key, _, val = chunk.partition("=")
                    parts[key.strip()] = val.strip()
            return parts.get("projectNumber"), parts.get("accountHeadId")
        return None, None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        try:
            return int(value) if value not in (None, "") else None
        except (ValueError, TypeError):
            return None
