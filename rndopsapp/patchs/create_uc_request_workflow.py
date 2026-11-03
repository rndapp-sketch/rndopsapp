import frappe

WORKFLOW_NAME = "uc_request_workflow"

PI = "Permanent Employee"
STAFF = "staff, RnD"
HOS = "Hos, RnD (Head of Section, RnD)"
DEAN = "Dean, RnD"

AUDITED = 'doc.uc_type == "Audited UC"'
NOT_AUDITED = 'doc.uc_type != "Audited UC"'

# (state, doc_status, allow_edit)
STATES = [
	("Draft", "0", PI),
	("Pending Staff Review", "0", STAFF),
	("Pending PI Verification", "0", PI),
	("Pending Staff Approval", "0", STAFF),
	("Pending HoS Approval", "0", HOS),
	# Offline: HoS prints and sends the UC to the Registrar; Staff uploads the
	# verified copy when it comes back, then HoS forwards it to the Dean.
	("Pending Registrar Verification", "0", HOS),
	("Pending Dean Approval", "0", DEAN),
	("Approved", "1", DEAN),
	("Rejected", "0", STAFF),
]

# (state, action, next_state, allowed, condition)
TRANSITIONS = [
	("Draft", "Submit", "Pending Staff Review", PI, None),
	("Pending Staff Review", "Forward to PI for Verification", "Pending PI Verification", STAFF, None),
	("Pending Staff Review", "Reject", "Rejected", STAFF, None),
	("Pending PI Verification", "Verify & Print", "Pending Staff Approval", PI, None),
	("Pending Staff Approval", "Forward", "Pending HoS Approval", STAFF, None),
	("Pending Staff Approval", "Reject", "Rejected", STAFF, None),
	("Pending HoS Approval", "Forward", "Pending Dean Approval", HOS, NOT_AUDITED),
	("Pending HoS Approval", "Print & Send to Registrar", "Pending Registrar Verification", HOS, AUDITED),
	("Pending HoS Approval", "Reject", "Rejected", HOS, None),
	# Gated in perform_uc_request_action on registrar_signed_uc being uploaded
	("Pending Registrar Verification", "Forward", "Pending Dean Approval", HOS, None),
	("Pending Registrar Verification", "Reject", "Rejected", HOS, None),
	("Pending Dean Approval", "Approve", "Approved", DEAN, None),
	("Pending Dean Approval", "Reject", "Rejected", DEAN, None),
]


def execute():
	"""Create the UC Request workflow:

	PI -> Staff -> PI (Verify & Print) -> Staff -> HoS -> Dean.
	Audited UC goes HoS -> Registrar (offline) -> HoS -> Dean.
	Put Back is handled by the generic put_back_action module.
	"""
	if not frappe.db.exists("DocType", "UC Request"):
		return

	for action in {t[1] for t in TRANSITIONS}:
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert(
				ignore_permissions=True
			)

	for state, _doc_status, _role in STATES:
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state}).insert(
				ignore_permissions=True
			)

	if frappe.db.exists("Workflow", WORKFLOW_NAME):
		frappe.delete_doc("Workflow", WORKFLOW_NAME, ignore_permissions=True)

	frappe.get_doc(
		{
			"doctype": "Workflow",
			"workflow_name": WORKFLOW_NAME,
			"document_type": "UC Request",
			"workflow_state_field": "workflow_state",
			"is_active": 1,
			"send_email_alert": 0,
			"override_status": 1,
			"states": [{"state": s, "doc_status": ds, "allow_edit": r} for s, ds, r in STATES],
			"transitions": [
				{
					"state": s,
					"action": a,
					"next_state": n,
					"allowed": r,
					"allow_self_approval": 1,
					"condition": c,
				}
				for s, a, n, r, c in TRANSITIONS
			],
		}
	).insert(ignore_permissions=True)

	_add_to_pending_task_registry()
	frappe.db.commit()


def _add_to_pending_task_registry():
	for page in ("pending-task",):
		if not frappe.db.exists("Module Registry", page):
			continue
		registry = frappe.get_doc("Module Registry", page)
		if any(row.doctype_name == "UC Request" for row in registry.doctype_name):
			continue
		registry.append("doctype_name", {"doctype_name": "UC Request", "mod_vis": 1})
		registry.save(ignore_permissions=True)
