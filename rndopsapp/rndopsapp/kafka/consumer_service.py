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


_MANUALLY_STOPPED_KEY = "kafka_consumer_manually_stopped"


def _set_manually_stopped(value: bool):
	try:
		frappe.cache().set_value(_MANUALLY_STOPPED_KEY, value)
	except Exception:
		pass


def _is_manually_stopped() -> bool:
	try:
		return bool(frappe.cache().get_value(_MANUALLY_STOPPED_KEY))
	except Exception:
		return False


@frappe.whitelist()
def start_kafka_consumer(**kwargs):
	_set_manually_stopped(False)
	from .consumer.manager import start_kafka_consumer as _fn
	return _fn()


@frappe.whitelist()
def stop_kafka_consumer(**kwargs):
	_set_manually_stopped(True)
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
	  1. Redis heartbeat check — if any worker's consumer thread is alive,
	     the heartbeat is fresh and other workers skip. Prevents N workers
	     each running their own consumer thread.
	  2. Skips auto-restart when the user has manually stopped the consumer
	     via the Control Center — cleared only when user clicks Start.
	  3. 60-second cooldown between restart attempts per worker — prevents
	     a crashing consumer from spamming restarts on every request.
	  4. One Mattermost notification per worker-process lifetime.
	"""
	global _restart_notified, _last_start_attempt
	try:
		from .consumer.manager import is_consumer_running_globally, start_kafka_consumer

		# Fast path — Redis heartbeat confirms consumer is alive somewhere
		if is_consumer_running_globally():
			return

		# Respect explicit user stop — don't auto-restart until user clicks Start
		if _is_manually_stopped():
			return

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
