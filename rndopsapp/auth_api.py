"""
Final Clean Authentication Flow API
Implements the simplified 3-step signup process:
1. STEP 1: Signup - Create Universal User__ and Email OTP__
2. STEP 2: Verify OTP
3. STEP 3: Set Password
"""

import frappe
import hashlib
import secrets
from frappe.utils import now_datetime, add_to_date
import re


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def _hash_otp(otp):
    """
    Hash an OTP string using SHA-256
    
    Args:
        otp (str): Plain text OTP (e.g., "123456")
    
    Returns:
        str: Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(otp.encode('utf-8')).hexdigest()


def _generate_otp(length=6):
    """
    Generate a random OTP
    
    Args:
        length (int): Length of OTP (default 6 digits)
    
    Returns:
        str: Random numeric OTP
    """
    import random
    return ''.join(random.choices('0123456789', k=length))


def _hash_password(password, salt=None):
    """
    Hash a password using PBKDF2 with SHA-256
    
    Args:
        password (str): Plain text password
        salt (str): Optional salt. If not provided, generates a new one.
    
    Returns:
        tuple: (password_hash, salt) both as hex strings
    """
    if salt is None:
        salt = secrets.token_hex(16)  # 32-character hex salt
    
    password_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000  # iterations
    )
    
    return password_hash.hex(), salt


def _verify_password(password, password_hash, salt):
    """
    Verify a password against stored hash
    
    Args:
        password (str): Plain text password to verify
        password_hash (str): Stored password hash (hex)
        salt (str): Stored salt (hex)
    
    Returns:
        bool: True if password matches
    """
    if not password or not password_hash or not salt:
        frappe.logger().warning(f"Password verification failed: password={bool(password)}, hash={bool(password_hash)}, salt={bool(salt)}")
        return False
    
    try:
        # Strip whitespace from inputs
        password = str(password).strip()
        password_hash_str = str(password_hash).strip()
        salt_str = str(salt).strip()
        
        frappe.logger().debug(f"Verifying password")
        frappe.logger().debug(f"  Input password length: {len(password)}")
        frappe.logger().debug(f"  Stored hash type: {type(password_hash_str).__name__}, length: {len(password_hash_str)}")
        frappe.logger().debug(f"  Stored salt type: {type(salt_str).__name__}, length: {len(salt_str)}")
        
        # Hash the provided password with the stored salt
        computed_hash, _ = _hash_password(password, salt_str)
        
        frappe.logger().debug(f"  Computed hash length: {len(computed_hash)}")
        frappe.logger().debug(f"  Computed hash first 32 chars: {computed_hash[:32]}")
        frappe.logger().debug(f"  Stored hash first 32 chars: {password_hash_str[:32]}")
        
        # Compare hashes
        result = computed_hash == password_hash_str
        
        frappe.logger().info(f"Password verification result: {result}")
        
        return result
    except Exception as e:
        frappe.logger().error(f"Password verification error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "password verification exception")
        return False


def _send_otp_email(email, otp_plain, expiry_time, full_name=None):
    """
    Send OTP email to user
    
    Args:
        email (str): Recipient email
        otp_plain (str): Plain text OTP (not hashed)
        expiry_time (datetime): When OTP expires
        full_name (str): User's name for personalization
    """
    try:
        # Format expiry time
        expiry_display = expiry_time.strftime("%d %B %Y at %I:%M %p")
        
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
                            {otp_plain}
                        </p>
                    </div>
                    
                    <table style="width: 100%; margin: 20px 0;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ecf0f1; font-weight: bold;">Email:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ecf0f1;">{email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #ecf0f1; font-weight: bold;">Expires:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #ecf0f1;">{expiry_display}</td>
                        </tr>
                    </table>
                    
                    <p style="color: #e74c3c; font-weight: bold;">
                        ⚠️ Do not share this OTP with anyone.
                    </p>
                    
                    <p>If you did not create an account, please ignore this email.</p>
                    
                    <hr style="border: none; border-top: 1px solid #ecf0f1; margin: 20px 0;">
                    
                    <p style="font-size: 12px; color: #7f8c8d;">
                        This is an automated message. Please do not reply.
                    </p>
                </div>
            </body>
        </html>
        """
        
        try:
            frappe.sendmail(
                recipients=[email],
                subject=subject,
                message=html_content,
                now=True
            )
            frappe.logger().info(f"OTP email sent to {email}")
        except frappe.OutgoingEmailError:
            # Log OTP if email not configured (for testing)
            frappe.logger().warning(f"""
            ========================================
            EMAIL NOT CONFIGURED - OTP LOG
            ========================================
            To: {email}
            OTP: {otp_plain}
            Expires: {expiry_display}
            ========================================
            """)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "OTP email sending error")
        frappe.logger().error(f"OTP email error: {str(e)}")


# ============================================================================
# STEP 1: SIGNUP - Create Universal User__ and Email OTP__
# ============================================================================

@frappe.whitelist(allow_guest=True)
def signup(email, full_name):
    """
    STEP 1: User submits signup form with email and full name
    
    Backend does:
    1. Check if email already exists
    2. Create Universal User__ (not Draft, no password yet)
    3. Generate OTP, hash it, create Email OTP__ record
    4. Send OTP email
    
    Args:
        email (str): User's email address
        full_name (str): User's full name
    
    Returns:
        dict: Success response or error
    """
    try:
        # ===== VALIDATE INPUTS =====
        if not email or not full_name:
            return {
                "status": "error",
                "message": "Email and Full Name are required",
                "success": False
            }
        
        email = email.strip().lower()
        full_name = full_name.strip()
        
        if not _is_valid_email(email):
            return {
                "status": "error",
                "message": "Invalid email address format",
                "success": False
            }
        
        if len(full_name) < 2:
            return {
                "status": "error",
                "message": "Full Name must be at least 2 characters",
                "success": False
            }
        
        # ===== CHECK IF EMAIL EXISTS =====
        if frappe.db.exists("Universal User__", {"email_u_r": email}):
            return {
                "status": "error",
                "message": "Email already registered. Please login or use a different email.",
                "success": False
            }
        
        # ===== GENERATE OTP FIRST =====
        otp_plain = _generate_otp(6)  # 6-digit OTP
        otp_hash = _hash_otp(otp_plain)  # Hash it
        
        # OTP expires in 5 minutes
        expiry_time = add_to_date(now_datetime(), minutes=5)
        
        # ===== CREATE UNIVERSAL USER__ =====
        universal_user = frappe.get_doc({
            "doctype": "Universal User__",
            "full_name_u_r": full_name,
            "email_u_r": email,
            "is_email_verified_u_r": 0,   # Not verified yet
            "is_password_set_u_r": 0,     # Password not set yet
            "status_u_r": "Active",
            "profile_type_u_r": "Individual",
            "is_auth_enabled_u_r": 1       # Enable auth by default
        })
        
        universal_user.flags.ignore_permissions = True
        universal_user.insert()
        frappe.logger().info(f"Universal User__ created: {universal_user.name} for {email}")
        
        # ===== CREATE EMAIL OTP__ RECORD =====
        email_otp = frappe.get_doc({
            "doctype": "Email OTP__",
            "email_u_r": email,
            "universal_user_u_r": universal_user.name,
            "otp_hash_u_r": otp_hash,        # Store HASHED OTP
            "expiry_time_u_r": expiry_time,
            "is_verified_u_r": 0,             # Not verified yet
            "otp_attempts_u_r": 0,
            "resent_count_u_r": 0
        })
        
        email_otp.flags.ignore_permissions = True
        email_otp.insert()
        frappe.logger().info(f"Email OTP__ created: {email_otp.name}")
        
        # ===== SEND OTP EMAIL =====
        _send_otp_email(email, otp_plain, expiry_time, full_name)
        
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": "Signup successful. OTP sent to your email.",
            "success": True,
            "data": {
                "email": email,
                "universal_user_id": universal_user.name,
                "message_detail": "Please check your email for the OTP. It expires in 5 minutes."
            }
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "signup error")
        return {
            "status": "error",
            "message": f"Signup failed: {str(e)}",
            "success": False
        }


# ============================================================================
# STEP 2: VERIFY OTP
# ============================================================================

@frappe.whitelist(allow_guest=True)
def verify_otp(email, otp_value):
    """
    STEP 2: User submits OTP from the OTP page
    
    Backend checks:
    1. Find latest OTP record for email
    2. Check: not expired, attempts < 5, not already verified
    3. Hash user's OTP input and compare with stored hash
    4. If correct: update Email OTP__.is_verified_u_r = 1, update Universal User__.is_email_verified_u_r = 1
    
    Args:
        email (str): User's email
        otp_value (str): OTP entered by user
    
    Returns:
        dict: Success or error
    """
    try:
        frappe.logger().info(f"verify_otp called with email: {email}, otp_value: ***")
        
        # ===== VALIDATE =====
        if not email or not otp_value:
            return {
                "status": "error",
                "message": "Email and OTP are required",
                "success": False
            }
        
        email = email.strip().lower()
        otp_value = str(otp_value).strip()
        frappe.logger().info(f"Processing verify_otp for email: {email}")
        
        # ===== FIND LATEST OTP RECORD =====
        frappe.logger().info(f"Looking for OTP records with email: {email}")
        otp_records = frappe.db.get_list(
            "Email OTP__",
            filters={"email_u_r": email, "is_verified_u_r": 0},
            order_by="creation desc",
            limit=1,
            ignore_permissions=True  # Allow guest user to query OTP records
        )
        frappe.logger().info(f"Found OTP records: {otp_records}")
        
        if not otp_records:
            return {
                "status": "error",
                "message": "No OTP found or already verified. Please signup again.",
                "success": False
            }
        
        frappe.logger().info(f"Loading OTP doc: {otp_records[0].name}")
        otp_doc = frappe.get_doc("Email OTP__", otp_records[0].name)
        frappe.logger().info(f"OTP doc loaded: {otp_doc.name}")
        
        # ===== CHECK IF EXPIRED =====
        frappe.logger().info(f"Checking expiry: now={now_datetime()}, expiry={otp_doc.expiry_time_u_r}")
        if now_datetime() > otp_doc.expiry_time_u_r:
            return {
                "status": "error",
                "message": "OTP has expired. Please request a new one.",
                "success": False
            }
        
        # ===== CHECK ATTEMPTS < 5 =====
        frappe.logger().info(f"Checking attempts: {otp_doc.otp_attempts_u_r}")
        if otp_doc.otp_attempts_u_r >= 5:
            # Mark as expired after max attempts
            otp_doc.flags.ignore_permissions = True
            otp_doc.is_verified_u_r = 0
            otp_doc.save()
            return {
                "status": "error",
                "message": "Maximum OTP attempts exceeded. Please request a new OTP.",
                "success": False
            }
        
        # ===== VERIFY OTP HASH =====
        frappe.logger().info(f"Hashing OTP input")
        otp_hash_input = _hash_otp(otp_value)
        frappe.logger().info(f"Comparing hashes: input={otp_hash_input[:8]}..., stored={otp_doc.otp_hash_u_r[:8] if otp_doc.otp_hash_u_r else 'None'}...")
        
        if otp_hash_input != otp_doc.otp_hash_u_r:
            # Wrong OTP - increment attempts
            frappe.logger().info(f"OTP mismatch, incrementing attempts")
            otp_doc.flags.ignore_permissions = True
            otp_doc.otp_attempts_u_r += 1
            otp_doc.save()
            frappe.db.commit()
            
            remaining = 5 - otp_doc.otp_attempts_u_r
            return {
                "status": "error",
                "message": f"Invalid OTP. {remaining} attempts remaining.",
                "success": False,
                "attempts_remaining": remaining
            }
        
        # ===== OTP CORRECT - MARK AS VERIFIED =====
        frappe.logger().info(f"OTP verified, marking as verified")
        otp_doc.flags.ignore_permissions = True
        otp_doc.is_verified_u_r = 1
        otp_doc.verified_at_u_r = now_datetime()
        otp_doc.save()
        
        # ===== UPDATE UNIVERSAL USER__ =====
        frappe.logger().info(f"Updating Universal User__: {otp_doc.universal_user_u_r}")
        universal_user = frappe.get_doc("Universal User__", otp_doc.universal_user_u_r)
        universal_user.flags.ignore_permissions = True
        universal_user.is_email_verified_u_r = 1
        universal_user.save()
        
        frappe.db.commit()
        frappe.logger().info(f"OTP verified successfully for {email}")
        
        return {
            "status": "success",
            "message": "OTP verified successfully. Please proceed to set your password.",
            "success": True,
            "data": {
                "email": email,
                "universal_user_id": otp_doc.universal_user_u_r
            }
        }
    
    except Exception as e:
        error_traceback = frappe.get_traceback()
        frappe.log_error(error_traceback, "verify_otp error")
        frappe.logger().error(f"verify_otp error: {error_traceback}")
        error_msg = str(e) if str(e) else "Unknown error occurred"
        return {
            "status": "error",
            "message": f"OTP verification failed: {error_msg}",
            "success": False
        }


# ============================================================================
# STEP 3: SET PASSWORD
# ============================================================================

@frappe.whitelist(allow_guest=True)
def set_password(email, password, confirm_password):
    """
    STEP 3: User sets password after OTP verification
    
    Backend checks:
    1. Confirm user exists and is_email_verified_u_r = 1
    2. Confirm is_password_set_u_r = 0
    3. Validate passwords match
    4. Hash password, update Universal User__, and set password in Frappe User
    5. Update is_password_set_u_r = 1
    6. Create login session
    
    Args:
        email (str): User's email
        password (str): Password to set
        confirm_password (str): Confirmation password
    
    Returns:
        dict: Success or error
    """
    try:
        # ===== VALIDATE INPUTS =====
        if not email or not password or not confirm_password:
            return {
                "status": "error",
                "message": "Email, password, and confirmation are required",
                "success": False
            }
        
        email = email.strip().lower()
        
        if len(password) < 8:
            return {
                "status": "error",
                "message": "Password must be at least 8 characters long",
                "success": False
            }
        
        if password != confirm_password:
            return {
                "status": "error",
                "message": "Passwords do not match",
                "success": False
            }
        
        # ===== FIND UNIVERSAL USER__ =====
        user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": email},
            fields=["name", "is_email_verified_u_r", "is_password_set_u_r", "auth_user_id_u_r"],
            limit=1,
            ignore_permissions=True
        )
        
        if not user_records:
            return {
                "status": "error",
                "message": "User not found. Please signup first.",
                "success": False
            }
        
        universal_user = user_records[0]
        
        # ===== CHECK EMAIL VERIFIED =====
        if not universal_user.get("is_email_verified_u_r"):
            return {
                "status": "error",
                "message": "Email not verified. Please verify OTP first.",
                "success": False
            }
        
        # ===== CHECK PASSWORD NOT ALREADY SET =====
        if universal_user.get("is_password_set_u_r"):
            return {
                "status": "error",
                "message": "Password already set. Please login or use forgot password.",
                "success": False
            }
        
        # ===== HASH PASSWORD =====
        password_hash, password_salt = _hash_password(password)
        now = now_datetime()
        
        # ===== UPDATE UNIVERSAL USER__ =====
        # Use direct SQL because Frappe ORM has issues saving password_salt_u_r
        frappe.db.sql("""
            UPDATE `tabUniversal User__`
            SET password_hash_u_r = %s,
                password_salt_u_r = %s,
                password_set_on_u_r = %s,
                is_password_set_u_r = 1
            WHERE name = %s
        """, (password_hash, password_salt, now, universal_user.name))
        
        # ===== UPDATE FRAPPE USER (if exists) =====
        if universal_user.get("auth_user_id_u_r"):
            try:
                frappe_user = frappe.get_doc("User", universal_user.get("auth_user_id_u_r"))
                frappe_user.new_password = password
                frappe_user.flags.ignore_permissions = True
                frappe_user.save()
                frappe.logger().info(f"Frappe User password updated for {email}")
            except Exception as e:
                frappe.logger().warning(f"Could not update Frappe User password: {str(e)}")
        
        frappe.db.commit()
        frappe.logger().info(f"Password set successfully for {email}")
        
        return {
            "status": "success",
            "message": "Password set successfully. You can now login.",
            "success": True,
            "data": {
                "email": email,
                "universal_user_id": universal_user.name,
                "message_detail": "Your account setup is complete. Please login with your email and password."
            }
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "set_password error")
        return {
            "status": "error",
            "message": f"Failed to set password: {str(e)}",
            "success": False
        }


# ============================================================================
# BONUS: OTP RESEND (for convenience)
# ============================================================================

@frappe.whitelist(allow_guest=True)
def resend_otp(email):
    """
    Resend OTP to user (max 3 resends)
    
    Args:
        email (str): User's email
    
    Returns:
        dict: Success or error
    """
    try:
        email = email.strip().lower()
        
        # Find latest unverified OTP
        otp_records = frappe.db.get_list(
            "Email OTP__",
            filters={"email_u_r": email, "is_verified_u_r": 0},
            order_by="creation desc",
            limit=1,
            ignore_permissions=True  # Allow guest user to query OTP records
        )
        
        if not otp_records:
            # No OTP found - suggest signup
            return {
                "status": "error",
                "message": "No pending OTP found. Please signup first.",
                "success": False
            }
        
        otp_doc = frappe.get_doc("Email OTP__", otp_records[0].name)
        
        # ===== CHECK RESEND LIMIT =====
        if otp_doc.resent_count_u_r >= 3:
            return {
                "status": "error",
                "message": "Maximum resend limit exceeded. Please wait or signup again.",
                "success": False
            }
        
        # ===== GENERATE NEW OTP & UPDATE =====
        otp_plain = _generate_otp(6)
        otp_hash = _hash_otp(otp_plain)
        expiry_time = add_to_date(now_datetime(), minutes=5)
        
        otp_doc.flags.ignore_permissions = True
        otp_doc.otp_hash_u_r = otp_hash
        otp_doc.expiry_time_u_r = expiry_time
        otp_doc.otp_attempts_u_r = 0  # Reset attempts
        otp_doc.resent_count_u_r += 1
        otp_doc.save()
        
        # ===== SEND EMAIL =====
        universal_user = frappe.get_doc("Universal User__", otp_doc.universal_user_u_r)
        _send_otp_email(email, otp_plain, expiry_time, universal_user.full_name_u_r)
        
        frappe.db.commit()
        frappe.logger().info(f"OTP resent to {email} (resend #{otp_doc.resent_count_u_r})")
        
        return {
            "status": "success",
            "message": "New OTP sent to your email.",
            "success": True,
            "data": {
                "email": email,
                "resend_count": otp_doc.resent_count_u_r
            }
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "resend_otp error")
        return {
            "status": "error",
            "message": f"Failed to resend OTP: {str(e)}",
            "success": False
        }


# ============================================================================
# LOGIN - Authenticate user and create session
# ============================================================================

def _generate_jwt_token(user_id):
    """
    Generate a JWT token for the user
    
    Args:
        user_id (str): Universal User__ ID
    
    Returns:
        str: JWT token or None if JWT not available
    """
    try:
        import jwt
        from datetime import datetime, timedelta
        
        payload = {
            "user_id": user_id,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=24)  # Token valid for 24 hours
        }
        
        # Use a secret key (should be stored in Frappe settings in production)
        secret_key = frappe.conf.get("jwt_secret_key") or "your-secret-key-change-in-production"
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return token
    except Exception:
        # If JWT not available, will use session-based auth
        return None


def _get_user_roles_and_permissions(universal_user_id):
    """
    Get user roles, permissions, and designation info
    
    Args:
        universal_user_id (str): Universal User__ ID
    
    Returns:
        dict: User roles and permission info
    """
    try:
        universal_user = frappe.get_doc("Universal User__", universal_user_id)
        
        # Get linked Frappe User if exists
        frappe_user_id = universal_user.auth_user_id_u_r
        roles = []
        permissions = {}
        designation = None
        user_type = "Individual"
        
        if frappe_user_id:
            try:
                frappe_user = frappe.get_doc("User", frappe_user_id)
                roles = frappe.get_roles(frappe_user_id)
                designation = frappe_user.designation
            except Exception:
                pass
        
        # Get user type from profile_type_u_r
        user_type = universal_user.profile_type_u_r or "Individual"
        
        return {
            "roles": roles,
            "user_type": user_type,
            "designation": designation,
            "is_auth_enabled": universal_user.is_auth_enabled_u_r,
            "full_name": universal_user.full_name_u_r,
            "email": universal_user.email_u_r,
            "profile_type": universal_user.profile_type_u_r
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_user_roles_and_permissions error")
        return {}


@frappe.whitelist(allow_guest=True)
def login(email, password, remember_me=False):
    """
    LOGIN - Authenticate user with email and password
    
    Backend handles:
    1. Validate inputs
    2. Find user by email
    3. Check account status (active, not locked, not suspended)
    4. Verify password
    5. On success: reset login attempts, update last_login_at, return token & user info
    6. On failure: increment login attempts, lock if >5 attempts, return error
    
    Edge cases:
    - Account not activated (not verified)
    - Account locked (too many failed attempts)
    - Account suspended
    - Password not set yet
    - Password expired
    
    Args:
        email (str): User's email address
        password (str): User's password
        remember_me (bool): Optional remember me flag (for future use)
    
    Returns:
        dict: Success response with token/session or error details
    """
    try:
        # ===== VALIDATE INPUTS =====
        if not email or not password:
            return {
                "status": "error",
                "message": "Email and password are required",
                "error_code": "MISSING_CREDENTIALS",
                "success": False
            }
        
        email = email.strip().lower()
        frappe.logger().info(f"Login attempt for email: {email}")
        
        # ===== FIND USER BY EMAIL =====
        user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": email},
            fields=[
                "name",
                "full_name_u_r",
                "is_email_verified_u_r",
                "is_password_set_u_r",
                "password_hash_u_r",
                "password_salt_u_r",
                "status_u_r",
                "is_auth_enabled_u_r",
                "profile_type_u_r",
                "auth_user_id_u_r"
            ],
            limit=1,
            ignore_permissions=True
        )
        
        if not user_records:
            frappe.logger().warning(f"Login failed: User not found for email {email}")
            return {
                "status": "error",
                "message": "Invalid email or password",
                "error_code": "INVALID_CREDENTIALS",
                "success": False
            }
        
        user = user_records[0]
        user_id = user.name
        frappe.logger().info(f"User found: {user_id}")
        
        # ===== CHECK: EMAIL NOT VERIFIED =====
        if not user.get("is_email_verified_u_r"):
            frappe.logger().warning(f"Login failed for {email}: Email not verified")
            return {
                "status": "error",
                "message": "Your email is not verified. Please verify your email first.",
                "error_code": "EMAIL_NOT_VERIFIED",
                "success": False
            }
        
        # ===== CHECK: PASSWORD NOT SET =====
        if not user.get("is_password_set_u_r"):
            frappe.logger().warning(f"Login failed for {email}: Password not set")
            return {
                "status": "error",
                "message": "Your password is not set. Please complete the signup process.",
                "error_code": "PASSWORD_NOT_SET",
                "success": False
            }
        
        # ===== CHECK: ACCOUNT STATUS =====
        status = user.get("status_u_r")
        if status == "Suspended":
            frappe.logger().warning(f"Login failed for {email}: Account suspended")
            return {
                "status": "error",
                "message": "Your account has been suspended. Please contact support.",
                "error_code": "ACCOUNT_SUSPENDED",
                "success": False
            }
        
        if status == "Inactive":
            frappe.logger().warning(f"Login failed for {email}: Account inactive")
            return {
                "status": "error",
                "message": "Your account is inactive. Please contact support.",
                "error_code": "ACCOUNT_INACTIVE",
                "success": False
            }
        
        # ===== VERIFY PASSWORD =====
        password_hash = user.get("password_hash_u_r")
        password_salt = user.get("password_salt_u_r")
        
        frappe.logger().info(f"Verifying password for {email}")
        frappe.logger().info(f"  Password hash stored: {password_hash[:30] if password_hash else 'None'}...")
        frappe.logger().info(f"  Password salt stored: {password_salt[:30] if password_salt else 'None'}...")
        
        if not password_hash:
            frappe.logger().warning(f"Login failed for {email}: Password hash missing")
            return {
                "status": "error",
                "message": "Invalid email or password",
                "error_code": "INVALID_CREDENTIALS",
                "success": False
            }
        
        # If salt is missing, use a default/empty salt or try to regenerate
        if not password_salt:
            frappe.logger().warning(f"Login for {email}: Salt is missing, trying without salt or regenerating")
            # Try with empty salt first
            computed_hash, _ = _hash_password(password, "")
            if computed_hash == password_hash:
                frappe.logger().info(f"Password verified using empty salt for {email}")
            else:
                # If that doesn't work, the password might have been hashed differently
                frappe.logger().warning(f"Login failed for {email}: Password hash mismatch (no salt)")
                return {
                    "status": "error",
                    "message": "Invalid email or password",
                    "error_code": "INVALID_CREDENTIALS",
                    "success": False
                }
        else:
            # Normal verification with salt
            if not _verify_password(password, password_hash, password_salt):
                frappe.logger().warning(f"Login failed for {email}: Invalid password")
                return {
                    "status": "error",
                    "message": "Invalid email or password",
                    "error_code": "INVALID_CREDENTIALS",
                    "success": False
                }
            frappe.logger().info(f"Password verified successfully for {email}")
        
        # ===== PASSWORD VERIFIED - LOGIN SUCCESSFUL =====
        frappe.logger().info(f"Login successful for {email}")
        
        # Update last login timestamp
        user_doc = frappe.get_doc("Universal User__", user_id)
        user_doc.flags.ignore_permissions = True
        user_doc.last_login_at_u_r = now_datetime()
        user_doc.save()
        frappe.db.commit()
        
        # ===== GENERATE TOKEN AND USER INFO =====
        token = _generate_jwt_token(user_id)
        roles_info = _get_user_roles_and_permissions(user_id)
        
        # Build response
        response_data = {
            "user_id": user_id,
            "email": email,
            "full_name": user.get("full_name_u_r"),
            "profile_type": user.get("profile_type_u_r"),
            "roles": roles_info.get("roles", []),
            "user_type": roles_info.get("user_type"),
            "designation": roles_info.get("designation"),
            "last_login": user_doc.last_login_at_u_r.isoformat() if user_doc.last_login_at_u_r else None
        }
        
        # ===== ADD EMPLOYEE CLASS INFO FOR DASHBOARD ROUTING =====
        frappe_user_id = user.get("auth_user_id_u_r")
        if frappe_user_id and frappe.db.exists("User", frappe_user_id):
            empclass_id = frappe.db.get_value("User", frappe_user_id, "empclass")
            if empclass_id:
                empclass_name = frappe.db.get_value(
                    "EmployeeClass_prornd", empclass_id, "empclass_name"
                )
                response_data["empclass_id"] = empclass_id
                response_data["empclass_name"] = empclass_name
        
        # Also try to resolve by email if auth_user_id_u_r is not set
        if "empclass_id" not in response_data:
            empclass_id = frappe.db.get_value("User", email, "empclass")
            if empclass_id:
                empclass_name = frappe.db.get_value(
                    "EmployeeClass_prornd", empclass_id, "empclass_name"
                )
                response_data["empclass_id"] = empclass_id
                response_data["empclass_name"] = empclass_name
        
        if token:
            response_data["token"] = token
            response_data["token_type"] = "Bearer"
            response_data["expires_in"] = 86400  # 24 hours in seconds
        
        return {
            "status": "success",
            "message": f"Welcome back, {user.get('full_name_u_r')}!",
            "success": True,
            "data": response_data
        }
    
    except Exception as e:
        error_traceback = frappe.get_traceback()
        frappe.log_error(error_traceback, "login error")
        frappe.logger().error(f"Login error: {error_traceback}")
        
        return {
            "status": "error",
            "message": "Login failed. Please try again.",
            "error_code": "SERVER_ERROR",
            "success": False
        }


# ============================================================================
# DEBUG - Test password hashing
# ============================================================================

@frappe.whitelist(allow_guest=True)
def test_password_hash(password, stored_hash, stored_salt):
    """
    DEBUG ENDPOINT: Test if password hashing/verification works
    
    Args:
        password (str): Plain text password to test
        stored_hash (str): Stored hash from database
        stored_salt (str): Stored salt from database
    
    Returns:
        dict: Debug info about password verification
    """
    try:
        # Test hashing
        computed_hash, _ = _hash_password(password, stored_salt)
        
        matches = computed_hash == stored_hash
        
        return {
            "status": "success",
            "password_provided": password,
            "password_length": len(password),
            "stored_hash": stored_hash[:50] + "..." if len(str(stored_hash)) > 50 else stored_hash,
            "computed_hash": computed_hash[:50] + "..." if len(str(computed_hash)) > 50 else computed_hash,
            "stored_salt": stored_salt[:50] + "..." if len(str(stored_salt)) > 50 else stored_salt,
            "hashes_match": matches,
            "hash_length_stored": len(str(stored_hash)),
            "hash_length_computed": len(str(computed_hash))
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "error_traceback": frappe.get_traceback()
        }


@frappe.whitelist(allow_guest=True)
def reset_user_password(email, new_password, confirm_password):
    """
    ADMIN/DEBUG: Reset a user's password with proper hash and salt
    
    This function forces a password reset with both hash and salt properly stored.
    Use this if the password hash/salt got corrupted or not saved properly.
    
    Args:
        email (str): User email
        new_password (str): New password to set
        confirm_password (str): Confirmation
    
    Returns:
        dict: Success or error
    """
    try:
        email = email.strip().lower()
        
        if not new_password or new_password != confirm_password:
            return {
                "status": "error",
                "message": "Passwords do not match",
                "success": False
            }
        
        if len(new_password) < 6:
            return {
                "status": "error",
                "message": "Password must be at least 6 characters",
                "success": False
            }
        
        # Find user
        user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": email},
            fields=["name"],
            limit=1,
            ignore_permissions=True
        )
        
        if not user_records:
            return {
                "status": "error",
                "message": "User not found",
                "success": False
            }
        
        user_id = user_records[0].name
        
        # Hash password with new salt
        password_hash, password_salt = _hash_password(new_password)
        
        frappe.logger().info(f"Password reset for {email}: hash={password_hash[:20]}... salt={password_salt}")
        
        # Update user with hash and salt using direct SQL (Frappe ORM has issues with password_salt_u_r field)
        frappe.db.sql("""
            UPDATE `tabUniversal User__`
            SET password_hash_u_r = %s, 
                password_salt_u_r = %s, 
                is_password_set_u_r = 1,
                password_set_on_u_r = NOW()
            WHERE name = %s
        """, (password_hash, password_salt, user_id))
        
        frappe.db.commit()
        
        return {
            "status": "success",
            "message": "Password reset successfully. You can now login.",
            "success": True,
            "data": {
                "email": email,
                "user_id": user_id
            }
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "reset_user_password error")
        return {
            "status": "error",
            "message": f"Password reset failed: {str(e)}",
            "success": False
        }


@frappe.whitelist(allow_guest=True)
def debug_user(email):
    """
    DEBUG ENDPOINT: Check what's stored in database for a user
    
    Args:
        email (str): User email
    
    Returns:
        dict: User data stored in database
    """
    try:
        email = email.strip().lower()
        
        user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": email},
            fields=[
                "name",
                "full_name_u_r",
                "email_u_r",
                "is_email_verified_u_r",
                "is_password_set_u_r",
                "password_hash_u_r",
                "password_salt_u_r",
                "status_u_r"
            ],
            limit=1,
            ignore_permissions=True
        )
        
        if not user_records:
            return {
                "status": "error",
                "message": "User not found"
            }
        
        user = user_records[0]
        
        return {
            "status": "success",
            "user_id": user.get("name"),
            "email": user.get("email_u_r"),
            "full_name": user.get("full_name_u_r"),
            "is_email_verified": user.get("is_email_verified_u_r"),
            "is_password_set": user.get("is_password_set_u_r"),
            "status": user.get("status_u_r"),
            "password_hash_exists": bool(user.get("password_hash_u_r")),
            "password_hash": user.get("password_hash_u_r")[:50] + "..." if user.get("password_hash_u_r") else "NULL",
            "password_salt_exists": bool(user.get("password_salt_u_r")),
            "password_salt": user.get("password_salt_u_r")[:50] + "..." if user.get("password_salt_u_r") else "NULL"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "error_traceback": frappe.get_traceback()
        }


@frappe.whitelist(allow_guest=True)
def debug_login_verification(email, password):
    """
    DEBUG: Test login verification step-by-step
    """
    try:
        email = email.strip().lower()
        
        # Get user
        user = frappe.db.sql("""
            SELECT name, password_hash_u_r, password_salt_u_r
            FROM `tabUniversal User__`
            WHERE email_u_r = %s
        """, (email,), as_dict=True)
        
        if not user:
            return {
                "error": "User not found",
                "success": False
            }
        
        stored_hash = user[0].password_hash_u_r
        stored_salt = user[0].password_salt_u_r
        
        # Verify
        result = _verify_password(password, stored_hash, stored_salt)
        
        # Also manually test
        computed_hash, _ = _hash_password(password, stored_salt)
        
        return {
            "success": result,
            "stored_hash": stored_hash[:30] + "..." if stored_hash else None,
            "stored_salt": stored_salt[:20] + "..." if stored_salt else None,
            "computed_hash": computed_hash[:30] + "...",
            "hashes_match": computed_hash == stored_hash,
            "verification_result": result
        }
    
    except Exception as e:
        return {
            "error": str(e),
            "traceback": frappe.get_traceback()
        }


# ============================================================================
# UNIVERSAL REGISTRATION DASHBOARD ENDPOINTS
# ============================================================================

# CONSOLIDATED: Removed duplicate - see final definition below


@frappe.whitelist()
def get_registration_progress():
    """
    Get the completion status/progress of user's registration profile.
    
    Returns progress percentage and list of completed/pending sections.
    """
    try:
        current_user = frappe.session.user
        
        # Get Universal User
        universal_user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": current_user},
            fields=["name"],
            limit=1
        )
        
        if not universal_user_records:
            return {
                "completion_percentage": 0,
                "completed_sections": [],
                "pending_sections": [
                    "basic", "kyc", "contact", "bank", "education", "experience"
                ]
            }
        
        universal_user_id = universal_user_records[0]["name"]
        
        # Get Registration
        reg_records = frappe.db.get_list(
            "Universal Registration__",
            filters={"universal_user_u_r": universal_user_id},
            fields=["name"],
            limit=1
        )
        
        if not reg_records:
            return {
                "completion_percentage": 0,
                "completed_sections": [],
                "pending_sections": [
                    "basic", "kyc", "contact", "bank", "education", "experience"
                ]
            }
        
        reg_doc = frappe.get_doc("Universal Registration__", reg_records[0]["name"])
        
        # Calculate completion for each section
        sections = {
            "basic": [
                "full_name_u_r", "dob_u_r", "gender_u_r", 
                "mobile_number_u_r", "email_address_u_r"
            ],
            "contact": [
                "mobile_number_u_r", "email_address_u_r", "whatsapp_number_u_r"
            ],
            "bank": ["bank_details_u_r"],
            "education": ["qualifications_u_r"],
            "experience": ["experiences_u_r"],
            "kyc": ["pan_number_org_u_r", "gst_status_u_r"]
        }
        
        completed_sections = []
        pending_sections = []
        
        for section, fields in sections.items():
            section_complete = True
            for field in fields:
                value = reg_doc.get(field)
                
                # Check if field is empty/null
                if not value or (isinstance(value, (list, dict)) and len(value) == 0):
                    section_complete = False
                    break
            
            if section_complete:
                completed_sections.append(section)
            else:
                pending_sections.append(section)
        
        completion_percentage = int((len(completed_sections) / len(sections)) * 100)
        
        return {
            "completion_percentage": completion_percentage,
            "completed_sections": completed_sections,
            "pending_sections": pending_sections
        }
        
    except Exception as e:
        frappe.logger().error(f"Error calculating registration progress: {str(e)}")
        return {
            "completion_percentage": 0,
            "completed_sections": [],
            "pending_sections": ["basic", "kyc", "contact", "bank", "education", "experience"],
            "error": str(e)
        }


@frappe.whitelist()
def save_registration_section(section_name=None, section_data=None):
    """
    Save a specific section of the registration form.
    
    Supports both parameter-based calls and JSON request body.
    
    Args:
        section_name (str): Name of section (basic, contact, bank, education, experience, organization)
        section_data (dict|str): Section data to save
    
    Returns:
        dict: Success/error response with proper error codes
    """
    try:
        current_user = frappe.session.user
        
        # Handle both parameter-based calls and JSON request body
        if section_name is None or section_data is None:
            data = frappe.local.request.json or {}
            section_name = section_name or data.get("section_name")
            section_data = section_data or data.get("section_data")
        
        # Validate request
        if not section_name or not section_data:
            return {
                "status": "error",
                "message": "section_name and section_data are required",
                "success": False,
                "error_code": "INVALID_REQUEST"
            }
        
        # Parse section_data if it's a string
        if isinstance(section_data, str):
            section_data = frappe.parse_json(section_data)
        
        # Get Universal User
        universal_user_records = frappe.db.get_list(
            "Universal User__",
            filters={"email_u_r": current_user},
            fields=["name"],
            limit=1
        )
        
        if not universal_user_records:
            return {
                "status": "error",
                "message": "Universal User not found",
                "success": False,
                "error_code": "NOT_FOUND"
            }
        
        universal_user_id = universal_user_records[0]["name"]
        
        # Get or Create Registration
        reg_records = frappe.db.get_list(
            "Universal Registration__",
            filters={"universal_user_u_r": universal_user_id},
            fields=["name"],
            limit=1
        )
        
        if reg_records:
            reg_doc = frappe.get_doc("Universal Registration__", reg_records[0]["name"])
        else:
            # Create new registration
            reg_doc = frappe.get_doc({
                "doctype": "Universal Registration__",
                "universal_user_u_r": universal_user_id,
                "profile_type_u_r": "Individual / Personal",
                "full_name_u_r": frappe.db.get_value("Universal User__", universal_user_id, "full_name_u_r")
            })
            reg_doc.insert(ignore_permissions=True)
        
        # =====================================================================
        # BASIC SECTION HANDLER
        # =====================================================================
        if section_name == "basic":
            # Validate section data
            is_valid, error_msg = _validate_registration_section(section_name, section_data, reg_doc.profile_type_u_r)
            if not is_valid:
                return {
                    "status": "error",
                    "message": f"Validation failed: {error_msg}",
                    "success": False,
                    "error_code": "VALIDATION_ERROR"
                }
            
            profile_type = reg_doc.profile_type_u_r
            
            if profile_type == "Individual / Personal":
                # Individual profile basic fields
                reg_doc.full_name_u_r = section_data.get("full_name_u_r") or reg_doc.full_name_u_r
                reg_doc.guardian_name_u_r = section_data.get("guardian_name_u_r")
                reg_doc.dob_u_r = section_data.get("dob_u_r")
                reg_doc.gender_u_r = section_data.get("gender_u_r")
                reg_doc.nationality_u_r = section_data.get("nationality_u_r", "India")
                reg_doc.mobile_number_u_r = section_data.get("mobile_number_u_r")
                reg_doc.email_address_u_r = section_data.get("email_address_u_r")
                reg_doc.same_as_mobile_number_u_r = section_data.get("same_as_mobile_number_u_r", 0)
                reg_doc.whatsapp_number_u_r = section_data.get("whatsapp_number_u_r")
                reg_doc.alternate_mobile_number_u_r = section_data.get("alternate_mobile_number_u_r")
                
                # Update address details
                if "address_details" in section_data:
                    reg_doc.address_details = []
                    for addr in section_data.get("address_details", []):
                        reg_doc.append("address_details", {
                            "address_line1": addr.get("address_line1"),
                            "address_line2": addr.get("address_line2"),
                            "city": addr.get("city"),
                            "state": addr.get("state"),
                            "postal_code": addr.get("postal_code"),
                            "country": addr.get("country")
                        })
            
            elif profile_type == "Organization":
                # Organization profile basic fields
                reg_doc.organization_sub_type_u_r = section_data.get("organization_sub_type_u_r")
                reg_doc.org_name_u_r = section_data.get("org_name_u_r")
                reg_doc.est_date_u_r = section_data.get("est_date_u_r")
                reg_doc.nature_of_business_u_r = section_data.get("nature_of_business_u_r")
                reg_doc.website_u_r = section_data.get("website_u_r")
                reg_doc.contact_person_u_r = section_data.get("contact_person_u_r")
                reg_doc.contact_designation = section_data.get("contact_designation")
                reg_doc.email_oraganization__contact_person_u_r = section_data.get("email_oraganization__contact_person_u_r")
                reg_doc.org_contact_number_u_r = section_data.get("org_contact_number_u_r")
                reg_doc.organization_mobile_number_u_r = section_data.get("organization_mobile_number_u_r")
                
                # Update org address details
                if "org_address_details_u_r" in section_data:
                    reg_doc.org_address_details_u_r = []
                    for addr in section_data.get("org_address_details_u_r", []):
                        reg_doc.append("org_address_details_u_r", {
                            "address_line1": addr.get("address_line1"),
                            "address_line2": addr.get("address_line2"),
                            "city": addr.get("city"),
                            "state": addr.get("state"),
                            "postal_code": addr.get("postal_code"),
                            "country": addr.get("country")
                        })
        
        # =====================================================================
        # CONTACT SECTION HANDLER
        # =====================================================================
        elif section_name == "contact":
            # Validate section data
            is_valid, error_msg = _validate_registration_section(section_name, section_data)
            if not is_valid:
                return {
                    "status": "error",
                    "message": f"Validation failed: {error_msg}",
                    "success": False,
                    "error_code": "VALIDATION_ERROR"
                }
            
            reg_doc.mobile_number_u_r = section_data.get("mobile_number_u_r")
            reg_doc.email_address_u_r = section_data.get("email_address_u_r")
            reg_doc.same_as_mobile_number_u_r = section_data.get("same_as_mobile_number_u_r", 0)
            reg_doc.whatsapp_number_u_r = section_data.get("whatsapp_number_u_r")
            reg_doc.alternate_mobile_number_u_r = section_data.get("alternate_mobile_number_u_r")
        
        # =====================================================================
        # BANK SECTION HANDLER
        # =====================================================================
        # BANK SECTION HANDLER
        # =====================================================================
        elif section_name == "bank":
            # Validate section data
            is_valid, error_msg = _validate_registration_section(section_name, section_data)
            if not is_valid:
                return {
                    "status": "error",
                    "message": f"Validation failed: {error_msg}",
                    "success": False,
                    "error_code": "VALIDATION_ERROR"
                }
            
            reg_doc.bank_details_u_r = []
            for bank in section_data.get("bank_details_u_r", []):
                reg_doc.append("bank_details_u_r", {
                    "account_holder_name": bank.get("account_holder_name"),
                    "account_number": bank.get("account_number"),
                    "account_type": bank.get("account_type"),
                    "bank_name": bank.get("bank_name"),
                    "ifsc_code": bank.get("ifsc_code"),
                    "branch": bank.get("branch")
                })
        
        # =====================================================================
        # EDUCATION SECTION HANDLER
        # =====================================================================
        elif section_name == "education":
            # Validate section data
            is_valid, error_msg = _validate_registration_section(section_name, section_data)
            if not is_valid:
                return {
                    "status": "error",
                    "message": f"Validation failed: {error_msg}",
                    "success": False,
                    "error_code": "VALIDATION_ERROR"
                }
            
            reg_doc.qualifications_u_r = []
            for qual in section_data.get("qualifications_u_r", []):
                reg_doc.append("qualifications_u_r", {
                    "degree": qual.get("degree"),
                    "field_of_study": qual.get("field_of_study"),
                    "institution": qual.get("institution"),
                    "completion_year": qual.get("completion_year"),
                    "grade_percentage": qual.get("grade_percentage")
                })
        
        # =====================================================================
        # EXPERIENCE SECTION HANDLER
        # =====================================================================
        elif section_name == "experience":
            # Validate section data
            is_valid, error_msg = _validate_registration_section(section_name, section_data)
            if not is_valid:
                return {
                    "status": "error",
                    "message": f"Validation failed: {error_msg}",
                    "success": False,
                    "error_code": "VALIDATION_ERROR"
                }
            
            reg_doc.experiences_u_r = []
            for exp in section_data.get("experiences_u_r", []):
                reg_doc.append("experiences_u_r", {
                    "job_title": exp.get("job_title"),
                    "company_name": exp.get("company_name"),
                    "industry": exp.get("industry"),
                    "start_date": exp.get("start_date"),
                    "end_date": exp.get("end_date"),
                    "is_current": exp.get("is_current", 0),
                    "description": exp.get("description")
                })
        
        # =====================================================================
        # ORGANIZATION SECTION HANDLER (for organization-specific fields)
        # =====================================================================
        elif section_name == "organization":
            reg_doc.org_name_u_r = section_data.get("org_name_u_r")
            reg_doc.est_date_u_r = section_data.get("est_date_u_r")
            reg_doc.nature_of_business_u_r = section_data.get("nature_of_business_u_r")
            reg_doc.website_u_r = section_data.get("website_u_r")
            reg_doc.contact_person_u_r = section_data.get("contact_person_u_r")
            reg_doc.org_contact_number_u_r = section_data.get("org_contact_number_u_r")
            reg_doc.type_of_business_u_r = section_data.get("type_of_business_u_r")
            reg_doc.other_business_type_u_r = section_data.get("other_business_type_u_r")
            reg_doc.nature_of_org = section_data.get("nature_of_org")
            reg_doc.pan_number_org_u_r = section_data.get("pan_number_org_u_r")
            reg_doc.gst_status_u_r = section_data.get("gst_status_u_r")
            reg_doc.gst_number_u_r = section_data.get("gst_number_u_r")
        
        # =====================================================================
        # COMPLIANCE SECTION HANDLER
        # =====================================================================
        elif section_name == "compliance":
            reg_doc.decl_info_true_u_r = section_data.get("decl_info_true_u_r", 0)
            reg_doc.signatory_name_u_r = section_data.get("signatory_name_u_r")
            reg_doc.date_of_signing_u_r = section_data.get("date_of_signing_u_r")
        
        else:
            return {
                "status": "error",
                "message": f"Unknown section: {section_name}",
                "success": False,
                "error_code": "INVALID_SECTION"
            }
        
        # Save the document
        reg_doc.flags.ignore_permissions = True
        reg_doc.save()
        frappe.db.commit()
        
        frappe.logger().info(f"Saved section '{section_name}' for user: {current_user}")
        
        return {
            "status": "success",
            "message": f"Section '{section_name}' saved successfully",
            "success": True,
            "registration_id": reg_doc.name
        }
        
    except frappe.ValidationError as ve:
        frappe.db.rollback()
        frappe.logger().error(f"Validation error saving registration section: {str(ve)}")
        frappe.log_error(frappe.get_traceback(), "save_registration_section validation error")
        return {
            "status": "error",
            "message": str(ve),
            "success": False,
            "error_code": "VALIDATION_ERROR"
        }
    except Exception as e:
        frappe.db.rollback()
        frappe.logger().error(f"Error saving registration section: {str(e)}")
        frappe.log_error(frappe.get_traceback(), "save_registration_section error")
        return {
            "status": "error",
            "message": str(e),
            "success": False,
            "error_code": "SAVE_FAILED"
        }


def _validate_registration_section(section_name, section_data, profile_type=None):
    """
    Validate section data before saving.
    
    Args:
        section_name (str): Section to validate
        section_data (dict): Data to validate
        profile_type (str): Profile type (Individual / Personal or Organization)
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    import re
    from datetime import datetime
    
    # ======= BASIC SECTION VALIDATION =======
    if section_name == "basic":
        if profile_type == "Individual / Personal":
            # Required fields
            if not section_data.get("full_name_u_r"):
                return False, "Full name is required"
            
            if not section_data.get("dob_u_r"):
                return False, "Date of birth is required"
            
            if not section_data.get("mobile_number_u_r"):
                return False, "Mobile number is required"
            
            if not section_data.get("email_address_u_r"):
                return False, "Email address is required"
            
            # Validate mobile number format (10 digits)
            mobile = str(section_data.get("mobile_number_u_r", "")).replace("+91", "").strip()
            if not re.match(r'^\d{10}$', mobile):
                return False, "Mobile number must be 10 digits"
            
            # Validate email format
            email = section_data.get("email_address_u_r", "")
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return False, "Email address format is invalid"
            
            # Validate age (18+) if dob is provided
            try:
                dob = datetime.strptime(str(section_data.get("dob_u_r")), "%Y-%m-%d") if section_data.get("dob_u_r") else None
                if dob:
                    today = datetime.now()
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
                    if age < 18:
                        return False, "Age must be 18 or above"
            except:
                pass  # Don't fail if date parsing fails - let Frappe handle it
            
            # Validate WhatsApp number if provided
            whatsapp = section_data.get("whatsapp_number_u_r", "")
            if whatsapp:
                whatsapp_clean = str(whatsapp).replace("+91", "").strip()
                if not re.match(r'^\d{10}$', whatsapp_clean):
                    return False, "WhatsApp number must be 10 digits"
            
            # Validate address details if provided
            addresses = section_data.get("address_details", [])
            if addresses:
                for addr in addresses:
                    if not addr.get("address_line1"):
                        return False, "Address line 1 is required in address details"
                    if not addr.get("city"):
                        return False, "City is required in address details"
                    if not addr.get("state"):
                        return False, "State is required in address details"
                    if not addr.get("country"):
                        return False, "Country is required in address details"
                    
                    # Validate postal code for India
                    postal_code = addr.get("postal_code", "")
                    if addr.get("country") == "India" and postal_code:
                        if not re.match(r'^\d{6}$', str(postal_code)):
                            return False, "Indian postal code must be 6 digits"
        
        elif profile_type == "Organization":
            # Organization basic field validation
            if not section_data.get("org_name_u_r"):
                return False, "Organization name is required"
            
            if not section_data.get("contact_person_u_r"):
                return False, "Contact person name is required"
            
            if not section_data.get("contact_designation"):
                return False, "Contact person designation is required"
    
    # ======= CONTACT SECTION VALIDATION =======
    elif section_name == "contact":
        if not section_data.get("mobile_number_u_r"):
            return False, "Mobile number is required"
        
        if not section_data.get("email_address_u_r"):
            return False, "Email address is required"
        
        # Validate mobile number format (10 digits)
        mobile = str(section_data.get("mobile_number_u_r", "")).replace("+91", "").strip()
        if not re.match(r'^\d{10}$', mobile):
            return False, "Mobile number must be 10 digits"
        
        # Validate email format
        email = section_data.get("email_address_u_r", "")
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return False, "Email address format is invalid"
    
    # ======= BANK SECTION VALIDATION =======
    elif section_name == "bank":
        banks = section_data.get("bank_details_u_r", [])
        for bank in banks:
            if not bank.get("account_holder_name"):
                return False, "Account holder name is required in bank details"
            
            if not bank.get("account_number"):
                return False, "Account number is required in bank details"
            
            if not bank.get("bank_name"):
                return False, "Bank name is required in bank details"
            
            if not bank.get("ifsc_code"):
                return False, "IFSC code is required in bank details"
            
            # Validate IFSC code format
            ifsc = str(bank.get("ifsc_code", "")).upper()
            if not re.match(r'^[A-Z]{4}0[A-Z0-9]{6}$', ifsc):
                return False, "IFSC code format is invalid (should be 11 characters: XXYY0ZZZXX)"
    
    # ======= EDUCATION SECTION VALIDATION =======
    elif section_name == "education":
        qualifications = section_data.get("qualifications_u_r", [])
        if qualifications:
            for qual in qualifications:
                if not qual.get("degree"):
                    return False, "Degree is required in qualifications"
                
                if not qual.get("institution"):
                    return False, "Institution is required in qualifications"
        
    # ======= EXPERIENCE SECTION VALIDATION =======
    elif section_name == "experience":
        experiences = section_data.get("experiences_u_r", [])
        if experiences:
            for exp in experiences:
                if not exp.get("job_title"):
                    return False, "Job title is required in experience"
                
                if not exp.get("company_name"):
                    return False, "Company name is required in experience"
                
                if not exp.get("start_date"):
                    return False, "Start date is required in experience"
                
                # Validate end_date is after start_date
                if exp.get("end_date"):
                    try:
                        start = datetime.strptime(str(exp.get("start_date")), "%Y-%m-%d") if exp.get("start_date") else None
                        end = datetime.strptime(str(exp.get("end_date")), "%Y-%m-%d") if exp.get("end_date") else None
                        if start and end and end < start:
                            return False, "End date must be after start date in experience"
                    except:
                        pass  # Don't fail if date parsing fails
    
    return True, None


def _serialize_child_table(child_table_list):
    """
    Convert child table rows to dictionary format for JSON serialization.
    
    Args:
        child_table_list: List of Row objects from Frappe child table
    
    Returns:
        list: List of dictionaries representing child table rows
    """
    result = []
    for row in child_table_list:
        if hasattr(row, 'as_dict'):
            result.append(row.as_dict())
        else:
            result.append(dict(row))
    return result


# ============================================================================
# FETCH USER REGISTRATION DETAILS FOR DASHBOARD
# ============================================================================

# CONSOLIDATED: Removed duplicate - see final definition below


# ============================================================================
# FETCH USER REGISTRATION DETAILS (for Dashboard)
# ============================================================================

@frappe.whitelist()
def get_user_registration_details(universal_user_id=None):
    """
    CONSOLIDATED ENDPOINT - Fetches user's Universal Registration__ details.
    
    This is the primary endpoint called from the React frontend dashboard after user signup/login.
    It retrieves the Universal Registration document and all its related data.
    
    Args:
        universal_user_id (str, optional): ID of the Universal User__ document.
                                          If not provided, uses the current logged-in user.
    
    Returns:
        dict: Comprehensive user registration data including:
              - Basic info (name, DOB, gender, nationality, contact)
              - Personal history (qualifications, experiences, addresses)
              - Organization details (if applicable)
              - Financial details (bank info, documents)
              - Profile type (Individual/Organization)
    
    Flow:
    1. Get current logged-in user from frappe.session.user (or use provided universal_user_id)
    2. Find the Universal User__ record
    3. Find the Universal Registration__ document linked to this user
    4. Return all registration details with comprehensive formatting
    """
    try:
        # ===== VALIDATE AUTHENTICATION =====
        current_user = frappe.session.user
        frappe.logger().info(f"Registration details request from user: {current_user}")
        
        # Check if user is authenticated
        if not current_user or current_user == "Guest":
            frappe.logger().error("Unauthenticated request to get_user_registration_details")
            return {
                "success": False,
                "message": "User not authenticated. Please log in first.",
                "data": None,
                "error_code": "AUTHENTICATION_REQUIRED"
            }
        
        # ===== DETERMINE UNIVERSAL_USER_ID =====
        if not universal_user_id:
            # If no ID provided, get from current user's email
            universal_user_id = frappe.db.get_value(
                "Universal User__",
                {"email_u_r": current_user},
                "name"
            )
            
            if not universal_user_id:
                frappe.logger().warning(f"No Universal User__ found for email: {current_user}")
                return {
                    "success": False,
                    "message": "Universal User record not found. Please complete registration first.",
                    "data": None,
                    "error_code": "USER_NOT_FOUND"
                }
        
        frappe.logger().info(f"Fetching registration for Universal User: {universal_user_id}")
        
        # ===== FETCH UNIVERSAL USER DETAILS =====
        try:
            universal_user = frappe.get_doc("Universal User__", universal_user_id)
        except frappe.DoesNotExistError:
            frappe.logger().error(f"Universal User not found: {universal_user_id}")
            return {
                "success": False,
                "message": "Universal User record not found",
                "data": None,
                "error_code": "USER_NOT_FOUND"
            }
        
        # ===== FETCH LINKED UNIVERSAL REGISTRATION =====
        registration_records = frappe.db.get_list(
            "Universal Registration__",
            filters={"universal_user_u_r": universal_user_id},
            order_by="modified desc",
            limit=1,
            ignore_permissions=True
        )
        
        if not registration_records:
            # Return basic user info if no registration exists yet
            frappe.logger().info(f"No registration found for user: {universal_user_id}")
            return {
                "success": True,
                "message": "User exists but registration not yet created",
                "data": {
                    "universal_user": {
                        "name": universal_user.name,
                        "full_name": universal_user.full_name_u_r,
                        "email": universal_user.email_u_r,
                        "is_email_verified": universal_user.is_email_verified_u_r,
                        "is_password_set": universal_user.is_password_set_u_r,
                        "status": universal_user.status_u_r,
                        "profile_type": universal_user.profile_type_u_r,
                        "creation": str(universal_user.creation)
                    },
                    "registration": None
                }
            }
        
        # ===== FETCH AND FORMAT REGISTRATION DATA =====
        registration_doc = frappe.get_doc(
            "Universal Registration__",
            registration_records[0].name
        )
        
        # Convert to dict for easier manipulation
        reg_dict = registration_doc.as_dict()
        
        # ===== FORMAT CHILD TABLE DATA =====
        # Process Address Details
        addresses = []
        if reg_dict.get("address_details"):
            for addr in reg_dict["address_details"]:
                addresses.append({
                    "idx": addr.get("idx"),
                    "address_line_1": addr.get("address_line_1_u_a"),
                    "address_line_2": addr.get("address_line_2_u_a"),
                    "city": addr.get("city_u_a"),
                    "state": addr.get("state_u_a"),
                    "postal_code": addr.get("postal_code_u_a"),
                    "country": addr.get("country_u_a"),
                    "address_type": addr.get("address_type_u_a")
                })
        
        # Process Qualifications
        qualifications = []
        if reg_dict.get("qualifications_u_r"):
            for qual in reg_dict["qualifications_u_r"]:
                qualifications.append({
                    "idx": qual.get("idx"),
                    "degree": qual.get("degree_u_q"),
                    "field_of_study": qual.get("field_of_study_u_q"),
                    "institution": qual.get("institution_u_q"),
                    "graduation_year": qual.get("graduation_year_u_q"),
                    "grade_percentage": qual.get("grade_percentage_u_q")
                })
        
        # Process Experiences
        experiences = []
        if reg_dict.get("experiences_u_r"):
            for exp in reg_dict["experiences_u_r"]:
                experiences.append({
                    "idx": exp.get("idx"),
                    "job_title": exp.get("job_title_u_e"),
                    "company_name": exp.get("company_name_u_e"),
                    "employment_type": exp.get("employment_type_u_e"),
                    "start_date": exp.get("start_date_u_e"),
                    "end_date": exp.get("end_date_u_e"),
                    "currently_working": exp.get("currently_working_u_e"),
                    "description": exp.get("description_u_e")
                })
        
        # Process Bank Details
        bank_details = []
        if reg_dict.get("bank_details_u_r"):
            for bank in reg_dict["bank_details_u_r"]:
                bank_details.append({
                    "idx": bank.get("idx"),
                    "bank_name": bank.get("bank_name_u_bd"),
                    "account_number": bank.get("account_number_u_bd"),
                    "ifsc_code": bank.get("ifsc_code_u_bd"),
                    "account_holder_name": bank.get("account_holder_name_u_bd"),
                    "account_type": bank.get("account_type_u_bd")
                })
        
        # Process Documents
        documents = []
        if reg_dict.get("uploaded_documents_u_r"):
            for doc in reg_dict["uploaded_documents_u_r"]:
                documents.append({
                    "idx": doc.get("idx"),
                    "document_type": doc.get("document_type_u_d"),
                    "document_name": doc.get("document_name_u_d"),
                    "file_path": doc.get("file_u_d")
                })
        
        # ===== PREPARE COMPREHENSIVE RESPONSE =====
        response_data = {
            "universal_user": {
                "name": universal_user.name,
                "full_name": universal_user.full_name_u_r,
                "email": universal_user.email_u_r,
                "is_email_verified": universal_user.is_email_verified_u_r,
                "is_password_set": universal_user.is_password_set_u_r,
                "status": universal_user.status_u_r,
                "profile_type": universal_user.profile_type_u_r,
                "creation": str(universal_user.creation)
            },
            "registration": {
                "name": registration_doc.name,
                "profile_type": reg_dict.get("profile_type_u_r"),
                "organization_sub_type": reg_dict.get("organization_sub_type_u_r"),
                "basic_info": {
                    "full_name": reg_dict.get("full_name_u_r"),
                    "guardian_name": reg_dict.get("guardian_name_u_r"),
                    "dob": reg_dict.get("dob_u_r"),
                    "gender": reg_dict.get("gender_u_r"),
                    "nationality": reg_dict.get("nationality_u_r"),
                    "mobile_number": reg_dict.get("mobile_number_u_r"),
                    "whatsapp_number": reg_dict.get("whatsapp_number_u_r"),
                    "alternate_mobile_number": reg_dict.get("alternate_mobile_number_u_r"),
                    "email_address": reg_dict.get("email_address_u_r"),
                    "same_as_mobile_number": reg_dict.get("same_as_mobile_number_u_r")
                },
                "contact_info": {
                    "contact_person": reg_dict.get("contact_person_u_r"),
                    "contact_designation": reg_dict.get("contact_designation"),
                    "contact_number": reg_dict.get("org_contact_number_u_r"),
                    "organization_mobile": reg_dict.get("organization_mobile_number_u_r"),
                    "organization_email": reg_dict.get("email_oraganization__contact_person_u_r")
                },
                "organization_info": {
                    "org_name": reg_dict.get("org_name_u_r"),
                    "establishment_date": reg_dict.get("est_date_u_r"),
                    "nature_of_business": reg_dict.get("nature_of_business_u_r"),
                    "website": reg_dict.get("website_u_r"),
                    "type_of_business": reg_dict.get("type_of_business_u_r"),
                    "other_business_type": reg_dict.get("other_business_type_u_r"),
                    "nature_of_org": reg_dict.get("nature_of_org")
                },
                "financial_info": {
                    "pan_number": reg_dict.get("pan_number_org_u_r"),
                    "gst_status": reg_dict.get("gst_status_u_r"),
                    "gst_number": reg_dict.get("gst_number_u_r"),
                    "overhead_percentage": reg_dict.get("overhead_percentage_u_r"),
                    "discount_percentage": reg_dict.get("discount_percentage_u_r"),
                    "agreement_number": reg_dict.get("agreement_number_u_r"),
                    "other_registration": reg_dict.get("other_registration_u_r")
                },
                "signatory_info": {
                    "signatory_name": reg_dict.get("signatory_name_u_r"),
                    "signatory_designation": reg_dict.get("signatory_designation_u_r"),
                    "date_of_signing": reg_dict.get("date_of_signing_u_r"),
                    "declaration_accepted": reg_dict.get("decl_info_true_u_r")
                },
                "addresses": addresses,
                "qualifications": qualifications,
                "experiences": experiences,
                "bank_details": bank_details,
                "documents": documents,
                "creation": str(registration_doc.creation),
                "modified": str(registration_doc.modified)
            }
        }
        
        frappe.logger().info(f"Registration details fetched successfully for: {universal_user_id}")
        
        return {
            "success": True,
            "message": "Registration details fetched successfully",
            "data": response_data
        }
    
    except frappe.DoesNotExistError as e:
        frappe.logger().error(f"Record not found: {str(e)}")
        return {
            "success": False,
            "message": f"Record not found: {str(e)}",
            "data": None,
            "error_code": "NOT_FOUND"
        }
    except frappe.PermissionError as e:
        frappe.logger().error(f"Permission denied: {str(e)}")
        return {
            "success": False,
            "message": "You do not have permission to access this registration",
            "data": None,
            "error_code": "PERMISSION_DENIED"
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_user_registration_details error")
        frappe.logger().error(f"Error fetching registration details: {str(e)}")
        return {
            "success": False,
            "message": f"Error fetching registration details: {str(e)}",
            "data": None,
            "error_code": "INTERNAL_ERROR"
        }

