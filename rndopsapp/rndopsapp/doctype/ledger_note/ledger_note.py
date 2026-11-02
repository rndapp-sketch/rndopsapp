# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime
from frappe.utils.html_utils import clean_html


class LedgerNote(Document):
	def validate(self):
		self.project_no = (self.project_no or "").strip()
		# None / whitespace both mean "general project note" and are stored as "".
		self.transaction_id = (self.transaction_id or "").strip()
		# Notes are rendered as HTML in other users' browsers: strip scripts, handlers, etc.
		self.content = clean_html(self.content or "")

		self.check_client_modified()
		self.check_unique()

	def check_client_modified(self):
		"""Optimistic concurrency: reject the save if the stored note changed after the
		client loaded it. The caller passes its copy of `modified` via
		doc.flags.client_modified."""
		client_modified = self.flags.get("client_modified")
		if not client_modified or self.is_new():
			return

		stored = frappe.db.get_value(self.doctype, self.name, "modified")
		if stored and get_datetime(stored) != get_datetime(client_modified):
			frappe.throw(
				_("This note was changed by someone else since you opened it. Reload it and try again."),
				frappe.TimestampMismatchError,
			)

	def check_unique(self):
		filters = {"project_no": self.project_no, "transaction_id": self.transaction_id}
		if not self.is_new():
			filters["name"] = ["!=", self.name]

		duplicate = frappe.get_all("Ledger Note", filters=filters, pluck="name", limit=1)
		if duplicate:
			if self.transaction_id:
				msg = _("A note for transaction {0} on project {1} already exists ({2}).").format(
					self.transaction_id, self.project_no, duplicate[0]
				)
			else:
				msg = _("A general note for project {0} already exists ({1}).").format(
					self.project_no, duplicate[0]
				)
			frappe.throw(msg, frappe.DuplicateEntryError)
