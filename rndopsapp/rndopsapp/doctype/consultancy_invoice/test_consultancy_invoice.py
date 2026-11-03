# Copyright (c) 2026, rndops and Contributors
# See license.txt

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.doctype.consultancy_invoice.consultancy_invoice import invoice_suffix
from rndopsapp.rndopsapp.consultancy_invoice_api import (
	get_con_invoice,
	save_con_invoice,
)

STAFF_USER = "consultancy.invoice.staff@example.com"
OTHER_USER = "consultancy.invoice.director@example.com"
INVOICE_RE = re.compile(r"^INVO-\d{4}-\d{2}-\d{2}-[A-Z]{3}[0-9]{3}$")


def _make_user(email, role):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"roles": [{"role": role}],
		}
	)
	user.flags.no_welcome_mail = True
	user.insert(ignore_permissions=True)


class TestConsultancyInvoice(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_make_user(STAFF_USER, "staff, RnD")
		_make_user(OTHER_USER, "Director")

		fund = frappe.db.sql(
			"""select fr.name, fr.fund_received_ref_number, fr.prjreg_title, pr.project_no
			from `tabFund Received` fr join `tabProject Registration` pr on pr.name = fr.prjreg_title
			where ifnull(fr.fund_received_ref_number, '') != '' and ifnull(pr.project_no, '') != ''
			limit 2""",
			as_dict=True,
		)
		if len(fund) < 2:
			raise cls.skipTest(cls, "needs two Fund Received rows with a reference number on the site")
		cls.fund, cls.other_fund = fund[0], fund[1]

	def setUp(self):
		frappe.set_user(STAFF_USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_suffix_sequence(self):
		self.assertEqual(invoice_suffix(1), "AAA001")
		self.assertEqual(invoice_suffix(2), "AAA002")
		self.assertEqual(invoice_suffix(999), "AAA999")
		self.assertEqual(invoice_suffix(1000), "AAB001")
		self.assertEqual(invoice_suffix(26 * 999 + 1), "ABA001")
		self.assertEqual(invoice_suffix(26 * 26 * 26 * 999), "ZZZ999")
		with self.assertRaises(frappe.ValidationError):
			invoice_suffix(26 * 26 * 26 * 999 + 1)

	def test_numbers_run_in_sequence(self):
		a = self.fund
		first = save_con_invoice(a.project_no, a.fund_received_ref_number)["invoice_no"]
		# a second, different fund received must get the next number
		other = frappe.db.sql(
			"""select fr.fund_received_ref_number ref, pr.project_no from `tabFund Received` fr
			join `tabProject Registration` pr on pr.name = fr.prjreg_title
			where ifnull(fr.fund_received_ref_number,'') not in ('', %s) and ifnull(pr.project_no,'') != '' limit 1""",
			(a.fund_received_ref_number,), as_dict=True,
		)[0]
		second = save_con_invoice(other.project_no, other.ref)["invoice_no"]
		n1 = int(first[-3:]); n2 = int(second[-3:])
		self.assertEqual(first[:-3] == second[:-3] and n2 - n1 == 1 or (second[-3:] == "001" and n1 == 999), True)

	def test_save_returns_generated_invoice_no_and_names_the_doc_after_it(self):
		res = save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		self.assertRegex(res["invoice_no"], INVOICE_RE)
		self.assertTrue(frappe.db.exists("Consultancy Invoice", res["invoice_no"]))

	def test_second_save_returns_the_same_number(self):
		first = save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		again = save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		self.assertEqual(first, again)
		self.assertEqual(frappe.db.count("Consultancy Invoice", {"invoice_no": first["invoice_no"]}), 1)

	def test_project_can_be_given_by_name(self):
		by_no = save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		by_name = save_con_invoice(self.fund.prjreg_title, self.fund.fund_received_ref_number)
		self.assertEqual(by_no, by_name)

	def test_get_returns_saved_number_or_none(self):
		self.assertEqual(
			get_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number),
			{"invoice_no": None},
		)
		saved = save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		self.assertEqual(
			get_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number), saved
		)
		self.assertEqual(get_con_invoice("NO-SUCH-PROJECT", "1"), {"invoice_no": None})

	def test_invalid_inputs_are_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			save_con_invoice("NO-SUCH-PROJECT", self.fund.fund_received_ref_number)
		with self.assertRaises(frappe.DoesNotExistError):
			save_con_invoice(self.fund.project_no, "NO-SUCH-FUND-REF")
		if self.other_fund.prjreg_title != self.fund.prjreg_title:
			with self.assertRaises(frappe.ValidationError):
				save_con_invoice(self.fund.project_no, self.other_fund.fund_received_ref_number)

	def test_user_without_access_is_refused(self):
		frappe.set_user(OTHER_USER)
		with self.assertRaises(frappe.PermissionError):
			save_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
		with self.assertRaises(frappe.PermissionError):
			get_con_invoice(self.fund.project_no, self.fund.fund_received_ref_number)
