# ICSS Kafka Commit, PO Re-Commit, And Final PO Delivery Flow

**Module:** Indent Cum Sanction Sheet  
**Parent DocType:** `Indent Cum Sanction Sheet`  
**PO DocType:** `ICSS_PO`  
**Staging DocType:** `Kafka Commit Staging`  
**Purpose:** Explain how ICSS commit data is staged, published to Kafka on Dean/Associate Dean approval, re-committed during PO generation, and finally closed as `PO Delivered`.

---

## 1. High-Level Lifecycle

The ICSS lifecycle has three separate backend concerns:

| Stage | Workflow State | Backend Concern |
|---|---|---|
| Staff/R&D review | `Pending Staff Approval` | Stage commit data in `Kafka Commit Staging` |
| Dean/Associate Dean approval | `Approve` -> `Pending PO Generation` | Publish staged commit to Kafka |
| PO generation | `Generate PO`: `Pending PO Generation` -> `PO Generated` | Save generated PO and stage/publish PO re-commit with module override |
| Signed PO upload | `PO Generated` -> `PO Delivered` | Store signed PO file and close ICSS |

Important separation:

- Normal ICSS commit uses the ICSS module ID, normally resolved from `Indent Cum Sanction Sheet`.
- PO generation re-commit uses `moduleId = 14` because the business module is PO generation even though the reference document is still ICSS.
- Final signed PO delivery is not a Kafka commit operation; it stores the signed PO file and moves ICSS to `PO Delivered`.

---

## 2. Backend Files Involved

ICSS workflow and final PO delivery:

```text
rndopsapp/rndopsapp/doctype/indent_cum_sanction_sheet/indent_cum_sanction_sheet.py
```

ICSS PO save:

```text
rndopsapp/rndopsapp/doctype/icss_po/icss_po.py
```

Commit staging and publish:

```text
rndopsapp/rndopsapp/commitPayment.py
```

Kafka commit producer:

```text
rndopsapp/rndopsapp/kafka/producer/reimbursement/producer.py
```

Kafka commit mapper:

```text
rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py
```

Workflow patches for final PO delivery:

```text
rndopsapp/patches/add_icss_po_delivered_workflow.py
rndopsapp/patches/remove_icss_po_delivery_workflow_actions.py
```

---

## 3. Step 1: Frontend Gets ICSS Commit Details

At `Pending Staff Approval`, frontend should fetch commit-related defaults from:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_icss_commit_details
```

Request:

```json
{
  "docname": "2026050710000832"
}
```

Response contains values frontend can use to prefill `submit_commit_data`:

```json
{
  "docname": "2026050710000832",
  "workflow_state": "Pending Staff Approval",
  "project_name": "2026032401MeiTy000667",
  "project_number": "26RBSBESP0391XXLS0010",
  "budget_head": "Recurring",
  "account_head": "Recurring",
  "indent_type": "Annual Maintenance Contract",
  "child_doctype": "AMC",
  "child_docname": "AMC-0001",
  "commit_amount": 50000,
  "module_id": 17,
  "ref_details": "AMC-0001"
}
```

Important fields:

- `project_name` / `project_number`: project reference/number for commit.
- `budget_head`: budget/account head to commit against.
- `commit_amount`: normalized ICSS amount from child/parent helper.
- `ref_details`: linked child document if available, otherwise parent ICSS docname.

---

## 4. Step 2: Staff/R&D Stages Commit Data

Frontend calls shared commit staging API:

```text
rndopsapp.rndopsapp.commitPayment.submit_commit_data
```

Recommended payload for normal ICSS commit:

```json
{
  "doctype": "Indent Cum Sanction Sheet",
  "frapAppId": "2026032401MeiTy000667",
  "name": "2026050710000832",
  "project_name": "26RBSBESP0391XXLS0010",
  "commit_amount": 50000,
  "budget_head": "Recurring",
  "refDetails": "AMC-0001",
  "commitParticular": "ICSS commitment"
}
```

Backend behavior in `submit_commit_data`:

1. Validates that `Indent Cum Sanction Sheet / 2026050710000832` exists.
2. Builds `payload`.
3. Checks for existing `Kafka Commit Staging` row with:

```text
reference_doctype = Indent Cum Sanction Sheet
reference_name = 2026050710000832
status = PENDING_APPROVAL
```

4. If found, updates existing staging payload.
5. If not found, inserts a new staging row.
6. Leaves status as:

```text
PENDING_APPROVAL
```

Example staging row:

```json
{
  "reference_doctype": "Indent Cum Sanction Sheet",
  "reference_name": "2026050710000832",
  "status": "PENDING_APPROVAL",
  "payload": {
    "commit_amount": 50000,
    "budget_head": "Recurring",
    "project_name": "26RBSBESP0391XXLS0010",
    "bmr": null,
    "bill_amount": null,
    "frap_app_id": "2026032401MeiTy000667",
    "ref_details": "AMC-0001",
    "commit_particular": "ICSS commitment"
  }
}
```

This step does not publish to Kafka yet.

---

## 5. Step 3: Staff/R&D Forwards Workflow

After staging commit data, frontend moves ICSS forward:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.perform_icss_action
```

Payload:

```json
{
  "docname": "2026050710000832",
  "action": "Forward"
}
```

Expected workflow:

```text
Pending Staff Approval -> Pending HoS Approval
```

No Kafka publish happens at this stage.

---

## 6. Step 4: HoS Routes To Dean Or Associate Dean

HoS performs `Forward`.

Backend helper:

```text
_resolve_hos_next_state(doc, requested_action, workflow, user_roles)
```

Routing:

| Action | Amount | Next State |
|---|---:|---|
| `Forward` | `> 1,00,000` | `Pending Dean Approval` |
| `Forward` | `<= 1,00,000` | `Pending Associate Dean` |

No Kafka publish happens at HoS stage.

---

## 7. Step 5: Dean Or Associate Dean Approves

Dean or Associate Dean performs:

```json
{
  "docname": "2026050710000832",
  "action": "Approve"
}
```

Expected workflow:

```text
Pending Dean Approval -> Pending PO Generation
```

or:

```text
Pending Associate Dean -> Pending PO Generation
```

In `perform_icss_action`, after workflow state becomes `Pending PO Generation`, backend explicitly calls:

```python
check_workflow_and_publish(doc)
```

This is needed because ICSS updates workflow state directly with `frappe.db.set_value(...)`, so normal `on_update` hooks may not automatically publish.

Working local Workflow rows:

```text
Pending Dean Approval  | Approve | Pending PO Generation | Dean, RnD
Pending Associate Dean | Approve | Pending PO Generation | Ado_RnD
```

Therefore the normal ICSS Kafka publish happens on:

```text
Dean/Associate Dean Approve -> Pending PO Generation
```

It does not publish when HoS forwards to Dean/Associate Dean.

---

## 8. Step 6: Publishing Staged Commit To Kafka

Publisher function:

```text
rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish
```

For most modules, publish trigger is:

```text
Approved
```

For ICSS, publish trigger is:

```text
Approved
Pending PO Generation
```

Backend searches `Kafka Commit Staging`:

```text
reference_doctype = Indent Cum Sanction Sheet
reference_name = <icss_docname>
status in (PENDING_APPROVAL, FAILED)
```

For every matching staging row:

1. Parse `payload`.
2. Call Kafka producer:

```text
kafka_publish_commit(...)
```

3. Pass values:

```text
commit_amount
budget_head
project_name
bmr
bill_amount
frap_app_id
ref_details
module_id
```

4. If Kafka publish succeeds:

```text
Kafka Commit Staging.status = PUBLISHED
```

5. If Kafka publish fails:

```text
Kafka Commit Staging.status = FAILED
Kafka Commit Staging.error_message = <reason>
```

---

## 9. Kafka Payload Module ID Resolution

Kafka mapper:

```text
rndopsapp/rndopsapp/kafka/producer/reimbursement/mapper.py
```

Normal ICSS commit:

- No `moduleId` is sent in staging payload.
- Mapper falls back to:

```text
get_module_id(doc.doctype)
```

- Since `doc.doctype = Indent Cum Sanction Sheet`, Kafka receives the ICSS module ID, for example `17`.

PO generation re-commit:

- Frontend sends:

```json
{
  "moduleId": 14
}
```

- `submit_commit_data` stores it inside staging payload.
- `check_workflow_and_publish` passes it to Kafka producer.
- Mapper uses override first:

```python
module_id = payload.get("moduleId") or payload.get("module_id")
```

- Kafka receives:

```text
data.moduleId = 14
```

This is required because the reference document remains `Indent Cum Sanction Sheet`, but the business operation is PO generation.

---

## 10. Step 7: PO Generation Save

When Staff/R&D generates PO, frontend saves PO data through:

```text
rndopsapp.rndopsapp.doctype.icss_po.icss_po.save_icss_po_data
```

Payload:

```json
{
  "project_number": "26RBSBESP0391XXLS0010",
  "icss_number": "2026050710000832",
  "indent_type": "Annual Maintenance Contract",
  "po_number": "PO-001",
  "po_date": "2026-06-05",
  "icss_po_form": "<p>Generated PO HTML</p>",
  "add_of_gst_": "18",
  "gst_amount": "18000",
  "grand_total": "118000",
  "amc_po_table": [
    {
      "sl_no": "1",
      "description_of_items": "AMC service",
      "end_user": "Lab",
      "year": "2026",
      "amc_from": "2026-06-05",
      "amc_to": "2027-06-04",
      "amc_amount": 100000
    }
  ]
}
```

Backend behavior:

- Finds existing `ICSS_PO` by `icss_number`, `po_number`, or `project_number`.
- Creates a new `ICSS_PO` if not found.
- Backfills `project_number` and `indent_type` from ICSS parent if needed.
- Saves PO HTML in `icss_po_form`.
- Saves `amc_po_table` only for `Annual Maintenance Contract`.
- Saves AMC summary fields only for `Annual Maintenance Contract`.
- Commits the `ICSS_PO` document.

This API saves PO data. It does not by itself publish Kafka commit data.

---

## 11. Step 8: PO Generation Re-Commit

When PO is generated, frontend should stage a second commit payload for PO generation.

Use the same API:

```text
rndopsapp.rndopsapp.commitPayment.submit_commit_data
```

Payload must include:

```json
{
  "doctype": "Indent Cum Sanction Sheet",
  "frapAppId": "2026032401MeiTy000667",
  "name": "2026050710000832",
  "project_name": "26RBSBESP0391XXLS0010",
  "commit_amount": 118000,
  "budget_head": "Recurring",
  "refDetails": "PO-001",
  "commitParticular": "ICSS PO generation re-commit",
  "moduleId": 14
}
```

Important:

- `doctype` remains `Indent Cum Sanction Sheet`.
- `name` remains the ICSS docname.
- `moduleId = 14` tells Kafka this is PO generation re-commit.
- Without `moduleId = 14`, Kafka mapper falls back to ICSS module ID, for example `17`.

### Publish Trigger For PO Re-Commit

The backend supports publishing the staged PO re-commit payload through:

```text
check_workflow_and_publish(doc)
```

or manual fallback:

```text
manually_publish_staged_commit(reference_name, reference_doctype)
```

Production must verify which path is used by the PO generation frontend/backend flow.

Expected safe sequence:

1. Save PO data using `save_icss_po_data`.
2. Stage PO re-commit using `submit_commit_data(..., moduleId=14)`.
3. Publish the staged PO re-commit either by:
   - calling `manually_publish_staged_commit("2026050710000832", "Indent Cum Sanction Sheet")`, or
   - having the PO generation workflow/backend action call `check_workflow_and_publish(doc)` after staging.
4. Move ICSS workflow state to:

```text
PO Generated
```

Production warning:

- Current ICSS approval publish is automatic when state enters `Pending PO Generation`.
- If PO re-commit is staged after the ICSS is already in `Pending PO Generation`, it will stay `PENDING_APPROVAL` unless a publish call is triggered.
- If production sees a PO re-commit staging row stuck as `PENDING_APPROVAL`, check whether the PO generation action calls `manually_publish_staged_commit` or `check_workflow_and_publish`.

---

## 12. Step 9: Move Workflow To PO Generated

After PO data is saved and PO re-commit is handled, ICSS should move:

```text
Pending PO Generation -> PO Generated
```

This can be done through:

```text
perform_icss_action(docname, action)
```

where `action` must match the active ICSS Workflow Transition from `Pending PO Generation` to `PO Generated`.

The working local workflow action is:

```text
Generate PO
```

Example:

```json
{
  "docname": "2026050710000832",
  "action": "Generate PO"
}
```

Production note:

- Production should use `Generate PO` to match local.
- Check production workflow transition table to confirm the actual action.

SQL check:

```sql
select wt.state, wt.action, wt.next_state, wt.allowed
from `tabWorkflow Transition` wt
join `tabWorkflow` w on wt.parent = w.name
where w.document_type = 'Indent Cum Sanction Sheet'
  and w.is_active = 1
  and wt.state = 'Pending PO Generation';
```

---

## 13. Step 10: Final Signed PO Delivery

After PO is generated, Staff/R&D uploads the signed/generated PO.

API:

```text
rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.upload_icss_signed_po
```

Allowed current states:

```text
PO Generated
PO Delivered
```

Payload if file is already in MinIO:

```json
{
  "docname": "2026050710000832",
  "file_url": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf"
}
```

Backend behavior:

1. Loads ICSS parent.
2. Confirms state is `PO Generated` or `PO Delivered`.
3. Validates signed PO file path is under:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/signed_po/
```

4. Creates/links a `File` row to ICSS.
5. Stores URL in:

```text
icss_signed_po_file
```

6. Sets:

```text
workflow_state = PO Delivered
```

7. Syncs child doctype workflow state.
8. Commits the update.

Successful response:

```json
{
  "status": "success",
  "message": "Signed PO uploaded and ICSS marked as PO Delivered.",
  "docname": "2026050710000832",
  "workflow_state": "PO Delivered",
  "signed_po_attachment": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf",
  "icss_signed_po_file": "/Project_Registration/26RBSBESP0391XXLS0010/indent_cum_sanction_sheet/2026050710000832/signed_po/signed-po.pdf"
}
```

No Kafka commit is published at this final delivery step.

---

## 14. Full End-To-End Sequence

```text
1. Applicant submits ICSS
2. ICSS reaches Pending Staff Approval
3. Frontend calls get_icss_commit_details
4. Frontend calls submit_commit_data without moduleId
5. Kafka Commit Staging row is created as PENDING_APPROVAL
6. Staff forwards ICSS to Pending HoS Approval
7. HoS clicks Forward and routes ICSS to Dean or Associate Dean
8. Dean/Associate Dean clicks Approve
9. ICSS moves to Pending PO Generation
10. Backend calls check_workflow_and_publish
11. Staged commit is published to Kafka
12. Kafka Commit Staging row becomes PUBLISHED
13. Staff/R&D saves generated PO using save_icss_po_data
14. Frontend stages PO re-commit using submit_commit_data with moduleId = 14
15. PO re-commit is published through manual publish or PO generation backend publish hook
16. Staff/R&D clicks Generate PO and ICSS moves to PO Generated
17. Staff/R&D uploads signed PO using upload_icss_signed_po
18. Backend stores icss_signed_po_file
19. ICSS moves to PO Delivered
20. ICSS leaves Staff/R&D pending task list
```

---

## 15. Verification Queries

### 15.1 Check ICSS Staging Rows

```sql
select name, reference_doctype, reference_name, status, payload, error_message, modified
from `tabKafka Commit Staging`
where reference_doctype = 'Indent Cum Sanction Sheet'
  and reference_name = '<ICSS_DOCNAME>'
order by modified desc;
```

Expected:

- First ICSS commit row should become `PUBLISHED` after Dean/Associate Dean approval.
- PO re-commit row should contain `"moduleId": 14`.
- PO re-commit row should become `PUBLISHED` after PO generation publish path runs.

### 15.2 Find Stuck PO Re-Commit Rows

```sql
select name, reference_name, status, payload, error_message, modified
from `tabKafka Commit Staging`
where reference_doctype = 'Indent Cum Sanction Sheet'
  and status = 'PENDING_APPROVAL'
  and payload like '%"moduleId": 14%'
order by modified desc;
```

If rows appear here after PO generation, publish trigger is missing.

### 15.3 Check Failed Commit Rows

```sql
select name, reference_name, status, error_message, payload, modified
from `tabKafka Commit Staging`
where reference_doctype = 'Indent Cum Sanction Sheet'
  and status = 'FAILED'
order by modified desc;
```

### 15.4 Check ICSS Workflow And Signed PO

```sql
select name, workflow_state, project_no, icss_signed_po_file, modified
from `tabIndent Cum Sanction Sheet`
where name = '<ICSS_DOCNAME>';
```

Expected final state:

```text
workflow_state = PO Delivered
icss_signed_po_file is not empty
```

### 15.5 Check ICSS PO Record

```sql
select name, project_number, icss_number, indent_type, po_number, po_date, modified
from `tabICSS_PO`
where icss_number = '<ICSS_DOCNAME>';
```

---

## 16. Common Production Issues

### Issue: Commit staged but not published after approval

Check:

- ICSS reached `Pending PO Generation`.
- `perform_icss_action` includes the explicit `check_workflow_and_publish(doc)` call.
- `Kafka Commit Staging.status` is `PENDING_APPROVAL` or `FAILED`.
- Kafka service is available.
- `error_message` in staging row.

### Issue: Kafka receives module ID `17` instead of `14` for PO generation

Cause:

- PO re-commit staging payload did not include `moduleId = 14`, or production backend does not pass module override through mapper.

Check staging payload:

```sql
select payload
from `tabKafka Commit Staging`
where reference_doctype = 'Indent Cum Sanction Sheet'
  and reference_name = '<ICSS_DOCNAME>'
order by modified desc
limit 5;
```

Expected PO re-commit payload:

```json
{
  "moduleId": 14
}
```

### Issue: PO re-commit remains `PENDING_APPROVAL`

Cause:

- Re-commit was staged after ICSS had already reached `Pending PO Generation`, but no publish trigger ran afterward.

Fix options:

- Call:

```text
manually_publish_staged_commit("<ICSS_DOCNAME>", "Indent Cum Sanction Sheet")
```

- Or update the PO generation backend path to call:

```text
check_workflow_and_publish(doc)
```

after staging PO re-commit.

### Issue: Signed PO upload fails

Check:

- ICSS is in `PO Generated` or already `PO Delivered`.
- File URL points to a file, not only a folder.
- File URL is under:

```text
/Project_Registration/<project_no>/indent_cum_sanction_sheet/<icss_docname>/signed_po/
```

### Issue: Signed PO uploaded but pending task still shows ICSS

Check:

- `workflow_state` is actually `PO Delivered`.
- Module Registry pending task filters exclude `PO Delivered`.
- Frontend refreshed pending task list after upload.

---

## 17. Frontend API Summary

Normal commit at Staff/R&D:

```text
get_icss_commit_details(docname)
submit_commit_data(... without moduleId)
perform_icss_action(docname, "Forward")
```

Approval publish:

```text
perform_icss_action(docname, "Approve")
```

PO generation:

```text
save_icss_po_data(...)
submit_commit_data(..., moduleId=14)
manually_publish_staged_commit(docname, "Indent Cum Sanction Sheet")
perform_icss_action(docname, "Generate PO")
```

Final signed PO delivery:

```text
upload_icss_signed_po(docname, file_url)
```

---

## 18. Production Deployment Notes

Required after code deployment:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
bench restart
```

No manual SQL is required for the Kafka `moduleId` override because it is stored in the existing JSON `payload` field of `Kafka Commit Staging`.

Manual SQL may only be needed to inspect or repair existing stuck staging rows.
