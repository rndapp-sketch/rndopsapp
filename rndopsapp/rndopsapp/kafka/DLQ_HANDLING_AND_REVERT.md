# Kafka DLQ Handling + Document Revert

Reference documentation for the DLQ (dead-letter-queue) handling work added on
2026-08-14. Covers why this was needed, what was investigated, the decisions
made, and every file touched.

## 1. The problem

`rndopsapp` publishes financial events (Fund Sanction, Fund Received, Deposit
Slip, Loan Request, Account Head Commit, Account Head Payment) to Kafka. Each
producer topic has a matching `-dlq` topic. A look at the cluster's topic list
showed real messages already sitting in 5 of these DLQ topics:

| Topic | Messages |
|---|---|
| `fund-sanction-events-dlq` | 2 |
| `fund-received-events-dlq` | 8 |
| `deposit-slip-events-dlq` | 1 |
| `account-head-commit-events-dlq` | 4 |
| `account-head-payment-events-dlq` | 3 |

Before this work, only `account-head-payment-events-dlq` had a consumer
(`kafka/consumer/payment_dlq/`) — and even that one only logged the failure
for the frontend to poll; it never reverted the source document. The other 4
topics had **no consumer at all**. Documents kept showing a state (e.g.
`workflow_state = "Sanction Approved"`, `payment_status = "PAID"`) that the
downstream ledger service had actually rejected.

## 2. Investigation

### 2.1 What's actually in the DLQ topics

Read-only peek at the 5 topics (no offsets committed, no consumer groups
touched — see the one-off script used, reproduced in §6):

```python
from kafka import KafkaConsumer
from kafka.structs import TopicPartition
consumer = KafkaConsumer(
    bootstrap_servers=['172.16.134.81:9095', '172.16.134.81:9096'],
    enable_auto_commit=False,
    auto_offset_reset='earliest',
    consumer_timeout_ms=8000,
)
```

Finding: the messages are **not** our own producer's retry-failure envelope
(`{originalTopic, failedAt, error, payload}` — that's what
`kafka/utils.py::publish_message()` sends to its own DLQ when *our* send
fails after retries). They're the **raw original event**
(`{schemaVersion, eventType, timestamp, data: {...}}`), meaning the external
Java ledger microservice received and rejected them, then republished the
unchanged message to `-dlq` itself. This matches the one working example
already in the codebase (`kafka/consumer/payment_dlq/`, see its docstring)
and confirms these are **downstream rejections**, not broker/network
failures. Also confirmed: unlike `payment_dlq`'s DTO, these messages carry
**no error reason** from the Java side.

### 2.2 Where the pieces live

- Producers: `kafka/producer/{fund_sanction,fund_received,deposit_slip,loan_request,project_registration,reimbursement}/producer.py`, all routing through `kafka/utils.py::publish_message()`.
- A second, older/legacy producer module `kafka_sync.py` also exists (duplicates some of the same publish logic) — not touched by this work.
- `commitPayment.py` publishes `account-head-commit-events` / `account-head-payment-events` via its own `kafka_publish_commit`/`kafka_publish_payment`, using the **`Kafka Commit Staging`** doctype to track publish status per staged commit (`PENDING_APPROVAL` → `PUBLISHED`/`FAILED`). This staging doctype is fed by ~9 unrelated doctypes (Travel, TA/DA Settlement, Disbursal of Honorarium/Consultancy, Top Up Fellowship, Recruitment Adhoc Contractual, Indent General Form, Cancellation Request, ICSS PO) via `commitPayment.py::check_workflow_and_publish`.
- Consumer infra: `kafka/consumer/manager.py` runs a background thread (auto-started via `hooks.py`'s `before_request` → `kafka/consumer_service.py::ensure_consumer_running`), polling every topic in `kafka/config.py::ALL_CONSUMER_TOPICS` and routing each message through `kafka/consumer/handler.py::TOPIC_HANDLERS`.
- Important existing quirk: `manager.py::get_consumer()` has **no persisted offsets** (`enable_auto_commit=False`, no `group_id`) and calls `seek_to_beginning()` on every (re)start — so a restart replays the full history of every assigned topic.

## 3. Decisions (asked, not assumed)

Two decisions were confirmed with the user before writing any code:

1. **Revert aggressiveness** — chosen: **actually revert `workflow_state`
   back** (not just flag it), mirroring the one place in the codebase that
   already does this correctly today, `project_registration.py`'s
   synchronous revert-on-publish-failure.
2. **Existing backlog** — chosen: **do not process it**. The new consumers
   must start from the current end of each DLQ topic; only failures from
   this point forward are handled.

## 4. Design

### 4.1 Capturing "previous state" at publish time

A DLQ consumer runs long after the original save transaction — it can't call
`get_doc_before_save()` the way `project_registration.py` does synchronously.
Every revert call site already computes `old_state`/`previous_state` (or
`current_state`) right before calling `publish_*`. Each of those call sites
now writes one extra row via a new shared helper,
`kafka/utils.py::record_publish_state(reference_doctype, reference_name,
topic, previous_state, published_state)`, into a new doctype:

**`Kafka Publish State Log`** — `reference_doctype`, `reference_name`,
`topic`, `status` (`PUBLISHED`/`DLQ_REVERTED`), `previous_workflow_state`,
`published_state`, `error_message`. This is the authoritative source the DLQ
consumers use to know what to revert to — no guessing from Kafka payload
contents. `record_publish_state()` is a no-op when there's no real
transition to capture (new document, or republishing the same state).

### 4.2 Shared DLQ log doctype

**`Kafka Event DLQ Log`** — `source_topic`, `event_type`,
`reference_doctype`, `reference_name`, `project_number`,
`previous_workflow_state`, `reverted` (checkbox), `raw_payload`. One shared
doctype (not one per topic) for the 4 new workflow-reverting consumers plus
the commit consumer, modeled on the existing `Kafka Payment DLQ Log`. Every
DLQ message is logged here regardless of whether reference resolution
succeeds, so nothing is silently dropped.

### 4.3 Shared consumer helper

`kafka/consumer/dlq_common.py` — used by the 4 workflow-state-reverting
consumers (sanction/fund-received/deposit-slip/loan-request):

- `find_publish_state_log(reference_doctype, reference_name, topic)` — latest still-`PUBLISHED` `Kafka Publish State Log` row.
- `revert_workflow_state(reference_doctype, reference_name, previous_state, state_log_name)` — `frappe.db.set_value(..., "workflow_state", previous_state, update_modified=False)` + marks the state-log row `DLQ_REVERTED` + commit. Same idiom `project_registration.py` already uses.
- `log_dlq_event(...)` — always writes a `Kafka Event DLQ Log` row.

Idempotency: because the underlying consumer replays from the beginning on
every restart (see §2.2), the revert action is naturally guarded by the
state-log row's `status` — once `DLQ_REVERTED`, `find_publish_state_log`
won't find it again (it only looks for `PUBLISHED`), so a replayed message
can't double-revert. The `Kafka Event DLQ Log` visibility table can still
gain a duplicate row on replay — same characteristic the existing
`Kafka Payment DLQ Log` already has; not a regression.

### 4.4 The 5 new DLQ consumer packages

Each follows the existing `kafka/consumer/payment_dlq/` shape
(`dto.py` / `mapper.py` / `consumer.py`):

| Package | Topic | Resolves reference via |
|---|---|---|
| `sanction_dlq` | `fund-sanction-events-dlq` | `projectNumber` → `Fund Sanction.refnum_prj_num` / `.project_proposal` (best-effort, no single natural key) |
| `fund_received_dlq` | `fund-received-events-dlq` | `fundReceivedRefNumberFap` == doc name (exact) |
| `deposit_slip_dlq` | `deposit-slip-events-dlq` | `depositSlipRefNumFab`/`slipNumber` == doc name, tried across all 6 known deposit-slip doctypes (imported from `kafka/producer/deposit_slip/producer.py`'s `CONSULTANCY_DOCTYPES`/`RESEARCH_DOCTYPES`) |
| `loan_request_dlq` | `loan-request-event-dlq` | `projectNumber` → `Loan Request.project_number` |
| `commit_dlq` | `account-head-commit-events-dlq` | `frapAppId` → `Kafka Commit Staging` row (`JSON_EXTRACT(payload, '$.frap_app_id')`) |

`commit_dlq` is the odd one out: instead of a `workflow_state` revert, it
flips the matching `Kafka Commit Staging` row `PUBLISHED` → `FAILED` with
`error_message = "Rejected by downstream ledger consumer (...)"` — the same
mechanism `commitPayment.py::check_workflow_and_publish` already uses for its
own synchronous failure path, and the same thing the frontend already polls
via `commitPayment.get_commit_staging_status`. Reverting `workflow_state` on
the ~9 doctypes that feed staging was explicitly **out of scope** — none of
them have a captured "previous state" to revert to, and guessing at 9
unrelated workflows blind was judged too risky.

### 4.5 Extending the existing payment DLQ consumer

`kafka/consumer/payment_dlq/mapper.py::PaymentDlqErrorMapper` gained
`revert_payment_status(reference_name)`: when the `AccountHeadPayment` doc
resolves and its `payment_status` is currently `PAID`, sets it to
`REJECTED` — an option that already existed on that Select field
(`doctype/accountheadpayment/accountheadpayment.json`) but was unused by any
code path before this. Called from `consumer.py::handle()` right after the
existing `save_error()` call.

### 4.6 Wiring

- `kafka/config.py` — added `TOPIC_ACCOUNT_HEAD_COMMIT` /
  `TOPIC_ACCOUNT_HEAD_COMMIT_DLQ` constants (previously only defined as
  plain strings inside `commitPayment.py`), added
  `NEW_DLQ_CONSUMER_TOPICS` (the 5 new DLQ topics), and appended them to
  `ALL_CONSUMER_TOPICS`.
- `kafka/consumer/handler.py` — registered the 5 new topic → handler
  entries in `TOPIC_HANDLERS`.
- `kafka/consumer/manager.py::get_consumer()` — after the existing
  `consumer.assign(...)` + `seek_to_beginning()`, added a targeted
  `consumer.seek_to_end(*new_dlq_tps)` for just the `NEW_DLQ_CONSUMER_TOPICS`
  partitions, so the pre-existing backlog is skipped (decision #2 in §3) —
  the 3 pre-existing consumer topics keep their unchanged beginning-replay
  behavior.

## 5. Files touched

**New files**

```
doctype/kafka_publish_state_log/kafka_publish_state_log.json
doctype/kafka_publish_state_log/__init__.py
doctype/kafka_event_dlq_log/kafka_event_dlq_log.json
doctype/kafka_event_dlq_log/__init__.py

kafka/consumer/dlq_common.py

kafka/consumer/sanction_dlq/{__init__,dto,mapper,consumer}.py
kafka/consumer/fund_received_dlq/{__init__,dto,mapper,consumer}.py
kafka/consumer/deposit_slip_dlq/{__init__,dto,mapper,consumer}.py
kafka/consumer/commit_dlq/{__init__,dto,mapper,consumer}.py
kafka/consumer/loan_request_dlq/{__init__,dto,mapper,consumer}.py

kafka/dlq_control_api.py

apps/frappe/frappe/www/kafka_dlq_control.html   # new admin page, see §8
```

**Edited files**

```
kafka/utils.py                    — added record_publish_state()
kafka/config.py                   — new topic constants, NEW_DLQ_CONSUMER_TOPICS, ALL_CONSUMER_TOPICS
kafka/consumer/handler.py         — 5 new TOPIC_HANDLERS entries
kafka/consumer/manager.py         — seek_to_end for NEW_DLQ_CONSUMER_TOPICS
kafka/consumer/payment_dlq/mapper.py    — revert_payment_status()
kafka/consumer/payment_dlq/consumer.py  — calls revert_payment_status()

doctype/fund_sanction/fund_sanction.py                                — record_publish_state() at both publish_sanction(doc) call sites
doctype/fund_received/fund_received.py                                — record_publish_state() before publish_fund_received(doc)
doctype/loan_request/loan_request.py                                  — record_publish_state() before publish_loan_request(doc)
doctype/research_deposit_slip/research_deposit_slip.py                — record_publish_state() at both publish call sites
doctype/research_consultancy_deposit_slip/research_consultancy_deposit_slip.py — record_publish_state()
doctype/d_consultancy_deposit_slip/d_consultancy_deposit_slip.py      — record_publish_state() at both publish call sites
doctype/e_non_routine_deposit_slip/e_non_routine_deposit_slip.py      — record_publish_state() at both publish call sites
doctype/t_testing_deposit_slip/t_testing_deposit_slip.py              — record_publish_state() at both publish call sites
doctype/other_event_deposit_slip/other_event_deposit_slip.py          — record_publish_state() at both publish call sites
```

**Explicitly out of scope** (documented, not silently skipped):

- `account-head-commit-batch-events-dlq` / `account-head-payment-batch-events-dlq` (fed by `doctype/po_commit_adjustment/po_commit_adjustment.py`) and `loan-settlement-events*` topics — zero historical traffic, and `Po Commit Adjustment` has no single revertible status field.
- Reverting `workflow_state` on the ~9 doctypes that feed `Kafka Commit Staging` (see §4.4).

## 6. Verification performed

1. **Syntax**: every new/edited `.py` file compiled cleanly (`python -m py_compile`).
2. **Import correctness**: every new/edited module imported cleanly against the real dev site (`frappe.init(site='prornd.local')` + `frappe.connect()` from `sites/`), catching any relative-import mistakes `py_compile` alone wouldn't.
3. **Schema**: both new doctypes reloaded onto the dev DB (`frappe.reload_doc('Rndopsapp', 'doctype', 'kafka_publish_state_log'/'kafka_event_dlq_log', force=True)`) and confirmed to exist (`frappe.db.table_exists(...)` → `True`).
4. **End-to-end simulation, Fund Sanction path** (real dev-DB document, no real Kafka messages touched):
   - Called `record_publish_state('Fund Sanction', <doc>, TOPIC_SANCTION, 'Draft', <current state>)` → confirmed a `PUBLISHED` `Kafka Publish State Log` row appeared.
   - Fed a hand-built raw DLQ message (matching the real shape from §2.1) through `SanctionDlqConsumerHandler.handle()`.
   - Confirmed: `workflow_state` reverted to `'Draft'`, a `Kafka Event DLQ Log` row was written with `reverted=1`, and the state-log row flipped to `DLQ_REVERTED`.
   - Restored the document's original `workflow_state` and deleted the test log rows.
5. **End-to-end simulation, Account Head Commit path** (real `Kafka Commit Staging` row, `Recruitment Adhoc Contractual` reference):
   - Fed a hand-built raw DLQ message through `CommitDlqConsumerHandler.handle()`.
   - Confirmed: staging row flipped `PUBLISHED` → `FAILED` with the expected `error_message`, and a `Kafka Event DLQ Log` row was written.
   - Restored the staging row to `PUBLISHED` and deleted the test log row.
6. **Wiring check**: confirmed every topic in `ALL_CONSUMER_TOPICS` has a registered entry in `TOPIC_HANDLERS` (8 topics, 8 handlers, zero gaps), and that `NEW_DLQ_CONSUMER_TOPICS` contains exactly the 5 new DLQ topics.

No real Kafka topics, consumer groups, or offsets were touched at any point — all peeking was read-only (`enable_auto_commit=False`, no committed offsets), and all document mutations happened only against hand-built synthetic messages in the dev DB, with cleanup after each test.

## 7a. Addendum: a deploy-timing race during rollout (2026-08-14, ~12:03)

The dev server this was built against (`bench serve`) auto-reloads on every
file save. The edits landed in this order: `kafka/config.py` →
`kafka/consumer/handler.py` → `kafka/consumer/manager.py` → the 9 doctype
call sites. The live process reloaded partway through — after `config.py`/
`handler.py` had already registered the 5 new DLQ topics, but *before*
`manager.py`'s `seek_to_end()` backlog-skip fix (§4.6) landed. In that
window, a real request triggered `ensure_consumer_running()`, and the
consumer replayed the full pre-existing backlog instead of skipping it
(counts matched exactly: 2 fund-sanction, 8 fund-received, 1 deposit-slip,
4 account-head-commit).

**Confirmed actual impact**, via the Error Log:

- Fund Sanction / Fund Received / Deposit Slip (11 messages total): every
  one hit `find_publish_state_log()` querying the not-yet-created
  `Kafka Publish State Log` doctype, raised, and was caught by the outer
  `except` before any `revert_workflow_state()` call was ever reached. **No
  real document's `workflow_state` was touched.**
- Account Head Commit (4 messages): 3 resolved to real `Kafka Commit
  Staging` rows and were correctly flipped `PUBLISHED` → `FAILED`
  (`Miscellaneous Commit` `20260806MiSCoM002445` / `20260806MiSCoM002490`,
  `Indent Cum Sanction Sheet` `2026080610002443`) — metadata-only, per
  design; the business documents themselves were never touched. The
  `log_dlq_event()` call right after failed for the same missing-doctype
  reason, so those 3 reverts had no matching `Kafka Event DLQ Log` row.

The bug is closed — `manager.py`'s fix is live, so any future restart
correctly seeks to end for `NEW_DLQ_CONSUMER_TOPICS`. The only residual gap
(3 missing audit rows) was backfilled from the staging rows'
`error_message` + the Error Log, marked `raw_payload: {"backfilled": true,
...}` so they're honestly distinguishable from a normally-captured DLQ
event.

**Lesson for next time**: on a server with file-watching auto-reload, land
consumer-registration changes (`config.py` + `handler.py`) and the
corresponding safety behavior (`manager.py`'s backlog handling) in the
same atomic edit/commit, not sequential ones — or disable auto-reload
during the rollout window.

## 7. Known follow-ups (not done here)

- `account-head-commit-batch-events-dlq` / `account-head-payment-batch-events-dlq` / `loan-settlement-events*` have no consumer — pick this up if they ever see real traffic.
- The 18 pre-existing backlog messages across the 5 DLQ topics (as of 2026-08-14) were deliberately left unprocessed per the user's decision (§3) — someone should still review them manually if the underlying documents need correcting.
- Reverting `workflow_state` on the ~9 doctypes that feed `Kafka Commit Staging` would need a per-doctype "previous state" capture design of its own before it could be done safely.

## 8. Admin UI: `/kafka_dlq_control`

A dedicated page (`apps/frappe/frappe/www/kafka_dlq_control.html`, same
`www`-page pattern as `kafka_control.html`, `pr_lookup.html`, etc. — no `.py`
controller needed, all data loaded client-side) covers the four things
asked for:

- **Check** — `get_dlq_topic_stats()` in the new `kafka/dlq_control_api.py`: a
  live, read-only peek at every DLQ topic's real backlog count directly from
  the broker (same technique as the §2.1 investigation — no group_id, no
  committed offsets). Includes the batch/loan-settlement topics that have no
  consumer yet, so a growing backlog there is visible before anyone builds
  one.
- **View** — four tabs backed by `list_event_dlq_logs`, `list_publish_state_logs`,
  `list_payment_dlq_logs`, `list_failed_commit_staging`. Each row's raw
  payload is viewable in a modal.
- **Manage** — `retry_commit_staging(staging_name)` re-publishes one FAILED
  `Kafka Commit Staging` row through the same `manually_publish_staged_commit`
  path `commitPayment.py` already exposes. Requires System Manager.
- **Clear** — `clear_dlq_logs(doctype, filters)` deletes rows from
  `CLEARABLE_DOCTYPES` (`Kafka Event DLQ Log`, `Kafka Publish State Log`,
  `Kafka Payment DLQ Log`) only. It cannot delete anything else, and it never
  touches the Kafka broker — there is deliberately no "purge the topic"
  button anywhere on this page. Requires System Manager.

Linked from `kafka_control.html` two ways: a Quick Links sidebar entry, and a
dedicated "DLQ Management" card in the Kafka section with an "Open DLQ
Management" button.
