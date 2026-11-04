# Copyright (c) 2026, rndops and Contributors
# See license.txt

import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.kafka.consumer import manager
from rndopsapp.rndopsapp.kafka.logs import logger as kafka_logger
from rndopsapp.rndopsapp.kafka.utils import _own_db_connection, consume_failure_reason

MESSAGE = {"eventType": "FUND_RECEIVED_UPDATE", "data": {"projectNumber": "2627R-TEST-0001", "amount": 5}}


def _db_rows(where="topic like 'test-%%'"):
	"""Read through a fresh connection: the rows are committed by the logger's own connection,
	which this test's open transaction would not see."""
	db = _own_db_connection()
	try:
		return db.sql(f"select * from `tabKafka Consumer Data Log` where {where} order by creation", as_dict=True)
	finally:
		db.close()


def _purge():
	db = _own_db_connection()
	try:
		db.sql("delete from `tabKafka Consumer Data Log` where topic like 'test-%%'")
		db.commit()
	finally:
		db.close()


def ok_handler(message):
	kafka_logger.log_consumer_event("FUND_RECEIVED_UPDATE", "REC-OK-1", "test-ok", "SUCCESS", "applied")
	return True


def quiet_fail_handler(message):
	kafka_logger.log_consumer_event("FUND_RECEIVED_UPDATE", "REC-BAD-2", "test-quiet-fail", "RECEIVED")
	kafka_logger.log_error("Fund Received REC-BAD-2 not found in the app", "FUND_RECEIVED_UPDATE_ERROR")
	return False


def skipping_handler(message):
	# what the real fund-received handler does for a document it cannot find
	kafka_logger.log_consumer_event("FUND_RECEIVED_UPDATE", "999", "test-skip", "RECEIVED")
	kafka_logger.log_consumer_event("FUND_RECEIVED_UPDATE", "999", "test-skip", "SKIPPED", "Document not found")
	return True


def raising_handler(message):
	raise ValueError("boom: bad amount")


def bare_false_handler(message):
	return False


class TestKafkaConsumerDataLog(FrappeTestCase):
	def setUp(self):
		_purge()
		self.addCleanup(_purge)
		patcher = mock.patch.dict(
			manager.TOPIC_HANDLERS,
			{"test-ok": ok_handler, "test-quiet-fail": quiet_fail_handler, "test-raises": raising_handler,
			 "test-bare-false": bare_false_handler, "test-x-dlq": ok_handler, "test-skip": skipping_handler},
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		log_patch = mock.patch("frappe.log_error")  # the handler wrapper writes an Error Log row on exceptions
		log_patch.start()
		self.addCleanup(log_patch.stop)

	def _consume(self, topic, partition=1, offset=10):
		return manager.process_message_with_context(topic, MESSAGE, partition, offset)

	def test_a_processed_message_is_logged_as_success(self):
		self.assertTrue(self._consume("test-ok", partition=3, offset=77))
		(row,) = _db_rows()
		self.assertEqual(
			(row.status, row.topic, row.project_number, row.event_type, row.reference_name, row.handler),
			("SUCCESS", "test-ok", "2627R-TEST-0001", "FUND_RECEIVED_UPDATE", "REC-OK-1", "ok_handler"),
		)
		self.assertEqual((row.partition, row.offset, row.is_dlq), (3, "77", 0))
		self.assertIsNone(row.failure_reason)
		self.assertEqual(json.loads(row.payload), MESSAGE)
		self.assertIn("applied", row.processing_log)
		self.assertGreaterEqual(row.duration_ms, 0)

	def test_a_failure_the_handler_reports_keeps_its_reason(self):
		self.assertFalse(self._consume("test-quiet-fail"))
		(row,) = _db_rows()
		self.assertEqual((row.status, row.reference_name), ("FAILED", "REC-BAD-2"))
		self.assertEqual(row.error_type, "FUND_RECEIVED_UPDATE_ERROR")
		self.assertEqual(row.failure_reason, "Fund Received REC-BAD-2 not found in the app")
		self.assertIn("REC-BAD-2", row.processing_log)

	def test_a_message_the_handler_accepted_but_ignored_is_skipped_not_success(self):
		self.assertTrue(self._consume("test-skip"))  # the handler still returns True, so the offset moves on
		(row,) = _db_rows()
		self.assertEqual((row.status, row.error_type, row.reference_name), ("SKIPPED", "SKIPPED", "999"))
		self.assertEqual(row.failure_reason, "999: Document not found")

	def test_an_exception_is_stored_with_its_type_and_message(self):
		self.assertFalse(self._consume("test-raises"))
		(row,) = _db_rows()
		self.assertEqual((row.status, row.error_type), ("FAILED", "HANDLER_EXCEPTION"))
		self.assertEqual(row.failure_reason, "ValueError: boom: bad amount")

	def test_a_bare_false_and_an_unknown_topic_say_so(self):
		self.assertFalse(self._consume("test-bare-false"))
		self.assertFalse(self._consume("test-unknown"))
		bare, unknown = _db_rows()
		self.assertEqual(bare.failure_reason, "The handler returned False without reporting a reason.")
		self.assertEqual((unknown.error_type, unknown.failure_reason), ("NO_HANDLER", "No handler found for topic: test-unknown"))
		self.assertIsNone(unknown.handler)

	def test_dead_letter_topics_are_flagged(self):
		self._consume("test-x-dlq")
		(row,) = _db_rows()
		self.assertEqual(row.is_dlq, 1)

	def test_the_row_survives_a_rollback_and_does_not_commit_the_handlers_work(self):
		marker = frappe.generate_hash(length=8)

		def half_done_handler(message):
			frappe.db.sql("insert into tabNote (name, title, creation, modified) values (%s, 'half', now(), now())", marker)
			kafka_logger.log_error("could not finish", "HALF_DONE")
			return False

		with mock.patch.dict(manager.TOPIC_HANDLERS, {"test-bare-false": half_done_handler}):
			self.assertFalse(self._consume("test-bare-false"))

		self.assertEqual(len(_db_rows()), 1)  # the log row was committed by its own connection
		db = _own_db_connection()
		try:
			# the handler's uncommitted insert is invisible to (and was not committed by) the logger
			self.assertEqual(db.sql("select count(*) from tabNote where name=%s", marker)[0][0], 0)
		finally:
			db.close()
		frappe.db.rollback()
		self.assertEqual(frappe.db.sql("select count(*) from tabNote where name=%s", marker)[0][0], 0)

	def test_a_logging_error_never_breaks_consuming(self):
		with mock.patch("rndopsapp.rndopsapp.kafka.utils._own_db_connection", side_effect=RuntimeError("db gone")):
			self.assertTrue(self._consume("test-ok"))
		self.assertEqual(_db_rows(), [])

	def test_the_writer_works_when_partition_offset_and_duration_are_unknown(self):
		from rndopsapp.rndopsapp.kafka.utils import log_consume_data

		log_consume_data("test-ok", MESSAGE, True)
		(row,) = _db_rows()
		self.assertEqual((row.status, row.partition, row.offset, row.duration_ms), ("SUCCESS", 0, None, 0))

	def test_capture_is_off_outside_a_message(self):
		kafka_logger.log_error("not captured", "X")  # no capture running: must not raise or leak
		kafka_logger.start_capture()
		kafka_logger.log_error("captured", "X")
		self.assertEqual([e["message"] for e in kafka_logger.stop_capture()], ["captured"])
		self.assertEqual(kafka_logger.stop_capture(), [])

	def test_failure_reason_prefers_the_exception_then_the_handlers_account(self):
		events = [{"kind": "event", "type": "CONSUME", "status": "FAILED", "doc": "N/A", "message": "wrapper noise"},
				  {"kind": "error", "type": "E1", "status": "ERROR", "doc": None, "message": "first"},
				  {"kind": "event", "type": "H", "status": "FAILED", "doc": "D", "message": "second"}]
		self.assertEqual(consume_failure_reason(events, KeyError("k")), ("EXCEPTION", "KeyError: 'k'"))
		self.assertEqual(consume_failure_reason(events), ("E1", "first; second"))
		self.assertEqual(consume_failure_reason([])[0], "HANDLER_FAILED")
