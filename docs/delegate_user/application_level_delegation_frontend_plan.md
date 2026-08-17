# Application-Level Delegation — Frontend Plan

> **Status: Finalized, ready for implementation.** All open questions were
> resolved on 2026-08-17 (see backend plan for the corresponding decisions).
> Coordinate delivery with the backend plan per §1 and §5 below — the new
> `applications` payload shape must not ship before the backend migration
> lands.

## Context

The backend currently accepts and stores `scope_type=application` but does not
enforce it — a delegate sees everything the delegator owns regardless of which
applications were selected. The backend plan
([application_level_delegation_backend_plan.md](application_level_delegation_backend_plan.md))
fixes that, which changes two things the frontend depends on: the payload
shape for `applications`, and the fact that scope will now visibly restrict
what the delegate sees. Both need frontend changes before/alongside the
backend fix ships.

---

## 0. Open access to all logged-in users (Permanent Employee, project staff, students, ...) [DECIDED: proceed]

Backend plan §"Access control" drops role-based gating entirely — there's no
"Student" role or Student→User sync in this codebase to allowlist against
(unlike Project Staff, which does sync to a `User` with role `project staff`),
so a role list can never actually cover "all users, students also." The
backend now gates only on "is a real logged-in user"
(`_require_authenticated_user()`). Frontend changes to match:

- **Route guard:** `/delegate-user` currently checks for the `Permanent
  Employee` role before rendering (per `delegation_frontend_guide.md`, "Who
  Can Use This?"). Change this to a plain "is logged in" check (not Guest) —
  drop the role check entirely rather than trying to enumerate an ever-growing
  list of eligible roles. This is a direct behavior change: any authenticated
  user, including students, can now reach the page.
- **Delegate picker labeling:** `search_delegate_users()` already returns any
  enabled `User` by name/full_name/email with no role filter — students and
  project staff will now show up in the autocomplete once the route/API gate
  stops blocking them from calling it. Consider adding a role/designation
  badge (e.g. "Project Staff — JRF", "Student") where derivable, purely for
  picker clarity — not required for coverage, since search already isn't
  role-filtered.
- **No change needed** to the scope pickers (`get_delegate_scope().projects` /
  `.applications`) — already keyed off document ownership by email, not role.
  A student delegator will correctly see only their own
  projects/applications once the route/API gate admits them; if they own
  none, the pickers are simply empty (nothing to delegate) rather than an error.
- **QA:** verify a plain student-only account (no `Permanent Employee` or
  `project staff` role) can open `/delegate-user`, see their own scope (empty
  or populated), create a delegation if they own any applications, and appear
  as a selectable delegate target for others. Also verify a fully logged-out
  (Guest) request is still blocked.

---

## 1. Payload shape change for `applications`

**Current:** frontend sends a flat JSON-stringified array of doc names:
```json
"applications": "[\"TRV-2026-00001\", \"LOAN-2026-00002\"]"
```

**New (backend Option B, decided):** send `{doctype, name}` pairs instead:
```json
"applications": "[{\"doctype\":\"Travel\",\"name\":\"TRV-2026-00001\"},{\"doctype\":\"Loan Request\",\"name\":\"LOAN-2026-00002\"}]"
```

`get_delegate_scope().applications` already returns `doctype` per row today
([delegation_frontend_guide.md](delegation_frontend_guide.md) §2), so the
application multi-select already has both fields available — this is purely a
change to what gets serialized on submit, not a new fetch.

**Action:** gate this change behind the backend deploy — do not ship the new
payload shape until the backend has migrated existing rows and switched
`_scoped_doc_names_for_doctype` to expect it, or existing delegations will
parse as empty scope.

---

## 2. Scope transparency in the UI

Because scope has had no visible effect until now, the existing UI (per
`delegation_frontend_guide.md`'s checklist) only shows *counts*
(`project_count`, `application_count`) on delegation cards. Once scope is
enforced, users need to actually see and manage what's included:

- Expand each delegation card to list the specific projects/applications
  included (not just a count) — e.g. a chip list of `Travel: TRV-2026-00001`.
- Surface this from `get_active_delegations()` — **backend plan §6 now covers
  this**: the response will include resolved `project_names` / `applications`
  lists (post-migration `{doctype, name}` shape) alongside the existing
  counts. No follow-up detail call needed.

---

## 3. Add a "remove item from scope" affordance

`delegate_user()` today only **merges/adds** to `project_names` and
`applications` — there's no way to shrink an existing scoped delegation
without revoking it entirely and starting over. Once scope actually matters,
users will want to remove a single project/application without nuking the
whole delegation.

**Decided:** backend plan §6 adds a `remove` list param to `delegate_user()`
(same call, not a new endpoint) accepting `{doctype, name}` / project-name
entries to remove. Build a per-chip "×" remove control on the delegation card
against this once it ships. Don't build against the current merge-only API —
it can't support it.

---

## 4. Warn on scope-narrowing edits

When a user changes an existing delegation's `scope_type` from `all` to
`project`/`application`, or from a still-being-configured `application` scope
with a wider list, the delegate's access will now *immediately shrink* after
the fix ships. Add a confirmation step:

> "This will restrict {delegate}'s access to only the selected items. They
> will no longer see your other records. Continue?"

This wasn't necessary before because scope changes had no real effect — it
becomes necessary the moment enforcement lands.

---

## 5. Communicate the behavior change to existing users

Any Permanent Employee who previously set up a `project`/`application` scoped
delegation — believing it was already restricting access — will see their
delegate's visibility drop once the backend fix ships (it's actually being
correctly enforced for the first time). Coordinate an in-app notice or
release note timed with the backend deploy so this doesn't read as a bug
report.

---

## 6. QA checklist (re-run against real enforcement)

The existing checklist in `delegation_frontend_guide.md` assumed scope was
cosmetic. Re-verify each item against actual restricted behavior once the
backend fix ships:

- [ ] `scope_type=application` with 1 selected item → delegate sees exactly
      that 1 document in the relevant list view, not the delegator's full list
- [ ] `scope_type=project` → delegate sees only documents under that project
      across all application doctypes, not just Project Registration
- [ ] Delegate cannot open a non-scoped document directly by URL (should now
      403, previously succeeded)
- [ ] Removing the last item from a scoped delegation's list results in zero
      extra visibility (not a silent fallback to unrestricted)
- [ ] `scope_type=all` still behaves exactly as before (no regression)
- [ ] New `{doctype, name}` payload round-trips correctly through create,
      merge-add, and (once built) remove flows
- [ ] Delegation card shows actual included items, not just counts
- [ ] Scope-narrowing confirmation dialog appears when tightening an existing
      delegation
