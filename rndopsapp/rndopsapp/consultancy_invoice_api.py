# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Whitelisted API for the "Consultancy Invoice" DocType.

Endpoints (under rndopsapp.rndopsapp.consultancy_invoice_api):
    save_con_invoice(project_no, fund_received_ref)  -> {"invoice_no": ...}
    get_con_invoice(project_no, fund_received_ref)   -> {"invoice_no": ... | None}

The only inputs are the project and the Fund Received it is invoiced against. The invoice
number is generated on the server (INVO-YYYY-MM-DD-AAA001); saving the same pair again
returns the number already issued instead of creating a second one.
"""

import frappe
from frappe import _

DOCTYPE = "Consultancy Invoice"


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


def _existing_invoice(project_no, fund_received_ref):
	rows = frappe.get_all(
		DOCTYPE,
		filters={"project_no": project_no, "fund_received_ref": fund_received_ref},
		pluck="invoice_no",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def save_con_invoice(project_no, fund_received_ref):
	"""Issue (or return the already issued) invoice number for a project + Fund Received."""
	frappe.has_permission(DOCTYPE, "create", throw=True)

	fund_received_ref = (fund_received_ref or "").strip()
	if not fund_received_ref:
		frappe.throw(_("Fund Received Ref is required."))

	project = _find_project(project_no)
	if not project:
		frappe.throw(_("Project {0} does not exist.").format(project_no), frappe.DoesNotExistError)
	project_name, project_number = project

	# fund_received_ref is the Fund Received's reference number (as used by the deposit
	# slips); the document name is accepted too.
	fund = frappe.get_all(
		"Fund Received",
		or_filters=[["fund_received_ref_number", "=", fund_received_ref], ["name", "=", fund_received_ref]],
		fields=["name", "prjreg_title"],
		limit=1,
	)
	if not fund:
		frappe.throw(_("Fund Received {0} does not exist.").format(fund_received_ref), frappe.DoesNotExistError)
	if fund[0].prjreg_title != project_name:
		frappe.throw(
			_("Fund Received {0} does not belong to project {1}.").format(fund_received_ref, project_number)
		)

	invoice_no = _existing_invoice(project_number, fund_received_ref)
	if not invoice_no:
		doc = frappe.get_doc(
			{"doctype": DOCTYPE, "project_no": project_number, "fund_received_ref": fund_received_ref}
		)
		doc.insert()
		invoice_no = doc.invoice_no

	return {"invoice_no": invoice_no}


@frappe.whitelist()
def get_con_invoice(project_no, fund_received_ref):
	"""The invoice number issued for this project + Fund Received, or None."""
	frappe.has_permission(DOCTYPE, "read", throw=True)

	project = _find_project(project_no)
	fund_received_ref = (fund_received_ref or "").strip()
	if not project or not fund_received_ref:
		return {"invoice_no": None}

	return {"invoice_no": _existing_invoice(project[1], fund_received_ref)}
