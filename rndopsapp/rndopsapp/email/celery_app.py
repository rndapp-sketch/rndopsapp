"""
The real Celery app + task for Email Manager notifications — Celery does
the actual job (task queue semantics, retry/backoff, visible in the
existing Flower dashboard at :5555 since it's the same broker). What's
different from a typical Celery deployment: nothing starts this worker
manually — rndopsapp.rndopsapp.email.consumer_service auto-spawns it as a
subprocess from a Frappe request hook, the same "auto-start on request"
pattern rndopsapp.kafka_consumer already uses for the Kafka consumer
thread. Same broker as notification-rabbitmq/notification-celery, own
queue+task name so the two never collide.
"""

import os
import threading
import time

from celery import Celery
from celery.signals import worker_process_init

from rndopsapp.rndopsapp.email.email_config import (
    EMAIL_MANAGER_QUEUE,
    RABBITMQ_HOST,
    RABBITMQ_PASSWORD,
    RABBITMQ_PORT,
    RABBITMQ_USER,
    RABBITMQ_VHOST,
)

BROKER_URL = (
    f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}/"
    f"{RABBITMQ_VHOST.strip('/')}"
)

app = Celery("pragati_email_worker", broker=BROKER_URL)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=False,
    task_default_queue=EMAIL_MANAGER_QUEUE,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    # This worker shares a broker with the pre-existing notification-celery
    # deployment and its Flower dashboard (see module docstring). Flower
    # periodically broadcasts pidbox control commands (e.g. enable_events)
    # to every worker on the broker, unique node name or not — a unique
    # name only avoids colliding on *reply* identity, it doesn't stop this
    # worker from *receiving* the broadcast. Since this worker runs
    # --without-heartbeat/--without-gossip/--without-mingle, it has no
    # event dispatcher to enable, so handling that command crashed with
    # "AttributeError: 'NoneType' object has no attribute 'groups'" every
    # ~5s (harmless to task processing, but constant log noise/exception
    # overhead — confirmed still happening live on 2026-08-31). Disabling
    # remote control means this worker no longer subscribes to the pidbox
    # exchange at all, so it never receives (or mishandles) that command.
    worker_enable_remote_control=False,
)

# Redis key this worker process's heartbeat thread writes to, so
# consumer_service.ensure_consumer_running() (running in the WEB process)
# can tell a worker is alive without needing to track its subprocess PID
# across different Gunicorn/bench worker processes.
_HEARTBEAT_KEY = "email_manager_consumer_heartbeat"
_HEARTBEAT_TTL = 15
_HEARTBEAT_INTERVAL = 5


def _heartbeat_loop(site: str):
    """
    Runs in its own daemon thread. frappe.local is thread-local, so this
    thread does NOT inherit the frappe.init()/connect() done in
    _init_frappe_context's thread — it needs its own, exactly like why
    kafka_consumer's background thread needs ensure_frappe_site_init().
    """
    import frappe

    try:
        frappe.init(site=site)
    except Exception:
        return

    while True:
        try:
            frappe.cache().set_value(_HEARTBEAT_KEY, time.time(), expires_in_sec=_HEARTBEAT_TTL)
        except Exception:
            pass
        time.sleep(_HEARTBEAT_INTERVAL)


@worker_process_init.connect
def _init_frappe_context(**kwargs):
    """
    Runs once when this worker process starts (pool=solo -> exactly the
    worker process itself, no extra fork). Connects to the site named by
    FRAPPE_SITE (set by consumer_service when it spawns this process) so
    the task below can read/write Frappe documents directly — no HTTP
    callback needed, this worker lives in the same bench Python
    environment as the site it's updating.
    """
    import frappe

    site = os.environ.get("FRAPPE_SITE")
    if not site:
        frappe.logger().error("Email Manager celery worker: FRAPPE_SITE not set, cannot connect")
        return

    frappe.init(site=site)
    frappe.connect()

    threading.Thread(target=_heartbeat_loop, args=(site,), daemon=True).start()


def _write_log(log_name: str, values: dict):
    """
    frappe.db.set_value + commit, reconnecting once on a dead connection.

    This worker's Frappe DB connection is opened once at process start
    (worker_process_init) and then reused across every task for as long as
    the process lives — unlike a normal Frappe request, which gets a fresh
    connection each time. If the underlying MySQL connection dies while
    idle between tasks (network blip, server restart, proxy timeout —
    happened repeatedly here, see logs/email_manager_celery_worker.log
    around 2026-08-29 to 2026-08-31), pymysql raises InterfaceError on the
    next use and does not auto-reconnect. Previously that propagated out of
    this function uncaught, so even the "mark as Failed" write in the
    except-block below could fail the same way — leaving the Email Send
    Logs row stuck at whatever status it last reached (see ESL-20260831-03165).
    """
    import frappe
    from pymysql.err import InterfaceError, OperationalError

    try:
        frappe.db.set_value("Email Send Logs", log_name, values, update_modified=True)
        frappe.db.commit()
    except (InterfaceError, OperationalError):
        frappe.db.connect()
        frappe.db.set_value("Email Send Logs", log_name, values, update_modified=True)
        frappe.db.commit()


@app.task(
    bind=True,
    name="pragati.send_status_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def send_status_email(self, log_name: str, to_addresses: list[str], subject: str, html_body: str):
    import frappe

    from rndopsapp.rndopsapp.email.send_email import send_email_with_password

    attempt = self.request.retries + 1

    if self.request.retries > 0:
        _write_log(
            log_name,
            {
                "status": "Retrying",
                "attempt_number": attempt,
                "retry_count": self.request.retries,
                "last_retry_at": frappe.utils.now_datetime(),
            },
        )

    ok = send_email_with_password(
        to_address=", ".join(to_addresses),
        subject=subject,
        description=html_body,
        html=True,
    )

    if not ok:
        if self.request.retries >= self.max_retries:
            # send_email_with_password already logged the real traceback via
            # frappe.log_error — point at that instead of duplicating it here.
            _write_log(
                log_name,
                {
                    "status": "Failed",
                    "attempt_number": attempt,
                    "retry_count": self.request.retries,
                    "final_result": "Permanently failed",
                    "error_message": "SMTP send failed on every retry — see Error Log for "
                    "'send_email_with_password failed' entries around this time.",
                },
            )
            return {"status": "failed", "log_name": log_name}

        raise RuntimeError("SMTP send failed — retrying")

    _write_log(
        log_name,
        {
            "status": "Success",
            "attempt_number": attempt,
            "retry_count": self.request.retries,
            "sent_at": frappe.utils.now_datetime(),
            "final_result": "Delivered",
            "error_message": "",
        },
    )
    return {"status": "sent", "log_name": log_name}
