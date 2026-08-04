# Application-Level Delegation — Backend Plan

## Problem

`User Delegation.scope_type` already supports `all | project | application`, and
`delegate_user()` already validates and stores `project_names` / `applications`.
But enforcement never actually looks at scope:

- `_build_permission_query()` (wired via `permission_query_conditions` for all 13
  doctypes) calls `get_visible_as_users(user)`, which returns **every** delegator
  with any active row — `all`, `project`, or `application` alike — then applies
  `field IN (visible_users)`. That grants the delegate every record the delegator
  owns in that doctype.
- No `has_permission` hook is registered (`hooks.py` has it commented out), so
  opening a single document isn't scope-checked either.
- `is_active_delegation()` already implements the correct per-document scope
  check but is never called from anywhere.

**Net effect today:** `scope_type=project` and `scope_type=application` are
functionally identical to `scope_type=all`. This is an over-sharing bug, not
just a missing feature — fix it as a security-priority item, not a
nice-to-have.

---

## Goal

Make `scope_type=application` (and `project`, which shares the same code path)
actually restrict:

1. List-view rows to only the named documents / documents under the named projects.
2. Single-document read access to the same set.
3. Write / workflow-transition access, gated additionally by `delegation_type`.

Additionally, broaden who can use delegation at all: today every endpoint is
gated to `Permanent Employee` only. Application-level delegation should be
usable by any legitimate project participant, not just permanent staff.

---

## Access control — open to all authenticated users

**Current state:** `_require_permanent_employee()` is the sole gate on every
delegation function (`search_delegate_users`, `get_delegate_scope`,
`get_active_delegations`, `delegate_user`, `undelegate_user`) — it hard-checks
`"Permanent Employee" in frappe.get_roles(frappe.session.user)`. Anyone
without that exact role gets a 403.

**Requested change:** allow all users — not just Permanent Employee —
including approved Project Staff *and* students.

**Why a role-allowlist doesn't work here:** Project Staff has a clean sync
path (`Project Staff Details._sync_project_staff_to_user()` assigns role
`"project staff"` to a real `User` on approval), so it could be added to a
role list. Students have no equivalent — there is **no "Student" role and no
doctype that syncs student data into a `User` role** anywhere in this app
(`studentdetails_`, `academic_student_info`, etc. are plain data doctypes with
no `frappe.get_doc("User"...)` calls). There's nothing to put in an allowlist
for students, and any future role (research scholar, JRF, SRF, etc.) would hit
the same problem — the allowlist would need to be maintained forever as new
user categories show up.

**Plan: drop role-based gating, gate on "is a real logged-in user" instead.**

1. Replace `_require_permanent_employee()` with `_require_authenticated_user()`:
   ```python
   def _require_authenticated_user():
       if frappe.session.user == "Guest":
           frappe.throw(
               "You must be logged in to manage delegations.",
               frappe.PermissionError,
           )
   ```
   Swap the call at the top of all 5 delegation functions. This admits
   Permanent Employees, project staff, students, and any other logged-in
   account uniformly — no role enumeration needed, and it never goes stale as
   new user categories are added.

2. Ownership stays the real access boundary, unchanged. `get_delegate_scope()`
   and `_query_applications()` already match by email
   (`pi_webmail`/`pi_userid`/`owner`/`head_approver`, per-doctype
   webmail/owner fields) — role-agnostic today. A student or project staff
   member only ever sees and delegates *their own* projects/applications; the
   gate change only decides who's allowed to open the feature, not what they
   can see inside it.

3. **Candidate search (`search_delegate_users`) already queries `User` by
   name/full_name/email with no role filter** — it already returns anyone
   enabled, including students and project staff, once the gate above stops
   blocking them from calling it. No search-side change is required to
   include students specifically; the earlier plan to also query `Project
   Staff Details` for `ps_designation` labeling is still worth doing for
   picker UX, but is now a nice-to-have, not a requirement for coverage.

4. **Flag before implementing:** this genuinely opens delegation to *every*
   enabled login, including any bare/external/vendor accounts with no project
   role at all. Since ownership-based scoping means an account with no
   projects/applications simply has nothing to delegate, the practical blast
   radius is low — but confirm this is the intended tradeoff before shipping,
   since it's a deliberate move away from role-gating entirely.

5. Update the DocType-level permission on `User Delegation`
   (`user_delegation.json`) — currently grants read/write/create only to
   `Permanent Employee`. Since the API gate no longer checks roles, either
   grant these permissions to `All` (Frappe's built-in universal role) or rely
   solely on the API-level checks (`ignore_permissions=True` is already used
   in `delegate_user()`/`undelegate_user()` for writes) and lock the DocType
   permissions down to read-only-via-API. Decide based on whether direct
   desk/report access to the `User Delegation` list should also open up.

---

## Open design question — `applications` storage format

Today `applications` is a flat JSON array of doc names with no doctype tag:
`["TRV-2026-00001", "LOAN-2026-00002"]`. To scope a specific doctype's list
query we need to know which names belong to it.

| Option | Approach | Tradeoff |
|---|---|---|
| A | Infer doctype from name prefix at query time | No schema/migration, but fragile — breaks if a naming series changes, and does a stringy prefix match per row |
| B (recommended) | Store `[{"doctype": "Travel", "name": "TRV-2026-00001"}, ...]` | Correct and explicit; requires a data migration for existing rows and a frontend payload change |

`get_delegate_scope()` already returns `doctype` alongside `name` for every
application row, so the frontend picker already has what it needs to send
Option B's shape — no new backend read endpoint required, only a change to
what gets POSTed back in `delegate_user()`.

**Decide before implementation starts.** The rest of this plan assumes Option B.

---

## Implementation steps

### 1. Migrate `applications` storage

- Update `User Delegation.applications` semantics to store `{doctype, name}` pairs.
- One-off migration (`patches/.../fix_delegation_application_scope.py`):
  for every existing `User Delegation` row with `scope_type=application`,
  resolve each bare name's doctype by checking `frappe.db.exists(doctype, name)`
  against the 12 registered application doctypes, and rewrite the JSON.
- Bump `applications` field description in `user_delegation.json` to document the new shape.

### 2. Add a scope-resolution helper (`delegate_user.py`)

```python
def _scoped_doc_names_for_doctype(delegator_user, delegate_user, doctype):
    """
    Return None if delegate has unrestricted (`all`) access to doctype from
    delegator_user, otherwise a set of doc names they may see (possibly empty).
    """
```

- Pull active, time-valid rows from `delegator_user` → `delegate_user` (reuse
  the same query shape as `is_active_delegation`).
- If any row has `scope_type == "all"` → return `None` (unrestricted, current behavior).
- Otherwise union:
  - names from `applications` tagged for this `doctype`
  - doc names under `project_names`, resolved via each doctype's `project_field`
    from `_APPLICATION_DOCTYPES` (e.g. `travel_project_number in (...)`)
- Cache per-request (`frappe.local` or `functools.lru_cache` keyed on args) since
  this will be called once per row-owning delegator per list query.

### 3. Rewrite `_build_permission_query`

Currently: one `field IN (visible_users)` clause for everyone.

New behavior, per doctype call:

1. Split `get_visible_as_users(user)` into:
   - **unrestricted delegators** — have an active `all`-scope row to this user
   - **restricted delegators** — only `project` / `application` scoped rows
2. Unrestricted delegators: keep today's `field IN (...)` clause (unchanged).
3. Restricted delegators: for each, resolve `_scoped_doc_names_for_doctype(...)`
   and add `` `tab<Doctype>`.`name` IN (scoped_names) `` as an additional OR
   branch (skip entirely if the set is empty).
4. Combine unrestricted-field-IN and restricted-name-IN branches with `OR`,
   wrapped exactly as today.
5. Keep the existing fast paths: no delegations → `""`; System Manager → `""`;
   unrestricted role (`if_owner=0`) → `""`.

### 4. Add `has_permission` hooks

- New shared function `_document_has_delegated_access(doc, user, permission_type)`:
  - No active delegation for this doc's owner → defer to Frappe (return `None`/no-op)
  - Active `all`-scope delegation → allow read; allow write/submit only if
    `delegation_type` permits (`is_active_delegation` already encodes this table)
  - Active `project`/`application`-scope delegation → allow only if
    `doc.name` is inside `_scoped_doc_names_for_doctype(...)`, same
    `delegation_type` gating for write/workflow
- Register in `hooks.py` under `has_permission = {...}` for Project Registration
  and all 12 application doctypes, pointing at per-doctype wrapper functions
  (mirrors the existing `permission_query_conditions` registration pattern).
- This is what finally makes `is_active_delegation()` live code instead of an
  unused exported helper.

### 5. Tests

- Unit: `_scoped_doc_names_for_doctype` with mixed `all` / `project` /
  `application` rows from the same delegator, including one revoked and one
  expired row (must be excluded).
- Integration: delegate with `scope_type=application` limited to one Travel
  doc → delegate's Travel list contains exactly that doc plus their own, not
  every Travel record the delegator owns.
- Integration: opening a non-scoped document directly by URL/API as the
  delegate is rejected (`has_permission` hook), even though it previously
  succeeded via the blanket list-query bug.
- Regression: `scope_type=all` delegations behave identically to today.
- Regression: users with an unrestricted role still short-circuit without the
  extra scope queries running.

### 6. Rollout

- This tightens security for any delegation currently configured as
  `project`/`application` scope — those delegates will lose access to records
  outside the configured scope the moment this ships. Treat as a breaking
  change for those users, not a silent patch.
- Notify any Permanent Employees with existing scoped (non-`all`) delegations
  before deploying, since their delegate's visible record count will shrink.
- Deploy migration → `bench migrate` → `bench clear-cache`.
- Coordinate with the frontend payload change (see frontend plan) so
  `delegate_user()` isn't receiving the old flat-name format after the backend
  starts expecting `{doctype, name}` pairs.
