"""Allow-lists for role delegation."""

# Roles that may be handed over. Never add System Manager or another admin role.
DELEGABLE_ROLES = (
	"Dean, RnD",
	"Ado_RnD",
	"Hos, RnD (Head of Section, RnD)",
	"head_approver_1",
	"Permanent Employee",
)

# Only a holder of at least one of these may receive a delegation.
DELEGATE_ROLES = DELEGABLE_ROLES

# Roles kept alongside the delegated ones while acting.
ACTING_BASE_ROLES = ("All_ProRnd_User", "Desk User", "All", "Guest")

SESSION_KEY = "acting_delegation"
HEADER = "X-Acting-Delegation"
SELF_PROFILE = "self"

_API = "rndopsapp.rndopsapp.api."

# Requests that never check or apply the current profile, so a user can always
# see, change or leave it. Matched on the exact method name.
EXEMPT_METHODS = frozenset(
	{
		_API + "get_acting_profiles",
		_API + "switch_profile",
		_API + "switch_to_own_profile",
		"login",
		"logout",
	}
)

# Account operations a delegate may never run on the delegator's behalf.
BLOCKED_METHODS = frozenset(
	{
		"frappe.core.doctype.user.user.update_password",
		"frappe.core.doctype.user.user.reset_password",
		"frappe.core.doctype.user.user.generate_keys",
		"rndopsapp.auth_api.set_password",
		"rndopsapp.auth_api.reset_user_password",
		"rndopsapp.auth_api.save_registration_section",
		"rndopsapp.rndopsapp.user_api.user_api.save_user_data",
	}
)

# Documents that cannot be created, changed or deleted while acting. The two
# involved users' own User records are protected as well.
PROTECTED_DOCTYPES = ("Role Delegation", "User Delegation")

# Framework bookkeeping left out of the per-document write log.
UNLOGGED_DOCTYPES = frozenset(
	{
		"Role Delegation Log", "Comment", "Version", "Activity Log", "Error Log",
		"Access Log", "Route History", "DocShare", "ToDo", "Notification Log",
		"Email Queue", "Email Queue Recipient", "Communication", "Scheduled Job Log",
	}
)

# Applicant fields checked in addition to the document owner (self-approval block).
APPLICANT_FIELDS = {
	"Acc Head to Head Fund Transfer": ("h2h_app_webmail",),
	"Disbursal of Consultancy": ("webmail_id",),
	"Disbursal of Honorarium": ("webmail_id",),
	"Indent Cum Sanction Sheet": ("icss_applicant_webmail_id",),
	"Indent General Form": ("igf_webmail_id",),
	"Leave Module": ("email",),
	"Loan Request": ("applicant_webmail",),
	"Miscellaneous Commit": ("applicant_webmail",),
	"Project Proposal": ("pi_webmail",),
	"Project Registration": ("pi_webmail",),
	"Project Staff Details": ("ps_email_id",),
	"Project Staff Resignation": ("applicant_email_id",),
	"Reimbursement": ("applicant_webmail",),
	"TA DA Settlement": ("webmail_id",),
	"Temporary Advance": ("applicant_webmail",),
	"Travel": ("applicant_name_travel", "webmail_id_travel", "traveler_webmail_id"),
}

# Actions that send a document backwards. They start a new approval cycle.
BACKWARD_ACTION_PREFIXES = ("put back", "reject", "return", "send back")
