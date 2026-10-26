# Cancellation Request — independent workflow

A **Cancellation Request** asks for an application (Reimbursement, Travel, Direct Purchase, …) to be
cancelled. It is approved through **its own workflow**, not a copy of the application's workflow.

Code:

| File | Role |
|---|---|
| `rndopsapp/rndopsapp/cancellation_workflow.py` | Stage rules, route resolver, builds the workflow |
| `rndopsapp/rndopsapp/doctype/cancellation_request/` | Doctype + controller (sets route, marks original cancelled / request rejected) |
| `rndopsapp/rndopsapp/cancellation_api.py` | Whitelisted API (create request, list applications, status, details) and the lock hook |
| `rndopsapp/workflow_pipeline.py` | `WorkflowManager` — honors transition conditions, picks the cancellation workflow |
| `rndopsapp/patchs/create_cancellation_request_workflow.py` | Creates the workflow on `bench migrate` |

## The chain

```
Draft → [Head] → Staff → HoS → Dean → Approved
```

Plus two single-stage entries for applications still waiting on the applicant side: **Mentor** and **Other PI**. There is **no PI stage**: an application pending at its PI is cancelled through Staff.

| Stage | Workflow state | Role that approves |
|---|---|---|
| Mentor | Pending Mentor Approval | `Mentor` |
| Other PI | Pending Other PI | `Other PI` |
| Head | Pending Head Approval | `head_approver_1` |
| Staff | Pending Staff Approval | `staff, RnD` |
| HoS | Pending HoS Approval | `Hos, RnD (Head of Section, RnD)` |
| Dean | Pending Dean Approval | `Dean, RnD` |

`Head` is only part of the chain for **Top Up Fellowship**, **Recruitment Adhoc Contractual** and **Travel**
(`HEAD_APPROVAL_DOCTYPES`). Every other application skips it. The Head stage goes to **one person** — the head of the initiator's department (see `_cancellation_head_user` in `module_registry.py`) — not to every holder of the Head role. For Travel this is the applicant's own department head, not the funding PI's head that the Travel form itself is re-pointed to.

## The rule: the cancellation ends where the application is

The cancellation walks the same stages as an approval would, **up to the stage the application is
currently waiting at**. Approving at that last stage finishes the cancellation (state → *Approved*) and
the original application is marked *Cancelled*.

`stage_for_application_state()` maps the application's `workflow_state` to the stop stage:

| Application state | Cancellation route (ends at) |
|---|---|
| Pending Mentor Approval | Mentor |
| Pending PI Approval | [Head →] Staff (the PI is skipped) |
| Pending Other PI | Other PI |
| Pending Head Approval / HoD Approval | Head |
| Pending Staff Approval (incl. Misc. Staff) | [Head →] Staff |
| Pending HoS Approval | [Head →] Staff → HoS |
| Pending Associate Dean / Dean / Director | [Head →] Staff → HoS → Dean |
| Approved, or any later state (Sanction Approved, Pending PO Generation, Pending Staff Verification, …) | [Head →] Staff → HoS → Dean |
| Draft, Rejected, Cancelled, Needs Correction, Rectification, Pending Applicant Acknowledgment | **not cancellable** — the request is refused |

`[Head →]` appears only for the Head doctypes (Top Up Fellowship, Recruitment Adhoc Contractual, Travel).

### Examples

* **Reimbursement, already Approved** → Draft → Staff → HoS → Dean → Approved.
* **Reimbursement, pending Staff** → Draft → Staff → Approved.
* **Any application pending at HoS** → Draft → Staff → HoS → Approved.
* **Direct Purchase, already Approved or at "Pending PO Generation"** → Draft → Staff → HoS → Dean → Approved. The long Direct Purchase workflow is ignored.
* **Top Up Fellowship, pending Staff** → Draft → Head → Staff → Approved.
* **Travel, pending PI Approval** → Draft → Head → Staff → Approved (PI skipped).
* **Top Up Fellowship, pending PI Approval** → Draft → Head → Staff → Approved.
* **Travel, pending Other PI** → Draft → Other PI → Approved.
* **Any application pending at Head** → Draft → Head → Approved.

Applies to every application type, including Reimbursement, Advance, Disbursal, Purchase,
Recruitment, Travel and Loan — nothing is configured per doctype.

## How it is implemented

### 1. One workflow, "Cancellation Request Workflow"

`ensure_cancellation_workflow()` builds it from the definitions in `cancellation_workflow.py`
(idempotent; `rebuild=True` recreates it). It is created by the migrate patch, and lazily the first
time a request is inserted if it is missing. It is the only workflow on the doctype, so there is no
per-doctype cloning, rebuilding, or switching of `is_active`.

States: Draft, the seven stage states, Approved, Rejected.
Transitions per stage: **Approve** (to the next stage, or to Approved), **Reject** (to Rejected).
Draft has one **Submit** transition per first stage.

### 2. The route is stored on the request

At insert, `CancellationRequest.set_route()` reads the application's current `workflow_state` and
calls `resolve_cancellation_path()`. It stores two read-only fields:

* `stop_stage` — last stage, e.g. `HoS`
* `stage_path` — delimited stages, e.g. `|Staff|HoS|`

The route is fixed at filing time. The application is locked while the request is pending, so its
state cannot move underneath it.

### 3. Transition conditions pick the route

Each transition carries a Frappe workflow **condition**, evaluated against the request:

| Transition | Condition |
|---|---|
| Draft → *first stage X* | `(doc.stage_path or "").startswith("\|X\|")` |
| Stage → next stage Y | `"\|Y\|" in (doc.stage_path or "")` |
| Stage X → Approved | `doc.stop_stage == "X"` |
| Stage → Rejected | none |

So at every state exactly one *Approve* is available: onward if the route continues, to *Approved* if
this is the stop stage. This uses Frappe's native mechanism, so the form's action buttons and
`apply_workflow` both follow it. `WorkflowManager` (used by the custom API) also checks conditions now
(`_transition_applies`).

### 4. Filing the request — `create_cancellation_request`

1. Validate: reason given, document exists, user owns it / is System Manager / is its head or PI,
   no other pending request for it.
2. Insert the request (route + workflow are set in `before_insert`; an uncancellable state raises).
3. `apply_workflow(request, "Submit")` moves it from Draft to the first stage. Failure here is
   raised, not hidden.
4. Comment added on the original document.

### 5. Approval → original cancelled

When the request reaches **Approved**, `on_update` / `on_update_after_submit` / `on_submit` call
`_mark_original_as_cancelled`, which sets the application's `workflow_state` to *Cancelled*, marks
the request `status = Approved`, flips the Kafka Commit Staging rows to CANCELLED, calls the ledger
cancel-commit API, and adds comments on both documents. A failure in this step is re-raised so the
approval rolls back instead of leaving an *Approved* request with a live application.

### 6. Rejection

State → **Rejected** sets `status = Rejected` (`_mark_rejected`). The application is untouched, its
lock is released and a new request can be filed.

### 7. Lock

`validate_original_document_not_locked` is registered as a `validate` hook on all doctypes
(`hooks.py`). While a request for a document has `status = Pending`, saving that document raises
*"This application is locked because a cancellation request (…) is pending approval."*

## Adding or changing things

* **Change who approves a stage** — edit `STAGE_STATES` roles, then
  `ensure_cancellation_workflow(rebuild=True)` (bench console).
* **Add the Head stage to another doctype** — add it to `HEAD_APPROVAL_DOCTYPES`. No migration needed.
* **Map a new application state** — edit `stage_for_application_state()`; add a test in
  `test_cancellation_request.py`.

## Existing requests and the old workflows

"Cancellation Request Workflow" is the **only** workflow in use. The 13 old `cancel_<workflow>`
workflows are inactive, nothing creates, rebuilds or activates them, and `WorkflowManager` no longer
reads them. They can be deleted.

Requests filed before this change have no `stage_path`/`stop_stage`. A legacy request sitting in a
state the new workflow does not have (for example a *Pending Head Approval* inherited from a cloned
workflow) has no action buttons; a System Manager has to move it.

## Tests

`rndopsapp/rndopsapp/doctype/cancellation_request/test_cancellation_request.py` covers the route
mapping (every case above) and walks each route through the real workflow to check it reaches
*Approved* at the right stage. Run with `bench --site <site> run-tests --doctype "Cancellation Request"`.

## Behaviour changes to be aware of

* The lock hook is now live, on every doctype (see 7).
* `WorkflowManager` now honors `condition` on transitions for every doctype, as Frappe does.
* A cancellation can no longer be filed for Draft, Rejected, Needs Correction or Pending Applicant
  Acknowledgment applications.
* Self-approval is allowed on all cancellation transitions (same default as the old clones).
* `Principal Investigator` is not a Role on this site, so the Other PI stage uses the `Other PI` role only.
