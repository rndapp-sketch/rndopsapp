"""
Create (or recreate) the Frappe Workflow for 'Indent Cum Sanction Sheet'.

Run via:
    bench --site <site> execute rndopsapp.rndopsapp.create_icss_workflow.execute

Matches the production handoff spec in ICSS_WORKFLOW_PRODUCTION_HANDOFF.md.

State/transition design (15 states, 30 transitions):

  Submit routing (Draft → 5 targets, backend picks via _resolve_initial_submit_next_state):
    - Permanent Employee / head_approver_1 / HoD / System Manager → Pending Staff Approval
    - Any other valid initiator → Pending PI Approval
    All 5 Draft→Submit rows are required so role validation passes before the backend override.

  HoS routing (2 Forward targets, backend picks via _resolve_hos_next_state):
    - amount > 1,00,000 → Pending Dean Approval
    - amount <= 1,00,000 → Pending Associate Dean
    Both rows are required.

  Director gate: enforced in perform_icss_action (send_to_director / director_signed_pdf),
    not as a workflow condition.

  PO Delivered: set by upload_icss_signed_po API — no manual transition row needed.

  Put-back transitions: explicit rows in the transition table (per production spec §9).
"""

import frappe

WORKFLOW_NAME = "indent_cum_sanction_sheet_workflow"
DOCTYPE = "Indent Cum Sanction Sheet"

# ---------------------------------------------------------------------------
# State definitions  (state_name, doc_status_str, allow_edit_role)
# ---------------------------------------------------------------------------
# 15 states per production handoff §3
ICSS_STATES = [
    ("Draft",                    "0", "All_ProRnd_User"),
    ("Pending PI Approval",      "1", "Permanent Employee"),
    ("Pending Mentor Approval",  "1", "Mentor"),
    ("Pending Other PI",         "1", "Other PI"),
    ("Pending Head Approval",    "1", "head_approver_1"),
    ("Pending Staff Approval",   "1", "staff, RnD"),
    ("Pending HoS Approval",     "1", "Hos, RnD (Head of Section, RnD)"),
    ("Pending Associate Dean",   "1", "Ado_RnD"),
    ("Approved",                 "1", "Administrator"),
    ("Pending Dean Approval",    "1", "Dean, RnD"),
    ("Pending PO Generation",    "1", "staff, RnD"),
    ("PO Generated",             "1", "staff, RnD"),
    ("PO Delivered",             "1", "Administrator"),
    ("Rejected",                 "2", "Administrator"),
    ("Put Back",                 "1", "All_ProRnd_User"),
]

# ---------------------------------------------------------------------------
# Transition definitions  (from_state, action, next_state, allowed_role)
# ---------------------------------------------------------------------------
# 30 transitions per production handoff §4
ICSS_TRANSITIONS = [
    # ── Draft → Submit (5 rows; backend _resolve_initial_submit_next_state routes) ──
    ("Draft", "Submit", "Pending PI Approval",     "All_ProRnd_User"),
    ("Draft", "Submit", "Pending Mentor Approval", "All_ProRnd_User"),
    ("Draft", "Submit", "Pending Other PI",        "All_ProRnd_User"),
    ("Draft", "Submit", "Pending Head Approval",   "All_ProRnd_User"),
    ("Draft", "Submit", "Pending Staff Approval",  "All_ProRnd_User"),

    # ── Pending PI Approval ───────────────────────────────────────────────────
    ("Pending PI Approval", "Forward", "Pending Other PI",       "Permanent Employee"),
    ("Pending PI Approval", "Forward", "Pending Staff Approval", "Permanent Employee"),
    ("Pending PI Approval", "Reject",  "Rejected",               "Permanent Employee"),

    # ── Pending Mentor Approval ───────────────────────────────────────────────
    ("Pending Mentor Approval", "Forward", "Pending Head Approval",   "Mentor"),
    ("Pending Mentor Approval", "Forward", "Pending Staff Approval",  "Mentor"),
    ("Pending Mentor Approval", "Reject",  "Rejected",                "Mentor"),

    # ── Pending Other PI ─────────────────────────────────────────────────────
    ("Pending Other PI", "Forward", "Pending Head Approval",   "Other PI"),
    ("Pending Other PI", "Forward", "Pending Staff Approval",  "Other PI"),
    ("Pending Other PI", "Reject",  "Rejected",                "Other PI"),

    # ── Pending Head Approval ─────────────────────────────────────────────────
    ("Pending Head Approval", "Forward", "Pending Staff Approval", "head_approver_1"),
    ("Pending Head Approval", "Reject",  "Rejected",               "head_approver_1"),

    # ── Pending Staff Approval ────────────────────────────────────────────────
    ("Pending Staff Approval", "Forward", "Pending HoS Approval", "staff, RnD"),
    ("Pending Staff Approval", "Reject",  "Rejected",              "staff, RnD"),

    # ── Pending HoS Approval (2 Forward rows; backend _resolve_hos_next_state) ─
    ("Pending HoS Approval", "Forward", "Pending Associate Dean",  "Hos, RnD (Head of Section, RnD)"),
    ("Pending HoS Approval", "Forward", "Pending Dean Approval",   "Hos, RnD (Head of Section, RnD)"),
    ("Pending HoS Approval", "Reject",  "Rejected",                "Hos, RnD (Head of Section, RnD)"),

    # ── Pending Associate Dean ────────────────────────────────────────────────
    ("Pending Associate Dean", "Approve", "Pending PO Generation", "Ado_RnD"),
    ("Pending Associate Dean", "Reject",  "Rejected",              "Ado_RnD"),

    # ── Pending Dean Approval ─────────────────────────────────────────────────
    # Director-PDF gate enforced in perform_icss_action, not as a condition here.
    ("Pending Dean Approval", "Approve", "Pending PO Generation", "Dean, RnD"),
    ("Pending Dean Approval", "Reject",  "Rejected",              "Dean, RnD"),

    # ── Pending PO Generation ─────────────────────────────────────────────────
    ("Pending PO Generation", "Generate PO", "PO Generated", "staff, RnD"),

    # ── Put-back transitions (explicit rows per production spec §9) ───────────
    ("Pending Staff Approval",   "Put Back", "Pending PI Approval",    "staff, RnD"),
    ("Pending HoS Approval",     "Put Back", "Pending Staff Approval", "Hos, RnD (Head of Section, RnD)"),
    ("Pending Dean Approval",    "Put Back", "Pending HoS Approval",   "Dean, RnD"),
    ("Pending Associate Dean",   "Put Back", "Pending HoS Approval",   "Associate Dean, RND"),

    # PO Generated → PO Delivered is set by upload_icss_signed_po API only.
    # No manual workflow action row added here intentionally.
]


def _ensure_role(role_name):
    if not frappe.db.exists("Role", role_name):
        frappe.get_doc({"doctype": "Role", "role_name": role_name}).insert(
            ignore_permissions=True
        )


def _ensure_workflow_state(state_name):
    if not frappe.db.exists("Workflow State", state_name):
        frappe.get_doc(
            {"doctype": "Workflow State", "workflow_state_name": state_name}
        ).insert(ignore_permissions=True)


def _ensure_workflow_action(action_name):
    if not frappe.db.exists("Workflow Action Master", action_name):
        frappe.get_doc(
            {"doctype": "Workflow Action Master", "workflow_action_name": action_name}
        ).insert(ignore_permissions=True)


def _deactivate_existing_icss_workflows():
    existing = frappe.get_all(
        "Workflow",
        filters={"document_type": DOCTYPE, "is_active": 1},
        pluck="name",
    )
    for wf_name in existing:
        if wf_name != WORKFLOW_NAME:
            frappe.db.set_value("Workflow", wf_name, "is_active", 0)
            frappe.logger("icss_workflow").info(
                f"Deactivated old ICSS workflow: {wf_name}"
            )


def execute():
    """Create or fully replace the ICSS Workflow."""

    # Pre-create all dependent records
    all_roles = {row[3] for row in ICSS_TRANSITIONS} | {row[2] for row in ICSS_STATES}
    all_actions = {row[1] for row in ICSS_TRANSITIONS}
    all_state_names = {row[0] for row in ICSS_STATES}

    for role in sorted(all_roles):
        _ensure_role(role)
    for state in all_state_names:
        _ensure_workflow_state(state)
    for action in all_actions:
        _ensure_workflow_action(action)

    # Deactivate any other active ICSS workflows
    _deactivate_existing_icss_workflows()

    # Delete and recreate so we start from a clean slate
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        frappe.delete_doc("Workflow", WORKFLOW_NAME, ignore_permissions=True, force=True)

    wf = frappe.new_doc("Workflow")
    wf.workflow_name = WORKFLOW_NAME
    wf.document_type = DOCTYPE
    wf.is_active = 1
    wf.send_email_alert = 0
    wf.workflow_state_field = "workflow_state"

    for state_name, doc_status, allow_edit in ICSS_STATES:
        wf.append("states", {
            "state": state_name,
            "doc_status": doc_status,
            "allow_edit": allow_edit,
            "update_field": "workflow_state",
            "update_value": state_name,
        })

    for from_state, action, next_state, allowed in ICSS_TRANSITIONS:
        wf.append("transitions", {
            "state": from_state,
            "action": action,
            "next_state": next_state,
            "allowed": allowed,
            "condition": "",
        })

    wf.insert(ignore_permissions=True)
    frappe.db.commit()

    print(
        f"✅ '{WORKFLOW_NAME}' created for '{DOCTYPE}' with "
        f"{len(ICSS_STATES)} states and {len(ICSS_TRANSITIONS)} transitions."
    )
