# Deposit Slip — Staff Post-Submit Field Update: Implementation Plan

## Status: Implemented (2026-08-05)

Built as designed in §4: shared helper module
`rndopsapp/rndopsapp/deposit_slip_common.py`
(`update_locked_deposit_slip`, `ensure_staff_or_manager`, `PROTECTED_FIELDS`,
child-table diff logic, audit-comment logging), plus one thin
`update_<doctype>_fields(docname, changes, child_table_changes)` wrapper added
to each of the 7 doctype `.py` files, calling into the shared function.
Verified via `bench --site prornd.local run-tests` — new tests added to all 7
`test_<doctype>.py` files (17 tests total, all passing), covering: non-staff
caller blocked with `frappe.PermissionError`; field updates persist post-submit
(`Deposit slip`, real `docstatus=1`) and post-workflow-lock; `docstatus`,
`workflow_state`, `fund_received_ref`, and unknown fieldnames are silently
dropped rather than written or crashing the call; empty payload is a no-op;
child-table row updates apply; the audit Comment is recorded.

**One implementation change vs. the original design**: rather than the field
allowlist being derived purely from `frappe.get_meta()` (§4.2), it's
additionally intersected with the doctype's *real* DB columns
(`frappe.db.get_table_columns`), matching the schema-drift guard `api.py`'s
Doctype Explorer already uses. This turned out to be load-bearing, not just
defensive: testing surfaced that `workflow_state` is declared in the DocType
JSON for `T Testing`, `D Consultancy`, `Other Event`, and `E Non Routine`
Deposit Slip, but the column was never migrated into their DB tables —
pre-existing drift, unrelated to this change, likely meaning `bench migrate`
hasn't been run since that field was added to those 4 doctypes. Worth running
a migration to close that gap (`workflow_state` is `PROTECTED_FIELDS`-listed
regardless, so this endpoint was never at risk from it — but it's live drift
that could bite other code touching those columns).

Not yet done: the DocPerm-row question in §5.1, the `fund_received_ref`
protection call in §5.2 (implemented as protected — see `PROTECTED_FIELDS` in
`deposit_slip_common.py`), the Kafka re-publish question in §5.3 (not wired
up — a post-submit correction via this endpoint does **not** re-trigger
`publish_deposit_slip`), and all of §5.4/frontend wiring, which remains out of
scope per the original request.

## 1. Goal

Give `staff, RnD` a whitelisted endpoint, per deposit slip doctype, that can
correct field values on a deposit slip **after it is submitted / has reached
a locked workflow state**, writing **only the fields that actually changed**
— never a full-document overwrite.

## 2. Scope — the 7 deposit slip doctypes

| Doctype | Controller file | Lock mechanism today |
|---|---|---|
| `Deposit slip` | `doctype/deposit_slip/deposit_slip.py` | `is_submittable=1` → real `docstatus` lock |
| `Research Deposit Slip` | `doctype/research_deposit_slip/research_deposit_slip.py` | `workflow_state` (not submittable) |
| `T Testing Deposit Slip` | `doctype/t_testing_deposit_slip/t_testing_deposit_slip.py` | `workflow_state` |
| `D Consultancy Deposit Slip` | `doctype/d_consultancy_deposit_slip/d_consultancy_deposit_slip.py` | `workflow_state` |
| `Other Event Deposit Slip` | `doctype/other_event_deposit_slip/other_event_deposit_slip.py` | `workflow_state` |
| `E Non Routine Deposit Slip` | `doctype/e_non_routine_deposit_slip/e_non_routine_deposit_slip.py` | `workflow_state` |
| `Research Consultancy Deposit Slip` | `doctype/research_consultancy_deposit_slip/research_consultancy_deposit_slip.py` | `workflow_state` |

Only `Deposit slip` is a truly submittable doctype (`docstatus`), so it's the
only one where `doc.save()` throws Frappe's `UpdateAfterSubmitError` today.
The other six aren't submittable — `save_<doctype>(doc_data)` on those can
already silently overwrite a "locked" (terminal `workflow_state`) record,
because nothing currently enforces the lock at the field-write level. That's
a gap this plan closes for all seven, not just the docstatus one.

## 3. Current state (what exists already)

Every doctype already follows the same hand-written pattern (e.g.
[t_testing_deposit_slip.py:52-320](apps/rndopsapp/rndopsapp/rndopsapp/doctype/t_testing_deposit_slip/t_testing_deposit_slip.py#L52-L320)):

- `get_<doctype>_fields(doc_name=None)` — field metadata + prefill for the React form
- `save_<doctype>(doc_data)` — **full-form save**, `doc.save(ignore_permissions=True)`, no role check, no diffing
- `submit_<doctype>(docname)` — `doc.submit()`
- `get_<doctype>_workflow_actions` / `perform_<doctype>_workflow_action` — on the 5 workflow-driven doctypes only (not `Deposit slip` or `Research Deposit Slip`)

None of these check the caller's role beyond being logged in. There's a
separate, unrelated generic "Document Editor" admin tool
([api.py:1321-1520](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L1321-L1520),
docs in `DOCUMENT_EDIT_UI_DESIGN_PATTERN.md`) that can already diff-update
any Rndopsapp doctype via `frappe.db.set_value` — but it's an unrestricted
System Manager admin page, not staff-facing, so it's the wrong place to bolt
a role gate onto for this use case (per decision below, we're not reusing it).

There is **no Role named exactly "Staff"** in this app. The closest existing
role, already present in `Research Deposit Slip`'s permission table
([research_deposit_slip.json](apps/rndopsapp/rndopsapp/rndopsapp/doctype/research_deposit_slip/research_deposit_slip.json)),
is **`staff, RnD`** — also used as the gate in
[api.py:315](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L315)
(`create_research_project_and_approve`). This plan reuses that role rather
than introducing a new one.

## 4. Design

### 4.1 Shared helper module (new file)

`rndopsapp/rndopsapp/rndopsapp/deposit_slip_common.py` — mirrors the existing
shared-code convention already used for deposit slips
(`fund_deposits/common/child_tables.py`). Holds logic common to all 7
doctypes so it isn't duplicated 7 times:

```python
STAFF_ROLE = "staff, RnD"
BYPASS_ROLES = {STAFF_ROLE, "System Manager"}

PROTECTED_FIELDS = {
    "name", "owner", "creation", "modified", "modified_by", "doctype",
    "docstatus", "idx", "amended_from", "workflow_state", "workflow_action",
}

def ensure_staff_or_manager():
    roles = frappe.get_roles(frappe.session.user)
    if not BYPASS_ROLES & set(roles):
        frappe.throw(_("Only Staff (RnD) can edit this document after submission."),
                     frappe.PermissionError)

def apply_field_diff(doctype, docname, changes, valid_fieldnames):
    """Writes only fields present in `changes` whose value actually differs
    from the current DB value. Returns the list of fieldnames actually
    written (for the audit comment + response)."""
    ...

def apply_child_table_diff(doctype, docname, child_table_changes, table_fields_by_name):
    """Same {updated,inserted,deleted} shape as api.py's update_document_fields
    child-table handling, scoped to this doctype's own child tables."""
    ...

def log_post_submit_edit(doctype, docname, updated_fields, before, after):
    """doc.add_comment(...) audit trail — see §4.4."""
    ...
```

### 4.2 Per-doctype endpoint (added to each of the 7 `.py` files)

One new whitelisted function per doctype, next to the existing
`save_<doctype>` / `submit_<doctype>`:

```python
@frappe.whitelist()
def update_t_testing_deposit_slip_fields(docname, changes, child_table_changes=None):
    from rndopsapp.rndopsapp.deposit_slip_common import (
        ensure_staff_or_manager, apply_field_diff, apply_child_table_diff,
        log_post_submit_edit, PROTECTED_FIELDS,
    )
    ensure_staff_or_manager()

    doctype = "T Testing Deposit Slip"
    if not frappe.db.exists(doctype, docname):
        return {"status": "error", "message": f"'{docname}' not found."}

    changes = json.loads(changes) if isinstance(changes, str) else (changes or {})
    ...
    before = frappe.db.get_value(doctype, docname, list(changes.keys()), as_dict=True)
    updated = apply_field_diff(doctype, docname, changes, valid_fieldnames)
    ...  # child tables, then commit, then log_post_submit_edit
    return {"status": "success", "docname": docname, "updated_fields": updated}
```

Repeated identically for `deposit_slip.py`, `research_deposit_slip.py`,
`d_consultancy_deposit_slip.py`, `other_event_deposit_slip.py`,
`e_non_routine_deposit_slip.py`, `research_consultancy_deposit_slip.py`
— only the doctype name string and the doctype's own field/child-table list
differ; all diffing, protection, and audit logic lives in the shared module.

**Field allowlist per doctype** (derived from `frappe.get_meta(doctype)` at
call time, minus `PROTECTED_FIELDS` and minus Table/structural fieldtypes —
same `_valid_fieldnames_for`-style derivation already used in
[api.py:1027-1036](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L1027-L1036) —
so a bad/unknown fieldname in the payload is silently dropped, never turned
into a raw SQL column write).

**Child tables in scope**, keyed by doctype:

- All 7: `ecs_dates` / `ecs_date` → `Deposit Slip ECS Date`
- `Other Event`, `E Non Routine`, `Research Consultancy`: `credit_distribution` → `Deposit Slip Credit Distribution`
- `Other Event`, `E Non Routine`: `additional_project_credits` → `Deposit Slip Project Credit`
- `Research Deposit Slip`: `pdf_credit_distribution` → `PDF Credit Distribution`, `dpf_credit_distributions` → `DPF Credit Distribution`
- `D Consultancy`: `dpf_credit_distributions` → `DPF Credit Distribution`

### 4.3 Why `frappe.db.set_value`, not `doc.save()`

`doc.save()` on a submitted (`docstatus=1`) or `allow_on_submit`-less field
raises `UpdateAfterSubmitError`; none of the 30+ deposit-slip fields are
flagged `allow_on_submit` today, and marking them all as such would let
*any* role with write access edit them post-submit (see §5.1). Writing via
`frappe.db.set_value(doctype, docname, field, value, update_modified=False)`
bypasses that check at the ORM layer, which is exactly the pattern already
established in `api.py`'s `update_project_registration`
([api.py:1163-1220](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L1163-L1220))
and the generic Document Editor's `update_document_fields`
([api.py:1445-1523](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L1445)) — this
plan is the same technique, deliberately re-scoped and role-gated for
deposit slips specifically.

### 4.4 Audit trail

`frappe.db.set_value` does **not** create a Version log the way `doc.save()`
does, so a post-submit edit would otherwise be invisible. Add one comment per
edit call via `doc.add_comment("Comment", ...)` — the same primitive already
used by `add_project_comment`
([api.py:257-279](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L257-L279)) —
summarizing, per changed field: old value → new value, editor, timestamp.
This is a plain Comment (visible in the desk timeline), not a new doctype —
no schema change needed, so it's the cheapest option that still gives a
readable trail. (A dedicated log doctype is a possible phase 2 if the
business wants structured/queryable audit data; `Staff Activity Log` isn't a
fit as-is since its `action` field is a fixed Select of
`Submit/Approve/Forward/Reject`, not free-form field diffs.)

### 4.5 Response shape

Consistent across all 7 endpoints:

```json
{"status": "success", "docname": "...", "updated_fields": ["bank", "amount_inclusive_of_gst"], "modified": "...", "modified_by": "..."}
```

or on a no-op (payload matched current values / nothing allowed changed):

```json
{"status": "success", "docname": "...", "updated_fields": []}
```

## 5. Open items to confirm before/while implementing

1. **DocType-level permission rows.** Only `Research Deposit Slip` currently
   lists `staff, RnD` in its `permissions` table; the other 6 doctypes don't.
   The endpoint's role check is code-level (`frappe.get_roles`) and doesn't
   depend on the DocType permission table, but for desk-UI visibility (so
   staff can actually open the record to see what they just edited) a DocPerm
   row for `staff, RnD` with at least `read` should probably be added to the
   other 6 — confirm whether that's wanted or if `All_ProRnd_User` (already
   on all 7) already covers it.
2. **Which fields, if any, should stay protected beyond the system fields.**
   E.g. should `fund_received_ref` (the link back to Fund Received, which
   Kafka sync keys off of) be editable via this endpoint, or should it be
   added to `PROTECTED_FIELDS`? Recommend protecting it — changing it
   post-submit would desync the Kafka producer/consumer pairing in
   `kafka/producer/deposit_slip/` and `kafka/consumer/deposit_slip/`.
3. **Kafka re-sync on edit.** `on_update()` hooks in the 5 workflow-driven
   controllers (e.g.
   [t_testing_deposit_slip.py:29-49](apps/rndopsapp/rndopsapp/rndopsapp/doctype/t_testing_deposit_slip/t_testing_deposit_slip.py#L29-L49))
   fire `publish_deposit_slip` on `workflow_state` transitions or first
   submit — since `frappe.db.set_value` doesn't trigger `on_update`, a
   post-submit correction won't currently re-publish to Kafka. Confirm
   whether downstream consumers need the corrected values re-published; if
   yes, `log_post_submit_edit` should explicitly call
   `publish_deposit_slip(frappe.get_doc(doctype, docname))` after the diff
   is applied.
4. **Frontend call sites.** Out of scope for this plan (backend endpoints
   only, per the request), but the React deposit-slip forms will need an
   "Edit" affordance that's only shown/enabled when `staff, RnD` is among the
   logged-in user's roles (`get_user_roles` at
   [api.py:282-300](apps/rndopsapp/rndopsapp/rndopsapp/api.py#L282) already
   exists for the frontend to check this).

## 6. Testing

- Extend each doctype's existing `test_<doctype>.py`
  (currently placeholder `pass`, e.g.
  [test_deposit_slip.py](apps/rndopsapp/rndopsapp/rndopsapp/doctype/deposit_slip/test_deposit_slip.py))
  with cases: non-`staff, RnD` user → `PermissionError`; changing a field
  post-submit persists via `frappe.db.get_value`; unchanged fields in the
  payload produce an empty `updated_fields`; protected fields in the payload
  are silently dropped, not written; child-table insert/update/delete each
  round-trip correctly.
- Manual bench-console smoke test per doctype before wiring up the frontend.

## 7. Rollout order

Implement `deposit_slip_common.py` + wire it into `Deposit slip` first (the
one doctype with a real `docstatus` lock, so it's the sharpest test of the
`UpdateAfterSubmitError` bypass), verify end-to-end, then repeat the
7-line-per-file wiring across the remaining 6 doctypes — the shared module
means each subsequent doctype is a small, low-risk addition rather than a
fresh implementation.
