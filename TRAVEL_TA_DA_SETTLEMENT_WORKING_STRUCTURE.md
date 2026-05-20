# Travel and TA/DA Settlement Working Structure

## Overview

This document explains the current implementation of the **Travel** and **TA/DA Settlement** flow in `rndopsapp`, including:

- related files
- form APIs
- workflow APIs
- pending-task/task-page behavior
- commit staging and Kafka publishing
- document relationships
- working sequence from Travel request to TA/DA Settlement approval

This document should be read together with:

- `TRAVEL_FORWARD_COMMIT_IMPLEMENTATION.md`

That file explains the Travel forward/commit split in detail. This document extends that and covers the full **Travel -> TA/DA Settlement** structure.

---

## Functional Relationship

The two doctypes are related, but they are not the same stage of the process:

1. **Travel**
   - created before travel
   - captures travel request, project, purpose, estimate, account head, leave details, and approval flow
   - can create a staged financial commitment through the shared commit flow

2. **TA DA Settlement**
   - created after travel against an existing Travel document
   - captures final claimed amount, advance adjustment, other expenses, declarations, and settlement workflow
   - also uses the shared commit staging flow and publishes only after final approval

So the working chain is:

`Travel request -> Travel approvals -> Travel commitment -> TA/DA Settlement creation from Travel -> TA/DA approvals -> TA/DA commitment publish on approval`

---

## User-Facing Pages and Screens

### 1. Travel form

Primary backend doctype:

- `rndopsapp/rndopsapp/doctype/travel/travel.json`
- `rndopsapp/rndopsapp/doctype/travel/travel.py`
- `rndopsapp/rndopsapp/doctype/travel/travel.js`

Usage:

- create/edit Travel request
- submit Travel request
- fetch workflow actions
- fetch commit panel details for pending task flow

### 2. TA/DA Settlement form

Primary backend doctype:

- `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.json`
- `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.py`
- `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.js`

Usage:

- create settlement linked to Travel
- prefill applicant/project/bank/travel information from Travel
- submit settlement
- fetch workflow actions
- fetch commit panel details for pending task flow

### 3. Pending Task page

There is no dedicated `page/travel` or `page/ta_da_settlement` folder in the repo.

Task-style approval UI is driven through the generic pending task infrastructure:

- `rndopsapp/rndopsapp/doctype/module_registry/module_registry.py`
- `rndopsapp/rndopsapp/doctype/module_registry/module_registry.json`
- `rndopsapp/rndopsapp/doctype/module_registry_item/module_registry_item.json`

This is how Travel and TA/DA Settlement appear in approval/task screens.

### 4. Utility / menu mapping

Feature visibility is also related to:

- `rndopsapp/rndopsapp/doctype/utility_access/utility_access.json`

It contains utility categorization such as `travel`, `advance`, `purchase`, etc. This is part of how modules/pages are grouped in the frontend utility system.

---

## Main Related Files

| Area | File | Purpose |
|------|------|---------|
| Travel schema | `rndopsapp/rndopsapp/doctype/travel/travel.json` | Travel fields, layout, fetch rules, conditions |
| Travel backend | `rndopsapp/rndopsapp/doctype/travel/travel.py` | load/save/submit/workflow/commit detail APIs |
| Travel client behavior | `rndopsapp/rndopsapp/doctype/travel/travel.js` | project number auto-fill, SCL balance UI, leave warning |
| Travel tests | `rndopsapp/rndopsapp/doctype/travel/test_travel.py` | Travel tests |
| TA/DA schema | `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.json` | TA/DA field definitions |
| TA/DA backend | `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.py` | field metadata, prefill, save, submit, workflow, commit detail |
| TA/DA client behavior | `rndopsapp/rndopsapp/doctype/ta_da_settlement/ta_da_settlement.js` | currently minimal/commented |
| TA/DA tests | `rndopsapp/rndopsapp/doctype/ta_da_settlement/test_ta_da_settlement.py` | TA/DA tests |
| TA/DA child table | `rndopsapp/rndopsapp/doctype/ta_da_other_expense/ta_da_other_expense.json` | Other expense rows in settlement |
| Shared commit staging | `rndopsapp/rndopsapp/commitPayment.py` | `submit_commit_data`, staging, manual publish helpers |
| Kafka staging doctype | `rndopsapp/rndopsapp/doctype/kafka_commit_staging/kafka_commit_staging.json` | stores staged commit payload |
| Kafka commit mapper | `rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py` | converts business docs to commit DTO |
| Kafka commit producer | `rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py` | publishes `ACCOUNT_HEAD_COMMIT` event |
| Pending tasks | `rndopsapp/rndopsapp/doctype/module_registry/module_registry.py` | fetches actionable records for current user |
| Pending task registry child table | `rndopsapp/rndopsapp/doctype/module_registry_item/module_registry_item.json` | stores doctype rows per page |
| Utility grouping | `rndopsapp/rndopsapp/doctype/utility_access/utility_access.json` | utility/page categorization |
| Budget head master | `rndopsapp/rndopsapp/doctype/budget_head/budget_head.json` | commit budget head resolution |
| SCL balance support | `rndopsapp/rndopsapp/doctype/special_leave_balance/special_leave_balance.py` | Travel SCL balance credit/deduct/reverse helpers |
| SCL balance schema | `rndopsapp/rndopsapp/doctype/special_leave_balance/special_leave_balance.json` | yearly balance record structure |
| SCL transaction log schema | `rndopsapp/rndopsapp/doctype/scl_transaction_log/scl_transaction_log.json` | child log for credit/deduction/reversal history |
| SCL scheduler tasks | `rndopsapp/rndopsapp/tasks/scl_credit.py` | January/July auto-credit and manual credit helper |
| App scheduler hooks | `rndopsapp/hooks.py` | cron registration for SCL auto-credit |
| Existing reference doc | `TRAVEL_FORWARD_COMMIT_IMPLEMENTATION.md` | prior Travel forward/commit explanation |

---

## Travel Working Structure

### 1. Form metadata load

API:

- `get_travel_fields(doc_name=None)`

Purpose:

- returns field metadata for Travel
- returns `depends_on`, `mandatory_depends_on`, `read_only_depends_on`
- returns parsed eval expressions
- returns link options
- returns existing doc data when editing
- prefills current user details

Key prefill fields:

- `webmail_id_travel`
- `applicant_name_travel`
- `designation_travel`
- `department_travel`

### 2. Travel client-side logic

`travel.js` is active and important now. It handles:

- auto-populating `webmail_id_travel` for new docs
- auto-fetching `travel_project_number` from `travel_project_title`
- loading Special Casual Leave balance
- showing SCL balance card
- showing warning when requested SCL days exceed available balance

### 3. Travel save flow

API:

- `save_travel(doc_data)`

Behavior:

- creates or updates Travel document
- handles standard fields
- handles file fields using backend file save logic
- handles tables if present
- saves data into Travel doctype and attachments into `tabFile`

### 4. Travel workflow flow

APIs:

- `submit_travel(docname)`
- `get_travel_workflow_actions(docname)`
- `perform_travel_action(docname, action)`

Behavior:

- `submit_travel` is the initial submit entry
- `get_travel_workflow_actions` returns actions allowed for current user/state
- `perform_travel_action` executes `Forward`, `Approve`, `Reject`, etc.

Special logic:

- if Travel reaches `Approved` and `travel_special_casual_leave == "Required"`, SCL is deducted through `special_leave_balance.py`
- if Travel reaches `Approved`, pending staged commit records are searched and published to Kafka

### 5. Travel commit panel behavior

API:

- `get_travel_commit_details(docname)`

Purpose:

- provides project, amount, account head, dates, travel nature, purpose, and module information to the pending task commit UI

Important point:

- the Travel doctype itself does not directly store commit transaction output
- commit is handled through shared staging in `commitPayment.py`

---

## Special Leave Balance Structure

Special Casual Leave is implemented as a separate balance subsystem used by the Travel module.

It is primarily relevant when:

- the Travel applicant is eligible for SCL
- `travel_special_casual_leave == "Required"`
- leave dates are entered on the Travel form
- Travel eventually reaches `Approved`

### 1. Main SCL files

- `rndopsapp/rndopsapp/doctype/special_leave_balance/special_leave_balance.py`
- `rndopsapp/rndopsapp/doctype/special_leave_balance/special_leave_balance.json`
- `rndopsapp/rndopsapp/doctype/scl_transaction_log/scl_transaction_log.json`
- `rndopsapp/rndopsapp/tasks/scl_credit.py`
- `rndopsapp/hooks.py`
- `rndopsapp/rndopsapp/doctype/travel/travel.py`
- `rndopsapp/rndopsapp/doctype/travel/travel.js`

### 2. Balance record doctype

The balance master is the `special_leave_balance` doctype.

Naming pattern:

- `{employee}-{year}`

Example:

- `user@iitg.ac.in-2026`

Main fields:

- `employee`
- `year`
- `total_credited`
- `utilized_balance`
- `available_balance`
- `last_credit_date`
- `scl_log`

Computed behavior:

- `available_balance = max(0, total_credited - utilized_balance)`

This is enforced in `before_save` inside `special_leave_balance.py`.

### 3. SCL transaction log

Each balance record contains child table `scl_log` using doctype `SCL Transaction Log`.

Transaction log fields:

- `transaction_date`
- `transaction_type`
- `days`
- `reference_doctype`
- `reference_name`
- `remarks`

Supported transaction types:

- `Credit`
- `Deduction`
- `Reversal`

This gives the audit trail for:

- scheduler credits
- Travel approval deductions
- Travel cancellation reversals
- manual test/backfill credits

### 4. Core balance helper methods

Main helper functions in `special_leave_balance.py`:

- `get_or_create_balance_record(employee, year)`
- `credit_leaves(employee, year, days, remarks="")`
- `deduct_leaves(employee, year, days, reference_doctype="Travel", reference_name="", remarks="")`
- `reverse_leaves(employee, year, days, reference_doctype="Travel", reference_name="", remarks="")`
- `get_special_leave_balance(employee=None)`

What they do:

- `get_or_create_balance_record` creates a year record if it does not exist
- `credit_leaves` adds credited days and appends a `Credit` log row
- `deduct_leaves` increases `utilized_balance` if enough balance exists
- `reverse_leaves` reduces `utilized_balance` and appends a `Reversal` row
- `get_special_leave_balance` returns the API response used by Travel UI

Important behavior:

- `deduct_leaves` returns `False` when balance is insufficient
- it does not raise an exception by itself
- caller decides whether to block or just warn

### 5. Eligibility logic

The current code treats SCL as available only to a specific employee class.

In `special_leave_balance.py`:

- `_is_permanent_employee(employee)` checks the user's `empclass`
- then compares the linked `EmployeeClass_prornd.empclass_name`
- the constant used is `_PERMANENT_CLASS_PREFIX = "PI - Principal Investigator"`

In scheduler code `scl_credit.py`:

- `_get_all_eligible_employees()` fetches enabled `User` records
- excludes `Guest` and `Administrator`
- filters by `empclass`
- the `EmployeeClass_prornd` lookup is also based on `_PERMANENT_CLASS_PREFIX = "PI - Principal Investigator"`

So the current implementation says "permanent employees" in comments, but the actual matching key in code is:

- `"PI - Principal Investigator"`

That means eligibility depends on how `EmployeeClass_prornd` is configured in the site database.

### 6. Travel form integration

Travel exposes SCL through both backend and frontend layers.

Relevant Travel APIs/helpers:

- `get_special_leave_balance_for_travel(employee=None)`
- `_safe_get_scl_balance(employee)`
- `_build_scl_balance_html(balance_info)`

Travel form behavior:

- Travel backend injects live balance HTML into the `travel_leave_balance_html` field
- `travel.js` fetches the same balance again for live rendering and warnings
- the form shows whether the applicant is eligible
- the form shows total credited, utilized, and available balance
- the form warns when requested days exceed the available balance

Travel fields involved:

- `travel_special_casual_leave`
- `travel_leave_from_date`
- `travel_leave_to_date`
- `travel_leave_balance_html`
- `webmail_id_travel`

### 7. How requested SCL days are calculated

Travel calculates requested leave days using:

- `_calculate_scl_days(doc)`

Logic:

- if `travel_leave_from_date` or `travel_leave_to_date` is missing -> `0`
- otherwise `date_diff(to_date, from_date) + 1`
- negative values are guarded by `max(0, ...)`

So the requested period is inclusive of both start and end date.

### 8. Deduction on Travel approval

Deduction happens in Travel workflow processing, not in the scheduler.

Relevant method:

- `_deduct_scl_on_approval(doc)`

Trigger:

- Travel moves to `Approved`
- `travel_special_casual_leave == "Required"`

Deduction flow:

1. get employee from `webmail_id_travel`
2. calculate requested days from leave dates
3. derive year from `travel_leave_from_date`
4. call `deduct_leaves(...)`
5. if insufficient balance, log warning
6. approval still continues unless code is changed to hard block

Important current behavior:

- insufficient SCL balance does not stop Travel approval
- it only writes a warning to the error log
- there is a commented `frappe.throw(...)` line showing how to enforce hard blocking if required later

### 9. Reversal on Travel cancellation

Reversal is exposed through:

- `cancel_travel_scl(docname)`

Purpose:

- restore SCL utilization when a Travel application is cancelled

Flow:

1. load Travel doc
2. check whether SCL was required
3. recalculate days from Travel leave dates
4. derive year from leave start date
5. call `reverse_leaves(...)`
6. append a `Reversal` entry in SCL log

Important note:

- this is a callable helper for cancel flow
- it is not documented in the current file as an automatic workflow hook
- frontend or another flow must call it when Travel cancellation needs balance reversal

### 10. Scheduler and auto-credit flow

SCL auto-credit is configured in app hooks.

File:

- `rndopsapp/hooks.py`

Configured scheduler events:

- `0 0 1 1 *` -> `rndopsapp.rndopsapp.tasks.scl_credit.credit_january_scl`
- `0 0 1 7 *` -> `rndopsapp.rndopsapp.tasks.scl_credit.credit_july_scl`

This means:

- January 1 at 00:00 -> first half-year credit
- July 1 at 00:00 -> second half-year credit

### 11. January credit job

Method:

- `credit_january_scl()`

Behavior:

- gets current year
- fetches all eligible employees
- creates the year record if missing
- adds `15` days for the first half-year credit
- skips employees already credited at least `15` days

Guard behavior:

- prevents double-crediting when January credit already exists

### 12. July credit job

Method:

- `credit_july_scl()`

Behavior:

- gets current year
- fetches all eligible employees
- gets or creates the year record
- adds another `15` days
- skips employees already credited at least `30` days total

Resulting yearly model:

- January credit: `15`
- July credit: `+15`
- total yearly credit target: `30`

### 13. Manual SCL credit helper

There is also a manual helper:

- `manual_credit(employee, year, half)`

Supported values:

- `half = "january"`
- `half = "july"`

Purpose:

- backfill
- testing
- one-off manual correction

### 14. Storage and audit behavior

SCL data is stored separately from Travel.

Storage layout:

- yearly balance -> `tabspecial_leave_balance`
- transaction rows -> child table under `SCL Transaction Log`
- Travel document only references SCL through applicant, leave dates, and approval logic

This means:

- Travel is the business trigger
- `special_leave_balance` is the balance ledger
- `SCL Transaction Log` is the audit trail

### 15. What the current document now covers for SCL

The implementation now includes:

- SCL eligibility check
- balance record structure
- transaction log structure
- Travel form balance display
- Travel approval deduction logic
- Travel cancellation reversal logic
- January scheduler credit
- July scheduler credit
- manual credit helper
- storage model

### 16. Important SCL implementation notes

1. Eligibility naming is slightly confusing.
   Comments talk about permanent employees, but the constant being matched is `"PI - Principal Investigator"`.

2. Insufficient balance does not block Travel approval.
   It logs a warning instead.

3. Cancellation reversal is helper-based.
   It must be called by the cancel flow; it is not shown here as an automatic workflow hook.

4. Year is derived from leave start date for deduction/reversal.
   This matters for leave spanning year boundaries.

---

## TA/DA Settlement Working Structure

### 1. Form metadata load

API:

- `get_ta_da_settlement_fields(doc_name=None, travel_ref=None)`

Purpose:

- returns field metadata for TA/DA Settlement
- returns link options
- returns child table metadata
- returns existing document data for edit mode
- optionally prefills from a linked Travel document

### 2. TA/DA prefill from Travel

When `travel_ref` is passed, TA/DA pulls data from Travel:

| Travel field | TA/DA field |
|------|------|
| `name` | `ta_da_travel_application` |
| `applicant_name_travel` | `ta_da_name` |
| `designation_travel` | `ta_da_designation` |
| `department_travel` | `ta_da_department_section` |
| `travel_project_number` | `project_no` |
| `webmail_id_travel` | `webmail_id` |
| User `employee_id` | `ta_da_employee_number` |
| `bank_account_holder` | `ta_da_bank_account_holder` |
| `bank_account_number` | `ta_da_bank_account_number` |
| `ifsc_code` | `ta_da_ifsc_code` |
| `purpose_of_visit` | `ta_da_purpose_of_journey` |
| `account_head` | `ta_da_account_head` |
| `total_estimate` | `ta_da_advance_taken` |

This means TA/DA Settlement is not a standalone process. It is structurally designed to be created from Travel.

### 3. TA/DA save flow

API:

- `save_ta_da_settlement(doc_data)`

Behavior:

- creates or updates TA/DA Settlement
- blocks editing if document is already submitted/cancelled
- maps frontend keys to doctype fields
- derives `applicant_category` from linked user `empclass`
- rebuilds child table `ta_da_other_expenses_p`
- commits to database

Child table used:

- `TA DA Other Expense`

Child fields:

- `ta_da_expense_type_other_expense`
- `ta_da_amount_other_expense`
- `ta_da_proof_other_expense`

Important implementation note:

- unlike Travel save, TA/DA save does not perform backend `save_file(...)` handling for attachments
- it stores the value passed in `ta_da_proof_other_expense`
- so file upload behavior depends on the frontend already supplying a valid attachment/file URL

### 4. TA/DA workflow flow

APIs:

- `submit_ta_da_settlement(docname)`
- `get_ta_da_settlement_workflow_actions(docname)`
- `perform_ta_da_settlement_action(docname, action)`

Behavior:

- `submit_ta_da_settlement` does not directly call `doc.submit()`
- it routes initial submission through `perform_ta_da_settlement_action(docname, "Submit")`
- workflow actions are role-based
- `perform_ta_da_settlement_action` also ensures `applicant_category` is available before transition logic

Approval side effect:

- when state becomes `Approved`, staged commit payloads are searched in `Kafka Commit Staging`
- matching records with status `PENDING_APPROVAL` or `FAILED` are republished to Kafka
- on success, staging status becomes `PUBLISHED`

### 5. TA/DA commit panel behavior

API:

- `get_ta_da_settlement_commit_details(docname)`

Returned business data includes:

- linked travel application
- project name and project number
- total claimed
- advance taken
- net claimed
- `commit_amount`
- `budget_head`
- purpose of journey
- module id
- `ref_details`

Current commit logic:

- TA/DA is always treated as funded from `Travel Head`
- `commit_amount = ta_da_net_claimed or ta_da_total_claimed or 0`
- `ref_details` is set to the linked Travel document name

---

## TA/DA Workflow Structure

Active workflow from repo audit:

- `TA_DA_settlement_workflow`

Main states:

1. `Draft`
2. `Pending PI Approval`
3. `Pending Staff Approval`
4. `Pending HoS Approval`
5. `Pending Associate Dean`
6. `Pending Dean Approval`
7. `Approved`
8. `Rejected`

Initial submission routing depends on applicant category:

- Permanent Employee / Independent Researcher / Inspire Faculty -> `Pending Staff Approval`
- Project Staff / Student -> `Pending PI Approval`

Approval routing after staff:

- `Pending Staff Approval -> Forward -> Pending HoS Approval`

Amount-based routing at HoS stage:

- if `ta_da_total_claimed <= 30000` -> `Pending Associate Dean`
- if `ta_da_total_claimed > 30000` -> `Pending Dean Approval`

Final approval:

- `Pending Associate Dean -> Approve -> Approved`
- `Pending Dean Approval -> Approve -> Approved`

Put back paths exist from PI, Staff, HoS, Associate Dean, and Dean stages.

Reject paths also exist.

---

## Shared Commit and Kafka Structure

### 1. Staging API

Shared API in:

- `rndopsapp/rndopsapp/commitPayment.py`

Main method:

- `submit_commit_data(...)`

Purpose:

- validates document existence
- builds commit payload
- inserts or updates `Kafka Commit Staging`
- stores status as `PENDING_APPROVAL`

Staging doctype:

- `Kafka Commit Staging`

Main fields:

- `reference_doctype`
- `reference_name`
- `status`
- `payload`
- `error_message`

Possible status values:

- `PENDING_APPROVAL`
- `PUBLISHED`
- `FAILED`

### 2. Publish trigger

For Travel and TA/DA Settlement, publishing is handled inside their doctype action methods:

- `perform_travel_action`
- `perform_ta_da_settlement_action`

On `Approved`:

- fetch staging records for the same doctype/document
- parse payload
- call Kafka producer
- update staging status

### 3. Kafka producer layer

Main files:

- `rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py`
- `rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py`

Producer event type:

- `ACCOUNT_HEAD_COMMIT`

Main topic:

- `account-head-commit-events`

Mapper responsibilities:

- resolve project number
- resolve budget head id
- derive module id from `Module Registry Item`
- generate commit particulars

Default particulars fallback:

- `Commitment for <doc.name>`

For TA/DA Settlement, because there is no dedicated mapper branch for TA/DA expense rows, the generic fallback particulars can be used unless other child-table data is available.

---

## Pending Task and Working Page Structure

The approval/task view is generic, not module-specific.

Main file:

- `rndopsapp/rndopsapp/doctype/module_registry/module_registry.py`

How it works:

1. fetches current user roles
2. loads `Module Registry` row for a page such as `pending-task`
3. iterates registered doctypes from `Module Registry Item`
4. loads each doctype's workflow
5. calculates actionable states for current user
6. fetches matching records
7. returns grouped records for frontend task rendering

This is the same infrastructure through which Travel and TA/DA Settlement approval cards/buttons are surfaced.

Important point:

- approval actions are not tied to dedicated `page/travel` or `page/ta_da_settlement` backend page folders in this repo
- they are surfaced through the generic pending-task mechanism

---

## Data Storage Structure

### Travel side

- parent data -> `tabTravel`
- uploaded attachments -> `tabFile`
- workflow state -> Travel document field `workflow_state`
- SCL balance usage -> `special_leave_balance` doctype records
- commit staging -> `tabKafka Commit Staging`

### TA/DA side

- parent data -> `tabTA DA Settlement`
- child rows -> `tabTA DA Other Expense`
- workflow state -> TA/DA Settlement field `workflow_state`
- commit staging -> `tabKafka Commit Staging`

---

## Suggested End-to-End Frontend Sequence

### Travel

1. call `get_travel_fields`
2. create/edit and call `save_travel`
3. call `submit_travel` or `perform_travel_action(..., "Submit")`
4. call `get_travel_workflow_actions` to render next task buttons
5. in pending task commit card:
   - call `get_travel_commit_details`
   - call shared `submit_commit_data`
   - then call `perform_travel_action(..., "Forward")`
6. final approver moves Travel to `Approved`
7. staged commit is published to Kafka

### TA/DA Settlement

1. call `get_ta_da_settlement_fields(travel_ref=<travel_docname>)`
2. prefill from Travel
3. save using `save_ta_da_settlement`
4. submit using `submit_ta_da_settlement`
5. call `get_ta_da_settlement_workflow_actions` for buttons
6. in pending task commit card:
   - call `get_ta_da_settlement_commit_details`
   - call shared `submit_commit_data`
   - then call `perform_ta_da_settlement_action(..., "Forward")`
7. final approver moves settlement to `Approved`
8. staged commit is published to Kafka

---

## Known Implementation Notes

### 1. Travel workflow lookup inconsistency

Travel currently uses two different lookup styles:

- `get_travel_workflow_actions()` uses hardcoded `"Travel_Workflow"`
- `perform_travel_action()` fetches active workflow from DB

This is already noted in `TRAVEL_FORWARD_COMMIT_IMPLEMENTATION.md` and still matters.

### 2. Module id lookup inconsistency

There is an inconsistency between commit/detail code and mapper code:

- `get_travel_commit_details()` and `get_ta_da_settlement_commit_details()` read `mod_vis`
- Kafka mapper `get_module_id()` reads `idx`

So the UI-side `module_id` value and Kafka-side `moduleId` derivation are not using the same source column.

### 3. TA/DA attachment handling is lighter than Travel

Travel save explicitly handles attachment persistence.

TA/DA save:

- rebuilds child rows
- copies proof field values
- does not itself save binary uploads

### 4. TA/DA doctype is workflow-based even though `Approved` has `doc_status = 0`

In the workflow audit:

- `Approved` state is not a `docstatus=1` submitted state

So the approval lifecycle is controlled through `workflow_state`, not traditional final Frappe submission semantics alone.

---

## Quick Reference APIs

### Travel

- `get_travel_fields(doc_name=None)`
- `save_travel(doc_data)`
- `submit_travel(docname)`
- `get_travel_workflow_actions(docname)`
- `perform_travel_action(docname, action)`
- `get_travel_commit_details(docname)`

### TA/DA Settlement

- `get_ta_da_settlement_fields(doc_name=None, travel_ref=None)`
- `save_ta_da_settlement(doc_data)`
- `submit_ta_da_settlement(docname)`
- `get_ta_da_settlement_workflow_actions(docname)`
- `perform_ta_da_settlement_action(docname, action)`
- `get_ta_da_settlement_commit_details(docname)`

### Shared commit layer

- `submit_commit_data(...)`
- `manually_publish_staged_commit(...)`

---

## Summary

The current architecture is:

- **Travel** is the source request and approval document
- **TA/DA Settlement** is the post-travel settlement document created from Travel
- both use workflow-driven approval
- both use the shared commit staging system
- both appear in generic pending-task infrastructure rather than dedicated page folders
- final Kafka commit publishing happens only when the document reaches `Approved`

If needed, this can be extended next with:

- exact field-by-field Travel schema documentation
- exact field-by-field TA/DA schema documentation
- sequence diagrams for Travel and TA/DA approval flows
- API payload examples for frontend integration
