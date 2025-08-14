import frappe
from frappe.model.workflow import apply_workflow

@frappe.whitelist()
def get_allowed_actions(doctype, docname):
    """
    Returns a list of workflow actions permitted for the current user based on their roles.
    """
    try:
        workflow_name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1})
        if not workflow_name:
            return []

        doc = frappe.get_doc(doctype, docname)
        transitions = frappe.get_all(
            "Workflow Transition",
            filters={"parent": workflow_name, "state": doc.workflow_state},
            fields=["action", "next_state", "allowed"]
        )
        
        user_roles = frappe.get_roles()
        allowed_actions = []
        for t in transitions:
            if t.allowed in user_roles:
                allowed_actions.append({"action": t.action, "label": t.action})  # Assuming action can be used as label
        return allowed_actions
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_allowed_actions failed")
        return []


@frappe.whitelist()
def handle_workflow_action(doctype, docname, action):
    """
    Applies a workflow action to a document after verifying user permissions.
    """
    try:
        # Security check: verify the user is allowed to perform this action
        allowed_actions = get_allowed_actions(doctype, docname)
        if not any(a['action'] == action for a in allowed_actions):
            frappe.throw(f"Action '{action}' not permitted for the current user.", frappe.PermissionError)

        doc = frappe.get_doc(doctype, docname)
        apply_workflow(doc, action)
        frappe.db.commit()
        return doc
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "handle_workflow_action failed")
        frappe.throw(str(e))

@frappe.whitelist(allow_guest=True)
def get_user_roles():
    """
    Returns the roles of the currently logged-in user.
    """
    if frappe.session.user == "Guest":
        return []
    
    return frappe.get_roles(frappe.session.user)

@frappe.whitelist()
def get_project_activity(doctype, docname):
    """
    Fetches all comments, workflow history, and communications for a given document.
    """
    frappe.log_error(f"Fetching activity for {doctype} - {docname}", "get_project_activity")
    try:
        comments = frappe.get_all(
            "Comment",
            filters={"reference_doctype": doctype, "reference_name": docname},
            fields=["content", "owner", "creation", "comment_type"],
            order_by="creation desc"
        )
        
        communications = frappe.get_all(
            "Communication",
            filters={"reference_doctype": doctype, "reference_name": docname},
            fields=["content", "sender as owner", "creation", "communication_type as comment_type"],
            order_by="creation desc"
        )
        
        activity = sorted(comments + communications, key=lambda k: k['creation'], reverse=True)
        return activity
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_project_activity failed")
        return []

# @frappe.whitelist()
# def add_project_comment(doctype, docname, content):
#     """
#     Adds a comment to a given document.
#     """
#     try:
#         comment = frappe.new_doc("Comment")
#         comment.comment_type = "Comment"
#         comment.reference_doctype = doctype
#         comment.reference_name = docname
#         comment.content = content
#         comment.insert(ignore_permissions=True)
#         frappe.db.commit()
#         return comment
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "add_project_comment failed")
#         frappe.throw(str(e))



@frappe.whitelist()
def add_project_comment(doctype, docname, content):
    """
    Adds a sanitized comment to a given document, ensuring it's not empty.
    """
    if not content or not content.strip():
        frappe.throw("Comment content cannot be empty.")

    sanitized_content = sanitize_html(content)

    try:
        if not frappe.db.exists(doctype, docname):
            frappe.throw(f"Document {doctype} {docname} not found.")

        comment = frappe.new_doc("Comment")
        comment.comment_type = "Comment"
        comment.reference_doctype = doctype
        comment.reference_name = docname
        comment.content = sanitized_content
        comment.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return comment
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "add_project_comment failed")
        frappe.throw(str(e))