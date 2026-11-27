"""
Delegate User — backend implementation for rndopsapp.

Public surface (called from api.py whitelisted wrappers):
  search_delegate_users(query="")
  get_delegate_scope(user=None)
  get_active_delegations(user=None)
  get_received_delegations()
  delegate_user(delegate_user, delegation_type, scope_type, project_names, applications,
                 remove_project_names, remove_applications, valid_from, valid_to,
                 allowed_doctypes, remove_allowed_doctypes)
  undelegate_user(delegation_name)
  create_application_on_behalf(doctype, delegator_user, project_name=None, fields=None)

Helpers available to the rest of the app:
  get_visible_as_users(user=None)
  is_active_delegation(delegator_user, delegate_user, doctype=None, docname=None, action_type="read")
  require_document_access(doc, action_type="read")
    — call at the top of any single-document read/write API function in this
      app (these bypass Frappe's native permission system, see
      has_delegated_access()'s docstring below for why that hook alone isn't
      enough).

"Specific Application" delegations are create-only: the delegate may create the
listed application types under the listed projects and gets no read, write or
workflow access to anything. Every access query below therefore filters on
_ACCESS_FILTERS; only create_application_on_behalf() honours them.

Registered in hooks.py:
  permission_query_conditions — list-view scope, via *_permission_query() below
  doc_events                  — apply_on_behalf_owner / verify_on_behalf_scope
  has_permission              — matters only for generic Frappe desk/report
                                 access to these doctypes, via has_delegated_access()
"""

import json

import frappe
from frappe.utils import flt, now_datetime
from rndopsapp.rndopsapp.role_delegation.service import refuse_while_acting

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_json_list(value):
    """Parse a JSON string into a list; return [] on any error or empty input."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _require_authenticated_user():
    """Raise PermissionError if the session user is not logged in (Guest)."""
    if frappe.session.user == "Guest":
        frappe.throw(
            "You must be logged in to manage delegations.",
            frappe.PermissionError,
        )


def _is_system_manager():
    return "System Manager" in frappe.get_roles(frappe.session.user)


def _resolve_target_user(user):
    """Return *user* if provided and caller is System Manager, otherwise session user."""
    if user and user != frappe.session.user and not _is_system_manager():
        return frappe.session.user
    return user or frappe.session.user


# ---------------------------------------------------------------------------
# Delegation validity helpers
# ---------------------------------------------------------------------------

_ACTIVE_FILTERS = {"enabled": 1, "revoked_at": ["is", "not set"]}

_SPECIFIC_APPLICATION = "Specific Application"

# Active rows that grant access to existing documents.
_ACCESS_FILTERS = {**_ACTIVE_FILTERS, "delegation_type": ["!=", _SPECIFIC_APPLICATION]}


def _active_rows_for_delegate(delegate_user):
    """All enabled, non-revoked, access-granting User Delegation rows where
    delegate_user matches."""
    return frappe.get_all(
        "User Delegation",
        filters={"delegate_user": delegate_user, **_ACCESS_FILTERS},
        fields=["delegator_user", "valid_from", "valid_to", "delegation_type",
                "scope_type", "project_names", "applications"],
        limit=0,
    )


def _row_is_time_valid(row, now):
    if row.valid_from and row.valid_from > now:
        return False
    if row.valid_to and row.valid_to < now:
        return False
    return True


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_visible_as_users(user=None):
    """
    Return [user, *delegator_users] for all active delegations where
    delegate_user = user.  Used by query helpers elsewhere in the app.
    """
    user = user or frappe.session.user
    now = now_datetime()

    rows = _active_rows_for_delegate(user)
    delegators = [r.delegator_user for r in rows if _row_is_time_valid(r, now)]
    return [user] + delegators


def is_active_delegation(
    delegator_user, delegate_user, doctype=None, docname=None, action_type="read"
):
    """
    Return True if an active delegation from delegator_user to delegate_user
    exists and covers the requested action / document.

    action_type: "read" | "write" | "workflow"
    """
    now = now_datetime()

    rows = frappe.get_all(
        "User Delegation",
        filters={
            "delegator_user": delegator_user,
            "delegate_user": delegate_user,
            **_ACCESS_FILTERS,
        },
        fields=["delegation_type", "scope_type", "project_names", "applications",
                "valid_from", "valid_to"],
        limit=0,
    )

    for row in rows:
        if not _row_is_time_valid(row, now):
            continue

        # Check action permission
        if action_type == "write" and row.delegation_type == "View Only":
            continue
        if action_type == "workflow" and row.delegation_type != "Workflow Action":
            continue

        if row.scope_type == "all":
            return True

        if not doctype or not docname:
            continue

        row_names = _row_scope_names(row, doctype)
        if row_names and docname in row_names:
            return True

    return False


# ---------------------------------------------------------------------------
# Application doctype registry
# Each tuple: (display_name, frappe_doctype, webmail_field, project_field)
# webmail_field / project_field may be None if not present on that doctype.
# ---------------------------------------------------------------------------

_APPLICATION_DOCTYPES = [
    ("Travel",                        "Travel",                        "webmail_id_travel",         "travel_project_number"),
    ("TA DA Settlement",              "TA DA Settlement",              "webmail_id",                "project_no"),
    ("Temporary Advance",             "Temporary Advance",             "applicant_webmail",         "project_name"),
    ("Advance Settlement",            "Advance Settlement",            None,                        "project_name"),
    ("Reimbursement",                 "Reimbursement",                 "applicant_webmail",         "project_number"),
    ("Direct Purchase",               "Direct Purchase",               None,                        "project_no"),
    ("Disbursal of Consultancy",      "Disbursal of Consultancy",      "webmail_id",                None),
    ("Disbursal of Honorarium",       "Disbursal of Honorarium",       "webmail_id",                None),
    ("Loan Request",                  "Loan Request",                  "loan_for_webmail_id",       None),
    ("Indent General Form",           "Indent General Form",           "igf_webmail_id",            None),
    ("Indent Cum Sanction Sheet",     "Indent Cum Sanction Sheet",     "icss_applicant_webmail_id", None),
    ("Recruitment Adhoc Contractual", "Recruitment Adhoc Contractual", "webmail_id",                None),
]


# ---------------------------------------------------------------------------
# Owner-field / project-field registries derived from _APPLICATION_DOCTYPES.
# Single source of truth for both permission_query and has_permission hooks,
# plus scope resolution (_row_scope_names / _scoped_doc_names_for_doctype).
# ---------------------------------------------------------------------------

_PROJECT_FIELD_BY_DOCTYPE = {
    doctype: project_field
    for _, doctype, _, project_field in _APPLICATION_DOCTYPES
    if project_field
}

_DOCTYPE_OWNER_FIELDS = {
    "Project Registration": ["pi_webmail", "pi_userid", "owner", "head_approver"],
    **{
        doctype: ([webmail_field, "owner"] if webmail_field else ["owner"])
        for _, doctype, webmail_field, _ in _APPLICATION_DOCTYPES
    },
}

# Doctypes whose project_field stores Project Registration's human-readable
# `project_no` (e.g. "2627C-0217-CLEG0985SENT") rather than its internal
# `name` (e.g. "2026063001001441") — confirmed against live data 2026-08-18.
# `User Delegation.project_names` always stores `name` values (see
# delegate_user()'s ownership check, which plucks "name"), so matching these
# doctypes' project_field requires resolving name -> project_no first.
# Advance Settlement is NOT here — its project_name field is a proper Link to
# Project Registration and correctly stores `name` already. Temporary
# Advance is deliberately NOT here either: its project_name field is free
# text in practice (mixes `name` values and full project titles across rows,
# confirmed via live data) and cannot be reliably resolved to either
# identifier space by code — treat project-scoped matching against Temporary
# Advance as best-effort/unreliable until that field's data is cleaned up.
_PROJECT_FIELD_USES_PROJECT_NO = {"Travel", "TA DA Settlement", "Reimbursement", "Direct Purchase"}


def _resolve_project_no_values(project_names):
    """Map Project Registration `name` values to their `project_no` values."""
    if not project_names:
        return []
    return frappe.get_all(
        "Project Registration",
        filters={"name": ["in", project_names]},
        pluck="project_no",
    )


def _row_scope_names(row, doctype):
    """
    Resolve a single User Delegation row's scope to the set of *doctype*
    document names it covers.  Returns None for scope_type == "all"
    (everything), otherwise a (possibly empty) set of covered names.
    """
    if row.scope_type == "all":
        return None

    if row.scope_type == "application":
        return {
            entry["name"]
            for entry in _safe_json_list(row.applications)
            if isinstance(entry, dict) and entry.get("doctype") == doctype and entry.get("name")
        }

    if row.scope_type == "project":
        project_names = _safe_json_list(row.project_names)
        if not project_names:
            return set()
        if doctype == "Project Registration":
            return set(project_names)
        project_field = _PROJECT_FIELD_BY_DOCTYPE.get(doctype)
        if not project_field:
            return set()
        match_values = (
            _resolve_project_no_values(project_names)
            if doctype in _PROJECT_FIELD_USES_PROJECT_NO
            else project_names
        )
        if not match_values:
            return set()
        return set(frappe.get_all(
            doctype,
            filters={project_field: ["in", match_values]},
            pluck="name",
            limit=0,
        ))

    return set()


def _scoped_doc_names_for_doctype(delegator_user, delegate_user, doctype):
    """
    Return None if the delegate has unrestricted ("all") access to *doctype*
    from delegator_user, otherwise the union of document names covered by
    their restricted (project/application) delegation rows.

    Cached per-request on frappe.local since this is called once per
    row-owning delegator per list query.
    """
    cache = getattr(frappe.local, "_delegation_scope_cache", None)
    if cache is None:
        cache = {}
        frappe.local._delegation_scope_cache = cache
    cache_key = (delegator_user, delegate_user, doctype)
    if cache_key in cache:
        return cache[cache_key]

    now = now_datetime()
    rows = frappe.get_all(
        "User Delegation",
        filters={
            "delegator_user": delegator_user,
            "delegate_user": delegate_user,
            **_ACCESS_FILTERS,
        },
        fields=["scope_type", "project_names", "applications", "valid_from", "valid_to"],
        limit=0,
    )

    names = set()
    for row in rows:
        if not _row_is_time_valid(row, now):
            continue
        row_names = _row_scope_names(row, doctype)
        if row_names is None:
            cache[cache_key] = None
            return None
        names |= row_names

    cache[cache_key] = names
    return names


def _query_applications(user):
    """
    Return normalized application objects for all doctypes in the registry.
    Skips doctypes that are not installed or whose fields differ — never crashes.
    """
    results = []

    for display_name, doctype, webmail_field, project_field in _APPLICATION_DOCTYPES:
        try:
            if not frappe.db.exists("DocType", doctype):
                continue

            meta_fields = {f.fieldname for f in frappe.get_meta(doctype).fields}

            # Build OR filter: owner OR webmail_field
            or_filters = [["owner", "=", user]]
            if webmail_field and webmail_field in meta_fields:
                or_filters.append([webmail_field, "=", user])

            fetch = ["name", "owner", "workflow_state"]
            if project_field and project_field in meta_fields:
                fetch.append(project_field)
            if webmail_field and webmail_field in meta_fields:
                fetch.append(webmail_field)

            rows = frappe.get_all(
                doctype,
                or_filters=or_filters,
                fields=fetch,
                limit=0,
            )

            for r in rows:
                results.append({
                    "doctype":         display_name,
                    "name":            r.get("name"),
                    "title":           r.get("name"),
                    "project_name":    r.get(project_field) if project_field else None,
                    "project_no":      None,
                    "workflow_state":  r.get("workflow_state"),
                    "owner":           r.get("owner"),
                })

        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"get_delegate_scope: error querying {doctype}",
            )
            continue

    return results


# Fields create_application_on_behalf() fills from the chosen project under a
# "Specific Application" delegation: {fieldname: Project Registration column}.
# Kept apart from _APPLICATION_DOCTYPES on purpose: adding project fields there
# would widen what existing project-scoped delegations can read.
_ON_BEHALF_PROJECT_FIELDS = {
    "Travel":                        {"travel_project_title": "name", "travel_project_number": "project_no"},
    "TA DA Settlement":              {"project_no": "project_no"},
    "Temporary Advance":             {"project_name": "name", "project_code": "project_no"},
    "Advance Settlement":            {"project_name": "name", "project_code": "project_no"},
    "Reimbursement":                 {"project_name": "name", "project_number": "project_no"},
    "Direct Purchase":               {"project_no": "project_no"},
    "Disbursal of Consultancy":      {"disbursal_project_number": "project_no", "project_title": "project_title"},
    "Disbursal of Honorarium":       {"project_name": "name", "project_no": "project_no"},
    "Loan Request":                  {"project_name": "name", "project_number": "project_no"},
    "Indent General Form":           {"igf_project_title": "name", "igf_project_code": "project_no"},
    "Indent Cum Sanction Sheet":     {"project_ref": "name", "project_no": "project_no"},
    "Recruitment Adhoc Contractual": {"upfa_project_code": "project_no", "upfa_project_title": "project_title"},
}


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

_VALID_DELEGATION_TYPES = {"View Only", "View and Edit", "Workflow Action", _SPECIFIC_APPLICATION}
_VALID_SCOPE_TYPES = {"all", "project", "application"}


# ---------------------------------------------------------------------------
# Project eligibility ("Specific Application")
# ---------------------------------------------------------------------------

def _fetch_project_balances(project_no):
    """
    Ledger balances for a project number, in get_project_available_amounts' shape.

    Overhead (PDF / DPF) funds are read directly: get_project_available_amounts
    ownership-checks them against the session user, which would refuse a delegate.
    """
    from rndopsapp.rndopsapp.commitPayment import get_project_available_amounts
    from rndopsapp.rndopsapp.overhead_fund import get_overhead_summary, resolve_overhead_fund

    overhead = resolve_overhead_fund(project_no)
    if overhead:
        return get_overhead_summary(overhead[0], overhead[1])
    return get_project_available_amounts(project_no)


def _require_eligible_project(project_name):
    """Throw unless the project is Approved and the ledger shows a positive
    commitable or actual balance. An unreadable ledger counts as ineligible."""
    project = frappe.db.get_value(
        "Project Registration",
        project_name,
        ["name", "project_no", "project_title", "workflow_state"],
        as_dict=True,
    )
    if not project:
        frappe.throw(f"Project '{project_name}' does not exist.")

    label = project.project_no or project.name

    def _reject(reason):
        frappe.throw(f"Project '{label}' is not eligible: {reason}.")

    if project.workflow_state != "Approved":
        _reject(f"it is not approved (current state: {project.workflow_state or 'none'})")

    if not project.project_no:
        _reject("it has no project number, so it has no funds in the ledger")

    try:
        result = _fetch_project_balances(project.project_no) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Delegation: project balance check failed")
        result = {}

    if result.get("status") != "success":
        _reject("its funds could not be verified with the ledger, please try again shortly")

    data = result.get("data") or {}
    if flt(data.get("committable")) <= 0 and flt(data.get("actualBalance")) <= 0:
        _reject("it has no available funds")


# ---------------------------------------------------------------------------
# API implementations (called by whitelisted wrappers in api.py)
# ---------------------------------------------------------------------------

def search_delegate_users(query=""):
    """
    Return up to 20 active, non-self Users matching *query* (email / full_name).
    Caller must be logged in (any authenticated user).
    """
    _require_authenticated_user()

    current_user = frappe.session.user
    query = (query or "").strip()

    base_filters = [
        ["name", "not in", [current_user, "Administrator", "Guest"]],
        ["enabled", "=", 1],
    ]

    if query:
        rows = frappe.get_all(
            "User",
            or_filters=[
                ["name", "like", f"%{query}%"],
                ["full_name", "like", f"%{query}%"],
                ["email", "like", f"%{query}%"],
            ],
            filters=base_filters,
            fields=["name", "full_name", "email"],
            limit=0,
        )
    else:
        rows = frappe.get_all(
            "User",
            filters=base_filters,
            fields=["name", "full_name", "email"],
            limit=0,
        )

    return [
        {
            "label":     r.full_name or r.name,
            "value":     r.name,
            "email":     r.name,
            "full_name": r.full_name or r.name,
        }
        for r in rows
    ]


def get_delegate_scope(user=None):
    """
    Return projects and applications that belong to / are assigned to *user*,
    plus the list of users already delegated by *user* and those delegations.
    """
    _require_authenticated_user()
    target = _resolve_target_user(user)

    # ── Current delegates for this user ──────────────────────────────────────
    delegations = frappe.get_all(
        "User Delegation",
        filters={"delegator_user": target, **_ACTIVE_FILTERS},
        fields=["name", "delegate_user", "delegation_type", "scope_type",
                "project_names", "allowed_doctypes", "valid_from", "valid_to"],
        limit=0,
    )
    delegate_names = [d.delegate_user for d in delegations]

    users = []
    if delegate_names:
        user_rows = frappe.get_all(
            "User",
            filters={"name": ["in", delegate_names], "enabled": 1},
            fields=["name", "full_name"],
            limit=0,
        )
        users = [
            {
                "label":     u.full_name or u.name,
                "value":     u.name,
                "email":     u.name,
                "full_name": u.full_name or u.name,
            }
            for u in user_rows
        ]

    # ── Projects ──────────────────────────────────────────────────────────────
    project_rows = frappe.get_all(
        "Project Registration",
        or_filters=[
            ["pi_webmail",    "=", target],
            ["pi_userid",     "=", target],
            ["owner",         "=", target],
            ["head_approver", "=", target],
        ],
        fields=["name", "project_title", "project_no", "workflow_state",
                "pi_webmail", "owner"],
        limit=0,
    )
    projects = [
        {
            "name":           p.name,
            "project_title":  p.project_title,
            "project_no":     p.project_no,
            "workflow_state": p.workflow_state,
            "pi_webmail":     p.pi_webmail,
            "owner":          p.owner,
        }
        for p in project_rows
    ]

    # ── Applications ──────────────────────────────────────────────────────────
    applications = _query_applications(target)

    for d in delegations:
        d["project_names"] = _safe_json_list(d.project_names)
        d["allowed_doctypes"] = _safe_json_list(d.allowed_doctypes)

    return {
        "users": users,
        "projects": projects,
        "applications": applications,
        "delegations": delegations,
    }


def get_active_delegations(user=None):
    """
    Return all active (enabled, non-revoked) delegations created by *user*.
    """
    _require_authenticated_user()
    target = _resolve_target_user(user)

    rows = frappe.get_all(
        "User Delegation",
        filters={"delegator_user": target, **_ACTIVE_FILTERS},
        fields=[
            "name", "delegate_user", "delegation_type", "scope_type",
            "project_names", "applications", "allowed_doctypes",
            "valid_from", "valid_to", "enabled",
        ],
        limit=0,
    )

    # Batch-resolve delegate user full names
    delegate_names = [r.delegate_user for r in rows]
    name_map = {}
    if delegate_names:
        user_rows = frappe.get_all(
            "User",
            filters={"name": ["in", delegate_names]},
            fields=["name", "full_name"],
            limit=0,
        )
        name_map = {u.name: u.full_name or u.name for u in user_rows}

    return [
        {
            "name":               r.name,
            "delegate_user":      r.delegate_user,
            "delegate_user_name": name_map.get(r.delegate_user, r.delegate_user),
            "delegation_type":    r.delegation_type,
            "scope_type":         r.scope_type,
            "project_names":      _safe_json_list(r.project_names),
            "applications":       _safe_json_list(r.applications),
            "allowed_doctypes":   _safe_json_list(r.allowed_doctypes),
            "project_count":      len(_safe_json_list(r.project_names)),
            "application_count":  len(_safe_json_list(r.applications)),
            "valid_from":         r.valid_from,
            "valid_to":           r.valid_to,
            "enabled":            r.enabled,
        }
        for r in rows
    ]


def get_received_delegations():
    """
    Active delegations, currently within their validity dates, where the session
    user is the delegate.  project_names is resolved to project details.
    """
    _require_authenticated_user()
    now = now_datetime()

    rows = [
        r for r in frappe.get_all(
            "User Delegation",
            filters={"delegate_user": frappe.session.user, **_ACTIVE_FILTERS},
            fields=["name", "delegator_user", "delegation_type", "scope_type",
                    "project_names", "allowed_doctypes", "valid_from", "valid_to"],
            limit=0,
        )
        if _row_is_time_valid(r, now)
    ]
    if not rows:
        return []

    name_map = {
        u.name: u.full_name or u.name
        for u in frappe.get_all(
            "User",
            filters={"name": ["in", [r.delegator_user for r in rows]]},
            fields=["name", "full_name"],
            limit=0,
        )
    }

    # project_names is only meaningful for project scope; merged rows can carry
    # stale entries under other scopes.
    projects_by_row = {
        r.name: _safe_json_list(r.project_names) if r.scope_type == "project" else []
        for r in rows
    }
    all_projects = {p for names in projects_by_row.values() for p in names}
    project_map = {}
    if all_projects:
        project_map = {
            p.name: p
            for p in frappe.get_all(
                "Project Registration",
                filters={"name": ["in", list(all_projects)]},
                fields=["name", "project_title", "project_no"],
                limit=0,
            )
        }

    return [
        {
            "name":                r.name,
            "delegator_user":      r.delegator_user,
            "delegator_user_name": name_map.get(r.delegator_user, r.delegator_user),
            "delegation_type":     r.delegation_type,
            "scope_type":          r.scope_type,
            "project_names":       [project_map[p] for p in projects_by_row[r.name] if p in project_map],
            "allowed_doctypes":    _safe_json_list(r.allowed_doctypes),
            "valid_from":          r.valid_from,
            "valid_to":            r.valid_to,
        }
        for r in rows
    ]


def _find_active_delegation(delegator_user, delegate_user, delegation_type):
    """
    Name of the row delegate_user() should merge into, or None.

    "Specific Application" lives in its own row, never merged with the access
    types: merging would turn a create-only project list into read access, or
    silently strip an existing delegation's access.  With no delegation_type the
    access row is preferred, falling back to whatever exists.
    """
    base = {"delegator_user": delegator_user, "delegate_user": delegate_user, **_ACTIVE_FILTERS}

    def _lookup(extra):
        return frappe.db.get_value("User Delegation", {**base, **extra}, "name")

    if delegation_type == _SPECIFIC_APPLICATION:
        return _lookup({"delegation_type": _SPECIFIC_APPLICATION})

    access_row = _lookup({"delegation_type": ["!=", _SPECIFIC_APPLICATION]})
    if access_row or delegation_type:
        return access_row
    return _lookup({})


def _dedupe_applications(entries):
    """Deduplicate {doctype, name} dicts by (doctype, name), order preserved.
    Silently drops malformed entries (not a dict, or missing either key)."""
    seen = set()
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        doctype, name = entry.get("doctype"), entry.get("name")
        if not doctype or not name:
            continue
        key = (doctype, name)
        if key in seen:
            continue
        seen.add(key)
        result.append({"doctype": doctype, "name": name})
    return result


def delegate_user(
    delegate_user,
    delegation_type=None,
    scope_type=None,
    project_names=None,
    applications=None,
    remove_project_names=None,
    remove_applications=None,
    valid_from=None,
    valid_to=None,
    allowed_doctypes=None,
    remove_allowed_doctypes=None,
):
    """
    Create or merge a User Delegation row.

    On CREATE  — defaults: delegation_type="View Only", scope_type="all".
    On UPDATE  — only fields explicitly provided are changed:
                 project_names and applications are MERGED (deduplicated),
                 remove_project_names / remove_applications SUBTRACT matching
                 entries (applied after the merge, so a name in both lists
                 ends up removed),
                 scope_type is NOT downgraded (e.g. "project" → "all") unless
                 the caller explicitly passes scope_type="all",
                 delegation_type and validity window are kept unless passed.

    applications entries use the shape {"doctype": ..., "name": ...} — see
    docs/delegate_user/application_level_delegation_backend_plan.md.

    "Specific Application" requires scope_type="project", at least one project
    and at least one allowed_doctypes entry (checked on the merged result), and
    every newly sent project must be the delegator's own (PI or owner),
    Approved and funded.  allowed_doctypes is ignored for other types.

    delegator_user is always frappe.session.user — never trusted from the frontend.
    """
    _require_authenticated_user()
    refuse_while_acting()

    current_user = frappe.session.user

    # ── Validate delegate_user ────────────────────────────────────────────────
    if not frappe.db.exists("User", {"name": delegate_user, "enabled": 1}):
        frappe.throw(f"User '{delegate_user}' does not exist or is disabled.")

    if delegate_user == current_user:
        frappe.throw("You cannot delegate to yourself.")

    # ── Validate enums only when explicitly provided ─────────────────────────
    if delegation_type is not None and delegation_type not in _VALID_DELEGATION_TYPES:
        frappe.throw(
            f"Invalid delegation_type. Allowed: {', '.join(sorted(_VALID_DELEGATION_TYPES))}"
        )

    if scope_type is not None and scope_type not in _VALID_SCOPE_TYPES:
        frappe.throw(
            f"Invalid scope_type. Allowed: {', '.join(sorted(_VALID_SCOPE_TYPES))}"
        )

    # ── Parse incoming scope lists ────────────────────────────────────────────
    incoming_projects = (
        _safe_json_list(project_names)
        if isinstance(project_names, str)
        else list(project_names or [])
    )
    incoming_apps = _dedupe_applications(
        _safe_json_list(applications)
        if isinstance(applications, str)
        else list(applications or [])
    )
    removed_projects = set(
        _safe_json_list(remove_project_names)
        if isinstance(remove_project_names, str)
        else list(remove_project_names or [])
    )
    removed_apps = {
        (e["doctype"], e["name"])
        for e in _dedupe_applications(
            _safe_json_list(remove_applications)
            if isinstance(remove_applications, str)
            else list(remove_applications or [])
        )
    }

    incoming_doctypes = _safe_json_list(allowed_doctypes)
    removed_doctypes = _safe_json_list(remove_allowed_doctypes)

    existing_name = _find_active_delegation(current_user, delegate_user, delegation_type)
    existing = frappe.get_doc("User Delegation", existing_name) if existing_name else None
    effective_type = delegation_type or (existing.delegation_type if existing else "View Only")
    is_specific = effective_type == _SPECIFIC_APPLICATION

    # ── Validate application doctypes against the registry ───────────────────
    valid_app_doctypes = {doctype for _, doctype, _, _ in _APPLICATION_DOCTYPES}
    for entry in incoming_apps:
        if entry["doctype"] not in valid_app_doctypes:
            frappe.throw(f"'{entry['doctype']}' is not a delegable application doctype.")

    if is_specific:
        for doctype in incoming_doctypes:
            if doctype not in valid_app_doctypes:
                frappe.throw(f"'{doctype}' is not a delegable application doctype.")

        effective_scope = scope_type or (existing.scope_type if existing else None)
        if effective_scope != "project":
            frappe.throw("scope_type must be 'project' for a Specific Application delegation.")

        merged = lambda field, incoming, removed: [
            v for v in dict.fromkeys(
                (_safe_json_list(existing.get(field)) if existing else []) + incoming
            )
            if v not in removed
        ]
        if not merged("project_names", incoming_projects, removed_projects):
            frappe.throw("At least one project is required for a Specific Application delegation.")
        if not merged("allowed_doctypes", incoming_doctypes, removed_doctypes):
            frappe.throw(
                "At least one entry in allowed_doctypes is required for a Specific Application delegation."
            )

    # Scope list requirements only enforced when scope_type is explicitly set
    elif scope_type == "project" and not incoming_projects:
        frappe.throw("At least one project is required when scope_type is 'project'.")

    if scope_type == "application" and not incoming_apps:
        frappe.throw("At least one application is required when scope_type is 'application'.")

    # ── Verify ownership of any incoming projects ─────────────────────────────
    if incoming_projects:
        ownership_fields = ["pi_webmail", "pi_userid", "owner"]
        if not is_specific:
            ownership_fields.append("head_approver")
        owned = set(
            frappe.get_all(
                "Project Registration",
                or_filters=[[field, "=", current_user] for field in ownership_fields],
                pluck="name",
                limit=0,
            )
        )
        for prj in incoming_projects:
            if prj not in owned:
                frappe.throw(
                    f"Project '{prj}' does not belong to or is not assigned to you."
                )

    # Only newly sent projects: one that has since run out of funds must not
    # block removing it, or editing the rest.  Creation re-checks every time.
    if is_specific:
        for prj in incoming_projects:
            if prj not in removed_projects:
                _require_eligible_project(prj)

    if existing:
        # ── MERGE into existing delegation ────────────────────────────────────
        doc = existing

        # Merge project_names — deduplicated, order preserved
        merged_projects = list(
            dict.fromkeys(_safe_json_list(doc.project_names) + incoming_projects)
        )
        merged_projects = [p for p in merged_projects if p not in removed_projects]

        # Merge applications — deduplicated by (doctype, name), order preserved
        merged_apps = _dedupe_applications(_safe_json_list(doc.applications) + incoming_apps)
        merged_apps = [
            e for e in merged_apps if (e["doctype"], e["name"]) not in removed_apps
        ]

        # scope_type: only change when caller explicitly passes it
        if scope_type is not None:
            doc.scope_type = scope_type

        # delegation_type: only change when caller explicitly passes it
        if delegation_type is not None:
            doc.delegation_type = delegation_type

        # valid_from / valid_to: only change when caller passes a non-empty value
        if valid_from:
            doc.valid_from = valid_from
        if valid_to:
            doc.valid_to = valid_to

        merged_doctypes = [
            d for d in dict.fromkeys(_safe_json_list(doc.allowed_doctypes) + incoming_doctypes)
            if d not in removed_doctypes
        ]

        doc.project_names = json.dumps(merged_projects) if merged_projects else ""
        doc.applications  = json.dumps(merged_apps)     if merged_apps     else ""
        doc.allowed_doctypes = json.dumps(merged_doctypes) if merged_doctypes else ""
        doc.revoked_at    = None
        doc.revoked_by    = None

    else:
        # ── CREATE new delegation ─────────────────────────────────────────────
        doc = frappe.new_doc("User Delegation")
        doc.delegator_user  = current_user
        doc.delegate_user   = delegate_user
        doc.enabled         = 1
        doc.delegation_type = effective_type
        doc.scope_type      = scope_type      or "all"
        projects = [p for p in dict.fromkeys(incoming_projects) if not (is_specific and p in removed_projects)]
        doctypes = [d for d in dict.fromkeys(incoming_doctypes) if d not in removed_doctypes]
        doc.project_names   = json.dumps(projects)      if projects      else ""
        doc.applications    = json.dumps(incoming_apps) if incoming_apps else ""
        doc.allowed_doctypes = json.dumps(doctypes)     if doctypes      else ""
        doc.valid_from      = valid_from or None
        doc.valid_to        = valid_to   or None

    if is_specific:
        doc.applications = ""
    else:
        doc.allowed_doctypes = ""

    doc.enabled = 1
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "name": doc.name}


# ---------------------------------------------------------------------------
# Permission query hooks — registered in hooks.py
# ---------------------------------------------------------------------------

def _user_has_unrestricted_read(user_roles, doctype):
    """
    Return True if any of the user's roles has unrestricted (if_owner=0) read
    access on *doctype*.  Fetches DocPerm at call time; result is not cached
    here — callers should gate this behind a delegation-existence check so it
    is only reached when genuinely needed.
    """
    perms = frappe.get_all(
        "DocPerm",
        filters={"parent": doctype, "permlevel": 0, "read": 1},
        fields=["role", "if_owner"],
    )
    return any(p.role in user_roles and not p.if_owner for p in perms)


def _build_permission_query(user, table, fields):
    """
    Expand list visibility to include records belonging to delegators of *user*.

    The two permission systems — Frappe role/if_owner and delegation — are
    kept completely independent:

    1. No active delegations → return "" immediately.  Frappe's own role and
       if_owner rules run untouched; this function has zero effect.

    2. Active delegations exist, user already has unrestricted read (any role
       with if_owner=0) → return "".  They already see every record, including
       the delegator's, so no expansion is needed.

    3. Active delegations exist, user's read access is entirely if_owner-gated
       → split delegators into unrestricted ("all"-scope) and restricted
       (project/application-scope).  Unrestricted delegators expand the
       implicit "owner = me" field match; restricted delegators contribute an
       explicit "name IN (...)" branch limited to their resolved scope.

    Delegation never reduces access; it only adds records.
    """
    if not user:
        user = frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""

    # Fast path — no delegations at all: leave Frappe's permission system alone.
    visible = get_visible_as_users(user)   # [user] when no delegations exist
    if len(visible) == 1:
        return ""

    # User has delegations.  Check whether their role already gives unrestricted
    # access; if so, they already see all records and no filter is needed.
    user_roles = set(frappe.get_roles(user))
    doctype = table[3:] if table.startswith("tab") else table   # strip "tab" prefix
    if _user_has_unrestricted_read(user_roles, doctype):
        return ""

    delegators = visible[1:]
    unrestricted = [user]
    restricted_name_sets = []
    for delegator in delegators:
        scoped = _scoped_doc_names_for_doctype(delegator, user, doctype)
        if scoped is None:
            unrestricted.append(delegator)
        elif scoped:
            restricted_name_sets.append(scoped)

    quoted = ", ".join(frappe.db.escape(u) for u in unrestricted)
    field_parts = [f"`{table}`.`{field}` in ({quoted})" for field in fields]
    branches = ["(" + " OR ".join(field_parts) + ")"]

    for scoped in restricted_name_sets:
        quoted_names = ", ".join(frappe.db.escape(n) for n in scoped)
        branches.append(f"`{table}`.`name` in ({quoted_names})")

    return "(" + " OR ".join(branches) + ")"


def _permission_query_for(doctype):
    """Build a permission_query_conditions callable for *doctype* using the
    shared owner-field registry."""
    table = f"tab{doctype}"
    fields = _DOCTYPE_OWNER_FIELDS[doctype]

    def _query(user=None):
        return _build_permission_query(user, table, fields)

    return _query


project_registration_permission_query      = _permission_query_for("Project Registration")
travel_permission_query                    = _permission_query_for("Travel")
ta_da_settlement_permission_query          = _permission_query_for("TA DA Settlement")
temporary_advance_permission_query         = _permission_query_for("Temporary Advance")
advance_settlement_permission_query        = _permission_query_for("Advance Settlement")
reimbursement_permission_query             = _permission_query_for("Reimbursement")
direct_purchase_permission_query           = _permission_query_for("Direct Purchase")
disbursal_of_consultancy_permission_query  = _permission_query_for("Disbursal of Consultancy")
disbursal_of_honorarium_permission_query   = _permission_query_for("Disbursal of Honorarium")
loan_request_permission_query              = _permission_query_for("Loan Request")
indent_general_form_permission_query       = _permission_query_for("Indent General Form")
indent_cum_sanction_sheet_permission_query = _permission_query_for("Indent Cum Sanction Sheet")
recruitment_adhoc_contractual_permission_query = _permission_query_for("Recruitment Adhoc Contractual")


def user_delegation_permission_query(user=None):
    """
    Restrict desk/report visibility of User Delegation rows to the ones a
    user is party to (as delegator or delegate).  Needed because the DocType
    grants `read` to the built-in `All` role — without this, any logged-in
    account could list every delegation in the system via desk/report view.
    """
    if not user:
        user = frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    escaped = frappe.db.escape(user)
    return (
        f"(`tabUser Delegation`.`delegator_user` = {escaped} "
        f"OR `tabUser Delegation`.`delegate_user` = {escaped})"
    )


# ---------------------------------------------------------------------------
# has_permission hooks — registered in hooks.py
# ---------------------------------------------------------------------------

_WRITE_PERMISSION_TYPES = {"write", "create", "delete", "submit", "cancel", "amend"}


def has_delegated_access(doc, ptype=None, user=None):
    """
    has_permission hook for Project Registration and the application doctypes
    in _DOCTYPE_OWNER_FIELDS.  Returns True to explicitly grant access, or
    None to defer to Frappe's normal permission system.

    NOTE ON EFFECTIVENESS: Frappe's has_permission hook is a deny-only gate —
    returning True/None here never grants access beyond what the caller's
    role + Frappe's own `owner` field + DocShare already allow; it can only
    additionally *deny* (by returning False, which this never does). This
    module's own whitelisted API functions (save_travel, submit_travel,
    get_travel_commit_details, etc.) don't go through Frappe's permission
    system at all — they call frappe.get_doc()/doc.save(ignore_permissions=True)
    directly. For those, use require_document_access() below instead; this
    hook only matters for generic Frappe access paths (desk, report view)
    that this app's own frontend doesn't use for these doctypes.
    """
    if not user:
        user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return None

    owner_fields = _DOCTYPE_OWNER_FIELDS.get(doc.doctype)
    if not owner_fields:
        return None

    delegators = {doc.get(f) for f in owner_fields if doc.get(f)}
    delegators.discard(user)
    if not delegators:
        return None

    if ptype == "workflow_action":
        action_type = "workflow"
    elif ptype in _WRITE_PERMISSION_TYPES:
        action_type = "write"
    else:
        action_type = "read"

    for delegator in delegators:
        if is_active_delegation(
            delegator, user, doctype=doc.doctype, docname=doc.name, action_type=action_type
        ):
            return True

    return None


# ---------------------------------------------------------------------------
# Explicit authorization helper for this app's own whitelisted API functions.
# These bypass Frappe's native permission system (ignore_permissions=True,
# plain frappe.get_doc() with no check_permission() call), so has_permission
# hooks above never run for them. This is the real enforcement point.
# ---------------------------------------------------------------------------

def require_document_access(doc, action_type="read"):
    """
    Raise frappe.PermissionError unless the session user owns *doc* (via any
    of its owner-identifying fields — see _DOCTYPE_OWNER_FIELDS) or holds an
    active delegation from an owner that covers this action/document, or is
    System Manager / Administrator.

    Call this at the top of any whitelisted function that reads or writes a
    single document by name, in doctypes covered by _DOCTYPE_OWNER_FIELDS.

    action_type: "read" | "write" | "workflow"
    """
    user = frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return

    owner_fields = _DOCTYPE_OWNER_FIELDS.get(doc.doctype, ["owner"])
    owners = {doc.get(f) for f in owner_fields if doc.get(f)}

    if user in owners:
        return

    for owner in owners:
        if is_active_delegation(owner, user, doctype=doc.doctype, docname=doc.name, action_type=action_type):
            return

    frappe.throw(
        f"You do not have permission to access this {doc.doctype}.",
        frappe.PermissionError,
    )


# ---------------------------------------------------------------------------
# Create on behalf — two ways in:
#   1. View and Edit / Workflow Action, scope "all" or a covering project.
#   2. Specific Application: listed doctype under a listed, Approved, funded
#      project.  The new document is owned by the delegator, so the delegate
#      gets no access to it.
# Every call is recorded in Delegation Audit Log.
# ---------------------------------------------------------------------------

_BLOCKED_CREATE_FIELDS = {
    "name", "owner", "docstatus", "workflow_state", "creation", "modified",
    "modified_by", "idx", "doctype", "flags",
}


def _active_create_rows(delegator_user, delegate_user):
    """Enabled, non-revoked, in-date rows from delegator_user to delegate_user."""
    now = now_datetime()
    rows = frappe.get_all(
        "User Delegation",
        filters={"delegator_user": delegator_user, "delegate_user": delegate_user, **_ACTIVE_FILTERS},
        fields=["name", "delegation_type", "scope_type", "project_names",
                "allowed_doctypes", "valid_from", "valid_to"],
        limit=0,
    )
    return [r for r in rows if _row_is_time_valid(r, now)]


def _access_delegation_for_create(rows, target_project):
    """
    Name of a View and Edit / Workflow Action row allowing creation, or None.

    scope_type='all'         -> always allowed.
    scope_type='project'     -> allowed only if target_project is in
                                 project_names.
    scope_type='application' -> never allowed (no forward-looking scope; it
                                 only lists specific existing documents).
    """
    for row in rows:
        if row.delegation_type not in ("View and Edit", "Workflow Action"):
            continue
        if row.scope_type == "all":
            return row.name
        if row.scope_type == "project" and target_project and target_project in _safe_json_list(row.project_names):
            return row.name
    return None


def _specific_rows_for_doctype(rows, doctype):
    return [
        r for r in rows
        if r.delegation_type == _SPECIFIC_APPLICATION
        and r.scope_type == "project"
        and doctype in _safe_json_list(r.allowed_doctypes)
    ]


def create_application_on_behalf(doctype, delegator_user, project_name=None, fields=None):
    """
    Create a new application document (one of _APPLICATION_DOCTYPES) on behalf
    of delegator_user, and audit the attempt whether or not it succeeds.

    project_name is a Project Registration `name`.  Returns only the new
    document's name.
    """
    _require_authenticated_user()

    audit = {
        "actual_user": frappe.session.user,
        "delegator_user": delegator_user,
        "application_doctype": doctype,
        "project_name": project_name,
    }
    savepoint = "create_on_behalf"
    frappe.db.savepoint(savepoint)

    try:
        doc = _create_on_behalf(doctype, delegator_user, project_name, fields, audit)
    except Exception as e:
        try:
            frappe.db.rollback(save_point=savepoint)
        except Exception:
            # A controller committed mid-insert, which discards the savepoint.
            frappe.db.rollback()
        try:
            _write_audit_log(audit, status="Failed", error=str(e))
            frappe.db.commit()
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Delegation Audit Log write failed")
        raise

    _write_audit_log(audit, status="Success", application_name=doc.name)
    frappe.db.commit()

    return {"status": "success", "name": doc.name}


def _write_audit_log(audit, status, application_name=None, error=None):
    entry = {**audit, "status": status, "application_name": application_name}
    entry = {k: str(v)[:140] if v else None for k, v in entry.items()}
    frappe.get_doc({
        "doctype": "Delegation Audit Log",
        **entry,
        "error": error,
    }).insert(ignore_permissions=True)
    frappe.logger("delegation").info({**entry, "error": error})


def _create_on_behalf(doctype, delegator_user, project_name, fields, audit):
    """Validate, authorise and insert. Sets audit["delegation"]; does not commit."""
    session_user = frappe.session.user

    valid_app_doctypes = {dt for _, dt, _, _ in _APPLICATION_DOCTYPES}
    if doctype not in valid_app_doctypes:
        frappe.throw(f"'{doctype}' is not a delegable application doctype.")

    if delegator_user == session_user:
        frappe.throw("Use the normal create flow for your own applications.")

    if not frappe.db.exists("User", {"name": delegator_user, "enabled": 1}):
        frappe.throw(f"User '{delegator_user}' does not exist or is disabled.")

    owner_field = next((wf for _, dt, wf, _ in _APPLICATION_DOCTYPES if dt == doctype), None)
    project_field = _PROJECT_FIELD_BY_DOCTYPE.get(doctype)

    if project_field and not project_name:
        frappe.throw(f"'{doctype}' requires project_name to create on behalf of another user.")

    rows = _active_create_rows(delegator_user, session_user)
    access_delegation = _access_delegation_for_create(rows, project_name)

    if access_delegation:
        audit["delegation"] = access_delegation
        return _insert_with_access_delegation(
            doctype, delegator_user, project_name, fields, owner_field, project_field
        )

    specific_rows = _specific_rows_for_doctype(rows, doctype)
    if specific_rows and not project_name:
        frappe.throw(f"'{doctype}' requires project_name to create on behalf of another user.")

    covering = next(
        (r for r in specific_rows if project_name in _safe_json_list(r.project_names)), None
    )
    if not covering:
        detail = f" for project '{project_name}'" if project_name else ""
        frappe.throw(
            f"You are not authorised to create a {doctype} on behalf of {delegator_user}{detail}.",
            frappe.PermissionError,
        )

    audit["delegation"] = covering.name
    _require_eligible_project(project_name)
    return _insert_with_specific_delegation(
        doctype, delegator_user, project_name, fields, owner_field
    )


def _insert_with_access_delegation(doctype, delegator_user, project_name, fields, owner_field, project_field):
    """
    The delegator is force-set on the owner-identifying field (webmail_id_travel
    / applicant_webmail / etc.). Frappe's own `owner` stays the session user
    (the delegate), who has access through the delegation anyway.
    """
    doc = frappe.new_doc(doctype)
    safe_fields = {
        k: v for k, v in (fields or {}).items()
        if k not in _BLOCKED_CREATE_FIELDS and k not in (owner_field, project_field)
    }
    doc.update(safe_fields)
    if owner_field:
        doc.set(owner_field, delegator_user)
    if project_field and project_name:
        # project_name is always a Project Registration `name`; some doctypes'
        # project_field stores the human-readable `project_no` instead — see
        # _PROJECT_FIELD_USES_PROJECT_NO for why and which.
        if doctype in _PROJECT_FIELD_USES_PROJECT_NO:
            project_no_values = _resolve_project_no_values([project_name])
            if not project_no_values:
                frappe.throw(f"Project '{project_name}' could not be resolved.")
            doc.set(project_field, project_no_values[0])
        else:
            doc.set(project_field, project_name)

    doc.insert(ignore_permissions=True)
    return doc


def _insert_with_specific_delegation(doctype, delegator_user, project_name, fields, owner_field):
    """
    Insert with the delegator as Frappe `owner` and on the owner-identifying
    field, and every project field derived from project_name.
    """
    project = frappe.db.get_value(
        "Project Registration",
        project_name,
        ["name", "project_no", "project_title"],
        as_dict=True,
    )
    meta = frappe.get_meta(doctype)
    forced = {
        field: project[column]
        for field, column in _ON_BEHALF_PROJECT_FIELDS[doctype].items()
        if meta.has_field(field)
    }
    if owner_field:
        forced[owner_field] = delegator_user

    doc = frappe.new_doc(doctype)
    doc.update({
        k: v for k, v in (fields or {}).items()
        if meta.has_field(k) and k not in _BLOCKED_CREATE_FIELDS and k not in forced
    })
    doc.update(forced)
    doc.flags.on_behalf = {"owner": delegator_user, "forced": forced}

    doc.insert(ignore_permissions=True)
    return doc


def apply_on_behalf_owner(doc, method=None):
    """before_insert hook. Frappe stamps `owner` with the session user just
    before this, so reassign it before naming, validation and on_update run."""
    on_behalf = doc.flags.get("on_behalf")
    if not on_behalf:
        return
    doc.owner = on_behalf["owner"]
    for child in doc.get_all_children():
        child.owner = on_behalf["owner"]


def verify_on_behalf_scope(doc, method=None):
    """before_save hook. fetch_from and controllers can overwrite the forced
    values (e.g. TA DA Settlement copies project_no from the linked Travel), so
    check them once everything else has run."""
    on_behalf = doc.flags.get("on_behalf")
    if not on_behalf or not doc.is_new():
        return
    for field, value in on_behalf["forced"].items():
        if (doc.get(field) or "") != (value or ""):
            frappe.throw(
                f"'{field}' resolved to '{doc.get(field)}', which does not match the delegated "
                "project and delegator. Check the linked records in the form.",
                frappe.PermissionError,
            )


def undelegate_user(delegation_name):
    """
    Revoke a delegation.  Only the original delegator or a System Manager may do this.
    """
    _require_authenticated_user()
    refuse_while_acting()

    if not frappe.db.exists("User Delegation", delegation_name):
        frappe.throw(f"Delegation '{delegation_name}' not found.")

    doc = frappe.get_doc("User Delegation", delegation_name)

    current_user = frappe.session.user
    if doc.delegator_user != current_user and not _is_system_manager():
        frappe.throw(
            "You are not authorised to revoke this delegation.",
            frappe.PermissionError,
        )

    doc.enabled    = 0
    doc.revoked_at = now_datetime()
    doc.revoked_by = current_user
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success"}
