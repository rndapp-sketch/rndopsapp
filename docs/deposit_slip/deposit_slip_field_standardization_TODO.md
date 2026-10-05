# Deposit Slip — Auto-fill Fix + Field-Name Standardization (TO-DO)

Scope decided: **mapping layer only**. Do **not** rename DocType schema fields
(no `bench migrate` field renames, no data migration). We fix auto-fill and unify
the naming at the read/write boundaries (frontend map + backend save/get_fields).

Target frontend: `mythos_omni_v0.3/prornd-ui/src/pages/DepositSlipForm.tsx`.

---

## PART A — Fix Auto-fill (this is the actual bug)

### Root cause (confirmed)

When a project is picked, the form calls `frappe.client.get` on **Project
Registration** and maps the returned doc's fields to form fields via
`PROJECT_FIELD_MAP`. But the map's keys do **not** exist on Project Registration.
Only `funding_agen` matches — so only Funding Agency ever fills.

**What Project Registration actually stores:**

| Data element | Real Project Registration fieldname(s) | Type |
|---|---|---|
| Principal Investigator (user id) | `pi_userid`, `pi_webmail` | Link → User |
| PI display name | `principal_investigator_name`, `pi_employee_id` | Data |
| Funding Agency | `funding_agen` (primary), `funding_agency_other` | Link → `fundingagency_` / Data |
| GSTIN | `gstin_number`, `consultancy_gstin` | Data |
| Client | *(no dedicated field exists)* | — |

> Note: the deposit-slip `principal_investigator` is a **Link → User**, so the
> auto-filled value must be a User id. Use `pi_userid` / `pi_webmail` (which hold
> the User id). Do **not** map `principal_investigator_name` into it — that's a
> display string and would set an invalid Link value.

### Fix — replace `PROJECT_FIELD_MAP` in `DepositSlipForm.tsx`

```ts
// Map from Project Registration fieldnames → canonical form fieldnames.
// First match wins per target (order matters).
const PROJECT_FIELD_MAP: Record<string, string> = {
    // Principal Investigator — must resolve to a User id (Link→User target)
    pi_userid: "principal_investigator",
    pi_webmail: "principal_investigator",

    // Funding Agency
    funding_agen: "funding_agency",
    funding_agency_other: "funding_agency",

    // GSTIN of Funding Agency
    gstin_number: "gstin_of_funding_agency",
    consultancy_gstin: "gstin_of_funding_agency",

    // NOTE: Project Registration has no "client" field. Client stays manual.
    // If/when a client field is added to Project Registration, add it here.
};
```

Keep `PROJECT_AUTOFILL_TARGET_FIELDS` as-is (it lists the *form* targets, which are
unchanged: `principal_investigator`, `client`, `funding_agency`,
`gstin_of_funding_agency`).

### Verify
1. Open an E or T deposit slip, pick a project in **Project Title**.
2. Confirm **Principal Investigator**, **Funding Agency**, and **GSTIN** auto-fill
   and render read-only (the "auto-filled" tag).
3. **Client** will remain blank/manual — expected (no source field).

---

## PART B — Canonical field dictionary (the single names to use)

These are the agreed canonical fieldnames for **shared** data across all slip types.
Everything in the app (form state keys, payload keys, validation, submit handlers,
type defs) should reference these names.

| Canonical fieldname | Meaning |
|---|---|
| `project_title` | Project / consultancy / event identifier (Link or Data) |
| `principal_investigator` | Lead person (PI / consultant / organizer), Link → User |
| `client` | Client name |
| `funding_agency` | Funding agency |
| `gstin_of_funding_agency` | GSTIN of the funding agency |
| `ecs_ac_no` | ECS account number |
| `bank` | Bank name |
| `ecs_dates` | ECS dates child table |
| `amount_inclusive_of_gst` | Gross amount incl. GST |
| `total_gst` | Total GST |
| `credit_distribution` | Credit distribution child table |

---

## PART C — True inconsistencies to normalize (mapping layer)

Only these fields use a *different name for the same data*. Because we are **not**
renaming schema fields, normalize them at the API boundary so the frontend always
sees/sends the canonical name.

| DocType | Stored (schema) fieldname | Canonical name | Action |
|---|---|---|---|
| Other Event Deposit Slip | `gstin_no` | `gstin_of_funding_agency` | alias |
| Deposit slip | `ecs_acc_no` | `ecs_ac_no` | alias |
| Research Deposit Slip | `bank_name` | `bank` | alias |
| Research Deposit Slip | `account_number` | `ecs_ac_no` | alias |
| Research Deposit Slip | `ecs_date` (table) | `ecs_dates` | alias |

### Where to apply the alias (backend, no schema change)

Centralize a per-doctype alias table in each slip's controller, then:

**1. In `get_*_fields` — rename outgoing fieldnames to canonical** so the frontend
renders canonical keys:

```python
# Canonical alias map: {schema_fieldname: canonical_fieldname}
FIELD_ALIASES = {
    "gstin_no": "gstin_of_funding_agency",   # Other Event
    "ecs_acc_no": "ecs_ac_no",               # Deposit slip
    "bank_name": "bank",                     # Research
    "account_number": "ecs_ac_no",           # Research
    "ecs_date": "ecs_dates",                 # Research (table)
}

# inside the field loop, after building field_data:
canonical = FIELD_ALIASES.get(f.fieldname)
if canonical:
    field_data["fieldname"] = canonical
```

Also remap the **prefill_data** keys the same way so existing-doc edits prefill the
canonical fields:

```python
if doc_name and frappe.db.exists(doctype_name, doc_name):
    raw = frappe.get_doc(doctype_name, doc_name).as_dict()
    prefill_data = { FIELD_ALIASES.get(k, k): v for k, v in raw.items() }
```

**2. In `save_*` — translate canonical payload keys back to the schema field**
when writing to the doc (reverse map), so stored data is untouched:

```python
REVERSE_ALIASES = {v: k for k, v in FIELD_ALIASES.items()}

# when setting a scalar field:
target = REVERSE_ALIASES.get(form_field, form_field)
doc.set(target, data[form_field])
```

> Apply `FIELD_ALIASES` only inside the controller that owns that field
> (Other Event → `gstin_no`; Deposit slip → `ecs_acc_no`; Research → the three).
> E / T / D Consultancy already use canonical names — no alias needed there.

### Child-table note (Research `ecs_date` → `ecs_dates`)
The Research slip's ECS table is `ecs_date`; everywhere else it's `ecs_dates`.
In Research `save_*`, append rows to the real field `ecs_date` while accepting the
canonical `ecs_dates` key from the payload:

```python
rows = data.get("ecs_dates", [])      # canonical key from frontend
doc.set("ecs_date", [])               # real schema field
for r in rows:
    doc.append("ecs_date", {"ecs_date": r.get("ecs_date"), "amount": r.get("amount", 0)})
```

---

## PART D — Type-specific fields: keep distinct (do NOT merge)

These look different but are **semantically different roles** — leave them, just
document the role. Optionally surface them under a shared *label* in the UI, but the
fieldnames stay type-specific:

| Type | Field | Why it stays separate |
|---|---|---|
| D Consultancy | `consultancy_title` | It's a consultancy title, not a project link |
| D Consultancy | `principal_consultant` | Consultant, not PI (still Link → User) |
| Other Event | `event_title` | Event name, not a project |
| Other Event | `principal_organizer` | Organizer, not PI |

If you want these to flow through the same form-state slot, alias them to the
canonical names (`project_title`, `principal_investigator`) using the same
`FIELD_ALIASES` mechanism in Part C — but only do this if the business logic treats
them as the same field. Default recommendation: **keep them distinct.**

---

## PART E — Checklist

- [ ] **A:** Replace `PROJECT_FIELD_MAP` with the corrected map (real PR fieldnames).
- [ ] **A:** Verify E & T auto-fill PI / Funding Agency / GSTIN on project select.
- [ ] **C:** Add `FIELD_ALIASES` to Other Event, Deposit slip, Research controllers.
- [ ] **C:** Remap outgoing `fields[].fieldname` + `prefill_data` keys to canonical.
- [ ] **C:** Reverse-map canonical → schema field in each `save_*`.
- [ ] **C:** Research `ecs_dates` (payload) → `ecs_date` (schema) in save.
- [ ] **D:** Confirm `consultancy_title` / `event_title` / `principal_consultant` /
      `principal_organizer` remain distinct (or alias intentionally).
- [ ] Regression: save + reload each slip type; confirm no field comes back blank.
- [ ] Regression: submit + workflow action still work on each type.

---

## Reference — current field names per type (as-is)

| Canonical | E NonRoutine | T Testing | D Consultancy | Research | Research Consultancy | Other Event | Deposit slip |
|---|---|---|---|---|---|---|---|
| project_title | `project_title` | `project_title` | `consultancy_title`* | `project_title` | `project_title` | `event_title`* | `project_title` |
| principal_investigator | `principal_investigator` | `principal_investigator` | `principal_consultant`* | `principal_investigator` | `principal_investigator` | `principal_organizer`* | `principal_investigator` |
| client | `client` | `client` | `client` | — | `client` | `client` | `client` |
| funding_agency | `funding_agency` | — | `funding_agency` | `funding_agency` | `funding_agency` | `funding_agency` | `funding_agency` |
| gstin_of_funding_agency | `gstin_of_funding_agency` | `gstin_of_funding_agency` | `gstin_of_funding_agency` | — | `gstin_of_funding_agency` | **`gstin_no`** | `gstin_of_funding_agency` |
| ecs_ac_no | `ecs_ac_no` | `ecs_ac_no` | `ecs_ac_no` | **`account_number`** | `ecs_ac_no` | `ecs_ac_no` | **`ecs_acc_no`** |
| bank | `bank` | `bank` | `bank` | **`bank_name`** | `bank` | `bank` | `bank` |
| ecs_dates | `ecs_dates` | `ecs_dates` | `ecs_dates` | **`ecs_date`** | `ecs_dates` | `ecs_dates` | `ecs_dates` |

`*` = semantically distinct role (Part D), keep separate.
**bold** = true inconsistency to alias (Part C).
