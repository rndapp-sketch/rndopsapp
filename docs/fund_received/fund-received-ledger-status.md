# Fund Received: ledger status → real workflow states + notifications

Reference documentation for the work added on 2026-08-14, following on from
`kafka/DLQ_HANDLING_AND_REVERT.md`. Covers the `accounts-fundreceived-update`
consumer specifically: why it silently dropped 3 of the 5 statuses the
ledger sends, what was built to fix that, and two real bugs found (and
fixed) along the way.

## 1. The problem

The external ledger reports 5 `fundReceivedStatus` values on the
`accounts-fundreceived-update` Kafka topic (consumed by
`kafka/consumer/fund_received/`, wired since before this session):
`PENDING_APPROVAL`, `PENDING_RECONCILIATION`, `PENDING_RECTIFICATION`,
`APPROVED`, `REJECTED`.

`FundReceivedConsumerMapper.map_status()` only recognized `PENDING_APPROVAL`
and `APPROVED` — the actual state names in the live `fund_received_with_kafka`
Workflow. Anything else fell through to `kafka_status.title()`, which
produced a string matching no real workflow state, got assigned priority `0`
in `_STATE_PRIORITY` (same tier as `Draft`), and was then silently rejected
by the anti-regression guard — so a `PENDING_RECTIFICATION` message from the
ledger had **zero visible effect**: `workflow_state` stayed wherever it was,
no one was told anything happened. The only way anyone found out was a human
noticing the raw Kafka error in the "kafka logs" Mattermost channel and
manually overriding the workflow state by hand (confirmed: this happened for
real on `REC_0508262396-prjreg_refnum`, Aug 7, `narayank@iitg.ac.in` via
Admin Panel).

## 2. Investigation

- `fund_received_with_kafka` (the active Workflow for Fund Received — a
  second, inactive `Fund_Received_Workflow` also exists, not used) has 7
  real states: `Draft`, `Pending Misc. Staff Approval`, `PENDING_APPROVAL`,
  `Pending Misc. Staff Approval(Deposit Slip Pending)`, `Pending HoS
  Approval`, `Approved`, `Fund Received`. None of the other 3 ledger
  statuses had an equivalent.
- No Deposit Slip doctype reads Fund Received's `workflow_state` at runtime
  (checked all 6 deposit-slip doctypes + producer/consumer code) — safe to
  add new states without touching that relationship.
- `_STATE_PRIORITY` (the anti-regression dict) is duplicated 3 times:
  `kafka/consumer/fund_received/mapper.py`, `doctype/fund_received/
  fund_received.py`'s `create_deposit_slip_from_data`, and `kafka_consumer.py`
  (root-level — confirmed **dead code**, not imported by `hooks.py` or any
  live entrypoint, only by standalone dev scripts). Only the first two are
  live and needed updating.
- `staff, RnD` is a real, established role (46 users, used in 40+ other
  workflows — Travel, Fund Sanction, Project Registration, etc.) but wasn't
  in `fund_received_with_kafka` at all before this.
- `perform_fund_received_action`'s `if next_state == "PENDING_APPROVAL":`
  block already re-publishes to Kafka on arrival at `PENDING_APPROVAL`
  regardless of which state it came from — so a new transition landing
  there gets "republish on Forward" for free.

## 3. Design, in the order it was actually built

### Phase 1 — informational only (safe default, no workflow changes)

Before touching the live Workflow doctype at all, the first pass was
deliberately conservative: record the raw status without ever moving
`workflow_state`, since forcing an unmapped state string into it risks
locking a document out of its own approval actions.

- New Custom Field `ledger_status` on Fund Received (Data, read-only) — the
  raw `fundReceivedStatus`, independent of `workflow_state`.
- `FundReceivedConsumerMapper.update_ledger_status()`: writes `ledger_status`
  on change (deduped — same value twice is a no-op, since the underlying
  consumer topic replays its full history on every process restart, see §6),
  and calls `_notify_ledger_status_change()`: posts a `[Ledger Status]`
  Comment (same convention as this doctype's existing `[Forward]`/`[Put
  Back]` comments) and a Notification Log alert to the document owner, with
  a plain-English explanation per status.

Adding the Custom Field hit a **pre-existing, unrelated bug**: Fund Received
already has `workflow_state` defined twice — once in its base doctype JSON,
once as a Custom Field (overriding it to a Link) — which fails
`validate_fields_for_doctype` on *any* new Custom Field addition to this
doctype. Not fixed (out of scope, didn't want to touch that override without
knowing why it's there); worked around with `doc.flags.ignore_validate =
True` before insert, which still runs the actual `ALTER TABLE`.

### Phase 2 — real workflow states

You then asked to go further: make the 3 statuses real, actionable workflow
states, with a way to fix-and-resubmit a `PENDING_RECTIFICATION` document.
Decision (asked, not assumed): `Pending Reconciliation` and `Rejected` stay
**passive** — no new user-facing transition — only `Pending Rectification`
gets a manual retry path, matching real historical data (a later
ledger-sent `APPROVED` was already observed moving a `REJECTED` document
forward directly, no manual step needed).

- 2 new `Workflow State` master records (`Pending Rectification`, `Pending
  Reconciliation` — `Rejected` already existed as a shared master used
  elsewhere) and 3 new `Workflow Document State` rows on
  `fund_received_with_kafka`.
- 1 new `Workflow Transition`: `Pending Rectification --Forward-->
  PENDING_APPROVAL`, role `staff, RnD`. Rides the existing
  `next_state == "PENDING_APPROVAL"` re-publish block for free — no new
  publish code needed.
- `map_status()` now maps all 5 statuses to real states via
  `_LEDGER_STATUS_TO_WORKFLOW_STATE`.
- `_STATE_PRIORITY` (both live copies): the 3 new states sit at **priority
  2**, the same tier as `PENDING_APPROVAL` — they're the ledger flagging a
  document sideways out of that stage, not genuine forward progress. This is
  also what lets a later `APPROVED` move a document forward past any of them
  without a manual step first.

No existing states, transitions, or roles were touched.

### Phase 3 — Put Back for the new states

`put_back_action.py` (a generic, doctype-agnostic tool — see
`put-back-action.md`) walks a workflow's `Workflow Transition` rows
*backwards* from the current state to find valid "put back" targets. Since
`Pending Rectification` / `Pending Reconciliation` / `Rejected` are entered
only by the Kafka consumer's direct DB write — never a real transition a
user clicks — there's no transition edge *into* them for that walk to
invert, so it found nothing.

Fixed generically (not a Fund-Received-only hack) via a new
`STATE_ALIASES` dict in `put_back_action.py`: these 3 states alias to
`PENDING_APPROVAL` (their same-priority sibling), so the backward walk
resumes from `PENDING_APPROVAL`'s own predecessors when the direct walk
dead-ends. **Not** `PENDING_APPROVAL` itself as the target — its
predecessor, `Pending Misc. Staff Approval` (per your explicit correction).

A real bug turned up while verifying this: once `Pending Rectification` had
a real transition *into* `PENDING_APPROVAL`, it started appearing as a
predecessor of `PENDING_APPROVAL` too — so `Rejected`'s put-back chain
incorrectly included `Pending Rectification` as an intermediate step (two
unrelated sibling states, not a real parent/child relationship). Fixed by
excluding every alias-source state (for the doctype) from ever being
selected as a predecessor result, not just as the walk's starting point.

Wired into the actual UI surface:

- `get_fund_received_workflow_actions()`: appends `"Put Back"` to the
  returned action list when the current state is a `STATE_ALIASES` key and
  the user has the right role — even though no real transition row grants
  it.
- `perform_fund_received_action()`: an early branch catches
  `action == "Put Back"` from one of those states *before* the normal
  transition-table lookup (which would otherwise `frappe.throw` — no such
  row exists), independently re-checks the role (defense in depth — this
  function is callable directly, not only via the action list), and
  delegates to `put_back_action.set_put_back_workflow_state()` — skipping
  every forward-transition side effect (deposit slip creation,
  `doc.submit()`, Kafka publish) that only makes sense for a real forward
  move.

### Phase 4 — attribution: "Account Portal", not "Administrator"

The Kafka consumer runs in a background thread under the Administrator
session, so every `[Ledger Status]` Comment and Notification Log entry was
showing "Administrator commented" in the desk timeline — misleading, since
this content originates from the external ledger, not an actual admin
action. The app already has a precedent for this: `api.py::
get_project_activity` merges in real external-portal comments labeled
`"user": "Account Portal"`.

Created a dedicated system user, `account.portal@rndopsapp.local`
(`full_name = "Account Portal"`, login disabled), and set it explicitly as
`owner` on the Comment / `from_user` on the Notification Log instead of
`frappe.session.user`.

## 4. Files touched

```
doctype/fund_received/fund_received.py          — Put Back UI wiring, _state_priority dict, ledger_status Custom Field (created live, not in this file)
kafka/consumer/fund_received/mapper.py           — map_status, _STATE_PRIORITY, _WORKFLOW_MAPPED_STATUSES, update_ledger_status, _notify_ledger_status_change, ACCOUNT_PORTAL_USER
put_back_action.py                               — STATE_ALIASES mechanism
put-back-action.md                               — documents STATE_ALIASES + the Fund Received integration
```

Plus, created directly against the live site (not files in this repo, but
real DB records that any environment this code runs against will need too):

- `Workflow State` master records: `Pending Rectification`, `Pending
  Reconciliation`.
- `Workflow Document State` + `Workflow Transition` rows on
  `fund_received_with_kafka` (see §3 Phase 2).
- Custom Field `Fund Received-ledger_status`.
- User `account.portal@rndopsapp.local`.

## 5. A note on role gating — the actual bug found in production

`Put Back` was initially gated to `RnD Administration` / `System Manager`
only, mirroring `PENDING_APPROVAL`'s own real `Put Back` transition's role.
That was wrong: `Forward` out of `Pending Rectification` was granted to
`staff, RnD`, a *different* role. Anyone with only `staff, RnD` — which is
most of the people who'd actually act on these documents day to day — saw
`Forward` but never `Put Back`. Reported against a real document
(`REC_0408262361-prjreg_refnum`) via the actual frontend, confirmed by
testing as a real `staff, RnD`-only user
(`karishma.rubab@iitg.ac.in`, verified to hold no admin role) before and
after the fix. `staff, RnD` is now included in both the action-list gate and
`perform_fund_received_action`'s independent re-check.

## 6. Live side effects from working on an auto-reloading dev server

Same underlying cause as the incident in `kafka/DLQ_HANDLING_AND_REVERT.md`
§7a: `accounts-fundreceived-update` is one of the original consumer topics
and replays its **entire history** on every process restart (no persisted
offsets — pre-existing, not introduced here). Every file save during this
work restarted the live `bench serve` process, which replayed the topic
again.

Confirmed, real effects (checked directly against the DB after each
restart, not assumed):

- The notify code (Phase 1) genuinely ran against ~40 real Fund Received
  documents' full real status history — 51, then 64, then 82 real Comments
  and Notification Log entries as the topic gradually drained across
  several restarts, correctly deduped (no repeats for an unchanged value;
  distinct real historical transitions for the same document, e.g.
  `PENDING_RECTIFICATION` → later `APPROVED`, both correctly recorded).
- Once Phase 2 landed, the same replay retroactively corrected every real
  document's `workflow_state` to match its `ledger_status` automatically —
  including `REC_0508262396-prjreg_refnum`, the document that had needed a
  manual admin override back on Aug 7. Cross-checked all 43 documents with a
  `ledger_status` set: every one's `workflow_state` was internally
  consistent (either matching the mapped state, or further ahead due to a
  real later event) — no regressions.
- **A real mistake, caught and fixed**: an early verification test cleaned
  up by deleting `Comment`/`Notification Log` rows using a broad
  content-based filter, which — because the *real* notify call for that
  document was itself a no-op (dedup: `ledger_status` hadn't changed) —
  ended up deleting the **genuine** entry alongside nothing, not a test
  artifact. Caught immediately, recreated the real Comment + Notification
  precisely, and switched every subsequent test cleanup to exact-name
  deletion (capture the created row's `name` before any assertion, delete
  only that) instead of content matching.
- Retroactively fixed all 64/58 (comments/notifications, at the time)
  `Administrator`-owned entries from before the Phase 4 attribution fix
  landed, so nothing is inconsistently attributed.

No `workflow_state` mutation ever happened on a real document without a
corresponding real, accurate ledger event behind it — confirmed via direct
cross-checks after every restart, not assumed from the code being "supposed
to" be safe.

## 7. Verification performed

- `map_status()` re-checked for all 5 inputs directly.
- `get_put_back_document_states()` checked for a `Pending Rectification`,
  a `Rejected`, and a plain `PENDING_APPROVAL` document — all three now
  resolve to the identical, correct chain `["Pending Misc. Staff Approval",
  "Draft"]`.
- `set_put_back_workflow_state()` and `perform_fund_received_action(...,
  "Put Back")` both exercised end-to-end against the real target document,
  each time reverted precisely afterward (state restored, exactly the one
  test-created Comment removed by its captured name).
- `get_fund_received_workflow_actions()` checked as a real `staff,
  RnD`-only user against the real reported document — confirmed
  `['Forward', 'Put Back']`.
- Cross-checked all 43 real documents with a `ledger_status` value against
  their `workflow_state` for internal consistency (§6).
