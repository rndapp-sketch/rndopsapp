# Copyright (c) 2026, rndops and contributors
# Payment settlement update consumer — accounts' decision on a payment we published.

import frappe

from .dto import PaymentSettlementDTO, SOURCE_OVERHEAD, SOURCE_PROJECT
from .mapper import PaymentSettlementMapper
from ...config import TOPIC_ACCOUNT_HEAD_PAYMENT_UPDATE, TOPIC_OVERHEAD_PAYMENT_UPDATE
from ...logs import log_consumer_event

_TOPIC_BY_SOURCE = {
	SOURCE_OVERHEAD: TOPIC_OVERHEAD_PAYMENT_UPDATE,
	SOURCE_PROJECT: TOPIC_ACCOUNT_HEAD_PAYMENT_UPDATE,
}


class PaymentSettlementConsumerHandler:
	"""
	Consumes the settlement decision for one payment, from either stream.

	Both streams carry the same envelope and the same four statuses; only the id field
	names differ, and the project stream additionally echoes its own creations. The DTO
	normalises the first difference and `is_creation_echo` handles the second, so
	everything below is source-agnostic.

	**Returning True acknowledges the message.** An unresolvable or already-applied
	message returns True deliberately: replaying it forever would block the partition and
	it will never resolve on a retry. Only an unexpected exception returns False.
	"""

	@classmethod
	def handle(cls, message: dict, source: str) -> bool:
		topic = _TOPIC_BY_SOURCE[source]
		try:
			dto = PaymentSettlementDTO.from_message(message, source)
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Payment Settlement - Malformed Message")
			log_consumer_event("PAYMENT_SETTLEMENT", "unknown", topic, "FAILED", str(e))
			return True

		if not dto.status:
			log_consumer_event("PAYMENT_SETTLEMENT", str(dto.payment_id or "unknown"), topic,
			                   "SKIPPED", "No paymentStatus on the message")
			return True

		try:
			doc_name = PaymentSettlementMapper.resolve_payment(dto)
			if not doc_name:
				# Nothing local to attach it to. Logged rather than retried: the payment
				# may have been raised outside this system, and no amount of redelivery
				# will make it resolve.
				log_consumer_event("PAYMENT_SETTLEMENT", str(dto.payment_id or "unknown"),
				                   topic, "SKIPPED", f"No matching payment for {dto}")
				return True

			current_status = frappe.db.get_value("AccountHeadPayment", doc_name, "payment_status")

			# A PENDING message on the project stream is normally our own publish coming
			# back. It is not a decision — but it carries their payment id, which is the
			# only source we have for it, so harvest and stop.
			if PaymentSettlementMapper.is_creation_echo(dto, current_status):
				PaymentSettlementMapper.record_accounts_payment_id(doc_name, dto)
				frappe.db.commit()
				log_consumer_event("PAYMENT_SETTLEMENT", doc_name, topic, "COMPLETED",
				                   f"Creation echo — recorded accounts id {dto.payment_id}")
				return True

			applied = PaymentSettlementMapper.apply(doc_name, dto)
			if not applied:
				log_consumer_event("PAYMENT_SETTLEMENT", doc_name, topic, "COMPLETED",
				                   f"Already applied: {dto.status}")
				return True

			# Only a real decision is worth telling anyone about; a deliberate reset back
			# to PENDING moves the row but raises no alarm.
			if dto.is_decision:
				PaymentSettlementMapper.notify(doc_name, dto)

			frappe.db.commit()
			log_consumer_event("PAYMENT_SETTLEMENT", doc_name, topic, "COMPLETED", str(dto))
			return True

		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(frappe.get_traceback(), "Payment Settlement Consumer Error")
			log_consumer_event("PAYMENT_SETTLEMENT", str(dto.payment_id or "unknown"),
			                   topic, "FAILED", str(e))
			return False


def handle_overhead_payment_update(message: dict) -> bool:
	"""Handler for `accounts-overheadpayment-update` (PDF / DPF funds)."""
	return PaymentSettlementConsumerHandler.handle(message, SOURCE_OVERHEAD)


def handle_account_head_payment_update(message: dict) -> bool:
	"""Handler for `accounts-accountheadpayment-update` (project account heads)."""
	return PaymentSettlementConsumerHandler.handle(message, SOURCE_PROJECT)
