# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	
	Examples:
		"eval:doc.category=='Research'" -> "doc.category=='Research'"
		"eval:doc.category.includes('Consultancy')" -> "doc.category.includes('Consultancy')"
		None -> None
		"" -> None
	"""
	if not expression:
		return None
	
	expression = str(expression).strip()
	
	if expression.startswith("eval:"):
		return expression[5:].strip()  # Remove 'eval:' prefix
	
	return expression


class RateContract(Document):
	def validate(self):
		self._compute_totals()

	def _compute_totals(self):
		item_total = sum(flt(row.amount) for row in self.get("items", []))
		self.rate_contract_total = item_total
		self.rate_contract_grand_total = item_total + flt(self.rate_contract_packing)


@frappe.whitelist()
def get_rate_contract_fields(doc_name=None):
	"""
	API to return Rate Contract field metadata and prefill data.
	Includes eval expressions for frontend conditional logic.
	"""
	rate_contract_meta = frappe.get_meta("Rate Contract")

	fields = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"description": f.description,
			"default": f.default,
			# Eval expressions for frontend conditional logic
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			# Extract eval expression for easier frontend parsing
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}
		for f in rate_contract_meta.get("fields")
	]

	prefill_data = {}
	link_options = {}
	related_data = {}
	child_table_fields = {}

	# Get child table field metadata for 'items'
	items_meta = frappe.get_meta("Rate Contract Purchase Item Detail")
	child_table_fields["items"] = [
		{
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"in_list_view": f.in_list_view,
			"read_only": f.read_only,
		}
		for f in items_meta.get("fields")
	]

	if doc_name:
		# Clean input
		doc_name = str(doc_name).strip('"').strip("'")

		# Fetch existing Rate Contract document for editing
		doc = frappe.get_doc("Rate Contract", doc_name)
		if doc:
			related_data = doc.as_dict()
			# Copy fields for prefill
			for field in fields:
				if hasattr(doc, field["fieldname"]):
					prefill_data[field["fieldname"]] = getattr(doc, field["fieldname"])
			# Include child table data
			prefill_data["items"] = [row.as_dict() for row in doc.get("items", [])]

	# Prefill current user data
	current_user = frappe.session.user
	if current_user and current_user != "Guest":
		try:
			user_doc = frappe.get_doc("User", current_user)
			user_dict = user_doc.as_dict()
			
			if not prefill_data.get("email_id"):
				prefill_data["email_id"] = current_user
			if not prefill_data.get("indentor"):
				prefill_data["indentor"] = current_user

			# Resolve Designation
			if not prefill_data.get("applicant_designation"):
				prefill_data["applicant_designation"] = user_dict.get("designation_name") or user_dict.get("designation")

			# Resolve Department (handle Link to Department_prornd)
			if not prefill_data.get("applicant_department"):
				dept_val = user_dict.get("department_name") or user_dict.get("department")
				
				# If it looks like a Link ID, try to fetch actual name from Department_prornd
				if dept_val:
					try:
						# Try fetching as Department_prornd
						dept_doc = frappe.get_doc("Department_prornd", dept_val)
						prefill_data["applicant_department"] = dept_doc.dept_name
					except Exception:
						# Fallback: use the value as is (it might be the name already or a different link)
						prefill_data["applicant_department"] = dept_val
		except Exception:
			pass

	# Link options for dropdowns
	link_options["email_id"] = frappe.get_all(
		"User", fields=["name as value", "name as label"], limit=200
	)
	link_options["indentor"] = frappe.get_all(
		"User", fields=["name as value", "full_name as label"], limit=200
	)
	link_options["project_number"] = frappe.get_all(
		"Project Registration", fields=["name as value", "project_title as label"], limit=200
	)
	link_options["account_head"] = frappe.get_all(
		"Budget Head", fields=["name as value", "budget_head as label"], limit=200
	)
	link_options["principal_supplier"] = frappe.get_all(
		"Principal Supplier", fields=["name as value", "principal_supplier_name as label"], limit=200
	)
	link_options["local_supplier"] = frappe.get_all(
		"Local Supplier Detail", fields=["name as value", "local_supplier_name as label"], limit=200
	)
	link_options["select_vendor"] = frappe.get_all(
		"Principal Supplier", fields=["name as value", "principal_supplier_name as label"], limit=200
	)
	link_options["amended_from"] = frappe.get_all(
		"Rate Contract", fields=["name as value", "name as label"], limit=200
	)

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"related_data": related_data,
		"child_table_fields": child_table_fields,
	}


@frappe.whitelist()
def save_rate_contract(doc_data):
	"""Saves or updates the Rate Contract data from the React form."""
	try:
		data = json.loads(doc_data) if isinstance(doc_data, str) else doc_data
		print("Received data for Rate Contract:", data)  # Debug log

		# Check if editing existing document
		doc_name = data.get("name")
		if doc_name:
			doc = frappe.get_doc("Rate Contract", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("Rate Contract")

		# Field mapping for Rate Contract
		field_mapping = {
			"select_form_type": "select_form_type",
			"email_id": "email_id",
			"indentor": "indentor",
			"applicant_designation": "applicant_designation",
			"applicant_department": "applicant_department",
			"project_number": "project_number",
			"account_head": "account_head",
			"item_type": "item_type",
			"principal_supplier": "principal_supplier",
			"principal_address": "principal_address",
			"agreement_no": "agreement_no",
			"local_supplier": "local_supplier",
			"local_address": "local_address",
			"local_email": "local_email",
			"certify_authorized_firm": "certify_authorized_firm",
			"certify_current_prices": "certify_current_prices",
			"certify_delivery_time": "certify_delivery_time",
			"justification": "justification",
			"p4_item_type": "p4_item_type",
			"select_vendor": "select_vendor",
			"vendor_address": "vendor_address",
			"vendor_email": "vendor_email",
			"rate_contract_total": "rate_contract_total",
			"rate_contract_packing": "rate_contract_packing",
			"rate_contract_grand_total": "rate_contract_grand_total",
			"amount_in_words": "amount_in_words",
		}

		# Update document with mapped data
		for form_field, doctype_field in field_mapping.items():
			if form_field in data and data[form_field] not in [None, ""]:
				doc.set(doctype_field, data[form_field])

		# Handle child table - items
		if "items" in data:
			doc.set("items", [])  # Clear existing items
			for item in (data.get("items") or []):
				if item.get("item_description") or item.get("cat_no"):
					doc.append(
						"items",
						{
							"item_description": item.get("item_description"),
							"cat_no": item.get("cat_no"),
							"page_no": item.get("page_no"),
							"unit_rate": item.get("unit_rate", 0),
							"quantity": item.get("quantity", 0),
							"discount_percentage": item.get("discount_percentage", 0),
							"gst_percentage": item.get("gst_percentage", 0),
							"amount": item.get("amount", 0),
						},
					)

		# Save the document
		if doc_name:
			doc.save(ignore_permissions=True)
		else:
			doc.insert(ignore_permissions=True)
		frappe.db.commit()

		print(f"Successfully saved Rate Contract: {doc.name}")  # Debug log

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Rate Contract Save Error")
		frappe.db.rollback()
		frappe.throw(f"Failed to save Rate Contract: {str(e)}")


@frappe.whitelist()
def submit_rate_contract(docname):
	"""
	Submit a Rate Contract document.
	"""
	try:
		doc = frappe.get_doc("Rate Contract", docname)
		
		if doc.docstatus == 0:
			doc.submit()
			frappe.db.commit()
			return {
				"status": "success",
				"message": f"Rate Contract '{docname}' submitted successfully.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		elif doc.docstatus == 1:
			return {
				"status": "info",
				"message": f"Rate Contract '{docname}' is already submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}
		else:
			return {
				"status": "error",
				"message": f"Rate Contract '{docname}' is cancelled and cannot be submitted.",
				"docname": docname,
				"docstatus": doc.docstatus,
			}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Rate Contract Submit Error")
		return {"status": "error", "message": str(e)}


# ============================================
# Filtered Link Options (Client Script Logic)
# ============================================

@frappe.whitelist()
def get_principal_suppliers_by_item_type(item_type=None):
	"""
	Get Principal Suppliers filtered by item_type.
	Implements: frm.set_query('principal_supplier') filter logic
	"""
	if not item_type:
		return []
	
	suppliers = frappe.get_all(
		"Principal Supplier",
		filters={"item_type": item_type},
		fields=["name as value", "principal_supplier_name as label", "addres", "agreement_no"],
		limit=0
	)
	return suppliers


@frappe.whitelist()
def get_local_suppliers_by_principal(principal_supplier=None):
	"""
	Get Local Suppliers filtered by parent Principal Supplier.
	Implements: frm.set_query('local_supplier') filter logic
	"""
	if not principal_supplier:
		return []
	
	suppliers = frappe.get_all(
		"Local Supplier Detail",
		filters={"parent": principal_supplier, "parenttype": "Principal Supplier"},
		fields=["name as value", "local_supplier_name as label", "address", "email"],
		limit=0
	)
	return suppliers


@frappe.whitelist()
def get_vendors_by_p4_item_type(p4_item_type=None):
	"""
	Get Vendors (Principal Suppliers) filtered by P4 item_type.
	Implements: filter for select_vendor in P4 form
	
	P4 item types: UPS Batteries, HP Printer Cartridges, Gas Refilling, 
	Copier Papers, UPS and Transformers, Furniture
	"""
	if not p4_item_type:
		return []
	
	vendors = frappe.get_all(
		"Principal Supplier",
		filters={"item_type": p4_item_type},
		fields=["name as value", "principal_supplier_name as label", "addres", "email"],
		limit=0
	)
	return vendors


@frappe.whitelist()
def get_principal_supplier_details(principal_supplier):
	"""
	Fetch Principal Supplier details (address, agreement_no).
	Implements: principal_supplier onChange logic
	"""
	if not principal_supplier:
		return {}
	
	details = frappe.db.get_value(
		"Principal Supplier",
		principal_supplier,
		["addres", "agreement_no"],
		as_dict=True
	)
	
	if details:
		return {
			"principal_address": details.get("addres"),
			"agreement_no": details.get("agreement_no")
		}
	return {}


@frappe.whitelist()
def get_local_supplier_details(local_supplier):
	"""
	Fetch Local Supplier details (address, email).
	Implements: local_supplier onChange logic
	"""
	if not local_supplier:
		return {}
	
	details = frappe.db.get_value(
		"Local Supplier Detail",
		local_supplier,
		["address", "email"],
		as_dict=True
	)
	
	if details:
		return {
			"local_address": details.get("address"),
			"local_email": details.get("email")
		}
	return {}


@frappe.whitelist()
def get_vendor_details(vendor):
	"""
	Fetch Vendor (Principal Supplier) details for P4 form.
	Implements: select_vendor onChange logic (similar to principal_supplier)
	"""
	if not vendor:
		return {}
	
	details = frappe.db.get_value(
		"Principal Supplier",
		vendor,
		["addres", "email"],
		as_dict=True
	)
	
	if details:
		return {
			"vendor_address": details.get("addres"),
			"vendor_email": details.get("email")
		}
	return {}


@frappe.whitelist()
def get_form_type_config():
	"""
	Returns P3/P4 form type configuration for frontend field visibility handling.
	Implements: select_form_type onChange logic
	"""
	return {
		"P3": {
			"form_type": "P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)",
			"visible_fields": [
				"item_type", "principal_supplier", "principal_address", 
				"agreement_no", "local_supplier", "local_address", "local_email",
				"certify_authorized_firm", "certify_current_prices", "certify_delivery_time"
			],
			"hidden_fields": [
				"p4_item_type", "select_vendor", "vendor_address", "vendor_email", "justification"
			]
		},
		"P4": {
			"form_type": "P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)",
			"visible_fields": [
				"p4_item_type", "select_vendor", "vendor_address", "vendor_email", "justification"
			],
			"hidden_fields": [
				"item_type", "principal_supplier", "principal_address", 
				"agreement_no", "local_supplier", "local_address", "local_email",
				"certify_authorized_firm", "certify_current_prices", "certify_delivery_time"
			]
		}
	}

