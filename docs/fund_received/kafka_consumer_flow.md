  # Fund Received Consumer — Flow

  Documents how an `accounts-fundreceived-update` Kafka message ends up as an
  update on a **Fund Received** document. Covers the live/wired code path only
  (there are older, unwired duplicate implementations in this app — see
  [Note on legacy files](#note-on-legacy-files)).

  ## 1. How the consumer thread stays alive

  There is no dedicated worker process. Instead:

  - `hooks.py` registers `kafka.consumer_service.ensure_consumer_running` as a
    `before_request` hook — it runs on **every HTTP request** handled by any
    Gunicorn worker.
  - `ensure_consumer_running()` checks a Redis heartbeat key
    (`kafka_consumer_heartbeat`, 15s TTL). If a heartbeat is fresh, some worker
    already has the consumer thread running and this call is a no-op.
  - If the heartbeat is stale (or missing) and the consumer wasn't manually
    stopped from the Control Center, it starts `KafkaConsumerThread`
    (`consumer/manager.py: start_consumer_loop`), subject to a 60s cooldown per
    worker process so a crashing consumer doesn't get restarted on every
    request.
  - The running loop writes its own heartbeat to Redis every 5s, so only one
    worker ends up actively polling Kafka at a time.

  ## 2. Consumer loop → topic routing

  `consumer/manager.py: start_consumer_loop()`:

  1. Creates a `KafkaConsumer` with **manual partition assignment** (no
    `group_id`, `seek_to_beginning()` on start) across all
    `ALL_CONSUMER_TOPICS` (`config.py`):
    - `accounts-fundreceived-update`
    - `accounts-depositslip-update`
    - `account-head-payment-events-dlq`
  2. Polls every ~1s, and for every message calls
    `process_message_with_context(topic, value, partition, offset)`.
  3. That wrapper ensures a live Frappe site/DB connection, then delegates to
    `consumer/handler.py: process_message(topic, message)`.
  4. `process_message` looks up `TOPIC_HANDLERS[topic]` and dispatches. For
    `accounts-fundreceived-update` that's
    `fund_received.handle_fund_received_update`.

  ## 3. Fund Received message flow

  ```
  Kafka message
    │  { schemaVersion, eventType, timestamp, data: {...} }
    ▼
  FundReceivedConsumerHandler.handle(message)          consumer.py
    │
    ├─ 1. log RECEIVED
    ├─ 2. dto = FundReceivedUpdateDTO.from_kafka_message(data)   dto.py
    ├─ 3. doc_name = FundReceivedConsumerMapper.find_document(dto)  mapper.py
    │       not found → log SKIPPED, return True (offset still commits)
    ├─ 4. FundReceivedConsumerMapper.apply_updates(doc_name, dto)
    │       failure → log FAILED, return False (message re-processed)
    ├─ 5. frappe.db.commit()
    ├─ 6. if dto.fundBudgetBreakupList: update_budget_breakup(...)
    ├─ 7. if dto.transactionDetailsList: update_transaction_details(...)
    ├─ 8. frappe.db.commit()
    └─ 9. log SUCCESS, return True
  ```

  ### 3.1 Parsing — `FundReceivedUpdateDTO.from_kafka_message`

  Turns the raw `data` dict into a typed DTO:

  | Kafka field | DTO field |
  |---|---|
  | `fundReceivedRefNumber` | `fundReceivedRefNumber` |
  | `fundReceivedRefNumberFap` | `fundReceivedRefNumberFap` |
  | `sanctionLetterNo` | `sanctionLetterNo` |
  | `projectNumber` | `projectNumber` |
  | `amountReceived` | `amountReceived` |
  | `iitgAccountNumber` | `iitgAccountNumber` |
  | `depositSlipStatus` / `fundReceivedStatus` | pass-through |
  | `fundBudgetBreakupList[]` | list of `FundBudgetBreakupUpdateDTO` |
  | `transactionDetailsList[]` | list of `TransactionDetailsUpdateDTO` |

  `transactionReceivedDate` is normalized: Kafka may send it as a string or as
  a `[year, month, day]` array — both are coerced to `YYYY-MM-DD`.

  ### 3.2 Finding the target document — `FundReceivedConsumerMapper.find_document`

  Tries, in order, and stops at the first hit:

  1. **`fundReceivedRefNumberFap`** — used directly as the `Fund Received`
    document name.
  2. **`fundReceivedRefNumber`** (stringified) — same, as a fallback name.
  3. **`sanctionLetterNo` + `projectNumber`** — `projectNumber` is first
    resolved to a `Project Registration` docname (via its `project_no`
    field), then used to filter `Fund Received` by `prjreg_title` (+
    `sanctioned_letter_no` if that column exists).

  If nothing matches, the document is treated as **not yet created** — this is
  logged as `SKIPPED` and the handler returns `True` so the Kafka offset still
  commits (not found ≠ processing error).

  ### 3.3 Applying the update — `FundReceivedConsumerMapper.apply_updates`

  All writes are direct `frappe.db.set_value` / raw SQL (bypasses document
  controller validation, so submitted docs can still be updated), gated by
  `frappe.db.has_column` so it's safe if a field doesn't exist in a given
  site's schema:

  | DTO field | Fund Received field | Notes |
  |---|---|---|
  | `sanctionLetterNo` | `sanctioned_letter_no` | direct |
  | `projectNumber` | `prjreg_title` | **Link field** — only written if `get_project_registration_name()` resolves a real `Project Registration` docname; otherwise skipped (never writes the raw project number, which would corrupt the link) |
  | `amountReceived` | `fund_received_amt` | direct |
  | `iitgAccountNumber` | `bank_account` | direct |
  | `fundReceivedStatus` | `workflow_state` | see below — forward-only |
  | `fundReceivedRefNumber` | `fund_received_ref_number` | cast to `int`, falls back to raw value on failure |

  **Workflow state transition (forward-only):**

  `map_status()` translates the Kafka status string:
  - `APPROVED` → `Pending Misc. Staff Approval(Deposit Slip Pending)`
  - `PENDING_APPROVAL` → `PENDING_APPROVAL` (exact Frappe workflow state name)
  - anything else → `.title()`-cased as-is

  States are ranked by `_STATE_PRIORITY` (Draft=0 → ... → Fund Received=6).
  The update is applied as a **single atomic conditional SQL `UPDATE`**:

  ```sql
  UPDATE `tabFund Received`
  SET workflow_state = %s, modified = NOW()
  WHERE name = %s AND workflow_state IN (<all states with priority <= target>)
  ```

  This does the "only move forward" check and the write in one statement,
  avoiding a read-then-write race: since MariaDB MVCC lets a `SELECT` see a
  stale snapshot while another transaction has already advanced the row, a
  plain Python `if current < new: set_value(...)` could silently stomp a state
  change made by a concurrent workflow action. If no rows are affected
  (current state already equal/ahead), it's logged as a skipped backward
  transition.

  ### 3.4 Child tables — replace-in-place

  Both child-table updates use the same pattern: **delete all existing rows
  for this parent, then re-insert everything from the message** (not a diff/
  merge):

  - `update_budget_breakup` → doctype `Project Received Budget`, parent field
    `received_amt_breakup`. Maps `accountHeadId` (or `accountHead`) →
    `account_head`, `amount` → `amount_received`, `remarks` → `remarks`.
  - `update_transaction_details` → doctype `Project Fund Transaction`, parent
    field `fund_transactions`. Maps `uniqueTransactionNumber` →
    `transaction_number`, normalized date → `transaction_date`,
    `transactionAmount` → `amount`.

  Both use `frappe.new_doc(...).db_insert()` (raw insert, no validation) inside
  the same DB transaction, committed once at the end of the handler.

  ### 3.5 Error handling

  - Any exception during `apply_updates`, `update_budget_breakup`, or
    `update_transaction_details` is caught, logged via `frappe.log_error`, and
    reported as a per-step failure — the handler still tries the remaining
    steps (child table failures are logged as `WARNING`, not fatal).
  - An exception anywhere in `FundReceivedConsumerHandler.handle` itself is
    caught at the top level, logged, and the handler returns `False` — the
    Kafka offset is not advanced for that message so it will be retried on
    next poll (offsets commit per-batch in `manager.py`, after
    `process_message_with_context` runs for every message in the batch).

  ## Sequence diagram

  ```mermaid
  sequenceDiagram
      participant HTTP as Any HTTP request
      participant Hook as before_request hook
      participant Loop as KafkaConsumerThread
      participant Handler as process_message
      participant FR as FundReceivedConsumerHandler
      participant Mapper as FundReceivedConsumerMapper
      participant DB as MariaDB (Fund Received)

      HTTP->>Hook: ensure_consumer_running()
      Hook->>Loop: start (if heartbeat stale)
      loop poll every ~1s
          Loop->>Loop: consumer.poll()
          Loop->>Handler: process_message(topic, msg)
          Handler->>FR: handle_fund_received_update(msg)
          FR->>FR: DTO.from_kafka_message(data)
          FR->>Mapper: find_document(dto)
          Mapper-->>FR: doc_name or None
          alt not found
              FR-->>Loop: True (SKIPPED, offset commits)
          else found
              FR->>Mapper: apply_updates(doc_name, dto)
              Mapper->>DB: set_value(...) / conditional UPDATE workflow_state
              FR->>DB: commit()
              FR->>Mapper: update_budget_breakup(...)
              FR->>Mapper: update_transaction_details(...)
              Mapper->>DB: delete + re-insert child rows
              FR->>DB: commit()
              FR-->>Loop: True (SUCCESS)
          end
      end
  ```

  ## Note on legacy files

  This app directory also contains older/duplicate implementations that are
  **not** referenced by `hooks.py` and appear to be superseded by the module
  documented above:

  - `rndopsapp/rndopsapp/kafka_consumer.py` — mostly commented-out, with an
    active duplicate of the same logic at the bottom of the file.
  - `rndopsapp/rndopsapp/kafka/consumer_handler.py` — an alternate
    group-based (`group_id`-committing) consumer implementation.
  - `rndopsapp/rndopsapp/consume_fund_received.py` — a standalone debug script
    (`if __name__ == "__main__"`) for manually tailing the raw
    `fund-received-events` producer topic.

  Only `kafka/consumer_service.py` → `kafka/consumer/manager.py` →
  `kafka/consumer/handler.py` → `kafka/consumer/fund_received/*` is wired into
  the running app via `hooks.py`.
