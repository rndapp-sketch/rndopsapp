# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Kafka trace: everything the app knows about what was sent to (and came back from) Kafka for
one project, joined into a single timeline.

    GET /api/method/rndopsapp.rndopsapp.kafka.trace_api.get_kafka_trace?project_number=...

Sources read (all of them, see SOURCES):
    Kafka Publish Data Log   - the exact message of every publish        (has the project number)
    Kafka Consumer Data Log  - every message consumed, and why it failed (has the project number)
    Kafka Commit Staging     - staged commits and their publish status   (project number is inside the payload)
    Kafka Publish State Log  - the state a document had before publish   (only doctype + name)
    Kafka Event DLQ Log      - messages the ledger rejected              (has the project number)
    Kafka Payment DLQ Log    - payments the ledger rejected              (has the project number)
    Error Log                - Kafka-related errors                      (free text)
    kafka/logs/files/*.log   - producer / consumer / error log files     (free text: "doc=<name>")
    Mattermost "kafka logs"  - send-only, cannot be read back

Only some of those carry the project number, so the missing links are made through the
documents: every document that belongs to the project is resolved with the app's own
project-link map (project_type_links.DOCTYPE_PR_LINKS), and each source is joined to the
project by document name. Each event in the timeline therefore carries
`reference_doctype` / `reference_name`, and `references` rolls the events up per document.
"""

import glob
import json
import os
import re
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from rndopsapp.rndopsapp.doctype.module_registry.project_type_links import (
	DEPOSIT_SLIP_DOCTYPES,
	DOCTYPE_PR_LINKS,
	PR_NAME,
	PR_PROJECT_NO,
	SELF,
)
from rndopsapp.rndopsapp.kafka.logs import logger as kafka_logger

SOURCES = [
	"publish_data_log",
	"consumer_data_log",
	"commit_staging",
	"publish_state_log",
	"event_dlq_log",
	"payment_dlq_log",
	"error_log",
	"log_file",
]

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000
MAX_DOCS_PER_DOCTYPE = 300
MAX_ERROR_LOG_ROWS = 5000
PAYLOAD_PREVIEW = 400  # characters of a payload shown when include_payload is off

# log files read for the trace (current file plus any rotated backups: error.log.1, ...)
LOG_FILES = {
	"error": kafka_logger.ERROR_LOG_FILE,
	"producer": kafka_logger.PRODUCER_LOG_FILE,
	"consumer": kafka_logger.CONSUMER_LOG_FILE,
}
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (\S+) - (\w+) - (.*)$")
TOKEN_SPLIT = re.compile(r"[\s,;|=:'\"\[\]\(\)\{\}<>]+")
DOC_IN_LINE = re.compile(r"doc=(\S+)")

STATUS_BY_STAGING = {
	"PUBLISHED": "SUCCESS",
	"FAILED": "FAILED",
	"PENDING_APPROVAL": "PENDING",
	"CANCELLED": "CANCELLED",
}


# ── project and its documents ───────────────────────────────────────────────

def _find_project(project_number):
	"""(Project Registration name or None, project_no) for a project number or PR name."""
	value = (project_number or "").strip()
	if not value:
		frappe.throw(_("project_number is required."))
	name = frappe.db.get_value("Project Registration", value, "name") or frappe.db.get_value(
		"Project Registration", {"project_no": value}, "name"
	)
	if not name:
		return None, value
	return name, frappe.db.get_value("Project Registration", name, "project_no") or value


def _project_documents(pr_name, project_no):
	"""{document name: doctype} for the project's own documents, resolved through
	DOCTYPE_PR_LINKS. This is what ties name-only sources (state log, error log, log files) to
	the project."""
	found = {}
	if pr_name:
		found[pr_name] = "Project Registration"

	for doctype, mapping in DOCTYPE_PR_LINKS.items():
		if doctype == "Project Registration" or not frappe.db.exists("DocType", doctype):
			continue
		or_filters = []
		for strategy in (mapping.get("primary"), mapping.get("fallback")):
			if not strategy:
				continue
			kind, field = strategy
			if kind == SELF or not field or not frappe.db.has_column(doctype, field):
				continue
			if kind == PR_NAME and pr_name:
				or_filters.append([field, "=", pr_name])
			elif kind == PR_PROJECT_NO and project_no:
				or_filters.append([field, "=", project_no])
		if not or_filters:
			continue
		for name in frappe.get_all(doctype, or_filters=or_filters, pluck="name", limit=MAX_DOCS_PER_DOCTYPE):
			found.setdefault(name, doctype)
	return found


# ── helpers ─────────────────────────────────────────────────────────────────

def _iso(value):
	if not value:
		return None
	return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def _preview(text, include_payload):
	if text is None:
		return None
	return text if include_payload else (text[:PAYLOAD_PREVIEW] + ("…" if len(text) > PAYLOAD_PREVIEW else ""))


def _strip_po(name):
	"""Legacy Direct Purchase PO commits are staged as '<DP>-po'."""
	name = name or ""
	return name[:-3] if name.endswith("-po") else name


DETAIL_KEYS_LIMIT = 30


def _payload_details(text):
	"""The flat facts of a message (amounts, status, reference numbers, ...) so they can be read
	without opening the payload: the scalar fields of `data` (or of the payload itself)."""
	try:
		payload = json.loads(text or "{}")
	except ValueError:
		return None
	if not isinstance(payload, dict):
		return None
	data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
	details = {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool)) or v is None}
	if payload is not data:
		for k in ("eventType", "schemaVersion", "timestamp"):
			if payload.get(k) is not None:
				details[k] = payload[k]
	return dict(list(details.items())[:DETAIL_KEYS_LIMIT]) or None


def _event(time, source, id, status, kind, reference_name=None, reference_doctype=None, topic=None, message=None, **extra):
	e = {
		"time": time,
		"source": source,
		"id": id,
		"status": status,
		"kind": kind,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"topic": topic,
		"message": message,
	}
	e.update({k: v for k, v in extra.items() if v is not None})
	return e


# ── one reader per source ───────────────────────────────────────────────────

def _read_publish_data_log(project_no, since, limit, include_payload):
	events = []
	rows = frappe.get_all(
		"Kafka Publish Data Log",
		filters={"project_number": project_no, **({"creation": [">=", since]} if since else {})},
		fields=["name", "creation", "topic", "event_type", "status", "reference_name", "kafka_key",
				"source", "attempts", "partition", "offset", "sent_to_dlq", "error_message", "payload"],
		order_by="creation desc",
		limit=limit,
	)
	for r in rows:
		msg = r.error_message or (f"{r.event_type or 'message'} published (partition {r.partition}, offset {r.offset})"
								  if r.status == "SUCCESS" else "publish failed")
		events.append(_event(
			_iso(r.creation), "publish_data_log", r.name, r.status, "publish", r.reference_name, None, r.topic, msg,
			event_type=r.event_type, publisher=r.source, attempts=r.attempts, sent_to_dlq=bool(r.sent_to_dlq),
			payload=_preview(r.payload, include_payload), details=_payload_details(r.payload),
		))
	return events


def _read_consumer_data_log(project_no, name_set, since, limit, include_payload):
	"""Messages the app consumed from Kafka. Those with a project number are matched on it; the
	rest (the handler only reported a document) are matched through the project's documents."""
	or_filters = [["project_number", "=", project_no]]
	if name_set:  # an empty "in ()" would match every row with a blank reference
		or_filters.append(["reference_name", "in", list(name_set)])
	rows = frappe.get_all(
		"Kafka Consumer Data Log",
		or_filters=or_filters,
		filters={**({"creation": [">=", since]} if since else {})},
		fields=["name", "creation", "topic", "event_type", "status", "reference_name", "handler", "is_dlq",
				"partition", "offset", "error_type", "failure_reason", "duration_ms", "processing_log", "payload"],
		order_by="creation desc",
		limit=limit,
	)
	return [
		_event(
			_iso(r.creation), "consumer_data_log", r.name, r.status, "consume", r.reference_name, None, r.topic,
			r.failure_reason if r.status in ("FAILED", "SKIPPED") else f"{r.event_type or 'message'} consumed (partition {r.partition}, offset {r.offset})",
			event_type=r.event_type, handler=r.handler, from_dlq_topic=bool(r.is_dlq), error_type=r.error_type,
			duration_ms=r.duration_ms, processing_log=r.processing_log,
			payload=_preview(r.payload, include_payload), details=_payload_details(r.payload),
		)
		for r in rows
	]


def _read_commit_staging(project_no, since, limit, include_payload):
	"""Staging rows carry the project number only inside the JSON payload (project_name)."""
	events = []
	conditions, values = ["payload like %s"], [f"%{project_no}%"]
	if since:
		conditions.append("creation >= %s")
		values.append(since)
	rows = frappe.db.sql(
		f"""select name, creation, modified, reference_doctype, reference_name, status, error_message, payload
		from `tabKafka Commit Staging` where {" and ".join(conditions)} order by creation desc limit %s""",
		(*values, limit * 3),
		as_dict=True,
	)
	for r in rows:
		try:
			payload = json.loads(r.payload or "{}")
		except ValueError:
			continue
		if str(payload.get("project_name") or "").strip() != project_no:
			continue
		app_id = payload.get("frap_app_id")
		events.append(_event(
			_iso(r.modified if r.status == "PUBLISHED" else r.creation), "commit_staging", r.name,
			STATUS_BY_STAGING.get(r.status, r.status), "commit",
			_strip_po(r.reference_name), r.reference_doctype, None,
			r.error_message or f"{payload.get('budget_head')} commit of {payload.get('commit_amount')} is {r.status}",
			frap_app_id=app_id, trigger_state=payload.get("trigger_state"),
			staged_as=r.reference_name if r.reference_name != _strip_po(r.reference_name) else None,
			payload=_preview(r.payload, include_payload), details=_payload_details(r.payload),
		))
		if len(events) >= limit:
			break
	return events


def _read_state_log(names, since, limit):
	if not names:
		return []
	rows = frappe.get_all(
		"Kafka Publish State Log",
		filters={"reference_name": ["in", list(names)], **({"creation": [">=", since]} if since else {})},
		fields=["name", "creation", "reference_doctype", "reference_name", "topic", "status",
				"previous_workflow_state", "published_state", "error_message"],
		order_by="creation desc",
		limit=limit,
	)
	return [
		_event(
			_iso(r.creation), "publish_state_log", r.name,
			"REVERTED" if r.status == "DLQ_REVERTED" else "SUCCESS", "state",
			r.reference_name, r.reference_doctype, r.topic,
			r.error_message or f"{r.previous_workflow_state} → {r.published_state} ({r.status})",
			previous_workflow_state=r.previous_workflow_state, published_state=r.published_state,
		)
		for r in rows
	]


def _read_event_dlq(project_no, since, limit, include_payload):
	rows = frappe.get_all(
		"Kafka Event DLQ Log",
		filters={"project_number": project_no, **({"creation": [">=", since]} if since else {})},
		fields=["name", "creation", "source_topic", "event_type", "reference_doctype", "reference_name",
				"previous_workflow_state", "reverted", "raw_payload"],
		order_by="creation desc",
		limit=limit,
	)
	return [
		_event(
			_iso(r.creation), "event_dlq_log", r.name, "REVERTED" if r.reverted else "DLQ", "dlq",
			r.reference_name, r.reference_doctype, r.source_topic,
			f"{r.event_type or 'event'} rejected by the ledger"
			+ (f"; document reverted to {r.previous_workflow_state}" if r.reverted else ""),
			event_type=r.event_type, previous_workflow_state=r.previous_workflow_state,
			payload=_preview(r.raw_payload, include_payload), details=_payload_details(r.raw_payload),
			reverted=bool(r.reverted),
		)
		for r in rows
	]


def _read_payment_dlq(project_no, since, limit, include_payload):
	rows = frappe.get_all(
		"Kafka Payment DLQ Log",
		filters={"project_number": project_no, **({"creation": [">=", since]} if since else {})},
		fields=["name", "creation", "account_head_id", "error_type", "error_message", "reference_doctype",
				"reference_name", "consumer_name", "original_topic", "dlq_topic", "failed_at", "raw_payload"],
		order_by="creation desc",
		limit=limit,
	)
	return [
		_event(
			_iso(r.creation), "payment_dlq_log", r.name, "DLQ", "dlq",
			r.reference_name, r.reference_doctype, r.original_topic or r.dlq_topic,
			r.error_message or r.error_type or "payment rejected by the ledger",
			account_head_id=r.account_head_id, error_type=r.error_type, consumer=r.consumer_name,
			failed_at=r.failed_at, payload=_preview(r.raw_payload, include_payload),
			details=_payload_details(r.raw_payload),
		)
		for r in rows
	]


def _tokens(text):
	"""Words of a free-text message, without the punctuation a sentence puts around a name
	("... found for 202610237A005749. All staging ..." must still match 202610237A005749)."""
	return {t.strip(".,;:!?") for t in TOKEN_SPLIT.split(text or "") if len(t.strip(".,;:!?")) >= 4}


def _read_error_log(project_no, name_set, since, limit):
	"""Kafka-related Error Log rows whose title/text mention the project or one of its documents."""
	conditions = [
		"(method like %s or method like %s or method like %s or error like %s or error like %s)"
	]
	values = ["%Kafka%", "%KAFKA%", "%DLQ%", "%Kafka%", "%KAFKA%"]
	if since:
		conditions.append("creation >= %s")
		values.append(since)
	rows = frappe.db.sql(
		f"""select name, creation, method, error from `tabError Log`
		where {" and ".join(conditions)} order by creation desc limit %s""",
		(*values, MAX_ERROR_LOG_ROWS),
		as_dict=True,
	)
	events = []
	for r in rows:
		text = f"{r.method or ''}\n{r.error or ''}"
		hit = _tokens(text) & name_set
		if project_no not in text and not hit:
			continue
		first_line = (r.error or "").strip().splitlines()[0] if (r.error or "").strip() else ""
		events.append(_event(
			_iso(r.creation), "error_log", r.name, "ERROR", "error",
			sorted(hit)[0] if hit else None, None, None, f"{r.method}: {first_line}"[:500],
			matched_by="project_number" if project_no in text else "document",
		))
		if len(events) >= limit:
			break
	return events


def _log_file_paths(path):
	"""The current file and its rotated backups (path.1, path.2, ...), newest first."""
	return [path] + sorted(glob.glob(path + ".*"))


def _read_log_files(project_no, name_set, since, limit):
	"""Lines of the Kafka log files that mention the project number, or "doc=<name>" of one of
	the project's documents."""
	events = []
	since_dt = get_datetime(since) if since else None
	for kind, path in LOG_FILES.items():
		matched = []
		for file_path in _log_file_paths(path):
			if not os.path.exists(file_path):
				continue
			with open(file_path, encoding="utf-8", errors="replace") as fh:
				for line in fh:
					if project_no not in line:
						m = DOC_IN_LINE.search(line)
						if not m or m.group(1) not in name_set:
							continue
					parsed = LOG_LINE.match(line.rstrip("\n"))
					if not parsed:
						continue
					when = datetime.strptime(parsed.group(1), "%Y-%m-%d %H:%M:%S")
					if since_dt and when < since_dt:
						continue
					doc = DOC_IN_LINE.search(line)
					level = parsed.group(3)
					matched.append((when, parsed, doc.group(1) if doc and doc.group(1) != "N/A" else None, level))
		matched.sort(key=lambda m: m[0], reverse=True)
		for when, parsed, doc, level in matched[:limit]:
			status = "FAILED" if level in ("ERROR", "CRITICAL") or "[FAILED]" in parsed.group(4) else "INFO"
			events.append(_event(
				when.strftime("%Y-%m-%d %H:%M:%S.000000"), "log_file", f"{kind}.log", status, "log",
				doc, None, None, parsed.group(4)[:600], logger=parsed.group(2), level=level, file=f"{kind}.log",
			))
	return events


# ── roll-ups ────────────────────────────────────────────────────────────────

def _fill_reference_doctypes(events, known):
	"""Give name-only events (publish data log, error log, log files) a doctype using what the
	other sources and the project's documents know about that name."""
	for e in events:
		if e["reference_name"] and not e["reference_doctype"]:
			e["reference_doctype"] = known.get(e["reference_name"]) or known.get(_strip_po(e["reference_name"]))


def _references(events):
	"""One row per document: what happened to it across every source."""
	refs = {}
	for e in sorted(events, key=lambda x: x["time"] or ""):
		name = e["reference_name"]
		if not name:
			continue
		r = refs.setdefault(name, {
			"reference_name": name, "reference_doctype": None, "events": 0, "sources": set(), "topics": set(),
			"first_at": e["time"], "last_at": None, "last_status": None,
			"published": 0, "failed": 0, "in_dlq": False, "reverted": False, "pending_commits": 0,
		})
		r["reference_doctype"] = r["reference_doctype"] or e["reference_doctype"]
		r["events"] += 1
		r["sources"].add(e["source"])
		if e["topic"]:
			r["topics"].add(e["topic"])
		r["last_at"] = e["time"]
		r.setdefault("kinds", set()).add(e["kind"])
		if e["kind"] in ("publish", "commit") and e["status"] in ("SUCCESS", "FAILED", "PENDING"):
			r["last_status"] = e["status"]
		if e["kind"] == "publish" and e["status"] == "SUCCESS":
			r["published"] += 1
		if e["status"] in ("FAILED", "ERROR"):
			r["failed"] += 1
		if e["kind"] == "dlq" or e.get("sent_to_dlq"):
			r["in_dlq"] = True
		if e["status"] == "REVERTED":
			r["reverted"] = True
		if e["kind"] == "commit" and e["status"] == "PENDING":
			r["pending_commits"] += 1
	out = []
	for r in refs.values():
		r["sources"], r["topics"], r["kinds"] = sorted(r["sources"]), sorted(r["topics"]), sorted(r["kinds"])
		r["published"] = r["published"] or (1 if "state" in r["kinds"] else 0)
		out.append(r)
	return sorted(out, key=lambda r: r["last_at"] or "", reverse=True)


def _summary(events, references):
	by_source = {s: 0 for s in SOURCES}
	for e in events:
		by_source[e["source"]] = by_source.get(e["source"], 0) + 1
	return {
		"events": len(events),
		"by_source": by_source,
		"documents": len(references),
		"published": sum(1 for e in events if e["kind"] == "publish" and e["status"] == "SUCCESS"),
		"failed_publishes": sum(1 for e in events if e["kind"] == "publish" and e["status"] == "FAILED"),
		"consumed": sum(1 for e in events if e["kind"] == "consume" and e["status"] == "SUCCESS"),
		"failed_consumes": sum(1 for e in events if e["kind"] == "consume" and e["status"] == "FAILED"),
		"skipped_consumes": sum(1 for e in events if e["kind"] == "consume" and e["status"] == "SKIPPED"),
		"dlq": sum(1 for e in events if e["kind"] == "dlq"),
		"reverted": sum(1 for e in events if e["status"] == "REVERTED"),
		"pending_commits": sum(1 for e in events if e["kind"] == "commit" and e["status"] == "PENDING"),
		"errors": sum(1 for e in events if e["source"] == "error_log"),
		"first_at": min((e["time"] for e in events if e["time"]), default=None),
		"last_at": max((e["time"] for e in events if e["time"]), default=None),
	}


# ── current state of each document, and what the data says went wrong ──────

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _describe_documents(references):
	"""Add the document's state right now to each reference: current_state, docstatus, modified,
	owner (and, for a Fund Received, the reference number accounts gave it)."""
	for r in references:
		doctype, name = r["reference_doctype"], r["reference_name"]
		if not doctype or not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
			continue
		wanted = ["workflow_state", "docstatus", "modified", "owner"]
		if doctype == "Fund Received":
			wanted.append("fund_received_ref_number")
		fields = [f for f in wanted if f == "docstatus" or frappe.db.has_column(doctype, f)]
		row = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
		r["current_state"] = row.get("workflow_state")
		r["docstatus"] = row.get("docstatus")
		r["modified"] = _iso(row.get("modified"))
		r["owner"] = row.get("owner")
		if doctype == "Fund Received":
			r["fund_received_ref_number"] = row.get("fund_received_ref_number") or None


def _fund_of_slip(slip_doctype, slip_name):
	"""The Fund Received a deposit slip points at (by docname or reference number), or None."""
	if not frappe.db.has_column(slip_doctype, "fund_received_ref"):
		return None
	ref = frappe.db.get_value(slip_doctype, slip_name, "fund_received_ref")
	if not ref:
		return None
	found = frappe.get_all(
		"Fund Received",
		or_filters=[["name", "=", ref], ["fund_received_ref_number", "=", ref]],
		fields=["name", "fund_received_ref_number", "workflow_state", "creation", "modified"],
		limit=1,
	)
	return found[0] if found else {"name": None, "missing_ref": ref}


def _finding(severity, code, ref, title, message, hint=None, evidence=None):
	return {
		"severity": severity,
		"code": code,
		"reference_doctype": ref["reference_doctype"],
		"reference_name": ref["reference_name"],
		"title": title,
		"message": message,
		"hint": hint,
		"evidence": evidence or {},
	}


def _findings(events, references):
	"""Plain-language problems, each with the likely cause and what to do. Built from facts in
	the sources above, never guessed: when the data cannot say, the finding says so."""
	by_ref = {}
	for e in events:
		if e["reference_name"]:
			by_ref.setdefault(e["reference_name"], []).append(e)

	out = []
	for ref in references:
		doctype, name = ref["reference_doctype"], ref["reference_name"]
		evs = by_ref.get(name, [])

		dlq = [e for e in evs if e["kind"] == "dlq"]
		if dlq:
			latest = dlq[0]  # events are newest first
			out.append(_finding(
				"high", "REJECTED_BY_LEDGER", ref, "Accounts rejected this message",
				f"Accounts could not process the {latest.get('event_type') or doctype or 'message'} and sent it back to "
				f"{latest['topic']} on {latest['time'][:19]}.",
				"The ledger sends no error text with a DLQ message, so the reason is not stored anywhere. "
				"See the findings below for what the data shows, fix the cause, then publish again.",
				{"dlq_event": latest["id"], "source": latest["source"], "times_rejected": len(dlq)},
			))
			if doctype in DEPOSIT_SLIP_DOCTYPES:
				fund = _fund_of_slip(doctype, name)
				sent_ref = (latest.get("details") or {}).get("fundReceivedRefNumber")
				if fund and fund.get("name") and not fund.get("fund_received_ref_number"):
					out.append(_finding(
						"high", "FUND_NOT_CONFIRMED", ref, "The Fund Received behind this slip was never confirmed by accounts",
						f"The slip was sent with fundReceivedRefNumber {sent_ref if sent_ref is not None else 0} because "
						f"Fund Received {fund['name']} has no reference number. Accounts gives that number when it confirms the "
						f"Fund Received, and it never did, so accounts has no fund to attach the slip to.",
						f"Find out why accounts has not processed Fund Received {fund['name']} (it is in '{fund['workflow_state']}'): "
						"the accounts consumer must handle fund-received-events and reply on accounts-fundreceived-update. "
						"Once it has a reference number, publish the deposit slip again.",
						{"fund_received": fund["name"], "fund_received_state": fund["workflow_state"],
						 "fund_received_ref_number": None, "slip_sent_fundReceivedRefNumber": sent_ref},
					))
				elif fund and not fund.get("name"):
					out.append(_finding(
						"high", "FUND_NOT_FOUND", ref, "The Fund Received this slip points at does not exist",
						f"fund_received_ref is {fund['missing_ref']} but no Fund Received has that name or reference number.",
						"Fix fund_received_ref on the slip and publish it again.", {"fund_received_ref": fund["missing_ref"]},
					))
			if not any(e.get("reverted") for e in dlq) and not any(e["source"] == "publish_state_log" for e in evs):
				has_state = ref.get("current_state") is not None
				out.append(_finding(
					"medium" if has_state else "low", "NOT_REVERTED", ref, "The document was not rolled back after the rejection",
					("No Kafka Publish State Log row exists for this publish, so the DLQ consumer did not know the state to "
					 f"revert to. The document stays in '{ref.get('current_state')}' as if accounts had accepted it.")
					if has_state else
					(f"{doctype} has no workflow state, so nothing is rolled back automatically: the document stays "
					 "submitted as if accounts had accepted it."),
					"Fix the cause, then publish the document again; set its state back by hand if it needs approval again."
					if has_state else "Fix the cause, then publish the document again.",
					{"current_state": ref.get("current_state"), "docstatus": ref.get("docstatus")},
				))

		if ref.get("published") or dlq:
			for dep in ref.get("depends_on", []):
				if not dep["published"] and dep["reference_doctype"] != "Project Registration":
					out.append(_finding(
						"low", "DEPENDENCY_NOT_PUBLISHED", ref, f"No record of {dep['reference_doctype']} {dep['reference_name']} being published",
						f"{doctype} {name} depends on {dep['reference_doctype']} {dep['reference_name']} (now '{dep['current_state']}'), "
						"but nothing in the Kafka records shows it was ever sent to accounts.",
						"If accounts does not know this document it cannot accept what depends on it: publish it first. "
						"(Documents sent before these logs existed may simply have no record.)",
						{"depends_on": dep["reference_name"], "dependency_state": dep["current_state"]},
					))

		if doctype == "Fund Received" and ref.get("current_state") is not None and not ref.get("fund_received_ref_number") and not dlq:
			published = [e for e in evs if (e["kind"] in ("publish", "state") and e["status"] == "SUCCESS")
						 or (e["source"] == "log_file" and e.get("file") == "producer.log" and "[PUBLISH] [SUCCESS]" in (e["message"] or ""))]
			if published:
				replies = [e for e in evs if e["kind"] == "consume" or (e["source"] == "log_file" and e.get("file") == "consumer.log")]
				out.append(_finding(
					"medium", "AWAITING_ACCOUNTS", ref, "Sent to accounts, but accounts has not confirmed it",
					f"Published on {published[-1]['time'][:19]}; it still has no reference number"
					+ (", and no message from accounts about it has been consumed." if not replies else "."),
					"Accounts must consume fund-received-events and answer on accounts-fundreceived-update. "
					"If that consumer is down or failing, nothing will come back.",
					{"state": ref.get("current_state"), "replies_in_consumer_log": len(replies)},
				))

		for e in evs:
			if e["kind"] == "consume" and e["status"] == "FAILED":
				out.append(_finding(
					"high", "CONSUME_FAILED", ref, "A message from accounts could not be processed",
					f"The app received a message on {e['topic']} on {e['time'][:19]} and failed to apply it: {e['message']}",
					"Fix the cause and have accounts send the message again; the stored payload shows what it contained.",
					{"consumer_log": e["id"], "handler": e.get("handler"), "error_type": e.get("error_type")},
				))
			if e["kind"] == "consume" and e["status"] == "SKIPPED":
				out.append(_finding(
					"medium", "CONSUME_SKIPPED", ref, "A message from accounts was received but ignored",
					f"The app received a message on {e['topic']} on {e['time'][:19]}, accepted it and did nothing: {e['message']}",
					"Accounts did reply, but the app could not match it to a document, so nothing was updated. "
					"Check that the reference in the message (see its payload) matches this document.",
					{"consumer_log": e["id"], "handler": e.get("handler")},
				))
			if e["kind"] == "publish" and e["status"] == "FAILED":
				out.append(_finding("high", "PUBLISH_FAILED", ref, "Publishing to Kafka failed", e["message"] or "publish failed",
									"Check the broker connection, then publish again.",
									{"event": e["id"], "attempts": e.get("attempts"), "sent_to_dlq": e.get("sent_to_dlq")}))
			elif e["kind"] == "commit" and e["status"] == "FAILED":
				out.append(_finding("high", "COMMIT_FAILED", ref, "A staged commit failed to publish", e["message"] or "commit failed",
									"Fix the cause and publish the staged commit again.", {"staging": e["id"]}))
			elif e["kind"] == "commit" and e["status"] == "PENDING":
				out.append(_finding("medium", "COMMIT_NOT_PUBLISHED", ref, "A staged commit was never published",
									f"Waiting for the document to reach '{e.get('trigger_state')}', which has not fired it.",
									"If the document is already past that state, publish the staged commit by hand.",
									{"staging": e["id"], "trigger_state": e.get("trigger_state")}))
		errors = [e for e in evs if e["source"] == "error_log"]
		if errors:
			out.append(_finding("low", "ERROR_LOGGED", ref, f"{len(errors)} error(s) in the Error Log mention this document",
								errors[0]["message"], None, {"error_log": [e["id"] for e in errors]}))

	out.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])
	return out


# ── connecting what the sources leave unconnected ───────────────────────────

# Keys that, inside a message, name the document it is about.
IDENTIFIER_KEYS = (
	"frapAppId", "frap_app_id", "depositSlipRefNumFab", "slipNumber", "fundReceivedRefNumberFap",
	"sanctionNumber", "referenceName", "applicationId",
)

# Reply / rejection topics -> the topic whose publish they answer
TOPIC_FAMILY = {
	"accounts-fundreceived-update": "fund-received-events",
	"accounts-depositslip-update": "deposit-slip-events",
	"accounts-accountheadpayment-update": "account-head-payment-events",
	"accounts-overheadpayment-update": "overhead-payment-events",
}


# Topics that are about exactly one kind of document
TOPIC_DOCTYPE = {
	"fund-sanction-events": "Fund Sanction",
	"fund-received-events": "Fund Received",
	"project-registration-events": "Project Registration",
}


def _family(topic):
	topic = TOPIC_FAMILY.get(topic or "", topic or "")
	return topic[:-4] if topic.endswith("-dlq") else topic


def _resolve_unreferenced(events, known, fund_by_refnum):
	"""Events that name no document (e.g. a commit DLQ row, which never stored one) get one from
	the identifiers inside their message, if that identifier is a document of this project."""
	resolved = 0
	for e in events:
		if e["reference_name"]:
			continue
		details = e.get("details") or {}
		candidate, how = None, None
		for key in IDENTIFIER_KEYS:
			value = details.get(key)
			if value not in (None, "") and str(value) in known:
				candidate, how = str(value), key
				break
		if not candidate:
			number = details.get("fundReceivedRefNumber")
			if number not in (None, "", 0) and str(number) in fund_by_refnum:
				candidate, how = fund_by_refnum[str(number)], "fundReceivedRefNumber"
		if not candidate:
			# A project has one Project Registration and usually one Fund Sanction; when the
			# topic says which kind of document the message is about and the project has
			# exactly one of that kind, that is the document.
			doctype = TOPIC_DOCTYPE.get(_family(e["topic"]))
			same_kind = [name for name, dt in known.items() if doctype and dt == doctype]
			if len(same_kind) == 1:
				candidate, how = same_kind[0], f"the project's only {doctype}"
		if candidate:
			e["reference_name"] = candidate
			e["reference_doctype"] = e["reference_doctype"] or known.get(candidate)
			e["resolved_by"] = how if how.startswith("the project") else f"payload.{how}"
			resolved += 1
	return resolved


def _link_causes(events):
	"""Tie each rejection (DLQ) and each reply from accounts to the publish that triggered it:
	`caused_by` on the effect, `led_to` on the cause. Same document, nearest earlier publish /
	staged commit / state change, preferring the same topic family."""
	chronological = sorted(events, key=lambda x: x["time"] or "")
	for i, e in enumerate(chronological):
		if e["kind"] not in ("dlq", "consume") or not e["reference_name"]:
			continue
		earlier = [c for c in chronological[:i]
				   if c["reference_name"] == e["reference_name"] and c["kind"] in ("publish", "commit", "state")]
		if not earlier:
			continue
		same_topic = [c for c in earlier if c["topic"] and _family(c["topic"]) == _family(e["topic"])]
		cause = (same_topic or earlier)[-1]
		e["caused_by"] = {"source": cause["source"], "id": cause["id"], "time": cause["time"], "kind": cause["kind"]}
		cause.setdefault("led_to", []).append({"source": e["source"], "id": e["id"], "kind": e["kind"], "status": e["status"]})


def _dependencies(references):
	"""What each document depends on, with that document's state: slip -> Fund Received ->
	Fund Sanction -> Project Registration."""
	in_trace = {r["reference_name"]: r for r in references}
	for r in references:
		doctype, name = r["reference_doctype"], r["reference_name"]
		target = None
		if doctype in DEPOSIT_SLIP_DOCTYPES:
			fund = _fund_of_slip(doctype, name)
			if fund and fund.get("name"):
				target = ("Fund Received", fund["name"])
		elif doctype == "Fund Received" and frappe.db.has_column("Fund Received", "sanction_ref_no"):
			sanction = frappe.db.get_value("Fund Received", name, "sanction_ref_no")
			if sanction and frappe.db.exists("Fund Sanction", sanction):
				target = ("Fund Sanction", sanction)
		elif doctype == "Fund Sanction":
			project = frappe.db.get_value("Fund Sanction", name, "project_proposal")
			if project and frappe.db.exists("Project Registration", project):
				target = ("Project Registration", project)
		r["depends_on"] = []
		if not target:
			continue
		dep_doctype, dep_name = target
		fields = ["docstatus"] + [f for f in ("workflow_state", "fund_received_ref_number") if frappe.db.has_column(dep_doctype, f)]
		row = frappe.db.get_value(dep_doctype, dep_name, fields, as_dict=True) or {}
		r["depends_on"].append({
			"reference_doctype": dep_doctype, "reference_name": dep_name,
			"current_state": row.get("workflow_state"), "docstatus": row.get("docstatus"),
			"fund_received_ref_number": row.get("fund_received_ref_number") or None,
			"in_trace": dep_name in in_trace,
			"published": bool(in_trace.get(dep_name, {}).get("published")),
		})


def _stage(references):
	"""A one-line status per document, from the facts collected: where is it in the round trip?"""
	for r in references:
		if r["in_dlq"] and not r["reverted"]:
			stage = "Rejected by accounts (in the DLQ)"
		elif r["in_dlq"]:
			stage = "Rejected by accounts and rolled back"
		elif r.get("fund_received_ref_number"):
			stage = f"Confirmed by accounts (reference {r['fund_received_ref_number']})"
		elif r["failed"]:
			stage = "Failed"
		elif r["pending_commits"]:
			stage = "Commit staged, not yet published"
		elif r["published"] or r["last_status"] == "SUCCESS":
			if r["reference_doctype"] == "Fund Received" or r["reference_doctype"] in DEPOSIT_SLIP_DOCTYPES:
				# accounts answers these (accounts-fundreceived-update / accounts-depositslip-update)
				stage = "Published; accounts has replied" if "consume" in r.get("kinds", []) else "Published, waiting for accounts"
			else:
				stage = "Published to accounts (no confirmation message expected)"
		else:
			stage = None
		r["stage"] = stage


# ── endpoint ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_kafka_trace(project_number, include_payload=0, limit=DEFAULT_LIMIT, from_date=None):
	"""Everything Kafka-related for one project, newest first.

	project_number   project number (or Project Registration name)
	include_payload  1 to include full message payloads (default: a 400-character preview)
	limit            events kept per source (default 200, max 1000)
	from_date        only events on/after this date or datetime

	{project_number, project: {name, project_no, project_title} | None, generated_at,
	 summary: {...counts..., findings: {high, medium, low}},
	 findings: [{severity, code, reference_doctype, reference_name, title, message, hint, evidence}],
	 unlinked: [events that could not be tied to any document, with why],
	 references: [{reference_doctype, reference_name, events, sources, topics, first_at, last_at,
	               last_status, published, failed, in_dlq, reverted, pending_commits}],
	 timeline: [{time, source, id, status, kind, reference_doctype, reference_name, topic, message, ...}],
	 not_available: ["Mattermost ..."]}

	System Manager only: the payloads contain project financial data.
	"""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Only System Manager can read the Kafka trace."), frappe.PermissionError)

	include_payload = cint(include_payload)
	limit = max(1, min(cint(limit) or DEFAULT_LIMIT, MAX_LIMIT))
	since = str(get_datetime(from_date)) if from_date else None

	pr_name, project_no = _find_project(project_number)
	documents = _project_documents(pr_name, project_no)

	events = []
	events += _read_publish_data_log(project_no, since, limit, include_payload)
	events += _read_commit_staging(project_no, since, limit, include_payload)
	events += _read_event_dlq(project_no, since, limit, include_payload)
	events += _read_payment_dlq(project_no, since, limit, include_payload)

	# Documents the project is known to have, plus those named by the sources that carry the
	# project number, so name-only sources (state log, error log, files) can be joined.
	known = dict(documents)
	for e in events:
		if e["reference_name"]:
			known.setdefault(e["reference_name"], e["reference_doctype"])
		if e.get("frap_app_id"):
			known.setdefault(str(e["frap_app_id"]), None)
	name_set = set(known)

	events += _read_consumer_data_log(project_no, name_set, since, limit, include_payload)
	events += _read_state_log(name_set, since, limit)
	for e in events:
		if e["reference_name"] and e["reference_doctype"]:
			known[e["reference_name"]] = e["reference_doctype"]
	events += _read_error_log(project_no, name_set, since, limit)
	events += _read_log_files(project_no, name_set, since, limit)

	fund_by_refnum = {
		str(f.fund_received_ref_number): f.name
		for f in (frappe.get_all("Fund Received", filters={"prjreg_title": pr_name},
								 fields=["name", "fund_received_ref_number"]) if pr_name else [])
		if f.fund_received_ref_number
	}
	resolved = _resolve_unreferenced(events, known, fund_by_refnum)
	_fill_reference_doctypes(events, {k: v for k, v in known.items() if v})
	events.sort(key=lambda e: e["time"] or "", reverse=True)
	_link_causes(events)
	references = _references(events)
	_describe_documents(references)
	_dependencies(references)
	_stage(references)
	findings = _findings(events, references)
	for r in references:
		r["findings"] = [f["code"] for f in findings if f["reference_name"] == r["reference_name"]]

	project = None
	if pr_name:
		project = {
			"name": pr_name,
			"project_no": project_no,
			"project_title": frappe.db.get_value("Project Registration", pr_name, "project_title"),
		}

	unlinked = [
		{"source": e["source"], "id": e["id"], "time": e["time"], "topic": e["topic"], "message": (e["message"] or "")[:200],
		 "why": "no document identifier in the record or its message matches a document of this project"}
		for e in events if not e["reference_name"]
	][:100]

	return {
		"project_number": project_no,
		"project": project,
		"generated_at": str(frappe.utils.now_datetime()),
		"summary": {
			**_summary(events, references),
			"findings": {sev: sum(1 for f in findings if f["severity"] == sev) for sev in SEVERITY_ORDER},
			"linked_by_payload": resolved,
			"unlinked_events": sum(1 for e in events if not e["reference_name"]),
		},
		"findings": findings,
		"unlinked": unlinked,
		"references": references,
		"timeline": events,
		"not_available": ['Mattermost "kafka logs" channel: notifications are send-only and cannot be read back.'],
	}
