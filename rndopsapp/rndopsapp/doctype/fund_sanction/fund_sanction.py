# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe

# frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/fund_sanction/fund_sanction.py

import frappe
from frappe.model.document import Document
from frappe import _


class FundSanction(Document):
	def validate(self):
		# Add any specific validation for Fund Sanction here
		pass


# Whitelisted method to fetch budget details from Project Proposal
@frappe.whitelist()
def get_project_proposal_budget_details(project_proposal_name):
	try:
		if not project_proposal_name:
			frappe.throw("Project Proposal name is required to fetch budget details.")

		project_proposal = frappe.get_doc("Project Proposal", project_proposal_name)

		return {
			"proposed_budget_breakup": project_proposal.get("proposed_budget_breakup", []),
			"total_first_year_budget": project_proposal.total_first_year_budget,
			"total_second_year_budget": project_proposal.total_second_year_budget,
			"total_third_year_budget": project_proposal.total_third_year_budget,
			"total_fourth_year_budget": project_proposal.total_fourth_year_budget,
			"total_fifth_year_budget": project_proposal.total_fifth_year_budget,
			"grand_total_proposal": project_proposal.grand_total_proposal,
			"total_budget_amount": project_proposal.total_budget_amount,  # <-- Added this field
		}

	except frappe.DoesNotExistError:
		frappe.log_error(
			f"Project Proposal {project_proposal_name} not found.", "Fund Sanction Budget Fetch Error"
		)
		frappe.throw(f"Project Proposal '{project_proposal_name}' not found.")
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Fund Sanction Budget Fetch Error")
		frappe.throw(f"An error occurred while fetching budget details: {e}")


@frappe.whitelist(allow_guest=True)
def get_fund_sanction_form_data():
	"""
	Return all data needed to render the Fund Sanction form.
	Accessible by all users.
	"""
	import frappe
	from frappe import _

	doctype_name = "Fund Sanction"

	try:
		# Disable permission checks temporarily
		# frappe.only_for("System Manager")  # Optional safeguard — remove if you want fully open access
		frappe.permissions.can_read = lambda doctype: True

		# Forcefully get metadata without permission issues
		meta = frappe.get_meta(doctype_name, cached=False)

		fields = []
		for field in meta.fields:
			if field.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
				continue
			fields.append(
				{
					"fieldname": field.fieldname,
					"label": _(field.label),
					"fieldtype": field.fieldtype,
					"default": field.default,
					"mandatory": bool(field.reqd),
					"read_only": bool(field.read_only),
					"hidden": bool(field.hidden),
					"description": _(field.description) if field.description else None,
					"options": field.options,
				}
			)

		link_options = {}
		for field in fields:
			if field["fieldtype"] == "Link" and field["options"]:
				linked_doctype = field["options"]
				try:
					title_field = frappe.get_meta(linked_doctype).get_title_field()
					options_list = frappe.get_list(
						linked_doctype,
						fields=["name", title_field],
						limit_page_length=1000,
						ignore_permissions=True,  # 👈 important
					)
					link_options[field["fieldname"]] = [
						{"value": d["name"], "label": d.get(title_field, d["name"])} for d in options_list
					]
				except Exception:
					link_options[field["fieldname"]] = []

		return {"fields": fields, "link_options": link_options, "prefill_data": {}}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching fund sanction form data"))
		return {"error": str(e)}


@frappe.whitelist()
def save_fund_sanction_data(data):
	"""
	Save Fund Sanction form data to the backend.
	Expects 'data' as a JSON string from frontend.
	"""
	import json

	try:
		# Parse JSON string if needed
		if isinstance(data, str):
			data = json.loads(data)

		# Create or update Fund Sanction document
		docname = data.get("name")  # If editing an existing doc
		if docname:
			fs_doc = frappe.get_doc("Fund Sanction", docname)
		else:
			fs_doc = frappe.new_doc("Fund Sanction")

		# Map simple fields
		simple_fields = [
			"amended_from",
			"project_proposal",
			"total_sanctioned_amount",
			"sanctioned_letter_no",
			"sanctioned_letter_date",
			"total_first_year_budget_1",
			"total_second_year_budget_1",
			"total_third_year_budget_1",
			"total_fourth_year_budget_1",
			"total_fifth_year_budget_1",
			"grand_total_proposal_1",
			"have_fund_details",
			"project_type_linked",
			"is_gst_invoice_issued",
			"invoice_details",
			"amount_received",
			"iitg_bank_account_number",
		]

		for field in simple_fields:
			if field in data:
				setattr(fs_doc, field, data[field] if data[field] != "null" else None)

		# Handle child tables
		child_tables = {
			"sanctioned_budget_breakup": "Sanctioned Budget Breakup",
			"fund_transactions": "Fund Transactions",
			"received_amount_breakup": "Received Amount Breakup",
		}

		for field, child_doctype in child_tables.items():
			if field in data:
				items = json.loads(data[field]) if isinstance(data[field], str) else data[field]
				fs_doc.set(field, [])  # clear existing child table
				for item in items:
					child = fs_doc.append(field, item)

		# Handle file attachments
		if "sanction_related_files_meta" in data:
			files_meta = json.loads(data["sanction_related_files_meta"])
			for fmeta in files_meta:
				# If file content comes as file_0, file_1, etc.
				file_key = f"file_{files_meta.index(fmeta)}"
				file_data = data.get(file_key)
				if file_data:
					# Save file in Frappe file system
					file_doc = frappe.get_doc(
						{
							"doctype": "File",
							"file_name": fmeta.get("description", f"file_{file_key}"),
							"attached_to_doctype": "Fund Sanction",
							"attached_to_name": fs_doc.name,
							"content": file_data,  # file content in base64
						}
					)
					file_doc.insert()

		fs_doc.save()
		frappe.db.commit()
		return {"status": "success", "name": fs_doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error saving Fund Sanction"))
		return {"status": "error", "message": str(e)}


