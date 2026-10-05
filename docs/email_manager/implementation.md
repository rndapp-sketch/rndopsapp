# Email Manager — Implementation & Troubleshooting Guide

Status: **Implemented and live-tested.** One real config exists today:
`Email Manager: Project Registration` → notify on status `Approved`,
template `Project Registration`.

**2026-08-29 update:** per-status template (§2.2, §3) — each `Doc Status`
row can pick its own Email Template, falling back to the parent's default
if left blank.

**2026-08-31 update — removed:** the 2026-08-29 change also added an
optional per-row Notify Role, whose members were additionally notified for
that status. An admin pointed it at `Permanent Employee` (~1,184 accounts,
basically every staff/faculty user), so every Project Registration approval
broadcast to nearly the whole institute — 10 approvals, ~11,840 emails,
before it was caught. The feature has been removed entirely (not capped):
recipients are now always just the document owner. See §5.

Sends a short branded email to a document's owner when its `workflow_state`
changes to a status an admin has configured, for whichever DocTypes an admin
has opted in — using a template an admin can create/edit/preview from a
dedicated admin page, sent via a real Celery worker that Frappe starts and
supervises itself. No manual process management, no file editing required
for either part.

---

## 1. Architecture — the whole flow in one picture

```
 User approves/rejects/etc a document in the UI
                │
                ▼
 doc.save() / doc.submit()  (any doctype, any docstatus)
                │
                ▼  (Frappe doc_events hook — fires SAME REQUEST, synchronous)
 workflow_monitor.on_workflow_state_change(doc)
                │
                ├─ workflow_state actually changed? (get_doc_before_save diff)
                ├─ an ENABLED Email Manager row exists for this doctype,      ─┐
                │  its Doc Status table lists this exact new status, AND a     │  cached 5 min,
                │  template resolves for that row (its own, else the parent's ─┘  invalidated on
                │  default)? (config lookup — cheap, cached)                      Email Manager save
                ├─ not already notified for this (doctype, doc, status)?
                ├─ owner holds "Permanent Employee" role — at least one
                │  recipient?
                │
                │  all four pass →
                ▼
 Email Send Logs row created, status="Pending", template_reference=<template name>
                │
                ▼  (frappe.enqueue, queue="short" — NOW we leave the request thread)
 workflow_monitor.dispatch_notification()   [runs in a Frappe RQ background worker]
                │
                ├─ fetch Email Notification Template.content FROM THE DATABASE
                │  (fresh read every time — no cache — so an admin's edit
                │   takes effect on the very next notification)
                ├─ render it with live doc data
                ▼
 rabbitmq_client.publish_task()  →  send_status_email.apply_async(...)
                │                        (a REAL Celery task, via kombu/amqp,
                │                         broker = notification-rabbitmq)
                ▼
 RabbitMQ queue "pragati_email_notifications"
                │
                ▼  (consumed by a Celery worker Frappe auto-spawned — see §4)
 celery_app.py :: send_status_email(log_name, to_addresses, subject, html_body)
                │
                ├─ send_email_with_password(...)  (SMTP via smtp.office365.com)
                ├─ on failure: retry with backoff (Celery's autoretry_for), up to 5 attempts
                ├─ writes result straight to Email Send Logs
                │  (frappe.db.set_value — this worker is connected to the site directly,
                │   no HTTP callback needed)
                ▼
 Email Send Logs row updated: status = Success | Failed
```

Two separate mechanisms are doing two separate jobs, and it's worth keeping
them distinct when debugging:

| | Runs where | Job |
|---|---|---|
| **Checking** (`on_workflow_state_change` → `dispatch_notification`) | Inline in the web request, then a Frappe background job | Decide *whether* to notify, render the email, hand it to RabbitMQ |
| **Sending** (Celery worker, `celery_app.py`) | A separate OS process, auto-spawned by Frappe | Actually send the SMTP email, retry on failure, report the result |

There's also a third, human-facing piece that doesn't sit in this pipeline
at all: the **`/email_manager` admin page** (§9) — where templates are
authored/edited/previewed, and where an admin can inspect and manually
resend any Email Send Logs row.

---

## 2. Files — what lives where and why

### DocTypes (must live under `doctype/`, standard Frappe convention)

| Path | Purpose |
|---|---|
| `rndopsapp/rndopsapp/doctype/email_manager/` | One row per monitored DocType. Fields: `module` (Link → DocType, **not** Module Registry — see §2.1), `enabled` (Check), `template` (Link → Email Notification Template, **optional default/fallback** — see §2.2), `doc_status` (child table of statuses to notify on, each with its own template). `autoname: field:module` + `unique: 1` enforces exactly one config per DocType. |
| `rndopsapp/rndopsapp/doctype/email_manager_status/` | Child table. Fields: `status` (Select, dropdown options populated **client-side** at runtime — see §2.1), `template` (Link → Email Notification Template, optional — per-status override of the parent's default). Used to also have a `role` field (Link → Role) — removed 2026-08-31, see §5. |
| `rndopsapp/rndopsapp/doctype/email_notification_template/` | The email content itself. Fields: `template_name` (unique, autoname source), `category` (free-text, organizational only), `content` (the HTML+Jinja source), `is_active`. Replaces what used to be 43 static files on disk — see §2.3. |
| `rndopsapp/rndopsapp/doctype/email_send_logs/` | The audit trail. One row per notification attempt: source doctype/doc, previous/new status, recipients, subject, `template_reference` (the Email Notification Template **name** used), Celery task id, attempt/retry counters, status (`Pending`/`Retrying`/`Success`/`Failed`), error message, timestamps. |

### `rndopsapp/rndopsapp/email/` — all the logic

| File | Role |
|---|---|
| `email_config.py` | **Gitignored** (matches the repo's existing `email_config.py` ignore rule). All credentials and tunables: SMTP account, RabbitMQ host/port/vhost/user/password, the queue name `pragati_email_notifications`. **This is the first place to check when anything mysteriously doesn't work** — a placeholder value left unfilled is the single most common failure mode so far. |
| `workflow_monitor.py` | The "checking" half. `on_workflow_state_change` is the hook entry point; `_handle` does the 4-gate check described in §1; `dispatch_notification` fetches the selected template's content fresh from the DB, renders it, and publishes the Celery task. |
| `rabbitmq_client.py` | Thin wrapper: `publish_task(...)` → `send_status_email.apply_async(...)`. |
| `celery_app.py` | The real Celery app + the `pragati.send_status_email` task. Also defines the `worker_process_init` hook that connects the worker process to the Frappe site, and the heartbeat thread (see §4). |
| `consumer_service.py` | Auto-start/supervise logic — mirrors `rndopsapp/rndopsapp/kafka/consumer_service.py` exactly. Whitelisted `start_email_consumer` / `stop_email_consumer` / `get_email_consumer_status`, plus `ensure_consumer_running()` wired into `before_request`. |
| `send_email.py` | Low-level SMTP sender (`send_email_with_password`), reused by the Celery task. Not Email-Manager-specific — this already existed for other one-off admin emails. |
| `api.py` | All whitelisted endpoints — see §2.4. |

### `apps/frappe/frappe/www/email_manager.html` — the admin page

A single self-contained page (no separate `.py` context file — same
pattern as the pre-existing `kafka_control.html`, which it visually
matches and links to/from). See §9.

### `rndopsapp/patchs/migrate_email_templates_to_db.py`

One-time, idempotent post-model-sync patch (registered in
`rndopsapp/patches.txt`) that loaded the 43 original static template files
into `Email Notification Template` records the first time this ran, and
backfilled the `Project Registration` Email Manager row's new `template`
field. Safe to leave registered — it no-ops on every subsequent migrate
once those records exist (checks `frappe.db.exists` per template name
before creating).

### 2.1 — Two runtime-populated dropdowns (not hardcoded)

Both of these matter for troubleshooting a config that "looks right" but
isn't working:

- **`Email Manager.module`** — a `Link` to `DocType`, filtered *client-side*
  (`email_manager.js`, `frm.set_query`) to `module=Rndopsapp, istable=0`.
  The JSON field itself has no hard restriction — the dropdown filter is
  pure UI. If you ever query/set this field programmatically, nothing
  stops you from pointing it at a DocType outside this app; it just won't
  make sense.
- **`Email Manager Status.status`** — a `Select` field whose *options* are
  set at runtime by `email_manager.js`, which calls
  `email.api.get_doctype_workflow_states(doctype)` whenever `module`
  changes, and pushes the result into the grid via
  `grid.update_docfield_property`. **If you change a document's Workflow
  after configuring Email Manager, the dropdown won't auto-refresh** —
  reopen the Email Manager record (triggers the `module` change handler)
  to repopulate it.

### 2.2 — Templates: per-status, with a parent-level default fallback

Unlike the old design (removed — see §2.3), **any** Email Notification
Template can be selected for **any** DocType. There is no name-matching,
no auto-resolution. As of 2026-08-29, template selection happens at two
levels:

- **`Email Manager Status.template`** (per-row, on each Doc Status row) —
  the template used for that specific workflow status. Takes priority.
- **`Email Manager.template`** (parent-level "Default Email Template") —
  used only when a row's own `template` is blank.

`_get_matching_config(doctype, new_state)` in `workflow_monitor.py`
resolves this per-status: `row.template or parent.template`. If *neither*
resolves to a value for the matched status, that transition is silently
treated as "no config exists" per §6.0, even if `enabled` is checked and
the status row is present — same behavior as the old "template empty"
case, just evaluated per-row instead of per-Email-Manager-record.

This means a single Email Manager row can send a different template per
workflow status (e.g. `Approved` → an approval email, `Rejected` → a
rejection email) just by filling in each Doc Status row's own `template`.

### 2.3 — Templates moved from files to the database

Originally, templates were 43 static `.html` files under
`rndopsapp/rndopsapp/templates/emails/<category>/<slug>.html`, one per
doctype in `activity_logger.TRACKED_DOCTYPES`, auto-resolved by a
doctype-name-to-filename slug match (`_find_template_path`, with an
override map for awkward names like `DP PO`, `P 11 Form`). **That
resolution function no longer exists.** Templates are now
`Email Notification Template` DocType records, explicitly selected via
`Email Manager.template` (§2.2), created/edited entirely through the
`/email_manager` admin page (§9) — no file editing, no deploy needed to
change a template's wording, color, or button.

The original 43 files are still on disk (untouched, no longer read by any
code path) and were the seed data the migration patch (above) loaded from.

### 2.4 — `email/api.py` endpoints (all System-Manager-gated except the first)

| Endpoint | Used by |
|---|---|
| `get_doctype_workflow_states(doctype)` | Email Manager form's Doc Status grid (§2.1) |
| `list_email_templates()` | `/email_manager` Templates tab — left-side list |
| `get_email_template(name)` | Templates tab — loading a template into the editor |
| `save_email_template(name, template_name, category, content, is_active)` | Templates tab — Save / + New Template (create-or-update by name) |
| `preview_email_template(content)` | Templates tab — Preview button; renders arbitrary (even unsaved) content with fixed sample data |
| `list_email_send_logs(limit, status)` | Logs tab |
| `resend_email_notification(log_name)` | Logs tab — Resend button, any status (not just Failed); see §2.5 and §7.7 |

### 2.5 — `resend_email_notification` resolves the template live, not from the log

It does **not** trust `Email Send Logs.template_reference` blindly —
that field can be stale (see §7.7 for exactly how, and why it produced a
plain-text "no design" email once). Instead it calls
`_resolve_template_for_resend(log)`, which prefers the **current**
Doc Status row's own template for `log.new_status`, then the parent
`Email Manager.template` default (same order a fresh notification would
resolve per §2.2), and self-heals `template_reference` on the log to
match. Only falls back to the log's stored value if neither of those
resolves and it happens to already name a real template; throws a clear
error if nothing resolves to anything (rather than silently producing an
undesigned email).

---

## 3. How to configure a new notification

1. Desk → **Email Manager** → New (or open `/email_manager` → "Manage
   Configs" link).
2. **Module (DocType)**: pick the DocType to watch (dropdown is pre-filtered
   to this app's own DocTypes).
3. **Default Email Template**: optional. Used by any Doc Status row below
   that doesn't pick its own template (§2.2). If every row will have its
   own template, this can be left blank — but at least one of "this
   field" or "that row's template" must be filled for a given status, or
   nothing will send for it.
4. **Doc Status**: add a row, pick a status from the dropdown (populated
   from that DocType's real Workflow states — if it's empty, that DocType
   has no Workflow at all, and Email Manager can never fire for it). For
   each row, optionally pick that row's own **Email Template** (overrides
   the default for this status). Add more rows for more trigger statuses.
5. **Enabled**: checked.
6. Save.

That's it — no restart, no cache-clear needed for a *new* Email Manager
record (the config cache is invalidated automatically by
`EmailManager.on_update`/`on_trash`, see `email_manager.py`). A cache clear
IS needed after editing **code** (`hooks.py`, `workflow_monitor.py`, etc.) —
see §6.

**There is no per-row recipient configuration.** Every notification always
goes only to the document's `owner`, and only if that owner holds the
`Permanent Employee` role. See §5 — a per-row Notify Role option existed
briefly (2026-08-29 to 2026-08-31) and caused a real mass-email incident, so
it was removed rather than capped.

---

## 4. The Celery worker — how "auto-start" actually works

There is **no separate service to deploy, no Docker container, no manual
`celery worker` command.** This was explicitly reworked to match how
`rndopsapp/rndopsapp/kafka_consumer.py` already runs the Kafka consumer in
this app:

1. Every HTTP request runs `before_request` hooks, including
   `email.consumer_service.ensure_consumer_running()`.
2. That function checks a Redis heartbeat key
   (`email_manager_consumer_heartbeat`). If it's fresh, do nothing — a
   worker is alive somewhere.
3. If stale/missing, and the admin hasn't explicitly stopped it (see
   `stop_email_consumer` below), and it's been >60s since the last spawn
   attempt from *this* process (cooldown, prevents restart-spam if the
   worker keeps crashing) — it spawns a real `celery worker` process via
   `subprocess.Popen`, `start_new_session=True` so it survives even if the
   web worker that spawned it gets recycled.
4. That new process runs `celery -A rndopsapp.rndopsapp.email.celery_app
   worker --pool=solo -n pragati_email_worker@%h`. On startup, Celery's
   `worker_process_init` signal fires `_init_frappe_context()`
   (`celery_app.py`), which calls `frappe.init()` + `frappe.connect()` for
   the site named by the `FRAPPE_SITE` env var the spawner set — this is
   why the worker can write to `Email Send Logs` directly, no HTTP
   callback needed.
5. That same init also starts a small heartbeat thread (its own,
   independent `frappe.init()` — **`frappe.local` is thread-local, a new
   thread does not inherit the site binding from another thread**; this
   bit it a real bug during development, see §7) that refreshes the Redis
   key every 5s.

**Manual controls** (whitelisted, so callable via
`/api/method/rndopsapp.rndopsapp.email.consumer_service.<name>`, or
`bench execute`):

- `start_email_consumer()` — clears the "manually stopped" flag, spawns if
  not already running.
- `stop_email_consumer()` — sets the "manually stopped" flag (blocks
  auto-restart until `start_email_consumer` is called again), terminates
  the process this call knows about, clears the heartbeat key.
- `get_email_consumer_status()` — `{"consumer_running_globally": bool,
  "manually_stopped": bool}`.

**Worker logs**: `<bench>/logs/email_manager_celery_worker.log` — plain
`celery worker` stdout/stderr, appended to.

**Why `--pool=solo`**: a single-threaded pool. Frappe's DB connection
object isn't safe to share across the prefork/threaded pools Celery
normally uses; solo keeps everything in one thread per worker process,
matching how the Kafka consumer thread works too.

**Why a unique node name** (`-n pragati_email_worker@%h`): this broker
already runs `notification-celery` (a pre-existing, unrelated Celery
deployment). Both apps' workers default their Celery node name to
`celery@<hostname>` — without an explicit `-n`, they collide on the
broker's pidbox (control-command) identity, producing (harmless but noisy)
`AttributeError` spam in the log. Fixed, but worth knowing why the log
comment exists if it resurfaces elsewhere.

---

## 5. Recipients — exactly who gets emailed, and why

```python
def _get_recipients(doc) -> list[str]:
    recipients = []
    if doc.owner and doc.owner not in ("Administrator", "Guest"):
        if PERMANENT_EMPLOYEE_ROLE in frappe.get_roles(doc.owner):
            recipients.append(doc.owner)
    return recipients
```

**The document owner only, gated on "Permanent Employee".** No CC, no
role-based recipients, no approver-on-next-transition notification, no
automatic broadcast.

This rule went through three iterations before landing here, all driven by
testing/incidents against real data on this site — worth knowing if the
requirement changes again:

1. First version: owner + everyone holding whatever role was allowed on
   the *next* Workflow transition. Discovered via a live test that
   `Permanent Employee` specifically is held by **~700-1,184 real
   accounts** here (it's used as the generic "can submit their own forms"
   role, not an approver-scoped one) — a config that included it as an
   approver role would have emailed nearly the entire institute on every
   single transition.
2. Corrected, per direct instruction, to the owner-only, role-gated
   version.
3. 2026-08-29: reopened the same risk through an "opt-in" side door — a
   per-row `Email Manager Status.role` field let an admin add "everyone
   holding Role X" alongside the owner. The reasoning at the time was that
   an *explicit* per-status admin choice couldn't cause the same silent
   mass-broadcast as the automatic version in (1). That reasoning was
   wrong in practice: on 2026-08-31 an admin pointed it at `Permanent
   Employee` itself, and 10 real Project Registration approvals broadcast
   to all 1,184 users before it was caught (~11,840 emails). **Removed
   entirely** rather than capped — there is no role-based recipient path
   left in the code at all, so this class of mistake can't recur through
   config alone.

If recipient logic needs to change again, **`_get_recipients` in
`workflow_monitor.py` is the only place to touch** — nothing else in the
pipeline knows or cares who the recipients are.

**`MAX_RECIPIENTS = 1` (2026-08-31) is a hard structural cap, enforced at
two independent gates**, not just documentation:
1. `_handle()` — blocks before an `Email Send Logs` row is even created if
   `_get_recipients` ever returns more than `MAX_RECIPIENTS`.
2. `dispatch_notification()` — re-checks the `recipients` list it was
   actually called with, right before publishing to RabbitMQ, so a future
   direct/alternate call site can't bypass gate 1.

Either gate tripping logs an Error Log entry ("Email Manager: recipient cap
exceeded") and the row is marked `Failed` with an explanatory
`error_message` — nothing sends. If recipients per notification ever
legitimately need to exceed 1, raise `MAX_RECIPIENTS` deliberately and
explain why in the commit — do not delete the cap.

---

## 6. If something isn't working — where to look, in order

### 6.0 First: is a config even configured for what you're testing?
```python
frappe.get_all("Email Manager", fields=["name", "module", "enabled", "template"])
frappe.get_all("Email Manager Status", filters={"parenttype": "Email Manager"}, fields=["parent", "status", "template"])
```
No row for the doctype+status you expect, or **neither** the row's own
`template` **nor** the parent's `template` is set for that status → nothing
will ever fire. This has already been the actual cause of "it's not
working" once (a config was accidentally deleted during testing).

### 6.1 Did the hook even fire?

Check `Email Send Logs` for the document in question:
```python
frappe.get_all("Email Send Logs", filters={"reference_name": "<docname>"}, fields=["name","status","new_status","previous_status","template_reference"])
```
- **No row at all** → the check-gate in `_handle()` rejected it, or the
  `doc_events` hook never ran for that particular save. In order of
  likelihood:
  1. **`workflow_state` didn't actually change** in a way Frappe's
     `get_doc_before_save()` diff sees. This happens when a doctype's own
     code pre-writes the new state via `frappe.db.set_value(...,
     "workflow_state", ...)` *before* calling `doc.save()`/`doc.submit()`
     — by the time the save runs, before == after in Frappe's eyes, so
     **no hook anywhere** sees a transition (confirmed: even the older,
     unrelated `activity_logger` hook misses these too). `Project
     Registration`'s very first Draft→Pending-Approval submission does
     this deliberately (works around a workflow-permission check) — that
     one specific transition can never be detected by any hook, by
     design of that existing code, not a bug in Email Manager.
  2. **Wrong event for a submittable doctype.** Once `docstatus == 1`,
     Frappe routes further saves through `on_update_after_submit`, NOT
     `on_update`. This was a real bug found and fixed — confirm the hook
     is registered on all three relevant events (`on_update`,
     `on_update_after_submit`, `on_submit`) in `hooks.py`.
  3. **Hooks cache is stale.** Frappe caches the `doc_events` registry in
     Redis. Editing `hooks.py` alone does **not** take effect on a
     running site — you must `bench clear-cache` (or restart bench)
     afterward. This bit us directly during development.
  4. **No matching config, dedupe, or no recipient** — see §6.0, §1's
     gate list, and §5. A `Failed` log from ~5 min ago for the *same*
     status blocks nothing (only `Pending`/`Retrying`/`Success` block a
     new attempt) — but a `Success`/`Pending` one for the exact same
     `(doctype, docname, new_status)` triple will.
- **Row exists, `status = "Pending"` and stays that way** → the
  RabbitMQ *publish* worked, but nothing is *consuming* — see §6.2.
- **Row exists, `status = "Failed"`, `error_message` explains a broker
  auth error** → see §6.3.
- **Row exists, `status = "Failed"`, `error_message` mentions SMTP** →
  the Celery task ran but the send itself failed — check `Error Log` for
  entries titled `send_email_with_password failed` around that time for
  the real traceback (the log row deliberately doesn't duplicate it).
- **The email arrived but is a plain, undesigned sentence** ("X status
  changed to Y") instead of the branded HTML → see §6.6.

### 6.2 Stuck on `Pending` forever

No Celery worker is consuming `pragati_email_notifications`. Check:
```python
from rndopsapp.rndopsapp.email import consumer_service
consumer_service.get_email_consumer_status()
```
or on the shell: `pgrep -af "rndopsapp.rndopsapp.email.celery_app"`, and
`tail -f <bench>/logs/email_manager_celery_worker.log`.

If nothing is running and it's not auto-starting: check
`get_email_consumer_status()["manually_stopped"]` — if `True`, someone
called `stop_email_consumer()`; call `start_email_consumer()` to clear it
and restart.

**A "Pending" row published *before* a code change to the publish/consume
format will never resolve** — a real example occurred during development
(a message published under an earlier, incompatible envelope sat forever;
had to be manually re-published). If you suspect this, use the
**Resend** button on `/email_manager`'s Logs tab (`email.api.resend_email_notification`,
works from any status) — or, for a row stuck specifically because the
*publish* itself never succeeded, a manual `frappe.db.set_value(...,
"status", "Failed")` first, then Resend.

### 6.3 `error_message` shows a RabbitMQ/AMQP error

`ConnectionClosedByBroker: (403) 'ACCESS_REFUSED...'` → wrong credentials.
Check `email_config.py`'s `RABBITMQ_USER`/`RABBITMQ_PASSWORD` against the
real broker credentials (same broker as `notification-rabbitmq` /
`~/Projects/notification-worker/.env` — must match exactly, same account).
**This has been the single most common failure during development** —
always check this file first, specifically for any value still literally
reading a placeholder-looking string.

### 6.4 Emails not arriving despite `status = "Success"`

The SMTP send genuinely succeeded from this server's point of view. Check:
recipient's spam folder, `FROM_SENDER`/`SMTP_HOST`/`SMTP_PORT` in
`email_config.py`, and whether `PRORNDADMIN_EMAIL_PASSWORD` is still valid
(an app password that got rotated/revoked on the Microsoft 365 side would
show up as a `Failed` status with an SMTP auth error, not a silent
`Success`, but worth ruling out if `Success` rows aren't landing).

### 6.5 General debugging entry points

```python
import frappe
frappe.clear_cache()  # picks up hooks.py / config changes in this session

from rndopsapp.rndopsapp.email.workflow_monitor import (
    _get_matching_config, _already_notified, _get_recipients, clear_config_cache,
)
clear_config_cache()
_get_matching_config("Project Registration", "Approved")   # None => no config match (or no template resolves for this status)
_get_recipients(frappe.get_doc("Project Registration", "<docname>"))  # [] => owner doesn't hold Permanent Employee; [owner] otherwise, never more than 1

frappe.get_hooks("doc_events")["*"]["on_update_after_submit"]  # confirm hook registration is live
```

### 6.6 Email arrived but is plain text, no design at all

The rendered body will look like `<p>Project Registration 2026... status
changed to Approved.</p>` — that exact string is `dispatch_notification`'s
hardcoded fallback, used **only** when the template lookup came back
empty:
```python
template_str = frappe.db.get_value("Email Notification Template", template_name, "content")
if template_str:
    html = frappe.render_template(...)
else:
    html = f"<p>{doctype_name} {docname} status changed to {doc.workflow_state}.</p>"
```
So `template_name` didn't resolve to a real `Email Notification Template`
record. Two ways this happens:
1. **Neither the Doc Status row's `template` nor `Email Manager.template`
   is set (or one points at a deleted template)** — fix in Desk, re-trigger.
2. **A stale `Email Send Logs.template_reference` from before templates
   moved to the database** — see §7.7. This was a real, confirmed
   incident: an old log's `template_reference` still held a *file path*
   (`.../templates/emails/project/project_registration.html`), and
   `resend_email_notification` used to trust it blindly. Fixed — resend
   now resolves from the live `Email Manager` config instead (§2.5) — but
   if you're looking at a log created before that fix and its
   `template_reference` doesn't match an existing
   `Email Notification Template` name, that's this.

Quick check:
```python
log = frappe.get_doc("Email Send Logs", "<name>")
frappe.db.exists("Email Notification Template", log.template_reference)  # False => this is it
```

---

## 7. Notable bugs found and fixed during implementation

Kept here because each one is the kind of thing that can silently
regress if touched again without this context:

1. **`config.py` naming collision.** The first version of the config
   module was named `config.py`, colliding with the pre-existing
   `rndopsapp/rndopsapp/config/` package (empty `__init__.py`, used as a
   namespace). Python resolved the package over the module — every
   `from rndopsapp.config import ...` silently hit the empty
   `__init__.py`. Renamed to `static_config.py` and (separately, for this
   feature) `email/email_config.py`.
2. **Mass-email risk from the `Permanent Employee` role** — see §5.
3. **Submittable-doctype hook gap** (`on_update_after_submit` missing) —
   see §6.1.2. Also required an explicit `bench clear-cache` to take
   effect, which is easy to forget.
4. **Heartbeat thread never initialized its own Frappe context.**
   `frappe.local` is thread-local; a thread spawned from inside another
   thread's `frappe.init()`'d context does not inherit it. The heartbeat
   write was wrapped in a bare `except Exception: pass`, so it failed
   *silently* for a while before being caught by directly comparing a
   fresh-process heartbeat check against the in-session one. Fixed in
   `celery_app.py::_heartbeat_loop` by giving it its own `frappe.init()`.
5. **Celery node-name collision** with the pre-existing
   `notification-celery` worker on the same broker — fixed with an
   explicit `-n pragati_email_worker@%h`.
6. **A `Dynamic Link` field (`Email Send Logs.reference_name`) rejects
   references to documents that don't exist** — relevant only for
   writing test/debug scripts against this doctype, not a runtime
   concern.
7. **Stale `template_reference` after templates moved to the database.**
   Logs created before the `Email Notification Template` DocType existed
   had `template_reference` set to a **file path**
   (`rndopsapp/rndopsapp/templates/emails/project/project_registration.html`),
   from the old `_find_template_path()`-based design. After the rework,
   `resend_email_notification` was passing that stale path straight
   through as a template *name* — no `Email Notification Template`
   record has that name, so the lookup came back empty and silently fell
   through to the plain-text fallback (§6.6). A real resend produced a
   "no design" email because of exactly this. Fixed: resend now resolves
   the template from the *current* `Email Manager` config (§2.5) instead
   of trusting the log's frozen value, and heals the log's
   `template_reference` on every resend so it can't recur for that row.
   The two logs that existed at the time were fixed directly; anything
   created after the fix always gets a name that resolves correctly.
8. **`www/*.html` pages are rendered through Jinja *in full*, including
   inside `<script>` blocks.** `email_manager.html`'s Templates tab shows
   the literal placeholder syntax (`{{ doc.name }}` etc.) both as static
   help text and inside JavaScript that *generates* template HTML
   (Visual Builder, §9.2) — every one of those literal `{{ }}` / `{% %}`
   sequences was being evaluated by Frappe's own Jinja renderer against
   the *page's* context (which has no `doc`), throwing
   `UndefinedError: 'doc' is undefined` and returning a 417/error page
   instead of the app. Fixed by wrapping every such block in
   `{% raw %}...{% endraw %}` — the help-text `<div>`, the token-button
   markup, and the *entire* main `<script>` block (nothing in it needs
   real Jinja evaluation; only the two tiny top-of-body scripts setting
   `window.csrf_token` / the Guest redirect do). **Any future edit to
   this page that types a literal `{{` or `{%` outside an existing raw
   block will reintroduce this** — always re-fetch the live page
   (`curl -H "Host: <site>" http://localhost:8000/email_manager`) and
   confirm `200` + the real title after touching it, not just a JS
   syntax check.

---

## 8. Explicitly out of scope / known limitations

- **No portal-facing notifications.** This only ever emails a Frappe
  `User` (via SMTP); the external Account Portal (Java backend) has its
  own, separate world and isn't touched by this feature.
- **No recipient customization at all.** Recipients are always exactly the
  document owner (gated on "Permanent Employee"), or nobody — no CC/BCC, no
  extra named recipients, no role-based option (removed 2026-08-31 after a
  mass-email incident, see §5), no per-row override of the owner gate.
- **Templates have a static login link, not a per-document deep link.**
  Deliberate — every template's button points at
  `https://pragati.iitg.ac.in/login`, not a URL for the specific
  document. Editable per-template via the Visual Builder's "Button Link"
  field if that ever needs to change (§9.2).
- **The very first Draft→Pending-Approval transition on `Project
  Registration` can never be detected**, because of the pre-existing
  `frappe.db.set_value` workaround in that doctype's own submit code (see
  §6.1.1). Not something this feature can fix without changing that other
  code, which wasn't requested.

---

## 9. The `/email_manager` admin page

`apps/frappe/frappe/www/email_manager.html` — visually matches the
pre-existing `kafka_control.html` (same CSS tokens, fonts, dark-theme
support), linked from it (Quick Links sidebar) and linking back to it
(top bar). Guest users are redirected to login, same pattern as
`kafka_control.html`; every actual write/read endpoint additionally
enforces System Manager server-side regardless of what the page shows.

### 9.1 Email Send Logs tab

Table of every `Email Send Logs` row (filterable by status), showing the
doctype/document, status transition, recipients, current status badge,
attempt/retry count, and either the sent time or the error message. Every
row has a **Resend** button — calls `resend_email_notification` (§2.4,
§2.5), works from any status, not just `Failed`.

### 9.2 Templates tab

Left: every `Email Notification Template`, grouped by `category`. Right:
an editor with two modes, toggled at the top:

- **Code** — the raw `content` field in a plain `<textarea>` (monospace,
  no syntax highlighting, no WYSIWYG) — full control, same source that's
  actually stored and rendered.
- **Visual Builder** — for admins who don't want to touch Jinja/HTML
  directly. Plain form fields (Application Label, Category Badge,
  Header/Button Color, Message, a "show Project row" toggle, Button
  Text/Link, Footer Text), plus click-to-insert token buttons next to the
  Message field (Reference No. / Status / Applicant / Recipient Name —
  each inserts the correct `{{ ... }}` snippet at the cursor, so the user
  never has to know the syntax). **"Apply to Template"** regenerates the
  full HTML from these fields — using the exact same table-based email
  skeleton every hand-written template already uses (verified
  byte-for-byte against the original `Deposit Slip` template during
  development; the Visual Builder does not invent a different design) —
  and writes it into the Code view. Opening an existing template
  best-effort parses its current HTML back into these fields via regex
  (each field independently guarded, so one non-matching field never
  breaks the rest) — switching between Code and Visual stays roughly in
  sync both ways, though a hand-edited template that drifts far from the
  standard skeleton may not parse cleanly back into every field.

Both modes write to the same underlying `content` — **Save** always saves
whatever's currently in the Code textarea (Visual Builder changes only
take effect once "Apply to Template" has pushed them there).

**Preview** renders the *current, possibly unsaved* Code content
server-side (`preview_email_template`, §2.4) with fixed sample data
(`doc.name = "SAMPLE-2026-00123"`, `workflow_state = "Pending Staff
Approval"`, etc. — Jinja must run server-side, this can't be done in the
browser) and shows it in a sandboxed `<iframe srcdoc="...">` modal — a
real render of exactly what would be sent, without needing to actually
send anything.

**+ New Template** clears the editor (defaults to Visual Builder mode,
since a blank Code textarea has nothing to parse) for a fresh template;
`save_email_template` creates it on first Save.
