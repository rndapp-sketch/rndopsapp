"""
Email Manager Consumer Service — auto-starts and supervises the real Celery
worker process (rndopsapp.rndopsapp.email.celery_app) from a Frappe request
hook, the same "auto-start on request" pattern
rndopsapp.rndopsapp.kafka.consumer_service already uses for the Kafka
consumer thread. The difference: Celery workers manage their own process
lifecycle (signal handling, etc.), so instead of running in a Python thread
in-process, it's spawned as its own OS subprocess — but that spawn is
itself triggered automatically by Frappe, not by a human running
`celery worker` by hand.
"""

import os
import subprocess
import sys
import time

import frappe

from rndopsapp.rndopsapp.email.celery_app import _HEARTBEAT_KEY

_MANUALLY_STOPPED_KEY = "email_manager_consumer_manually_stopped"
_RESTART_COOLDOWN = 60  # seconds between spawn attempts per worker process
_last_start_attempt = 0.0  # per-process guard

# Cross-process spawn lock: without this, two Gunicorn/bench worker
# processes can both pass the is_consumer_running_globally() heartbeat
# check before either one's spawned subprocess has written its first
# heartbeat (the heartbeat thread only starts once worker_process_init
# finishes Celery's own startup), so both spawn a worker — observed live
# on this site as 4 duplicate "pragati_email_worker@%h" processes running
# at once, each holding its own DB connection. The TTL just needs to
# outlast that startup race, not the worker's lifetime.
_SPAWN_LOCK_KEY = "email_manager_consumer_spawn_lock"
_SPAWN_LOCK_TTL = 30

# Kept only so this process can kill what IT spawned on stop_email_consumer;
# other Gunicorn/bench worker processes rely on the Redis heartbeat instead.
_process = None


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


def is_consumer_running_globally() -> bool:
	"""True if ANY worker process (spawned by any Gunicorn/bench worker) has
	written a fresh heartbeat — see celery_app.py's worker_process_init handler."""
	try:
		return bool(frappe.cache().get_value(_HEARTBEAT_KEY))
	except Exception:
		return False


def _try_acquire_spawn_lock() -> bool:
	"""
	True if THIS process won the right to spawn — a Redis SETNX, so only one
	of any number of concurrent callers (across processes) gets True. Used
	to close the race where multiple processes pass the heartbeat check
	before any spawned worker has written its first heartbeat.
	"""
	try:
		key = frappe.cache().make_key(_SPAWN_LOCK_KEY)
		return bool(frappe.cache().set(key, "1", nx=True, ex=_SPAWN_LOCK_TTL))
	except Exception:
		# Redis unreachable — fall back to "allowed", same as every other
		# guard in this module failing open (see ensure_consumer_running).
		return True


def _spawn_worker_process():
	global _process

	site = frappe.local.site
	log_dir = os.path.join(frappe.utils.get_bench_path(), "logs")
	os.makedirs(log_dir, exist_ok=True)
	log_path = os.path.join(log_dir, "email_manager_celery_worker.log")

	env = dict(os.environ)
	env["FRAPPE_SITE"] = site

	cmd = [
		sys.executable, "-m", "celery",
		"-A", "rndopsapp.rndopsapp.email.celery_app",
		"worker",
		"--loglevel=INFO",
		"--pool=solo",  # single-threaded: safe to share one Frappe DB connection
		# Unique node name — same broker as notification-celery, whose worker
		# also defaults to "celery@<hostname>"; without this both processes
		# collide on the same pidbox control-command identity.
		"-n", "pragati_email_worker@%h",
		"--without-heartbeat", "--without-gossip", "--without-mingle",
	]

	with open(log_path, "a") as log_file:
		_process = subprocess.Popen(
			cmd,
			env=env,
			stdout=log_file,
			stderr=subprocess.STDOUT,
			start_new_session=True,  # survives this Gunicorn worker being recycled
		)

	frappe.logger().info(f"Email Manager: spawned Celery worker (pid={_process.pid}), log: {log_path}")


@frappe.whitelist()
def start_email_consumer(**kwargs):
	_set_manually_stopped(False)
	if is_consumer_running_globally():
		return {"status": "warning", "message": "Consumer already running"}
	if not _try_acquire_spawn_lock():
		return {"status": "warning", "message": "Consumer is already starting"}
	_spawn_worker_process()
	return {"status": "success", "message": "Email Manager Celery worker starting"}


@frappe.whitelist()
def stop_email_consumer(**kwargs):
	global _process

	_set_manually_stopped(True)
	if _process is not None:
		try:
			_process.terminate()
		except Exception:
			pass
		_process = None
	try:
		frappe.cache().delete_value(_HEARTBEAT_KEY)
	except Exception:
		pass
	return {"status": "success", "message": "Email Manager consumer stop requested"}


@frappe.whitelist()
def get_email_consumer_status(**kwargs):
	return {
		"consumer_running_globally": is_consumer_running_globally(),
		"manually_stopped": _is_manually_stopped(),
	}


def ensure_consumer_running():
	"""
	Called from the before_request hook on every HTTP request — same guards
	as kafka's ensure_consumer_running:
	  1. Redis heartbeat check — skip if a worker is alive anywhere.
	  2. Skip auto-restart if the user explicitly stopped it (cleared only
	     by calling start_email_consumer again).
	  3. Cooldown between spawn attempts per worker process, so a crashing
	     worker can't spam restarts on every request.
	  4. Cross-process spawn lock (_try_acquire_spawn_lock) — closes the
	     race between (1) and a spawned worker's first heartbeat, which
	     previously let multiple processes spawn duplicate workers.
	"""
	global _last_start_attempt
	try:
		if is_consumer_running_globally():
			return

		if _is_manually_stopped():
			return

		now = time.monotonic()
		if now - _last_start_attempt < _RESTART_COOLDOWN:
			return

		_last_start_attempt = now

		if not _try_acquire_spawn_lock():
			return

		_spawn_worker_process()
	except Exception:
		pass  # never interrupt the request


__all__ = [
	"start_email_consumer",
	"stop_email_consumer",
	"get_email_consumer_status",
	"ensure_consumer_running",
]
