# Copyright (c) 2026, rndops and Contributors
# See license.txt

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp import kafka_sync
from rndopsapp.rndopsapp.kafka import utils as kafka_utils
from rndopsapp.rndopsapp.kafka.utils import extract_project_number

ENVELOPE = {
	"schemaVersion": "1.0",
	"eventType": "FUND_RECEIVED",
	"timestamp": "2026-11-04T10:00:00",
	"data": {"projectNumber": "2627R-0213-NANO1355TADU", "amountReceived": 1.5},
}


class _Meta:
	partition, offset = 2, 41


class _Future:
	def __init__(self, fail=False):
		self.fail = fail

	def get(self, timeout=None):
		if self.fail:
			raise RuntimeError("broker down")
		return _Meta()


class _Producer:
	"""Records what is sent; `fail_topics` raise like an unreachable broker."""

	def __init__(self, fail_topics=()):
		self.sent = []
		self.fail_topics = set(fail_topics)

	def send(self, topic, key=None, value=None):
		self.sent.append((topic, key, value))
		return _Future(fail=topic in self.fail_topics)


def _rows(**filters):
	return frappe.get_all(
		"Kafka Publish Data Log", filters=filters,
		fields=["name", "project_number", "topic", "event_type", "status", "reference_name", "kafka_key",
				"source", "attempts", "partition", "offset", "sent_to_dlq", "error_message", "payload"],
		order_by="creation asc",
	)


class TestKafkaPublishDataLog(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Kafka Publish Data Log")

	def test_extract_project_number(self):
		self.assertEqual(extract_project_number(ENVELOPE), "2627R-0213-NANO1355TADU")
		self.assertEqual(extract_project_number({"projectNumber": "P-1"}), "P-1")
		self.assertEqual(extract_project_number({"data": {"batch": [{"projectNumber": "P-2"}]}}), "P-2")
		self.assertEqual(extract_project_number({"data": {"x": 1}}, key="P-3"), "P-3")
		self.assertIsNone(extract_project_number({"data": {"x": 1}}))
		# the envelope's own data wins over an unrelated nested value
		self.assertEqual(
			extract_project_number({"meta": {"projectNumber": "WRONG"}, "data": {"projectNumber": "RIGHT"}}), "RIGHT"
		)

	def _check_success(self, source):
		rows = _rows(source=source)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(
			(row.project_number, row.topic, row.event_type, row.status, row.reference_name, row.kafka_key),
			("2627R-0213-NANO1355TADU", "fund-received-events", "FUND_RECEIVED", "SUCCESS", "FR-1", "2627R-0213-NANO1355TADU"),
		)
		self.assertEqual((row.attempts, row.partition, row.offset, row.sent_to_dlq), (1, 2, "41", 0))
		# the stored payload is exactly what was sent
		self.assertEqual(json.loads(row.payload), ENVELOPE)

	def test_kafka_utils_logs_a_successful_publish(self):
		producer = _Producer()
		with mock.patch.object(kafka_utils, "get_producer", return_value=producer):
			ok = kafka_utils.publish_message(
				"fund-received-events", ENVELOPE, "FR-1", "fund-received-events-dlq", key="2627R-0213-NANO1355TADU"
			)
		self.assertTrue(ok)
		self.assertEqual(producer.sent[0][2], ENVELOPE)
		self._check_success("kafka.utils")

	def test_kafka_sync_logs_a_successful_publish(self):
		producer = _Producer()
		with mock.patch.object(kafka_sync, "get_producer", return_value=producer):
			ok = kafka_sync.publish_message(
				"fund-received-events", ENVELOPE, "FR-1", "fund-received-events-dlq", key="2627R-0213-NANO1355TADU"
			)
		self.assertTrue(ok)
		self._check_success("kafka_sync")

	def _check_failure(self, publish, patch_target, source):
		# the main topic always fails, the DLQ topic works
		producer = _Producer(fail_topics={"fund-received-events"})
		with mock.patch.object(patch_target, "get_producer", return_value=producer), \
				mock.patch("time.sleep"):
			ok = publish("fund-received-events", ENVELOPE, "FR-2", "fund-received-events-dlq", key="P-9")
		self.assertFalse(ok)
		rows = _rows(source=source)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual((row.status, row.sent_to_dlq, row.reference_name), ("FAILED", 1, "FR-2"))
		self.assertIn("broker down", row.error_message)
		self.assertGreaterEqual(row.attempts, 1)
		self.assertEqual(row.project_number, "2627R-0213-NANO1355TADU")
		self.assertEqual(json.loads(row.payload), ENVELOPE)

	def test_kafka_utils_logs_a_failed_publish_that_went_to_the_dlq(self):
		self._check_failure(kafka_utils.publish_message, kafka_utils, "kafka.utils")

	def test_kafka_sync_logs_a_failed_publish_that_went_to_the_dlq(self):
		self._check_failure(kafka_sync.publish_message, kafka_sync, "kafka_sync")

	def test_producer_unavailable_is_logged_as_failed(self):
		for module, source in ((kafka_utils, "kafka.utils"), (kafka_sync, "kafka_sync")):
			with mock.patch.object(module, "get_producer", return_value=None):
				self.assertFalse(module.publish_message("t", ENVELOPE, "FR-3", None, key="P-1"))
		rows = _rows()
		self.assertEqual(sorted((r.source, r.status, r.attempts) for r in rows),
						 [("kafka.utils", "FAILED", 0), ("kafka_sync", "FAILED", 0)])

	def test_a_logging_error_never_breaks_publishing(self):
		producer = _Producer()
		with mock.patch.object(kafka_utils, "get_producer", return_value=producer), \
				mock.patch.object(frappe, "get_doc", side_effect=RuntimeError("table missing")):
			self.assertTrue(kafka_utils.publish_message("t", ENVELOPE, "FR-4", None, key="P-1"))
