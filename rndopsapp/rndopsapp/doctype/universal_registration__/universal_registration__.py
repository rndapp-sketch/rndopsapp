# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils.file_manager import save_file
import json

class UniversalRegistration__(Document):
	pass

def map_frontend_fields_to_doctype(data):
	"""
	Map frontend field names to DocType field names.
	This handles the conversion from form field names to actual DocType field names.
	"""
	field_mapping = {
		# Personal Information
		"email": "email_address_u_r",
		"full_name": "full_name_u_r",
		"parent_guardian_name": "guardian_name_u_r",
		"guardian_name": "guardian_name_u_r",
		"date_of_birth": "dob_u_r",
		"dob": "dob_u_r",
		"gender": "gender_u_r",
		"nationality": "nationality_u_r",
		"mobile_number": "mobile_number_u_r",
		"phone": "mobile_number_u_r",
		"whatsapp_number": "whatsapp_number_u_r",
		"alternate_mobile": "alternate_mobile_number_u_r",
		"same_as_mobile": "same_as_mobile_number_u_r",
		
		# Organization Information
		"organization_name": "org_name_u_r",
		"org_name": "org_name_u_r",
		"establishment_date": "est_date_u_r",
		"incorporation_date": "est_date_u_r",
		"business_nature": "nature_of_business_u_r",
		"nature_of_business": "nature_of_business_u_r",
		"website": "website_u_r",
		"contact_person": "contact_person_u_r",
		"contact_designation": "contact_designation",
		"organization_email": "email_oraganization__contact_person_u_r",
		"org_email": "email_oraganization__contact_person_u_r",
		"org_phone": "org_contact_number_u_r",
		"organization_phone": "org_contact_number_u_r",
		"org_mobile": "organization_mobile_number_u_r",
		"organization_mobile": "organization_mobile_number_u_r",
		
		# Profile & Classification
		"profile_type": "profile_type_u_r",
		"org_sub_type": "organization_sub_type_u_r",
		"organization_sub_type": "organization_sub_type_u_r",
		
		# Identity / KYC (Individual)
		"aadhaar_number": "aadhaar_number_u_r",
		"aadhaar_expiry": "aadhaar_expiry_u_r",
		"aadhaar_file": "aadhaar_file_u_r",
		"aadhaar_file_back": "aadhaar_file_back_u_r",
		"pan_number": "pan_number_u_r",
		"pan_expiry": "pan_expiry_u_r",
		"pan_file": "pan_file_u_r",
		"other_identity_number": "other_identity_number_u_r",
		"other_expiry": "other_expiry_u_r",
		"other_file": "other_file_u_r",
		"other_file_back": "other_file_back_u_r",
		
		# Financial & Documents
		"bank_details": "bank_details_u_r",
		"documents": "uploaded_documents_u_r",
		"uploaded_documents": "uploaded_documents_u_r",
		"addresses": "address_details",
		"address_details": "address_details",
		"org_addresses": "org_address_details_u_r",
		"org_address_details": "org_address_details_u_r",
		"qualifications": "qualifications_u_r",
		"experiences": "experiences_u_r",
		"experience": "experiences_u_r",
		
		# Vendor & Compliance
		"type_of_business": "type_of_business_u_r",
		"nature_of_org": "nature_of_org",
		"organization_nature": "nature_of_org",
		"pan_number_org": "pan_number_org_u_r",
		"gst_status": "gst_status_u_r",
		"gst_number": "gst_number_u_r",
		"other_registration": "other_registration_u_r",
		"overhead_percentage": "overhead_percentage_u_r",
		"discount_percentage": "discount_percentage_u_r",
		"agreement_number": "agreement_number_u_r",
		
		# Signatory
		"signatory_name": "signatory_name_u_r",
		"signatory_designation": "signatory_designation_u_r",
		"date_of_signing": "date_of_signing_u_r",
		"declaration": "decl_info_true_u_r",
		"info_declaration": "decl_info_true_u_r",
		
		# User email (if different from email_address_u_r)
		"user_email": "email_address_u_r"
	}
	
	# Create mapped data
	mapped_data = {}
	for frontend_field, value in data.items():
		# Map to doctype field if mapping exists, otherwise keep original
		doctype_field = field_mapping.get(frontend_field, frontend_field)
		mapped_data[doctype_field] = value
	
	return mapped_data

def map_doctype_fields_to_frontend(data):
	"""
	Map DocType field names back to frontend field names for response.
	"""
	reverse_mapping = {
		"email_address_u_r": "email",
		"full_name_u_r": "full_name",
		"guardian_name_u_r": "parent_guardian_name",
		"dob_u_r": "date_of_birth",
		"gender_u_r": "gender",
		"nationality_u_r": "nationality",
		"mobile_number_u_r": "mobile_number",
		"whatsapp_number_u_r": "whatsapp_number",
		"alternate_mobile_number_u_r": "alternate_mobile",
		"same_as_mobile_number_u_r": "same_as_mobile",
		"org_name_u_r": "organization_name",
		"est_date_u_r": "establishment_date",
		"nature_of_business_u_r": "business_nature",
		"website_u_r": "website",
		"contact_person_u_r": "contact_person",
		"email_oraganization__contact_person_u_r": "organization_email",
		"org_contact_number_u_r": "org_phone",
		"organization_mobile_number_u_r": "org_mobile",
		"profile_type_u_r": "profile_type",
		"organization_sub_type_u_r": "org_sub_type",
		"bank_details_u_r": "bank_details",
		"uploaded_documents_u_r": "documents",
		"address_details": "addresses",
		"org_address_details_u_r": "org_addresses",
		"qualifications_u_r": "qualifications",
		"experiences_u_r": "experiences",
		"type_of_business_u_r": "type_of_business",
		"nature_of_org": "nature_of_org",
		"pan_number_org_u_r": "pan_number",
		"gst_status_u_r": "gst_status",
		"gst_number_u_r": "gst_number",
		"other_registration_u_r": "other_registration",
		"overhead_percentage_u_r": "overhead_percentage",
		"discount_percentage_u_r": "discount_percentage",
		"agreement_number_u_r": "agreement_number",
		"signatory_name_u_r": "signatory_name",
		"signatory_designation_u_r": "signatory_designation",
		"date_of_signing_u_r": "date_of_signing",
		"decl_info_true_u_r": "declaration",
	}
	
	mapped_data = {}
	for doctype_field, value in data.items():
		# Map back to frontend field if reverse mapping exists, otherwise keep original
		frontend_field = reverse_mapping.get(doctype_field, doctype_field)
		mapped_data[frontend_field] = value
	
	return mapped_data

@frappe.whitelist(allow_guest=True)
def get_universal_registration___fields(doc_name=None):
	"""
	Return Universal Registration field metadata + prefill data.
	"""
	doctype_name = "Universal Registration__"
	try:
		meta = frappe.get_meta(doctype_name)
	except Exception:
		frappe.throw(_("DocType Universal Registration__ not found."))

	fields = []
	
	# --- 1. Build Fields List (recurse for child tables) ---
	for f in meta.fields:
		if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
			continue
			
		field_data = {
			"fieldname": f.fieldname,
			"label": _(f.label),
			"fieldtype": f.fieldtype,
			"options": getattr(f, "options", None),
			"mandatory": getattr(f, "reqd", False),
			"hidden": getattr(f, "hidden", False),
			"read_only": getattr(f, "read_only", False),
			"description": getattr(f, "description", "") or "",
			"default": getattr(f, "default", ""),
			"depends_on": getattr(f, "depends_on", None)
		}
		
		# Child table handling
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				child_fields = []
				for cf in child_meta.fields:
					if cf.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
						continue
					child_fields.append({
						"fieldname": cf.fieldname,
						"label": _(cf.label),
						"fieldtype": cf.fieldtype,
						"options": getattr(cf, "options", None),
						"mandatory": getattr(cf, "reqd", False),
						"hidden": getattr(cf, "hidden", False),
						"read_only": getattr(cf, "read_only", False),
						"in_list_view": getattr(cf, "in_list_view", False),
						"default": getattr(cf, "default", "")
					})
				field_data["child_fields"] = child_fields
			except Exception:
				pass
				
		fields.append(field_data)

	# --- 2. Link Options (Generic) ---
	link_options = {}
	for f in fields:
		if f["fieldtype"] == "Link" and f["options"]:
			try:
				doctype = f["options"]
				if doctype == "[Select]": continue

				# Try to get title field
				linked_meta = frappe.get_meta(doctype)
				title_field = linked_meta.get_title_field() or "name"
				
				# Fetch options
				options_list = frappe.get_list(
					doctype,
					fields=["name", title_field],
					limit_page_length=200,
					order_by=f"{title_field} asc" if title_field != "name" else "name asc"
				)
				
				link_options[f["fieldname"]] = [
					{"value": item["name"], "label": item.get(title_field, item["name"])}
					for item in options_list
				]
			except Exception:
				link_options[f["fieldname"]] = []

	# --- 3. Prefill Logic ---
	prefill_data = {}
	if doc_name:
		try:
			doc = frappe.get_doc(doctype_name, doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	elif frappe.session.user != "Guest":
		# Optional: Auto-fill user details if creating new from a logged-in user context
		try:
			user_doc = frappe.get_doc("User", frappe.session.user)
			prefill_data = {
				"email_address_u_r": frappe.session.user,
				"full_name_u_r": user_doc.full_name,
				"mobile_number_u_r": getattr(user_doc, "mobile_no", "")
			}
		except Exception:
			pass

	# --- 4. Client Scripts ---
	client_scripts = []
	try:
		scripts = frappe.get_all("Client Script", filters={"dt": doctype_name, "enabled": 1}, fields=["name", "script", "view"])
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts
	}

@frappe.whitelist(allow_guest=True)
def save_universal_registration___data(data=None, **kwargs):
	"""
	Save Universal Registration data (parent + child tables).
	Expects 'data' as a JSON string or dict, or accepts individual field arguments.
	Automatically maps frontend field names to DocType field names.
	Allows guest users to register.
	"""
	try:
		# Handle different input formats
		if data is None:
			# If no 'data' parameter, use kwargs as form fields
			data = kwargs
		elif isinstance(data, str):
			try:
				data = json.loads(data)
			except:
				# If data is not valid JSON, treat as single field and use kwargs
				data = kwargs
		
		# Filter out frappe system parameters
		data = {k: v for k, v in data.items() if k not in ['cmd', 'doctype', 'name_field']}
		
		# Map frontend field names to doctype field names
		data = map_frontend_fields_to_doctype(data)

		docname = data.get("name") or data.get("docname")
		
		if docname:
			doc = frappe.get_doc("Universal Registration__", docname)
		else:
			doc = frappe.new_doc("Universal Registration__")
		
		# Get metadata to filter valid fields
		meta = frappe.get_meta("Universal Registration__")

		# Iterate over data and set fields
		for fieldname, value in data.items():
			if not meta.has_field(fieldname):
				continue
			
			# Skip empty values
			if value is None or value == "":
				continue
				
			df = meta.get_field(fieldname)
			
			# Handle Phone fields
			if df.fieldtype == "Phone" and value:
				# Basic formatting: ensure it has country code if missing
				phone_str = str(value).strip()
				if not phone_str.startswith("+"):
					value = f"+91-{phone_str}"
				else:
					value = phone_str
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				
				for child_row in value:
					if not isinstance(child_row, dict):
						continue
						
					# Parse specific child fields
					for cf in child_meta.fields:
						# Handle Phone fields in child table
						if cf.fieldtype == "Phone" and child_row.get(cf.fieldname):
							p_val = child_row[cf.fieldname]
							if not str(p_val).startswith("+"):
								child_row[cf.fieldname] = f"+91-{p_val}"
								
						# Handle Attach fields (Base64) in child table
						elif cf.fieldtype in ["Attach", "Attach Image"] and child_row.get(cf.fieldname) and isinstance(child_row[cf.fieldname], dict) and child_row[cf.fieldname].get("file_data"):
							try:
								saved_file = save_file(
									child_row[cf.fieldname]["file_name"],
									child_row[cf.fieldname]["file_data"],
									"Universal Registration__",
									doc.name,
									decode=True,
									is_private=0,
									df=cf.fieldname
								)
								child_row[cf.fieldname] = saved_file.file_url
							except Exception as e:
								frappe.log_error(f"Child Table File Upload Error: {str(e)}")
								child_row[cf.fieldname] = None

					doc.append(fieldname, child_row)
					
			# Handle Attach fields (Base64) - if sent as dict {file_name, file_data}
			elif df.fieldtype in ["Attach", "Attach Image"] and isinstance(value, dict) and value.get("file_data"):
				try:
					saved_file = save_file(
						value["file_name"],
						value["file_data"],
						doc.doctype,
						doc.name,
						decode=True,
						is_private=0,
						df=fieldname
					)
					doc.set(fieldname, saved_file.file_url)
				except Exception as e:
					frappe.log_error(f"File Upload Error: {str(e)}")
					pass
				
			# Standard fields
			else:
				doc.set(fieldname, value)

		# For guest users, set owner as system
		if doc.is_new():
			if frappe.session.user == "Guest":
				doc.owner = "Administrator"
			else:
				doc.owner = frappe.session.user

		# Auto-populate uploaded_documents_u_r child table for Identity files
		identity_docs_mapping = [
			{"file": "aadhaar_file_u_r", "number": "aadhaar_number_u_r", "name": "Aadhaar Card", "expiry": "aadhaar_expiry_u_r"},
			{"file": "pan_file_u_r", "number": "pan_number_u_r", "name": "PAN Card", "expiry": "pan_expiry_u_r"},
			{"file": "other_file_u_r", "number": "other_identity_number_u_r", "name": "Other Identity", "expiry": "other_expiry_u_r"}
		]
		
		for doc_map in identity_docs_mapping:
			file_url = doc.get(doc_map["file"])
			if file_url:
				exists = False
				for row in doc.get("uploaded_documents_u_r", []):
					if row.document_name_u_r == doc_map["name"] and row.file_u_r == file_url:
						exists = True
						break
				
				if not exists:
					doc.append("uploaded_documents_u_r", {
						"document_name_u_r": doc_map["name"],
						"document_type_u_r": "Identity",
						"id_number_u_r": doc.get(doc_map["number"]),
						"file_u_r": file_url,
						"expiry_date_u_r": doc.get(doc_map["expiry"])
					})

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Saved successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Universal Registration Save Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration___list(filters=None, limit=None, offset=None):
	"""
	Fetch a list of Universal Registration documents with optional filtering.
	"""
	try:
		if filters and isinstance(filters, str):
			filters = json.loads(filters)
		
		limit = int(limit) if limit else 50
		offset = int(offset) if offset else 0
		
		# Build filter conditions
		filter_conditions = {}
		if filters:
			for key, value in filters.items():
				if value:
					filter_conditions[key] = value
		
		# Fetch documents
		documents = frappe.get_list(
			"Universal Registration__",
			filters=filter_conditions,
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r", "modified", "owner"],
			order_by="modified desc",
			limit=limit,
			start=offset
		)
		
		# Get total count
		total = frappe.db.count(
			"Universal Registration__",
			filters=filter_conditions
		)
		
		return {
			"status": "success",
			"data": documents,
			"total": total,
			"limit": limit,
			"offset": offset
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration List Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration___details(docname):
	"""
	Fetch complete details of a Universal Registration document.
	Returns data with both doctype and frontend field names for flexibility.
	"""
	try:
		doc = frappe.get_doc("Universal Registration__", docname)
		
		# Convert to dictionary for response
		doc_dict = doc.as_dict()
		
		# Also provide frontend-mapped version
		frontend_mapped = map_doctype_fields_to_frontend(doc_dict.copy())
		
		return {
			"status": "success",
			"data": doc_dict,
			"data_frontend": frontend_mapped
		}
	except frappe.DoesNotExistError:
		return {"status": "error", "message": f"Universal Registration document '{docname}' not found."}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration Details Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def update_universal_registration___data(docname, data):
	"""
	Update an existing Universal Registration document.
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)
		
		doc = frappe.get_doc("Universal Registration__", docname)
		
		# Get metadata to filter valid fields
		meta = frappe.get_meta("Universal Registration__")
		
		# Iterate over data and update fields
		for fieldname, value in data.items():
			if not meta.has_field(fieldname):
				continue
				
			df = meta.get_field(fieldname)
			
			# Handle Phone fields
			if df.fieldtype == "Phone" and value:
				if not str(value).startswith("+"):
					value = f"+91-{value}"
			
			# Handle Child Tables
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				
				for child_row in value:
					if not isinstance(child_row, dict):
						continue
					# Handle Parse specific child fields
					for cf in child_meta.fields:
						if cf.fieldtype == "Phone" and child_row.get(cf.fieldname):
							p_val = child_row[cf.fieldname]
							if not str(p_val).startswith("+"):
								child_row[cf.fieldname] = f"+91-{p_val}"
						elif cf.fieldtype in ["Attach", "Attach Image"] and child_row.get(cf.fieldname) and isinstance(child_row[cf.fieldname], dict) and child_row[cf.fieldname].get("file_data"):
							try:
								saved_file = save_file(
									child_row[cf.fieldname]["file_name"],
									child_row[cf.fieldname]["file_data"],
									"Universal Registration__",
									doc.name,
									decode=True,
									is_private=0,
									df=cf.fieldname
								)
								child_row[cf.fieldname] = saved_file.file_url
							except Exception as e:
								frappe.log_error(f"Child Table File Upload Error: {str(e)}")
								child_row[cf.fieldname] = None

					doc.append(fieldname, child_row)
					
			# Handle Attach fields (Base64)
			elif df.fieldtype in ["Attach", "Attach Image"] and isinstance(value, dict) and value.get("file_data"):
				try:
					saved_file = save_file(
						value["file_name"],
						value["file_data"],
						doc.doctype,
						doc.name,
						decode=True,
						is_private=0,
						df=fieldname
					)
					doc.set(fieldname, saved_file.file_url)
				except Exception as e:
					frappe.log_error(f"File Upload Error: {str(e)}")
					pass
				
			# Standard fields
			else:
				doc.set(fieldname, value)

		# Auto-populate uploaded_documents_u_r child table for Identity files
		identity_docs_mapping = [
			{"file": "aadhaar_file_u_r", "number": "aadhaar_number_u_r", "name": "Aadhaar Card", "expiry": "aadhaar_expiry_u_r"},
			{"file": "pan_file_u_r", "number": "pan_number_u_r", "name": "PAN Card", "expiry": "pan_expiry_u_r"},
			{"file": "other_file_u_r", "number": "other_identity_number_u_r", "name": "Other Identity", "expiry": "other_expiry_u_r"}
		]
		
		for doc_map in identity_docs_mapping:
			file_url = doc.get(doc_map["file"])
			if file_url:
				exists = False
				for row in doc.get("uploaded_documents_u_r", []):
					if row.document_name_u_r == doc_map["name"] and row.file_u_r == file_url:
						exists = True
						break
				
				if not exists:
					doc.append("uploaded_documents_u_r", {
						"document_name_u_r": doc_map["name"],
						"document_type_u_r": "Identity",
						"id_number_u_r": doc.get(doc_map["number"]),
						"file_u_r": file_url,
						"expiry_date_u_r": doc.get(doc_map["expiry"])
					})

		doc.flags.ignore_permissions = True
		doc.save()
		frappe.db.commit()

		return {"status": "success", "docname": doc.name, "message": "Updated successfully."}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Universal Registration Update Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def delete_universal_registration__(docname):
	"""
	Delete a Universal Registration document.
	"""
	try:
		frappe.delete_doc("Universal Registration__", docname, force=1)
		frappe.db.commit()
		
		return {"status": "success", "message": f"Document '{docname}' deleted successfully."}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Delete Universal Registration Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration___by_email(email):
	"""
	Fetch a Universal Registration document by email address.
	"""
	try:
		# Search for document with matching email
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"email_address_u_r": email},
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=1
		)
		
		if documents:
			# Get full details of the first match
			return get_universal_registration___details(documents[0]["name"])
		else:
			return {"status": "error", "message": f"No Universal Registration found with email '{email}'."}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration by Email Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_universal_registration___by_phone(phone):
	"""
	Fetch a Universal Registration document by phone number.
	"""
	try:
		# Search for document with matching phone
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"mobile_number_u_r": phone},
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=1
		)
		
		if documents:
			return get_universal_registration___details(documents[0]["name"])
		else:
			return {"status": "error", "message": f"No Universal Registration found with phone '{phone}'."}
			
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Universal Registration by Phone Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def search_universal_registration__(search_text):
	"""
	Search Universal Registration documents by name, email, or phone.
	"""
	try:
		# Search across multiple fields
		documents = frappe.get_list(
			"Universal Registration__",
			filters=[
				["name", "like", f"%{search_text}%"],
				"or",
				["full_name_u_r", "like", f"%{search_text}%"],
				"or",
				["email_address_u_r", "like", f"%{search_text}%"],
				"or",
				["mobile_number_u_r", "like", f"%{search_text}%"],
				"or",
				["org_name_u_r", "like", f"%{search_text}%"]
			],
			fields=["name", "profile_type_u_r", "full_name_u_r", "email_address_u_r", "mobile_number_u_r", "org_name_u_r"],
			limit=50
		)
		
		return {
			"status": "success",
			"data": documents,
			"count": len(documents)
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Search Universal Registration Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_registration_by_profile_type(profile_type):
	"""
	Fetch all registrations of a specific profile type (Individual or Organization).
	"""
	try:
		documents = frappe.get_list(
			"Universal Registration__",
			filters={"profile_type_u_r": profile_type},
			fields=["name", "profile_type_u_r", "full_name_u_r", "org_name_u_r", "email_address_u_r", "mobile_number_u_r", "modified"],
			order_by="modified desc",
			limit=100
		)
		
		return {
			"status": "success",
			"profile_type": profile_type,
			"count": len(documents),
			"data": documents
		}
		
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Registration by Profile Type Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def check_email_availability(email=None, exclude_docname=None):
	"""
	Real-time email availability check.
	Checks both Universal Registration__ and Frappe core User tables.
	Returns availability status with details about where the email was found.
	"""
	try:
		if not email or not email.strip():
			return {"status": "error", "message": "Email is required."}

		email = email.strip().lower()
		found_in = []

		# 1. Check in Universal Registration__
		ur_filters = {"email_address_u_r": email}
		if exclude_docname:
			ur_filters["name"] = ["!=", exclude_docname]

		if frappe.db.exists("Universal Registration__", ur_filters):
			found_in.append("Universal Registration")

		# 2. Check in Frappe core User (User doctype uses email as the 'name' field)
		if frappe.db.exists("User", email):
			found_in.append("System User")

		if found_in:
			return {
				"status": "success",
				"available": False,
				"found_in": found_in,
				"message": f"This email is already registered in: {', '.join(found_in)}"
			}
		else:
			return {
				"status": "success",
				"available": True,
				"found_in": [],
				"message": "Email is available."
			}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Check Email Availability Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist(allow_guest=True)
def get_external_profile(search=None):
	"""
	Free-form / fuzzy search across full_name_u_r and email_address_u_r.
	Accepts: ?search=<term>
	Returns ALL matching records with their child table details.
	"""
	term = (search or "").strip()
	if not term:
		return {"status": "error", "message": "Provide at least one of: search, email, or name."}

	like = f"%{term}%"

	# Build OR filter across email and full_name
	matches = frappe.db.sql(
		"""
		SELECT name, full_name_u_r, mobile_number_u_r, email_address_u_r
		FROM `tabUniversal Registration__`
		WHERE email_address_u_r LIKE %(like)s
		   OR full_name_u_r     LIKE %(like)s
		ORDER BY
			CASE WHEN email_address_u_r = %(term)s THEN 0
			     WHEN full_name_u_r     = %(term)s THEN 1
			     ELSE 2 END,
			full_name_u_r ASC
		""",
		{"like": like, "term": term},
		as_dict=True
	)

	if not matches:
		return {"status": "error", "message": f"No registration found matching '{term}'."}

	address_fields = [
		"address_type_u_r",
		"address_line_1_u_r",
		"address_line_2_u_r",
		"landmark_u_r",
		"pincode_u_r",
		"district_u_r",
		"city_u_r",
		"state_u_r"
	]

	results = []
	for match in matches:
		docname = match["name"]

		institution_rows = frappe.db.get_all(
			"Institution Details",
			filters={"parent": docname, "parenttype": "Universal Registration__"},
			fields=[
				"institution_name_u_r",
				"designation_u_r",
				"address_institution_u_r",
				"website_link_u_r",
				"department_u_r"
			],
			order_by="idx asc"
		)

		address_rows = frappe.db.get_all(
			"Universal Address__",
			filters={"parent": docname, "parentfield": "address_details", "parenttype": "Universal Registration__"},
			fields=address_fields,
			order_by="idx asc"
		)

		org_address_rows = frappe.db.get_all(
			"Universal Address__",
			filters={"parent": docname, "parentfield": "org_address_details_u_r", "parenttype": "Universal Registration__"},
			fields=address_fields,
			order_by="idx asc"
		)

		results.append({
			"full_name_u_r":           match.get("full_name_u_r"),
			"mobile_number_u_r":       match.get("mobile_number_u_r"),
			"email_address_u_r":       match.get("email_address_u_r"),
			"institution_details_u_r": institution_rows,
			"address_details":         address_rows,
			"org_address_details_u_r": org_address_rows
		})

	return {
		"status": "success",
		"count": len(results),
		"data": results
	}


@frappe.whitelist(allow_guest=True)
def check_duplicate_registration(email=None, id_numbers=None, exclude_docname=None):
	"""
	Check if an email or any ID Number already exists.
	"""
	try:
		duplicates = []
		
		# Check Email
		if email:
			filters = {"email_address_u_r": email}
			if exclude_docname:
				filters["name"] = ["!=", exclude_docname]
			
			if frappe.db.exists("Universal Registration__", filters):
				duplicates.append("Email")
				
		# Check ID Numbers
		if id_numbers:
			if isinstance(id_numbers, str):
				id_numbers = json.loads(id_numbers)
				
			for id_num in id_numbers:
				query = "SELECT parent FROM `tabUniversal Documents__` WHERE parenttype = 'Universal Registration__' AND id_number_u_r = %s"
				args = [id_num]
				if exclude_docname:
					query += " AND parent != %s"
					args.append(exclude_docname)
					
				if frappe.db.sql(query, tuple(args)):
					if "ID Number" not in duplicates:
						duplicates.append("ID Number")
					break
					
		return {
			"status": "success",
			"has_duplicate": len(duplicates) > 0,
			"duplicates": duplicates
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Check Duplicate Registration Error")
		return {"status": "error", "message": str(e)}