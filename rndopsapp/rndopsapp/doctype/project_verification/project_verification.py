import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response as WerkzeugResponse

from rndopsapp.rndopsapp.doctype.project_registration.project_registration import (
	_PR_DIRECT_LINKS,
	_PR_INDIRECT_LINKS,
)

_ALLOWED_APPLICATION_DOCTYPES = {spec[0] for spec in _PR_DIRECT_LINKS + _PR_INDIRECT_LINKS}

_VALID_STATUSES = ("Pending", "Verified", "Needs Correction")

_SKIP_FIELDTYPES = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Button",
	"Table", "Table MultiSelect", "Fold", "Heading", "Password", "Signature",
	"Attach", "Attach Image", "Geolocation",
}


class ProjectVerification(Document):
	def validate(self):
		if self.application_doctype not in _ALLOWED_APPLICATION_DOCTYPES:
			frappe.throw(
				_("{0} is not a recognised application document type").format(self.application_doctype)
			)

		duplicate = frappe.db.exists(
			"Project Verification",
			{
				"project": self.project,
				"application_doctype": self.application_doctype,
				"application_name": self.application_name,
				"name": ["!=", self.name or ""],
			},
		)
		if duplicate:
			frappe.throw(
				_("A verification record already exists for this application: {0}").format(duplicate)
			)

		if self.verification_status == "Needs Correction" and not (self.remarks or "").strip():
			frappe.throw(_("Remarks are required when marking an application as Needs Correction"))


def _ensure_verification_access():
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	roles = frappe.get_roles(frappe.session.user)
	if "System Manager" not in roles and "Verification Staff" not in roles:
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _request_header(key):
	"""frappe.get_request_header() assumes a bound HTTP request; these whitelisted
	functions are only ever called from one, but guard anyway (e.g. console/testing)."""
	if not getattr(frappe.local, "request", None):
		return ""
	return frappe.get_request_header(key) or ""


def _client_ip():
	xff = _request_header("X-Forwarded-For")
	if xff:
		return xff.split(",", 1)[0].strip()
	return _request_header("REMOTE_ADDR") or getattr(frappe.local, "request_ip", "") or ""


def _resolve_project(project):
	if frappe.db.exists("Project Registration", project):
		return project
	name = frappe.db.get_value("Project Registration", {"project_no": project}, "name")
	if not name:
		frappe.throw(_("No Project Registration found for: {0}").format(project))
	return name


_BUDGET_BREAKUP_FIELDS = [
	"account_head", "total_proposal_of_heads", "first_year_budget", "second_year_budget",
	"third_year_budget", "fourth_year_budget", "fifth_year_budget", "sixth_year_budget",
	"is_total_row", "idx",
]


def _get_project_budget_breakup(pr_name):
	"""Sanctioned budget break-up rows for a project (falls back to the proposed
	break-up if nothing has been sanctioned yet). Both live in the same child
	doctype, "Project Sanctioned Budget", under different parentfields on
	Project Registration."""
	for parentfield in ("sanctioned_budget_breakup", "proposed_budget_breakup"):
		rows = frappe.get_all(
			"Project Sanctioned Budget",
			filters={"parent": pr_name, "parenttype": "Project Registration", "parentfield": parentfield},
			fields=_BUDGET_BREAKUP_FIELDS,
			order_by="idx asc",
		)
		if rows:
			return {"source": parentfield, "rows": rows}
	return {"source": None, "rows": []}


@frappe.whitelist()
def get_project_applications(project):
	"""List every application document filed against a project, merged with its
	current Project Verification status, for the verification portal's center panel."""
	_ensure_verification_access()
	if not project:
		frappe.throw(_("Project is required"))

	pr_name = _resolve_project(project)
	pr = frappe.db.get_value(
		"Project Registration", pr_name,
		["project_no", "project_title", "principal_investigator_name", "workflow_state",
		 "project_duration_months", "project_duration_days", "total_budget_amount",
		 "total_sanctioned_amount", "prj_start_date", "prj_end_date"],
		as_dict=True,
	)
	project_no = (pr.get("project_no") or "").strip()

	seen = set()
	applications = []

	def _collect(spec_list, filter_value):
		if not filter_value:
			return
		for (doctype, field, display, category) in spec_list:
			if not frappe.db.table_exists(doctype):
				continue
			try:
				docs = frappe.get_all(
					doctype,
					filters={field: filter_value},
					fields=["name", "workflow_state", "docstatus", "modified"],
					limit=200,
				)
			except Exception:
				continue
			for doc in docs:
				key = (doctype, doc["name"])
				if key in seen:
					continue
				seen.add(key)
				applications.append({
					"doctype": doctype,
					"name": doc["name"],
					"label": display,
					"category": category,
					"workflow_state": doc.get("workflow_state") or "",
					"docstatus": int(doc.get("docstatus") or 0),
					"modified": doc.get("modified"),
				})

	_collect(_PR_DIRECT_LINKS, pr_name)
	_collect(_PR_INDIRECT_LINKS, project_no)

	if applications:
		verif_rows = frappe.get_all(
			"Project Verification",
			filters={"project": pr_name},
			fields=["application_doctype", "application_name", "verification_status",
			        "remarks", "verified_by", "verified_on"],
		)
		verif_map = {(r.application_doctype, r.application_name): r for r in verif_rows}
		for app in applications:
			v = verif_map.get((app["doctype"], app["name"]))
			app["verification_status"] = v.verification_status if v else "Pending"
			app["remarks"] = v.remarks if v else ""
			app["verified_by"] = v.verified_by if v else None
			app["verified_on"] = v.verified_on if v else None

	total = len(applications)
	verified = sum(1 for a in applications if a["verification_status"] == "Verified")
	needs_correction = sum(1 for a in applications if a["verification_status"] == "Needs Correction")

	return {
		"status": "success",
		"project": {
			"name": pr_name,
			"project_no": project_no,
			"project_title": pr.get("project_title") or "",
			"pi_name": pr.get("principal_investigator_name") or "",
			"workflow_state": pr.get("workflow_state") or "",
			"duration_months": pr.get("project_duration_months"),
			"duration_days": pr.get("project_duration_days"),
			"total_budget_amount": pr.get("total_budget_amount"),
			"total_sanctioned_amount": pr.get("total_sanctioned_amount"),
			"start_date": pr.get("prj_start_date"),
			"completion_date": pr.get("prj_end_date"),
			"budget_breakup": _get_project_budget_breakup(pr_name),
		},
		"applications": applications,
		"summary": {
			"total": total,
			"verified": verified,
			"needs_correction": needs_correction,
			"pending": total - verified - needs_correction,
		},
	}


@frappe.whitelist()
def get_application_detail(application_doctype, application_name):
	"""Read-only field dump of a single application document, for the portal's
	'View Details' panel. Restricted to the known set of project-application doctypes."""
	_ensure_verification_access()

	if application_doctype not in _ALLOWED_APPLICATION_DOCTYPES:
		frappe.throw(
			_("{0} is not a recognised application document type").format(application_doctype),
			frappe.PermissionError,
		)
	if not frappe.db.exists(application_doctype, application_name):
		frappe.throw(_("{0} {1} not found").format(application_doctype, application_name))

	doc = frappe.get_doc(application_doctype, application_name)
	meta = frappe.get_meta(application_doctype)

	fields = []
	tables = []
	for df in meta.fields:
		if df.fieldtype in ("Table", "Table MultiSelect"):
			table = _get_child_table_detail(doc, df)
			if table["rows"]:
				tables.append(table)
			continue
		if df.fieldtype in _SKIP_FIELDTYPES:
			continue
		value = doc.get(df.fieldname)
		if value in (None, ""):
			continue
		fields.append({
			"label": df.label or df.fieldname,
			"fieldname": df.fieldname,
			"fieldtype": df.fieldtype,
			"value": _display_value(value, df),
		})

	return {
		"status": "success",
		"doctype": application_doctype,
		"name": application_name,
		"meta": {
			"owner": doc.owner,
			"creation": doc.creation,
			"modified": doc.modified,
			"workflow_state": doc.get("workflow_state") or "",
			"docstatus": doc.docstatus,
		},
		"fields": fields,
		"tables": tables,
	}


def _get_child_table_detail(doc, table_df):
	"""Build a display-ready {label, columns, rows} block for one child table field.
	Columns prefer the child doctype's own in_list_view fields (its natural summary
	view); if none are marked, fall back to all non-structural fields."""
	child_meta = frappe.get_meta(table_df.options)
	columns = [f for f in child_meta.fields if f.in_list_view and f.fieldtype not in _SKIP_FIELDTYPES]
	if not columns:
		columns = [f for f in child_meta.fields if f.fieldtype not in _SKIP_FIELDTYPES | {"Table", "Table MultiSelect"}]

	rows = []
	for child in doc.get(table_df.fieldname) or []:
		row = {}
		has_value = False
		for col in columns:
			value = child.get(col.fieldname)
			if value not in (None, ""):
				has_value = True
			row[col.fieldname] = _display_value(value, col)
		if has_value:
			rows.append(row)

	return {
		"label": table_df.label or table_df.fieldname,
		"fieldname": table_df.fieldname,
		"columns": [{"fieldname": c.fieldname, "label": c.label or c.fieldname} for c in columns],
		"rows": rows,
	}


def _display_value(value, df):
	"""Human-readable rendering of a field value. Link fields whose target doctype
	uses a non-descriptive autoname (hash/counter) are resolved to their title_field
	instead of showing the raw docname — e.g. Budget Head's name is a random hash,
	its title_field ("budget_head") holds the actual account head text."""
	if df.fieldtype == "Check":
		return bool(value)
	if value in (None, ""):
		return frappe.utils.cstr(value)
	if df.fieldtype == "Link" and df.options and frappe.db.exists("DocType", df.options):
		title_field = frappe.get_meta(df.options).get_title_field()
		if title_field and title_field != "name":
			label = frappe.get_cached_value(df.options, value, title_field)
			if label:
				return frappe.utils.cstr(label)
	return frappe.utils.cstr(value)


@frappe.whitelist()
def save_verification(project, application_doctype, application_name, verification_status, remarks=None):
	"""Create or update the Project Verification record for one application, stamping
	verifier/timestamp/IP/user-agent. Runs through normal doc.save() permission checks."""
	_ensure_verification_access()

	if application_doctype not in _ALLOWED_APPLICATION_DOCTYPES:
		frappe.throw(
			_("{0} is not a recognised application document type").format(application_doctype),
			frappe.PermissionError,
		)
	if verification_status not in _VALID_STATUSES:
		frappe.throw(_("Invalid verification status"))

	pr_name = _resolve_project(project)
	if not frappe.db.exists(application_doctype, application_name):
		frappe.throw(_("{0} {1} not found").format(application_doctype, application_name))

	existing = frappe.db.get_value(
		"Project Verification",
		{
			"project": pr_name,
			"application_doctype": application_doctype,
			"application_name": application_name,
		},
	)

	doc = frappe.get_doc("Project Verification", existing) if existing else frappe.new_doc("Project Verification")
	doc.project = pr_name
	doc.application_doctype = application_doctype
	doc.application_name = application_name
	doc.verification_status = verification_status
	doc.remarks = remarks or ""
	doc.verified_by = frappe.session.user
	doc.verified_on = now_datetime()
	doc.ip_address = _client_ip()
	doc.user_agent = _request_header("User-Agent")
	doc.save()

	return {
		"status": "success",
		"record": doc.name,
		"verification": {
			"verification_status": doc.verification_status,
			"remarks": doc.remarks,
			"verified_by": doc.verified_by,
			"verified_on": doc.verified_on,
		},
	}


@frappe.whitelist()
def get_verification_audit_history(project, application_doctype, application_name):
	"""Timeline of who changed what on this application's verification record,
	sourced from Frappe's built-in Version tracking (track_changes=1)."""
	_ensure_verification_access()
	pr_name = _resolve_project(project)

	pv_name = frappe.db.get_value(
		"Project Verification",
		{
			"project": pr_name,
			"application_doctype": application_doctype,
			"application_name": application_name,
		},
	)
	if not pv_name:
		return {"status": "success", "history": []}

	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": "Project Verification", "docname": pv_name},
		fields=["name", "owner", "creation", "data"],
		order_by="creation desc",
	)

	history = []
	for v in versions:
		try:
			data = json.loads(v.data or "{}")
		except ValueError:
			data = {}
		changed = data.get("changed") or []
		if not changed:
			continue
		history.append({
			"by": v.owner,
			"on": v.creation,
			"changes": [
				{"field": c[0], "from": c[1], "to": c[2]}
				for c in changed if len(c) == 3
			],
		})

	return {"status": "success", "history": history}


_ALLOWED_PATH_PREFIXES = (
	"/project_verification",
	"/login",
	"/api/method/login",
	"/api/method/logout",
	"/api/method/frappe.",
	"/api/method/rndopsapp.rndopsapp.doctype.project_verification.",
	"/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.search_projects",
	"/assets/",
	"/favicon.ico",
)

# Exact paths (not prefixes — "/" would otherwise match every route via startswith)
# left open even for a logged-in Verification Staff session: the plain site landing page.
_ALLOWED_EXACT_PATHS = ("/", "")


def restrict_verification_staff_routes():
	"""before_request hook: users whose only meaningful role is 'Verification Staff'
	may only reach the verification portal, its own APIs, shared auth/asset routes,
	and the plain site root ("/", left open on request so their landing page still
	looks like the normal Frappe site rather than being force-redirected).
	/app itself is already blocked for them by Frappe core (Website User -> app.py);
	this closes off the *other* internal www tools (kafka_control, pr_link_graph, etc.)
	which are otherwise open to any logged-in user.

	Raised as a werkzeug HTTPException carrying a ready-made redirect Response: this hook
	runs during init_request(), well before frappe.website.serve.get_response()'s
	frappe.Redirect-aware exception handling kicks in, so frappe.redirect()/frappe.Redirect
	would not actually produce a redirect here — only a real HTTPException is honoured by
	app.py's `except HTTPException as e: return e`."""
	if frappe.session.user == "Guest":
		return

	roles = frappe.get_roles(frappe.session.user)
	if "Verification Staff" not in roles:
		return
	if any(r in roles for r in ("System Manager", "Administrator")):
		return

	path = frappe.request.path if frappe.request else ""
	if path in _ALLOWED_EXACT_PATHS:
		return
	if any(path.startswith(prefix) for prefix in _ALLOWED_PATH_PREFIXES):
		return

	raise HTTPException(
		response=WerkzeugResponse(status=302, headers={"Location": "/project_verification"})
	)
