# Copyright (c) 2026, rndops and contributors
# Overhead Producer — publishes overhead fund commits and payments (PDF, DPF).

import frappe
from frappe.utils import flt, nowdate
from typing import Optional

from .dto import OverheadCommitDTO, OverheadPaymentDTO, wrap_event
from ...utils import publish_message, is_kafka_available, mm_notify
from ...logs import log_producer_event

TOPIC_OVERHEAD_COMMIT = "overhead-commit-events"
TOPIC_OVERHEAD_COMMIT_DLQ = "overhead-commit-events-dlq"
TOPIC_OVERHEAD_PAYMENT = "overhead-payment-events"
TOPIC_OVERHEAD_PAYMENT_DLQ = "overhead-payment-events-dlq"

# Every overhead spend books to the single "Overhead" head. These funds have no head
# dimension, but OverheadCommit carries a real AccountHead, so one must be sent.
OVERHEAD_ACCOUNT_HEAD_ID = 1


# ---------------------------------------------------------------------------
# Fund-type resolution
# ---------------------------------------------------------------------------
#
# The Accounts service scopes an overhead fund three different ways:
#
#     PDF              -> employeeId
#     DPF              -> departmentId
#     IDF / SWF / STWF -> neither (a global institute pool)
#
# PDF and DPF are surfaced as projects today. Which is which is decided by
# overhead_fund.FUND_TYPES — the single place a fund's scoping is described — so adding
# the institute-wide pools means adding a row there, not editing this file: the DTO
# already carries both identifiers, and `scopeType` is derived on their side from
# fundType + the identifier.
#
# Deliberately NOT permission-checked. This decides which topic a commit belongs on and
# runs at approval time as whoever approved, who is usually not the fund's owner.
# See docs/pdf-project-implementation.md §5.4 and docs/dpf-project-implementation.md §5.4.


def resolve_overhead_scope(project_number):
	"""
	The overhead fund a project's money belongs to, or None for an ordinary project.

	Returns ``(fund_type, scope)`` where `scope` holds exactly the one identifier that
	fund type is scoped by — so a caller never has to know which is which.

	Returning None is what keeps every ordinary project on the existing
	account-head-* topics, untouched.

	`project_number` may be EITHER the Project Registration docname or its project_no;
	overhead_fund accepts both. Callers are inconsistent — the commit staging payload
	carries the docname, which get_project_number() in the reimbursement mapper only
	converts later — and matching one alone silently sent every overhead commit to
	account-head-commit-events.
	"""
	from rndopsapp.rndopsapp.overhead_fund import resolve_overhead_fund

	resolved = resolve_overhead_fund(project_number)
	if not resolved:
		return None
	fund_type, scope, _row = resolved
	return fund_type, scope


def _module_id_for_doctype(doctype):
	"""
	The ModuleCode for a doctype, from Module Registry (e.g. Reimbursement -> "5").

	Callers only pass `module_id` when they need a deliberate override (ICSS PO re-commit
	uses 14), so for an ordinary commit it arrives as None and the Accounts side receives
	no module at all. Their transaction log doesn't echo moduleId back either, so deriving
	it here is the only way it ever reaches them.
	"""
	if not doctype:
		return None
	try:
		rows = frappe.get_all(
			"Module Registry Doctype" if frappe.db.exists("DocType", "Module Registry Doctype") else "Module Registry",
			filters={"parent": "pending-task", "doctype_name": doctype},
			fields=["idx"],
			limit=1,
		)
		if rows:
			return str(rows[0]["idx"])
	except Exception:
		pass

	# Fall back to walking the parent document's child table.
	try:
		registry = frappe.get_doc("Module Registry", "pending-task")
		for row in registry.get("doctype_name") or []:
			if getattr(row, "doctype_name", None) == doctype:
				return str(row.idx)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead - Module Id Lookup Failed")
	return None


def _department_id_for_project(project_number):
	"""
	The owner's department id, as the Accounts service numbers them.

	Only ever needed for an employee-scoped fund (PDF), where the department is context
	rather than the scope key. A DPF commit already carries departmentId as its scope, so
	this is not consulted.
	"""
	from rndopsapp.rndopsapp.kafka.utils import get_department_id
	from rndopsapp.rndopsapp.overhead_fund import resolve_overhead_fund

	resolved = resolve_overhead_fund(project_number)
	if not resolved:
		return None
	dept_link = (resolved[2] or {}).get("implementation_department")
	if not dept_link:
		dept_link = frappe.db.get_value(
			"Project Registration", resolved[2]["name"], "implementation_department"
		)
	dept_id = get_department_id(dept_link) if dept_link else None
	# Their DTO types departmentId as an integer (their examples send 12, not "12");
	# frappe.db.get_value hands back whatever the column holds, often a string.
	try:
		return int(dept_id) if dept_id not in (None, "") else None
	except (TypeError, ValueError):
		return None


def _created_by_for(frap_app_id):
	"""
	The staff member who raised the commit.

	Taken from the Kafka Commit Staging record's owner — that row is created by
	submit_commit_data at the moment the commit form is submitted, so its owner is the
	person who actually committed. `frappe.session.user` at publish time would instead be
	whoever approved the application, which is often someone else.
	"""
	if frap_app_id:
		owner = frappe.db.get_value(
			"Kafka Commit Staging", {"reference_name": frap_app_id}, "owner"
		)
		if owner:
			return owner
	user = frappe.session.user
	return user if user and user != "Guest" else "frappe-erp"


def is_overhead_project(project_number) -> bool:
	"""True when commits for this project belong on the overhead topics, not the project ones."""
	return resolve_overhead_scope(project_number) is not None


def publish_overhead_commit(
	doc,
	commit_amount: float,
	budget_head=None,
	project_name: str = None,
	bmr: Optional[str] = None,
	bill_amount: Optional[float] = None,
	validate: bool = True,
	log_errors: bool = True,
	frap_app_id: Optional[str] = None,
	ref_details=None,
	module_id=None,
	commit_particular: Optional[str] = None,
) -> bool:
	"""
	Publish an overhead commit (PDF / DPF) to overhead-commit-events.

	Deliberately mirrors publish_commit's signature so the caller can pick a topic
	without reshaping its arguments (see commitPayment._dispatch_commit).

	`budget_head` is accepted and ignored: an overhead fund has no head dimension, and the
	account head is fixed at "Overhead".
	"""
	resolved = resolve_overhead_scope(project_name)
	if not resolved:
		frappe.log_error(
			f"publish_overhead_commit called for non-overhead project {project_name}",
			"Overhead Commit - Not An Overhead Project",
		)
		return False
	fund_type, scope = resolved

	if not is_kafka_available():
		log_producer_event("OVERHEAD_COMMIT", doc.name, TOPIC_OVERHEAD_COMMIT, "SKIPPED", "Kafka not available")
		return False

	amount = flt(commit_amount)
	if amount <= 0:
		log_producer_event("OVERHEAD_COMMIT", doc.name, TOPIC_OVERHEAD_COMMIT, "VALIDATION_FAILED", "commitAmount must be > 0")
		return False

	# refDetails on the overhead side is a parent overheadCommitId (Long), not the
	# free-text reference the project side allows. Send it only when it really is one.
	parent_commit_id = None
	if ref_details not in (None, ""):
		try:
			parent_commit_id = int(ref_details)
		except (TypeError, ValueError):
			parent_commit_id = None

	resolved_frap_app_id = frap_app_id or doc.name

	# Derived rather than required from the caller: an ordinary commit passes no
	# module_id (only deliberate overrides do), and the scope carries no department for
	# an employee-scoped fund. Both are informational on the Accounts side but were
	# arriving empty, so they are resolved here.
	resolved_module_id = (
		str(module_id) if module_id not in (None, "")
		else _module_id_for_doctype(getattr(doc, "doctype", None))
	)
	resolved_department_id = scope.get("departmentId") or _department_id_for_project(project_name)

	dto = OverheadCommitDTO(
		fundType=fund_type,
		employeeId=scope.get("employeeId"),
		departmentId=resolved_department_id,
		accountHeadId=OVERHEAD_ACCOUNT_HEAD_ID,
		commitDate=nowdate(),
		commitParticular=commit_particular or f"Commitment for {doc.name}",
		commitAmount=amount,
		billAmount=flt(bill_amount) if bill_amount else None,
		moduleId=resolved_module_id,
		refDetails=parent_commit_id,
		frapAppId=resolved_frap_app_id,
		remarks=bmr or None,
		createdBy=_created_by_for(resolved_frap_app_id),
	)

	try:
		log_producer_event("OVERHEAD_COMMIT", doc.name, TOPIC_OVERHEAD_COMMIT, "STARTED", "Beginning publish process")
		success = publish_message(
			TOPIC_OVERHEAD_COMMIT,
			wrap_event("OVERHEAD_COMMIT", dto),
			doc.name,
			TOPIC_OVERHEAD_COMMIT_DLQ,
			# Partition by the fund's own scope so one employee's — or one department's —
			# commits stay ordered. str() because DPF's departmentId is an int.
			key=str(scope.get("employeeId") or scope.get("departmentId") or fund_type),
		)
		log_producer_event(
			"OVERHEAD_COMMIT", doc.name, TOPIC_OVERHEAD_COMMIT,
			"PUBLISHED" if success else "FAILED",
			f"{fund_type} {scope} amount={amount}",
		)
		if not success:
			mm_notify(
				f":x: **Overhead Commit publish FAILED**\n"
				f"**Doc:** {doc.name}\n**Topic:** {TOPIC_OVERHEAD_COMMIT}"
			)
		return bool(success)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead Commit Publish Error")
		return False


def resolve_overhead_commit_id(project_number, frap_app_id):
	"""
	The Accounts service's own overheadCommitId for a commit we published.

	A payment must reference it, and it is generated on their side, so it has to be read
	back. The overhead transaction log carries both the id and our frapAppId, which is the
	only correlation available — there is no lookup-by-frapAppId endpoint.
	"""
	if not frap_app_id:
		return None

	import requests
	from rndopsapp.rndopsapp.pdf_fund import ACCOUNTS_API_BASE_URL, REQUEST_TIMEOUT

	resolved = resolve_overhead_scope(project_number)
	if not resolved:
		return None
	fund_type, scope = resolved

	try:
		response = requests.get(
			f"{ACCOUNTS_API_BASE_URL}/overhead-transactions/{fund_type}/logs",
			params=scope,
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		rows = response.json()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead - Resolve Commit Id Failed")
		return None

	if not isinstance(rows, list):
		return None

	for row in rows:
		if row.get("transactionType") == "COMMIT" and row.get("frapAppId") == frap_app_id:
			return row.get("transactionId")
	return None


def publish_overhead_payment(
	doc,
	project_name: Optional[str] = None,
	payment_amount: Optional[float] = None,
	budget_head=None,
	bmr: Optional[str] = None,
	validate: bool = True,
	log_errors: bool = True,
	ref_details: Optional[str] = None,
	frap_app_id: Optional[str] = None,
	module_name: Optional[str] = None,
	bill_amount: Optional[float] = None,
) -> bool:
	"""
	Publish an overhead payment (PDF / DPF) to overhead-payment-events.

	Mirrors publish_payment's signature, for the same reason as the commit above.

	Unlike the project side — where a payment is addressed by projectNumber +
	accountHeadId — an overhead payment must carry the Accounts service's own
	`overheadCommitId`. That id only exists after they have consumed our commit, so it is
	resolved from their transaction log here. If it cannot be found the payment is NOT
	published: sending one without it would be rejected, and a silent DLQ entry is worse
	than a logged failure someone can retry.
	"""
	if not is_overhead_project(project_name):
		frappe.log_error(
			f"publish_overhead_payment called for non-overhead project {project_name}",
			"Overhead Payment - Not An Overhead Project",
		)
		return False

	if not is_kafka_available():
		log_producer_event("OVERHEAD_PAYMENT", doc.name, TOPIC_OVERHEAD_PAYMENT, "SKIPPED", "Kafka not available")
		return False

	# `commit_id` on the payment doc is the ledger's own transactionCommitNumber, which for
	# an overhead commit IS the overheadCommitId — PaymentForm forwards it from the Pending
	# Commits row. Prefer it; fall back to scanning their log by frapAppId when a payment is
	# raised through some path that doesn't carry it.
	overhead_commit_id = getattr(doc, "commit_id", None)
	if overhead_commit_id in (None, "", 0, "0"):
		overhead_commit_id = resolve_overhead_commit_id(project_name, frap_app_id or doc.name)

	if not overhead_commit_id:
		msg = (
			f"No overheadCommitId found for frapAppId={frap_app_id or doc.name} on {project_name}. "
			"The commit may not have been consumed by Accounts yet."
		)
		log_producer_event("OVERHEAD_PAYMENT", doc.name, TOPIC_OVERHEAD_PAYMENT, "VALIDATION_FAILED", msg)
		frappe.log_error(msg, "Overhead Payment - Commit Id Unresolved")
		mm_notify(f":x: **Overhead Payment blocked**\n**Doc:** {doc.name}\n{msg}")
		return False

	# Every explicit argument falls back to the document, mirroring
	# AccountHeadPaymentMapper exactly: submit_payment_data passes payment_amount / bmr /
	# budget_head as None on purpose and expects the doc to be read. Taking the argument
	# at face value published paymentAmount 0.0 for a real ₹900 payment.
	dto = OverheadPaymentDTO(
		overheadCommitId=int(overhead_commit_id),
		paymentDate=str(getattr(doc, "payment_date", None) or nowdate()),
		paymentParticular=getattr(doc, "payment_particular", None) or f"Payment for {doc.name}",
		paymentRefDetails=ref_details or getattr(doc, "payment_reference_details", None) or None,
		paymentAmount=flt(payment_amount or getattr(doc, "payment_amount", 0)),
		bmr=bmr or getattr(doc, "payment_bmr", None) or None,
		paymentStatus=getattr(doc, "payment_status", None) or "PAID",
		bankTransactionNumber=getattr(doc, "bank_transaction_number", None) or None,
		bankTransactionDate=(
			str(getattr(doc, "bank_transaction_date", None))
			if getattr(doc, "bank_transaction_date", None) else None
		),
		frapAppId=frap_app_id or doc.name,
		# Always the payment document's own name, never the caller's argument:
		# `frap_app_id` is the application, and one application produces many payments.
		frapRowId=doc.name,
		createdBy=_created_by_for(frap_app_id or doc.name),
	)

	if dto.paymentAmount <= 0:
		msg = f"Refusing to publish a zero/negative overhead payment for {doc.name}"
		log_producer_event("OVERHEAD_PAYMENT", doc.name, TOPIC_OVERHEAD_PAYMENT, "VALIDATION_FAILED", msg)
		frappe.log_error(msg, "Overhead Payment - Invalid Amount")
		return False

	try:
		log_producer_event("OVERHEAD_PAYMENT", doc.name, TOPIC_OVERHEAD_PAYMENT, "STARTED", "Beginning publish process")
		success = publish_message(
			TOPIC_OVERHEAD_PAYMENT,
			wrap_event("OVERHEAD_PAYMENT", dto),
			doc.name,
			TOPIC_OVERHEAD_PAYMENT_DLQ,
			key=str(overhead_commit_id),
		)
		log_producer_event(
			"OVERHEAD_PAYMENT", doc.name, TOPIC_OVERHEAD_PAYMENT,
			"PUBLISHED" if success else "FAILED",
			f"overheadCommitId={overhead_commit_id} amount={flt(payment_amount)}",
		)
		return bool(success)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Overhead Payment Publish Error")
		return False
