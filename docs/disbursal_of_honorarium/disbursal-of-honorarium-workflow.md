# Disbursal of Honorarium — Approval Workflow Reference

> Source file: `rndopsapp/rndopsapp/doctype/disbursal_of_honorarium/disbursal_of_honorarium.py`
> Workflow name in DB: `Disbursal_Honorarium_Workflow_Through_Rest_API` (not version-controlled — lives only
> as a `Workflow` document in the site DB, same as several other workflows in this app; this file is the
> closest thing to a source-of-truth for it).
> Doctype: `Disbursal of Honorarium`

---

## 1. Current Approval Chain (as of 2026-08-20)

```
Draft ──Submit──► Pending Staff Approval ──Forward──► Pending HoS Approval ──Forward──► Pending Dean Approval
 (Permanent           (staff, RnD)                    (Hos, RnD)                        (Dean, RnD)
  Employee)                                                                                   │
                                                                                total_amount ≤ ₹2,00,000
                                                                                     │ Approve
                                                                                     ▼
                                                                                 Approved
                                                                                     ▲
                                                                                     │ Approve
                                                                          Pending Director Approval
                                                                                     ▲
                                                                                     │ Forward, total_amount > ₹2,00,000
                                                                          Pending Dean Approval (same node as above)
```

Every stage except `Pending Director Approval` also has a `Reject → Rejected` transition (`staff, RnD` from
`Pending Staff Approval`, `Hos, RnD` from `Pending HoS Approval`, `Dean, RnD` from `Pending Dean Approval`,
`Director` from `Pending Director Approval`).

**`Pending PI Approval` exists as a state but has no transition into it** — only `Pending Staff Approval` is
reachable from `Draft`. This is orphaned config unrelated to the 2026-08-20 change below; left as found.

---

## 2. States

| State | `doc_status` | Who acts here (`allow_edit`) |
|---|---|---|
| `Draft` | 0 | Permanent Employee |
| `Pending PI Approval` | 0 | Permanent Employee — unreachable, see §1 |
| `Pending Staff Approval` | 0 | `staff, RnD` |
| `Pending HoS Approval` | 0 | `Hos, RnD (Head of Section, RnD)` |
| `Pending Dean Approval` | 0 | `Dean, RnD` |
| `Pending Director Approval` | 0 | `Director` |
| `Approved` | 1 | Administrator |
| `Rejected` | 1 | Administrator |

## 3. Transitions

| From state | Action | To state | Allowed role | Condition |
|---|---|---|---|---|
| `Draft` | Submit | `Pending Staff Approval` | Permanent Employee | — |
| `Pending Staff Approval` | Forward | `Pending HoS Approval` | `staff, RnD` | — |
| `Pending Staff Approval` | Reject | `Rejected` | `staff, RnD` | — |
| `Pending HoS Approval` | Forward | `Pending Dean Approval` | `Hos, RnD (Head of Section, RnD)` | — (always forwards, no amount gate) |
| `Pending HoS Approval` | Reject | `Rejected` | `Hos, RnD (Head of Section, RnD)` | — |
| `Pending Dean Approval` | Approve | `Approved` | `Dean, RnD` | `doc.total_amount <= 200000` |
| `Pending Dean Approval` | Forward | `Pending Director Approval` | `Dean, RnD` | `doc.total_amount > 200000` |
| `Pending Dean Approval` | Reject | `Rejected` | `Dean, RnD` | — |
| `Pending Director Approval` | Approve | `Approved` | `Director` | — |
| `Pending Director Approval` | Reject | `Rejected` | `Director` | — |

The amount gate is intentionally split as two mutually-exclusive `Forward`/`Approve` transitions off the same
`(state, action)` pair rather than one transition with branching logic — `perform_disbursal_of_honorarium_action`
iterates every transition row matching `(current_state, action)` in order and skips any whose `condition` evaluates
falsy (`disbursal_of_honorarium.py:442-452`), so multiple rows sharing a state+action are how amount-based routing
is expressed in this workflow engine. This is the same pattern `Direct_Purchase_Workflow` uses for its own
Dean→Director escalation.

---

## 4. History — 2026-08-20 policy change

**Before:** `Pending HoS Approval` forwarded to one of two places based on amount — `Pending Associate Dean`
(`Ado_RnD` role) if `total_amount ≤ ₹30,000`, or `Pending Dean Approval` if `> ₹30,000`. This mirrored several
other financial forms in the system (Temporary Advance, Disbursal of Consultancy, TA DA Settlement all still use
this Associate-Dean-vs-Dean, ₹30,000 shape today — this change only affected Disbursal of Honorarium).

**What broke it:** at some point between the workflow's creation (2026-02-11) and 2026-08-20, the
`Pending Associate Dean` state and its three transitions were dropped from the live `Workflow` record (Desk-UI
edit, cause unknown — this workflow has no fixture/export in version control, so there's no diff to inspect).
Only the `> ₹30,000 → Pending Dean Approval` transition survived. Every Disbursal of Honorarium with
`total_amount ≤ ₹30,000` was left with **no transition at all** out of `Pending HoS Approval` other than Reject —
confirmed live on 2026-08-20 against document `202608062A002491` (₹24,000, stuck at `Pending HoS Approval`
indefinitely when HoS clicked Forward).

**Policy decision (2026-08-20):** rather than restore the Associate Dean stage, the organization changed the
actual policy — Associate Dean is retired from this workflow entirely. New shape: Dean approves outright up to
₹2,00,000; above that, Dean forwards to Director (the same escalation shape already used by
`Direct_Purchase_Workflow`, with `Director` as the approving role at that stage — see
[direct_purchase/directpurchaseworkflow.md](../direct_purchase/directpurchaseworkflow.md)).

**What changed, concretely:**
- `Pending HoS Approval → Forward → Pending Dean Approval` — amount condition removed, now unconditional.
- `Pending Dean Approval → Approve → Approved` — gained condition `doc.total_amount <= 200000`.
- New: `Pending Dean Approval → Forward → Pending Director Approval` — `doc.total_amount > 200000`.
- New state `Pending Director Approval` + `Approve`/`Reject` transitions, role `Director`.
- `Pending Associate Dean` state and its transitions were **not** restored — deliberately retired.

Applied directly to the live `Workflow` document (no code deploy — this workflow isn't in version control).
See [general/workflow_audit_report.md](../general/workflow_audit_report.md) for the resulting raw state/transition
dump, and [general/ERP_COMPLETE_APPLICATIONS_MANUAL.md §1.5](../general/ERP_COMPLETE_APPLICATIONS_MANUAL.md#15-disbursal-of-honorarium-)
for the user-facing description.

---

## 5. Why `frappe.db.set_value` instead of `doc.save()`/`doc.submit()`

`perform_disbursal_of_honorarium_action` (`disbursal_of_honorarium.py:424-574`) writes `workflow_state` (and
`docstatus`, when it changes) directly via `frappe.db.set_value`, rather than going through the Document API:

- `doc.save()`/`doc.submit()` call `validate_workflow()`, which filters allowed transitions by the **caller's
  Frappe desk roles**. API callers (the mobile/web app) don't carry those roles the way a Desk session would, so
  Frappe throws `WorkflowTransitionError: Transition not allowed from X to Draft`.
- Writing directly to the DB bypasses `validate_workflow()` entirely. **This means
  `perform_disbursal_of_honorarium_action` itself never checks the caller's role against `t.allowed`** — it only
  matches `(state, action, condition)`. Role enforcement is purely advisory, done client-side: the frontend only
  shows action buttons for what `get_disbursal_of_honorarium_workflow_actions` returns, which *does* filter by
  `t.allowed in frappe.get_roles(frappe.session.user)` (`disbursal_of_honorarium.py:588-611`). Any authenticated
  user who knows a docname could technically POST `action="Approve"` directly regardless of role. Pre-existing
  behavior across this whole file, not introduced by the 2026-08-20 Dean/Director work — noted here, not fixed,
  per explicit instruction to leave it out of scope. The two Director-hardcopy endpoints in §7
  (`update_send_to_director_honorarium`, `attach_director_pdf_honorarium`) are the exception — those *do* check
  roles server-side.
- Confirmed live: none of `Hos, RnD`, `Dean, RnD`, or `Director` have any `DocPerm` row at all on `Disbursal of
  Honorarium` (only `System Manager`, `Permanent Employee`, `staff, RnD`, `All_ProRnd_User` do) — so this bypass
  isn't optional, it's the only way these roles can act on the document at all through the standard screens.

**Consequence:** since `frappe.db.set_value` doesn't trigger ORM hooks, the `on_update` hook
(`check_workflow_and_publish`) never fires for this doctype's transitions. Kafka commit-staging publish is
therefore triggered **explicitly** inside `perform_disbursal_of_honorarium_action` whenever `next_state ==
"Approved"` (lines 516-559) — this fires identically whether `Approved` was reached via Dean (≤ ₹2,00,000) or
Director (> ₹2,00,000), since the check is only on the resulting state, not which role/stage produced it.

---

## 6. API surface

| Endpoint | Purpose |
|---|---|
| `get_disbursal_of_honorarium_fields(doc_name=None)` | Field metadata + prefill data for the form |
| `save_disbursal_of_honorarium_data(data, files=None)` | Create/update the Draft document |
| `submit_disbursal_of_honorarium(docname)` | Draft → `Pending Staff Approval` (wraps the `Submit` transition) |
| `get_disbursal_of_honorarium_workflow_actions(docname)` | Actions available to the current user at the doc's current state |
| `perform_disbursal_of_honorarium_action(docname, action)` | Executes a transition (Forward/Approve/Reject) — gated per §7 for Director Approve |
| `get_disbursal_of_honorarium_by_project(project_code, limit, start)` | List disbursals for a project |

The frontend (`DisbursalOfHonorariumActionButtons.tsx` in `prornd-ui`) reads available actions dynamically from
`get_disbursal_of_honorarium_workflow_actions` rather than hardcoding state names or thresholds — the 2026-08-20
Dean/Director restructuring required no frontend code changes. The Director-hardcopy endpoints in §7 are new
surface area the frontend does need to integrate.

---

## 7. Director hardcopy / PDF flow (added 2026-08-20, mirrors Indent General Form)

Director approval for Disbursal of Honorarium requires a **physically-signed, scanned PDF** — not a plain
in-system click — matching the pattern already used by `Indent General Form`
(`indent_general_form.py:447-547`) and `Travel_Workflow`. This is a deliberate choice over the simpler
`Direct_Purchase_Workflow`-style plain approval that Honorarium's Director stage originally launched with earlier
the same day; it was upgraded to the hardcopy-gated pattern before anyone used it in production.

**New doctype fields** (`disbursal_of_honorarium.json`):

| Field | Type | Notes |
|---|---|---|
| `send_to_director` | Check, default 0 | One-way flag; set once, never cleared |
| `director_signed_pdf` | Data, hidden | Stores the uploaded scan's file URL, not a file itself |

**Endpoints:**

| Endpoint | Caller | What it does |
|---|---|---|
| `update_send_to_director_honorarium(docname, send_to_director)` | Dean, RnD / System Manager | Manually opts a document into the Director-hardcopy flow. Only callable from `Pending Dean Approval`. Sets `send_to_director=1` and `workflow_state="Pending Director Approval"` directly via `frappe.db.set_value` — bypasses the declarative Workflow transition table entirely, same as the amount-based auto-Forward does. One-way: passing `send_to_director=0` throws. |
| `attach_director_pdf_honorarium(docname, file_url)` | staff, RnD / System Manager | Binds an **already-uploaded** file's URL to `director_signed_pdf`. Only callable while in `Pending Director Approval`. The actual file upload itself goes through the generic Frappe file-upload endpoint first (e.g. `upload_file`); this call just records the resulting URL on the document. Replacing an existing value is allowed (re-upload if the scan was wrong). |
| `get_pending_director_uploads_honorarium()` | any | Lists every `Pending Director Approval` doc (both awaiting upload and already-uploaded), for a Staff-facing "needs signature" queue. Row fields: `name`, `project_name`, `project_no`, `account_head`, `total_amount`, `webmail_id`, `name_of_applicant`, `applicant_department`, `director_signed_pdf`, `send_to_director`, `modified`, `workflow_state` — `name_of_applicant`/`applicant_department` are `fetch_from: webmail_id.*` display fields, added 2026-08-20 so the frontend doesn't have to resolve `webmail_id` itself. |

**The gate** (`perform_disbursal_of_honorarium_action`, right after fetching `current_state`): calling `action="Approve"`
while `current_state == "Pending Director Approval"` and `director_signed_pdf` is empty throws
`"Cannot approve: the Director-signed PDF has not been uploaded by Staff yet."` before the normal transition
lookup even runs.

**Typical flow for an amount > ₹2,00,000:**
1. Dean forwards (`perform_disbursal_of_honorarium_action(docname, "Forward")`) — auto-routes via the
   `total_amount > 200000` transition to `Pending Director Approval`. (`update_send_to_director_honorarium` is
   only needed if Dean wants to escalate a *smaller* amount to Director at their own discretion — the normal
   >₹2,00,000 path doesn't need it, since the transition condition already lands the document there.)
2. Someone physically gets the Director's signature on a printed copy.
3. Staff uploads the scan (generic upload endpoint) and calls `attach_director_pdf_honorarium(docname, file_url)`.
4. Director (or Staff on the Director's behalf) calls `perform_disbursal_of_honorarium_action(docname, "Approve")`
   — now unblocked.
