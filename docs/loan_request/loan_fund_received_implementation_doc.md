# Loan Fund Received — Implementation Design Document

**Status:** Pre-implementation — for review before coding begins  
**Author:** Backend Team  
**Date:** 2026-04-06

---

## 1. Overview

When a Loan Request is **Approved by Dean**, the Misc. Staff (RnD Miscellaneous role) needs to record the actual receipt of funds from the accounts system. This is done via a new **Loan Fund Received** form — pre-filled from the approved Loan Request — which follows the same Kafka + deposit slip flow as regular Fund Received.

**Key difference from regular Fund Received:**
- Regular Fund Received → created by Permanent Employee (PI) from scratch
- Loan Fund Received → created automatically when Loan Request is Approved, pre-filled, and appears in Misc. Staff's pending task queue

---

## 2. Full Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  LOAN REQUEST (existing doctype)                                 │
│                                                                  │
│  Draft → Pending PI → Pending Staff → Pending HoS →             │
│  Pending Dean → ★ APPROVED ★                                     │
│                     │                                            │
│   perform_loan_request_action("Approve") fires                   │
│   → on_loan_request_approved(doc) hook called                    │
│                     │                                            │
│       ┌─────────────▼──────────────────┐                        │
│       │  AUTO-CREATE Loan Fund Received │                        │
│       │  (status: Pending Misc. Staff  │                        │
│       │   Approval)                     │                        │
│       │                                │                        │
│       │  Pre-filled from Loan Request: │                        │
│       │  - project_name                │                        │
│       │  - project_number              │                        │
│       │  - loan_amount                 │                        │
│       │  - loan_account_type           │                        │
│       │  - fund_breakup rows           │                        │
│       │  - loan_request_ref = LR name  │                        │
│       └─────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  get_pending_task()                                              │
│  → Loan Fund Received is registered in Module Registry           │
│  → RnD Miscellaneous role sees "Pending Misc. Staff Approval"    │
│  → Card appears in pending task page                            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  MISC. STAFF opens Loan Fund Received from pending task          │
│                                                                  │
│  Pre-filled form shows:                                          │
│  - Project name + number (from Loan Request)                    │
│  - Total loan amount                                             │
│  - Fund breakup table (copied from Loan Request rows)           │
│  - Loan account type                                             │
│                                                                  │
│  Staff fills in additional fields:                               │
│  - bank_account (IITG account number)                           │
│  - received_amt_breakup (budget breakup for Fund Received)      │
│  - fund_transactions (transaction details - UTR, date, amount)  │
│                                                                  │
│  Staff clicks FORWARD                                            │
│  → perform_loan_fund_received_action("Forward")                  │
│  → Publishes to Kafka (Fund Received topic)                     │
│  → workflow_state → "PENDING_APPROVAL"                          │
└──────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────────┐
          │ SAME AS FUND RECEIVED FROM HERE            │
          ▼                                            │
┌──────────────────────────┐                          │
│  PENDING_APPROVAL        │                          │
│  (System Manager /       │                          │
│   External Accounts App) │                          │
│                          │                          │
│  → Approve               │                          │
│  → Pending Misc. Staff   │                          │
│    Approval              │                          │
│    (Deposit Slip Pending)│                          │
└────────────┬─────────────┘                          │
             │                                        │
             ▼                                        │
┌──────────────────────────────────┐                  │
│  Pending Misc. Staff Approval    │                  │
│  (Deposit Slip Pending)          │                  │
│                                  │                  │
│  Staff action: Generate Deposit  │                  │
│  Slip → creates deposit slip doc │                  │
│  → workflow_state →              │                  │
│    Pending HoS Approval          │                  │
└────────────┬─────────────────────┘                  │
             │                                        │
             ▼                                        │
┌──────────────────────────┐                          │
│  Pending HoS Approval    │                          │
│  → Approve → Approved    │                          │
│  → Put Back              │                          │
└────────────┬─────────────┘                          │
             │                                        │
             ▼                                        │
┌──────────────────────────┐                          │
│  Approved                │                          │
│  → Verify (RnD Accounts) │                          │
│  → Fund Received ✓       │                          │
└──────────────────────────┘                          │
```

---

## 3. New Doctype — `Loan Fund Received`

### 3.1 Fields

| Field Name | Label | Type | Notes |
|---|---|---|---|
| `loan_request_ref` | Loan Request | Link → Loan Request | Auto-set on creation. Read-only |
| `prjreg_title` | Project | Link → Project Registration | Pre-filled from Loan Request |
| `project_number` | Project Number | Data | Pre-filled. Read-only |
| `loan_account_type` | Loan Account Type | Data | Pre-filled from Loan Request |
| `loan_amount` | Loan Amount | Currency | Pre-filled from Loan Request. Read-only |
| `loan_fund_breakup` | Loan Fund Breakup | Table → `loan_fund_breakup_row` | Copied from Loan Request's `account_head_fund_breakup` |
| `bank_account` | IITG Account Number | Data | Filled by Misc. Staff |
| `fund_received_amt` | Amount Received | Currency | Filled by Misc. Staff |
| `received_amt_breakup` | Received Amount Breakup | Table → same as Fund Received | Budget head breakdown |
| `fund_transactions` | Transaction Details | Table → same as Fund Received | UTR, date, amount |
| `sanction_ref_no` | Sanction Ref No | Link → Fund Sanction | Optional |
| `deposit_slip_status` | Deposit Slip Status | Check | Auto-set when deposit slip created |
| `workflow_state` | Workflow State | Data | Managed by workflow |

### 3.2 Naming

```
autoname: format:{YYYY}{MM}{DD}LFR{#####}
example:  202604060LFR00001
```

### 3.3 Submittable

Yes (`is_submittable: 1`) — same as Fund Received.

---

## 4. Workflow — `loan_fund_received_workflow`

Copy the `fund_received_with_kafka` workflow structure exactly:

| From State | Action | Next State | Allowed Role |
|---|---|---|---|
| `Draft` | *(auto, no manual submit)* | `Pending Misc. Staff Approval` | *(set on creation)* |
| `Pending Misc. Staff Approval` | Forward | `PENDING_APPROVAL` | `RnD Miscellaneous` |
| `Pending Misc. Staff Approval` | Put Back | `Draft` | `RnD Miscellaneous` |
| `PENDING_APPROVAL` | Approve | `Pending Misc. Staff Approval(Deposit Slip Pending)` | `System Manager` |
| `PENDING_APPROVAL` | Put Back | `Pending Misc. Staff Approval` | `RnD Administration` |
| `Pending Misc. Staff Approval(Deposit Slip Pending)` | Generate Deposit Slip | `Pending HoS Approval` | `RnD Miscellaneous` |
| `Pending Misc. Staff Approval(Deposit Slip Pending)` | Put Back | `PENDING_APPROVAL` | `RnD Miscellaneous` |
| `Pending HoS Approval` | Approve | `Approved` | `Hos, RnD` |
| `Pending HoS Approval` | Put Back | `Pending Misc. Staff Approval(Deposit Slip Pending)` | `Hos, RnD` |
| `Approved` | Verify | `Fund Received` | `RnD Accounts` |

> **Note:** The initial state is `Pending Misc. Staff Approval` (not Draft). The document is **auto-created** by the backend when Loan Request is Approved — it never passes through Draft manually.

---

## 5. Backend Implementation Plan

### 5.1 File to create

```
rndopsapp/rndopsapp/doctype/loan_fund_received/
├── __init__.py
├── loan_fund_received.json       ← doctype definition
├── loan_fund_received.py         ← backend logic
├── test_loan_fund_received.py
```

### 5.2 `loan_fund_received.py` — Functions to implement

#### A. `on_loan_request_approved(loan_request_doc)`
Called from `perform_loan_request_action` in `loan_request.py` when `next_state == "Approved"`.

```python
def on_loan_request_approved(loan_request_doc):
    """
    Auto-creates a Loan Fund Received document pre-filled from the approved Loan Request.
    Sets workflow_state = "Pending Misc. Staff Approval" directly.
    """
    # 1. Check if one already exists for this loan request (idempotency)
    existing = frappe.db.get_value(
        "Loan Fund Received",
        {"loan_request_ref": loan_request_doc.name},
        "name"
    )
    if existing:
        return  # Already created, skip

    # 2. Create new Loan Fund Received
    doc = frappe.new_doc("Loan Fund Received")
    doc.loan_request_ref = loan_request_doc.name
    doc.prjreg_title = loan_request_doc.project_name
    doc.project_number = loan_request_doc.project_number
    doc.loan_account_type = loan_request_doc.loan_account_type
    doc.loan_amount = loan_request_doc.loan_amount
    doc.workflow_state = "Pending Misc. Staff Approval"

    # 3. Copy fund breakup rows from Loan Request
    for row in (loan_request_doc.account_head_fund_breakup or []):
        doc.append("loan_fund_breakup", {
            "budget_head": row.budget_head,
            "account_head_amount": row.account_head_amount,
        })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
```

#### B. `get_loan_fund_received_fields(doc_name=None)`
Returns field metadata + prefill data for the frontend form. Same pattern as `get_ta_da_settlement_fields`.

#### C. `save_loan_fund_received(doc_data)`
Saves/updates the form. Only allowed when `workflow_state == "Pending Misc. Staff Approval"`.

#### D. `perform_loan_fund_received_action(docname, action, deposit_slip_data=None)`
Mirrors `perform_fund_received_action`. Key logic:

```python
# When action == "Forward" from "Pending Misc. Staff Approval":
#   → next_state = "PENDING_APPROVAL"
#   → Publish to Kafka using Fund Received producer

if next_state == "PENDING_APPROVAL":
    from rndopsapp.rndopsapp.kafka.producer.fund_received import publish_fund_received
    publish_fund_received(doc)   # Same producer as regular Fund Received

# When action == "Generate Deposit Slip" from "(Deposit Slip Pending)":
#   → Create deposit slip (reuse create_deposit_slip_from_data from fund_received.py)
#   → next_state = "Pending HoS Approval"

if next_state == "Pending HoS Approval" and deposit_slip_data:
    from rndopsapp.rndopsapp.doctype.fund_received.fund_received import create_deposit_slip_from_data
    create_deposit_slip_from_data(deposit_slip_data, doc)
```

#### E. `get_loan_fund_received_workflow_actions(docname)`
Standard pattern — returns role-based available actions.

---

### 5.3 Change to `loan_request.py`

In `perform_loan_request_action`, add the hook call when `next_state == "Approved"`:

```python
if next_state == "Approved":
    # Existing Kafka block...
    # ...

    # NEW: Auto-create Loan Fund Received
    try:
        from rndopsapp.rndopsapp.doctype.loan_fund_received.loan_fund_received import (
            on_loan_request_approved
        )
        doc_fresh = frappe.get_doc("Loan Request", docname)
        on_loan_request_approved(doc_fresh)
        frappe.logger().info(f"[Loan Fund Received] Auto-created for {docname}")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"[Loan Fund Received] Auto-create failed for {docname}")
```

---

### 5.4 Kafka Mapping for Loan Fund Received

The `FundReceivedMapper` reads these specific fields from the doc:

| Mapper reads | Loan Fund Received field | Notes |
|---|---|---|
| `doc.name` | `name` (auto) | → `fundReceivedRefNumberFap` |
| `doc.prjreg_title` | `prjreg_title` | → resolves `projectNumber` via Project Registration |
| `doc.sanction_ref_no` | `sanction_ref_no` | → `sanctionNumber` (optional) |
| `doc.fund_received_amt` | `fund_received_amt` | → `amountReceived` |
| `doc.bank_account` | `bank_account` | → `iitgAccountNumber` |
| `doc.received_amt_breakup` | child table | → `fundBudgetBreakupList` (needs `account_head`, `amount_received`, `b_id`) |
| `doc.fund_transactions` | child table | → `transactionDetailsList` (needs `transaction_number`, `transaction_date`, `amount`) |

> **Important:** The `received_amt_breakup` and `fund_transactions` child tables must use **the same field names** as in Fund Received. The mapper reads them by attribute name directly. Use the same child doctypes as Fund Received or create new ones with identical field names.

---

### 5.5 Module Registry — Register the new doctype

Add `Loan Fund Received` to the `pending-task` Module Registry child table:

```python
# Run once via bench console or migration
registry = frappe.get_doc("Module Registry", "pending-task")
registry.append("doctype_name", {
    "doctype_name": "Loan Fund Received",
    "mod_vis": 16   # next idx
})
registry.save(ignore_permissions=True)
frappe.db.commit()
```

After this, `get_pending_task()` will automatically include `Loan Fund Received` in its results for `RnD Miscellaneous` role users.

---

## 6. API Reference (New Endpoints)

All under: `POST /api/method/rndopsapp.rndopsapp.doctype.loan_fund_received.loan_fund_received.<fn>`

| Endpoint | Params | Purpose |
|---|---|---|
| `get_loan_fund_received_fields` | `doc_name` (optional) | Field metadata + prefill data for form rendering |
| `save_loan_fund_received` | `doc_data` (JSON) | Save staff-filled fields before Forward |
| `perform_loan_fund_received_action` | `docname`, `action`, `deposit_slip_data` (optional) | Execute workflow transition |
| `get_loan_fund_received_workflow_actions` | `docname` | Available actions for current user |

---

## 7. Frontend Integration

### 7.1 Pending Task Card

`get_pending_task` will return:
```json
{
  "doctype": "Loan Fund Received",
  "mod_vis": 16,
  "records": [
    {
      "name": "202604060LFR00001",
      "status": "Pending Misc. Staff Approval",
      "modified": "...",
      "owner": "..."
    }
  ]
}
```

Frontend renders card and on click → opens the Loan Fund Received form.

### 7.2 Two form states (same as Fund Received)

| `status` (workflow_state) | Form to show |
|---|---|
| `Pending Misc. Staff Approval` | Pre-filled form — staff adds bank account, transaction details, budget breakup → Forward |
| `Pending Misc. Staff Approval(Deposit Slip Pending)` | Generate Deposit Slip form — same as Fund Received deposit slip form |

### 7.3 On form open — call `get_loan_fund_received_fields`

```
POST get_loan_fund_received_fields
  doc_name: "202604060LFR00001"

Response:
  prefill_data: {
    loan_request_ref: "202604030LOAN00001",
    prjreg_title: "PRJ-0001",
    project_number: "26RBSBESP0391XXLS0010",
    loan_amount: 5000,
    loan_account_type: "PDF (Personal Development Fund)",
    loan_fund_breakup: [
      { budget_head: "gqu3lqj4n5", account_head_amount: "3000" },
      { budget_head: "f91602nspa", account_head_amount: "2000" }
    ],
    workflow_state: "Pending Misc. Staff Approval"
  }
```

### 7.4 On Forward — call `save` then `perform_action`

```
Step 1: save_loan_fund_received
  doc_data: {
    name: "202604060LFR00001",
    bank_account: "SBI-XXXX",
    fund_received_amt: 5000,
    received_amt_breakup: [...],
    fund_transactions: [...]
  }

Step 2: perform_loan_fund_received_action
  docname: "202604060LFR00001"
  action: "Forward"

→ Backend publishes to Kafka, moves to PENDING_APPROVAL
```

---

## 8. Kafka Payload (what gets published)

Same structure as regular Fund Received:

```json
{
  "schemaVersion": "1.0",
  "eventType": "FUND_RECEIVED",
  "timestamp": "2026-04-06T...",
  "data": {
    "fundReceivedRefNumberFap": "202604060LFR00001",
    "sanctionNumber": null,
    "sanctionLetterNo": null,
    "projectNumber": "26RBSBESP0391XXLS0010",
    "amountReceived": 5000.0,
    "iitgAccountNumber": "SBI-XXXX",
    "depositSlipStatus": false,
    "fundReceivedStatus": "PENDING_APPROVAL",
    "depositeStatusUpdateTime": "2026-04-06T...",
    "fundReceivedStatusUpdateTime": "2026-04-06T...",
    "fundBudgetBreakupList": [
      { "accountHeadId": "3", "amount": 3000.0, "remarks": "" },
      { "accountHeadId": "6", "amount": 2000.0, "remarks": "" }
    ],
    "transactionDetailsList": [
      {
        "uniqueTransactionNumber": "UTR123456",
        "transactionReceivedDate": "2026-04-06",
        "transactionAmount": 5000.0
      }
    ]
  }
}
```

**Kafka Topic:** Same as Fund Received — `TOPIC_FUND_RECEIVED`

---

## 9. Questions to Verify Before Implementation

Please confirm the following before coding starts:

| # | Question | Decision Needed |
|---|---|---|
| 1 | Should `received_amt_breakup` and `fund_transactions` use the **same child doctypes** as Fund Received, or new ones with identical field names? | Same child doctypes preferred (reuses mapper) |
| 2 | Should the Loan Fund Received appear in the **same pending task tab** as Fund Received (same `mod_vis`), or a separate tab? | New tab (mod_vis=16) recommended |
| 3 | What happens if the Loan Request is re-approved after amendment — should a new LFR be created, or the existing one updated? | Idempotency check on `loan_request_ref` suggested |
| 4 | Is `sanction_ref_no` applicable to Loan Fund Received, or should it always be null? | Likely null — loan is internal, not externally sanctioned |
| 5 | Should the deposit slip flow use the same `create_deposit_slip_from_data` function from `fund_received.py`, or a separate one? | Reuse existing function — pass `doc` with `prjreg_title` field |
| 6 | Should `fund_received_amt` be pre-filled from `loan_amount`, or left for Misc. Staff to enter? | Pre-fill recommended but allow edit |
