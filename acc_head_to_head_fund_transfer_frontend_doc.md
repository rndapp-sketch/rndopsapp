# Acc Head to Head Fund Transfer — Frontend Developer Documentation

**Doctype:** `Acc Head to Head Fund Transfer`
**Module:** Rndopsapp
**Naming Pattern:** `{YYYY}{MM}H2H{DD}{####}` — e.g. `202608H2H220001`
**Submittable:** Yes (`is_submittable: 1`)
**Active Workflow:** `h2h_workflow`
**Controller:** `rndopsapp/rndopsapp/doctype/acc_head_to_head_fund_transfer/acc_head_to_head_fund_transfer.py`

Purpose: a PI / project staff member requests that a sanctioned amount be moved from
one project account head (budget head) to another within the same project.

---

## 1. Field Reference

| Field Name | Label | Type | Required | Read Only | Notes |
|---|---|---|---|---|---|
| `h2h_app_webmail` | Applicant Webmail | Link → User | **Yes** | No | Frontend sets this to the logged-in user on create; server falls back to `frappe.session.user` |
| `h2h_app_name` | Applicant Name | Data | No | Yes | Server-derived from `User.full_name` |
| `h2h_app_designation` | Designation | Data | No | Yes | Server-derived (`Designation_prornd.designation_prornd`) |
| `h2h_dept` | Department | Data | No | Yes | Server-derived (`Department_prornd.dept_name`) |
| `h2h_app_category` | Applicant Category | Data | No | Yes | Server-derived (`EmployeeClass_prornd.empclass_name`) |
| `h2h_proj_code` | Project Code | Link → Project Registration | **Yes** | No | Store the PR `name`; the API also accepts a `project_no` and resolves it |
| `h2h_proj_num` | Project Number | Data | No | Yes | Server-derived from `Project Registration.project_no` |
| `h2h_proj_title` | Project Title | Small Text | No | Yes | Server-derived |
| `h2h_pi_webmail` | PI Webmail | Link → User | No | Yes | Server-derived from the project's `pi_webmail` |
| `h2h_transfer_from` | Account Head to Transfer From | Link → Budget Head | **Yes** | No | Store `Budget Head.name`, display `budget_head` |
| `h2h_transfer_to` | Account Head to Transfer To | Link → Budget Head | **Yes** | No | Must differ from `h2h_transfer_from` |
| `h2h_amount` | Amount to Transfer | Currency | **Yes** | No | Must be `> 0` |
| `h2h_amount_in_words` | Amount in Words | Data | No | Yes | Server-derived on save |
| `h2h_justification` | Justification for Transfer | Small Text | **Yes** | No | Free text |
| `h2h_supporting_document` | Supporting Document | Attach | No | No | File URL from `/api/method/upload_file` |
| `h2h_remarks` | Remarks | Small Text | No | No | Free text |
| `workflow_state` | Workflow State | Data | No | Yes | Written only by the workflow endpoints |
| `amended_from` | Amended From | Link → Acc Head to Head Fund Transfer | No | Yes | System field, amendments only |

**List view columns:** `h2h_app_webmail`, `h2h_proj_num`, `h2h_transfer_from`, `h2h_transfer_to`, `h2h_amount`
**Standard filters:** `h2h_app_webmail`, `h2h_proj_code`, `workflow_state`
**Title field:** `h2h_proj_num`

> **Read-only fields are derived server-side in `validate()`.** Anything you send for
> `h2h_app_name`, `h2h_dept`, `h2h_app_designation`, `h2h_app_category`, `h2h_proj_num`,
> `h2h_proj_title`, `h2h_pi_webmail` or `h2h_amount_in_words` is ignored — only the
> fields in [Section 5.3](#53-save--create-a-transfer-request) are writable.

### Budget Head Options

Always fetch live — do not hardcode. Either use the `link_options` returned by
`get_acc_head_to_head_fund_transfer_fields` (see 5.1), or:

```
GET /api/resource/Budget Head?fields=["name","budget_head","id"]&limit=50
```

Store `name` (an opaque id such as `gqu3lqj4n5`), display `budget_head` (e.g. `Travel`).

---

## 2. Validation Rules (enforced server-side)

| Rule | Message |
|---|---|
| `h2h_transfer_from != h2h_transfer_to` | "The source and destination account heads must be different." |
| `h2h_amount > 0` | "Amount to Transfer must be greater than zero." |
| `h2h_app_webmail`, `h2h_proj_code`, `h2h_transfer_from`, `h2h_transfer_to`, `h2h_amount`, `h2h_justification` are mandatory | Standard Frappe mandatory-field error |

`save_acc_head_to_head_fund_transfer_data` returns `{"status": "error", "message": ...}`
rather than raising, so surface `message` directly in the UI.

> There is **no** server-side check that the source head actually holds the requested
> amount. Use `get_project_account_heads` (5.2) to show sanctioned/received figures and
> warn the user before they submit.

---

## 3. Frontend Behaviour

### 3.1 Applicant auto-fill

On create, set `h2h_app_webmail` to the logged-in user, then call
`get_applicant_details` and populate the four read-only display fields. The server
recomputes them on save regardless — this is purely for display.

```js
const { message } = await frappe.call({
  method: `${PREFIX}.get_applicant_details`,
  args: { user_email: frappe.session.user },
});
// message = { h2h_app_name, h2h_dept, h2h_app_designation, h2h_app_category }
```

### 3.2 Project auto-fill

When `h2h_proj_code` changes, fetch `project_no`, `project_title` and `pi_webmail` from
Project Registration and display them. Do not rely on `fetch_from` — these are plain
read-only Data fields resolved by the controller.

### 3.3 Account head selection

1. On project selection, call `get_project_account_heads` (5.2) and use the returned
   `account_heads` to show what is sanctioned/received per head.
2. Filter `h2h_transfer_to` to exclude the currently selected `h2h_transfer_from` (and
   vice versa) — the server rejects a match anyway, but filtering avoids the round trip.

### 3.4 Amount in words

`h2h_amount_in_words` is computed on save. To show it live while the user types, call
`get_amount_in_words` (5.8).

---

## 4. Workflow States & Transitions

**Active Workflow:** `h2h_workflow` (`workflow_state_field: workflow_state`, no email alerts)
**Reproducible via:** `bench --site <site> execute rndopsapp.rndopsapp.create_h2h_workflow.execute`

### States

| State | docstatus | Editable by | Who Acts |
|---|---|---|---|
| `Draft` | 0 | `Permanent Employee` | Applicant / PI |
| `Pending Staff Approval` | 0 | `staff, RnD` | R&D Staff |
| `Pending HoS Approval` | 0 | `Hos, RnD (Head of Section, RnD)` | Head of Section |
| `Pending Dean Approval` | 0 | `Dean, RnD` | Dean |
| `Approved` | **1** | `Administrator` | Terminal — document is submitted |
| `Rejected` | 0 | `Administrator` | Terminal |

### Transitions

| From State | Action | Next State | Allowed Role |
|---|---|---|---|
| `Draft` | Submit | `Pending Staff Approval` | `Permanent Employee` |
| `Pending Staff Approval` | Forward | `Pending HoS Approval` | `staff, RnD` |
| `Pending HoS Approval` | Forward | `Pending Dean Approval` | `Hos, RnD (Head of Section, RnD)` |
| `Pending Dean Approval` | Approve | `Approved` | `Dean, RnD` |
| `Pending Dean Approval` | Reject | `Rejected` | `Dean, RnD` |

New documents are created in `Draft` (field default, also enforced in `before_insert`).

> The `Editable by` column is the workflow's `allow_edit` role, which governs **desk**
> editing only. `save_acc_head_to_head_fund_transfer_data` saves with
> `ignore_permissions=True`, so portal edits are not blocked by it — enforce your own
> "editable only in Draft, only by the applicant" rule in the frontend.

> **Only `Permanent Employee` can Submit from Draft.** A project-staff applicant
> (`All_ProRnd_User`) cannot move their own request forward — the PI must submit it.
> `get_..._workflow_actions` returns `[]` for such a user in Draft, and
> `submit_...` returns a `status: "error"` explaining this rather than force-submitting.
> If applicants should be able to submit for themselves, add a
> `Draft / Submit / Pending Staff Approval / All_ProRnd_User` row (or a `Pending PI
> Approval` state) in `create_h2h_workflow.py` and re-run it.

> **No Put Back transitions exist.** An approver can only Forward, Approve or Reject;
> nothing can be sent back down the chain. Render put-back UI only after such rows are added.

> **`Rejected` carries docstatus 0, not 2.** A rejected request stays a draft-status
> document (still editable/deletable) rather than a cancelled one — treat it as terminal
> in the UI based on `workflow_state`, not `docstatus`.

Like the other application doctypes, transitions are written directly via
`frappe.db.set_value` so API callers without desk roles are not blocked by
`validate_workflow`. `perform_...action` still checks that the requested action is one
the caller's roles actually allow from the current state.

---

## 5. API Reference

All custom endpoints live on the controller module:

```
POST /api/method/rndopsapp.rndopsapp.doctype.acc_head_to_head_fund_transfer.acc_head_to_head_fund_transfer.<function_name>
Content-Type: application/x-www-form-urlencoded
Authorization: token <api_key>:<api_secret>   OR   session cookie
```

Below, `PREFIX` = `rndopsapp.rndopsapp.doctype.acc_head_to_head_fund_transfer.acc_head_to_head_fund_transfer`.

---

### 5.1 Get Field Metadata + Prefill Data

Call this first to render the form dynamically.

```
POST /api/method/{PREFIX}.get_acc_head_to_head_fund_transfer_fields

Params:
  doc_name: string  (optional — Project Registration name OR project_no, to prefill project info)
  docname:  string  (optional — an existing transfer, to prefill for editing)
```

**Response:**
```json
{
  "fields": [ { "fieldname": "h2h_amount", "label": "Amount to Transfer", "fieldtype": "Currency",
                "mandatory": 1, "read_only": 0, "depends_on_eval": null, "...": "..." } ],
  "prefill_data": {
    "h2h_app_webmail": "user@iitg.ac.in",
    "h2h_app_name": "A N Other",
    "h2h_dept": "Computer Science and Engineering",
    "h2h_app_designation": "Project Staff",
    "h2h_app_category": "Contractual",
    "h2h_proj_code": "2026021801MeiTy000473",
    "h2h_proj_num": "26RBSBESP0391XXLS0010",
    "h2h_proj_title": "…",
    "h2h_pi_webmail": "pi@iitg.ac.in"
  },
  "link_options": {
    "h2h_transfer_from": [ { "value": "gqu3lqj4n5", "label": "Travel" }, "..." ],
    "h2h_transfer_to":   [ { "value": "gqu3lqj4n5", "label": "Travel" }, "..." ],
    "h2h_proj_code":     [ { "value": "2026021801MeiTy000473", "label": "26RBSBESP0391XXLS0010 — Project Title" }, "..." ]
  },
  "related_project_data": {
    "name": "2026021801MeiTy000473",
    "project_no": "26RBSBESP0391XXLS0010",
    "project_title": "…",
    "pi_webmail": "pi@iitg.ac.in",
    "implementation_department": "…"
  }
}
```

Each entry in `fields` carries the usual serialized metadata: `fieldname`, `label`,
`fieldtype`, `options`, `mandatory`, `hidden`, `read_only`, `in_list_view`,
`description`, `default`, `depends_on`, plus the pre-stripped `*_eval` variants for
client-side evaluation.

When `docname` is passed, `prefill_data` is the full existing document.

---

### 5.2 Get Project Account Heads (with amounts)

```
POST /api/method/{PREFIX}.get_project_account_heads

Params:
  project_code: string  (Project Registration name OR project_no)
```

**Response:**
```json
{
  "project": { "name": "2026021801MeiTy000473", "project_no": "26RBSBESP0391XXLS0010",
               "project_title": "…", "pi_webmail": "pi@iitg.ac.in",
               "implementation_department": "…" },
  "account_heads": [
    { "account_head": "Consumable",  "sanctioned_amount": 250000.0, "received_amount": 100000.0 },
    { "account_head": "Travel",      "sanctioned_amount": 150000.0, "received_amount": 50000.0 }
  ]
}
```

- `sanctioned_amount` — summed from the PR's `sanctioned_budget_breakup` (falling back to
  `proposed_budget_breakup`), skipping total rows.
- `received_amount` — summed over the project's non-cancelled `Fund Received` documents'
  `received_amt_breakup` rows.
- `account_head` here is the **free-text head name** stored on the budget breakup rows,
  not a `Budget Head` docname. Match it against the `label` of the Budget Head options
  when correlating with `h2h_transfer_from` / `h2h_transfer_to`.

Throws `Project Registration not found.` for an unresolvable `project_code`.

---

### 5.3 Save / Create a Transfer Request

```
POST /api/method/{PREFIX}.save_acc_head_to_head_fund_transfer_data

Params:
  data: JSON string — form data
```

**Writable fields:** `h2h_app_webmail`, `h2h_proj_code`, `h2h_transfer_from`,
`h2h_transfer_to`, `h2h_amount`, `h2h_justification`, `h2h_supporting_document`,
`h2h_remarks`, `amended_from`. Everything else is ignored.

**Payload:**
```json
{
  "h2h_app_webmail": "user@iitg.ac.in",
  "h2h_proj_code": "2026021801MeiTy000473",
  "h2h_transfer_from": "gikfesrl5i",
  "h2h_transfer_to": "gqu3lqj4n5",
  "h2h_amount": 50000,
  "h2h_justification": "Field visits require additional travel budget.",
  "h2h_supporting_document": "/files/approval.pdf",
  "h2h_remarks": ""
}
```

> To **update** an existing draft, include `"name": "202608H2H220001"` in the payload.

**Response:**
```json
{
  "status": "success",
  "docname": "202608H2H220001",
  "doc": { "name": "202608H2H220001", "h2h_amount_in_words": "INR Fifty Thousand only.", "...": "..." }
}
```

**Error response** (validation failure or exception):
```json
{ "status": "error", "message": "The source and destination account heads must be different." }
```

---

### 5.4 Get One Transfer Request

```
POST /api/method/{PREFIX}.get_acc_head_to_head_fund_transfer

Params:
  docname: string
```

Returns the full document plus three conveniences:

```json
{
  "name": "202608H2H220001",
  "h2h_transfer_from": "gikfesrl5i",
  "h2h_transfer_from_label": "Consumable",
  "h2h_transfer_to": "gqu3lqj4n5",
  "h2h_transfer_to_label": "Travel",
  "workflow_actions": [],
  "...": "..."
}
```

(`GET /api/resource/Acc Head to Head Fund Transfer/{name}` also works, without the labels.)

---

### 5.5 List Transfer Requests

```
POST /api/method/{PREFIX}.list_acc_head_to_head_fund_transfers

Params:
  applicant:      string  (optional — a user email, or "all" for every readable record;
                           defaults to the logged-in user's own records)
  project_code:   string  (optional — PR name or project_no)
  workflow_state: string or JSON array (optional — an array is matched with "in")
  limit:          int     (default 50)
  start:          int     (default 0)
```

**Response:**
```json
{
  "records": [
    {
      "name": "202608H2H220001",
      "h2h_app_webmail": "user@iitg.ac.in",
      "h2h_app_name": "A N Other",
      "h2h_dept": "Computer Science and Engineering",
      "h2h_proj_code": "2026021801MeiTy000473",
      "h2h_proj_num": "26RBSBESP0391XXLS0010",
      "h2h_proj_title": "…",
      "h2h_transfer_from": "gikfesrl5i",
      "h2h_transfer_from_label": "Consumable",
      "h2h_transfer_to": "gqu3lqj4n5",
      "h2h_transfer_to_label": "Travel",
      "h2h_amount": 50000.0,
      "workflow_state": "Pending Staff Approval",
      "docstatus": 0,
      "creation": "2026-08-22 16:53:24",
      "modified": "2026-08-22 16:53:24"
    }
  ],
  "count": 1
}
```

Ordered by `creation desc`.

---

### 5.5b Approver Inbox — Requests Pending On Me

```
POST /api/method/{PREFIX}.get_pending_acc_head_to_head_fund_transfers

Params:
  limit: int (default 50)
  start: int (default 0)
```

Returns the same record shape as 5.5, restricted to documents sitting in a state the
current user's roles hold a transition out of, plus the states used:

```json
{ "records": [ "..." ], "count": 3, "states": ["Pending Staff Approval"] }
```

Empty (`{"records": [], "count": 0, "states": []}`) for a user with no approver role.

---

### 5.6 Submit

```
POST /api/method/{PREFIX}.submit_acc_head_to_head_fund_transfer

Params:
  docname: string
```

Performs the workflow's `Submit` / `Forward` / `Apply` action when one is available to
the caller — i.e. `Draft → Pending Staff Approval` for a `Permanent Employee`.

```json
{
  "status": "success",
  "message": "Action 'Submit' completed. New State: Pending Staff Approval",
  "docname": "202608H2H220001",
  "workflow_state": "Pending Staff Approval",
  "next_actions": []
}
```

If the caller holds no transition from the current state, the workflow is **not**
bypassed:

```json
{ "status": "error",
  "message": "You are not permitted to submit this request from state 'Draft'. Available actions: none" }
```

Already-submitted documents return `{"status": "success", "message": "Already submitted."}`.

---

### 5.7 Workflow Actions

```
POST /api/method/{PREFIX}.get_acc_head_to_head_fund_transfer_workflow_actions
Params: docname

POST /api/method/{PREFIX}.perform_acc_head_to_head_fund_transfer_action
Params: docname, action
```

`get_...workflow_actions` returns a de-duplicated list of action names the current
user's roles allow from the document's current state — `[]` when the state is terminal
(`Approved` / `Rejected`) or the user holds no transition out of it. Examples:

```json
// Draft — Permanent Employee            ["Submit"]
// Draft — All_ProRnd_User               []
// Pending Staff Approval — staff, RnD   ["Forward"]
// Pending Dean Approval — Dean, RnD     ["Approve", "Reject"]
// Approved / Rejected                   []
```

`perform_...action` rejects an action the caller is not permitted to perform:
`{"status": "error", "message": "You are not permitted to perform 'Approve' from state 'Draft'."}`

`perform_...action` response:
```json
{
  "status": "success",
  "message": "Action 'Forward' completed. New State: Pending Staff Approval",
  "docname": "202608H2H220001",
  "workflow_state": "Pending Staff Approval",
  "next_actions": []
}
```

---

### 5.8 Helpers

```
POST /api/method/{PREFIX}.get_applicant_details
Params: user_email (optional — defaults to the session user)
→ { "h2h_app_name": "...", "h2h_dept": "...", "h2h_app_designation": "...", "h2h_app_category": "..." }

POST /api/method/{PREFIX}.get_amount_in_words
Params: amount, currency (optional)
→ "INR Fifty Thousand only."
```

---

### 5.9 Delete

```
POST /api/method/{PREFIX}.delete_acc_head_to_head_fund_transfer

Params:
  docname: string
```

Drafts only. A submitted document returns
`{"status": "error", "message": "Cancel the submitted request before deleting it."}`.

---

## 6. Permissions

**Full create/read/write/submit/delete** — applicant-side roles:
`System Manager`, `All_ProRnd_User`, `Independent Researcher`, `Inspired Faculty`,
`Ado_RnD`, `Permanent Employee`

**Read/write/submit (no create, no delete)** — approver roles from the workflow:
`staff, RnD`, `Hos, RnD (Head of Section, RnD)`, `Dean, RnD`

There is no `permission_query_conditions` entry for this doctype in `hooks.py` yet, so
delegated-user scoping (as applied to Temporary Advance, Loan Request, etc.) does **not**
apply here. `list_acc_head_to_head_fund_transfers` defaults to the caller's own records,
which covers the common portal case.

---

## 7. Project Linkage

The doctype is registered in `rndopsapp/rndopsapp/api.py`:

- `_DOCTYPE_PR_MAP` → `("h2h_proj_code", "link")` — so
  `lookup_project_from_application("Acc Head to Head Fund Transfer", docname)` and
  `get_pr_link_map()` resolve it.
- `_PROJECT_NO_SYNC_MAP` → `h2h_proj_num` is refreshed via `h2h_proj_code` whenever a
  `Project Registration.project_no` is edited.

---

## 8. Deployment Notes

```
bench --site <site> migrate
```

`h2h_amount` changed from `Data` to `Currency` and the two account head fields changed
from option-less `Select` to `Link → Budget Head`, so any pre-existing rows created
during doctype scaffolding should be checked (or deleted) after migrating.

The `h2h_workflow` record already exists on `prornd.local`. On any other site, create it
with:

```
bench --site <site> execute rndopsapp.rndopsapp.create_h2h_workflow.execute
```

That script deletes and recreates `h2h_workflow` from scratch (and deactivates any other
active workflow on this doctype), so it is also the place to edit states/transitions —
change the `H2H_STATES` / `H2H_TRANSITIONS` tables and re-run.

Not yet built: Kafka producer/consumer wiring, print format, and a
`permission_query_conditions` entry in `hooks.py` for delegated-user scoping.
