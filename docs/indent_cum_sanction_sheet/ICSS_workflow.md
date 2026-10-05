# Indent-Cum-Sanction Sheet (ICSS) — Complete Workflow Documentation

## Overview

| Property | Value |
|---|---|
| **Primary DocType** | `Indent Cum Sanction Sheet` |
| **Workflow Name** | `indent_cum_sanction_sheet_workflow` |
| **Backend Module** | `rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet` |
| **Total States** | 15 |
| **Total Transitions** | 30+ |

The ICSS workflow governs the full lifecycle of an Indent-Cum-Sanction Sheet from initial draft through multi-level approval to final PO delivery. Routing decisions are made in Python (not in Frappe's native workflow conditions) to support dynamic role checks and amount-based branching.

---

## 1. Workflow States

| # | State | Docstatus | Edit Role | Description |
|---|---|---|---|---|
| 1 | `Draft` | 0 | `All_ProRnd_User` | Initial state; document is editable |
| 2 | `Pending PI Approval` | 1 | `Permanent Employee` | Awaiting Principal Investigator review |
| 3 | `Pending Mentor Approval` | 1 | `Mentor` | Awaiting Mentor review (IR path) |
| 4 | `Pending Other PI` | 1 | `Other PI` | Awaiting additional PI review |
| 5 | `Pending Head Approval` | 1 | `head_approver_1` | Awaiting Head of Department review |
| 6 | `Pending Staff Approval` | 1 | `staff, RnD` | Awaiting R&D Staff processing |
| 7 | `Pending HoS Approval` | 1 | `Hos, RnD (Head of Section, RnD)` | Awaiting Head of Section review |
| 8 | `Pending Associate Dean` | 1 | `Ado_RnD` | Awaiting Associate Dean (amount ≤ ₹1,00,000) |
| 9 | `Pending Dean Approval` | 1 | `Dean, RnD` | Awaiting Dean (amount > ₹1,00,000) |
| 10 | `Pending PO Generation` | 1 | `staff, RnD` | Staff prepares Purchase Order |
| 11 | `PO Generated` | 1 | `staff, RnD` | PO created and awaiting delivery |
| 12 | `PO Delivered` | 1 | `Administrator` | Signed PO uploaded — terminal state |
| 13 | `Approved` | 1 | `Administrator` | Document fully approved |
| 14 | `Rejected` | 2 | `Administrator` | Workflow cancelled — terminal state |
| 15 | `Put Back` | 1 | `All_ProRnd_User` | Revision requested — document returned |

---

## 2. User Roles and Responsibilities

| Role | Responsibilities |
|---|---|
| `All_ProRnd_User` | Submit new documents from Draft |
| `Permanent Employee` | Review and forward/reject at PI stage |
| `Mentor` | Review IR-path documents |
| `Other PI` | Review documents requiring co-PI approval |
| `head_approver_1` | Head-of-Department level review |
| `staff, RnD` | Process at Staff stage; generate PO; upload Director PDF |
| `Hos, RnD (Head of Section, RnD)` | HoS review; routes by amount to Dean or Associate Dean |
| `Ado_RnD` | Associate Dean — approves amounts ≤ ₹1,00,000 |
| `Dean, RnD` | Dean — approves amounts > ₹1,00,000; marks for Director review |
| `Associate Dean, RND` | Can put-back from Associate Dean state |
| `Administrator` | Manages terminal states (PO Delivered, Approved, Rejected) |
| `System Manager` | Can perform put-back from any eligible state |

---

## 3. Workflow Transitions

### 3.1 Initial Submit (Draft → Next State)

The routing from `Draft` on `Submit` is determined by the **submitting user's roles**, resolved in Python:

```
if user has any of [Permanent Employee, head_approver_1, HoD, System Manager]:
    → Pending Staff Approval
else:
    → Pending PI Approval
```

Alternative initial routes (specific user roles):
| Submitting Role | Next State |
|---|---|
| `All_ProRnd_User` (general) | `Pending PI Approval` |
| `Permanent Employee` / `head_approver_1` / `HoD` | `Pending Staff Approval` (skips PI) |
| Independent Researcher path | `Pending Mentor Approval` |

### 3.2 Pending PI Approval

| Action | Next State | Role Required |
|---|---|---|
| Forward | `Pending Other PI` | `Permanent Employee` |
| Forward | `Pending Staff Approval` | `Permanent Employee` |
| Reject | `Rejected` | `Permanent Employee` |

### 3.3 Pending Mentor Approval

| Action | Next State | Role Required |
|---|---|---|
| Forward | `Pending Head Approval` | `Mentor` |
| Forward | `Pending Staff Approval` | `Mentor` |
| Reject | `Rejected` | `Mentor` |

### 3.4 Pending Other PI

| Action | Next State | Role Required |
|---|---|---|
| Forward | `Pending Head Approval` | `Other PI` |
| Forward | `Pending Staff Approval` | `Other PI` |
| Reject | `Rejected` | `Other PI` |

### 3.5 Pending Head Approval

| Action | Next State | Role Required |
|---|---|---|
| Forward | `Pending Staff Approval` | `head_approver_1` |
| Reject | `Rejected` | `head_approver_1` |

### 3.6 Pending Staff Approval

| Action | Next State | Role Required |
|---|---|---|
| Forward | `Pending HoS Approval` | `staff, RnD` |
| Put Back | `Pending PI Approval` | `staff, RnD` |
| Reject | `Rejected` | `staff, RnD` |

### 3.7 Pending HoS Approval — Amount-Based Routing

Routing from HoS is **determined by approval amount** (Python-side, not Frappe conditions):

```
if approval_amount > ₹1,00,000:
    → Pending Dean Approval
else:
    → Pending Associate Dean
```

| Action | Next State | Condition |
|---|---|---|
| Forward | `Pending Associate Dean` | amount ≤ ₹1,00,000 |
| Forward | `Pending Dean Approval` | amount > ₹1,00,000 |
| Put Back | `Pending Staff Approval` | — |
| Reject | `Rejected` | — |

### 3.8 Pending Associate Dean

| Action | Next State | Role Required |
|---|---|---|
| Approve | `Pending PO Generation` | `Ado_RnD` |
| Put Back | `Pending HoS Approval` | `Associate Dean, RND` |
| Reject | `Rejected` | `Ado_RnD` |

### 3.9 Pending Dean Approval — Director Gate

Before Dean can `Approve`, the system checks the **Director Approval Gate**:

```
if director_approval_required == 1 AND director_signed_pdf is empty:
    BLOCK — throw "Cannot approve: Director-signed PDF not uploaded"
```

| Action | Next State | Role Required | Condition |
|---|---|---|---|
| Approve | `Pending PO Generation` | `Dean, RnD` | Director PDF uploaded (if required) |
| Put Back | `Pending HoS Approval` | `Dean, RnD` | — |
| Reject | `Rejected` | `Dean, RnD` | — |

### 3.10 Pending PO Generation

| Action | Next State | Role Required |
|---|---|---|
| Generate PO | `PO Generated` | `staff, RnD` |

### 3.11 PO Generated → PO Delivered

Triggered by `upload_icss_signed_po()` API — staff uploads signed PO file, state moves to `PO Delivered`.

---

## 4. Approval / Rejection Paths (Flow Diagrams)

### Standard Path (General User)
```
Draft
  └─[Submit]─→ Pending PI Approval
                  └─[Forward]─→ Pending Staff Approval
                                  └─[Forward]─→ Pending HoS Approval
                                                  ├─[amount ≤ 1L]─→ Pending Associate Dean
                                                  │                     └─[Approve]─→ Pending PO Generation
                                                  │                                      └─[Generate PO]─→ PO Generated
                                                  │                                                           └─[Upload]─→ PO Delivered
                                                  └─[amount > 1L]─→ Pending Dean Approval
                                                                        └─[Approve]─→ Pending PO Generation ─→ ...
```

### Short Path (Permanent Employee / HoD)
```
Draft
  └─[Submit]─→ Pending Staff Approval ─→ Pending HoS Approval ─→ ...
```

### Independent Researcher Path
```
Draft
  └─[Submit]─→ Pending Mentor Approval
                  └─[Forward]─→ Pending Head Approval
                                  └─[Forward]─→ Pending Staff Approval ─→ ...
```

### Rejection Path (from any approval stage)
```
Any Approval State
  └─[Reject]─→ Rejected  (docstatus = 2, terminal)
```

### Put-Back Path
```
Pending Staff Approval  ─[Put Back]─→ Pending PI Approval
Pending HoS Approval    ─[Put Back]─→ Pending Staff Approval
Pending Dean Approval   ─[Put Back]─→ Pending HoS Approval
Pending Associate Dean  ─[Put Back]─→ Pending HoS Approval
```

---

## 5. Business Rules and Validations

### 5.1 Approval Amount Resolution

The amount used for all routing decisions depends on `icss_indent_type`:

| Indent Type | Amount Field Used |
|---|---|
| `Repair/ Repleacement` | `icss_repair_grand_total` |
| `Annual Maintenance Contract` | `icss_amc_grand_total` |
| All others | `icss_grand_total` |

**Calculations:**
- `icss_grand_total` = `total_basic_value` + packing + freight + other charges
- `icss_repair_grand_total` = `icss_repair_expenditure` + `icss_repair_other_charges`
- `icss_amc_grand_total` = (`icss_amc_value` + `icss_amc_other_charges`) × (1 + GST%)

### 5.2 Director Approval Threshold

Triggered when Dean marks `send_to_director = 1`. System auto-sets `director_approval_required`.

| Account Head Type | Director Required When |
|---|---|
| Contains "equipment" | amount > ₹10,00,000 (10 lakhs) |
| All other heads | amount > ₹3,00,000 (3 lakhs) |

**Account head detection:** `"equipment" in str(icss_account_head or icss_other_account_head).lower()`

### 5.3 Put-Back Rules

| Current State | Allowed Put-Back Roles | Available Targets |
|---|---|---|
| `Pending PI Approval` | `Permanent Employee`, `head_approver_1`, `HoD`, `System Manager` | Requestor (→ Draft) |
| `Pending Staff Approval` | `staff, RnD`, `System Manager` | PI (→ Pending PI Approval), Requestor (→ Draft) |
| `Pending HoS Approval` | `Hos, RnD`, `System Manager` | Staff, PI, Requestor |
| `Pending Dean Approval` | `Dean, RnD`, `System Manager` | HoS, Staff, PI, Requestor |
| `Pending Associate Dean` | `Ado_RnD`, `System Manager` | HoS, Staff, PI, Requestor |

**Put-Back Target → State Mapping:**

| Target | Lands In |
|---|---|
| Requestor | `Draft` |
| PI | `Pending PI Approval` |
| Staff | `Pending Staff Approval` |
| HoS | `Pending HoS Approval` |

**Put-Back Blocked States:** `PO Delivered`, `PO Generated`, `Pending PO Generation`

**Side-effect:** When put-back from Dean stage, director approval fields are cleared:
- `director_approval_required → 0`
- `send_to_director → 0`
- `director_signed_pdf → ""`

### 5.4 Field-Level Constraints

| Rule | Details |
|---|---|
| Indent type locked after submit | Cannot change `icss_indent_type` once submitted |
| sub_doctype_reference immutable | Cannot update after creation |
| Director gate blocks approval | `director_approval_required = 1` + empty `director_signed_pdf` prevents Dean from approving |
| Mandatory declaration | `check_the_below_declaration` must be checked before submit |

---

## 6. Status Transitions Table (Complete)

| From State | Action | To State | Role | Condition |
|---|---|---|---|---|
| `Draft` | Submit | `Pending PI Approval` | `All_ProRnd_User` | User lacks privileged roles |
| `Draft` | Submit | `Pending Staff Approval` | `All_ProRnd_User` | User has `Permanent Employee`/`HoD`/`head_approver_1` |
| `Draft` | Submit | `Pending Mentor Approval` | `All_ProRnd_User` | IR path |
| `Pending PI Approval` | Forward | `Pending Other PI` | `Permanent Employee` | — |
| `Pending PI Approval` | Forward | `Pending Staff Approval` | `Permanent Employee` | — |
| `Pending PI Approval` | Reject | `Rejected` | `Permanent Employee` | — |
| `Pending Mentor Approval` | Forward | `Pending Head Approval` | `Mentor` | — |
| `Pending Mentor Approval` | Forward | `Pending Staff Approval` | `Mentor` | — |
| `Pending Mentor Approval` | Reject | `Rejected` | `Mentor` | — |
| `Pending Other PI` | Forward | `Pending Head Approval` | `Other PI` | — |
| `Pending Other PI` | Forward | `Pending Staff Approval` | `Other PI` | — |
| `Pending Other PI` | Reject | `Rejected` | `Other PI` | — |
| `Pending Head Approval` | Forward | `Pending Staff Approval` | `head_approver_1` | — |
| `Pending Head Approval` | Reject | `Rejected` | `head_approver_1` | — |
| `Pending Staff Approval` | Forward | `Pending HoS Approval` | `staff, RnD` | — |
| `Pending Staff Approval` | Put Back | `Pending PI Approval` | `staff, RnD` | — |
| `Pending Staff Approval` | Reject | `Rejected` | `staff, RnD` | — |
| `Pending HoS Approval` | Forward | `Pending Associate Dean` | `Hos, RnD` | amount ≤ ₹1,00,000 |
| `Pending HoS Approval` | Forward | `Pending Dean Approval` | `Hos, RnD` | amount > ₹1,00,000 |
| `Pending HoS Approval` | Put Back | `Pending Staff Approval` | `Hos, RnD` | — |
| `Pending HoS Approval` | Reject | `Rejected` | `Hos, RnD` | — |
| `Pending Associate Dean` | Approve | `Pending PO Generation` | `Ado_RnD` | — |
| `Pending Associate Dean` | Put Back | `Pending HoS Approval` | `Associate Dean, RND` | — |
| `Pending Associate Dean` | Reject | `Rejected` | `Ado_RnD` | — |
| `Pending Dean Approval` | Approve | `Pending PO Generation` | `Dean, RnD` | Director PDF present (if required) |
| `Pending Dean Approval` | Put Back | `Pending HoS Approval` | `Dean, RnD` | — |
| `Pending Dean Approval` | Reject | `Rejected` | `Dean, RnD` | — |
| `Pending PO Generation` | Generate PO | `PO Generated` | `staff, RnD` | — |
| `PO Generated` | Upload Signed PO | `PO Delivered` | `staff, RnD` | via `upload_icss_signed_po()` API |

---

## 7. Sub-DocType Synchronization

When an ICSS document is saved, a linked child doctype record is auto-created/updated based on `icss_indent_type`:

| Indent Type | Child DocType Created |
|---|---|
| `Proprietary Purchase with Proprietary certificate from the OEM` | `proprietary_purchase` |
| `Standerdised/ Emergent Purchase` | `standerdized_purchase` |
| `Repair/ Repleacement` | `repair_replacement` |
| `Annual Maintenance Contract` | `AMC` |
| `Rate Contract Purchase` | `Rate Contract` |

**Synced Fields:** `indent_cum_sanction_sheet_id`, `project_ref`, `project_no`, `indent_type`

The `sub_doctype_reference` field on the ICSS stores the created child record's name.

---

## 8. Director Approval Process (Dean Stage Detail)

```
Pending Dean Approval
  │
  ├── Dean checks: does this require Director approval?
  │     (Equipment > ₹10L or Non-Equipment > ₹3L)
  │
  ├── [YES] Dean sets send_to_director = 1
  │           System sets director_approval_required = 1
  │           Staff uploads Director-signed PDF via attach_director_pdf_icss()
  │           Dean can now Approve → Pending PO Generation
  │
  └── [NO]  Dean can Approve directly → Pending PO Generation
```

**Director-related fields:**
- `send_to_director` — Check, set by Dean
- `director_approval_required` — Check, read-only, auto-set
- `director_signed_pdf` — Attach, uploaded by Staff

---

## 9. API Endpoints

| Endpoint | Purpose |
|---|---|
| `get_icss_workflow_actions(docname)` | Get available actions for current user + state |
| `perform_icss_action(docname, action)` | Execute a workflow action |
| `submit_icss(docname)` | Submit from Draft (wrapper for perform_icss_action) |
| `put_back_icss(docname, target, reason)` | Return document to a prior stage |
| `get_available_icss_put_back_actions(docname)` | List available put-back targets for current user |
| `update_send_to_director_icss(docname, send_to_director)` | Dean marks document for Director review |
| `attach_director_pdf_icss(docname, file_url, file_name, file_data)` | Staff uploads Director-signed PDF |
| `get_icss_director_approval_status(docname)` | Get current Director approval status |
| `get_pending_director_uploads_icss()` | List all documents awaiting Director PDF upload |
| `upload_icss_signed_po(docname, file_url, file_name, file_data)` | Upload signed PO → moves to PO Delivered |
| `save_icss_data(data)` | Save parent ICSS document |
| `save_icss_composite_data(data)` | Save parent + child records together |

---

## 10. Kafka Integration (Workflow Events)

A global hook fires on every document `on_update`:

```python
doc_events = {
    "*": {
        "on_update": "rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish"
    }
}
```

`check_workflow_and_publish(doc)`:
- Checks if `doc.workflow_state` matches any `Kafka Commit Staging` record's `trigger_state`
- If matched, publishes commit event to Kafka topic

---

## 11. Legacy Purchase Workflows (Dynamic)

The file `create_workflows.py` auto-generates Frappe workflow objects for purchase sub-doctypes. These share a similar state machine but with Frappe-native condition strings.

**DocTypes covered:**
- `proprietary_purchase` (amount field: `pp_grand_total`)
- `standerdized_purchase` (amount field: `sp_grand_total`)
- `repair_replacement` (amount field: `rr_grand_total`)
- `Direct Purchase` (amount field: `total_estimate`)

**States:** Draft → Pending PI Approval → Pending Other PI → Pending Mentor Approval → Pending HoD Approval → Pending Staff Approval → Pending HoS Approval → Pending Associate Dean / Pending Dean Approval → Pending Director Approval → Approved / Rejected

**Key Differences from ICSS:**
- Uses native Frappe condition strings evaluated at transition time
- `Direct Purchase` has a Consumable/Contingency shortcut: amounts ≤ ₹3,00,000 skip Director, Dean approves directly
- `Standerdized Purchase` skips HoD after Mentor, goes directly to Staff
- All routing conditions check `Project Registration.project_type` for Other PI branching

---

## 12. Sanction Sheet (SS) Workflow

The `sanction_sheet` doctype has its own workflow managed via `perform_sanction_sheet_action()`.

**Special Logic — Final Approval Linking:**

When a Sanction Sheet reaches `SancSheetApproved` and has an `amended_from` chain:
```
sanction_sheet.amended_from → P_11 Form.amended_from → Direct Purchase
    Set Direct Purchase.workflow_state = "SancSheetApproved"
```

This links the SS approval back to the originating Direct Purchase.

---

## 13. Database Dependencies

| Table / DocType | Purpose |
|---|---|
| `tabIndent Cum Sanction Sheet` | Main workflow document |
| `tabWorkflow` | Frappe workflow definitions |
| `tabWorkflow State` | State definitions with docstatus |
| `tabWorkflow Transition` | Transition rules (from/to/action/role/condition) |
| `tabWorkflow Action Master` | Master list of actions |
| `tabWorkflow Status Permission` | Custom permission overrides per state |
| `tabWorkflow Status Permission Item` | Child rows for permission mappings |
| `tabProject Registration` | Looked up for `project_type` (Other PI check) |
| `tabBudget Head` | Account head lookups for Director threshold check |
| `tabKafka Commit Staging` | Trigger states for Kafka publish on workflow events |
| `tabModule Registry Item` | Module ID lookups (moduleId for Kafka payloads) |
| `tabsanction_sheet` | Sanction Sheet — linked via `app_id` to Direct Purchase |
| `tabP_11 Form` | Intermediate linking document for SS amend chain |
| `tabDirect Purchase` | Sub-purchase document; state synced from SS final approval |

---

## 14. Exceptions and Conditional Branches Summary

| Scenario | Handling |
|---|---|
| User submits with `Permanent Employee` role | Skips PI stage entirely → goes to Staff |
| Amount ≤ ₹1,00,000 at HoS | Routes to Associate Dean instead of Dean |
| Amount > ₹1,00,000 at HoS | Routes to Dean |
| Equipment amount > ₹10,00,000 | Dean must get Director signature before approving |
| Non-equipment amount > ₹3,00,000 | Dean must get Director signature before approving |
| Director PDF missing when required | System throws error, blocks Dean's Approve action |
| Put-back from Dean stage | Clears all director-approval fields automatically |
| Document in PO Delivered / PO Generated | Put-back is blocked — no rollback possible |
| SS amended_from chain | Final SS approval propagates state to originating Direct Purchase |
| Kafka trigger match on workflow state change | Publishes batch commit event to Kafka automatically |
