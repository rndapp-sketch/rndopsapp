import frappe

@frappe.whitelist(allow_guest=True)
def get_dashboard_data(user_email, department):
    data = {}

    # 1. User Data
    user_data = frappe.get_all(
        "User",
        filters={"email": user_email},
        fields=["full_name"]
    )

    # Fetch user roles from the Has Role child table
    user_roles = frappe.get_all(
        "Has Role",
        filters={"parent": user_email, "parenttype": "User"},
        fields=["role"]
    )

    data["user_data"] = {
        **(user_data[0] if user_data else {}),
        "roles": [r.role for r in user_roles]
    }

    # 2. Pending Approvals
    pending_approvals = frappe.get_list(
        "Approval Request",
        filters={"assigned_to": user_email, "status": "Pending"},
        fields=["title", "description", "request_type", "creation"],
        order_by="creation desc",
        limit=5
    )
    data["pending_approvals"] = pending_approvals

    # 3. Recent Submissions
    recent_submissions = frappe.get_list(
        "Approval Request",
        filters={"requested_by": user_email},
        fields=["title", "description", "request_type", "status", "creation"],
        order_by="creation desc",
        limit=5
    )
    data["recent_submissions"] = recent_submissions

    # 4. Department Projects Analytics
    department_projects = frappe.get_list(
        "Project",
        filters={"department": department},
        fields=[
            "project_name", "status", "principal_investigator",
            "start_date", "end_date", "completion_date"
        ]
    )
    data["department_projects"] = department_projects

    total_projects_count = frappe.db.count("Project", filters={"department": department})

    # Count active PIs — now using Has Role properly
    active_pis = frappe.get_all(
        "Has Role",
        filters={"role": "Principal Investigator"},
        fields=["parent"]
    )
    active_pis_count = len({
        pi["parent"]
        for pi in active_pis
        if frappe.db.get_value("User", pi["parent"], "department") == department
    })

    completed_this_year_count = frappe.db.count(
        "Project",
        filters={
            "department": department,
            "status": "Completed",
            "completion_date": ["between", [frappe.utils.get_year_start(), frappe.utils.get_year_end()]]
        }
    )
    data["project_analytics"] = {
        "total_projects": total_projects_count,
        "active_pis": active_pis_count,
        "completed_this_year": completed_this_year_count
    }

    # 5. Department Funds Analytics
    department_budget = frappe.get_all(
        "Department Budget",
        filters={
            "department": department,
            "fiscal_year": frappe.utils.get_fiscal_year(frappe.utils.today())
        },
        fields=["total_allocation", "utilized_amount", "pending_requests_amount"]
    )

    if department_budget:
        budget = department_budget[0]
        available_funds = budget.total_allocation - budget.utilized_amount - budget.pending_requests_amount
        utilization_rate = (budget.utilized_amount / budget.total_allocation * 100) if budget.total_allocation else 0
        data["fund_analytics"] = {
            "total_allocation": budget.total_allocation,
            "utilized_amount": budget.utilized_amount,
            "pending_requests_amount": budget.pending_requests_amount,
            "available_funds": available_funds,
            "utilization_rate": utilization_rate
        }
    else:
        data["fund_analytics"] = {}

    return data


@frappe.whitelist()
def get_director_dashboard_data():
    """
    Director Dashboard — Backend API
    Returns comprehensive analytics for all projects, funding, IPR, and proposals
    """
    data = {}

    # 1. PROJECT OVERVIEW — KPI Strip
    total_projects = frappe.db.count("Project Registration")
    research_projects = frappe.db.count("Project Registration", filters={"project_type": "Research"})
    consultancy_projects = frappe.db.count("Project Registration", filters={"project_type": "Consultancy"})

    # Completed projects - checking workflow_state or docstatus
    completed_projects = frappe.db.count("Project Registration", filters={"docstatus": 1})

    # Total staff count - count from manpower details child table across all projects
    total_staff_count = frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabproject_registration_manpower_details`
    """)[0][0] or 0

    data["project_overview"] = {
        "total_projects": total_projects,
        "research_projects": research_projects,
        "consultancy_projects": consultancy_projects,
        "completed_projects": completed_projects,
        "total_staff_count": total_staff_count
    }

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

    data["funding_analytics"] = {
        "total_allocation": float(total_allocation),
        "utilized": float(utilized),
        "remaining": float(remaining)
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
    # Get projects grouped by year with status breakdown
    project_status_by_year = frappe.db.sql("""
        SELECT
            YEAR(creation) as year,
            COUNT(*) as registered,
            SUM(CASE WHEN docstatus = 0 THEN 1 ELSE 0 END) as ongoing,
            SUM(CASE WHEN docstatus = 1 THEN 1 ELSE 0 END) as completed
        FROM `tabProject Registration`
        GROUP BY YEAR(creation)
        ORDER BY year DESC
        LIMIT 5
    """, as_dict=True)

    data["project_status_by_year"] = [
        {
            "year": str(row.year),
            "registered": row.registered or 0,
            "ongoing": row.ongoing or 0,
            "completed": row.completed or 0
        }
        for row in project_status_by_year
    ]

    # 7. FUNDING SOURCES — Pie Chart
    funding_sources = frappe.db.sql("""
        SELECT
            IFNULL(funding_agen, 'Unknown') as name,
            COUNT(*) as value
        FROM `tabProject Registration`
        WHERE funding_agen IS NOT NULL AND funding_agen != ''
        GROUP BY funding_agen
        ORDER BY value DESC
        LIMIT 10
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
            pr.implementation_department as department,
            IFNULL(pr.total_budget_amount, 0) as total_budget_amount
        FROM `tabProject Registration` pr
        WHERE pr.total_budget_amount IS NOT NULL
        ORDER BY pr.total_budget_amount DESC
        LIMIT 10
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

    # 9. RECENT PROJECTS — Recent Registrations List
    recent_projects = frappe.db.sql("""
        SELECT
            pr.name as project_id,
            pr.project_title,
            pr.principal_investigator_name as pi_name,
            pr.implementation_department as department,
            pr.creation
        FROM `tabProject Registration` pr
        ORDER BY pr.creation DESC
        LIMIT 10
    """, as_dict=True)

    data["recent_projects"] = [
        {
            "project_id": row.project_id,
            "project_title": row.project_title,
            "pi_name": row.pi_name or "N/A",
            "department": row.department or "N/A",
            "creation": str(row.creation) if row.creation else ""
        }
        for row in recent_projects
    ]

    return data
