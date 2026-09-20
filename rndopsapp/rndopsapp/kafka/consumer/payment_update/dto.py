# Copyright (c) 2026, rndops and contributors
# Payment settlement update — one shape for both accounts settlement streams.

from dataclasses import dataclass, field
from typing import Optional


# The two streams are separate systems end to end: separate tables, separate id
# sequences, separate topics. Overhead payment #2 and project payment #2 are different
# records, so `source` travels with every message and is part of every lookup key.
SOURCE_OVERHEAD = "OVERHEAD"
SOURCE_PROJECT = "PROJECT"

# The four statuses the accounts service settles a payment into. PENDING is not a
# decision — on the project stream it is mostly the echo of our own publish.
STATUS_PENDING = "PENDING"
STATUS_PAID = "PAID"
STATUS_REJECTED = "REJECTED"
STATUS_RECTIFICATION = "RECTIFICATION"

DECISION_STATUSES = (STATUS_PAID, STATUS_REJECTED, STATUS_RECTIFICATION)

# Field names differ between the streams; nothing else does. Left is overhead, right is
# project — see the Accounts "Overhead Payment Events" spec, "Telling overhead apart from
# project payments".
_FIELDS_BY_SOURCE = {
	SOURCE_OVERHEAD: {"payment_id": "overheadPaymentId", "commit_id": "overheadCommitId"},
	SOURCE_PROJECT: {"payment_id": "transactionPaymentNumber", "commit_id": "transactionCommitNumber"},
}


def _as_int(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


def _as_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


@dataclass
class PaymentSettlementDTO:
	"""
	An accounts decision on one payment, normalised across both streams.

	The event is a **state snapshot**, not a delta, and delivery is at-least-once — so a
	consumer must be idempotent on (payment_id, status) and must tolerate unknown fields
	rather than failing on them.
	"""
	source: str = SOURCE_OVERHEAD
	payment_id: Optional[int] = None
	commit_id: Optional[int] = None
	# Our correlation ids, echoed back exactly as sent. `frap_app_id` is the application
	# docname and repeats across instalments; `frap_row_id` is the payment row's own
	# docname and is the only reliable per-payment key.
	frap_app_id: Optional[str] = None
	frap_row_id: Optional[str] = None
	status: str = ""
	remarks: Optional[str] = None
	payment_amount: Optional[float] = None
	payment_date: Optional[str] = None
	bank_transaction_number: Optional[str] = None
	bank_transaction_date: Optional[str] = None
	# Parent-commit context, recomputed by accounts after this change. Informational.
	total_paid_amount: Optional[float] = None
	remaining_amount: Optional[float] = None
	commit_status: Optional[str] = None
	raw: dict = field(default_factory=dict)

	@classmethod
	def from_message(cls, message: dict, source: str) -> "PaymentSettlementDTO":
		data = (message or {}).get("data") or {}
		names = _FIELDS_BY_SOURCE[source]
		return cls(
			source=source,
			payment_id=_as_int(data.get(names["payment_id"])),
			commit_id=_as_int(data.get(names["commit_id"])),
			frap_app_id=(data.get("frapAppId") or None),
			frap_row_id=(data.get("frapRowId") or None),
			status=(data.get("paymentStatus") or "").strip().upper(),
			# The project payload has no remarks field at all — the reason lives behind
			# the comments API there. Overhead carries it inline.
			remarks=(data.get("remarks") or None),
			payment_amount=_as_float(data.get("paymentAmount")),
			payment_date=(data.get("paymentDate") or None),
			bank_transaction_number=(data.get("bankTransactionNumber") or None),
			bank_transaction_date=(data.get("bankTransactionDate") or None),
			total_paid_amount=_as_float(data.get("totalPaidAmount")),
			remaining_amount=_as_float(data.get("remainingAmount")),
			commit_status=(data.get("commitStatus") or None),
			raw=data,
		)

	@property
	def is_decision(self) -> bool:
		"""PAID / REJECTED / RECTIFICATION. PENDING is not a decision."""
		return self.status in DECISION_STATUSES

	def __str__(self):
		return (
			f"{self.source} payment id={self.payment_id} commit={self.commit_id} "
			f"status={self.status} frapAppId={self.frap_app_id} frapRowId={self.frap_row_id}"
		)
