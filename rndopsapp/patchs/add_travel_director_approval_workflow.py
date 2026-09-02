import frappe


def execute():
	"""Add the Director-approval branch to Travel_Workflow for International
	travel (see docs/travel-director-approval-implementation.md in prornd-ui).

	Pending Dean Approval --Send for Director Approval--> Pending Director Approval
	    (Dean, RnD; only when doc.nature_of_travel == "International")
	Pending Dean Approval --Approve--> Approved
	    (existing transition; gated to non-International only)
	Pending Director Approval --Approve--> Approved
	    (Dean, RnD; only once doc.director_signed_pdf is set)
	Pending Director Approval --Reject--> Rejected
	    (Dean, RnD)
	"""
	if not frappe.db.exists("Workflow", "Travel_Workflow"):
		return

	# Workflow Transition.action is a Link to Workflow Action Master — this
	# action name doesn't exist in the fixture list yet, so create it first.
	if not frappe.db.exists("Workflow Action Master", "Send for Director Approval"):
		frappe.get_doc(
			{
				"doctype": "Workflow Action Master",
				"workflow_action_name": "Send for Director Approval",
			}
		).insert(ignore_permissions=True)

	workflow = frappe.get_doc("Workflow", "Travel_Workflow")

	if not any(s.state == "Pending Director Approval" for s in workflow.states):
		workflow.append(
			"states",
			{
				"state": "Pending Director Approval",
				"doc_status": "0",
				"allow_edit": "Dean, RnD",
			},
		)

	for t in workflow.transitions:
		if (
			t.state == "Pending Dean Approval"
			and t.action == "Approve"
			and t.next_state == "Approved"
			and not t.condition
		):
			t.condition = "doc.nature_of_travel != 'International'"

	if not any(
		t.state == "Pending Dean Approval" and t.action == "Send for Director Approval"
		for t in workflow.transitions
	):
		workflow.append(
			"transitions",
			{
				"state": "Pending Dean Approval",
				"action": "Send for Director Approval",
				"next_state": "Pending Director Approval",
				"allowed": "Dean, RnD",
				"condition": "doc.nature_of_travel == 'International'",
			},
		)

	if not any(
		t.state == "Pending Director Approval" and t.action == "Approve"
		for t in workflow.transitions
	):
		workflow.append(
			"transitions",
			{
				"state": "Pending Director Approval",
				"action": "Approve",
				"next_state": "Approved",
				"allowed": "Dean, RnD",
				"condition": "doc.director_signed_pdf",
			},
		)

	if not any(
		t.state == "Pending Director Approval" and t.action == "Reject"
		for t in workflow.transitions
	):
		workflow.append(
			"transitions",
			{
				"state": "Pending Director Approval",
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": "Dean, RnD",
			},
		)

	workflow.save(ignore_permissions=True)
	frappe.db.commit()
