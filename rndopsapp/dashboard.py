import frappe

@frappe.whitelist(allow_guest=True)
def get_dashboard_data(user_email, department):
    """
    Generic (user_email, department) dashboard — legacy response shape.

    The original implementation queried "Approval Request" and "Department Budget" —
    neither DocType exists anywhere in this codebase (no doctype folder, no DB table) —
    and the generic core "Project" doctype, which this app doesn't use for R&D projects
    (that's "Project Registration" everywhere else in this module). It crashed on every
    call and had no callers anywhere in the app.

    Rebuilt on top of get_head_dashboard_data(), which already implements this exact
    (user_email, department) contract against the real schema (Project Registration,
    Fund Sanction, Department_prornd) and is verified elsewhere in this module — so this
    function now returns real, live data in the old shape instead of throwing.
    """
    head_data = get_head_dashboard_data(user_email, department)

    data = {}
    data["user_data"] = head_data["user_data"]

    # 2. Pending Approvals — this department's projects still moving through the approval
    # workflow (Fund-Sanction single source of truth: submitted = not yet sanctioned).
    pending_approvals = [
        {
            "title": proj["project_title"],
            "description": proj["project_title"],
            "request_type": proj["project_type"],
            "creation": proj["creation"],
        }
        for pi in head_data["pi_wise_projects"]
        for proj in pi["projects"]
        if proj["status"] == "submitted"
    ]
    data["pending_approvals"] = pending_approvals

    # 3. Recent Submissions — this specific user's own Project Registration submissions
    # in the department (pi_webmail is the real "submitted by" field on Project Registration).
    recent_submissions = frappe.get_list(
        "Project Registration",
        filters={"pi_webmail": user_email, "implementation_department": head_data["department"]["id"]},
        fields=["project_title as title", "project_type as request_type", "workflow_state as status", "creation"],
        order_by="creation desc",
        ignore_permissions=True
    )
    data["recent_submissions"] = recent_submissions

    # 4. Department Projects Analytics — flattened from the same pi_wise_projects data
    # get_head_dashboard_data already computed, so this adds no extra queries.
    department_projects = [
        {
            "project_name": proj["project_title"],
            "status": proj["status"],
            "principal_investigator": pi["pi_name"],
            "start_date": proj["prj_start_date"],
            "end_date": proj["prj_end_date"],
            "completion_date": proj["prj_end_date"] if proj["status"] == "completed" else None,
        }
        for pi in head_data["pi_wise_projects"]
        for proj in pi["projects"]
    ]
    data["department_projects"] = department_projects

    from frappe.utils import getdate, get_year_start, get_year_ending
    year_start = getdate(get_year_start(frappe.utils.today()))
    year_end = getdate(get_year_ending(frappe.utils.today()))
    completed_this_year_count = sum(
        1 for p in department_projects
        if p["status"] == "completed" and p["end_date"] and year_start <= getdate(p["end_date"]) <= year_end
    )

    data["project_analytics"] = {
        "total_projects": head_data["project_overview"]["total_projects"],
        # Distinct PIs with at least one project in this department — derived from the
        # same PI-wise grouping above instead of the original's per-row Has Role lookup.
        "active_pis": len(head_data["pi_wise_projects"]),
        "completed_this_year": completed_this_year_count
    }

    # 5. Department Funds Analytics — same Fund Sanction totals get_head_dashboard_data
    # already computed for this department. "pending_requests_amount" from the old
    # "Department Budget" doctype has no real backing source in this schema, so it's
    # dropped rather than fabricated.
    data["fund_analytics"] = head_data["fund_analytics"]

    return data



@frappe.whitelist(allow_guest=True)
def get_head_dashboard_data(user_email, department):
    """
    HoD Dashboard — Department-level analytics (mirrors director dashboard at department scope).
    Returns project overview, PI-wise breakdown, fund analytics, and proposal stats.
    """
    data = {}

    # Resolve department — try dept_name match, then direct ID, then user's own department
    dept_record = frappe.db.sql("""
        SELECT name, dept_name FROM `tabDepartment_prornd`
        WHERE dept_name = %s OR name = %s
        LIMIT 1
    """, (department, department), as_dict=True)

    if dept_record:
        department_id    = dept_record[0].name
        department_label = dept_record[0].dept_name
    else:
        # Fall back: pull department from the user's own record
        user_dept_id = frappe.db.get_value("User", user_email, "department_name")
        if user_dept_id:
            department_id    = user_dept_id
            department_label = frappe.db.get_value("Department_prornd", user_dept_id, "dept_name") or user_dept_id
        else:
            department_id    = department
            department_label = department

    data["department"] = {"id": department_id, "name": department_label}

    # Debug: show all departments so caller can verify the correct ID
    all_depts = frappe.db.sql(
        "SELECT name, dept_name FROM `tabDepartment_prornd` ORDER BY dept_name",
        as_dict=True
    )
    data["_debug_departments"] = [{"id": d.name, "name": d.dept_name} for d in all_depts]

    # 1. User Data
    user_data = frappe.get_all(
        "User",
        filters={"email": user_email},
        fields=["full_name"],
        ignore_permissions=True
    )
    user_roles = frappe.get_all(
        "Has Role",
        filters={"parent": user_email, "parenttype": "User"},
        fields=["role"],
        ignore_permissions=True
    )
    data["user_data"] = {
        **(user_data[0] if user_data else {}),
        "roles": [r.role for r in user_roles]
    }

    today = frappe.utils.today()

    # 2. Project Overview — fetch all registered projects in this department with status.
    # Ongoing is decided by Fund Sanction alone (same single source of truth as the Director
    # Dashboard — Fund Received is a later step in the money trail, not a status signal).
    # Draft-mislabeled (docstatus=1, workflow_state still "Draft") and "Needs Correction (*)"
    # projects are excluded, matching the Director Dashboard's project-status definition.
    all_projects = frappe.db.sql("""
        SELECT
            pr.name AS project_id,
            pr.project_title,
            pr.project_type,
            pr.pi_webmail,
            pr.principal_investigator_name,
            pr.prj_start_date,
            pr.prj_end_date,
            pr.creation,
            CASE
                WHEN pr.prj_end_date IS NOT NULL AND pr.prj_end_date < %s THEN 'completed'
                WHEN (pr.prj_end_date IS NULL OR pr.prj_end_date >= %s)
                 AND EXISTS (SELECT 1 FROM `tabFund Sanction` fs WHERE fs.project_proposal = pr.name AND fs.docstatus = 1)
                 THEN 'ongoing'
                ELSE 'submitted'
            END AS status
        FROM `tabProject Registration` pr
        WHERE pr.docstatus = 1
          AND pr.workflow_state != 'Draft'
          AND pr.workflow_state NOT LIKE 'Needs Correction%%'
          AND pr.implementation_department = %s
        ORDER BY pr.creation DESC
    """, (today, today, department_id), as_dict=True)

    submitted_projects = [p for p in all_projects if p.status == 'submitted']
    ongoing_projects  = [p for p in all_projects if p.status == 'ongoing']
    completed_projects = [p for p in all_projects if p.status == 'completed']
    all_project_ids   = [p.project_id for p in all_projects]

    research_count    = sum(1 for p in all_projects if p.get("project_type") == "Research")
    consultancy_count = sum(1 for p in all_projects if p.get("project_type") == "Consultancy")

    total_staff = 0
    if all_project_ids:
        placeholders = ", ".join(["%s"] * len(all_project_ids))
        total_staff = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabproject_registration_manpower_details` WHERE parent IN ({placeholders})",
            tuple(all_project_ids)
        )[0][0] or 0

    data["project_overview"] = {
        "total_projects": len(all_projects),
        "submitted_projects": len(submitted_projects),
        "ongoing_projects": len(ongoing_projects),
        "completed_projects": len(completed_projects),
        "research_projects": research_count,
        "consultancy_projects": consultancy_count,
        "total_staff": total_staff
    }

    # 3. PI-wise Project Breakdown
    pi_map = {}
    for p in all_projects:
        key = p.pi_webmail or p.principal_investigator_name or "Unknown"
        if key not in pi_map:
            pi_map[key] = {
                "pi_email": p.pi_webmail,
                "pi_name": p.principal_investigator_name or "Unknown",
                "projects": []
            }
        pi_map[key]["projects"].append({
            "project_id": p.project_id,
            "project_title": p.project_title,
            "project_type": p.project_type,
            "status": p.status,
            "prj_start_date": str(p.prj_start_date) if p.prj_start_date else None,
            "prj_end_date": str(p.prj_end_date) if p.prj_end_date else None,
            "creation": str(p.creation) if p.creation else None
        })

    pi_list = sorted(pi_map.values(), key=lambda x: len(x["projects"]), reverse=True)
    for pi in pi_list:
        pi["project_count"] = len(pi["projects"])
    data["pi_wise_projects"] = pi_list

    # 4. Fund Analytics — from Fund Sanction for this department's projects
    if all_project_ids:
        placeholders = ", ".join(["%s"] * len(all_project_ids))
        fund_rows = frappe.db.sql(f"""
            SELECT
                IFNULL(SUM(total_sanctioned_amount), 0) AS total_allocation,
                IFNULL(SUM(CASE WHEN have_fund_details = 'Yes' THEN amount_received ELSE 0 END), 0) AS utilized_amount
            FROM `tabFund Sanction`
            WHERE docstatus = 1 AND project_proposal IN ({placeholders})
        """, tuple(all_project_ids), as_dict=True)

        if fund_rows and fund_rows[0]:
            total_allocation = float(fund_rows[0].total_allocation or 0)
            utilized_amount  = float(fund_rows[0].utilized_amount or 0)
            available_funds  = total_allocation - utilized_amount
            utilization_rate = (utilized_amount / total_allocation * 100) if total_allocation else 0
            data["fund_analytics"] = {
                "total_allocation": total_allocation,
                "utilized_amount": utilized_amount,
                "available_funds": available_funds,
                "utilization_rate": utilization_rate
            }
        else:
            data["fund_analytics"] = {}
    else:
        data["fund_analytics"] = {}

    # 5. Proposal Analytics — Project Proposals from this department (all docstatus)
    proposal_rows = frappe.db.sql("""
        SELECT
            docstatus,
            COUNT(*) AS total,
            IFNULL(SUM(total_budget_amount), 0) AS budget_total
        FROM `tabProject Proposal`
        WHERE implementation_department = %s
        GROUP BY docstatus
    """, (department_id,), as_dict=True)

    draft_count     = next((r.total for r in proposal_rows if r.docstatus == 0), 0)
    submitted_count = next((r.total for r in proposal_rows if r.docstatus == 1), 0)
    cancelled_count = next((r.total for r in proposal_rows if r.docstatus == 2), 0)
    proposed_budget_total = sum(float(r.budget_total or 0) for r in proposal_rows)

    pending_hod_approval = frappe.db.count(
        "Project Proposal",
        filters={"implementation_department": department_id, "workflow_state": "Pending HoD Approval", "docstatus": 0}
    )

    data["proposal_analytics"] = {
        "total_proposals": draft_count + submitted_count + cancelled_count,
        "draft_proposals": draft_count,
        "submitted_proposals": submitted_count,
        "cancelled_proposals": cancelled_count,
        "pending_hod_approval": pending_hod_approval,
        "proposed_budget_total": proposed_budget_total
    }

    return data


@frappe.whitelist()
def get_director_dashboard_data():
    """
    Director Dashboard — Backend API
    Returns comprehensive analytics for all projects, funding, IPR, and proposals
    """
    data = {}
    from collections import defaultdict
    from frappe.utils import add_days, now_datetime

    # ------------------------------------------------------------------
    # 1. PROJECT STATUS — single source of truth for every count below.
    #
    # Draft      = Project Registration with docstatus = 0 (unsubmitted), OR docstatus = 1 with
    #              workflow_state still literally "Draft" — a data inconsistency where the
    #              document was submitted but its workflow label never advanced. Both are
    #              treated as Draft and excluded everywhere.
    # Needs Correction = workflow_state starting with "Needs Correction" (per the active
    #              `pending_approval_prjReg` workflow: "(PE)"/"(IR)"/"(PS)"/"(Head)" variants) —
    #              the project was kicked back for revision, so it isn't meaningfully "submitted
    #              forward". Excluded everywhere, same as Draft.
    # Cancelled  = docstatus = 2 (Rejected). Excluded everywhere — matches Frappe's own
    #              default list behaviour and the rest of this module (see funding_sources,
    #              top_funded_projects, etc. which all key off docstatus = 1).
    # Ongoing    = non-draft project with at least one *submitted* (docstatus = 1)
    #              `Fund Sanction` whose `project_proposal` link points at it. Fund Sanction is
    #              the only doctype used for this per the sanction-detection requirement — the
    #              separate "Fund Received" doctype is a later step in the money trail and is
    #              intentionally not used to decide Ongoing/Submitted.
    # Submitted  = every other non-draft, non-"Needs Correction" project (still moving through
    #              the approval workflow, or Approved but with no Fund Sanction yet).
    #
    # total_projects = submitted_projects + ongoing_projects always, by construction —
    # every counted project falls into exactly one bucket, deduped on Project Registration name.
    # ------------------------------------------------------------------
    projects = frappe.db.sql("""
        SELECT
            pr.name AS project_id,
            pr.project_title,
            pr.project_type,
            pr.principal_investigator_name,
            pr.implementation_department,
            IFNULL(d.dept_name, pr.implementation_department) AS department,
            pr.funding_agen,
            IFNULL(NULLIF(fa.funding_agency_name, ''), NULLIF(pr.funding_agen, '')) AS funding_agency_name,
            pr.workflow_state,
            pr.creation
        FROM `tabProject Registration` pr
        LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
        LEFT JOIN `tabfundingagency_` fa ON fa.name = pr.funding_agen
        WHERE pr.docstatus = 1
          AND pr.workflow_state != 'Draft'
          AND pr.workflow_state NOT LIKE 'Needs Correction%%'
    """, as_dict=True)

    # Distinct projects that have at least one submitted Fund Sanction — dedupes multiple
    # Fund Sanction rows (e.g. multi-year sanctions or amendments) against the same project.
    sanctioned_project_ids = set(frappe.db.sql_list("""
        SELECT DISTINCT project_proposal
        FROM `tabFund Sanction`
        WHERE docstatus = 1 AND project_proposal IS NOT NULL AND project_proposal != ''
    """))

    total_projects = len(projects)
    ongoing_list = [p for p in projects if p.project_id in sanctioned_project_ids]
    submitted_list = [p for p in projects if p.project_id not in sanctioned_project_ids]

    research_projects = sum(1 for p in projects if p.project_type == "Research")
    consultancy_projects = sum(1 for p in projects if p.project_type == "Consultancy")

    # Total staff count - count Users where employee class is 'PS - Project Staff' (ID: 64rqq35p8v)
    total_staff_count = frappe.db.count("User", filters={"empclass": "64rqq35p8v"}) or 0

    # Top-level KPIs (per the dashboard's Project Status card)
    data["total_projects"] = total_projects
    data["submitted_projects"] = len(submitted_list)
    data["ongoing_projects"] = len(ongoing_list)
    data["status_breakdown"] = {
        "active": len(ongoing_list),
        "pending_sanction": len(submitted_list)
    }

    data["project_overview"] = {
        "total_projects": total_projects,
        "research_projects": research_projects,
        "consultancy_projects": consultancy_projects,
        "submitted_projects": len(submitted_list),
        "submitted_project_nos": [p.project_id for p in submitted_list],
        "ongoing_projects": len(ongoing_list),
        "ongoing_project_nos": [p.project_id for p in ongoing_list],
        "total_staff_count": total_staff_count
    }

    # 1b. TOP FUNDING AGENCIES — grouped by unique project, against total_projects
    agency_counts = defaultdict(int)
    for p in projects:
        agency_counts[p.funding_agency_name or "Missing Funding Agency Name"] += 1
    agencies_sorted = sorted(agency_counts.items(), key=lambda kv: kv[1], reverse=True)

    data["top_funding_agencies"] = [
        {
            "name": name,
            "count": count,
            "percentage": round((count / total_projects) * 100) if total_projects else 0
        }
        for name, count in agencies_sorted
    ]

    # 1c. FUNDING SOURCES — BREAKDOWN — top agencies individually, remainder combined as "Others".
    # Note: a real funding agency can itself be named "Others" in the data (distinct from this
    # synthetic catch-all bucket) — merge into the same row instead of emitting a duplicate "Others".
    FUNDING_BREAKDOWN_LIMIT = 7
    funding_source_breakdown = [
        {"name": name, "count": count}
        for name, count in agencies_sorted[:FUNDING_BREAKDOWN_LIMIT]
    ]
    others_count = sum(count for _, count in agencies_sorted[FUNDING_BREAKDOWN_LIMIT:])
    if others_count:
        existing_others = next((row for row in funding_source_breakdown if row["name"] == "Others"), None)
        if existing_others:
            existing_others["count"] += others_count
        else:
            funding_source_breakdown.append({"name": "Others", "count": others_count})
    data["funding_source_breakdown"] = funding_source_breakdown

    # 1d. DEPARTMENT-WISE PROJECT DISTRIBUTION — top departments individually, rest combined
    dept_counts = defaultdict(int)
    for p in projects:
        dept_counts[p.department or "Unspecified Department"] += 1
    depts_sorted = sorted(dept_counts.items(), key=lambda kv: kv[1], reverse=True)

    DEPARTMENT_LIMIT = 10
    department_distribution = [
        {"name": name, "count": count}
        for name, count in depts_sorted[:DEPARTMENT_LIMIT]
    ]
    other_dept_count = sum(count for _, count in depts_sorted[DEPARTMENT_LIMIT:])
    if other_dept_count:
        department_distribution.append({"name": "Other Departments", "count": other_dept_count})
    data["department_distribution"] = department_distribution

    # 2. FUNDING ANALYTICS — Financial Breakdown
    # Total allocation from Fund Sanction
    total_allocation = frappe.db.sql("""
        SELECT IFNULL(SUM(total_sanctioned_amount), 0)
        FROM `tabFund Sanction`
        WHERE docstatus = 1
    """)[0][0] or 0.0

    # Utilized funds from Fund Received or project transactions
    utilized = frappe.db.sql("""
        SELECT IFNULL(SUM(amount_received), 0)
        FROM `tabFund Sanction`
        WHERE docstatus = 1 AND have_fund_details = 'Yes'
    """)[0][0] or 0.0

    remaining = total_allocation - utilized

    # Total Sanction Amount — FY Wise (Indian FY: Apr–Mar)
    # FY label: if month >= 4 → "YYYY-YY+1", else → "YYYY-1-YYYY"
    fy_wise_sanctions = frappe.db.sql("""
        SELECT
            CASE
                WHEN MONTH(IFNULL(sanctioned_letter_date, creation)) >= 4
                    THEN CONCAT(YEAR(IFNULL(sanctioned_letter_date, creation)), '-', LPAD(YEAR(IFNULL(sanctioned_letter_date, creation)) - 1999, 2, '0'))
                ELSE CONCAT(YEAR(IFNULL(sanctioned_letter_date, creation)) - 1, '-', LPAD(YEAR(IFNULL(sanctioned_letter_date, creation)) - 2000, 2, '0'))
            END AS fy,
            IFNULL(SUM(total_sanctioned_amount), 0) AS total_amount
        FROM `tabFund Sanction`
        WHERE docstatus = 1
        GROUP BY fy
        ORDER BY MIN(IFNULL(sanctioned_letter_date, creation)) DESC
    """, as_dict=True)

    data["funding_analytics"] = {
        "total_allocation": float(total_allocation),
        "utilized": float(utilized),
        "remaining": float(remaining),
        "sanction_by_fy": [
            {"fy": row.fy, "total_amount": float(row.total_amount)}
            for row in fy_wise_sanctions
        ]
    }

    # 3. IPR ANALYTICS — Intellectual Property
    total_patents_filed = frappe.db.count("IPR Invention Disclosure")

    data["ipr_analytics"] = {
        "total_patents_filed": total_patents_filed
    }

    # 4. INTERNATIONAL COLLABORATION — Global MOUs
    # Count unique international funding agencies
    active_agencies = frappe.db.sql("""
        SELECT COUNT(DISTINCT funding_agen)
        FROM `tabProject Registration`
        WHERE origin_of_funding_agency = 'International'
    """)[0][0] or 0

    data["international_collaboration"] = {
        "active_agencies": active_agencies
    }

    # 5. PROPOSAL ANALYTICS — Proposals Under Review
    # Assuming proposals are in Project Proposal doctype with workflow_state indicating review
    total_proposals = frappe.db.count("Project Proposal", filters={"docstatus": 0})

    proposed_budget_total = frappe.db.sql("""
        SELECT IFNULL(SUM(total_budget_amount), 0)
        FROM `tabProject Proposal`
        WHERE docstatus = 0
    """)[0][0] or 0.0

    data["proposal_analytics"] = {
        "total_proposals": total_proposals,
        "proposed_budget_total": float(proposed_budget_total)
    }

    # 6. PROJECT STATUS BY YEAR — Bar Chart
    # Get projects grouped by year with mutually exclusive status breakdown
    project_status_by_year = frappe.db.sql("""
        SELECT
            YEAR(IFNULL(pr.prj_start_date, pr.creation)) as year,
            SUM(CASE 
                WHEN (pr.prj_end_date IS NULL OR pr.prj_end_date >= CURDATE())
                 AND NOT EXISTS (SELECT 1 FROM `tabFund Sanction` fs WHERE fs.project_proposal = pr.name AND fs.docstatus = 1)
                 AND NOT EXISTS (SELECT 1 FROM `tabFund Received` fr WHERE fr.prjreg_title = pr.name AND fr.docstatus = 1) 
                 THEN 1 ELSE 0 END) as submitted,
            SUM(CASE 
                WHEN (pr.prj_end_date IS NULL OR pr.prj_end_date >= CURDATE())
                 AND (EXISTS (SELECT 1 FROM `tabFund Sanction` fs WHERE fs.project_proposal = pr.name AND fs.docstatus = 1) 
                      OR EXISTS (SELECT 1 FROM `tabFund Received` fr WHERE fr.prjreg_title = pr.name AND fr.docstatus = 1))
                 THEN 1 ELSE 0 END) as ongoing,
            SUM(CASE 
                WHEN pr.prj_end_date IS NOT NULL AND pr.prj_end_date < CURDATE() 
                 THEN 1 ELSE 0 END) as completed
        FROM `tabProject Registration` pr
        WHERE pr.docstatus = 1
          AND pr.workflow_state != 'Draft'
          AND pr.workflow_state NOT LIKE 'Needs Correction%%'
        GROUP BY YEAR(IFNULL(pr.prj_start_date, pr.creation))
        ORDER BY year DESC
    """, as_dict=True)

    data["project_status_by_year"] = [
        {
            "year": str(row.year),
            "submitted": int(row.submitted or 0),
            "ongoing": int(row.ongoing or 0),
            "completed": int(row.completed or 0)
        }
        for row in project_status_by_year
    ]

    # 7. FUNDING SOURCES — Pie Chart
    funding_sources = frappe.db.sql("""
        SELECT
            IFNULL(fa.funding_agency_name, IFNULL(NULLIF(pr.funding_agen, ''), 'Unknown')) as name,
            COUNT(*) as value
        FROM `tabProject Registration` pr
        LEFT JOIN `tabfundingagency_` fa ON fa.name = pr.funding_agen
        WHERE pr.docstatus = 1
          AND pr.workflow_state != 'Draft'
          AND pr.workflow_state NOT LIKE 'Needs Correction%%'
          AND (pr.prj_end_date IS NULL OR pr.prj_end_date >= CURDATE())
        GROUP BY name
        ORDER BY value DESC
    """, as_dict=True)

    data["funding_sources"] = [
        {
            "name": row.name,
            "value": row.value or 0
        }
        for row in funding_sources
    ]

    # 8. TOP FUNDED PROJECTS — List
    top_funded_projects = frappe.db.sql("""
        SELECT
            pr.name as project_id,
            pr.project_title,
            pr.principal_investigator_name as pi_name,
            IFNULL(d.dept_name, pr.implementation_department) as department,
            IFNULL(pr.total_budget_amount, 0) as total_budget_amount
        FROM `tabProject Registration` pr
        LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
        WHERE pr.total_budget_amount IS NOT NULL
        ORDER BY pr.total_budget_amount DESC
    """, as_dict=True)

    data["top_funded_projects"] = [
        {
            "project_id": row.project_id,
            "project_title": row.project_title,
            "pi_name": row.pi_name or "N/A",
            "department": row.department or "N/A",
            "total_budget_amount": float(row.total_budget_amount or 0)
        }
        for row in top_funded_projects
    ]

    # 9. RECENT PROJECTS — every non-draft project, newest first, reusing the dataset
    # already fetched in section 1 rather than issuing a duplicate query.
    new_project_cutoff = add_days(now_datetime(), -7)
    recent_sorted = sorted(projects, key=lambda p: p.creation, reverse=True)

    data["recent_projects"] = [
        {
            "project_id": p.project_id,
            "project_title": p.project_title,
            "project_name": p.project_title,
            "pi_name": p.principal_investigator_name or "N/A",
            "principal_investigator": p.principal_investigator_name or "N/A",
            "department": p.department or "N/A",
            "creation": str(p.creation) if p.creation else "",
            "status": "Ongoing" if p.project_id in sanctioned_project_ids else "Submitted",
            "is_new": bool(p.creation and p.creation >= new_project_cutoff)
        }
        for p in recent_sorted
    ]

    return data



@frappe.whitelist()
def get_pi_dashboard_data(user=None):
    """
    PI Dashboard — Backend API
    Returns overview stats, active staff count, financial totals, and recent updates.
    """
    if not user:
        user = frappe.session.user

    if user == "Guest":
        return {}

    from frappe.utils import flt
    data = {}

    # 1. Project Overview — same status model as the Director Dashboard:
    # Draft = docstatus 0, or docstatus 1 stuck on workflow_state "Draft" (data inconsistency).
    # Rejected = docstatus 2 — tracked separately, never folded into another bucket.
    # Ongoing = non-draft, non-rejected project with at least one submitted Fund Sanction —
    # the same single source of truth used everywhere else in this module.
    # Pending Review = every other non-draft, non-rejected project (still moving through the
    # workflow, Approved but not yet sanctioned, or "Needs Correction" — unlike the aggregate
    # Director Dashboard, a PI's own "Needs Correction" projects are surfaced, not excluded,
    # since the PI needs to see and act on them).
    projects = frappe.get_all(
        "Project Registration",
        filters={"pi_webmail": user},
        fields=["name", "workflow_state", "docstatus"],
        ignore_permissions=True
    )

    total_projects = len(projects)
    project_names = [p.name for p in projects]

    draft_projects = 0
    rejected_projects = 0
    active_names = []

    for p in projects:
        if p.docstatus == 0 or (p.docstatus == 1 and p.workflow_state == "Draft"):
            draft_projects += 1
        elif p.docstatus == 2:
            rejected_projects += 1
        else:
            active_names.append(p.name)

    ongoing_projects = 0
    if active_names and frappe.db.exists("DocType", "Fund Sanction"):
        placeholders = ", ".join(["%s"] * len(active_names))
        ongoing_projects = len(frappe.db.sql_list(
            f"""SELECT DISTINCT project_proposal FROM `tabFund Sanction`
                WHERE docstatus = 1 AND project_proposal IN ({placeholders})""",
            tuple(active_names)
        ))

    pending_review = len(active_names) - ongoing_projects

    completion_rate = int((ongoing_projects / total_projects) * 100) if total_projects > 0 else 0

    # Active Staff (count rows in manpower_details across all PI projects)
    active_staff = 0
    if total_projects > 0:
        active_staff = frappe.db.count("project_registration_manpower_details", filters={"parent": ["in", project_names]})

    data["project_overview"] = {
        "total_projects": total_projects,
        "draft_projects": draft_projects,
        "rejected_projects": rejected_projects,
        "ongoing_projects": ongoing_projects,
        "completion_rate": completion_rate,
        "pending_review": pending_review,
        "active_staff": active_staff
    }

    # 2. Financial Summary
    total_allocation = 0.0
    utilized = 0.0
    
    if total_projects > 0 and frappe.db.exists("DocType", "Fund Sanction"):
        fund_sanctions = frappe.get_all(
            "Fund Sanction",
            filters={"project_proposal": ["in", project_names], "docstatus": 1},
            fields=["total_sanctioned_amount", "amount_received"],
            ignore_permissions=True
        )
        for fs in fund_sanctions:
            total_allocation += flt(fs.total_sanctioned_amount or 0)
            utilized += flt(fs.amount_received or 0)
        
    available = total_allocation - utilized
    utilization_rate = int((utilized / total_allocation) * 100) if total_allocation > 0 else 0
    
    # Pending requests
    pending_requests_amount = 0.0
    financial_doctypes = ["Reimbursement", "Temporary Advance", "Direct Purchase"]
    for dt in financial_doctypes:
        if frappe.db.exists("DocType", dt):
            meta = frappe.get_meta(dt)
            amt_field = None
            for f in ["total_amount", "grand_total", "amount", "net_amount", "total"]:
                if meta.has_field(f):
                    amt_field = f
                    break
            
            if amt_field:
                try:
                    rs = frappe.db.sql(f"SELECT IFNULL(SUM({amt_field}), 0) FROM `tab{dt}` WHERE docstatus=0 AND owner=%s", (user,))
                    if rs and rs[0][0]:
                        pending_requests_amount += flt(rs[0][0])
                except Exception as e:
                    frappe.log_error(f"Error summing pending requests for {dt}: {e}")
    # Try to grab current fiscal year string safely
    try:
        fiscal_year = frappe.utils.get_fiscal_year(frappe.utils.today())[0]
    except Exception:
        fiscal_year = "2023-24"

    data["financial_summary"] = {
        "total_allocation": total_allocation,
        "utilized": utilized,
        "available": available,
        "pending_requests": pending_requests_amount,
        "financial_year": fiscal_year,
        "utilization_rate": utilization_rate
    }
    
    # 3. Recent Updates
    recent_updates = []
    if frappe.db.exists("DocType", "Activity Log"):
        logs = frappe.get_all("Activity Log",
            filters={"user": user},
            fields=["subject", "creation"],
            order_by="creation desc"
        )
        for log in logs:
            recent_updates.append({
                "title": log.subject,
                "meta": str(log.creation)[:10],
                "type": "system"
            })
            
    # Fallback if no updates
    if not recent_updates:
        recent_updates = [
            {"title": "Welcome to your Dashboard", "meta": str(frappe.utils.today()), "type": "system"},
            {"title": "Please complete your profile", "meta": str(frappe.utils.today()), "type": "announcement"}
        ]
        
    data["recent_updates"] = recent_updates
    
    return data





@frappe.whitelist(allow_guest=True)
def get_role_based_project_counts():
    """
    Returns the count of projects for each user under specific roles:
    - 6i6gphpk2s (IR - Independent Researcher)
    - 6mcdqaqti2 (IF - Inspired Faculty)
    - 7orhr5qb5t (PI - Principal Investigator)
    - 5r4emiig95 (P - Permanent Employee)
    """
    query = """
        SELECT 
            pr.pi_webmail AS user_email, 
            pr.principal_investigator_name AS user_name,
            ec.empclass_name AS role,
            d1.dept_name AS implementation_department,
            d2.dept_name AS user_department,
            COUNT(pr.name) AS project_count 
        FROM `tabProject Registration` pr
        LEFT JOIN `tabEmployeeClass_prornd` ec ON pr.applicant_type = ec.name
        LEFT JOIN `tabUser` u ON pr.pi_webmail = u.name
        LEFT JOIN `tabDepartment_prornd` d1 ON pr.implementation_department = d1.name
        LEFT JOIN `tabDepartment_prornd` d2 ON u.department_name = d2.name
        WHERE pr.applicant_type IN ('6i6gphpk2s', '6mcdqaqti2', '7orhr5qb5t', '5r4emiig95')
          AND pr.docstatus < 2
        GROUP BY 
            pr.pi_webmail, 
            pr.principal_investigator_name, 
            ec.empclass_name,
            d1.dept_name,
            d2.dept_name
        ORDER BY role ASC, project_count DESC
    """
    
    # Executing raw SQL to bypass Frappe ORM complexities for this aggregation
    results = frappe.db.sql(query, as_dict=True)
    return results


# Doctypes documented in docs/project_registration/PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md
# as holding a Project Registration relationship (Link or plain Data field) that
# aren't (yet) registered as a visible entry in the "Module Registry" doctype below.
# That doc is markdown only — there's no live table to query it from — so this list
# has to be kept in sync by hand if the doc's PR-relationship audit is redone.
PR_LINKED_APPLICATIONS_NOT_IN_REGISTRY = [
    "AccountHeadPayment", "AMC", "Deposit slip", "Deposit Slip Project Credit",
    "Disbursement of Honorarium", "dp_po", "E Non Routine Deposit Slip",
    "Endorsement Data", "Extension Of Tenure Of Appointment", "myProjects", "NIQ",
    "payments", "Project Extension", "Project Verification", "proprietary_purchase",
    "Rate Contract", "repair_replacement", "Research Consultancy Deposit Slip",
    "Research Deposit Slip", "standerdized_purchase", "T Testing Deposit Slip",
    "UC Request", "User Delegation"
]


def get_application_doctype_names():
    """
    The app's "applications" — the union of every doctype flagged visible
    (`mod_vis=1`) in the live "Module Registry" doctype (the same list the app's
    own pending-task views use) and every doctype in
    PR_LINKED_APPLICATIONS_NOT_IN_REGISTRY above. Shared by get_module_process_counts
    and track_application so both agree on what counts as an "application".
    """
    registry_doctypes = frappe.get_all(
        "Module Registry Item", filters={"mod_vis": 1}, pluck="doctype_name"
    )
    return sorted(set(registry_doctypes) | set(PR_LINKED_APPLICATIONS_NOT_IN_REGISTRY))


@frappe.whitelist()
def get_module_process_counts():
    """
    Form-processing counts (today / this week / this month / all-time) for the
    app's "applications" — the union of every doctype flagged visible (`mod_vis=1`)
    in the live "Module Registry" doctype (the same list the app's own pending-task
    views use) and every doctype in PR_LINKED_APPLICATIONS_NOT_IN_REGISTRY above.
    Each parent has its own child-table doctypes nested underneath and counted the
    same way, plus daily/weekly/monthly trend series built from the parent-level
    data.

    "Processed" = not cancelled (docstatus < 2); a record's `creation` date is
    treated as its processing date. Windows are rolling (today = current calendar
    day, week = last 7 days, month = calendar-month-to-date), not per-doctype
    workflow-specific, since these doctypes have no single shared "processed"
    field to key off of.

    Child-table rows are counted per parent doctype (via `parenttype`, since a
    child doctype can in principle be attached to more than one parent) and are
    NOT folded into the top-level `totals` / trend series — those stay a count of
    actual submitted forms, not of every row in every child table.
    """
    from collections import defaultdict
    from frappe.utils import today, add_days, get_first_day, getdate

    today_date = getdate(today())
    week_start = add_days(today_date, -6)
    month_start = get_first_day(today_date)
    trend_start = add_days(today_date, -364)

    def fetch_counts(doctype_name, parenttype=None):
        where = "docstatus < 2"
        params = []
        if parenttype:
            where += " AND parenttype = %s"
            params.append(parenttype)

        total = frappe.db.sql(
            f"SELECT COUNT(*) FROM `tab{doctype_name}` WHERE {where}", tuple(params)
        )[0][0] or 0

        rows = frappe.db.sql(f"""
            SELECT DATE(creation) AS d, COUNT(*) AS c
            FROM `tab{doctype_name}`
            WHERE {where} AND creation >= %s
            GROUP BY DATE(creation)
        """, tuple(params) + (trend_start,), as_dict=True)

        return total, rows

    def bucket(rows):
        today_count = week_count = month_count = 0
        for row in rows:
            d, c = row.d, row.c or 0
            if d == today_date:
                today_count += c
            if d >= week_start:
                week_count += c
            if d >= month_start:
                month_count += c
        return today_count, week_count, month_count

    doctypes = frappe.get_all(
        "DocType",
        filters={"name": ["in", get_application_doctype_names()], "istable": 0, "issingle": 0},
        fields=["name", "module"],
        order_by="module, name"
    )
    modules = sorted({dt.module for dt in doctypes})

    daily_totals = defaultdict(int)
    doctype_counts = []
    totals = {"today": 0, "this_week": 0, "this_month": 0, "total": 0}

    for dt in doctypes:
        if not frappe.db.table_exists(dt.name):
            continue

        try:
            total_count, rows = fetch_counts(dt.name)
        except Exception:
            # Doctype table exists but query failed (e.g. missing docstatus/creation
            # on a legacy table) — skip rather than fail the whole dashboard.
            continue

        today_count, week_count, month_count = bucket(rows)
        for row in rows:
            daily_totals[row.d] += row.c or 0

        children = []
        for table_field in frappe.get_meta(dt.name).get_table_fields():
            child_doctype = table_field.options
            if not child_doctype or not frappe.db.table_exists(child_doctype):
                continue
            try:
                c_total, c_rows = fetch_counts(child_doctype, parenttype=dt.name)
            except Exception:
                continue
            c_today, c_week, c_month = bucket(c_rows)
            children.append({
                "doctype": child_doctype,
                "fieldname": table_field.fieldname,
                "today": c_today,
                "this_week": c_week,
                "this_month": c_month,
                "total": c_total
            })

        doctype_counts.append({
            "doctype": dt.name,
            "module": dt.module,
            "today": today_count,
            "this_week": week_count,
            "this_month": month_count,
            "total": total_count,
            "children": children
        })

        totals["today"] += today_count
        totals["this_week"] += week_count
        totals["this_month"] += month_count
        totals["total"] += total_count

    doctype_counts.sort(key=lambda x: x["total"], reverse=True)

    weekly_totals = defaultdict(int)
    monthly_totals = defaultdict(int)
    for d, c in daily_totals.items():
        weekly_totals[str(add_days(d, -d.weekday()))] += c
        monthly_totals[d.strftime("%Y-%m")] += c

    return {
        "modules": modules,
        "totals": totals,
        "doctype_counts": doctype_counts,
        "daily_trend": [{"date": str(d), "count": c} for d, c in sorted(daily_totals.items())],
        "weekly_trend": [{"week_start": k, "count": v} for k, v in sorted(weekly_totals.items())],
        "monthly_trend": [{"month": k, "count": v} for k, v in sorted(monthly_totals.items())]
    }


@frappe.whitelist()
def track_application(docname, doctype=None):
    """
    Application Tracker — given a docname (and, only if that name exists in more
    than one doctype, its `doctype` to disambiguate), returns:
      - current workflow status (state + docstatus)
      - previous vs current workflow state
      - who it's currently pending with (role, from the live Workflow definition,
        and any concrete user(s) via open ToDo assignments)
      - the last completed workflow action and the last user to touch the document
      - the 5 most recent activities (edits, workflow actions, comments)

    Built on module_registry.py's `_build_document_touch_history` (which already
    merges Version/Workflow Action/Comment into one timeline) rather than
    re-deriving that logic, plus the live Workflow definition and ToDo — both
    existing Frappe mechanisms — for the "pending with" piece.

    Doctype is resolved against get_application_doctype_names() (the same
    "application" list get_module_process_counts uses) when not given explicitly.

    Permission is whatever the caller already has on the resolved document
    (frappe.has_permission) — this endpoint isn't gated to an admin role list,
    since an applicant tracking their own submission needs to call it too.

    Additionally, if the application links to a Project Registration (a real
    Link field, discovered from the doctype's own metadata — no hardcoded
    per-doctype map needed), the caller must be that project's owner/PI or
    otherwise hold read permission on it (frappe.has_permission again, so
    User Permissions / Shares / role perms on Project Registration all apply).
    Without that, nothing is returned at all — even a caller who can read the
    application doctype itself is refused if they have no standing on the
    project it belongs to. System Manager always passes.
    """
    from rndopsapp.rndopsapp.doctype.module_registry.module_registry import (
        _build_document_touch_history, DEPT_FIELD_MAP, HEAD_FIELD_MAP, SPECIFIC_APPROVER_MAP
    )

    docname = (docname or "").strip()
    if not docname:
        return {"success": False, "message": "docname is required."}

    if doctype:
        if not frappe.db.exists("DocType", doctype):
            return {"success": False, "message": f"DocType '{doctype}' does not exist."}
        candidates = [doctype]
    else:
        candidates = get_application_doctype_names()

    matches = []
    for dt in candidates:
        if not frappe.db.exists("DocType", dt):
            continue
        if frappe.get_meta(dt).istable:
            continue
        if not frappe.db.exists(dt, docname):
            continue
        if not frappe.has_permission(dt, "read", doc=docname):
            continue
        matches.append(dt)

    if not matches:
        return {"success": False, "message": f"No application found with ID '{docname}'."}

    if len(matches) > 1:
        return {
            "success": False,
            "message": (
                f"'{docname}' exists in more than one doctype ({', '.join(matches)}). "
                "Pass `doctype` to disambiguate."
            ),
            "matches": matches
        }

    dt = matches[0]
    meta = frappe.get_meta(dt)

    # Project-level access gate: if this application links to a Project
    # Registration (a real Link field, discovered from the doctype's own
    # metadata rather than a hardcoded per-doctype map), the caller must own
    # that project (its `owner` or `pi_webmail`) or otherwise hold read
    # permission on it — reusing frappe.has_permission so User Permissions,
    # role perms, and Shares on Project Registration all apply automatically.
    # Without that, the application is not returned at all, even though the
    # caller already passed the has_permission check on `dt` itself above.
    session_user = frappe.session.user
    is_system_manager = "System Manager" in frappe.get_roles(session_user)
    linked_project = None

    pr_name = docname if dt == "Project Registration" else None
    if pr_name is None:
        for link_field in meta.get_link_fields():
            if link_field.options == "Project Registration":
                pr_name = frappe.db.get_value(dt, docname, link_field.fieldname)
                if pr_name:
                    break

    # Several application doctypes (Direct Purchase, AMC, NIQ, sanction_sheet,
    # Rate Contract, etc. — see PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md
    # Section 2) have no real Link field to Project Registration, only a plain
    # Data field copying the PR's `project_no`. Fall back to resolving the PR
    # by that value when no Link field produced one.
    if pr_name is None:
        for data_field in ("project_no", "project_number", "project_code", "upfa_project_code", "igf_project_code"):
            if meta.has_field(data_field):
                value = frappe.db.get_value(dt, docname, data_field)
                if value:
                    pr_name = frappe.db.get_value("Project Registration", {"project_no": value}, "name")
                    if pr_name:
                        break

    if pr_name and frappe.db.exists("Project Registration", pr_name):
        pr = frappe.db.get_value(
            "Project Registration", pr_name, ["name", "project_no", "owner", "pi_webmail"], as_dict=True
        )
        is_owner = session_user in {pr.owner, pr.pi_webmail}
        has_project_access = (
            is_system_manager
            or is_owner
            or frappe.has_permission("Project Registration", "read", doc=pr.name, user=session_user)
        )
        if not has_project_access:
            return {
                "success": False,
                "message": (
                    f"Access denied: you do not have permission to view the project "
                    f"({pr.project_no or pr.name}) linked to this application."
                )
            }
        linked_project = {"name": pr.name, "project_no": pr.project_no}

    status_field = None
    for field_name in ["workflow_state", "status", "state"]:
        if meta.has_field(field_name):
            status_field = field_name
            break

    touch = _build_document_touch_history(dt, docname, meta)
    timeline = touch["timeline"]  # ascending by timestamp
    current_state = touch["current_status"]
    docstatus = touch["docstatus"]
    docstatus_label = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(docstatus, str(docstatus))

    # Previous workflow state: a "Workflow Action" row's `workflow_state` is set
    # to whatever state the document was in when that action was opened, so the
    # most recently COMPLETED one names the state immediately before whichever
    # transition produced `current_state`.
    previous_state = None
    if status_field:
        last_completed = frappe.get_all(
            "Workflow Action",
            filters={"reference_doctype": dt, "reference_name": docname, "status": "Completed"},
            fields=["workflow_state"],
            order_by="creation desc",
            limit_page_length=1
        )
        if last_completed:
            previous_state = last_completed[0].workflow_state

    # Pending role(s): read straight off the live Workflow definition for this
    # doctype — the roles allowed to transition (or, failing that, edit) the
    # document out of its current state. A role string can itself contain a
    # comma (e.g. "staff, RnD"), so tokens are only kept when they exactly match
    # a real Role name rather than being naively comma-split.
    pending_roles = []
    is_terminal = docstatus == 2
    if status_field and current_state and not is_terminal:
        all_role_names = set(frappe.get_all("Role", pluck="name"))

        def resolve_roles(raw):
            if not raw:
                return set()
            found = set()
            raw = str(raw).strip()
            if raw in all_role_names:
                found.add(raw)
            for line in raw.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line in all_role_names:
                    found.add(line)
                    continue
                for part in line.split(","):
                    part = part.strip()
                    if part in all_role_names:
                        found.add(part)
            return found

        role_set = set()
        has_declared_next_step = False
        for wfn in frappe.get_all("Workflow", filters={"document_type": dt}, pluck="name"):
            wf_doc = frappe.get_doc("Workflow", wfn)
            for transition_row in wf_doc.transitions:
                if transition_row.state == current_state:
                    has_declared_next_step = True
                    role_set |= resolve_roles(transition_row.allowed)
            if not role_set:
                for state_row in wf_doc.states:
                    if state_row.state == current_state and resolve_roles(state_row.allow_edit):
                        has_declared_next_step = True
                        role_set |= resolve_roles(state_row.allow_edit)

        # "Administrator" is the site's built-in superuser role, not a real
        # business approver — some workflows fall back to it as a placeholder
        # `allow_edit` when the actual next step is handled by a custom app
        # action instead of a declared Workflow Transition (e.g. Direct
        # Purchase's "POGenerated" state). Never present it as who an
        # application is pending with.
        role_set.discard("Administrator")

        pending_roles = sorted(role_set)
        # Terminal only when the workflow declares no next step at all for this
        # state — NOT merely because every declared role got filtered out above
        # (that means "no identifiable business approver here", not "done").
        is_terminal = not has_declared_next_step

    # Specific approver(s): some states are scoped to one exact person (their
    # email stored on the document) rather than a role. Reuses the exact field
    # maps get_pending_task uses, so the two endpoints can't disagree about who
    # a document is really waiting on.
    specific_approvers = []
    if not is_terminal and current_state:
        if current_state == "Pending Head Approval":
            head_field = HEAD_FIELD_MAP.get(dt)
            if head_field and meta.has_field(head_field):
                email = frappe.db.get_value(dt, docname, head_field)
                if email:
                    specific_approvers.append(email)
            elif dt in DEPT_FIELD_MAP and meta.has_field(DEPT_FIELD_MAP[dt]):
                dept_value = frappe.db.get_value(dt, docname, DEPT_FIELD_MAP[dt])
                if dept_value:
                    dept_head = (
                        frappe.db.get_value("Department_prornd", {"name": dept_value}, "dept_head")
                        or frappe.db.get_value("Department_prornd", {"dept_name": dept_value}, "dept_head")
                    )
                    if dept_head:
                        specific_approvers.append(dept_head)

        sa = SPECIFIC_APPROVER_MAP.get(dt)
        if sa:
            sa_state, sa_field = sa
            if current_state == sa_state and meta.has_field(sa_field):
                email = frappe.db.get_value(dt, docname, sa_field)
                if email:
                    specific_approvers.append(email)

    specific_approvers = sorted(set(specific_approvers))

    # Pending user(s): open ToDo assignments on this document (the existing
    # Frappe assignment mechanism — e.g. via "Assign To").
    assignments = frappe.get_all(
        "ToDo",
        filters={"reference_type": dt, "reference_name": docname, "status": "Open"},
        fields=["allocated_to", "description", "priority", "date"],
        order_by="creation desc"
    )

    recent_activity = list(reversed(timeline))[:5]
    last_action = recent_activity[0] if recent_activity else None

    return {
        "success": True,
        "doctype": dt,
        "docname": docname,
        "title": touch["title"],
        "project_no": linked_project.get("project_no") if linked_project else None,
        "linked_project": linked_project,
        "current_status": {
            "workflow_state": current_state,
            "docstatus": docstatus,
            "docstatus_label": docstatus_label
        },
        "workflow_progress": {
            "previous_state": previous_state,
            "current_state": current_state
        },
        "pending_with": {
            "state": None if is_terminal else current_state,
            "roles": pending_roles,
            "specific_approvers": specific_approvers,
            "assigned_to": [a.allocated_to for a in assignments],
            "is_terminal": is_terminal
        },
        "assignments": assignments,
        "created": {"by": touch["owner"], "on": touch["creation"]},
        "last_user": touch["modified_by"],
        "last_action": last_action,
        "recent_activity": recent_activity
    }

