# Copyright (c) 2026, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.ledger_notes_api import (
	delete_ledger_note,
	get_ledger_notes,
	save_ledger_note,
)

STAFF_USER = "ledger.note.staff@example.com"
READER_USER = "ledger.note.director@example.com"


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


class TestLedgerNote(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_make_user(STAFF_USER, "staff, RnD")
		_make_user(READER_USER, "Director")
		project = frappe.get_all(
			"Project Registration", filters={"project_no": ["!=", ""], "docstatus": 1}, fields=["name", "project_no"], limit=1
		)
		if not project:
			raise cls.skipTest(cls, "needs at least one submitted Project Registration with a project_no")
		cls.project = project[0].name
		cls.project_no = project[0].project_no

	def setUp(self):
		frappe.set_user(STAFF_USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_staff_can_save_update_and_delete(self):
		res = save_ledger_note(self.project, "<p>first</p>", transaction_id="TID-1", reference_summary="s")
		self.assertTrue(res["name"])

		res2 = save_ledger_note(self.project, "<p>second</p>", transaction_id="TID-1", modified=res["modified"])
		self.assertEqual(res2["name"], res["name"])
		self.assertEqual(frappe.db.get_value("Ledger Note", res["name"], "content"), "<p>second</p>")

		delete_ledger_note(res["name"])
		self.assertFalse(frappe.db.exists("Ledger Note", res["name"]))

	def test_project_can_be_given_as_project_no(self):
		res = save_ledger_note(self.project_no, "<p>x</p>")
		self.assertEqual(frappe.db.get_value("Ledger Note", res["name"], "project_no"), self.project)

	def test_unknown_project_is_rejected(self):
		with self.assertRaises(frappe.DoesNotExistError):
			save_ledger_note("NO-SUCH-PROJECT", "<p>x</p>")

	def test_non_staff_can_read_but_not_write(self):
		res = save_ledger_note(self.project, "<p>seen</p>", transaction_id="TID-R")

		frappe.set_user(READER_USER)
		notes = get_ledger_notes(self.project)
		self.assertIn(res["name"], [n["name"] for n in notes])

		with self.assertRaises(frappe.PermissionError):
			save_ledger_note(self.project, "<p>nope</p>", transaction_id="TID-R2")
		with self.assertRaises(frappe.PermissionError):
			delete_ledger_note(res["name"])

	def test_second_save_upserts_and_duplicate_is_rejected(self):
		first = save_ledger_note(self.project, "<p>a</p>", transaction_id="TID-U")
		again = save_ledger_note(self.project, "<p>b</p>", transaction_id=" TID-U ")
		self.assertEqual(first["name"], again["name"])
		self.assertEqual(
			frappe.db.count("Ledger Note", {"project_no": self.project, "transaction_id": "TID-U"}), 1
		)

		# General notes: None and "" are the same key.
		g1 = save_ledger_note(self.project, "<p>g</p>", transaction_id=None)
		g2 = save_ledger_note(self.project, "<p>g2</p>", transaction_id="")
		self.assertEqual(g1["name"], g2["name"])

		# A direct insert bypassing the upsert must hit the validate() uniqueness check.
		dup = frappe.get_doc(
			{"doctype": "Ledger Note", "project_no": self.project, "transaction_id": "TID-U", "content": "x"}
		)
		with self.assertRaises(frappe.DuplicateEntryError):
			dup.insert()

	def test_script_tags_are_stripped(self):
		res = save_ledger_note(
			self.project,
			'<p onclick="x()">hi</p><script>alert(1)</script><img src=x onerror="alert(2)">',
			transaction_id="TID-XSS",
		)
		content = frappe.db.get_value("Ledger Note", res["name"], "content").lower()
		self.assertNotIn("<script", content)
		self.assertNotIn("onerror", content)
		self.assertNotIn("onclick", content)
		self.assertIn("hi", content)

	def test_stale_modified_raises_timestamp_mismatch(self):
		res = save_ledger_note(self.project, "<p>v1</p>", transaction_id="TID-C")
		stale = res["modified"]
		save_ledger_note(self.project, "<p>v2</p>", transaction_id="TID-C", modified=stale)

		with self.assertRaises(frappe.TimestampMismatchError):
			save_ledger_note(self.project, "<p>v3</p>", transaction_id="TID-C", modified=stale)
		self.assertEqual(frappe.db.get_value("Ledger Note", res["name"], "content"), "<p>v2</p>")
