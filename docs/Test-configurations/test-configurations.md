# Test Environment Configuration

Tracks the config swapped in for running this app against the test environment, and exactly what changed in code so it can be reverted or re-applied. Branch: `pragati-bk_v0.02`.

## 1. Kafka

No code change — `rndopsapp/rndopsapp/kafka/config.py` already pointed at the test broker:

```
KAFKA_BOOTSTRAP_SERVERS = ['172.16.135.81:9095', '172.16.135.81:9096']
```

`172.16.135.81:8090` is **not** a broker/REST-proxy endpoint — it's the "UI for Apache Kafka" web dashboard (confirmed via `/actuator/health` → `{"status":"UP"}`, root page title "UI for Apache Kafka"). Useful for browsing topics/consumer groups in a browser, but not something the app's `kafka-python` client connects to.

Stale `172.16.134.81:9095/9096` references remain in standalone/admin scripts not on the app's runtime path (not updated): `test_kafka.py`, `test_kafka_consumer.py`, `test_kafka_dummy_data.py`, `force_recreate_topics.py`, `fix_remaining_topics.py`, `recreate_topics.py`, `update_partitions.py`.

## 2. Mattermost

Same server (`172.16.135.118:8065`), test channels created via the Mattermost API on team `RnDops-Team` (`kwiom3xihtdjuew8z8bjdd4noe`):

| Purpose | Channel name | Channel ID | Used in |
|---|---|---|---|
| Kafka producer success/error messages | `kafka_logs_test` | `1w6cq5uwpfrk5ga5ynhokx8g1y` | `rndopsapp/rndopsapp/kafka/utils.py` (`_MM_KAFKA_CHANNEL`, feeds `mm_notify()`) |
| Server-restart / consumer auto-start ping | `log_test` | `1nztudh15fr67x1txb7w6kd5yr` | `rndopsapp/rndopsapp/kafka/consumer_service.py` (`_notify_restart`) |

Previously pointed at the production channels `kafka-logs` (`yh7piky97iycjrdytia1hqy99a`) and `logs` (`ihmkbbfq9ibzugfpy9rncq5yke`) — restore those IDs to go back to prod.

Not touched: `_MM_SALARY_CHANNEL` in `commitPayment.py` (salary-payment exception notifications) still posts to its original channel.

## 3. Ledger API

`rndopsapp/static_config.py` → `ACCOUNT_PORTAL_BASE_URL`:

- Was: `http://172.16.134.81:18080`
- Now: `http://172.16.135.27:18083`

This base URL feeds every Account Portal / ledger endpoint (`sanction-details`, `commit-payment-transactions`, `account-head-payments`, `account-head-commit`, `projects`, `fund-received`, `account-heads`), including `commitPayment.LEDGER_API_BASE_URL` and the "Accounts service (ledger) base" used in `loan_settlement.py`.

Confirmed reachable (`18083` open, root returns `HTTP 403` — consistent with the IP-restriction behavior already anticipated in `commitPayment.py`'s `_dev_fallback()` comment).

## 4. Email sending — disabled

`rndopsapp/rndopsapp/email/email_config.py` (gitignored, not in version control):

```python
EMAIL_SENDING_ENABLED = False
```

Checked at the top of `send_email_with_password()` in `rndopsapp/rndopsapp/email/send_email.py`. When `False`, it skips the SMTP call, logs the skip via `frappe.logger("email")`, and returns `True` — so the Celery task in `celery_app.py` treats it as a successful send rather than retrying 5x or marking the "Email Send Logs" row `Failed`.

To resume sending, flip `EMAIL_SENDING_ENABLED = True` in `email_config.py`.

## 5. App host/IP

No change. `Procfile`'s gunicorn already binds `0.0.0.0:8000`, so the app is reachable at `172.17.1.46:8000` without any DNS hostname involved. No nginx config or DNS entry found in this bench.

## Keeping these test values out of git

`email_config.py` was already gitignored (holds real SMTP credentials). The other four files carry a mix of shared business logic and one test-only value each, so they couldn't just be gitignored outright without losing tracking for everything else in them. Instead they're marked `skip-worktree`, so git treats their current on-disk content as untouchable — `git status`/`git diff`/`git add -A`/`git commit -a` won't see them, and `git pull`/`checkout` won't overwrite them:

```
rndopsapp/static_config.py
rndopsapp/rndopsapp/kafka/config.py
rndopsapp/rndopsapp/kafka/consumer_service.py
rndopsapp/rndopsapp/kafka/utils.py
```

This is local to this clone only (stored in `.git/index`, never pushed) — since the test values are never committed, they never reach the remote, so `live` (or anyone else pulling the remote) is unaffected by construction.

**Caveat:** while a file is `skip-worktree`, git also ignores *any other* future edit to that file, not just the line that was swapped — so a genuine upstream change to one of these four files won't merge in here until the flag is lifted. To restore normal tracking on a file (e.g. before making a real code change to it, or to pull in upstream updates):

```bash
git update-index --no-skip-worktree <path>
```

Then swap the test value back afterward if the app still needs to run against test.
