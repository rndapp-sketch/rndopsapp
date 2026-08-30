"""
Whitelisted endpoints for the Email Manager pipeline — backs both the
Email Manager DocType form (get_doctype_workflow_states) and the
/email_manager admin page (everything else: template CRUD, log listing,
manual resend).
"""

import frappe


def _require_system_manager():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw("Only System Manager can access Email Manager.", frappe.PermissionError)


@frappe.whitelist()
def get_doctype_workflow_states(doctype: str):
    """
    Backs the Email Manager form's "Doc Status" grid: the workflow_state
    values valid for whichever DocType was picked in "module", so the user
    picks from a real dropdown instead of free-typing a status string that
    might never actually occur. Returns [] (not an error) when the DocType
    has no Workflow — the grid just has nothing to offer yet.
    """
    if not doctype:
        return []

    workflow_name = frappe.get_value("Workflow", {"document_type": doctype}, "name")
    if not workflow_name:
        return []

    states = frappe.get_all(
        "Workflow Document State",
        filters={"parent": workflow_name, "parenttype": "Workflow"},
        fields=["state"],
        order_by="idx asc",
    )
    # dict.fromkeys dedupes while preserving order (a state can legitimately
    # appear more than once as the target of different transitions).
    return list(dict.fromkeys(s.state for s in states if s.state))


# ---------------------------------------------------------------------------
# Templates (Email Notification Template) — list/get/save for the
# /email_manager page's Templates tab. Content is edited as plain text
# there, never as a rendered/WYSIWYG preview.
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_email_templates():
    _require_system_manager()
    return frappe.get_all(
        "Email Notification Template",
        fields=["name", "template_name", "category", "is_active", "modified"],
        order_by="category asc, template_name asc",
    )


@frappe.whitelist()
def get_email_template(name: str):
    _require_system_manager()
    doc = frappe.get_doc("Email Notification Template", name)
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "category": doc.category,
        "is_active": doc.is_active,
        "content": doc.content,
    }


@frappe.whitelist()
def save_email_template(
    name: str = None,
    template_name: str = None,
    category: str = None,
    content: str = None,
    is_active: int = 1,
):
    """
    Create (name not given / doesn't exist) or update (name given) an
    Email Notification Template. This is the only write path the
    /email_manager page's Templates tab uses — "Save" and "+ New
    Template" both call this.
    """
    _require_system_manager()

    template_name = (template_name or "").strip()
    if not template_name:
        frappe.throw("Template Name is required.")
    if content is None:
        frappe.throw("Template content is required.")

    if name and frappe.db.exists("Email Notification Template", name):
        doc = frappe.get_doc("Email Notification Template", name)
    elif frappe.db.exists("Email Notification Template", template_name):
        doc = frappe.get_doc("Email Notification Template", template_name)
    else:
        doc = frappe.new_doc("Email Notification Template")

    doc.template_name = template_name
    doc.category = category or ""
    doc.content = content
    doc.is_active = 1 if int(is_active or 0) else 0
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "saved", "name": doc.name}


@frappe.whitelist()
def preview_email_template(content: str):
    """
    Renders arbitrary (possibly unsaved) template source with fixed sample
    data, for the Templates tab's "Preview" button. Jinja has to run
    server-side, so this can't be done in the browser — the page opens the
    returned HTML in a sandboxed iframe.
    """
    _require_system_manager()

    if not content:
        frappe.throw("No content to preview.")

    sample_doc = frappe._dict(
        {
            "name": "SAMPLE-2026-00123",
            "doctype": "Sample DocType",
            "owner": frappe.session.user,
            "workflow_state": "Pending Staff Approval",
            "modified": frappe.utils.now(),
            "project_no": "PRJ-2026-0099",
            "project_number": "PRJ-2026-0099",
        }
    )

    try:
        return frappe.render_template(
            content, {"doc": sample_doc, "recipient_name": "Sample User", "frappe": frappe}
        )
    except Exception as e:
        frappe.throw(f"Template failed to render: {e}")


# ---------------------------------------------------------------------------
# Email Send Logs — listing + manual resend for the page's Logs tab.
# ---------------------------------------------------------------------------


@frappe.whitelist()
def list_email_send_logs(limit: int = 200, status: str = None):
    _require_system_manager()

    filters = {}
    if status:
        filters["status"] = status

    return frappe.get_all(
        "Email Send Logs",
        filters=filters,
        fields=[
            "name", "module", "reference_doctype", "reference_name",
            "previous_status", "new_status", "recipients", "subject",
            "template_reference", "task_id", "attempt_number", "retry_count",
            "status", "final_result", "error_message", "sent_at",
            "last_retry_at", "creation",
        ],
        order_by="creation desc",
        limit_page_length=int(limit or 200),
    )


def _resolve_template_for_resend(log) -> str | None:
    """
    Prefer the CURRENT Email Manager config's template for this doctype —
    matches what a fresh notification would use right now, and self-heals
    old Email Send Logs rows whose template_reference predates the move to
    DB-backed templates (used to store a file path under
    rndopsapp/rndopsapp/templates/emails/..., not a template name — a
    stale one of those silently falls through to dispatch_notification's
    plain-text fallback, which is why an old resend can come out with "no
    design"). Falls back to the log's own template_reference only if it
    happens to already be a valid template name.

    Since templates became per-status (2026-08-29), "current" means: the
    Doc Status row matching log.new_status's own template, else the
    parent Email Manager's default template — the same order
    workflow_monitor._get_matching_config uses for a fresh notification.
    """
    row_template = frappe.db.get_value(
        "Email Manager Status",
        {"parent": log.reference_doctype, "parenttype": "Email Manager", "status": log.new_status},
        "template",
    )
    if row_template and frappe.db.exists("Email Notification Template", row_template):
        return row_template

    default_template = frappe.db.get_value("Email Manager", log.reference_doctype, "template")
    if default_template and frappe.db.exists("Email Notification Template", default_template):
        return default_template

    if log.template_reference and frappe.db.exists("Email Notification Template", log.template_reference):
        return log.template_reference

    return None


@frappe.whitelist()
def resend_email_notification(log_name: str):
    """
    Manually re-publish an Email Send Logs row — any status, not just
    Failed (an admin may want to resend a Success just as much as retry a
    Failed one). Re-renders the template fresh from both the current
    document state AND the current template content, so a resend after
    either was edited reflects reality rather than replaying stale HTML.
    """
    _require_system_manager()

    log = frappe.get_doc("Email Send Logs", log_name)

    template_name = _resolve_template_for_resend(log)
    if not template_name:
        frappe.throw(
            f"No Email Notification Template is configured for '{log.reference_doctype}' "
            "(check Email Manager) — nothing to resend with."
        )

    from rndopsapp.rndopsapp.email.workflow_monitor import dispatch_notification

    log.attempt_number = (log.attempt_number or 1) + 1
    log.retry_count = (log.retry_count or 0) + 1
    log.status = "Pending"
    log.error_message = ""
    log.template_reference = template_name  # heal any stale (pre-DB-template) reference
    log.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.enqueue(
        dispatch_notification,
        queue="short",
        job_name=f"email-manager-resend-{log.name}",
        log_name=log.name,
        doctype_name=log.reference_doctype,
        docname=log.reference_name,
        recipients=[e.strip() for e in (log.recipients or "").split(",") if e.strip()],
        subject=log.subject,
        template_name=template_name,
    )

    return {"status": "queued", "log_name": log.name}
