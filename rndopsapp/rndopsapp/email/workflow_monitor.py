"""
Email Manager — workflow-state-change → RabbitMQ email notification pipeline.

Frappe Workflow Change -> Email Manager Status Check -> RabbitMQ -> Celery
Worker -> Email Send -> Email Send Logs

Entry point: on_workflow_state_change(doc, method), wired in hooks.py under
doc_events["*"]["on_update"] / on_update_after_submit / on_submit (a
workflow_state change can arrive through any of the three — see
docs/email_manager/implementation.md §6.1 for why all three are needed).

Everything past the initial checks runs inside frappe.enqueue() (queue="short")
so a slow RabbitMQ connection, template render, or recipient lookup never
adds latency to the document save request itself.
"""

import frappe

CACHE_KEY = "email_manager_doctype_map"
PERMANENT_EMPLOYEE_ROLE = "Permanent Employee"

# Hard ceiling on recipients per notification — one document, one owner,
# one email. Enforced at both the enqueue gate (_handle) and the publish
# gate (dispatch_notification) so a bulk-send can't happen even if a future
# change to _get_recipients, or a direct call to dispatch_notification,
# tries to pass more. See 2026-08-31 incident in
# docs/email_manager/implementation.md §5 — a "safe" opt-in bulk-recipient
# feature broadcast ~11,840 emails before this cap existed. Never raise
# this without also changing how recipients are computed to justify it.
MAX_RECIPIENTS = 1


def on_workflow_state_change(doc, method=None):
    """doc_events hook (on_update / on_update_after_submit / on_submit)."""
    try:
        _handle(doc)
    except Exception:
        # Must never break the save that triggered this.
        frappe.log_error(frappe.get_traceback(), "Email Manager: on_workflow_state_change failed")


def _handle(doc):
    if not getattr(doc, "workflow_state", None):
        return

    doc_before = doc.get_doc_before_save()
    if not doc_before:
        return

    old_state = getattr(doc_before, "workflow_state", None)
    new_state = doc.workflow_state
    if not old_state or old_state == new_state:
        return

    config = _get_matching_config(doc.doctype, new_state)
    if not config:
        return

    if _already_notified(doc.doctype, doc.name, new_state):
        return

    recipients = _get_recipients(doc)
    if not recipients:
        return

    if len(recipients) > MAX_RECIPIENTS:
        frappe.log_error(
            f"Email Manager: blocked notification for {doc.doctype} {doc.name} -> "
            f"{new_state}: {len(recipients)} recipients resolved, MAX_RECIPIENTS is "
            f"{MAX_RECIPIENTS}. Not sent. This should be structurally impossible — "
            "see docs/email_manager/implementation.md §5.",
            "Email Manager: recipient cap exceeded",
        )
        return

    log = frappe.get_doc(
        {
            "doctype": "Email Send Logs",
            "module": config["module"],
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "previous_status": old_state,
            "new_status": new_state,
            "recipients": ", ".join(recipients),
            "subject": f"[Pragati] {doc.doctype} {doc.name} — {new_state}",
            "template_reference": config["template"],
            "attempt_number": 1,
            "retry_count": 0,
            "status": "Pending",
        }
    ).insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.enqueue(
        "rndopsapp.rndopsapp.email.workflow_monitor.dispatch_notification",
        queue="short",
        job_name=f"email-manager-dispatch-{log.name}",
        log_name=log.name,
        doctype_name=doc.doctype,
        docname=doc.name,
        recipients=recipients,
        subject=log.subject,
        template_name=config["template"],
    )


# ---------------------------------------------------------------------------
# Config resolution ({doctype: {module, default_template, statuses}}, one
# Email Manager row per doctype — "module" IS the monitored DocType itself,
# enforced unique in the JSON). Each entry in `statuses` is itself
# {status: {template}} — a row's own template, resolved against
# the parent's default_template at lookup time in _get_matching_config.
# ---------------------------------------------------------------------------


def _get_matching_config(doctype: str, new_state: str):
    """{"module": doctype, "template": <Email Notification Template name>}
    for the specific Doc Status row matching `new_state`, if an enabled
    Email Manager row exists for `doctype` with that status configured AND
    a template resolves (row's own, else the parent's default). None
    otherwise."""
    entry = _get_doctype_map().get(doctype)
    if not entry:
        return None

    status_cfg = entry["statuses"].get(new_state)
    if not status_cfg:
        return None

    template = status_cfg.get("template") or entry.get("default_template")
    if not template:
        return None

    return {"module": entry["module"], "template": template}


def _get_doctype_map():
    cached = frappe.cache().get_value(CACHE_KEY)
    if cached is not None:
        return cached

    doctype_map = {}
    for em in frappe.get_all(
        "Email Manager", filters={"enabled": 1}, fields=["name", "module", "template"]
    ):
        statuses = {
            row.status: {"template": row.template}
            for row in frappe.get_all(
                "Email Manager Status",
                filters={"parent": em.name, "parenttype": "Email Manager"},
                fields=["status", "template"],
            )
            if row.status
        }
        if statuses:
            doctype_map[em.module] = {
                "module": em.module,
                "default_template": em.template,
                "statuses": statuses,
            }

    frappe.cache().set_value(CACHE_KEY, doctype_map, expires_in_sec=300)
    return doctype_map


def clear_config_cache():
    frappe.cache().delete_value(CACHE_KEY)


def _already_notified(doctype: str, docname: str, new_state: str) -> bool:
    """
    Dedupe: skip if an Email Send Logs row already exists for this exact
    (doctype, docname, new_status) transition that is Pending/Retrying/
    Success — a Failed row is left alone so it can be manually retried
    without silently blocking a fresh notification forever.
    """
    return bool(
        frappe.db.exists(
            "Email Send Logs",
            {
                "reference_doctype": doctype,
                "reference_name": docname,
                "new_status": new_state,
                "status": ["in", ["Pending", "Retrying", "Success"]],
            },
        )
    )


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------


def _get_recipients(doc) -> list[str]:
    """
    The document owner only — and only when that owner actually holds the
    Permanent Employee role — deliberately NOT "every user holding the
    Permanent Employee role": that role is held by ~1,184 accounts,
    basically every regular staff/faculty account, used just to submit
    their own forms (confirmed live against this site).

    There used to also be an opt-in "notify everyone holding Role X" per
    Doc Status row (Email Manager Status.role). It was removed on
    2026-08-31 after an admin pointed it at Permanent Employee itself,
    broadcasting every Project Registration approval to all 1,184 users —
    the exact mass-email risk this function's owner-gate was designed to
    avoid, just reopened through the "opt-in" side door. Recipients are now
    always exactly the single document owner, or nobody.
    """
    recipients: list[str] = []

    if doc.owner and doc.owner not in ("Administrator", "Guest"):
        if PERMANENT_EMPLOYEE_ROLE in frappe.get_roles(doc.owner):
            recipients.append(doc.owner)

    return recipients


# ---------------------------------------------------------------------------
# Dispatch (runs inside the background worker, not the request thread)
# ---------------------------------------------------------------------------


def dispatch_notification(log_name, doctype_name, docname, recipients, subject, template_name):
    """
    Renders the selected Email Notification Template (fetched fresh from
    the DB, not cached — an admin's edit to a template takes effect on the
    very next notification, no cache to bust) with live document data, and
    publishes one Celery task per notification. Any failure here — a
    template that got deleted, a doc that got deleted, a broker outage —
    is recorded on the Email Send Logs row as Failed rather than raised,
    since this already runs inside frappe.enqueue and there's no request
    to surface an error to.
    """
    from rndopsapp.rndopsapp.email.rabbitmq_client import publish_task

    if len(recipients) > MAX_RECIPIENTS:
        frappe.db.set_value(
            "Email Send Logs",
            log_name,
            {
                "status": "Failed",
                "error_message": f"Blocked: {len(recipients)} recipients exceeds "
                f"MAX_RECIPIENTS ({MAX_RECIPIENTS}). Not published to RabbitMQ.",
                "final_result": "Blocked — recipient cap exceeded",
            },
            update_modified=True,
        )
        frappe.db.commit()
        frappe.log_error(
            f"Email Manager: dispatch_notification blocked for {log_name}: "
            f"{len(recipients)} recipients, MAX_RECIPIENTS is {MAX_RECIPIENTS}.",
            "Email Manager: recipient cap exceeded",
        )
        return

    try:
        doc = frappe.get_doc(doctype_name, docname)

        template_str = frappe.db.get_value("Email Notification Template", template_name, "content")
        if template_str:
            html = frappe.render_template(
                template_str, {"doc": doc.as_dict(), "recipient_name": None, "frappe": frappe}
            )
        else:
            html = f"<p>{doctype_name} {docname} status changed to {doc.workflow_state}.</p>"

        task_id = publish_task(
            log_name=log_name,
            to_addresses=recipients,
            subject=subject,
            html_body=html,
        )

        frappe.db.set_value(
            "Email Send Logs", log_name, {"task_id": task_id, "status": "Pending"}, update_modified=True
        )
        frappe.db.commit()

    except Exception as e:
        frappe.db.set_value(
            "Email Send Logs",
            log_name,
            {"status": "Failed", "error_message": str(e), "final_result": "Publish to RabbitMQ failed"},
            update_modified=True,
        )
        frappe.db.commit()
        frappe.log_error(frappe.get_traceback(), f"Email Manager: dispatch_notification failed ({log_name})")
