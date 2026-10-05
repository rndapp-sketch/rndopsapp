# Copyright (c) 2025, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.deposit_slip_common import update_locked_deposit_slip


class TestResearchConsultancyDepositSlip(FrappeTestCase):
	def _make_doc(self):
		doc = frappe.new_doc("Research Consultancy Deposit Slip")
		doc.client = "ORIGINAL CLIENT"
		doc.bank = "ORIGINAL BANK"
		doc.insert(ignore_permissions=True)
		self.addCleanup(
			frappe.delete_doc, "Research Consultancy Deposit Slip", doc.name,
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
				"Research Consultancy Deposit Slip", doc.name, {"bank": "SHOULD NOT APPLY"},
			)
		finally:
			frappe.set_user("Administrator")

	def test_field_update_and_protected_fields_dropped(self):
		doc = self._make_doc()
		result = update_locked_deposit_slip(
			"Research Consultancy Deposit Slip", doc.name,
			changes={
				"bank": "UPDATED BANK",
				"workflow_state": "HACKED",
				"docstatus": 5,
				"fund_received_ref": "FAKE-REF",
			},
		)
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["updated_fields"], ["bank"])
		self.assertEqual(
			frappe.db.get_value("Research Consultancy Deposit Slip", doc.name, "bank"), "UPDATED BANK"
		)
