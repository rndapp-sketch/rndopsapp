"""
Delegate User — backend implementation for rndopsapp.

Public surface (called from api.py whitelisted wrappers):
  search_delegate_users(query="")
  get_delegate_scope(user=None)
  get_active_delegations(user=None)
  delegate_user(delegate_user, delegation_type, scope_type, project_names, applications, valid_from, valid_to)
  undelegate_user(delegation_name)

Helpers available to the rest of the app:
  get_visible_as_users(user=None)
  is_active_delegation(delegator_user, delegate_user, doctype=None, docname=None, action_type="read")
"""

import json

import frappe
from frappe.utils import now_datetime

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


def _require_permanent_employee():
    """Raise PermissionError if the session user lacks the Permanent Employee role."""
    if "Permanent Employee" not in frappe.get_roles(frappe.session.user):
        frappe.throw(
            "Only users with the Permanent Employee role can manage delegations.",
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


def _active_rows_for_delegate(delegate_user):
    """All enabled, non-revoked User Delegation rows where delegate_user matches."""
    # The User Delegation DocType may not be installed (e.g. fresh DB or
    # pre-migration). In that case there are no delegations — return [] so
    # permission queries and login don't crash with DoesNotExistError.
    if not frappe.db.exists("DocType", "User Delegation"):
        return []
    return frappe.get_all(
        "User Delegation",
        filters={"delegate_user": delegate_user, **_ACTIVE_FILTERS},
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
    if not frappe.db.exists("DocType", "User Delegation"):
        return False

    now = now_datetime()

    rows = frappe.get_all(
        "User Delegation",
        filters={
            "delegator_user": delegator_user,
            "delegate_user": delegate_user,
            **_ACTIVE_FILTERS,
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

        if docname:
            if row.scope_type == "project" and docname in _safe_json_list(row.project_names):
                return True
            if row.scope_type == "application" and docname in _safe_json_list(row.applications):
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
    ("Direct Purchase",               "Direct Purchase",               None,                        None),
    ("Disbursal of Consultancy",      "Disbursal of Consultancy",      "webmail_id",                None),
    ("Disbursal of Honorarium",       "Disbursal of Honorarium",       "webmail_id",                None),
    ("Loan Request",                  "Loan Request",                  "loan_for_webmail_id",       None),
    ("Indent General Form",           "Indent General Form",           "igf_webmail_id",            None),
    ("Indent Cum Sanction Sheet",     "Indent Cum Sanction Sheet",     "icss_applicant_webmail_id", None),
    ("Recruitment Adhoc Contractual", "Recruitment Adhoc Contractual", "webmail_id",                None),
]


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


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

_VALID_DELEGATION_TYPES = {"View Only", "View and Edit", "Workflow Action"}
_VALID_SCOPE_TYPES = {"all", "project", "application"}


# ---------------------------------------------------------------------------
# API implementations (called by whitelisted wrappers in api.py)
# ---------------------------------------------------------------------------

def search_delegate_users(query=""):
    """
    Return up to 20 active, non-self Users matching *query* (email / full_name).
    Caller must have Permanent Employee role.
    """
    _require_permanent_employee()

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
    plus the list of users already delegated by *user*.
    """
    _require_permanent_employee()
    target = _resolve_target_user(user)

    # ── Current delegates for this user ──────────────────────────────────────
    delegations = frappe.get_all(
        "User Delegation",
        filters={"delegator_user": target, **_ACTIVE_FILTERS},
        fields=["delegate_user"],
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

    return {"users": users, "projects": projects, "applications": applications}


def get_active_delegations(user=None):
    """
    Return all active (enabled, non-revoked) delegations created by *user*.
    """
    _require_permanent_employee()
    target = _resolve_target_user(user)

    rows = frappe.get_all(
        "User Delegation",
        filters={"delegator_user": target, **_ACTIVE_FILTERS},
        fields=[
            "name", "delegate_user", "delegation_type", "scope_type",
            "project_names", "applications", "valid_from", "valid_to", "enabled",
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
            "project_count":      len(_safe_json_list(r.project_names)),
            "application_count":  len(_safe_json_list(r.applications)),
            "valid_from":         r.valid_from,
            "valid_to":           r.valid_to,
            "enabled":            r.enabled,
        }
        for r in rows
    ]


def delegate_user(
    delegate_user,
    delegation_type=None,
    scope_type=None,
    project_names=None,
    applications=None,
    valid_from=None,
    valid_to=None,
):
    """
    Create or merge a User Delegation row.

    On CREATE  — defaults: delegation_type="View Only", scope_type="all".
    On UPDATE  — only fields explicitly provided are changed:
                 project_names and applications are MERGED (deduplicated),
                 scope_type is NOT downgraded (e.g. "project" → "all") unless
                 the caller explicitly passes scope_type="all",
                 delegation_type and validity window are kept unless passed.

    delegator_user is always frappe.session.user — never trusted from the frontend.
    """
    _require_permanent_employee()

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
    incoming_apps = (
        _safe_json_list(applications)
        if isinstance(applications, str)
        else list(applications or [])
    )

    # Scope list requirements only enforced when scope_type is explicitly set
    if scope_type == "project" and not incoming_projects:
        frappe.throw("At least one project is required when scope_type is 'project'.")

    if scope_type == "application" and not incoming_apps:
        frappe.throw("At least one application is required when scope_type is 'application'.")

    # ── Verify ownership of any incoming projects ─────────────────────────────
    if incoming_projects:
        owned = set(
            frappe.get_all(
                "Project Registration",
                or_filters=[
                    ["pi_webmail",    "=", current_user],
                    ["pi_userid",     "=", current_user],
                    ["owner",         "=", current_user],
                    ["head_approver", "=", current_user],
                ],
                pluck="name",
                limit=0,
            )
        )
        for prj in incoming_projects:
            if prj not in owned:
                frappe.throw(
                    f"Project '{prj}' does not belong to or is not assigned to you."
                )

    # ── Find existing active delegation ───────────────────────────────────────
    existing_name = frappe.db.get_value(
        "User Delegation",
        {
            "delegator_user": current_user,
            "delegate_user":  delegate_user,
            "enabled":        1,
            "revoked_at":     ["is", "not set"],
        },
        "name",
    )

    if existing_name:
        # ── MERGE into existing delegation ────────────────────────────────────
        doc = frappe.get_doc("User Delegation", existing_name)

        # Merge project_names — deduplicated, order preserved
        merged_projects = list(
            dict.fromkeys(_safe_json_list(doc.project_names) + incoming_projects)
        )

        # Merge applications — deduplicated, order preserved
        merged_apps = list(
            dict.fromkeys(_safe_json_list(doc.applications) + incoming_apps)
        )

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

        doc.project_names = json.dumps(merged_projects) if merged_projects else ""
        doc.applications  = json.dumps(merged_apps)     if merged_apps     else ""
        doc.revoked_at    = None
        doc.revoked_by    = None

    else:
        # ── CREATE new delegation ─────────────────────────────────────────────
        doc = frappe.new_doc("User Delegation")
        doc.delegator_user  = current_user
        doc.delegate_user   = delegate_user
        doc.enabled         = 1
        doc.delegation_type = delegation_type or "View Only"
        doc.scope_type      = scope_type      or "all"
        doc.project_names   = json.dumps(incoming_projects) if incoming_projects else ""
        doc.applications    = json.dumps(incoming_apps)     if incoming_apps     else ""
        doc.valid_from      = valid_from or None
        doc.valid_to        = valid_to   or None

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
       → return the delegation-aware filter that replaces Frappe's implicit
       "owner = me" with "owner/webmail IN (me + delegators)".

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

    # User's access is if_owner-gated only.  Expand the implicit "owner = me"
    # to include every delegator so their records become visible too.
    quoted = ", ".join(frappe.db.escape(u) for u in visible)
    parts = [f"`{table}`.`{field}` in ({quoted})" for field in fields]
    return "(" + " OR ".join(parts) + ")"


def project_registration_permission_query(user=None):
    return _build_permission_query(
        user, "tabProject Registration",
        ["pi_webmail", "pi_userid", "owner", "head_approver"],
    )


def travel_permission_query(user=None):
    return _build_permission_query(
        user, "tabTravel",
        ["webmail_id_travel", "owner"],
    )


def ta_da_settlement_permission_query(user=None):
    return _build_permission_query(
        user, "tabTA DA Settlement",
        ["webmail_id", "owner"],
    )


def temporary_advance_permission_query(user=None):
    return _build_permission_query(
        user, "tabTemporary Advance",
        ["applicant_webmail", "owner"],
    )


def advance_settlement_permission_query(user=None):
    return _build_permission_query(
        user, "tabAdvance Settlement",
        ["owner"],
    )


def reimbursement_permission_query(user=None):
    return _build_permission_query(
        user, "tabReimbursement",
        ["applicant_webmail", "owner"],
    )


def direct_purchase_permission_query(user=None):
    return _build_permission_query(
        user, "tabDirect Purchase",
        ["owner"],
    )


def disbursal_of_consultancy_permission_query(user=None):
    return _build_permission_query(
        user, "tabDisbursal of Consultancy",
        ["webmail_id", "owner"],
    )


def disbursal_of_honorarium_permission_query(user=None):
    return _build_permission_query(
        user, "tabDisbursal of Honorarium",
        ["webmail_id", "owner"],
    )


def loan_request_permission_query(user=None):
    return _build_permission_query(
        user, "tabLoan Request",
        ["loan_for_webmail_id", "owner"],
    )


def indent_general_form_permission_query(user=None):
    return _build_permission_query(
        user, "tabIndent General Form",
        ["igf_webmail_id", "owner"],
    )


def indent_cum_sanction_sheet_permission_query(user=None):
    return _build_permission_query(
        user, "tabIndent Cum Sanction Sheet",
        ["icss_applicant_webmail_id", "owner"],
    )


def recruitment_adhoc_contractual_permission_query(user=None):
    return _build_permission_query(
        user, "tabRecruitment Adhoc Contractual",
        ["webmail_id", "owner"],
    )


def undelegate_user(delegation_name):
    """
    Revoke a delegation.  Only the original delegator or a System Manager may do this.
    """
    _require_permanent_employee()

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
