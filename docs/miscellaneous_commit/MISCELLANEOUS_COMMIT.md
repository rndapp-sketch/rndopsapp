# Miscellaneous Commit — How It Works

`Miscellaneous Commit` is a submittable Frappe DocType used to record an ad-hoc
budget **Commit** or **De-Commit** against a project's budget head, outside the
flow of any specific module-specific form (Reimbursement, TA/DA, Loan Request,
etc.). Once approved, the commit amount is pushed to an external ledger system
over Kafka so the project's "committed" balance reflects it.

Backend code: [`miscellaneous_commit.py`](miscellaneous_commit.py)
DocType schema: [`miscellaneous_commit.json`](miscellaneous_commit.json)
Client script: [`miscellaneous_commit.js`](miscellaneous_commit.js) — empty; the
UI is a custom frontend (not the standard Frappe desk form) that talks to the
whitelisted methods below.

---

## 1. DocType shape

- **Autoname:** `format:{YYYY}{MM}{DD}MiSCoM{######}` — e.g. `20260729MiSCoM000001`.
- **Submittable:** `is_submittable: 1`, plus a **Workflow** drives state transitions
  (see §3) rather than the plain submit/cancel buttons.
- **`amended_from`** — standard Frappe field for amending a cancelled doc.

| Field | Type | Notes |
|---|---|---|
| `project_number` | Link → Project Registration | required |
| `budget_head` | Link → Budget Head | required (labelled "Account Head") |
| `commit_decommit` | Select: `Commit` / `De-Commit` | required |
| `commit_amount` | Currency | required |
| `commit_particular` | Data | required, free-text description |
| `linked_application` | Data | only mandatory when `module == "Recruitment Adhoc Contractual"` |
| `applicant_webmail` / `applicant_department` / `applicant_designation` | Data | required, prefilled from the logged-in `User` |
| `module` | Select | required; the option list is **not** static — see §2 |
| `workflow_state` | Data, read-only | driven by the Workflow engine |

### Permissions (from the JSON, not the workflow)

| Role | create/write/delete | submit |
|---|---|---|
| System Manager | yes | yes |
| All_ProRnd_User, Permanent Employee, `staff, RnD` | yes | yes |
| `Hos, RnD (Head of Section, RnD)` | write/read only, no create/delete | no |
| `Dean, RnD` | write/read only, no create/delete | no |

This shape (staff can create/submit, Hos/Dean can only read+write) matches a
typical staff-raises → section-head-reviews → dean-approves chain, which lines
up with the workflow-role comments in the code (§3).

---

## 2. The `module` dropdown is dynamic, not static

`get_miscellaneous_commit_fields()` overrides the doctype's own Select options
for the `module` field at request time. Instead of the static option list baked
into the JSON, it reads live from the **Module Registry** doctype:

1. Finds the `Module Registry` document whose `page_name == "pending-task"`.
2. Collects the distinct `doctype_name` values from its `doctype_name` child
   table, excluding `"Miscellaneous Commit"` itself.
3. Sorts them and rebuilds `field.options` as a newline-joined list.

This means newly registered modules automatically show up in the frontend
dropdown without a DocType migration — the JSON's baked-in option list is only
a fallback/reference, never actually served once this API is used.

---

## 3. Workflow: Draft → Submit → Approved

There's no `states: []` fixture for this doctype in the repo — the workflow
(`Workflow` doctype with `document_type == "Miscellaneous Commit"`,
`is_active = 1`) is configured directly in the site, not checked into code. The
Python only *drives* whatever transitions exist. What's explicit in the code:

- **Two roles can Submit from Draft** — `staff, RnD` and `Permanent Employee` —
  via **two separate transitions** that happen to share the same
  `(state="Draft", action="Submit")` pair. `perform_miscellaneous_commit_action`
  resolves this by walking `workflow.transitions` in order and taking the
  **first** transition whose `allowed` role matches the current user's roles —
  so which role you have determines which transition (and therefore which
  `next_state`) you land on.
- **`"Approved"` is the trigger state** for Kafka publishing (see §4) — reached
  when, per the code comment, "Dean approves."
- **System Manager** is always allowed to perform any transition regardless of
  its `allowed` roles (`perform_miscellaneous_commit_action` / `get_miscellaneous_commit_workflow_actions`
  both special-case it).

### Functions involved

- **`get_miscellaneous_commit_workflow_actions(docname)`** — returns the list
  of action names (e.g. `["Submit"]`) available to the *current user* from the
  document's *current* `workflow_state`, by filtering the active workflow's
  transitions to ones starting at that state and allowing one of the user's
  roles.
- **`submit_miscellaneous_commit(docname)`** — convenience wrapper that only
  works from `Draft`; internally just calls
  `perform_miscellaneous_commit_action(docname, "Submit")`. If the doc isn't in
  `Draft`, it returns an `"info"` status without doing anything.
- **`perform_miscellaneous_commit_action(docname, action)`** — the general
  transition executor:
  1. Loads the active workflow and finds the matching `(current_state, action)`
     transition allowed for the user (or System Manager).
  2. If `action == "Submit"`, stages the commit for Kafka **before** changing
     state (§4).
  3. Sets `doc.workflow_state = next_state` **on the in-memory doc before**
     calling `submit()` / `cancel()` / `save()` — this ordering matters because
     the global `on_update` hook (`check_workflow_and_publish`, §4) reads
     `workflow_state` off the doc during that same save, and a raw
     `frappe.db.set_value`/`db_set` afterwards would bypass `on_update` entirely
     and silently skip the Kafka publish.
  4. Picks the actual document operation from the workflow state's
     `doc_status`: `1` → `doc.submit()`, `2` → `doc.cancel()`, otherwise a plain
     `doc.save()`. Both `submit()`/`cancel()` are called with
     `ignore_permissions=True` and `ignore_workflow=True` (workflow enforcement
     is handled manually here, not by Frappe's built-in workflow action button).
  5. Commits and returns the new state plus the next set of available actions
     (calls `get_miscellaneous_commit_workflow_actions` again).

---

## 4. Kafka staging: how the commit reaches the external ledger

Publishing is **two-phase**, decoupled from the workflow transition itself:

**Phase 1 — Stage (happens inside `perform_miscellaneous_commit_action`, only on `action == "Submit"`):**

```
doc.project_number (Project Registration) → resolved to its project_no
signed_amount = +commit_amount  if commit_decommit == "Commit"
              = -commit_amount  if commit_decommit == "De-Commit"
→ submit_commit_data(doctype="Miscellaneous Commit", frapAppId=doc.name,
                      name=doc.name, project_name=project_no,
                      commit_amount=signed_amount, budget_head=doc.budget_head,
                      commitParticular=doc.commit_particular,
                      trigger_state="Approved")
```

`submit_commit_data` (in [`commitPayment.py`](../../commitPayment.py)) writes/
updates a **`Kafka Commit Staging`** row with `status = "PENDING_APPROVAL"` and
a JSON `payload` that embeds `trigger_state`. It does **not** talk to Kafka —
this just parks the payload until the document reaches the right state. If a
staging row for the same `(doctype, name)` already exists with status
`PENDING_APPROVAL` and the same `trigger_state`, it's updated in place rather
than duplicated (this is what lets a re-commit for a different `trigger_state`
coexist as a separate row for other doctypes that reuse this same mechanism).

**Phase 2 — Publish (happens automatically, decoupled from this doctype's code):**

`hooks.py` registers `commitPayment.check_workflow_and_publish` on the global
`doc_events["*"]["on_update"]` hook — it fires on **every** document save
across the whole site, not just Miscellaneous Commit. On each save it:

1. Reads the doc's current `workflow_state`.
2. Looks up any `Kafka Commit Staging` rows for this `(doctype, name)` still
   `PENDING_APPROVAL` or `FAILED`.
3. For each row, compares `current_state` to that row's stored `trigger_state`
   (`"Approved"` for Miscellaneous Commit). If they don't match, skips it.
4. Idempotency guard: if the state *before* this save was already the trigger
   state, skips (prevents re-publishing on unrelated re-saves once already
   approved).
5. Calls `kafka_publish_commit(...)` (from
   `rndopsapp.rndopsapp.kafka.producer.reimbursement`), passing the staged
   payload fields. The mapper resolves `moduleId` via `Module Registry` (same
   registry used for the `module` dropdown in §2) unless overridden in the
   payload.
6. Marks the staging row `PUBLISHED` on success or `FAILED` (with
   `error_message`) on failure, and fires a Mattermost notification either way.

So concretely, for Miscellaneous Commit: the staged payload only gets sent to
Kafka once `workflow_state` transitions to **`"Approved"`** — i.e. whichever
step in the workflow represents the Dean's approval — regardless of how many
intermediate states (e.g. an Hos/section-head review step) sit between Draft
and Approved.

A stuck/failed row can be re-driven manually via
`commitPayment.manually_publish_staged_commit(reference_name, reference_doctype)`,
and its current status can be checked via
`commitPayment.get_commit_staging_status(reference_name, ...)` (used by the
frontend "Make a Commitment" widget to avoid re-submitting a commit that's
already staged/published).

---

## 5. Frontend-facing API surface

All are `@frappe.whitelist()` and are meant to be called from the custom
frontend rather than the desk form (whose `.js` controller is empty).

| Method | Purpose |
|---|---|
| `get_miscellaneous_commit_fields(doc_name=None)` | Field metadata (label, type, options, mandatory/hidden/read-only, `depends_on`) + dynamic `module` options (§2) + prefill data (either from an existing doc, or the logged-in user's email/department/designation for a new one) + link options for `project_number` (id/label/title) and `budget_head` (id/label). |
| `save_miscellaneous_commit(doc_data)` | Create or update a Draft. Refuses to edit if `docstatus != 0` (submitted/cancelled). Only a fixed whitelist of scalar fields is settable (`project_number`, `budget_head`, `commit_decommit`, `module`, `commit_amount`, `commit_particular`, `linked_application`, `applicant_webmail`, `applicant_department`, `applicant_designation`). New docs default `applicant_webmail` to the session user. Returns `{"status": "error", ...}` (truncated traceback, 140 chars) on failure rather than raising. |
| `submit_miscellaneous_commit(docname)` | Submit-from-Draft convenience wrapper (§3). |
| `get_miscellaneous_commit_workflow_actions(docname)` | Actions available to the current user from the doc's current state (§3). |
| `perform_miscellaneous_commit_action(docname, action)` | Execute any workflow action, e.g. `"Submit"`, whatever an approver's action is named (`"Approve"`/`"Reject"` etc., defined in the site's Workflow doc) (§3, §4). |

---

## 6. End-to-end lifecycle (typical path)

```
1. User opens the form.
     → get_miscellaneous_commit_fields()  (fields, module list, prefill, link options)

2. User fills the form and saves as Draft (possibly multiple times).
     → save_miscellaneous_commit(doc_data)   [workflow_state == "Draft"]

3. User submits.
     → submit_miscellaneous_commit(docname)
         → perform_miscellaneous_commit_action(docname, "Submit")
             - role-specific transition picked ("staff, RnD" vs "Permanent Employee")
             - Kafka commit STAGED (Kafka Commit Staging, status=PENDING_APPROVAL,
               trigger_state="Approved")
             - workflow_state set in-memory, doc.submit()/save() called
             - on_update hook fires → check_workflow_and_publish
               → current_state != "Approved" yet → publish skipped

4. Approver(s) act on it (e.g. Hos, RnD review → Dean, RnD approval), each via
     → perform_miscellaneous_commit_action(docname, "<their action>")

5. The transition that lands workflow_state on "Approved" triggers the same
   on_update hook again:
     → check_workflow_and_publish finds the PENDING_APPROVAL staging row,
       current_state == trigger_state → kafka_publish_commit(...) is called
     → staging row marked PUBLISHED (or FAILED, retryable via
       manually_publish_staged_commit)
```

---

## 7. Notes / gotchas

- **Don't set `workflow_state` via `frappe.db.set_value`/`doc.db_set`** anywhere
  in a Miscellaneous Commit flow — it bypasses `on_update` and silently skips
  the Kafka publish (explicitly called out in the code comments).
- `save_miscellaneous_commit` and `perform_miscellaneous_commit_action` both
  swallow exceptions and return `{"status": "error", ...}` instead of raising —
  callers must check `status`, not rely on HTTP error codes.
- The actual set of workflow states/transitions/roles lives in the site's
  **Workflow** document (`document_type = "Miscellaneous Commit"`), not in this
  app's source — check the site directly (Workflow list) for the authoritative
  state diagram.

---

## 8. Secondary use: funding source for migrated-employee salary payments

Beyond ad-hoc project commits, `Miscellaneous Commit` doubles as the **fallback
funding source for salary payments to employees migrated from the legacy
system**, who have no `Recruitment Adhoc Contractual` / `Selection Committee
Report` record in this app. This is exactly why `module` includes a
`"Recruitment Adhoc Contractual"` option and `linked_application` becomes
mandatory for it (§1) — those fields were built for this case.

**To fund a migrated employee's salary from a project's budget:** create a
`Miscellaneous Commit` with:

| Field | Value |
|---|---|
| `project_number` | The employee's project |
| `module` | `"Recruitment Adhoc Contractual"` (required — this is the match key the fallback filters on) |
| `commit_decommit` | `"Commit"` (a `"De-Commit"` row is never used as a funding source) |
| `linked_application` | Optional. If set to the employee's `ps_emp_id`, the fallback prefers this record over other approved commits on the same project when there's more than one candidate. If left generic, the commit is treated as a shared, project-level pool any migrated employee on that project can draw from. |
| `budget_head`, `commit_amount`, `commit_particular` | As normal |

Once this document reaches `workflow_state == "Approved"`, it publishes to Kafka
exactly like any other Miscellaneous Commit (§4) — the ledger then holds a real
commit row keyed by `frapAppId = <this document's name>`. The salary module's
`commitPayment.salary_payment_data` looks for exactly that row
(`_find_migrated_employee_commit`, in
[`commitPayment.py`](../../commitPayment.py)) whenever an employee's Recruitment/
SCR chain doesn't resolve. Full design and rationale:
[`migrated-employee-salary-fallback.md`](../../migrated-employee-salary-fallback.md); step-by-step flow:
[`salary-payment-workflow.md`](../../salary-payment-workflow.md#2-1a-migrated-employee-fallback)
and
[`salary-module-full-flow.md`](../../salary-module-full-flow.md#step-4c--migrated-employee-fallback-only-runs-if-recruitmentscr-linkage-is-missing).
