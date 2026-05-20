import frappe


DOCTYPE = "Indent Cum Sanction Sheet"
PO_GENERATED_STATE = "PO Generated"
PO_DELIVERED_STATE = "PO Delivered"


def _ensure_workflow_state(state_name, style="Success"):
	if not frappe.db.exists("Workflow State", state_name):
		frappe.get_doc({
			"doctype": "Workflow State",
			"workflow_state_name": state_name,
			"style": style,
		}).insert(ignore_permissions=True)


def execute():
	"""Add terminal PO Delivered workflow state support for ICSS."""
	_ensure_workflow_state(PO_GENERATED_STATE, style="Info")
	_ensure_workflow_state(PO_DELIVERED_STATE)

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": DOCTYPE, "is_active": 1},
		"name",
	)
	if not workflow_name:
		workflow_name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE}, "name")

	if not workflow_name:
		frappe.log_error(
			f"No workflow found for {DOCTYPE}; PO Delivered workflow patch skipped.",
			"ICSS PO Delivered Workflow Patch",
		)
		return

	workflow = frappe.get_doc("Workflow", workflow_name)

	if not any(row.state == PO_DELIVERED_STATE for row in workflow.get("states", [])):
		workflow.append("states", {
			"state": PO_DELIVERED_STATE,
			"doc_status": "1",
			"allow_edit": "System Manager",
			"send_email": 0,
		})

	workflow.save(ignore_permissions=True)
