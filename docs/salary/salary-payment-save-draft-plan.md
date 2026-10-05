# Implementation Plan — "Save for Later" Draft Option in Salary Payment

## 1. Problem

A PI processing salary for a month may select many employees, edit per-employee
overrides (arrear, deductions, comments, remarks), but run out of time to click
**Submit** for all of them in one sitting. Today none of that in-progress state is
persisted anywhere:

- `selectedEmpIds` (checkbox selection) — pure React state, lost on refresh/tab close.
- `overrides` (per-employee `ta`, `otherDeduction`, `arrear`, `medicalDeduction`,
  `idCardCharge`, `electricityBill`, `comment`, `remarks`) — pure React state, lost.
- `preparedCycles` ("is this month prepared") — `localStorage`, browser-local only,
  doesn't survive a different machine/browser.

The only thing that *does* survive is `processedEmployees`, derived from the
`Salary Staging` doc — but that only reflects employees who were **already actually
paid** (Step 6 of the existing flow), not employees who were merely reviewed/edited
but not yet submitted.

**Goal:** let the PI click a "Save for Later" action that persists the current
in-progress batch (which employees are selected + their override edits) server-side,
so they — or a colleague on a different machine — can reopen the module later (same
day or the next) and resume exactly where they left off, without re-entering
deductions/arrears/comments for employees not yet paid.

## 2. Why not reuse the existing `Salary Staging` doctype

`Salary Staging` (`{YYYY}_{MMMM}` doc, single JSON field `salary_record`) is a
**post-submission audit trail** — records only land in it from `_append_salary_staging_record`
at Step 6 of `submit_payment_data`, tagged `status: "PENDING_PUBLISH"` etc. Two things
already read that array and assume every entry represents a real submission attempt:

- `_salary_staging_has_ps_emp_id` — the "already initiated this month, don't let the
  PI resubmit" duplicate-payment guard.
- `publish_salary_staging` — the admin recovery path that replays anything not yet
  `PUBLISHED`.

If unsent drafts were appended to the same array, the duplicate-guard would start
blocking real payment for employees who were only ever *edited*, never paid — a
serious correctness bug. Drafts need **their own, separate store**.

## 3. Data model — new doctype `Salary Payment Draft`

One row per `(salary_year_month, ps_emp_id)`, matching the pattern already used for
other lightweight custom doctypes in this app (e.g. `Kafka Commit Staging` —
`doctype/kafka_commit_staging/kafka_commit_staging.json`, `custom: 1`, no controller
`.py` needed).

```
doctype/salary_payment_draft/salary_payment_draft.json
doctype/salary_payment_draft/__init__.py
```

| Field | Type | Notes |
|---|---|---|
| `salary_year_month` | Data, reqd, in_list_view | e.g. `"2026_july"` — same key format as `Salary Staging` |
| `ps_emp_id` | Data, reqd, in_list_view | Project Staff employee id |
| `project_no` | Data, in_list_view | denormalized for easy filtering/search |
| `draft_payload` | Code (JSON), reqd | `{"selected": true, "overrides": {...EditableInputs}}` |
| `owner` | (standard Frappe field) | who saved it — used to scope drafts per PI |

**Naming:** `autoname: "format:{salary_year_month}-{ps_emp_id}"` — the name itself is
the composite key, so "save" is always an upsert (`frappe.get_doc` + update if the
name exists, else `frappe.new_doc` + insert) and no separate uniqueness constraint is
needed.

**No locking needed.** Unlike `Salary Staging`'s single-JSON-blob-per-month design
(which needs `GET_LOCK` because every submission does a read-modify-write on one
column), each draft is its own row — concurrent saves for different employees don't
contend, and a save for the same employee is just last-write-wins (acceptable: this is
editing convenience, not a financial record).

## 4. Backend — new endpoints in `commitPayment.py`

Add near the existing `_append_salary_staging_record` / `_salary_staging_has_ps_emp_id`
helpers (`commitPayment.py:186-220`):

### 4.1 `save_salary_draft_batch(salary_year_month, drafts)` — POST, `@frappe.whitelist()`

- `drafts` = JSON list: `[{"ps_emp_id": "...", "project_no": "...", "selected": true, "overrides": {...}}, ...]`
- For each entry: upsert a `Salary Payment Draft` row named
  `f"{salary_year_month}-{ps_emp_id}"` with `draft_payload = json.dumps({"selected":..., "overrides":...})`.
- Scope to the calling user — set/require `owner = frappe.session.user` so one PI's
  draft edits can't clobber another PI's for the same month (mirrors the existing
  `owner=PI` scoping already used to filter `Project Staff Details`, per
  `salary-module-full-flow.md` §4 row 1).
- Returns `{"status": "success", "saved": <count>}`.
- Fire a lightweight Mattermost notify (consistent with every other write path in this
  file) — but keep it low-volume (one line per batch, not per employee), since this
  will be called far more often than an actual payment submission.

### 4.2 `delete_salary_draft(salary_year_month, ps_emp_id)` — POST, `@frappe.whitelist()`

- Deletes the single draft row if it exists (no-op if not — idempotent).
- Called automatically by the frontend right after a successful `submit_payment_data`
  for that employee (so a paid employee's draft doesn't linger and confuse the next
  session), and manually if the PI clicks "discard draft" on a row.

### 4.3 Reads — no new endpoint needed

Frontend reads drafts with the standard generic REST list call, the same pattern
already used for `Project Staff Details` / `Project Registration` / `Salary Staging`
reads (`salary-module-full-flow.md` §4, rows 1-4):

```
GET /api/resource/Salary Payment Draft?filters=[["salary_year_month","=","2026_july"]]&fields=["ps_emp_id","project_no","draft_payload"]&limit_page_length=0
```

## 5. Frontend — `SalaryModule.tsx`

### 5.1 New state

```
draftLastSavedAt   — timestamp | null, shown as "Saved 5 min ago"
draftSaving        — bool, disables the Save button mid-request
```

### 5.2 Load drafts on mount / period change

Alongside the existing fetch that builds `processedEmployees` from `Salary Staging`
(§7 state map, `salary-module-full-flow.md`), add a fetch of
`Salary Payment Draft` filtered by the current `salary_year_month`:

- For each row: add `ps_emp_id` to `selectedEmpIds` if `draft_payload.selected`, and
  merge `draft_payload.overrides` into the `overrides[docName]` map.
- Do this **before** the PI starts editing, so it doesn't clobber in-progress edits on
  a background refresh.

### 5.3 "Save for Later" action

New button next to the existing pay/submit action (not inside the BMR modal — BMR
number isn't decided yet at draft-save time, and draft-saving shouldn't require it).

- On click: build `drafts` from the current `selectedEmpIds` × `overrides` (only the
  employees currently checked, with whatever overrides they have — defaults for the
  rest are fine, they get recomputed on load anyway).
- POST to `save_salary_draft_batch`.
- On success: set `draftLastSavedAt`, show a toast.

Deliberately **do not** store the derived/computed numbers (`proRataBasic`, `netPay`,
etc.) in the draft — only the raw `overrides` inputs. Eligibility and pay computation
(Step 4/`salary_payment_data`) always re-run fresh at actual submit time regardless
(`commitPayment.py` never trusts client-computed amounts as a source of truth for
eligibility, only for the final `payment_amount` at submission), so storing derived
numbers would just be a staleness risk (e.g. if `ps_basic_salary` changes between
save and resume) for no benefit.

### 5.4 Clear draft on successful payment

In Step 6's per-employee loop, immediately after a `submit_payment_data` call
succeeds for an employee, fire-and-forget `delete_salary_draft(salary_year_month, ps_emp_id)`
so that employee's draft doesn't reappear as "unsaved work" next time the module
loads for this month.

### 5.5 Optional UX polish (not required for v1)

- Small "Draft" badge on rows that have saved-but-unpaid overrides, with "Saved 2
  hours ago by <name>" from the doc's standard `owner`/`modified` fields.
- "Discard draft" per-row action calling `delete_salary_draft` directly.

## 6. Edge cases

| Case | Handling |
|---|---|
| Employee becomes ineligible between save and resume (recruitment un-approved, tenure ended) | No special handling needed — Step 4 (`salary_payment_data`) re-checks eligibility fresh at submit time regardless of draft contents; an ineligible employee just shows as Error/Skipped like today. |
| `Project Staff Details` record referenced by a draft is deleted/renamed | Guard the merge step: skip draft rows whose `ps_emp_id` no longer matches a loaded `StaffRecord`. |
| Two PIs' data colliding in the same month | Prevented by scoping draft rows to `owner = frappe.session.user`; each PI already only ever sees their own staff (`owner=PI` filter on `Project Staff Details`). |
| Draft saved, then that employee gets paid via a completely different session before this one resumes | §5.4's delete-on-success handles the normal path; if the draft still shows stale on reload, the mount-time fetch of `processedEmployees` (already existing) takes precedence — a `processedEmployees` employee should never be re-offered as "pending" even if a draft row for them still exists. |
| Very old orphaned drafts piling up | Not required for v1. Optional future cleanup: a scheduled patch deleting `Salary Payment Draft` rows older than e.g. 90 days. |

## 7. Rollout

1. **Backend:** add `doctype/salary_payment_draft/` (json + `__init__.py`, `custom: 1`,
   modeled on `doctype/kafka_commit_staging/`), plus `save_salary_draft_batch` and
   `delete_salary_draft` in `commitPayment.py`. No changes to `Salary Staging` or any
   existing endpoint.
2. **Frontend:** add the Save button, the mount-time draft fetch/merge, and the
   delete-on-success call in `SalaryModule.tsx`.
3. **QA:**
   - Select employees, edit overrides, Save, hard-refresh the page → selection and
     overrides restored.
   - Pay one of the drafted employees → their draft is removed; on next reload they
     show under Processed, not as a stale draft.
   - Two different browsers/users for the same month → confirm drafts don't bleed
     across `owner`.
   - Draft for an employee whose Recruitment record got un-approved after saving →
     confirm they surface as ineligible/Error on resume, not silently payable.

## 8. Out of scope for v1

- Auto-save (debounced save on every keystroke) — starting with an explicit button is
  simpler and avoids write amplification; can be added later if the explicit button
  proves annoying in practice.
- Cross-month draft carry-over — a draft is only ever valid for the `salary_year_month`
  it was saved under.
