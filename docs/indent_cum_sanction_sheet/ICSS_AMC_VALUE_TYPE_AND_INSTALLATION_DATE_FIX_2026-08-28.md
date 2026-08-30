# ICSS AMC — Value Type (%/Amount), Installation Date, Submittable — 2026-08-28

## Context

For **Indent Type = "Annual Maintenance Contract"** on the Indent Cum Sanction
Sheet (ICSS), the AMC details are captured in the linked child doctype
**AMC** (`rndopsapp/rndopsapp/doctype/amc/`). The parent ICSS form is
metadata-driven — the frontend renders whatever fields `get_icss_child_fields`
returns for the selected indent type, so all of the fixes below are pure
doctype/controller changes; no frontend code changes were required.

## Issues fixed

1. **AMC value could only be entered as a flat amount.** There was no way to
   specify the AMC value as a percentage of the PO's Basic Value (BV), even
   though the field's description hinted at this (`"@___________ % of BV"`).
2. **`amc_date_of_installation` was a Data (free-text) field**, not a proper
   Date field.
3. Several amount fields (`basic_value_bv_of_the_po`, `amc_other_charges`,
   `amc_gst`, `amc_grand_total`) were typed as Data instead of Currency,
   so the grand-total calculation relied entirely on `flt()` coercion at
   runtime instead of real numeric columns.
4. Confirmed `is_submittable` was already `1` on both **AMC** and the parent
   **Indent Cum Sanction Sheet** — no change was needed there.

## Changes

### `amc.json`

- Added `amc_value_type` — Select (`Value` / `Percentage`, default `Value`,
  reqd) — "Value of the AMC is in".
- Added `amc_value_percentage` — Percent field, `depends_on` /
  `mandatory_depends_on`: `eval:doc.amc_value_type=="Percentage"` —
  "AMC Value (%)", described as "% of Basic Value (BV) of the PO".
- `amc_value` — now Currency, `depends_on` / `mandatory_depends_on`:
  `eval:doc.amc_value_type=="Value"` — "Value of the AMC (Rs)".
- Added `amc_computed_value` — read-only Currency field — the resolved AMC
  value regardless of which mode was used (percentage-of-BV or flat amount).
- `amc_date_of_installation` — changed fieldtype from `Data` to `Date`.
- `basic_value_bv_of_the_po`, `amc_other_charges`, `amc_gst`,
  `amc_grand_total` — changed fieldtype from `Data` to `Currency`
  (`amc_grand_total` also made read-only).

### `amc.py`

`_compute_totals()` now resolves the AMC value based on `amc_value_type`
before computing the grand total:

```python
if self.get("amc_value_type") == "Percentage":
    computed_value = flt(self.get("basic_value_bv_of_the_po")) * flt(self.get("amc_value_percentage")) / 100
else:
    computed_value = flt(self.get("amc_value"))
self.amc_computed_value = computed_value

self.amc_grand_total = (
    computed_value
    + flt(self.get("amc_other_charges"))
    + flt(self.get("amc_gst"))
)
```

## Data migration (existing records)

Changing `amc_date_of_installation` and the four amount fields to typed
columns required cleaning up pre-existing data before `bench migrate` could
`ALTER TABLE`:

- **Dates** in `DD/MM/YYYY` and `DD-MM-YYYY` formats were normalized to
  `YYYY-MM-DD`.
- One `basic_value_bv_of_the_po` value contained non-numeric text
  (`"315000 Euro"`) — stripped to the numeric portion (`315000`).
- `NULL` values in `amc_other_charges`, `amc_value`, `amc_gst`, and
  `basic_value_bv_of_the_po` were set to `0` (strict SQL mode rejects
  `NULL` → `NOT NULL DEFAULT 0` column conversions).
- `amc_value_type` defaulted to `Value` for all existing rows, preserving
  their original (flat-amount) meaning.

`bench --site prornd.local migrate` ran clean afterward.

## Verification

Ran in `bench --site prornd.local console`:

```python
meta = frappe.get_meta("AMC")
meta.get_field("amc_value_type").options   # "Value\nPercentage"
meta.get_field("amc_date_of_installation").fieldtype  # "Date"
meta.is_submittable  # 1

doc = frappe.get_doc({
    "doctype": "AMC",
    "basic_value_bv_of_the_po": 1000000,
    "amc_value_type": "Percentage",
    "amc_value_percentage": 10,
    "amc_other_charges": 500,
    "amc_gst": 100,
})
doc.run_method("validate")
# computed_value 100000.0
# grand_total    100600.0
```

10% of ₹1,000,000 + ₹500 + ₹100 = ₹100,600 — matches expectation.
