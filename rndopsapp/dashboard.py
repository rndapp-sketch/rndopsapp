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

    today = frappe.utils.today()

    # Get mutually exclusive statuses for all approved projects
    project_statuses = frappe.db.sql("""
        SELECT
            pr.name as project_id,
            CASE 
                WHEN pr.prj_end_date IS NOT NULL AND pr.prj_end_date < %s THEN 'completed'
                WHEN (pr.prj_end_date IS NULL OR pr.prj_end_date >= %s)
                 AND (
                     EXISTS (SELECT 1 FROM `tabFund Sanction` fs WHERE fs.project_proposal = pr.name AND fs.docstatus = 1)
                     OR 
                     EXISTS (SELECT 1 FROM `tabFund Received` fr WHERE fr.prjreg_title = pr.name AND fr.docstatus = 1)
                 ) THEN 'ongoing'
                WHEN (pr.prj_end_date IS NULL OR pr.prj_end_date >= %s)
                 AND NOT EXISTS (SELECT 1 FROM `tabFund Sanction` fs WHERE fs.project_proposal = pr.name AND fs.docstatus = 1)
                 AND NOT EXISTS (SELECT 1 FROM `tabFund Received` fr WHERE fr.prjreg_title = pr.name AND fr.docstatus = 1)
                 THEN 'submitted'
                ELSE 'other'
            END as status
        FROM `tabProject Registration` pr
        WHERE pr.docstatus = 1
    """, (today, today, today), as_dict=True)

    completed_projects = [p.project_id for p in project_statuses if p.status == 'completed']
    ongoing_projects = [p.project_id for p in project_statuses if p.status == 'ongoing']
    submitted_projects = [p.project_id for p in project_statuses if p.status == 'submitted']

    # Total staff count - count Users where employee class is 'PS - Project Staff' (ID: 64rqq35p8v)
    total_staff_count = frappe.db.count("User", filters={"empclass": "64rqq35p8v"}) or 0

    data["project_overview"] = {
        "total_projects": len(ongoing_projects) + len(submitted_projects),
        "research_projects": research_projects,
        "consultancy_projects": consultancy_projects,
        "submitted_projects": len(submitted_projects),
        "submitted_project_nos": submitted_projects,
        "ongoing_projects": len(ongoing_projects),
        "ongoing_project_nos": ongoing_projects,
        "completed_projects": len(completed_projects),
        "completed_project_nos": completed_projects,
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
        LIMIT 10
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
        GROUP BY YEAR(IFNULL(pr.prj_start_date, pr.creation))
        ORDER BY year DESC
        LIMIT 5
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
            IFNULL(fa.funding_agency_name, IFNULL(pr.funding_agen, 'Unknown')) as name,
            COUNT(*) as value
        FROM `tabProject Registration` pr
        LEFT JOIN `tabfundingagency_` fa ON fa.name = pr.funding_agen
        WHERE pr.funding_agen IS NOT NULL AND pr.funding_agen != ''
        GROUP BY pr.funding_agen, fa.funding_agency_name
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
            IFNULL(d.dept_name, pr.implementation_department) as department,
            IFNULL(pr.total_budget_amount, 0) as total_budget_amount
        FROM `tabProject Registration` pr
        LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
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
            IFNULL(d.dept_name, pr.implementation_department) as department,
            pr.creation
        FROM `tabProject Registration` pr
        LEFT JOIN `tabDepartment_prornd` d ON d.name = pr.implementation_department
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

