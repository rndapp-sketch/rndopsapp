# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt
#
# Guest-readable, read-only endpoints that expose Pragati project-staff and
# leave data to the external Presence (Upasthiti) attendance backend.
#
# These are intentionally allow_guest=True so the Presence backend does not need
# an API key. To keep that safe, ONLY low-sensitivity fields are returned here -
# never PAN / Aadhar / salary / addresses / bank details.
#
# Callable as:
#   /api/method/rndopsapp.rndopsapp.presence_api.<function>

import frappe
from frappe.utils import getdate
from datetime import timedelta

PROJECT_STAFF_DOCTYPE = "Project Staff Details"
LEAVE_MODULE_DOCTYPE = "Leave Module"
LEAVE_DATA_DOCTYPE = "Leave Data"
DEPARTMENT_DOCTYPE = "Department_prornd"

# 2-char employee class code used by the Presence backend for project staff.
EMP_CLASS = "PS"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _username_from_email(email):
    if email and "@" in email:
        return email.split("@", 1)[0].strip() or None
    return (email or "").strip() or None


def _iso(value):
    if not value:
        return None
    try:
        return getdate(value).isoformat()
    except Exception:
        return str(value)


def _dept_name(dept_id):
    """ps_department stores a Department_prornd docname (random hash) -> resolve
    to the human-readable dept_name. Falls back to the raw id if not found."""
    if not dept_id:
        return None
    try:
        name = frappe.db.get_value(DEPARTMENT_DOCTYPE, dept_id, "dept_name")
    except Exception:
        name = None
    return name or dept_id


def _user_full_name(email, cache):
    if not email:
        return None
    if email in cache:
        return cache[email]
    try:
        name = frappe.db.get_value("User", email, "full_name")
    except Exception:
        name = None
    cache[email] = name
    return name


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
@frappe.whitelist(allow_guest=True)
def ping():
    return {"status": "ok", "app": "rndopsapp", "service": "presence_api"}


@frappe.whitelist(allow_guest=True)
def get_project_staff(workflow_state="Approved"):
    """Approved Project Staff Details, normalized to the Presence `staff_with_pi`
    shape. Guest-readable; sensitive fields are intentionally excluded."""
    filters = {}
    if workflow_state:
        filters["workflow_state"] = workflow_state

    rows = frappe.get_all(
        PROJECT_STAFF_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "ps_emp_id",
            "erp_mail",
            "ps_email_id",
            "ps_first_name",
            "ps_middle_name",
            "ps_last_name",
            "ps_department",
            "ps_designation",
            "ps_joining_date",
            "ps_term_completion_date",
            "project_no",
            "pi_id",
            "workflow_state",
        ],
        limit_page_length=0,
    )

    name_cache = {}
    out = []
    for r in rows:
        emp_id = r.get("ps_emp_id")
        if not emp_id:
            continue

        erp_mail = (r.get("erp_mail") or "").strip()
        username = _username_from_email(erp_mail) or _username_from_email(r.get("ps_email_id"))
        if not username:
            continue

        full_name = (
            " ".join(
                p for p in [r.get("ps_first_name"), r.get("ps_middle_name"), r.get("ps_last_name")] if p
            )
            or None
        )
        joining = _iso(r.get("ps_joining_date"))
        term = _iso(r.get("ps_term_completion_date"))
        pi_email = (r.get("pi_id") or "").strip()

        out.append(
            {
                "staffEmpId": emp_id,
                "staffUsername": username,
                "staffFullName": full_name,
                "projectId": r.get("project_no"),
                "deptName": _dept_name(r.get("ps_department")),
                "designation": r.get("ps_designation"),
                "empClass": EMP_CLASS,
                "joiningDate": joining,
                "rawJoiningDate": joining,
                "termCompletionDate": term,
                "piEmpId": None,
                "piUsername": _username_from_email(pi_email),
                "piFullName": _user_full_name(pi_email, name_cache),
                "erpMail": erp_mail or None,
                "sourceDatabase": "pragati",
            }
        )
    return out


def _resolve_emp_id(email, username):
    """Map a leave application back to a project-staff Employee Id."""
    emp_id = None
    if username:
        emp_id = frappe.db.get_value(LEAVE_DATA_DOCTYPE, {"emp_username": username}, "emp_id")
    if not emp_id and email:
        emp_id = frappe.db.get_value(PROJECT_STAFF_DOCTYPE, {"erp_mail": email}, "ps_emp_id")
    return emp_id


@frappe.whitelist(allow_guest=True)
def get_leaves(workflow_state="Approved"):
    """Approved Leave Module applications expanded to per-date entries.

    Each entry's `dayType` is FULL or HALF and `leaveType` is one of CL / EL / OL
    (On Duty Leave), matching how the Presence backend already classifies leave.
    """
    filters = {}
    if workflow_state:
        filters["workflow_state"] = workflow_state

    rows = frappe.get_all(
        LEAVE_MODULE_DOCTYPE,
        filters=filters,
        fields=[
            "name",
            "email",
            "username",
            "pi",
            "leave_type",
            "from_date",
            "to_date",
            "reason_for_leave",
            "workflow_state",
        ],
        limit_page_length=0,
    )

    out = []
    for r in rows:
        username = r.get("username") or _username_from_email(r.get("email"))
        emp_id = _resolve_emp_id(r.get("email"), username)

        lt = r.get("leave_type")
        if lt == "CL":
            code = "CL"
        elif lt == "EL":
            code = "EL"
        else:
            code = "OL"  # On Duty Leave

        dates = []
        if lt == "CL":
            cl_rows = frappe.get_all(
                "CL Date Row",
                filters={"parent": r.get("name"), "parenttype": LEAVE_MODULE_DOCTYPE},
                fields=["cl_date", "day_type"],
                limit_page_length=0,
            )
            for cr in cl_rows:
                if not cr.get("cl_date"):
                    continue
                day_type = "FULL" if (cr.get("day_type") or "Full Day") == "Full Day" else "HALF"
                dates.append({"date": _iso(cr.get("cl_date")), "dayType": day_type})
        else:
            f = r.get("from_date")
            t = r.get("to_date")
            if f and t:
                d = getdate(f)
                end = getdate(t)
                while d <= end:
                    dates.append({"date": d.isoformat(), "dayType": "FULL"})
                    d = d + timedelta(days=1)

        if not dates:
            continue

        out.append(
            {
                "refNum": r.get("name"),
                "empId": emp_id,
                "empUsername": username,
                "leaveType": code,
                "status": r.get("workflow_state"),
                "reason": r.get("reason_for_leave"),
                "fromDate": _iso(r.get("from_date")) or dates[0]["date"],
                "toDate": _iso(r.get("to_date")) or dates[-1]["date"],
                "dates": dates,
            }
        )
    return out


@frappe.whitelist(allow_guest=True)
def get_leave_balances():
    """Leave Data balances (allocated CL/EL) per project-staff employee."""
    return frappe.get_all(
        LEAVE_DATA_DOCTYPE,
        fields=["emp_id", "emp_username", "emp_class", "department", "el", "cl"],
        limit_page_length=0,
    )


@frappe.whitelist(allow_guest=True)
def get_leave_states():
    """Diagnostic: count of each workflow_state present on Leave Module.
    Use this once after deploy to confirm the real 'approved' state name."""
    from collections import Counter

    rows = frappe.get_all(LEAVE_MODULE_DOCTYPE, fields=["workflow_state"], limit_page_length=0)
    return dict(Counter([r.get("workflow_state") or "(empty)" for r in rows]))
