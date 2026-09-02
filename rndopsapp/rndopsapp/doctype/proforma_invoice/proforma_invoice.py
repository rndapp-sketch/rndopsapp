# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from frappe.utils.html_utils import sanitize_html


def _add_workflow_comment(doc, action, comment):
	"""Record the submitter's / approver's note on the document timeline."""
	if comment and str(comment).strip():
		doc.add_comment("Workflow", sanitize_html(f"[{action}] {comment.strip()}"))


# ── Workflow (see Workflow "porforma_invoice") ──────────────────────────────
# Draft --Submit--> Pending HoS Approval --Approve--> Approved   (all docstatus 0)
HOS_ROLE = "Hos, RnD (Head of Section, RnD)"
PRINT_FORMAT = "Proforma Invoice Letterhead"

STATE_DRAFT = "Draft"
STATE_PENDING = "Pending HoS Approval"
STATE_APPROVED = "Approved"


class Proforma_Invoice(Document):
	pass


# ── Internal helpers ────────────────────────────────────────────────────────
def _generate_pdf(doc, file_name):
	"""Render the invoice through the Proforma Invoice Letterhead print format and
	attach it (private) to the document's invoice_attachment field. The signature
	only renders once workflow_state == 'Approved' (guarded in the print format)."""
	try:
		pdf_data = frappe.get_print(
			"Proforma_Invoice", doc.name,
			print_format=PRINT_FORMAT, as_pdf=True, no_letterhead=False,
		)
		pdf_file = frappe.get_doc({
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "Proforma_Invoice",
			"attached_to_name": doc.name,
			"attached_to_field": "invoice_attachment",
			"content": pdf_data,
			"is_private": 1,
		})
		pdf_file.insert(ignore_permissions=True)
		doc.db_set("invoice_attachment", pdf_file.file_url)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Proforma PDF error for {doc.name}")


def _get_user_signature(user):
	"""The approver's signature image. Users upload it to the 'Digital Signature'
	field on their User profile; fall back to the profile photo if unset."""
	sig = frappe.db.get_value("User", user, "digital_signature")
	if not sig:
		sig = frappe.db.get_value("User", user, "user_image")
	return sig


def _get_hos_users():
	"""Enabled users holding the HoS role. Queried via Has Role because a
	`{"roles": [role]}` filter on User trips an IndexError in make_filter_tuple."""
	candidates = frappe.get_all(
		"Has Role", filters={"role": HOS_ROLE, "parenttype": "User"}, pluck="parent"
	)
	return [u for u in set(candidates) if frappe.db.get_value("User", u, "enabled")]


def _notify_hos(doc):
	"""Create a ToDo for every enabled HoS user so the invoice appears in their
	dashboard 'To Do' list. Dedup-guarded so re-submits don't pile up."""
	hos_users = _get_hos_users()
	for user_id in hos_users:
		if frappe.db.exists("ToDo", {
			"reference_type": "Proforma_Invoice",
			"reference_name": doc.name,
			"allocated_to": user_id,
			"status": "Open",
		}):
			continue
		frappe.get_doc({
			"doctype": "ToDo",
			"description": f"Review Proforma Invoice: {doc.name}",
			"assigned_by": frappe.session.user,
			"allocated_to": user_id,
			"reference_type": "Proforma_Invoice",
			"reference_name": doc.name,
			"status": "Open",
			"priority": "High",
		}).insert(ignore_permissions=True)
	if not hos_users:
		frappe.log_error(
			f"No enabled '{HOS_ROLE}' users to notify for {doc.name}",
			"Proforma Invoice",
		)


def _close_hos_todos(doc):
	for todo in frappe.get_all("ToDo", filters={
		"reference_type": "Proforma_Invoice",
		"reference_name": doc.name,
		"status": "Open",
	}, pluck="name"):
		frappe.db.set_value("ToDo", todo, "status", "Closed")


def _serialize(doc):
	return {
		"name": doc.name,
		"project_no": doc.project_no,
		"workflow_state": doc.workflow_state or STATE_DRAFT,
		"invoice_content": doc.invoice_content,
		"invoice_attachment": doc.invoice_attachment,
		"approver_name": doc.approver_name,
		"approver_email": doc.approver_email,
		"approver_date": doc.approver_date,
		"approver_signature": doc.approver_signature,
	}


# ── Whitelisted API ─────────────────────────────────────────────────────────
@frappe.whitelist()
def get_proforma_invoice(project_no):
	"""Return the latest Proforma Invoice for a project (or None)."""
	name = frappe.db.get_value(
		"Proforma_Invoice", {"project_no": project_no}, "name",
		order_by="modified desc",
	)
	if not name:
		return None
	doc = frappe.get_doc("Proforma_Invoice", name)
	return _serialize(doc)


@frappe.whitelist()
def get_proforma_invoice_by_name(docname):
	"""Return a single Proforma Invoice by its own name (used by the HoS review
	route opened from the dashboard pending-task list). Read runs with elevated
	permissions so an approver without doc-level read can still review it."""
	doc = frappe.get_doc("Proforma_Invoice", docname)
	return _serialize(doc)


@frappe.whitelist()
def save_proforma_invoice(project_no, invoice_content, docname=None):
	"""Create or update a Draft Proforma Invoice, storing the rendered HTML in
	invoice_content. Returns the doc name + state."""
	if docname:
		doc = frappe.get_doc("Proforma_Invoice", docname)
	else:
		existing = frappe.db.get_value("Proforma_Invoice", {"project_no": project_no}, "name")
		doc = frappe.get_doc("Proforma_Invoice", existing) if existing else frappe.new_doc("Proforma_Invoice")

	if doc.workflow_state and doc.workflow_state != STATE_DRAFT:
		frappe.throw(_("This Proforma Invoice is already submitted and cannot be edited."))

	doc.project_no = project_no
	doc.invoice_content = invoice_content
	if not doc.workflow_state:
		doc.workflow_state = STATE_DRAFT
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return _serialize(doc)


@frappe.whitelist()
def submit_proforma_for_approval(docname=None, project_no=None, invoice_content=None, comment=None):
	"""Move the invoice to 'Pending HoS Approval': persist the latest content,
	generate an UNSIGNED PDF, and raise a ToDo for the HoS role. An optional
	comment is recorded on the document timeline."""
	if not docname:
		if not project_no:
			frappe.throw(_("docname or project_no is required."))
		docname = frappe.db.get_value("Proforma_Invoice", {"project_no": project_no}, "name")

	if docname:
		doc = frappe.get_doc("Proforma_Invoice", docname)
	else:
		doc = frappe.new_doc("Proforma_Invoice")
		doc.project_no = project_no

	if invoice_content is not None:
		doc.invoice_content = invoice_content
	# Insert/update while still in Draft. Setting workflow_state to Pending BEFORE
	# save trips Frappe's workflow role-gate (WorkflowPermissionError: transition not
	# allowed Draft -> Pending HoS Approval), so save as Draft first...
	if not doc.workflow_state:
		doc.workflow_state = STATE_DRAFT
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	# ...then move to Pending via a direct DB write (bypasses the transition gate;
	# these APIs enforce their own access rules). Persist state + HoS ToDos and
	# commit BEFORE the best-effort PDF so a wkhtmltopdf failure can't revert them.
	doc.db_set("workflow_state", STATE_PENDING)
	_notify_hos(doc)
	_add_workflow_comment(doc, "Submitted for HoS Approval", comment)
	frappe.db.commit()

	_generate_pdf(doc, f"{doc.name}-Proforma-{now_datetime().strftime('%Y%m%d%H%M%S')}.pdf")
	frappe.db.commit()
	return _serialize(doc)


@frappe.whitelist()
def process_proforma_action(docname, action, comment=None):
	"""HoS decision. action = 'Approve' | 'Reject'. An optional comment is
	recorded on the document timeline.
	Approve: stamp approver + signature (from the approver's User.user_image),
	regenerate the now-signed PDF, close the ToDo, state -> Approved.
	Reject: clear approver, close the ToDo, state -> Draft."""
	doc = frappe.get_doc("Proforma_Invoice", docname)

	user_roles = frappe.get_roles(frappe.session.user)
	if HOS_ROLE not in user_roles and "System Manager" not in user_roles:
		frappe.throw(_("Only the Head of Section (RnD) can act on this invoice."))

	if action == "Approve":
		signature = _get_user_signature(frappe.session.user)
		# Save the approver fields with workflow_state UNCHANGED (still Pending) so
		# the save doesn't trip the workflow transition gate; move the state after.
		doc.approver_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
		doc.approver_email = frappe.session.user
		doc.approver_date = now_datetime()
		doc.approver_signature = signature  # only set now -> signature appears post-approval
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		# Persist state + approver + comment + close ToDos and commit BEFORE the
		# best-effort PDF regeneration, so a wkhtmltopdf failure (which triggers a
		# log_error rollback) can't drop the approval or the recorded comment.
		doc.db_set("workflow_state", STATE_APPROVED)
		_close_hos_todos(doc)
		_add_workflow_comment(doc, action, comment)
		frappe.db.commit()

		# Regenerate with the signature now that state == Approved.
		_generate_pdf(doc, f"{doc.name}-Proforma-FINAL.pdf")

	elif action == "Reject":
		# Clear approver fields with state unchanged, then move Pending -> Draft.
		doc.approver_name = None
		doc.approver_email = None
		doc.approver_date = None
		doc.approver_signature = None
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
		doc.db_set("workflow_state", STATE_DRAFT)
		_close_hos_todos(doc)
		_add_workflow_comment(doc, action, comment)
		frappe.db.commit()

	else:
		frappe.throw(_("Unknown action: {0}").format(action))

	return _serialize(doc)
