# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import base64
import json
import string

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import getseries
from frappe.utils import cint, now_datetime

from rndopsapp.rndopsapp.doctype.module_registry.project_type_links import DEPOSIT_SLIP_DOCTYPES

INVOICE_PREFIX = "INVO"
SERIES_KEY = "CONSULTANCY-INVOICE"
LETTERS = string.ascii_uppercase
DIGIT_SPAN = 999  # numeric part runs 001..999, then the letters advance


def invoice_suffix(n):
	"""Running sequence: 1 -> AAA001, 2 -> AAA002, ... 999 -> AAA999, 1000 -> AAB001, ...
	3 letters (base 26) followed by 3 digits."""
	if n < 1 or n > len(LETTERS) ** 3 * DIGIT_SPAN:
		frappe.throw(_("The Consultancy Invoice number sequence is exhausted."))
	block, digits = divmod(n - 1, DIGIT_SPAN)
	letters = ""
	for _i in range(3):
		block, rem = divmod(block, len(LETTERS))
		letters = LETTERS[rem] + letters
	return f"{letters}{digits + 1:03d}"


def generate_docname():
	"""Document name INVO-YYYY-MM-DD-AAA001: today's date plus the next number of one running sequence
	(never reset, so numbers are unique across days). The counter is the database-locked
	Frappe naming series, so concurrent saves can't be given the same number."""
	n = cint(getseries(SERIES_KEY, 1))
	return f"{INVOICE_PREFIX}-{now_datetime().strftime('%Y-%m-%d')}-{invoice_suffix(n)}"


class ConsultancyInvoice(Document):
	def autoname(self):
		# The document name is always generated; invoice_no is the user's own input.
		self.name = generate_docname()

	def validate(self):
		self.project_no = (self.project_no or "").strip()
		self.fund_received_ref = (self.fund_received_ref or "").strip()

		# invoice_no is a table of Invoice Number rows: at least one, no blanks, no repeats,
		# and none already used by another Consultancy Invoice.
		seen = set()
		for row in list(self.get("invoice_no") or []):
			number = (row.invoice_number or "").strip()
			if not number:
				self.remove(row)
				continue
			if number in seen:
				frappe.throw(_("Invoice number {0} is listed more than once.").format(number))
			seen.add(number)
			row.invoice_number = number
		if not seen:
			frappe.throw(_("Invoice Number is required."))

		taken = frappe.get_all(
			"invoice_number",
			filters={
				"parenttype": "Consultancy Invoice",
				"invoice_number": ["in", list(seen)],
				"parent": ["!=", self.name],
			},
			fields=["invoice_number", "parent"],
			limit=1,
		)
		if taken:
			frappe.throw(
				_("Invoice number {0} is already used by another invoice ({1}).").format(
					taken[0].invoice_number, taken[0].parent
				),
				frappe.DuplicateEntryError,
			)

		filters = {"project_no": self.project_no, "fund_received_ref": self.fund_received_ref}
		if not self.is_new():
			filters["name"] = ["!=", self.name]
		existing = frappe.get_all("Consultancy Invoice", filters=filters, pluck="name", limit=1)
		if existing:
			frappe.throw(
				_("An invoice ({0}) already exists for project {1} and fund received ref {2}.").format(
					existing[0], self.project_no, self.fund_received_ref
				),
				frappe.DuplicateEntryError,
			)


# ── Whitelisted API ─────────────────────────────────────────────────────────
# save_con_invoice(project_no, fund_received_ref, invoice_no) -> {"name", "fund_received_ref", "invoice_no": [...]}
# get_con_invoice(project_no, fund_received_ref)             -> {"name" | None, "fund_received_ref" | None, "invoice_no": [...]}
# fund_received_ref is the Fund Received docname (its reference number is accepted too and
# converted); the invoice is always stored against the docname.
# `invoice_no` is a table on the document, so it takes one number or a list of numbers; `name`
# is the generated document name (INVO-YYYY-MM-DD-AAA001). Saving a pair again adds any new
# numbers to the same document and ignores ones it already has; a number that belongs to
# another invoice is rejected. Needs create/write permission on the DocType for saving.

def _find_project(project_no):
	"""(Project Registration name, human-readable project_no), or None. Accepts either
	identifier."""
	project_no = (project_no or "").strip()
	if not project_no:
		return None
	name = frappe.db.get_value("Project Registration", project_no, "name") or frappe.db.get_value(
		"Project Registration", {"project_no": project_no}, "name"
	)
	if not name:
		return None
	return name, (frappe.db.get_value("Project Registration", name, "project_no") or name)


def _find_fund(fund_received_ref, project_name):
	"""The Fund Received for this project given its docname or reference number:
	{name, fund_received_ref_number}, or None. Raises if it belongs to another project."""
	fund = frappe.get_all(
		"Fund Received",
		or_filters=[["name", "=", fund_received_ref], ["fund_received_ref_number", "=", fund_received_ref]],
		fields=["name", "prjreg_title", "fund_received_ref_number"],
		limit=1,
	)
	if not fund:
		return None
	if fund[0].prjreg_title != project_name:
		return "other-project"
	return fund[0]


def _existing_invoice(project_no, fund):
	"""Invoice name for (project, Fund Received). Records are keyed by the Fund Received
	docname; ones saved earlier with its reference number are found too."""
	keys = [fund.name] + ([fund.fund_received_ref_number] if fund.fund_received_ref_number else [])
	rows = frappe.get_all(
		"Consultancy Invoice",
		filters={"project_no": project_no, "fund_received_ref": ["in", keys]},
		pluck="name",
		limit=1,
	)
	return rows[0] if rows else None


def _numbers_of(doc):
	return [r.invoice_number for r in (doc.get("invoice_no") or []) if r.invoice_number]


def _as_numbers(invoice_no):
	"""One invoice number, a list of them, or a JSON-encoded list -> clean list of strings."""
	if isinstance(invoice_no, str):
		text = invoice_no.strip()
		if text.startswith("["):
			try:
				invoice_no = json.loads(text)
			except ValueError:
				invoice_no = [text]
		else:
			invoice_no = [text]
	if not isinstance(invoice_no, (list, tuple)):
		invoice_no = [invoice_no]

	numbers = []
	for n in invoice_no:
		n = ("" if n is None else str(n)).strip()
		if n and n not in numbers:
			numbers.append(n)
	return numbers


@frappe.whitelist()
def save_con_invoice(project_no, fund_received_ref, invoice_no):
	"""Save the invoice for a project + Fund Received. `invoice_no` is one number or a list.
	Returns the document name and all its invoice numbers."""
	frappe.has_permission("Consultancy Invoice", "create", throw=True)

	fund_received_ref = (fund_received_ref or "").strip()
	if not fund_received_ref:
		frappe.throw(_("Fund Received Ref is required."))
	numbers = _as_numbers(invoice_no)
	if not numbers:
		frappe.throw(_("Invoice Number is required."))

	project = _find_project(project_no)
	if not project:
		frappe.throw(_("Project {0} does not exist.").format(project_no), frappe.DoesNotExistError)
	project_name, project_number = project

	# fund_received_ref may be the Fund Received docname or its reference number; the
	# invoice is always saved against the docname.
	fund = _find_fund(fund_received_ref, project_name)
	if not fund:
		frappe.throw(_("Fund Received {0} does not exist.").format(fund_received_ref), frappe.DoesNotExistError)
	if fund == "other-project":
		frappe.throw(
			_("Fund Received {0} does not belong to project {1}.").format(fund_received_ref, project_number)
		)

	existing = _existing_invoice(project_number, fund)
	if existing:
		doc = frappe.get_doc("Consultancy Invoice", existing)
		have = set(_numbers_of(doc))
		new = [n for n in numbers if n not in have]
		if new or doc.fund_received_ref != fund.name:
			for n in new:
				doc.append("invoice_no", {"invoice_number": n})
			doc.fund_received_ref = fund.name  # moves a legacy reference-number record to the docname
			doc.save()
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Consultancy Invoice",
				"project_no": project_number,
				"fund_received_ref": fund.name,
				"invoice_no": [{"invoice_number": n} for n in numbers],
			}
		)
		doc.insert()

	return {"name": doc.name, "fund_received_ref": doc.fund_received_ref, "invoice_no": _numbers_of(doc)}


@frappe.whitelist()
def get_con_invoice(project_no, fund_received_ref):
	"""The invoice saved for this project + Fund Received (docname or reference number):
	{name, fund_received_ref, invoice_no: [numbers]}; name None / invoice_no [] if none."""
	frappe.has_permission("Consultancy Invoice", "read", throw=True)
	empty = {"name": None, "fund_received_ref": None, "invoice_no": []}

	project = _find_project(project_no)
	fund_received_ref = (fund_received_ref or "").strip()
	if not project or not fund_received_ref:
		return empty
	fund = _find_fund(fund_received_ref, project[0])
	if not fund or fund == "other-project":
		return empty

	name = _existing_invoice(project[1], fund)
	if not name:
		return empty
	doc = frappe.get_doc("Consultancy Invoice", name)
	return {"name": name, "fund_received_ref": doc.fund_received_ref, "invoice_no": _numbers_of(doc)}


DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


def _encode_cursor(direction, row):
	raw = json.dumps({"d": direction, "c": str(row["creation"]), "n": row["name"]})
	return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(pagination_id):
	try:
		raw = base64.urlsafe_b64decode(pagination_id + "=" * (-len(pagination_id) % 4)).decode()
		data = json.loads(raw)
		if data["d"] not in ("next", "previous"):
			raise ValueError
		return data["d"], str(data["c"]), str(data["n"])
	except Exception:
		frappe.throw(_("Invalid pagination_id."), frappe.ValidationError)


def _project_page(filters, direction, creation, name, limit):
	"""Up to `limit` project rows (newest first) strictly after ("next") or strictly before
	("previous") the (creation, name) position, using that pair as a unique sort key so a
	project is never repeated or skipped between pages. direction/creation/name None -> first page."""
	fields = ["name", "project_no", "project_title", "workflow_state", "creation"]
	common = dict(fields=fields, limit_page_length=0)

	if not creation:
		return frappe.get_list("Project Registration", filters=filters, order_by="creation desc, name desc", **{**common, "limit_page_length": limit})

	# rows sharing the cursor's exact `creation` need to be skipped from the fetch window
	ties = len(frappe.get_list("Project Registration", filters=filters + [["creation", "=", creation]], pluck="name", limit_page_length=0))
	if direction == "next":
		rows = frappe.get_list(
			"Project Registration", filters=filters + [["creation", "<=", creation]],
			order_by="creation desc, name desc", **{**common, "limit_page_length": limit + ties},
		)
		rows = [r for r in rows if str(r.creation) != creation or r.name < name]
		return rows[:limit]

	rows = frappe.get_list(
		"Project Registration", filters=filters + [["creation", ">=", creation]],
		order_by="creation asc, name asc", **{**common, "limit_page_length": limit + ties},
	)
	rows = [r for r in rows if str(r.creation) != creation or r.name > name]
	return list(reversed(rows[:limit]))


@frappe.whitelist()
def get_approved_consultancy_funds(project_no=None, pagination_id=None, page_size=DEFAULT_PAGE_SIZE):
	"""Approved Consultancy projects that have Fund Received, with each Fund Received
	docname and the deposit slip(s) raised against it. Used to pick what to invoice.
	Paginated, newest project first, 10 per page by default.

	project_no     optional: narrow to one project (project number or Project Registration name)
	pagination_id  optional: `next_id` / `previous_id` from the previous response; omit for page 1
	page_size      optional: 1..100, default 10

	{data: [{project, project_no, project_title, workflow_state,
	         fund_received: [{name, fund_received_ref_number, fund_received_amt, workflow_state,
	                          deposit_slips: [{doctype, name, docstatus, creation}]}]}],
	 page_size, count, total, has_next, has_previous, next_id, previous_id}

	To go forward call again with pagination_id=next_id, to go back with previous_id
	(each is None when there is nothing in that direction). The position is the last/first
	project's (creation, name), so no project repeats or is skipped across pages, even if
	projects are added between calls.

	Everything is read with the caller's own permissions: projects, funds or slip types the
	user can't read are left out. Slips link to a Fund Received by its docname or its
	reference number; a fund with neither a slip yet has an empty list.
	"""
	frappe.has_permission("Consultancy Invoice", "read", throw=True)

	page_size = cint(page_size) or DEFAULT_PAGE_SIZE
	page_size = max(1, min(page_size, MAX_PAGE_SIZE))
	empty = {
		"data": [], "page_size": page_size, "count": 0, "total": 0,
		"has_next": False, "has_previous": False, "next_id": None, "previous_id": None,
	}

	# Only projects that have at least one Fund Received count, so pages are not short.
	fund_projects = list(
		{
			f.prjreg_title
			for f in frappe.get_list(
				"Fund Received",
				filters={"docstatus": ["<", 2], "prjreg_title": ["is", "set"]},
				fields=["prjreg_title"],
				limit_page_length=0,
			)
		}
	)
	if not fund_projects:
		return empty

	filters = [
		["project_type", "=", "Consultancy"],
		["workflow_state", "=", "Approved"],
		["docstatus", "=", 1],
		["name", "in", fund_projects],
	]
	if project_no:
		project = _find_project(project_no)
		if not project:
			return empty
		filters.append(["name", "=", project[0]])

	total = len(frappe.get_list("Project Registration", filters=filters, pluck="name", limit_page_length=0))

	direction = creation = name = None
	if pagination_id:
		direction, creation, name = _decode_cursor(pagination_id)

	projects = _project_page(filters, direction, creation, name, page_size)
	if not projects:
		return {**empty, "total": total}

	first, last = projects[0], projects[-1]
	has_next = bool(_project_page(filters, "next", str(last.creation), last.name, 1))
	has_previous = bool(_project_page(filters, "previous", str(first.creation), first.name, 1))

	funds = frappe.get_list(
		"Fund Received",
		filters={"prjreg_title": ["in", [p.name for p in projects]], "docstatus": ["<", 2]},
		fields=["name", "prjreg_title", "fund_received_ref_number", "fund_received_amt", "workflow_state"],
		order_by="creation asc",
		limit_page_length=0,
	)

	# A slip's `fund_received_ref` holds either the Fund Received docname (consultancy slips,
	# e.g. REC_2010265689-prjreg_refnum) or its reference number (research slips, e.g. 74).
	fund_by_key = {}
	for f in funds:
		fund_by_key[f.name] = f.name
		if f.fund_received_ref_number:
			fund_by_key.setdefault(f.fund_received_ref_number, f.name)

	slips_by_fund = {}
	if fund_by_key:
		for slip_doctype in DEPOSIT_SLIP_DOCTYPES:
			if not frappe.db.exists("DocType", slip_doctype) or not frappe.has_permission(slip_doctype, "read"):
				continue
			for s in frappe.get_list(
				slip_doctype,
				filters={"fund_received_ref": ["in", list(fund_by_key)]},
				fields=["name", "fund_received_ref", "docstatus", "creation"],
				order_by="creation asc",
				limit_page_length=0,
			):
				slips_by_fund.setdefault(fund_by_key[s.fund_received_ref], []).append(
					{
						"doctype": slip_doctype,
						"name": s.name,
						"docstatus": s.docstatus,
						"creation": str(s.creation),
					}
				)

	funds_by_project = {}
	for f in funds:
		funds_by_project.setdefault(f.prjreg_title, []).append(
			{
				"name": f.name,
				"fund_received_ref_number": f.fund_received_ref_number,
				"fund_received_amt": f.fund_received_amt,
				"workflow_state": f.workflow_state,
				"deposit_slips": slips_by_fund.get(f.name, []),
			}
		)

	data = [
		{
			"project": p.name,
			"project_no": p.project_no,
			"project_title": p.project_title,
			"workflow_state": p.workflow_state,
			"fund_received": funds_by_project.get(p.name, []),
		}
		for p in projects
	]
	return {
		"data": data,
		"page_size": page_size,
		"count": len(data),
		"total": total,
		"has_next": has_next,
		"has_previous": has_previous,
		"next_id": _encode_cursor("next", last) if has_next else None,
		"previous_id": _encode_cursor("previous", first) if has_previous else None,
	}
