# Copyright (c) 2025, rndops and contributors
# Kafka Consumer Service - Central entry point for all Kafka consumer operations

import time
import frappe
from .log_reader import get_kafka_logs

# Per-process guards — each Gunicorn worker has its own copy of these
_restart_notified = False       # send at most one Mattermost ping per worker lifetime
_last_start_attempt = 0.0       # epoch seconds of the last restart attempt


@frappe.whitelist()
def fetch_kafka_logs(log_type='consumer', lines=50, search_string=None):
	"""
	Fetches the last N lines of the specified Kafka log.
	Allowed types: consumer, producer, error, debug, frappe, terminal.
	Optionally filters by search_string.
	"""
	return get_kafka_logs(log_type, lines, search_string)


@frappe.whitelist()
def start_kafka_consumer(**kwargs):
	from .consumer.manager import start_kafka_consumer as _fn
	return _fn()


@frappe.whitelist()
def stop_kafka_consumer(**kwargs):
	from .consumer.manager import stop_kafka_consumer as _fn
	return _fn()


@frappe.whitelist()
def get_kafka_consumer_status(**kwargs):
	from .consumer.manager import get_kafka_consumer_status as _fn
	return _fn()


@frappe.whitelist()
def reset_consumer_offset_to_beginning(**kwargs):
	from .consumer.manager import reset_consumer_offset_to_beginning as _fn
	return _fn()


@frappe.whitelist()
def consume_kafka_messages(max_messages=10, **kwargs):
	from .consumer.manager import consume_kafka_messages as _fn
	return _fn(max_messages=max_messages)


def _notify_restart():
	"""
	Runs in a daemon thread — completely isolated from Frappe's request cycle.
	Any error (network, timeout, import) is silently discarded.
	"""
	try:
		import requests as _req
		import datetime
		ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		_req.post(
			"http://172.16.135.118:8065/api/v4/posts",
			json={
				"channel_id": "ihmkbbfq9ibzugfpy9rncq5yke",
				"message": f":arrows_counterclockwise: **[{ts}] rndopsapp server restarted** — Kafka consumer auto-started.",
			},
			headers={
				"Authorization": "Bearer fmjih41b4iymicttnuhinsqime",
				"Content-Type": "application/json",
			},
			timeout=(2, 3),
		)
	except Exception:
		pass


_RESTART_COOLDOWN = 60  # seconds between restart attempts per worker process


def ensure_consumer_running():
	"""
	Called by the before_request hook on every HTTP request.
	Guards:
	  1. 60-second cooldown between restart attempts — prevents a crashing
	     consumer from spamming restarts on every request.
	  2. One Mattermost notification per worker-process lifetime — prevents
	     multiple Gunicorn workers each sending a ping on every hot-reload.
	"""
	global _restart_notified, _last_start_attempt
	try:
		from .consumer.manager import _consumer_thread, start_kafka_consumer
		if _consumer_thread is not None and _consumer_thread.is_alive():
			return  # fast path — nothing to do

		now = time.monotonic()
		if now - _last_start_attempt < _RESTART_COOLDOWN:
			return  # too soon to retry

		_last_start_attempt = now
		start_kafka_consumer()

		if not _restart_notified:
			_restart_notified = True
			try:
				import threading
				t = threading.Thread(target=_notify_restart, daemon=True)
				t.start()
			except Exception:
				pass
	except Exception:
		pass  # never interrupt the request


__all__ = [
	"start_kafka_consumer",
	"stop_kafka_consumer",
	"get_kafka_consumer_status",
	"reset_consumer_offset_to_beginning",
	"consume_kafka_messages",
	"fetch_kafka_logs",
	"ensure_consumer_running",
]
