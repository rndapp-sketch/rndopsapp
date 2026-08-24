# Notification System — Implementation Plan

Status: **Draft for review — not implemented**
Scope: All doctypes in the `rndopsapp` module (145 doctypes across 3 doctype
folders), with read/unread tracking, a notification inbox, and automatic
alerts on workflow state changes.

---

## 1. Current state (what already exists)

- **Frappe 15.74.2** ships a built-in `Notification Log` doctype
  (`read`, `for_user`, `type`, `subject`, `document_type`, `document_name`,
  `from_user`, `link`) plus `Notification Settings` (per-user, per-type
  on/off). This already gives us read/unread storage, the desk bell icon,
  and realtime push — for free, no new doctype needed.
- `enqueue_create_notification()` from
  `frappe.desk.doctype.notification_log.notification_log` is **already used
  twice** in this app:
  - `rndopsapp/kafka/consumer/dlq_common.py:137` (`notify_ledger_rejection`)
  - `rndopsapp/kafka/consumer/fund_received/mapper.py:241`
    (`_notify_ledger_status_change`)
  Both follow the same pattern: write an audit `Comment`, then call
  `enqueue_create_notification([owner], {...})`. This is our template.
- `rndopsapp/activity_logger.py` already hooks `doc_events["*"]["on_update"]`
  → `log_workflow_transition`, which detects `workflow_state` changes and
  writes to a custom **Staff Activity Log** doctype for a `TRACKED_DOCTYPES`
  map (24 doctypes, grouped by category: Purchase, Financial, Project,
  HR-Staff, Deposits, Travel, IPR, Other). This is the exact detection point
  we'll reuse for notifications — no need to re-derive "did workflow_state
  change" logic.
- `rndopsapp/api.py:206-290` has `DOCTYPE_TO_COMMENT_CATEGORIES`, mapping
  doctypes to categories used to fetch comments from the external Account
  Portal (Java backend at `ACCOUNT_PORTAL_BASE_URL`). Relevant because
  portal-side comments already surface in `get_project_activity()`, and any
  new in-app notification feed should not duplicate/conflict with that feed.
- No `notification_config` is set in `hooks.py` (currently commented out).
- No `frappe.publish_realtime` usage anywhere in the app yet.
- The 24 doctypes with `workflow_state` (the natural targets for
  "workflow change" alerts): Direct Purchase, Loan Request, Project
  Registration, Advance Settlement, Proprietary Purchase, PO Commit
  Adjustment, Temporary Advance, Project Staff Extension, AMC, Reimbursement,
  Disbursal of Consultancy/Honorarium, Cancellation Request, Fund Received,
  Standerdized Purchase, Project Staff Details, Recruitment Adhoc
  Contractual, Miscellaneous Commit, Project Proposal, Research
  (Consultancy) Deposit Slip, Rate Contract, Travel, Repair Replacement (+2
  more from the 24, see `activity_logger.py` `TRACKED_DOCTYPES` for the
  authoritative list).

**Conclusion:** we should not invent a parallel notification/read-unread
store. Build on `Notification Log` + `Notification Settings`, and hang the
new logic off the same `workflow_state` transition detection
`activity_logger.py` already performs.

---

## 2. Open decisions (need your input before implementation)

These materially change the design — flagging them here rather than
guessing:

1. **Recipients per doctype.** Who gets notified on a workflow transition?
   Options, possibly combined:
   - The document **owner** (simplest — who submitted it).
   - Users holding the **role(s) allowed to act on the next workflow
     state** (pulled from the `Workflow` doctype's transition rules) — i.e.
     notify whoever needs to approve next.
   - Explicit **watchers** (a new child table / "Notify" field on the
     doctype, or reuse Frappe's built-in "Assign To").
   - A **static role list per category**, similar to how
     `activity_logger.TRACKED_DOCTYPES` groups doctypes into
     Purchase/Financial/Project/HR/etc.
2. **Audience: desk users only, or Account Portal (external) users too?**
   The Java backend seems to serve external/portal users who may not be
   Frappe desk users at all. If they also need notifications, `Notification
   Log` (desk-only) isn't sufient by itself — we'd need a REST endpoint the
   portal can poll, or push notifications *into* the portal via its own API.
3. **Scope: all 145 doctypes, or the 24 workflow doctypes first?** Every
   doctype technically *could* get "created/updated" notifications, but
   most value is in workflow-state changes on the 24 tracked doctypes.
   Recommend phasing (see §4).
4. **Notification granularity:** one alert per state transition, or only on
   specific "interesting" transitions (e.g. → Approved, → Rejected) per
   doctype, configurable?
5. **Where should users read notifications?** The stock Frappe desk bell
   icon + `/app/notification-log` list is free with `Notification Log`. If
   there's a separate custom frontend/portal for these users, we need a
   dedicated notifications page/API instead of (or in addition to) the desk
   bell.

Recommend answering these via a short call before Phase 2 starts; Phase 1
(infrastructure) is decision-agnostic and can start immediately.

---

## 3. Proposed architecture

```
Workflow state change on any tracked doctype
        │
        ▼
doc_events["*"]["on_update"]  (hooks.py — already fires activity_logger)
        │
        ▼
rndopsapp/notifications.py::notify_workflow_transition(doc, method)
        │  1. Was there actually a workflow_state change? (reuse
        │     activity_logger's old/new state diff logic)
        │  2. Is this doctype in NOTIFY_CONFIG?
        │  3. Resolve recipients (owner / next-state role / watchers)
        │  4. Build subject + link (matches Notification Log's
        │     document_type/document_name/link fields)
        ▼
frappe.desk.doctype.notification_log.notification_log
    .enqueue_create_notification(recipients, notification_doc)
        │
        ▼
Notification Log rows created (read=0) + realtime bell-icon push
        │
        ▼
User reads in desk bell / Notification Log list
   → read flag flips to 1 (built-in, no code needed)
```

Key point: steps 1–4 are **new code**; everything from
`enqueue_create_notification` onward is **existing Frappe framework
functionality** we don't need to build.

---

## 4. Phased implementation

### Phase 1 — Infrastructure (no behavior change yet)
- Create `rndopsapp/rndopsapp/notifications.py` with:
  - `NOTIFY_CONFIG`: dict per doctype → `{recipients: fn, subject: fn,
    transitions: [...] | "*"}`, seeded from `activity_logger.TRACKED_DOCTYPES`
    so both stay in sync (or refactor to a single shared config both files
    import).
  - `notify_workflow_transition(doc, method)` — generic handler.
  - Recipient resolver helpers: `get_doc_owner`, `get_users_with_role`,
    `get_next_state_roles(doc)` (reads `Workflow`/`Workflow Document State`
    for the doctype).
- Wire into `hooks.py` `doc_events["*"]["on_update"]` alongside the existing
  `activity_logger.log_workflow_transition` entry (same trigger point, so no
  new event wiring pattern to learn).
- Add a patch (`apps/rndopsapp/rndopsapp/patches/...`) to bulk-create
  `Notification Settings` for all users, reusing the logic already in
  `fix_users.py`.
- No doctypes enabled in `NOTIFY_CONFIG` yet — deploy inert, verify no
  errors/perf regression on `on_update`.

### Phase 2 — Pilot on 2–3 doctypes
- Enable `NOTIFY_CONFIG` for e.g. `Miscellaneous Commit` and
  `Direct Purchase` (both already understood end-to-end from the DLQ/kafka
  notification code).
- Validate: correct recipients, no duplicate notifications on unrelated
  field saves (only on actual `workflow_state` change), read/unread flips
  correctly, bell icon realtime push works.
- Confirm perf: `on_update` fires on every save — recipient resolution
  (esp. `get_next_state_roles`) must be cheap or cached.

### Phase 3 — Roll out to remaining workflow doctypes
- Extend `NOTIFY_CONFIG` to the rest of the 24 `workflow_state` doctypes,
  grouped by the existing category buckets (Purchase/Financial/Project/
  HR-Staff/Deposits/Travel/IPR/Other) so recipient rules can be defined
  once per category rather than per doctype where behavior is identical.

### Phase 4 — Non-workflow doctypes (optional, only if needed)
- For the remaining ~121 doctypes without `workflow_state`, decide case by
  case whether `on_insert`/`on_submit`/`on_cancel` events warrant a
  notification (e.g. child records, DLQ logs likely don't need one; staff
  document approvals might). Likely low-value for most — recommend
  skipping unless a specific doctype is called out.

### Phase 5 — Portal-facing notifications (only if Decision #2 requires it)
- If Account Portal (external) users need notifications too: add a
  whitelisted API (`get_unread_notifications`, `mark_notification_read`)
  the Java backend can poll, backed by the same `Notification Log` rows
  (filtered by `for_user`), OR push into the portal via its existing
  `/api/comments/...`-style REST pattern if it has a notifications
  endpoint of its own.

### Phase 6 — UI polish (if the stock desk bell isn't sufficient)
- Custom "Notifications" page/report if users need doctype-grouped or
  category-grouped views beyond the stock `Notification Log` list.
- Optional: unread-count badge in any custom workspace/portal shell.

---

## 5. Files to touch (summary)

| File | Change |
|---|---|
| `rndopsapp/rndopsapp/notifications.py` | **New.** Core notify logic. |
| `rndopsapp/hooks.py` | Add entry to `doc_events["*"]["on_update"]`. |
| `rndopsapp/rndopsapp/activity_logger.py` | Possibly refactor shared `TRACKED_DOCTYPES`/diff logic into a common module both files import. |
| `rndopsapp/rndopsapp/patches/...` | New patch: backfill `Notification Settings` for all users. |
| `rndopsapp/rndopsapp/api.py` | Only touched if Phase 5 portal API is needed. |
| `apps/rndopsapp/docs/notifications/` | This doc + follow-up design notes as decisions are made. |

---

## 6. Testing plan

- Unit: recipient resolution functions (mock `Workflow` doc, assert correct
  role/user set per transition).
- Integration: submit/transition a `Miscellaneous Commit` through its
  workflow in a test site, assert `Notification Log` rows created for the
  right users with `read=0`, then assert `read=1` after
  `frappe.db.set_value("Notification Log", name, "read", 1)` (what the
  frontend does on open).
- Load check: confirm `on_update` overhead is negligible (recipient
  resolution should not do N+1 queries per save — cache role→user lookups
  per request).

---

## 7. Next step

Answer the 5 open decisions in §2 (recipients, audience, scope, granularity,
UI surface) — once set, Phase 1 can start immediately since it's
decision-agnostic infrastructure.
