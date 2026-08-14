# Travel Forward and Commit Implementation

## Overview

The Travel task page shown in the screenshot has two separate backend flows:

- **Forward button**: handled by the Travel workflow APIs in `travel.py`
- **Commit panel**: handled by the shared commit/ledger APIs in `commitPayment.py`

These two are not the same feature.

In the current implementation:

1. Saving a Travel document stores only Travel form data.
2. Clicking **Forward** changes the Travel document's workflow state.
3. Clicking **Commit** publishes a separate account-head commit event to Kafka.
4. Forwarding Travel does **not** automatically create a commit.

---

## Main Files

- Travel doctype logic: `rndopsapp/rndopsapp/doctype/travel/travel.py`
- Travel schema: `rndopsapp/rndopsapp/doctype/travel/travel.json`
- Shared commit/payment API: `rndopsapp/rndopsapp/commitPayment.py`
- Alternate cached-commit helper: `rndopsapp/rndopsapp/commitToJsonFrappe.py`
- Kafka commit producer: `rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py`
- Kafka commit mapper: `rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py`

---

## UI Mapping From the Screenshot

### 1. Forward button

The **Forward** button at the top-right of the task page is implemented as a workflow action call against the Travel document.

Expected backend flow:

1. frontend asks which actions are allowed for the current Travel doc
2. frontend shows `Forward` if the current user has an allowed workflow action
3. when clicked, frontend sends the selected action to the Travel workflow API
4. backend updates `workflow_state`

### 2. Make a Commitment panel

The **Make a Commitment** card on the right is a separate financial action.

Expected backend flow:

1. frontend loads available balance for the project
2. user selects a budget head and enters amount
3. frontend calls the shared commit API
4. backend publishes an `ACCOUNT_HEAD_COMMIT` event to Kafka

This commit is not stored as a field inside the Travel doctype itself.

---

## 1. Travel Form Load

### API

`get_travel_fields(doc_name=None)`

### What it does

This method returns everything the frontend needs to render the Travel form:

- Travel field metadata
- `depends_on` / `mandatory_depends_on` / `read_only_depends_on`
- extracted eval expressions for frontend logic
- link options for Link fields
- client scripts stored in Frappe
- child table metadata if any table fields exist
- existing document data when `doc_name` is provided
- current logged-in user prefill

### Current user prefill

If the user is logged in, backend prefills:

- `webmail_id_travel`
- `applicant_name_travel`
- `designation_travel`
- `department_travel`

### Important observation

The local DocType JS file `travel.js` is basically empty, so the actual task UI is likely a custom React/frontend page that consumes these APIs.

---

## 2. Travel Save Flow

### API

`save_travel(doc_data)`

### What it does

This API saves or updates a `Travel` document from frontend JSON.

### Save sequence

1. parse incoming JSON
2. load existing Travel doc if `name` exists, otherwise create a new one
3. copy standard fields into the document
4. separate file fields and table fields
5. insert/save once to get `doc.name`
6. process attachments and table rows
7. save again
8. commit DB transaction

### File handling

For Attach or Attach Image fields:

- if frontend sends `{ file_name, file_data }`
- backend uses `save_file(...)`
- backend stores returned file URL in the document

### Result

Parent Travel data is stored in:

- `tabTravel`

Uploaded files are stored in:

- `tabFile`

### Important note

The save API does **not** create a financial commit.

---

## 3. How the Forward Button Works

The screenshot shows a **Forward** button. In backend terms, this is implemented as a workflow action.

### APIs involved

- `get_travel_workflow_actions(docname)`
- `perform_travel_action(docname, action)`

### Step A: frontend asks available actions

`get_travel_workflow_actions(docname)`:

1. loads the Travel document
2. reads current state from `doc.workflow_state` or defaults to `"Draft"`
3. gets current user roles
4. loads workflow definition
5. checks transitions that match current state
6. returns only actions allowed for the user's roles

### Workflow lookup behavior

There is a small inconsistency in implementation:

- `get_travel_workflow_actions()` hardcodes workflow name as `"Travel_Workflow"`
- `perform_travel_action()` looks up the active workflow in DB where:
  - `document_type = "Travel"`
  - `is_active = 1`

So the frontend action list and actual action execution may depend on slightly different workflow lookup paths.

### Step B: frontend triggers forward

When user clicks **Forward**, frontend should call:

`perform_travel_action(docname, action)`

### What `perform_travel_action()` does

1. loads the Travel document
2. gets current `workflow_state`
3. fetches the active Travel workflow
4. finds the matching transition where:
   - current state matches
   - action matches
   - current user has one of the allowed roles
5. sets:
   - `doc.workflow_state = next_state`
6. checks workflow state's `doc_status`
7. based on target state:
   - `doc.submit()` if target is submitted state
   - `doc.cancel()` if target is cancelled state
   - `doc.save(ignore_permissions=True)` otherwise
8. commits the transaction
9. returns updated state and next actions

### Return to frontend

The method returns:

- `status`
- `message`
- `docname`
- `workflow_state`
- `next_actions`

### Practical meaning of the Forward button

In this codebase, **Forward** is not a separate special API.

It is simply a frontend label for one workflow transition action returned by:

- `get_travel_workflow_actions(docname)`

and executed by:

- `perform_travel_action(docname, action)`

---

## 4. Submit vs Forward in Travel

There is also:

`submit_travel(docname)`

### Important difference

`submit_travel()` directly calls:

- `doc.submit()`

It does not perform workflow transition logic like `perform_travel_action()`.

So for the task page in your screenshot, the **Forward** button is more likely using:

- `perform_travel_action(docname, action)`

not `submit_travel(docname)`.

---

## 5. How the Commit Panel Works

The right-side **Make a Commitment** panel is a separate financial flow from Travel approval.

### APIs involved

- `get_project_available_amounts(project_number)`
- `submit_commit_data(...)`

Both are in:

- `rndopsapp/rndopsapp/commitPayment.py`

### Step A: load available balance

The panel first needs available project balance.

That is done through:

`get_project_available_amounts(project_number)`

### What it does

This method calls the external ledger API and returns:

- `projectNumber`
- `totalFundReceived`
- `totalCommitted`
- `totalPaid`
- `availableCommitAmount`
- `availablePaymentAmount`
- `actualBalance`
- `committable`

That is what likely powers the text shown in UI like:

`Available: ₹19,09,179.99`

### Step B: submit commit

When the user selects budget head and enters amount, frontend should call:

`submit_commit_data(doctype, frapAppId, name, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None)`

For Travel, typical arguments would be:

- `doctype = "Travel"`
- `name = <travel document name>`
- `project_name = <project reference>`
- `commit_amount = <amount entered in panel>`
- `budget_head = <selected budget head>`

### What this method does

1. loads the source Travel document
2. calls Kafka producer helper `kafka_publish_commit(...)`
3. mapper converts Travel doc + API parameters into DTO
4. validator checks required fields
5. producer publishes event to Kafka topic:

`account-head-commit-events`

### Success response

If publish succeeds, it returns:

```json
{
  "status": "success",
  "message": "Commit published to Kafka"
}
```

---

## 6. How Travel Commit Payload is Built

The commit DTO is built by the shared mapper in:

`kafka/producer/reimbursement/mapper.py`

Even though the folder says `reimbursement`, it is reused for Travel, Temporary Advance, and others.

### Fields mapped into commit DTO

The DTO contains:

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

### projectNumber

The mapper resolves the project reference through `get_project_number()`.

It tries:

1. `Project Registration.project_no`
2. `Project Registration.name`
3. fallback to raw input

### accountHeadId

The selected budget head from the commit panel is converted into numeric `accountHeadId` by:

1. using it directly if numeric
2. resolving `Budget Head.name`
3. resolving `Budget Head.budget_head`

### moduleId

The mapper reads `Module Registry Item` using the doctype name.

For Travel, module ID is expected to resolve through the registry, and project docs mention Travel commonly maps to module slot `6`.

### commitParticular for Travel

This is an important implementation detail.

The shared mapper builds `commitParticular` from:

- `table_bosk` rows for Reimbursement
- `expenditure_details` rows for Advance Settlement

Travel does not populate either of these structures.

So for Travel, the mapper usually falls back to:

`Commitment for <travel_doc.name>`

That means Travel commit text is generic unless frontend explicitly sends useful `refDetails`.

---

## 7. Is Travel Commit Saved in Travel Doctype?

No, not directly.

The commit panel does not write commit amount or budget head into Travel fields in `travel.py`.

Instead, it sends a separate financial transaction to Kafka/ledger using `submit_commit_data(...)`.

So:

- Travel document remains in `tabTravel`
- commit transaction goes to Kafka / external ledger flow

This is why Travel workflow and Travel financial commit are loosely coupled.

---

## 8. Alternate Cached Commit Flow

There is also another commit helper:

- `rndopsapp/rndopsapp/commitToJsonFrappe.py`

This version does not publish immediately to Kafka.

Instead it:

1. maps commit DTO
2. writes it into JSON file:
   - `private/files/disbursement_of_honorarium_commits.json`
3. stores pending commit data locally

### Important note

This helper is currently generic in function signature, but the file name and documented use are tied to Honorarium delayed-approval flow.

For normal Travel commit behavior shown in your screenshot, the main implementation is more likely:

- `commitPayment.submit_commit_data(...)`

not the JSON-cache version.

---

## 9. End-to-End Travel Task Flow

### A. User opens Travel task page

1. frontend calls `get_travel_fields(doc_name)`
2. backend returns metadata + existing doc values
3. frontend renders form and side panels

### B. Forward button flow

1. frontend calls `get_travel_workflow_actions(docname)`
2. backend returns actions allowed for current user
3. frontend labels one of those actions as `Forward`
4. user clicks Forward
5. frontend calls `perform_travel_action(docname, action)`
6. backend updates `workflow_state`
7. backend submits/saves/cancels depending on target workflow state

### C. Commit panel flow

1. frontend reads project number from Travel doc
2. frontend calls `get_project_available_amounts(project_number)`
3. user chooses budget head and commit amount
4. frontend calls `submit_commit_data("Travel", frapAppId, docname, project_name, commit_amount, budget_head, ...)`
5. backend publishes `ACCOUNT_HEAD_COMMIT` to Kafka

---

## 10. Key Behavioral Conclusions

### 1. Forward is workflow-based

The Forward button is implemented through Travel workflow APIs, not through a special forward-only endpoint.

### 2. Commit is a separate shared service

The commit panel uses the shared ledger/Kafka API in `commitPayment.py`, not Travel doctype fields.

### 3. Forward does not auto-commit

There is no call from:

- `save_travel()`
- `submit_travel()`
- `perform_travel_action()`

to:

- `submit_commit_data()`

So commit must be triggered separately by frontend.

### 4. Travel commit description is generic by default

Because Travel does not provide mapper-specific child rows for commit particulars, the commit text usually becomes:

`Commitment for <doc.name>`

### 5. Small workflow inconsistency exists

`get_travel_workflow_actions()` hardcodes `"Travel_Workflow"`, but `perform_travel_action()` fetches active workflow from DB.

If those ever differ, the action list shown to frontend and the action execution logic may not perfectly match.

---

## Practical Conclusion

### Forward button

Implemented by:

- `get_travel_workflow_actions(docname)`
- `perform_travel_action(docname, action)`

### Commit button

Implemented by:

- `get_project_available_amounts(project_number)`
- `submit_commit_data(...)`

### Final takeaway

Travel approval workflow and Travel commitment posting are currently **two separate backend flows** connected by the frontend task page.

