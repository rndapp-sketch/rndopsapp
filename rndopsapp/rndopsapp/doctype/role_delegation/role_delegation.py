import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from rndopsapp.rndopsapp.role_delegation.constants import DELEGABLE_ROLES, DELEGATE_ROLES
from rndopsapp.rndopsapp.role_delegation.service import assigned_roles, is_enabled_system_user

_TEXT_FIELDS = ("delegator", "delegate", "reason")
_TIME_FIELDS = ("from_datetime", "to_datetime")


class RoleDelegation(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before:
			self._validate_unchanged(before)
		else:
			self._validate_new()

	def _validate_unchanged(self, before):
		"""A grant can only be revoked; to change anything else, make a new one."""
		changed = (
			any((self.get(f) or "") != (before.get(f) or "") for f in _TEXT_FIELDS)
			or any(get_datetime(self.get(f)) != get_datetime(before.get(f)) for f in _TIME_FIELDS)
			or sorted(r.role for r in self.roles) != sorted(r.role for r in before.roles)
		)
		if changed:
			frappe.throw(_("A role delegation cannot be edited. Revoke it and create a new one."))
		if before.status == "Revoked" and self.status != "Revoked":
			frappe.throw(_("A revoked delegation cannot be reactivated."))

	def _validate_new(self):
		self.status = "Active"
		self.revoked_by = self.revoked_at = None

		if self.delegator == self.delegate:
			frappe.throw(_("You cannot delegate a role to yourself."))
		for user in (self.delegator, self.delegate):
			if not is_enabled_system_user(user):
				frappe.throw(_("User '{0}' must be an enabled system user.").format(user))

		roles = [r.role for r in self.roles]
		if not roles:
			frappe.throw(_("Select at least one role to delegate."))
		if len(roles) != len(set(roles)):
			frappe.throw(_("The same role is listed more than once."))

		held = assigned_roles(self.delegator)
		for role in roles:
			if role not in DELEGABLE_ROLES:
				frappe.throw(_("'{0}' is not a delegable role.").format(role))
			if role not in held:
				frappe.throw(_("'{0}' does not hold the role '{1}'.").format(self.delegator, role))

		if not assigned_roles(self.delegate).intersection(DELEGATE_ROLES):
			frappe.throw(
				_("The delegate must hold one of these roles: {0}.").format("; ".join(DELEGATE_ROLES))
			)

		start, end = get_datetime(self.from_datetime), get_datetime(self.to_datetime)
		if end <= start:
			frappe.throw(_("The end time must be after the start time."))
		if end <= now_datetime():
			frappe.throw(_("The end time must be in the future."))

		self._validate_no_overlap(roles, start, end)

	def _validate_no_overlap(self, roles, start, end):
		overlapping = frappe.get_all(
			"Role Delegation",
			filters={
				"delegator": self.delegator,
				"delegate": self.delegate,
				"status": "Active",
				"from_datetime": ("<", end),
				"to_datetime": (">", start),
			},
			pluck="name",
		)
		if overlapping and frappe.db.exists(
			"Role Delegation Role", {"parent": ("in", overlapping), "role": ("in", roles)}
		):
			frappe.throw(_("An active delegation already covers this role and period."))
