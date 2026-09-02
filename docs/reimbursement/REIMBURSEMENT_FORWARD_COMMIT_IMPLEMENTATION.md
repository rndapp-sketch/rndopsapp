# Reimbursement Forward and Commit Implementation

## Overview

In this codebase, **Reimbursement forwarding** and **Reimbursement commit publishing** are handled by two different modules:

- `Reimbursement` doctype APIs handle form loading, saving, editing, and workflow movement.
- `commitPayment.py` handles publishing commit/payment events to Kafka and integrating with the ledger service.

This means:

1. Saving a Reimbursement document does **not** automatically publish a commit.
2. Forwarding a Reimbursement document does **not** automatically publish a commit.
3. Commit publishing must be triggered separately by calling the commit API.

---

## Main Files

- Reimbursement doctype logic: `rndopsapp/rndopsapp/doctype/reimbursement/reimbursement.py`
- Reimbursement schema: `rndopsapp/rndopsapp/doctype/reimbursement/reimbursement.json`
- Reimbursement child table schema: `rndopsapp/rndopsapp/doctype/particulars_of_items_reimbursement/particulars_of_items_reimbursement.json`
- Commit/Payment integration: `rndopsapp/rndopsapp/commitPayment.py`
- Kafka commit/payment producer: `rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py`
- Kafka DTO mapper: `rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py`

---

## 1. Reimbursement Form Load

### API

`get_reimbursement_fields(doc_name=None)`

### What it does

This API is used by the frontend to build the reimbursement form.

It returns:

- Parent field metadata from the `Reimbursement` DocType
- Child table field metadata for `table_bosk`
- Prefill data for current user
- Project-linked prefill data when a Project Registration document is passed
- Link options for users, budget heads, projects, sanctions, fund received entries

### Important prefill behavior

If `doc_name` is a `Project Registration` name, the API fills:

- `project_name`
- `project_number`
- `sanction_ref_no` when exactly one sanction exists
- applicant details from the logged-in user

### Source

- `rndopsapp/rndopsapp/doctype/reimbursement/reimbursement.py`

---

## 2. Reimbursement Save Flow

### API

`save_reimbursement_data(data)`

### What the frontend sends

The frontend sends a JSON object or JSON string containing:

- Parent fields like `project_name`, `project_number`, `account_head`, `comment`
- Applicant/bank details
- Declaration checkboxes `dec1` to `dec4`
- Child rows in `table_bosk`

### Parent fields saved

The save method copies these fields into the `Reimbursement` document:

- `project_number`
- `project_name`
- `account_head`
- `other_head`
- `comment`
- `bank_name`
- `account_holder_name`
- `bank_account_number`
- `ifsc_code`
- `applicant_webmail`
- `applicant_department`
- `applicant_designation`
- `reimbursement_for_id`
- `reimbursement_for_department`
- `reimbursement_for_designation`
- `dec1`
- `dec2`
- `dec3`
- `dec4`
- `amended_from`

### Child table saved

The child table is `table_bosk`, linked to `Particulars of Items Reimbursement`.

Each row may contain:

- `r_date`
- `vendors_name`
- `particulars`
- `amount`
- `uploads`

### Attachment handling

If a child row contains:

```json
{
  "uploads": {
    "file_name": "bill.pdf",
    "file_data": "base64..."
  }
}
```

the backend saves the file using `save_file()` and replaces the field value with the saved file URL.

### Database effect

Frappe saves:

- parent data into `tabReimbursement`
- child rows into `tabParticulars of Items Reimbursement`
- uploaded files into `tabFile`

### Important note

The save flow only stores document data. It does **not** create any account-head commit.

---

## 3. Reimbursement Edit Flow

### API

`edit_reimbursement(data)`

### Rule

Editing is only allowed when:

- `docstatus == 0`
- `workflow_state == "Draft"`

If the document has already been forwarded or submitted, edit is blocked.

### Behavior

It updates the same parent fields and child table structure as `save_reimbursement_data()`.

---

## 4. Forward Flow in Reimbursement

### APIs

- `get_reimbursement_workflow_actions(docname)`
- `perform_reimbursement_action(docname, action)`
- `submit_reimbursement(docname)`

### How forwarding works

In this module, "forward" means moving the document to the next workflow state.

The backend does this by:

1. Loading the current Reimbursement document
2. Reading the active `Workflow` for document type `Reimbursement`
3. Finding the transition whose:
   - `state == current workflow_state`
   - `action == requested action`
4. Setting `doc.workflow_state = next_state`
5. Submitting, cancelling, or saving the doc based on the target workflow state's `doc_status`
6. Committing the DB transaction

### Forward implementation

`perform_reimbursement_action(docname, action)` is the main forward API.

`submit_reimbursement(docname)` is a convenience wrapper that assumes the first action is `"Submit"` from `"Draft"`.

### Important note

This Reimbursement module does **not** create explicit forwarding records like:

- `ToDo`
- `DocShare`
- notification routing

inside `reimbursement.py`.

So from the code currently present, "forward" is primarily a **workflow state transition**, not a separate assignment engine.

### Result returned to frontend

The API returns:

- `status`
- `message`
- `docname`
- `workflow_state`
- `next_actions`

---

## 5. Commit Flow for Reimbursement

### API

`rndopsapp.rndopsapp.commitPayment.submit_commit_data`

### Signature

```python
submit_commit_data(
    doctype,
    frapAppId,
    name,
    project_name,
    commit_amount,
    budget_head,
    bmr=None,
    bill_amount=None,
    refDetails=None
)
```

### What it does

This API is separate from Reimbursement save/forward.

It:

1. Loads the Frappe document using `doctype` and `name`
2. Calls `kafka_publish_commit(...)`
3. Builds a Kafka DTO through the reimbursement mapper
4. Validates the DTO
5. Publishes the message to topic:

`account-head-commit-events`

### Actual publisher used

`commitPayment.submit_commit_data()` calls:

- `rndopsapp.rndopsapp.kafka.producer.reimbursement.publish_commit`

which internally uses:

- `AccountHeadCommitProducer.publish(...)`

---

## 6. How Commit Payload is Built

### Mapper

The commit payload is built in:

`rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py`

### Mapping logic

The mapper builds a DTO with:

- `projectNumber`
- `accountHeadId`
- `commitAmount`
- `commitDate`
- `commitParticular`
- `refDetails`
- `status`
- `frapAppId`
- `moduleId`
- `billAmount`

### projectNumber resolution

`project_name` passed to commit API is resolved to a project number using `get_project_number()`.

Lookup order:

1. `Project Registration.project_no`
2. `Project Registration.name`
3. raw value passed by caller

### accountHeadId resolution

`budget_head` is converted into numeric `accountHeadId` by:

1. accepting a numeric value directly
2. looking up `Budget Head.name`
3. looking up `Budget Head.budget_head`

### commitParticular generation

For Reimbursement, the mapper reads `table_bosk` rows and collects each row's `particulars`.

If rows contain particulars, it joins them as:

`item1, item2, item3`

If not, it falls back to:

`Commitment for <doc.name>`

### moduleId generation

The mapper checks `Module Registry Item` using the source doctype name and resolves an `idx` value as `moduleId`.

If not found, it falls back to default `7`.

### Final event envelope

The Kafka message is wrapped as:

```json
{
  "schemaVersion": "1.0",
  "eventType": "ACCOUNT_HEAD_COMMIT",
  "timestamp": "UTC ISO timestamp",
  "data": {
    "transactionCommitNumber": null,
    "projectNumber": "...",
    "accountHeadId": 12,
    "transactionReceivedRefNumber": 8,
    "commitDate": "YYYY-MM-DD",
    "commitParticular": "...",
    "refDetails": "...",
    "commitAmount": 1000.0,
    "status": "COMMITTED",
    "frapAppId": "...",
    "moduleId": 7,
    "billAmount": 1000.0
  }
}
```

---

## 7. Important Behavioral Observations

### 1. Commit is not automatic

There is no call to `submit_commit_data()` inside:

- `save_reimbursement_data()`
- `edit_reimbursement()`
- `perform_reimbursement_action()`
- `submit_reimbursement()`

So commit publishing must be triggered separately by frontend or another service.

### 2. Forward and commit are decoupled

A reimbursement can be forwarded in workflow without any commit being published.

### 3. Commit amount is trusted from API input

`submit_commit_data()` receives `commit_amount` as a parameter.

It does **not** calculate commit amount from `table_bosk.amount` values.

That means the caller is responsible for sending the correct commit total.

### 4. Child row amounts are stored but not used for commit automatically

The child table contains an `amount` field, but the commit mapper uses child rows only for `commitParticular`.

It does not sum the row amounts.

### 5. Kafka publish success/failure is separate from reimbursement save

Even if reimbursement is saved correctly in DB, commit publishing can still fail independently.

---

## 8. End-to-End Sequence

### A. Save reimbursement

1. Frontend calls `get_reimbursement_fields()`
2. Frontend renders form and prefill data
3. User enters reimbursement details
4. Frontend calls `save_reimbursement_data(data)`
5. Backend stores parent, child rows, and uploads in Frappe DB

### B. Forward reimbursement

1. Frontend calls `get_reimbursement_workflow_actions(docname)`
2. User selects action such as `Submit` or another workflow action
3. Frontend calls `perform_reimbursement_action(docname, action)` or `submit_reimbursement(docname)`
4. Backend updates `workflow_state`
5. Backend submits/saves/cancels based on workflow state's `doc_status`

### C. Publish commit

1. Frontend or service calls `submit_commit_data(...)`
2. Backend loads the reimbursement document
3. Mapper builds commit DTO
4. Validator checks required fields
5. Producer publishes to Kafka topic `account-head-commit-events`

---

## 9. Recommended Frontend Responsibility

If the intended business flow is:

"Save reimbursement -> forward for approval -> publish commit"

then the frontend or orchestration layer should explicitly decide **when** to call commit publish.

Typical safe options are:

- after reimbursement save
- after reimbursement reaches a specific approved workflow state
- after a staff-level verification step

Right now the backend does not enforce any of these automatically for Reimbursement.

---

## 10. Practical Conclusion

### Forward

Forwarding in Reimbursement is implemented as a workflow transition in `reimbursement.py`.

### Commit

Commit is implemented as a separate Kafka publishing call in `commitPayment.py`.

### Key takeaway

Reimbursement workflow and Reimbursement financial commit are currently **loosely coupled**, not automatic.

