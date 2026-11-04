# Copyright (c) 2026, rndops and Contributors
# See license.txt

import json
import os
import tempfile
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.kafka import trace_api
from rndopsapp.rndopsapp.kafka.trace_api import get_kafka_trace
from rndopsapp.rndopsapp.kafka.utils import _own_db_connection, log_consume_data, log_publish_data

STAFF = "kafka.trace.user@example.com"


class TestKafkaTrace(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		row = frappe.db.sql(
			"""select pr.name pr_name, pr.project_no, fr.name fund
			from `tabProject Registration` pr join `tabFund Received` fr on fr.prjreg_title = pr.name
			where ifnull(pr.project_no, '') != '' and pr.docstatus = 1 limit 1""",
			as_dict=True,
		)
		if not row:
			raise cls.skipTest(cls, "needs a Project Registration with a Fund Received")
		cls.pr, cls.pn, cls.fund = row[0].pr_name, row[0].project_no, row[0].fund

		if frappe.db.exists("User", STAFF):
			frappe.delete_doc("User", STAFF, force=True, ignore_permissions=True)
		user = frappe.get_doc({"doctype": "User", "email": STAFF, "first_name": "trace", "send_welcome_email": 0,
							   "roles": [{"role": "Director"}]})
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)

	def setUp(self):
		frappe.set_user("Administrator")
		self.tmp = tempfile.mkdtemp()
		self.files = {k: os.path.join(self.tmp, f"{k}.log") for k in ("error", "producer", "consumer")}
		for path in self.files.values():
			open(path, "w").close()
		patcher = mock.patch.object(trace_api, "LOG_FILES", self.files)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _seed(self):
		"""One row in each source; only some of them carry the project number."""
		payload = {"eventType": "FUND_RECEIVED", "data": {"projectNumber": self.pn, "amountReceived": 5}}
		# 1. publish data log - has the project number, but no doctype for the document
		log_publish_data("fund-received-events", payload, self.fund, self.pn, "SUCCESS", "kafka.utils",
						 partition=1, offset=9)
		# 2. commit staging - project number only inside the payload
		frappe.get_doc({
			"doctype": "Kafka Commit Staging", "reference_doctype": "Fund Received", "reference_name": self.fund + "-po",
			"status": "FAILED", "error_message": "ledger said no",
			"payload": json.dumps({"project_name": self.pn, "budget_head": "Manpower", "commit_amount": 10,
								   "frap_app_id": self.fund, "trigger_state": "Approved"}),
		}).insert(ignore_permissions=True)
		# 3. publish state log - NO project number, only doctype + name
		frappe.get_doc({"doctype": "Kafka Publish State Log", "reference_doctype": "Fund Received",
						"reference_name": self.fund, "topic": "fund-received-events", "status": "DLQ_REVERTED",
						"previous_workflow_state": "Draft", "published_state": "Approved"}).insert(ignore_permissions=True)
		# 4. / 5. DLQ logs
		frappe.get_doc({"doctype": "Kafka Event DLQ Log", "project_number": self.pn, "event_type": "FUND_RECEIVED",
						"source_topic": "fund-received-events-dlq", "reference_doctype": "Fund Received",
						"reference_name": self.fund, "reverted": 1, "previous_workflow_state": "Draft",
						"raw_payload": "{}"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Kafka Payment DLQ Log", "project_number": self.pn, "account_head_id": 3,
						"error_message": "payment rejected", "reference_doctype": "AccountHeadPayment",
						"reference_name": "AHP-TEST-1", "raw_payload": "{}"}).insert(ignore_permissions=True)
		# 6. Error Log - free text, names the document only
		error_log = frappe.get_doc({"doctype": "Error Log", "method": "Kafka Publish Error",
									"error": f"Attempt 3/3 failed for fund-received-events: broker down ({self.fund}). Giving up"}
								   ).insert(ignore_permissions=True)
		# Error Log rows survive a rollback in Frappe, so remove it explicitly
		self.addCleanup(lambda: frappe.db.sql("delete from `tabError Log` where name = %s", error_log.name))
		# 7. log files - "doc=<name>" only, and a line with the project number only
		with open(self.files["producer"], "w") as fh:
			fh.write(f"2026-11-01 10:00:00 - kafka.producer - INFO - [FUND_RECEIVED] [SUCCESS] doc={self.fund} | topic=fund-received-events | ok\n")
			fh.write("2026-11-01 10:00:01 - kafka.producer - INFO - [OTHER] [SUCCESS] doc=UNRELATED-DOC | topic=x | ok\n")
		with open(self.files["error"], "w") as fh:
			fh.write(f"2026-11-01 10:05:00 - kafka.error - ERROR - [PUBLISH] [FAILED] doc=NOT-OURS | topic=t | projectNumber={self.pn}\n")

	def test_every_source_is_read_and_joined_to_the_project(self):
		self._seed()
		r = get_kafka_trace(self.pn)
		by_source = r["summary"]["by_source"]
		for source in ("publish_data_log", "commit_staging", "publish_state_log", "event_dlq_log",
					   "payment_dlq_log", "error_log", "log_file"):
			self.assertGreaterEqual(by_source[source], 1, source)

		self.assertEqual(r["project"]["project_no"], self.pn)
		self.assertTrue(r["not_available"])  # Mattermost is send-only

		timeline = r["timeline"]
		self.assertEqual([e["time"] for e in timeline], sorted((e["time"] for e in timeline), reverse=True))

		# the state log has no project number: it is joined through the document name
		state = [e for e in timeline if e["source"] == "publish_state_log" and e["reference_name"] == self.fund]
		self.assertEqual(len(state), 1)
		self.assertEqual(state[0]["status"], "REVERTED")

		# the staged "<doc>-po" row is attached to the document, not to the "-po" name
		staged = [e for e in timeline if e["source"] == "commit_staging" and e["reference_name"] == self.fund]
		self.assertTrue(staged and staged[0]["status"] == "FAILED" and staged[0]["staged_as"] == self.fund + "-po")

		# name-only sources: Error Log and a log file line that mention the document
		self.assertTrue([e for e in timeline if e["source"] == "error_log" and e["reference_name"] == self.fund])
		files = [e for e in timeline if e["source"] == "log_file"]
		self.assertTrue([e for e in files if e["reference_name"] == self.fund])
		self.assertTrue([e for e in files if e["file"] == "error.log" and e["status"] == "FAILED"])
		self.assertFalse([e for e in files if e["reference_name"] == "UNRELATED-DOC"])

		# the publish data log row had no doctype; it is filled in from the other sources
		published = [e for e in timeline if e["source"] == "publish_data_log"][0]
		self.assertEqual(published["reference_doctype"], "Fund Received")

	def test_references_roll_events_up_per_document(self):
		self._seed()
		refs = {x["reference_name"]: x for x in get_kafka_trace(self.pn)["references"]}
		fund = refs[self.fund]
		self.assertEqual(fund["reference_doctype"], "Fund Received")
		self.assertGreaterEqual(len(fund["sources"]), 5)
		self.assertTrue(fund["in_dlq"] and fund["reverted"])
		self.assertGreaterEqual(fund["published"], 1)
		self.assertGreaterEqual(fund["failed"], 1)
		self.assertIn("fund-received-events", fund["topics"])
		self.assertIn("AHP-TEST-1", refs)  # a payment DLQ row for a document of its own

	def test_options(self):
		self._seed()
		short = [e for e in get_kafka_trace(self.pn)["timeline"] if e["source"] == "event_dlq_log"][0]
		self.assertLessEqual(len(short["payload"] or ""), trace_api.PAYLOAD_PREVIEW + 1)
		big = {"projectNumber": self.pn, "pad": "x" * 2000}
		log_publish_data("t", big, "BIG-1", self.pn, "SUCCESS", "kafka.utils")
		full = [e for e in get_kafka_trace(self.pn, include_payload=1)["timeline"] if e["id"] and e["reference_name"] == "BIG-1"]
		trunc = [e for e in get_kafka_trace(self.pn)["timeline"] if e["reference_name"] == "BIG-1"]
		self.assertGreater(len(full[0]["payload"]), 2000)
		self.assertLess(len(trunc[0]["payload"]), 1000)

		self.assertEqual(get_kafka_trace(self.pn, from_date="2999-01-01")["summary"]["events"], 0)
		limited = get_kafka_trace(self.pn, limit=1)["summary"]["by_source"]
		self.assertTrue(all(v <= 1 for k, v in limited.items() if k != "log_file"))

	def test_project_can_be_given_by_registration_name_and_unknown_projects_are_empty(self):
		self._seed()
		self.assertEqual(get_kafka_trace(self.pr)["project_number"], self.pn)
		none = get_kafka_trace("NO-SUCH-PROJECT")
		self.assertIsNone(none["project"])
		self.assertEqual(none["summary"]["events"], 0)

	def test_only_system_manager(self):
		frappe.set_user(STAFF)
		with self.assertRaises(frappe.PermissionError):
			get_kafka_trace(self.pn)

	def test_payload_details_are_the_flat_facts_of_the_message(self):
		text = json.dumps({"eventType": "DEPOSIT_SLIP", "schemaVersion": "1.0",
						   "data": {"slipNumber": "S-1", "amountReceived": 5.5, "fundReceivedRefNumber": 0,
									"gstDetails": {"x": 1}, "ecsDates": ["2026-08-25"]}})
		details = trace_api._payload_details(text)
		self.assertEqual(details["slipNumber"], "S-1")
		self.assertEqual(details["fundReceivedRefNumber"], 0)  # 0 is a fact worth showing
		self.assertEqual(details["eventType"], "DEPOSIT_SLIP")
		self.assertNotIn("gstDetails", details)  # nested objects and lists are left to the payload
		self.assertNotIn("ecsDates", details)
		self.assertIsNone(trace_api._payload_details("not json"))

	def _ref(self, doctype, name, **extra):
		return {"reference_doctype": doctype, "reference_name": name, **extra}

	def _dlq_event(self, **extra):
		return {"time": "2026-10-15 18:05:20.000000", "source": "event_dlq_log", "id": "d1", "status": "DLQ", "kind": "dlq",
				"reference_doctype": "E Non Routine Deposit Slip", "reference_name": "SLIP-1",
				"topic": "deposit-slip-events-dlq", "message": "x", "event_type": "DEPOSIT_SLIP",
				"details": {"fundReceivedRefNumber": 0}, "reverted": False, **extra}

	def test_findings_explain_a_slip_sent_before_accounts_confirmed_its_fund(self):
		fund = {"name": "REC-1", "fund_received_ref_number": None, "workflow_state": "Pending Misc. Staff Approval"}
		with mock.patch.object(trace_api, "_fund_of_slip", return_value=fund):
			findings = trace_api._findings([self._dlq_event()],
										   [self._ref("E Non Routine Deposit Slip", "SLIP-1", current_state=None, docstatus=1)])
		codes = [f["code"] for f in findings]
		self.assertEqual(codes[:2], ["REJECTED_BY_LEDGER", "FUND_NOT_CONFIRMED"])
		cause = findings[1]
		self.assertIn("fundReceivedRefNumber 0", cause["message"])
		self.assertEqual(cause["evidence"]["fund_received"], "REC-1")
		self.assertEqual(findings[0]["severity"], "high")
		self.assertIn("NOT_REVERTED", codes)  # no state log, and a slip has no workflow state
		self.assertEqual([f for f in findings if f["code"] == "NOT_REVERTED"][0]["severity"], "low")

	def test_a_confirmed_fund_is_not_blamed(self):
		fund = {"name": "REC-1", "fund_received_ref_number": "423", "workflow_state": "Approved"}
		with mock.patch.object(trace_api, "_fund_of_slip", return_value=fund):
			findings = trace_api._findings([self._dlq_event(details={"fundReceivedRefNumber": 423})],
										   [self._ref("E Non Routine Deposit Slip", "SLIP-1", current_state=None, docstatus=1)])
		self.assertNotIn("FUND_NOT_CONFIRMED", [f["code"] for f in findings])

	def test_fund_received_waiting_for_accounts(self):
		published = {"time": "2026-09-15 17:40:21.000000", "source": "publish_state_log", "id": "s1", "status": "SUCCESS",
					 "kind": "state", "reference_doctype": "Fund Received", "reference_name": "REC-1", "topic": "t",
					 "message": "x"}
		ref = self._ref("Fund Received", "REC-1", current_state="Pending Misc. Staff Approval", fund_received_ref_number=None)
		findings = trace_api._findings([published], [ref])
		self.assertEqual([f["code"] for f in findings], ["AWAITING_ACCOUNTS"])
		self.assertEqual(findings[0]["evidence"]["replies_in_consumer_log"], 0)

		# once accounts has given it a reference number there is nothing to report
		ref["fund_received_ref_number"] = "77"
		self.assertEqual(trace_api._findings([published], [ref]), [])

	def test_findings_are_sorted_high_first_and_counted_in_the_summary(self):
		self._seed()
		result = get_kafka_trace(self.pn)
		severities = [f["severity"] for f in result["findings"]]
		self.assertEqual(severities, sorted(severities, key=trace_api.SEVERITY_ORDER.get))
		self.assertEqual(sum(result["summary"]["findings"].values()), len(result["findings"]))
		self.assertTrue(any(f["code"] == "REJECTED_BY_LEDGER" for f in result["findings"]))
		for r in result["references"]:
			self.assertIn("findings", r)

	def _purge_consumer_rows(self):
		db = _own_db_connection()
		try:
			db.sql("delete from `tabKafka Consumer Data Log` where topic like 'trace-test-%%'")
			db.commit()
		finally:
			db.close()

	def test_consumed_messages_and_their_failure_reasons_are_traced(self):
		self._purge_consumer_rows()
		self.addCleanup(self._purge_consumer_rows)
		ok_payload = {"eventType": "FUND_RECEIVED_UPDATE", "data": {"projectNumber": self.pn, "fundReceivedRefNumber": 12}}
		# one row has the project number in the message, the other only names the document
		log_consume_data("trace-test-ok", ok_payload, True, 0, 5, handler="h")
		log_consume_data(
			"trace-test-fail", {"eventType": "X", "data": {"slip": 1}}, False, 1, 6, handler="h",
			events=[{"kind": "event", "type": "DEPOSIT_SLIP_UPDATE", "status": "RECEIVED", "doc": self.fund, "message": ""},
					{"kind": "error", "type": "SLIP_ERROR", "status": "ERROR", "doc": None, "message": "No slip row for 77"}],
		)

		# the rows were committed by the logger's own connection; start a fresh snapshot to see
		# them, as a new web request would (nothing else was written through this connection)
		frappe.db.rollback()
		result = get_kafka_trace(self.pn)
		consumed = {e["topic"]: e for e in result["timeline"] if e["source"] == "consumer_data_log"}
		self.assertEqual(consumed["trace-test-ok"]["status"], "SUCCESS")
		self.assertEqual(consumed["trace-test-ok"]["details"]["fundReceivedRefNumber"], 12)

		failed = consumed["trace-test-fail"]  # joined through the document it reported
		self.assertEqual((failed["status"], failed["reference_name"]), ("FAILED", self.fund))
		self.assertEqual(failed["message"], "No slip row for 77")
		self.assertIn("No slip row for 77", failed["processing_log"])

		self.assertEqual(result["summary"]["by_source"]["consumer_data_log"], 2)
		self.assertEqual((result["summary"]["consumed"], result["summary"]["failed_consumes"]), (1, 1))
		finding = [f for f in result["findings"] if f["code"] == "CONSUME_FAILED"][0]
		self.assertEqual(finding["severity"], "high")
		self.assertIn("No slip row for 77", finding["message"])
		self.assertEqual(finding["evidence"]["consumer_log"], failed["id"])

	def test_a_consumed_message_counts_as_a_reply_from_accounts(self):
		published = {"time": "2026-09-15 17:40:21.000000", "source": "publish_state_log", "id": "s1", "status": "SUCCESS",
					 "kind": "state", "reference_doctype": "Fund Received", "reference_name": "REC-1", "topic": "t", "message": "x"}
		reply = {"time": "2026-09-16 09:00:00.000000", "source": "consumer_data_log", "id": "c1", "status": "SUCCESS",
				 "kind": "consume", "reference_doctype": "Fund Received", "reference_name": "REC-1", "topic": "u", "message": "ok"}
		ref = self._ref("Fund Received", "REC-1", current_state="Pending", fund_received_ref_number=None)
		finding = trace_api._findings([published, reply], [ref])[0]
		self.assertEqual(finding["evidence"]["replies_in_consumer_log"], 1)
		self.assertNotIn("no message from accounts", finding["message"])

	def test_a_skipped_reply_from_accounts_is_a_finding(self):
		skipped = {"time": "2026-10-01 10:00:00.000000", "source": "consumer_data_log", "id": "c9", "status": "SKIPPED",
				   "kind": "consume", "reference_doctype": "Fund Received", "reference_name": "REC-1",
				   "topic": "accounts-fundreceived-update", "message": "REC-1: Document not found", "handler": "h"}
		finding = trace_api._findings([skipped], [self._ref("Fund Received", "REC-1", current_state="Pending")])[0]
		self.assertEqual((finding["code"], finding["severity"]), ("CONSUME_SKIPPED", "medium"))
		self.assertIn("Document not found", finding["message"])

	def _e(self, id, kind, time, ref=None, topic=None, source="x", status="SUCCESS", **extra):
		return {"time": time, "source": source, "id": id, "status": status, "kind": kind, "reference_doctype": None,
				"reference_name": ref, "topic": topic, "message": "m", **extra}

	def test_events_naming_no_document_are_resolved_from_their_payload(self):
		known = {"APP-1": "Direct Purchase", "SAN-1": "Fund Sanction", "REC-1": "Fund Received"}
		by_app = self._e("d1", "dlq", "2026-10-01", topic="account-head-commit-events-dlq", details={"frapAppId": "APP-1"})
		by_number = self._e("d2", "dlq", "2026-10-01", topic="deposit-slip-events-dlq", details={"fundReceivedRefNumber": 77})
		by_topic = self._e("d3", "dlq", "2026-10-01", topic="fund-sanction-events-dlq", details={"projectNumber": "P"})
		foreign = self._e("d4", "dlq", "2026-10-01", topic="account-head-commit-events-dlq", details={"frapAppId": "NOT-OURS"})
		events = [by_app, by_number, by_topic, foreign]
		resolved = trace_api._resolve_unreferenced(events, known, {"77": "REC-1"})
		self.assertEqual(resolved, 3)
		self.assertEqual((by_app["reference_name"], by_app["reference_doctype"], by_app["resolved_by"]),
						 ("APP-1", "Direct Purchase", "payload.frapAppId"))
		self.assertEqual(by_number["reference_name"], "REC-1")
		self.assertEqual((by_topic["reference_name"], by_topic["resolved_by"]), ("SAN-1", "the project's only Fund Sanction"))
		self.assertIsNone(foreign["reference_name"])  # an identifier that is not ours is not guessed at

		# two sanctions: the topic alone no longer says which one
		ambiguous = self._e("d5", "dlq", "2026-10-01", topic="fund-sanction-events-dlq", details={})
		trace_api._resolve_unreferenced([ambiguous], {**known, "SAN-2": "Fund Sanction"}, {})
		self.assertIsNone(ambiguous["reference_name"])

	def test_a_rejection_or_reply_is_tied_to_the_publish_that_caused_it(self):
		old = self._e("p1", "publish", "2026-10-01 09:00", "REC-1", "fund-received-events")
		other_topic = self._e("p2", "state", "2026-10-02 09:00", "REC-1", "deposit-slip-events")
		latest = self._e("p3", "publish", "2026-10-03 09:00", "REC-1", "fund-received-events")
		reply = self._e("c1", "consume", "2026-10-04 09:00", "REC-1", "accounts-fundreceived-update")
		dlq = self._e("d1", "dlq", "2026-10-05 09:00", "REC-1", "fund-received-events-dlq")
		unrelated = self._e("c2", "consume", "2026-10-06 09:00", "REC-2", "accounts-fundreceived-update")
		trace_api._link_causes([old, other_topic, latest, reply, dlq, unrelated])

		self.assertEqual(reply["caused_by"]["id"], "p3")  # nearest earlier, same topic family
		self.assertEqual(dlq["caused_by"]["id"], "p3")
		self.assertEqual([x["id"] for x in latest["led_to"]], ["c1", "d1"])
		self.assertNotIn("led_to", old)
		self.assertNotIn("caused_by", unrelated)  # nothing earlier for that document

	def test_stage_says_where_each_document_is_in_the_round_trip(self):
		def ref(doctype, **kw):
			base = {"reference_doctype": doctype, "in_dlq": False, "reverted": False, "failed": 0, "pending_commits": 0,
					"published": 0, "last_status": None, "kinds": [], "fund_received_ref_number": None}
			return {**base, **kw}

		refs = [
			ref("Deposit Slip X", in_dlq=True),
			ref("Fund Received", fund_received_ref_number="42"),
			ref("Fund Received", published=1),
			ref("Fund Received", published=1, kinds=["consume"]),
			ref("Fund Sanction", published=1),
			ref("Travel", pending_commits=1),
			ref("Travel", failed=1),
			ref("Travel"),
		]
		trace_api._stage(refs)
		self.assertEqual([r["stage"] for r in refs], [
			"Rejected by accounts (in the DLQ)",
			"Confirmed by accounts (reference 42)",
			"Published, waiting for accounts",
			"Published; accounts has replied",
			"Published to accounts (no confirmation message expected)",  # accounts never answers a sanction
			"Commit staged, not yet published",
			"Failed",
			None,
		])

	def test_the_trace_exposes_the_connections(self):
		self._seed()
		result = get_kafka_trace(self.pn)
		self.assertIn("unlinked", result)
		self.assertEqual(result["summary"]["unlinked_events"], sum(1 for e in result["timeline"] if not e["reference_name"]))
		self.assertIn("linked_by_payload", result["summary"])
		for r in result["references"]:
			self.assertIn("stage", r)
			self.assertIsInstance(r["depends_on"], list)

