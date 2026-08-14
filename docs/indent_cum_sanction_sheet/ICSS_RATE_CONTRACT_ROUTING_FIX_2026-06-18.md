# ICSS Routing Bug Fix — All Indent Types

## Problem

ICSS documents of **all indent types** were routing to **Pending Associate Dean** regardless of the actual amount, even when the true grand total far exceeded the ₹1,00,000 threshold.

This was initially discovered for Rate Contract, then found to affect Proprietary Purchase (e.g. `2026061810001221`, `pp_grand_total = ₹26,56,230`) and Standardized Purchase as well.

### Root Cause Chain

Four bugs combined to cause this:

---

### Bug 0 — `_get_icss_approval_amount()` read `icss_grand_total` for all non-RC types

**File:** `rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py`

`icss_grand_total` on the ICSS parent is **always 0** for Proprietary, Standardized, Repair, and AMC types because each type stores its items in its own child sub-doctype. The ICSS's `calculate_item_totals()` sums `icss_items` (always empty) → writes 0 to `icss_grand_total` on every save.

**Fix (2026-06-18):** Replaced the entire function with a mapping that reads the grand total directly from the child sub-doctype for **every** indent type. `icss_grand_total` is **never** used for routing.

```python
_ICSS_AMOUNT_SOURCE = {
    INDENT_TYPE_PROPRIETARY:  ("proprietary_purchase",  "pp_grand_total"),
    INDENT_TYPE_STANDARDIZED: ("standerdized_purchase", "sp_grand_total"),
    INDENT_TYPE_REPAIR:       ("repair_replacement",    "rr_grand_total"),
    INDENT_TYPE_AMC:          ("AMC",                   "amc_grand_total"),
    INDENT_TYPE_RATE_CONTRACT:("Rate Contract",         "rate_contract_grand_total"),
}


def _get_icss_approval_amount(doc):
    indent_type = doc.get("icss_indent_type") or ""
    source = _ICSS_AMOUNT_SOURCE.get(indent_type)
    if not source:
        return 0
    child_doctype, amount_field = source
    sub_ref = doc.get("sub_doctype_reference")
    if not sub_ref:
        return 0
    return flt(frappe.db.get_value(child_doctype, sub_ref, amount_field))
```

---

### Bug 1 — `RateContract.validate()` was missing

**File:** `rndopsapp/doctype/rate_contract/rate_contract.py`

The `RateContract` class had only `pass`. No `validate()` hook existed, so `rate_contract_grand_total` was never computed server-side. It remained `0` in the database even when items were saved with large amounts.

**Fix:** Added `validate()` with `_compute_totals()`:

```python
class RateContract(Document):
    def validate(self):
        self._compute_totals()

    def _compute_totals(self):
        item_total = sum(flt(row.amount) for row in self.get("items", []))
        self.rate_contract_total = item_total
        self.rate_contract_grand_total = item_total + flt(self.rate_contract_packing)
```

---

### Bug 2 — `_get_icss_approval_amount()` had no Rate Contract case

**File:** `rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py`

The HoS routing function read `icss_grand_total` for all indent types. For Rate Contract ICSS, `icss_grand_total` is always `0` because items live in the linked Rate Contract child doctype, not in the ICSS itself.

**Fix:** Added `INDENT_TYPE_RATE_CONTRACT` case that follows the `sub_doctype_reference` link:

```python
def _get_icss_approval_amount(doc):
    indent_type = doc.get("icss_indent_type") or ""
    if indent_type == INDENT_TYPE_REPAIR:
        return flt(doc.get("icss_repair_grand_total"))
    if indent_type == INDENT_TYPE_AMC:
        return flt(doc.get("icss_amc_grand_total"))
    if indent_type == INDENT_TYPE_RATE_CONTRACT:
        sub_ref = doc.get("sub_doctype_reference")
        if sub_ref:
            return flt(frappe.db.get_value("Rate Contract", sub_ref, "rate_contract_grand_total"))
        return 0
    return flt(doc.get("icss_grand_total"))
```

---

### Bug 3 — Intermediate save zeroed grand total during Kafka payload ingestion

**File:** `rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py` → `_save_doc_from_payload()`

The two-pass save pattern in `_save_doc_from_payload()` runs `validate()` on the first save **before** child table items are appended. This caused `calculate_item_totals()` to sum zero items → grand total written as `0` to DB. On the second save, items are appended correctly, but for Rate Contract type, `icss_grand_total` is always `0` anyway (amounts live in Rate Contract sub-doc), so this only matters for other types. The fix guards all total-calculation calls.

**Fix:** Added `skip_total_calculation` flag around intermediate save:

```python
has_deferred_tables = any(df.fieldtype == "Table" for _, _, df in deferred)
if has_deferred_tables:
    doc.flags.skip_total_calculation = True
if is_new:
    doc.insert(ignore_permissions=True)
else:
    doc.save(ignore_permissions=True)
doc.flags.skip_total_calculation = False
```

And guarded in `validate()`:

```python
def validate(self):
    self._validate_indent_type()
    self._validate_indent_type_change()
    if not self.flags.get("skip_total_calculation"):
        self.calculate_item_totals()
        self.calculate_repair_total()
        self.calculate_amc_total()
    self._update_director_approval_required()
```

---

## Routing Logic (after fix)

```
HoS clicks "Forward"
    ↓
_get_icss_approval_amount(doc)   [reads from child sub-doctype ONLY — never icss_grand_total]
    ├── Proprietary Purchase     → proprietary_purchase.pp_grand_total
    ├── Standardized Purchase    → standerdized_purchase.sp_grand_total
    ├── Repair/Replacement       → repair_replacement.rr_grand_total
    ├── AMC                      → AMC.amc_grand_total
    └── Rate Contract Purchase   → Rate Contract.rate_contract_grand_total
    ↓
_resolve_hos_next_state(amount)
    ├── amount > ₹1,00,000  → "Pending Dean Approval"
    └── amount ≤ ₹1,00,000  → "Pending Associate Dean"
```

---

## Data Fix for Affected Documents

### Root cause of `icss_grand_total = 0` for Proprietary / Standardized types

For Proprietary Purchase and Standardized Purchase, items live in the child doctype's table (`table_qanf` / `details_of_items_to_be_purchased`), not in the ICSS itself. When the ICSS parent was saved, `calculate_item_totals()` summed its own (empty) item rows → `icss_grand_total = 0`. The `_get_icss_approval_amount()` then read `flt(0)` → below threshold → incorrectly routed to Associate Dean.

The fix (code) is the `skip_total_calculation` guard. The data fix below corrects existing documents by syncing `icss_grand_total` from the child's computed grand total.

### Documents corrected

Rate Contract document (`2026061710001203`) was fixed via `fix_icss_state.py`. The other documents were fixed directly via SQL.

| Document | Indent Type | Child Doc | `icss_grand_total` before | Source of correct amount | Corrected amount | Corrected State |
|---|---|---|---|---|---|---|
| `2026061710001203` | Rate Contract Purchase | `2026061711RATE001204` (Rate Contract) | `0` | `rate_contract_grand_total` | ₹14,70,250 | Pending Dean Approval |
| `2026060910001036` | Proprietary Purchase | `e8pntcqihu` (proprietary_purchase) | `0` | child `pp_grand_total` | ₹39,89,993 | Pending Dean Approval |
| `2026061710001205` | Standardized Purchase | `i9l857n6hb` (standerdized_purchase) | `0` | child `sp_grand_total` | ₹30,40,000 | Pending Dean Approval |
| `2026061810001221` | Proprietary Purchase | `47uv2vhk7r` (proprietary_purchase) | `0` | child `pp_grand_total` | ₹26,56,230 | Fixed by code — no SQL needed (routing now reads child directly) |

No Repair/Replacement or AMC documents were found stuck at "Pending Associate Dean".

### SQL used for Proprietary Purchase fix (`2026060910001036`)

```sql
UPDATE `tabIndent Cum Sanction Sheet`
SET icss_grand_total = 3989993, workflow_state = 'Pending Dean Approval',
    modified = NOW(), modified_by = 'Administrator'
WHERE name = '2026060910001036';

UPDATE `tabproprietary_purchase`
SET workflow_state = 'Pending Dean Approval', modified = NOW(), modified_by = 'Administrator'
WHERE name = 'e8pntcqihu';
```

### SQL used for Standardized Purchase fix (`2026061710001205`)

```sql
UPDATE `tabIndent Cum Sanction Sheet`
SET icss_grand_total = 3040000, workflow_state = 'Pending Dean Approval',
    modified = NOW(), modified_by = 'Administrator'
WHERE name = '2026061710001205';

UPDATE `tabstanderdized_purchase`
SET workflow_state = 'Pending Dean Approval', modified = NOW(), modified_by = 'Administrator'
WHERE name = 'i9l857n6hb';
```

### SQL to scan for future stuck documents

Run after deployment to verify no new documents are stuck:

```sql
-- Proprietary / Standardized: icss_grand_total = 0 but child has a non-zero total
SELECT i.name, i.icss_indent_type, i.workflow_state, i.icss_grand_total,
       pp.pp_grand_total AS child_total
FROM `tabIndent Cum Sanction Sheet` i
JOIN `tabproprietary_purchase` pp ON pp.name = i.sub_doctype_reference
WHERE i.icss_indent_type LIKE '%Proprietary%'
  AND i.workflow_state = 'Pending Associate Dean'
  AND i.icss_grand_total = 0 AND pp.pp_grand_total > 100000;

SELECT i.name, i.icss_indent_type, i.workflow_state, i.icss_grand_total,
       sp.sp_grand_total AS child_total
FROM `tabIndent Cum Sanction Sheet` i
JOIN `tabstanderdized_purchase` sp ON sp.name = i.sub_doctype_reference
WHERE i.icss_indent_type = 'Standerdised/ Emergent Purchase'
  AND i.workflow_state = 'Pending Associate Dean'
  AND i.icss_grand_total = 0 AND sp.sp_grand_total > 100000;

-- Rate Contract: same pattern via linked Rate Contract
SELECT i.name, i.workflow_state, rc.rate_contract_grand_total
FROM `tabIndent Cum Sanction Sheet` i
JOIN `tabRate Contract` rc ON rc.name = i.sub_doctype_reference
WHERE i.icss_indent_type = 'Rate Contract Purchase'
  AND i.workflow_state = 'Pending Associate Dean'
  AND rc.rate_contract_grand_total > 100000;
```

---

## Verification

Rate Contract `2026061711RATE001204` values confirmed correct:

```
rate_contract_total      : ₹14,60,250   (250,000 units × ₹5 − 1% disc + 18% GST)
rate_contract_packing    : ₹10,000
rate_contract_grand_total: ₹14,70,250   ✓ matches recomputed
```

₹14,70,250 >> ₹1,00,000 threshold → correctly routes to **Pending Dean Approval**.

---

## After Deployment

Run `bench restart` after deploying the code fixes so the updated `validate()` hooks and `_get_icss_approval_amount()` are loaded. New HoS Forward actions will then route correctly without needing any data fix scripts.

> **Note (2026-06-18):** After the final `_get_icss_approval_amount()` rewrite (Bug 0 above), no SQL data fixes are needed for future stuck documents. The function now always reads from the child sub-doctype at routing time, so `icss_grand_total` on the parent is irrelevant to workflow routing regardless of its stored value.

---

## Follow-up — `skip_total_calculation` Applied to All 4 Remaining Child Doctypes

After fixing Rate Contract, the same `skip_total_calculation` guard was applied to all other ICSS child doctypes to prevent the same intermediate-save zeroing issue.

### proprietary_purchase

**File:** `rndopsapp/doctype/proprietary_purchase/proprietary_purchase.py`

Has `table_qanf` child table → two-pass save issue is real for this type.

```python
def validate(self):
    self._validate_parent_linkage()
    if not self.flags.get("skip_total_calculation"):
        self.calculate_totals()
```

### standerdized_purchase

**File:** `rndopsapp/doctype/standerdized_purchase/standerdized_purchase.py`

Has `details_of_items_to_be_purchased` child table → two-pass save issue is real for this type.

```python
def validate(self):
    if not self.flags.get("skip_total_calculation"):
        self.calculate_totals()
```

### repair_replacement

**File:** `rndopsapp/doctype/repair_replacement/repair_replacement.py`

Two changes:

1. Added `skip_total_calculation` guard.
2. Fixed stale calculation — `rr_other_charges` was converted from `Column Break` to `Currency` in a prior DB fix, but the Python code still excluded it. Updated:

```python
def validate(self):
    if not self.flags.get("skip_total_calculation"):
        self.calculate_totals()

def calculate_totals(self):
    self.rr_grand_total = flt(self.get("rr_repair_expenditure")) + flt(self.get("rr_other_charges"))
```

### AMC

**File:** `rndopsapp/doctype/amc/amc.py`

The `AMC` class had only `pass` — same root cause as Rate Contract. `amc_grand_total` was never computed server-side. Added full `validate()`:

```python
class AMC(Document):
    def validate(self):
        if not self.flags.get("skip_total_calculation"):
            self._compute_totals()

    def _compute_totals(self):
        # amc_value, amc_other_charges, amc_gst are Data fields (user-entered amounts)
        total = (
            flt(self.get("amc_value"))
            + flt(self.get("amc_other_charges"))
            + flt(self.get("amc_gst"))
        )
        self.amc_grand_total = total
```

Note: For AMC, `_get_icss_approval_amount()` reads `icss_amc_grand_total` from the **ICSS parent** (computed by `calculate_amc_total()` on the ICSS), not from the AMC child's `amc_grand_total`. The child's `amc_grand_total` is a display field in the AMC form only.

### Summary Table

| Doctype | Had validate()? | Had child table issue? | Additional fix |
|---|---|---|---|
| `proprietary_purchase` | Yes | Yes (`table_qanf`) | Guard added |
| `standerdized_purchase` | Yes | Yes (`details_of_items_to_be_purchased`) | Guard added |
| `repair_replacement` | Yes | No | Guard added + `rr_other_charges` included in total |
| `AMC` | No (was `pass`) | No | Full `validate()` + `_compute_totals()` added |
| `Rate Contract` | No (was `pass`) | Yes (`items`) | Already fixed (see above) |
