# Delegate User — Implementation Reference

## Overview

Allows a **Permanent Employee** (User A) to delegate visibility/access of their projects and applications to another user (User B). When B logs in, documents where `pi_webmail`, `head_approver`, or `owner` = A can be included in B's visible records.

---

## Files

| File | Purpose |
|---|---|
| `rndopsapp/rndopsapp/delegate_user/delegate_user.py` | All logic — helpers + API implementations |
| `rndopsapp/rndopsapp/delegate_user/__init__.py` | Package marker |
| `rndopsapp/rndopsapp/doctype/user_delegation/user_delegation.json` | DocType definition |
| `rndopsapp/rndopsapp/doctype/user_delegation/user_delegation.py` | DocType controller |
| `rndopsapp/rndopsapp/api.py` | 5 whitelisted wrappers (lines 1058–1110) |

> After deploy run: `bench migrate`

---

## DocType — `User Delegation`

**Autoname:** `DEL-{YYYY}-{#####}`

| Field | Type | Notes |
|---|---|---|
| `delegator_user` | Link → User | Always set to `session.user` on insert |
| `delegate_user` | Link → User | The user receiving access |
| `enabled` | Check | Default 1 |
| `delegation_type` | Select | `View Only` / `View and Edit` / `Workflow Action` |
| `scope_type` | Select | `all` / `project` / `application` |
| `project_names` | Long Text | JSON array of Project Registration names |
| `applications` | Long Text | JSON array of application doc names |
| `valid_from` | Datetime | Optional start of validity window |
| `valid_to` | Datetime | Optional end of validity window |
| `revoked_at` | Datetime | Set on revocation, read-only |
| `revoked_by` | Link → User | Set on revocation, read-only |
| `remarks` | Small Text | Optional notes |

**Permissions:**
- `Permanent Employee` — read, write, create
- `System Manager` — full access

---

## Whitelisted API Endpoints

All 5 endpoints are at `rndopsapp.rndopsapp.api.*`

---

### 1. `search_delegate_users`

```
GET /api/method/rndopsapp.rndopsapp.api.search_delegate_users
     ?query=<string>
```

**Auth:** Permanent Employee role required.

Returns all enabled users matching `query` against `name / full_name / email`. Excludes self, Administrator, Guest.

**Response:**
```json
{
  "message": [
    {
      "label": "Full Name",
      "value": "user@iitg.ac.in",
      "email": "user@iitg.ac.in",
      "full_name": "Full Name"
    }
  ]
}
```

---

### 2. `get_delegate_scope`

```
GET /api/method/rndopsapp.rndopsapp.api.get_delegate_scope
     ?user=<email>   (optional; ignored unless System Manager)
```

**Auth:** Permanent Employee role required.

Returns all projects and applications belonging to / assigned to the current user, plus the users already delegated by them.

**Project query matches:** `pi_webmail`, `pi_userid`, `owner`, `head_approver`

**Application doctypes covered:**

| DocType | Webmail Field | Project Field |
|---|---|---|
| Travel | `webmail_id_travel` | `travel_project_number` |
| TA DA Settlement | `webmail_id` | `project_no` |
| Temporary Advance | `applicant_webmail` | `project_name` |
| Advance Settlement | *(owner only)* | `project_name` |
| Reimbursement | `applicant_webmail` | `project_number` |
| Direct Purchase | *(owner only)* | — |
| Disbursal of Consultancy | `webmail_id` | — |
| Disbursal of Honorarium | `webmail_id` | — |
| Loan Request | `loan_for_webmail_id` | — |
| Indent General Form | `igf_webmail_id` | — |
| Indent Cum Sanction Sheet | `icss_applicant_webmail_id` | — |
| Recruitment Adhoc Contractual | `webmail_id` | — |

**Response:**
```json
{
  "message": {
    "users": [ { "label": "...", "value": "...", "email": "...", "full_name": "..." } ],
    "projects": [
      {
        "name": "PRJ-0001",
        "project_title": "...",
        "project_no": "...",
        "workflow_state": "...",
        "pi_webmail": "...",
        "owner": "..."
      }
    ],
    "applications": [
      {
        "doctype": "Travel",
        "name": "TRV-0001",
        "title": "TRV-0001",
        "project_name": "PRJ-0001",
        "project_no": null,
        "workflow_state": "Draft",
        "owner": "a@iitg.ac.in"
      }
    ]
  }
}
```

---

### 3. `get_active_delegations`

```
GET /api/method/rndopsapp.rndopsapp.api.get_active_delegations
     ?user=<email>   (optional; ignored unless System Manager)
```

**Auth:** Permanent Employee role required.

Returns all enabled, non-revoked delegations created by the current user.

**Response:**
```json
{
  "message": [
    {
      "name": "DEL-2026-00001",
      "delegate_user": "b@iitg.ac.in",
      "delegate_user_name": "User B",
      "delegation_type": "View Only",
      "scope_type": "project",
      "project_count": 3,
      "application_count": 0,
      "valid_from": null,
      "valid_to": null,
      "enabled": 1
    }
  ]
}
```

---

### 4. `delegate_user`

```
POST /api/method/rndopsapp.rndopsapp.api.delegate_user
```

| Parameter | Type | Required | Default |
|---|---|---|---|
| `delegate_user` | email | yes | — |
| `delegation_type` | string | no | `View Only` |
| `scope_type` | string | no | `all` |
| `project_names` | JSON array / string | no | `[]` |
| `applications` | JSON array / string | no | `[]` |
| `valid_from` | Datetime string | no | null |
| `valid_to` | Datetime string | no | null |

**Auth:** Permanent Employee role required.

**Validations:**
- `delegate_user` must exist and be enabled
- Cannot delegate to self
- `delegation_type` must be one of: `View Only`, `View and Edit`, `Workflow Action`
- `scope_type` must be one of: `all`, `project`, `application`
- If `scope_type=project` — at least one project required; each must belong to session user
- If `scope_type=application` — at least one application required
- `delegator_user` is always `frappe.session.user` — never taken from request

Creates a new delegation or updates an existing active one for the same pair.

**Response:**
```json
{ "message": { "status": "success", "name": "DEL-2026-00001" } }
```

---

### 5. `undelegate_user`

```
POST /api/method/rndopsapp.rndopsapp.api.undelegate_user
```

| Parameter | Type | Required |
|---|---|---|
| `delegation_name` | string | yes |

**Auth:** Permanent Employee role required. Only the original `delegator_user` or a System Manager can revoke.

Sets `enabled=0`, `revoked_at=now`, `revoked_by=session.user`.

**Response:**
```json
{ "message": { "status": "success" } }
```

---

## Internal Helpers (available app-wide)

### `get_visible_as_users(user=None)`

```python
from rndopsapp.rndopsapp.delegate_user.delegate_user import get_visible_as_users

visible = get_visible_as_users()
# → ["a@iitg.ac.in", "b@iitg.ac.in"]
```

Returns `[user, *delegator_users]` — all users whose documents should be visible to `user`. Filters out expired, disabled, or revoked delegations. Use this in `get_list` queries:

```python
frappe.get_all("Project Registration",
    filters={"pi_webmail": ["in", get_visible_as_users()]})
```

---

### `is_active_delegation(delegator_user, delegate_user, doctype=None, docname=None, action_type="read")`

```python
from rndopsapp.rndopsapp.delegate_user.delegate_user import is_active_delegation

is_active_delegation("a@iitg.ac.in", "b@iitg.ac.in", action_type="write")
```

| `action_type` | Allowed delegation types |
|---|---|
| `read` | View Only, View and Edit, Workflow Action |
| `write` | View and Edit, Workflow Action |
| `workflow` | Workflow Action only |

Returns `True` if a valid, in-scope, in-window delegation exists. Scope is checked against `project_names` / `applications` JSON lists when `scope_type` is not `all`.

---

## Security Rules

| Rule | Enforcement |
|---|---|
| Only Permanent Employee can call any API | `_require_permanent_employee()` at top of each function |
| `delegator_user` always = `session.user` | Set in code; DocType `before_insert` also enforces it |
| Cannot delegate to self | Checked in `delegate_user()` and DocType `validate()` |
| Only delegator or System Manager can revoke | Checked in `undelegate_user()` |
| Expired / disabled / revoked rows excluded | `_ACTIVE_FILTERS` + `_row_is_time_valid()` applied everywhere |
| System Manager can inspect any user's data | `_resolve_target_user()` allows override only for System Manager |
| Frontend-provided `user` param ignored for non-managers | `_resolve_target_user()` falls back to `session.user` |

---

## Permission Query Design — Isolation Rules

Registered in `hooks.py` under `permission_query_conditions` for all 13 application doctypes.

All hooks call `_build_permission_query(user, table, fields)` in `delegate_user.py`.

### Rule: Delegation never reduces existing access

The two permission systems — Frappe role/if_owner and delegation — are completely independent. Delegation only **adds** visibility; it never restricts what a user could already see.

### Decision tree inside `_build_permission_query`

```
1. System Manager → return ""   (no restriction ever)

2. No active delegations for this user
   → return ""   (Frappe's native role + if_owner rules run untouched)

3. Active delegations exist  AND  user has any role with if_owner=0 on this doctype
   → return ""   (unrestricted role already covers all records including delegator's)

4. Active delegations exist  AND  user's read access is entirely if_owner=1
   → return  (field IN (me, delegator1, delegator2, ...))
      replaces Frappe's implicit "owner = me" with the expanded delegation-aware list
```

### Helper added: `_user_has_unrestricted_read(user_roles, doctype)`

Queries `DocPerm` (permlevel=0, read=1) for the doctype and returns `True` if any of the user's roles has `if_owner=0`. Only called when active delegations exist (step 3 above) to avoid unnecessary DB queries on every list view.

### Doctypes registered and their expansion fields

| DocType | Fields checked in WHERE expansion |
|---|---|
| Project Registration | `pi_webmail`, `pi_userid`, `owner`, `head_approver` |
| Travel | `webmail_id_travel`, `owner` |
| TA DA Settlement | `webmail_id`, `owner` |
| Temporary Advance | `applicant_webmail`, `owner` |
| Advance Settlement | `owner` |
| Reimbursement | `applicant_webmail`, `owner` |
| Direct Purchase | `owner` |
| Disbursal of Consultancy | `webmail_id`, `owner` |
| Disbursal of Honorarium | `webmail_id`, `owner` |
| Loan Request | `loan_for_webmail_id`, `owner` |
| Indent General Form | `igf_webmail_id`, `owner` |
| Indent Cum Sanction Sheet | `icss_applicant_webmail_id`, `owner` |
| Recruitment Adhoc Contractual | `webmail_id`, `owner` |

---

## Pending Task & Task Registry — `ignore_permissions=True`

`get_pending_task` and `get_task_registry` in `module_registry.py` use `frappe.get_list` internally to fetch documents across multiple doctypes for approval-inbox and task-history views.

**Problem after delegation:** The `permission_query_conditions` hooks restrict list results to records owned by / assigned to the current user. Approvers (HoS, Dean, Ado_RnD, etc.) need to see other users' documents pending their action — the permission query was filtering those out, returning empty results.

**Fix:** All `frappe.get_list` calls inside both functions use `ignore_permissions=True`. This is safe because:

- Both functions call `frappe.has_permission(dt, "read")` (role check) before processing each doctype
- `get_pending_task` filters by workflow state + role-to-state mapping + `head_field` email matching
- `get_task_registry` filters by `modified_by = current_user` and an explicit `allowed_roles` list
- `limit_page_length=1000` on all three calls
