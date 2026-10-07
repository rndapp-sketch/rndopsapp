# Copyright (c) 2026, rndops and contributors
# Overhead Commit / Payment DTOs — the payload the Accounts service consumes on
# overhead-commit-events and overhead-payment-events.

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class OverheadCommitDTO:
	"""
	A commit against an overhead fund.

	Scoped by fund type plus one identifier: PDF -> employeeId, DPF -> departmentId,
	IDF/SWF/STWF -> neither (a global pool). We only ever publish PDF.

	Field contract from the Accounts team's "Overhead Commit/Payment Kafka Consumption &
	Module Logic" design (2026-08-04):
	  - `scopeType` is server-derived and ignored if sent, so it is never included.
	  - `overheadCommitId` is auto-generated; only sent when replaying a message that
	    should be recognised as already-processed.
	  - `status` defaults to PENDING on their side when omitted, which is NOT what we want:
	    a commit reserves funds and must land as COMMITTED, exactly as the project-side
	    AccountHeadCommitDTO already sends. Always emitted.
	  - `moduleId` reuses the same ModuleCode values as the project side, unchanged.
	  - `refDetails` is a parent overheadCommitId (Long), not a free-text reference.
	"""
	fundType: str = "PDF"
	employeeId: Optional[str] = None
	departmentId: Optional[int] = None
	accountHeadId: Optional[int] = None
	commitDate: Optional[str] = None
	commitParticular: str = ""
	commitAmount: float = 0.0
	status: str = "COMMITTED"
	billAmount: Optional[float] = None
	moduleId: Optional[str] = None
	refDetails: Optional[int] = None
	frapAppId: Optional[str] = None
	beneficiaryProjectNumber: Optional[str] = None
	remarks: Optional[str] = None
	createdBy: str = "frappe-erp"

	def to_dict(self) -> dict:
		payload = {
			"fundType": self.fundType,
			"accountHeadId": self.accountHeadId,
			"commitParticular": self.commitParticular,
			"commitAmount": self.commitAmount,
			"status": self.status,
			"createdBy": self.createdBy,
		}
		# Exactly one scope identifier, matching the fund type.
		if self.employeeId:
			payload["employeeId"] = self.employeeId
		if self.departmentId is not None:
			payload["departmentId"] = self.departmentId

		for key, value in (
			("commitDate", self.commitDate),
			("billAmount", self.billAmount),
			("moduleId", self.moduleId),
			("refDetails", self.refDetails),
			("frapAppId", self.frapAppId),
			("beneficiaryProjectNumber", self.beneficiaryProjectNumber),
			("remarks", self.remarks),
		):
			if value not in (None, ""):
				payload[key] = value

		return payload


@dataclass
class OverheadPaymentDTO:
	"""
	A payment against an existing overhead commit.

	`overheadCommitId` is the Accounts service's own PK for the commit — required, and
	the reason payments need the resolution step in producer.publish_overhead_payment.
	"""
	overheadCommitId: Optional[int] = None
	paymentDate: Optional[str] = None
	paymentParticular: str = ""
	paymentRefDetails: Optional[str] = None
	paymentAmount: float = 0.0
	bmr: Optional[str] = None
	paymentStatus: str = "PAID"
	bankTransactionNumber: Optional[str] = None
	bankTransactionDate: Optional[str] = None
	frapAppId: Optional[str] = None
	# This payment row's own docname. `frapAppId` is the *application* docname and
	# repeats across every instalment and correction on that application, so it cannot
	# identify a single payment. Accounts matches on `frapRowId` when it is present and
	# falls back to (commit, amount, date) when it is not — that heuristic conflates two
	# identical instalments on the same day, which this removes.
	frapRowId: Optional[str] = None
	remarks: Optional[str] = None
	createdBy: str = "frappe-erp"

	def to_dict(self) -> dict:
		payload = {
			"overheadCommitId": self.overheadCommitId,
			"paymentParticular": self.paymentParticular,
			"paymentAmount": self.paymentAmount,
			"paymentStatus": self.paymentStatus,
			"createdBy": self.createdBy,
		}
		for key, value in (
			("paymentDate", self.paymentDate),
			("paymentRefDetails", self.paymentRefDetails),
			("bmr", self.bmr),
			("bankTransactionNumber", self.bankTransactionNumber),
			("bankTransactionDate", self.bankTransactionDate),
			("frapAppId", self.frapAppId),
			("frapRowId", self.frapRowId),
			("remarks", self.remarks),
		):
			if value not in (None, ""):
				payload[key] = value
		return payload


def wrap_event(event_type: str, data, schema_version: str = "1.0") -> dict:
	"""The common envelope every consumer in this system expects."""
	return {
		"schemaVersion": schema_version,
		"eventType": event_type,
		"timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
		"data": data.to_dict(),
	}
