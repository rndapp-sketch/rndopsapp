# `put_back_action.py` — Workflow "Put Back" Action

## Overview

"Put Back" lets a user force a document's `workflow_state` backward to an earlier state in its own workflow chain — e.g. sending a document that's `Pending HOS Approval` back to `Pending Staff Approval` or `Draft`.

Normal workflow transitions are role-gated (`Workflow Transition.allowed`), so a user who wants to send a document back a step usually doesn't hold the role for that specific *forward* transition in reverse. This module deliberately **bypasses that role check** by writing `workflow_state` straight to the database instead of going through `doc.save()`. To keep that bypass safe, every put-back is made auditable: the acting `username` must be supplied explicitly and is always recorded — together with the logged-in session user and an optional reason — as a `Comment` on the document.

| Function | Whitelisted as | Purpose |
|---|---|---|
| `get_put_back_document_states(doctype, docname)` | `frappe.whitelist()` | Returns the list of valid "put back" target states for a document. |
| `set_put_back_workflow_state(doctype, docname, state, username, comment=None)` | `frappe.whitelist()` | Performs the put-back: writes the new state and logs a Comment. |
| `get_put_back_document_states_test(...)` | `frappe.whitelist(allow_guest=True)` | **Test-only** clone of the getter. |
| `set_put_back_workflow_state_test(...)` | `frappe.whitelist(allow_guest=True)` | **Test-only** clone of the writer. |

---

## `_get_active_workflow(doctype)`

Resolves which `Workflow` document governs a doctype:

1. Look for a `Workflow` where `document_type == doctype` and `is_active == 1`.
2. If none is active, fall back to *any* `Workflow` for that doctype.
3. Return the first match's `name`, or `None` if the doctype has no workflow at all.

---

## Step 1 — `get_put_back_document_states`

Given a document's current `workflow_state`, walks the workflow's transition graph **backwards** to build the list of valid put-back targets.

1. Confirm the document exists and resolve its active workflow (via `_get_active_workflow`). Either failure returns `{"status": "error", ...}`.
2. Read the document's current `workflow_state`. If it has none, return an empty state list.
3. Load all `Workflow Transition` rows for the workflow (`state`, `next_state` pairs) and invert them into a `predecessors` map: `next_state → [state, ...]`.
4. Starting from `current_state`, repeatedly look up predecessors, take the first unseen one, append it to `states`, and continue from there — stopping when a state has no unseen predecessor (cycle guard via a `seen` set).

```
current_state = "Pending HOS Approval"
predecessors  = {"Pending HOS Approval": ["Pending Staff Approval"],
                  "Pending Staff Approval": ["Draft"]}

→ states = ["Pending Staff Approval", "Draft"]
```

**Note:** if a state has multiple predecessors (a workflow with more than one incoming transition), only the *first* one returned by `frappe.get_all` is followed — the walk does not branch or explore alternate paths.

**Automation-only states (`STATE_ALIASES`):** some workflow states are entered only by a Kafka consumer writing `workflow_state` straight to the database (see `kafka/consumer/fund_received/mapper.py`), never by a user clicking a real `Workflow Transition` — so they have no predecessor edge for the walk above to find, and would otherwise return `states: []`. `STATE_ALIASES` maps each such state to the state it should be treated as equivalent-position to; when the direct walk from `current_state` dead-ends, it resumes from the alias's own predecessors instead. Fund Received's `Pending Rectification` / `Pending Reconciliation` / `Rejected` all alias to `PENDING_APPROVAL` (same priority tier in `FundReceivedConsumerMapper._STATE_PRIORITY`), so put-back on any of them offers the same chain `PENDING_APPROVAL` itself would: `["Pending Misc. Staff Approval", "Draft"]`. All states listed as an alias *source* for a doctype are also excluded from ever appearing as a predecessor *result* — otherwise, once `Pending Rectification` gained a real `Forward` transition into `PENDING_APPROVAL`, it would incorrectly show up as a put-back step for its own sibling states (`Rejected`, `Pending Reconciliation`).

Returns:
```json
{"status": "success", "current_state": "Pending HOS Approval", "states": ["Pending Staff Approval", "Draft"]}
```

---

## Step 2 — `set_put_back_workflow_state`

Performs the actual state reversion.

1. **Validate inputs:** document must exist; `username` (trimmed) and `state` are required.
2. **Validate target state:** if the doctype has a workflow, `state` must appear in that workflow's `Workflow Document State` list — otherwise the request is rejected with `"'{state}' is not a valid state for this workflow"`.
3. **Capture context:** reads the current `workflow_state` as `prev_state` (defaulting to `"Unknown"`) and the active session user (`frappe.session.user`) — this is the user who is *invoking* the API, not necessarily the `username` credited with the action.
4. **Write the state directly:**
   ```python
   frappe.db.set_value(doctype, docname, "workflow_state", state, update_modified=False)
   ```
   This is the bypass: going around `doc.save()` means the `Workflow Transition` role check (which only fires on a normal save-triggered transition) never runs.
5. **Log a `Comment`**, not an `Activity Log` entry — Frappe's document "Activity" tab reads `docinfo.workflow_logs`, which is built from `Comment` records with `comment_type: "Workflow"`. Writing an `Activity Log` doc instead would be invisible in the UI, so the audit trail has to be a `Comment`:
   ```
   [Put Back] {username}: {prev_state} → {state} | Reason: {comment}
   ```
   inserted with `ignore_permissions=True`.
6. `frappe.db.commit()` and return a success payload including `from_state`, `to_state`, `put_back_by` (the supplied `username`), and `session_user`.

All failures are caught, logged via `frappe.log_error`, and returned as `{"status": "error", "message": ...}` rather than raising.

---

## ⚠️ Guest-accessible test endpoints

`get_put_back_document_states_test` and `set_put_back_workflow_state_test` are thin wrappers marked `allow_guest=True`, explicitly commented `"TESTING ONLY ... Remove before production."`

- `set_put_back_workflow_state_test` inherits the full bypass described above (direct DB write, no role check) **and** requires no authentication — any unauthenticated caller can revert the workflow state of *any* document in the system.
- If this file is deployed as-is, these two endpoints are a live privilege-escalation / data-integrity risk, not just a hypothetical one — they should be removed (or gated behind a non-production feature flag) before this reaches a production site.

---

## Integration with `doctype/fund_received/fund_received.py`

The Fund Received workflow-actions UI calls `get_fund_received_workflow_actions(docname)` to decide which action buttons to show, and `perform_fund_received_action(docname, action, ...)` to execute one — both normally driven entirely by real `Workflow Transition` rows matching the document's current state.

- `get_fund_received_workflow_actions`: after the normal per-transition role check, if the current state is a `STATE_ALIASES` key for `"Fund Received"` (i.e. `Pending Rectification` / `Pending Reconciliation` / `Rejected`) and the user has `staff, RnD`, `RnD Administration`, or `System Manager`, `"Put Back"` is appended even though no real transition row grants it. `staff, RnD` is included specifically because it's the same role granted the real `Forward` transition out of `Pending Rectification` — whoever can resubmit a document must also be able to put it back (see the incident writeup in `fund-received-ledger-status.md` §6, where gating Put Back to `RnD Administration` only left every `staff, RnD` user seeing `Forward` with no way to reverse it).
- `perform_fund_received_action`: before the normal transition lookup (which would otherwise `frappe.throw` with "No valid transition found"), an early branch catches `action == "Put Back"` from one of those same aliased states, independently re-checks the same three roles (defense in depth — this function can be called directly, not just via the action list), resolves the target via `get_put_back_document_states`, and calls `set_put_back_workflow_state` directly — skipping every forward-transition side effect (deposit slip creation, `doc.submit()`, Kafka publish) that only makes sense for a real forward move.

## Audit trail caveat

Auditability here depends entirely on the caller supplying an honest `username`. Nothing in `set_put_back_workflow_state` verifies that `username` corresponds to the actual person acting — it's a free-text argument, cross-checked only against `frappe.session.user` for the log entry, not validated as the same identity. A malicious or misconfigured caller could attribute a put-back to any username string.
