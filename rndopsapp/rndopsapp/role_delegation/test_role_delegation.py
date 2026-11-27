"""
Role delegation tests. Requests go through frappe.app.application, so the auth
hook, session storage and after_request log run as in production.

These tests commit: they create temporary users and records and delete them
again. Run on a development site only.
"""

import json
import threading
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime
from werkzeug.test import Client

from rndopsapp.rndopsapp.role_delegation import service

API = "/api/method/rndopsapp.rndopsapp.api."
HEADER = "X-Acting-Delegation"
TEST_DOC_PREFIX = "RD-TEST-TA-"
ADO = "rd_test_ado@example.com"
DEAN = "rd_test_dean@example.com"
OTHER = "rd_test_other@example.com"
STAFF = "rd_test_staff@example.com"
USERS = {
	ADO: ["Ado_RnD", "All_ProRnd_User"],
	DEAN: ["Dean, RnD", "All_ProRnd_User"],
	OTHER: ["Dean, RnD", "All_ProRnd_User"],
	STAFF: ["All_ProRnd_User"],
}


def _workflow_without_field_updates(doctype):
	"""
	The site's Temporary Advance states have an update_field that blanks
	workflow_state in Frappe's generic apply_workflow. Not part of this test.
	"""
	from frappe.model.workflow import get_workflow_name

	workflow = frappe.get_doc("Workflow", get_workflow_name(doctype))
	for state in workflow.states:
		state.update_field = None
	return workflow


class TestRoleDelegation(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Read here: request threads have no frappe.local of their own yet.
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.patches = [
			patch.object(service, "is_enabled", return_value=True),
			# No external publishing or mail from test documents.
			patch("rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish"),
			patch("rndopsapp.rndopsapp.email.workflow_monitor.on_workflow_state_change"),
		]
		for p in cls.patches:
			p.start()
		cls._cleanup()
		for email, roles in USERS.items():
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"send_welcome_email": 0,
					"user_type": "System User",
					"roles": [{"role": r} for r in roles],
				}
			)
			user.flags.no_welcome_mail = True
			user.insert(ignore_permissions=True)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._cleanup()
		for p in cls.patches:
			p.stop()
		super().tearDownClass()

	@classmethod
	def _cleanup(cls):
		frappe.db.rollback()
		users = tuple(USERS)
		for name in frappe.get_all("Role Delegation", filters={"delegator": ("in", users)}, pluck="name"):
			frappe.db.delete("Role Delegation Role", {"parent": name})
			frappe.db.delete("Role Delegation", {"name": name})
		frappe.db.delete("Role Delegation Log", {"actual_user": ("in", users)})
		# By name, not owner: test documents have several different owners.
		mine = ("like", f"{TEST_DOC_PREFIX}%")
		frappe.db.delete("Comment", {"reference_name": mine})
		frappe.db.delete("Staff Activity Log", {"document_name": mine})
		frappe.db.delete("Temporary Advance", {"name": mine})
		for email in users:
			frappe.db.delete("Sessions", {"user": email})
			if frappe.db.exists("User", email):
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.db.delete("Role Delegation Log", {"actual_user": ("in", tuple(USERS))})
		for name in frappe.get_all("Role Delegation", filters={"delegator": ADO}, pluck="name"):
			frappe.db.delete("Role Delegation Role", {"parent": name})
			frappe.db.delete("Role Delegation", {"name": name})
		frappe.db.commit()

	# ------------------------------------------------------------ helpers

	def grant(self, delegate=DEAN, roles=("Ado_RnD",), start=-1, end=24):
		doc = frappe.get_doc(
			{
				"doctype": "Role Delegation",
				"delegator": ADO,
				"delegate": delegate,
				"roles": [{"role": r} for r in roles],
				"from_datetime": add_to_date(now_datetime(), hours=start),
				"to_datetime": add_to_date(now_datetime(), hours=end),
				"reason": "test",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def login(self, user):
		"""A browser session without calling any external login service."""
		sid = []

		def start():
			from frappe.sessions import Session

			frappe.init(site=self.site, sites_path=self.sites_path)
			frappe.connect()
			try:
				frappe.local.request_ip = "127.0.0.1"
				frappe.local.form_dict = frappe._dict()
				frappe.local.request = frappe._dict(cookies={}, headers={})
				session = Session(user=user, resume=False, full_name=user, user_type="System User")
				sid.append(session.data.sid)
				frappe.db.commit()
			finally:
				frappe.destroy()

		self._in_thread(start)
		return sid[0]

	def call(self, sid, method, data=None, header=None, verb="POST", path=None):
		result = {}

		def run():
			from frappe.app import application

			client = Client(application)
			client.set_cookie("sid", sid)
			headers = {"X-Frappe-Site-Name": self.site, "Accept": "application/json"}
			if header:
				headers[HEADER] = header
			kwargs = {"headers": headers}
			if verb == "POST":
				kwargs["json"] = data or {}
			else:
				kwargs["query_string"] = data or {}
			response = client.open(path or API + method, method=verb, **kwargs)
			result["status"] = response.status_code
			result["body"] = json.loads(response.get_data(as_text=True) or "{}")

		self._in_thread(run)
		frappe.db.rollback()  # see what the request committed
		return result["status"], result["body"]

	def _in_thread(self, fn):
		"""frappe.local is per context, so requests cannot disturb the test's."""
		errors = []

		def target():
			try:
				fn()
			except BaseException as e:
				errors.append(e)

		thread = threading.Thread(target=target)
		thread.start()
		thread.join()
		if errors:
			raise errors[0]

	def roles(self, sid, header=None):
		status, body = self.call(sid, "get_user_roles", header=header, verb="GET")
		self.assertEqual(status, 200, body)
		return set(body["message"])

	def switch(self, sid, grant, header=None):
		status, body = self.call(sid, "switch_profile", {"delegation": grant}, header=header)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["current"], grant)

	def switch_back(self, sid, header=None):
		status, body = self.call(sid, "switch_to_own_profile", header=header)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["current"], "self")

	def logs(self, **filters):
		return frappe.get_all("Role Delegation Log", filters=filters, fields=["*"])

	# ------------------------------------------------------------ grants

	def test_grant_rules(self):
		def rejects(**kwargs):
			with self.assertRaises(frappe.ValidationError):
				self.grant(**kwargs)

		rejects(delegate=ADO)
		rejects(roles=("System Manager",))
		rejects(roles=("Dean, RnD",))  # not held by the delegator
		rejects(roles=("Associate Dean, RND",))  # not delegable
		rejects(delegate=STAFF)  # holds no role that can receive
		rejects(roles=())
		rejects(start=-5, end=-1)
		rejects(start=5, end=1)
		name = self.grant()
		rejects()  # overlap
		doc = frappe.get_doc("Role Delegation", name)
		doc.to_datetime = add_to_date(now_datetime(), days=30)
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_create_list_revoke_over_http(self):
		ado, other = self.login(ADO), self.login(OTHER)
		status, body = self.call(ado, "create_role_delegation", {
			"delegate": DEAN, "roles": ["Ado_RnD"], "reason": "leave",
			"from_datetime": str(add_to_date(now_datetime(), hours=-1))[:19],
			"to_datetime": str(add_to_date(now_datetime(), hours=5))[:19],
		})
		self.assertEqual(status, 200, body)
		name = body["message"]["name"]
		self.assertEqual(body["message"]["delegator"], ADO)
		self.assertEqual(body["message"]["state"], "active")

		status, body = self.call(ado, "get_role_delegations", verb="GET")
		self.assertEqual(body["message"]["delegable_roles"], ["Ado_RnD"])
		self.assertEqual([g["name"] for g in body["message"]["given"]], [name])

		status, _body = self.call(other, "revoke_role_delegation", {"delegation": name})
		self.assertEqual(status, 403)
		status, body = self.call(ado, "revoke_role_delegation", {"delegation": name})
		self.assertEqual(body["message"]["state"], "revoked")
		self.assertEqual({row.event for row in self.logs(delegation=name)}, {"grant", "revoke"})

	# ------------------------------------------------------------ switching

	def test_switch_and_switch_back(self):
		name = self.grant()
		sid = self.login(DEAN)
		own = self.roles(sid)
		self.assertIn("Dean, RnD", own)
		self.assertNotIn("Ado_RnD", own)

		status, body = self.call(sid, "get_acting_profiles", verb="GET")
		self.assertEqual([p["id"] for p in body["message"]["profiles"]], ["self", name])

		self.switch(sid, name)
		acting = self.roles(sid, header=name)
		self.assertIn("Ado_RnD", acting)
		self.assertNotIn("Dean, RnD", acting)

		# The shared role cache still holds the user's real roles.
		cached = frappe.cache.hget("roles", DEAN)
		frappe.local.cache.pop(frappe.cache.make_key("roles"), None)
		cached = frappe.cache.hget("roles", DEAN)
		self.assertNotIn("Ado_RnD", cached or [])

		# Another session of the same user is unaffected.
		self.assertIn("Dean, RnD", self.roles(self.login(DEAN)))

		self.switch_back(sid, header=name)
		self.assertEqual(self.roles(sid), own)
		self.switch_back(sid)  # harmless when already on own profile
		self.assertEqual(
			sorted(row.event for row in self.logs(delegation=name)), ["switch_in", "switch_out"]
		)

	def test_cannot_use_someone_elses_grant(self):
		name = self.grant()
		sid = self.login(OTHER)
		status, body = self.call(sid, "switch_profile", {"delegation": name})
		self.assertEqual(status, 403, body)
		self.assertNotIn("Ado_RnD", self.roles(sid))
		self.assertTrue(self.logs(actual_user=OTHER, event="denied"))

	def test_scheduled_grant_cannot_be_used(self):
		name = self.grant(start=2, end=5)
		status, _body = self.call(self.login(DEAN), "switch_profile", {"delegation": name})
		self.assertEqual(status, 403)

	def test_switch_needs_post(self):
		name = self.grant()
		sid = self.login(DEAN)
		status, _body = self.call(sid, "switch_profile", {"delegation": name}, verb="GET")
		self.assertEqual(status, 403)

	def test_header_must_match(self):
		name = self.grant()
		sid = self.login(DEAN)

		# Own profile, tab claims to be acting.
		status, body = self.call(sid, "get_role_delegations", header=name)
		self.assertEqual((status, body.get("exc_type")), (409, "ProfileMismatch"), body)

		self.switch(sid, name)
		for header in (None, "self", "RD-99999"):
			status, body = self.call(sid, "get_role_delegations", header=header)
			self.assertEqual((status, body.get("exc_type")), (409, "ProfileMismatch"), body)

		status, _body = self.call(sid, "get_role_delegations", header=name)
		self.assertEqual(status, 200)

	def test_cmd_parameter_cannot_borrow_an_exemption(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		status, body = self.call(
			sid, "get_acting_profiles",
			{"cmd": "rndopsapp.rndopsapp.api.get_role_delegations"},
		)
		self.assertEqual((status, body.get("exc_type")), (409, "ProfileMismatch"), body)

	def test_revoked_and_expired_grants_end_the_profile(self):
		for change in (
			{"status": "Revoked"},
			{"to_datetime": add_to_date(now_datetime(), minutes=-1)},
		):
			self.setUp()
			name = self.grant()
			sid = self.login(DEAN)
			self.switch(sid, name)
			frappe.db.set_value("Role Delegation", name, change)
			frappe.db.commit()

			status, body = self.call(sid, "get_role_delegations", header=name)
			self.assertEqual((status, body.get("exc_type")), (409, "DelegationEnded"), body)
			own = self.roles(sid)
			self.assertIn("Dean, RnD", own)
			self.assertNotIn("Ado_RnD", own)
			self.assertTrue(self.logs(delegation=name, event="switch_out"))

	def test_switch_back_after_revocation(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		frappe.db.set_value("Role Delegation", name, "status", "Revoked")
		frappe.db.commit()
		self.switch_back(sid)

	def test_delegator_losing_the_role_ends_the_profile(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		row = frappe.db.get_value("Has Role", {"parent": ADO, "role": "Ado_RnD"}, "name")
		frappe.db.set_value("Has Role", row, "parent", "rd_test_nobody")
		frappe.db.commit()
		try:
			status, body = self.call(sid, "get_role_delegations", header=name)
			self.assertEqual(body.get("exc_type"), "DelegationEnded", body)
		finally:
			frappe.db.set_value("Has Role", row, "parent", ADO)
			frappe.db.commit()

	def test_logout_then_login_starts_on_own_profile(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		status, body = self.call(sid, "", header=name, path="/api/method/logout")
		self.assertEqual(status, 200, body)
		self.assertEqual(self.logs(delegation=name, event="switch_out")[0].message, "logout")
		self.assertIn("Dean, RnD", self.roles(self.login(DEAN)))

	def test_delegation_management_refused_while_acting(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		for method, data in (
			("revoke_role_delegation", {"delegation": name}),
			("undelegate_user", {"delegation_name": "none"}),
			("delegate_user", {"delegate_user": OTHER}),
		):
			status, body = self.call(sid, method, data, header=name)
			self.assertEqual(status, 403, (method, body))
		# Failed writes made while acting are logged.
		self.assertTrue(self.logs(delegation=name, event="action", result="Failed"))

	# ------------------------------------------------------------ approvals

	def _temporary_advance(self, owner, state="Pending Associate Dean"):
		doc = frappe.new_doc("Temporary Advance")
		doc.name = f"{TEST_DOC_PREFIX}{frappe.generate_hash(length=8)}"
		doc.owner = owner
		doc.workflow_state = state
		doc.account_head = "Test Head"
		doc.db_insert()
		# db_insert stamps the session user as owner.
		frappe.db.set_value("Temporary Advance", doc.name, "owner", owner, update_modified=False)
		frappe.db.commit()
		return doc.name

	def _act(self, sid, docname, action, header=None):
		return self.call(
			sid, None, {"docname": docname, "action": action}, header=header,
			path="/api/method/rndopsapp.rndopsapp.doctype.temporary_advance."
			"temporary_advance.perform_temporary_advance_action",
		)

	def _action_for(self, docname, role):
		state = frappe.db.get_value("Temporary Advance", docname, "workflow_state")
		workflow = frappe.db.get_value(
			"Workflow", {"document_type": "Temporary Advance", "is_active": 1}
		)
		rows = frappe.get_all(
			"Workflow Transition",
			filters={"parent": workflow, "state": state, "allowed": role},
			fields=["action", "next_state"],
		)
		forward = [r for r in rows if not r.action.lower().startswith(("reject", "put back"))]
		if not forward:
			self.skipTest(f"No forward transition for {role} from {state} on this site")
		return forward[0]

	def test_approval_as_delegate_then_double_approval_blocked(self):
		name = self.grant()
		docname = self._temporary_advance(ADO.replace("ado", "applicant"))
		sid = self.login(DEAN)
		transition = self._action_for(docname, "Ado_RnD")

		# On the own profile the Dean cannot take the Associate Dean step.
		status, body = self._act(sid, docname, transition.action)
		self.assertEqual(body["message"]["status"], "error", body)

		self.switch(sid, name)
		status, body = self._act(sid, docname, transition.action, header=name)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["status"], "success", body)
		self.assertEqual(
			frappe.db.get_value("Temporary Advance", docname, "workflow_state"), transition.next_state
		)
		# The record shows the delegator; the log shows who really acted.
		self.assertEqual(frappe.db.get_value("Temporary Advance", docname, "modified_by"), ADO)

		rows = self.logs(ref_name=docname, event="action")
		self.assertEqual(len(rows), 1, rows)
		self.assertEqual(
			(rows[0].actual_user, rows[0].delegator, rows[0].delegated_roles, rows[0].result),
			(DEAN, ADO, "Ado_RnD", "Success"),
		)
		self.assertTrue(
			frappe.db.exists("Comment", {"reference_name": docname, "content": ("like", "%acting as%")})
		)

		self.switch_back(sid, header=name)
		status, body = self._act(sid, docname, "Approve")
		self.assertEqual(status, 403, body)
		self.assertIn("cannot approve it again", json.dumps(body))

		# A put back starts a new approval cycle.
		frappe.db.set_value("Role Delegation Log", rows[0].name, "superseded", 1)
		frappe.db.commit()
		status, body = self._act(sid, docname, "Approve")
		self.assertEqual(status, 200, body)

	def test_failed_action_is_logged_and_does_not_block(self):
		name = self.grant()
		docname = self._temporary_advance("rd_test_applicant@example.com")
		sid = self.login(DEAN)
		self.switch(sid, name)
		status, body = self._act(sid, docname, "No Such Action", header=name)
		self.assertEqual(body["message"]["status"], "error", body)
		rows = self.logs(ref_name=docname, event="action")
		self.assertEqual([r.result for r in rows], ["Failed"])

	def test_self_approval_blocked(self):
		name = self.grant()
		docname = self._temporary_advance(DEAN)
		sid = self.login(DEAN)
		self.switch(sid, name)
		status, body = self._act(sid, docname, "Approve", header=name)
		self.assertEqual(status, 403, body)
		self.assertEqual(
			frappe.db.get_value("Temporary Advance", docname, "workflow_state"),
			"Pending Associate Dean",
		)
		self.assertTrue(self.logs(ref_name=docname, event="denied"))

	def test_pending_tasks_follow_the_profile(self):
		if not frappe.db.exists("Module Registry", {"page_name": "pending-task"}):
			self.skipTest("No pending-task Module Registry on this site")
		name = self.grant()
		docname = self._temporary_advance("rd_test_applicant@example.com")
		sid = self.login(DEAN)
		path = "/api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_pending_task"

		def listed(header=None):
			status, body = self.call(sid, None, verb="GET", header=header, path=path)
			self.assertEqual(status, 200, body)
			return docname in json.dumps(body["message"])

		self.assertFalse(listed())
		self.switch(sid, name)
		self.assertTrue(listed(header=name))
		self.switch_back(sid, header=name)
		self.assertFalse(listed())

	def test_generic_workflow_endpoint_is_guarded_and_logged(self):
		name = self.grant()
		docname = self._temporary_advance("rd_test_applicant@example.com")
		sid = self.login(DEAN)
		self.switch(sid, name)

		def apply(action, header=None):
			doc = frappe.get_doc("Temporary Advance", docname)
			return self.call(
				sid, None, {"doc": doc.as_json(), "action": action}, header=header,
				path="/api/method/frappe.model.workflow.apply_workflow",
			)

		with patch("frappe.model.workflow.get_workflow", _workflow_without_field_updates):
			status, body = apply("Approve", header=name)
		self.assertEqual(status, 200, body)
		self.assertEqual(
			frappe.db.get_value("Temporary Advance", docname, "workflow_state"), "Approved"
		)
		rows = self.logs(ref_name=docname, event="action")
		self.assertEqual([(r.actual_user, r.result) for r in rows], [(DEAN, "Success")])

		# Back on the own profile, a further state change by the same person is refused.
		self.switch_back(sid, header=name)
		frappe.set_user(DEAN)
		with patch.object(frappe.local, "request", frappe._dict(method="POST"), create=True):
			doc = frappe.get_doc("Temporary Advance", docname)
			doc._doc_before_save = frappe.get_doc("Temporary Advance", docname)
			doc.workflow_state = "Pending Dean Approval"
			from rndopsapp.rndopsapp.role_delegation.context import check_workflow_change

			with self.assertRaises(frappe.PermissionError):
				check_workflow_change(doc)

	def test_feature_off_changes_nothing(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		with patch.object(service, "is_enabled", return_value=False):
			# A tab that still thinks it is acting is refused, not run as the Dean.
			status, body = self.call(sid, "get_role_delegations", header=name)
			self.assertEqual(body.get("exc_type"), "ProfileMismatch", body)
			self.assertIn("Dean, RnD", self.roles(sid))
			status, body = self.call(sid, "get_acting_profiles", verb="GET")
			self.assertEqual((body["message"]["enabled"], body["message"]["current"]), (False, "self"))
			status, _body = self.call(sid, "switch_profile", {"delegation": name})
			self.assertEqual(status, 403)
			self.switch_back(sid)

	def test_senior_role_can_go_to_any_listed_role_holder(self):
		from rndopsapp.rndopsapp.role_delegation.constants import DELEGABLE_ROLES

		for role in DELEGABLE_ROLES:
			self.assertTrue(frappe.db.exists("Role", role), role)
		row = frappe.db.get_value("Has Role", {"parent": OTHER, "role": "Dean, RnD"}, "name")
		frappe.db.set_value("Has Role", row, "role", "Permanent Employee")
		frappe.db.commit()
		frappe.clear_cache(user=OTHER)
		try:
			name = self.grant(delegate=OTHER)
			sid = self.login(OTHER)
			self.switch(sid, name)
			acting = self.roles(sid, header=name)
			self.assertIn("Ado_RnD", acting)
			self.assertNotIn("Permanent Employee", acting)
		finally:
			frappe.db.set_value("Has Role", row, "role", "Dean, RnD")
			frappe.db.commit()
			frappe.clear_cache(user=OTHER)

	def test_delegators_own_application_blocked(self):
		name = self.grant()
		docname = self._temporary_advance(ADO)
		sid = self.login(DEAN)
		self.switch(sid, name)
		status, body = self._act(sid, docname, "Approve", header=name)
		self.assertEqual(status, 403, body)
		self.assertIn("own application", json.dumps(body))

	def test_all_workflow_handlers_are_guarded(self):
		import glob
		import re

		app = frappe.get_app_path("rndopsapp")
		unguarded = []
		for path in glob.glob(f"{app}/rndopsapp/doctype/*/*.py"):
			if " copy" in path:
				continue
			with open(path) as handle:
				source = handle.read()
			for match in re.finditer(r"^def (perform_\w+_action)\(", source, re.M):
				above = source[: match.start()].rstrip().rsplit("\n", 1)[-1]
				if not above.startswith("@guarded_action"):
					unguarded.append(match[1])
		self.assertEqual(unguarded, [])

	def test_task_registry_follows_the_profile(self):
		name = self.grant()
		of_ado = self._temporary_advance("rd_test_applicant@example.com", state="Approved")
		of_dean = self._temporary_advance("rd_test_applicant@example.com", state="Approved")
		acted = self._temporary_advance("rd_test_applicant@example.com")
		for docname, user in ((of_ado, ADO), (of_dean, DEAN)):
			frappe.db.set_value("Temporary Advance", docname, "modified_by", user, update_modified=False)
		frappe.db.commit()
		sid = self.login(DEAN)
		path = "/api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_task_registry"

		def registry(header=None):
			status, body = self.call(sid, None, verb="GET", header=header, path=path)
			self.assertEqual(status, 200, body)
			self.assertTrue(body["message"]["success"], body)
			return {
				record["name"]
				for group in body["message"]["results"]
				for record in group["records"]
			}

		own = registry()
		self.assertIn(of_dean, own)
		self.assertNotIn(of_ado, own)

		self.switch(sid, name)
		status, body = self._act(sid, acted, "Approve", header=name)
		self.assertEqual(body["message"]["status"], "success", body)
		acting = registry(header=name)
		self.assertIn(of_ado, acting)  # the delegator's history
		self.assertIn(acted, acting)  # done under the delegation
		self.assertNotIn(of_dean, acting)  # not the delegate's own history

		self.switch_back(sid, header=name)
		self.assertIn(of_dean, registry())
		self.assertNotIn(of_ado, registry())

	def logged_user(self, sid, header=None):
		status, body = self.call(
			sid, None, verb="GET", header=header, path="/api/method/frappe.auth.get_logged_user"
		)
		self.assertEqual(status, 200, body)
		return body["message"]

	def session_owner(self, sid):
		frappe.db.rollback()
		return frappe.db.sql("select user, sessiondata from tabSessions where sid=%s", sid)[0]

	def test_requests_run_as_the_delegator_only_while_acting(self):
		name = self.grant()
		sid, other_session = self.login(DEAN), self.login(DEAN)
		self.switch(sid, name)
		for _ in range(3):  # the login session must keep belonging to the Dean
			self.assertEqual(self.logged_user(sid, header=name), ADO)
		self.call(sid, "get_user_roles", header=name)  # a POST, which saves the session
		self.assertEqual(self.session_owner(sid)[0], DEAN)
		self.assertNotIn(ADO, self.session_owner(sid)[1])
		self.assertEqual(self.logged_user(other_session), DEAN)

		status, body = self.call(sid, "get_acting_profiles", verb="GET")
		self.assertEqual(body["message"]["current"], name, body)
		self.switch_back(sid, header=name)
		self.assertEqual(self.logged_user(sid), DEAN)

		frappe.local.cache.pop(frappe.cache.make_key("roles"), None)
		self.assertNotIn("Ado_RnD", frappe.cache.hget("roles", DEAN) or [])

	def test_delegator_account_is_protected(self):
		name = self.grant()
		sid = self.login(DEAN)
		self.switch(sid, name)
		before = frappe.db.get_value("User", ADO, "first_name")
		for method, data in (
			("frappe.client.set_value",
				{"doctype": "User", "name": ADO, "fieldname": "first_name", "value": "Changed"}),
			("frappe.core.doctype.user.user.update_password",
				{"new_password": "x-Long-Password-123", "old_password": "x"}),
			("rndopsapp.auth_api.reset_user_password",
				{"email": ADO, "new_password": "abcdefgh", "confirm_password": "abcdefgh"}),
		):
			status, body = self.call(
				sid, None, data, header=name, path=f"/api/method/{method}"
			)
			self.assertEqual(status, 403, (method, body))
		self.assertEqual(frappe.db.get_value("User", ADO, "first_name"), before)
		self.assertTrue(self.logs(delegation=name, event="denied", actual_user=DEAN))

	def test_documents_written_while_acting_are_logged(self):
		name = self.grant()
		docname = self._temporary_advance("rd_test_applicant@example.com")
		sid = self.login(DEAN)
		self.switch(sid, name)
		self._act(sid, docname, "Approve", header=name)
		rows = self.logs(ref_name=docname, event="write")
		self.assertEqual(
			[(r.actual_user, r.delegator, r.result) for r in rows], [(DEAN, ADO, "Success")]
		)
