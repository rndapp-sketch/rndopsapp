# Frappe "running but not opening" — root cause & fix

**Symptom:** `bench start` processes are all alive (`ps` shows them running), but the site
(e.g. `http://172.16.131.206:8000/app/`) hangs or times out in the browser. Happens
intermittently, not every time.

## Root cause

The `rndopsapp` app runs its Kafka consumer **inside the same OS process that serves
HTTP requests**, instead of as an independent worker process.

1. `hooks.py` (originally at lines 217-220, before this fix — see
   [`KAFKA_CONSUMER_MULTIWORKER_FIX.md`](KAFKA_CONSUMER_MULTIWORKER_FIX.md) for
   why it was added in the first place) registered a `before_request` hook:
   ```python
   before_request = [
       "rndopsapp.rndopsapp.kafka.consumer_service.ensure_consumer_running",
       ...
   ]
   ```
   This ran **on every single HTTP request** to the site.

2. `consumer_service.ensure_consumer_running()`
   (`rndopsapp/rndopsapp/kafka/consumer_service.py`) checks a Redis heartbeat;
   if no consumer is alive anywhere, it calls `start_kafka_consumer()`, which
   spawns a **daemon thread** running `start_consumer_loop()`
   (`rndopsapp/rndopsapp/kafka/consumer/manager.py`) — inside that same
   `bench serve` worker process.

3. That consumer thread then runs continuously in the background of the web
   process: polling Kafka, fetching docs, and saving them (`Fund Received`,
   `Deposit Slip`, etc.) — all while sharing the process with the threads that
   are trying to answer browser requests.

4. `bench start` runs the dev server (Werkzeug, `frappe/app.py:508`) as a single
   **threaded but single-process** server. All threads in that process share one
   Python GIL and the same DB/redis connections. When the consumer thread is busy
   (a burst of Kafka messages, a slow doc save, a DB lock), it starves the
   HTTP-handling threads of GIL time and connections — the site looks "stuck"
   even though the process is technically alive and not crashed.

This is exactly the "running but not opening" pattern: no process died, no error
in the logs, it's just contention inside one process.

### Why it's easy to misdiagnose as a hung process

`ps -o pcpu` reports **cumulative** CPU% over the process's lifetime, not
instantaneous load. A worker that's been legitimately busy (real user traffic +
the inline Kafka consumer processing a backlog) can sit at 80-90% CPU for many
minutes while working completely normally. **Do not kill a `bench serve` worker
based on high CPU% alone** — check whether it's still returning responses first
(see instant fix, step 1). Killing the wrong process brings down the *entire*
`bench start` process group (honcho stops all Procfile entries — redis, socketio,
worker, scheduler — the moment `web.1` exits), not just the web server.

## Instant fix (when it happens again)

Do these in order — stop as soon as the site responds.

1. **Check if it's actually dead or just slow**, before touching anything:
   ```bash
   curl -sS -o /dev/null -w "HTTP %{http_code} time=%{time_total}s\n" --max-time 20 http://localhost:8000/app/
   ```
   If you get an HTTP code back (even a slow one), it's contention, not a crash —
   just wait ~30-60s for the Kafka burst to drain. Don't kill anything.

2. If it truly never responds (curl times out completely, `HTTP 000`), check
   what's actually listening:
   ```bash
   ss -tlnp | grep 8000
   ps aux | grep "frappe serve" | grep -v grep
   ```

3. If nothing is listening on 8000, or the whole stack is down, restart from the
   tmux session where `bench start` normally runs (session name: `frappe`):
   ```bash
   tmux attach -t frappe        # or: tmux send-keys -t frappe "bench start" Enter
   ```
   Do **not** `kill -9` an individual `frappe serve` PID as a first move — it
   takes the whole stack down with it (see root cause above). If you must kill
   something, kill the top-level `honcho start` PID and then restart `bench
   start` cleanly, so you get one clean shutdown instead of a partial one.

4. After restart, re-run the curl check from step 1 until it returns 200/301
   consistently.

## Real fix (removes the problem, not just the symptom)

Move the Kafka consumer out of the web-serving process entirely. Three ways to
do that:

- **Option A — dedicated background worker (implemented below):** run the
  consumer loop as its own Procfile process, matching the pattern the existing
  `worker`/`schedule` entries already use.

- **Option B — supervisor/systemd unit:** same idea, but managed outside
  `bench start`/honcho, so it survives independently of the dev server
  restarting (useful once you move off `bench start` to production mode).
  Not implemented yet — natural next step once this moves off `bench start`.

- **Option C (partial, lower effort):** keep `before_request` but make it a
  no-op check that just reports status without ever calling
  `start_kafka_consumer()` from the request path — start the consumer once at
  process boot (`app_init`/`on_boot`) instead of on every request. This still
  leaves the consumer thread sharing the process, so it reduces but does not
  eliminate GIL contention. Not recommended as a final fix, not implemented.

### Option A — IMPLEMENTED

Moved the Kafka consumer out of the web-serving process entirely, as its own
Procfile process:

1. **`Procfile`** — added a dedicated entry that runs the *actual* live consumer
   loop (`rndopsapp.rndopsapp.kafka.consumer.manager.start_consumer_loop`) via
   `bench execute`, which resolves the site context the same safe way `bench
   worker`/`bench schedule` already do:
   ```
   kafka_consumer: bench execute rndopsapp.rndopsapp.kafka.consumer.manager.start_consumer_loop 1>> logs/kafka_consumer.log 2>> logs/kafka_consumer.error.log
   ```
   Note: `run_consumer_foreground.py` was **not** reused — it imports from a
   different, legacy module (`rndopsapp.rndopsapp.kafka_consumer`), not the
   `kafka.consumer.manager` module that `hooks.py` actually wires up and that
   was processing the live Fund Received / DBT traffic. Running the wrong
   module would have started a second, divergent consumer instead of moving
   the real one.

2. **`hooks.py`** — removed `ensure_consumer_running` from `before_request`.
   The consumer no longer needs to be "kept alive" by request traffic because
   it runs as its own supervised process now.

This decouples "is the Kafka consumer alive" from "is a browser tab making a
request right now," and stops the consumer's DB/CPU work from ever competing
with the web server's GIL.

**This needs a `bench start` restart to take effect** (Procfile is only read
by honcho at startup — see instant-fix step 3). It hasn't been restarted yet
as part of this change, to avoid another disruption to live users; do it at a
low-traffic moment.

**Known side effect — read before relying on it:** the Kafka Consumer Control
Center's Start/Stop buttons
(`consumer_service.start_kafka_consumer` / `stop_kafka_consumer`) operate on an
in-process `threading.Event` and thread handle. Once the consumer runs in its
own `kafka_consumer` process, those RPCs — fired from the `web.1` process —
can no longer actually start/stop it; `web.1` no longer holds the real thread
reference. Clicking "Stop" in the UI will report success but have no effect on
the real consumer. To actually stop/start it now, manage the `kafka_consumer`
Procfile process directly (e.g. `honcho`/`tmux` pane, or a process manager once
this moves off `bench start`). If the Control Center UI is actively used
day-to-day, this needs a follow-up (e.g. have those RPCs signal the separate
process via Redis instead of an in-memory `Event`) rather than being left
silently broken.

Option B — running it under supervisor/systemd instead of inside `bench
start`/honcho — is the natural next step once this moves off the dev server to
a production setup; not done here since the rest of the stack still runs under
`bench start`.

## Changelog — what was actually changed

Two files edited, nothing restarted yet, no `git` in this repo so tracked here
instead.

### 1. `Procfile`

Added a new process entry after the existing `worker` line:

```diff
 worker:  bench worker 1>> logs/worker.log 2>> logs/worker.error.log

+kafka_consumer: bench execute rndopsapp.rndopsapp.kafka.consumer.manager.start_consumer_loop 1>> logs/kafka_consumer.log 2>> logs/kafka_consumer.error.log
```

Runs the real consumer loop (`kafka.consumer.manager.start_consumer_loop`) as
its own honcho-managed process, logging to `logs/kafka_consumer.log` /
`logs/kafka_consumer.error.log`, separate from `web.log`.

### 2. `apps/rndopsapp/rndopsapp/hooks.py`

Removed the line that started the consumer from inside request handling:

```diff
 before_request = [
-	"rndopsapp.rndopsapp.kafka.consumer_service.ensure_consumer_running",
 	"rndopsapp.rndopsapp.doctype.project_verification.project_verification.restrict_verification_staff_routes",
 ]
```

### Status

| Item | State |
|---|---|
| Code changes | Done |
| `bench start` restarted to pick up new Procfile entry | **Not done yet** — holding until a low-traffic moment, since a restart briefly drops the site for everyone currently on it |
| Kafka Consumer Control Center Start/Stop buttons | Will silently stop working once the restart happens (see side effect above) — not yet fixed, needs a decision on whether it's worth a follow-up |

### To actually activate this fix

```bash
tmux attach -t frappe
# Ctrl+C to stop the current bench start
bench start
```
Then confirm the new process came up:
```bash
tmux capture-pane -t frappe -p -S -40 | grep kafka_consumer
```
should show a `kafka_consumer.1 started (pid=...)` line alongside the other
Procfile entries.

## What NOT to do

- Don't `kill -9` a `frappe serve` PID to "unstick" the site — it's a child of
  the `honcho`/reloader process group; killing it tears down redis, socketio,
  worker, and scheduler with it (all get SIGTERM the moment `web.1` exits).
- Don't judge a hang purely from `ps` CPU% — confirm with a `curl` request first.
