# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate, now_datetime


class AnnouncementPragati(Document):
	def validate(self):
		if self.disabled is None:
			self.disabled = 0

		if self.start_date and self.end_date and getdate(self.start_date) > getdate(self.end_date):
			frappe.throw("End Date cannot be before Start Date")

	def before_insert(self):
		self.disabled = 0


@frappe.whitelist()
def set_disabled(docname, disabled):
	doc = frappe.get_doc("Announcement Pragati", docname)
	doc.check_permission("write")
	doc.db_set("disabled", 1 if cint(disabled) else 0)
	return doc.disabled


@frappe.whitelist()
def get_visible_announcements():
	"""
	Announcements within their date window and not disabled, restricted to
	the ones whose `visible_to_roles` is either empty (shown to everyone)
	or contains at least one role the current user holds.
	"""
	user_roles = set(frappe.get_roles())
	now = now_datetime()

	announcements = frappe.get_all(
		"Announcement Pragati",
		filters={"disabled": 0, "start_date": ["<=", now], "end_date": [">=", now]},
		fields=["name", "title", "message", "start_date", "end_date"],
		order_by="start_date desc",
	)

	visible = []
	for announcement in announcements:
		roles = frappe.get_all(
			"Has Role", filters={"parent": announcement.name, "parenttype": "Announcement Pragati"}, pluck="role"
		)
		if not roles or user_roles.intersection(roles):
			visible.append(announcement)

	return visible


def auto_disable_expired_announcements():
	"""
	Scheduled job (see hooks.py) — flips any announcement whose End Date has
	passed to Disabled. Manual Activate/Disable via set_disabled is
	unaffected; this only ever moves Active -> Disabled, never the reverse,
	so re-activating a past announcement always requires a manual action.
	"""
	expired = frappe.get_all(
		"Announcement Pragati",
		filters={"disabled": 0, "end_date": ["<", now_datetime()]},
		pluck="name",
	)
	for name in expired:
		frappe.db.set_value("Announcement Pragati", name, "disabled", 1)

	if expired:
		frappe.db.commit()
