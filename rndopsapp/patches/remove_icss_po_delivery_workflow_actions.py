import frappe


DOCTYPE = "Indent Cum Sanction Sheet"
PO_GENERATED_STATE = "PO Generated"
PO_DELIVERED_STATE = "PO Delivered"
PO_DELIVERY_UPLOAD_ACTIONS = {"Upload Signed PO", "Deliver PO"}


def execute():
	"""
	Remove manual PO delivery workflow actions.

	The frontend upload button calls upload_icss_signed_po(), and that API moves
	ICSS to PO Delivered after the signed PO is saved. Keeping workflow actions
	here creates duplicate buttons in pending-task UI.
	"""
	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": DOCTYPE, "is_active": 1},
		"name",
	)
	if not workflow_name:
		workflow_name = frappe.db.get_value("Workflow", {"document_type": DOCTYPE}, "name")

	if not workflow_name:
		return

	workflow = frappe.get_doc("Workflow", workflow_name)
	original_transitions = list(workflow.get("transitions", []))
	workflow.set("transitions", [])

	for row in original_transitions:
		if (
			row.state == PO_GENERATED_STATE
			and row.next_state == PO_DELIVERED_STATE
			and row.action in PO_DELIVERY_UPLOAD_ACTIONS
		):
			continue
		row_data = row.as_dict()
		for key in ("name", "parent", "parentfield", "parenttype", "idx", "doctype"):
			row_data.pop(key, None)
		workflow.append("transitions", row_data)

	workflow.save(ignore_permissions=True)
