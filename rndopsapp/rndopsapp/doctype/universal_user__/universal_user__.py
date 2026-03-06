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
