# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Recruitment Advertisment - marks an approved Recruitment Adhoc Contractual as published.

A Recruitment Adhoc Contractual is published when a Recruitment Advertisment record with
publish = "Yes" exists for it. No record (or publish = "No") means it is not yet published.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document

RAC = "Recruitment Adhoc Contractual"
APPROVED_STATE = "Approved"


class RecruitmentAdvertisment(Document):
	def validate(self):
		rac = frappe.db.get_value(
			RAC, self.recruitment_adhoc_contractual, ["workflow_state", "upfa_project_code"], as_dict=True
		)
		if not rac:
			frappe.throw(_("Recruitment Adhoc Contractual {0} not found").format(self.recruitment_adhoc_contractual))
		if rac.workflow_state != APPROVED_STATE:
			frappe.throw(
				_("Recruitment Adhoc Contractual {0} is not approved yet (status: {1}).").format(
					self.recruitment_adhoc_contractual, rac.workflow_state
				)
			)
		if not self.project_no:
			self.project_no = rac.upfa_project_code


def _status(record, approved=True):
	"""Shape returned to the caller for one Recruitment Adhoc Contractual.
	Only an approved recruitment can be published; anything else is "Not approved"."""
	if not approved:
		return {"approved": False, "published": False, "status": "Not approved", "record": record}
	published = bool(record and record.get("publish") == "Yes")
	return {
		"approved": True,
		"published": published,
		"status": "Published" if published else "Not yet published",
		"record": record,
	}


_FIELDS = ["name", "recruitment_adhoc_contractual", "project_no", "publish", "creation", "modified"]


def _is_approved(rac_name):
	return frappe.db.get_value(RAC, rac_name, "workflow_state") == APPROVED_STATE


@frappe.whitelist()
def save_recruitment_advertisment(recruitment_adhoc_contractual, publish="Yes", project_no=None):
	"""
	Publish (or unpublish) an approved Recruitment Adhoc Contractual. One record per
	recruitment: it is created on first call and updated afterwards. Rejected unless the
	recruitment is Approved.

	Args:
		recruitment_adhoc_contractual: name of the approved Recruitment Adhoc Contractual.
		publish: "Yes" (default) or "No".
		project_no: optional; defaults to the recruitment's project code.
	"""
	if not recruitment_adhoc_contractual:
		frappe.throw(_("recruitment_adhoc_contractual is required"))
	publish = "Yes" if str(publish).strip().lower() in ("yes", "1", "true") else "No"

	existing = frappe.db.get_value(
		"Recruitment Advertisment", {"recruitment_adhoc_contractual": recruitment_adhoc_contractual}, "name"
	)
	if existing:
		doc = frappe.get_doc("Recruitment Advertisment", existing)
		if doc.publish == publish and (not project_no or doc.project_no == project_no):
			# Already saved with these values: nothing to write.
			return {"status": "success", **_status(doc.as_dict())}
		doc.publish = publish
		if project_no:
			doc.project_no = project_no
		doc.save()
	else:
		doc = frappe.get_doc({
			"doctype": "Recruitment Advertisment",
			"recruitment_adhoc_contractual": recruitment_adhoc_contractual,
			"project_no": project_no,
			"publish": publish,
		})
		doc.insert()

	return {"status": "success", **_status(doc.as_dict())}


@frappe.whitelist()
def get_recruitment_advertisment(recruitment_adhoc_contractual):
	"""
	Is this Recruitment Adhoc Contractual published?
	  - not approved          -> status "Not approved"
	  - approved, no record   -> "Not yet published"
	  - approved, record Yes  -> "Published"
	"""
	if not recruitment_adhoc_contractual:
		frappe.throw(_("recruitment_adhoc_contractual is required"))
	record = frappe.db.get_value(
		"Recruitment Advertisment",
		{"recruitment_adhoc_contractual": recruitment_adhoc_contractual},
		_FIELDS,
		as_dict=True,
	)
	return {
		"recruitment_adhoc_contractual": recruitment_adhoc_contractual,
		**_status(record, approved=_is_approved(recruitment_adhoc_contractual)),
	}


@frappe.whitelist()
def get_recruitment_advertisments(recruitment_adhoc_contractuals):
	"""
	Bulk lookup: a JSON list of Recruitment Adhoc Contractual names ->
	{name: {approved, published, status, record}}.
	"""
	if isinstance(recruitment_adhoc_contractuals, str):
		try:
			recruitment_adhoc_contractuals = json.loads(recruitment_adhoc_contractuals)
		except ValueError:
			recruitment_adhoc_contractuals = [recruitment_adhoc_contractuals]
	names = [n for n in (recruitment_adhoc_contractuals or []) if n]
	records, approved = {}, set()
	if names:
		for r in frappe.get_all(
			"Recruitment Advertisment",
			filters={"recruitment_adhoc_contractual": ["in", names]},
			fields=_FIELDS,
		):
			records[r.recruitment_adhoc_contractual] = r
		approved = set(
			frappe.get_all(RAC, filters={"name": ["in", names], "workflow_state": APPROVED_STATE}, pluck="name")
		)
	return {n: _status(records.get(n), approved=n in approved) for n in names}


# Project numbers look like "2627R-0274-CHEM0540GKRI": the letter after the 4-digit year
# is the project kind (R = Research, C = Consultancy, anything else = Others).
_TYPE_SQL = "CASE SUBSTRING(r.upfa_project_code, 5, 1) WHEN 'R' THEN 'Research' WHEN 'C' THEN 'Consultancy' ELSE 'Others' END"
# Recruitments approved before this date are not part of the advertisement list.
ADVERTISEMENT_FROM_DATE = "2026-11-24"

# Approval time: the workflow "Approved" comment, then a Workflow Action row, else last modified
# (same order as _approved_on).
_APPROVED_ON_SQL = """COALESCE(
	(SELECT MAX(c.creation) FROM `tabComment` c
	 WHERE c.reference_doctype = 'Recruitment Adhoc Contractual' AND c.reference_name = r.name
	   AND c.comment_type = 'Workflow' AND c.content = 'Approved'),
	(SELECT MAX(w.modified) FROM `tabWorkflow Action` w
	 WHERE w.reference_doctype = 'Recruitment Adhoc Contractual' AND w.reference_name = r.name
	   AND w.workflow_state = 'Approved'),
	r.modified)"""
_TYPES = {"research": "Research", "consultancy": "Consultancy", "others": "Others", "other": "Others"}


def _project_type(project_no):
	kind = (project_no or "")[4:5]
	return "Research" if kind == "R" else "Consultancy" if kind == "C" else "Others"


def _approved_on(names):
	"""{name: datetime} - when each recruitment was approved.

	Taken from the workflow "Approved" comment, then a Workflow Action row; recruitments
	approved without either (e.g. migrated) fall back to their last-modified time.
	"""
	if not names:
		return {}
	result = {}
	for row in frappe.db.sql(
		"""SELECT reference_name, MAX(creation) FROM `tabComment`
		   WHERE reference_doctype=%s AND comment_type='Workflow' AND content='Approved'
		     AND reference_name IN %s GROUP BY reference_name""",
		(RAC, tuple(names)),
	):
		result[row[0]] = row[1]
	missing = [n for n in names if n not in result]
	if missing:
		for row in frappe.db.sql(
			"""SELECT reference_name, MAX(modified) FROM `tabWorkflow Action`
			   WHERE reference_doctype=%s AND workflow_state='Approved' AND reference_name IN %s
			   GROUP BY reference_name""",
			(RAC, tuple(missing)),
		):
			result[row[0]] = row[1]
	return result


@frappe.whitelist()
def list_approved_recruitments(published="0", type=None, project_no=None, page=1, page_length=50):
	"""
	Approved Recruitment Adhoc Contractual records with their advertisement status, one page
	at a time (50 per page by default). Recruitments approved before 24/11/2026
	(ADVERTISEMENT_FROM_DATE) are left out.

	Args:
		published: "0"/"No" (default) -> only not yet published; "1"/"Yes" -> only published;
			"all" -> both.
		type: optional "Research" | "Consultancy" | "Others" (from the project number).
		project_no: optional exact project number.
		page: 1-based page number.
		page_length: rows per page (default 50, max 100).

	Returns:
		summary:    pending (= approved and not yet published) totals - total, research,
		            consultancy, others - plus the published count. Not affected by filters.
		pagination: page, page_length, total (rows matching the filters), total_pages,
		            has_next, has_prev.
		data:       [{recruitment, type, project_no, project_title, approved_on,
		              advertisement, published}]
	"""
	page = max(int(page or 1), 1)
	page_length = min(max(int(page_length or 50), 1), 100)

	published_sql = "EXISTS (SELECT 1 FROM `tabRecruitment Advertisment` a WHERE a.recruitment_adhoc_contractual = r.name AND a.publish = 'Yes')"
	base = (
		"FROM `tabRecruitment Adhoc Contractual` r WHERE r.workflow_state = %(approved)s "
		f"AND {_APPROVED_ON_SQL} >= %(from_date)s"
	)
	values = {"approved": APPROVED_STATE, "from_date": ADVERTISEMENT_FROM_DATE}

	# Summary: pending (approved, not yet published) by type, plus how many are published.
	counts = {"Research": 0, "Consultancy": 0, "Others": 0}
	for kind, n in frappe.db.sql(
		f"SELECT {_TYPE_SQL}, COUNT(*) {base} AND NOT {published_sql} GROUP BY 1", values
	):
		counts[kind] = n
	published_count = frappe.db.sql(f"SELECT COUNT(*) {base} AND {published_sql}", values)[0][0]
	summary = {
		"total_pending": sum(counts.values()),
		"research": counts["Research"],
		"consultancy": counts["Consultancy"],
		"others": counts["Others"],
		"published": published_count,
	}

	where = ""
	if published is not None and str(published).strip().lower() not in ("", "all"):
		want = str(published).strip().lower() in ("1", "yes", "true")
		where += f" AND {'' if want else 'NOT '}{published_sql}"
	if type:
		kind = _TYPES.get(str(type).strip().lower())
		if not kind:
			frappe.throw(_("type must be Research, Consultancy or Others"))
		where += f" AND {_TYPE_SQL} = %(kind)s"
		values["kind"] = kind
	if project_no:
		where += " AND r.upfa_project_code = %(project_no)s"
		values["project_no"] = project_no

	total = frappe.db.sql(f"SELECT COUNT(*) {base}{where}", values)[0][0]
	values.update({"limit": page_length, "offset": (page - 1) * page_length})
	rows = frappe.db.sql(
		f"""SELECT r.name, r.upfa_project_code, r.upfa_project_title, r.modified,
		           {published_sql} AS is_published
		    {base}{where} ORDER BY r.modified DESC LIMIT %(limit)s OFFSET %(offset)s""",
		values,
		as_dict=True,
	)
	approved_on = _approved_on([r.name for r in rows])

	data = []
	for r in rows:
		when = approved_on.get(r.name) or r.modified
		data.append({
			"recruitment": r.name,
			"type": _project_type(r.upfa_project_code),
			"project_no": r.upfa_project_code,
			"project_title": r.upfa_project_title,
			"approved_on": when.isoformat() if when else None,
			"advertisement": "Published" if r.is_published else "Not yet published",
			"published": bool(r.is_published),
		})

	total_pages = -(-total // page_length) if total else 0
	return {
		"summary": summary,
		"pagination": {
			"page": page,
			"page_length": page_length,
			"total": total,
			"total_pages": total_pages,
			"has_next": page < total_pages,
			"has_prev": page > 1,
		},
		"data": data,
	}
