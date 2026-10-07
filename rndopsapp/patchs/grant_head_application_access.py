# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Let a department head raise applications, so a DPF fund can actually be spent.

A DPF project is owned by the department head (`Department_prornd.dept_head`, role
`head_approver_1`). A PDF project is owned by a PI, who is a `Permanent Employee` — and
`Permanent Employee` is the role every application doctype and workflow was built around.
So PDF got the whole application suite for free and DPF got none of it: the head could
open the fund, see the balance and create a draft, but the draft never appeared in a list
and Submit failed silently.

Two independent gates had to be opened, which is why the symptom looked odd — a draft that
saved but neither listed nor submitted:

  1. **DocPerm.** Reimbursement, Indent General Form and Disbursal of Consultancy never
     granted the general applicant role, so the head had no read/create/submit at all.
     (The other doctypes already grant `All_ProRnd_User`, which a head holds.)
  2. **Workflow transitions.** The initial `Submit` transition is gated on
     `allowed = "Permanent Employee"`. A head matches no allowed role, so the transition
     was skipped and `submit_*` returned an empty error. This one blocks 11 doctypes,
     including several whose DocPerm was already fine — which is why fixing permissions
     alone would not have been enough.

`head_approver_1` is granted rather than `All_ProRnd_User`: it is exactly the 47 department
heads, whereas `All_ProRnd_User` would hand create/submit rights to 589 additional users
who have no business raising these forms.

**Loan Request is deliberately excluded.** Loans are not possible against an overhead fund
— the frontend already drops the Loan group for PDF and DPF projects — so granting it
would contradict the design. See docs/dpf-project-implementation.md §7.

Idempotent: re-running adds nothing that is already there.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

HEAD_ROLE = "head_approver_1"
APPLICANT_ROLE = "Permanent Employee"

# Every application an overhead fund can be spent through. Loan Request is absent by
# design (see the module docstring).
APPLICATION_DOCTYPES = [
	"Reimbursement",
	"Travel",
	"Temporary Advance",
	"Advance Settlement",
	"TA DA Settlement",
	"Direct Purchase",
	"Indent General Form",
	"Indent Cum Sanction Sheet",
	"Recruitment Adhoc Contractual",
	"Top Up Fellowship",
	"Disbursal of Honorarium",
	"Disbursal of Consultancy",
	"Miscellaneous Commit",
]

PERM_TYPES = ("read", "write", "create", "submit")


def _grant_docperm(doctype):
	"""Give the head role the same r/w/c/s the applicant role already has."""
	if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": HEAD_ROLE}) or \
			frappe.db.exists("DocPerm", {"parent": doctype, "role": HEAD_ROLE}):
		return False

	add_permission(doctype, HEAD_ROLE, 0)
	for ptype in PERM_TYPES:
		update_permission_property(doctype, HEAD_ROLE, 0, ptype, 1)
	return True


def _grant_workflow_transitions(doctype):
	"""
	Mirror the applicant's initial Submit transition for the head role.

	The applicant transition is cloned field-for-field with only `allowed` changed, so any
	condition or self-approval setting on it carries over untouched rather than being
	guessed at.
	"""
	workflow_name = frappe.db.get_value("Workflow", {"document_type": doctype}, "name")
	if not workflow_name:
		return 0

	workflow = frappe.get_doc("Workflow", workflow_name)
	initial_state = workflow.states[0].state if workflow.states else "Draft"

	existing = {(t.state, t.action, t.next_state, t.allowed) for t in workflow.transitions}
	to_add = []
	for t in workflow.transitions:
		if t.state not in (initial_state, "Draft"):
			continue
		if t.allowed != APPLICANT_ROLE:
			continue
		if (t.state, t.action, t.next_state, HEAD_ROLE) in existing:
			continue
		to_add.append(t)

	for t in to_add:
		row = t.as_dict()
		for key in ("name", "owner", "creation", "modified", "modified_by", "idx",
		            "parent", "parenttype", "parentfield", "docstatus"):
			row.pop(key, None)
		row["allowed"] = HEAD_ROLE
		workflow.append("transitions", row)

	if to_add:
		workflow.flags.ignore_permissions = True
		workflow.save(ignore_permissions=True)
	return len(to_add)


def execute():
	granted_perms, added_transitions = [], []

	for doctype in APPLICATION_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		try:
			if _grant_docperm(doctype):
				granted_perms.append(doctype)
			n = _grant_workflow_transitions(doctype)
			if n:
				added_transitions.append(f"{doctype}({n})")
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Head Application Access - {doctype}")

	frappe.db.commit()
	frappe.clear_cache()

	print(f"Head application access: DocPerm granted on {len(granted_perms)} doctype(s): {granted_perms}")
	print(f"Head application access: workflow transitions added: {added_transitions}")
