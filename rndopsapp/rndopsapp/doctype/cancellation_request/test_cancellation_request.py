# Copyright (c) 2026, rndops and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from rndopsapp.rndopsapp.cancellation_workflow import (
	WORKFLOW_NAME,
	ensure_cancellation_workflow,
	resolve_cancellation_path,
	stage_for_application_state,
)


class TestCancellationRoute(FrappeTestCase):
	def route(self, doctype, state):
		stop, path = resolve_cancellation_path(doctype, state)
		return stop, path

	def test_pending_chain_stages_end_at_themselves(self):
		self.assertEqual(self.route("Reimbursement", "Pending Staff Approval"), ("Staff", ["Staff"]))
		self.assertEqual(self.route("Direct Purchase", "Pending HoS Approval"), ("HoS", ["Staff", "HoS"]))
		self.assertEqual(
			self.route("Direct Purchase", "Pending Dean Approval"), ("Dean", ["Staff", "HoS", "Dean"])
		)

	def test_approved_and_later_states_run_the_full_chain(self):
		full = ("Dean", ["Staff", "HoS", "Dean"])
		for state in ("Approved", "Sanction Approved", "Pending PO Generation", "Pending Staff Verification"):
			self.assertEqual(self.route("Direct Purchase", state), full, state)

	def test_head_stage_only_for_head_doctypes(self):
		self.assertEqual(
			self.route("Top Up Fellowship", "Approved"), ("Dean", ["Head", "Staff", "HoS", "Dean"])
		)
		self.assertEqual(
			self.route("Recruitment Adhoc Contractual", "Pending HoS Approval"),
			("HoS", ["Head", "Staff", "HoS"]),
		)
		self.assertEqual(self.route("Reimbursement", "Approved"), ("Dean", ["Staff", "HoS", "Dean"]))
		self.assertEqual(self.route("Travel", "Approved"), ("Dean", ["Head", "Staff", "HoS", "Dean"]))
		self.assertEqual(self.route("Travel", "Pending HoS Approval"), ("HoS", ["Head", "Staff", "HoS"]))

	def test_applicant_side_stages_are_single_stage(self):
		# No PI stage: an application waiting on its PI goes straight to Staff.
		self.assertEqual(self.route("Reimbursement", "Pending PI Approval"), ("Staff", ["Staff"]))
		self.assertEqual(
			self.route("Top Up Fellowship", "Pending PI Approval"), ("Staff", ["Head", "Staff"])
		)
		self.assertEqual(self.route("Reimbursement", "Pending Mentor Approval"), ("Mentor", ["Mentor"]))
		self.assertEqual(self.route("Travel", "Pending Other PI"), ("Other PI", ["Other PI"]))
		self.assertEqual(self.route("Travel", "Pending Head Approval"), ("Head", ["Head"]))

	def test_not_cancellable_states(self):
		for state in ("Draft", "", None, "Rejected", "Cancelled", "Needs Correction (PE)"):
			self.assertIsNone(stage_for_application_state(state), state)
			with self.assertRaises(frappe.ValidationError):
				resolve_cancellation_path("Reimbursement", state)


class TestCancellationWorkflow(FrappeTestCase):
	def test_workflow_is_created_and_active(self):
		ensure_cancellation_workflow()
		wf = frappe.get_doc("Workflow", WORKFLOW_NAME)
		self.assertEqual(wf.document_type, "Cancellation Request")
		self.assertTrue(wf.is_active)

	def test_each_route_reaches_approved_at_its_stop_stage(self):
		from frappe.model.workflow import is_transition_condition_satisfied

		ensure_cancellation_workflow()
		wf = frappe.get_doc("Workflow", WORKFLOW_NAME)

		def walk(doctype, state):
			from rndopsapp.rndopsapp.cancellation_workflow import encode_path

			stop, path = resolve_cancellation_path(doctype, state)
			doc = frappe._dict(stop_stage=stop, stage_path=encode_path(path))
			doc.as_dict = lambda d=doc: d
			current, visited = "Draft", []
			for _ in range(10):
				nxt = {
					t.next_state
					for t in wf.transitions
					if t.state == current
					and t.action in ("Submit", "Approve")
					and is_transition_condition_satisfied(t, doc)
				}
				self.assertEqual(len(nxt), 1, f"{current}: {nxt}")
				current = nxt.pop()
				visited.append(current)
				if current == "Approved":
					return visited
			self.fail("did not reach Approved")

		self.assertEqual(
			walk("Reimbursement", "Approved"),
			["Pending Staff Approval", "Pending HoS Approval", "Pending Dean Approval", "Approved"],
		)
		self.assertEqual(
			walk("Reimbursement", "Pending HoS Approval"),
			["Pending Staff Approval", "Pending HoS Approval", "Approved"],
		)
		self.assertEqual(
			walk("Top Up Fellowship", "Pending Staff Approval"),
			["Pending Head Approval", "Pending Staff Approval", "Approved"],
		)
		self.assertEqual(walk("Travel", "Pending PI Approval"), ["Pending Head Approval", "Pending Staff Approval", "Approved"])
		self.assertEqual(walk("Travel", "Pending Other PI"), ["Pending Other PI", "Approved"])
