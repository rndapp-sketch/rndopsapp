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

    # Completed projects - docstatus=1 but NOT in 'Approved' state (those are ongoing)
    ongoing_projects = frappe.db.count("Project Registration", filters={"docstatus": 1, "workflow_state": ["not in", ["Approved"]]})

    # Total staff count - count from manpower details child table across all projects
    total_staff_count = frappe.db.sql("""
        SELECT COUNT(*)
        FROM `tabproject_registration_manpower_details`
    """)[0][0] or 0

    data["project_overview"] = {
        "total_projects": total_projects,
        "research_projects": research_projects,
        "consultancy_projects": consultancy_projects,
        "ongoing_projects": ongoing_projects,
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

    # 1. Project Overview
    projects = frappe.get_all(
        "Project Registration",
        filters={"pi_webmail": user},
        fields=["name", "workflow_state", "docstatus"],
        ignore_permissions=True
    )
    
    total_projects = len(projects)
    draft_projects = 0
    pending_review = 0
    ongoing_projects = 0
    
    draft_states = ["Draft", "Endorsement Draft"]
    
    for p in projects:
        if p.docstatus == 0 and p.workflow_state in draft_states:
            draft_projects += 1
        elif p.docstatus == 1 and p.workflow_state == "Approved":
            # Approved = ongoing project (registered & being worked on)
            pending_review += 1
        elif p.docstatus == 1:
            ongoing_projects += 1
        else:
            if p.workflow_state not in draft_states and p.workflow_state != 'Rejected':
                pending_review += 1
    
    completion_rate = int((ongoing_projects / total_projects) * 100) if total_projects > 0 else 0
    
    # Active Staff (count rows in manpower_details across all PI projects)
    active_staff = 0
    if total_projects > 0:
        project_names = [p.name for p in projects]
        active_staff = frappe.db.count("project_registration_manpower_details", filters={"parent": ["in", project_names]})
    
    data["project_overview"] = {
        "total_projects": total_projects,
        "draft_projects": draft_projects,
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
            order_by="creation desc", 
            limit=3
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

