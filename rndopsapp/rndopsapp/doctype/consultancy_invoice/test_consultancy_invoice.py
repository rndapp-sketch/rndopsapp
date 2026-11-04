# Copyright (c) 2026, rndops and Contributors
# See license.txt

import re

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.doctype.consultancy_invoice.consultancy_invoice import (
	get_approved_consultancy_funds,
	get_con_invoice,
	invoice_suffix,
	save_con_invoice,
)

STAFF_USER = "consultancy.invoice.staff@example.com"
OTHER_USER = "consultancy.invoice.director@example.com"
NAME_RE = re.compile(r"^INVO-\d{4}-\d{2}-\d{2}-[A-Z]{3}[0-9]{3}$")


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
		# test methods share one transaction (rolled back after the class), so start each
		# one from an empty Consultancy Invoice table
		frappe.db.delete("invoice_number", {"parenttype": "Consultancy Invoice"})
		frappe.db.delete("Consultancy Invoice")
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

	def test_saves_a_plain_string_invoice_no(self):
		f = self.fund
		res = save_con_invoice(f.project_no, f.fund_received_ref_number, "test-1234")
		self.assertRegex(res["name"], NAME_RE)
		self.assertEqual(res["invoice_no"], ["test-1234"])

		doc = frappe.get_doc("Consultancy Invoice", res["name"])
		# saved against the Fund Received docname, even though the reference number was passed
		self.assertEqual((doc.project_no, doc.fund_received_ref), (f.project_no, f.name))
		self.assertEqual(res["fund_received_ref"], f.name)
		self.assertEqual([r.invoice_number for r in doc.invoice_no], ["test-1234"])

		# numbers with slashes (like the Fund Received invoice numbers) are fine too
		o = self.other_fund
		second = save_con_invoice(o.project_no, o.fund_received_ref_number, "IITG/07000/26-27")
		self.assertEqual(second["invoice_no"], ["IITG/07000/26-27"])
		self.assertEqual(int(second["name"][-3:]), int(res["name"][-3:]) + 1)

	def test_docname_or_reference_number_reach_the_same_record(self):
		f = self.fund
		by_docname = save_con_invoice(f.project_no, f.name, "INV-1")
		by_number = save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1")
		self.assertEqual(by_docname, by_number)
		self.assertEqual(by_docname["fund_received_ref"], f.name)
		self.assertEqual(get_con_invoice(f.project_no, f.name), by_docname)
		self.assertEqual(get_con_invoice(f.project_no, f.fund_received_ref_number), by_docname)
		self.assertEqual(frappe.db.count("Consultancy Invoice"), 1)

	def test_record_saved_with_a_reference_number_is_found_and_moved_to_the_docname(self):
		f = self.fund
		legacy = frappe.get_doc(
			{
				"doctype": "Consultancy Invoice",
				"project_no": f.project_no,
				"fund_received_ref": f.fund_received_ref_number,  # how it used to be saved
				"invoice_no": [{"invoice_number": "OLD-1"}],
			}
		).insert()
		found = get_con_invoice(f.project_no, f.name)
		self.assertEqual((found["name"], found["invoice_no"]), (legacy.name, ["OLD-1"]))

		res = save_con_invoice(f.project_no, f.name, "NEW-1")
		self.assertEqual(res["name"], legacy.name)
		self.assertEqual(res["invoice_no"], ["OLD-1", "NEW-1"])
		self.assertEqual(frappe.db.get_value("Consultancy Invoice", legacy.name, "fund_received_ref"), f.name)
		self.assertEqual(frappe.db.count("Consultancy Invoice"), 1)

	def test_accepts_a_list_or_json_list_and_adds_to_the_same_document(self):
		f = self.fund
		first = save_con_invoice(f.project_no, f.fund_received_ref_number, ["INV-1", "INV-2"])
		self.assertEqual(first["invoice_no"], ["INV-1", "INV-2"])

		# same pair again: new numbers are added to the same document, known ones ignored
		again = save_con_invoice(f.project_no, f.fund_received_ref_number, '["INV-2", "INV-3"]')
		self.assertEqual(again["name"], first["name"])
		self.assertEqual(again["invoice_no"], ["INV-1", "INV-2", "INV-3"])
		self.assertEqual(save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1"), again)
		self.assertEqual(frappe.db.count("Consultancy Invoice"), 1)

	def test_numbers_must_be_present_and_unique_across_invoices(self):
		f, o = self.fund, self.other_fund
		save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1")
		with self.assertRaises(frappe.DuplicateEntryError):
			save_con_invoice(o.project_no, o.fund_received_ref_number, "INV-1")
		for blank in ("  ", "", [], ["", " "]):
			with self.assertRaises(frappe.ValidationError):
				save_con_invoice(f.project_no, f.fund_received_ref_number, blank)
		self.assertEqual(frappe.db.count("Consultancy Invoice"), 1)

	def test_project_can_be_given_by_name(self):
		f = self.fund
		by_no = save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1")
		by_name = save_con_invoice(f.prjreg_title, f.fund_received_ref_number, "INV-1")
		self.assertEqual(by_no, by_name)

	def test_get_returns_name_and_numbers_or_empty(self):
		f = self.fund
		empty = {"name": None, "fund_received_ref": None, "invoice_no": []}
		self.assertEqual(get_con_invoice(f.project_no, f.fund_received_ref_number), empty)
		saved = save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1")
		self.assertEqual(get_con_invoice(f.project_no, f.fund_received_ref_number), saved)
		self.assertEqual(get_con_invoice("NO-SUCH-PROJECT", "1"), empty)

	def test_invalid_inputs_are_rejected(self):
		f = self.fund
		with self.assertRaises(frappe.DoesNotExistError):
			save_con_invoice("NO-SUCH-PROJECT", f.fund_received_ref_number, "INV-1")
		with self.assertRaises(frappe.DoesNotExistError):
			save_con_invoice(f.project_no, "NO-SUCH-FUND-REF", "INV-1")
		if self.other_fund.prjreg_title != f.prjreg_title:
			with self.assertRaises(frappe.ValidationError):
				save_con_invoice(f.project_no, self.other_fund.fund_received_ref_number, "INV-1")

	def test_everyone_can_view_but_only_authorised_roles_can_save(self):
		f = self.fund
		saved = save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-1")

		frappe.set_user(OTHER_USER)  # a Director: read-only on this DocType
		self.assertEqual(get_con_invoice(f.project_no, f.fund_received_ref_number), saved)
		self.assertTrue(frappe.has_permission("Consultancy Invoice", "read", saved["name"]))
		with self.assertRaises(frappe.PermissionError):
			save_con_invoice(f.project_no, f.fund_received_ref_number, "INV-9")
		with self.assertRaises(frappe.PermissionError):
			save_con_invoice(self.other_fund.project_no, self.other_fund.fund_received_ref_number, "INV-2")

	def test_approved_consultancy_funds(self):
		frappe.set_user("Administrator")
		page = get_approved_consultancy_funds()
		result = page["data"]
		if not result:
			self.skipTest("no approved consultancy project with Fund Received on the site")

		self.assertEqual(page["page_size"], 10)
		self.assertLessEqual(len(result), 10)
		self.assertEqual(page["count"], len(result))
		for p in result:
			self.assertEqual(
				tuple(frappe.db.get_value("Project Registration", p["project"], ["project_type", "workflow_state", "docstatus"])),
				("Consultancy", "Approved", 1),
			)
			self.assertTrue(p["fund_received"])
			for fund in p["fund_received"]:
				self.assertEqual(frappe.db.get_value("Fund Received", fund["name"], "prjreg_title"), p["project"])
				for slip in fund["deposit_slips"]:
					# a slip points at its Fund Received by docname or by reference number
					ref = frappe.db.get_value(slip["doctype"], slip["name"], "fund_received_ref")
					self.assertIn(ref, (fund["name"], fund["fund_received_ref_number"]))

		first = result[0]
		for key in (first["project_no"], first["project"]):
			one = get_approved_consultancy_funds(key)
			self.assertEqual([p["project"] for p in one["data"]], [first["project"]])
			self.assertEqual((one["total"], one["has_next"], one["has_previous"]), (1, False, False))
		self.assertEqual(get_approved_consultancy_funds("NO-SUCH-PROJECT")["data"], [])

	def test_approved_consultancy_funds_pagination(self):
		frappe.set_user("Administrator")

		def names(page):
			return [p["project"] for p in page["data"]]

		page = get_approved_consultancy_funds(page_size=3)
		if page["total"] < 7:
			self.skipTest("needs at least 7 approved consultancy projects with funds")
		self.assertFalse(page["has_previous"])
		self.assertIsNone(page["previous_id"])

		# forward through every page: no repeats, nothing missed, every full page is page_size
		pages = [names(page)]
		while page["next_id"]:
			page = get_approved_consultancy_funds(pagination_id=page["next_id"], page_size=3)
			pages.append(names(page))
		flat = [n for p in pages for n in p]
		self.assertEqual(len(flat), len(set(flat)))
		self.assertEqual(len(flat), page["total"])
		self.assertTrue(all(len(p) == 3 for p in pages[:-1]))
		self.assertFalse(page["has_next"])

		# backward from the last page gives the same pages in reverse
		back = [names(page)]
		while page["previous_id"]:
			page = get_approved_consultancy_funds(pagination_id=page["previous_id"], page_size=3)
			back.append(names(page))
		self.assertEqual(back, list(reversed(pages)))

		# default size and limits
		self.assertEqual(get_approved_consultancy_funds()["page_size"], 10)
		self.assertEqual(get_approved_consultancy_funds(page_size=0)["page_size"], 10)
		self.assertEqual(get_approved_consultancy_funds(page_size=100000)["page_size"], 100)
		with self.assertRaises(frappe.ValidationError):
			get_approved_consultancy_funds(pagination_id="not-a-valid-id!")

	def test_approved_consultancy_funds_respects_the_callers_own_permissions(self):
		# The endpoint reads projects/funds with the caller's permissions, so a user whose
		# only role is Director (no read on Project Registration) is refused, not shown everything.
		frappe.set_user(OTHER_USER)
		with self.assertRaises(frappe.PermissionError):
			get_approved_consultancy_funds()
