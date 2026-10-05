# Incident — Project-Scoped Delegation Showed Empty/Incomplete Application Lists

> 2026-08-18. Two bugs, both fixed in `delegate_user.py`, both verified
> against live production data. No frontend changes were made or needed.

## Reported symptom

Project `2627C-0217-CLEG0985SENT` (Project Registration `2026063001001441`),
owned by `senthilmurugan@iitg.ac.in`, was project-scope delegated to
`s_kumar@iitg.ac.in` (`DEL-2026-02207`, `delegation_type="Workflow Action"`).
`s_kumar` successfully created a new Direct Purchase application on behalf of
`senthilmurugan` via `create_application_on_behalf` — but when viewing the
project's Direct Purchase list in the frontend
(`prornd-ui/src/pages/ProjectDetailsOverview.tsx:1662`, a plain
`GET /api/resource/Direct Purchase?filters=[["project_no","=",...]]` call),
neither `senthilmurugan`'s original Direct Purchase document nor s_kumar's
own on-behalf-created one showed up correctly as expected for a delegate.

## Root cause 1 — two different identifier spaces for "project"

`User Delegation.project_names` always stores Project Registration's
internal `name` (its autoname primary key, e.g. `"2026063001001441"`) — this
is what `delegate_user()`'s ownership check plucks
(`frappe.get_all("Project Registration", ..., pluck="name")`).

But several application doctypes' own "project" field stores Project
Registration's **human-readable** `project_no` instead (e.g.
`"2627C-0217-CLEG0985SENT"`) — a completely different string, for the same
project. Confirmed against live data:

| DocType | Field | Stores |
|---|---|---|
| Travel | `travel_project_number` | `project_no` (confirmed, 5/5 sample rows) |
| TA DA Settlement | `project_no` | `project_no` (confirmed) |
| Reimbursement | `project_number` | `project_no` (confirmed, 5/5 sample rows) |
| Direct Purchase | `project_no` | `project_no` (confirmed — this is the doctype in the report) |
| Advance Settlement | `project_name` | Project Registration `.name` — **correct already**, this field is a proper `Link` to Project Registration |
| Temporary Advance | `project_name` | **Inconsistent free text** — some rows hold a `.name` value, others hold the full project *title* string. Confirmed via a live sample: 0 of 7 non-empty rows matched either `name` or `project_no` cleanly. This is a data-quality problem, not something fixable in code — left unresolved, see "Known unresolved issue" below. |

The delegation's scope-resolution code (`_row_scope_names()`,
`delegate_user.py:228`) was filtering these doctypes directly by
`{project_field: ["in", project_names]}` — i.e. searching for the Project
Registration `.name` inside a field that actually holds `project_no`. That
comparison can never match, so a `scope_type='project'` delegation granted
**zero** visibility into Travel, TA DA Settlement, Reimbursement, or Direct
Purchase, regardless of correct field-name registration.

This also affected the write side: `create_application_on_behalf()` was
setting the sibling doctype's project field directly to the incoming
`project_name` param (a Project Registration `.name`) — for Direct Purchase
this would have written the wrong value (the internal ID instead of the
human-readable code) into `project_no` once the field mapping existed.

### Fix

Added a registry of which doctypes need name→project_no resolution, and a
helper to do it, in `delegate_user.py`:

```python
# delegate_user.py:214
_PROJECT_FIELD_USES_PROJECT_NO = {"Travel", "TA DA Settlement", "Reimbursement", "Direct Purchase"}

# delegate_user.py:217
def _resolve_project_no_values(project_names):
    """Map Project Registration `name` values to their `project_no` values."""
    ...
```

`_row_scope_names()` (`delegate_user.py:228`) now resolves through this
before filtering, for both the list-scope path and (via
`_scoped_doc_names_for_doctype()`) the `permission_query_conditions` path.
`create_application_on_behalf()` (`delegate_user.py:991`, resolution logic
around line 1043) resolves the same way before setting the new document's
project field, so on-behalf creates for these four doctypes now store the
correct `project_no` value, not the Project Registration internal ID.

Advance Settlement and Project Registration itself were left untouched —
they already correctly use `.name`.

## Root cause 2 — a separate crash bug found while verifying the fix

While confirming the fix against real data, calling
`_scoped_doc_names_for_doctype()` directly threw:

```
AttributeError: __dict__
  File ".../delegate_user.py", line 279, in _scoped_doc_names_for_doctype
    cache = frappe.local.__dict__.setdefault("_delegation_scope_cache", {})
  File ".../werkzeug/local.py", line 88, in __getattr__
    raise AttributeError(name)
```

`frappe.local` is a Werkzeug `Local` proxy, not a plain object — it doesn't
expose a `__dict__` the way this code assumed. **This meant every
project/application-scoped delegation crashed with a 500 error** the moment
list scoping needed to resolve a restricted delegator, rather than silently
returning incomplete data. This is more severe than root cause 1 and was
purely a bug in this session's own earlier implementation, not a pre-existing
issue.

### Fix

```python
# delegate_user.py:279
cache = getattr(frappe.local, "_delegation_scope_cache", None)
if cache is None:
    cache = {}
    frappe.local._delegation_scope_cache = cache
```
Standard Frappe idiom for per-request state on `frappe.local` (`getattr`/
`setattr`, matching how `frappe.local.flags`/`frappe.local.request_cache`
etc. are used elsewhere in the framework) instead of reaching into an
internal `__dict__` that doesn't exist on this proxy type.

## Verification

Both fixes were verified against the real records via `bench console`,
exercising the actual code paths (not a synthetic test):

```python
_scoped_doc_names_for_doctype("senthilmurugan@iitg.ac.in", "s_kumar@iitg.ac.in", "Direct Purchase")
# -> {'2026073122002313', '2026081322002652'}   (both docs, correct)

frappe.set_user("s_kumar@iitg.ac.in")
frappe.get_list("Direct Purchase", filters={"project_no": "2627C-0217-CLEG0985SENT"}, fields=["name","owner","project_no"])
# -> [
#      {'name': '2026081322002652', 'owner': 's_kumar@iitg.ac.in', 'project_no': '2627C-0217-CLEG0985SENT'},
#      {'name': '2026073122002313', 'owner': 'senthilmurugan@iitg.ac.in', 'project_no': '2627C-0217-CLEG0985SENT'},
#    ]
```

The frontend's actual call (`GET /api/resource/Direct Purchase?filters=[["project_no","=",...]]`,
`ProjectDetailsOverview.tsx:1662`) goes through exactly this code path
(`DatabaseQuery` → `permission_query_conditions` → `direct_purchase_permission_query`
→ `_build_permission_query` → `_scoped_doc_names_for_doctype`), so no
frontend change was needed — confirmed by reading (not modifying) the
frontend source.

## Known unresolved issue — Temporary Advance

`Temporary Advance.project_name` is free text in production, not a reliable
identifier in either space. Project-scoped delegation matching against
Temporary Advance remains best-effort/unreliable until that field's existing
data is cleaned up (or the field is migrated to a proper Link, mirroring
Advance Settlement). Not something code alone can fix — flagged for a
separate decision, not resolved here.
