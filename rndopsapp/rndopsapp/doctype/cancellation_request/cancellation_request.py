# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CancellationRequest(Document):
	def before_validate(self):
		"""Ensure the correct workflow is set as active before validation/saving."""
		if self.reference_doctype and not self.source_workflow:
			wf_name = frappe.get_value("Workflow", {"document_type": self.reference_doctype}, "name")
			self.source_workflow = wf_name or ""

		if self.source_workflow:
			self.activate_workflow()

	def activate_workflow(self):
		target_wf = f"cancel_{self.source_workflow}"
		if frappe.db.exists("Workflow", target_wf):
			# Set this workflow as active and others for this doctype as inactive
			frappe.db.sql(
				"""
				UPDATE `tabWorkflow`
				SET is_active = (CASE WHEN name = %s THEN 1 ELSE 0 END)
				WHERE document_type = 'Cancellation Request'
			""",
				(target_wf,),
			)
			frappe.clear_cache(doctype="Cancellation Request")

	def before_insert(self):
		"""Set defaults before the document is inserted."""
		self.requested_by = self.requested_by or frappe.session.user
		self.request_date = self.request_date or frappe.utils.now_datetime()
		self.status = "Pending"

		# Generate short name for auto-naming
		if self.reference_doctype and not self.reference_doctype_short:
			self.reference_doctype_short = self._get_short_name(self.reference_doctype)

		# Store the source workflow name
		if self.reference_doctype and not self.source_workflow:
			wf_name = frappe.get_value("Workflow", {"document_type": self.reference_doctype}, "name")
			self.source_workflow = wf_name or ""

	def validate(self):
		"""Validate the cancellation request."""
		if not self.cancellation_reason or not self.cancellation_reason.strip():
			frappe.throw(_("Cancellation reason is required."))

		if not self.reference_doctype or not self.reference_name:
			frappe.throw(_("Reference document is required."))

		# Verify the referenced document exists
		if not frappe.db.exists(self.reference_doctype, self.reference_name):
			frappe.throw(
				_("Referenced document {0} ({1}) does not exist.").format(
					self.reference_name, self.reference_doctype
				)
			)

		# Check for duplicate pending cancellation requests
		if self.is_new():
			existing = frappe.get_all(
				"Cancellation Request",
				filters={
					"reference_doctype": self.reference_doctype,
					"reference_name": self.reference_name,
					"status": "Pending",
					"docstatus": ["<", 2],
				},
				limit=1,
			)
			if existing:
				frappe.throw(
					_("A pending cancellation request already exists for {0} ({1}).").format(
						self.reference_name, self.reference_doctype
					)
				)

	def on_update(self):
		"""Handle workflow state changes."""
		# Check if the cancellation has reached an approved state
		workflow_state = getattr(self, "workflow_state", None)
		if workflow_state and self._is_approved_state(workflow_state):
			self._mark_original_as_cancelled()

	def on_submit(self):
		"""When submitted, check if the cancellation workflow has been completed."""
		pass

	def _mark_original_as_cancelled(self):
		"""Mark the original document as cancelled when cancellation is approved."""
		if self.status == "Approved":
			# Already processed
			return

		try:
			ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)

			# Set workflow_state to "Cancelled" directly in the database to bypass workflow validation
			if hasattr(ref_doc, "workflow_state"):
				frappe.db.set_value(
					self.reference_doctype,
					self.reference_name,
					"workflow_state",
					"Cancelled",
					update_modified=True,
				)
				ref_doc.reload()

			# Update our status
			self.db_set("status", "Approved", update_modified=True)

			# Add audit comment on the original document
			ref_doc.add_comment(
				"Info",
				_("This document has been cancelled via Cancellation Request {0}. Reason: {1}").format(
					self.name, self.cancellation_reason
				),
			)

			# Add comment on the cancellation request itself
			self.add_comment(
				"Info",
				_("Cancellation approved. Original document {0} ({1}) has been marked as Cancelled.").format(
					self.reference_name, self.reference_doctype
				),
			)

			frappe.db.commit()

		except Exception as e:
			frappe.log_error(
				frappe.get_traceback(), _("Error marking {0} as cancelled").format(self.reference_name)
			)

	def _is_approved_state(self, state):
		"""Check if the given workflow state is an approved/final state."""
		approved_keywords = ["approved", "sanction approved", "endorsement approved"]
		state_lower = (state or "").strip().lower()
		return any(keyword in state_lower for keyword in approved_keywords)

	@staticmethod
	def _get_short_name(doctype_name):
		"""Generate a short abbreviation from doctype name for auto-naming."""
		if not doctype_name:
			return "GEN"
		words = doctype_name.replace("_", " ").split()
		if len(words) == 1:
			return words[0][:4].upper()
		return "".join(w[0].upper() for w in words[:4])
