# Commit to Kafka Publish — Disbursal of Consultancy, Honorarium & Travel
**Document:** commit_kafka_publish_doc_priyam
**Author:** Backend Team
**Date:** 2026-03-28 | Updated: 2026-03-30
**Scope:** Disbursal of Consultancy | Disbursal of Honorarium | Travel

---

## 1. Overview

Both Disbursal of Consultancy and Disbursal of Honorarium follow a **two-phase commit pattern**:

- **Phase 1 (Staff):** Fill form → Stage commit payload in DB → Submit for approval
- **Phase 2 (Dean / Ado-RnD):** Review → Approve → Kafka message auto-published

The backend Kafka publish logic is **identical** for both doctypes. The only difference is the field names and form structure.

---

## 2. End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  STAFF SIDE — Form Page                                         │
│                                                                 │
│  Step 1: Fill form and save document                            │
│          POST save_disbursal_of_*_data                          │
│          ↓ document created with workflow_state = "Draft"       │
│          ↓ returns docname                                      │
│                                                                 │
│  Document now appears on Staff's Pending Task page              │
│  (GET get_pending_task?page_name=pending-task)                  │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAFF SIDE — Pending Task Page (staff clicks "Commit")         │
│                                                                 │
│  Step 2: Stage the commit payload in DB       ← COMMIT ACTION  │
│          POST commitPayment.submit_commit_data                  │
│          ↓ creates Kafka Commit Staging record (PENDING_APPROVAL)│
│                                                                 │
│  Step 3: Submit document for approval         ← SAME BUTTON    │
│          POST submit_disbursal_of_*                             │
│          ↓ workflow: Draft → Pending Approval                   │
│                                                                 │
│  NOTE: Steps 2 and 3 are triggered together when staff          │
│        clicks the Commit/Submit button on the pending task page │
└─────────────────────────────────────────────────────────────────┘
                          │
                          ▼  (document disappears from Staff list,
                              appears in Dean / Ado-RnD pending list)
┌─────────────────────────────────────────────────────────────────┐
│  DEAN / ADO-RND SIDE — Pending Task Page                        │
│                                                                 │
│  Step 4: Get available actions                                  │
│          GET get_disbursal_of_*_workflow_actions                │
│          ↓ returns ["Approve", "Reject"]                        │
│                                                                 │
│  Step 5: Approve                                                │
│          POST perform_disbursal_of_*_action { action: "Approve" }│
│          ↓ workflow: Pending Approval → Approved                │
│          ↓ Backend finds Kafka Commit Staging record            │
│          ↓ Publishes to Kafka topic: account-head-commit-events │
│          ↓ Staging record status → PUBLISHED                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Workflow States

| State | docstatus | Actor | Available Actions |
|---|---|---|---|
| `Draft` | 0 | Staff | Submit |
| `Pending Approval` | 0 | Dean / Ado-RnD | Approve, Reject |
| `Approved` | 1 | — | none (Kafka published) |
| `Rejected` | 2 | — | none |

---

## 4. Backend Architecture

### 4.1 Why `frappe.db.set_value` Instead of `doc.save()` / `doc.submit()`

`doc.save()` and `doc.submit()` both call `validate_workflow()` internally. This function filters allowed workflow transitions by the **caller's roles**. API callers (mobile/web app) lack the Frappe desk roles (e.g. "RnD Staff", "Dean") defined in the workflow, so Frappe throws:

```
WorkflowTransitionError: Transition not allowed from X to Draft
```

**Solution:** Write `workflow_state` and `docstatus` directly to DB using `frappe.db.set_value`, which completely bypasses `validate_workflow()`.

### 4.2 Why Kafka Is NOT in the `on_update` Hook

The `check_workflow_and_publish` function in `commitPayment.py` is an `on_update` hook. However, since `frappe.db.set_value` writes directly to the database, it **does not trigger ORM hooks** (`before_save`, `on_update`, etc.). Therefore the Kafka publish must be triggered **explicitly inside `perform_disbursal_of_*_action`** when `next_state == "Approved"`.

### 4.3 Kafka Commit Staging Doctype

The staging doctype `Kafka Commit Staging` acts as a queue between staff commit and Dean approval.

| Field | Description |
|---|---|
| `reference_doctype` | e.g. `"Disbursal of Consultancy"` |
| `reference_name` | The document name (docname) |
| `payload` | JSON string of commit parameters |
| `status` | `PENDING_APPROVAL` → `PUBLISHED` or `FAILED` |

### 4.4 Kafka Message Schema

Published to topic: `account-head-commit-events`

```json
{
  "schemaVersion": "1.0",
  "eventType": "ACCOUNT_HEAD_COMMIT",
  "timestamp": "2026-03-28T10:00:00",
  "data": {
    "transactionCommitNumber": null,
    "projectNumber": "PROJ-2024-001",
    "accountHeadId": 12,
    "transactionReceivedRefNumber": 8,
    "commitDate": "2026-03-28",
    "commitParticular": "Commitment for 202603281C000688",
    "refDetails": null,
    "commitAmount": 50000.0,
    "status": "COMMITTED",
    "frapAppId": "202603281C000688",
    "moduleId": 9,
    "billAmount": null
  }
}
```

**Field sources:**

| Kafka Field | Source |
|---|---|
| `projectNumber` | Resolved from `project_name` via `Project Registration.project_no` |
| `accountHeadId` | Resolved from `budget_head` string via `Budget Head.id` |
| `commitAmount` | `commit_amount` passed to `submit_commit_data` |
| `frapAppId` | docname of the Frappe document |
| `moduleId` | `idx` from `Module Registry Item` where `doctype_name` matches, fallback `7` |
| `commitParticular` | Built from child table `particulars` rows; fallback `"Commitment for {docname}"` |

---

## 5. API Reference

### Base URL Pattern
```
POST /api/method/<endpoint>
Content-Type: application/x-www-form-urlencoded
Authorization: token <api_key>:<api_secret>
```

---

### 5.1 Save Document

#### Disbursal of Honorarium
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.save_disbursal_of_honorarium_data
```

**Request body** (`data` as JSON string):
```json
{
  "webmail_id": "staff@iitg.ac.in",
  "name_of_applicant": "Dr. John Doe",
  "project_name": "PROJECT-REG-001",
  "project_no": "PROJ-2024-001",
  "account_head": "Honorarium",
  "total_amount": 50000,
  "table_weoy": [
    {
      "particulars": "Honorarium for January",
      "amount": 50000
    }
  ]
}
```

#### Disbursal of Consultancy
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy.save_disbursal_of_consultancy_data
```

**Request body** (`data` as JSON string):
```json
{
  "webmail_id": "staff@iitg.ac.in",
  "pi_name": "Dr. John Doe",
  "employee_id": "EMP001",
  "project_title": "Project Title",
  "date_of_registration": "2026-01-01",
  "date_of_completion": "2026-03-31",
  "total_amount_received": 100000,
  "current_balance": 80000,
  "disbursal_project_number": "PROJ-2024-001",
  "details_of_disbursal": [
    {
      "disbursal_employee_student": "Employee",
      "designation": "Professor",
      "disbursal_pdf_no_or_bank_account_no": "PDF-001",
      "disbursal_amount": 50000,
      "web_mail_id": "person@iitg.ac.in",
      "name1": "Person Name",
      "emp_id": "EMP002"
    }
  ]
}
```

> **Consultancy auto-calculated fields (DO NOT send):**
> `total_disbursal_amount`, `total_personal_share`, `total_institute_share`, `idf`, `dpf`, `staff_welfare_fund`, `student_welfare_fund`, `disbursal_personal_share`, `disbursal_institute_share`

**Response (both):**
```json
{ "status": "success", "docname": "202603281C000688" }
```

---

### 5.2 Stage the Commit — **CRITICAL STEP**

Same endpoint for both doctypes.

```
POST /api/method/rndopsapp.rndopsapp.commitPayment.submit_commit_data
```

#### For Disbursal of Honorarium
```json
{
  "doctype": "Disbursal of Honorarium",
  "frapAppId": "202603281H000123",
  "name": "202603281H000123",
  "project_name": "PROJECT-REG-001",
  "commit_amount": 50000,
  "budget_head": "Honorarium",
  "bmr": null,
  "bill_amount": null,
  "refDetails": null
}
```

#### For Disbursal of Consultancy
```json
{
  "doctype": "Disbursal of Consultancy",
  "frapAppId": "202603281C000688",
  "name": "202603281C000688",
  "project_name": "PROJ-2024-001",
  "commit_amount": 50000,
  "budget_head": "Consultancy",
  "bmr": null,
  "bill_amount": null,
  "refDetails": null
}
```

| Parameter | Description |
|---|---|
| `doctype` | Exact doctype string — `"Disbursal of Honorarium"` or `"Disbursal of Consultancy"` |
| `frapAppId` | docname returned from save (becomes `frapAppId` in Kafka message) |
| `name` | Same as `frapAppId` |
| `project_name` | For honorarium: `project_no` field. For consultancy: `disbursal_project_number` field |
| `commit_amount` | For honorarium: `total_amount`. For consultancy: `total_disbursal_amount` |
| `budget_head` | Budget Head name string — must match a record in Budget Head doctype |
| `bmr` | Optional BMR reference |
| `bill_amount` | Optional |
| `refDetails` | Optional — used as `commitParticular` context in Kafka |

**Response:**
```json
{ "status": "success", "message": "Commit payload staged for Kafka publishing upon approval" }
```

> Calling this again for the same `name` **overwrites** the existing staged payload. Idempotent — safe to call on every re-save.

---

### 5.3 Submit for Approval (Staff)

#### Disbursal of Honorarium
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.submit_disbursal_of_honorarium
```

#### Disbursal of Consultancy
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy.submit_disbursal_of_consultancy
```

**Request (both):**
```json
{ "docname": "202603281C000688" }
```

**Response:**
```json
{
  "status": "success",
  "message": "Action 'Submit' completed. New State: Pending Approval",
  "docname": "202603281C000688",
  "workflow_state": "Pending Approval",
  "next_actions": []
}
```

**If already submitted:**
```json
{
  "status": "info",
  "message": "Document is already in state 'Pending Approval'.",
  "workflow_state": "Pending Approval"
}
```

---

### 5.4 Get Workflow Actions (Dean / Ado-RnD)

#### Disbursal of Honorarium
```
GET /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.get_disbursal_of_honorarium_workflow_actions?docname=202603281H000123
```

#### Disbursal of Consultancy
```
GET /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy.get_disbursal_of_consultancy_workflow_actions?docname=202603281C000688
```

**Response:**
```json
["Approve", "Reject"]
```

Returns `[]` if the current user has no allowed actions for the document's current state.

---

### 5.5 Perform Workflow Action — Approve / Reject (Dean / Ado-RnD)

#### Disbursal of Honorarium
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_honorarium.disbursal_of_honorarium.perform_disbursal_of_honorarium_action
```

#### Disbursal of Consultancy
```
POST /api/method/rndopsapp.rndopsapp.doctype.disbursal_of_consultancy.disbursal_of_consultancy.perform_disbursal_of_consultancy_action
```

**Request:**
```json
{
  "docname": "202603281C000688",
  "action": "Approve"
}
```

**Response on Approve:**
```json
{
  "status": "success",
  "message": "Action 'Approve' completed. New State: Approved",
  "docname": "202603281C000688",
  "workflow_state": "Approved",
  "next_actions": []
}
```

**Response on Reject:**
```json
{
  "status": "success",
  "message": "Action 'Reject' completed. New State: Rejected",
  "docname": "202603281C000688",
  "workflow_state": "Rejected",
  "next_actions": []
}
```

> When `action = "Approve"` the backend automatically:
> 1. Finds all `Kafka Commit Staging` records for this document with status `PENDING_APPROVAL` or `FAILED`
> 2. Publishes each one to Kafka topic `account-head-commit-events`
> 3. Updates staging record status to `PUBLISHED` (or `FAILED` on error)
>
> **No extra frontend call is needed for Kafka publishing.**

---

## 6. Backend Code Locations

| File | Purpose |
|---|---|
| `rndopsapp/doctype/disbursal_of_honorarium/disbursal_of_honorarium.py` | Honorarium save, submit, perform action, workflow actions |
| `rndopsapp/doctype/disbursal_of_consultancy/disbursal_of_consultancy.py` | Consultancy save, submit, perform action, workflow actions |
| `rndopsapp/commitPayment.py` | `submit_commit_data` — generic staging function for all doctypes |
| `rndopsapp/kafka/producer/reimbursement/producer.py` | `publish_commit()` — sends to Kafka broker |
| `rndopsapp/kafka/producer/reimbursement/mapper.py` | `AccountHeadCommitMapper` — maps Frappe doc → DTO |
| `rndopsapp/kafka/producer/reimbursement/dto.py` | `AccountHeadCommitDTO` — Kafka message data structure |
| `rndopsapp/kafka/producer/reimbursement/validator.py` | Validates DTO before publishing |

---

## 7. Kafka Publish Internal Flow

When `perform_disbursal_of_*_action` reaches `next_state == "Approved"`:

```
perform_disbursal_of_*_action(docname, "Approve")
  │
  ├── frappe.db.set_value → workflow_state = "Approved", docstatus = 1
  │
  └── [Kafka block]
        │
        ├── query: Kafka Commit Staging WHERE reference_name = docname
        │          AND status IN ("PENDING_APPROVAL", "FAILED")
        │
        └── for each staging record:
              │
              ├── parse payload JSON
              │
              └── kafka_publish_commit(
                      doc, commit_amount, budget_head,
                      project_name, bmr, bill_amount,
                      frap_app_id, ref_details
                  )
                    │
                    ├── AccountHeadCommitMapper.map_to_event()
                    │     ├── resolve_budget_head_id(budget_head) → accountHeadId
                    │     ├── get_project_number(project_name) → projectNumber
                    │     ├── get_module_id(doctype) → moduleId
                    │     └── builds AccountHeadCommitDTO
                    │
                    ├── AccountHeadCommitValidator.validate(dto)
                    │
                    └── publish_message(topic="account-head-commit-events", payload)
                          │
                          ├── SUCCESS → staging.status = "PUBLISHED"
                          └── FAILURE → staging.status = "FAILED"
                                        staging.error_message = <reason>
```

---

## 8. Troubleshooting

### Kafka not publishing after Dean Approval

**Check 1 — Was `submit_commit_data` called by the frontend?**

Go to Frappe Desk → `Kafka Commit Staging` list. Filter by `reference_name = <docname>`.
- If **no record exists** → Frontend never called `submit_commit_data`. Frontend fix required.
- If **record exists with status `PENDING_APPROVAL`** → `perform_disbursal_of_*_action` did not find it. Check doctype/name mismatch.
- If **record exists with status `FAILED`** → Kafka broker issue. Check `error_message` field on the record.
- If **record exists with status `PUBLISHED`** → Kafka published successfully. Check the consumer/ledger service.

**Check 2 — Frappe Error Log**

Go to Frappe Desk → Error Log. Search for titles:
- `Consultancy Kafka - No Staging Record`
- `Consultancy Kafka Publish Failed`
- `Process Staged Commit Error`
- `Data Pipeline Error`

**Check 3 — Was bench restarted after code changes?**
```bash
bench restart
```

### Workflow transition error

Symptom: `perform_disbursal_of_*_action` returns `{"status": "error", "message": "No valid transition found for action '...' from state '...'"}`

Cause: The `action` string sent from frontend doesn't match the action name in the Frappe Workflow definition.

Fix: Call `get_disbursal_of_*_workflow_actions` first and use the exact string returned.

---

## 9. Frontend Implementation Checklist

### Staff Side — Form Page
- [ ] Call `save_disbursal_of_*_data` → store returned `docname`
- [ ] Document is now in `Draft` state — appears in Staff's Pending Task list

### Staff Side — Pending Task Page (on "Commit" button click)
- [ ] Call `submit_commit_data` with `doctype`, `frapAppId=docname`, `name=docname`, `project_name`, `commit_amount`, `budget_head`
- [ ] Then call `submit_disbursal_of_*` with `docname`
- [ ] **Both calls happen together on the same Commit button click**
- [ ] Show success/info/error based on `status` field in response
- [ ] On success: document moves to `Pending Approval` — remove from staff's list

### Dean / Ado-RnD Side — Pending Task Page
- [ ] Call `get_disbursal_of_*_workflow_actions` to get available action buttons
- [ ] On "Approve" button click, call `perform_disbursal_of_*_action` with `docname` and `action: "Approve"`
- [ ] Handle `workflow_state` in response to update UI
- [ ] No Kafka call needed — backend handles it automatically on Approve
- [ ] On success: document moves to `Approved` — remove from Dean's list

---

## 10. Key Rules

1. **Stage before submit, both on the Commit button** — The staff's Pending Task page Commit button must call `submit_commit_data` first, then `submit_disbursal_of_*`. If you submit without staging, no `Kafka Commit Staging` record exists when Dean approves and Kafka will silently do nothing. This is the most common cause of missing Kafka messages.

2. **`budget_head` must match exactly** — The string passed as `budget_head` must match a record name or `budget_head` field in the `Budget Head` doctype. Wrong string = `accountHeadId = null` in Kafka = validation failure.

3. **`project_name` is the Project Registration document name** — Not the display title. For consultancy, use the value of the `disbursal_project_number` field. For honorarium, use the `project_no` field value.

4. **Re-staging is safe** — Calling `submit_commit_data` again for the same document overwrites the existing `PENDING_APPROVAL` staging record. Safe to call on every save.

5. **Kafka fires once** — The staging record moves to `PUBLISHED` after the first successful publish. Re-approving (if ever needed) will find no `PENDING_APPROVAL` record and skip Kafka — preventing duplicate messages.

---

## 11. Travel — Complete Commit-to-Kafka Flow

### 11.1 Overview

Travel follows the same two-phase commit pattern as Consultancy and Honorarium, with one key difference in the workflow: Travel has a **multi-level approval chain** before reaching Dean. RnD Staff (`staff, RnD` role) sits in the middle of this chain — their Forward action is the **commit point**.

**Commit point:** When `staff, RnD` clicks "Forward" on the Pending Task page (from `Pending Staff Approval` → `Pending HoS Approval`), they must stage the commit data.

### 11.2 Travel Workflow States

| State | Actor / Role | Action(s) Available |
|---|---|---|
| `Draft` | Applicant (various roles) | Submit |
| `Pending PI Approval` | PI | Forward, Put Back |
| `Pending Head Approval` | head_approver_1 | Forward, Put Back |
| `Pending Mentor Approval` | Mentor | Put Back |
| `Pending Staff Approval` | staff, RnD | **Forward** ← commit point, Put Back, Put Back |
| `Pending HoS Approval` | Hos, RnD | Forward, Put Back |
| `Pending Dean Approval` | Dean, RnD | **Approve** ← Kafka fires here, Reject, Put Back |
| `Pending Associate Dean` | Ado_RnD | **Approve** ← Kafka fires here, Reject |
| `Approved` | — | none (Kafka published) |
| `Rejected` | — | none |

### 11.3 End-to-End Flow for Travel

```
┌──────────────────────────────────────────────────────────────────┐
│  APPLICANT — Form Page                                           │
│                                                                  │
│  Step 1: Fill form and save                                      │
│          POST travel.save_travel (doc_data as JSON string)       │
│          ↓ returns { status, docname }                           │
│          ↓ workflow_state = "Draft"                              │
│                                                                  │
│  Step 2: Submit for workflow                                     │
│          POST travel.perform_travel_action                       │
│          { docname, action: "Submit" }                           │
│          ↓ Draft → Pending PI Approval (or Pending Head          │
│            Approval / Pending Mentor Approval depending on role) │
└──────────────────────────────────────────────────────────────────┘
                         │
                         ▼  (multi-level approvals: PI → Head → HoS → Staff)
┌──────────────────────────────────────────────────────────────────┐
│  RnD STAFF — Pending Task Page (state: Pending Staff Approval)  │
│                                                                  │
│  Step 3: Stage the commit payload ← COMMIT ACTION               │
│          POST commitPayment.submit_commit_data                   │
│          { doctype: "Travel", frapAppId: docname,                │
│            name: docname, project_name, commit_amount,           │
│            budget_head }                                         │
│          ↓ creates Kafka Commit Staging (PENDING_APPROVAL)       │
│                                                                  │
│  Step 4: Forward for HoS approval  ← SAME BUTTON                │
│          POST travel.perform_travel_action                       │
│          { docname, action: "Forward" }                          │
│          ↓ Pending Staff Approval → Pending HoS Approval         │
└──────────────────────────────────────────────────────────────────┘
                         │
                         ▼  (HoS forwards to Dean)
┌──────────────────────────────────────────────────────────────────┐
│  DEAN / ADO-RND — Pending Task Page                              │
│                                                                  │
│  Step 5: Get available actions                                   │
│          GET travel.get_travel_workflow_actions?docname=...      │
│          ↓ returns ["Approve", "Reject"]                         │
│                                                                  │
│  Step 6: Approve                                                 │
│          POST travel.perform_travel_action                       │
│          { docname, action: "Approve" }                          │
│          ↓ workflow_state → "Approved"                           │
│          ↓ Backend publishes Kafka Commit Staging record         │
│          ↓ Staging record status → PUBLISHED                     │
└──────────────────────────────────────────────────────────────────┘
```

### 11.4 Key Difference From Consultancy/Honorarium

| Aspect | Consultancy / Honorarium | Travel |
|---|---|---|
| Workflow save method | `frappe.db.set_value` (bypasses ORM hooks) | `doc.save()` / `doc.submit()` (fires ORM hooks) |
| `check_workflow_and_publish` fires? | No (db.set_value bypasses it) | Yes (doc.save fires on_update) |
| Explicit Kafka block in perform_action? | Yes (only way it publishes) | Yes (added as safety net + logging) |
| Commit point (who stages commit) | Staff submitting the document | RnD Staff forwarding to HoS |
| Kafka topic | `account-head-commit-events` | `account-head-commit-events` (same) |

### 11.5 Travel API Reference

#### Get Form Fields and Prefill Data
```
GET /api/method/rndopsapp.rndopsapp.doctype.travel.travel.get_travel_fields
GET /api/method/rndopsapp.rndopsapp.doctype.travel.travel.get_travel_fields?doc_name=202603307A000001
```
Returns field metadata, link options, and existing doc data for the form.

#### Get Travel Commit Details (for Pending Task Page UI)
```
GET /api/method/rndopsapp.rndopsapp.doctype.travel.travel.get_travel_commit_details?docname=202603307A000001
```
Returns all commit-relevant fields for rendering the commit form on the Staff Pending Task page.

**Response:**
```json
{
  "docname": "202603307A000001",
  "workflow_state": "Pending Staff Approval",
  "applicant_name": "Dr. Jane Smith",
  "webmail_id": "jane@iitg.ac.in",
  "project_name": "PROJECT-REG-001",
  "project_number": "PROJ-2024-001",
  "total_estimate": 45000.0,
  "budget_head": "Travel Head",
  "travel_head": 1,
  "contingency_head": 0,
  "other_acc_head": 0,
  "specify_other_acc_head": null,
  "do_you_need_advance": "Yes",
  "from_date": "2026-04-10",
  "to_date": "2026-04-13",
  "nature_of_travel": "National",
  "purpose_of_visit": "Conference on AI",
  "module_id": 7
}
```

#### Save Travel Document
```
POST /api/method/rndopsapp.rndopsapp.doctype.travel.travel.save_travel
```
**Request body** (`doc_data` as JSON string):
```json
{
  "webmail_id_travel": "staff@iitg.ac.in",
  "applicant_name_travel": "Dr. Jane Smith",
  "travel_project_title": "PROJECT-REG-001",
  "from_date": "2026-04-10",
  "to_date": "2026-04-13",
  "nature_of_travel": "National",
  "travel_financial_assistance": "Yes",
  "travel_head": 1,
  "total_estimate": 45000,
  "do_you_need_advance": "Yes"
}
```
**Response:** `{ "status": "success", "docname": "202603307A000001" }`

#### Stage Commit Data (RnD Staff commit point)
```
POST /api/method/rndopsapp.rndopsapp.commitPayment.submit_commit_data
```
```json
{
  "doctype": "Travel",
  "frapAppId": "202603307A000001",
  "name": "202603307A000001",
  "project_name": "PROJECT-REG-001",
  "commit_amount": 45000,
  "budget_head": "Travel Head",
  "bmr": null,
  "bill_amount": null,
  "refDetails": null
}
```
> Use `travel_project_title` field value as `project_name`. Use `total_estimate` as `commit_amount`.
> For `budget_head`: use `"Travel Head"` if `travel_head==1`, `"Contingency Head"` if `contingency_head==1`, or `specify_other_acc_head` value if `other_acc_head==1`.

#### Perform Workflow Action (all roles)
```
POST /api/method/rndopsapp.rndopsapp.doctype.travel.travel.perform_travel_action
```
```json
{ "docname": "202603307A000001", "action": "Forward" }
```
or
```json
{ "docname": "202603307A000001", "action": "Approve" }
```
**Response:**
```json
{
  "status": "success",
  "message": "Action 'Approve' completed. New State: Approved",
  "docname": "202603307A000001",
  "workflow_state": "Approved",
  "next_actions": []
}
```

#### Get Workflow Actions
```
GET /api/method/rndopsapp.rndopsapp.doctype.travel.travel.get_travel_workflow_actions?docname=202603307A000001
```
Returns list of action strings the current user can perform on the document.

### 11.6 Frontend Implementation Checklist — Travel

#### Applicant Side — Form Page
- [ ] Call `save_travel` → store returned `docname`
- [ ] Call `perform_travel_action` with `action: "Submit"` → document enters first pending state
- [ ] Document now appears in appropriate approver's Pending Task list

#### RnD Staff — Pending Task Page (state: `Pending Staff Approval`)
- [ ] Call `get_travel_commit_details` to populate commit form UI (project, amount, budget head)
- [ ] On "Forward/Commit" button click:
  - [ ] Call `submit_commit_data` with `doctype="Travel"`, `project_name`, `commit_amount=total_estimate`, `budget_head` (resolved from checkboxes)
  - [ ] Then call `perform_travel_action` with `action: "Forward"`
  - [ ] **Both calls together on the same button click**
- [ ] On success: document leaves Staff list, enters HoS list

#### HoS Side — Pending Task Page (state: `Pending HoS Approval`)
- [ ] Call `get_travel_workflow_actions` to get buttons
- [ ] On "Forward": call `perform_travel_action` with `action: "Forward"`
- [ ] No Kafka staging needed at this step

#### Dean / Ado-RnD Side — Pending Task Page
- [ ] Call `get_travel_workflow_actions` to get `["Approve", "Reject"]` buttons
- [ ] On "Approve": call `perform_travel_action` with `action: "Approve"`
- [ ] **No Kafka call needed** — backend publishes automatically on Approve
- [ ] On success: document moves to `Approved`

### 11.7 Troubleshooting — Travel

| Problem | Likely Cause | Fix |
|---|---|---|
| Kafka not published after Dean Approve | `submit_commit_data` never called by RnD Staff frontend | Check `Kafka Commit Staging` list for this docname — if empty, frontend fix needed |
| `No valid transition` error | Wrong `action` string sent | Call `get_travel_workflow_actions` first, use exact returned string |
| `No Staging Record` in Error Log | Staff frontend calls `perform_travel_action("Forward")` but skips `submit_commit_data` | Must call `submit_commit_data` BEFORE `perform_travel_action` on commit button |
| `budget_head` not resolving | Checkbox field value not translated to Budget Head name | Use exact Budget Head doctype record name: `"Travel Head"`, `"Contingency Head"`, or `specify_other_acc_head` value |

Error Log titles to search for Travel:
- `Travel Kafka - No Staging Record`
- `Travel Kafka - Publish Failed`
- `Travel Action Error`
