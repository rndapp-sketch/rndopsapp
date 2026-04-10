import frappe
import jwt
from functools import wraps
from frappe.utils import now_datetime

def get_secret_key():
    return frappe.conf.get("jwt_secret_key") or "your-secret-key-change-in-production"

def validate_token(token):
    """
    Validate JWT token manually.
    Raises exception or returns user payload.
    """
    if not token:
        frappe.throw("Authorization Token is missing", frappe.AuthenticationError)
    
    # Remove Bearer prefix if present
    if token.startswith("Bearer "):
        token = token.split("Bearer ")[1]
        
    try:
        secret_key = get_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        user_id = payload.get("user_id")
        
        if not user_id:
            frappe.throw("Invalid token payload", frappe.AuthenticationError)
            
        # Optional: Verify user exists and is active
        status = frappe.db.get_value("Universal User__", user_id, "status_u_r")
        if not status or status != "Active":
            frappe.throw("User account is not active", frappe.AuthenticationError)
            
        return payload
    except jwt.ExpiredSignatureError:
        frappe.throw("Token has expired", frappe.AuthenticationError)
    except jwt.InvalidTokenError:
        frappe.throw("Invalid token", frappe.AuthenticationError)
    except Exception as e:
        frappe.throw(f"Authentication failed: {str(e)}", frappe.AuthenticationError)


def jwt_auth_required(func):
    """
    Decorator to protect API endpoints with JWT.
    Checks 'Authorization' header.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth_header = frappe.request.headers.get("Authorization")
        if not auth_header:
            frappe.throw("Missing Authorization header", frappe.AuthenticationError)
            
        payload = validate_token(auth_header)
        frappe.local.request_user_id = payload.get("user_id")
        return func(*args, **kwargs)
        
    return wrapper

@frappe.whitelist(allow_guest=True)
def get_current_user_info():
    """
    Helper API for frontend to fetch current user context.
    Must be called with Authorization Bearer token.
    """
    auth_header = frappe.request.headers.get("Authorization")
    if not auth_header:
        return {"status": "error", "message": "Missing token", "success": False}
        
    try:
        payload = validate_token(auth_header)
        user_id = payload.get("user_id")
        
        user_info = frappe.db.get_value(
            "Universal User__", 
            user_id, 
            ["name", "email_u_r", "full_name_u_r", "profile_type_u_r"], 
            as_dict=True
        )
        
        return {
            "status": "success",
            "success": True,
            "data": user_info
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "success": False
        }

@frappe.whitelist(allow_guest=True)
def logout():
    """
    Backend logout. Since JWT is stateless, we just return a success message.
    The frontend is responsible for clearing the token from localStorage.
    If a token blacklist table is created in the future, it would be added here.
    """
    return {
        "status": "success", 
        "message": "Logged out successfully",
        "success": True
    }
