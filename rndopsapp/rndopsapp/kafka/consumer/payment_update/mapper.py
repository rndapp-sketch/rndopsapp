# Copyright (c) 2026, rndops and contributors
# Payment settlement update — resolution, application and notification.

import frappe
from frappe.utils import flt

from .dto import (
	PaymentSettlementDTO,
	SOURCE_PROJECT,
	STATUS_PAID,
	STATUS_PENDING,
	STATUS_RECTIFICATION,
	STATUS_REJECTED,
)
from ..dlq_common import ACCOUNT_PORTAL_USER

PAYMENT_DOCTYPE = "AccountHeadPayment"

# What the initiator is told, per decision. Written from their side of the screen: the
# officer's own `remarks` is appended when there is one.
_STATUS_BLURB = {
	STATUS_PAID: "The payment has been released by Accounts.",
	STATUS_REJECTED: "Accounts rejected this payment. The committed amount has been "
	                 "released back to the fund; a fresh payment must be raised.",
	STATUS_RECTIFICATION: "Accounts sent this payment back for correction. The amount "
	                      "is still claimed against the commit.",
}


class PaymentSettlementMapper:
	"""
	Applies an accounts settlement decision to the AccountHeadPayment it belongs to.

	Resolution never trusts a numeric id on its own: overhead payment #2 and project
	payment #2 are different records, so every lookup is scoped by `source` as well.
	"""

	# ------------------------------------------------------------------
	# Resolution
	# ------------------------------------------------------------------

	@staticmethod
	def resolve_payment(dto: PaymentSettlementDTO):
		"""
		The AccountHeadPayment docname this decision belongs to, or None.

		Three routes, most precise first:

		  1. `frapRowId` — the payment row's own docname. Exact, and the only key that
		     separates two instalments made on the same commit, amount and date.
		  2. `accounts_payment_id` — their PK, once we have recorded it (harvested from a
		     creation echo, or written by an earlier decision).
		  3. `frapAppId` + `commit_id` — the legacy route, for payments published before
		     frapRowId existed. Ambiguous by construction when an application has several
		     payments against one commit, so it deliberately refuses rather than guess.
		"""
		if dto.frap_row_id and frappe.db.exists(PAYMENT_DOCTYPE, dto.frap_row_id):
			return dto.frap_row_id

		if dto.payment_id is not None:
			match = frappe.db.get_value(
				PAYMENT_DOCTYPE,
				{
					"accounts_payment_id": str(dto.payment_id),
					"settlement_source": dto.source,
				},
				"name",
			)
			if match:
				return match

		if dto.frap_app_id and dto.commit_id is not None:
			candidates = frappe.get_all(
				PAYMENT_DOCTYPE,
				filters={"commit_id": str(dto.commit_id)},
				fields=["name"],
				limit=2,
			)
			if len(candidates) == 1:
				return candidates[0]["name"]

		return None

	# ------------------------------------------------------------------
	# Echo detection
	# ------------------------------------------------------------------

	@staticmethod
	def is_creation_echo(dto: PaymentSettlementDTO, current_status: str) -> bool:
		"""
		Whether this PENDING message is our own publish coming back.

		`accounts-accountheadpayment-update` publishes from seven places — payment
		created, batch created, updated, generic status change, the three settle actions
		and salary bulk actions — so a PENDING event there is normally the echo of a
		payment we just sent. The overhead stream publishes only on the three settle
		actions and never echoes.

		Following the Accounts team's refinement: a PENDING message is treated as
		meaningful (a deliberate `PATCH /{id}/status` reset) only when we already hold
		that payment in a *settled* state. Otherwise it is an echo — which is still worth
		consuming, because it carries their payment id.
		"""
		if dto.status != STATUS_PENDING:
			return False
		return (current_status or "").upper() not in (STATUS_PAID, STATUS_REJECTED, STATUS_RECTIFICATION)

	# ------------------------------------------------------------------
	# Application
	# ------------------------------------------------------------------

	@staticmethod
	def record_accounts_payment_id(doc_name: str, dto: PaymentSettlementDTO) -> None:
		"""
		Store their PK against our row.

		This is the only reason a creation echo is worth consuming: it is the sole source
		of `transactionPaymentNumber` on the project stream, which otherwise has no way
		of reaching us.
		"""
		if dto.payment_id is None:
			return
		updates = {"accounts_payment_id": str(dto.payment_id), "settlement_source": dto.source}
		current = frappe.db.get_value(PAYMENT_DOCTYPE, doc_name, "accounts_payment_id")
		if str(current or "") == str(dto.payment_id):
			return
		frappe.db.set_value(PAYMENT_DOCTYPE, doc_name, updates, update_modified=False)

	@classmethod
	def apply(cls, doc_name: str, dto: PaymentSettlementDTO) -> bool:
		"""
		Write the decision onto the payment. Returns False when it was already applied.

		Idempotent on (payment_id, status), as the spec requires: the event is a state
		snapshot and delivery is at-least-once, so a repeat must be a no-op rather than a
		second notification.
		"""
		current = frappe.db.get_value(
			PAYMENT_DOCTYPE, doc_name, ["payment_status", "accounts_payment_id"], as_dict=True
		) or {}

		already = (
			(current.get("payment_status") or "").upper() == dto.status
			and str(current.get("accounts_payment_id") or "") == str(dto.payment_id or "")
		)
		if already:
			return False

		updates = {
			"payment_status": dto.status,
			"settlement_source": dto.source,
		}
		if dto.payment_id is not None:
			updates["accounts_payment_id"] = str(dto.payment_id)
		# Only PAID carries a bank reference; the other two must not leave a stale one behind.
		if dto.status == STATUS_PAID:
			if dto.bank_transaction_number:
				updates["bank_transaction_number"] = dto.bank_transaction_number
			if dto.bank_transaction_date:
				updates["bank_transaction_date"] = dto.bank_transaction_date
			updates["settlement_remarks"] = ""
		else:
			updates["settlement_remarks"] = dto.remarks or ""

		for fieldname, value in (
			("commit_status", dto.commit_status),
			("total_paid_amount", dto.total_paid_amount),
			("remaining_amount", dto.remaining_amount),
		):
			if value is not None:
				updates[fieldname] = flt(value) if fieldname != "commit_status" else value

		# Every field is guarded: this doctype is extended by patch, and a site that has
		# not migrated yet must degrade to writing what it has rather than throwing.
		writable = {
			k: v for k, v in updates.items()
			if frappe.db.has_column(PAYMENT_DOCTYPE, k)
		}
		if writable:
			frappe.db.set_value(PAYMENT_DOCTYPE, doc_name, writable, update_modified=False)
		return True

	# ------------------------------------------------------------------
	# Telling the initiator
	# ------------------------------------------------------------------

	@classmethod
	def notify(cls, doc_name: str, dto: PaymentSettlementDTO) -> None:
		"""
		Comment for the audit trail plus a Notification Log for the initiator.

		Both best-effort and never raised: a notification failure must not fail the Kafka
		message and cause the decision to be reprocessed. Same convention as the Fund
		Received consumer.
		"""
		blurb = _STATUS_BLURB.get(dto.status, f"Accounts set this payment to {dto.status}.")
		if dto.remarks:
			blurb += f" Reason: {dto.remarks}"

		cls._comment(PAYMENT_DOCTYPE, doc_name, f"[Payment {dto.status}] {blurb}")

		# The same note belongs on the application the initiator actually opens — they do
		# not go looking for an AccountHeadPayment row.
		application = cls.resolve_application(dto)
		if application:
			cls._comment(
				application["doctype"], application["name"],
				f"[Payment {dto.status}] {blurb}",
			)

		cls._alert(doc_name, dto, blurb, application)

	@staticmethod
	def resolve_application(dto: PaymentSettlementDTO):
		"""
		The application document behind `frapAppId`, as {doctype, name}.

		`frapAppId` is an application docname but carries no doctype, so it is resolved
		through `Kafka Commit Staging`, which records both for the commit that this
		payment eventually drew against.
		"""
		if not dto.frap_app_id:
			return None
		row = frappe.db.get_value(
			"Kafka Commit Staging",
			{"reference_name": dto.frap_app_id},
			["reference_doctype", "reference_name"],
			as_dict=True,
		)
		if not row or not row.get("reference_doctype"):
			return None
		if not frappe.db.exists(row["reference_doctype"], row["reference_name"]):
			return None
		return {"doctype": row["reference_doctype"], "name": row["reference_name"]}

	@staticmethod
	def _comment(doctype: str, name: str, content: str) -> None:
		try:
			comment = frappe.get_doc({
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": doctype,
				"reference_name": name,
				"content": content,
				"owner": ACCOUNT_PORTAL_USER,
			})
			comment.insert(ignore_permissions=True)
			if comment.owner != ACCOUNT_PORTAL_USER:
				frappe.db.set_value("Comment", comment.name, "owner", ACCOUNT_PORTAL_USER)
		except Exception:
			frappe.log_error(
				f"Failed to add settlement comment on {doctype} {name}",
				"Payment Settlement Notify Error",
			)

	@staticmethod
	def _alert(doc_name: str, dto: PaymentSettlementDTO, blurb: str, application) -> None:
		try:
			# Notify whoever raised the application when we can identify it, since that is
			# the person who must act; fall back to the payment's own owner.
			target_doctype, target_name = PAYMENT_DOCTYPE, doc_name
			if application:
				target_doctype, target_name = application["doctype"], application["name"]

			owner = frappe.db.get_value(target_doctype, target_name, "owner")
			if not owner or owner in ("Administrator", "Guest"):
				return

			from frappe.desk.doctype.notification_log.notification_log import (
				enqueue_create_notification,
			)
			enqueue_create_notification([owner], {
				"type": "Alert",
				"document_type": target_doctype,
				"document_name": target_name,
				"subject": f"Payment {dto.status}: {blurb}",
				"from_user": ACCOUNT_PORTAL_USER,
			})
		except Exception:
			frappe.log_error(
				f"Failed to alert initiator of settlement on {doc_name}",
				"Payment Settlement Notify Error",
			)
