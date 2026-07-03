# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
from datetime import datetime

import frappe
from frappe.model.document import Document


def _normalize_date(value):
	"""Convert DD/MM/YYYY to YYYY-MM-DD; pass through anything else unchanged."""
	if isinstance(value, str) and len(value) == 10 and value[2] == "/" and value[5] == "/":
		try:
			return datetime.strptime(value, "%d/%m/%Y").strftime("%Y-%m-%d")
		except ValueError:
			pass
	return value


class ICSS_PO(Document):
	def before_save(self):
		if self.po_date:
			self.po_date = _normalize_date(self.po_date)


AMC_INDENT_TYPE = "Annual Maintenance Contract"


def _parse_table_rows(value):
	"""Accept table rows from form-data JSON strings or JSON request bodies."""
	if value in (None, ""):
		return []
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except Exception:
			frappe.throw("amc_po_table must be a valid JSON array.")
	if not isinstance(value, list):
		frappe.throw("amc_po_table must be a list of row objects.")
	return value


def _clean_child_row(row):
	"""Remove Frappe child row system keys before appending table rows."""
	cleaned = dict(row or {})
	for key in (
		"name",
		"creation",
		"modified",
		"modified_by",
		"owner",
		"docstatus",
		"idx",
		"parent",
		"parentfield",
		"parenttype",
		"doctype",
	):
		cleaned.pop(key, None)
	return cleaned


@frappe.whitelist()
def save_icss_po_data(
	project_number=None,
	icss_number=None,
	indent_type=None,
	po_number=None,
	po_date=None,
	icss_po_form=None,
	amc_po_table=None,
	add_of_gst_=None,
	gst_amount=None,
	grand_total=None,
):
	"""
	Save or update an ICSS_PO document.

	Expected payload fields from frontend:
	- project_number
	- icss_number
	- indent_type
	- po_number
	- po_date
	- icss_po_form
	- amc_po_table (only saved when indent_type is Annual Maintenance Contract)
	- add_of_gst_ (only saved when indent_type is Annual Maintenance Contract)
	- gst_amount (only saved when indent_type is Annual Maintenance Contract)
	- grand_total (only saved when indent_type is Annual Maintenance Contract)

	The record is primarily linked to ICSS through ``icss_number`` and is updated
	if an existing ICSS_PO already exists for the same ICSS document.
	"""
	try:
		if not icss_number and not project_number:
			frappe.throw("At least one of 'icss_number' or 'project_number' must be provided.")

		# If the ICSS parent exists, use it as the canonical source for linkage
		# and backfill project number when frontend only sends the ICSS number.
		if icss_number and frappe.db.exists("Indent Cum Sanction Sheet", icss_number):
			project_number = project_number or frappe.db.get_value(
				"Indent Cum Sanction Sheet",
				icss_number,
				"project_no",
			)
			indent_type = indent_type or frappe.db.get_value(
				"Indent Cum Sanction Sheet",
				icss_number,
				"icss_indent_type",
			)

		existing_name = None
		if icss_number:
			existing_name = frappe.db.get_value(
				"ICSS_PO",
				{"icss_number": icss_number},
				"name",
			)

		if not existing_name and po_number:
			existing_name = frappe.db.get_value(
				"ICSS_PO",
				{"po_number": po_number},
				"name",
			)

		if not existing_name and project_number:
			existing_name = frappe.db.get_value(
				"ICSS_PO",
				{"project_number": project_number},
				"name",
			)

		if existing_name:
			doc = frappe.get_doc("ICSS_PO", existing_name)
		else:
			doc = frappe.new_doc("ICSS_PO")

		if project_number is not None:
			doc.project_number = project_number
		if icss_number is not None:
			doc.icss_number = icss_number
		if indent_type is not None:
			doc.indent_type = indent_type
		if po_number is not None:
			doc.po_number = po_number
		if po_date is not None:
			doc.po_date = _normalize_date(po_date)
		if icss_po_form is not None:
			doc.icss_po_form = icss_po_form

		# AMC PO rows are meaningful only for Annual Maintenance Contract.
		# Replace rows only when frontend explicitly sends the table, so partial
		# saves do not accidentally wipe an existing AMC table.
		if doc.indent_type != AMC_INDENT_TYPE:
			doc.set("amc_po_table", [])
		elif amc_po_table is not None:
			doc.set("amc_po_table", [])
			for row in _parse_table_rows(amc_po_table):
				doc.append("amc_po_table", _clean_child_row(row))

		# AMC summary fields are stored only for AMC indent type. Preserve
		# existing values during partial AMC saves when frontend omits them.
		if doc.indent_type != AMC_INDENT_TYPE:
			doc.add_of_gst_ = None
			doc.gst_amount = None
			doc.grand_total = None
		else:
			if add_of_gst_ is not None:
				doc.add_of_gst_ = add_of_gst_
			if gst_amount is not None:
				doc.gst_amount = gst_amount
			if grand_total is not None:
				doc.grand_total = grand_total

		# Mirror NIQ behavior: allow partial/upsert style saves from frontend.
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		frappe.logger().info(f"ICSS_PO document saved: {doc.name}")
		return {
			"status": "success",
			"docname": doc.name,
			"indent_type": doc.indent_type,
			"amc_po_table_rows": len(doc.get("amc_po_table") or []),
			"add_of_gst_": doc.add_of_gst_,
			"gst_amount": doc.gst_amount,
			"grand_total": doc.grand_total,
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "save_icss_po_data Error")
		frappe.throw(f"An error occurred while saving ICSS_PO data: {str(e)}")
