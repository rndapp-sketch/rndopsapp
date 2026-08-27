import frappe


def execute():
	"""Create the Loan Settlement workflow (see docs/loan-settlement-implementation.md).

	Pending Staff Processing --Process--> Processed   (staff, RnD)
	Pending Staff Processing --Reject---> Rejected    (staff, RnD)

	Publishing to the Accounts service happens on the Process transition, in
	perform_loan_settlement_action — a Rejected settlement is never published.
	"""
	if not frappe.db.exists("DocType", "Loan Settlement"):
		return

	if frappe.db.exists("Workflow", {"document_type": "Loan Settlement"}):
		return

	# Workflow Transition.action is a Link to Workflow Action Master.
	for action_name in ("Process", "Reject"):
		if not frappe.db.exists("Workflow Action Master", action_name):
			frappe.get_doc({
				"doctype": "Workflow Action Master",
				"workflow_action_name": action_name,
			}).insert(ignore_permissions=True)

	# Workflow Document State.state is a Link to Workflow State.
	for state_name in ("Pending Staff Processing", "Processed", "Rejected"):
		if not frappe.db.exists("Workflow State", state_name):
			frappe.get_doc({
				"doctype": "Workflow State",
				"workflow_state_name": state_name,
			}).insert(ignore_permissions=True)

	workflow = frappe.get_doc({
		"doctype": "Workflow",
		"workflow_name": "loan_settlement_workflow",
		"document_type": "Loan Settlement",
		"workflow_state_field": "workflow_state",
		"is_active": 1,
		"send_email_alert": 0,
		"states": [
			{
				"state": "Pending Staff Processing",
				"doc_status": "0",
				"allow_edit": "staff, RnD",
			},
			{
				"state": "Processed",
				"doc_status": "0",
				"allow_edit": "staff, RnD",
			},
			{
				"state": "Rejected",
				"doc_status": "0",
				"allow_edit": "staff, RnD",
			},
		],
		"transitions": [
			{
				"state": "Pending Staff Processing",
				"action": "Process",
				"next_state": "Processed",
				"allowed": "staff, RnD",
			},
			{
				"state": "Pending Staff Processing",
				"action": "Reject",
				"next_state": "Rejected",
				"allowed": "staff, RnD",
			},
		],
	})
	workflow.insert(ignore_permissions=True)
	frappe.db.commit()
