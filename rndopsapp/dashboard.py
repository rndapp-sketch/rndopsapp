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
