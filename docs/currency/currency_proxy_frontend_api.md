# Currency Proxy — Frontend API Reference

Audience: frontend developers (React UI) who need exchange rates.
Backend module: [`currency_proxy.py`](../../rndopsapp/rndopsapp/currency_proxy.py) ·
Backend/ops notes: [`currency_proxy.md`](currency_proxy.md)

The frontend never talks to the currency-rate server directly. It calls **one Frappe endpoint**,
which forwards the request and returns the server's answer unchanged.

---

## 1. The endpoint

```
GET {FRAPPE_BASE_URL}/api/method/rndopsapp.rndopsapp.currency_proxy.proxy
```

| Item | Value |
|---|---|
| Method | `GET` only |
| Auth | Logged-in Frappe session (cookie). Guests are rejected. |
| CSRF token | Not needed (GET) |
| Required query param | `path` — the route to call, always starting with `/v2/` |
| Other query params | Everything else is forwarded as-is (see §3) |
| Response | The server's JSON, **without** Frappe's `{ "message": … }` wrapper |

> **Important:** read the response body directly — `const data = await res.json()`, not
> `payload.message`. This differs from most other `rndopsapp` endpoints.

Use `credentials: "include"` so the session cookie is sent (same as other services in the UI,
e.g. `overheadLedger.ts`).

---

## 2. Routes (`path` values)

| `path` | Use it for | Response |
|---|---|---|
| `/v2/rate/{base}/{quote}` | **One pair — the usual choice** (e.g. `/v2/rate/USD/INR`) | `Rate` |
| `/v2/rates` | Latest / historical / time-series rates | `Rate[]` |
| `/v2/coverage` | First and last available date for a query | `Coverage` |
| `/v2/currencies` | Supported currencies | `Currency[]` |
| `/v2/currency/{code}` | One currency | `Currency` |
| `/v2/providers` | Rate sources | `Provider[]` |
| `/v2/providers/{provider}` | One source (freshness, datasets) | `Provider` |
| `/v2/providers/{provider}/rates` | Rates from one source | `Rate[]` |
| `/v2/providers/{provider}/rate/{base}/{quote}` | One pair from one source | `Rate` |
| `/v2/openapi.json` | The server's OpenAPI document | JSON |

Any other `path` is rejected (see §6). Codes/keys use letters, digits, `_`, `-`, `.`
(e.g. provider dataset `nbp.b`). Add `.csv` / `.json` / `.ndjson` to a path for those formats (§5).

---

## 3. Query parameters

Send them next to `path`. They are not validated by Frappe — the server decides.

| Param | Example | Meaning | Applies to |
|---|---|---|---|
| `base` | `USD` | Currency converted **from** (default `EUR`) | `/v2/rates`, provider rates, `/v2/coverage` |
| `quotes` | `INR,EUR` or repeated `quotes=INR&quotes=EUR` | Currencies converted **to** | same |
| `date` | `2026-11-18` | Rate for one date | `/v2/rate/…`, `/v2/rates` |
| `from`, `to` | `2026-11-01`, `2026-11-19` | Time-series range (`to` defaults to today) | `/v2/rates`, provider rates |
| `providers` | `ECB,FBIL` | Only these sources | rates, coverage, currencies |
| `group` | `week` / `month` | Downsample a series | `/v2/rates` |
| `expand` | `providers` | Add per-provider detail to each rate | `/v2/rates` |
| `scope` | `all` | Include legacy currencies | `/v2/currencies` |

- Use **`quotes`**, not `quote` → `422 unknown parameter: quote`.
- `path` **must include `/v2/`**; `rates` alone is rejected.
- Don't send `cmd`, `_`; they are dropped.
- Use `URLSearchParams` so values are encoded and repeated keys work.

---

## 4. Response shapes (TypeScript)

Verified against the live server on 19 Nov 2026.

```ts
/** One observation. */
export interface Rate {
  date: string;          // "2026-11-19"  (ISO date the rate belongs to)
  base: string;          // "USD"
  quote: string;         // "INR"
  rate: number;          // 93.44  (1 base = rate quote)
  providers?: RateProvider[];   // only with expand=providers
}

export interface RateProvider {
  key: string;           // "FBIL"
  date: string;          // that provider's own observation date (may be older)
  rate: number;
  excluded?: boolean;    // true = did not contribute to the blended rate
}

export interface Coverage {
  base: string;
  quotes: string[];
  providers: string[] | null;
  start_date: string;
  end_date: string;      // bounds only — gaps inside the range can exist
}

export interface Currency {
  iso_code: string;      // "INR"
  iso_numeric: string;   // "356"
  name: string;          // "Indian Rupee"
  symbol: string;        // "₹"
  type: string;          // "currency" (also metals / crypto)
  start_date: string;
  end_date: string;
  providers?: string[];  // on /v2/currency/{code}
}

export interface Provider {
  key: string;           // "FBIL"
  name: string;          // "Financial Benchmarks India"
  country_code: string;
  rate_type: string;     // "reference rate"
  pivot_currency: string;
  data_url?: string;
  // more fields exist (cadence, freshness, datasets) — type them as needed
  [extra: string]: unknown;
}

/** Error body for every non-2xx answer. */
export interface ApiError {
  status: number;        // 400 | 404 | 422 | 503 | 504 …
  message: string;       // "not found", "unknown parameter: quote", …
}
```

### Examples (real responses)

`GET …proxy?path=/v2/rate/USD/INR`
```json
{ "date": "2026-11-19", "base": "USD", "quote": "INR", "rate": 93.44 }
```

`GET …proxy?path=/v2/rates&base=USD&quotes=INR&quotes=EUR`
```json
[
  { "date": "2026-11-19", "base": "USD", "quote": "EUR", "rate": 0.91072 },
  { "date": "2026-11-19", "base": "USD", "quote": "INR", "rate": 93.44 }
]
```

`GET …proxy?path=/v2/rates&base=USD&quotes=INR&expand=providers`
```json
[{ "date": "2026-11-19", "base": "USD", "quote": "INR", "rate": 93.44,
   "providers": [ { "key": "BB", "date": "2026-11-19", "rate": 93.47 },
                  { "key": "BCV", "date": "2026-11-19", "rate": 93.43 } ] }]
```

`GET …proxy?path=/v2/coverage&base=USD&quotes=INR`
```json
{ "base": "USD", "quotes": ["INR"], "providers": null,
  "start_date": "1994-03-01", "end_date": "2026-11-19" }
```

---

## 5. Other formats

Normally JSON. For large series the server can stream NDJSON, or return CSV:

| Want | How |
|---|---|
| NDJSON (one JSON object per line) | send header `Accept: application/x-ndjson` |
| CSV | `path=/v2/rates.csv` or header `Accept: text/csv` |

The response `Content-Type` tells you which one you got. Parse NDJSON with
`text.trim().split("\n").map(JSON.parse)`.

---

## 6. Errors

The HTTP status and body come from the server unchanged, so check `res.ok`.

| Status | Body | Cause | What to show / do |
|---|---|---|---|
| `400` | `ApiError` | Malformed request | Fix the call |
| `404` | `{status:404, message:"not found"}` | Unknown currency / provider / no rate for the date | "Rate not available" |
| `422` | `{status:422, message:"unknown parameter: …"}` | Bad parameter name or combination | Fix the call |
| `503` | `ApiError` (`Currency service unavailable`) | Server down / unreachable, or server busy (a `Retry-After` header may be present) | Retry later; fall back to the last stored rate |
| `504` | `ApiError` | Server too slow | Retry later |
| `502` | `ApiError` | Response too large | Narrow the range / add `quotes` / use `group` |
| `403` | Frappe error page / JSON | Not logged in, or session expired | Redirect to login |
| `417` | Frappe error JSON (`exc_type: "ValidationError"`) | `path` missing or not an allowed route | Fix the call |

Frappe's own errors (403, 417) have the usual Frappe body (`exception`, `_server_messages`),
not `{status, message}` — handle both shapes.

---

## 7. Usage examples (documentation only)

These are reference snippets; nothing has been added to the frontend code.

### 7.1 Generic call

```ts
import { FRAPPE_BASE_URL } from "@/utils/frappeUrl";

const PROXY = `${FRAPPE_BASE_URL}/api/method/rndopsapp.rndopsapp.currency_proxy.proxy`;

export async function currencyApi<T>(
  path: string,
  params: Record<string, string | string[]> = {},
): Promise<T> {
  const qs = new URLSearchParams({ path });
  for (const [k, v] of Object.entries(params)) {
    (Array.isArray(v) ? v : [v]).forEach((x) => qs.append(k, x));
  }
  const res = await fetch(`${PROXY}?${qs}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new Error(body?.message || body?.exception || `Currency service error (${res.status})`);
  }
  return body as T;            // no `.message` wrapper
}
```

### 7.2 Calls

```ts
// Current USD → INR
const r = await currencyApi<Rate>("/v2/rate/USD/INR");

// Rate on a past date
const past = await currencyApi<Rate>("/v2/rate/USD/INR", { date: "2026-11-18" });

// Several currencies at once
const rows = await currencyApi<Rate[]>("/v2/rates", { base: "USD", quotes: ["INR", "EUR", "GBP"] });

// Monthly series for a chart
const series = await currencyApi<Rate[]>("/v2/rates", {
  base: "USD", quotes: "INR", from: "2026-01-01", group: "month",
});

// Currency dropdown
const currencies = await currencyApi<Currency[]>("/v2/currencies");

// One source's rate (e.g. an official reference rate)
const fbil = await currencyApi<Rate>("/v2/providers/FBIL/rate/USD/INR");
```

### 7.3 Converting amounts

There is no conversion endpoint — fetch the rate and multiply. **For INR always fetch the
foreign → INR rate** and divide for the other direction, because the inverse rate has few
significant digits (`INR→USD` is `0.010702`):

```ts
// foreign → INR
const toInr = (amount: number, usdInr: number) => amount * usdInr;

// INR → foreign
const fromInr = (amountInr: number, usdInr: number) => amountInr / usdInr;
```

Round for display only; keep the rate and its `date` for the record (below).

### 7.4 With frappe-react-sdk

`useFrappeGetCall` wraps results in `message`, so it does not fit this endpoint. Use plain
`fetch` (§7.1) or a small hook around it.

---

## 8. Good practice

- **Store the rate on the document.** When a rate is used in a form (e.g. a quotation in USD),
  save `exchange_rate`, `rate_date` and the converted INR amount with the record. Don't re-fetch
  later — the amount would change.
- **Show the returned `date`**, not today's date. Weekends/holidays return the previous business
  day, and some providers publish with a lag.
- **Cache in the UI** (e.g. React Query, 1–6 hours per pair/date). Rates change about once a day.
- **Narrow requests:** pass `quotes`, a bounded `from`/`to`, or `group` — avoid `expand=providers`
  on wide ranges.
- **Handle failure:** on `503`/`504` fall back to the last rate stored or cached, and show its date.
- **Don't build the URL by hand**; use `URLSearchParams`.
- Rates are **reference rates, not live market quotes**. For tax or accounting amounts, pin a
  specific source with `providers=` instead of the blended rate.

---

## 9. Quick checklist

- [ ] Call `…currency_proxy.proxy` with `path=/v2/...` and `credentials: "include"`.
- [ ] Read the body directly (no `.message`).
- [ ] Use `quotes` (plural); repeated keys or comma lists both work.
- [ ] Check `res.ok`; map 404 → "rate not available", 503/504 → retry/fallback, 403 → login.
- [ ] Save `rate` and `date` on the record.
