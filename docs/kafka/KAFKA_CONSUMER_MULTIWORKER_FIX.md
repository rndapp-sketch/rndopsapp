# Kafka Consumer — Multi-Worker & Auto-Start/Stop Fix

## Problem

The Command and Control Center showed the consumer status cycling between **STARTED** and **STOPPED** unexpectedly:

- Clicking **Stop Consumer** would stop it, but within ~60 seconds it auto-restarted.
- Refreshing the page would show **STOPPED** even when the consumer was running.
- Multiple Gunicorn workers would each spin up their own consumer thread, causing messages to be processed multiple times (once per worker).

---

## Root Cause

### 1 — `ensure_consumer_running()` fires on every HTTP request

`consumer_service.py` registers `ensure_consumer_running` as a Frappe `before_request` hook:

```python
# hooks.py
before_request = [
    "rndopsapp.rndopsapp.kafka.consumer_service.ensure_consumer_running",
]
```

Every page load, API call, or background fetch triggered this function. If the consumer thread was dead (including after an intentional Stop), it would auto-restart after the 60-second cooldown — making the Stop button useless.

### 2 — Consumer state stored per Gunicorn worker process

`_consumer_thread` is a module-level variable in `manager.py`. Gunicorn forks N worker processes; each has its own copy of this variable.

- Worker A starts the consumer → `_consumer_thread` alive in Worker A's memory.
- Page refresh hits Worker B → Worker B's `_consumer_thread` is `None` → status shows **STOPPED** → `ensure_consumer_running()` starts another thread in Worker B.
- Result: N workers each running their own Kafka consumer, processing every message N times.

---

## Fix

Two changes were made:

### Fix 1 — Redis "manually stopped" flag

**File:** `rndopsapp/rndopsapp/kafka/consumer_service.py`

When the user clicks **Stop Consumer**, a Redis key `kafka_consumer_manually_stopped` is set to `True`. `ensure_consumer_running()` checks this key before auto-restarting. When the user clicks **Start Consumer**, the key is cleared.

```python
_MANUALLY_STOPPED_KEY = "kafka_consumer_manually_stopped"

def _set_manually_stopped(value: bool):
    frappe.cache().set_value(_MANUALLY_STOPPED_KEY, value)

def _is_manually_stopped() -> bool:
    return bool(frappe.cache().get_value(_MANUALLY_STOPPED_KEY))

@frappe.whitelist()
def start_kafka_consumer(**kwargs):
    _set_manually_stopped(False)          # clear the stop flag
    from .consumer.manager import start_kafka_consumer as _fn
    return _fn()

@frappe.whitelist()
def stop_kafka_consumer(**kwargs):
    _set_manually_stopped(True)           # set the stop flag
    from .consumer.manager import stop_kafka_consumer as _fn
    return _fn()
```

`ensure_consumer_running()` now checks this before restarting:

```python
if _is_manually_stopped():
    return   # user explicitly stopped it — do not auto-restart
```

The Redis key persists across `bench restart`, so if the consumer was stopped before a server restart, it stays stopped until the user explicitly starts it again.

### Fix 2 — Redis heartbeat shared across all workers

**File:** `rndopsapp/rndopsapp/kafka/consumer/manager.py`

The consumer loop now writes a heartbeat to Redis every 5 seconds with a 15-second TTL. All workers read this shared heartbeat for status checks and before deciding to start a new thread.

```python
_HEARTBEAT_KEY = "kafka_consumer_heartbeat"
_HEARTBEAT_TTL = 15        # seconds — if no heartbeat for this long, consumer is dead
_HEARTBEAT_INTERVAL = 5    # seconds between heartbeats from the loop

def _write_heartbeat():
    frappe.cache().set_value(_HEARTBEAT_KEY, time.time(), expires_in_sec=_HEARTBEAT_TTL)

def _clear_heartbeat():
    frappe.cache().delete_value(_HEARTBEAT_KEY)

def is_consumer_running_globally() -> bool:
    """True if any worker's consumer thread is alive — safe to call from any worker."""
    try:
        return bool(frappe.cache().get_value(_HEARTBEAT_KEY))
    except Exception:
        return _consumer_thread is not None and _consumer_thread.is_alive()
```

Consumer loop (inside `start_consumer_loop()`):

```python
last_heartbeat = 0.0
while not _stop_consumer.is_set():
    now = time.monotonic()
    if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
        _write_heartbeat()
        last_heartbeat = now
    ...

# On exit:
finally:
    _clear_heartbeat()   # immediately marks consumer as stopped in Redis
    close_consumer()
```

`get_kafka_consumer_status()` now reads from Redis:

```python
return {
    "running": is_consumer_running_globally(),   # Redis — consistent across all workers
    ...
}
```

`ensure_consumer_running()` uses the Redis heartbeat as its fast-path check:

```python
if is_consumer_running_globally():
    return   # consumer alive in some worker — this worker should not start another one
```

---

## Behaviour After Fix

| Scenario | Before | After |
|---|---|---|
| Click Stop | Stops for ~60 s, then auto-restarts | Stays stopped until user clicks Start |
| Page refresh | Status shows STOPPED (different worker) | Status reads Redis heartbeat — consistent |
| `bench restart` | All workers auto-start new threads | Workers check heartbeat; only one starts |
| Consumer crashes | Auto-restarts after 60 s cooldown | Auto-restarts after 60 s (heartbeat expired) |
| Multiple workers | Each starts its own consumer thread | Heartbeat prevents duplicate threads |

---

## Files Changed

| File | Change |
|---|---|
| `rndopsapp/rndopsapp/kafka/consumer_service.py` | Added `_MANUALLY_STOPPED_KEY` helpers; `start/stop_kafka_consumer` set/clear the flag; `ensure_consumer_running` checks heartbeat first, then manually-stopped flag |
| `rndopsapp/rndopsapp/kafka/consumer/manager.py` | Added `_HEARTBEAT_KEY`, `_write_heartbeat()`, `_clear_heartbeat()`, `is_consumer_running_globally()`; consumer loop writes heartbeat every 5 s and clears on exit; `get_kafka_consumer_status()` uses `is_consumer_running_globally()` |

---

## Deployment

```bash
bench restart
```

No migration required — uses only Redis (no new DocType fields or DB columns).

---

## Verification

After `bench restart`:

1. Open Command and Control Center.
2. Click **Start Consumer** → status shows **STARTED**.
3. Refresh the page → status should still show **STARTED** (reads from Redis heartbeat).
4. Click **Stop Consumer** → status shows **STOPPED**.
5. Refresh the page repeatedly → status stays **STOPPED** (Redis flag prevents auto-restart).
6. Click **Start Consumer** again → auto-restart resumes normally after this point.

To inspect Redis keys directly:

```bash
bench --site prornd.local execute frappe.cache.get_value --kwargs '{"key": "kafka_consumer_heartbeat"}'
bench --site prornd.local execute frappe.cache.get_value --kwargs '{"key": "kafka_consumer_manually_stopped"}'
```
