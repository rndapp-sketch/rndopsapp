# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class KafkaPublishDataLog(Document):
	"""One row per message handed to Kafka: the exact payload, where it went and how it
	ended. Written by rndopsapp.rndopsapp.kafka.utils.log_publish_data from both
	publish_message() implementations; never edited by hand."""

	pass
