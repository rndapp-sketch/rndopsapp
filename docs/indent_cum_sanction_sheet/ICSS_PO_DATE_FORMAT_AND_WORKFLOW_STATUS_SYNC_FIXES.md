# Bug Fixes — 2026-06-18

---

## Fix 1 — ICSS_PO: Incorrect date format on insert

**File:** `rndopsapp/rndopsapp/doctype/icss_po/icss_po.py`

### Problem

Inserting an ICSS_PO document via the REST API (`POST /api/resource/ICSS_PO`) failed with:

```
pymysql.err.OperationalError: (1292, "Incorrect date value: '18/06/2026'
for column `tabICSS_PO`.`po_date` at row 1")
```

The frontend was sending `po_date` in `DD/MM/YYYY` format, but MySQL requires `YYYY-MM-DD`.

### Fix

Added a `_normalize_date` helper that converts `DD/MM/YYYY` → `YYYY-MM-DD` using `datetime.strptime`. Any other format (already correct, `None`, non-string) passes through unchanged.

Applied the normalization in two places:

1. **`ICSS_PO.before_save`** — covers the standard REST API path (`/api/resource/ICSS_PO`) and any direct Frappe UI save.
2. **`save_icss_po_data`** — covers the custom whitelisted save endpoint.

```python
def _normalize_date(value):
    if isinstance(value, str) and len(value) == 10 and value[2] == "/" and value[5] == "/":
        try:
            return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return value


class ICSS_PO(Document):
    def before_save(self):
        if self.po_date:
            self.po_date = _normalize_date(self.po_date)
```

---

## Fix 2 — Fund Sanction: Two workflow statuses showing out of sync

**File:** `rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py`

### Problem

The Fund Sanction form showed two workflow indicators with different values:

| Location | Field | Value shown |
|---|---|---|
| Form header badge | `workflow_state` (Frappe native) | Sanction Approved |
| Form body field | `sanction_workflow_status` (custom Data field) | Pending Staff Approval |

### Root Cause

`sanction_workflow_status` is a custom Data field intended to mirror `workflow_state`. It was only updated inside `perform_fund_sanction_action`. Frappe's native workflow UI can advance `workflow_state` directly (through the badge/button at the top of the form) without calling that function, causing the two fields to drift apart.

### Fix

1. **Added `before_save` to `FundSanction`** — `sanction_workflow_status` is now always copied from `workflow_state` on every save, regardless of how the transition was triggered.

```python
class FundSanction(Document):
    def before_save(self):
        if self.workflow_state:
            self.sanction_workflow_status = self.workflow_state
```

2. **Fixed the existing out-of-sync record** (`SAN_010626-878-2026052501000781`) via a direct DB update:

```sql
UPDATE `tabFund Sanction`
SET sanction_workflow_status = workflow_state
WHERE name = 'SAN_010626-878-2026052501000781';
```

After the fix, both fields on that record read `Sanction Approved`.

---

## Fix 3 — Fund Received: Reverts to "Pending Misc. Staff Approval(Deposit Slip Pending)" after HoS Approves

**Document affected:** `REC_240426413-prjreg_refnum`  
**Linked Deposit Slip:** `RES-DS-2026-00019`  
**Symptom:** After the HoS approves a Fund Received from state `"Pending HoS Approval"`, the document silently reverts to `"Pending Misc. Staff Approval(Deposit Slip Pending)"`.

---

### Fund Received DocType — Overview

| Property | Value |
|---|---|
| DocType | `Fund Received` |
| Autoname | `REC_{DD}{MM}{YY}{###}-{prjreg_refnum}` |
| Is Submittable | Yes (docstatus 0=Draft, 1=Submitted, 2=Cancelled) |
| Workflow | `fund_received_with_kafka` |
| Python Controller | `rndopsapp/doctype/fund_received/fund_received.py` |

### Fund Received — Fields

| Fieldname | Fieldtype | Required | Notes |
|---|---|---|---|
| `prjreg_title` | Link → Project Registration | ✅ | Links FR to its project |
| `fund_received_ref_number` | Data | — | Read-only, filled by Accounts Portal |
| `sanction_ref_no` | Data | — | Filled from Fund Sanction on validate |
| `fund_received_amt` | Currency | ✅ | Total amount received |
| `bank_account` | Data | ✅ | Bank account / scheme where money arrived |
| `gst_invoice_issued` | Select (Yes/No) | — | Shown only when project type is Consultancy |
| `invoice_no` | Data | — | Shown only when GST invoice = Yes |
| `document_upload` | Attach | — | Supporting file (MinIO) |
| `fund_transactions` | Table → Project Fund Transaction | — | UTR / date / amount rows |
| `received_amt_breakup` | Table → Project Received Budget | — | Account head / amount rows |
| `workflow_state` | Data | — | Read-only; managed by workflow engine |
| `amended_from` | Link → Fund Received | — | Hidden; set on amendment |

---

### Workflow: `fund_received_with_kafka`

```
[PE / IR / Project Staff]
      │  Submit
      ▼
  Pending Misc. Staff Approval          (docstatus=0)
      │  Forward [RnD Misc]      │  Put Back [RnD Misc]
      ▼                          ▼
  PENDING_APPROVAL               Draft
  (published to Kafka)
      │  Approve [System Mgr]    │  Put Back [RnD Admin]
      ▼                          ▼
  Pending Misc. Staff Approval(Deposit Slip Pending)   (docstatus=0)
      │  Generate Deposit Slip   │  Put Back [RnD Misc]
      │  [RnD Misc]              ▼
      ▼                       PENDING_APPROVAL
  Pending HoS Approval          (docstatus=0)
      │  Approve [HoS RnD]       │  Put Back [HoS RnD]
      ▼                          ▼
  Approved                Pending Misc. Staff Approval(Deposit Slip Pending)
  (docstatus=1, DS auto-approved, Kafka published)
      │  Verify [RnD Accounts]
      ▼
  Fund Received             (docstatus=1)
```

**All transitions are handled by `perform_fund_received_action`** — NOT by Frappe's built-in workflow buttons.

---

### How `perform_fund_received_action` Works

**Endpoint:** `POST /api/method/rndopsapp.rndopsapp.doctype.fund_received.fund_received.perform_fund_received_action`

| Step | What Happens |
|---|---|
| 1 | Load doc, read current `workflow_state` |
| 2 | Find matching transition `(current_state + action) → next_state` |
| 3 | Parse and validate `deposit_slip_data` from request |
| 4 | **If next_state = "Pending HoS Approval":** call `create_deposit_slip_from_data()` → inserts new Deposit Slip linked to this FR |
| 5 | Set `doc.workflow_state = next_state` in memory |
| 6 | Resolve legacy Budget Head IDs |
| 7 | Try `doc.submit()` (if new docstatus=1) or `doc.save()` |
| 8 | Force-write: `doc.db_set("workflow_state", next_state)` + `frappe.db.commit()` |
| 9 | **If next_state = "PENDING_APPROVAL":** publish to Kafka topic `fund-received-events` + Mattermost notification |
| 10 | **If next_state = "Approved":** find linked Deposit Slip → auto-approve + submit → publish to Kafka + Mattermost |
| 11 | Return `{ status, message, docname, workflow_state, next_actions }` |

**Deposit Slip auto-approval logic (step 10) after Bug 2 fix:**

```python
# Pass 1 — find the active DS waiting for HoS (newest first)
ds = frappe.db.get_value(
    doctype,
    {"fund_received_ref": doc.name, "workflow_state": "Pending HoS Approval"},
    "name", order_by="creation desc"
)
# Pass 2 — fallback: most recently created DS for this FR
if not ds:
    ds = frappe.db.get_value(
        doctype,
        {"fund_received_ref": doc.name},
        "name", order_by="creation desc"
    )
```

---

### Kafka Integration

#### Outbound — Frappe → External Accounts Portal

- **Trigger:** FR transitions to `PENDING_APPROVAL`
- **Topic:** `fund-received-events`
- **Function:** `publish_fund_received(doc)`

#### Inbound — External Accounts Portal → Frappe

- **Topic:** `accounts-fundreceived-update`
- **Consumer:** `FundReceivedConsumerHandler` → `FundReceivedConsumerMapper.apply_updates()`

**Status mapping:**

| Kafka `fundReceivedStatus` | Frappe `workflow_state` |
|---|---|
| `APPROVED` | `Pending Misc. Staff Approval(Deposit Slip Pending)` |
| `PENDING_APPROVAL` | `PENDING_APPROVAL` |
| anything else | `.title()` of value |

**State priority guard (prevents backward movement):**

| State | Priority |
|---|---|
| Draft | 0 |
| Pending Misc. Staff Approval | 1 |
| PENDING_APPROVAL | 2 |
| Pending Misc. Staff Approval(Deposit Slip Pending) | 3 |
| Pending HoS Approval | 4 |
| Approved | 5 |
| Fund Received | 6 |

---

### Root Cause 1 — TOCTOU Race in Kafka Consumer

**File:** `rndopsapp/kafka/consumer/fund_received/mapper.py`

The external accounts portal sent back an `APPROVED` Kafka event **~11 days** after `REC_240426413-prjreg_refnum` was published at `PENDING_APPROVAL`. By that time the FR had advanced to `"Approved"` (priority 5).

The old priority check was a **read-then-update** pattern:

```python
# ❌ OLD CODE — UNSAFE under MariaDB MVCC
current_status = frappe.db.get_value(...)       # SELECT reads MVCC snapshot (stale)
if new_priority >= current_priority:            # Python-level check
    frappe.db.set_value(..., 'workflow_state')  # UPDATE writes to LATEST row
```

Under MariaDB's `REPEATABLE READ` isolation, `SELECT` reads from a frozen transaction snapshot. If that snapshot was taken when the FR was at `PENDING_APPROVAL` (priority 2), the Python check sees priority 2 and allows the write — even though the actual row has already advanced to `"Approved"` (priority 5). The `UPDATE` then silently overwrites `"Approved"` with `"Pending Misc. Staff Approval(Deposit Slip Pending)"`.

**Evidence:** Two Fund Received documents were both modified at exactly `2026-05-25 14:41:46` — the Kafka consumer's batch confirmed the race.

#### Fix

Replaced with a single **atomic conditional SQL UPDATE**:

```python
# ✅ NEW CODE — atomic: check and write happen in one MariaDB statement
allowed_from_states = [
    state for state, pri in cls._STATE_PRIORITY.items()
    if pri <= new_priority
]
placeholders = ', '.join(['%s'] * len(allowed_from_states))
rows_affected = frappe.db.sql(
    f"""
    UPDATE `tabFund Received`
    SET workflow_state = %s, modified = NOW()
    WHERE name = %s
      AND workflow_state IN ({placeholders})
    """,
    [new_status, doc_name] + allowed_from_states,
)
if not rows_affected:
    current_status = frappe.db.get_value('Fund Received', doc_name, 'workflow_state') or ''
    frappe.logger().warning(
        f"[FundReceivedConsumerMapper] Skipped backward state change for "
        f"{doc_name}: current='{current_status}' → '{new_status}' (priority {new_priority}) ignored."
    )
```

The `WHERE workflow_state IN (...)` guard executes atomically with the write inside MariaDB. `"Approved"` is not in `allowed_from_states` for an `APPROVED` update (priority 3 ≤ 3), so zero rows are updated and the state is preserved.

---

### Root Cause 2 — Wrong Deposit Slip Selected During HoS Approval

**File:** `rndopsapp/doctype/fund_received/fund_received.py`

For `REC_240426413-prjreg_refnum`, the HoS had put back the FR **twice**, so three deposit slips existed linked to the same FR:

| Deposit Slip | workflow_state | docstatus |
|---|---|---|
| `RES-DS-2026-00007` | Pending HoS Approval | 0 |
| `RES-DS-2026-00009` | Pending HoS Approval | 0 |
| `RES-DS-2026-00019` | Approved | 1 |

The old auto-approve code:

```python
# ❌ OLD CODE — arbitrary row returned (no ordering)
ds_name = frappe.db.get_value(dt, {"fund_received_ref": doc.name}, "name")
```

`frappe.db.get_value` with no `order_by` returns an arbitrary row — effectively the oldest (`RES-DS-2026-00007`). The wrong deposit slip was submitted.

#### Fix

```python
# ✅ NEW CODE — Pass 1: find the active DS in "Pending HoS Approval" (newest first)
name = frappe.db.get_value(
    dt,
    {"fund_received_ref": doc.name, "workflow_state": "Pending HoS Approval"},
    "name",
    order_by="creation desc",
)
# Pass 2 — fallback: most recently created DS of any state
if not name:
    name = frappe.db.get_value(
        dt,
        {"fund_received_ref": doc.name},
        "name",
        order_by="creation desc",
    )
```

---

### Data Fix Applied to `REC_240426413-prjreg_refnum`

```sql
-- Move FR from the stuck state back to "Pending HoS Approval"
-- so the HoS can approve cleanly
UPDATE `tabFund Received`
SET workflow_state = 'Pending HoS Approval', modified = NOW()
WHERE name = 'REC_240426413-prjreg_refnum'
  AND workflow_state = 'Pending Misc. Staff Approval(Deposit Slip Pending)';
```

**State before:** `Pending Misc. Staff Approval(Deposit Slip Pending)`  
**State after:** `Pending HoS Approval` ✅  
**Next step:** HoS clicks **Approve** from the UI. With Bug 2 fixed, the system finds `RES-DS-2026-00019` (already Approved/submitted) and skips re-approving it, then moves FR to `Approved` (docstatus=1) and publishes to Kafka.

---

### Files Changed — Fix 3

| File | Change |
|---|---|
| `rndopsapp/kafka/consumer/fund_received/mapper.py` | `apply_updates()` — replaced read-then-update with atomic conditional SQL UPDATE |
| `rndopsapp/doctype/fund_received/fund_received.py` | `perform_fund_received_action()` — fixed deposit slip selection: filter by `"Pending HoS Approval"` + `order_by="creation desc"` fallback |
