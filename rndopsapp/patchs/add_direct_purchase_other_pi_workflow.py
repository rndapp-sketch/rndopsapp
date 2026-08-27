import frappe

WORKFLOW = "Direct_Purchase_Workflow"
STATE = "Pending Other PI"

# Where the Other PI's Forward hands the document on. Direct Purchase sends
# every applicant role to "Pending Staff Approval" after the funding decision,
# matching IGF and ICSS (Travel is the odd one out — it goes to the head).
NEXT_AFTER_PI = "Pending Staff Approval"


def execute():
	"""Wire the "Project of other PI" flow into Direct_Purchase_Workflow.

	When an applicant charges a direct purchase to a project owned by a
	*different* PI, the form must first be routed to that Other PI, who picks
	which of their own projects funds it and then Forwards it down the normal
	chain (or Puts it Back to the applicant).

	    Draft --Submit (dp_other_pi == "Other")--> Pending Other PI
	    Pending Other PI --Forward--> Pending Staff Approval
	    Pending Other PI --Put Back--> Draft

	The per-document guard that only the *assigned* Other PI (dp_other_pi_id)
	may act lives in direct_purchase.py::perform_direct_purchase_action; the
	"Permanent Employee" role here only makes the transition visible to PIs,
	exactly as the existing "Pending PI Approval" transitions do.

	Idempotent — safe to re-run.
	"""
	if not frappe.db.exists("Workflow", WORKFLOW):
		return

	for action in ("Submit", "Forward", "Put Back"):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc(
				{"doctype": "Workflow Action Master", "workflow_action_name": action}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("Workflow State", STATE):
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": STATE}
		).insert(ignore_permissions=True)

	workflow = frappe.get_doc("Workflow", WORKFLOW)

	# 1. State
	if not any(s.state == STATE for s in workflow.states):
		workflow.append(
			"states",
			{"state": STATE, "doc_status": "0", "allow_edit": "Permanent Employee"},
		)

	# 2. Guard the existing Draft -> Submit transitions so they only fire when
	#    the purchase is NOT charged to another PI. Without this, an "Other"
	#    submission matches both the normal and the other-PI transition.
	guard = 'doc.dp_other_pi != "Other"'
	for t in workflow.transitions:
		if t.state == "Draft" and t.action == "Submit" and t.next_state != STATE:
			cond = (t.condition or "").strip()
			if "dp_other_pi" not in cond:
				t.condition = f"({cond}) and ({guard})" if cond else guard

	# 3. Draft -> Submit -> Pending Other PI, for every role that can submit a
	#    Direct Purchase today.
	other_pi_cond = 'doc.dp_other_pi == "Other"'
	submitter_roles = sorted(
		{
			t.allowed
			for t in workflow.transitions
			if t.state == "Draft" and t.action == "Submit" and t.allowed
		}
	)
	for role in submitter_roles:
		if not any(
			t.state == "Draft"
			and t.action == "Submit"
			and t.next_state == STATE
			and t.allowed == role
			for t in workflow.transitions
		):
			workflow.append(
				"transitions",
				{
					"state": "Draft",
					"action": "Submit",
					"next_state": STATE,
					"allowed": role,
					"condition": other_pi_cond,
				},
			)

	# 4. Other PI acts: Forward down the normal chain, or Put Back to applicant.
	if not any(t.state == STATE and t.action == "Forward" for t in workflow.transitions):
		workflow.append(
			"transitions",
			{
				"state": STATE,
				"action": "Forward",
				"next_state": NEXT_AFTER_PI,
				"allowed": "Permanent Employee",
			},
		)

	if not any(t.state == STATE and t.action == "Put Back" for t in workflow.transitions):
		workflow.append(
			"transitions",
			{
				"state": STATE,
				"action": "Put Back",
				"next_state": "Draft",
				"allowed": "Permanent Employee",
			},
		)

	workflow.save(ignore_permissions=True)
	frappe.db.commit()
