# Delegate User — Implementation Reference

> **Updated 2026-11-27** — added the create-only
> [`Specific Application`](#specific-application-delegations) delegation type,
> `get_received_delegations` and the Delegation Audit Log.
>
> **Updated 2026-08-17** — application-level scope enforcement, create-on-behalf,
> and the "any authenticated user" access model described here are all live.
> See [application_level_delegation_backend_plan.md](application_level_delegation_backend_plan.md)
> for the design rationale and [known_auth_gaps.md](../security/known_auth_gaps.md)
> for a related, pre-existing, **unfixed** authorization gap in the app's own
> document read/write endpoints — this delegation system does not by itself
> close that gap for every code path (see "Enforcement Reality" below).

## Overview

Allows any authenticated user (User A) to delegate visibility/access of their
projects and applications to another user (User B) — no role requirement.
When B logs in, documents where `pi_webmail`, `head_approver`, or `owner` = A
can be included in B's visible records, and B can act on them according to
the delegation's `delegation_type` and `scope_type`.

The exception is [`Specific Application`](#specific-application-delegations),
which grants no visibility at all, only the right to create certain
applications.

---

## Specific Application delegations

A picks one or more projects and the application types B may create under them.

| | View Only | View and Edit | Workflow Action | Specific Application |
|---|---|---|---|---|
| Read A's documents | yes | yes | yes | **no** |
| Edit | no | yes | yes | **no** |
| Workflow actions | no | no | yes | **no** |
| Create on behalf | no | yes | yes | listed types and projects only |
| Allowed `scope_type` | any | any | any | `project` only |
| New document's `owner` | — | B | B | **A** |

"No" means delegation grants nothing. It does not take away what B's roles
already allow (see [Enforcement Reality](#enforcement-reality--what-this-system-does-and-doesnt-cover)).

**Rules**

- `allowed_doctypes` takes any of the 12 application doctypes.
- Every project must be A's own as PI or owner (`pi_webmail`, `pi_userid`,
  `owner`). `head_approver` alone does not count for this type.
- Every project must be eligible: `workflow_state = 'Approved'` and a positive
  commitable **or** actual balance in the ledger. Overhead (PDF / DPF) funds are
  read from the overhead ledger. An unreadable ledger counts as ineligible.
- Eligibility is checked when a project is added (only the `project_names` sent
  on that call) and again on every create.
- These delegations live in their own row and are never merged with the other
  types, so one A→B pair can have two active rows. To change a delegation to or
  from this type, revoke the old row and create a new one.
- Access queries filter on `_ACCESS_FILTERS`, which excludes this type:
  `get_visible_as_users()`, `is_active_delegation()`,
  `_scoped_doc_names_for_doctype()` and everything built on them.

---

## Files

| File | Purpose |
|---|---|
| `rndopsapp/rndopsapp/delegate_user/delegate_user.py` | All logic — helpers + API implementations |
| `rndopsapp/rndopsapp/delegate_user/__init__.py` | Package marker |
| `rndopsapp/rndopsapp/doctype/user_delegation/user_delegation.json` | DocType definition |
| `rndopsapp/rndopsapp/doctype/user_delegation/user_delegation.py` | DocType controller |
| `rndopsapp/rndopsapp/api.py` | 7 whitelisted wrappers |
| `rndopsapp/rndopsapp/doctype/delegation_audit_log/` | Audit log of create-on-behalf calls |
| `rndopsapp/rndopsapp/doctype/user_delegation/test_user_delegation.py` | Tests |
| `rndopsapp/hooks.py` | Permission hooks, plus `before_insert` / `before_save` doc events for create-on-behalf |
| `rndopsapp/patchs/fix_delegation_application_scope.py` | Migrates `applications` from flat name arrays to `{doctype, name}` pairs |

> After deploy run: `bench migrate`, `bench clear-cache`, then restart.

---

## DocType — `User Delegation`

**Autoname:** `DEL-{YYYY}-{#####}`

| Field | Type | Notes |
|---|---|---|
| `delegator_user` | Link → User | Always set to `session.user` on insert |
| `delegate_user` | Link → User | The user receiving access |
| `enabled` | Check | Default 1 |
| `delegation_type` | Select | `View Only` / `View and Edit` / `Workflow Action` / `Specific Application` |
| `scope_type` | Select | `all` / `project` / `application` |
| `project_names` | Long Text | JSON array of Project Registration names |
| `applications` | Long Text | JSON array of `{"doctype": ..., "name": ...}` pairs (migrated from a flat name array — see the migration patch above) |
| `allowed_doctypes` | Long Text | `Specific Application` only: JSON array of doctypes B may create |
| `valid_from` | Datetime | Optional start of validity window |
| `valid_to` | Datetime | Optional end of validity window |
| `revoked_at` | Datetime | Set on revocation, read-only |
| `revoked_by` | Link → User | Set on revocation, read-only |
| `remarks` | Small Text | Optional notes |

**Permissions:**
- `All` (built-in universal role) — read only
- `System Manager` — full access

Because `read` is open to `All`, desk/report visibility of `User Delegation`
rows is separately restricted by `user_delegation_permission_query()` (in
`hooks.py` → `permission_query_conditions`) to rows where the current user is
the `delegator_user` or `delegate_user` — otherwise any logged-in user could
list every delegation in the system.

---

## DocType — `Delegation Audit Log`

One row for every authenticated `create_application_on_behalf` call, successful
or failed. Read-only, visible to `System Manager`.

| Field | Notes |
|---|---|
| `actual_user` | The session user (delegate) |
| `delegator_user` | As requested |
| `delegation` | The `User Delegation` that covered the call; empty if none did |
| `application_doctype` | As requested |
| `application_name` | The new document; empty on failure |
| `project_name` | As requested |
| `status` | `Success` / `Failed` |
| `error` | Failure message |

---

## Whitelisted API Endpoints

All 7 endpoints are at `rndopsapp.rndopsapp.api.*`

---

### 1. `search_delegate_users`

```
GET /api/method/rndopsapp.rndopsapp.api.search_delegate_users
     ?query=<string>
```

**Auth:** Any authenticated user (not Guest).

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

**Auth:** Any authenticated user (not Guest).

Returns all projects and applications belonging to / assigned to the current user, plus the users already delegated by them and those delegations.

**Project query matches:** `pi_webmail`, `pi_userid`, `owner`, `head_approver`

**Application doctypes covered:**

| DocType | Webmail Field | Project Field |
|---|---|---|
| Travel | `webmail_id_travel` | `travel_project_number` |
| TA DA Settlement | `webmail_id` | `project_no` |
| Temporary Advance | `applicant_webmail` | `project_name` |
| Advance Settlement | *(owner only)* | `project_name` |
| Reimbursement | `applicant_webmail` | `project_number` |
| Direct Purchase | *(owner only)* | `project_no` |
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
    ],
    "delegations": [
      {
        "name": "DEL-2026-00001",
        "delegate_user": "b@iitg.ac.in",
        "delegation_type": "Specific Application",
        "scope_type": "project",
        "project_names": ["PRJ-0001"],
        "allowed_doctypes": ["Travel"],
        "valid_from": null,
        "valid_to": null
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

**Auth:** Any authenticated user (not Guest).

Returns all enabled, non-revoked delegations created by the current user,
including expired and not-yet-started ones.

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
      "project_names": ["PRJ-2026-00003"],
      "applications": [{"doctype": "Travel", "name": "TRV-2026-00001"}],
      "allowed_doctypes": [],
      "project_count": 1,
      "application_count": 1,
      "valid_from": null,
      "valid_to": null,
      "enabled": 1
    }
  ]
}
```

`allowed_doctypes` is `[]` for every type except `Specific Application`.

`project_names` / `applications` are the resolved, already-parsed arrays
(added alongside the pre-existing counts) — no follow-up call needed to show
actual scope contents on a delegation card.

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
| `project_names` | JSON array / string of names | no | `[]` — **merged** into existing list |
| `applications` | JSON array / string of `{doctype, name}` pairs | no | `[]` — **merged** into existing list |
| `remove_project_names` | JSON array / string of names | no | `[]` — subtracted after the merge above |
| `remove_applications` | JSON array / string of `{doctype, name}` pairs | no | `[]` — subtracted after the merge above |
| `allowed_doctypes` | JSON array / string of doctypes | `Specific Application` only | `[]` — **merged** into existing list |
| `remove_allowed_doctypes` | JSON array / string of doctypes | no | `[]` — subtracted after the merge above |
| `valid_from` | Datetime string | no | null |
| `valid_to` | Datetime string | no | null |

**Auth:** Any authenticated user (not Guest).

`applications` and `remove_applications` use the shape `{"doctype": "Travel",
"name": "TRV-2026-00001"}` — `doctype` must be one of the 12 registered
application doctypes (see the table above), or the call throws. `project_names`
/ `remove_project_names` are plain Project Registration names.
`remove_project_names` / `remove_applications` can be sent alone, without
`project_names`/`applications`, to shrink an existing delegation without
resending the rest.

**Validations:**
- `delegate_user` must exist and be enabled
- Cannot delegate to self
- `delegation_type` must be one of: `View Only`, `View and Edit`, `Workflow Action`, `Specific Application`
- `scope_type` must be one of: `all`, `project`, `application`
- If `scope_type=project` — at least one project required; each must belong to session user
- If `scope_type=application` — at least one application required
- Each application entry's `doctype` must be a registered application doctype
- `delegator_user` is always `frappe.session.user` — never taken from request

**Additional validations for `Specific Application`:**
- `scope_type` must be `project` (required on create, may be omitted on update)
- The merged result must keep at least one project and one `allowed_doctypes`
  entry; to remove the last one, revoke the delegation
- Every `allowed_doctypes` entry must be a registered application doctype, else
  `'{doctype}' is not a delegable application doctype.`
- Every sent project must be the delegator's as PI or owner
- Every sent project not also being removed must be eligible, else
  `Project '{project_no}' is not eligible: {reason}.`
- `applications` is ignored. For other types, `allowed_doctypes` is ignored.

```json
{
  "delegate_user": "b@iitg.ac.in",
  "delegation_type": "Specific Application",
  "scope_type": "project",
  "project_names": "[\"PRJ-REG-...\"]",
  "applications": "[]",
  "allowed_doctypes": "[\"Travel\", \"Direct Purchase\"]",
  "valid_from": "2026-12-01 00:00:00",
  "valid_to": "2026-12-31 23:59:59"
}
```

Creates a new delegation or updates an existing active one for the same pair.
`Specific Application` calls only update a `Specific Application` row; calls with
another type only update a row of another type. A call with no `delegation_type`
updates the other-type row if there is one, otherwise the `Specific Application`
row, so **always send `delegation_type`** when editing the latter.
If a name appears in both an add list and the corresponding remove list in
the same call, removal wins (applied after the merge).

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

**Auth:** Any authenticated user (not Guest). Only the original `delegator_user` or a System Manager can revoke.

Sets `enabled=0`, `revoked_at=now`, `revoked_by=session.user`.

**Response:**
```json
{ "message": { "status": "success" } }
```

---

### 6. `get_received_delegations`

```
GET /api/method/rndopsapp.rndopsapp.api.get_received_delegations
```

**Auth:** Any authenticated user (not Guest). No parameters.

Returns the enabled, non-revoked delegations of **every type** where the session
user is the delegate and today is within the validity dates. `project_names` is
resolved to project details, and is `[]` unless `scope_type` is `project`. A
listed project may have become ineligible since; creation re-checks.

**Response:**
```json
{
  "message": [
    {
      "name": "DEL-2026-00001",
      "delegator_user": "a@iitg.ac.in",
      "delegator_user_name": "User A",
      "delegation_type": "Specific Application",
      "scope_type": "project",
      "project_names": [
        {"name": "PRJ-REG-...", "project_title": "...", "project_no": "..."}
      ],
      "allowed_doctypes": ["Travel", "Direct Purchase"],
      "valid_from": "2026-12-01 00:00:00",
      "valid_to": null
    }
  ]
}
```

---

### 7. `create_application_on_behalf`

```
POST /api/method/rndopsapp.rndopsapp.api.create_application_on_behalf
```

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `doctype` | string | yes | Must be one of the 12 registered application doctypes |
| `delegator_user` | email | yes | The project owner this document is created for |
| `project_name` | string | conditional | Project Registration `name`. Always required under `Specific Application`; otherwise required for doctypes with a project field in the table above |
| `fields` | dict / JSON string | no | Field values for the new document, including all mandatory ones |

**Auth:** Any authenticated user (not Guest), plus an enabled, in-date delegation
from `delegator_user` that covers the call, either:

1. **`View and Edit` / `Workflow Action`** with `scope_type='all'`, or
   `scope_type='project'` and `project_name` in `project_names`.
   `scope_type='application'` never grants creation.
2. **`Specific Application`** with `doctype` in `allowed_doctypes`,
   `project_name` in `project_names`, and the project still eligible.

If both cover the call, the first applies.

**The new document**

| | Under (1) | Under (2) |
|---|---|---|
| Owner-identifying field (e.g. `webmail_id_travel`) | `delegator_user` | `delegator_user` |
| Frappe `owner` | the delegate | `delegator_user` |
| Project fields | the registry field only (none if the doctype has none) | all fields below, from `project_name` |
| `fields` | blocklist removed | blocklist, unknown fields and server-set fields removed |

Blocklist: `name`, `owner`, `docstatus`, `workflow_state`, `creation`,
`modified`, `modified_by`, `idx`, `doctype`, `flags`.

**Project fields under `Specific Application`** (`_ON_BEHALF_PROJECT_FIELDS`).
The create form does not need to fill these.

| DocType | Gets `name` | Gets `project_no` | Gets `project_title` |
|---|---|---|---|
| Travel | `travel_project_title` | `travel_project_number` | |
| TA DA Settlement | | `project_no` | |
| Temporary Advance | `project_name` | `project_code` | |
| Advance Settlement | `project_name` | `project_code` | |
| Reimbursement | `project_name` | `project_number` | |
| Direct Purchase | | `project_no` | |
| Disbursal of Consultancy | | `disbursal_project_number` | `project_title` |
| Disbursal of Honorarium | `project_name` | `project_no` | |
| Loan Request | `project_name` | `project_number` | |
| Indent General Form | `igf_project_title` | `igf_project_code` | |
| Indent Cum Sanction Sheet | `project_ref` | `project_no` | |
| Recruitment Adhoc Contractual | | `upfa_project_code` | `upfa_project_title` |

This mapping is deliberately separate from `_APPLICATION_DOCTYPES`: adding
project fields there would widen what existing project-scoped delegations can
read.

Two doc events enforce this on insert: `apply_on_behalf_owner` (`before_insert`)
sets `owner`, and `verify_on_behalf_scope` (`before_save`) rejects the document
if `fetch_from` or a controller changed a server-set value, e.g. a TA DA
Settlement linked to a Travel of another project.

Under (2) the delegate gets no access to the document afterwards through
delegation: they cannot reopen, edit, submit or attach files to it, so send
everything in one call.

**Errors**

| Case | Error |
|---|---|
| Nothing covers the call | `PermissionError`: `You are not authorised to create a {doctype} on behalf of {delegator_user} for project '{project_name}'.` |
| Project no longer eligible (`Specific Application`) | `ValidationError`: `Project '{project_no}' is not eligible: {reason}.` |
| `project_name` missing where required | `ValidationError` |
| A server-set value was overwritten (`Specific Application`) | `PermissionError` |
| `doctype` not registered, `delegator_user` unknown, disabled or self | `ValidationError` |

**Response:**
```json
{ "message": { "status": "success", "name": "TRV-2026-00042" } }
```

> This endpoint writes via `doc.insert(ignore_permissions=True)` after its own
> delegation check — same pattern as every other write in this app (see
> `known_auth_gaps.md` for why that's the established convention here, not a
> shortcut specific to this function). Every call is recorded in
> `Delegation Audit Log`.

---

## Internal Helpers (available app-wide)

### `get_visible_as_users(user=None)`

```python
from rndopsapp.rndopsapp.delegate_user.delegate_user import get_visible_as_users

visible = get_visible_as_users()
# → ["a@iitg.ac.in", "b@iitg.ac.in"]
```

Returns `[user, *delegator_users]` — all users whose documents should be visible to `user`. Filters out expired, disabled, or revoked delegations, and `Specific Application` ones. Use this in `get_list` queries:

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

`Specific Application` never matches any action.

Returns `True` if a valid, in-scope, in-window delegation exists. For
`project`/`application` scope, `docname` is checked against the row's
resolved scope via `_row_scope_names()` — for `project` scope this correctly
resolves through each doctype's `project_field` (a fix; the original version
only matched `project_names` directly against Project Registration names,
never actually covering application doctypes under a delegated project).

---

### `require_document_access(doc, action_type="read")`

```python
from rndopsapp.rndopsapp.delegate_user.delegate_user import require_document_access

doc = frappe.get_doc("Travel", docname)
require_document_access(doc, action_type="read")   # raises PermissionError if disallowed
```

Raises `frappe.PermissionError` unless the session user owns `doc` (via any
of its owner-identifying fields, or Frappe's `owner`), holds an active
delegation from an owner covering this action/document, or is System Manager
/ Administrator.

**This is the real enforcement point for this app's own whitelisted
functions** (`save_travel`, `get_travel_commit_details`, etc.) — they call
`frappe.get_doc()` / `doc.save(ignore_permissions=True)` directly and never
go through Frappe's native permission system, so `has_permission` hooks (see
below) never run for them. As of 2026-11-27, **nothing outside
`delegate_user.py` calls `require_document_access()`**: it has not been
retrofitted into the pre-existing read/write functions across the 13 application
doctypes — see [known_auth_gaps.md](../security/known_auth_gaps.md) for the
full inventory of what's still unguarded and why that was left out of scope.

---

### `has_delegated_access(doc, ptype=None, user=None)`

Registered in `hooks.py` under `has_permission` for all 13 doctypes.
**Read this before relying on it:** Frappe's `has_permission` hook is a
deny-only gate — returning `True`/`None` (all this function ever does) never
grants access beyond what the caller's role + Frappe's own `owner` field +
DocShare already allow. It only matters for generic Frappe access paths
(desk, report view) that this app's frontend doesn't use for these doctypes.
It is harmless to leave registered, but do not mistake it for real
enforcement of the app's own API functions — that's `require_document_access()` above.

---

## Security Rules

| Rule | Enforcement |
|---|---|
| Any authenticated (non-Guest) user can call the delegation API | `_require_authenticated_user()` at top of each function |
| `delegator_user` always = `session.user` | Set in code; DocType `before_insert` also enforces it |
| Cannot delegate to self | Checked in `delegate_user()` and DocType `validate()` |
| Only delegator or System Manager can revoke | Checked in `undelegate_user()` |
| Expired / disabled / revoked rows excluded | `_ACTIVE_FILTERS` + `_row_is_time_valid()` applied everywhere |
| System Manager can inspect any user's data | `_resolve_target_user()` allows override only for System Manager |
| Frontend-provided `user` param ignored for non-managers | `_resolve_target_user()` falls back to `session.user` |
| `create_application_on_behalf` requires scope-covering delegation | `_access_delegation_for_create()` / `_specific_rows_for_doctype()` |
| `Specific Application` grants no read, write or workflow access | `_ACCESS_FILTERS` |
| `Specific Application` projects must be Approved and funded | `_require_eligible_project()`, on delegate and on create |
| Every create-on-behalf call is audited | `Delegation Audit Log` |
| Desk/report listing of `User Delegation` limited to parties involved | `user_delegation_permission_query()` |

---

## Enforcement Reality — what this system does and doesn't cover

- **List views** (Project Registration + 12 application doctypes): real,
  functional. `permission_query_conditions` correctly expands/restricts
  visibility per delegation scope.
- **`create_application_on_behalf`**: real, functional. Does its own
  delegation-scope check before `insert(ignore_permissions=True)`.
- **Role permissions are independent of delegation** (observed on the
  development site, 2026-11-27): `Custom DocPerm` gives roles such as
  `Permanent Employee` and `All_ProRnd_User` read access with `if_owner=0` on
  the application doctypes. A delegate holding such a role can read other
  users' documents through generic Frappe access, including under a
  `Specific Application` delegation.
- **Single-document read/write via this app's own API functions**
  (`save_travel`, `get_loan_request_fields`, etc.): **not covered** by
  anything built for delegation. These functions predate delegation, bypass
  Frappe's permission system entirely, and were never retrofitted with
  `require_document_access()`. This is a pre-existing gap, not something
  delegation introduced or fixed — see
  [known_auth_gaps.md](../security/known_auth_gaps.md).
- **Generic Frappe desk/report access**: covered by `has_delegated_access()`
  registered as `has_permission`, for whatever it's worth given this app's
  frontend doesn't route through that path for these doctypes.

---

## Permission Query Design — Isolation Rules

Registered in `hooks.py` under `permission_query_conditions` for all 13
application doctypes, **plus `User Delegation` itself** (see Security Rules
above). `has_permission` is also registered for the 13 doctypes (see
"Enforcement Reality" above for what that hook does and doesn't accomplish).

All 13 doctype hooks call `_build_permission_query(user, table, fields)` in
`delegate_user.py`; each per-doctype wrapper (`travel_permission_query`,
etc.) is generated by `_permission_query_for(doctype)`, which pulls `fields`
from `_DOCTYPE_OWNER_FIELDS` — a single source of truth shared with
`has_delegated_access()` and `require_document_access()`, instead of
duplicating field lists per function.

### Rule: Delegation never reduces existing access

`Specific Application` rows are ignored here altogether. The two permission systems — Frappe role/if_owner and delegation — are completely independent. Delegation only **adds** visibility; it never restricts what a user could already see.

### Decision tree inside `_build_permission_query`

```
1. System Manager → return ""   (no restriction ever)

2. No active delegations for this user
   → return ""   (Frappe's native role + if_owner rules run untouched)

3. Active delegations exist  AND  user has any role with if_owner=0 on this doctype
   → return ""   (unrestricted role already covers all records including delegator's)

4. Active delegations exist  AND  user's read access is entirely if_owner=1
   → split delegators into unrestricted (active "all"-scope row to this user)
     and restricted (only project/application-scope rows):
       - unrestricted delegators + self → field IN (...) branch, as before
       - each restricted delegator with a non-empty resolved scope → an
         additional `` `name` IN (scoped_names) `` OR-branch, via
         _scoped_doc_names_for_doctype()
   → combine all branches with OR
```

Before this rewrite, `project`/`application`-scoped delegations were
functionally identical to `all`-scope in list views — the query only ever
did a blanket `field IN (...)` regardless of scope_type. That's fixed now:
restricted delegators only contribute the specific document names their
scope actually covers.

### Helper added: `_user_has_unrestricted_read(user_roles, doctype)`

Queries `DocPerm` (permlevel=0, read=1) for the doctype and returns `True` if any of the user's roles has `if_owner=0`. Only called when active delegations exist (step 3 above) to avoid unnecessary DB queries on every list view.

### Doctypes registered and their expansion fields

`_DOCTYPE_OWNER_FIELDS` in `delegate_user.py` (used by permission_query,
has_permission, require_document_access, and scope resolution alike):

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
