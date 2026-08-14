# Salary Module — Complete Frontend + Backend Reference

> The full picture of one salary payment, merging `SalaryModule.tsx` (frontend,
> Payroll Workspace UI — not in this repo) with [`commitPayment.py`](commitPayment.py)
> (backend, `rndopsapp`). Nothing here is a summary pointing elsewhere — every
> formula, payload shape, locking mechanism, Kafka detail, and error path from both
> sides is written out in full, organized around the single walkthrough a payment
> actually takes.

---

## 1. Overview

The Salary Module is a **Payroll Workspace** used by a Principal Investigator (PI) at
IIT Guwahati's R&D Operations to pay monthly salary to their approved Project Staff
(Recruitment Adhoc Contractual employees). A salary payment is not a standalone
document — it rides on top of domains that already exist in the app:

| Domain | Doctype | Role |
|---|---|---|
| Recruitment | `Recruitment Adhoc Contractual` | The employment record. Its `workflow_state` reaching `Approved` is what **commits** budget for the employee — the prerequisite for any payment. |
| Staffing | `Project Staff Details` → `table_ymed` (tenure child table) | Joining date, term completion date, basic salary per tenure. Decides "is this employee currently eligible to be paid." |
| Finance | `AccountHeadPayment` | The actual payment ledger row created for every payout, salary or otherwise. |
| Staging | `Salary Staging` (single JSON field `salary_record`, autonamed `{YYYY}_{MMMM}`, e.g. `2026_july`) | Durable audit trail of every salary payload received for a given month, independent of whether the Kafka publish succeeded. |

The frontend (PI's browser) owns staff rendering, pro-rata salary math, deduction
overrides, and a client-side "is this month prepared" lock. The backend
(`commitPayment.py`) owns eligibility rules, the staging audit trail,
`AccountHeadPayment` creation, and Kafka publishing. Every payment ends as one Kafka
event on topic **`account-head-payment-events`**, consumed by an external ledger
microservice (Java, `172.16.134.81:18080`) that is **outside this repo** — this app
never consumes that topic back.

---

## 2. System Architecture

```
  Recruitment Adhoc Contractual → Approved
                 │
                 │ commit event (earlier, on approval)
                 ▼
  ┌──────────────────────────────┐
  │      External Ledger         │
  │        + Kafka                │
  └───────────────▲──────────────┘
                  │ ② checks committed budget
                  │      publishes payment event
                  │
  ┌───────────────┴──────────────┐
  │   Backend — commitPayment.py  │
  └───────────────▲──────────────┘
                  │ ① "Who can be paid?"
                  │ ② "Pay them"
                  │
  ┌───────────────┴──────────────┐
  │       Salary Module UI        │
  └───────────────▲──────────────┘
                  │
             PI (Browser)
```

- **Prerequisite (top of diagram):** happens earlier, independent of the PI's session —
  when the employee's Recruitment record reaches workflow state `Approved`, the
  backend publishes a **commit** event that earmarks budget on the ledger.
- **Trip ①:** once per employee, read-only — "is budget committed for this person?"
- **Trip ②:** once per employee, after PI confirms — the only step that writes
  anything: an audit record, a payment document, and a Kafka event.

---

## 3. Data Types & Payload Shapes

### 3.1 `StaffRecord` (frontend, mapped from `Project Staff Details`)

```
docName               — Frappe document name
employee_id           — ps_emp_id
first_name            — full name (first + middle + last)
email_id              — erp_mail or ps_email_id
department            — ps_department
designation           — ps_designation
joining_date          — ps_joining_date
term_completion_date  — ps_term_completion_date
basic_salary          — ps_basic_salary (rounded integer)
hra                   — calculated from ps_hra % of basic
hra_percent           — raw % value
medical_allowance     — ps_ma ("yes" = ₹1250, else numeric)
hostel                — ps_hostel amount
workflow_state        — must be "Approved"
project_no            — project_no
bank_account_number   — bank_account_number
ps_hostel             — raw hostel field (used for HRA deduction logic)
```

### 3.2 `EditableInputs` (per-employee overrides, frontend `overrides` state)

```
ta                — Transport Allowance deduction
otherDeduction    — Other deductions
arrear            — Arrear addition to earnings
medicalDeduction  — Medical deduction (default = pro-rated medical_allowance)
idCardCharge      — ID card charge deduction
electricityBill   — Electricity bill deduction
comment           — Free-text comment
remarks           — Free-text remarks
```

### 3.3 Commit payload (built by frontend after Step 4/4b succeeds)

```json
{
  "projectNumber": "26RCLSTSP0742SAMI0001",
  "accountHeadId": "2",
  "moduleId": "11",
  "frapAppId": "202604150A00290",
  "commitDate": "2026-04-23",
  "commitParticular": "Salary payment for Victoria Thangjam (2026TS0009) - July 2026",
  "refDetails": "4",
  "commitAmount": 45000,
  "transactionCommitNumber": "4",
  "salary_year_month": "2026_july",
  "salary_user_details": { "...all calculated salary fields..." },
  "salary_backend_details": { "ps_emp_id": "2026TS0009", "scr_id": "S2605061900544", "project_no": "26RCLSTSP0742SAMI0001" }
}
```

### 3.4 `submit_payment_data` POST body (Step 6b, sent per employee)

```json
{
  "doctype": "Recruitment Adhoc Contractual",
  "moduleName": "Recruitment Adhoc Contractual",
  "moduleId": "11",
  "project_ref_number": "<Frappe Project Registration doc name>",
  "project_name": "<same as project_ref_number>",
  "project_no": "26RCLSTSP0742SAMI0001",
  "payment_amount": 45000,
  "budget_head": "2",
  "payment_particular": "Salary payment for Victoria Thangjam - July 2026",
  "payment_date": "2026-07-20",
  "payment_status": "PENDING",
  "bmr": "BMR-2026-001",
  "frapAppId": "202604150A00290",
  "commit_id": "4",
  "refDetails": "4",
  "salary_year_month": "2026_july",
  "salary_user_details": { "...full payslip breakdown..." },
  "salary_backend_details": { "ps_emp_id": "2026TS0009", "scr_id": "S2605061900544", "project_no": "26RCLSTSP0742SAMI0001" }
}
```

### 3.5 Kafka payment event envelope (what the backend actually publishes)

Every payment event is wrapped in a schema envelope
(`AccountHeadPaymentEvent.to_kafka_payload`,
[`kafka/producer/reimbursement/mapper.py:44-69`](kafka/producer/reimbursement/mapper.py#L44)):

```json
{
  "schemaVersion": "1.0",
  "eventType": "ACCOUNT_HEAD_PAYMENT",
  "timestamp": "2026-07-20T05:26:32.873849",
  "data": {
    "transactionPaymentNumber": null,
    "transactionCommitNumber": null,
    "projectNumber": "26RCLSTSP0742SAMI0001",
    "accountHeadId": 2,
    "paymentDate": "2026-07-20",
    "paymentParticular": "Salary payment for Victoria Thangjam - July 2026",
    "paymentRefDetails": "4",
    "paymentAmount": 45000.0,
    "bmr": "BMR-2026-001",
    "paymentStatus": "PENDING",
    "bankTransactionNumber": null,
    "bankTransactionDate": "2026-07-20",
    "frapAppId": "202604150A00290",
    "moduleId": 11
  }
}
```

Field derivation (`AccountHeadPaymentMapper.map_to_dto`,
[`mapper.py:328-410`](kafka/producer/reimbursement/mapper.py#L328)):

| DTO field | Source |
|---|---|
| `projectNumber` | `get_project_number(project_ref_number)` — resolves `Project Registration.project_no`, falling back to the doc name, then the raw string |
| `accountHeadId` | `resolve_budget_head_id(budget_head)` — tries `Budget Head.id`, falls back to `Budget Head.idx` (row position) if `id` is null |
| `moduleId` | `int(module_name)` if numeric (salary always sends `"11"`), else looked up from `Module Registry Item`, else `7` |
| `frapAppId` | explicit override if given, else falls back to `projectNumber` |

---

## 4. All API Endpoints

### GET (read-only)

| # | When called | Endpoint | Backend function | What runs |
|---|---|---|---|---|
| 1 | Mount / Refresh | `frappe.client.get_list` → `Project Staff Details` | *(generic Frappe list API)* | Filters `owner=PI, workflow_state=Approved`, 3-tier fallback |
| 2 | After staff loaded | `frappe.client.get_list` → `Project Registration` | *(generic)* | Reads `funding_agency_schemes`, `enter_scheme_number` per project |
| 3 | After staff loaded | `frappe.client.get_list` → `Department_prornd` | *(generic)* | Resolves department id → name |
| 4 | Period change / after staff load | `GET /api/resource/Salary Staging/{yyyy_month}` | *(generic REST — reads what `_append_salary_staging_record` writes)* | Returns `salary_record` JSON string; 404 if month never staged |
| 5 | Per employee, `handlePaySelected` | `GET .../commitPayment.salary_payment_data?ps_emp_id=...&yyyy_month=...` | `salary_payment_data` ([`commitPayment.py:219`](commitPayment.py#L219)) | Full eligibility chain — see §5 Step 4 |
| 6 | Only if #5 returns `[]` | `GET /ledger-api/account-head-commit/by-status/COMMITTED` | *(direct passthrough to `ACCOUNT_HEAD_COMMIT_API_URL`, bypasses `commitPayment.py`)* | External ledger returns every `COMMITTED` row; frontend filters client-side |
| 7 | Per employee, `handleBmrSubmit` Step A | `GET /api/resource/Project Registration?filters=[["project_no","=","..."]]&fields=["name"]` | *(generic)* | Resolves `project_no` → Frappe doc name, cached client-side |

### POST (write)

| # | When called | Endpoint | Backend function | What runs |
|---|---|---|---|---|
| 8 | Per employee, `handleBmrSubmit` Step B | `POST .../commitPayment.submit_payment_data` | `submit_payment_data` ([`commitPayment.py:1224`](commitPayment.py#L1224)) | Stage → resolve refs → create `AccountHeadPayment` → publish to Kafka — see §5 Step 6 |

Calls **#5 and #6 read the same ledger table** through two different code paths — one
filtered server-side by `commitPayment.py`, one filtered client-side by the frontend.
Call **#8 is the only write** that produces a Kafka event in this whole flow;
everything before it is read-only.

---

## 5. Step-by-Step Walkthrough

### Step 0 — Prerequisite: budget commit on Recruitment approval (before the PI ever opens the module)

This happens independently, whenever an admin approves a `Recruitment Adhoc
Contractual` record — not during the PI's payment session, but it's what makes
Trip ① (Step 4) return anything at all.

1. `submit_commit_data(doctype, frapAppId, name, ..., trigger_state=None)`
   ([`commitPayment.py:751-828`](commitPayment.py#L751)) is called when the
   Recruitment record is created/edited. It does **not** publish anything yet — it
   just upserts a `Kafka Commit Staging` row keyed by
   `(reference_doctype, reference_name, trigger_state)`, with `trigger_state`
   defaulting to `"Approved"`.
2. `check_workflow_and_publish(doc, method)`
   ([`commitPayment.py:831-937`](commitPayment.py#L831)) is registered against
   **every doctype's** `on_update` hook in [`hooks.py:154-161`](../hooks.py#L154).
   Whenever any document saves, it:
   - Finds `Kafka Commit Staging` rows for `(doc.doctype, doc.name)` still
     `PENDING_APPROVAL` or `FAILED`.
   - Checks whether `doc.workflow_state` now equals that row's stored
     `trigger_state` (for Recruitment Adhoc Contractual: **`Approved`**).
   - Guards against re-firing if the document was already in that state before this
     save (idempotency via `doc.get_doc_before_save()`).
   - Calls `kafka_publish_commit(...)` → topic **`account-head-commit-events`**.
   - Marks the staging row `PUBLISHED` or `FAILED`, fires a Mattermost notification.
3. **The status sent is always `"COMMITTED"`**, hardcoded in
   `AccountHeadCommitMapper.map_to_dto`
   ([`kafka/producer/reimbursement/mapper.py:273`](kafka/producer/reimbursement/mapper.py#L273))
   — there is no code path in this app that sends `"PENDING"` for a commit. Despite
   that, the external ledger has been observed storing the row as `status: "PENDING"`
   anyway (see §11.1) — the ledger applies its own state on ingestion rather than
   trusting what's sent. The **only** other status this app ever pushes for an
   existing commit is `"CANCELLED"`, via a separate endpoint
   (`cancellation_request.py:166` → `POST .../account-head-commit/status/by-project-frap`).
   Nothing calls that endpoint (or an equivalent) to move a row from `PENDING` to
   `COMMITTED`.

So the full lifecycle really involves **two independent Kafka events**, tied together
only by `frapAppId` / `projectNumber` / `moduleId=11`:

```
Recruitment Adhoc Contractual → Approved  ──▶  account-head-commit-events   (budget earmarked)
submit_payment_data (salary branch)       ──▶  account-head-payment-events (money paid out)
```

---

### Step 1 — Page loads: fetch the staff list

The PI opens the Salary Module. Month/Year default to the current cycle.

- **Frontend calls:** `frappe.client.get_list` on `Project Staff Details`, filtered to
  `owner = current PI` and `workflow_state = Approved`. If empty, retries against
  `pi_webmail` / `pi_email` / `principal_investigator` fields; as a last resort
  fetches every `Approved` row and filters client-side by owner/email, then finally
  falls back to "use all Approved rows" as a safety net, with one last client-side
  `workflow_state === "approved"` filter.
- **Backend returns:** raw document fields (see `StaffRecord`, §3.1) — no custom
  endpoint touched, this is Frappe's generic list API.
- **Frontend does with it:** maps each row via `mapRow()` into a `StaffRecord`
  (normalizing field names, computing HRA amount from %, medical from "yes"/"no",
  full name from parts), then — entirely client-side, no further API call — runs the
  pro-rata salary formula (§6) for the selected month to get gross/net pay per
  employee.

**→ Screen shows:** the salary table, one row per approved staff member, with
calculated pay for the month.

---

### Step 2 — Is this month "prepared"?

```
localStorage key: "rnd_prepared_salary_cycles"
Value:            { "2026-7": true, "2026-6": true, ... }
cycleKey          = `${selectedYear}-${selectedMonth}`
isPrepared        = !!preparedCycles[cycleKey]
```

- **Frontend calls:** nothing — pure `localStorage` read in the PI's own browser.
- **Backend involvement:** none. The backend has no doctype, field, or endpoint
  representing "this month is prepared" — it's a UX gate only.
- The "Unlock" button removes the key from `localStorage` and resets
  `processedEmployees`.

**→ Screen shows:** either a "Not Prepared" banner (table, export, and payment
buttons hidden), or the full table unlocked — purely based on what's stored in *this
browser*.

---

### Step 3 — Who's already been paid this month?

- **Frontend calls:** `GET /api/resource/Salary Staging/2026_july` (a plain Frappe
  document read). Called automatically once staff records are loaded and the cycle
  is prepared, and re-triggered on every period change.
- **Backend returns:** the `salary_record` field — a JSON array string built by every
  earlier call to `submit_payment_data` (Step 6) for that month. If nobody has been
  paid yet this month, the document doesn't exist and the request 404s (frontend
  treats this as "nobody processed yet" — not an error).
- **Frontend does with it:** parses the array, pulls out each entry's employee id
  (`ps_emp_id` / `employee_id`), builds a `processedEmployees` Set. A stale-guard
  discards the result if the PI changed the month while the request was in flight.

**→ Screen shows:** staff split into two tabs — **Pending** (not in the set) and
**Processed** (in the set).

---

### Step 4 — PI selects employees, clicks "Pay Selected" → eligibility check

Runs **once per selected employee**, one at a time.

- **Frontend calls:**
  `GET .../commitPayment.salary_payment_data?ps_emp_id=2026TS0009&yyyy_month=2026_july`
- **Backend (`salary_payment_data`, [`commitPayment.py:219-456`](commitPayment.py#L219)) does, in order:**
  1. **Duplicate-submission guard** — if this employee is already inside this
     month's `Salary Staging` (checked via `_salary_staging_has_ps_emp_id`,
     [`commitPayment.py:185-215`](commitPayment.py#L185), which recursively searches
     every staged payload for a matching `ps_emp_id` via `_json_contains_ps_emp_id`,
     [`commitPayment.py:173-182`](commitPayment.py#L173)) — stops immediately.
  2. **Tenure resolution** — queries `Project Staff Details` for this `ps_emp_id`,
     walks each record's `table_ymed` child table (joining date, term completion
     date, basic salary), keeps only tenures whose `pstd_term_completion_date` is
     still in the future, and among valid tenures picks the one with the latest
     `(joining_date, term_completion_date)`. A fallback treats the parent doc's
     `ps_joining_date`/`ps_term_completion_date`/`ps_basic_salary` as a tenure when
     `table_ymed` is empty.
  3. **Recruitment linkage** — from the winning tenure's `scr_id`, looks up
     `Selection Committee Report.interview_id`. That `interview_id` **is** the
     `Recruitment Adhoc Contractual` document name (`frapAppId`). If it doesn't
     resolve to an existing document — the case for every employee migrated from
     the legacy system, who never had a Recruitment/SCR record created in this
     app — falls into the **migrated-employee fallback**, Step 4a below, instead
     of returning `[]` immediately.
  4. **External commit lookup (parallelized)** — calls the ledger REST API three
     times in parallel via `ThreadPoolExecutor`
     (`_fetch_account_head_commits_by_status`,
     [`commitPayment.py:67-84`](commitPayment.py#L67)), one request per status in
     `SALARY_COMMIT_STATUSES = ["COMMITTED", "PARTIALLY_PAID", "OVERPAYMENT"]`,
     hitting `GET {ACCOUNT_HEAD_COMMIT_API_URL}/by-status/{status}`.
  5. **Filtering** — merges all three result sets, keeps only rows where
     `moduleId == "11"` **and** `frapAppId == recruitment_doc_name` **and**
     `projectNumber == project_no`. Each surviving row is enriched with
     `projectTitle` (`_get_project_title_by_number`,
     [`commitPayment.py:53-64`](commitPayment.py#L53)).

- **Backend returns one of four shapes:**

  | Response | Meaning |
  |---|---|
  | `[{projectNumber, accountHeadId, moduleId, frapAppId, transactionCommitNumber, commitDate, ...}]` | Commit found (RAC-sourced, or Miscellaneous-Commit-sourced — see Step 4a) |
  | `[{status: "Pending Approval in Account Portal", message: "Salary already initiated"}]` | Already staged this month |
  | `[{status: "error", message: "..."}]` | Hard failure (no tenure, no employee, no Recruitment record **and** no approved Miscellaneous Commit fallback — see Step 4a) |
  | `[]` | Nothing matched |

- **Frontend does with each:**
  - Commit found → builds the commit payload (§3.3), marks the employee **payable**.
  - Already staged → marks them **Skipped**.
  - Error → marks them **Error**, shows the message.
  - Empty `[]` → does **not** give up — falls through to Step 4b.

---

### Step 4a — Migrated-employee fallback (server-side, part of the same `salary_payment_data` call as Step 4)

*File:* [`commitPayment.py`](commitPayment.py) — `_find_migrated_employee_commit`,
called from inside `salary_payment_data` the moment Recruitment linkage (Step 4,
point 3) fails to resolve. This runs **before** the function returns anything to
the frontend — it is not a separate HTTP call, and it means Step 4b (client-side
ledger fallback, below) is never reached for a migrated employee: this step
always resolves to either a match or an explicit error, never a bare `[]`.

1. Resolves `project_no` → the `Project Registration` document name.
2. Searches `Miscellaneous Commit` for candidates matching `project_number =
   <resolved project>`, `module = "Recruitment Adhoc Contractual"`,
   `commit_decommit = "Commit"`, `workflow_state = "Approved"`.
3. If more than one candidate exists, prefers one whose `linked_application`
   exactly matches `ps_emp_id`; otherwise takes the most recently approved
   project-level entry.
4. Re-fetches the real ledger row for that candidate — same parallel
   `by-status/{COMMITTED,PARTIALLY_PAID,OVERPAYMENT}` call as Step 4, point 4 —
   matched on `frapAppId == <Miscellaneous Commit name>` and `projectNumber ==
   project_no` (not `moduleId == "11"`, since a Miscellaneous Commit's `moduleId`
   on the ledger comes from the `Miscellaneous Commit` doctype's own Module
   Registry mapping, not a hardcoded 11).
5. **Match found on the ledger** → returns `[<row>]`, tagged with `source:
   "miscellaneous_commit"` and `linked_miscellaneous_commit: <name>` — same shape
   as any other commit-found response, so the frontend needs no changes to
   consume it. Fires an `:information_source:` **Salary Payment Data — Migrated
   Employee Fallback** Mattermost notification.
6. **No approved Miscellaneous Commit exists, or one exists but the ledger
   hasn't ingested it yet** (same `PENDING`-style lag as §10.1) → returns
   `[{"status": "error", "message": "No Recruitment/Selection Committee record
   found for employee '<ps_emp_id>', and no approved Miscellaneous Commit exists
   for project '<project_no>'. Salary payment cannot proceed."}]`. Fires an `:x:`
   **Salary Payment Data — No Funding Source** notification.

**Why the payment phase (`submit_payment_data`, Step 6 below) needed no
changes:** `_is_recruitment_salary_payment` already routes into the salary branch
based on `moduleName`/`moduleId == "11"` — always sent by the frontend for a
salary commit payload — not on `frapAppId` resolving to a real `Recruitment
Adhoc Contractual` document. A payment built from this fallback's row
(`frapAppId = <Miscellaneous Commit name>`) is detected and processed identically
to a normal Recruitment-sourced payment. Full design rationale, tie-break rules,
and edge cases: [`migrated-employee-salary-fallback.md`](migrated-employee-salary-fallback.md).

---

### Step 4b — Ledger fallback (only runs if Step 4 returned `[]`)

- **Frontend calls, directly, bypassing `commitPayment.py`:**
  `GET /ledger-api/account-head-commit/by-status/COMMITTED`
- **Backend involvement:** none — this hits the external ledger's REST API straight
  from the browser.
- **Ledger returns:** every `COMMITTED` commit row in the whole system, across all
  projects.
- **Frontend does with it:** filters it itself — keeps rows where
  `moduleId === "11"` **and** `normalize(projectNumber) === normalize(project_no)`,
  where `normalize` = trim + uppercase + strip non-alphanumeric characters.
  - Match found → builds the commit payload from this row instead.
  - Still no match → marks the employee **Error**: *"No committed budget-head entry
    found for project ..."*

> **This is the exact path that produces a false negative when a commit is stuck at
> `PENDING`.** Both Step 4 (`SALARY_COMMIT_STATUSES`) and Step 4b (hardcoded
> `/by-status/COMMITTED`) only ever look for commits already in a *settled* state.
> Neither one ever asks for `by-status/PENDING`. Confirmed live on 2026-07-20 for
> `ps_emp_id=2026TS0009`, `project_no=26RCLSTSP0742SAMI0001`,
> `frapAppId=202604150A00290`: two commit rows existed on the ledger for that exact
> project/frapAppId pair — ₹1,170,510 and ₹2,507,450 — both `status: "PENDING"`. Full
> root-cause writeup in §11.1.

---

### Step 5 — BMR modal

- Once every selected employee has been through Steps 4/4b, the frontend counts how
  many ended up **payable**.
  - **0 payable** → skips straight to the Results screen (Step 7), showing only the
    errors/skips.
  - **≥1 payable** → runs a **scheme validation**: all selected employees must share
    the same `schemeNumberMap[project_no]` (built in an earlier `Project
    Registration` fetch). If schemes are mixed, the PI gets an alert and the modal
    never opens.
  - Otherwise opens a modal listing each payable employee with net pay and a running
    total, and asks the PI to type in a **BMR** (Bill/Money Receipt) number.
- No backend call happens here — it's just collecting one piece of input before
  submission.

---

### Step 6 — PI clicks Submit → payment sent, one employee at a time

Runs **sequentially**, not in parallel — the backend's staging step below takes a
database lock per month, so parallel requests for the same month would just queue
behind each other anyway; sequential avoids surprising timeout behavior.

**6a.** — **Frontend calls:**
`GET /api/resource/Project Registration?filters=[["project_no","=","..."]]&fields=["name"]`
to turn the human-readable project number into the Frappe document name needed for
linking. Cached client-side in `projectRefCache`, so shared projects are only looked
up once per batch.

**6b.** — **Frontend calls:**
`POST .../commitPayment.submit_payment_data` with the body shown in §3.4.

**Backend (`submit_payment_data`, [`commitPayment.py:1224-1615`](commitPayment.py#L1224)) does, in order:**

1. **Salary detection** — `_is_recruitment_salary_payment`
   ([`commitPayment.py:1021-1033`](commitPayment.py#L1021)) checks, via
   `_get_form_value` ([`commitPayment.py:1073-1078`](commitPayment.py#L1073), which
   accepts both snake_case and camelCase keys):
   ```text
   doctype    == "Recruitment Adhoc Contractual"
   moduleName == "Recruitment Adhoc Contractual"
   moduleName == "11"
   moduleId   == "11"
   frapAppId exists as a "Recruitment Adhoc Contractual" document
   ```
   Any one being true routes into the salary branch below; otherwise it falls
   through to the generic path used by Reimbursement/Travel/TA-DA/Settlement.

2. **Build the staging payload** — starts from `dict(frappe.form_dict)` (everything
   the client posted), overwrites with the explicit function arguments, adds
   `status: "PENDING_PUBLISH"`, `project_no`, `account_number`, strips Frappe's
   internal `cmd` key. Fires a `:inbox_tray:` **Salary Payment Received** Mattermost
   notification — the first observability signal for this request.

3. **Stage & lock** — `_append_salary_staging_record`
   ([`commitPayment.py:1058-1160`](commitPayment.py#L1058)). This is a
   read-modify-write on a single JSON column, so concurrent submissions for the same
   month would race without protection:
   ```python
   lock_name = f"salary_staging_{salary_year_month}"
   got_lock = frappe.db.sql("SELECT GET_LOCK(%s, 10)", lock_name)[0][0]
   ```
   - Waits up to 10s for the lock. If it can't be acquired, returns an error and
     fires a `:x:` **Salary Staging Lock Timeout** alert — the only path where
     staging is skipped entirely and the caller is told to retry.
   - Once locked: loads the existing `Salary Staging/<year_month>` doc (if any),
     parses `salary_record` as a JSON array, appends the new payload, and
     `frappe.db.commit()`s immediately — so this audit row survives even if
     something later in the request fails.
   - If no staging doc exists yet, creates one with `flags.name_set = True` to
     bypass the `format:{YYYY}_{MMMM}` autoname and force the exact
     `salary_year_month` key.
   - `finally:` always releases the lock, even on exception.
   - **Why a JSON array and not JSON Lines?** MariaDB enforces a `json_valid()`
     CHECK constraint on `salary_record`. One JSON object per line fails that
     constraint; a single wrapping array satisfies it.

4. **Resolve project & budget head:**
   - `_sal_project` ([`commitPayment.py:1345`](commitPayment.py#L1345)): prefers
     explicit `project_name`, else `project_name`/`projectNumber`/`project_no` from
     the form. If not already a `Project Registration` doc name, looked up by
     `project_no`.
   - `_sal_bh` ([`commitPayment.py:1352`](commitPayment.py#L1352)): prefers
     explicit `budget_head`, else `budget_head`/`accountHeadId`/`account_head_id`.
     If not already a `Budget Head` PK, resolved by the `budget_head` label field,
     then by `id`.
   - Either failing to resolve → hard stop, no document created, fires `:x:`
     **Salary Payment Error** (`project_ref_number is required` /
     `budget_head is required`).

5. **Create the payment document**
   ([`commitPayment.py:1312-1370`](commitPayment.py#L1312)):
   ```python
   _sal_doc = frappe.new_doc("AccountHeadPayment")
   _sal_doc.project_ref_number = _sal_project
   _sal_doc.budget_head        = _sal_bh
   _sal_doc.payment_amount     = flt(payment_amount or 0)
   _sal_doc.payment_bmr        = bmr
   _sal_doc.payment_particular = ... or f"Salary payment - {frapAppId}"
   _sal_doc.payment_date       = today()
   _sal_doc.payment_status     = "PENDING"
   _sal_doc.flags.ignore_permissions = True
   _sal_doc.insert()
   ```
   **Naming** (`AccountHeadPayment.autoname`,
   [`doctype/accountheadpayment/accountheadpayment.py:9-25`](doctype/accountheadpayment/accountheadpayment.py#L9)):
   `{DD}{MM}{YYYY}{project_ref_number}`, `-{n}` suffix on collision — e.g. for
   project `26RCLSTSP0742SAMI0001` submitted on 20 July 2026, the name would be
   `2007202626RCLSTSP0742SAMI0001`.

6. **Publish to Kafka** — `kafka_publish_payment(...)` is called immediately.
   **There is no separate approval step for the salary payment itself** (unlike the
   commit phase in Step 0, which gates on workflow approval). Full mapper →
   validate → publish → retry/DLQ mechanics are in §8.
   - Success → `:white_check_mark:` **Salary Kafka Published**, returns
     `{"status": "success", "message": "Salary payment published to Kafka", "name": <doc>, "data": <doc.as_dict()>}`.
   - Failure → `:x:` **Salary Kafka FAILED**, returns
     `{"status": "error", "message": "Failed to publish salary payment to Kafka"}`.
     **The `AccountHeadPayment` document remains inserted even if Kafka publish
     fails** — payment execution and event publishing are not atomic (see §11.4 and
     the recovery path `publish_salary_staging` in §14).

**Frontend does with the response:** records a per-employee outcome
(success/error), then moves to the next employee in the batch.

---

### Step 7 — Results screen

- Once every employee in the batch has gone through Step 6, the frontend shows a
  **Results Modal**: one line per employee — ✓ success (with the created document
  name), ✗ error (with the message), or ⊘ skipped (already staged / no commit
  found).
- Successful employees are added to `processedEmployees` immediately, so they show
  up in the **Processed** tab without waiting for a page refresh
  (`markAsProcessed(empId)`).
- Frontend silently re-runs Step 1 (`fetchData()`) in the background to stay in sync
  with the server.

---

## 6. Salary Calculation Formula (frontend, client-side only)

```
daysInMonth       = total calendar days in selected month/year

workingDays       = days employee was active in the month
                    (from max(joining_date, monthStart)
                     to min(term_completion_date, monthEnd))
                    → 0 if joining_date > monthEnd
                    → 0 if term_completion_date < monthStart

proRataBasic      = round((basic_salary / daysInMonth) * workingDays)
proRataHRA        = round((hra / daysInMonth) * workingDays)
proRataMedical    = round((medical_allowance / daysInMonth) * workingDays)

grossPay          = proRataBasic + proRataHRA + proRataMedical + arrear

── Deductions ──────────────────────────────────────────
hraDeduction      = proRataHRA  (only if ps_hostel is truthy)
                    = 0         (if ps_hostel = "0" / "no" / "false" / "")
medicalDeduction  = proRataMedical  (default, editable)
pTax              = calcPTax(basic_salary)   ← see slabs below
ta                = 0  (editable)
idCardCharge      = 0  (editable)
electricityBill   = 0  (editable)
otherDeduction    = 0  (editable)

totalDeduction    = hraDeduction + medicalDeduction + pTax
                  + ta + idCardCharge + electricityBill + otherDeduction

netPay            = grossPay - totalDeduction
```

**Professional Tax Slabs** (Assam, applied on the contract basic salary, not
pro-rated):

| Monthly Basic Salary | P-Tax |
|---|---|
| ≤ ₹15,000 | ₹0 |
| ₹15,001 – ₹25,000 | ₹180 |
| > ₹25,000 | ₹208 |

This entire calculation runs in the browser — the backend never recomputes it.
`payment_amount` in the Step 6b payload is accepted by `submit_payment_data` exactly
as sent; there is no server-side tax/deduction/bonus recalculation anywhere in
`commitPayment.py`.

---

## 7. Frontend State Map

```
records[]               — all StaffRecord objects from Frappe
isLoading               — true during fetchData
error                   — Frappe error string or null
selectedMonth           — 0–11 (current month default)
selectedYear            — e.g. 2026
preparedCycles          — { "2026-7": true } from localStorage
isPrepared              — derived from preparedCycles[cycleKey]
processedEmployees      — Set<employee_id> from Salary Staging doc
overrides               — { [docName]: Partial<EditableInputs> }
selectedEmpIds          — Set<employee_id> (checkboxes)
pendingBulkCommits      — { [empId]: commitPayload } ready for submission
selectedBulkRecords     — StaffRecord[] shown in BMR modal preview
buildFailures[]         — PaymentOutcome[] for employees that couldn't get a commit
bmrInput                — string entered in BMR modal
bmrSubmitting           — true while POSTing payments
paymentResults[]        — final per-employee outcomes
resultsModalOpen        — controls Results Modal visibility
schemeMap               — { project_no → funding_agency_schemes }
schemeNumberMap         — { project_no → enter_scheme_number }
departmentLabels        — { dept_id → dept_name }
activeTab               — "pending" | "processed"
```

---

## 8. Kafka Publishing — Full Mechanics

### 8.1 Producer Architecture

*Directory:* [`kafka/producer/reimbursement/`](kafka/producer/reimbursement/)

```
  submit_payment_data() / check_workflow_and_publish()
                    │
                    ▼
  publish_payment() / publish_commit()
                    │
                    ▼
            Mapper.map_to_event()
                    │
                    ▼
             DTO (dataclass)
                    │
                    ▼
            Validator.validate()
              │              │
          invalid          valid
              │              │
              ▼              ▼
  ValidationError      to_kafka_payload()
  → mm_notify                │
  → return False             ▼
                       publish_message()
                              │
                              ▼
                  KafkaProducer.send()
                  (acks=all, retries=3)
                    │              │
                   ack        all retries fail
                    │              │
                    ▼              ▼
             mm_notify        DLQ topic
              SUCCESS
```

### 8.2 Validation (`AccountHeadPaymentValidator`, [`validator.py:68-107`](kafka/producer/reimbursement/validator.py#L68))

| Rule | Failure message |
|---|---|
| `projectNumber` must be truthy | `projectNumber is required` |
| `accountHeadId` must not be `None` | `accountHeadId is required` |
| `paymentDate` must be truthy | `paymentDate is required` |
| `paymentStatus` ∈ `{PAID, PENDING, CANCELLED, FAILED, RECTIFICATION, REJECTED}` | `paymentStatus must be one of: ...` |

A validation failure raises `ValidationError`, which the producer catches, logs,
Mattermost-alerts (`:x: Kafka Payment Validation FAILED`), and returns `False` — **no
Kafka send is attempted**, and no retry/DLQ applies (validation happens before the
network call).

For commits, `AccountHeadCommitValidator` ([`validator.py:17-65`](kafka/producer/reimbursement/validator.py#L17))
accepts `status` ∈ `{COMMITTED, PENDING, CANCELLED}` — `PENDING` is a *valid* value
the validator would accept, it's just that nothing in this codebase ever constructs a
commit DTO with it (see §5 Step 0, point 3).

### 8.3 Publish + Retry + DLQ (`publish_message`, [`kafka/utils.py:99-190`](kafka/utils.py#L99))

- Uses a **singleton `KafkaProducer`** (`get_producer()`), connected to
  `KAFKA_BOOTSTRAP_SERVERS = ['172.16.134.81:9095', '172.16.134.81:9096']` with
  `acks="all"`, `retries=3`, `linger_ms=10`.
- Partition key = `projectNumber` (all events for one project land on the same
  partition, preserving ordering for that project).
- Up to `PRODUCER_MAX_RETRIES = 3` attempts, exponential backoff
  (`PRODUCER_RETRY_DELAY_SECONDS * 2**attempt`), resetting the producer connection
  between attempts.
- If every attempt fails, the payload is wrapped with `originalTopic`, `failedAt`,
  `retryCount`, `error` and sent once to the **DLQ topic**
  (`account-head-payment-events-dlq`).
- Every attempt/success/retry/DLQ send is logged via `log_producer_event` into
  `kafka/logs/files/producer.log` (rotating, 10 MB × 5 backups) and mirrored to
  `error.log` on failure.

### 8.4 Topics Reference

| Topic | Direction | Purpose |
|---|---|---|
| `account-head-commit-events` | Produced | Budget committed for a project/employee (fires on workflow → `Approved`) |
| `account-head-commit-events-dlq` | Produced (on failure) | Dead-letter for the above |
| `account-head-payment-events` | Produced | Actual payment made (fires immediately on `submit_payment_data`) |
| `account-head-payment-events-dlq` | Produced (on failure) | Dead-letter for the above |

There is **no consumer** for either topic inside this app — the consumer is the
external ledger microservice at `172.16.134.81:18080`, which also exposes the REST
APIs used by Steps 4/4b.

---

## 9. Error & Skip Conditions — Full Table

| Condition | Layer | Outcome |
|---|---|---|
| Employee's working days = 0 for selected period | Frontend (Step 1) | Filtered out — never shown in the table |
| `isPrepared === false` for the selected cycle | Frontend (Step 2) | Table/actions hidden behind "Not Prepared" banner |
| `salary_payment_data` returns `status: "Pending Approval in Account Portal"` | Backend (Step 4) | **Skipped** — already staged, not submitted again |
| `salary_payment_data` returns `status: "error"` (no tenure / no employee) | Backend (Step 4) | **Error** — shown in results modal |
| No Recruitment/SCR record for the employee, and an approved Miscellaneous Commit exists for the project | Backend (Step 4a) | **Payable** — funded from the Miscellaneous Commit's budget head, same as any other match |
| No Recruitment/SCR record for the employee, and no approved Miscellaneous Commit exists (or one exists but isn't on the ledger yet) | Backend (Step 4a) | **Error** — "No Recruitment/Selection Committee record found ... and no approved Miscellaneous Commit exists ..." — see [`migrated-employee-salary-fallback.md`](migrated-employee-salary-fallback.md) |
| `salary_payment_data` returns `[]` AND ledger fallback finds no `moduleId=11` commit for this project | Backend (Step 4) + Frontend (Step 4b) | **Error** — "No committed budget-head entry found" (see §11.1 for the `PENDING`-commit false-negative case). Only reachable for employees whose Recruitment/SCR chain resolves — the migrated-employee path (Step 4a) never returns a bare `[]`. |
| Commit payload missing `projectNumber`/`accountHeadId`/`moduleId`/`frapAppId`/`transactionCommitNumber` | Frontend (`buildCommitData`) | **Error** — "Incomplete commit data — missing: ..." |
| Selected employees belong to different scheme numbers | Frontend (Step 5) | **Aborted before modal** — alert shown |
| Salary staging lock not acquired within 10s | Backend (`_append_salary_staging_record`) | Returns error; **record NOT staged**; `:x:` Mattermost alert |
| `salary_year_month` unresolved | Backend (`submit_payment_data`) | Staging step skipped entirely, execution continues to payment creation; `:warning:` Mattermost alert |
| DB error while staging (JSON parse/write) | Backend (`_append_salary_staging_record`) | `frappe.log_error`, returns error dict; lock still released via `finally`; `:rotating_light:` alert |
| `project_ref_number` / `budget_head` unresolvable | Backend (`submit_payment_data`) | Hard return before any document is created; `:x:` alert |
| `AccountHeadPayment.insert()` raises | Backend (outer `try/except`) | `frappe.log_error`, returns `{"status": "error", ...}`; `:rotating_light:` alert |
| `submit_payment_data` returns HTTP error | Frontend (Step 6b) | **Error** — HTTP status shown |
| `submit_payment_data` returns 200 but `message.status === "error"` | Frontend (Step 6b) | **Error** — backend message shown |
| `submit_payment_data` returns 200 but no `message.name` | Frontend (Step 6b) | **Error** — "Backend did not confirm the payment was staged" |
| DTO validation fails (missing required field / bad enum) | Backend (`AccountHeadPaymentProducer.publish`) | No Kafka send attempted, returns `False`; `:x:` Kafka Payment Validation FAILED |
| Kafka broker unreachable / all 3 retries fail | Backend (`publish_message`) | Payload forwarded once to DLQ; `CRITICAL` entry in `error.log` if that also fails; `:x:` alert |
| `is_kafka_available()` is `False` | Backend (`AccountHeadPaymentProducer.publish`) | Immediate `False`, no attempt made; `:warning:` Kafka Payment SKIPPED |

---

## 10. Integration Gotchas

### 10.1 "No committed budget-head entry found" can show even when a commit genuinely exists

Both Step 4 (`SALARY_COMMIT_STATUSES = ["COMMITTED", "PARTIALLY_PAID", "OVERPAYMENT"]`)
and Step 4b (hardcoded to `/by-status/COMMITTED`) only ever look for commits already
in a *settled* state. Neither one ever asks for `by-status/PENDING`.

Confirmed live on 2026-07-20 for `ps_emp_id=2026TS0009`,
`project_no=26RCLSTSP0742SAMI0001`, `frapAppId=202604150A00290`: two commit rows
existed on the ledger for that exact project/frapAppId pair — ₹1,170,510 and
₹2,507,450 — both `status: "PENDING"`. Step 4 returned `count: 0`; Step 4b would also
have returned nothing, since it only asks for `COMMITTED`. The PI's read of the
situation ("budget head is there") was correct — the row exists — but neither step
surfaces `PENDING` rows, so the UI shows an error that reads like a missing commit
rather than a stuck one.

**Root cause is outside this repo.** The backend always publishes commits with
`status: "COMMITTED"` (§5 Step 0, point 3 / §8.2) — hardcoded, not overridable. The
only status-*update* call this codebase ever makes against the ledger sets
`"CANCELLED"` (`cancellation_request.py:166`), not `"COMMITTED"`. So a commit landing
at `PENDING` isn't something the frontend or `commitPayment.py` did — the ledger
microservice applies its own initial status on ingestion regardless of what's sent,
and nothing in this stack ever advances it. Fixing the PI-visible symptom means
either (a) adding `PENDING` to both status checks so these are surfaced (with
whatever UX makes sense for "commit not yet settled"), or (b) getting the ledger
service to honor/transition the incoming status — neither is a `rndopsapp` code
change on its own.

### 10.2 The "prepared cycle" lock is invisible to the backend

`isPrepared` (Step 2) comes entirely from browser `localStorage`. The backend has no
doctype, field, or endpoint representing "this month is prepared" — Steps 4 and 6
will happily respond regardless of what the frontend thinks. The lock is therefore
per-browser, not per-PI-account, and can't be enforced server-side.

### 10.3 Two independent "already paid" checks, one authoritative

Step 3's `processedEmployees` and the duplicate guard inside Step 4
(`_salary_staging_has_ps_emp_id`) both read the same `Salary Staging` doc, but at
different times: Step 3 is a **display-only** snapshot taken once per period change;
the check inside Step 4 is **live**, re-checked on every eligibility call, and is
what actually prevents a double-submission if the frontend's cached snapshot is
stale (e.g. two browser tabs open). The tab split can lag reality by one refresh —
the live check in Step 4 is what actually guards against duplicates.

### 10.4 `payment_status` starts at `PENDING` and nothing advances it

Both the frontend (Step 6b payload) and the backend default fall back to
`payment_status: "PENDING"`. Nothing in either half of this flow ever transitions an
`AccountHeadPayment` document's status after creation — presumably a downstream
reconciliation step (bank confirmation, ledger settlement) outside both halves
documented here. Combined with §5 Step 6 point 6 (staging commits before Kafka
publish is attempted, non-atomically), a `Salary Staging` audit row can show an
attempt while its `AccountHeadPayment` sits in `PENDING` with no corresponding Kafka
event — `publish_salary_staging` (§14) is the intended way to reconcile this later.

---

## 11. Configuration Reference

### 11.1 Mattermost (hardcoded in both `commitPayment.py` and `kafka/utils.py`)

```python
_MM_URL     = "http://172.16.135.118:8065/api/v4/posts"
_MM_TOKEN   = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_KAFKA_CHANNEL = "yh7piky97iycjrdytia1hqy99a"    # "kafka logs" channel
_MM_SALARY_CHANNEL = "knetjx859tfu8g3tecr1tu8mne"   # "Salary Module" channel
```

`_mm_notify` always runs in a **daemon thread** with a `(2, 3)` second connect/read
timeout and swallows all exceptions — a Mattermost outage can never break the payment
flow, but also fails silently (nothing in `Error Log` if the POST itself fails).

### 11.2 Kafka (`kafka/config.py`)

| Setting | Value |
|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `172.16.134.81:9095`, `172.16.134.81:9096` |
| `PRODUCER_ACKS` | `"all"` |
| `PRODUCER_RETRIES` / `PRODUCER_MAX_RETRIES` | `3` / `3` |
| `PRODUCER_RETRY_DELAY_SECONDS` | `1` (exponential: 1s, 2s, 4s) |
| `PRODUCER_LINGER_MS` | `10` |
| `CONSUMER_GROUP_ID` | `rndopsapp-consumer-group-v2` (unrelated to salary — no consumer subscribes to the payment/commit topics) |

### 11.3 External Ledger REST API (`commitPayment.py:44-46`)

```python
LEDGER_API_BASE_URL          = "http://172.16.134.81:18080/api/commit-payment-transactions"
ACCOUNT_HEAD_PAYMENTS_API_URL = "http://172.16.134.81:18080/api/account-head-payments"
ACCOUNT_HEAD_COMMIT_API_URL   = "http://172.16.134.81:18080/api/account-head-commit"
```

Endpoints actually used against `ACCOUNT_HEAD_COMMIT_API_URL`:

| Path | Used by | Purpose |
|---|---|---|
| `GET /by-status/{status}` | Step 4 (`_fetch_account_head_commits_by_status`), Step 4b (frontend direct), `po_commit_adjustment.py` | Read commits filtered by status |
| `GET /by-account-head/{id}` | `get_commits_by_account_head` (commitPayment.py:645) | Read commits for one budget head |
| `GET /by-account-head/{id}/status/{status}` | `get_commits_by_account_head_and_status` (commitPayment.py:694) | Read commits for one budget head, filtered by status |
| `POST /status/by-project-frap` | `cancellation_request.py:166` | **The only status-update call in this codebase** — sets `status: "CANCELLED"` in place by `(project, frapAppId)`. Nothing calls this (or an equivalent) to advance a commit from `PENDING` to `COMMITTED`. |

### 11.4 Frappe Hooks (`hooks.py`)

```python
doc_events = {
    "*": {
        "on_update": [
            "rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish",
            "rndopsapp.rndopsapp.activity_logger.log_workflow_transition",
        ]
    }
}
```

No scheduled/cron job drives the salary flow — the recovery endpoints in §14 are
`@frappe.whitelist()` endpoints, invoked on demand, not on a timer.

### 11.5 Logging

| File | Content |
|---|---|
| `kafka/logs/files/producer.log` | Every `STARTED`/`VALIDATED`/`SUCCESS`/`FAILED`/`RETRY` producer event (rotating, 10 MB × 5 backups) |
| `kafka/logs/files/error.log` | Mirror of all `FAILED`/`ERROR` producer events + explicit `log_error` calls |
| `kafka/logs/files/debug.log` | Low-level debug (e.g. producer connection established) |
| Frappe `Error Log` doctype | `frappe.log_error(...)` calls from `commitPayment.py` itself |
| `print(...)` statements (`[PAYMENT_DEBUG]`, `[SALARY_STAGING]`, `[SUBMIT_PAYMENT_DATA]`) | Go to stdout of the Frappe web worker process — visible under `bench start`, **not** in `Error Log` |

---

## 12. Code References (backend)

| Component | File | Responsibility |
|---|---|---|
| `salary_payment_data` | [`commitPayment.py:219`](commitPayment.py#L219) | Eligibility + already-staged check (read-only) — Step 4 |
| `_salary_staging_has_ps_emp_id` / `_json_contains_ps_emp_id` | [`commitPayment.py:185`](commitPayment.py#L185) / [`:87`](commitPayment.py#L173) | Duplicate-submission detection inside staged JSON |
| `_fetch_account_head_commits_by_status` | [`commitPayment.py:67`](commitPayment.py#L67) | External ledger REST call, per status |
| `_get_project_title_by_number` | [`commitPayment.py:53`](commitPayment.py#L53) | Project title enrichment |
| `_is_recruitment_salary_payment` | [`commitPayment.py:1081`](commitPayment.py#L1081) | Salary-vs-generic branch detection — Step 6 |
| `_get_form_value` | [`commitPayment.py:1073`](commitPayment.py#L1073) | snake_case/camelCase form fallback |
| `_salary_payload_identity` | [`commitPayment.py:1096`](commitPayment.py#L1096) | Human-readable id for logs/Mattermost |
| `_append_salary_staging_record` | [`commitPayment.py:1118`](commitPayment.py#L1118) | Locked upsert into `Salary Staging` — Step 6, point 3 |
| `submit_payment_data` | [`commitPayment.py:1224`](commitPayment.py#L1224) | Main entry point: salary branch + generic branch — Step 6 |
| `submit_commit_data` | [`commitPayment.py:811`](commitPayment.py#L811) | Stage a commit for later workflow-triggered publish — Step 0 |
| `check_workflow_and_publish` | [`commitPayment.py:891`](commitPayment.py#L891) | `on_update` hook — fires commit publish on workflow state match — Step 0 |
| `manually_publish_staged_commit` | [`commitPayment.py:1001`](commitPayment.py#L1001) | Admin re-trigger for stuck commit staging rows |
| `publish_salary_staging` | [`commitPayment.py:1617`](commitPayment.py#L1617) | Admin re-trigger: replay every un-published record in a month's staging doc |
| `search_salary_records` | [`commitPayment.py:1964`](commitPayment.py#L1964) | Flattens all `Salary Staging` docs into searchable/paginated rows for an ops/admin UI |
| `delete_salary_record` | [`commitPayment.py:2117`](commitPayment.py#L2117) | Password-gated removal of one employee's entry from a month's `salary_record` array |
| `_mm_notify` | [`commitPayment.py:23`](commitPayment.py#L23) | Fire-and-forget Mattermost POST (daemon thread) |
| `AccountHeadPaymentMapper` / `AccountHeadCommitMapper` | [`kafka/producer/reimbursement/mapper.py`](kafka/producer/reimbursement/mapper.py) | Frappe doc → DTO |
| `AccountHeadPaymentDTO` / `AccountHeadCommitDTO` | [`kafka/producer/reimbursement/dto.py`](kafka/producer/reimbursement/dto.py) | Wire-format dataclasses |
| `AccountHeadPaymentValidator` / `AccountHeadCommitValidator` | [`kafka/producer/reimbursement/validator.py`](kafka/producer/reimbursement/validator.py) | Required-field / enum validation before publish |
| `publish_message`, `get_producer`, `is_kafka_available` | [`kafka/utils.py`](kafka/utils.py) | Singleton producer, retry + DLQ, `mm_notify` |
| `AccountHeadPayment.autoname` | [`doctype/accountheadpayment/accountheadpayment.py:9`](doctype/accountheadpayment/accountheadpayment.py#L9) | `{DD}{MM}{YYYY}{project_ref_number}[-n]` naming |
| `doc_events["*"]["on_update"]` | [`hooks.py:154`](../hooks.py#L154) | Wires `check_workflow_and_publish` to every doctype save |

---

## 13. Failure Modes Across the Boundary — Quick Reference

| Symptom the PI sees | Which step | Root cause layer |
|---|---|---|
| "No committed budget-head entry found" | Step 4 / 4b both return no match | Backend + Step 4b status filter, or a genuinely `PENDING` commit (§10.1 above) |
| "Salary already initiated" | Step 4 finds this employee already staged | Working as intended — duplicate guard |
| Employee never appears in the payable list at all | Filtered out before Step 4 even runs | Frontend-only: `workingDays === 0` for the selected period |
| "Backend did not confirm the payment was staged" | Step 6b returned 200 but no `name` field | Likely hit the generic (non-salary) path instead — check `frapAppId`/`moduleName`/`moduleId` were actually sent |
| Payment "succeeds" but PI can't find the Kafka event later | Step 6b returned success | `AccountHeadPayment` was saved; Kafka publish may still have failed after retries — check Mattermost `:x: Kafka Payment FAILED`, not the HTTP response |

---

## 14. Recovery / Admin Endpoints

- **`manually_publish_staged_commit(reference_name, reference_doctype)`**
  ([`commitPayment.py:941`](commitPayment.py#L941)) — replays any
  `PENDING_APPROVAL`/`FAILED` `Kafka Commit Staging` row for a document, for the
  commit phase (Step 0). Use when a Recruitment doc is already `Approved` but the
  `on_update` hook didn't fire the commit publish.
- **`publish_salary_staging(salary_year_month)`**
  ([`commitPayment.py:1557`](commitPayment.py#L1557)) — iterates every record inside
  a month's `Salary Staging.salary_record` array not already `status: "PUBLISHED"`,
  creates/reuses an `AccountHeadPayment` per record, republishes to Kafka, and writes
  the per-record outcome back into the array. Returns
  `{"published": n, "failed": n, "skipped": n, "total": n}`. This is the intended
  fix for the non-atomicity gap noted in §10.4.
- **`search_salary_records(query, year, month, status, page, page_size)`**
  ([`commitPayment.py:1904`](commitPayment.py#L1904)) — flattens every `Salary
  Staging` doc into searchable, paginated rows (one per employee per month) for an
  ops/admin view.
- **`delete_salary_record(year_month, employee_id, project_number, commit_date, override_password)`**
  ([`commitPayment.py:2057`](commitPayment.py#L2057)) — password-gated removal of
  one employee's entry from a month's `salary_record` JSON array; deletes the whole
  `Salary Staging` doc if the array becomes empty.

---

## 15. Where To Look Next

- **Backend-only deep dive** (this same content, backend-centric framing): [`salary-payment-workflow.md`](salary-payment-workflow.md).
- **Frontend calculation edge cases, exact TypeScript types**: frontend team's `SalaryModule.tsx` source.
- **Ledger status behavior** (`PENDING` vs `COMMITTED`, the `/status/by-project-frap` endpoint): only visible from the ledger microservice's own code/logs — outside this repo, owned by whoever runs `172.16.134.81:18080`.
