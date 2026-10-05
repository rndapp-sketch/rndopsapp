import frappe


def execute():
	"""Wire the "Project of other PI" flow into Travel_Workflow.

	Per the ProMAn Travel & Faculty Leave module documentation, when an
	applicant charges the travel to a project owned by a *different* PI, the
	form must first be routed to that Other PI, who selects which of their own
	projects/account head funds the travel and then Forwards it down the normal
	chain (or Puts it Back to the applicant).

	The Travel doctype fields (travel_other_pi / travel_other_pi_id) and the
	controller logic in travel.py already handle this — but the workflow was
	never given the "Pending Other PI" state or its transitions, so a
	submission with travel_other_pi == "Other" errored with "Submit action is
	not available". This patch adds them (idempotently).

	    Draft --Submit (travel_other_pi == "Other")--> Pending Other PI
	    Pending Other PI --Forward--> Pending Head Approval
	    Pending Other PI --Put Back--> Draft

	The per-document guard that only the *assigned* Other PI (travel_other_pi_id)
	may act lives in travel.py::perform_travel_action; the "Permanent Employee"
	role here just makes the transition visible to PIs (who are permanent
	employees), exactly as the existing "Pending PI Approval" transitions do.
	"""
	if not frappe.db.exists("Workflow", "Travel_Workflow"):
		return

	# Actions used below already exist as fixtures (Submit/Forward/Put Back),
	# but create defensively so the patch is safe on a fresh site.
	for action in ("Submit", "Forward", "Put Back"):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("Workflow State", "Pending Other PI"):
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": "Pending Other PI"}
		).insert(ignore_permissions=True)

	workflow = frappe.get_doc("Workflow", "Travel_Workflow")

	# 1. State
	if not any(s.state == "Pending Other PI" for s in workflow.states):
		workflow.append(
			"states",
			{
				"state": "Pending Other PI",
				"doc_status": "0",
				"allow_edit": "Permanent Employee",
			},
		)

	# 2. Guard the existing Draft -> Submit transitions so they only fire when
	#    the travel is NOT charged to another PI. Without this, an "Other"
	#    submission would match both the normal and the other-PI transition.
	guard = 'doc.travel_other_pi != "Other"'
	for t in workflow.transitions:
		if (
			t.state == "Draft"
			and t.action == "Submit"
			and t.next_state != "Pending Other PI"
		):
			cond = (t.condition or "").strip()
			if "travel_other_pi" not in cond:
				t.condition = f"({cond}) and ({guard})" if cond else guard

	# 3. Draft -> Submit -> Pending Other PI for each applicant role that the
	#    documentation supports the "Project of other PI" flow for.
	other_pi_cond = 'doc.travel_other_pi == "Other"'
	for role in ("Permanent Employee", "Independent Researcher", "Inspire Faculty"):
		if not any(
			t.state == "Draft"
			and t.action == "Submit"
			and t.next_state == "Pending Other PI"
			and t.allowed == role
			for t in workflow.transitions
		):
			workflow.append(
				"transitions",
				{
					"state": "Draft",
					"action": "Submit",
					"next_state": "Pending Other PI",
					"allowed": role,
					"condition": other_pi_cond,
				},
			)

	# 4. Other PI acts: Forward down the normal chain, or Put Back to applicant.
	if not any(
		t.state == "Pending Other PI" and t.action == "Forward"
		for t in workflow.transitions
	):
		workflow.append(
			"transitions",
			{
				"state": "Pending Other PI",
				"action": "Forward",
				"next_state": "Pending Head Approval",
				"allowed": "Permanent Employee",
			},
		)

	if not any(
		t.state == "Pending Other PI" and t.action == "Put Back"
		for t in workflow.transitions
	):
		workflow.append(
			"transitions",
			{
				"state": "Pending Other PI",
				"action": "Put Back",
				"next_state": "Draft",
				"allowed": "Permanent Employee",
			},
		)

	workflow.save(ignore_permissions=True)
	frappe.db.commit()
