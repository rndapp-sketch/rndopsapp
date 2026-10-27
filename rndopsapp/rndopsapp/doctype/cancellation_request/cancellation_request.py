# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from rndopsapp.rndopsapp.cancellation_workflow import (
	encode_path,
	ensure_cancellation_workflow,
	resolve_cancellation_path,
)


class CancellationRequest(Document):
	def set_route(self):
		"""
		Decide how far this cancellation travels, from the state the application
		is in right now. Stored on the request so the workflow's transition
		conditions can read it, and so it does not change if the application's
		state somehow moves later.
		"""
		if self.stop_stage and self.stage_path:
			return

		app_state = frappe.db.get_value(self.reference_doctype, self.reference_name, "workflow_state")
		stop_stage, path = resolve_cancellation_path(self.reference_doctype, app_state)
		self.stop_stage = stop_stage
		self.stage_path = encode_path(path)

		# Make sure the independent workflow exists (idempotent).
		ensure_cancellation_workflow()

	def before_insert(self):
		"""Set defaults before the document is inserted."""
		self.requested_by = self.requested_by or frappe.session.user
		self.request_date = self.request_date or frappe.utils.now_datetime()
		self.status = "Pending"

		# Generate short name for auto-naming
		if self.reference_doctype and not self.reference_doctype_short:
			self.reference_doctype_short = self._get_short_name(self.reference_doctype)

		self.set_route()

	def validate(self):
		"""Validate the cancellation request."""
		self._check_head_is_acting()

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

	def _check_head_is_acting(self):
		"""
		The Head stage belongs to ONE person (the head of the application's
		department), not to every holder of the Head role. Moving the request
		out of Pending Head Approval is therefore limited to that head.
		"""
		before = self.get_doc_before_save()
		if not before or before.workflow_state != "Pending Head Approval":
			return
		if self.workflow_state == before.workflow_state:
			return

		user = frappe.session.user
		if user == "Administrator" or "System Manager" in frappe.get_roles(user):
			return

		from rndopsapp.rndopsapp.doctype.module_registry.module_registry import (
			_cancellation_head_ok,
		)

		ref_doc = frappe.db.get_value(self.reference_doctype, self.reference_name, "*", as_dict=True)
		if not ref_doc or not _cancellation_head_ok(user, self.reference_doctype, ref_doc):
			frappe.throw(
				_("Only the head of the applicant's department can act on this cancellation at Head approval."),
				frappe.PermissionError,
			)

	def on_update(self):
		"""Handle workflow state changes."""
		# The "Pending Head Approval" skip is applied once, at workflow-clone
		# time, by cancellation_api._setup_cancellation_workflow (rewiring the
		# cloned workflow's own transitions via CANCELLATION_SKIP_STATES) —
		# not here on every save.

		# Check if the cancellation has reached an approved state
		workflow_state = getattr(self, "workflow_state", None)
		if workflow_state and self._is_approved_state(workflow_state):
			self._mark_original_as_cancelled()
		elif workflow_state == "Rejected":
			self._mark_rejected()

	def _mark_rejected(self):
		"""
		A rejected cancellation leaves the original document untouched. Moving
		status off "Pending" is what releases the lock on the original and
		lets a new request be filed.
		"""
		if self.status == "Rejected":
			return

		self.db_set("status", "Rejected", update_modified=False)
		self.add_comment(
			"Info",
			_("Cancellation rejected. {0} ({1}) is unchanged.").format(
				self.reference_name, self.reference_doctype
			),
		)

	def on_update_after_submit(self):
		"""
		Submitted documents (docstatus=1) fire this instead of on_update, and
		every workflow transition — including the final approval — happens after
		submit. Without this the approval was a no-op: the request reached
		"Approved" but the original document was never marked Cancelled.
		"""
		self.on_update()

	def on_submit(self):
		"""When submitted, check if the cancellation workflow has been completed."""
		self.on_update()

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

			# Call external ledger API to cancel the commit
			try:
				import json

				import requests

				frap_app_id = self.reference_name
				project_number = None

				# Try to get frap_app_id and project_number from Kafka Commit Staging
				staging_records = frappe.get_all(
					"Kafka Commit Staging",
					filters={
						"reference_doctype": self.reference_doctype,
						"reference_name": self.reference_name,
					},
					fields=["name", "payload"],
				)
				for st in staging_records:
					frappe.db.set_value(
						"Kafka Commit Staging", st.name, "status", "CANCELLED", update_modified=True
					)

					if st.payload:
						try:
							payload = json.loads(st.payload)
							if payload.get("frap_app_id"):
								frap_app_id = payload.get("frap_app_id")
							if payload.get("project_name"):
								project_number = payload.get("project_name")
						except Exception:
							pass

				# Fallback to ref_doc fields if project_number not resolved from staging payload
				if not project_number:
					project_number = (
						ref_doc.get("project_no")
						or ref_doc.get("project_code")
						or ref_doc.get("project_name")
						or ref_doc.get("upfa_project_code")
					)

				# Resolve project_number (database ID) to the actual human-readable project number/code
				if project_number:
					resolved_proj = frappe.db.get_value("Project Registration", project_number, "project_no")
					if resolved_proj:
						project_number = resolved_proj

				if project_number:
					api_url = "http://172.16.134.81:18080/api/account-head-commit/status/by-project-frap"
					headers = {"Content-Type": "application/json"}
					body = {
						"projectNumber": str(project_number),
						"frapAppId": str(frap_app_id),
						"status": "CANCELLED",
					}
					frappe.log_error(
						title="Cancel Commit API Request",
						message=f"Calling cancel commit API: URL={api_url}, Body={json.dumps(body)}",
					)
					response = requests.patch(api_url, headers=headers, json=body, timeout=10)
					if response.status_code == 200:
						frappe.log_error(
							title="Cancel Commit API Success",
							message=f"Cancel commit API success: {response.text}",
						)
					else:
						frappe.log_error(
							title="Cancel Commit API Error",
							message=f"Cancel commit API returned status {response.status_code}: {response.text}",
						)
				else:
					frappe.log_error(
						title="Cancel Commit Resolve Error",
						message=f"Could not resolve project number for {self.reference_name} to cancel commit.",
					)

			except Exception as api_err:
				frappe.log_error(
					title="Cancel Commit API Exception",
					message=f"Exception while calling cancel commit API: {str(api_err)}",
				)

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

		except Exception:
			# Do not swallow this: the approval transition must roll back rather
			# than leave a request at "Approved" with the original still live.
			frappe.log_error(
				frappe.get_traceback(), _("Error marking {0} as cancelled").format(self.reference_name)
			)
			raise

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