# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from datetime import datetime


class UniversalUser__(Document):
	"""
	Universal User__ DocType for managing user authentication.
	
	This is the core user record that stores:
	- Identity information (full_name_u_r, email_u_r, username_u_r, profile_type_u_r)
	- Email verification status (is_email_verified_u_r)
	- Password information (password_hash_u_r, password_salt_u_r, password_set_on_u_r, is_password_set_u_r)
	- Authentication mapping (auth_user_id_u_r, is_auth_enabled_u_r, status_u_r)
	- Audit information (created_by_ip_u_r, last_login_at_u_r)
	
	All signup operations are handled through auth_api.py:
	- signup() -> Creates this record with initial data
	- verify_otp() -> Updates is_email_verified_u_r
	- set_password() -> Updates password fields and is_password_set_u_r
	"""
	
	def autoname(self):
		"""Generate user ID in format: U_U_YYYYMMDD_HHMMSS"""
		timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
		self.name = f"U_U_{timestamp}"
	
	def validate(self):
		"""Validate Universal User__ record"""
		if not self.email_u_r:
			frappe.throw("Email is mandatory")
		
		if not self.full_name_u_r:
			frappe.throw("Full Name is mandatory")
	
	def before_save(self):
		"""Set defaults before saving"""
		if not self.status_u_r:
			self.status_u_r = "Active"
		
		if not self.profile_type_u_r:
			self.profile_type_u_r = "Individual"
		
		if not self.is_email_verified_u_r:
			self.is_email_verified_u_r = 0
		
		if not self.is_password_set_u_r:
			self.is_password_set_u_r = 0
		
		if not getattr(self, 'is_auth_enabled_u_r', None):
			self.is_auth_enabled_u_r = 1
		
		# Ensure datetime fields are None, not 0
		if not self.password_set_on_u_r or self.password_set_on_u_r == '0' or self.password_set_on_u_r == 0:
			self.password_set_on_u_r = None
		
		if not self.last_login_at_u_r or self.last_login_at_u_r == '0' or self.last_login_at_u_r == 0:
			self.last_login_at_u_r = None


@frappe.whitelist(allow_guest=True)
def get_universal_user___fields(doc_name=None):
	"""Returns field metadata and client scripts for Universal User__"""
	meta = frappe.get_meta('Universal User__')
	fields = []
	
	for f in meta.fields:
		if f.fieldtype in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]:
			continue
			
		field_data = {
			'fieldname': f.fieldname,
			'label': f.label,
			'fieldtype': f.fieldtype,
			'options': f.options,
			'mandatory': f.reqd,
			'read_only': f.read_only,
			'default': f.default,
			'hidden': f.hidden,
			'description': f.description,
			'depends_on': f.depends_on,
			'mandatory_depends_on': f.mandatory_depends_on,
			'read_only_depends_on': f.read_only_depends_on,
			'depends_on_eval': f.depends_on.replace('eval:', '') if f.depends_on and str(f.depends_on).startswith('eval:') else None,
			'mandatory_depends_on_eval': f.mandatory_depends_on.replace('eval:', '') if f.mandatory_depends_on and str(f.mandatory_depends_on).startswith('eval:') else None,
			'read_only_depends_on_eval': f.read_only_depends_on.replace('eval:', '') if f.read_only_depends_on and str(f.read_only_depends_on).startswith('eval:') else None,
		}
		
		if f.fieldtype == 'Table':
			child_meta = frappe.get_meta(f.options)
			field_data['child_fields'] = [{
				'fieldname': cf.fieldname,
				'label': cf.label,
				'fieldtype': cf.fieldtype,
				'options': cf.options,
				'mandatory': cf.reqd,
				'read_only': cf.read_only,
				'default': cf.default,
				'hidden': cf.hidden,
				'description': cf.description,
				'depends_on': cf.depends_on,
				'mandatory_depends_on': cf.mandatory_depends_on,
				'read_only_depends_on': cf.read_only_depends_on,
				'depends_on_eval': cf.depends_on.replace('eval:', '') if cf.depends_on and str(cf.depends_on).startswith('eval:') else None,
				'mandatory_depends_on_eval': cf.mandatory_depends_on.replace('eval:', '') if cf.mandatory_depends_on and str(cf.mandatory_depends_on).startswith('eval:') else None,
				'read_only_depends_on_eval': cf.read_only_depends_on.replace('eval:', '') if cf.read_only_depends_on and str(cf.read_only_depends_on).startswith('eval:') else None,
				'in_list_view': cf.in_list_view
			} for cf in child_meta.fields if cf.fieldtype not in ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]]
			
		fields.append(field_data)
		
	prefill_data = {}
	link_options = {}

	def _fetch_link_options(f_list):
		for field in f_list:
			if field.get("fieldtype") == "Table" and "child_fields" in field:
				_fetch_link_options(field["child_fields"])
			elif field.get("fieldtype") == "Link" and field.get("options"):
				try:
					linked_doctype = field["options"]
					linked_meta = frappe.get_meta(linked_doctype)
					title_field = linked_meta.get_title_field()

					options_list = frappe.get_all(
						linked_doctype,
						fields=["name", title_field],
						limit=0,
					)

					link_options[field["fieldname"]] = [
						{"value": item["name"], "label": item.get(title_field, item["name"])}
						for item in options_list
					]
				except Exception:
					link_options[field["fieldname"]] = []
	
	_fetch_link_options(fields)

	if doc_name:
		try:
			doc = frappe.get_doc('Universal User__', doc_name)
			prefill_data = doc.as_dict()
		except frappe.DoesNotExistError:
			pass

	client_scripts = []
	try:
		scripts = frappe.get_all('Client Script', filters={'dt': 'Universal User__', 'enabled': 1}, fields=['name', 'script', 'view'])
		for script in scripts:
			client_scripts.append({
				'name': script.name,
				'script': script.script,
				'view': script.view
			})
	except Exception:
		pass

	return {
		'fields': fields,
		'prefill_data': prefill_data,
		'link_options': link_options,
		'client_scripts': client_scripts
	}


@frappe.whitelist(allow_guest=True)
def save_universal_user___data(data):
	"""
	Saves Universal User data.
	Handles Phone number formatting (+91)
	"""
	import json
	
	if isinstance(data, str):
		data = json.loads(data)
		
	doc_name = data.get('name')
	
	if doc_name:
		doc = frappe.get_doc('Universal User__', doc_name)
	else:
		doc = frappe.new_doc('Universal User__')
	
	for key, value in data.items():
		if key not in ['name', 'doctype', 'owner', 'creation', 'modified', 'modified_by', 'idx']:
			if hasattr(doc, key):
				setattr(doc, key, value)
	
	# Phone number formatting (+91)
	if getattr(doc, 'mobile_number_u_r', None):
		mobile = str(doc.mobile_number_u_r).strip()
		# If user didn't provide standard country code
		if not mobile.startswith('+'):
			# E.g. 919876543210 -> +919876543210
			if mobile.startswith('91') and len(mobile) == 12:
				doc.mobile_number_u_r = '+' + mobile
			else:
				# E.g. 9876543210 -> +919876543210
				doc.mobile_number_u_r = '+91' + mobile.lstrip('0')
				
	# Save the document independently of standard permission validations (it might be guest signup)
	doc.flags.ignore_permissions = True
	doc.save()
	
	return {
		'status': 'success',
		'docname': doc.name
	}