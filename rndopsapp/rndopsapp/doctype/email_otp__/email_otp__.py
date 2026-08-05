# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
import random
import string
import hashlib
import secrets
from datetime import datetime, timedelta
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


def _hash_password(password, salt=None):
	if salt is None:
		salt = secrets.token_hex(16)
	
	password_hash = hashlib.pbkdf2_hmac(
		'sha256',
		password.encode('utf-8'),
		salt.encode('utf-8'),
		100000
	)
	return password_hash.hex(), salt


class EmailOTP__(Document):
	"""
	DocType for managing Email OTP (One-Time Password) for user registration and login.
	Handles OTP generation, sending, and verification.
	"""
	
	def validate(self):
		"""Validate OTP document before saving"""
		email = self.get("email_u_r")
		# Ensure email is provided
		if not email:
			frappe.throw("Email Address is mandatory")
		
		# Check if email is valid
		if not self._is_valid_email(email):
			frappe.throw("Invalid email address format")
	
	def before_save(self):
		"""Set default values before saving"""
		if not self.get("otp_attempts_u_r"):
			self.set("otp_attempts_u_r", 0)
		
		if not self.get("resent_count_u_r"):
			self.set("resent_count_u_r", 0)
		
		if not self.get("is_expired_u_r"):
			self.set("is_expired_u_r", 0)
	
	def _is_valid_email(self, email):
		"""Validate email format"""
		import re
		pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
		return re.match(pattern, email) is not None
	
	@staticmethod
	def generate_otp(length=6):
		"""Generate a random OTP of specified length (default 6 digits)"""
		return ''.join(random.choices(string.digits, k=length))


@frappe.whitelist(allow_guest=True)
def send_otp_for_signup(email, full_name=None):
	"""
	Generate and send OTP to user email for registration.
	CHECKS IF USER ALREADY EXISTS.
	"""
	try:
		# 1. Validate email presence
		if not email:
			frappe.throw("Email address is required")
		
		# 2. Validate email format
		if not _is_valid_email(email):
			frappe.throw("Invalid email address format")

		# ------------------------------------------------------------------
		# 3. CHECK FOR EXISTING USER IN UNIVERSAL USER__ DOCTYPE
		# ------------------------------------------------------------------
		existing_user = frappe.db.get_value(
			"Universal User__",
			{"email_u_r": email},
			["name", "is_password_set_u_r"],
			as_dict=True
		)
		if existing_user and existing_user.get("is_password_set_u_r"):
			return {
				"status": "error",
				"message": "Email already registered. Please login or use a different email.",
				"success": False
			}
		# ------------------------------------------------------------------
		
		# 4. Generate OTP
		otp = EmailOTP__.generate_otp(6)
		
		# Set expiry time (10 minutes from now)
		expiry_time = add_to_date(now_datetime(), minutes=10)
		
		# Create OTP record
		otp_doc = frappe.get_doc({
			"doctype": "Email OTP__",
			"email_u_r": email,
			"otp_u_r": otp,
			"purpose_u_r": "Registration",
			"expiry_time_u_r": expiry_time,
			"is_verified_u_r": 0,
			"is_expired_u_r": 0,
			"otp_attempts_u_r": 0,
			"resent_count_u_r": 0,
			"last_sent_at_u_r": now_datetime()
		})
		
		otp_doc.flags.ignore_permissions = True
		otp_doc.insert()
		
		frappe.logger().info(f"OTP document created: {otp_doc.name} for {email}")
		
		# Send email
		_send_otp_email(email, otp, expiry_time, full_name)
		
		return {
			"status": "success",
			"message": f"OTP sent to {email}",
			"otp_record": otp_doc.name,
			"otp_value": otp,
			"email": email,
			"success": True
		}
	
	except frappe.PermissionError:
		frappe.log_error(frappe.get_traceback(), "send_otp_for_signup permission error")
		return {
			"status": "error",
			"message": "Permission denied. Unable to process signup.",
			"success": False
		}
	except frappe.ValidationError as ve:
		frappe.log_error(frappe.get_traceback(), "send_otp_for_signup validation error")
		return {
			"status": "error",
			"message": str(ve),
			"success": False
		}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "send_otp_for_signup error")
		return {
			"status": "error",
			"message": f"Error sending OTP: {str(e)}",
			"success": False
		}


@frappe.whitelist(allow_guest=True)
def verify_otp(email, otp_value):
	"""
	Verify OTP entered by user
	
	Args:
		email (str): User's email address
		otp_value (str): OTP entered by user
	
	Returns:
		dict: Verification status
	"""
	try:
		# Find OTP record
		otp_records = frappe.get_all(
			"Email OTP__",
			filters={
				"email_u_r": email,
				"purpose_u_r": "Registration",
				"is_verified_u_r": 0
			},
			order_by="creation desc",
			limit=1,
			ignore_permissions=True
		)
		
		if not otp_records:
			return {
				"status": "error",
				"message": "No OTP found for this email or OTP already verified",
				"success": False
			}
		
		otp_doc = frappe.get_doc("Email OTP__", otp_records[0].name)
		
		# Check if OTP is expired
		if _is_otp_expired(otp_doc):
			otp_doc.flags.ignore_permissions = True
			otp_doc.set("is_expired_u_r", 1)
			otp_doc.save()
			return {
				"status": "error",
				"message": "OTP has expired. Please request a new OTP",
				"success": False
			}
		
		# Check OTP attempts
		attempts = otp_doc.get("otp_attempts_u_r") or 0
		if attempts >= 3:
			return {
				"status": "error",
				"message": "Maximum OTP attempts exceeded. Please request a new OTP",
				"success": False
			}
		
		# Verify OTP
		if otp_doc.get("otp_u_r") != str(otp_value):
			otp_doc.flags.ignore_permissions = True
			new_attempts = attempts + 1
			otp_doc.set("otp_attempts_u_r", new_attempts)
			otp_doc.save()
			remaining = 3 - new_attempts
			return {
				"status": "error",
				"message": f"Invalid OTP. Attempts remaining: {remaining}",
				"success": False,
				"attempts_remaining": remaining
			}
		
		# Mark as verified
		otp_doc.flags.ignore_permissions = True
		otp_doc.set("is_verified_u_r", 1)
		otp_doc.set("verified_at_u_r", now_datetime())
		otp_doc.save()
		
		return {
			"status": "success",
			"message": "OTP verified successfully",
			"email": email,
			"success": True
		}
	
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "verify_otp error")
		return {
			"status": "error",
			"message": f"OTP verification failed: {str(e)}",
			"success": False
		}


@frappe.whitelist(allow_guest=True)
def resend_otp(email):
	"""
	Resend OTP to user email
	
	Args:
		email (str): User's email address
	
	Returns:
		dict: Status of resend operation
	"""
	try:
		# Validate email
		if not email:
			return {
				"status": "error",
				"message": "Email address is required",
				"success": False
			}
		
		# Find the latest unverified OTP
		otp_records = frappe.get_all(
			"Email OTP__",
			filters={
				"email_u_r": email,
				"purpose_u_r": "Registration",
				"is_verified_u_r": 0
			},
			order_by="creation desc",
			limit=1,
			ignore_permissions=True
		)
		
		if not otp_records:
			# If no unverified OTP exists, create a new one
			return send_otp_for_signup(email)
		
		otp_doc = frappe.get_doc("Email OTP__", otp_records[0].name)
		
		# Check resend limit (max 3 resends)
		resent_count = otp_doc.get("resent_count_u_r") or 0
		if resent_count >= 3:
			return {
				"status": "error",
				"message": "Maximum resend attempts exceeded. Please try again later",
				"success": False
			}
		
		# Update resend count and timestamp
		otp_doc.flags.ignore_permissions = True
		otp_doc.set("resent_count_u_r", resent_count + 1)
		otp_doc.set("last_sent_at_u_r", now_datetime())
		
		# Extend expiry time
		otp_doc.set("expiry_time_u_r", add_to_date(now_datetime(), minutes=10))
		otp_doc.save()
		
		otp_value = otp_doc.get("otp_u_r")
		expiry_time = otp_doc.get("expiry_time_u_r")
		
		# Send email
		_send_otp_email(email, otp_value, expiry_time)
		
		return {
			"status": "success",
			"message": f"OTP resent to {email}",
			"otp_value": otp_value,
			"resend_count": otp_doc.get("resent_count_u_r"),
			"success": True
		}
	
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "resend_otp error")
		return {
			"status": "error",
			"message": f"Error resending OTP: {str(e)}",
			"success": False
		}


def _is_valid_email(email):
	"""Validate email format"""
	import re
	pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
	return re.match(pattern, email) is not None


def _is_otp_expired(otp_doc):
	"""Check if OTP is expired"""
	if otp_doc.get("is_expired_u_r"):
		return True
	
	expiry_time = otp_doc.get("expiry_time_u_r")
	current_time = now_datetime()
	
	return current_time > expiry_time


def _send_otp_email(email, otp, expiry_time, full_name=None):
	"""
	Send OTP email to user
	
	Args:
		email (str): Recipient email address
		otp (str): Generated OTP
		expiry_time (datetime): OTP expiry time
		full_name (str): User's full name (optional)
	"""
	try:
		# Format expiry time for display
		expiry_datetime = expiry_time if hasattr(expiry_time, 'strftime') else datetime.fromisoformat(str(expiry_time))
		expiry_display = expiry_datetime.strftime("%d %B %Y at %I:%M %p")
		
		# Prepare email content
		subject = "Your OTP for Registration"
		
		html_content = f"""
		<html>
			<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
				<div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
					<h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">Email Verification</h2>
					
					<p>Hello {full_name or 'User'},</p>
					
					<p>Thank you for signing up! To complete your registration, please use the following One-Time Password (OTP):</p>
					
					<div style="background-color: #f8f9fa; padding: 20px; border-left: 4px solid #3498db; margin: 20px 0; border-radius: 5px;">
						<p style="text-align: center; font-size: 28px; font-weight: bold; color: #2c3e50; letter-spacing: 2px; margin: 0;">
							{otp}
						</p>
					</div>
					
					<table style="width: 100%; margin: 20px 0;">
						<tr>
							<td style="padding: 8px; border-bottom: 1px solid #ecf0f1; font-weight: bold;">Username (Email):</td>
							<td style="padding: 8px; border-bottom: 1px solid #ecf0f1;">{email}</td>
						</tr>
						<tr>
							<td style="padding: 8px; border-bottom: 1px solid #ecf0f1; font-weight: bold;">OTP Expires:</td>
							<td style="padding: 8px; border-bottom: 1px solid #ecf0f1;">{expiry_display}</td>
						</tr>
					</table>
					
					<p style="color: #e74c3c; font-weight: bold;">
						⚠️ Important: Do not share this OTP with anyone. We will never ask for your OTP via email or phone.
					</p>
					
					<p>If you did not create an account, please ignore this email.</p>
					
					<hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
					
					<p style="font-size: 12px; color: #7f8c8d;">
						This is an automated message. Please do not reply to this email.
					</p>
				</div>
			</body>
		</html>
		"""
		
		# Try to send email
		try:
			frappe.sendmail(
				recipients=[email],
				subject=subject,
				message=html_content,
				now=True
			)
			frappe.logger().info(f"OTP email sent to {email}")
		
		except frappe.OutgoingEmailError:
			# If email account is not configured, log the OTP for manual testing
			frappe.logger().warning(f"""
			========================================
			EMAIL ACCOUNT NOT CONFIGURED - OTP LOG
			========================================
			To: {email}
			Subject: {subject}
			OTP Code: {otp}
			Full Name: {full_name or 'N/A'}
			Expires: {expiry_display}
			========================================
			
			To enable email sending:
			1. Go to Setup → Email Account
			2. Configure SMTP settings
			3. Mark as Default Outgoing
			""")
			frappe.logger().info(f"OTP generated for {email}: {otp} (expires {expiry_display})")
	
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Email sending error")
		frappe.throw(f"Failed to process OTP: {str(e)}")


@frappe.whitelist(allow_guest=True)
def create_user_with_password(email, password, full_name=None):
	"""
	Create or update a Universal User__ record after OTP verification.
	Stores user credentials ONLY in Universal User__ Doctype (NOT Frappe core User).
	"""
	try:
		# Validate inputs
		if not email:
			return {
				"status": "error",
				"message": "Email address is required",
				"success": False
			}
		
		if not password or len(password) < 8:
			return {
				"status": "error",
				"message": "Password must be at least 8 characters long",
				"success": False
			}
		
		if not _is_valid_email(email):
			return {
				"status": "error",
				"message": "Invalid email address format",
				"success": False
			}
		
		# Check if OTP was verified for this email
		otp_records = frappe.get_all(
			"Email OTP__",
			filters={
				"email_u_r": email,
				"is_verified_u_r": 1,
				"purpose_u_r": "Registration"
			},
			fields=["name"],
			order_by="verified_at_u_r desc",
			limit=1,
			ignore_permissions=True
		)
		
		if not otp_records:
			return {
				"status": "error",
				"message": "Email not verified. Please verify OTP first.",
				"success": False
			}
		
		# Read full_name from parameter or default to formatted username from email
		username_part = email.split("@")[0].lower()
		full_name = full_name or username_part.replace(".", " ").replace("_", " ").title()
		
		# Hash password for Universal User__
		password_hash, password_salt = _hash_password(password)
		
		# Check if Universal User__ record already exists
		existing_universal_user = frappe.db.exists("Universal User__", {"email_u_r": email})
		
		if existing_universal_user:
			universal_user = frappe.get_doc("Universal User__", existing_universal_user)
			if universal_user.get("is_password_set_u_r"):
				return {
					"status": "error",
					"message": "User with this email already registered",
					"success": False
				}
			universal_user.set("full_name_u_r", full_name)
			universal_user.set("password_hash_u_r", password_hash)
			universal_user.set("password_salt_u_r", password_salt)
			universal_user.set("is_password_set_u_r", 1)
			universal_user.set("is_email_verified_u_r", 1)
			universal_user.set("password_set_on_u_r", now_datetime())
			universal_user.set("status_u_r", "Active")
		else:
			# Create new Universal User__ record (strictly in Universal User__ Doctype)
			universal_user = frappe.get_doc({
				"doctype": "Universal User__",
				"full_name_u_r": full_name,
				"email_u_r": email,
				"username_u_r": username_part,
				"profile_type_u_r": "Individual",
				"status_u_r": "Active",
				"is_auth_enabled_u_r": 1,
				"is_email_verified_u_r": 1,
				"is_password_set_u_r": 1,
				"password_hash_u_r": password_hash,
				"password_salt_u_r": password_salt,
				"password_set_on_u_r": now_datetime(),
				"auth_created_on_u_r": now_datetime()
			})
		
		universal_user.flags.ignore_permissions = True
		universal_user.save()
		
		frappe.logger().info(f"Universal User created: {universal_user.name}")
		
		# Link OTP to universal user
		otp_doc = frappe.get_doc("Email OTP__", otp_records[0].name)
		otp_doc.flags.ignore_permissions = True
		otp_doc.set("universal_user_u_r", universal_user.name)
		otp_doc.save()
		
		frappe.db.commit()
		
		return {
			"status": "success",
			"message": "Account created successfully",
			"success": True,
			"email": email,
			"username": username_part,
			"universal_user_id": universal_user.name
		}
	
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "create_user_with_password error")
		return {
			"status": "error",
			"message": f"Failed to create account: {str(e)}",
			"success": False
		}
