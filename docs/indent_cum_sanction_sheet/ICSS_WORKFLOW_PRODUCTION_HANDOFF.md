<!-- EDITED BY MKY | 2026-06-05 11:20 IST -->
<!-- START OF EDIT — Recreate production handoff reference matching indent_cum_sanction_sheet_workflow -->

# ICSS Workflow Production Handoff

**Module:** Indent Cum Sanction Sheet  
**DocType:** `Indent Cum Sanction Sheet`  
**Workflow Name:** `indent_cum_sanction_sheet_workflow`  
**Purpose:** Production workflow/state/transition reference for configuring and verifying the ICSS workflow, resolving transition conflicts, and ensuring proper role-based access.

---

## 1. Important Backend Rule

The ICSS workflow is not only a plain Frappe Workflow table flow. The backend method below controls the workflow action:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.perform_icss_action
```

The frontend should call:

```text
perform_icss_action(docname, action)
```

For submit:

```text
submit_icss(docname)
```

`submit_icss(docname)` internally calls:

```text
perform_icss_action(docname, "Submit")
```

Even though the backend has custom routing logic, the production system must still have matching rows in the active Frappe Workflow Transition table. If a matching transition row is missing from the active workflow in the database, the backend throws:

```text
No valid transition found for action 'Submit' from state 'Draft' matching your role and conditions.
```

---

## 2. Active Workflow Check

Production must have exactly one active workflow for ICSS.

Check:

```sql
select name, document_type, is_active, workflow_state_field
from `tabWorkflow`
where document_type = 'Indent Cum Sanction Sheet';
```

Expected:

- One workflow named `indent_cum_sanction_sheet_workflow` with `is_active = 1`.
- `workflow_state_field` should be `workflow_state`.

If multiple workflows are active, deactivate the older or incorrect ones.

---

## 3. Expected Workflow States

Production should have these 15 ICSS states available in the active workflow:

| No. | State | Doc Status | Update Field | Update Value | Only Allow Edit For | Notes |
|---|---|---|---|---|---|---|
| 1 | `Draft` | 0 | `workflow_state` | `Draft` | `All_ProRnd_User` | Initial saved state |
| 2 | `Pending PI Approval` | 1 | `workflow_state` | `Pending PI Approval` | `Permanent Employee` | First-stage approval |
| 3 | `Pending Mentor Approval` | 1 | `workflow_state` | `Pending Mentor Approval` | `Mentor` | Mentor review stage |
| 4 | `Pending Other PI` | 1 | `workflow_state` | `Pending Other PI` | `Other PI` | Additional investigator check |
| 5 | `Pending Head Approval` | 1 | `workflow_state` | `Pending Head Approval` | `head_approver_1` | Department Head review |
| 6 | `Pending Staff Approval` | 1 | `workflow_state` | `Pending Staff Approval` | `staff, RnD` | R&D Staff review |
| 7 | `Pending HoS Approval` | 1 | `workflow_state` | `Pending HoS Approval` | `Hos, RnD (Head of Section, RnD)` | Head of Section review |
| 8 | `Pending Associate Dean` | 1 | `workflow_state` | `Pending Associate Dean` | `Ado_RnD` | Routed when amount `<= 1L` |
| 9 | `Approved` | 1 | `workflow_state` | `Approved` | `Administrator` | Document fully approved |
| 10 | `Pending Dean Approval` | 1 | `workflow_state` | `Pending Dean Approval` | `Dean, RnD` | Routed when amount `> 1L` |
| 11 | `Pending PO Generation` | 1 | `workflow_state` | `Pending PO Generation` | `staff, RnD` | PO setup stage |
| 12 | `PO Generated` | 1 | `workflow_state` | `PO Generated` | `staff, RnD` | PO created by R&D Staff |
| 13 | `PO Delivered` | 1 | `workflow_state` | `PO Delivered` | `Administrator` | Final state after PO signed PDF upload |
| 14 | `Rejected` | 2 | `workflow_state` | `Rejected` | `Administrator` | Workflow cancelled/rejected |
| 15 | `Put Back` | 1 | `workflow_state` | `Put Back` | `All_ProRnd_User` | State for revisions |

Check workflow states via SQL:

```sql
select ws.state, ws.doc_status, ws.allow_edit
from `tabWorkflow Document State` ws
join `tabWorkflow` w on w.name = ws.parent
where w.document_type = 'Indent Cum Sanction Sheet'
  and w.is_active = 1
order by ws.idx;
```

---

## 4. Expected Transition Rules

The active workflow must have these 30 transitions configured:

| No. | State | Action | Next State | Allowed Role |
|---|---|---|---|---|
| 1 | `Draft` | `Submit` | `Pending PI Approval` | `All_ProRnd_User` |
| 2 | `Draft` | `Submit` | `Pending Mentor Approval` | `All_ProRnd_User` |
| 3 | `Draft` | `Submit` | `Pending Other PI` | `All_ProRnd_User` |
| 4 | `Draft` | `Submit` | `Pending Head Approval` | `All_ProRnd_User` |
| 5 | `Draft` | `Submit` | `Pending Staff Approval` | `All_ProRnd_User` |
| 6 | `Pending PI Approval` | `Forward` | `Pending Other PI` | `Permanent Employee` |
| 7 | `Pending PI Approval` | `Forward` | `Pending Staff Approval` | `Permanent Employee` |
| 8 | `Pending PI Approval` | `Reject` | `Rejected` | `Permanent Employee` |
| 9 | `Pending Mentor Approval` | `Forward` | `Pending Head Approval` | `Mentor` |
| 10 | `Pending Mentor Approval` | `Forward` | `Pending Staff Approval` | `Mentor` |
| 11 | `Pending Mentor Approval` | `Reject` | `Rejected` | `Mentor` |
| 12 | `Pending Other PI` | `Forward` | `Pending Head Approval` | `Other PI` |
| 13 | `Pending Other PI` | `Forward` | `Pending Staff Approval` | `Other PI` |
| 14 | `Pending Other PI` | `Reject` | `Rejected` | `Other PI` |
| 15 | `Pending Head Approval` | `Forward` | `Pending Staff Approval` | `head_approver_1` |
| 16 | `Pending Head Approval` | `Reject` | `Rejected` | `head_approver_1` |
| 17 | `Pending Staff Approval` | `Forward` | `Pending HoS Approval` | `staff, RnD` |
| 18 | `Pending Staff Approval` | `Reject` | `Rejected` | `staff, RnD` |
| 19 | `Pending HoS Approval` | `Forward` | `Pending Associate Dean` | `Hos, RnD (Head of Section, RnD)` |
| 20 | `Pending HoS Approval` | `Forward` | `Pending Dean Approval` | `Hos, RnD (Head of Section, RnD)` |
| 21 | `Pending HoS Approval` | `Reject` | `Rejected` | `Hos, RnD (Head of Section, RnD)` |
| 22 | `Pending Associate Dean` | `Approve` | `Pending PO Generation` | `Ado_RnD` |
| 23 | `Pending Associate Dean` | `Reject` | `Rejected` | `Ado_RnD` |
| 24 | `Pending Dean Approval` | `Approve` | `Pending PO Generation` | `Dean, RnD` |
| 25 | `Pending Dean Approval` | `Reject` | `Rejected` | `Dean, RnD` |
| 26 | `Pending PO Generation` | `Generate PO` | `PO Generated` | `staff, RnD` |
| 27 | `Pending Staff Approval` | `Put Back` | `Pending PI Approval` | `staff, RnD` |
| 28 | `Pending HoS Approval` | `Put Back` | `Pending Staff Approval` | `Hos, RnD (Head of Section, RnD)` |
| 29 | `Pending Dean Approval` | `Put Back` | `Pending HoS Approval` | `Dean, RnD` |
| 30 | `Pending Associate Dean` | `Put Back` | `Pending HoS Approval` | `Associate Dean, RND` |

---

## 5. Initial Submit Routing Logic

The backend routing override determines the actual destination state on submit:

```text
_resolve_initial_submit_next_state(user_roles)
```

The roles checked in backend code bypass the PI approval stage if the submitter is already a high-privilege/direct role:

| Submitter Role Category | Submit Target |
|---|---|
| User has `Permanent Employee` | `Pending Staff Approval` |
| User has `head_approver_1` | `Pending Staff Approval` |
| User has `HoD` | `Pending Staff Approval` |
| User has `System Manager` | `Pending Staff Approval` |
| Any other valid initiator | `Pending PI Approval` |

### Production Requirement:
- Active Workflow must contain all 5 `Draft -> Submit` transitions listed in Section 4.
- If these transitions are missing, role-based permission checks in Frappe's engine will fail before the backend code overrides the target state.
- The `allowed` role for these transition rows must cover the submitting user (e.g. `All_ProRnd_User`).

---

## 6. HoS Amount-Based Routing Logic

Backend helper:

```text
_resolve_hos_next_state(doc)
```

The next state after Head of Section review is determined dynamically by the approval amount:

| Current State | Action | Amount | Target State |
|---|---|---|---|
| `Pending HoS Approval` | `Forward` | `> 1,00,000` | `Pending Dean Approval` |
| `Pending HoS Approval` | `Forward` | `<= 1,00,000` | `Pending Associate Dean` |

### Production Requirement:
- The active workflow must contain both forward transitions from `Pending HoS Approval` (`Pending Dean Approval` and `Pending Associate Dean`).
- The transition action name must be `Forward`.
- The target state name must be exactly `Pending Associate Dean` (not `Pending Associate Dean Approval`).

---

## 7. Director Approval Gate

Director approval is not a separate workflow route. Instead, it acts as a blocking gate inside the state:

```text
Pending Dean Approval
```

Director approval is required when:

| Account/Budget Head | Amount | Director PDF Required |
|---|---:|---|
| Equipment | `> 10,00,000` | Yes |
| Non-equipment | `> 3,00,000` | Yes |
| Equipment | `<= 10,00,000` | No |
| Non-equipment | `<= 3,00,000` | No |

### Behavior:
- When a document is in `Pending Dean Approval` and Director approval is required, the `Approve` button is blocked until the Director-signed PDF is uploaded.
- The Dean flags the document by setting `send_to_director = 1`.
- The Staff/R&D uploads the signed PDF through the upload API, which stores the URL in `director_signed_pdf`.
- Only then can the Dean successfully invoke the `Approve` action.

---

## 8. PO Generation And PO Delivered Flow

After approvals are completed, the final closed loop is:

```text
Pending PO Generation -> PO Generated -> PO Delivered
```

1. **Generate PO**: Staff/R&D clicks `Generate PO` from `Pending PO Generation` to move the document to `PO Generated`.
2. **Deliver PO**: Staff/R&D uploads the signed/scanned PO via `upload_icss_signed_po` API. This:
   - Sets the state to `PO Delivered`.
   - Stores the URL in `icss_signed_po_file`.
   - Syncs the child doctype's workflow state to `PO Delivered`.

*Note: The transition from `PO Generated` to `PO Delivered` is performed automatically by the API and is not a manual workflow button.*

---

## 9. Put-Back Flow

Unlike previous implementations where put-backs were purely virtual, the new workflow configures explicit transitions inside the transition table to allow roles to put documents back to previous reviewers:

- **Staff put back to PI**: allowed for `staff, RnD`. Moves `Pending Staff Approval` -> `Pending PI Approval`.
- **HoS put back to Staff**: allowed for `Hos, RnD (Head of Section, RnD)`. Moves `Pending HoS Approval` -> `Pending Staff Approval`.
- **Dean put back to HoS**: allowed for `Dean, RnD`. Moves `Pending Dean Approval` -> `Pending HoS Approval`.
- **Associate Dean put back to HoS**: allowed for `Associate Dean, RND`. Moves `Pending Associate Dean` -> `Pending HoS Approval`.

---

## 10. Production SQL Verification Queries

Use these queries on the production database to troubleshoot submit or routing issues.

### 10.1 Active Workflow Status

```sql
select name, document_type, is_active, workflow_state_field
from `tabWorkflow`
where document_type = 'Indent Cum Sanction Sheet';
```

### 10.2 Draft Submit Transitions

```sql
select state, action, next_state, allowed, condition
from `tabWorkflow Transition`
where parent = 'indent_cum_sanction_sheet_workflow'
  and state = 'Draft'
  and action = 'Submit';
```

*Expected output: 5 rows corresponding to Pending PI Approval, Pending Mentor Approval, Pending Other PI, Pending Head Approval, and Pending Staff Approval.*

### 10.3 User Roles Verification

Replace `<USER_EMAIL>` with the email of the submitting user.

```sql
select role
from `tabHas Role`
where parent = '<USER_EMAIL>'
order by role;
```

### 10.4 State Spelling Verification

```sql
select distinct state
from `tabWorkflow Document State`
where parent = 'indent_cum_sanction_sheet_workflow'
order by state;
```

---

## 11. Deployment Steps

After deploying the backend code and importing the workflow JSON/CSV:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

If transitions were changed manually in the database or the Desk:

```bash
bench --site <site-name> clear-cache
bench restart
```

---

## 12. Production Acceptance Checklist

- [ ] Exactly one workflow named `indent_cum_sanction_sheet_workflow` is active for `Indent Cum Sanction Sheet`.
- [ ] Five submit transitions exist from `Draft` for the action `Submit` (to PI, Mentor, Other PI, Head, and Staff).
- [ ] Submitting as a `Permanent Employee` routes the document to `Pending Staff Approval`.
- [ ] Submitting as a standard user routes the document to `Pending PI Approval`.
- [ ] PI forwards to `Pending Staff Approval` or `Pending Other PI`.
- [ ] Mentor forwards to `Pending Head Approval` or `Pending Staff Approval`.
- [ ] Other PI forwards to `Pending Head Approval` or `Pending Staff Approval`.
- [ ] Head Approval forwards to `Pending Staff Approval`.
- [ ] Staff forwards to `Pending HoS Approval`.
- [ ] HoS forwards amount `> 1L` to `Pending Dean Approval` and `<= 1L` to `Pending Associate Dean`.
- [ ] Dean approval is blocked for Director-required documents unless `director_signed_pdf` is uploaded.
- [ ] Dean/Associate Dean approval transitions the document to `Pending PO Generation`.
- [ ] Staff PO generation transitions the document to `PO Generated`.
- [ ] Uploading the final signed PO transitions the document to `PO Delivered`.
- [ ] Put-back transitions are working correctly according to the defined roles.

<!-- END OF EDIT — MKY | 2026-06-05 11:20 IST -->
