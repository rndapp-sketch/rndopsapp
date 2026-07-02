# Fund Sanction — Unique `sanctioned_letter_no` Implementation

**Date:** 2026-06-10
**File modified:** `apps/rndopsapp/rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py`

## Goal

The `sanctioned_letter_no` field on the **Fund Sanction** doctype must be unique —
no two Fund Sanction documents may share the same sanctioned letter number.
A realtime endpoint lets the frontend check for duplicates while the user types,
and suggests a unique alternative when a duplicate is found.

---

## 1. Doctype-level validation (`FundSanction.validate`)

Every normal `doc.save()` / `doc.insert()` runs `validate()`, which calls
`validate_unique_sanctioned_letter_no()`:

```python
class FundSanction(Document):
    def validate(self):
        self.validate_unique_sanctioned_letter_no()

    def validate_unique_sanctioned_letter_no(self):
        if not self.sanctioned_letter_no:
            return
        duplicate = frappe.db.get_value(
            "Fund Sanction",
            {
                "sanctioned_letter_no": self.sanctioned_letter_no,
                "name": ["!=", self.name or ""],
            },
            "name",
        )
        if duplicate:
            frappe.throw(...)  # "Duplicate Sanctioned Letter No"
```

Key points:

- Empty / null letter numbers are allowed (no check).
- The check excludes the document's own `name`, so re-saving an existing
  document with its own letter number does not flag itself.
- On conflict it throws a `frappe.ValidationError` with the title
  **"Duplicate Sanctioned Letter No"**, naming the conflicting document.

## 2. Enforcement inside `save_fund_sanction_data`

The custom save endpoint `save_fund_sanction_data` saves with
`doc.flags.ignore_validate = True`, which **skips** `validate()` entirely.
To prevent that path from bypassing the rule, the same duplicate check is
repeated inside `save_fund_sanction_data` itself — right after the
existing-draft auto-detection block and **before** the document is
created/updated:

```python
letter_no = (data.get("sanctioned_letter_no") or "").strip()
if letter_no:
    dup_filters = {"sanctioned_letter_no": letter_no}
    if data.get("name"):
        dup_filters["name"] = ["!=", data.get("name")]
    duplicate = frappe.db.get_value("Fund Sanction", dup_filters, "name")
    if duplicate:
        frappe.throw(...)  # same "Duplicate Sanctioned Letter No" error
```

When updating an existing document (`data["name"]` present — either passed by
the frontend or auto-detected from an existing draft), that document is
excluded from the duplicate search.

## 3. Realtime duplicate-check endpoint

### `check_sanctioned_letter_no`

```
POST /api/method/rndopsapp.rndopsapp.doctype.fund_sanction.fund_sanction.check_sanctioned_letter_no
```

| Argument | Required | Description |
|---|---|---|
| `sanctioned_letter_no` | yes | The letter number to check |
| `docname` | no | Current Fund Sanction name — excluded from the check so an open document doesn't flag itself |

**Response — value is free:**

```json
{
  "status": "success",
  "is_duplicate": false,
  "sanctioned_letter_no": "ANRF/ARG/2025/003460/PS"
}
```

**Response — duplicate found:**

```json
{
  "status": "success",
  "is_duplicate": true,
  "existing_doc": "SAN_140526-667-2026050701ANRF000573",
  "suggested": "ANRF/ARG/2025/003460/PS-SL00001"
}
```

### Suggestion format (auto-increment suffix)

When a duplicate is found, `get_unique_sanctioned_letter_no()` generates the
suggestion by appending `-SL<NNNNN>` (zero-padded to 5 digits) and
incrementing the counter until a value is found that no Fund Sanction uses:

```
<letter_no>-SL00001   → taken? try
<letter_no>-SL00002   → taken? try
<letter_no>-SL00003   → free → returned
```

```python
def get_unique_sanctioned_letter_no(letter_no):
    counter = 1
    while True:
        candidate = f"{letter_no}-SL{counter:05d}"
        if not frappe.db.exists("Fund Sanction", {"sanctioned_letter_no": candidate}):
            return candidate
        counter += 1
```

---

## 4. Frontend implementation

### Reusable resolver

A single helper that always returns a **usable unique value** — the original
if free, or the server's `-SL00001` suggestion if taken:

```javascript
async function resolveUniqueSanctionLetterNo(letterNo, docname = null) {
    const res = await fetch(
        "/api/method/rndopsapp.rndopsapp.doctype.fund_sanction.fund_sanction.check_sanctioned_letter_no",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-Frappe-CSRF-Token": window.csrf_token || "",
            },
            body: JSON.stringify({
                sanctioned_letter_no: letterNo,
                ...(docname ? { docname } : {}),
            }),
        }
    );
    const data = await res.json();
    const m = data.message || {};
    if (m.status !== "success") throw new Error(m.message || "Check failed");

    return {
        isDuplicate: m.is_duplicate,
        finalValue: m.is_duplicate ? m.suggested : letterNo, // always safe to save
        existingDoc: m.existing_doc || null,
    };
}
```

### Option A — realtime check while typing (debounced)

```html
<input type="text" id="sanction-letter-no" class="form-input">
<div id="letter-no-hint" style="font-size: 0.8rem; margin-top: 4px;"></div>
```

```javascript
let letterNoTimer = null;

document.getElementById("sanction-letter-no").addEventListener("input", (e) => {
    clearTimeout(letterNoTimer);
    const hint = document.getElementById("letter-no-hint");
    hint.textContent = "";

    const value = e.target.value.trim();
    if (!value) return;

    letterNoTimer = setTimeout(async () => {
        hint.style.color = "#888";
        hint.textContent = "Checking...";
        try {
            const r = await resolveUniqueSanctionLetterNo(value, window.currentSanctionName);
            if (r.isDuplicate) {
                e.target.value = r.finalValue;  // auto-replace with appended value
                hint.style.color = "#f9ab00";
                hint.textContent =
                    `⚠️ "${value}" already used in ${r.existingDoc} — changed to "${r.finalValue}"`;
            } else {
                hint.style.color = "#1e8e3e";
                hint.textContent = "✓ Letter number is available";
            }
        } catch (err) {
            hint.style.color = "#d93025";
            hint.textContent = "Could not verify: " + err.message;
        }
    }, 500);
});
```

### Option B — resolve silently at save time (recommended safety net)

Two users can pass the realtime check simultaneously, so also resolve right
before calling `save_fund_sanction_data`. This guarantees the save never hits
the backend duplicate throw:

```javascript
async function saveFundSanction(formData) {
    if (formData.sanctioned_letter_no) {
        const r = await resolveUniqueSanctionLetterNo(
            formData.sanctioned_letter_no,
            formData.name  // undefined for new docs — fine
        );
        if (r.isDuplicate) {
            formData.sanctioned_letter_no = r.finalValue;  // use appended version
            console.warn(`Letter no was duplicate; saved as "${r.finalValue}"`);
        }
    }
    return callMethod(
        "rndopsapp.rndopsapp.doctype.fund_sanction.fund_sanction.save_fund_sanction_data",
        formData
    );
}
```

Use **A and B together**: A gives immediate user feedback; B handles the race
condition.

### Option C — Frappe Desk client script

For users editing via `/app`, add a Client Script (Doctype: Fund Sanction):

```javascript
frappe.ui.form.on("Fund Sanction", {
    sanctioned_letter_no(frm) {
        if (!frm.doc.sanctioned_letter_no) return;
        frappe.call({
            method: "rndopsapp.rndopsapp.doctype.fund_sanction.fund_sanction.check_sanctioned_letter_no",
            args: {
                sanctioned_letter_no: frm.doc.sanctioned_letter_no,
                docname: frm.doc.name,
            },
            callback(r) {
                const m = r.message || {};
                if (m.is_duplicate) {
                    frm.set_value("sanctioned_letter_no", m.suggested);
                    frappe.show_alert({
                        message: __("Duplicate of {0} — changed to {1}", [m.existing_doc, m.suggested]),
                        indicator: "orange",
                    }, 7);
                }
            },
        });
    },
});
```

---

## Deployment notes

- **Restart required:** run `bench restart` for the Python changes to load.
- **Pre-existing duplicates:** as of 2026-06-10 the database already contained
  **26 letter numbers with duplicates** (mostly double-submit pairs, plus junk
  values like `Email` ×6, `NA` ×5, `Nil` ×3). The validation does not modify
  existing rows, but the next save of any of those documents will be blocked
  until its letter number is changed (the endpoint's `suggested` value can be
  used for that).
- **No DB-level unique constraint** was added (existing duplicates would make
  the migration fail). Uniqueness is enforced at the application layer in both
  save paths described above.
