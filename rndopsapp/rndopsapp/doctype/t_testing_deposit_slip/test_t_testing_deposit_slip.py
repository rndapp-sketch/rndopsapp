# Copyright (c) 2025, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip


class TestTTestingDepositSlip(FrappeTestCase):
	def _make_doc(self):
		doc = frappe.new_doc("T Testing Deposit Slip")
		doc.client = "ORIGINAL CLIENT"
		doc.bank = "ORIGINAL BANK"
		doc.flags.skip_kafka_sync = True
		doc.insert(ignore_permissions=True)
		self.addCleanup(
			frappe.delete_doc, "T Testing Deposit Slip", doc.name,
			ignore_permissions=True, force=True, delete_permanently=True,
		)
		return doc

	def test_non_staff_user_is_blocked(self):
		doc = self._make_doc()
		frappe.set_user("Guest")
		try:
			self.assertRaises(
				frappe.PermissionError,
				update_locked_deposit_slip,
				"T Testing Deposit Slip", doc.name, {"client": "SHOULD NOT APPLY"},
			)
		finally:
			frappe.set_user("Administrator")

	def test_field_update_and_protected_fields_dropped(self):
		doc = self._make_doc()
		result = update_locked_deposit_slip(
			"T Testing Deposit Slip", doc.name,
			changes={
				"client": "UPDATED CLIENT",
				"workflow_state": "HACKED",
				"docstatus": 5,
				"fund_received_ref": "FAKE-REF",
			},
		)
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["updated_fields"], ["client"])
		self.assertEqual(frappe.db.get_value("T Testing Deposit Slip", doc.name, "client"), "UPDATED CLIENT")
