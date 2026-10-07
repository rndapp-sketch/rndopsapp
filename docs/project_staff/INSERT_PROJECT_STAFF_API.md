# `/insert_project_staff` — API Reference for React Port

Source page: `apps/frappe/frappe/www/insert_project_staff.html`
Backend module: `rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details`
(file: `apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_staff_details/project_staff_details.py`)

All endpoints are Frappe REST-over-RPC: `POST /api/method/<dotted.method.path>`,
`Content-Type: application/json` (unless noted as multipart), header
`X-Frappe-CSRF-Token: <csrf_token>`, and the Frappe session cookie for auth.
Response envelope is always `{"message": <return value>}` on success.

---

## 1. Auth

Session-cookie auth, same as the rest of Frappe Desk. No token/JWT.

### Login
```
POST /api/method/login
Content-Type: application/json

{ "usr": "<username or email>", "pwd": "<password>" }
```
- On success: sets the session cookie (`sid`), response is a Frappe login payload. The page just does `window.location.reload()` and relies on the cookie from then on — in React, after this call, fetch the CSRF token (see below) and store the session.
- On failure: non-2xx status; `data.message` or `data._server_messages` holds the error text.

### Logout
```
POST /api/method/logout
X-Frappe-CSRF-Token: <csrf_token>
```

### CSRF token
Server-rendered pages get it injected as `{{ frappe.session.csrf_token }}`. A pure React/SPA client instead reads it from:
```
GET /api/method/frappe.sessions.get_csrf_token   // or decode it from boot info
```
Simplest working approach for a separate React app talking to the same Frappe site: call `GET /api/method/frappe.auth.get_logged_user` after login to confirm the session, and fetch `/app` once to scrape `csrf_token` from `window.csrf_token`/`frappe.boot`, OR (cleaner) have the backend expose a tiny whitelisted method that returns `frappe.session.csrf_token` for XHR clients. Every mutating call below requires this token in `X-Frappe-CSRF-Token`.

### Current user
Session user is available server-side; if React needs it client-side, call:
```
GET /api/method/frappe.auth.get_logged_user
```

---

## 2. Reference data

### 2.1 Departments (dropdown)
```
POST /api/method/frappe.client.get_list
{
  "doctype": "Department_prornd",
  "fields": ["name", "dept_name"],
  "limit_page_length": 0,
  "order_by": "dept_name asc"
}
```
→ `message`: `[{ "name": "...", "dept_name": "..." }, ...]`
Use `dept_name` as both the option value and label (that's what the HTML page does — it stores the label text, not the `name` id, into `ps_department`).

### 2.2 Project Number search (typeahead combobox)
```
POST /api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.search_projects
{ "query": "<free text, min 2 chars>", "page_size": 15 }
```
Debounce ~300ms client-side (that's what the HTML does) before firing.

Args: `query` (str), `department` (str, optional exact filter — unused on this page), `page` (int, default 1), `page_size` (int, default 20, capped 100).

→ `message`:
```json
{
  "status": "success",
  "total": 42,
  "page": 1,
  "page_size": 15,
  "results": [
    { "project_no": "PRJ-0001", "project_title": "...", "pi_name": "...", "...": "..." }
  ]
}
```
Selecting a result sets `project_no` as the field value (not a separate id).

---

## 3. Employee ID preview

```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.get_next_emp_id
```
No args. → `message`: a string like `"2026TS0001"` — the *next* id if someone saved right now. **Preview only** — never send this value back on create; the server allocates the real id atomically inside `create_project_staff_details_entry`. Can drift between preview and actual save if another submission happens in between; that's expected.

---

## 4. Create one Project Staff record (manual form submit)

```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.create_project_staff_details_entry
{ "data": { ...fields... } }
```

Runs under the logged-in user's normal doctype permissions (no permission bypass). On success it also: allocates `ps_emp_id`, force-sets `workflow_state = "Approved"`, creates/updates the matching `User` record, appends a tenure row, and allocates Leave Data — all server-side, nothing else needed from the client.

### Accepted fields (`data` keys)
| Field | Required | Notes |
|---|---|---|
| `pi_id` | ✅ | email |
| `project_no` | ✅ | from the project search combobox |
| `scr_id` | | |
| `ps_department` | ✅ | dept_name text (see §2.1) |
| `ps_designation` | ✅ | free text |
| `ps_first_name` | ✅ | auto title-cased server-side |
| `ps_middle_name` | | auto title-cased |
| `ps_last_name` | ✅ | auto title-cased |
| `ps_gender` | ✅ | `Male` \| `Female` |
| `ps_date_of_birth` | | `YYYY-MM-DD` |
| `ps_fathers_name` | | auto title-cased |
| `ps_blood_group` | | `A+ A− B+ B− AB+ AB− O+ O−` |
| `ps_maritial_status` | | `Single` \| `Married` |
| `ps_citizenship` | | defaults to `Indian` in the UI, not server-enforced |
| `ps_phone_number` | | |
| `ps_email_id` | | |
| `erp_mail` | | defaults to `ps_email_id` client-side if left blank — replicate that in React |
| `ps_present_address` | | |
| `ps_permanent_address` | | |
| `bank_account_number` | | |
| `ifsc_code` | | upper-cased both client- and server-side |
| `ps_pan` | | |
| `ps_aadhar_number` | | |
| `ps_joining_date` | ✅ | `YYYY-MM-DD` |
| `ps_term_completion_date` | | |
| `ps_basic_salary` | | numeric |
| `ps_hra` | | `16%` \| `18%` \| `20%` |
| `ps_ma` | | free text/number, e.g. `1250` |
| `ps_hostel` | | `Yes` \| `No` |
| `ps_ta` | | `Yes` \| `No` — "Travel Allowance Needed" |
| `ps_ta_amount` | | only sent/relevant when `ps_ta === "Yes"` |

→ `message`:
```json
{ "status": "success", "docname": "PSD-00123", "ps_emp_id": "2026TS0042" }
```
On failure the request itself comes back non-2xx (Frappe raises) — surface `data.message` / `data.exc_type`.

---

## 5. Bulk Upload (CSV / Excel) — 3-step flow

### Step 1 — Upload & auto-detect columns
```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.preview_bulk_import_headers
Content-Type: multipart/form-data
file: <File>   (.csv / .xls / .xlsx)
```
→ `message`:
```json
{
  "headers": ["PI Id", "Project Number", "..."],
  "suggested_mapping": ["pi_id", "project_no", null, "..."],
  "sample_row": ["pi@iitg.ac.in", "PRJ-0001", "..."],
  "data_rows": [["...", "...", "..."], ...],
  "fields": [
    { "fieldname": "pi_id", "label": "PI Id", "required": true },
    { "fieldname": "project_no", "label": "Project Number", "required": true },
    ...
  ]
}
```
Use `fields` to render the "maps to" dropdown per column (with `"— Do not import —"` as the null option), pre-selected from `suggested_mapping`. `data_rows`/`headers` are kept entirely client-side for the rest of the flow — nothing is staged server-side.

### Step 2 — Column mapping (client-side only)
No network call. User corrects the dropdown per column. Validate that every `required: true` field in `fields` has at least one column mapped to it before proceeding (client-side check mirrored from the HTML page).

### Step 3 — Editable row preview (client-side only)
Build an editable grid: rows = `data_rows`, columns = only the ones mapped to a field in step 2. Each row has an "include" checkbox (default checked). No network call yet.

### Step 4 — Commit the import
```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.bulk_import_project_staff_details_from_rows
{ "rows": [ { "pi_id": "...", "project_no": "...", ... }, ... ] }
```
`rows`: array of plain `{fieldname: value}` objects — only mapped + checked rows, only non-empty cells. Same field list/validation as §4, but processed row-by-row: missing required fields or duplicates (same Aadhar / PAN / project+name+joining-date) don't abort the batch.

→ `message`:
```json
{
  "status": "success",
  "counts": { "success": 8, "duplicate": 1, "error": 1 },
  "results": [
    { "row": 1, "name": "John Doe", "status": "success", "docname": "PSD-00123", "ps_emp_id": "2026TS0042", "message": "Created PSD-00123 — Employee ID 2026TS0042" },
    { "row": 2, "name": "Jane Doe", "status": "duplicate", "message": "...", "row_data": {...} },
    { "row": 3, "name": "Row 3", "status": "error", "message": "Missing required field(s): ...", "row_data": {...} }
  ]
}
```
`status` per row is one of `success | duplicate | error`. `duplicate`/`error` rows carry `row_data` back so the UI can offer a "Fix & Retry" form.

### Step 5 — Fix & Retry a single failed/duplicate row
Re-uses the single-record endpoint from §4 directly:
```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.create_project_staff_details_entry
{ "data": { ...edited row_data... } }
```
On success, patch that row's status to `success` in local state (no need to re-fetch the whole batch).

### Alternative bulk endpoint (not used by this page, but available)
```
POST /api/method/rndopsapp.rndopsapp.doctype.project_staff_details.project_staff_details.bulk_import_project_staff_details
Content-Type: multipart/form-data
file: <File>
column_mapping: <JSON array, optional>   // same length/order as the file's header row; fieldname or null per column
```
Does the upload + column-mapping + import in one call (no manual preview/edit step). Use this if you want a simpler "upload and go" alternative flow instead of the full 3-step UI.

---

## 6. Field reference used for both the manual form and the bulk importer

Canonical order + required flags (mirrors the downloadable CSV template):

```
pi_id*              PI Id
project_no*         Project Number
scr_id              SCR Id
ps_department*      Department
ps_designation*     Designation
ps_first_name*      First Name
ps_middle_name      Middle Name
ps_last_name*       Last Name
ps_gender*          Gender            (Male | Female)
ps_date_of_birth    Date of Birth     (YYYY-MM-DD)
ps_fathers_name     Father's Name
ps_blood_group      Blood Group       (A+ A− B+ B− AB+ AB− O+ O−)
ps_maritial_status  Maritial Status   (Single | Married)
ps_citizenship      Citizenship
ps_phone_number     Phone Number
ps_email_id         Email Id
erp_mail            ERP Mail          (falls back to ps_email_id if blank)
ps_present_address  Present Address
ps_permanent_address Permanent Address
bank_account_number Bank Account Number
ifsc_code           IFSC Code         (upper-cased)
ps_pan              PAN
ps_aadhar_number    Aadhar Number
ps_joining_date*    Joining Date      (YYYY-MM-DD)
ps_term_completion_date Term Completion Date
ps_basic_salary     Basic Salary      (number)
ps_hra              HRA               (16% | 18% | 20%)
ps_ma               Medical Allowance
ps_hostel           Hostel            (Yes | No)
ps_ta               Travel Allowance Needed  (Yes | No)
ps_ta_amount        Travel Allowance Amount  (only if ps_ta = Yes)
```
`*` = required by both the manual form and the bulk importer's required-field check.

Bulk-import-only normalization the backend applies automatically (replicate client-side for a better UX, but the server is the source of truth):
- **Dates** (`ps_date_of_birth`, `ps_joining_date`, `ps_term_completion_date`): accepts `YYYY-MM-DD`, `YYYY/MM/DD`, `DD-MM-YYYY`, `DD/MM/YYYY`, `DD.MM.YYYY`, `DD-MM-YY`, `DD/MM/YY`, `MM-DD-YYYY`, `MM/DD/YYYY` — converts to `YYYY-MM-DD`.
- **`ps_ta`** (Yes/No): accepts `yes/y/true/1` → `Yes`, `no/n/false/0` → `No`.
- Header text matching for CSV/Excel column auto-detection is case/space/punctuation-insensitive (e.g. "PI Id", "pi_id", "PIID" all map to `pi_id`).

---

## 7. Summary — what React needs to implement

| UI piece | Endpoint(s) |
|---|---|
| Login screen | `POST /api/method/login`, then reload/refetch session |
| Logout button | `POST /api/method/logout` |
| Employee ID preview field | `GET/POST get_next_emp_id` |
| Department dropdown | `frappe.client.get_list` (Department_prornd) |
| Project Number typeahead | `search_projects` |
| "Create Staff Record" button | `create_project_staff_details_entry` |
| "Download Template" button | pure client-side CSV generation, no endpoint |
| Bulk upload → map columns | `preview_bulk_import_headers` (multipart) |
| Bulk preview grid → Import All Rows | `bulk_import_project_staff_details_from_rows` |
| Bulk results → Fix & Retry | `create_project_staff_details_entry` |
| (optional simpler bulk path) | `bulk_import_project_staff_details` (multipart, one-shot) |

All mutating calls need `X-Frappe-CSRF-Token`; all calls rely on the Frappe session cookie, so the React app must either be served from/proxied through the same origin as the Frappe site, or you configure CORS + `frappe.conf` to allow the React app's origin with credentials.
