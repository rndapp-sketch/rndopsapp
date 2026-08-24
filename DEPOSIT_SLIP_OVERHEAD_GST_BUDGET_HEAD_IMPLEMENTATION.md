
# Deposit Slip — Overhead / GST Budget Head Enforcement

**Document:** DEPOSIT_SLIP_OVERHEAD_GST_BUDGET_HEAD_IMPLEMENTATION
**Scope:** Research Deposit Slip · Research Consultancy Deposit Slip · D Consultancy Deposit Slip · E Non Routine Deposit Slip · T Testing Deposit Slip · Other Event Deposit Slip
**Related docs:** [commit_kafka_publish_doc_priyam.md](commit_kafka_publish_doc_priyam.md), [KAFKA_COMMIT_FRONTEND.md](KAFKA_COMMIT_FRONTEND.md)

---

## 1. Problem Statement

Today, when a Fund Received document is approved and a Deposit Slip is generated against it, the Deposit Slip's `overhead_amount` (or `total_overhead_amount`) and GST amount (`total_gst` / `gst_final`) are pure calculated numbers. Nothing ties them back to an actual **Budget Head** allocation on the Fund Received's `received_amt_breakup` table. This means:

- The accounts system can receive a Deposit Slip whose Overhead/GST money was never actually earmarked against any budget head on the Fund Received side.
- There is no way to guarantee the Deposit Slip's overhead/GST figures reconcile with what Fund Received actually allocated.

This document specifies how to close that gap:

1. Block deposit-slip submission if Overhead/GST money exists but no matching budget head is allocated on the Fund Received.
2. Let the user allocate it interactively (modal), update Fund Received's budget breakup, and **republish Fund Received to Kafka** so Accounts sees the new allocation.
3. Re-validate that the Deposit Slip's Overhead/GST figures match the (now updated) Fund Received allocation before allowing the Deposit Slip itself to be published to Kafka.

---

## 2. Grounding — Existing Data Model (verified in code)

### 2.1 Fund Received budget breakup

- `Fund Received.received_amt_breakup` → child table doctype **`Project Received Budget`**
  ([project_received_budget.json](rndopsapp/rndopsapp/doctype/project_received_budget/project_received_budget.json)):
  | Field | Type | Notes |
  |---|---|---|
  | `account_head` | Link → `Budget Head` | |
  | `amount_received` | Currency | |
  | `remarks` | Small Text | |
  | `budget_year_funds_receive` | (int, default 1) | present in frontend payload, not shown above but handled by `update_fund_received` |

- **`Budget Head`** doctype ([budget_head.json](rndopsapp/rndopsapp/doctype/budget_head/budget_head.json)):
  | Field | Type |
  |---|---|
  | `budget_head` | Data (display label, e.g. "Overhead", "GST", "Manpower") |
  | `id` | Int (external accounts-system account head id) |
  | `specify_the_budget_head` | Data |

  `name` is an internal autoname/hash (see `add_budget_head` in [budget_head.py](rndopsapp/rndopsapp/doctype/budget_head/budget_head.py)) — **never assume `name == "Overhead"`**. Always resolve by the `budget_head` label field, case-insensitively. `rndopsapp/rndopsapp/kafka/utils.py::get_budget_head_id()` already implements this name→id resolution pattern; reuse it.

### 2.2 Fund Received → Kafka payload already carries the breakup

[kafka/producer/fund_received/mapper.py](rndopsapp/rndopsapp/kafka/producer/fund_received/mapper.py) `map_budget_breakups()` maps every `received_amt_breakup` row into `FundBudgetBreakupDTO{accountHeadId, amount, remarks}` inside `fundBudgetBreakupList`. **This means simply updating `received_amt_breakup` and calling `publish_fund_received(doc)` again is sufficient to push the new allocation to Accounts** — no DTO/mapper changes needed for the breakup itself.

**One field does need a small, targeted change: `fundReceivedStatus`.** [dto.py:50](rndopsapp/rndopsapp/kafka/producer/fund_received/dto.py#L50) defaults it to `"PENDING_APPROVAL"`, and [mapper.py:217](rndopsapp/rndopsapp/kafka/producer/fund_received/mapper.py#L217) `map_to_dto()` **hardcodes the literal `"PENDING_APPROVAL"` unconditionally** — it never reads `doc.workflow_state`. That happens to be correct today because the only existing call site (`perform_fund_received_action`, `next_state == "PENDING_APPROVAL"`) matches it by coincidence.

The new `allocate_deposit_slip_budget_heads` (§5.1) republishes **after** the Fund Received has already reached `"Approved"` (deposit slips are only ever filled post-approval), so that call must send `fundReceivedStatus = "APPROVED"`. Rather than deriving this generically from `doc.workflow_state` (the exact accounts-side enum vocabulary for every intermediate Frappe state like `"Pending HoS Approval"` isn't confirmed — see §7.5), thread an **explicit override** through the publish call so each call site states its own intent and the existing call site's behavior is untouched:

- `FundReceivedMapper.map_to_dto(doc, fund_received_status: str | None = None)` → uses `fund_received_status or "PENDING_APPROVAL"` instead of the hardcoded literal.
- `FundReceivedMapper.map_to_event(doc, fund_received_status: str | None = None)` → passes it through to `map_to_dto`.
- `FundReceivedProducer.publish(doc, validate=True, log_errors=True, fund_received_status: str | None = None)` → passes it through to `map_to_event`.
- Module-level `publish_fund_received(doc, validate=True, log_errors=True, fund_received_status: str | None = None)` ([producer.py:262](rndopsapp/rndopsapp/kafka/producer/fund_received/producer.py#L262)) → passes it through.
- `allocate_deposit_slip_budget_heads` calls `publish_fund_received(doc, fund_received_status="APPROVED")`.
- The existing call in `perform_fund_received_action` (~line 902) stays exactly as `publish_fund_received(doc)` — no argument, so it keeps defaulting to `"PENDING_APPROVAL"`, unchanged.

### 2.3 Deposit Slip overhead/GST fields (per doctype — verified via each `.json`)

| Doctype | Overhead field | GST field(s) | Notes |
|---|---|---|---|
| Research Deposit Slip | `overhead_amount` | — | **No GST concept** — skip GST check entirely for this type |
| Research Consultancy Deposit Slip | `overhead_amount` | `total_gst` | |
| D Consultancy Deposit Slip | `total_overhead_amount` | `total_gst` | Also has `total_overhead_institute_share` (overhead + institute share) — see [§7 open question](#7-open-questions--decisions-needed) |
| E Non Routine Deposit Slip | `overhead_amount` | `total_gst` | |
| T Testing Deposit Slip | `overhead_amount` | `total_gst` | |
| Other Event Deposit Slip | `overhead_amount` | `gst_final` | |

**None of the 6 doctypes currently has a Link field to `Budget Head` for overhead or GST.** New fields are required (§4).

### 2.4 Where Deposit Slip currently reaches Kafka

Two independent trigger points publish a Deposit Slip today — both must be gated by the new validation:

1. **`fund_received.py::perform_fund_received_action`**, when the Fund Received transitions to `"Approved"` (~line 952–1093): it locates the linked Deposit Slip, force-sets `workflow_state = "Approved"`, submits it with `flags.skip_kafka_sync = True`, then explicitly calls `publish_deposit_slip(ds_doc)`. **This is the primary/live path** (the standalone `/deposit-slip-new` and `/deposit-slip/:name` routes and their `get_*_workflow_actions`/`perform_*_workflow_action` methods referenced in `DepositSlipForm.tsx` are not implemented in the backend today for `research_deposit_slip.py` — verify per-doctype before relying on them).
2. Each Deposit Slip doctype's own `on_update()` hook (e.g. `research_deposit_slip.py::ResearchDepositSlip.on_update`), guarded by `self.flags.get('skip_kafka_sync')`, fires if `workflow_state` flips to `Approved/Verified/Submitted` or on first submit **outside** of path 1.

### 2.5 Where the deposit-slip form is actually filled

`FundReceivedDetails.tsx` — not the standalone `DepositSlipForm.tsx` — is the live UI. It:
- Lets staff pick a type and fills/calculates `overhead_amount`/`total_gst` etc. client-side.
- Already has an editable `received_amt_breakup` UI (`editBreakup` state, `handleSaveEdits` → `update_fund_received`).
- Bundles `deposit_slip_data` + `deposit_slip_type` into `handleBeforeAction`, which is passed as `onBeforeAction` to the workflow-action button component (same prop pattern as `LoanRequestActionButtons.tsx`) and fires right before `perform_fund_received_action` is called for "Forward"/"Generate Deposit Slip".

`update_fund_received` (fund_received.py, ~line 1539) already fully replaces `received_amt_breakup` from a JSON payload, resolving Budget Head labels → doc names — but **it does not currently republish to Kafka**. That call must be added (§5.3).

---

## 3. Functional Spec

### 3.1 Pre-submission check (client-side, in `FundReceivedDetails.tsx`)

Immediately before the deposit-slip "Save"/"Forward"/"Generate Deposit Slip" action is allowed to proceed (i.e. at the top of `handleBeforeAction`, before it currently returns `{ deposit_slip_data, deposit_slip_type }`):

1. Read the current deposit slip's computed overhead figure (`overhead_amount` or `total_overhead_amount` per type) and GST figure (`total_gst` / `gst_final`, absent for `research_deposit_slip`).
2. Resolve, from `fundData.received_amt_breakup`, whether a row exists whose `account_head` resolves (via `Budget Head.budget_head`, case-insensitive) to `"Overhead"` with `amount_received > 0`, and similarly for `"GST"` — call these `frOverheadFunded` / `frGstFunded` (booleans).
3. For overhead, and separately for GST, there are exactly three outcomes — **only one of them opens the modal**:

   | FR head funded? | DS figure > 0? | Outcome |
   |---|---|---|
   | No | No | **Allow** — nothing to reconcile (§ zero-value edge case below). |
   | No | Yes | **Open the transfer modal** (§3.3) — DS wants money that isn't backed by a Fund Received head yet. |
   | **Yes** | **No** | **Block immediately — no modal.** Fund Received already has money set aside (e.g. Overhead ₹500) but this deposit slip isn't accounting for it (shows ₹0). There's nothing to "add fund" for here — the fix is on the deposit-slip side, not the Fund Received side, so don't offer the transfer modal. Show a plain blocking error instead, e.g. *"Fund Received has ₹500 allocated to Overhead, but this deposit slip shows ₹0 overhead. Correct the deposit slip amount before submitting."* Abort the action the same way (`handleBeforeAction` returns `null`). |
   | Yes | Yes | **Allow through to the amount-match check.** Both sides have something — whether they actually *match* is enforced by §3.4's reconciliation, which (see note below) is now also invoked at this same immediate point, not only at the later Kafka-publish gate. |

4. If both overhead and GST land in the top row (nothing funded, nothing required) → proceed exactly as today, no behavior change.

**Zero-value edge case**: as above — if the deposit slip's overhead figure is 0 **and** its GST figure is 0 (or absent for `research_deposit_slip`), this whole check is skipped and the action proceeds — **even if `received_amt_breakup` is completely empty**. This flow only ever gates on there being actual overhead/GST *money* to reconcile on at least one side; it must never require Fund Received to already have budget-head rows just because none happen to exist yet.

**Immediate, not just at final approval**: the "Yes/No" and "Yes/Yes" rows above must be enforced **right here, at Save/Forward time**, not only at the later Kafka-publish gate described in §3.4. Concretely: the same `validate_overhead_gst_budget_heads` helper (§5.2) is called from **two** places now — this immediate submission point (server-side, inside `perform_fund_received_action`'s `"Pending HoS Approval"` branch, right alongside `create_deposit_slip_from_data` — not just client-side JS, since that can be bypassed) and the pre-existing final gate at the `"Approved"` transition (kept as a defense-in-depth backstop, not the only enforcement point anymore). See §5.2 for how the same helper works against both a not-yet-saved `deposit_slip_data` payload and a saved Deposit Slip doc.

This is independent from a separate, unconditional rule: **whatever budget heads *do* exist on the Fund Received (whether or not overhead/GST triggered anything) must also end up on the Deposit Slip** — see §3.2 below.

(Note this whole check is also independent of the pre-existing, unrelated `hasMissingRequired`/`budgetBreakup: !(received_amt_breakup?.length > 0)` guard already in `FundReceivedDetails.tsx` for the Approved-state view — that guard is untouched by this feature and continues to apply on its own terms.)

### 3.2 Deposit Slip carries a full copy of the Fund Received budget breakup

Separately from the Overhead/GST-specific source-head fields (§4), **the complete `received_amt_breakup` list — every head, not just Overhead/GST — must be mirrored onto the Deposit Slip**, so the Deposit Slip is a self-contained record of what it was funded against. This applies unconditionally: whether or not the overhead/GST check in §3.1 fired, if Fund Received has budget-head rows, the Deposit Slip must have them too.

- New Table field on all 6 Deposit Slip doctypes: `fund_budget_breakup`, reusing the **existing** child doctype `Project Received Budget` (`account_head` / `amount_received` / `remarks`) rather than defining a new one — it's already `istable: 1` and Frappe supports one child doctype being referenced by Table fields on multiple parents.
- Populated (full replace, not merge) at two points:
  1. **Deposit Slip creation** — `create_deposit_slip_from_data` (fund_received.py) copies `fund_received_doc.received_amt_breakup` row-for-row into `new_doc.fund_budget_breakup` at the same time it sets `fund_received_ref`.
  2. **After any `allocate_deposit_slip_budget_heads` transfer** (§5.1) — since that call changes the Fund Received's breakup (e.g. Recurring 2,000 → 1,500, Overhead 0 → 500), it must re-copy the now-updated `received_amt_breakup` onto the linked Deposit Slip's `fund_budget_breakup` in the same transaction, so the two never drift out of sync.

### 3.3 Modal Flow — `MissingBudgetHeadModal`

**Step A — Notice.**
Message text is conditional on what's missing:
- Only overhead missing: *"No budget head has been allotted money for Overhead. ₹{overhead_amount} must be allocated to an Overhead budget head before this deposit slip can be submitted."*
- Only GST missing: same wording for GST.
- Both missing: *"No budget head has been allotted money for Overhead or GST. Both must be allocated before this deposit slip can be submitted."*

Buttons: **Add Fund** (continue) / **Cancel** (abort — deposit slip action does not fire).

**Step B — Allocation form** (shown after "Add Fund"):

This is a **reallocation (transfer), not new money**. The Overhead/GST amount does not appear out of nowhere — it is moved out of an *existing* budget head on the same Fund Received. The total across `received_amt_breakup` (and therefore `fund_received_amt`) must stay unchanged before/after. Every row not involved in the transfer is left completely untouched.

- Render **one row per missing item** (1 or 2 rows, independent of each other): one for Overhead if `overheadMissing`, one for GST if `gstMissing`.
- Each row is a **"deduct from" selector**, not a destination selector — the destination is fixed (the "Overhead" / "GST" budget head respectively). What the user picks is which *existing* Fund Received budget head to deduct the required amount from:
  - Source Budget Head dropdown, populated **only from the heads already present in this Fund Received's `received_amt_breakup`** (not the full global Budget Head list) — e.g. Consultancy, Manpower, Recurring — each option showing its current `amount_received` (e.g. "Recurring — ₹2,000") so the user can see what's available before picking.
  - A read-only "Required amount" showing the deposit slip's figure (`overhead_amount`/`total_overhead_amount` for the Overhead row, `total_gst`/`gst_final` for the GST row) — this is fixed, not user-editable (it must exactly equal what's being moved, since §3.4 will later check the destination head's total against this same figure).
  - **When the source head selection changes**, re-fetch/display that head's current `amount_received` and re-validate against the required amount (don't leave a stale "insufficient balance" message from the previously selected head).
- **Validation**: the selected source head's `amount_received` must be `>=` the required amount for that row. If not, show inline error and disable "Continue" for that row (e.g. "Recurring only has ₹300 available; ₹500 is required for Overhead — pick a different head or reduce spend elsewhere first").
- The two rows (Overhead source, GST source) are fully independent — the user may pick the **same** source head for both (it will be debited twice, once per row) or two **different** source heads.

**Worked example** (Overhead only missing, amount required = ₹500, user picks "Recurring" as the source):

| Budget Head | Before | After |
|---|---|---|
| Consultancy | 1,000 | 1,000 (untouched) |
| Manpower | 1,000 | 1,000 (untouched) |
| Recurring | 2,000 | **1,500** (debited by 500) |
| Overhead | *(row did not exist)* | **500** (new row created) |
| **Total** | **4,000** | **4,000** (unchanged — `fund_received_amt` is not touched) |

If GST were also missing (say ₹200, sourced from Manpower), Manpower would drop to 800 and a new GST row of 200 would be added alongside the above, with the total still conserved at 4,000.

**Step C — Confirmation (second, distinct dialog).**
Before calling the backend: *"This will update the Fund Received budget breakup and republish it to Kafka. If Fund Received is not updated first, this Deposit Slip cannot be consumed on the Accounts side. Continue?"* — **Yes** / **Cancel**.

This is a deliberate second confirmation, separate from Step A/B, because it is the point of no return that touches Fund Received's Kafka state.

**Step D — Commit.**
On **Yes**: call the new backend endpoint (§5.1) with `{ docname: fundReceivedName, transfers: [{ source_head, amount, purpose: "OVERHEAD" | "GST" }, ...] }` — `source_head` is the budget head to debit; the credited (destination) head is implied by `purpose`. This same call also re-syncs the linked Deposit Slip's `fund_budget_breakup` mirror (§3.2).

- **Success** (breakup updated AND Kafka republish succeeded): close modal, resume the original blocked deposit-slip action (call through to the existing `perform_fund_received_action`/save flow) automatically — no need for the user to click "Forward" again.
- **Partial failure** (breakup updated, Kafka republish failed): show a blocking error — *"Fund Received budget breakup was updated but Kafka publish failed: {error}. The Deposit Slip cannot be submitted until this succeeds — click Retry."* Provide a **Retry** button that re-calls the same endpoint (idempotent — see §5.1 design) instead of re-doing the whole allocation. Do **not** allow the deposit-slip action to proceed.
- **Failure** (breakup update itself failed): show error, keep modal open at Step B so the user can retry without re-entering everything.

### 3.4 Final gate — Deposit Slip vs Fund Received reconciliation (backend, enforced server-side)

**This is now a backstop, not the primary enforcement point** — the same check already ran immediately at submission time (§3.1's "Immediate, not just at final approval" note, §5.2 point 1). It's kept here too in case Fund Received or Deposit Slip data is hand-edited via Desk between submission and HoS approval. Independent of §3.1/3.3, before the Deposit Slip is actually allowed to move to `Approved`/be published:

- `overhead_amount` (or `total_overhead_amount`) on the Deposit Slip must equal the amount allocated to the Overhead-labelled head(s) in the Fund Received's `received_amt_breakup` (within a currency rounding tolerance — recommend `0.01`) — this also covers the "head funded, deposit slip shows 0" case (§3.1's Yes/No row), since 0 vs. any funded amount is just a specific case of mismatch.
- `total_gst`/`gst_final` must equal the amount allocated to the GST-labelled head(s), same tolerance. Skipped entirely for `Research Deposit Slip` (no GST field).
- On mismatch: **do not submit/approve/publish** — surface a clear error naming both figures, e.g. *"Deposit Slip overhead (₹50,000) does not match the Overhead budget head allocation on Fund Received (₹45,000). Update the allocation and try again."*
- Only once this passes does the existing `publish_deposit_slip(ds_doc)` call in `perform_fund_received_action` (and the equivalent in each doctype's `on_update`) execute.

---

## 4. Doctype Changes

Add to **each** of the 6 Deposit Slip doctypes (`research_deposit_slip.json`, `research_consultancy_deposit_slip.json`, `d_consultancy_deposit_slip.json`, `e_non_routine_deposit_slip.json`, `t_testing_deposit_slip.json`, `other_event_deposit_slip.json`) — two new fields, placed near their respective totals section:

| Fieldname | Fieldtype | Options | Notes |
|---|---|---|---|
| `overhead_source_head` | Link | `Budget Head` | The FR budget head the overhead amount was transferred **from** (§3.3). Present on all 6 doctypes. |
| `gst_source_head` | Link | `Budget Head` | The FR budget head the GST amount was transferred **from**. Omit from `Research Deposit Slip` (no GST field to back). |
| `fund_budget_breakup` | Table | `Project Received Budget` (reused) | Full mirror of the Fund Received's `received_amt_breakup` at the time the Deposit Slip was created / last transferred — see §3.2. |

`overhead_source_head`/`gst_source_head` are **read-only, informational mirrors** of what the user selected in the modal (§3.3) — they record *which existing head the money was moved out of*, for audit/traceability on the Deposit Slip itself (the destination is always the fixed "Overhead"/"GST" head, so it doesn't need its own field). The actual money lives on `Fund Received.received_amt_breakup`; these fields are not additive amount stores.

No changes needed to `Budget Head` or `Project Received Budget` — both already support this use case as-is.

---

## 5. Backend Changes

### 5.1 New whitelisted method: `allocate_deposit_slip_budget_heads`

Location: `rndopsapp/rndopsapp/doctype/fund_received/fund_received.py` (co-locate with `update_fund_received`, which it wraps/extends).

This performs a **transfer within the existing breakup** — debit a source head, credit the Overhead/GST head — never adds money on top and never touches rows not named in `transfers`. Worked example: §3.3. It must also re-sync the linked Deposit Slip's `fund_budget_breakup` mirror (§3.2, §4) in the same call.

```python
@frappe.whitelist()
def allocate_deposit_slip_budget_heads(docname, transfers):
    """
    transfers: JSON list of {"source_head": "<Budget Head name or label>",
                              "amount": <float>,
                              "purpose": "OVERHEAD" | "GST"}
    purpose fixes the destination label ("Overhead" / "GST" — see §7.2 for
    the exact label constants).

    doc = frappe.get_doc("Fund Received", docname)
    original_total = sum(row.amount_received for row in doc.received_amt_breakup)

    For each transfer, in order:
      1. Resolve `source_head` to a Budget Head doc name (name match, then
         `budget_head` label match — reuse get_budget_head_id()'s resolution
         logic, or a shared helper).
      2. Find the existing `received_amt_breakup` row for that resolved head.
         frappe.throw if not found (source must already exist — this is a
         transfer, not fresh money) or if its `amount_received` < `amount`
         (insufficient balance — re-validates what the client already
         checked, since the client's view may be stale).
      3. Decrement that row's `amount_received` by `amount`. Leave the row
         in place even if it reaches 0 (keeps an audit trail of which head
         used to hold the money — do not delete the row).
      4. Resolve the destination label for `purpose` ("Overhead" or "GST").
         If a `received_amt_breakup` row for that head already exists,
         INCREMENT its `amount_received` by `amount`. Otherwise APPEND a new
         row {account_head, amount_received: amount,
         remarks: f"Allocated from {source_head} for {purpose} on Deposit Slip"}.

    Sanity check (must hold, else frappe.throw before saving — this is a
    hard invariant, not a warning):
      assert sum(row.amount_received for row in doc.received_amt_breakup) == original_total

    Then:
      - doc.save(ignore_permissions=True); preserve workflow_state (same
        pattern as update_fund_received's save block). Since this method
        only ever runs after the Fund Received has already reached
        "Approved" (deposit slips are only filled post-approval), workflow
        state is expected to already be "Approved" and is left as-is.
      - Re-sync the mirror (§3.2, §4): find the linked Deposit Slip via
        `fund_received_ref` (same doctype-search pattern as
        get_linked_deposit_slip / perform_fund_received_action's Approved
        block), replace its `fund_budget_breakup` child table wholesale with
        the doc's now-updated `received_amt_breakup` rows, save it too
        (flags.ignore_validate = True, no workflow_state change here).
      - frappe.db.commit()
      - Republish to Kafka with the status forced to APPROVED for this call
        site specifically (see §7.5 — do NOT rely on the mapper's default):
            from rndopsapp.rndopsapp.kafka.producer import publish_fund_received
            result = publish_fund_received(doc, fund_received_status="APPROVED")
      - Return {"status": "success", "kafka_published": True} or
        {"status": "success", "kafka_published": False, "error": "..."}
        (breakup IS committed either way — Kafka failure is reported
        separately so the frontend can show the Retry flow in §3.3 Step D
        without re-doing the transfer a second time; a retry call must be
        able to tell the transfer already happened — e.g. by re-deriving
        "is there already an Overhead/GST row big enough to satisfy this
        purpose" — and, if so, skip straight to re-calling
        publish_fund_received instead of transferring again).
    """
```

Why a **new** endpoint rather than reusing `update_fund_received` directly: `update_fund_received` replaces the *entire* `received_amt_breakup` table from whatever the caller sends, and has no Kafka republish, and knows nothing about the linked Deposit Slip's mirror table. Overloading it risks accidentally dropping unrelated breakup rows the frontend didn't happen to have loaded, and mixes concerns. A small dedicated transfer method is safer, keeps the conservation invariant enforceable in one place, and is idempotent-by-design for the retry case in §3.3 Step D.

### 5.2 Shared validation helper for §3.4

New module, e.g. `rndopsapp/rndopsapp/doctype/fund_received/deposit_slip_budget_validation.py`:

```python
OVERHEAD_FIELD_BY_DOCTYPE = {
    "Research Deposit Slip": "overhead_amount",
    "Research Consultancy Deposit Slip": "overhead_amount",
    "D Consultancy Deposit Slip": "total_overhead_amount",
    "E Non Routine Deposit Slip": "overhead_amount",
    "T Testing Deposit Slip": "overhead_amount",
    "Other Event Deposit Slip": "overhead_amount",
}
GST_FIELD_BY_DOCTYPE = {
    "Research Consultancy Deposit Slip": "total_gst",
    "D Consultancy Deposit Slip": "total_gst",
    "E Non Routine Deposit Slip": "total_gst",
    "T Testing Deposit Slip": "total_gst",
    "Other Event Deposit Slip": "gst_final",
    # "Research Deposit Slip" intentionally absent — no GST concept
}

def validate_overhead_gst_budget_heads(overhead_amount, gst_amount, fr_doc, has_gst_field=True):
    """
    Core comparison, independent of whether a Deposit Slip doc exists yet.
    Raises frappe.ValidationError (via frappe.throw) covering BOTH failure
    modes from §3.1's table, not just a mismatch:
      - fr_doc has an Overhead/GST head funded (amount_received > 0) but
        overhead_amount/gst_amount is 0 → "head funded, DS silent" error.
      - both sides > 0 but the amounts don't match (tolerance 0.01) →
        "mismatch" error.
      - fr_doc has NO Overhead/GST head funded but overhead_amount/gst_amount
        > 0 → NOT this function's job; that's the missing-head/transfer-modal
        case (§3.3) and must have already been resolved by
        allocate_deposit_slip_budget_heads before this function is ever
        reached — treat it as a mismatch here too (0 vs required) as a
        defensive fallback, since it means the transfer step was skipped.
    """

def validate_overhead_gst_budget_heads_for_doc(ds_doc, fr_doc):
    """Thin wrapper for the two call sites where a saved Deposit Slip doc
    already exists — pulls overhead_amount/gst_amount off ds_doc via
    OVERHEAD_FIELD_BY_DOCTYPE / GST_FIELD_BY_DOCTYPE and calls the core
    function above."""

def validate_overhead_gst_budget_heads_for_payload(deposit_slip_type, deposit_slip_data, fr_doc):
    """Thin wrapper for the immediate submission call site, where there is
    only the incoming `deposit_slip_data` dict and no saved doc yet — reads
    the same field names (mapped via deposit_slip_type) out of the dict
    instead of a doc, and calls the core function above."""
```

Call this from **three** points now (all three ultimately go through the one core function, so the actual comparison logic lives in exactly one place):

1. **Immediate, at submission** — `perform_fund_received_action`, inside the existing `if next_state == "Pending HoS Approval":` branch (~line 834), right alongside the existing `create_deposit_slip_from_data(deposit_slip_data, doc, deposit_slip_type=deposit_slip_type)` call — call `validate_overhead_gst_budget_heads_for_payload(...)` **before** creating the Deposit Slip, so a failure blocks the whole action (including the FR's own state transition) rather than leaving a half-created Deposit Slip behind.
2. **Final gate** — `perform_fund_received_action`, inside `if next_state == "Approved":` (~line 1040, right before `kafka_result = publish_deposit_slip(ds_doc)`) — call `validate_overhead_gst_budget_heads_for_doc(...)`. Kept as a backstop; by this point it should already be consistent because of (1), but Fund Received/Deposit Slip data can still be hand-edited via Desk in between.
3. Each doctype's own `on_update()` (right before its own `publish_research_deposit_slip(self)` / equivalent call) — same `_for_doc` wrapper, same backstop reasoning as (2).

On failure, all three call sites should behave like the existing failure branch already coded there (orange `frappe.msgprint`, `frappe.log_error`, Mattermost `notify_mattermost` — do **not** invent a new error-reporting channel, reuse the existing one). For (1) specifically, the failure must also prevent `doc.workflow_state` from advancing to `"Pending HoS Approval"` at all — i.e. raise before the save/submit block later in the same function, not just log a warning.

### 5.3 `update_fund_received` — no change required for this feature

Confirmed not to need modification — the new `allocate_deposit_slip_budget_heads` (§5.1) is additive and Kafka-aware; `update_fund_received` stays as the general-purpose "replace everything" editor used by the existing Fund Received edit-mode UI.

---

## 6. API Surface Summary

| Method | Status | Purpose |
|---|---|---|
| `rndopsapp.rndopsapp.doctype.fund_received.fund_received.allocate_deposit_slip_budget_heads` | **New** | Debit source head(s), credit Overhead/GST head(s) on Fund Received (transfer, total conserved), republish to Kafka with `fundReceivedStatus="APPROVED"` |
| `rndopsapp.rndopsapp.doctype.fund_received.deposit_slip_budget_validation.validate_overhead_gst_budget_heads` (core) + `..._for_doc` / `..._for_payload` wrappers | **New** (internal, not whitelisted) | One shared reconciliation check with two thin wrappers — one for a saved Deposit Slip doc, one for a raw `deposit_slip_data` payload — called from all three points below |
| `rndopsapp.rndopsapp.doctype.fund_received.fund_received.perform_fund_received_action` | **Modified** | **Two** insertions now: (a) `_for_payload` validation inside the `"Pending HoS Approval"` branch, immediately before `create_deposit_slip_from_data` — this is the new **immediate** check; (b) `_for_doc` validation inside the `"Approved"` branch, before `publish_deposit_slip(ds_doc)` — the pre-existing final-gate backstop. Its own `publish_fund_received(doc)` call at the PENDING_APPROVAL transition is left as-is. |
| Each `<type>_deposit_slip.py::on_update()` | **Modified** | Insert `_for_doc` validation before its own publish call (same backstop role as 5.2 item 3) |
| `kafka/producer/fund_received/mapper.py::FundReceivedMapper.map_to_dto` / `map_to_event` | **Modified** | Accept optional `fund_received_status` override instead of hardcoding `"PENDING_APPROVAL"` |
| `kafka/producer/fund_received/producer.py::FundReceivedProducer.publish` / module-level `publish_fund_received` | **Modified** | Accept and thread through the same `fund_received_status` override (default `None` → unchanged behavior) |
| `rndopsapp.rndopsapp.doctype.fund_received.fund_received.create_deposit_slip_from_data` | **Modified** | Also copy `fund_received_doc.received_amt_breakup` into `new_doc.fund_budget_breakup` (§3.2) at creation time |
| `rndopsapp.rndopsapp.doctype.fund_received.fund_received.update_fund_received` | Unchanged | |

---

## 7. Open Questions / Decisions Needed

1. **D Consultancy overhead figure**: the spec says "overhead amount or total overhead amount" — D Consultancy has `total_overhead_amount` (10%×Y + 10%×Z) **and** `total_overhead_institute_share` (adds the 20%×Y institute share on top). Confirm whether the Overhead budget head must cover `total_overhead_amount` only, or `total_overhead_institute_share`. This doc assumes `total_overhead_amount` per the literal field-name match; flag before implementing.
2. **Budget Head label matching**: this design hardcodes matching against the literal labels `"Overhead"` and `"GST"` (case-insensitive) via `Budget Head.budget_head`. Confirm these exact head records exist (or will be created via `add_budget_head`) in the target environment — if the institute uses different naming (e.g. "Overheads", "GST Component"), the match constants need updating accordingly.
3. **Rounding tolerance** for the §3.4 reconciliation — this doc assumes ₹0.01; confirm.
4. **Same head for both Overhead and GST** — ✅ *resolved*: confirmed allowed per spec ("may be different... or from same head as well"). §5.1's transfer logic supports the same source head being debited twice (once per `purpose`) in a single `transfers` call.
5. **`fundReceivedStatus` on republish** — ✅ *resolved*: confirmed the value must be `"APPROVED"` specifically for the `allocate_deposit_slip_budget_heads` republish, since it only ever fires post-approval. Implemented via an explicit override parameter threaded through the mapper/producer (§2.2) rather than a generic Frappe-state→enum mapping table, so the existing `perform_fund_received_action` call site's behavior is not disturbed. Still open: whether any *other* future republish call site will need its own explicit value, and what the accounts side expects for intermediate states like `"Pending HoS Approval"` if that ever needs to be sent — out of scope until such a call site exists.
6. **Insufficient source-head balance**: §5.1 hard-fails (`frappe.throw`) if the chosen source head's `amount_received` is less than the required transfer amount, rather than allowing a partial transfer or a negative balance. Confirm this is the desired behavior (vs., e.g., allowing the user to split the required amount across two source heads) — the current spec's "two selectable [heads]" wording only covers Overhead vs. GST each having one source, not splitting a single purpose across multiple sources.
7. **Zero-balance source rows**: after a transfer drains a source head to exactly 0, §5.1 keeps the row (for audit trail) rather than deleting it. Confirm this is acceptable — a 0-amount row will still appear in the Fund Received UI and in the next Kafka payload's `fundBudgetBreakupList`.
8. **Immediate vs. final-gate enforcement** — ✅ *resolved*: all three rows of §3.1's table (head funded but DS silent; both funded but mismatched; missing head resolved via transfer) must be enforced **immediately**, at the moment the staff submits the deposit slip (`perform_fund_received_action`'s `"Pending HoS Approval"` branch), not only at the later `"Approved"`/Kafka-publish gate. The later gate stays in place as a defense-in-depth backstop for data hand-edited via Desk in between, but is no longer the primary enforcement point.
