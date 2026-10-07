# Project Staff Extension — Premature Term Rollover Bug & Fix

Status: code fix deployed, scheduled job registered, historical data corrected (2026-10-01).

Related: [STAFF_EXTENSION_TENURE_FEATURE.md](STAFF_EXTENSION_TENURE_FEATURE.md) (the original auto-tenure-computation feature this bug lived inside).

---

## 1. The Bug

### Symptom

For employee `2026TS0057`, the **current term** (as recorded on `Project Staff Details`) was due to complete on **2026-10-23**. The staff member applied for an extension in September 2026 — before the current term had ended. As soon as the extension reached the `Approved` workflow state (on 2026-09-25), the system immediately overwrote the employee's live term dates to the **new** term (`2026-10-29 → 2027-07-28`), even though the current term still had almost a month left to run.

Every other system that reads `Project Staff Details.ps_joining_date` / `ps_term_completion_date` directly (including the Salary Module) would therefore have shown the employee as already on their *new* term, weeks before the old one had actually finished.

### Root cause

**File:** `rndopsapp/rndopsapp/doctype/project_staff_extension/project_staff_extension.py`

- `perform_project_staff_extension_action()` called `doc.auto_create_tenure_record()` unconditionally the instant the workflow transitioned to `Approved` — no date comparison of any kind.
- Inside the old `auto_create_tenure_record()`, the new term dates were computed via `compute_new_tenure()` and written **synchronously, in the same request**, onto the parent `Project Staff Details` document:
  - A new row appended to the `table_ymed` ("Tenure Details") child table.
  - `parent_doc.ps_joining_date` / `parent_doc.ps_term_completion_date` overwritten to the new term.
  - `parent_doc.save()` committed immediately.
- There was no check anywhere comparing `today()` against the *current* term's completion date (`ex_date_of_expiry` on the extension doc) before applying the new term. The only date logic that existed (`_validate_application_window()`) governs **when staff are allowed to apply** for an extension (within the last month of their term) — it does not govern when an *already-approved* extension's new term is allowed to take effect.
- No scheduled task / staging mechanism existed anywhere in the app to defer this kind of "already approved, but shouldn't take effect yet" change (unlike, e.g., the Kafka Commit Staging pattern used for payment commits).

### Why this matters

The application window is intentionally the **last month before term completion** (`APPLICATION_WINDOW_MONTHS = 1`), which means *every* extension filed within that normal window and approved promptly would hit this bug — the new term would go live before the old one ended, as long as approval happened even one day before the old `ex_date_of_expiry`.

---

## 2. The Fix

### Design principle

An approval decision and its real-world effective date are two different things:
- **At `Approved`**: the new term's dates/salary are final and should be locked in immediately, visible on the extension document itself, so nothing about the decision is lost or has to be recomputed later.
- **On `Project Staff Details`** (the live record everything else reads): the new term must not appear until the *current* term has actually finished.

### Code changes

**File:** `rndopsapp/rndopsapp/doctype/project_staff_extension/project_staff_extension.py`

1. **`auto_create_tenure_record()`** (line 188) — now does two things, split apart:
   - Always (regardless of date): computes the new tenure preview, validates the period cap, and locks `ex_computed_new_joining_date`, `ex_computed_new_completion_date`, `ex_current_basic`, `ex_final_new_joining_date`, `ex_final_new_completion_date` onto the extension document via `db_set`.
   - Then compares `today()` against `ex_date_of_expiry` (the current term's completion date, captured on the extension doc before this extension's own rollover happens):
     - If the current term **hasn't ended yet** → stops here. `Project Staff Details` is **not touched**. A blue alert (`frappe.msgprint`) tells the approver the new term will apply automatically once the current term ends.
     - If the current term **has already ended** (or there's no date to compare) → calls `_apply_tenure_to_project_staff_details()` immediately, preserving the original behavior for the (common) case where approval genuinely happens after term end.
   - Guarded by `self.tenure_row_created` at the top — idempotency: this can never append a duplicate tenure row, even if called twice.

2. **`_apply_tenure_to_project_staff_details()`** (line 251) — new method, extracted from the old `auto_create_tenure_record()` body. Does the actual write: appends the new `table_ymed` row, updates `parent_doc.ps_joining_date` / `ps_term_completion_date` / `ps_basic_salary` / `scr_id`, saves the parent, and sets `tenure_row_created = 1` on the extension doc. Only ever called once per extension (same idempotency guard).

3. **`apply_pending_project_staff_extensions()`** (line 294) — new module-level function, the daily scheduled job. Finds every `Project Staff Extension` where:
   - `workflow_state = "Approved"`
   - `tenure_row_created = 0`
   - `ex_date_of_expiry <= today()`
   - `ex_final_new_joining_date` / `ex_final_new_completion_date` are set

   For each match, calls `doc._apply_tenure_to_project_staff_details(...)` with the already-locked final dates/salary, commits, and logs+rolls back individually on error (`"Project Staff Extension Rollover Error"` in the Error Log) so one bad record can't block the rest of the batch.

**File:** `hooks.py`

```python
scheduler_events = {
    "daily": [
        "rndopsapp.rndopsapp.api.auto_clear_old_mattermost_posts",
        "rndopsapp.rndopsapp.doctype.project_staff_extension.project_staff_extension.apply_pending_project_staff_extensions",
    ],
    ...
}
```

Registered under `daily` — Frappe's scheduler runs this once every 24 hours.

### Reused field — no schema change needed

`tenure_row_created` (Check, hidden, read-only, default `0`) already existed on the `Project Staff Extension` doctype but was **completely unused** by the old code — it was dead weight left over from an earlier iteration. It's now repurposed as the idempotency / "has this been rolled over yet" flag, so no `bench migrate` / schema change was required for the fix itself.

---

## 3. Historical Data Correction (2026-10-01)

Because the old code always applied the new term immediately, every `Approved` `Project Staff Extension` in the system had `tenure_row_created = 0` even though most of them had, in fact, already been correctly rolled onto `Project Staff Details` (because they happened to be approved *after* their current term had already ended — the bug only bites when approval happens *before* term end).

### Audit

Compared each `Approved` extension's approval timestamp against its own `ex_date_of_expiry` (the current term's end date at time of filing):

| Extension | Employee | Approved | Current term ended | Premature? |
|---|---|---|---|---|
| `lm91io4tjt` | 2026TS0049 | 2026-08-28 | 2026-09-08 | **Yes** |
| `hr2jisqcks` | 2026TS0048 | 2026-09-09 | 2026-09-24 | **Yes** |
| `41ep0jup0h` | 2026TS0057 | 2026-09-25 | 2026-10-23 | **Yes** |
| 13 others (`ves0lu7t1t`, `qonnua77a5`, `ue6f4ik3ln`, `4fifvrssfa`, `quos2fkrrt`, `vdstf9jpkq`, `3ds2pdo8pj`, `rm3s3n0qab`, `csjgem1nkq`, `uumpeoltgc`, `oulokupnhj`, `ac7m1fv2ip`, `927odsfhvu`) | various | — | approved after term end | No — already correctly applied |

### Correction performed

Via a one-off script (`temp_fix_premature_extensions.py`, deleted after use — see §5):

1. For the 3 premature extensions, on their linked `Project Staff Details` record:
   - Removed the premature `table_ymed` tenure row.
   - Reverted `ps_joining_date` / `ps_term_completion_date` / `ps_basic_salary` back to the previous (still-current) tenure row's values.
   - Set `tenure_row_created = 0` on the extension doc, so `apply_pending_project_staff_extensions()` will correctly re-apply it once the current term's end date actually arrives.

   | Employee | Reverted to |
   |---|---|
   | 2026TS0057 | `2024-12-22 → 2026-10-23`, basic ₹28,500 |
   | 2026TS0049 | `2026-03-09 → 2026-09-08`, basic ₹35,000 |
   | 2026TS0048 | `2026-03-25 → 2026-09-24`, basic ₹56,000 |

2. For the other 13 already-correctly-applied extensions, set `tenure_row_created = 1` so the new scheduled job never attempts to touch them again (would otherwise have mistaken them for "pending" and tried to re-append tenure rows).

### Verified post-correction (2026-10-01)

```
Project Staff Details (08s46fqku7 / 2026TS0057): ps_joining_date=2024-12-22, ps_term_completion_date=2026-10-23
Project Staff Extension (41ep0jup0h): tenure_row_created=0, ex_final_new_joining_date=2026-10-29, ex_final_new_completion_date=2027-07-28
```
New term is locked on the extension document and will apply automatically — nothing was lost.

### Known data anomaly — NOT fixed, flagged only

`qonnua77a5` (employee `2026TS0050`) has a corrupted `ex_date_of_expiry` of `0206-09-09` (year `0206` instead of `2026`), with matching garbage in `ex_final_new_joining_date` / `ex_final_new_completion_date` (`0207-02-09`). This is an unrelated pre-existing data-entry bug, not caused by or related to the rollover issue. It was deliberately left untouched (included only in the "flag as already applied" group so the new scheduler ignores it) because the correct intended date can't be inferred with confidence. **Needs separate investigation.**

---

## 4. What Happens Going Forward

For any `Project Staff Extension` approved from now on:

1. **At Approval**: new term dates/salary computed and locked on the extension doc immediately (visible right away). `Project Staff Details` updated immediately **only if** the current term has already ended as of the approval date.
2. **If the current term is still running**: nothing on `Project Staff Details` changes. The approver sees a blue notice explaining the new term will apply automatically once the current term ends.
3. **Daily**, Frappe's scheduler runs `apply_pending_project_staff_extensions()`, which finds any extension whose current term's end date (`ex_date_of_expiry`) has now arrived and applies the (already-locked) new term to `Project Staff Details` at that point — append tenure row, update top-level joining/completion dates and salary, mark `tenure_row_created = 1`.

For `2026TS0057` specifically: the new term (`2026-10-29 → 2027-07-28`) will go live automatically on/shortly after **2026-10-23**, with no manual action required — provided the site's scheduler is enabled (see §6).

---

## 5. Cleanup

- `apps/rndopsapp/rndopsapp/rndopsapp/temp_fix_premature_extensions.py` — the one-off correction script. **Should be deleted** once confirmed no longer needed; it was never meant to be permanent application code.

---

## 6. Open Follow-ups

- [ ] Confirm Frappe's scheduler is actually enabled on `prornd.local` (`bench --site prornd.local scheduler status`) — the daily job does nothing if the scheduler isn't running.
- [ ] Investigate and correct the corrupted dates on `qonnua77a5` (2026TS0050) separately.
- [ ] Delete `temp_fix_premature_extensions.py` once the fix is confirmed stable.
- [ ] Consider whether `apply_pending_project_staff_extensions()` should also notify the employee/HR by email when a deferred rollover is finally applied (no notification currently fires — mirrors the general pattern noted in other module manuals, e.g. Temporary Advance, where most stages have no email alert).
