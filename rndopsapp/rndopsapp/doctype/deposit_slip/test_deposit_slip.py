# Copyright (c) 2025, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip


class TestDepositslip(FrappeTestCase):
	def _make_submitted_doc(self):
		doc = frappe.new_doc("Deposit slip")
		doc.category = "Research"
		doc.bank = "ORIGINAL BANK"
		doc.append("ecs_dates", {"ecs_date": "2026-01-01"})
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.addCleanup(self._delete_doc, doc.name)
		return doc

	def _delete_doc(self, docname):
		frappe.db.set_value("Deposit slip", docname, "docstatus", 2, update_modified=False)
		frappe.delete_doc("Deposit slip", docname, ignore_permissions=True, force=True, delete_permanently=True)

	def test_non_staff_user_is_blocked(self):
		doc = self._make_submitted_doc()
		frappe.set_user("Guest")
		try:
			self.assertRaises(
				frappe.PermissionError,
				update_locked_deposit_slip,
				"Deposit slip", doc.name, {"bank": "SHOULD NOT APPLY"},
			)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Deposit slip", doc.name, "bank"), "ORIGINAL BANK")

	def test_post_submit_field_and_child_row_update(self):
		doc = self._make_submitted_doc()
		row_name = frappe.get_all(
			"Deposit Slip ECS Date", filters={"parent": doc.name}, pluck="name"
		)[0]

		result = update_locked_deposit_slip(
			"Deposit slip", doc.name,
			changes={"bank": "UPDATED BANK"},
			child_table_changes=[
				{"fieldname": "ecs_dates", "updated": [{"name": row_name, "changes": {"ecs_date": "2026-02-02"}}]},
			],
		)

		self.assertEqual(result["status"], "success")
		self.assertEqual(result["updated_fields"], ["bank"])
		self.assertEqual(frappe.db.get_value("Deposit slip", doc.name, "bank"), "UPDATED BANK")
		self.assertEqual(str(frappe.db.get_value("Deposit Slip ECS Date", row_name, "ecs_date")), "2026-02-02")
		self.assertEqual(frappe.db.get_value("Deposit slip", doc.name, "docstatus"), 1)

	def test_protected_and_unknown_fields_are_dropped_not_written(self):
		doc = self._make_submitted_doc()

		result = update_locked_deposit_slip(
			"Deposit slip", doc.name,
			changes={
				"bank": "UPDATED BANK 2",
				"docstatus": 5,
				"workflow_state": "HACKED",
				"fund_received_ref": "FAKE-REF",
				"not_a_real_field_xyz": "whatever",
			},
		)

		self.assertEqual(result["status"], "success")
		self.assertEqual(result["updated_fields"], ["bank"])
		self.assertEqual(frappe.db.get_value("Deposit slip", doc.name, "docstatus"), 1)
		self.assertIsNone(frappe.db.get_value("Deposit slip", doc.name, "fund_received_ref"))

	def test_empty_changes_is_a_noop(self):
		doc = self._make_submitted_doc()
		result = update_locked_deposit_slip("Deposit slip", doc.name, changes={})
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["updated_fields"], [])

	def test_audit_comment_is_recorded(self):
		doc = self._make_submitted_doc()
		update_locked_deposit_slip("Deposit slip", doc.name, changes={"bank": "AUDITED BANK"})
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "Deposit slip", "reference_name": doc.name},
			fields=["content"],
		)
		self.assertTrue(any("Staff post-submit edit" in c.content for c in comments))
