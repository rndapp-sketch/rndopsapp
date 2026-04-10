# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
import random
import string
from datetime import datetime, timedelta
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


class EmailOTP__(Document):
	"""
	DocType for managing Email OTP (One-Time Password) for user registration and login.
	Handles OTP generation, sending, and verification.
	"""
	
	def validate(self):
		"""Validate OTP document before saving"""
		# Ensure email is provided
		if not self.email_u_r:
			frappe.throw("Email Address is mandatory")
		
		# Check if email is valid
		if not self._is_valid_email(self.email_u_r):
			frappe.throw("Invalid email address format")
	
	def before_save(self):
		"""Set default values before saving"""
		if not getattr(self, 'otp_attempts_u_r', None):
			self.otp_attempts_u_r = 0
		
		if not getattr(self, 'resent_count_u_r', None):
			self.resent_count_u_r = 0
		
		if not getattr(self, 'is_expired_u_r', None):
			self.is_expired_u_r = 0
	
	def _is_valid_email(self, email):
		"""Validate email format"""
		import re
		pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
		return re.match(pattern, email) is not None
	
	@staticmethod
	def generate_otp(length=6):
		"""Generate a random OTP of specified length (default 6 digits)"""
		return ''.join(random.choices(string.digits, k=length))
