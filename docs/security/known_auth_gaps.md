# Known Authorization Gaps — Application Doctypes

> Logged 2026-08-17 during delegation-feature work. Not fixed — deliberately
> out of scope for that work (see below). This is a record for follow-up, not
> an action plan; each item needs its own review before touching code.

## Context

While wiring document-level delegation checks, an audit of how the app's own
whitelisted API functions (not generic Frappe desk) read/write the 13
"application" doctypes (Project Registration, Travel, TA DA Settlement,
Temporary Advance, Advance Settlement, Reimbursement, Direct Purchase,
Disbursal of Consultancy, Disbursal of Honorarium, Loan Request, Indent
General Form, Indent Cum Sanction Sheet, Recruitment Adhoc Contractual) found
that most single-document read/write endpoints call `frappe.get_doc()` /
`doc.save(ignore_permissions=True)` directly, with **no ownership or role
check at all** — not a delegation gap, a pre-existing one, present before any
of this session's changes.

The fix machinery already exists and is unused:
`rndopsapp.rndopsapp.delegate_user.delegate_user.require_document_access(doc,
action_type)` — raises `PermissionError` unless the caller owns the document,
holds an active delegation from an owner, or is System Manager. Its docstring
says to call it at the top of any single-document read/write function; almost
nothing does.

## Critical — live, exploitable, unauthenticated

**`doctype/recruitment_adhoc_contractual/recruitment_adhoc_contractual.py`**,
functions `update_walk_in`, `update_upfa_interview_date`,
`update_upfa_interview_time`, `update_last_date_of_appllication` (~L863-883):
registered `allow_guest=True`, accept a caller-supplied `user` string, loosely
resolve it against `User` records, call `frappe.set_user(user)`, then write
the field as that impersonated user. **No login required.** Anyone with
network access can impersonate a resolvable user and mutate this doctype.

## Critical — deliberate role-check bypass

Three workflow-action handlers write via `frappe.db.set_value()` instead of
`.save()`/`.submit()`, specifically to skip Frappe's `validate_workflow()`
role check (comments in the code say this is intentional, "because API
callers lack the desk roles"):
- `doctype/disbursal_of_consultancy/disbursal_of_consultancy.py` →
  `perform_disbursal_of_consultancy_action` (~L381-439)
- `doctype/disbursal_of_honorarium/disbursal_of_honorarium.py` →
  `perform_disbursal_of_honorarium_action` (~L424-499)
- `doctype/indent_general_form/indent_general_form.py` →
  `perform_indent_general_form_action` (~L220-253)

Any authenticated user can drive these through any workflow transition,
including ones that trigger financial Kafka commit publishes.

## High — broken/inverted existing check

`doctype/project_registration/project_registration.py` →
`save_project_draft` (~L1670-1780): the ownership check is inverted — the
non-owner/non-admin branch silently passes, while the branch that throws only
fires when the caller **is** System Manager and not the owner. Net effect:
blocks admins, lets everyone else through.

## High — financial side-effects, no ownership check

- `doctype/advance_settlement/advance_settlement.py` →
  `submit_advance_settlement_commit` (~L619): attacker-controlled
  `commit_amount`/`budget_head` published to Kafka for any document name.
- `rndopsapp/commitPayment.py` → `submit_commit_data` (~L865): same pattern,
  shared across all 13 doctypes' approval flows.
- `doctype/direct_purchase/direct_purchase.py` → `generate_p11_form` /
  `generate_sanction_sheet` / `generate_purchase_order` (~L801-926): chained
  document generation + workflow-state mutation, no check at any step.

## Standard — ~25 functions with no check at all

Every `get_X_fields(doc_name)`, `save_X_data`/`save_X`, and
`get_X_commit_details` across all 13 doctype controllers. These are the
lowest-risk fix (pure addition of `require_document_access()`, no existing
logic to preserve/conflict with) — see the full per-function inventory that
produced this doc (agent transcript, 2026-08-17) for exact file:line
references if picking this up later.

## Not part of this gap — already correctly protected

`update_proposed_budget_breakup`, `delete_draft_project`,
`preview_pr_cascade_delete`/`delete_pr_cascade`, `attach_director_pdf_travel`,
all ICSS workflow/put-back/director functions, IGF's
`update_send_to_director_igf`/`attach_director_pdf_igf`/`put_back`,
`update_chairperson_fields`, `cancellation_api.get_original_commitment`
(uses `frappe.has_permission()` correctly — good model to copy), and every
`get_X_workflow_actions`/`perform_X_action` pair that already has a
role-based transition check (Travel, TA DA Settlement, Temporary Advance,
Advance Settlement, Reimbursement, Direct Purchase, Loan Request, ICSS).

**Caution for whoever picks this up:** many of the "no ownership check"
functions are workflow-action handlers that are *supposed* to let a
non-owner (director, approver, dean) act on someone else's document via a
role check. Bolting `require_document_access()` onto those without also
accounting for the legitimate role-based path would break real approval
flows, not fix a bug — this needs per-function review, not a mechanical
find/replace.
