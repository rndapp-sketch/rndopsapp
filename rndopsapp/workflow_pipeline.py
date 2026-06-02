"""

Generic Workflow module for any doctype.

Features:
- Supports any doctype (defaults to "Project Registration" for compatibility)
- Clear role parsing (handles strings, CSV, list)
- Permission checks (System Manager bypass, Frappe permissions)
- Safe document loading with helpful exceptions
- Audit logging (comment on state change)
- UI-friendly debug messages and whitelisted API functions
"""

from typing import Iterable, List, Optional

import frappe
from frappe import _
from frappe.utils import now_datetime


class WorkflowError(frappe.ValidationError):
	pass


class PermissionDenied(frappe.PermissionError):
	pass


class WorkflowManager:
	"""Manage workflow operations for arbitrary documents."""

	DEFAULT_DOCTYPE = "Project Registration"

	def __init__(self, docname: str, doctype: Optional[str] = None):
		"""
		Args:
		    docname: name/id of the document
		    doctype: document type, e.g. "Sales Invoice". If None uses DEFAULT_DOCTYPE.
		"""
		if not docname:
			frappe.throw(_("docname is required"), exc=WorkflowError)

		self.doctype = doctype or self.DEFAULT_DOCTYPE
		self.docname = docname

		try:
			self.doc = frappe.get_doc(self.doctype, docname)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WorkflowManager: failed to load document")
			frappe.throw(_("Could not load {0} '{1}'").format(self.doctype, docname), exc=WorkflowError)

		# ensure we read a usable current state
		self.current_state: Optional[str] = getattr(self.doc, "workflow_state", None) or "Draft"
		self.user: str = frappe.session.user
		self.user_roles: List[str] = frappe.get_roles(self.user) or []
		self.workflow = self._get_workflow_doc()

	# -------------------------
	# Internal helpers
	# -------------------------
	def _get_workflow_doc(self) -> Optional[frappe]:
		"""Return Workflow doc for this doctype or None."""
		if self.doc.doctype == "Cancellation Request" and getattr(self.doc, "source_workflow", None):
			wf_name = f"cancel_{self.doc.source_workflow}"
		else:
			wf_name = frappe.get_value("Workflow", {"document_type": self.doc.doctype}, "name")
		if not wf_name:
			return None
		try:
			return frappe.get_doc("Workflow", wf_name)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WorkflowManager: invalid Workflow doc")
			return None

	def _is_system_manager(self) -> bool:
		return "System Manager" in self.user_roles

	@staticmethod
	def _parse_roles(raw) -> List[str]:
		"""
		Normalize role definitions to a list of role strings.
		Accepts: list, comma-separated string, newline-separated, single string, None.
		"""
		if not raw:
			return []
		if isinstance(raw, list):
			return [str(r).strip() for r in raw if r]
		if isinstance(raw, str):
			raw_str = raw.strip()
			# Keep the full unsplit string first to support roles containing commas (e.g. 'staff, RnD')
			parts = [raw_str]
			for sep in [",", "\n", ";"]:
				if sep in raw_str:
					parts.extend([p.strip() for p in raw_str.split(sep) if p.strip()])
			return list(dict.fromkeys(p for p in parts if p))
		return [str(raw).strip()]

	def _get_state_row(self):
		"""Return Workflow state row doc for current state or None."""
		if not self.workflow:
			return None
		for s in getattr(self.workflow, "states", []) or []:
			if (
				getattr(s, "state", None) == self.current_state
				or getattr(s, "state_name", None) == self.current_state
			):
				return s
		return None

	def _get_state_allowed_roles(self) -> List[str]:
		"""Get roles allowed to edit in current state (handles several shapes)."""
		state_row = self._get_state_row()
		if not state_row:
			return []
		raw = (
			getattr(state_row, "allow_edit", None)
			or getattr(state_row, "roles", None)
			or getattr(state_row, "allowed_roles", None)
		)
		return self._parse_roles(raw)

	def _get_transition_roles(self, transition) -> List[str]:
		"""Return list of roles allowed for a transition (robust parsing)."""
		raw = (
			getattr(transition, "allowed", None)
			or getattr(transition, "allowed_roles", None)
			or getattr(transition, "roles", None)
		)
		return self._parse_roles(raw)

	def _can_user_act(self) -> bool:
		"""Whether the current user can act on this document in the workflow (state-level check)."""
		if self._is_system_manager():
			return True
		allowed_roles = self._get_state_allowed_roles()
		if not allowed_roles:
			# if no role restriction defined at state level, require write permission on the doc
			return frappe.has_permission(self.doctype, ptype="write", doc=self.doc)
		return any(role in self.user_roles for role in allowed_roles)

	# -------------------------
	# Public methods
	# -------------------------
	def get_available_actions(self) -> List[str]:
		"""
		Return list of action names that the current user is allowed to perform from current state.
		"""
		if not self.workflow:
			return []

		actions: List[str] = []
		for t in getattr(self.workflow, "transitions", []) or []:
			if getattr(t, "state", None) != self.current_state:
				continue
			transition_roles = self._get_transition_roles(t)
			permitted = (
				self._is_system_manager()
				or (not transition_roles and frappe.has_permission(self.doctype, ptype="write", doc=self.doc))
				or any(r in self.user_roles for r in transition_roles)
			)
			if permitted:
				action_name = getattr(t, "action", None) or getattr(t, "action_name", None)
				if action_name:
					actions.append(action_name)
		return list(dict.fromkeys(actions))  # dedupe preserve order

	def get_valid_transitions(self) -> List[dict]:
		"""
		Return transitions (dicts) from current state:
		    [{ "action": "...", "next_state": "...", "roles": [...] }, ...]
		"""
		if not self.workflow:
			return []
		results = []
		for t in getattr(self.workflow, "transitions", []) or []:
			if getattr(t, "state", None) != self.current_state:
				continue
			action = getattr(t, "action", None) or getattr(t, "action_name", None)
			next_state = getattr(t, "next_state", None) or getattr(t, "next_state_name", None)
			roles = self._get_transition_roles(t)
			results.append({"action": action, "next_state": next_state, "roles": roles})
		return results

	def get_next_state(self, action: str) -> Optional[str]:
		"""Return next_state for a named action from current state, or None."""
		if not action or not self.workflow:
			return None
		for t in getattr(self.workflow, "transitions", []) or []:
			if getattr(t, "state", None) != self.current_state:
				continue
			action_name = getattr(t, "action", None) or getattr(t, "action_name", None)
			if action_name == action:
				return getattr(t, "next_state", None) or getattr(t, "next_state_name", None)
		return None

	def perform_action(self, action: str) -> str:
		"""
		Perform the workflow action and persist the new workflow_state.
		Raises:
		    PermissionDenied, WorkflowError
		Returns:
		    new_state (str)
		"""
		if not self.workflow:
			frappe.throw(_("No workflow configured for {0}").format(self.doctype), exc=WorkflowError)

		if not self._can_user_act():
			frappe.throw(
				_("You do not have permission to perform workflow actions on this document."),
				exc=PermissionDenied,
			)

		next_state = self.get_next_state(action)
		if not next_state:
			frappe.throw(
				_("Invalid action '{0}' from state '{1}'").format(action, self.current_state),
				exc=WorkflowError,
			)

		# find transition row
		transition = None
		for t in getattr(self.workflow, "transitions", []) or []:
			action_name = getattr(t, "action", None) or getattr(t, "action_name", None)
			if getattr(t, "state", None) == self.current_state and action_name == action:
				transition = t
				break

		if not transition:
			frappe.throw(_("Transition not found."), exc=WorkflowError)

		transition_roles = self._get_transition_roles(transition)
		if (
			not self._is_system_manager()
			and transition_roles
			and not any(r in self.user_roles for r in transition_roles)
		):
			frappe.throw(_("You are not allowed to perform this action."), exc=PermissionDenied)

		if getattr(self.doc, "docstatus", 0) == 2:
			frappe.throw(_("Document is cancelled; cannot change workflow state."), exc=WorkflowError)

		old_state = self.current_state
		self.doc.workflow_state = next_state
		self.doc.save(ignore_permissions=True)

		# Add audit comment
		try:
			self.doc.add_comment(
				"Info",
				f"Workflow action '{action}' performed by {self.user} ({', '.join(self.user_roles)}) "
				f"on {now_datetime().strftime('%Y-%m-%d %H:%M:%S')}: {old_state} → {next_state}",
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "WorkflowManager: failed to add workflow audit comment")

		# update internal state
		self.current_state = next_state
		return next_state

	def log_debug_info(self) -> None:
		"""UI-friendly debug info."""
		wf_name = frappe.get_value("Workflow", {"document_type": self.doc.doctype}, "name")
		frappe.msgprint(_("Workflow Name: {0}").format(wf_name or _("(none configured)")))
		frappe.msgprint(_("Current Workflow State: {0}").format(self.current_state))
		frappe.msgprint(_("User: {0}").format(self.user))
		frappe.msgprint(_("User Roles: {0}").format(", ".join(self.user_roles) or _("(none)")))

		if not self.workflow:
			frappe.msgprint(_("⚠ No workflow is configured."))
			return

		allowed_roles = self._get_state_allowed_roles()
		frappe.msgprint(
			_("Roles allowed at this state: {0}").format(", ".join(allowed_roles) or _("(none specified)"))
		)

		if not self._can_user_act():
			frappe.msgprint(_("🚫 You are not allowed to perform any workflow actions."))
			return

		valid_transitions = self.get_valid_transitions()
		if valid_transitions:
			lines = [
				f"{t['action']} → {t['next_state']} (roles: {', '.join(t['roles']) or '(any with permission)'})"
				for t in valid_transitions
			]
			frappe.msgprint("Available Workflow Actions:<br>" + "<br>".join(lines))
			frappe.msgprint(_("Document: {0}").format(self.docname))
		else:
			frappe.msgprint(_("⚠ No available workflow actions from current state."))


# -------------------------
# API (whitelisted) helpers
# -------------------------
@frappe.whitelist()
def get_available_workflow_actions(docname: str, doctype: Optional[str] = None) -> List[str]:
	"""
	Return actions the current user can perform for the given doc.
	Usage: get_available_workflow_actions("DOCNAME", "Doctype Name")
	If doctype is not provided, defaults to 'Project Registration'.
	"""
	wf = WorkflowManager(docname, doctype)
	actions = wf.get_available_actions()
	try:
		frappe.logger().debug(
			f"Available actions for {doctype or WorkflowManager.DEFAULT_DOCTYPE}:{docname}: {actions}"
		)
	except Exception:
		pass
	return actions


@frappe.whitelist()
def perform_workflow_action(docname: str, action: str, doctype: Optional[str] = None) -> str:
	"""
	Perform an action and return the new workflow state.
	Usage: perform_workflow_action("DOCNAME", "Approve", "Doctype Name")
	"""
	wf = WorkflowManager(docname, doctype)
	return wf.perform_action(action)


@frappe.whitelist()
def get_workflow_actions(docname: str, doctype: Optional[str] = None):
	"""
	Return structured list of valid transitions or messages.
	Usage: get_workflow_actions("DOCNAME", "Doctype Name")
	"""
	wf = WorkflowManager(docname, doctype)
	if not wf.workflow:
		return {"message": ["No workflow configured."]}

	if not wf._can_user_act():
		return {"message": ["🚫 You are not allowed to perform any workflow actions."]}

	valid_actions = wf.get_valid_transitions()
	if not valid_actions:
		return {"message": ["⚠ No available workflow actions from current state."]}

	return {"message": valid_actions}


# @frappe.whitelist()
# def log_available_workflow_actions(docname: str, doctype: Optional[str] = None):
# 	"""Show detailed workflow debug info via frappe.msgprint (UI-friendly)."""
# 	wf = WorkflowManager(docname, doctype)
# 	wf.log_debug_info()


@frappe.whitelist()
def log_available_workflow_actions(docname: str, doctype: Optional[str] = None):
	"""
	Return detailed workflow debug info as a JSON object.
	Usage: /api/method/path.to.module.log_available_workflow_actions
	"""
	wf = WorkflowManager(docname, doctype)

	# Fetch workflow metadata
	wf_name = frappe.get_value("Workflow", {"document_type": wf.doc.doctype}, "name")

	# specific state permissions
	allowed_roles = wf._get_state_allowed_roles()

	# transitions valid for this state
	transitions = wf.get_valid_transitions()

	return {
		"meta": {
			"workflow_name": wf_name,
			"doctype": wf.doctype,
			"docname": wf.docname,
			"current_state": wf.current_state,
		},
		"user_context": {
			"user": wf.user,
			"roles": wf.user_roles,
			"is_system_manager": wf._is_system_manager(),
		},
		"permissions": {"roles_allowed_to_edit_state": allowed_roles, "can_user_act": wf._can_user_act()},
		"available_transitions": transitions,
	}
