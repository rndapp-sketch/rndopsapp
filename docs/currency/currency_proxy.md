# Currency Exchange-Rate API Proxy

> **Status: IMPLEMENTED.** Module: [`rndopsapp/rndopsapp/currency_proxy.py`](../../rndopsapp/rndopsapp/currency_proxy.py)

This Frappe app proxies GET requests to a **self-hosted currency-rate server**
(Docker, default `http://172.16.131.206:7070`). The browser / UI talks only to Frappe; Frappe
forwards the request and returns the server's answer **unchanged** — status code, body and
content type. Every query parameter is passed through, so any current or future
parameter works without a code change.

```
UI / client ──► Frappe  /api/method/rndopsapp.rndopsapp.currency_proxy.proxy
                          │  (login required, route whitelist, all params forwarded)
                          ▼
                 Currency server  http://172.16.131.206:7070/v2/...
```

---

## 1. Configuration

| Setting | Where | Default |
|---|---|---|
| `CURRENCY_API_BASE_URL` | [`currency_proxy.py`](../../rndopsapp/rndopsapp/currency_proxy.py) (top of the file) | `http://172.16.131.206:7070` |
| `currency_api_url` | site config (overrides the default for one site) | – |

Use the site config when the container runs on another host:

```bash
bench --site <site> set-config currency_api_url "http://172.16.x.x:7070"
```

Timeouts: 3 s to connect, 30 s to read. Responses larger than 50 MB are refused.

---

## 2. The proxy endpoint

```
GET /api/method/rndopsapp.rndopsapp.currency_proxy.proxy?path=<API route>&<any API params>
```

- `path` — the full currency API route starting with `/v2/` (see §3), e.g. `/v2/rates`. A missing leading `/` is added, but the `v2` prefix is required.
- **Every other query parameter is forwarded as-is**, including repeated keys
  (`quotes=INR&quotes=EUR`) and parameters the API adds in future.
- Frappe's own keys (`cmd`, `path`, `_`) are not forwarded.
- **GET only. Login required** (not available to Guest users).
- `Accept: application/x-ndjson` or `text/csv` is forwarded, so those formats work; the
  `.csv` path suffix (`/v2/rates.csv`) also works.

### Response

The body, HTTP status and `Content-Type` are exactly what the currency server returned. It is **not**
wrapped in Frappe's usual `{"message": ...}` envelope. `Retry-After`, `Cache-Control`, `ETag`
and `Last-Modified` are passed on too.

| Situation | Result |
|---|---|
| Success | `200` + the server's JSON / CSV / NDJSON |
| The currency server says 400 / 404 / 422 / 503 | Same status and `{"status":…,"message":…}` body |
| Currency service unreachable | `503` `{"status":503,"message":"Currency service unavailable"}` |
| Currency server too slow | `504` `{"status":504,"message":"Currency service did not respond in time"}` |
| Response too large | `502` |
| `path` missing / not an allowed route | `417` Frappe validation error (nothing is sent upstream) |

Unreachable / timeout failures are also written to **Error Log** with the title
"Currency Proxy".

---

## 3. Proxied routes

Only these routes are forwarded; anything else is rejected before any request is made, so the
proxy cannot be used to reach other URLs on the currency server host.

| Route | Purpose |
|---|---|
| `/v2/rates` | Latest, historical (`date`) and time-series (`from`/`to`, `group`) rates |
| `/v2/rate/{base}/{quote}` | One currency pair (optional `date`, `providers`) |
| `/v2/coverage` | First / last available date for a rate query |
| `/v2/currencies` | Supported currencies (`scope=all`, `providers=`) |
| `/v2/currency/{code}` | One currency |
| `/v2/providers` | Rate providers |
| `/v2/providers/{provider}` | One provider (cadence, freshness, datasets) |
| `/v2/providers/{provider}/rates` | Rates from one provider |
| `/v2/providers/{provider}/rate/{base}/{quote}` | One pair from one provider |
| `/v2/openapi.json` | the server's OpenAPI document |

Currency codes and provider / dataset keys may contain letters, digits, `_`, `-` and `.`
(dataset keys such as `nbp.b` contain a dot). `..`, `//`, `%`, `?` and `#` in `path` are rejected.
Each route also accepts an optional `.json`, `.csv` or `.ndjson` suffix.

### Query parameters (forwarded untouched)

| Parameter | Example | Purpose |
|---|---|---|
| `base` | `base=USD` | Base currency |
| `quotes` | `quotes=INR,EUR` | Target currencies |
| `date` | `date=2026-11-19` | Specific date |
| `from` / `to` | `from=2026-01-01` | Time-series range |
| `providers` | `providers=ECB,FBIL` | Restrict to providers |
| `group` | `group=month` | Downsample (`week` / `month`) |
| `expand` | `expand=providers` | Show per-provider contributions |
| `scope` | `scope=all` | Include legacy currencies (`/v2/currencies`) |

Use `quotes`, not `quote` — the API answers `422 unknown parameter: quote`.

---

## 4. Examples

```bash
# All calls need an authenticated Frappe session or API key.

# USD -> INR now
GET /api/method/rndopsapp.rndopsapp.currency_proxy.proxy?path=/v2/rate/USD/INR

# Historical
...proxy?path=/v2/rate/USD/INR&date=2026-11-18

# Latest USD rates for selected currencies
...proxy?path=/v2/rates&base=USD&quotes=INR,EUR,GBP,JPY

# Time series, monthly
...proxy?path=/v2/rates&base=USD&quotes=INR&from=2026-01-01&group=month

# Which providers contributed to the blended rate
...proxy?path=/v2/rates&base=USD&quotes=INR&expand=providers

# One provider, provider freshness, currency list, coverage
...proxy?path=/v2/providers/FBIL/rates&base=USD&quotes=INR
...proxy?path=/v2/providers/FBIL
...proxy?path=/v2/currencies
...proxy?path=/v2/coverage&base=USD&quotes=INR
```

From the browser or the React UI, call it with the logged-in session:

```ts
const r = await fetch(
  "/api/method/rndopsapp.rndopsapp.currency_proxy.proxy?" +
    new URLSearchParams({ path: "/v2/rate/USD/INR" }),
  { credentials: "include" },
);
const { rate, date } = await r.json();   // no "message" wrapper
```

NDJSON / CSV:

```bash
curl -H "Accept: application/x-ndjson" "…proxy?path=/v2/rates&base=USD&quotes=INR&from=2026-01-01"
curl "…proxy?path=/v2/rates.csv&base=USD&quotes=INR"
```

### Conversion

There is no conversion endpoint. Fetch the rate and multiply:
`converted = amount × rate`. For INR amounts prefer fetching **foreign → INR**
(`/v2/rate/USD/INR`, about 93) and dividing for INR → foreign, because the inverse rate
(about 0.0107) is returned with few significant digits.

---

## 5. Using it from Python (server side)

```python
from rndopsapp.rndopsapp.currency_proxy import currency_get

rate = currency_get("/v2/rate/USD/INR", {"date": "2026-11-18"})
# {"date": "2026-11-18", "base": "USD", "quote": "INR", "rate": 93.44}

series = currency_get("/v2/rates", {"base": "USD", "quotes": "INR", "from": "2026-11-01"})
```

`currency_get` is not whitelisted. It uses the same route check, timeouts and base URL, returns
parsed JSON, and raises `frappe.ValidationError` (with the server's message) for a non-2xx
answer or an unreachable server — so callers can catch it and fall back to a cached rate.

---

## 6. Security notes

- **Not open to guests**; any logged-in Frappe user can call it. Restrict further (roles) if
  rates should not be visible to every user.
- **Route allow-list**, not a free-form URL proxy: the host is fixed by configuration and only
  the routes in §3 are forwarded. Redirects from the upstream are never followed.
- The currency server needs no API key for the public data sources; if one is ever required,
  add it in the proxy (server side) rather than exposing it to the browser.
- The data are reference rates, not live market quotes; they update once or a few
  times a day. Cache what you need and store the rate (and its date) on the document that uses it.

---

## 7. Testing

Verified against a stand-in server (routing, parameter pass-through, error pass-through,
rejection of bad paths, unreachable upstream) **and** against the real server
`http://172.16.131.206:7070` (19 Nov 2026):

- `/v2/rate/USD/INR` → `200` (`rate` 93.44); `/v2/rate/INR/USD` → `200` (`rate` 0.010702, i.e. only
  about 5 significant digits — see the conversion note in §4);
- `/v2/rates` with `quotes`, repeated `quotes`, `from`/`to` and `expand=providers`; `/v2/coverage`,
  `/v2/currency/INR`, `/v2/providers/FBIL`, `/v2/providers/FBIL/rate/USD/INR` → `200`;
- `Accept: application/x-ndjson` and `/v2/rates.csv` return NDJSON / CSV with the right content type;
- upstream errors pass through unchanged: `quote=INR` → `422 unknown parameter: quote`,
  unknown currency → `404 not found`;
- `currency_get("/v2/rate/USD/INR")` returns the parsed JSON.

These were called inside the Frappe process (`bench console`), not over HTTP with a browser session.
To check the login requirement end to end:

```bash
curl -s "http://<frappe-host>/api/method/rndopsapp.rndopsapp.currency_proxy.proxy?path=/v2/rate/USD/INR"
#   -> 403 (not logged in)
# With a logged-in session or API key it returns the server's JSON directly.
curl -s http://172.16.131.206:7070/v2/rate/USD/INR     # currency server directly
```

## 8. Files

| File | Change |
|---|---|
| [`rndopsapp/rndopsapp/currency_proxy.py`](../../rndopsapp/rndopsapp/currency_proxy.py) | New — `proxy` (whitelisted) and `currency_get` (helper) |
| `docs/currency/currency_proxy.md` | This document |

No DocType, no migration, no `bench migrate`. Restart workers after deploy so the new module loads.
