import frappe


def execute():
	wf_name = "Direct_Purchase_Workflow"
	if not frappe.db.exists("Workflow", wf_name):
		print(f"❌ Workflow {wf_name} not found.")
		return

	doc = frappe.get_doc("Workflow", wf_name)

	# 1. Ensure 'Pending Other PI' state exists
	if not frappe.db.exists("Workflow State", "Pending Other PI"):
		ws = frappe.new_doc("Workflow State")
		ws.workflow_state_name = "Pending Other PI"
		ws.insert(ignore_permissions=True)

	if not any(s.state == "Pending Other PI" for s in doc.states):
		doc.append("states", {
			"state": "Pending Other PI",
			"doc_status": 0,
			"allow_edit": "Permanent Employee",
		})

	# 2. Gate the existing Draft -> Submit transitions to only fire when
	# dp_other_pi is not "Other" (each keeps its existing role/next_state).
	for t in doc.transitions:
		if t.state == "Draft" and t.action == "Submit" and t.next_state != "Pending Other PI":
			t.condition = 'doc.dp_other_pi != "Other"'

	# 3. Add new Draft -> Pending Other PI transitions (one per role that can submit),
	# mirroring the existing Draft -> Submit transitions but for dp_other_pi == "Other".
	other_pi_roles = ["Independent Researcher", "Inspired Faculty", "Permanent Employee", "project staff"]
	existing_other_pi = {
		t.allowed for t in doc.transitions
		if t.state == "Draft" and t.action == "Submit" and t.next_state == "Pending Other PI"
	}
	for role in other_pi_roles:
		if role in existing_other_pi:
			continue
		doc.append("transitions", {
			"state": "Draft",
			"action": "Submit",
			"next_state": "Pending Other PI",
			"allowed": role,
			"condition": 'doc.dp_other_pi == "Other"',
		})

	# 4. Pending Other PI -> Pending Staff Approval (Forward) and -> Draft (Put Back)
	if not any(
		t.state == "Pending Other PI" and t.action == "Forward" and t.next_state == "Pending Staff Approval"
		for t in doc.transitions
	):
		doc.append("transitions", {
			"state": "Pending Other PI",
			"action": "Forward",
			"next_state": "Pending Staff Approval",
			"allowed": "Permanent Employee",
		})

	if not any(
		t.state == "Pending Other PI" and t.action == "Put Back" and t.next_state == "Draft"
		for t in doc.transitions
	):
		doc.append("transitions", {
			"state": "Pending Other PI",
			"action": "Put Back",
			"next_state": "Draft",
			"allowed": "Permanent Employee",
		})

	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print("✅ Direct_Purchase_Workflow patched with 'Pending Other PI' state and transitions.")
