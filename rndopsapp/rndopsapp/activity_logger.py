import frappe
from frappe.utils import now_datetime, time_diff_in_hours

TRACKED_DOCTYPES = {
    # Purchase
    "Direct Purchase":              "Purchase",
    "Proprietary Purchase":         "Purchase",
    "Standerdized Purchase":        "Purchase",
    "Repair Replacement":           "Purchase",
    "Indent General Form":          "Purchase",
    "Indent Cum Sanction Sheet":    "Purchase",
    "Rate Contract":                "Purchase",
    "AMC":                          "Purchase",
    "DP PO":                        "Purchase",
    "NIQ":                          "Purchase",
    # Financial
    "Temporary Advance":            "Financial",
    "Advance Settlement":           "Financial",
    "TA DA Settlement":             "Financial",
    "Reimbursement":                "Financial",
    "Loan Request":                 "Financial",
    "P 11 Form":                    "Financial",
    # Project
    "Project Registration":         "Project",
    "Project Proposal":             "Project",
    "Project Extension":            "Project",
    "Fund Received":                "Project",
    "Fund Sanction":                "Project",
    "Project Sanction Details":     "Project",
    "UC Request":                   "Project",
    "Myprojects":                   "Project",
    # HR / Staff
    "Recruitment Adhoc Contractual":        "HR / Staff",
    "Project Staff Details":                "HR / Staff",
    "Extension of Tenure of Appointment":   "HR / Staff",
    "Project Staff Resignation":            "HR / Staff",
    "Leave Module":                         "HR / Staff",
    "Top Up Fellowship":                    "HR / Staff",
    "Selection Committee Report":           "HR / Staff",
    # Deposits
    "Deposit Slip":                         "Deposits",
    "Research Deposit Slip":                "Deposits",
    "Research Consultancy Deposit Slip":    "Deposits",
    "Disbursal of Consultancy":             "Deposits",
    "Disbursal of Honorarium":              "Deposits",
    "Disbursement of Honorarium":           "Deposits",
    # Travel
    "Travel":                       "Travel",
    # IPR
    "IPR Invention Disclosure":     "IPR",
    # Other
    "Cancellation Request":         "Other",
    "Endorsement Data":             "Other",
    "Sanction Sheet":               "Other",
    "PO Commit Adjustment":         "Other",
}


# Keys the frontend uses for the note typed into the action dialog.
_COMMENT_KEYS = ("comment", "remark", "remarks", "approval_comment")


def _extract_action_comment():
	"""
	Read the approver's typed note off the current request.

	The action dialogs post it as `comment` alongside the workflow action, but
	most `perform_*_action` endpoints don't declare that parameter and Frappe
	drops kwargs that aren't in a whitelisted method's signature — so the text
	never reached the document. It is still on the request, so take it here.
	"""
	form = getattr(frappe.local, "form_dict", None) or {}
	for key in _COMMENT_KEYS:
		value = form.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return None


def record_workflow_action_comment(doc, method=None):
	"""
	Record the note an approver typed when forwarding / approving / rejecting /
	putting back, as a real comment on the document.
	"""
	if not getattr(doc, "workflow_state", None):
		return

	doc_before = doc.get_doc_before_save()
	if not doc_before:
		return

	old_state = getattr(doc_before, "workflow_state", None)
	if not old_state or old_state == doc.workflow_state:
		return

	text = _extract_action_comment()
	if not text:
		return

	# A single action can save the document more than once; only comment once
	# per document per request.
	seen = getattr(frappe.local, "_rndops_action_comments", None)
	if seen is None:
		seen = set()
		frappe.local._rndops_action_comments = seen
	key = (doc.doctype, doc.name)
	if key in seen:
		return
	seen.add(key)

	try:
		doc.add_comment("Comment", frappe.utils.escape_html(text))
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Failed to record workflow action comment")


def log_workflow_transition(doc, method):
    if doc.doctype not in TRACKED_DOCTYPES:
        return
    if not getattr(doc, "workflow_state", None):
        return

    doc_before = doc.get_doc_before_save()
    if not doc_before:
        return

    old_state = getattr(doc_before, "workflow_state", None)
    new_state = doc.workflow_state

    if not old_state or old_state == new_state:
        return

    action = _classify_action(old_state, new_state)

    # Time in queue: find when the doc entered old_state
    queue_entry_ts = frappe.db.get_value(
        "Staff Activity Log",
        filters={"document_name": doc.name, "doctype_name": doc.doctype, "to_state": old_state},
        fieldname="timestamp",
        order_by="timestamp desc",
    )
    if not queue_entry_ts:
        queue_entry_ts = getattr(doc_before, "modified", None) or getattr(doc_before, "creation", None)

    try:
        time_in_queue = round(time_diff_in_hours(now_datetime(), queue_entry_ts), 2)
    except Exception:
        time_in_queue = 0.0

    project_no = (
        getattr(doc, "project_no", None)
        or getattr(doc, "project_number", None)
        or ""
    )

    log = frappe.new_doc("Staff Activity Log")
    log.user = frappe.session.user
    log.timestamp = now_datetime()
    log.doctype_name = doc.doctype
    log.document_name = doc.name
    log.form_category = TRACKED_DOCTYPES[doc.doctype]
    log.from_state = old_state
    log.to_state = new_state
    log.action = action
    log.time_in_queue = time_in_queue
    log.project_no = str(project_no) if project_no else ""
    log.insert(ignore_permissions=True)
    frappe.db.commit()


def _classify_action(from_state, to_state):
    if from_state == "Draft":
        return "Submit"
    if to_state == "Rejected":
        return "Reject"
    if "Pending" in from_state and "Pending" not in to_state:
        return "Approve"
    return "Forward"
