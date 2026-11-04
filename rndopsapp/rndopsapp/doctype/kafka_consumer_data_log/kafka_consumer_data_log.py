# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class KafkaConsumerDataLog(Document):
	"""One row per message the consumer received: the payload, whether it was processed, and
	for a failure the reason. Written by rndopsapp.rndopsapp.kafka.utils.log_consume_data from
	consumer/manager.py; never edited by hand."""

	pass
