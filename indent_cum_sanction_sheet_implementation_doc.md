# Indent Cum Sanction Sheet — Implementation Design Document

**Status:** Partially implemented — composite backend flow is now in code  
**Author:** Codex  
**Date:** 2026-05-07

---

## 1. Overview

The `Indent Cum Sanction Sheet` (ICSS) module should support a **single frontend submission flow** where the user fills:

- the **parent ICSS form**
- the **indent-type-specific child form**
- the **child table rows inside the child form**

and submits them together from the frontend.

On the backend:

- the **parent ICSS document** must be created or updated
- the **child doctype document** must be created or updated
- the child document must be linked back to the parent using a field like:
  - `indent_cum_sanction_sheet_id`
- the parent response payload must expose the child data in JSON form, similar to how other modules return nested data through `doc.as_dict()`
- after submission, the module must move through workflow similar to `Recruitment Adhoc Contractual`, `Reimbursement`, and `Direct Purchase`

This document defines the recommended implementation model before code changes begin.

### 1.1 Implementation Status

Implemented now:

- `get_icss_child_fields(indent_type, child_docname=None)`
- `save_icss_composite_data(data)`
- nested child JSON in `get_icss_fields(doc_name=...)`
- combined parent + child JSON in workflow action response
- backend subtype map corrected for:
  - `repair_replacement`
  - `AMC`
- generic internal payload saver added for parent/child doctypes
- HoS amount-based routing implemented:
  - amount `> 1L` -> `Pending Dean Approval`
  - amount `<= 1L` -> `Pending Associate Dean`

Partially implemented:

- child workflow synchronization on parent workflow actions

Pending:

- backend-enforced HoS conditional routing by amount
- Director escalation workflow logic
- full AMC child API parity
- full linkage-field harmonization across every child doctype

---

## 2. Design Goal

The module should behave like a **hybrid of two existing patterns** already used in the app:

- **Pattern A: single API-driven document modules**
  - Example: Recruitment, Reimbursement, Direct Purchase
  - Frontend calls `get_*_fields`, `save_*_data`, `get_*_workflow_actions`, `perform_*_action`
  - `doc.as_dict()` returns parent plus child table rows as one JSON object

- **Pattern B: parent controlling a specialized downstream document**
  - Example: current ICSS code already maps indent type -> sub doctype
  - Parent acts as orchestration record
  - Specialized child doctype stores type-specific fields

Recommended approach:

- keep **ICSS parent as the entrypoint**
- keep **one specialized child doctype per indent type**
- accept **combined frontend payload**
- save both parent and child in one backend transaction
- return a **combined JSON response** so frontend sees ICSS like a single module

---

## 3. Target Functional Flow

### 3.1 Frontend User Flow

1. User opens ICSS form.
2. Frontend loads parent metadata from ICSS API.
3. User selects `icss_indent_type`.
4. Frontend loads child doctype metadata for the selected type.
5. User fills:
   - parent ICSS fields
   - child doctype fields
   - child tables inside the child doctype
6. Frontend submits one payload.
7. Backend saves:
   - parent ICSS
   - child doctype
   - child doctype child tables
8. Backend returns combined JSON.
9. Frontend shows draft/saved/submitted state.
10. Workflow actions continue through ICSS workflow.

### 3.2 Backend Save Flow

1. Validate indent type.
2. Create or update parent ICSS doc.
3. Resolve child doctype from indent type.
4. Create or update child doctype doc.
5. Set child link field:
   - `indent_cum_sanction_sheet_id = parent.name`
6. Set parent reference field:
   - `sub_doctype_reference = child.name`
7. Save child tables for the child doctype.
8. Commit both documents in one transaction.
9. Return parent JSON plus nested child JSON.

---

## 4. Parent-Child Architecture

### 4.1 Parent Doctype

Parent doctype:

- `Indent Cum Sanction Sheet`

Parent responsibilities:

- applicant/project/common financial fields
- indent type selection
- top-level workflow
- link to specialized child doctype
- unified API entrypoint for frontend

Key parent fields already relevant:

- `icss_indent_type`
- `project_ref`
- `project_no`
- `icss_account_head`
- `workflow_state`
- `sub_doctype_reference`

### 4.2 Child Doctype by Indent Type

The existing mapping in code should remain the basis:

- Proprietary Purchase -> `proprietary_purchase`
- Standardized / Emergent Purchase -> `standerdized_purchase`
- Repair / Replacement -> `repair_replacement`
- Annual Maintenance Contract -> `AMC`
- Rate Contract Purchase -> `Rate Contract`

Each child doctype should contain:

- indent-type-specific fields
- its own child tables
- a parent link field such as `indent_cum_sanction_sheet_id`
- common reference fields where useful:
  - `project_ref`
  - `project_no`
  - `indent_type`

### 4.2.1 Standardized Common Child Fields

All ICSS child doctypes should expose these shared fields uniformly:

- `amended_from`
- `indent_cum_sanction_sheet_id`
- `project_no`
- `project_ref`
- `indent_type`
- `workflow_state`

Implementation status:

- already present earlier in:
  - `proprietary_purchase`
  - `standerdized_purchase`
- now standardized in:
  - `repair_replacement`
  - `AMC`
  - `Rate Contract`

### 4.3 Relationship Rules

Rules:

- one ICSS parent -> one specialized child document
- child document must not be treated as standalone from frontend
- parent is the canonical entrypoint
- child document stores specialized business data
- frontend should not need separate save orchestration for parent and child

---

## 5. API Contract

## 5.1 Metadata API

Recommended APIs:

- `get_icss_indent_types()`
- `get_icss_fields(doc_name=None)`
- `get_icss_child_fields(indent_type, child_docname=None)`

### Current Status

Implemented.

### Purpose

- parent metadata comes from `get_icss_fields`
- child metadata comes from `get_icss_child_fields`
- frontend renders both forms dynamically

### Response Shape

```json
{
  "status": "success",
  "parent": {
    "fields": [],
    "prefill_data": {},
    "link_options": {},
    "client_scripts": [],
    "computation_rules": {}
  },
  "child": {
    "doctype": "proprietary_purchase",
    "fields": [],
    "prefill_data": {},
    "link_options": {},
    "client_scripts": [],
    "computation_rules": {}
  }
}
```

This follows the same metadata-driven pattern already used in Recruitment, Reimbursement, and Direct Purchase.

---

## 5.2 Save API

Recommended new API:

- `save_icss_composite_data(data)`

This should become the main API used by frontend.

### Current Status

Implemented.

### Request Payload Shape

```json
{
  "parent": {
    "name": null,
    "icss_indent_type": "Proprietary Purchase with Proprietary certificate from the OEM",
    "icss_applicant_webmail_id": "user@iitg.ac.in",
    "project_ref": "PRJ-0001",
    "project_no": "RND/2026/001",
    "icss_account_head": "Budget Head A"
  },
  "child": {
    "doctype": "proprietary_purchase",
    "name": null,
    "pp_pack_and_forward": 1000,
    "pp_freight": 500,
    "pp_other_charges": 250,
    "table_qanf": [
      {
        "icss_item_name": "Item 1",
        "icss_qty": 2,
        "icss_rate": 10000,
        "icss_discount_percent": 0,
        "icss_gst_percent": 18
      }
    ]
  }
}
```

### Save Behavior

The API should:

1. parse payload
2. validate indent type and child doctype match
3. save parent
4. inject linkage values into child:
   - `indent_cum_sanction_sheet_id = parent.name`
   - `project_ref = parent.project_ref`
   - `project_no = parent.project_no`
   - `indent_type = parent.icss_indent_type`
5. save child and child tables
6. update parent `sub_doctype_reference`
7. return combined JSON

### Response Shape

```json
{
  "status": "success",
  "docname": "2026050710XXXXXX",
  "parent_doctype": "Indent Cum Sanction Sheet",
  "child_doctype": "proprietary_purchase",
  "child_docname": "PP-0001",
  "data": {
    "name": "2026050710XXXXXX",
    "icss_indent_type": "Proprietary Purchase with Proprietary certificate from the OEM",
    "sub_doctype_reference": "PP-0001",
    "workflow_state": "Draft",
    "child_document": {
      "doctype": "proprietary_purchase",
      "name": "PP-0001",
      "indent_cum_sanction_sheet_id": "2026050710XXXXXX",
      "table_qanf": [
        {
          "icss_item_name": "Item 1"
        }
      ]
    }
  }
}
```

This is the important point for frontend:

- parent response should include **nested child JSON**
- this gives a single combined module response similar to other modules

---

## 5.3 Get Existing Document API

Recommended behavior for:

- `get_icss_fields(doc_name=...)`

When fetching an existing parent document:

1. load parent doc
2. inspect `sub_doctype_reference`
3. resolve child doctype from `icss_indent_type`
4. fetch child doc
5. return parent prefill plus nested child data

### Returned JSON Shape

```json
{
  "fields": [...],
  "prefill_data": {
    "...parent fields...": "...",
    "child_document": {
      "...child fields...": "...",
      "table_qanf": []
    }
  },
  "link_options": {},
  "client_scripts": [],
  "computation_rules": {}
}
```

This is how frontend can reopen the full record without separately stitching parent and child manually.

### Current Status

Implemented.

Current parent fetch now includes:

- `child_document`
- `child_doctype`

---

## 6. Workflow Design

ICSS should behave workflow-wise like the other major modules:

- Draft save
- Submit action
- role-based workflow transitions
- submitted state tracked with `workflow_state`
- child record stays in sync with parent state

### 6.1 Conditional Approval Routing

Initial submit routing:

- Any authenticated ProRND user can initiate an ICSS.
- If the initiator has `Permanent Employee`, `head_approver_1`, `HoD`, or `System Manager`, `Submit` routes directly to `Pending Staff Approval`.
- If the initiator does not have one of those direct-routing roles, `Submit` routes first to `Pending PI Approval`.
- From `Pending PI Approval`, the permanent employee approver forwards the form to `Pending Staff Approval`.
- The normal chain after that is `Pending Staff Approval` -> `Pending HoS Approval` -> `Pending Associate Dean` or `Pending Dean Approval`.

After the ICSS form is submitted and reaches the HoS stage, the next approval state must be decided conditionally.

Currently confirmed routing:

- if amount is **more than 1 lakh**, route to `Pending Dean Approval`
- if amount is **1 lakh or less**, route to `Pending Associate Dean`

Additional Director approval rules are now proposed as a **Dean-stage PDF gate**, not as a separate workflow route:

- if budget head / account head is `Equipment` and amount is **more than 10 lakh**, Director approval PDF is required before Dean can approve
- if budget head / account head is **not Equipment** and amount is **more than 3 lakh**, Director approval PDF is required before Dean can approve
- if below the above Director thresholds, Dean / Associate Dean approval can proceed normally

This means ICSS workflow must support **condition-based routing**, not only a fixed linear transition chain.

### Recommended Workflow Principle

- **frontend works only with parent workflow**
- parent workflow action API drives both:
  - parent workflow transition
  - child workflow transition if needed

### Recommended APIs

- `get_icss_workflow_actions(docname)`
- `perform_icss_action(docname, action)`
- `submit_icss(docname)`

### Workflow Transition Handling

When parent action is performed:

1. resolve next parent workflow state
2. update parent `workflow_state`
3. submit/cancel parent if target state requires docstatus change
4. if child workflow exists:
   - load linked child doc
   - apply same action or mapped action
   - update child workflow/docstatus

This matches the intent already present in current ICSS controller logic.

### Current Status

Partially implemented.

Implemented now:

- parent workflow action response returns combined parent + child JSON
- child workflow sync is triggered during non-submit parent workflow transitions when a linked child exists
- backend-enforced initial submit routing:
  - Permanent Employee / HoD initiators route to `Pending Staff Approval`
  - all other initiators route to `Pending PI Approval` first
- backend-enforced HoS routing based on normalized approval amount:
  - amount `> 100000` routes to `Pending Dean Approval`
  - amount `<= 100000` routes to `Pending Associate Dean`

Still pending:

- Director approval PDF gate implementation inside `Pending Dean Approval`

### 6.2 Recommended Workflow States

The exact workflow can evolve, but the implementation should be designed around states like:

- `Draft`
- `Pending HoS Approval`
- `Pending Associate Dean Approval`
- `Pending Dean Approval`
- `Approved`
- `Rejected`

### 6.3 Recommended Routing Logic After HoS

At the HoS forward / approve step, backend should continue using the confirmed routing:

1. If amount > `1,00,000`:
   route to `Pending Dean Approval`
2. Else:
   route to `Pending Associate Dean Approval`

Director approval is not a HoS routing destination in the proposed implementation. It is a blocking condition at `Pending Dean Approval`: Dean can mark the form for Director approval, Staff/R&D uploads the Director-signed ICSS PDF, and only then Dean can approve to `Pending PO Generation`.

### 6.4 Future Workflow Expansion

More routing cases are expected later. To keep the implementation maintainable, conditional approval routing should be centralized in backend helpers such as:

- `_resolve_hos_next_state(doc, requested_action, workflow, user_roles)`
- `_is_icss_director_approval_required(doc)`
- `requires_dean_approval(doc)`
- `_get_icss_approval_amount(doc)`

This keeps the frontend contract unchanged even when more workflow conditions are introduced later.

---

## 7. JSON Behavior Requirement

This section directly answers the main implementation expectation.

### Requirement

When frontend submits ICSS, parent and child should be treated as one logical module.

That means:

- request may contain parent + child in one payload
- backend saves both
- response must include both
- fetching an existing ICSS must return both

### Recommended JSON Model

Parent remains the outer document.

Child is embedded as a nested object:

```json
{
  "name": "ICSS-0001",
  "workflow_state": "Draft",
  "icss_indent_type": "Standerdised/ Emergent Purchase",
  "sub_doctype_reference": "SP-0001",
  "child_document": {
    "doctype": "standerdized_purchase",
    "name": "SP-0001",
    "indent_cum_sanction_sheet_id": "ICSS-0001",
    "table_xxx": []
  }
}
```

This is the cleanest way to preserve:

- parent as workflow entrypoint
- child as specialized data holder
- one frontend contract

---

## 8. Backend Implementation Plan

### Phase 1 — Stabilize Composite API

Implement or refactor:

- `get_icss_child_fields(indent_type, child_docname=None)`
- `save_icss_composite_data(data)`
- nested child JSON in `get_icss_fields`

Deliverable:

- frontend can save and reopen parent + child together

Status:

- implemented

### Phase 2 — Normalize Child Mapping

Implement a central helper:

- `resolve_icss_child_doctype(indent_type)`

Implement central save helper:

- `save_icss_parent_and_child(parent_data, child_data)`

Deliverable:

- no duplicated save logic across indent types

Status:

- partially implemented

### Phase 3 — Workflow Synchronization

Refine:

- `get_icss_workflow_actions`
- `perform_icss_action`
- child workflow synchronization

Deliverable:

- ICSS behaves like other modules after submission

Status:

- partially implemented

### Phase 4 — Type Completion

Complete the same composite pattern for:

- AMC
- Rate Contract

Deliverable:

- all indent types work through the same parent-child save contract

Status:

- pending / partial

---

## 9. Recommended Server-Side Method Structure

Recommended methods in `indent_cum_sanction_sheet.py`:

- `get_icss_indent_types()`
- `get_icss_fields(doc_name=None)`
- `get_icss_child_fields(indent_type, child_docname=None)`
- `save_icss_composite_data(data)`
- `save_icss_parent_and_child(parent_data, child_data)`
- `get_icss_workflow_actions(docname)`
- `perform_icss_action(docname, action)`
- `submit_icss(docname)`
- `get_user_details_icss(user_email)`

Recommended internal helpers:

- `_resolve_child_doctype(indent_type)`
- `_load_child_doc(parent_doc)`
- `_map_parent_to_child(parent_doc, child_doc)`
- `_serialize_icss_composite(parent_doc, child_doc)`
- `_perform_child_workflow_if_needed(parent_doc, child_doc, action)`

---

## 10. Validation Rules

### Parent Validations

- `icss_indent_type` required
- `icss_applicant_webmail_id` required
- `project_ref` required
- `project_no` required
- `icss_account_head` required

### Child Validations

Child validations remain type-specific:

- Proprietary Purchase:
  - at least one item row
- Standardized Purchase:
  - at least one item row
  - at least one standardized reason row
- Repair / Replacement:
  - repair item name required
  - repair justification required
- AMC:
  - AMC-specific required fields
- Rate Contract:
  - rate-contract-specific required fields

### Link Integrity

- child `indent_cum_sanction_sheet_id` must always point to parent
- parent `sub_doctype_reference` must always point to child
- child doctype must match parent `icss_indent_type`

### Workflow Routing Inputs

To support conditional routing safely, backend must always be able to determine:

- the normalized approval amount
- the effective account head / budget head

Recommended planning rule:

- use a single helper to calculate the approval amount based on indent type
- do not scatter amount-routing logic across multiple workflow branches

Expected amount source by type:

- Proprietary / Standardized / Rate Contract:
  use final grand total
- Repair / Replacement:
  use repair grand total
- AMC:
  use AMC grand total

This exact helper logic can be finalized during implementation, but the workflow design must depend on one normalized amount value.

---

## 11. Error Handling

The composite save must rollback fully if any of these fail:

- parent validation
- child validation
- child table validation
- file upload inside parent or child
- workflow transition failure

Recommended rule:

- no partial save of parent without child
- no child save without updating parent link

Use one transaction:

- `frappe.db.rollback()` on failure
- `frappe.db.commit()` only after both docs are valid and saved

Workflow-specific rule:

- if next approval state cannot be determined because amount or budget head is missing, the workflow action must fail with a clear error instead of routing incorrectly

---

## 12. Recommended Frontend Contract

Frontend should follow this contract:

### Initial Load

- call `get_icss_indent_types()`
- call `get_icss_fields()`

### After Indent Type Selection

- call `get_icss_child_fields(indent_type)`

### Save Draft

- call `save_icss_composite_data({ parent, child })`

### Reopen Existing Record

- call `get_icss_fields(doc_name)`
- read nested `child_document`

### Workflow Actions

- call `get_icss_workflow_actions(docname)`
- call `perform_icss_action(docname, action)`

---

## 13. Why This Design Is Recommended

This design is recommended because it preserves the strengths of the current codebase:

- matches the API-driven module pattern already used elsewhere
- keeps ICSS as one module from frontend perspective
- keeps specialized child doctypes for maintainability
- avoids forcing frontend to orchestrate two separate saves
- keeps workflow centralized at parent level
- allows child workflow sync where required

It also reduces risk:

- avoids turning child doctypes into fully separate modules for users
- avoids duplicating the same parent fields in every specialized doctype
- avoids breaking the current `SUB_DOCTYPE_MAP` design direction
- allows conditional approval rules to grow later without changing the frontend payload contract

---

## 14. Suggested Implementation Decision

Proceed with this implementation model:

- ICSS parent remains the main document
- selected indent type creates/updates exactly one child doctype
- frontend sends one combined payload
- backend saves both in one transaction
- parent fetch API returns nested child JSON
- workflow is driven from parent API, with child sync behind the scenes

---

## 15. Confirmation Points Before Coding

Please confirm these points before implementation:

1. Frontend should submit **one combined payload** with `parent` and `child`.
2. Parent workflow should be the **only workflow visible to frontend**.
3. Child workflow should be **backend-synced only**, not directly user-driven.
4. Existing child doctypes should remain separate doctypes, not merged into parent fields.
5. Parent fetch response should include nested child JSON under a key like `child_document`.
6. We should implement this pattern first for:
   - Proprietary
   - Standardized
   - Repair
   and then extend to:
   - AMC
   - Rate Contract
7. HoS-to-approval routing should currently follow:
   - amount > 1L -> `Pending Dean Approval`
   - amount <= 1L -> `Pending Associate Dean Approval`
8. Director approval should be implemented as a Dean-stage PDF gate:
   - Equipment + amount > 10L -> Dean approval is blocked until `director_signed_pdf` is uploaded
   - Non-Equipment + amount > 3L -> Dean approval is blocked until `director_signed_pdf` is uploaded

If you confirm this direction, the next step will be a code implementation plan file-by-file and then the actual backend changes.

---

## 16. Implemented Workflow State / Pending Task Alignment

The ICSS workflow has now been aligned with the existing Direct Purchase and Recruitment architecture:

- Normal workflow movement now persists `workflow_state` using direct `frappe.db.set_value(...)` instead of relying on `doc.save()` for draft-status pending states.
- The parent ICSS document remains the workflow owner.
- Linked child indent doctypes mirror the parent `workflow_state` directly.
- Child workflow actions are not replayed from the parent because child workflows may have different transition graphs.
- Existing linked child records were aligned to their current parent workflow states.

Frappe Desk and Pending Task alignment:

- `workflow_state` remains hidden as a separate field/column in ICSS list/form views.
- ICSS list indicator uses `workflow_state`, so pending records should show states like `Pending Staff Approval`, `Pending HoS Approval`, `Pending Dean Approval`, etc.
- ICSS has a dedicated `indent_cum_sanction_sheet_list.js` list controller with `has_indicator_for_draft` enabled so Frappe does not show the default docstatus `Draft` pill for pending workflow records.
- The live ICSS `workflow_state` Custom Field metadata was kept hidden with `hidden = 1` and `in_list_view = 0`; the list indicator fetches it through `add_fields`.
- ICSS has DocPerm entries for the workflow roles used in transitions.
- The ICSS `pending-task` module registry row is enabled with `mod_vis = 1`.
- `get_pending_task("pending-task")` returns ICSS through the generic module registry path.

Runtime notes:

- `bench migrate` was run for site `prornd.local`.
- `bench --site prornd.local clear-cache` and `bench restart` were run after implementation.
- A migrate warning was observed for unrelated hook path `rndopsapp.rndopsapp.rndopsapp.api.auto_clear_old_mattermost_posts`; migration still completed.
- Duplicate ICSS `workflow_state` metadata was cleaned up: the DocType JSON/DocField copy was removed, and the workflow-managed Custom Field remains hidden for backend workflow/status-pill use.
- Duplicate `workflow_state` metadata was also cleaned for ICSS child doctypes: `repair_replacement`, `proprietary_purchase`, `standerdized_purchase`, and `Rate Contract`. Their workflow-managed Custom Fields remain; duplicate DocField/JSON definitions were removed.

---

## 17. Production Deployment Handoff

This section records all backend, DocType, workflow, and database changes made for the ICSS module so production developers can deploy safely.

### 17.1 Code Files Changed

ICSS parent:

- `rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py`
- `rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json`
- `rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet_list.js`

ICSS child doctypes:

- `rndopsapp/rndopsapp/doctype/proprietary_purchase/proprietary_purchase.json`
- `rndopsapp/rndopsapp/doctype/proprietary_purchase/proprietary_purchase.py`
- `rndopsapp/rndopsapp/doctype/standerdized_purchase/standerdized_purchase.json`
- `rndopsapp/rndopsapp/doctype/standerdized_purchase/standerdized_purchase.py`
- `rndopsapp/rndopsapp/doctype/repair_replacement/repair_replacement.json`
- `rndopsapp/rndopsapp/doctype/repair_replacement/repair_replacement.py`
- `rndopsapp/rndopsapp/doctype/rate_contract/rate_contract.json`
- `rndopsapp/rndopsapp/doctype/rate_contract/rate_contract.py`
- `rndopsapp/rndopsapp/doctype/amc/amc.json`
- `rndopsapp/rndopsapp/doctype/rate_contract_purchase_item_detail/rate_contract_purchase_item_detail.json`

Documentation:

- `indent_cum_sanction_sheet_implementation_doc.md`

### 17.2 Parent ICSS Backend Changes

Implemented APIs and helpers:

- `get_icss_child_fields(indent_type, child_docname=None)`
- `save_icss_composite_data(data)`
- `get_icss_fields(doc_name=None)` now returns nested child data when available.
- Child doctype mapping is centralized through `SUB_DOCTYPE_MAP`.
- Generic payload save helper supports parent, child, tables, links, and attach fields.
- Link normalization resolves common frontend values like User full name and Department display label.

Implemented workflow behavior:

- Initial submit routing:
  - Permanent Employee, HoD/head role, or System Manager routes directly to `Pending Staff Approval`.
  - Other initiators route to `Pending PI Approval`.
- Staff/RnD forwards to `Pending HoS Approval`.
- HoS/RnD routing:
  - amount `> 1L` routes to `Pending Dean Approval`
  - amount `<= 1L` routes to `Pending Associate Dean`
- Director escalation is documented for future implementation but not active in current routing.
- Normal workflow movement updates `workflow_state` through `frappe.db.set_value(...)`, matching Direct Purchase and Recruitment behavior.
- Linked child doctype `workflow_state` is synced directly from the parent ICSS state.
- Child workflow transitions are not replayed because child workflows may have different transition graphs.

### 17.3 Frappe Desk List View Changes

ICSS Desk list should show only:

- `ID`
- `Status`
- `Webmail ID`

Implementation details:

- `workflow_state` remains hidden as a field/column.
- `indent_cum_sanction_sheet_list.js` drives the `Status` pill from hidden `workflow_state`.
- `has_indicator_for_draft = true` prevents Frappe from showing default `Draft` for pending workflow records.
- `icss_applicant_name`, `icss_applying_for_mail`, `icss_applying_for_name`, and `workflow_state` are not shown in list view.

### 17.4 Child Doctype Changes

All ICSS child doctypes were aligned to parent-driven workflow:

- `proprietary_purchase`
- `standerdized_purchase`
- `repair_replacement`
- `AMC`
- `Rate Contract`

Common child linkage fields:

- `indent_cum_sanction_sheet_id`
- `project_no`
- `project_ref`
- `indent_type`
- `workflow_state` through Frappe Workflow Custom Field where applicable

Workflow metadata cleanup:

- Removed duplicate DocType JSON/DocField definitions of `workflow_state` where a Frappe Workflow Custom Field already exists.
- Kept the workflow-managed Custom Field hidden and not in list view.
- Cleaned duplicates for:
  - `Indent Cum Sanction Sheet`
  - `repair_replacement`
  - `proprietary_purchase`
  - `standerdized_purchase`
  - `Rate Contract`
- `AMC` currently has only one DocField `workflow_state` and no duplicate Custom Field, so it was left unchanged.

Repair/Replacement amount fix:

- `rr_other_charges` previously existed as `Column Break`, so Frappe could not save it as a data field.
- Converted `rr_other_charges` to `Currency`.
- Converted `rr_grand_total` to `Currency`.
- Updated calculation:

```python
rr_grand_total = rr_repair_expenditure + rr_other_charges
```

### 17.5 Runtime Database Changes Applied Locally

These live DB changes were applied on site `prornd.local`.

Module Registry:

- Enabled ICSS in `pending-task` registry with `mod_vis = 1`.

Permissions:

- ICSS DocPerms were added/migrated for workflow roles:
  - `System Manager`
  - `All_ProRnd_User`
  - `Permanent Employee`
  - `Mentor`
  - `Other PI`
  - `head_approver_1`
  - `staff, RnD`
  - `Hos, RnD (Head of Section, RnD)`
  - `Ado_RnD`
  - `Dean, RnD`

Workflow state cleanup:

- Removed duplicate `workflow_state` rows from `tabDocField` where a workflow Custom Field already existed.
- Kept `tabCustom Field.workflow_state` hidden and not in list view.
- Synced existing linked child records to parent ICSS workflow state.

Field display cleanup:

- Hidden `workflow_state` from ICSS field/list display.
- Removed `Applicant Name`, `Applying for Webmail ID`, and `Applying for Name` from ICSS list columns.

Repair field fix:

- Changed live `repair_replacement.rr_other_charges` from `Column Break` to `Currency`.
- Changed live `repair_replacement.rr_grand_total` to `Currency`.

Server Script cleanup:

- A stray server script/runtime issue involving `name 't' is not defined` was cleaned locally.
- Production should avoid relying on Server Scripts for this module unless server scripts are explicitly enabled.

### 17.6 Production SQL Checklist

Run a DB backup before executing cleanup SQL in production.

Inspect duplicates first:

```sql
select 'DocField' source, parent doctype, count(*) count
from `tabDocField`
where fieldname='workflow_state'
  and parent in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract',
    'AMC'
  )
group by parent
union all
select 'Custom Field' source, dt doctype, count(*) count
from `tabCustom Field`
where fieldname='workflow_state'
  and dt in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract',
    'AMC'
  )
group by dt;
```

Remove duplicate DocField copies where Custom Field exists:

```sql
delete from `tabDocField`
where fieldname='workflow_state'
  and parent in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract'
  );

update `tabCustom Field`
set hidden=1,
    in_list_view=0,
    modified=now(),
    modified_by='Administrator'
where fieldname='workflow_state'
  and dt in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract'
  );
```

Enable ICSS in Pending Task registry:

```sql
set sql_safe_updates=0;

update `tabModule Registry Item` i
join `tabModule Registry` p on p.name = i.parent
set i.mod_vis = 1,
    i.modified = now(),
    i.modified_by = 'Administrator'
where p.page_name = 'pending-task'
  and i.doctype_name = 'Indent Cum Sanction Sheet';
```

Keep ICSS list columns minimal:

```sql
update `tabDocField`
set in_list_view=0,
    modified=now(),
    modified_by='Administrator'
where parent='Indent Cum Sanction Sheet'
  and fieldname in (
    'icss_applicant_name',
    'icss_applying_for_mail',
    'icss_applying_for_name',
    'workflow_state'
  );

update `tabCustom Field`
set hidden=1,
    in_list_view=0,
    modified=now(),
    modified_by='Administrator'
where dt='Indent Cum Sanction Sheet'
  and fieldname='workflow_state';
```

Repair/Replacement field fix:

```sql
update `tabDocField`
set fieldtype='Currency',
    modified=now(),
    modified_by='Administrator'
where parent='repair_replacement'
  and fieldname in ('rr_other_charges', 'rr_grand_total');
```

Sync existing ICSS child workflow state after deployment:

```sql
set sql_safe_updates=0;

update `tabproprietary_purchase` c
join `tabIndent Cum Sanction Sheet` p on p.sub_doctype_reference = c.name
set c.workflow_state = p.workflow_state
where p.icss_indent_type = 'Proprietary Purchase with Proprietary certificate from the OEM'
  and coalesce(p.workflow_state, '') != '';

update `tabstanderdized_purchase` c
join `tabIndent Cum Sanction Sheet` p on p.sub_doctype_reference = c.name
set c.workflow_state = p.workflow_state
where p.icss_indent_type = 'Standerdised/ Emergent Purchase'
  and coalesce(p.workflow_state, '') != '';

update `tabrepair_replacement` c
join `tabIndent Cum Sanction Sheet` p on p.sub_doctype_reference = c.name
set c.workflow_state = p.workflow_state
where p.icss_indent_type = 'Repair/ Repleacement'
  and coalesce(p.workflow_state, '') != '';

update `tabAMC` c
join `tabIndent Cum Sanction Sheet` p on p.sub_doctype_reference = c.name
set c.workflow_state = p.workflow_state
where p.icss_indent_type = 'Annual Maintenance Contract'
  and coalesce(p.workflow_state, '') != '';

update `tabRate Contract` c
join `tabIndent Cum Sanction Sheet` p on p.sub_doctype_reference = c.name
set c.workflow_state = p.workflow_state
where p.icss_indent_type = 'Rate Contract Purchase'
  and coalesce(p.workflow_state, '') != '';
```

### 17.7 Deployment Command Sequence

Recommended production sequence:

```bash
bench --site <site-name> backup
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

After migration, run the SQL inspection queries above. If duplicates exist, run the cleanup SQL, then run:

```bash
bench --site <site-name> clear-cache
bench restart
```

### 17.8 Post-Deployment Verification

Verify metadata:

```sql
select 'DocField' source, parent doctype, count(*) count
from `tabDocField`
where fieldname='workflow_state'
  and parent in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract'
  )
group by parent
union all
select 'Custom Field' source, dt doctype, count(*) count
from `tabCustom Field`
where fieldname='workflow_state'
  and dt in (
    'Indent Cum Sanction Sheet',
    'repair_replacement',
    'proprietary_purchase',
    'standerdized_purchase',
    'Rate Contract'
  )
group by dt;
```

Expected result:

- `DocField` count should be `0` for the doctypes listed above.
- `Custom Field` count should be `1` for each workflow-enabled doctype.

Verify behavior:

- Open `/app/doctype/repair_replacement` and add/edit a field; duplicate `workflow_state` error should not appear.
- Open `/app/indent-cum-sanction-sheet`; list should show `ID`, `Status`, and `Webmail ID`.
- Submit ICSS as Permanent Employee/HoD and confirm it routes to `Pending Staff Approval`.
- Forward as Staff/RnD and confirm it routes to `Pending HoS Approval`.
- Forward as HoS/RnD and confirm amount-based routing:
  - `> 1L` to `Pending Dean Approval`
  - `<= 1L` to `Pending Associate Dean`
- Confirm `get_pending_task("pending-task")` returns ICSS records through Module Registry.

---

## 18. ICSS PO AMC Table Save Support

### 18.1 Change Summary

`ICSS_PO` now supports the new `indent_type` field and the `amc_po_table` child table.

It also supports AMC-only summary fields:

- `add_of_gst_`
- `gst_amount`
- `grand_total`

The table is only meaningful for:

```text
Annual Maintenance Contract
```

For all other indent types, the backend keeps `amc_po_table` empty.

### 18.2 Files Changed

- `rndopsapp/rndopsapp/doctype/icss_po/icss_po.py`
- `rndopsapp/rndopsapp/doctype/icss_po/icss_po.json`
- `rndopsapp/rndopsapp/doctype/amc_po_table/amc_po_table.json`

### 18.3 API Updated

Endpoint:

```text
rndopsapp.rndopsapp.doctype.icss_po.icss_po.save_icss_po_data
```

Supported payload fields:

- `project_number`
- `icss_number`
- `indent_type`
- `po_number`
- `po_date`
- `icss_po_form`
- `amc_po_table`
- `add_of_gst_`
- `gst_amount`
- `grand_total`

If `indent_type` is not sent but `icss_number` exists, backend derives it from:

```text
Indent Cum Sanction Sheet.icss_indent_type
```

### 18.4 AMC Table Payload

Frontend should send `amc_po_table` only when:

```text
indent_type == "Annual Maintenance Contract"
```

Example:

```json
{
  "project_number": "PROJECT-001",
  "icss_number": "2026050710000833",
  "indent_type": "Annual Maintenance Contract",
  "po_number": "PO-001",
  "po_date": "2026-05-12",
  "icss_po_form": "<p>PO HTML content</p>",
  "add_of_gst_": "18",
  "gst_amount": "18000",
  "grand_total": "118000",
  "amc_po_table": [
    {
      "sl_no": "1",
      "description_of_items": "AMC for equipment",
      "end_user": "Lab / Department",
      "year": "2026",
      "amc_from": "2026-05-12",
      "amc_to": "2027-05-11",
      "amc_amount": 100000
    }
  ]
}
```

For non-AMC indent types:

```json
{
  "project_number": "PROJECT-001",
  "icss_number": "2026050710000833",
  "indent_type": "Rate Contract Purchase",
  "po_number": "PO-002",
  "po_date": "2026-05-12",
  "icss_po_form": "<p>PO HTML content</p>"
}
```

Backend behavior:

- When `indent_type` is `Annual Maintenance Contract`, `amc_po_table` rows are saved if the table is sent.
- Existing AMC rows are not wiped during partial saves unless frontend explicitly sends `amc_po_table`.
- AMC summary fields `add_of_gst_`, `gst_amount`, and `grand_total` are saved only for Annual Maintenance Contract.
- Existing AMC summary values are not wiped during partial saves unless frontend explicitly sends those fields.
- When `indent_type` is anything else, `amc_po_table` is cleared/kept empty.
- When `indent_type` is anything else, AMC summary fields are cleared/kept empty.
- Child row system fields like `name`, `parent`, `idx`, `doctype`, etc. are stripped before appending rows.

### 18.5 Deployment Notes

Run after pulling code:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

Verify tables exist:

```sql
show tables like 'tabICSS_PO';
show tables like 'tabamc_po_table';
```

Verify child table columns:

```sql
describe `tabamc_po_table`;
```

Expected important columns:

- `add_of_gst_` in `tabICSS_PO`
- `gst_amount` in `tabICSS_PO`
- `grand_total` in `tabICSS_PO`
- `sl_no`
- `description_of_items`
- `end_user`
- `year`
- `amc_from`
- `amc_to`
- `amc_amount`

### 18.6 Post-Deployment Verification

Test AMC save:

- Call `save_icss_po_data` with `indent_type = Annual Maintenance Contract`.
- Include at least one `amc_po_table` row.
- Include `add_of_gst_`, `gst_amount`, and `grand_total`.
- Verify rows are saved in `tabamc_po_table` with `parent` equal to the created/updated `ICSS_PO` docname.
- Verify AMC summary fields are saved in `tabICSS_PO`.

Test non-AMC save:

- Call `save_icss_po_data` with any other indent type.
- Send no `amc_po_table`.
- Verify the `ICSS_PO` document saves, child table remains empty, and AMC summary fields remain empty.

## 19. Kafka Commit Module Override for ICSS PO Re-Commit

### 19.1 Requirement

The frontend PO re-commit card can send `moduleId = 14` while staging commit data. This is needed because the saved reference document is still `Indent Cum Sanction Sheet`, whose Module Registry ID resolves to `17`, but the PO generation re-commit must publish to Kafka with module ID `14`.

Normal ICSS commit behavior must remain unchanged:

- Pending Staff Approval / normal ICSS commit: frontend does not send a module override, so backend derives module ID from `Indent Cum Sanction Sheet` and publishes `17`.
- Pending PO Generation re-commit: frontend sends `moduleId = 14`, so backend publishes `14`.

### 19.2 Backend Implementation

Updated files:

- `rndopsapp/rndopsapp/commitPayment.py`
- `rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py`
- `rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py`

Implementation details:

- `submit_commit_data(..., moduleId=None, module_id=None)` now accepts an optional module override.
- If `moduleId` or `module_id` is supplied, it is stored inside `Kafka Commit Staging.payload` as `moduleId`.
- `check_workflow_and_publish()` reads `payload["moduleId"]` / `payload["module_id"]` and passes it to Kafka publishing.
- `manually_publish_staged_commit()` uses the same override path for manual re-publish.
- `publish_commit()` and `AccountHeadCommitProducer.publish()` pass the optional `module_id` to the mapper.
- `AccountHeadCommitMapper` resolves the override first. If no override is present, it falls back to `get_module_id(doc.doctype)`.

Effective mapper logic:

```python
module_id = payload.get("moduleId") or payload.get("module_id")

if module_id:
    publish with this module_id
else:
    publish with get_module_id(doc.doctype)
```

### 19.3 Frontend Contract

For normal ICSS commit staging, do not send `moduleId`:

```json
{
  "doctype": "Indent Cum Sanction Sheet",
  "name": "2026050710000832",
  "project_name": "PROJECT-001",
  "commit_amount": 50000,
  "budget_head": "Recurring"
}
```

For PO generation re-commit staging, send:

```json
{
  "doctype": "Indent Cum Sanction Sheet",
  "name": "2026050710000832",
  "project_name": "PROJECT-001",
  "commit_amount": 50000,
  "budget_head": "Recurring",
  "moduleId": 14
}
```

### 19.4 Deployment Notes

No DocType schema or SQL migration is required for this change because the override is stored inside the existing JSON `payload` field.

Run after pulling code:

```bash
bench --site <site-name> clear-cache
bench restart
```

### 19.5 Verification

Verify staging payload:

```sql
select reference_doctype, reference_name, payload, status
from `tabKafka Commit Staging`
where reference_doctype = 'Indent Cum Sanction Sheet'
order by modified desc
limit 5;
```

Expected:

- Normal ICSS staging may not contain `moduleId`.
- PO re-commit staging should contain `"moduleId": 14`.
- Kafka published payload should contain `data.moduleId = 14` for PO re-commit.
- Kafka published payload should contain `data.moduleId = 17` for normal ICSS commit.

## 20. Final Signed PO Delivery

### 20.1 Requirement

After staff/R&D uploads the signed/generated PO for an ICSS document, the backend must treat the application as complete with final status:

```text
PO Delivered
```

This replaces any frontend-only display workaround. Backend is now the source of truth.

Expected final flow:

```text
Pending PO Generation -> PO Generated -> PO Delivered
```

### 20.2 Backend Implementation

Updated files:

- `rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json`
- `rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py`
- `rndopsapp/rndopsapp/doctype/module_registry/module_registry.py`
- `rndopsapp/patches.txt`
- `rndopsapp/patches/add_icss_po_delivered_workflow.py`
- `rndopsapp/patches/__init__.py`

Added ICSS parent field:

```text
icss_signed_po_file
```

Field details:

- Field Type: `Attach`
- Label: `Signed PO Attachment`
- `allow_on_submit = 1`
- `read_only = 1`
- Stores the signed PO file URL for frontend `View Signed PO`.

Added whitelisted API:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.upload_icss_signed_po
```

API behavior:

- Accepts `docname`.
- Accepts either `file_url`, a multipart uploaded file, or base64 `file_name` + `file_data`.
- Allows upload only when ICSS is in `PO Generated`.
- Allows safe retry when already in `PO Delivered`.
- Stores direct uploads in MinIO under the ICSS project + ICSS document folder.
- Creates/links a `File` attachment row to the ICSS document.
- Stores the file URL in `icss_signed_po_file`.
- Sets `workflow_state = PO Delivered`.
- Syncs child doctype `workflow_state` when the child has that field.
- Commits the update.
- Returns the signed PO file URL in both `signed_po_attachment` and `icss_signed_po_file`.

MinIO storage folder for new uploads:

```text
rnd-files/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/
```

Example browser folder:

```text
http://172.16.135.118:9001/browser/rnd-files/Project_Registration%2F26RBSBESP0391XXLS0010%2Findent_cum_sanction_sheet%2F2026050710000832%2F
```

Backend stores the internal object path in ICSS:

```text
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/<filename>
```

If frontend sends a MinIO browser URL, backend normalizes it to the internal object path before saving.

Recommended ICSS file layout:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/
  applicant_attachments/
  director_approval/
  signed_po/
```

Examples:

```text
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/applicant_attachments/vendor-quotation.pdf
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/director_approval/director-signed.pdf
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf
```

This keeps all files for one ICSS document together even when the same project has multiple ICSS records.

### 20.3 Workflow Patch

Added migration patch:

```text
rndopsapp.patches.add_icss_po_delivered_workflow
```

Patch behavior:

- Ensures `Workflow State = PO Generated` exists.
- Ensures `Workflow State = PO Delivered` exists.
- Adds final workflow state `PO Delivered` to the active `Indent Cum Sanction Sheet` workflow.
- Removes manual workflow actions from `PO Generated` to `PO Delivered`.

The final state transition is intentionally API-driven:

```text
upload_icss_signed_po() -> workflow_state = PO Delivered
```

Reason:

- The frontend already has a dedicated signed PO upload button.
- Workflow action buttons like `Upload Signed PO` or `Deliver PO` should not appear beside it.
- The document should move to `PO Delivered` only after the signed PO file is successfully uploaded/stored.

Added cleanup patch:

```text
rndopsapp.patches.remove_icss_po_delivery_workflow_actions
```

This removes these duplicate manual workflow buttons from `PO Generated`:

- `Upload Signed PO`
- `Deliver PO`

### 20.4 Pending Task and Task Registry Behavior

Pending task behavior:

- `PO Delivered` is excluded from Staff/R&D pending tasks.
- Once signed PO is uploaded, the ICSS document should disappear from pending tasks.

Task registry behavior:

- Task Registry reads the current workflow/status field.
- After upload, it should show the ICSS document with status `PO Delivered`.

Applicant/permanent employee application list:

- ICSS parent data now contains `icss_signed_po_file`.
- Frontend can show `View Signed PO` when `icss_signed_po_file` has a URL.

### 20.5 Frontend Contract

If the file is already uploaded to MinIO:

```json
{
  "docname": "2026050710000832",
  "file_url": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf"
}
```

Frontend may also send the MinIO console browser file URL; backend will normalize it before saving.

If sending multipart form-data directly to `upload_icss_signed_po`, send the file under one of these keys:

- `file`
- `signed_po`
- `signed_po_attachment`
- `icss_signed_po_file`

If sending base64 JSON, send:

```json
{
  "docname": "2026050710000832",
  "file_name": "signed-po.pdf",
  "file_data": "data:application/pdf;base64,..."
}
```

Successful response:

```json
{
  "status": "success",
  "workflow_state": "PO Delivered",
  "signed_po_attachment": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf",
  "icss_signed_po_file": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf",
  "minio_folder": "Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po",
  "minio_browser_folder": "http://172.16.135.118:9001/browser/rnd-files/Project_Registration%2F26RBSBESP0391XXLS0010%2Findent_cum_sanction_sheet%2F2026050710000832%2Fsigned_po",
  "minio_browser_url": "http://172.16.135.118:9001/browser/rnd-files/Project_Registration%2F26RBSBESP0391XXLS0010%2Findent_cum_sanction_sheet%2F2026050710000832%2Fsigned_po%2Fsigned-po.pdf"
}
```

Backend validation:

- If `file_url` is a MinIO `Project_Registration/...` object path, it must be inside `/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/`.
- A folder-only URL is not enough; `file_url` must point to the actual signed PO file.

### 20.6 Deployment Notes

Run after pulling code:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

This change requires migration because:

- New ICSS DocType field `icss_signed_po_file` is added.
- Workflow state/transition patch is applied.

### 20.7 Verification

Verify field:

```sql
select fieldname, fieldtype, allow_on_submit
from `tabDocField`
where parent = 'Indent Cum Sanction Sheet'
and fieldname = 'icss_signed_po_file';
```

Expected:

```text
icss_signed_po_file | Attach | 1
```

Verify workflow states:

```sql
select name, workflow_state_name
from `tabWorkflow State`
where name in ('PO Generated', 'PO Delivered');
```

Verify workflow transition:

```sql
select wt.state, wt.action, wt.next_state, wt.allowed
from `tabWorkflow Transition` wt
join `tabWorkflow` w on wt.parent = w.name
where w.document_type = 'Indent Cum Sanction Sheet'
and wt.state = 'PO Generated';
```

Expected:

- State `PO Delivered` exists.
- No `Upload Signed PO` or `Deliver PO` workflow buttons exist from `PO Generated`.
- After calling upload API, ICSS `workflow_state` becomes `PO Delivered`.
- `icss_signed_po_file` stores the signed PO URL.

---

## 21. Implemented Director Approval PDF Gate

### 21.1 Planning Status

Status: **Implemented for ICSS backend.**

Implemented files:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
rndopsapp/APPS_DOCUMENTATION.md
indent_cum_sanction_sheet_implementation_doc.md
```

Local deployment/verification completed:

```bash
python3 -m py_compile rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
python3 -m json.tool rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json
bench --site prornd.local migrate
bench --site prornd.local clear-cache
bench restart
bench --site prornd.local execute rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_pending_director_uploads_icss
bench --site prornd.local execute rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_icss_director_approval_status --kwargs '{"docname": "2026050710000832"}'
```

Database columns verified locally:

```text
send_to_director
director_signed_pdf
director_approval_required
```

This section supersedes the older future note that suggested routing high-value ICSS documents to a separate `Pending Director Approval` workflow state.

Implementation boundary:

- This can be implemented independently for `Indent Cum Sanction Sheet`.
- No Selection Committee Report backend code needs to be touched.
- No SCR DocType fields or APIs are required for ICSS to work.
- ICSS will follow the same frontend-visible behavior pattern, but with ICSS-specific fields and APIs.

The proposed ICSS design keeps the existing HoS routing:

```text
Pending HoS Approval
  -> amount > 1L  -> Pending Dean Approval
  -> amount <= 1L -> Pending Associate Dean
```

Director approval will be enforced inside `Pending Dean Approval` as a document/file gate.

### 21.2 Reference Backend Check

Frontend reference mentioned:

```text
origin/mythos_omni_v0.2
```

Local backend branches checked:

```text
current working copy
origin/production-206
sketch/production-206
```

Selection Committee Report backend files checked:

```text
rndopsapp/rndopsapp/doctype/selection_committee_report/selection_committee_report.json
rndopsapp/rndopsapp/doctype/selection_committee_report/selection_committee_report.py
```

Result:

- SCR backend does **not** currently contain `send_to_director`.
- SCR backend does **not** currently contain `director_signed_pdf`.
- SCR backend does **not** currently contain `update_send_to_director_scr`.
- SCR backend does **not** currently contain `attach_director_pdf_scr`.
- SCR backend does **not** currently contain `get_pending_director_uploads_scr`.
- No fetched backend `mythos` branch is available in this local repo.
- Online remote check for `mythos` was not completed because network/approval was not available.

Conclusion:

ICSS Director Approval should be implemented as a new backend capability. It cannot be safely copied from the current SCR backend in this repo.

That is acceptable because the ICSS implementation only needs:

- ICSS DocType fields
- ICSS helper methods
- ICSS whitelisted APIs
- ICSS workflow approve guard

No shared SCR dependency is needed.

### 21.3 Business Flow

Target ICSS flow:

```text
Pending Dean Approval
  -> Dean reviews/downloads ICSS PDF
  -> Dean marks Send for Director Approval
  -> Staff/R&D receives offline Director-approved signed PDF
  -> Staff/R&D uploads Director-approved ICSS PDF
  -> Dean sees uploaded Director PDF
  -> Dean clicks Approve
  -> ICSS moves to Pending PO Generation
```

Important separation:

```text
director_signed_pdf = Director-approved ICSS PDF before Dean approval
icss_signed_po_file = final signed/generated PO after PO Generated
```

These fields must not be mixed.

### 21.4 Director Approval Trigger

Director approval is required only when ICSS is in `Pending Dean Approval` and:

- Account/budget head is Equipment and approval amount is greater than `10,00,000`.
- Account/budget head is not Equipment and approval amount is greater than `3,00,000`.

Use the existing ICSS amount helper:

```python
_get_icss_approval_amount(doc)
```

Proposed helper:

```python
def _is_icss_director_approval_required(doc):
    amount = _get_icss_approval_amount(doc)

    account_head = (
        doc.get("icss_account_head")
        or doc.get("icss_other_account_head")
        or ""
    )

    account_head_text = account_head

    try:
        budget_head = frappe.db.get_value(
            "Budget Head",
            account_head,
            ["budget_head", "name"],
            as_dict=True,
        )
        if budget_head:
            account_head_text = budget_head.budget_head or budget_head.name or account_head
    except Exception:
        pass

    is_equipment = "equipment" in str(account_head_text or "").lower()

    if is_equipment:
        return amount > 1000000

    return amount > 300000
```

Optional enhancement:

- Store calculated result in `director_approval_required` during validation/save for frontend visibility.
- Still recalculate server-side during workflow approval so the rule cannot be bypassed.

### 21.5 ICSS Fields To Add

Add these fields to:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json
```

Required fields:

```json
{
  "allow_on_submit": 1,
  "default": "0",
  "fieldname": "send_to_director",
  "fieldtype": "Check",
  "label": "Send for Director Approval"
}
```

```json
{
  "allow_on_submit": 1,
  "fieldname": "director_signed_pdf",
  "fieldtype": "Attach",
  "label": "Director Signed PDF",
  "read_only": 1
}
```

Optional field:

```json
{
  "allow_on_submit": 1,
  "default": "0",
  "fieldname": "director_approval_required",
  "fieldtype": "Check",
  "label": "Director Approval Required",
  "read_only": 1
}
```

Recommended placement:

- Put these near the existing signed PO/system workflow fields.
- Keep `director_signed_pdf` separate from `icss_signed_po_file`.
- Do not expose these as list-view columns unless frontend requests it.

Implementation status:

- Added to ICSS DocType JSON.
- Migrated locally to `tabIndent Cum Sanction Sheet`.

### 21.6 Backend APIs To Add

Add to:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
```

Required APIs:

```text
update_send_to_director_icss(docname, send_to_director)
attach_director_pdf_icss(docname, file_url)
get_pending_director_uploads_icss()
```

Additional helper API implemented:

```text
get_icss_director_approval_status(docname)
```

Frontend API paths:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.update_send_to_director_icss
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.attach_director_pdf_icss
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_pending_director_uploads_icss
```

### 21.7 API 1: Mark Send To Director

API:

```text
update_send_to_director_icss(docname, send_to_director)
```

Purpose:

- Dean marks an ICSS as requiring offline Director approval.

Rules:

- Allowed roles: `Dean, RnD`, `System Manager`.
- Consider allowing R&D admin role only if product confirms it.
- ICSS must be in `Pending Dean Approval`.
- `_is_icss_director_approval_required(doc)` must return true.
- This should be one-way: can set from `0` to `1`, cannot clear from `1` to `0`.

Response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "send_to_director": 1,
  "director_approval_required": 1
}
```

### 21.8 API 2: Attach Director PDF

API:

```text
attach_director_pdf_icss(docname, file_url)
```

Purpose:

- Staff/R&D attaches the Director-approved scanned ICSS PDF.

Rules:

- Allowed roles: `staff, RnD`, `RnD Staff`, `R&D Staff`, `System Manager`.
- `file_url` is required.
- ICSS must still be in `Pending Dean Approval`.
- `_is_icss_director_approval_required(doc)` must return true.
- `send_to_director` must already be `1`.
- Replacing an uploaded Director PDF is allowed while still in `Pending Dean Approval`.

Storage decision:

- If frontend already uploads to MinIO, backend can store the supplied `file_url`.
- Backend direct upload is also supported using multipart or base64, using the same MinIO service pattern as `upload_icss_signed_po`.
- Recommended folder:

```text
rnd-files/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/director_approval/
```

Response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "director_signed_pdf": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/director_approval/director-signed.pdf"
}
```

### 21.9 API 3: Pending Director Uploads

API:

```text
get_pending_director_uploads_icss()
```

Purpose:

- Staff/R&D upload page lists ICSS documents awaiting Director PDF upload.

Return records where:

- `send_to_director = 1`
- `workflow_state = Pending Dean Approval`
- Director approval is still required by threshold helper

Include already uploaded rows too, so Staff/R&D can view or replace the file.

Suggested fields:

```text
name
icss_indent_type
icss_applicant_name
icss_applicant_webmail_id
project_ref
project_no
icss_account_head
icss_other_account_head
director_signed_pdf
modified
workflow_state
```

Response:

```json
{
  "status": "success",
  "data": [
    {
      "name": "2026050710000832",
      "workflow_state": "Pending Dean Approval",
      "send_to_director": 1,
      "director_signed_pdf": "/Project_Registration/..."
    }
  ]
}
```

### 21.10 Dean Approve Guard

Add the guard inside:

```text
perform_icss_action(docname, action)
```

The guard must run before applying the workflow transition.

Rule:

```python
if (
    action == "Approve"
    and current_state == "Pending Dean Approval"
    and _is_icss_director_approval_required(doc)
    and not (doc.get("director_signed_pdf") or "").strip()
):
    frappe.throw(
        "Cannot approve: Director approval is required and the "
        "Director-signed PDF has not been uploaded by Staff yet."
    )
```

Important behavior:

- Only `Approve` is blocked.
- `Reject`, `Forward`, `Put Back`, or other non-approval actions should remain unaffected.
- Below-threshold ICSS records should approve normally.
- Above-threshold records should approve only after `director_signed_pdf` exists.

### 21.11 Workflow Impact

No new workflow state is required for this proposed implementation.

Existing flow remains:

```text
Pending HoS Approval
  -> Pending Dean Approval
  -> Pending PO Generation
```

Director approval is represented by fields:

```text
send_to_director
director_signed_pdf
director_approval_required
```

This is intentionally different from the final PO flow:

```text
Pending PO Generation -> PO Generated -> PO Delivered
```

### 21.12 Frontend Contract

Frontend should add:

```text
icssAPI.updateSendToDirector
icssAPI.attachDirectorPdf
icssAPI.getPendingDirectorUploads
```

Expected usage:

1. Dean page checks ICSS at `Pending Dean Approval`.
2. If backend metadata or doc data says Director approval is needed, show `Send for Director Approval`.
3. Dean calls `update_send_to_director_icss`.
4. Staff/R&D page calls `get_pending_director_uploads_icss`.
5. Staff/R&D uploads Director PDF to MinIO and calls `attach_director_pdf_icss`.
6. Dean reopens ICSS and sees `director_signed_pdf`.
7. Dean clicks normal `Approve`.
8. Backend allows approval and moves ICSS to `Pending PO Generation`.

### 21.13 Frontend API Handoff

Base DocType module path:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet
```

#### Existing APIs Frontend Will Continue Using

Get ICSS form metadata / existing record:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_icss_fields
```

Expected params:

```json
{
  "doc_name": "2026050710000832"
}
```

After implementation, `prefill_data` should include:

```json
{
  "send_to_director": 0,
  "director_signed_pdf": null,
  "director_approval_required": 1
}
```

Get available workflow actions:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_icss_workflow_actions
```

Expected params:

```json
{
  "docname": "2026050710000832"
}
```

Perform workflow action:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.perform_icss_action
```

Expected params:

```json
{
  "docname": "2026050710000832",
  "action": "Approve"
}
```

For Director-required ICSS at `Pending Dean Approval`, this call should fail until `director_signed_pdf` exists:

```json
{
  "status": "error",
  "message": "Cannot approve: Director approval is required and the Director-signed PDF has not been uploaded by Staff yet."
}
```

#### New API 1: Mark Send For Director Approval

Frontend wrapper suggestion:

```text
icssAPI.updateSendToDirector
```

Backend path:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.update_send_to_director_icss
```

Request:

```json
{
  "docname": "2026050710000832",
  "send_to_director": 1
}
```

Success response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "workflow_state": "Pending Dean Approval",
  "send_to_director": 1,
  "director_approval_required": 1,
  "director_signed_pdf": null
}
```

Frontend usage:

- Show this button only for Dean view when ICSS is in `Pending Dean Approval`.
- Backend will still enforce roles and threshold, so frontend does not need to be trusted.
- Once success is returned, show a status like `Sent for Director Approval`.

#### New API 2: Attach Director Signed PDF

Frontend wrapper suggestion:

```text
icssAPI.attachDirectorPdf
```

Backend path:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.attach_director_pdf_icss
```

Request when frontend already uploaded file to MinIO:

```json
{
  "docname": "2026050710000832",
  "file_url": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/director_approval/director-signed.pdf"
}
```

Alternative multipart upload:

- Method: `POST`
- Content-Type: `multipart/form-data`
- Fields:
  - `docname`
  - file key: `file`, `director_pdf`, `director_signed_pdf`, or `director_approval_pdf`

Alternative base64 upload:

```json
{
  "docname": "2026050710000832",
  "file_name": "director-signed.pdf",
  "file_data": "data:application/pdf;base64,..."
}
```

Success response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "workflow_state": "Pending Dean Approval",
  "send_to_director": 1,
  "director_approval_required": 1,
  "director_signed_pdf": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/director_approval/director-signed.pdf"
}
```

Frontend usage:

- This API does not move workflow state.
- It only stores/replaces the Director-approved ICSS PDF.
- Dean still has to click normal `Approve` after the file is uploaded.

#### New API 3: Get Pending Director Uploads

Frontend wrapper suggestion:

```text
icssAPI.getPendingDirectorUploads
```

Backend path:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_pending_director_uploads_icss
```

Request:

```json
{}
```

Success response:

```json
{
  "status": "success",
  "data": [
    {
      "name": "2026050710000832",
      "icss_indent_type": "Proprietary Purchase with Proprietary certificate from the OEM",
      "icss_applicant_name": "Lingraj Sahoo",
      "icss_applicant_webmail_id": "ls@iitg.ac.in",
      "project_ref": "2026032401MeiTy000667",
      "project_no": "26RBSBESP0391XXLS0010",
      "icss_account_head": "Equipment",
      "icss_other_account_head": null,
      "workflow_state": "Pending Dean Approval",
      "send_to_director": 1,
      "director_approval_required": 1,
      "director_signed_pdf": null,
      "modified": "2026-05-17 10:30:00"
    }
  ]
}
```

Frontend usage:

- Use this for Staff/R&D Director PDF upload screen.
- Include rows even if `director_signed_pdf` is already present so Staff/R&D can view/replace the PDF.
- Do not treat this as final PO delivery. Final PO still uses `upload_icss_signed_po`.

#### New API 4: Get Director Approval Status

This API is implemented for a cleaner Dean UI.

Frontend wrapper suggestion:

```text
icssAPI.getDirectorApprovalStatus
```

Backend path:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_icss_director_approval_status
```

Request:

```json
{
  "docname": "2026050710000832"
}
```

Success response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "workflow_state": "Pending Dean Approval",
  "approval_amount": 1250000,
  "account_head": "Equipment",
  "director_approval_required": 1,
  "send_to_director": 1,
  "director_signed_pdf": "/Project_Registration/..."
}
```

Frontend can use this API for a lightweight status check, or read the same fields from `get_icss_fields(doc_name)` when loading the full ICSS form.

### 21.14 Frontend Display Rules

Dean page:

- If `workflow_state != "Pending Dean Approval"`, do not show Director approval controls.
- If `director_approval_required != 1`, show normal approval flow.
- If `director_approval_required == 1` and `send_to_director != 1`, show `Send for Director Approval`.
- If `send_to_director == 1` and `director_signed_pdf` is empty, show `Waiting for Director Signed PDF`.
- If `director_signed_pdf` exists, show `View Director Signed PDF` and allow normal `Approve`.

Staff/R&D Director upload page:

- Fetch records using `get_pending_director_uploads_icss`.
- Show upload control for each row.
- After upload to MinIO, call `attach_director_pdf_icss`.
- After success, refresh the list or update the row locally.

Important frontend warning:

- `director_signed_pdf` is for Director-approved ICSS PDF before Dean approval.
- `icss_signed_po_file` is for final signed/generated PO after `PO Generated`.
- These two upload controls should be separate in UI and state logic.

### 21.15 ICSS File Storage Standard

All new ICSS uploads should be stored under the same project and ICSS document folder:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/
```

For example, for project `26RBSBESP0391XXLS0010` and ICSS docname `2026050710000832`:

```text
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/
```

Recommended category folders:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/applicant_attachments/
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/director_approval/
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/signed_po/
```

File examples:

```text
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/applicant_attachments/quotation.pdf
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/director_approval/director-signed.pdf
/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf
```

Backend direct-upload APIs should create/use the category folder automatically.

If frontend uploads to MinIO first and then sends `file_url`, backend should validate that the path starts with:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/
```

Reason:

- One project can have multiple ICSS documents.
- The ICSS docname folder prevents Director PDFs, signed POs, and applicant attachments from mixing across different ICSS records.
- It also makes production file audits easier because the project folder remains the top-level owner and the ICSS number becomes the exact application folder.

Backward compatibility:

- Existing already-uploaded files may remain at the older path.
- New uploads should use the docname-scoped path.
- If needed, backend can accept old paths for read/view only, but new upload/save responses should return the new path.

### 21.16 Backend Implementation Summary

Implemented:

1. Added ICSS JSON fields:
   - `send_to_director`
   - `director_signed_pdf`
   - `director_approval_required`
2. Added helper `_is_icss_director_approval_required(doc)`.
3. Calculates/stores `director_approval_required` during validation/save when possible.
4. Added whitelisted APIs:
   - `update_send_to_director_icss`
   - `attach_director_pdf_icss`
   - `get_pending_director_uploads_icss`
   - `get_icss_director_approval_status`
5. Added Dean `Approve` guard inside `perform_icss_action`.
6. `get_icss_fields(...)` now returns computed `director_approval_required`.
7. Signed PO uploads now use the docname-scoped `signed_po` folder.
8. Director PDF uploads use the docname-scoped `director_approval` folder.
9. ICSS parent/child attachment payloads saved through ICSS APIs use the docname-scoped `applicant_attachments` folder.
10. Compile, JSON validation, migrate, cache clear, and bench restart completed locally.

### 21.17 Deployment Plan After Confirmation

Files expected to change:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.json
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
indent_cum_sanction_sheet_implementation_doc.md
```

Optional if a DB patch is preferred for existing sites:

```text
rndopsapp/patches/add_icss_director_approval_fields.py
rndopsapp/patches.txt
```

Normal deployment commands:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

No separate SQL deployment should be required if the JSON fields are included and `bench migrate` is run.

### 21.18 Verification Checklist

Field verification:

```sql
show columns from `tabIndent Cum Sanction Sheet` like 'send_to_director';
show columns from `tabIndent Cum Sanction Sheet` like 'director_signed_pdf';
show columns from `tabIndent Cum Sanction Sheet` like 'director_approval_required';
```

Functional verification:

- Equipment ICSS with amount `> 10L` reaches `Pending Dean Approval`.
- Non-equipment ICSS with amount `> 3L` reaches `Pending Dean Approval`.
- Dean `Approve` is blocked for those records when `director_signed_pdf` is empty.
- Dean can set `send_to_director = 1`.
- Staff/R&D pending upload API lists the flagged ICSS record.
- Staff/R&D can attach/replace `director_signed_pdf`.
- Dean can approve after Director PDF upload.
- Approved record moves to `Pending PO Generation`.
- Below-threshold ICSS records are not blocked.
- `icss_signed_po_file` and `PO Delivered` behavior remains unaffected.

---

## 22. Implemented Dynamic Put-Back Engine

### 22.1 Planning Status

Status: **Implemented for ICSS backend.**

Implemented files:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
rndopsapp/APPS_DOCUMENTATION.md
indent_cum_sanction_sheet_implementation_doc.md
```

Verification completed:

```bash
python3 -m py_compile rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
bench --site prornd.local clear-cache
bench restart
bench --site prornd.local execute rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_available_icss_put_back_actions --kwargs '{"docname": "2026050710000832"}'
```

Smoke-test result for sample approved ICSS:

```json
{"status": "success", "docname": "2026050710000832", "current_state": "Approved", "actions": []}
```

This section documents the ICSS-only dynamic put-back engine similar to the Strategy C pattern tested for Indent General Form.

Goal:

- Avoid adding many duplicate `Put Back to X` rows in the Frappe Workflow Transition table.
- Keep forward/approval transitions inside the normal Workflow document.
- Handle backward movement through two whitelisted backend APIs.
- Keep parent ICSS and linked child doctype workflow states in sync.
- Add a visible audit comment for every put-back action.

### 22.2 Why Dynamic Put-Back Is Useful For ICSS

ICSS has multiple approval states:

```text
Draft
Pending PI Approval
Pending Staff Approval
Pending HoS Approval
Pending Dean Approval
Pending Associate Dean
Pending PO Generation
PO Generated
PO Delivered
```

If every approver needs multiple backward targets, the Workflow Transition table becomes noisy and fragile.

The dynamic engine keeps the workflow compact:

- Forward actions remain configured in Frappe Workflow.
- Backward actions are generated dynamically from backend config.
- Frontend asks backend which put-back targets are allowed for the current user/state.
- Backend directly updates `workflow_state` after validating role, current state, and target.

### 22.3 Recommended Scope For First Implementation

Implement put-back only for approval-stage records before PO generation:

```text
Pending PI Approval
Pending Staff Approval
Pending HoS Approval
Pending Dean Approval
Pending Associate Dean
```

Do not include these states initially:

```text
Pending PO Generation
PO Generated
PO Delivered
```

Reason:

- `Pending PO Generation` can already mean approval is complete and commit/PO work may have started.
- `PO Generated` and `PO Delivered` are post-approval operational states.
- Reversing those states may require undoing PO/commit side effects, so that should be a separate confirmed business rule.

### 22.4 Implemented Backend Config

Add to:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
```

Implemented target map:

```python
ICSS_PUT_BACK_TARGETS = {
    "Requestor": "Draft",
    "PI": "Pending PI Approval",
    "Staff": "Pending Staff Approval",
    "HoS": "Pending HoS Approval",
}
```

Implemented rule map:

```python
ICSS_PUT_BACK_RULES = {
    "Pending PI Approval": {
        "roles": ["Permanent Employee", "head_approver_1", "HoD", "System Manager"],
        "targets": ["Requestor"],
    },
    "Pending Staff Approval": {
        "roles": ["staff, RnD", "System Manager"],
        "targets": ["PI", "Requestor"],
    },
    "Pending HoS Approval": {
        "roles": ["Hos, RnD (Head of Section, RnD)", "System Manager"],
        "targets": ["Staff", "PI", "Requestor"],
    },
    "Pending Dean Approval": {
        "roles": ["Dean, RnD", "System Manager"],
        "targets": ["HoS", "Staff", "PI", "Requestor"],
    },
    "Pending Associate Dean": {
        "roles": ["Ado_RnD", "System Manager"],
        "targets": ["HoS", "Staff", "PI", "Requestor"],
    },
}
```

Note:

- `PI` target is useful only for ICSS records that actually passed through `Pending PI Approval`.
- If product wants a simpler model, Staff can be limited to only `Requestor`, and higher approvers can be limited to only the immediate previous stage.
- Backend can optionally hide `PI` target if the ICSS was created by a Permanent Employee / HoD and never needed PI approval.

### 22.5 Implemented APIs

Added these whitelisted APIs:

```text
get_available_icss_put_back_actions(docname)
put_back_icss(docname, target, reason=None)
```

Full paths:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_available_icss_put_back_actions
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.put_back_icss
```

### 22.6 API 1: Get Available Put-Back Actions

Purpose:

- Frontend calls this on ICSS detail page to know whether to show a put-back dropdown/button.

Request:

```json
{
  "docname": "2026050710000832"
}
```

Response when actions are available:

```json
{
  "status": "success",
  "current_state": "Pending Dean Approval",
  "actions": [
    {
      "target": "HoS",
      "label": "Put Back to HoS",
      "next_state": "Pending HoS Approval"
    },
    {
      "target": "Staff",
      "label": "Put Back to Staff",
      "next_state": "Pending Staff Approval"
    },
    {
      "target": "PI",
      "label": "Put Back to PI",
      "next_state": "Pending PI Approval"
    },
    {
      "target": "Requestor",
      "label": "Put Back to Requestor",
      "next_state": "Draft"
    }
  ]
}
```

Response when not allowed:

```json
{
  "status": "success",
  "current_state": "Pending Staff Approval",
  "actions": []
}
```

### 22.7 API 2: Apply Put-Back

Purpose:

- Applies a validated backward state movement.

Request:

```json
{
  "docname": "2026050710000832",
  "target": "HoS",
  "reason": "Please correct budget head remarks."
}
```

Response:

```json
{
  "status": "success",
  "docname": "2026050710000832",
  "from": "Pending Dean Approval",
  "to": "Pending HoS Approval",
  "target": "HoS",
  "next_actions": ["Approve", "Reject"],
  "data": {
    "name": "2026050710000832",
    "workflow_state": "Pending HoS Approval"
  }
}
```

Validation:

- `docname` must exist.
- `target` must exist in `ICSS_PUT_BACK_TARGETS`.
- Current `workflow_state` must exist in `ICSS_PUT_BACK_RULES`.
- Current user must have one of the configured roles for the current state.
- Target must be allowed from the current state.
- Cannot put back from `PO Delivered`.
- Cannot put back from `PO Generated`.
- Cannot put back from `Pending PO Generation` unless product explicitly confirms it later.

### 22.8 State Update Behavior

Backend should not call Frappe `apply_workflow` for put-back.

Reason:

- `apply_workflow` requires a Workflow Transition row for every source/target pair.
- The dynamic engine exists specifically to avoid duplicating those transition rows.

Recommended behavior:

```python
frappe.db.set_value(DOCTYPE, docname, "workflow_state", next_state, update_modified=True)
```

Then sync child doctype:

```python
doc.reload()
doc._sync_sub_doctype_workflow_state(next_state)
```

Then add audit comment and commit.

### 22.9 Audit Trail

Every put-back should create a `Comment` row:

```python
frappe.get_doc({
    "doctype": "Comment",
    "comment_type": "Workflow",
    "reference_doctype": DOCTYPE,
    "reference_name": docname,
    "content": f"Put back to {target} ({next_state}) by {frappe.session.user} from {current_state}. Reason: {reason}",
}).insert(ignore_permissions=True)
```

This makes the action visible in the document activity log without needing extra custom tables.

### 22.10 Director Approval Interaction

When ICSS is put back from `Pending Dean Approval` to any lower state, Director approval data may become stale because applicant/staff may change amount, account head, or attachments.

Recommended behavior:

- If current state is `Pending Dean Approval` and target is `HoS`, `Staff`, `PI`, or `Requestor`, clear:
  - `send_to_director`
  - `director_signed_pdf`
  - `director_approval_required`
- On next save/validation, `director_approval_required` will be recalculated.
- Dean can send again for Director approval if the corrected ICSS still crosses the threshold.

Alternative:

- Keep `director_signed_pdf` and only clear `send_to_director`.
- This is less safe because the signed PDF may no longer match corrected ICSS data.

Recommendation for first implementation:

- Clear Director approval fields when putting back from `Pending Dean Approval`.

### 22.11 Frontend Contract

Frontend should add:

```text
icssAPI.getAvailablePutBackActions
icssAPI.putBack
```

Backend paths:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_available_icss_put_back_actions
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.put_back_icss
```

Frontend flow:

1. On ICSS detail page load, call `get_available_icss_put_back_actions(docname)`.
2. If `actions` is empty, hide put-back UI.
3. If `actions` has values, show dropdown/menu using `label`.
4. Require a short reason text before calling `put_back_icss`.
5. Call `put_back_icss(docname, target, reason)`.
6. On success, refresh ICSS details and pending task list.
7. Use returned `workflow_state` / `data.workflow_state` to update status pill.

Compatibility behavior:

- `get_icss_workflow_actions(docname)` also appends dynamic labels such as `Put Back to Staff`, `Put Back to PI`, and `Put Back to Requestor`.
- Legacy/generic Workflow-table actions named `Put Back` are filtered out from `get_icss_workflow_actions`.
- `perform_icss_action(docname, "Put Back to Staff")` delegates to `put_back_icss(docname, "Staff")`.
- This means existing frontend screens that only read `get_icss_workflow_actions` can still show put-back options without integrating the separate put-back-list API immediately.

Important:

- Frontend should not directly set `workflow_state`.
- Frontend should not create fake workflow actions like `Put Back to HoS` in the Workflow Transition table.
- Frontend should only use backend-returned targets.

### 22.12 Pending Task / Registry Impact

Because the engine directly updates `workflow_state`:

- Module Registry pending task logic should show the ICSS under the new target role/state.
- Frappe Desk list status should show the new state through the existing hidden `workflow_state` list indicator.
- Linked child doctype should mirror the parent workflow state.

No separate SQL should be required if this is implemented only in Python.

### 22.13 Implementation Summary

Files changed:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
rndopsapp/APPS_DOCUMENTATION.md
indent_cum_sanction_sheet_implementation_doc.md
```

Implemented:

1. Added `ICSS_PUT_BACK_TARGETS`.
2. Added `ICSS_PUT_BACK_RULES`.
3. Added helper `_get_available_icss_put_back_action_rows(doc, user_roles=None)`.
4. Added helper `_clear_icss_director_fields_for_put_back(current_state)`.
5. Added helper `_add_icss_put_back_comment(...)`.
6. Added API `get_available_icss_put_back_actions(docname)`.
7. Added API `put_back_icss(docname, target, reason=None)`.
8. Parent `workflow_state` is updated directly with `frappe.db.set_value(...)`.
9. Linked child doctype `workflow_state` is synced after put-back.
10. Director approval fields are cleared when putting back from `Pending Dean Approval`.
11. Workflow comment audit trail is created.
12. API returns updated composite ICSS payload.
13. `get_icss_workflow_actions` appends dynamic put-back action labels for existing frontend compatibility.
14. Legacy `Put Back` Workflow-table action labels are hidden from the workflow action API.
15. `perform_icss_action` delegates dynamic `Put Back to X` labels to `put_back_icss`.
16. `APPS_DOCUMENTATION.md` was updated.
17. Python compile check passed.

No migration is required because this implementation adds Python APIs only and no new DocType fields.

### 22.14 Verification Checklist

Smoke checks:

- Staff user at `Pending Staff Approval` can see `Put Back to Requestor`.
- Staff user cannot put back from `Pending HoS Approval`.
- HoS user at `Pending HoS Approval` can put back to `Staff`, `PI`, or `Requestor`.
- Dean user at `Pending Dean Approval` can put back to `HoS`, `Staff`, `PI`, or `Requestor`.
- Associate Dean user at `Pending Associate Dean` can put back to `HoS`, `Staff`, `PI`, or `Requestor`.
- Unauthorized user receives no available actions and cannot call `put_back_icss`.
- Child doctype `workflow_state` matches parent after put-back.
- Comment is created in the ICSS activity log.
- Director approval fields are cleared when putting back from `Pending Dean Approval`.
- `Pending PO Generation`, `PO Generated`, and `PO Delivered` return no put-back actions.

Suggested command checks after implementation:

```bash
python3 -m py_compile rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
bench --site <site-name> clear-cache
bench restart
```
