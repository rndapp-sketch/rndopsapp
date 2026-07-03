# Delegate User — Frontend Integration Guide

## What is Delegation?

A **Permanent Employee** (User A) can delegate access to their projects and applications to another user (User B).

Once delegated:
- User B logs in and **automatically sees** User A's projects and applications in all list views
- The backend enforces this — no frontend query changes are needed for visibility
- The frontend only needs to provide the UI to **create**, **view**, and **revoke** delegations

---

## Who Can Use This?

- Only users with the **`Permanent Employee`** role can call any of these APIs
- The route `/delegate-user` should remain guarded for `Permanent Employee`
- Backend enforces this independently — a 403 is thrown if the role is missing

---

## Base URL

All endpoints follow the pattern:

```
/api/method/rndopsapp.rndopsapp.api.<method_name>
```

All responses are wrapped by Frappe:
```json
{ "message": <actual return value> }
```

All errors are returned as HTTP `417` with:
```json
{ "exc_type": "ValidationError", "exception": "frappe.exceptions.ValidationError: <message>" }
```

---

## Page Flow

```
/delegate-user
│
├── On load → call get_delegate_scope()
│              → populates: current delegates list, project picker, application picker
│
├── Search user → call search_delegate_users(query)
│
├── Submit form → call delegate_user(...)
│
├── View active delegations → call get_active_delegations()
│
└── Revoke button → call undelegate_user(delegation_name)
```

---

## API Reference

---

### 1. Search Users to Delegate To

**Use when:** User types in the delegate user search/autocomplete field.

```
GET /api/method/rndopsapp.rndopsapp.api.search_delegate_users?query=<string>
```

| Param | Type | Required | Notes |
|---|---|---|---|
| `query` | string | no | Searches email, full_name. Empty returns all users. |

**Response:**
```json
{
  "message": [
    {
      "label": "John Doe",
      "value": "john@iitg.ac.in",
      "email": "john@iitg.ac.in",
      "full_name": "John Doe"
    }
  ]
}
```

**Notes:**
- Excludes current user, Administrator, Guest, and disabled users
- Use `value` as the user identifier in all subsequent calls
- Suitable for use as autocomplete/select options directly

---

### 2. Get Delegation Scope (Projects + Applications)

**Use when:** Page loads — populate the project/application multi-select pickers and show existing delegates.

```
GET /api/method/rndopsapp.rndopsapp.api.get_delegate_scope
```

No parameters needed. Always uses the logged-in user.

**Response:**
```json
{
  "message": {
    "users": [
      {
        "label": "Jane Smith",
        "value": "jane@iitg.ac.in",
        "email": "jane@iitg.ac.in",
        "full_name": "Jane Smith"
      }
    ],
    "projects": [
      {
        "name": "PRJ-REG-2026-00001",
        "project_title": "AI Research Project",
        "project_no": "RND/2026/001",
        "workflow_state": "Approved",
        "pi_webmail": "a@iitg.ac.in",
        "owner": "a@iitg.ac.in"
      }
    ],
    "applications": [
      {
        "doctype": "Travel",
        "name": "TRV-2026-00001",
        "title": "TRV-2026-00001",
        "project_name": "PRJ-REG-2026-00001",
        "project_no": null,
        "workflow_state": "Draft",
        "owner": "a@iitg.ac.in"
      },
      {
        "doctype": "Loan Request",
        "name": "LOAN-2026-00001",
        "title": "LOAN-2026-00001",
        "project_name": null,
        "project_no": null,
        "workflow_state": "Pending Approval",
        "owner": "a@iitg.ac.in"
      }
    ]
  }
}
```

**Field guide:**

| Field | Use for |
|---|---|
| `users` | Show as "already delegated to" badges/chips on the page |
| `projects` | Populate project multi-select; use `name` as value, `project_title` as label |
| `applications` | Populate application multi-select; use `name` as value, `doctype + name` as label |

**Application doctypes returned:**

| DocType | Notes |
|---|---|
| Travel | |
| TA DA Settlement | |
| Temporary Advance | |
| Advance Settlement | |
| Reimbursement | |
| Direct Purchase | |
| Disbursal of Consultancy | |
| Disbursal of Honorarium | |
| Loan Request | |
| Indent General Form | |
| Indent Cum Sanction Sheet | |
| Recruitment Adhoc Contractual | |

---

### 3. Get Active Delegations

**Use when:** Showing the list of current delegations created by the logged-in user.

```
GET /api/method/rndopsapp.rndopsapp.api.get_active_delegations
```

No parameters needed. Always uses the logged-in user.

**Response:**
```json
{
  "message": [
    {
      "name": "DEL-2026-00001",
      "delegate_user": "jane@iitg.ac.in",
      "delegate_user_name": "Jane Smith",
      "delegation_type": "View Only",
      "scope_type": "project",
      "project_count": 2,
      "application_count": 0,
      "valid_from": null,
      "valid_to": "2026-12-31 00:00:00",
      "enabled": 1
    }
  ]
}
```

**Field guide:**

| Field | Use for |
|---|---|
| `name` | Pass to `undelegate_user` to revoke |
| `delegate_user_name` | Display name in the delegation card |
| `delegation_type` | Show as a badge: `View Only` / `View and Edit` / `Workflow Action` |
| `scope_type` | Show scope: `all` / `project` / `application` |
| `project_count` | Show "3 projects" label |
| `application_count` | Show "5 applications" label |
| `valid_from` / `valid_to` | Show validity dates; `null` means no restriction |

---

### 4. Create / Merge a Delegation

**Use when:** User submits the delegate form.

```
POST /api/method/rndopsapp.rndopsapp.api.delegate_user
```

| Parameter | Type | Required | Default | Notes |
|---|---|---|---|---|
| `delegate_user` | string (email) | **yes** | — | The user to delegate to |
| `delegation_type` | string | no | `View Only` *(create only)* | Omit to keep existing value on update |
| `scope_type` | string | no | `all` *(create only)* | Omit to keep existing value on update |
| `project_names` | JSON string | no | `[]` | Required if `scope_type=project`. **Merged** into existing list. |
| `applications` | JSON string | no | `[]` | Required if `scope_type=application`. **Merged** into existing list. |
| `valid_from` | string (datetime) | no | null | Only updates existing value if provided |
| `valid_to` | string (datetime) | no | null | Only updates existing value if provided |

**Allowed values:**

`delegation_type`:
- `View Only` — delegate can see documents but not edit
- `View and Edit` — delegate can see and edit documents
- `Workflow Action` — delegate can perform workflow actions

`scope_type`:
- `all` — all projects and applications
- `project` — only selected projects (must pass `project_names`)
- `application` — only selected applications (must pass `applications`)

#### Create vs Merge behaviour

| Scenario | Backend behaviour |
|---|---|
| No active delegation exists | **Creates** new row with provided values; defaults `delegation_type="View Only"`, `scope_type="all"` |
| Active delegation already exists | **Merges** — `project_names` and `applications` are appended (deduplicated); other fields only change if explicitly sent |
| Existing `scope_type=project`, caller omits `scope_type` | Keeps `project` — scope is **not** downgraded to `all` |
| Caller explicitly sends `scope_type=all` | Overrides existing scope to `all` |
| Caller omits `delegation_type` | Keeps existing delegation type unchanged |
| Caller omits `valid_from` / `valid_to` | Keeps existing validity window unchanged |

**Example — first delegation (creates new):**
```json
{
  "delegate_user": "jane@iitg.ac.in",
  "delegation_type": "View Only",
  "scope_type": "project",
  "project_names": "[\"PRJ-REG-2026-00001\"]",
  "valid_to": "2026-12-31 00:00:00"
}
```

**Example — add more projects to existing delegation (merges):**
```json
{
  "delegate_user": "jane@iitg.ac.in",
  "project_names": "[\"PRJ-REG-2026-00002\", \"PRJ-REG-2026-00003\"]"
}
```
> Only `delegate_user` and `project_names` needed. Existing projects, scope_type, delegation_type and validity are preserved.

> `project_names` and `applications` must be sent as **JSON strings** (stringify the array before sending).

**Success response:**
```json
{
  "message": {
    "status": "success",
    "name": "DEL-2026-00001"
  }
}
```

**Validation errors thrown by backend:**

| Condition | Error message |
|---|---|
| `delegate_user` does not exist or is disabled | `User 'x@...' does not exist or is disabled.` |
| Delegating to self | `You cannot delegate to yourself.` |
| Invalid `delegation_type` | `Invalid delegation_type. Allowed: ...` |
| Invalid `scope_type` | `Invalid scope_type. Allowed: ...` |
| `scope_type=project` with no projects | `At least one project is required when scope_type is 'project'.` |
| `scope_type=application` with no applications | `At least one application is required when scope_type is 'application'.` |
| Project not owned by current user | `Project 'PRJ-...' does not belong to or is not assigned to you.` |
| Not a Permanent Employee | `Only users with the Permanent Employee role can manage delegations.` |

---

### 5. Revoke a Delegation

**Use when:** User clicks the Revoke / Remove button on a delegation card.

```
POST /api/method/rndopsapp.rndopsapp.api.undelegate_user
```

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `delegation_name` | string | **yes** | The `name` field from `get_active_delegations` (e.g. `DEL-2026-00001`) |

**Example:**
```json
{
  "delegation_name": "DEL-2026-00001"
}
```

**Success response:**
```json
{
  "message": {
    "status": "success"
  }
}
```

**Errors:**

| Condition | Error |
|---|---|
| Delegation not found | `Delegation 'DEL-...' not found.` |
| Not the delegator and not System Manager | `You are not authorised to revoke this delegation.` |

---

## Scope Type UI Logic

```
scope_type = "all"
  → No project/application picker needed
  → Label: "All Projects & Applications"

scope_type = "project"
  → Show multi-select populated from get_delegate_scope().projects
  → project_names = JSON.stringify(selectedProjectNames)
  → Label: "Selected Projects"

scope_type = "application"
  → Show multi-select populated from get_delegate_scope().applications
  → applications = JSON.stringify(selectedApplicationNames)
  → Label: "Selected Applications"
```

---

## Delegation Type Behaviour (for display only)

| Type | What the delegate can do |
|---|---|
| `View Only` | See documents in list and detail view |
| `View and Edit` | See and edit documents |
| `Workflow Action` | Perform workflow transitions on documents |

> The backend computes this. The frontend does **not** need to enforce it — just display the type on delegation cards.

---

## Visibility — How It Works Automatically

Once a delegation is active, **no frontend query changes are needed**. Frappe list views for the following doctypes automatically include delegated records for the logged-in user:

- Project Registration
- Travel
- TA DA Settlement
- Temporary Advance
- Advance Settlement
- Reimbursement
- Direct Purchase
- Disbursal of Consultancy
- Disbursal of Honorarium
- Loan Request
- Indent General Form
- Indent Cum Sanction Sheet
- Recruitment Adhoc Contractual

**Example:** User B has an active delegation from User A →
- B opens the Travel list → sees both B's and A's travel records automatically
- A revokes the delegation → B's next page load shows only B's records

---

## Datetime Format

All datetime fields (`valid_from`, `valid_to`, `revoked_at`) use:

```
YYYY-MM-DD HH:MM:SS
```

Example: `"2026-12-31 23:59:59"`

Pass `null` or omit the field to leave it unrestricted.

---

## Suggested UI Checklist

- [ ] Delegate User search — autocomplete using `search_delegate_users`
- [ ] Delegation type selector — `View Only` / `View and Edit` / `Workflow Action`
- [ ] Scope type selector — `all` / `project` / `application`
- [ ] Project multi-select — shown only when `scope_type = project`, options from `get_delegate_scope().projects`
- [ ] Application multi-select — shown only when `scope_type = application`, options from `get_delegate_scope().applications`
- [ ] Optional validity date pickers — `valid_from` / `valid_to`
- [ ] Active delegations list — loaded from `get_active_delegations()`
- [ ] Revoke button per delegation card — calls `undelegate_user(name)`
- [ ] Error toast for all backend validation errors
- [ ] Refresh delegation list after create or revoke
