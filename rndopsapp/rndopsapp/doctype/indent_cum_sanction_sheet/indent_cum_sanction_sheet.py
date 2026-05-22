# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json
from html import escape
from urllib.parse import quote, unquote, urlparse

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


# =============================================================================
# HELPER
# =============================================================================

def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None
	expression = str(expression).strip()
	if expression.startswith("eval:"):
		return expression[5:].strip()
	return expression


# =============================================================================
# INDENT TYPE CONSTANTS
# =============================================================================

INDENT_TYPE_PROPRIETARY = "Proprietary Purchase with Proprietary certificate from the OEM"
INDENT_TYPE_STANDARDIZED = "Standerdised/ Emergent Purchase"
INDENT_TYPE_REPAIR = "Repair/ Repleacement"
INDENT_TYPE_AMC = "Annual Maintenance Contract"
INDENT_TYPE_RATE_CONTRACT = "Rate Contract Purchase"

INDENT_TYPES = [
	INDENT_TYPE_PROPRIETARY,
	INDENT_TYPE_STANDARDIZED,
	INDENT_TYPE_REPAIR,
	INDENT_TYPE_AMC,
	INDENT_TYPE_RATE_CONTRACT,
]

DOCTYPE = "Indent Cum Sanction Sheet"
SIGNED_PO_FIELD = "icss_signed_po_file"
SEND_TO_DIRECTOR_FIELD = "send_to_director"
DIRECTOR_SIGNED_PDF_FIELD = "director_signed_pdf"
DIRECTOR_APPROVAL_REQUIRED_FIELD = "director_approval_required"
PO_GENERATED_STATE = "PO Generated"
PO_DELIVERED_STATE = "PO Delivered"
PENDING_DEAN_APPROVAL_STATE = "Pending Dean Approval"
ICSS_MINIO_FOLDER = "indent_cum_sanction_sheet"
ICSS_APPLICANT_ATTACHMENTS_FOLDER = "applicant_attachments"
ICSS_DIRECTOR_APPROVAL_FOLDER = "director_approval"
ICSS_SIGNED_PO_FOLDER = "signed_po"
MINIO_BROWSER_BASE_URL = "http://172.16.135.118:9001/browser/rnd-files"
PO_DELIVERY_UPLOAD_ACTIONS = {"Upload Signed PO", "Deliver PO"}
DIRECTOR_MARK_ALLOWED_ROLES = {"Dean, RnD", "System Manager"}
DIRECTOR_UPLOAD_ALLOWED_ROLES = {"staff, RnD", "Staff, RnD", "RnD Staff", "R&D Staff", "System Manager"}
ICSS_PUT_BACK_ACTION_PREFIX = "Put Back to "
ICSS_PUT_BACK_TARGETS = {
	"Requestor": "Draft",
	"PI": "Pending PI Approval",
	"Staff": "Pending Staff Approval",
	"HoS": "Pending HoS Approval",
}
ICSS_PUT_BACK_RULES = {
	"Pending PI Approval": {
		"roles": ["Permanent Employee", "head_approver_1", "HoD", "System Manager"],
		"targets": ["Requestor"],
	},
	"Pending Staff Approval": {
		"roles": ["staff, RnD", "System Manager"],
		"targets": ["PI", "Requestor"],
	},
	"Pending HoS Approval": {
		"roles": ["Hos, RnD (Head of Section, RnD)", "System Manager"],
		"targets": ["Staff", "PI", "Requestor"],
	},
	"Pending Dean Approval": {
		"roles": ["Dean, RnD", "System Manager"],
		"targets": ["HoS", "Staff", "PI", "Requestor"],
	},
	"Pending Associate Dean": {
		"roles": ["Ado_RnD", "System Manager"],
		"targets": ["HoS", "Staff", "PI", "Requestor"],
	},
}

# Sub-DocType Mapping
SUB_DOCTYPE_MAP = {
	INDENT_TYPE_PROPRIETARY: "proprietary_purchase",
	INDENT_TYPE_STANDARDIZED: "standerdized_purchase",
	INDENT_TYPE_REPAIR: "repair_replacement",
	INDENT_TYPE_AMC: "AMC",
	INDENT_TYPE_RATE_CONTRACT: "Rate Contract",
}

# Workflow Mapping
WORKFLOW_MAP = {
	INDENT_TYPE_PROPRIETARY: "Proprietary Purchase Workflow",
	INDENT_TYPE_STANDARDIZED: "Standardized Purchase Workflow",
	INDENT_TYPE_REPAIR: "Repair Replacement Workflow",
	INDENT_TYPE_AMC: "AMC Workflow",
	INDENT_TYPE_RATE_CONTRACT: "Rate Contract Workflow",
}

CHILD_FIELD_API_MAP = {
	"proprietary_purchase": "rndopsapp.rndopsapp.doctype.proprietary_purchase.proprietary_purchase.get_proprietary_purchase_fields",
	"standerdized_purchase": "rndopsapp.rndopsapp.doctype.standerdized_purchase.standerdized_purchase.get_standerdized_purchase_fields",
	"repair_replacement": "rndopsapp.rndopsapp.doctype.repair_replacement.repair_replacement.get_repair_replacement_fields",
	"Rate Contract": "rndopsapp.rndopsapp.doctype.rate_contract.rate_contract.get_rate_contract_fields",
}


def _get_sub_doctype(indent_type):
	"""Return the mapped child doctype for an indent type."""
	return SUB_DOCTYPE_MAP.get(indent_type)


def _get_workflow_eval_context(doc):
	"""Context used by ICSS workflow conditions."""
	return {"doc": doc, "frappe": frappe, "flt": flt}


def _get_child_api_response(sub_doctype_name, doc_name=None):
	"""Fetch child doctype metadata using its own API when available."""
	method_path = CHILD_FIELD_API_MAP.get(sub_doctype_name)
	if method_path:
		try:
			method = frappe.get_attr(method_path)
			return method(doc_name=doc_name)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"ICSS Child API Error: {sub_doctype_name}",
			)

	return _build_doctype_fields_response(sub_doctype_name, doc_name=doc_name)


def _build_doctype_fields_response(doctype_name, doc_name=None):
	"""Generic metadata response for doctypes without a dedicated API."""
	meta = frappe.get_meta(doctype_name)
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
			"default": f.default,
			"description": f.description,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
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
					"in_list_view": cf.in_list_view,
					"read_only": cf.read_only,
					"fetch_from": cf.fetch_from,
					"default": cf.default,
				}
				for cf in child_meta.fields
			]
		fields.append(field_data)

	prefill_data = {}
	if doc_name:
		try:
			prefill_data = frappe.get_doc(doctype_name, doc_name).as_dict()
		except Exception:
			pass

	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": doctype_name, "enabled": 1},
			fields=["name", "script", "view"],
		)
		client_scripts = [
			{"name": script.name, "script": script.script, "view": script.view}
			for script in scripts
		]
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": {},
		"client_scripts": client_scripts,
		"computation_rules": {},
	}


def _normalize_payload(data):
	"""Parse API payloads whether they arrive as JSON string or dict."""
	if isinstance(data, str):
		return json.loads(data)
	return data or {}


def _clean_scalar_value(value):
	"""Normalize scalar values coming from the frontend."""
	if value == "null":
		return None
	return value


def _resolve_link_value(df, value, payload):
	"""Resolve common frontend display labels back to real Link values."""
	clean_value = _clean_scalar_value(value)
	if not clean_value or df.fieldtype != "Link" or not df.options or not isinstance(clean_value, str):
		return clean_value

	if df.options == "User":
		# Prefer the paired webmail field when frontend sends the display name.
		if df.fieldname == "icss_applicant_name":
			return payload.get("icss_applicant_webmail_id") or payload.get("webmail_id") or clean_value
		if df.fieldname == "icss_applying_for_name":
			return payload.get("icss_applying_for_mail") or payload.get("applying_for_mail") or clean_value

		if frappe.db.exists("User", clean_value):
			return clean_value

		user_name = frappe.db.get_value("User", {"full_name": clean_value}, "name")
		return user_name or clean_value

	if df.options == "Department_prornd":
		if frappe.db.exists("Department_prornd", clean_value):
			return clean_value

		dept_name = frappe.db.get_value("Department_prornd", {"dept_name": clean_value}, "name")
		return dept_name or clean_value

	if frappe.db.exists(df.options, clean_value):
		return clean_value

	return clean_value


def _strip_row_system_fields(row_dict):
	"""Drop transient row keys before appending table rows."""
	for key in (
		"name",
		"creation",
		"modified",
		"owner",
		"modified_by",
		"docstatus",
		"parent",
		"parentfield",
		"parenttype",
		"idx",
	):
		row_dict.pop(key, None)


def _get_uploaded_file_content(file_keys=None):
	"""Read an uploaded multipart file using the first matching key."""
	request = getattr(frappe.local, "request", None)
	files = getattr(request, "files", None)
	if not files:
		return None, None

	for key in file_keys or ("file",):
		uploaded = files.get(key)
		if uploaded:
			return uploaded.filename, uploaded.stream.read()

	return None, None


def _decode_base64_file(file_data):
	"""Decode a base64/data-URI file payload."""
	import base64

	file_data_str = file_data
	if isinstance(file_data_str, str) and "," in file_data_str:
		file_data_str = file_data_str.split(",", 1)[1]
	return base64.b64decode(file_data_str)


def _get_icss_docname_from_payload(doctype_name, doc_name, payload=None):
	"""Return the parent ICSS docname for parent or child attachment storage."""
	payload = payload or {}
	if doctype_name == DOCTYPE:
		return doc_name

	icss_docname = payload.get("indent_cum_sanction_sheet_id")
	if icss_docname:
		return icss_docname

	try:
		meta = frappe.get_meta(doctype_name)
		if meta.has_field("indent_cum_sanction_sheet_id") and frappe.db.exists(doctype_name, doc_name):
			return frappe.db.get_value(doctype_name, doc_name, "indent_cum_sanction_sheet_id")
	except Exception:
		pass

	return None


def _get_icss_project_storage_id_from_values(project_no=None, project_ref=None, icss_docname=None):
	"""Resolve project folder ID from payload values or the parent ICSS document."""
	if project_no:
		return project_no

	if project_ref:
		linked_project_no = frappe.db.get_value("Project Registration", project_ref, "project_no")
		return linked_project_no or project_ref

	if icss_docname and frappe.db.exists(DOCTYPE, icss_docname):
		icss_doc = frappe.get_doc(DOCTYPE, icss_docname)
		return _get_icss_project_storage_id(icss_doc)

	return icss_docname


def _get_icss_category_minio_folder(project_id, icss_docname, category):
	"""Return Project_Registration-scoped ICSS category folder."""
	return f"{ICSS_MINIO_FOLDER}/{icss_docname}/{category}".strip("/")


def _save_icss_attachment_to_minio(value, doctype_name, doc_name, fieldname, payload=None):
	"""Save an ICSS-related attachment under the project/docname/category folder."""
	if not (isinstance(value, dict) and value.get("file_data")):
		return None

	icss_docname = _get_icss_docname_from_payload(doctype_name, doc_name, payload)
	if not icss_docname:
		return None

	project_id = _get_icss_project_storage_id_from_values(
		project_no=(payload or {}).get("project_no"),
		project_ref=(payload or {}).get("project_ref"),
		icss_docname=icss_docname,
	)
	if not project_id:
		return None

	from rndopsapp.minio import get_rnd_file_service

	file_service = get_rnd_file_service()
	upload_result = file_service.save_file(
		filename=value.get("file_name") or value.get("filename") or "attachment",
		content=_decode_base64_file(value["file_data"]),
		is_private=True,
		doctype="Project Registration",
		docname=project_id,
		folder=_get_icss_category_minio_folder(project_id, icss_docname, ICSS_APPLICANT_ATTACHMENTS_FOLDER),
		use_hash=False,
	)
	if not upload_result.get("status"):
		frappe.throw(_("ICSS attachment upload failed: {0}").format(upload_result.get("message")))

	return upload_result.get("data", {}).get("file_url")


def _save_file_field(value, doctype_name, doc_name, fieldname, payload=None):
	"""Persist a parent or child attachment and return the saved URL."""
	from frappe.utils.file_manager import save_file

	if isinstance(value, dict) and value.get("file_data"):
		icss_file_url = _save_icss_attachment_to_minio(
			value,
			doctype_name,
			doc_name,
			fieldname,
			payload=payload,
		)
		if icss_file_url:
			return icss_file_url

		saved_file = save_file(
			value.get("file_name", "attachment"),
			value["file_data"],
			doctype_name,
			doc_name,
			decode=True,
			is_private=1,
			df=fieldname,
		)
		return saved_file.file_url
	if isinstance(value, str):
		return value
	return None


def _save_doc_from_payload(doctype_name, data, allow_submitted_edit=False, skip_subdoctype_sync=False):
	"""Create or update a doctype from a generic payload without committing."""
	payload = _normalize_payload(data)
	doc_name = payload.get("name")
	is_new = False

	if doc_name and frappe.db.exists(doctype_name, doc_name):
		doc = frappe.get_doc(doctype_name, doc_name)
		if doc.docstatus != 0 and not allow_submitted_edit:
			frappe.throw(_("Cannot edit a submitted or cancelled {0}.").format(doctype_name))
	else:
		doc = frappe.new_doc(doctype_name)
		is_new = True

	meta = frappe.get_meta(doctype_name)
	deferred_fields = []

	for fieldname, value in payload.items():
		if fieldname in ("name", "doctype", "docstatus"):
			continue
		if not meta.has_field(fieldname):
			continue

		df = meta.get_field(fieldname)
		if df.fieldtype in ("Attach", "Attach Image", "Table"):
			deferred_fields.append((fieldname, value))
			continue

		clean_value = _resolve_link_value(df, value, payload)
		if clean_value is not None:
			doc.set(fieldname, clean_value)

	doc.flags.ignore_permissions = True
	if doctype_name == DOCTYPE and skip_subdoctype_sync:
		doc.flags.skip_icss_subdoctype_sync = True
	if is_new:
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
	else:
		doc.save(ignore_permissions=True)

	for fieldname, value in deferred_fields:
		df = meta.get_field(fieldname)
		if df.fieldtype == "Table":
			if isinstance(value, str):
				try:
					value = json.loads(value)
				except Exception:
					value = []
			if isinstance(value, list):
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				for child_row in value:
					row_dict = dict(child_row or {})
					_strip_row_system_fields(row_dict)
					for cf in child_meta.fields:
						if cf.fieldtype in ("Attach", "Attach Image") and row_dict.get(cf.fieldname):
							row_dict[cf.fieldname] = _save_file_field(
								row_dict.get(cf.fieldname),
								doctype_name,
								doc.name,
								cf.fieldname,
								payload=payload,
							)
					doc.append(fieldname, row_dict)
		else:
			saved_url = _save_file_field(value, doctype_name, doc.name, fieldname, payload=payload)
			if saved_url:
				doc.set(fieldname, saved_url)

	if doctype_name == DOCTYPE and skip_subdoctype_sync:
		doc.flags.skip_icss_subdoctype_sync = True
	doc.save(ignore_permissions=True)
	return doc


def _get_linked_child_doc(parent_doc):
	"""Load the child document linked to a parent ICSS doc."""
	if not parent_doc or not parent_doc.sub_doctype_reference or not parent_doc.icss_indent_type:
		return None

	sub_doctype_name = _get_sub_doctype(parent_doc.icss_indent_type)
	if not sub_doctype_name:
		return None

	try:
		return frappe.get_doc(sub_doctype_name, parent_doc.sub_doctype_reference)
	except Exception:
		return None


def _serialize_icss_composite(parent_doc, child_doc=None):
	"""Return parent JSON with nested child JSON for the frontend."""
	composite = parent_doc.as_dict()
	if child_doc:
		composite["child_document"] = child_doc.as_dict()
		composite["child_doctype"] = child_doc.doctype
	return composite


def _get_icss_project_storage_id(doc):
	"""Return the project folder ID used for ICSS MinIO storage."""
	project_no = doc.get("project_no")
	if project_no:
		return project_no

	project_ref = doc.get("project_ref")
	if project_ref:
		project_no = frappe.db.get_value("Project Registration", project_ref, "project_no")
		return project_no or project_ref

	return doc.name


def _get_icss_doc_minio_folder(doc):
	"""Return object-storage folder for one ICSS document."""
	return f"Project_Registration/{_get_icss_project_storage_id(doc)}/{ICSS_MINIO_FOLDER}/{doc.name}"


def _get_icss_category_object_folder(doc, category):
	"""Return object-storage category folder for one ICSS document."""
	return f"{_get_icss_doc_minio_folder(doc)}/{category}".strip("/")


def _get_icss_signed_po_minio_folder(doc):
	"""Return object-storage folder for ICSS signed PO files."""
	return _get_icss_category_object_folder(doc, ICSS_SIGNED_PO_FOLDER)


def _get_icss_director_approval_minio_folder(doc):
	"""Return object-storage folder for Director-approved ICSS PDF files."""
	return _get_icss_category_object_folder(doc, ICSS_DIRECTOR_APPROVAL_FOLDER)


def _as_int_bool(value):
	"""Normalize common truthy/falsy request values to 0 or 1."""
	if isinstance(value, str):
		return 1 if value.strip().lower() in ("1", "true", "yes", "on") else 0
	return 1 if value else 0


def _get_minio_browser_url(file_url):
	"""Return MinIO console browser URL for a stored object path."""
	if not file_url:
		return None
	object_key = _normalize_minio_file_url(file_url).strip("/")
	if not object_key:
		return None
	return f"{MINIO_BROWSER_BASE_URL}/{quote(object_key, safe='')}"


def _normalize_minio_file_url(file_url):
	"""Normalize browser/bucket URLs to the internal Frappe MinIO file_url path."""
	if not file_url:
		return None

	normalized = str(file_url).strip()
	if not normalized:
		return None

	parsed = urlparse(normalized)
	if parsed.scheme and parsed.netloc and "/browser/rnd-files/" in parsed.path:
		object_key = parsed.path.split("/browser/rnd-files/", 1)[1]
		normalized = "/" + unquote(object_key).strip("/")
	elif normalized.startswith("/rnd-files/"):
		normalized = "/" + normalized.split("/rnd-files/", 1)[1].strip("/")
	elif normalized.startswith("rnd-files/"):
		normalized = "/" + normalized.split("rnd-files/", 1)[1].strip("/")
	elif normalized.startswith("prod-rnd-files/"):
		normalized = "/" + normalized.split("prod-rnd-files/", 1)[1].strip("/")
	elif normalized.startswith("Project_Registration/"):
		normalized = "/" + normalized

	return normalized.rstrip("/")


def _ensure_icss_file_attachment(docname, file_url, is_private=0, attached_to_field=SIGNED_PO_FIELD):
	"""Create a File attachment row for a signed PO URL without File validation issues."""
	file_url = _normalize_minio_file_url(file_url)
	if not file_url:
		return None

	existing_file = frappe.db.get_value(
		"File",
		{
			"file_url": file_url,
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": docname,
		},
		"name",
	)
	if existing_file:
		return frappe.db.get_value("File", existing_file, "file_url") or file_url

	file_doc_name = frappe.generate_hash(length=10)
	now = frappe.utils.now()
	file_name = file_url.rsplit("/", 1)[-1] or "signed_po"
	frappe.db.sql("""
		INSERT INTO `tabFile`
			(name, file_name, file_url, is_private,
			 attached_to_doctype, attached_to_name, attached_to_field,
			 owner, creation, modified, modified_by, docstatus, idx)
		VALUES
			(%(name)s, %(file_name)s, %(file_url)s, %(is_private)s,
			 %(attached_to_doctype)s, %(attached_to_name)s, %(attached_to_field)s,
			 %(owner)s, %(creation)s, %(modified)s, %(modified_by)s, 0, 0)
	""", {
		"name": file_doc_name,
		"file_name": file_name,
		"file_url": file_url,
		"is_private": _as_int_bool(is_private),
		"attached_to_doctype": DOCTYPE,
		"attached_to_name": docname,
		"attached_to_field": attached_to_field,
		"owner": frappe.session.user,
		"creation": now,
		"modified": now,
		"modified_by": frappe.session.user,
	})
	return file_url


def _save_uploaded_icss_file(doc, category, file_keys=None, is_private=0, file_name=None, file_data=None, default_filename="attachment"):
	"""Save an uploaded ICSS file to the project/docname/category MinIO folder."""
	content = None
	filename = None

	filename, content = _get_uploaded_file_content(file_keys or ("file",))

	if content is None and getattr(frappe.local, "uploaded_file", None):
		content = frappe.local.uploaded_file
		filename = frappe.local.uploaded_filename

	if content is None and file_data:
		filename = file_name or default_filename
		content = _decode_base64_file(file_data)

	if content is None:
		return None

	from rndopsapp.minio import get_rnd_file_service

	file_service = get_rnd_file_service()
	upload_result = file_service.save_file(
		filename=filename or default_filename,
		content=content,
		is_private=bool(_as_int_bool(is_private)),
		doctype="Project Registration",
		docname=_get_icss_project_storage_id(doc),
		folder=f"{ICSS_MINIO_FOLDER}/{doc.name}/{category}",
		use_hash=False,
	)
	if not upload_result.get("status"):
		frappe.throw(_("ICSS file upload to MinIO failed: {0}").format(upload_result.get("message")))

	return upload_result.get("data", {}).get("file_url")


def _save_uploaded_signed_po_file(doc, is_private=0, file_name=None, file_data=None):
	"""Save an uploaded signed PO file to the ICSS MinIO signed PO folder."""
	return _save_uploaded_icss_file(
		doc,
		ICSS_SIGNED_PO_FOLDER,
		file_keys=("file", "signed_po", "signed_po_attachment", "icss_signed_po_file"),
		is_private=is_private,
		file_name=file_name,
		file_data=file_data,
		default_filename="signed_po",
	)


def _save_uploaded_director_pdf_file(doc, is_private=0, file_name=None, file_data=None):
	"""Save an uploaded Director-approved ICSS PDF to the Director approval folder."""
	return _save_uploaded_icss_file(
		doc,
		ICSS_DIRECTOR_APPROVAL_FOLDER,
		file_keys=("file", "director_pdf", "director_signed_pdf", "director_approval_pdf"),
		is_private=is_private,
		file_name=file_name,
		file_data=file_data,
		default_filename="director-signed.pdf",
	)


def _get_icss_approval_amount(doc):
	"""Return the normalized amount used for HoS approval routing."""
	child_doc = _get_linked_child_doc(doc)
	indent_type = getattr(doc, "icss_indent_type", None)

	if indent_type == INDENT_TYPE_PROPRIETARY:
		if child_doc and hasattr(child_doc, "pp_grand_total"):
			return flt(child_doc.pp_grand_total)
		return flt(getattr(doc, "icss_grand_total", 0))

	if indent_type == INDENT_TYPE_STANDARDIZED:
		if child_doc and hasattr(child_doc, "sp_grand_total"):
			return flt(child_doc.sp_grand_total)
		return flt(getattr(doc, "icss_grand_total", 0))

	if indent_type == INDENT_TYPE_REPAIR:
		if child_doc and hasattr(child_doc, "rr_grand_total"):
			return flt(child_doc.rr_grand_total)
		return flt(getattr(doc, "icss_repair_grand_total", 0))

	if indent_type == INDENT_TYPE_AMC:
		if child_doc and hasattr(child_doc, "amc_grand_total"):
			return flt(child_doc.amc_grand_total)
		return flt(getattr(doc, "icss_amc_grand_total", 0))

	if indent_type == INDENT_TYPE_RATE_CONTRACT:
		if child_doc and hasattr(child_doc, "rate_contract_grand_total"):
			return flt(child_doc.rate_contract_grand_total)
		return flt(getattr(doc, "icss_grand_total", 0))

	return flt(getattr(doc, "icss_grand_total", 0))


def _get_icss_account_head_text(doc):
	"""Return account/budget head text used to identify Equipment purchases."""
	account_head = (
		doc.get("icss_account_head")
		or doc.get("icss_other_account_head")
		or ""
	)
	account_head_text = account_head

	if account_head:
		try:
			budget_head = frappe.db.get_value(
				"Budget Head",
				account_head,
				["budget_head", "name"],
				as_dict=True,
			)
			if budget_head:
				account_head_text = budget_head.budget_head or budget_head.name or account_head
		except Exception:
			pass

	return account_head_text or ""


def _is_icss_director_approval_required(doc):
	"""Return whether ICSS needs Director-approved PDF before Dean approval."""
	amount = _get_icss_approval_amount(doc)
	account_head_text = _get_icss_account_head_text(doc)
	is_equipment = "equipment" in str(account_head_text or "").lower()

	if is_equipment:
		return amount > 1000000

	return amount > 300000


def _set_director_approval_required_value(doc):
	"""Set cached Director approval requirement if the field exists."""
	try:
		if frappe.get_meta(DOCTYPE).has_field(DIRECTOR_APPROVAL_REQUIRED_FIELD):
			doc.set(DIRECTOR_APPROVAL_REQUIRED_FIELD, 1 if _is_icss_director_approval_required(doc) else 0)
	except Exception:
		# Never block save only because the informational cache could not refresh.
		pass


def _has_any_role(user_roles, allowed_roles):
	"""Return true when current user has one of the allowed roles."""
	roles = set(user_roles or [])
	return (
		bool(roles.intersection(set(allowed_roles or ())))
		or "System Manager" in roles
		or frappe.session.user == "Administrator"
	)


def _get_available_icss_put_back_action_rows(doc, user_roles=None):
	"""Build put-back actions available to the current user and ICSS state."""
	current_state = doc.workflow_state or "Draft"
	rule = ICSS_PUT_BACK_RULES.get(current_state)
	if not rule or not _has_any_role(user_roles or frappe.get_roles(frappe.session.user), rule.get("roles")):
		return []

	return [
		{
			"target": target,
			"label": _("Put Back to {0}").format(target),
			"next_state": ICSS_PUT_BACK_TARGETS[target],
		}
		for target in rule.get("targets", [])
		if target in ICSS_PUT_BACK_TARGETS
	]


def _get_icss_put_back_target_from_action(action):
	"""Extract dynamic put-back target from a workflow-style action label."""
	action_text = str(action or "").strip()
	if not action_text.startswith(ICSS_PUT_BACK_ACTION_PREFIX):
		return None
	return action_text[len(ICSS_PUT_BACK_ACTION_PREFIX):].strip() or None


def _clear_icss_director_fields_for_put_back(current_state):
	"""Return Director approval fields to clear when moving back from Dean."""
	if current_state != PENDING_DEAN_APPROVAL_STATE:
		return {}

	return {
		SEND_TO_DIRECTOR_FIELD: 0,
		DIRECTOR_SIGNED_PDF_FIELD: None,
		DIRECTOR_APPROVAL_REQUIRED_FIELD: 0,
	}


def _add_icss_put_back_comment(docname, current_state, next_state, target, reason=None):
	"""Add an auditable workflow comment for dynamic put-back actions."""
	reason_text = str(reason or "").strip()
	content = (
		f"Put back to {escape(str(target))} ({escape(str(next_state))}) "
		f"by {escape(str(frappe.session.user))} from {escape(str(current_state))}."
	)
	if reason_text:
		content += f" Reason: {escape(reason_text)}"

	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Workflow",
		"reference_doctype": DOCTYPE,
		"reference_name": docname,
		"content": content,
	}).insert(ignore_permissions=True)


def _resolve_hos_next_state(doc, requested_action, workflow, user_roles):
	"""Override HoS approval routing based on the ICSS amount threshold."""
	current_state = doc.workflow_state or "Draft"
	if current_state != "Pending HoS Approval" or requested_action not in ("Approve", "Forward"):
		return None

	amount = _get_icss_approval_amount(doc)
	target_state = "Pending Dean Approval" if amount > 100000 else "Pending Associate Dean"

	for transition in workflow.transitions:
		if not (
			transition.state == current_state
			and transition.action == requested_action
			and transition.next_state == target_state
		):
			continue

		allowed_roles = transition.get("allowed") or []
		if isinstance(allowed_roles, str):
			allowed_roles = [allowed_roles]
		if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
			continue

		return target_state

	frappe.throw(
		_("Workflow transition for HoS routing to '{0}' is missing.").format(target_state)
	)


def _resolve_initial_submit_state(doc, requested_action, workflow, user_roles):
	"""Route initial ICSS submit based on the initiator role category."""
	current_state = doc.workflow_state or "Draft"
	if current_state != "Draft" or requested_action != "Submit":
		return None

	direct_roles = {"Permanent Employee", "head_approver_1", "HoD"}
	target_state = (
		"Pending Staff Approval"
		if direct_roles.intersection(set(user_roles)) or "System Manager" in user_roles
		else "Pending PI Approval"
	)

	for transition in workflow.transitions:
		if not (
			transition.state == current_state
			and transition.action == requested_action
			and transition.next_state == target_state
		):
			continue

		allowed_roles = transition.get("allowed") or []
		if isinstance(allowed_roles, str):
			allowed_roles = [allowed_roles]
		if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
			return target_state

	frappe.throw(
		_("Workflow transition for initial routing to '{0}' is missing.").format(target_state)
	)


	# =============================================================================
	# DOCUMENT CONTROLLER
	# =============================================================================

class IndentCumSanctionSheet(Document):

	def before_insert(self):
		"""Hook before document insertion."""
		self._validate_indent_type()

	def validate(self):
		"""Server-side validations: calculate totals and type-specific checks."""
		self._validate_indent_type()
		self._validate_indent_type_change()
		self.calculate_item_totals()
		self.calculate_repair_total()
		self.calculate_amc_total()
		_set_director_approval_required_value(self)

	def before_save(self):
		"""Hook before saving - create or update sub-doctype."""
		if self.flags.get("skip_icss_subdoctype_sync") or self.is_new():
			return
		if self.icss_indent_type:
			self._sync_sub_doctype()

	def on_submit(self):
		"""Hook on document submission - keep the linked sub-doctype state aligned."""
		if self.sub_doctype_reference and self.icss_indent_type:
			self._sync_sub_doctype_workflow_state(self.workflow_state)

	def on_update_after_submit(self):
		"""Hook after update on submitted document."""
		if self.sub_doctype_reference and self.icss_indent_type:
			self._sync_sub_doctype_after_submit()

	# -------------------------------------------------------------------------
	# CORE DESIGN RULE: CENTRALIZED SUB-DOCTYPE MANAGEMENT
	# -------------------------------------------------------------------------

	def _validate_indent_type(self):
		"""Validate that indent_type is set and valid."""
		if not self.icss_indent_type:
			return

		if self.icss_indent_type not in INDENT_TYPES:
			frappe.throw(_("Invalid Indent Type: {0}").format(self.icss_indent_type))

	def _validate_indent_type_change(self):
		"""Block indent_type changes after submission."""
		if self.docstatus > 0 and self.has_value_changed("icss_indent_type"):
			frappe.throw(_("Cannot change Indent Type after submission."))

	def _sync_sub_doctype(self):
		"""
		Create or update the sub-doctype record automatically.
		This is the single controller method for all sub-doctype operations.
		"""
		sub_doctype_name = _get_sub_doctype(self.icss_indent_type)

		if not sub_doctype_name:
			frappe.log_error(
				f"No sub-doctype mapping found for indent type: {self.icss_indent_type}",
				"ICSS Sub-DocType Sync Error"
			)
			return

		# Check if sub-doctype record already exists
		if self.sub_doctype_reference:
			try:
				sub_doc = frappe.get_doc(sub_doctype_name, self.sub_doctype_reference)
			except frappe.DoesNotExistError:
				sub_doc = None
		else:
			sub_doc = None

		# Create new sub-doctype record if it doesn't exist
		if not sub_doc:
			sub_doc = self._create_sub_doctype_record(sub_doctype_name)
		else:
			# Update existing sub-doctype record
			self._map_parent_data_to_subdoctype(sub_doc)

		# Save sub-doctype
		self._save_sub_doctype(sub_doc)

		# Update parent reference
		if not self.sub_doctype_reference:
			self.db_set("sub_doctype_reference", sub_doc.name, update_modified=False)

	def _create_sub_doctype_record(self, sub_doctype_name):
		"""
		Internal method: Create a new sub-doctype record.
		Must be called only from parent controller.
		"""
		sub_doc = frappe.new_doc(sub_doctype_name)

		# Assign mandatory linkage fields
		sub_doc.indent_cum_sanction_sheet_id = self.name
		sub_doc.project_ref = self.project_ref
		sub_doc.project_no = self.project_no
		sub_doc.indent_type = self.icss_indent_type

		# Map parent data to sub-doctype
		self._map_parent_data_to_subdoctype(sub_doc)

		frappe.logger().info(
			f"ICSS: Created sub-doctype {sub_doctype_name} for parent {self.name}"
		)

		return sub_doc

	def _map_parent_data_to_subdoctype(self, sub_doc):
		"""
		Internal method: Map relevant parent fields into the sub-doctype.
		Field mapping logic based on indent type.
		"""
		# Common fields mapping
		if hasattr(sub_doc, "project_ref"):
			sub_doc.project_ref = self.project_ref
		if hasattr(sub_doc, "project_no"):
			sub_doc.project_no = self.project_no
		if hasattr(sub_doc, "indent_cum_sanction_sheet_id"):
			sub_doc.indent_cum_sanction_sheet_id = self.name
		if hasattr(sub_doc, "indent_type"):
			sub_doc.indent_type = self.icss_indent_type

		frappe.logger().info(
			f"ICSS: Mapped parent data to sub-doctype {sub_doc.doctype} - {sub_doc.name}"
		)

	def _save_sub_doctype(self, sub_doc):
		"""
		Internal method: Save the sub-doctype record.
		Must be called only from parent controller.
		"""
		try:
			sub_doc.flags.ignore_permissions = True
			if sub_doc.is_new():
				sub_doc.insert(ignore_permissions=True)
			else:
				sub_doc.save(ignore_permissions=True)

			frappe.logger().info(
				f"ICSS: Saved sub-doctype {sub_doc.doctype} - {sub_doc.name}"
			)
		except Exception as e:
			frappe.log_error(
				f"Error saving sub-doctype {sub_doc.doctype}: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Save Error"
			)
			frappe.throw(_("Failed to save sub-doctype record: {0}").format(str(e)))

	def _perform_sub_doctype_workflow_action(self, action):
		"""
		Internal method: Trigger workflow transition on the sub-doctype.
		Must be called only from parent controller.
		"""
		if not self.sub_doctype_reference:
			return

		sub_doctype_name = _get_sub_doctype(self.icss_indent_type)
		if not sub_doctype_name:
			return

		try:
			sub_doc = frappe.get_doc(sub_doctype_name, self.sub_doctype_reference)

			# Get workflow for the sub-doctype
			workflow_name = WORKFLOW_MAP.get(self.icss_indent_type)
			if not workflow_name:
				frappe.logger().info(
					f"ICSS: No workflow mapping found for indent type: {self.icss_indent_type}"
				)
				return

			# Check if workflow exists
			if not frappe.db.exists("Workflow", {"document_type": sub_doctype_name, "is_active": 1}):
				frappe.logger().info(
					f"ICSS: No active workflow found for {sub_doctype_name}"
				)
				return

			# Apply workflow action
			workflow = frappe.get_doc("Workflow", {"document_type": sub_doctype_name, "is_active": 1})
			current_state = sub_doc.workflow_state or "Draft"

			# Find matching transition
			for transition in workflow.transitions:
				if transition.state == current_state and transition.action == action:
					sub_doc.workflow_state = transition.next_state

					# Handle docstatus transitions
					state_doc = next((s for s in workflow.states if s.state == transition.next_state), None)
					if state_doc and state_doc.doc_status == "1" and sub_doc.docstatus == 0:
						sub_doc.submit()
					elif state_doc and state_doc.doc_status == "2" and sub_doc.docstatus != 2:
						sub_doc.cancel()
					else:
						sub_doc.save(ignore_permissions=True)

					break

			frappe.logger().info(
				f"ICSS: Performed workflow action '{action}' on sub-doctype {sub_doc.doctype} - {sub_doc.name}"
			)

		except Exception as e:
			frappe.log_error(
				f"Error performing workflow action on sub-doctype: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Workflow Error"
			)

	def _sync_sub_doctype_workflow_state(self, workflow_state=None):
		"""
		Keep child workflow_state in sync with the parent ICSS record.

		The child indent doctypes have their own workflows, so replaying the parent
		action on the child can fail when the child transition graph differs. For
		ICSS, the parent owns routing; the child record mirrors the parent state.
		"""
		if not self.sub_doctype_reference or not self.icss_indent_type:
			return

		sub_doctype_name = _get_sub_doctype(self.icss_indent_type)
		if not sub_doctype_name:
			return

		try:
			if not frappe.get_meta(sub_doctype_name).has_field("workflow_state"):
				return

			frappe.db.set_value(
				sub_doctype_name,
				self.sub_doctype_reference,
				"workflow_state",
				workflow_state or self.workflow_state or "Draft",
				update_modified=False,
			)
		except Exception as e:
			frappe.log_error(
				f"Error syncing sub-doctype workflow_state: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Workflow Sync Error",
			)

	def _sync_sub_doctype_after_submit(self):
		"""
		Internal method: Sync sub-doctype after parent update.
		Must be called only from parent controller.
		"""
		if not self.sub_doctype_reference:
			return

		sub_doctype_name = _get_sub_doctype(self.icss_indent_type)
		if not sub_doctype_name:
			return

		try:
			sub_doc = frappe.get_doc(sub_doctype_name, self.sub_doctype_reference)
			self._map_parent_data_to_subdoctype(sub_doc)

			# Update without changing docstatus
			sub_doc.flags.ignore_permissions = True
			sub_doc.save(ignore_permissions=True)

			frappe.logger().info(
				f"ICSS: Synced sub-doctype after submit {sub_doc.doctype} - {sub_doc.name}"
			)

		except Exception as e:
			frappe.log_error(
				f"Error syncing sub-doctype after submit: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Sync Error"
			)

	# -------------------------------------------------------------------------
	# CALCULATION METHODS (Existing)
	# -------------------------------------------------------------------------

	def calculate_item_totals(self):
		"""Calculate row amounts for the items table and overall basic value."""
		total_basic = 0
		for row in (self.get("icss_items") or []):
			base = flt(row.icss_qty) * flt(row.icss_rate)
			discount = base * flt(row.icss_discount_percent) / 100
			gst = (base - discount) * flt(row.icss_gst_percent) / 100
			row.icss_amount = base - discount + gst
			total_basic += flt(row.icss_amount)

		self.icss_total_basic_value = total_basic

		# Grand total = basic + packing + freight + other
		self.icss_grand_total = (
			flt(self.get("icss_total_basic_value"))
			+ flt(self.get("icss_packing_charges"))
			+ flt(self.get("icss_freight_charges"))
			+ flt(self.get("icss_other_charges"))
		)

	def calculate_repair_total(self):
		"""Grand total for repair section."""
		self.icss_repair_grand_total = (
			flt(self.get("icss_repair_expenditure"))
			+ flt(self.get("icss_repair_other_charges"))
		)

	def calculate_amc_total(self):
		"""Grand total for AMC section."""
		amc_subtotal = flt(self.get("icss_amc_value")) + flt(self.get("icss_amc_other_charges"))
		gst_amount = amc_subtotal * flt(self.get("icss_amc_gst_percent")) / 100
		self.icss_amc_grand_total = amc_subtotal + gst_amount


# =============================================================================
# API ENDPOINTS
# =============================================================================


@frappe.whitelist()
def get_icss_indent_types():
	"""
	Returns all available indent type options for the Indent Cum Sanction Sheet.

	Returns:
		list[dict]: Each dict has ``value`` and ``label`` keys.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		meta = frappe.get_meta(DOCTYPE)
		df = meta.get_field("icss_indent_type")

		if not df:
			frappe.throw(_("Field 'icss_indent_type' not found in {0}").format(DOCTYPE))

		raw_options = (df.options or "").split("\n")
		options = [opt.strip() for opt in raw_options if opt.strip()]

		return {
			"status": "success",
			"indent_types": [
				{"value": opt, "label": opt} for opt in options
			],
		}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Get Indent Types Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# GET FIELDS  (Standard metadata API)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_icss_fields(doc_name=None):
	"""
	API to return Indent Cum Sanction Sheet field metadata, prefill data,
	link options, child table metadata, client scripts, and computation rules.

	Args:
		doc_name (str, optional): If provided, returns prefill data for editing.

	Returns:
		dict: ``fields``, ``prefill_data``, ``link_options``,
		      ``client_scripts``, ``computation_rules``.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	meta = frappe.get_meta(DOCTYPE)

	# ---- Field Metadata ----
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
			"default": f.default,
			"description": f.description,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}

		# Child Tables: include child field metadata
		if f.fieldtype == "Table" and f.options:
			child_meta = frappe.get_meta(f.options)
			child_fields_list = []
			for cf in child_meta.fields:
				cf_data = {
					"fieldname": cf.fieldname,
					"label": cf.label,
					"fieldtype": cf.fieldtype,
					"options": cf.options,
					"mandatory": cf.reqd,
					"in_list_view": cf.in_list_view,
					"read_only": cf.read_only,
					"fetch_from": cf.fetch_from,
					"default": cf.default,
				}
				if cf.fieldtype == "Link" and getattr(cf, "link_filters", None):
					cf_data["link_filters"] = cf.link_filters
				child_fields_list.append(cf_data)
			field_data["child_fields"] = child_fields_list

		fields.append(field_data)

	# ---- Prefill Data ----
	prefill_data = {}
	link_options = {}

	if doc_name:
		try:
			doc = frappe.get_doc(DOCTYPE, doc_name)
			prefill_data = doc.as_dict()
			prefill_data[DIRECTOR_APPROVAL_REQUIRED_FIELD] = (
				1 if _is_icss_director_approval_required(doc) else 0
			)
			child_doc = _get_linked_child_doc(doc)
			if child_doc:
				prefill_data["child_document"] = child_doc.as_dict()
				prefill_data["child_doctype"] = child_doc.doctype
		except Exception:
			pass
	else:
		# Prefill current user details
		user = frappe.session.user
		if user and user != "Guest":
			try:
				user_doc = frappe.get_doc("User", user)
				prefill_data["icss_applicant_webmail_id"] = user
				prefill_data["icss_applicant_name"] = user_doc.full_name
				prefill_data["icss_applicant_department__centre__section"] = user_doc.department_name
				prefill_data["icss_applicant_designation"] = getattr(user_doc, "designation_name", "")
			except Exception:
				pass

	# Declaration checkboxes default to unchecked
	prefill_data.setdefault("icss_declaration_sanctioned_accept", 0)
	prefill_data.setdefault("icss_declaration_nonsanctioned_accept", 0)
	prefill_data.setdefault("icss_repair_declaration_checkbox", 0)
	prefill_data.setdefault("icss_amc_declaration", 0)
	prefill_data.setdefault(SEND_TO_DIRECTOR_FIELD, 0)
	prefill_data.setdefault(DIRECTOR_APPROVAL_REQUIRED_FIELD, 0)
	prefill_data.setdefault(DIRECTOR_SIGNED_PDF_FIELD, None)

	# ---- Link Options ----

	# Account Head
	try:
		account_heads = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label"],
			limit_page_length=500,
		)
		link_options["icss_account_head"] = [
			{"value": r["value"], "label": r.get("label") or r["value"]}
			for r in account_heads
		]
	except Exception:
		link_options["icss_account_head"] = []

	# Users (for applicant / applying-for fields)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=500,
		)
		link_options["icss_applicant_webmail_id"] = users
		link_options["icss_applying_for_mail"] = users
	except Exception:
		link_options["icss_applicant_webmail_id"] = []
		link_options["icss_applying_for_mail"] = []

	# Departments
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "dept_name as label"],
			limit_page_length=500,
		)
		link_options["icss_applicant_department__centre__section"] = departments
		link_options["icss_applying_for_department_centre_section"] = departments
	except Exception:
		link_options["icss_applicant_department__centre__section"] = []

	# ---- Client Scripts ----
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": DOCTYPE, "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view,
			})
	except Exception:
		pass

	# ---- Computation Rules ----
	computation_rules = {
		"row_calculations": [
			{
				"table_fieldname": "icss_items",
				"target_field": "icss_amount",
				"formula": "(icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100) + (((icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100)) * icss_gst_percent / 100)",
				"trigger_fields": ["icss_qty", "icss_rate", "icss_discount_percent", "icss_gst_percent"],
				"description": "Row amount = (Qty × Rate) - Discount% + GST%",
			}
		],
		"aggregations": [
			{
				"target_field": "icss_total_basic_value",
				"source_table": "icss_items",
				"source_field": "icss_amount",
				"operation": "sum",
				"description": "Total basic value = sum of all item amounts",
			}
		],
		"computed_fields": [
			{
				"target_field": "icss_grand_total",
				"formula": "icss_total_basic_value + icss_packing_charges + icss_freight_charges + icss_other_charges",
				"trigger_fields": [
					"icss_total_basic_value",
					"icss_packing_charges",
					"icss_freight_charges",
					"icss_other_charges",
				],
				"description": "Grand total = Basic Value + Packing + Freight + Other Charges",
			},
			{
				"target_field": "icss_repair_grand_total",
				"formula": "icss_repair_expenditure + icss_repair_other_charges",
				"trigger_fields": ["icss_repair_expenditure", "icss_repair_other_charges"],
				"description": "Repair grand total = Repair Expenditure + Other Charges",
			},
			{
				"target_field": "icss_amc_grand_total",
				"formula": "(icss_amc_value + icss_amc_other_charges) + ((icss_amc_value + icss_amc_other_charges) * icss_amc_gst_percent / 100)",
				"trigger_fields": ["icss_amc_value", "icss_amc_other_charges", "icss_amc_gst_percent"],
				"description": "AMC grand total = (AMC Value + Other Charges) + GST%",
			},
		],
		"auto_populate": [
			{
				"trigger_field": "icss_applicant_webmail_id",
				"context": "parent",
				"api": "rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_user_details_icss",
				"api_param": "user_email",
				"field_map": {
					"full_name": "icss_applicant_name",
					"department_name": "icss_applicant_department__centre__section",
					"designation_name": "icss_applicant_designation",
				},
				"description": "Auto-fill applicant details when webmail ID is selected",
			},
			{
				"trigger_field": "icss_applying_for_mail",
				"context": "parent",
				"api": "rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_user_details_icss",
				"api_param": "user_email",
				"field_map": {
					"full_name": "icss_applying_for_name",
					"department_name": "icss_applying_for_department_centre_section",
					"designation_name": "icss_applying_for_designation",
				},
				"description": "Auto-fill applying-for details when webmail ID is selected",
			},
		],
	}

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
		"computation_rules": computation_rules,
	}


@frappe.whitelist()
def get_icss_child_fields(indent_type, child_docname=None):
	"""
	Return metadata and prefill data for the indent-type-specific child doctype.
	"""
	if not indent_type:
		frappe.throw(_("Indent Type is required."))

	sub_doctype_name = _get_sub_doctype(indent_type)
	if not sub_doctype_name:
		frappe.throw(_("No child doctype mapping found for indent type: {0}").format(indent_type))

	response = _get_child_api_response(sub_doctype_name, doc_name=child_docname)
	response["doctype"] = sub_doctype_name
	return response


# ---------------------------------------------------------------------------
# SAVE DATA  (Generic create / update)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_icss_data(data):
	"""
	Creates or updates an Indent Cum Sanction Sheet document.
	Handles parent fields, child tables, and file uploads.

	Args:
		data (str | dict): JSON payload with document field values.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		doc = _save_doc_from_payload(DOCTYPE, data)
		frappe.db.commit()
		child_doc = _get_linked_child_doc(doc)

		return {
			"status": "success",
			"docname": doc.name,
			"data": _serialize_icss_composite(doc, child_doc),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Save Error")
		frappe.throw(_("Failed to save Indent Cum Sanction Sheet: {0}").format(str(e)))


@frappe.whitelist()
def save_icss_composite_data(data):
	"""
	Save the ICSS parent and the indent-type-specific child document together.
	"""
	try:
		payload = _normalize_payload(data)
		parent_data = payload.get("parent") if isinstance(payload.get("parent"), dict) else None
		child_data = payload.get("child") if isinstance(payload.get("child"), dict) else None

		# Backward compatibility: allow parent-only payloads to keep working.
		if parent_data is None and child_data is None:
			return save_icss_data(payload)

		parent_data = parent_data or {}
		child_data = child_data or {}

		indent_type = parent_data.get("icss_indent_type") or child_data.get("indent_type")
		if not indent_type:
			frappe.throw(_("Indent Type is required."))
		if indent_type not in INDENT_TYPES:
			frappe.throw(_("Invalid Indent Type: {0}").format(indent_type))

		parent_data["icss_indent_type"] = indent_type
		parent_doc = _save_doc_from_payload(DOCTYPE, parent_data, skip_subdoctype_sync=True)

		sub_doctype_name = _get_sub_doctype(indent_type)
		if not sub_doctype_name:
			frappe.throw(_("No child doctype mapping found for indent type: {0}").format(indent_type))

		child_doctype = child_data.get("doctype") or sub_doctype_name
		if child_doctype != sub_doctype_name:
			frappe.throw(
				_("Child doctype '{0}' does not match indent type '{1}'.").format(child_doctype, indent_type)
			)

		if not child_data.get("name") and parent_doc.sub_doctype_reference:
			child_data["name"] = parent_doc.sub_doctype_reference

		child_data["doctype"] = sub_doctype_name
		child_data.setdefault("indent_type", indent_type)

		child_meta = frappe.get_meta(sub_doctype_name)
		if child_meta.has_field("indent_cum_sanction_sheet_id"):
			child_data["indent_cum_sanction_sheet_id"] = parent_doc.name
		if child_meta.has_field("project_ref"):
			child_data["project_ref"] = parent_doc.project_ref
		if child_meta.has_field("project_no"):
			child_data["project_no"] = parent_doc.project_no
		if child_meta.has_field("workflow_state") and not child_data.get("workflow_state"):
			child_data["workflow_state"] = parent_doc.workflow_state or "Draft"

		child_doc = _save_doc_from_payload(sub_doctype_name, child_data)

		if parent_doc.sub_doctype_reference != child_doc.name:
			parent_doc.db_set("sub_doctype_reference", child_doc.name, update_modified=False)
			parent_doc.reload()

		frappe.db.commit()

		return {
			"status": "success",
			"docname": parent_doc.name,
			"parent_doctype": DOCTYPE,
			"child_doctype": child_doc.doctype,
			"child_docname": child_doc.name,
			"data": _serialize_icss_composite(parent_doc, child_doc),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Composite Save Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# INDENT-TYPE-SPECIFIC SAVE APIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_icss_proprietary_purchase_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Proprietary Purchase with Proprietary Certificate from the OEM**.

	Validates proprietary-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the proprietary option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_PROPRIETARY

		# Proprietary-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_items") or len(data.get("icss_items", [])) == 0:
			frappe.throw(_("At least one item is required in the Items table."))

		frappe.logger().info(
			f"ICSS Proprietary Purchase: Creating/updating for user {frappe.session.user}"
		)

		return save_icss_data(data)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Proprietary Purchase Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_standardized_purchase_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Standardised / Emergent Purchase**.

	Validates standardized-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the standardized option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_STANDARDIZED

		# Standardized-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_items") or len(data.get("icss_items", [])) == 0:
			frappe.throw(_("At least one item is required in the Items table."))

		if not data.get("icss_standardized_reasons") or len(data.get("icss_standardized_reasons", [])) == 0:
			frappe.throw(_("At least one reason is required in the Standardized Reasons table."))

		frappe.logger().info(
			f"ICSS Standardized Purchase: Creating/updating for user {frappe.session.user}"
		)

		return save_icss_data(data)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Standardized Purchase Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_repair_replacement_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Repair / Replacement**.

	Validates repair-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the repair/replacement option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_REPAIR

		# Repair-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_repair_item_name"):
			frappe.throw(_("Repair Item Name is required for Repair/Replacement indent."))

		if not data.get("icss_repair_justification"):
			frappe.throw(_("Justification is required for Repair/Replacement indent."))

		frappe.logger().info(
			f"ICSS Repair/Replacement: Creating/updating for user {frappe.session.user}"
		)

		return save_icss_data(data)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Repair Replacement Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# WORKFLOW ACTIONS
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_icss_commit_details(docname):
	"""
	Return commit-related fields for the ICSS pending task commit UI.

	Frontend can use this to prefill the shared ``submit_commit_data`` payload
	before moving the document forward in workflow.
	"""
	if not frappe.db.exists(DOCTYPE, docname):
		frappe.throw(_("Indent Cum Sanction Sheet document not found."))

	doc = frappe.get_doc(DOCTYPE, docname)
	child_doc = _get_linked_child_doc(doc)

	project_name = doc.project_ref or None
	project_number = doc.project_no or None
	budget_head = doc.icss_account_head or None
	commit_amount = flt(_get_icss_approval_amount(doc))

	if budget_head == "Others" and getattr(doc, "icss_other_account_head", None):
		budget_head = doc.icss_other_account_head

	module_id = frappe.db.get_value(
		"Module Registry Item",
		{"doctype_name": DOCTYPE, "parent": "pending-task"},
		"mod_vis"
	) or None

	return {
		"docname": docname,
		"workflow_state": doc.workflow_state,
		"applicant_name": doc.icss_applicant_name,
		"webmail_id": doc.icss_applicant_webmail_id,
		"project_name": project_name,
		"project_ref": doc.project_ref,
		"project_number": project_number,
		"project_no": doc.project_no,
		"budget_head": budget_head,
		"account_head": doc.icss_account_head,
		"indent_type": doc.icss_indent_type,
		"child_doctype": child_doc.doctype if child_doc else _get_sub_doctype(doc.icss_indent_type),
		"child_docname": child_doc.name if child_doc else doc.sub_doctype_reference,
		"commit_amount": commit_amount,
		"module_id": module_id,
		# Keep ref_details aligned to the specialized child when present so
		# downstream logs can trace both the parent workflow doc and child form.
		"ref_details": doc.sub_doctype_reference or doc.name,
	}


@frappe.whitelist()
def get_icss_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on
	the document's current workflow state.

	Args:
		docname (str): Name of the Indent Cum Sanction Sheet document.

	Returns:
		list[str]: Available action names (de-duplicated).

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": DOCTYPE, "is_active": 1},
		"name",
	)

	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue
		if current_state == PO_GENERATED_STATE and transition.action in PO_DELIVERY_UPLOAD_ACTIONS:
			continue
		if str(transition.action or "").strip() == "Put Back":
			continue
		if str(transition.action or "").strip().startswith(ICSS_PUT_BACK_ACTION_PREFIX):
			continue

		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			if transition.condition:
				try:
					if not frappe.safe_eval(transition.condition, None, _get_workflow_eval_context(doc)):
						continue
				except Exception:
					continue

			allowed_actions.append(transition.action)

	allowed_actions.extend([
		action["label"]
		for action in _get_available_icss_put_back_action_rows(doc, user_roles=user_roles)
	])

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def get_icss_director_approval_status(docname):
	"""Return Director approval status for one ICSS document."""
	if not docname:
		frappe.throw(_("ICSS docname is required."))

	doc = frappe.get_doc(DOCTYPE, docname)
	required = 1 if _is_icss_director_approval_required(doc) else 0

	return {
		"status": "success",
		"docname": docname,
		"workflow_state": doc.workflow_state or "Draft",
		"approval_amount": flt(_get_icss_approval_amount(doc)),
		"account_head": _get_icss_account_head_text(doc),
		"director_approval_required": required,
		SEND_TO_DIRECTOR_FIELD: _as_int_bool(doc.get(SEND_TO_DIRECTOR_FIELD)),
		DIRECTOR_SIGNED_PDF_FIELD: doc.get(DIRECTOR_SIGNED_PDF_FIELD),
	}


@frappe.whitelist()
def update_send_to_director_icss(docname, send_to_director):
	"""Mark a Director-required ICSS for offline Director approval."""
	if not docname:
		frappe.throw(_("ICSS docname is required."))

	user_roles = frappe.get_roles(frappe.session.user)
	if not _has_any_role(user_roles, DIRECTOR_MARK_ALLOWED_ROLES):
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	doc = frappe.get_doc(DOCTYPE, docname)
	if (doc.workflow_state or "") != PENDING_DEAN_APPROVAL_STATE:
		frappe.throw(_("Can send to Director only from {0}.").format(PENDING_DEAN_APPROVAL_STATE))

	if not _is_icss_director_approval_required(doc):
		frappe.throw(_("Director approval is not required for this ICSS."))

	if _as_int_bool(doc.get(SEND_TO_DIRECTOR_FIELD)):
		return {
			"status": "success",
			"docname": docname,
			"workflow_state": doc.workflow_state,
			SEND_TO_DIRECTOR_FIELD: 1,
			DIRECTOR_APPROVAL_REQUIRED_FIELD: 1,
			DIRECTOR_SIGNED_PDF_FIELD: doc.get(DIRECTOR_SIGNED_PDF_FIELD),
		}

	if not _as_int_bool(send_to_director):
		frappe.throw(_("send_to_director can only be set, not cleared."))

	update_values = {SEND_TO_DIRECTOR_FIELD: 1}
	if frappe.get_meta(DOCTYPE).has_field(DIRECTOR_APPROVAL_REQUIRED_FIELD):
		update_values[DIRECTOR_APPROVAL_REQUIRED_FIELD] = 1

	frappe.db.set_value(DOCTYPE, docname, update_values, update_modified=True)
	frappe.db.commit()

	return {
		"status": "success",
		"docname": docname,
		"workflow_state": PENDING_DEAN_APPROVAL_STATE,
		SEND_TO_DIRECTOR_FIELD: 1,
		DIRECTOR_APPROVAL_REQUIRED_FIELD: 1,
		DIRECTOR_SIGNED_PDF_FIELD: doc.get(DIRECTOR_SIGNED_PDF_FIELD),
	}


@frappe.whitelist()
def attach_director_pdf_icss(docname, file_url=None, is_private=0, file_name=None, file_data=None):
	"""Attach/replace the Director-approved ICSS PDF before Dean approval."""
	if not docname:
		frappe.throw(_("ICSS docname is required."))

	user_roles = frappe.get_roles(frappe.session.user)
	if not _has_any_role(user_roles, DIRECTOR_UPLOAD_ALLOWED_ROLES):
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		if (doc.workflow_state or "") != PENDING_DEAN_APPROVAL_STATE:
			frappe.throw(_("Director PDF can only be uploaded from {0}.").format(PENDING_DEAN_APPROVAL_STATE))

		if not _is_icss_director_approval_required(doc):
			frappe.throw(_("Director approval is not required for this ICSS."))

		if not _as_int_bool(doc.get(SEND_TO_DIRECTOR_FIELD)):
			frappe.throw(_("This ICSS is not flagged for Director approval."))

		expected_folder = _get_icss_director_approval_minio_folder(doc)
		director_pdf_url = file_url or _save_uploaded_director_pdf_file(
			doc,
			is_private=is_private,
			file_name=file_name,
			file_data=file_data,
		)
		if not director_pdf_url:
			frappe.throw(_("Director signed PDF file URL or uploaded file is required."))

		director_pdf_url = _normalize_minio_file_url(director_pdf_url)
		if director_pdf_url.startswith("/Project_Registration/"):
			expected_prefix = f"/{expected_folder}/"
			if not director_pdf_url.startswith(expected_prefix):
				frappe.throw(
					_("Director signed PDF must be stored under {0}. Received: {1}").format(
						expected_prefix,
						director_pdf_url,
					)
				)

		director_pdf_url = _ensure_icss_file_attachment(
			docname,
			director_pdf_url,
			is_private=is_private,
			attached_to_field=DIRECTOR_SIGNED_PDF_FIELD,
		)

		update_values = {DIRECTOR_SIGNED_PDF_FIELD: director_pdf_url}
		if frappe.get_meta(DOCTYPE).has_field(DIRECTOR_APPROVAL_REQUIRED_FIELD):
			update_values[DIRECTOR_APPROVAL_REQUIRED_FIELD] = 1

		frappe.db.set_value(DOCTYPE, docname, update_values, update_modified=True)
		frappe.db.commit()

		return {
			"status": "success",
			"docname": docname,
			"workflow_state": PENDING_DEAN_APPROVAL_STATE,
			SEND_TO_DIRECTOR_FIELD: 1,
			DIRECTOR_APPROVAL_REQUIRED_FIELD: 1,
			DIRECTOR_SIGNED_PDF_FIELD: director_pdf_url,
			"minio_folder": expected_folder,
			"minio_browser_folder": f"{MINIO_BROWSER_BASE_URL}/{quote(expected_folder, safe='')}",
			"minio_browser_url": _get_minio_browser_url(director_pdf_url),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Director PDF Upload Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_pending_director_uploads_icss():
	"""Return ICSS records flagged for Director PDF upload by Staff/R&D."""
	user_roles = frappe.get_roles(frappe.session.user)
	if not _has_any_role(user_roles, DIRECTOR_UPLOAD_ALLOWED_ROLES):
		frappe.throw(_("Not permitted."), frappe.PermissionError)

	docs = frappe.get_all(
		DOCTYPE,
		filters={
			SEND_TO_DIRECTOR_FIELD: 1,
			"workflow_state": PENDING_DEAN_APPROVAL_STATE,
		},
		fields=[
			"name",
			"icss_indent_type",
			"icss_applicant_name",
			"icss_applicant_webmail_id",
			"project_ref",
			"project_no",
			"icss_account_head",
			"icss_other_account_head",
			DIRECTOR_SIGNED_PDF_FIELD,
			"modified",
			"workflow_state",
		],
		order_by="modified desc",
	)

	result = []
	for row in docs:
		doc = frappe.get_doc(DOCTYPE, row.name)
		if not _is_icss_director_approval_required(doc):
			continue

		row[DIRECTOR_APPROVAL_REQUIRED_FIELD] = 1
		row[SEND_TO_DIRECTOR_FIELD] = 1
		row["approval_amount"] = flt(_get_icss_approval_amount(doc))
		row["account_head_text"] = _get_icss_account_head_text(doc)
		result.append(row)

	return {"status": "success", "data": result}


@frappe.whitelist()
def get_available_icss_put_back_actions(docname):
	"""Return dynamic put-back targets available for current user/state."""
	if not docname:
		return {"status": "error", "actions": [], "error": "ICSS docname is required."}

	if not frappe.db.exists(DOCTYPE, docname):
		return {"status": "error", "actions": [], "error": "Document not found"}

	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.workflow_state or "Draft"
	actions = _get_available_icss_put_back_action_rows(
		doc,
		user_roles=frappe.get_roles(frappe.session.user),
	)

	return {
		"status": "success",
		"docname": docname,
		"current_state": current_state,
		"actions": actions,
	}


@frappe.whitelist()
def put_back_icss(docname, target, reason=None):
	"""Apply a validated dynamic put-back action for ICSS."""
	if not docname:
		frappe.throw(_("ICSS docname is required."))
	if not target:
		frappe.throw(_("Put-back target is required."))
	if target not in ICSS_PUT_BACK_TARGETS:
		frappe.throw(_("Unknown put-back target: {0}").format(target))
	if not frappe.db.exists(DOCTYPE, docname):
		frappe.throw(_("Document not found."))

	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"
		rule = ICSS_PUT_BACK_RULES.get(current_state)

		if not rule:
			frappe.throw(_("No put-back actions allowed from state '{0}'.").format(current_state))
		if target not in rule.get("targets", []):
			frappe.throw(_("Cannot put back to '{0}' from '{1}'.").format(target, current_state))

		user_roles = frappe.get_roles(frappe.session.user)
		if not _has_any_role(user_roles, rule.get("roles")):
			frappe.throw(
				_("Role '{0}' required to put back from '{1}'.").format(
					", ".join(rule.get("roles", [])),
					current_state,
				),
				frappe.PermissionError,
			)

		next_state = ICSS_PUT_BACK_TARGETS[target]
		update_values = {"workflow_state": next_state}
		update_values.update(_clear_icss_director_fields_for_put_back(current_state))

		frappe.db.set_value(DOCTYPE, docname, update_values, update_modified=True)

		doc.reload()
		if doc.sub_doctype_reference and doc.icss_indent_type:
			doc._sync_sub_doctype_workflow_state(next_state)

		_add_icss_put_back_comment(
			docname,
			current_state=current_state,
			next_state=next_state,
			target=target,
			reason=reason,
		)

		child_doc = _get_linked_child_doc(doc)
		frappe.db.commit()

		return {
			"status": "success",
			"docname": docname,
			"from": current_state,
			"to": next_state,
			"target": target,
			"workflow_state": next_state,
			"next_actions": get_icss_workflow_actions(docname),
			"available_put_back_actions": get_available_icss_put_back_actions(docname).get("actions", []),
			"data": _serialize_icss_composite(doc, child_doc),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Dynamic Put Back Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def perform_icss_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.

	Args:
		docname (str): Name of the Indent Cum Sanction Sheet document.
		action  (str): Workflow action to perform (e.g. "Approve", "Reject").

	Returns:
		dict: ``{"status": "success", "workflow_state": "...", ...}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)
		put_back_target = _get_icss_put_back_target_from_action(action)
		if put_back_target:
			return put_back_icss(docname, put_back_target)

		if (
			action == "Approve"
			and current_state == PENDING_DEAN_APPROVAL_STATE
			and _is_icss_director_approval_required(doc)
			and not (doc.get(DIRECTOR_SIGNED_PDF_FIELD) or "").strip()
		):
			frappe.throw(
				_("Cannot approve: Director approval is required and the "
				  "Director-signed PDF has not been uploaded by Staff yet.")
			)

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": DOCTYPE, "is_active": 1},
			"name",
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for {0}.").format(DOCTYPE))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		matched_transition = None

		routed_state = _resolve_initial_submit_state(doc, action, workflow, user_roles)
		if routed_state:
			next_state = routed_state

		for t in workflow.transitions:
			if next_state:
				break
			if t.state != current_state or t.action != action:
				continue

			allowed_roles = t.get("allowed") or []
			if isinstance(allowed_roles, str):
				allowed_roles = [allowed_roles]

			if not (
				any(role in user_roles for role in allowed_roles)
				or "System Manager" in user_roles
			):
				continue

			if t.condition:
				try:
					if not frappe.safe_eval(t.condition, None, _get_workflow_eval_context(doc)):
						continue
				except Exception as e:
					frappe.log_error(
						f"ICSS Workflow condition error: {str(e)}",
						"ICSS Workflow Error",
					)
					continue

			next_state = t.next_state
			matched_transition = t
			break

		hos_routed_state = _resolve_hos_next_state(doc, action, workflow, user_roles)
		if hos_routed_state:
			next_state = hos_routed_state

		if not next_state:
			frappe.throw(
				_("No valid transition found for action '{0}' from state "
				  "'{1}' matching your role and conditions.").format(action, current_state)
			)

		doc.workflow_state = next_state

		# Handle docstatus transitions (submit / cancel)
		state_doc = next(
			(s for s in workflow.states if s.state == next_state), None
		)

		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
			doc.cancel()
		else:
			# Match Direct Purchase/Recruitment: workflow movement updates the
			# state field directly so draft-status pending records do not appear
			# stuck in Draft because of Frappe's document status handling.
			frappe.db.set_value(DOCTYPE, docname, "workflow_state", next_state)

			# Since db.set_value does NOT trigger on_update hooks, explicitly
			# invoke the shared Kafka publish hook when the document reaches
			# its approval-complete state. For ICSS this can now be
			# "Pending PO Generation" after Dean / Associate Dean action.
			if next_state in ("Approved", "Pending PO Generation"):
				from rndopsapp.rndopsapp.commitPayment import check_workflow_and_publish

				doc.reload()
				check_workflow_and_publish(doc)

		doc.reload()
		if doc.sub_doctype_reference and doc.icss_indent_type:
			doc._sync_sub_doctype_workflow_state(next_state)

		child_doc = _get_linked_child_doc(doc)
		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_icss_workflow_actions(docname),
			"data": _serialize_icss_composite(doc, child_doc),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_icss(docname):
	"""
	Submit an Indent Cum Sanction Sheet document using Workflow transitions.

	Args:
		docname (str): Name of the document to submit.

	Returns:
		dict: Result from ``perform_icss_action``.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	return perform_icss_action(docname, "Submit")


@frappe.whitelist()
def upload_icss_signed_po(docname, file_url=None, is_private=0, file_name=None, file_data=None):
	"""
	Attach the final signed/generated PO and close ICSS as PO Delivered.

	Accepts either:
	- ``file_url`` for a file already uploaded to the ICSS MinIO folder
	- multipart file under ``file``, ``signed_po``, ``signed_po_attachment``,
	  or ``icss_signed_po_file``
	- base64 payload using ``file_name`` and ``file_data``
	"""
	if not docname:
		frappe.throw(_("ICSS docname is required."))

	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"

		if current_state not in (PO_GENERATED_STATE, PO_DELIVERED_STATE):
			frappe.throw(
				_("Signed PO can only be uploaded after {0}. Current state: {1}").format(
					PO_GENERATED_STATE,
					current_state,
				)
			)

		expected_folder = _get_icss_signed_po_minio_folder(doc)
		signed_po_url = file_url or _save_uploaded_signed_po_file(
			doc,
			is_private=is_private,
			file_name=file_name,
			file_data=file_data,
		)
		if not signed_po_url:
			frappe.throw(_("Signed PO file URL or uploaded file is required."))

		signed_po_url = _normalize_minio_file_url(signed_po_url)
		if signed_po_url.startswith("/Project_Registration/"):
			expected_prefix = f"/{expected_folder}/"
			if not signed_po_url.startswith(expected_prefix):
				frappe.throw(
					_("Signed PO must be stored under {0}. Received: {1}").format(
						expected_prefix,
						signed_po_url,
					)
				)

		signed_po_url = _ensure_icss_file_attachment(
			docname,
			signed_po_url,
			is_private=is_private,
		)

		if not frappe.get_meta(DOCTYPE).has_field(SIGNED_PO_FIELD):
			frappe.throw(_("ICSS signed PO field is missing. Please run migrate."))

		frappe.db.set_value(
			DOCTYPE,
			docname,
			{
				SIGNED_PO_FIELD: signed_po_url,
				"workflow_state": PO_DELIVERED_STATE,
			},
			update_modified=True,
		)

		doc.reload()
		if doc.sub_doctype_reference and doc.icss_indent_type:
			doc._sync_sub_doctype_workflow_state(PO_DELIVERED_STATE)

		child_doc = _get_linked_child_doc(doc)
		frappe.db.commit()

		return {
			"status": "success",
			"message": "Signed PO uploaded and ICSS marked as PO Delivered.",
			"docname": docname,
			"workflow_state": PO_DELIVERED_STATE,
			"signed_po_attachment": signed_po_url,
			SIGNED_PO_FIELD: signed_po_url,
			"minio_folder": expected_folder,
			"minio_browser_folder": f"{MINIO_BROWSER_BASE_URL}/{quote(expected_folder, safe='')}",
			"minio_browser_url": _get_minio_browser_url(signed_po_url),
			"data": _serialize_icss_composite(doc, child_doc),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Signed PO Upload Error")
		return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# USER DETAILS HELPER
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_user_details_icss(user_email):
	"""
	Fetch user details (name, department, designation) for auto-populating
	applicant and applying-for fields.

	Args:
		user_email (str): The user's email / webmail ID.

	Returns:
		dict | None: ``{"full_name": ..., "department_name": ..., "designation_name": ...}``

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))

	try:
		user_email = str(user_email).strip('"').strip("'")
		user_doc = frappe.get_doc("User", user_email)

		result = {
			"full_name": user_doc.full_name,
			"department_name": user_doc.department_name,
			"designation_name": getattr(user_doc, "designation_name", ""),
		}

		# Resolve department link to actual name
		if user_doc.department_name:
			try:
				dept_doc = frappe.get_doc("Department_prornd", user_doc.department_name)
				result["department_name"] = dept_doc.dept_name
			except Exception:
				pass

		return result

	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("ICSS Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))
