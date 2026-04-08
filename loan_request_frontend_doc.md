# Loan Request — Frontend Developer Documentation

**Doctype:** `Loan Request`  
**Naming Pattern:** `{YYYY}{MM}{DD}LOAN{#####}` — e.g. `202604030LOAN00001`  
**Submittable:** Yes (`is_submittable: 1`)  
**Active Workflow:** `loan_workflow_without_copi`

---

## 1. Field Reference

### Main Document Fields

| Field Name | Label | Type | Required | Read Only | Notes |
|---|---|---|---|---|---|
| `self_other` | Applying for self or other? | Data | No | Yes | Default: `"Self"`. Show "Applying For" section only when value is `"Other"` |
| `loan_for_webmail_id` | PI Webmail Id | Link → User | No | No | Only shown/used when `self_other = "Other"` |
| `loan_for_name` | Name | Data | No | No | Auto-fetched from `loan_for_webmail_id.full_name` |
| `loan_for_department` | Department | Data | No | No | Auto-fetched from `loan_for_webmail_id.department_name` |
| `loan_for_designation` | Designation | Data | No | No | Auto-fetched from `loan_for_webmail_id.designation_name` |
| `applicant_webmail` | Webmail Id | Link → User | No | Yes | **Must be set by frontend** to logged-in user's email on create |
| `applicant_department` | Department | Data | No | Yes | Auto-fetched from `applicant_webmail.department_name` |
| `applicant_designation` | Designation | Data | No | Yes | Auto-fetched from `applicant_webmail.designation_name` |
| `project_name` | Project Title | Link → Project Registration | No | No | Dropdown — display `project_title`, store `name` |
| `project_number` | Project Number | Data | No | Yes | **Must be set via JS** — see Section 3.1. Do NOT rely on `fetch_from` |
| `loan_account_type` | Loan From account Type | Select | No | No | See options below |
| `account_head_fund_breakup` | Fund Breakup | Table | No | No | Child table — see Section 2 |
| `loan_amount` | Total Loan Amount | Currency | No | Yes | **Auto-calculated** — sum of all child rows. Read-only, never editable |
| `agreement_no_1` | Agreement 1 | Check | No | No | Must be `1` before submission |
| `agreement_no_2` | Agreement 2 | Check | No | No | Must be `1` before submission |
| `amended_from` | Amended From | Link → Loan Request | No | Yes | System field — only present on amendments |

### `loan_account_type` Select Options

```
IDF (Institute Development Fund)
PDF (Personal Development Fund)
DPF (Department Provisional Fund)
SWF (Staff Welfare Fund)
```

### Agreement Checkbox Labels

- **Agreement 1:** "I Agree to repay the loan upon receipt and realization of the said project funds in the R&D Section."
- **Agreement 2:** "In case of non-receipt of funds till the end of current financial year, I authorize recovery from any dues payable to me by the institute."

---

## 2. Fund Breakup Child Table — `loan_amount_accounthead_breakup`

Each row in the Fund Breakup table has:

| Field Name | Label | Frappe Type | Notes |
|---|---|---|---|
| `budget_head` | Account Head | Link → Budget Head | Dropdown — display `budget_head` label, store `name` |
| `account_head_amount` | Amount | **Data** (not Currency) | User types a number. **Must use `parseFloat()`** in JS. Stored as string in DB |

> **Important:** `account_head_amount` is stored as a `Data` field (string). Always parse with `parseFloat(value) || 0` when doing calculations. Do not use a currency-formatted input that strips decimal separators without parsing first.

### Budget Head Options (live from DB)

Always fetch live — do not hardcode:
```
GET /api/resource/Budget Head?fields=["name","budget_head","id"]&limit=50
```

Current records:

| `name` (store this) | `budget_head` (show to user) | `id` |
|---|---|---|
| `h1lhg99vfq` | Overhead | 1 |
| `gu12bngg1u` | Manpower | 2 |
| `gqu3lqj4n5` | Travel | 3 |
| `gn92mb763g` | Contingency | 4 |
| `gikfesrl5i` | Consumable | 5 |
| `f91602nspa` | Equipments | 6 |
| `v7l2glhkuq` | GST | 7 |
| `vnacmhhbu5` | Recurring | 8 |
| `vqcr82fk6f` | Non-Recurring | 9 |

---

## 3. Auto-Calculated Fields

### 3.1 `project_number` — Auto-fill from Project Selection

When the user selects a `project_name`, immediately fetch and fill `project_number`:

```js
// On project_name change:
async function onProjectChange(projectName) {
  if (!projectName) {
    setFieldValue("project_number", "");
    return;
  }
  const res = await frappe.db.get_value("Project Registration", projectName, "project_no");
  setFieldValue("project_number", res?.project_no || "");
}
```

> **Why not `fetch_from`?** The `project_no` field in Project Registration is `hidden: 1`. Frappe's `fetch_from` does not reliably work with hidden fields. Always use an explicit JS/API call.

### 3.2 `loan_amount` — Total Loan Amount

`loan_amount` must be **read-only** and auto-updated whenever the user types in any row's `account_head_amount` or adds/removes a row.

```js
function updateLoanTotal(rows) {
  const total = (rows || []).reduce(
    (sum, row) => sum + (parseFloat(row.account_head_amount) || 0),
    0
  );
  setFieldValue("loan_amount", total);
}

// Trigger on:
// - account_head_amount field change in any row
// - row added to account_head_fund_breakup
// - row removed from account_head_fund_breakup
// - form load / refresh
```

**Examples:**
| Rows | Result |
|---|---|
| Travel: 1000 | loan_amount = 1000 |
| Travel: 1000 + Equipments: 2000 | loan_amount = 3000 |
| Travel: 1000 + Equipments: 2000 + Consumable: 500 | loan_amount = 3500 |
| Row deleted (Travel removed) | loan_amount recalculates from remaining rows |

### 3.3 User Auto-fill (Applicant Details)

When `applicant_webmail` is set (on load, since it's read-only):

```js
const user = await frappe.db.get_value(
  "User", applicant_webmail, ["full_name", "department_name", "designation_name"]
);
// Display full_name wherever applicant name is needed (no separate field)
setFieldValue("applicant_department", user.department_name);
setFieldValue("applicant_designation", user.designation_name);
```

> **Note:** There is no `applicant_name` field in the doctype. To display the applicant's name in the UI, fetch `full_name` from the User record using `applicant_webmail`.

Same applies for `loan_for_webmail_id` → `loan_for_name`, `loan_for_department`, `loan_for_designation`.

---

## 4. Workflow States & Transitions

**Active Workflow:** `loan_workflow_without_copi`

### States

| State | Who Acts |
|---|---|
| `Draft` | Applicant (creator) |
| `Pending PI Approval` | PI (`Permanent Employee` role) |
| `Pending Staff Approval` | RnD Staff (`staff, RnD` role) |
| `Pending HoS Approval` | Head of Section (`Hos, RnD` role) |
| `Pending Dean Approval` | Dean (`Dean, RnD` role) |
| `Approved` | Terminal — read-only |
| `Rejected` | Terminal — read-only |

### Transitions

| From State | Action | Next State | Allowed Role |
|---|---|---|---|
| `Draft` | Submit | `Pending PI Approval` | `All_ProRnd_User` |
| `Draft` | Submit | `Pending Staff Approval` | `Permanent Employee` |
| `Pending PI Approval` | Forward | `Pending Staff Approval` | `Permanent Employee` |
| `Pending Staff Approval` | Forward | `Pending HoS Approval` | `staff, RnD` |
| `Pending Staff Approval` | Put Back | `Pending PI Approval` | `staff, RnD` |
| `Pending HoS Approval` | Forward | `Pending Dean Approval` | `Hos, RnD` |
| `Pending HoS Approval` | Put Back | `Pending Staff Approval` | `Hos, RnD` |
| `Pending Dean Approval` | Approve | `Approved` | `Dean, RnD` |
| `Pending Dean Approval` | Reject | `Rejected` | `Dean, RnD` |
| `Pending Dean Approval` | Put Back | `Pending HoS Approval` | `Dean, RnD` |

> **Draft → Submit note:** `All_ProRnd_User` goes to `Pending PI Approval` (non-PI applicants need PI to forward). `Permanent Employee` (who is the PI) skips PI approval and goes directly to `Pending Staff Approval`.

---

## 5. API Reference

All custom endpoints:
```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.<function_name>
Content-Type: application/x-www-form-urlencoded
Authorization: token <api_key>:<api_secret>   OR   session cookie
```

---

### 5.1 Get Field Metadata + Prefill Data

Call this first to render the form dynamically.

```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.get_loan_request_fields

Params:
  doc_name: string  (optional — pass existing name to prefill for editing)
```

**Response:**
```json
{
  "fields": [ { "fieldname": "...", "label": "...", "fieldtype": "...", ... } ],
  "prefill_data": { "self_other": "Self", "applicant_webmail": "user@...", ... },
  "link_options": {
    "budget_head": [ { "value": "gqu3lqj4n5", "label": "Travel", "id": 3 }, ... ],
    "project_name": [ { "value": "PRJ-0001", "label": "Project Title", "project_no": "26RB..." }, ... ]
  },
  "child_table_meta": {
    "account_head_fund_breakup": {
      "doctype": "loan_amount_accounthead_breakup",
      "fields": [ { "fieldname": "budget_head", ... }, { "fieldname": "account_head_amount", ... } ]
    }
  }
}
```

---

### 5.2 Save / Create a Loan Request

```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.save_loan_request

Params:
  doc_data: JSON string — full form data
```

**Payload (doc_data):**
```json
{
  "self_other": "Self",
  "applicant_webmail": "user@institute.ac.in",
  "applicant_department": "Computer Science",
  "applicant_designation": "Project Staff",
  "project_name": "PRJ-REGISTRATION-0001",
  "project_number": "26RBSBESP0391XXLS0010",
  "loan_account_type": "PDF (Personal Development Fund)",
  "agreement_no_1": 1,
  "agreement_no_2": 1,
  "account_head_fund_breakup": [
    { "budget_head": "gqu3lqj4n5", "account_head_amount": "1000" },
    { "budget_head": "f91602nspa", "account_head_amount": "1000" }
  ]
}
```

> Do NOT send `loan_amount` — it is recalculated from rows on the backend automatically.  
> To **update** an existing draft, include `"name": "202604030LOAN00001"` in the payload.

**Response:**
```json
{
  "status": "success",
  "docname": "202604030LOAN00001",
  "loan_amount": 2000
}
```

---

### 5.3 Submit a Loan Request (Draft → next state)

```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.submit_loan_request

Params:
  docname: string
```

**Response:**
```json
{
  "status": "success",
  "message": "Action 'Submit' completed. New State: Pending Staff Approval",
  "docname": "202604030LOAN00001",
  "workflow_state": "Pending Staff Approval",
  "next_actions": []
}
```

---

### 5.4 Get a Loan Request (read existing)

```
GET /api/resource/Loan Request/{name}
```

Returns full document including `account_head_fund_breakup` child rows.

---

### 5.5 Get Available Workflow Actions

```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.get_loan_request_workflow_actions

Params:
  docname: string
```

**Response** (examples by state/role):
```json
// Draft — All_ProRnd_User
["Submit"]

// Draft — Permanent Employee
["Submit"]

// Pending Staff Approval — staff, RnD
["Forward", "Put Back"]

// Pending Dean Approval — Dean, RnD
["Approve", "Reject", "Put Back"]

// Approved / Rejected
[]
```

---

### 5.6 Perform Workflow Action

```
POST /api/method/rndopsapp.rndopsapp.doctype.loan_request.loan_request.perform_loan_request_action

Params:
  docname: string   — e.g. "202604030LOAN00001"
  action:  string   — "Submit" | "Forward" | "Approve" | "Reject" | "Put Back"
```

**Success Response:**
```json
{
  "status": "success",
  "message": "Action 'Forward' completed. New State: Pending HoS Approval",
  "docname": "202604030LOAN00001",
  "workflow_state": "Pending HoS Approval",
  "next_actions": ["Put Back"]
}
```

**Error Response:**
```json
{
  "status": "error",
  "message": "No valid transition found for action 'Forward' from state 'Draft'."
}
```

---

### 5.7 List Loan Requests

```
GET /api/resource/Loan Request
  ?fields=["name","workflow_state","loan_amount","project_name","project_number","applicant_webmail","modified"]
  &filters=[["applicant_webmail","=","user@institute.ac.in"]]
  &order_by=modified desc
  &limit=20
```

---

### 5.8 Get Budget Head Options

```
GET /api/resource/Budget Head?fields=["name","budget_head","id"]&limit=50
```

---

### 5.9 Get Project Options

```
GET /api/resource/Project Registration
  ?fields=["name","project_title","project_no"]
  &limit=500
```

Display `project_title` in dropdown. On selection, store `name` as `project_name` and set `project_number` = `project_no` via JS (see Section 3.1).

---

### 5.10 Fetch User Details (for auto-fill)

```
GET /api/resource/User/{webmail_id}?fields=["full_name","department_name","designation_name"]
```

---

## 6. Form Sections & Rendering Guide

Field display order follows the doctype `field_order`. Render exactly in this order:

```
┌──────────────────────────────────────────────────┐
│  202604030LOAN00001          [Draft badge]        │
├──────────────────────────────────────────────────┤
│  APPLYING FOR  (show only when self_other="Other")│
│    PI Webmail Id   [user search dropdown]         │
│    Name            [readonly — auto from webmail] │
│    Department      [readonly — auto from webmail] │
│    Designation     [readonly — auto from webmail] │
├──────────────────────────────────────────────────┤
│  APPLICANT DETAILS                                │
│    Webmail Id      [readonly — logged-in user]    │
│    Department      [readonly — auto]              │
│    Designation     [readonly — auto]              │
│    (Display full_name fetched from User record)   │
├──────────────────────────────────────────────────┤
│  PROJECT DETAILS                                  │
│    Project Title   [dropdown → Project Reg.]      │
│    Project Number  [readonly — auto via JS]       │
├──────────────────────────────────────────────────┤
│  LOAN DETAILS                                     │
│    Loan From Account Type  [select dropdown]      │
│                                                   │
│    Fund Breakup  [child table]                    │
│    ┌─────┬──────────────────┬──────────────┐      │
│    │ No. │ Account Head     │ Amount       │      │
│    ├─────┼──────────────────┼──────────────┤      │
│    │  1  │ [BudgetH. drop.] │ [number inp] │      │
│    │  2  │ [BudgetH. drop.] │ [number inp] │      │
│    └─────┴──────────────────┴──────────────┘      │
│    [+ Add Row]                                    │
│                                                   │
│    Total Loan Amount  ₹2,000  [readonly — auto]   │
├──────────────────────────────────────────────────┤
│  LOAN AGREEMENTS                                  │
│    ☑ I Agree to repay the loan...                 │
│    ☑ In case of non-receipt of funds...           │
├──────────────────────────────────────────────────┤
│                          [Submit]  ← Draft only   │
└──────────────────────────────────────────────────┘
```

---

## 7. Frontend Validations (client-side, before Submit)

| Check | Error Message |
|---|---|
| `account_head_fund_breakup` has at least 1 row | "Please add at least one fund breakup row." |
| `loan_amount > 0` | "Total Loan Amount must be greater than zero." |
| `agreement_no_1 == 1` | "Please accept all loan agreements before submitting." |
| `agreement_no_2 == 1` | "Please accept all loan agreements before submitting." |
| `project_name` is set | "Project Title is required." |
| `loan_account_type` is set | "Loan From Account Type is required." |
| No row has empty `account_head_amount` | "Please enter an amount for all fund breakup rows." |

---

## 8. Pending Task Page Integration

### Card display fields

```
Title:      {name}  (e.g. 202604030LOAN00001)
Applicant:  {full_name from applicant_webmail}  |  {applicant_department}
Project:    {project_number}  —  {project_name.project_title}
Amount:     ₹{loan_amount}
State:      {workflow_state}
Modified:   {modified}
```

### Action buttons per state (role-based)

| State | Role | Show Buttons |
|---|---|---|
| `Draft` | Creator | Edit, Submit |
| `Pending PI Approval` | `Permanent Employee` | Forward |
| `Pending Staff Approval` | `staff, RnD` | Forward, Put Back |
| `Pending HoS Approval` | `Hos, RnD` | Forward, Put Back |
| `Pending Dean Approval` | `Dean, RnD` | Approve, Reject, Put Back |
| `Approved` | All | View only |
| `Rejected` | All | View only |

Use `get_loan_request_workflow_actions` to dynamically determine which buttons to show for the current user — do not hardcode role checks in the frontend.

---

## 9. Key Notes for Developers

| # | Rule |
|---|---|
| 1 | `loan_amount` is **always read-only** — never render as editable. It equals the sum of all `account_head_amount` rows. |
| 2 | `account_head_amount` is a **Data field** (string). Always `parseFloat(val) \|\| 0` before arithmetic. |
| 3 | `project_number` **cannot use `fetch_from`** because `project_no` is hidden in Project Registration. Use an explicit API/JS fetch after `project_name` is selected. |
| 4 | **No `applicant_name` field exists.** Fetch `full_name` from `User` record using `applicant_webmail` for display purposes. |
| 5 | `applicant_webmail` is read-only in the form but **must be sent by the frontend** when creating a new document (set it to the logged-in user's email). |
| 6 | `self_other` defaults to `"Self"` and is read-only. The **"Applying For" section** (PI details) must only be rendered when `self_other == "Other"`. |
| 7 | Use `perform_loan_request_action` for all workflow transitions — never call `doc.submit()` directly from the frontend. |
| 8 | Budget Head `name` (random hash) is stored; `budget_head` (e.g. "Travel") is for display only. Always fetch live from Budget Head API. |
