# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Python port of the frontend's src/utils/projectTypeMapping.ts (DOCTYPE_PR_LINKS).

This is the single source of truth for how each DocType links back to
Project Registration. It exists so backend endpoints (get_categorized_pending_task,
get_categorized_task_registry in module_registry.py) can resolve each task
record's research/consultancy/others bucket server-side, instead of the
frontend bulk-fetching every Project Registration and resolving links
client-side. Keep this in sync with projectTypeMapping.ts by hand if either
side changes — there is no automated sync between the two repos.

Strategies (mirrors the TS PRLinkStrategy union):
    self          - the record itself IS a Project Registration
    pr_name       - the named field stores the PR document `name` (auto-id)
    pr_project_no - the named field stores the human-readable PR `project_no`
    direct_type   - the named field already contains the project_type value
                    (populated via Frappe fetch_from on save)
"""

SELF = "self"
PR_NAME = "pr_name"
PR_PROJECT_NO = "pr_project_no"
DIRECT_TYPE = "direct_type"

# doctype -> {"primary": (strategy, field), "fallback": (strategy, field) | None}
# `field` is None only for the "self" strategy.
DOCTYPE_PR_LINKS = {
	"Project Registration": {"primary": (SELF, None)},

	# Direct Link DocTypes (field stores PR `name`)
	"Account Head Payment": {"primary": (PR_NAME, "project_ref_number")},
	"Advance Settlement": {
		"primary": (PR_NAME, "project_name"),
		"fallback": (PR_PROJECT_NO, "project_code"),
	},
	"Deposit slip": {"primary": (PR_NAME, "project_title")},
	"Deposit Slip Project Credit": {"primary": (PR_NAME, "project_number")},
	"Disbursement of Honorarium": {"primary": (PR_NAME, "project_number")},
	"E Non Routine Deposit Slip": {"primary": (PR_NAME, "project_title")},
	"Fund Received": {"primary": (PR_NAME, "prjreg_title")},
	"Fund Sanction": {
		"primary": (DIRECT_TYPE, "project_type_linked"),
		"fallback": (PR_NAME, "project_proposal"),
	},
	"Indent Cum Sanction Sheet": {
		"primary": (PR_NAME, "project_ref"),
		"fallback": (PR_PROJECT_NO, "project_no"),
	},
	"Indent General Form": {
		"primary": (PR_NAME, "igf_project_title"),
		"fallback": (PR_PROJECT_NO, "igf_project_code"),
	},
	"Loan Request": {
		"primary": (PR_NAME, "project_name"),
		"fallback": (PR_PROJECT_NO, "project_number"),
	},
	"Miscellaneous Commit": {"primary": (PR_NAME, "project_number")},
	"myProjects": {"primary": (PR_NAME, "project_proposal")},
	"payments": {"primary": (PR_NAME, "project_id")},
	"Project Extension": {
		"primary": (PR_NAME, "project_ref"),
		"fallback": (PR_PROJECT_NO, "prj_num"),
	},
	"Project Staff Resignation": {"primary": (PR_PROJECT_NO, "applicant_prj_num")},
	"Project Staff Extension": {"primary": (PR_PROJECT_NO, "ex_proj_no")},
	"proprietary_purchase": {
		"primary": (PR_NAME, "project_ref"),
		"fallback": (PR_PROJECT_NO, "project_no"),
	},
	"Rate Contract": {"primary": (PR_NAME, "project_number")},
	"Reimbursement": {
		"primary": (PR_NAME, "project_name"),
		"fallback": (PR_PROJECT_NO, "project_number"),
	},
	"Research Consultancy Deposit Slip": {
		"primary": (PR_NAME, "project_title"),
		"fallback": (PR_PROJECT_NO, "project_number"),
	},
	"Research Deposit Slip": {
		"primary": (PR_NAME, "project_title"),
		"fallback": (PR_PROJECT_NO, "project_no"),
	},
	"standerdized_purchase": {
		"primary": (PR_NAME, "project_ref"),
		"fallback": (PR_PROJECT_NO, "project_no"),
	},
	"T Testing Deposit Slip": {"primary": (PR_NAME, "project_title")},
	"Travel": {
		"primary": (PR_NAME, "travel_project_title"),
		"fallback": (PR_PROJECT_NO, "travel_project_number"),
	},
	"UC Request": {"primary": (PR_NAME, "project_id")},

	# Indirect Data-field-only DocTypes (field stores PR `project_no`)
	"Direct Purchase": {"primary": (PR_PROJECT_NO, "project_no")},
	"Disbursal of Consultancy": {"primary": (PR_PROJECT_NO, "disbursal_project_number")},
	"Disbursal of Honorarium": {"primary": (PR_PROJECT_NO, "project_no")},
	"Endorsement Data": {"primary": (PR_PROJECT_NO, "project_no")},
	"Extension Of Tenure Of Appointment": {"primary": (PR_PROJECT_NO, "project_number")},
	"Leave Module": {"primary": (PR_PROJECT_NO, "project_no")},
	"P_11 Form": {"primary": (PR_PROJECT_NO, "project_no")},
	"Recruitment Adhoc Contractual": {"primary": (PR_PROJECT_NO, "upfa_project_code")},
	"Selection Committee Report": {"primary": (PR_PROJECT_NO, "project_number")},
	"repair_replacement": {"primary": (PR_PROJECT_NO, "project_no")},
	"sanction_sheet": {"primary": (PR_PROJECT_NO, "project_no")},
	"TA DA Settlement": {"primary": (PR_PROJECT_NO, "project_no")},
	"Temporary Advance": {"primary": (PR_PROJECT_NO, "project_code")},
	"Top Up Fellowship": {"primary": (PR_PROJECT_NO, "project_no")},
}

# Hardcoded to Consultancy regardless of any Project Registration link
# (mirrors the frontend's UI-level special case for these two doctypes,
# which never appear in DOCTYPE_PR_LINKS itself).
HARDCODED_CONSULTANCY_DOCTYPES = {"Proforma Invoice", "Disbursal of Consultancy"}

# Every doctype that carries a `fund_received_ref` field pointing back at a
# Fund Received's `fund_received_ref_number`, used to resolve the "Deposit:
# RES-DS-..." sub-line shown under Fund Received rows.
DEPOSIT_SLIP_DOCTYPES = [
	"Deposit slip",
	"D Consultancy Deposit Slip",
	"E Non Routine Deposit Slip",
	"Other Event Deposit Slip",
	"Research Consultancy Deposit Slip",
	"Research Deposit Slip",
	"T Testing Deposit Slip",
]


def normalize_project_type(raw):
	"""Case-insensitive substring match, same three buckets as the frontend."""
	t = (raw or "").lower()
	if "research" in t:
		return "research"
	if "consult" in t:
		return "consultancy"
	return "others"


def pr_link_fields(doctype):
	"""Every record fieldname DOCTYPE_PR_LINKS needs fetched for this doctype."""
	mapping = DOCTYPE_PR_LINKS.get(doctype)
	if not mapping:
		return []
	fields = []
	for strategy in (mapping.get("primary"), mapping.get("fallback")):
		if strategy and strategy[1] and strategy[1] not in fields:
			fields.append(strategy[1])
	return fields


def _apply_strategy(strategy, record, pr_name_to_type, pr_no_to_type):
	kind, field = strategy
	if kind == SELF:
		return pr_name_to_type.get(record.get("name"))
	if kind == DIRECT_TYPE:
		return record.get(field) or None
	if kind == PR_NAME:
		val = record.get(field)
		return pr_name_to_type.get(val) if val else None
	if kind == PR_PROJECT_NO:
		val = record.get(field)
		return pr_no_to_type.get(val) if val else None
	return None


def resolve_project_category(record, doctype, pr_name_to_type, pr_no_to_type):
	"""
	record: dict with at least "name" plus whatever pr_link_fields(doctype) named.
	pr_name_to_type / pr_no_to_type: PR `name`/`project_no` -> raw project_type string.
	"""
	if doctype in HARDCODED_CONSULTANCY_DOCTYPES:
		return "consultancy"

	mapping = DOCTYPE_PR_LINKS.get(doctype)
	if not mapping:
		return "others"

	raw = _apply_strategy(mapping["primary"], record, pr_name_to_type, pr_no_to_type)
	if raw:
		return normalize_project_type(raw)

	fallback = mapping.get("fallback")
	if fallback:
		raw = _apply_strategy(fallback, record, pr_name_to_type, pr_no_to_type)
		if raw:
			return normalize_project_type(raw)

	return "others"


def resolve_project_no(record, doctype, pr_name_to_no):
	"""Best-effort linked Project Registration's project_no, for display."""
	if doctype == "Project Registration":
		return pr_name_to_no.get(record.get("name"))

	mapping = DOCTYPE_PR_LINKS.get(doctype)
	if not mapping:
		return None

	for strategy in (mapping.get("primary"), mapping.get("fallback")):
		if not strategy:
			continue
		kind, field = strategy
		if kind == PR_PROJECT_NO:
			val = record.get(field)
			if val:
				return val
		elif kind == PR_NAME:
			val = record.get(field)
			if val and pr_name_to_no.get(val):
				return pr_name_to_no[val]

	return None
