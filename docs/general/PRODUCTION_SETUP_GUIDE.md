# Moving `prornd` (Frappe bench) to Production Mode

## Why

Currently the site is served by `bench start`, which runs `bench serve --port 8000` —
a single Werkzeug **dev** process. It's threaded, but Python's GIL means CPU-bound
work still serializes onto one core. Under real multi-user load (confirmed: users
like dornd@iitg.ac.in, rndadmin@iitg.ac.in, mks@iitg.ac.in, hocenv@iitg.ac.in,
ssbag75@iitg.ac.in were active in the logs) this process sits pinned at ~95-100%
CPU, and other requests queue behind whatever it's currently doing — this is the
"sometimes the app just doesn't load" symptom.

Production mode replaces that with **gunicorn running multiple worker processes**
(true multi-core parallelism) managed by **supervisor** (auto-restart on crash),
fronted by an **nginx vhost** that serves static assets/files directly and proxies
dynamic requests to gunicorn.

Machine has **32 cores**. `sites/common_site_config.json` already has
`"gunicorn_workers": 65`, which is Frappe's own formula (`2 × cores + 1`) — it's
just unused right now because `bench start` never calls gunicorn. No change needed
there.

---

## 0. Current-state notes (read before touching anything)

- Bench root: `/home/prornd/frappe-dev/prornd`, user `prornd`, site `prornd.local`.
- Machine IP: `172.16.131.206` (not `172.126.131.206` — that was a typo that caused
  a separate, earlier "can't reach the app at all" issue).
- **Port 80 is already in use** by an nginx vhost at
  `/etc/nginx/sites-available/default` (symlinked into `sites-enabled/`), with
  `server_name pragati.iitg.ac.in`, `proxy_pass http://127.0.0.1:8081`. That
  8081 backend is currently an *unrelated* Vite dev server for another project
  (`mythos_omni_v0.4/prornd-ui`). This config is `default_server`, so it
  currently swallows **any** request on port 80 that doesn't match a more
  specific vhost.
  - If `pragati.iitg.ac.in` is a real domain someone else relies on, **do not
    delete this file** — `bench setup production` will add a *new*,
    more specific vhost for `prornd.local`; the two can coexist as long as
    `default_server` isn't claimed twice (nginx will fail to reload if two
    files both say `default_server` on the same `listen 80`). Check this
    during Step 4.
- `/etc/hosts` has no entry for `prornd.local`. If you want to browse by
  hostname instead of the raw IP, add `127.0.0.1 prornd.local` (or the
  server's IP, if browsing from another machine) — separately from everything
  below.
- Two huge log files (`logs/terminal.log` 32.6 GB, `logs/worker.error.log`
  2.5 GB) were already truncated on 2026-08-03 to reclaim ~33.5 GB. Not
  related to the CPU issue, just noting it's already handled.
- No passwordless `sudo` is configured for `prornd` on this box — every step
  below marked **(sudo)** needs to be run interactively, by you, in a real
  terminal.

---

## 1. Decide on `developer_mode`

Production setups conventionally run with `developer_mode: 0` in
`sites/prornd.local/site_config.json` (currently `1`). With it on:
tracebacks/print debugging stay verbose, and some dev-only conveniences
(like auto-reload) remain active — neither of which you want for a
process supervisor is managing and restarting for you.

If you still want to actively develop against this same site (the IDE has
`miscellaneous_commit.py` open, suggesting active dev work), read
**Appendix: keeping a dev workflow** at the bottom before flipping this —
you likely want to keep `bench start` available for local iteration and
only route *real user* traffic through the production stack.

```bash
# optional — only if you're ready to fully cut over
bench --site prornd.local set-config developer_mode 0
```

---

## 2. Stop the dev server

```bash
# in the terminal running `bench start`, Ctrl+C
# or, if backgrounded:
pkill -f "bench start"
```

Confirm nothing is still listening on 8000/9000 before continuing
(`ss -tlnp | grep -E '8000|9000'`).

---

## 3. Run the production setup (sudo)

```bash
cd /home/prornd/frappe-dev/prornd
sudo bench setup production prornd
```

This will:
- Generate `config/supervisor.conf` (gunicorn workers, redis, worker/scheduler
  processes, socketio) and install it under supervisor.
- Generate an nginx vhost for the bench (typically written to
  `config/nginx.conf` in the bench root and symlinked into
  `/etc/nginx/conf.d/` or `/etc/nginx/sites-enabled/`).
- Start supervisor + reload nginx.

You'll be prompted for your sudo password interactively.

---

## 4. Resolve the nginx port-80 conflict

After step 3, check for a `default_server` collision:

```bash
sudo nginx -t
```

If it errors about duplicate `default_server` on `0.0.0.0:80`:
- Open the newly generated bench nginx conf (likely
  `/etc/nginx/conf.d/frappe-prornd.local.conf` or similar — `bench setup
  production` prints the path) and the existing
  `/etc/nginx/sites-available/default`.
- Decide which one should be `default_server` for unmatched hostnames/IP-only
  requests (probably the Frappe one, since that's the one you actually use
  day-to-day) — remove `default_server` from the other's `listen` directive.
- `sudo nginx -t && sudo systemctl reload nginx`

This is also the point where the earlier misrouting (port 80 → unrelated
Vite app on 8081) gets fixed, *if* you make the Frappe vhost the default (or
match it to the IP/hostname you actually browse with, `172.16.131.206`).

---

## 5. Verify

```bash
sudo supervisorctl status            # all frappe: processes should be RUNNING
curl -I http://127.0.0.1:8000/       # gunicorn should answer directly
curl -I http://172.16.131.206/       # through nginx, port 80
```

Load the site in a browser, log in, click around a few pages that are known
error-prone (Project Registration activity/workflow endpoints, per the
earlier investigation) and confirm no regressions.

Watch CPU across workers for a bit:

```bash
top -o %CPU
```

You should now see load spread across multiple `gunicorn` worker processes
instead of one process pinned at 100%.

---

## 6. Ongoing operations (after cutover)

- Restart after a code change: `sudo bench restart` (or
  `sudo supervisorctl restart all`).
- Rebuild JS/CSS assets: `bench build` (no more `bench watch` live-reload in
  production).
- Migrate after a pull: `bench --site prornd.local migrate`.
- Logs move from `logs/*.log` to supervisor-managed logs (check
  `config/supervisor.conf` for exact paths) plus the usual
  `sites/prornd.local/logs/`.
- Right-size `gunicorn_workers` if 65 turns out to be too many for actual
  concurrent traffic (each worker is a full process/memory footprint —
  watch `free -h` under load): `bench set-config gunicorn_workers <N>`, then
  `sudo bench restart`.

---

## Appendix: keeping a dev workflow alongside production

If you still need live-reload dev iteration on this same codebase:
- Production (supervisor + gunicorn + nginx) owns port 8000/80 for real
  users, with `developer_mode: 0`.
- For active development, use a **separate site** (`bench new-site
  dev.prornd.local`) or a separate bench checkout entirely, run via
  `bench start` on a different port (`bench serve --port 8001`), with
  `developer_mode: 1`. Test there, then deploy (git pull + migrate +
  build + restart) to the production site once verified.
- Mixing "edit live production code and expect instant reload" with
  "stable multi-user serving" is the fundamental tension causing today's
  CPU pinning — the two want opposite tradeoffs (hot-reload/no caching vs.
  precompiled/cached/parallel), so keeping them as separate environments is
  the standard resolution, not a workaround.
