import frappe


CC_HEADS = '(doc.account_head in ("Consumable", "Contingency"))'
NON_CC_HEADS = '(doc.account_head not in ("Consumable", "Contingency"))'

CC_DEAN_LIMIT = 300000  # ₹3,00,000 — Dean approves alone for Consumable/Contingency


def execute():
	wf_name = "Direct Purchase Workflow"
	if not frappe.db.exists("Workflow", wf_name):
		wf_name = "Direct_Purchase_Workflow"
	if not frappe.db.exists("Workflow", wf_name):
		print("❌ Direct Purchase workflow not found.")
		return

	doc = frappe.get_doc("Workflow", wf_name)

	# Rebuild Dean Approve/Forward and Director Approve transitions.
	# Reject and unrelated transitions are preserved.
	kept = []
	for t in doc.transitions:
		if t.state == "Pending Dean Approval" and t.action in ("Approve", "Forward"):
			continue
		if t.state == "Pending Director Approval" and t.action == "Approve":
			continue
		kept.append(t)
	doc.set("transitions", kept)

	# --- Pending Dean Approval ---

	# Consumable/Contingency ≤ ₹3,00,000 → Approved
	doc.append("transitions", {
		"state": "Pending Dean Approval",
		"action": "Approve",
		"next_state": "Approved",
		"allowed": "Dean, RnD",
		"condition": f"{CC_HEADS} and flt(doc.total_estimate) <= {CC_DEAN_LIMIT}",
	})

	# Consumable/Contingency > ₹3,00,000 → Director
	doc.append("transitions", {
		"state": "Pending Dean Approval",
		"action": "Forward",
		"next_state": "Pending Director Approval",
		"allowed": "Dean, RnD",
		"condition": f"{CC_HEADS} and flt(doc.total_estimate) > {CC_DEAN_LIMIT}",
	})

	# All other budget heads → Dean approves directly (any amount)
	doc.append("transitions", {
		"state": "Pending Dean Approval",
		"action": "Approve",
		"next_state": "Approved",
		"allowed": "Dean, RnD",
		"condition": NON_CC_HEADS,
	})

	# --- Pending Director Approval ---

	# Only reachable for Consumable/Contingency > ₹3,00,000. No amount cap.
	doc.append("transitions", {
		"state": "Pending Director Approval",
		"action": "Approve",
		"next_state": "Approved",
		"allowed": "Director",
		"condition": CC_HEADS,
	})

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print("✅ Direct Purchase workflow patched: non-C/C goes Dean→Approved; C/C>3L goes Dean→Director→Approved.")
