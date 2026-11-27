from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.delegate_user import delegate_user as du

PI = "deleg-pi@example.com"
DELEGATE = "deleg-b@example.com"

SPECIFIC = "Specific Application"
ALLOWED = ["Travel", "Loan Request", "Disbursal of Consultancy"]

FUNDED = "TEST-DEL-FUNDED"
OTHER = "TEST-DEL-OTHER"  # funded and approved, never delegated
UNFUNDED = "TEST-DEL-UNFUNDED"
UNAPPROVED = "TEST-DEL-UNAPPROVED"
FOREIGN = "TEST-DEL-FOREIGN"  # PI is only head_approver

MANDATORY = {
	"Travel": {
		"organizing_authority": "Test",
		"from_date": "2026-12-01",
		"to_date": "2026-12-02",
		"travel_financial_assistance": "No",
	},
}


def _balances(project_no):
	amount = 0 if UNFUNDED in project_no else 1000
	return {"status": "success", "data": {"committable": amount, "actualBalance": amount}}


class TestUserDelegation(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# The code under test commits; keep everything inside one transaction
		# that is rolled back after each test.
		for target, kwargs in (
			(patch.object(frappe.db, "commit"), {}),
			(patch.object(du, "_fetch_project_balances", side_effect=_balances), {}),
		):
			target.start()
			self.addCleanup(target.stop)
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(frappe.set_user, "Administrator")

		for email in (PI, DELEGATE):
			if not frappe.db.exists("User", email):
				user = frappe.get_doc(
					{"doctype": "User", "email": email, "first_name": email.split("@")[0]}
				)
				user.name = email
				user.db_insert()
		frappe.db.set_value("User", PI, "enabled", 1)
		frappe.db.set_value("User", DELEGATE, "enabled", 1)

		for name in (FUNDED, OTHER, UNFUNDED, UNAPPROVED, FOREIGN):
			project = frappe.new_doc("Project Registration")
			project.update({
				"name": name,
				"project_no": f"NO-{name}",
				"project_title": f"Title {name}",
				"workflow_state": "Draft" if name == UNAPPROVED else "Approved",
				"owner": "Administrator",
				"pi_webmail": "Administrator" if name == FOREIGN else PI,
				"head_approver": PI if name == FOREIGN else None,
			})
			project.db_insert()

		frappe.set_user(PI)

	def _delegate(self, **kwargs):
		frappe.set_user(PI)
		args = {
			"delegate_user": DELEGATE,
			"delegation_type": SPECIFIC,
			"scope_type": "project",
			"project_names": frappe.as_json([FUNDED]),
			"applications": "[]",
			"allowed_doctypes": frappe.as_json(ALLOWED),
			**kwargs,
		}
		return du.delegate_user(**args)["name"]

	def _create(self, doctype="Loan Request", project=FUNDED, fields=None):
		frappe.set_user(DELEGATE)
		fields = {**MANDATORY.get(doctype, {}), **(fields or {})}
		return du.create_application_on_behalf(doctype, PI, project, fields)["name"]

	# ── create ───────────────────────────────────────────────────────────────

	def test_create_is_owned_by_delegator_and_scoped_to_project(self):
		delegation = self._delegate()
		for doctype in ALLOWED:
			name = self._create(doctype, fields={"owner": DELEGATE, "doctype": "User"})
			doc = frappe.get_doc(doctype, name)
			self.assertEqual(doc.owner, PI)
			for field, column in du._ON_BEHALF_PROJECT_FIELDS[doctype].items():
				expected = frappe.db.get_value("Project Registration", FUNDED, column)
				self.assertEqual(doc.get(field), expected, f"{doctype}.{field}")

			log = frappe.get_last_doc("Delegation Audit Log", {"application_name": name})
			self.assertEqual(
				(log.actual_user, log.delegator_user, log.delegation, log.project_name, log.status),
				(DELEGATE, PI, delegation, FUNDED, "Success"),
			)

	def test_client_cannot_redirect_project_or_applicant(self):
		self._delegate()
		name = self._create(fields={
			"project_name": OTHER,
			"project_number": f"NO-{OTHER}",
			"loan_for_webmail_id": DELEGATE,
		})
		doc = frappe.get_doc("Loan Request", name)
		self.assertEqual(doc.project_name, FUNDED)
		self.assertEqual(doc.project_number, f"NO-{FUNDED}")
		self.assertEqual(doc.loan_for_webmail_id, PI)

	def test_rejects_doctype_not_allowed(self):
		self._delegate()
		with self.assertRaises(frappe.PermissionError):
			self._create("Reimbursement")
		log = frappe.get_last_doc("Delegation Audit Log", {"actual_user": DELEGATE})
		self.assertEqual((log.status, log.application_name), ("Failed", None))

	def test_rejects_project_not_delegated(self):
		self._delegate()
		with self.assertRaises(frappe.PermissionError):
			self._create(project=OTHER)

	def test_requires_project_name(self):
		self._delegate()
		with self.assertRaisesRegex(frappe.ValidationError, "requires project_name"):
			self._create("Disbursal of Consultancy", project=None)

	def test_rechecks_eligibility_at_create(self):
		self._delegate()
		frappe.db.set_value("Project Registration", FUNDED, "workflow_state", "Draft")
		with self.assertRaisesRegex(frappe.ValidationError, "not approved"):
			self._create()
		frappe.db.set_value("Project Registration", FUNDED, "workflow_state", "Approved")
		with patch.object(du, "_fetch_project_balances", return_value={"status": "error"}):
			with self.assertRaisesRegex(frappe.ValidationError, "could not be verified"):
				self._create()

	def test_rejects_outside_validity_and_after_revoke(self):
		name = self._delegate(valid_to="2000-01-01 00:00:00")
		with self.assertRaises(frappe.PermissionError):
			self._create()
		frappe.db.set_value("User Delegation", name, "valid_to", None)
		frappe.set_user(PI)
		du.undelegate_user(name)
		with self.assertRaises(frappe.PermissionError):
			self._create()

	# ── delegate_user validation ─────────────────────────────────────────────

	def test_delegate_user_rejections(self):
		cases = [
			({"project_names": frappe.as_json([UNAPPROVED])}, "UNAPPROVED.*not approved"),
			({"project_names": frappe.as_json([UNFUNDED])}, "UNFUNDED.*no available funds"),
			({"project_names": frappe.as_json([FOREIGN])}, "does not belong"),
			({"scope_type": "all"}, "scope_type must be 'project'"),
			({"scope_type": "application"}, "scope_type must be 'project'"),
			({"scope_type": None}, "scope_type must be 'project'"),
			({"project_names": "[]"}, "At least one project"),
			({"allowed_doctypes": "[]"}, "At least one entry in allowed_doctypes"),
			({"allowed_doctypes": '["User"]'}, "'User' is not a delegable application doctype"),
		]
		for kwargs, message in cases:
			with self.subTest(kwargs), self.assertRaisesRegex(frappe.ValidationError, message):
				self._delegate(**kwargs)
		self.assertFalse(frappe.db.exists("User Delegation", {"delegator_user": PI}))

	def test_add_and_remove(self):
		name = self._delegate()
		self.assertEqual(
			self._delegate(
				project_names=frappe.as_json([OTHER]), allowed_doctypes='["Reimbursement"]'
			),
			name,
		)
		# Removing an exhausted project must not be blocked by its own eligibility.
		with patch.object(du, "_fetch_project_balances", return_value={"status": "error"}):
			self._delegate(
				project_names="[]", allowed_doctypes="[]",
				remove_project_names=frappe.as_json([FUNDED]),
				remove_allowed_doctypes='["Travel"]',
			)
		row = du.get_active_delegations()[0]
		self.assertEqual(row["project_names"], [OTHER])
		self.assertEqual(
			row["allowed_doctypes"], ["Loan Request", "Disbursal of Consultancy", "Reimbursement"]
		)
		with self.assertRaisesRegex(frappe.ValidationError, "At least one project"):
			self._delegate(project_names="[]", remove_project_names=frappe.as_json([OTHER]))

	def test_never_merges_with_access_delegation(self):
		view = self._delegate(delegation_type="View Only", project_names=frappe.as_json([OTHER]))
		specific = self._delegate()
		self.assertNotEqual(view, specific)
		view_row = frappe.get_doc("User Delegation", view)
		self.assertEqual(view_row.delegation_type, "View Only")
		self.assertEqual(du._safe_json_list(view_row.project_names), [OTHER])
		self.assertFalse(view_row.allowed_doctypes)
		# An update that names no type goes to the access row.
		self.assertEqual(self._delegate(delegation_type=None, scope_type=None), view)

	# ── no read access ───────────────────────────────────────────────────────

	def test_grants_no_access(self):
		frappe.set_user("Administrator")
		existing = frappe.new_doc("Loan Request")
		existing.update({"name": "TEST-DEL-LOAN", "owner": PI, "loan_for_webmail_id": PI,
			"project_name": FUNDED})
		existing.db_insert()
		self._delegate()
		created = self._create()

		self.assertEqual(du.get_visible_as_users(DELEGATE), [DELEGATE])
		self.assertEqual(du.loan_request_permission_query(DELEGATE), "")
		self.assertEqual(du.project_registration_permission_query(DELEGATE), "")
		self.assertEqual(du._scoped_doc_names_for_doctype(PI, DELEGATE, "Loan Request"), set())
		for name in (existing.name, created):
			doc = frappe.get_doc("Loan Request", name)
			for ptype, action in (("read", "read"), ("write", "write"), ("workflow_action", "workflow")):
				self.assertIsNone(du.has_delegated_access(doc, ptype=ptype, user=DELEGATE))
				with self.assertRaises(frappe.PermissionError):
					du.require_document_access(doc, action)

	# ── read APIs ────────────────────────────────────────────────────────────

	def test_read_apis(self):
		name = self._delegate()
		self.assertEqual(du.get_delegate_scope()["delegations"][0]["allowed_doctypes"], ALLOWED)

		frappe.set_user(DELEGATE)
		[row] = du.get_received_delegations()
		self.assertEqual(row["name"], name)
		self.assertEqual(row["delegator_user"], PI)
		self.assertEqual(row["allowed_doctypes"], ALLOWED)
		self.assertEqual(row["project_names"], [
			{"name": FUNDED, "project_title": f"Title {FUNDED}", "project_no": f"NO-{FUNDED}"}
		])

		frappe.db.set_value("User Delegation", name, "valid_from", "2999-01-01 00:00:00")
		self.assertEqual(du.get_received_delegations(), [])

	# ── other types unchanged ────────────────────────────────────────────────

	def test_view_only_cannot_create_but_can_read(self):
		self._delegate(delegation_type="View Only")
		self.assertEqual(du.get_visible_as_users(DELEGATE), [DELEGATE, PI])
		self.assertTrue(du.is_active_delegation(PI, DELEGATE, "Project Registration", FUNDED))
		self.assertFalse(
			du.is_active_delegation(PI, DELEGATE, "Project Registration", FUNDED, "write")
		)
		with self.assertRaises(frappe.PermissionError):
			self._create()

	def test_access_types_create_as_before(self):
		for delegation_type in ("View and Edit", "Workflow Action"):
			# No eligibility check for these types.
			name = self._delegate(
				delegation_type=delegation_type, project_names=frappe.as_json([UNFUNDED])
			)
			created = self._create("Travel", project=UNFUNDED)
			doc = frappe.get_doc("Travel", created)
			self.assertEqual(doc.owner, DELEGATE)
			self.assertEqual(doc.webmail_id_travel, PI)
			self.assertEqual(doc.travel_project_number, f"NO-{UNFUNDED}")
			self.assertTrue(du.is_active_delegation(PI, DELEGATE, "Travel", created, "write"))
			self.assertEqual(
				du.is_active_delegation(PI, DELEGATE, "Travel", created, "workflow"),
				delegation_type == "Workflow Action",
			)
			# Doctypes with no registry project field still don't require one.
			frappe.set_user(PI)
			du.delegate_user(DELEGATE, scope_type="all")
			self._create("Disbursal of Consultancy", project=None)
			frappe.set_user(PI)
			du.undelegate_user(name)
