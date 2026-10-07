

# -========================bhasker update

# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import math
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.workflow import apply_workflow, get_transitions
from frappe.utils import getdate
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import read_xls_file_from_attached_file, read_xlsx_file_from_attached_file


def _extract_eval(expression):
	if not expression:
		return None
	expression = str(expression).strip()
	return expression[5:].strip() if expression.startswith("eval:") else expression


# Personal-details name fields get title-cased on entry, since staff/HR type
# them in all-caps, all-lowercase, or mixed case interchangeably (e.g.
# "JOHN DOE", "john doe" -> "John Doe"). str.title() also does the right
# thing across hyphens and apostrophes ("mary-jane" -> "Mary-Jane",
# "d'angelo" -> "D'Angelo").
NAME_FIELDS_TO_TITLE_CASE = {"ps_first_name", "ps_middle_name", "ps_last_name", "ps_fathers_name"}


def _normalize_name_casing(value):
	value = str(value or "").strip()
	return value.title() if value else value


class ProjectStaffDetails(Document):
	def validate(self):
		# Runs on every insert/save regardless of entry point — the
		# `/insert_project_staff` admin tool, its bulk CSV/Excel importer,
		# Frappe Desk's own Data Import tool, direct Desk edits, or API
		# scripts — so name casing and IFSC formatting stay consistent no
		# matter how the record was created.
		for field in NAME_FIELDS_TO_TITLE_CASE:
			value = self.get(field)
			if value:
				self.set(field, _normalize_name_casing(value))
		if self.ifsc_code:
			self.ifsc_code = self.ifsc_code.strip().upper()

		# ps_designation is free-text (hand-typed/bulk-imported), so the same
		# role ends up spelled many ways ("JRF GATE", "JRF(GATE)", ...). Snap
		# it to the canonical Designation_prornd spelling whenever it's a
		# confident match, same resolution _sync_project_staff_to_user already
		# uses for the User sync — left unchanged if nothing matches closely
		# enough, rather than guessing.
		if self.ps_designation:
			resolved_designation = _resolve_link_value("Designation_prornd", self.ps_designation)
			if resolved_designation:
				self.ps_designation = resolved_designation

	# Employee ID is allocated when the staff submits the joining form
	# (see `submit_project_staff_details`), not at draft-insert time, so
	# abandoned drafts don't burn numbers in the series.
	def on_update(self):
		self._allocate_leave_if_approved()

	def on_submit(self):
		self._allocate_leave_if_approved()

	def on_update_after_submit(self):
		self._allocate_leave_if_approved()

	def _allocate_leave_if_approved(self):
		if (self.workflow_state or "").strip() != "Approved":
			return

		if getattr(frappe.flags, "allocating_project_staff_leave", False):
			return

		frappe.flags.allocating_project_staff_leave = True
		try:
			_allocate_leave_data_on_approval(self)
		finally:
			frappe.flags.allocating_project_staff_leave = False

	def get_date_of_last_extension(self):
		"""
		Calculates the Date of Last Extension based on the child table `table_ymed` (tenure details).
		Gets the pstd_joining_date from the newest/latest row.
		"""
		tenures = self.get("table_ymed") or []
		valid_tenures = [t for t in tenures if t.pstd_joining_date]

		if not valid_tenures:
			return None

		from frappe.utils import getdate

		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
		return sorted_tenures[-1].pstd_joining_date

	def get_gap_from_previous_tenure(self):
		"""
		Days between the latest tenure row's joining date and the term
		completion date of the row right before it, based on `table_ymed`.
		Returns None if there are fewer than two tenure rows.
		"""
		tenures = self.get("table_ymed") or []
		valid_tenures = [t for t in tenures if t.pstd_joining_date]

		if len(valid_tenures) < 2:
			return None

		from frappe.utils import getdate

		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
		latest, previous = sorted_tenures[-1], sorted_tenures[-2]

		if not previous.pstd_term_completion_date:
			return None

		return (getdate(latest.pstd_joining_date) - getdate(previous.pstd_term_completion_date)).days


def generate_emp_id():
	"""
	Allocate the next Employee ID for the current calendar year in the format
	YYYYTS0001 (e.g. 2026TS0001, 2026TS0002 ...).

	Uses Frappe's `make_autoname` which atomically increments the underlying
	`tabSeries` row, so two concurrent submissions can't collide on the same
	number. The series row is auto-created on first use.

	Some existing records were assigned an emp id directly (bulk imports,
	admin tools) without going through this series, so the counter can lag
	behind the real max. Guard against handing out an id that's already
	taken by re-drawing (the series call itself already advanced the
	counter, so this never repeats a value) until we land on a free one.
	"""
	from frappe.utils import nowdate
	from frappe.model.naming import make_autoname

	year = nowdate()[:4]
	for _ in range(50):
		# ".####" -> 4-digit zero-padded counter scoped to the "{year}TS" prefix.
		emp_id = make_autoname(f"{year}TS.####")
		if not frappe.db.exists("Project Staff Details", {"ps_emp_id": emp_id}):
			return emp_id
	frappe.throw(_("Could not allocate a free Employee ID, please try again."))


@frappe.whitelist()
def get_next_emp_id():
	from frappe.utils import nowdate

	year = nowdate()[:4]
	series_key = f"{year}TS"
	current = frappe.db.sql("SELECT current FROM `tabSeries` WHERE name = %s", series_key)
	next_num = (current[0][0] if current else 0) + 1
	return f"{series_key}{str(next_num).zfill(4)}"


@frappe.whitelist()
def get_project_staff_details_fields(doc_name=None):
	"""
	Returns field metadata, prefill data (if doc_name provided), and link options.
	"""
	meta = frappe.get_meta("Project Staff Details")

	fields = []
	for f in meta.get("fields"):
		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": _extract_eval(f.depends_on),
			"mandatory_depends_on_eval": _extract_eval(f.mandatory_depends_on),
			"read_only_depends_on_eval": _extract_eval(f.read_only_depends_on),
		}
		if f.fieldtype == "Table" and f.options:
			child_meta = frappe.get_meta(f.options)
			field_data["child_fields"] = [
				{
					"fieldname": cf.fieldname,
					"label": cf.label,
					"fieldtype": cf.fieldtype,
					"options": cf.options,
					"mandatory": cf.reqd,
					"hidden": cf.hidden,
					"read_only": cf.read_only,
					"in_list_view": cf.in_list_view,
				}
				for cf in child_meta.get("fields")
			]
		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	if doc_name:
		doc_name = str(doc_name).strip('"').strip("'")
		doc = frappe.get_doc("Project Staff Details", doc_name)
		prefill_data = doc.as_dict()

		# table_ymed (Tenure Details) is the real source of truth for the
		# current joining/term-completion/basic-salary — a staff member's
		# service is a sequence of tenure rows (original hire + each
		# extension), and the parent's own ps_joining_date /
		# ps_term_completion_date / ps_basic_salary only reflect whichever
		# tenure last happened to write them. Override with the latest row
		# here instead of trusting the parent fields to always be in sync.
		valid_tenures = [
			t for t in (doc.get("table_ymed") or [])
			if t.get("pstd_joining_date") and t.get("pstd_term_completion_date")
		]
		if valid_tenures:
			latest_tenure = max(valid_tenures, key=lambda t: getdate(t.get("pstd_joining_date")))
			prefill_data["ps_joining_date"] = latest_tenure.get("pstd_joining_date")
			prefill_data["ps_term_completion_date"] = latest_tenure.get("pstd_term_completion_date")
			if latest_tenure.get("pstd_basic_salary"):
				prefill_data["ps_basic_salary"] = latest_tenure.get("pstd_basic_salary")

	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "Project Staff Details", "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
	}


@frappe.whitelist(methods=["POST"])
def create_project_staff_details_entry(data):
	"""
	Backs the `/insert_project_staff` admin tool page (linked from Kafka
	Control's Quick Links). Unlike `save_project_staff_details_data` (the
	staff-facing joining form, which defers ps_emp_id allocation to Submit),
	this is a quick "add an already-onboarded staff member" tool: it
	allocates the Employee ID immediately and marks the record Approved,
	mirroring how bulk-imported staff records are created.

	Deliberately does NOT use ignore_permissions — it runs as whichever
	Frappe user is logged into that page (via the external_auth-backed
	session), so Frappe's normal doctype permissions decide whether they're
	allowed to create a Project Staff Details record.
	"""
	if isinstance(data, str):
		data = json.loads(data)

	field_mapping = [
		"scr_id",
		"pi_id",
		"project_no",
		"ps_first_name",
		"ps_middle_name",
		"ps_last_name",
		"ps_gender",
		"ps_email_id",
		"ps_phone_number",
		"ps_department",
		"ps_designation",
		"ps_date_of_birth",
		"ps_joining_date",
		"ps_term_completion_date",
		"ps_fathers_name",
		"ps_present_address",
		"ps_permanent_address",
		"ps_pan",
		"ps_aadhar_number",
		"ps_blood_group",
		"ps_maritial_status",
		"ps_basic_salary",
		"ps_hra",
		"ps_ma",
		"ps_ta",
		"ps_ta_amount",
		"ps_hostel",
		"ps_citizenship",
		"bank_account_number",
		"ifsc_code",
		"erp_mail",
	]

	doc = frappe.new_doc("Project Staff Details")
	for field in field_mapping:
		if data.get(field) not in (None, ""):
			doc.set(field, data[field])

	# Runs the doctype's normal permission + validation checks for the
	# logged-in user (no ignore_permissions).
	doc.insert()

	emp_id = generate_emp_id()
	# workflow_state can't be set to "Approved" through doc.insert() itself
	# (Frappe blocks a brand-new document from landing anywhere but the
	# workflow's first state) — set it directly after insert, same as the
	# rest of this module does for admin-driven state changes.
	frappe.db.set_value(
		"Project Staff Details",
		doc.name,
		{"ps_emp_id": emp_id, "workflow_state": "Approved"},
	)

	# Reload so the in-memory doc picks up ps_emp_id/workflow_state="Approved"
	# from the db.set_value above — both helpers below either read fresh DB
	# values by doc.name (leave) or call doc.save() themselves (tenure), and
	# a stale in-memory workflow_state would make that save() look like an
	# illegal Draft->Approved jump and throw WorkflowPermissionError.
	doc.reload()

	# A record reaching "Approved" through the real workflow action
	# (perform_project_staff_details_action) triggers these same three steps —
	# run them here too so a record created straight-to-Approved by this
	# tool isn't missing its tenure row, Leave Data allocation, or User
	# account. Unlike perform_project_staff_details_action, no Ado_RnD role
	# check is needed here: this endpoint already ran doc.insert() under the
	# creator's own normal permissions (no ignore_permissions) rather than
	# the Ado_RnD-gated workflow Approve action.
	_sync_project_staff_to_user(doc)
	_populate_tenure_on_approval(doc)
	_allocate_leave_data_on_approval(doc)

	frappe.db.commit()

	return {"status": "success", "docname": doc.name, "ps_emp_id": emp_id}


# Header text (as it appears on the `/insert_project_staff` form, or the raw
# fieldname) -> Project Staff Details fieldname. Matched case/space/punctuation
# -insensitively, see `_normalize_bulk_import_header`.
BULK_IMPORT_HEADER_MAP = {
	"piid": "pi_id",
	"piidemail": "pi_id",
	"projectnumber": "project_no",
	"projectno": "project_no",
	"scrid": "scr_id",
	"department": "ps_department",
	"designation": "ps_designation",
	"firstname": "ps_first_name",
	"middlename": "ps_middle_name",
	"lastname": "ps_last_name",
	"gender": "ps_gender",
	"dateofbirth": "ps_date_of_birth",
	"fathersname": "ps_fathers_name",
	"bloodgroup": "ps_blood_group",
	"maritialstatus": "ps_maritial_status",
	"maritalstatus": "ps_maritial_status",
	"citizenship": "ps_citizenship",
	"phonenumber": "ps_phone_number",
	"emailid": "ps_email_id",
	"erpmail": "erp_mail",
	"presentaddress": "ps_present_address",
	"permanentaddress": "ps_permanent_address",
	"bankaccountnumber": "bank_account_number",
	"ifsccode": "ifsc_code",
	"ifsc": "ifsc_code",
	"pan": "ps_pan",
	"aadharnumber": "ps_aadhar_number",
	"joiningdate": "ps_joining_date",
	"termcompletiondate": "ps_term_completion_date",
	"basicsalary": "ps_basic_salary",
	"hra": "ps_hra",
	"medicalallowance": "ps_ma",
	"hostel": "ps_hostel",
	"travelallowanceneeded": "ps_ta",
	"travelallowanceamount": "ps_ta_amount",
}
# Also accept the raw fieldnames themselves (e.g. "ps_first_name") as headers.
BULK_IMPORT_HEADER_MAP.update(
	{re.sub(r"[^a-z0-9]", "", f): f for f in set(BULK_IMPORT_HEADER_MAP.values())}
)

BULK_IMPORT_REQUIRED_FIELDS = {
	"pi_id": "PI Id",
	"project_no": "Project Number",
	"ps_department": "Department",
	"ps_designation": "Designation",
	"ps_first_name": "First Name",
	"ps_last_name": "Last Name",
	"ps_gender": "Gender",
	"ps_joining_date": "Joining Date",
}

# (fieldname, label, required) for every column the importer understands, in
# the same order as the downloadable template — used to populate the manual
# column-mapping dropdowns on the upload page.
BULK_IMPORT_FIELD_DEFINITIONS = [
	("pi_id", "PI Id", True),
	("project_no", "Project Number", True),
	("scr_id", "SCR Id", False),
	("ps_department", "Department", True),
	("ps_designation", "Designation", True),
	("ps_first_name", "First Name", True),
	("ps_middle_name", "Middle Name", False),
	("ps_last_name", "Last Name", True),
	("ps_gender", "Gender", True),
	("ps_date_of_birth", "Date of Birth", False),
	("ps_fathers_name", "Father's Name", False),
	("ps_blood_group", "Blood Group", False),
	("ps_maritial_status", "Maritial Status", False),
	("ps_citizenship", "Citizenship", False),
	("ps_phone_number", "Phone Number", False),
	("ps_email_id", "Email Id", False),
	("erp_mail", "ERP Mail", False),
	("ps_present_address", "Present Address", False),
	("ps_permanent_address", "Permanent Address", False),
	("bank_account_number", "Bank Account Number", False),
	("ifsc_code", "IFSC Code", False),
	("ps_pan", "PAN", False),
	("ps_aadhar_number", "Aadhar Number", False),
	("ps_joining_date", "Joining Date", True),
	("ps_term_completion_date", "Term Completion Date", False),
	("ps_basic_salary", "Basic Salary", False),
	("ps_hra", "HRA", False),
	("ps_ma", "Medical Allowance", False),
	("ps_hostel", "Hostel", False),
	("ps_ta", "Travel Allowance Needed", False),
	("ps_ta_amount", "Travel Allowance Amount", False),
]


def _normalize_bulk_import_header(header):
	return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


# Bulk-uploaded CSV/Excel files come from HR/staff and mix date formats
# (DD-MM-YYYY, DD/MM/YYYY, D-M-YY, ...) rather than the YYYY-MM-DD MySQL
# expects, which previously failed the whole row with a raw "Incorrect date
# value" DB error. Tried in order; DD-first formats come before MM-first
# ones since this data is Indian-staff DOB/joining-date entry.
BULK_IMPORT_DATE_FIELDS = {"ps_date_of_birth", "ps_joining_date", "ps_term_completion_date"}
BULK_IMPORT_DATE_FORMATS = [
	"%Y-%m-%d", "%Y/%m/%d",
	"%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
	"%d-%m-%y", "%d/%m/%y",
	"%m-%d-%Y", "%m/%d/%Y",
]


def _normalize_bulk_import_date(value):
	"""
	Best-effort parse of a bulk-import date cell into 'YYYY-MM-DD'. Returns
	the original (stripped) value unchanged if no known format matches, so
	the row still reaches normal validation/error reporting instead of being
	silently dropped.
	"""
	from datetime import date, datetime

	# Excel date cells (.xlsx/.xls) come back as real datetime/date objects,
	# not strings — format those directly rather than round-tripping through
	# str() (which would produce "1994-03-07 00:00:00" and fail every
	# strptime pattern below).
	if isinstance(value, datetime):
		return value.strftime("%Y-%m-%d")
	if isinstance(value, date):
		return value.isoformat()

	value = str(value or "").strip()
	if not value:
		return value

	for fmt in BULK_IMPORT_DATE_FORMATS:
		try:
			return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
		except ValueError:
			continue
	return value


# `ps_ta` (If Travel Allowance Needed) is a Select field restricted to
# "", "Yes", "No" — but bulk-uploaded files commonly spell that as 0/1,
# Y/N, True/False, etc. Wrap those into the values the field actually
# accepts before insert, instead of letting every non-exact-match row fail
# with a raw "... should be one of ..." select-field error.
BULK_IMPORT_YES_NO_FIELDS = {"ps_ta"}
BULK_IMPORT_YES_VALUES = {"yes", "y", "true", "1"}
BULK_IMPORT_NO_VALUES = {"no", "n", "false", "0"}


def _normalize_bulk_import_yes_no(value):
	raw = str(value or "").strip()
	normalized = raw.lower()
	if normalized in BULK_IMPORT_YES_VALUES:
		return "Yes"
	if normalized in BULK_IMPORT_NO_VALUES:
		return "No"
	# Unrecognized value (including "") is passed through unchanged so it
	# still reaches normal validation/error reporting rather than being
	# silently dropped or guessed at.
	return raw


def _find_duplicate_project_staff_row(row_data, seen_in_file):
	"""
	Best-effort duplicate check for a bulk-import row: same Aadhar/PAN, or
	the same project + name + joining date, either already in the doctype
	or earlier in the same uploaded file. Returns a reason string, or None
	if the row looks new (and records its identity into `seen_in_file`).
	"""
	aadhar = (row_data.get("ps_aadhar_number") or "").strip()
	pan = (row_data.get("ps_pan") or "").strip()
	combo = (
		(row_data.get("project_no") or "").strip().lower(),
		(row_data.get("ps_first_name") or "").strip().lower(),
		(row_data.get("ps_last_name") or "").strip().lower(),
		(row_data.get("ps_joining_date") or "").strip(),
	)
	combo_usable = all(combo[:3])

	if aadhar and aadhar in seen_in_file["aadhar"]:
		return _("Duplicate Aadhar Number within the uploaded file")
	if pan and pan in seen_in_file["pan"]:
		return _("Duplicate PAN within the uploaded file")
	if combo_usable and combo in seen_in_file["combo"]:
		return _("Duplicate row (same project, name & joining date) within the uploaded file")

	if aadhar and frappe.db.exists("Project Staff Details", {"ps_aadhar_number": aadhar}):
		return _("Aadhar Number already exists in Project Staff Details")
	if pan and frappe.db.exists("Project Staff Details", {"ps_pan": pan}):
		return _("PAN already exists in Project Staff Details")
	if combo_usable and frappe.db.exists(
		"Project Staff Details",
		{
			"project_no": row_data.get("project_no"),
			"ps_first_name": row_data.get("ps_first_name"),
			"ps_last_name": row_data.get("ps_last_name"),
			"ps_joining_date": row_data.get("ps_joining_date"),
		},
	):
		return _("A record with the same project, name & joining date already exists")

	if aadhar:
		seen_in_file["aadhar"].add(aadhar)
	if pan:
		seen_in_file["pan"].add(pan)
	if combo_usable:
		seen_in_file["combo"].add(combo)
	return None


def _read_bulk_import_rows(uploaded):
	"""
	Reads an uploaded CSV/XLS/XLSX file into a list of rows (list-of-lists),
	blank rows stripped. Shared by the header-preview and the actual import
	endpoint so both parse the file identically.
	"""
	if not uploaded or not uploaded.filename:
		frappe.throw(_("No file uploaded."))

	filename = uploaded.filename
	content = uploaded.read()
	ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

	if ext == "csv":
		rows = read_csv_content(content)
	elif ext in ("xlsx", "xlsm"):
		rows = read_xlsx_file_from_attached_file(fcontent=content)
	elif ext == "xls":
		rows = read_xls_file_from_attached_file(content)
	else:
		frappe.throw(_("Unsupported file type '.{0}'. Please upload a .csv, .xls or .xlsx file.").format(ext))

	rows = [r for r in rows if r and any(str(c or "").strip() for c in r)]
	if not rows:
		frappe.throw(_("The uploaded file is empty."))
	return rows


@frappe.whitelist(methods=["POST"])
def preview_bulk_import_headers():
	"""
	Reads the header row and all data rows of an uploaded CSV/XLS/XLSX file
	and returns them along with the best-guess field for each column (via
	`BULK_IMPORT_HEADER_MAP`) and the full list of fields the importer
	understands. Backs the upload page's two-step preview: first a manual
	column-mapping UI (instead of relying solely on header-name matching),
	then an editable grid of every row so mistakes can be fixed by hand
	before anything is inserted.
	"""
	uploaded = frappe.request.files.get("file") if frappe.request else None
	rows = _read_bulk_import_rows(uploaded)
	header_row, data_rows = rows[0], rows[1:]

	headers = [str(h or "").strip() for h in header_row]
	suggested_mapping = [BULK_IMPORT_HEADER_MAP.get(_normalize_bulk_import_header(h)) for h in headers]

	def stringify_row(row):
		return [str(c) if c is not None else "" for c in row]

	return {
		"headers": headers,
		"suggested_mapping": suggested_mapping,
		"sample_row": stringify_row(data_rows[0]) if data_rows else [],
		"data_rows": [stringify_row(r) for r in data_rows],
		"fields": [
			{"fieldname": fieldname, "label": label, "required": required}
			for fieldname, label, required in BULK_IMPORT_FIELD_DEFINITIONS
		],
	}


def _normalize_bulk_import_field_value(field, value):
	if value is None:
		return None
	if field in BULK_IMPORT_DATE_FIELDS:
		return _normalize_bulk_import_date(value)
	if field in BULK_IMPORT_YES_NO_FIELDS:
		return _normalize_bulk_import_yes_no(value)
	return value.strip() if isinstance(value, str) else str(value).strip()


def _build_bulk_import_row_data(raw_row, col_field):
	"""Maps one raw file row (list of cells) to a fieldname -> value dict
	using `col_field` (built from either header-name matching or an explicit
	column_mapping — see `bulk_import_project_staff_details`)."""
	row_data = {}
	for col_idx, field in enumerate(col_field):
		if not field or col_idx >= len(raw_row):
			continue
		value = _normalize_bulk_import_field_value(field, raw_row[col_idx])
		if value is not None:
			row_data[field] = value
	return row_data


def _process_bulk_import_rows(rows_data):
	"""
	Shared insert pipeline for both bulk-import entry points: takes an
	iterable of (display_row_number, row_data dict) pairs and, for each,
	runs the same missing-field check, duplicate check
	(`_find_duplicate_project_staff_row`) and insert
	(`create_project_staff_details_entry`) as the rest of this module. One
	bad row does not abort the batch — every row gets its own try/except and
	the response reports success/duplicate/error per row plus totals.
	"""
	results = []
	seen_in_file = {"aadhar": set(), "pan": set(), "combo": set()}
	counts = {"success": 0, "duplicate": 0, "error": 0}

	for idx, row_data in rows_data:
		if not any(row_data.values()):
			continue  # fully blank row — skip silently, don't count as an error

		display_name = " ".join(
			p for p in [row_data.get("ps_first_name"), row_data.get("ps_last_name")] if p
		) or f"Row {idx}"

		missing = [label for field, label in BULK_IMPORT_REQUIRED_FIELDS.items() if not row_data.get(field)]
		if missing:
			counts["error"] += 1
			results.append(
				{
					"row": idx,
					"name": display_name,
					"status": "error",
					"message": _("Missing required field(s): {0}").format(", ".join(missing)),
					# Included so the upload page can offer an inline "fix & retry"
					# form for this row instead of requiring a whole new file.
					"row_data": row_data,
				}
			)
			continue

		dup_reason = _find_duplicate_project_staff_row(row_data, seen_in_file)
		if dup_reason:
			counts["duplicate"] += 1
			results.append(
				{
					"row": idx,
					"name": display_name,
					"status": "duplicate",
					"message": dup_reason,
					"row_data": row_data,
				}
			)
			continue

		try:
			created = create_project_staff_details_entry(row_data)
			counts["success"] += 1
			results.append(
				{
					"row": idx,
					"name": display_name,
					"status": "success",
					"docname": created["docname"],
					"ps_emp_id": created["ps_emp_id"],
					"message": _("Created {0} — Employee ID {1}").format(
						created["docname"], created["ps_emp_id"]
					),
				}
			)
		except Exception as e:
			frappe.db.rollback()
			counts["error"] += 1
			results.append(
				{
					"row": idx,
					"name": display_name,
					"status": "error",
					"message": str(e),
					"row_data": row_data,
				}
			)

	return {"status": "success", "counts": counts, "results": results}


@frappe.whitelist(methods=["POST"])
def bulk_import_project_staff_details(column_mapping=None):
	"""
	Bulk-imports Project Staff Details from an uploaded CSV/XLS/XLSX file
	(multipart/form-data, field name "file" — same as the standard Frappe
	file upload pattern; binary spreadsheets don't belong in a JSON body).

	By default the first row is treated as the header row, and column
	headers are matched against `BULK_IMPORT_HEADER_MAP`
	case/space/punctuation-insensitively, so either the friendly labels used
	on the `/insert_project_staff` form ("PI Id", "First Name", ...) or the
	raw fieldnames ("pi_id", "ps_first_name", ...) both work. Unrecognized
	columns are ignored.

	`column_mapping`, if given, overrides that auto-detection: a JSON array
	aligned to the file's columns (same order as its header row), each entry
	either a Project Staff Details fieldname or null/"" to skip that column.
	This lets the upload page's manual mapping step force a specific column
	to a specific field regardless of what its header text says — useful
	when a file's headers don't match any known alias.

	See `_process_bulk_import_rows` for the shared insert/duplicate-check
	pipeline this feeds into.
	"""
	uploaded = frappe.request.files.get("file") if frappe.request else None
	rows = _read_bulk_import_rows(uploaded)

	header_row, data_rows = rows[0], rows[1:]

	if column_mapping:
		if isinstance(column_mapping, str):
			column_mapping = json.loads(column_mapping)
		valid_fields = {fieldname for fieldname, _label, _req in BULK_IMPORT_FIELD_DEFINITIONS}
		col_field = [
			field if field in valid_fields else None
			for field in (
				column_mapping[i] if i < len(column_mapping) else None for i in range(len(header_row))
			)
		]
	else:
		col_field = [BULK_IMPORT_HEADER_MAP.get(_normalize_bulk_import_header(h)) for h in header_row]

	if not any(col_field):
		frappe.throw(
			_("Could not recognize any column headers in the uploaded file. Please use the provided template.")
		)

	rows_data = (
		(idx, _build_bulk_import_row_data(raw_row, col_field))
		for idx, raw_row in enumerate(data_rows, start=2)  # 2 = first data row, header is row 1
	)
	return _process_bulk_import_rows(rows_data)


@frappe.whitelist(methods=["POST"])
def bulk_import_project_staff_details_from_rows(rows):
	"""
	Imports Project Staff Details from rows the upload page has already
	parsed and let the user hand-edit in its preview grid, instead of
	re-uploading and re-parsing the original file. `rows` is a JSON array of
	fieldname -> value dicts (fieldnames per `BULK_IMPORT_FIELD_DEFINITIONS`,
	same as `bulk_import_project_staff_details` builds from a file). Runs
	through the identical missing-field/duplicate/create pipeline — see
	`_process_bulk_import_rows`.
	"""
	if isinstance(rows, str):
		rows = json.loads(rows)
	if not rows:
		frappe.throw(_("No rows to import."))

	valid_fields = {fieldname for fieldname, _label, _req in BULK_IMPORT_FIELD_DEFINITIONS}

	def normalize_row(row):
		normalized = {}
		for field, value in (row or {}).items():
			if field not in valid_fields:
				continue
			value = _normalize_bulk_import_field_value(field, value)
			if value:
				normalized[field] = value
		return normalized

	rows_data = ((idx, normalize_row(row)) for idx, row in enumerate(rows, start=1))
	return _process_bulk_import_rows(rows_data)


@frappe.whitelist()
def save_project_staff_details_data(data):
	"""
	Creates a new Project Staff Details record or updates an existing one.
	"""
	from frappe.utils.file_manager import save_file

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Project Staff Details", doc_name)
			if doc.docstatus == 2:
				frappe.throw(_("Cannot edit a cancelled document."))
			if doc.docstatus == 1:
				frappe.throw(_("Cannot edit a submitted document. Use the workflow action endpoint instead."))
		else:
			# Enforce a single Joining Form per candidate. If a Project Staff Details
			# already exists for this candidate (application_id), do not create a
			# second one — the existing record must be opened instead.
			application_id = data.get("application_id")
			if application_id:
				existing = frappe.db.get_value(
					"Project Staff Details",
					{"application_id": application_id},
					["name", "workflow_state"],
					as_dict=True,
				)
				if existing:
					frappe.throw(
						_(
							"A Joining Form already exists for this candidate ({0}). Open the existing record instead of creating a new one."
						).format(existing.name)
					)
			doc = frappe.new_doc("Project Staff Details")

		# NOTE: ps_emp_id is intentionally NOT in this list. It is server-owned
		# and gets allocated exactly once on the first successful Submit (see
		# `submit_project_staff_details`). Accepting it from the client caused
		# the preview value (e.g. 2026TS0001) to be persisted on save, which
		# then short-circuited the real allocation at submit time and made
		# every candidate end up with the same ID.
		field_mapping = [
			"scr_id",
			"pi_id",
			"application_id",
			"project_no",
			"ps_first_name",
			"ps_middle_name",
			"ps_last_name",
			"ps_gender",
			"ps_email_id",
			"ps_phone_number",
			"ps_department",
			"ps_designation",
			"ps_date_of_birth",
			"ps_joining_date",
			"ps_term_completion_date",
			"ps_fathers_name",
			"ps_present_address",
			"ps_permanent_address",
			"ps_pan",
			"ps_aadhar_number",
			"ps_blood_group",
			"ps_maritial_status",
			"ps_basic_salary",
			"ps_hra",
			"ps_ma",
			"ps_ta",
			"ps_ta_amount",
			"ps_hostel",
			"ps_citizenship",
			"ps_aon",
			"ps_mro",
			"ps_jrn",
			"bank_account_number",
			"erp_mail",
			"workflow_state",
			"amended_from",
		]

		for field in field_mapping:
			if field in data and data[field] not in [None, ""]:
				doc.set(field, data[field])

		# Attach fields: frontend sends either an existing file URL (str)
		# or a {file_name, file_data} base64 payload (dict, handled after the
		# doc has a name).
		attach_fields = ["ps_photo", "ps_signature", "ps_medical_certificate"]
		for field in attach_fields:
			value = data.get(field)
			if isinstance(value, str) and value:
				doc.set(field, value)

		# Handle tenure details child table
		tenure_rows = data.get("table_ymed", [])
		if tenure_rows is not None:
			doc.set("table_ymed", [])
			child_fields = [
				"pstd_joining_date",
				"pstd_term_completion_date",
				"pstd_basic_salary",
				"pstd_increment",
				"pstd_hra",
				"pstd_extension_sought",
				"pstd_joining_number",
				"pstd_pi_extension_sought",
				"pstd_staff_extension_sought",
				"pstd_tentative_joining_date",
			]
			for row in tenure_rows:
				doc.append(
					"table_ymed", {f: row.get(f) for f in child_fields if row.get(f) not in [None, ""]}
				)

		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)

		# Now that the doc has a name, save any base64 file uploads and link them.
		# Frontend sends `file_data` as pure base64 (no data URL prefix). One bad
		# attachment must not abort the entire save — log and continue.
		attachments_updated = False
		for field in attach_fields:
			value = data.get(field)
			if not (isinstance(value, dict) and value.get("file_data")):
				continue

			file_data = value["file_data"]
			# Defensive: strip a `data:<mime>;base64,` prefix in case an older
			# client sends a data URL. save_file(decode=True) cannot handle it.
			if isinstance(file_data, str) and file_data.startswith("data:") and "," in file_data:
				file_data = file_data.split(",", 1)[1]

			try:
				saved_file = save_file(
					value.get("file_name", "attachment"),
					file_data,
					"Project Staff Details",
					doc.name,
					decode=True,
					is_private=1,
					df=field,
				)
				doc.set(field, saved_file.file_url)
				attachments_updated = True
			except Exception as upload_err:
				frappe.log_error(
					frappe.get_traceback(),
					f"PSD attach upload failed for field {field} on {doc.name}",
				)
				# Surface as a non-fatal message; keep going with the save.
				frappe.msgprint(
					_("Could not save attachment for {0}: {1}").format(field, upload_err),
					indicator="orange",
				)

		if attachments_updated:
			doc.save(ignore_permissions=True)

		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Save Error")
		frappe.throw(_("Failed to save Project Staff Details: {0}").format(str(e)))


@frappe.whitelist()
def get_project_staff_details_list(filters=None, limit=100000):
	"""
	Returns a paginated list of Project Staff Details records.
	"""
	try:
		parsed_filters = {}
		if filters:
			parsed_filters = json.loads(filters) if isinstance(filters, str) else filters

		records = frappe.get_all(
			"Project Staff Details",
			filters=parsed_filters,
			fields=[
				"name",
				"scr_id",
				"pi_id",
				"project_no",
				"ps_emp_id",
				"ps_first_name",
				"ps_middle_name",
				"ps_last_name",
				"ps_gender",
				"ps_email_id",
				"ps_phone_number",
				"ps_department",
				"ps_designation",
				"ps_date_of_birth",
				"ps_joining_date",
				"ps_term_completion_date",
				"ps_aon",
				"ps_jrn",
				"bank_account_number",
				"erp_mail",
				"workflow_state",
				"docstatus",
				"modified",
				"creation",
			],
			order_by="modified desc",
			limit=int(limit),
		)
		return {"status": "success", "data": records}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Details List Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_gap_from_previous_tenure(docname):
	"""
	Days between the latest tenure row's joining date and the term
	completion date of the row right before it, for a Project Staff Details
	docname. Returns None in `gap_days` if there are fewer than two rows.
	"""
	doc = frappe.get_doc("Project Staff Details", docname)
	return {"status": "success", "gap_days": doc.get_gap_from_previous_tenure()}


@frappe.whitelist()
def get_joining_by_application(application_id):
	"""
	Returns the existing Joining Form (Project Staff Details) for a candidate,
	identified by application_id, or None. Used by the form to load the existing
	record (view/edit) instead of creating a duplicate.
	"""
	if not application_id:
		return {"status": "success", "data": None}

	rec = frappe.db.get_value(
		"Project Staff Details",
		{"application_id": application_id},
		["name", "workflow_state", "docstatus"],
		as_dict=True,
	)
	# A doc is considered "submitted" (view-only) once it has moved past Draft.
	is_submitted = bool(rec) and (
		int(rec.docstatus or 0) >= 1 or (rec.workflow_state or "").strip().lower() not in ("", "draft")
	)
	return {
		"status": "success",
		"data": (
			{
				"docname": rec.name,
				"workflow_state": rec.workflow_state,
				"docstatus": rec.docstatus,
				"is_submitted": is_submitted,
			}
			if rec
			else None
		),
	}


@frappe.whitelist()
def update_joining_report_number(docname, ps_jrn):
	"""
	Update only the joining report number (ps_jrn) on a Project Staff Details doc.
	Uses db.set_value so it works even when the document is submitted, mirroring
	the appointment/medical report number update endpoints on Selection Candidate
	Details.
	"""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	try:
		frappe.db.set_value("Project Staff Details", docname, "ps_jrn", ps_jrn)
		frappe.db.commit()
		return {"status": "success", "docname": docname, "ps_jrn": ps_jrn}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update ps_jrn failed for {docname}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def delete_project_staff_details(docname):
	"""
	Deletes a Project Staff Details document (only Draft records).
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)

		if doc.docstatus == 1:
			frappe.throw(_("Cannot delete a submitted document. Cancel it first."))

		frappe.delete_doc("Project Staff Details", docname, ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "message": _("Record '{0}' deleted successfully.").format(docname)}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Delete Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_project_staff_details_workflow_actions(docname):
	"""
	Returns the workflow actions available to the current user for this doc,
	based on its current workflow_state and the user's roles.
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)
		transitions = get_transitions(doc)
		actions = list(dict.fromkeys([t.get("action") for t in transitions]))
		return {
			"status": "success",
			"workflow_state": doc.workflow_state,
			"docstatus": doc.docstatus,
			"actions": actions,
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Workflow Actions Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def perform_project_staff_details_action(docname, action):
	"""
	Applies a workflow action (Submit / Forward / Approve / Reject / Put Back ...)
	to a Project Staff Details document. Uses Frappe's apply_workflow which
	handles state transition, permission check, and docstatus updates.
	"""
	try:
		doc = frappe.get_doc("Project Staff Details", docname)
		updated = apply_workflow(doc, action)

		# On ADO, RnD approval, create / update the corresponding Frappe User.
		if action == "Approve" and "Ado_RnD" in frappe.get_roles():
			_sync_project_staff_to_user(updated)

		# Once the document reaches the 'Approved' state, capture a tenure row
		# (joining date / term completion date / basic salary) in the child table.
		if (updated.workflow_state or "").strip() == "Approved":
			_populate_tenure_on_approval(updated)
			_allocate_leave_data_on_approval(updated)

		frappe.db.commit()

		return {
			"status": "success",
			"message": _("Action '{0}' completed. New state: {1}").format(action, updated.workflow_state),
			"docname": docname,
			"workflow_state": updated.workflow_state,
			"docstatus": updated.docstatus,
			"next_actions": get_project_staff_details_workflow_actions(docname).get("actions", []),
		}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Project Staff Details Action Error")
		return {"status": "error", "message": str(e)}


def _populate_tenure_on_approval(doc):
	"""
	On approval, add a row to the 'Project Staff Tenure Details' (table_ymed)
	child table capturing the joining date, term completion date and basic salary
	from the parent. Other child fields are left blank. Idempotent: skips if a row
	with the same joining date already exists.
	"""
	joining_date = doc.get("ps_joining_date")
	term_completion_date = doc.get("ps_term_completion_date")
	basic_salary = doc.get("ps_basic_salary")

	# Nothing meaningful to record.
	if not (joining_date or term_completion_date or basic_salary):
		return

	# Avoid duplicating the row if approval is re-triggered.
	for row in doc.get("table_ymed") or []:
		if str(row.pstd_joining_date or "") == str(joining_date or "") and str(
			row.pstd_basic_salary or ""
		) == str(basic_salary or ""):
			return

	doc.append(
		"table_ymed",
		{
			"pstd_joining_date": joining_date,
			"pstd_term_completion_date": term_completion_date,
			"pstd_basic_salary": basic_salary,
		},
	)
	doc.save(ignore_permissions=True)


def round_up_to_half(value):
	return math.ceil(value * 2) / 2


def get_tenure_months(joining_date, term_completion_date):
	if not joining_date or not term_completion_date:
		return 0
	from frappe.utils import getdate

	j_date = getdate(joining_date)
	c_date = getdate(term_completion_date)
	if c_date < j_date:
		return 0
	# Calculate days difference inclusively
	days_diff = (c_date - j_date).days + 1
	# Standard average days per month is 30.437
	return int(round(days_diff / 30.437))


def _allocate_leave_data_on_approval(doc):
	try:
		# Always reload key fields from DB — the in-memory doc may predate the
		# ps_emp_id assignment that happens at Submit time.
		ps_data = frappe.db.get_value(
			"Project Staff Details",
			doc.name,
			[
				"ps_emp_id",
				"erp_mail",
				"ps_joining_date",
				"ps_term_completion_date",
				"ps_department",
			],
			as_dict=True,
		)

		if not ps_data:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: record not found in DB.",
				"Leave Allocation Error",
			)
			return

		emp_id = ps_data.ps_emp_id

		if not emp_id:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: ps_emp_id is not set.",
				"Leave Allocation Error",
			)
			return

		joining_date = ps_data.ps_joining_date or doc.ps_joining_date
		term_completion_date = ps_data.ps_term_completion_date or doc.ps_term_completion_date

		tenure_months = get_tenure_months(joining_date, term_completion_date)

		if tenure_months <= 0:
			frappe.log_error(
				f"Cannot allocate leave for Project Staff Details {doc.name}: "
				f"tenure_months={tenure_months} "
				f"(joining={joining_date}, completion={term_completion_date}).",
				"Leave Allocation Error",
			)
			return

		# Round up to the next 0.5
		cl = round_up_to_half(tenure_months * 8.0 / 11.0)
		el = round_up_to_half(max(0, (tenure_months - 1) * 2.5))

		# emp_username derived from erp_mail; optional — leave blank if not yet set.
		erp_mail = (ps_data.erp_mail or "").strip()
		emp_username = erp_mail.split("@", 1)[0] if "@" in erp_mail else ""

		department = ps_data.ps_department or doc.ps_department or ""

		# Check by both document name (autoname=field:emp_id) and by field value
		# to handle any existing records that may have been named differently.
		existing_name = frappe.db.get_value("Leave Data", {"emp_id": emp_id}, "name")

		if existing_name:
			leave_data_doc = frappe.get_doc("Leave Data", existing_name)

			if emp_username:
				leave_data_doc.emp_username = emp_username

			leave_data_doc.emp_class = "Project Staff"
			leave_data_doc.department = department
			leave_data_doc.cl = cl
			leave_data_doc.el = el

			leave_data_doc.save(ignore_permissions=True)

		else:
			leave_data_doc = frappe.new_doc("Leave Data")
			leave_data_doc.emp_id = emp_id
			leave_data_doc.emp_username = emp_username
			leave_data_doc.emp_class = "Project Staff"
			leave_data_doc.department = department
			leave_data_doc.cl = cl
			leave_data_doc.el = el

			leave_data_doc.insert(ignore_permissions=True)

	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Failed to allocate leave for Project Staff Details {doc.name}",
		)


_LINK_VALUE_CACHE = {}


def _resolve_link_value(doctype, raw_value, cutoff=0.72):
	"""
	Resolves free-text (typo'd/case-mismatched/whitespace-mismatched) input
	against an existing Link-target record's name: exact match
	case/whitespace-insensitively first, then the closest fuzzy match (via
	difflib) if it's a strong enough match, else None.

	Project Staff Details' ps_department/ps_designation are plain Data/Text
	fields hand-typed or bulk-imported over the years, but the User doctype's
	department_name/designation_name are Link fields to Department_prornd/
	Designation_prornd — an exact-text mismatch (extra space, "&" vs "and",
	different casing, ...) would otherwise hard-fail the whole User save.
	Returns None (field left unset) rather than guessing wrong when nothing
	is a close enough match.
	"""
	raw_value = (raw_value or "").strip()
	if not raw_value:
		return None

	if doctype not in _LINK_VALUE_CACHE:
		_LINK_VALUE_CACHE[doctype] = frappe.get_all(doctype, pluck="name")
	names = _LINK_VALUE_CACHE[doctype]

	for name in names:
		if name.strip().lower() == raw_value.lower():
			return name

	import difflib

	# Case-insensitive on purpose: bulk-imported/hand-typed values are
	# commonly ALL-CAPS or Title Case against a canonical list that's a mix
	# of both (e.g. "SRF DIRECT" vs "SRF(Direct)", "RESEARCH ASSOCIATE -1"
	# vs "Research Associate (1)") — comparing raw case made those fuzzy
	# ratios collapse to near-zero and fall under cutoff, or (worse) match
	# an unrelated ALL-CAPS entry instead just because it shared casing.
	lower_to_name = {name.lower(): name for name in names}
	close = difflib.get_close_matches(raw_value.lower(), lower_to_name.keys(), n=1, cutoff=cutoff)
	return lower_to_name[close[0]] if close else None


def _sync_project_staff_to_user(doc):
	"""
	Creates (or updates) a Frappe User from an approved Project Staff Details doc.
	Field mapping:
	  email                -> erp_mail               (full ERP mail address)
	  username             -> erp_mail.split('@')[0] (local part of ERP mail)
	  first/middle/last    -> ps_first_name / ps_middle_name / ps_last_name
	  full_name            -> first + middle + last
	  employee_id          -> ps_emp_id
	  department_name      -> ps_department, resolved against Department_prornd (see _resolve_link_value)
	  designation_name     -> ps_designation, resolved against Designation_prornd
	  piheadmentor_user_id -> pi_id, only if a matching User already exists
	"""
	from rndopsapp.rndopsapp.user_api.user_api import save_user_data

	erp_mail = (doc.erp_mail or "").strip()
	if not erp_mail or "@" not in erp_mail:
		frappe.log_error(
			"Project Staff Details {0} has no valid erp_mail; skipping User creation.".format(doc.name),
			"Project Staff User Sync",
		)
		return

	full_name = " ".join(p for p in [doc.ps_first_name, doc.ps_middle_name, doc.ps_last_name] if p)

	roles = ["project staff"]
	if frappe.db.exists("User", erp_mail):
		existing_roles = [r.role for r in frappe.get_doc("User", erp_mail).roles]
		for r in existing_roles:
			if r not in roles:
				roles.append(r)

	pi_id = (doc.pi_id or "").strip()

	payload = {
		"email": erp_mail,
		"username": erp_mail.split("@", 1)[0],
		"first_name": doc.ps_first_name,
		"middle_name": doc.ps_middle_name,
		"last_name": doc.ps_last_name,
		"full_name": full_name,
		"employee_id": doc.ps_emp_id,
		"department_name": _resolve_link_value("Department_prornd", doc.ps_department),
		"designation_name": _resolve_link_value("Designation_prornd", doc.ps_designation),
		"piheadmentor_user_id": pi_id if pi_id and frappe.db.exists("User", pi_id) else None,
		"enabled": 1,
		"roles": roles,
	}

	save_user_data(payload)


def _update_single_field(docname, fieldname, value):
	"""Internal helper: update exactly one field on a Project Staff Details doc."""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	try:
		frappe.db.set_value("Project Staff Details", docname, fieldname, value)
		frappe.db.commit()
		return {"status": "success", "docname": docname, fieldname: value}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"update {fieldname} failed for {docname}")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def update_joining_report_number(docname, joining_report_number):
	"""Update only the ps_jrn (Joining Report Number) field."""
	return _update_single_field(docname, "ps_jrn", joining_report_number)


@frappe.whitelist()
def backfill_project_staff_users(dry_run=1, suppress_welcome_email=1):
	"""
	One-off backfill for the gap fixed in `create_project_staff_details_entry`
	(that path set workflow_state straight to "Approved" without ever calling
	`_sync_project_staff_to_user`, so every record created that way — manual
	form entries and bulk imports alike — never got a Frappe User). Finds
	every Approved Project Staff Details with a valid erp_mail but no
	matching User, and runs `_sync_project_staff_to_user` on it.

	dry_run (default 1): only reports which records would get a User created;
	makes no changes.
	suppress_welcome_email (default 1): sets flags.no_welcome_mail on the new
	User so the backfill doesn't blast Frappe's "Send Welcome Email" to
	every affected staff member at once (they're already active, not new
	signups) — set to 0 to allow it.
	"""
	dry_run = frappe.utils.cint(dry_run)
	suppress_welcome_email = frappe.utils.cint(suppress_welcome_email)

	candidates = frappe.get_all(
		"Project Staff Details",
		filters={"workflow_state": "Approved"},
		fields=["name", "erp_mail", "ps_first_name", "ps_last_name", "ps_emp_id"],
	)

	to_create = []
	for row in candidates:
		erp_mail = (row.erp_mail or "").strip()
		if not erp_mail or "@" not in erp_mail:
			continue
		if not frappe.db.exists("User", erp_mail):
			to_create.append(row)

	if dry_run:
		return {
			"status": "success",
			"dry_run": True,
			"total_approved": len(candidates),
			"missing_user_count": len(to_create),
			"missing_user": [
				{"docname": r.name, "erp_mail": r.erp_mail, "ps_emp_id": r.ps_emp_id} for r in to_create
			],
		}

	created, failed = [], []
	# Frappe's throttle_user_creation() blocks new User inserts past
	# throttle_user_limit (default 60) in a rolling window — a spam guard
	# meant for public signup forms. It explicitly exempts frappe.flags.in_import,
	# which is exactly this case: an administrative backfill, not a signup flood.
	frappe.flags.in_import = True
	try:
		for row in to_create:
			try:
				doc = frappe.get_doc("Project Staff Details", row.name)
				if suppress_welcome_email:
					frappe.flags.no_welcome_mail = True
				_sync_project_staff_to_user(doc)
				frappe.db.commit()
				created.append({"docname": row.name, "erp_mail": row.erp_mail})
			except Exception as e:
				frappe.db.rollback()
				frappe.log_error(frappe.get_traceback(), f"Project Staff User backfill failed for {row.name}")
				failed.append({"docname": row.name, "erp_mail": row.erp_mail, "message": str(e)})
			finally:
				frappe.flags.no_welcome_mail = False
	finally:
		frappe.flags.in_import = False

	return {
		"status": "success",
		"dry_run": False,
		"total_approved": len(candidates),
		"missing_user_count": len(to_create),
		"created": created,
		"failed": failed,
	}


@frappe.whitelist()
def normalize_project_staff_designations(dry_run=1, cutoff=0.72):
	"""
	One-off backfill: `ps_designation` is free-text (hand-typed/bulk-imported
	over the years), so the same role ends up spelled many ways across
	records — "JRF GATE", "JRF(GATE)", "JRF (GATE)" — none of which line up
	with the canonical `Designation_prornd` list that `_sync_project_staff_to_user`
	already resolves against for the User sync. This backfill does the same
	resolution (`_resolve_link_value`, exact match case/whitespace-insensitively
	first, then fuzzy via difflib) directly on `ps_designation` so Desk
	filters/reports group correctly instead of splintering by spelling.

	Only touches values that resolve to a single, unambiguous, *different*
	string. Values that don't resolve to anything in Designation_prornd
	(cutoff not met) are reported under `unresolved`; values whose best
	fuzzy match ties with another equally-close candidate (e.g. "Research
	Associate (I)" scoring identically against "...(1)", "...(2)" and
	"...(3)" — the roman numeral gives no signal for which digit was meant)
	are reported under `ambiguous` instead of guessed at. Neither list is
	touched — both need a human to pick the right value.

	dry_run (default 1): reports the mapping and how many records each
	affects, without writing anything.
	"""
	import difflib

	dry_run = frappe.utils.cint(dry_run)
	cutoff = float(cutoff)

	distinct_values = frappe.get_all(
		"Project Staff Details",
		filters={"ps_designation": ["is", "set"]},
		fields=["ps_designation", "count(name) as cnt"],
		group_by="ps_designation",
	)

	canonical_names = frappe.get_all("Designation_prornd", pluck="name")
	lower_to_name = {name.lower(): name for name in canonical_names}

	changes = []
	unresolved = []
	ambiguous = []
	for row in distinct_values:
		old_value = row.ps_designation

		# Exact, case/whitespace-insensitive match short-circuits before any
		# fuzzy scoring, so it can never be flagged ambiguous.
		exact = lower_to_name.get(old_value.strip().lower())
		if exact:
			if exact != old_value:
				changes.append({"from": old_value, "to": exact, "count": row.cnt})
			continue

		scored = difflib.get_close_matches(old_value.lower(), lower_to_name.keys(), n=2, cutoff=cutoff)
		if not scored:
			unresolved.append({"value": old_value, "count": row.cnt})
			continue

		if len(scored) > 1:
			top_ratio = difflib.SequenceMatcher(None, old_value.lower(), scored[0]).ratio()
			runner_up_ratio = difflib.SequenceMatcher(None, old_value.lower(), scored[1]).ratio()
			if top_ratio == runner_up_ratio:
				ambiguous.append(
					{
						"value": old_value,
						"count": row.cnt,
						"candidates": [lower_to_name[scored[0]], lower_to_name[scored[1]]],
					}
				)
				continue

		changes.append({"from": old_value, "to": lower_to_name[scored[0]], "count": row.cnt})

	if not dry_run:
		for change in changes:
			frappe.db.set_value(
				"Project Staff Details",
				{"ps_designation": change["from"]},
				"ps_designation",
				change["to"],
			)
		frappe.db.commit()

	return {
		"status": "success",
		"dry_run": bool(dry_run),
		"changes": changes,
		"records_affected": sum(c["count"] for c in changes),
		"unresolved": unresolved,
		"ambiguous": ambiguous,
	}


@frappe.whitelist()
def submit_project_staff_details(docname):
	"""
	Staff-facing submit endpoint. Triggers the 'Submit' workflow action
	(Draft -> Pending HoS Approval) and, on the *first* submit, allocates a
	fresh Employee ID for the candidate (idempotent: re-submitting an already
	allotted record reuses the existing ps_emp_id rather than burning a new
	one from the series).

	Returns the allotted `ps_emp_id` alongside the workflow result so the UI
	can surface it in the post-submit confirmation alert without an extra
	round trip.
	"""
	if not docname:
		return {"status": "error", "message": "docname is required"}

	if not frappe.db.exists("Project Staff Details", docname):
		return {"status": "error", "message": f"Document '{docname}' not found"}

	# Capture the workflow state BEFORE we attempt the transition. We only
	# allocate a fresh Employee ID when this call is the doc's first Submit
	# (was Draft / blank going in). Doing the allocation AFTER apply_workflow
	# succeeds means a failed/forbidden transition can't burn a series number.
	before_state = (
		(frappe.db.get_value("Project Staff Details", docname, "workflow_state") or "").strip().lower()
	)

	result = perform_project_staff_details_action(docname, "Submit")

	if isinstance(result, dict) and result.get("status") == "success":
		if before_state in ("", "draft"):
			# First successful Submit — allocate a fresh ID, overwriting any
			# stale preview value (e.g. "2026TS0001") that earlier client builds
			# may have written into ps_emp_id via the save handler.
			emp_id = generate_emp_id()
			frappe.db.set_value("Project Staff Details", docname, "ps_emp_id", emp_id)
			frappe.db.commit()
		else:
			emp_id = frappe.db.get_value("Project Staff Details", docname, "ps_emp_id")
		result["ps_emp_id"] = emp_id

		if (result.get("workflow_state") or "").strip() == "Approved":
			_allocate_leave_data_on_approval(frappe.get_doc("Project Staff Details", docname))
			frappe.db.commit()
	return result


@frappe.whitelist()
def get_my_project_staff_details():
	"""
	Return the Project Staff Details row whose `erp_mail` matches the
	logged-in user's email. Uses session user server-side so the client
	does not need List permission on Project Staff Details.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)

	rows = frappe.get_all(
		"Project Staff Details",
		filters={"erp_mail": user},
		fields=[
			"name",
			"erp_mail",
			"ps_first_name",
			"ps_middle_name",
			"ps_last_name",
			"ps_department",
			"ps_designation",
			"project_no",
			"bank_account_number",
			"ps_aadhar_number",
			"ps_pan",
			"ps_joining_date",
			"ps_term_completion_date",
		],
		limit=1,
		ignore_permissions=True,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_my_basic_details():
	"""
	Return Basic Details for the currently logged-in user by joining the
	User doctype's `username` against the part of `erp_mail` before '@'
	in Project Staff Details.
	"""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)

	rows = frappe.db.sql(
		"""
		SELECT
			psd.name,
			psd.erp_mail,
			psd.ps_first_name,
			psd.ps_middle_name,
			psd.ps_last_name,
			psd.ps_fathers_name,
			psd.ps_gender,
			psd.ps_date_of_birth,
			psd.ps_blood_group,
			psd.ps_maritial_status,
			psd.ps_citizenship,
			psd.ps_phone_number,
			psd.ps_email_id,
			psd.ps_present_address,
			psd.ps_permanent_address,
			psd.ps_department,
			COALESCE(dept.dept_name, psd.ps_department) AS ps_department_name,
			psd.ps_designation,
			psd.ps_emp_id,
			psd.project_no,
			pr.project_title AS project_name,
			psd.ps_joining_date,
			psd.ps_term_completion_date,
			psd.ps_basic_salary,
			psd.bank_account_number,
			psd.ps_aadhar_number,
			psd.ps_pan,
			psd.ps_photo,
			u.username,
			u.full_name,
			u.email
		FROM `tabProject Staff Details` psd
		INNER JOIN `tabUser` u
			ON u.username = SUBSTRING_INDEX(psd.erp_mail, '@', 1)
		LEFT JOIN `tabDepartment_prornd` dept
			ON dept.name = psd.ps_department
		LEFT JOIN `tabProject Registration` pr
			ON pr.project_no = psd.project_no
		WHERE u.name = %(user)s
		LIMIT 1
		""",
		{"user": user},
		as_dict=True,
	)
	if not rows:
		return None

	res = dict(rows[0])

	# Fetch Date of Last Extension
	doc = frappe.get_doc("Project Staff Details", res["name"])
	res["ex_last_ex_date"] = doc.get_date_of_last_extension()

	# Fetch latest tenure details from the child table
	tenures = doc.get("table_ymed") or []
	valid_tenures = [t for t in tenures if t.pstd_joining_date]
	res["tenures"] = []
	if valid_tenures:
		from frappe.utils import getdate

		sorted_tenures = sorted(valid_tenures, key=lambda x: getdate(x.pstd_joining_date))
		latest_tenure = sorted_tenures[-1]

		# Preserve original parent ps_joining_date and ps_term_completion_date.
		# Expiry of present tenure is fetched from the latest tenure's completion date.
		res["ex_date_of_expiry"] = latest_tenure.pstd_term_completion_date
		res["ps_basic_salary"] = latest_tenure.pstd_basic_salary

		# Full tenure history (each term's joining + completion + basic), oldest first.
		res["tenures"] = [
			{
				"joining_date": str(t.pstd_joining_date) if t.pstd_joining_date else None,
				"term_completion_date": str(t.pstd_term_completion_date) if t.pstd_term_completion_date else None,
				"basic_salary": t.pstd_basic_salary,
			}
			for t in sorted_tenures
		]

	j_date = res.get("ps_joining_date")
	if j_date:
		from frappe.utils import getdate, today

		jd = getdate(j_date)
		cd = getdate(today())
		if cd >= jd:
			days_diff = (cd - jd).days + 1
			months = int(days_diff / 30.437)
			if months < 1:
				res["no_of_months_worked"] = 0
				res["no_of_days_worked"] = days_diff
			else:
				res["no_of_months_worked"] = months
				res["no_of_days_worked"] = 0
		else:
			res["no_of_months_worked"] = 0
			res["no_of_days_worked"] = 0
	else:
		res["no_of_months_worked"] = 0
		res["no_of_days_worked"] = 0

	return res
