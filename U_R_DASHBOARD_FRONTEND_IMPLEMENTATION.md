# 🎯 DASHBOARD FRONTEND IMPLEMENTATION GUIDE

## 📋 BACKEND SESSION CREATION STATUS

✅ **Session is created AUTOMATICALLY by Frappe after successful login**

When `login()` API (line 761) returns success:
- Frappe framework automatically creates a session
- `frappe.session.user` contains the logged-in email
- Frontend receives token (if JWT configured) and user info

**No additional session creation needed in backend.**

---

## ⚠️ BACKEND ENDPOINT TO CREATE

**IMPORTANT:** Backend needs a new endpoint that doesn't exist yet:

### `get_dashboard_context()` (Need to add to auth_api.py)

This should be added to `auth_api.py` by backend team:

```python
@frappe.whitelist()
def get_dashboard_context():
    """
    Dashboard state check - Returns auth + profile existence.
    Called on EVERY dashboard load to determine what to show.
    """
    try:
        current_user = frappe.session.user
        if not current_user or current_user == "Guest":
            return {
                "success": False,
                "message": "Not authenticated"
            }
        
        # Get Universal User__
        uu = frappe.db.get_value(
            "Universal User__",
            {"email_u_r": current_user},
            ["name", "full_name_u_r", "email_u_r", 
             "is_email_verified_u_r", "is_password_set_u_r"]
        )
        
        if not uu:
            return {"success": False, "message": "User not found"}
        
        # Check if profile exists
        profile_exists = frappe.db.exists(
            "Universal Registration__",
            {"universal_user_u_r": uu[0]}
        )
        
        profile_name = None
        if profile_exists:
            profile_name = frappe.db.get_value(
                "Universal Registration__",
                {"universal_user_u_r": uu[0]},
                "name"
            )
        
        return {
            "success": True,
            "auth": {
                "full_name": uu[1],
                "email": uu[2],
                "is_email_verified": uu[3],
                "is_password_set": uu[4]
            },
            "profile": {
                "exists": bool(profile_exists),
                "profile_name": profile_name
            }
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "get_dashboard_context")
        return {"success": False, "message": str(e)}
```

---

## 🚀 FRONTEND IMPLEMENTATION

### 1️⃣ CREATE USER CONTEXT (Global State)

**File:** `src/context/UserContext.tsx`

```typescript
import React, { createContext, useContext, useState, useEffect } from "react";

interface AuthData {
  full_name: string;
  email: string;
  is_email_verified: number;
  is_password_set: number;
}

interface ProfileData {
  exists: boolean;
  profile_name?: string;
}

interface UserContextType {
  loading: boolean;
  authenticated: boolean;
  auth: AuthData | null;
  profile: ProfileData | null;
  error: string | null;
  fetchDashboardContext: () => Promise<void>;
}

const UserContext = createContext<UserContextType | undefined>(undefined);

export const UserProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [auth, setAuth] = useState<AuthData | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchDashboardContext = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch("/api/method/rndopsapp.api.get_dashboard_context", {
        method: "GET",
        headers: {
          "X-Frappe-CSRF-Token": getCookie("csrf_token") || "",
          "Content-Type": "application/json",
        },
        credentials: "include", // Include cookies for session
      });

      const data = await response.json();

      if (data.message?.success) {
        setAuthenticated(true);
        setAuth(data.message.auth);
        setProfile(data.message.profile);
      } else {
        setAuthenticated(false);
        setError(data.message?.message || "Failed to fetch user context");
      }
    } catch (err) {
      setAuthenticated(false);
      setError(err instanceof Error ? err.message : "Network error");
    } finally {
      setLoading(false);
    }
  };

  // Fetch on mount
  useEffect(() => {
    fetchDashboardContext();
  }, []);

  return (
    <UserContext.Provider
      value={{
        loading,
        authenticated,
        auth,
        profile,
        error,
        fetchDashboardContext,
      }}
    >
      {children}
    </UserContext.Provider>
  );
};

export const useUser = (): UserContextType => {
  const context = useContext(UserContext);
  if (!context) {
    throw new Error("useUser must be used within UserProvider");
  }
  return context;
};

// Helper function to get cookie
function getCookie(name: string): string | null {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return decodeURIComponent(parts[1].split(";")[0]);
  return null;
}
```

---

### 2️⃣ UPDATE MAIN APP.tsx

Wrap your app with UserProvider:

```typescript
import { UserProvider } from "./context/UserContext";

function App() {
  return (
    <UserProvider>
      <Router>
        <Routes>
          {/* Your routes */}
        </Routes>
      </Router>
    </UserProvider>
  );
}
```

---

### 3️⃣ CREATE DASHBOARD COMPONENT

**File:** `src/pages/Dashboard.tsx`

```typescript
import React from "react";
import { useUser } from "../context/UserContext";
import { useNavigate } from "react-router-dom";

export const Dashboard: React.FC = () => {
  const { loading, authenticated, auth, profile, error } = useUser();
  const navigate = useNavigate();

  // Show loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  // Show error if not authenticated
  if (error || !authenticated) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
          <h2 className="text-red-800 font-bold mb-2">Authentication Error</h2>
          <p className="text-red-700 mb-4">
            {error || "You are not authenticated. Please login first."}
          </p>
          <button
            onClick={() => navigate("/login")}
            className="bg-red-600 text-white px-4 py-2 rounded hover:bg-red-700"
          >
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  // CASE A: Profile EXISTS
  if (profile?.exists) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-6xl mx-auto">
          {/* Welcome Header */}
          <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
            <h1 className="text-3xl font-bold text-gray-800 mb-2">
              Welcome back, {auth?.full_name}! 👋
            </h1>
            <p className="text-gray-600">{auth?.email}</p>
          </div>

          {/* Profile Summary Card */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                Profile Status
              </h3>
              <p className="text-2xl font-bold text-green-600">Active</p>
              <p className="text-xs text-gray-500 mt-2">
                ID: {profile.profile_name}
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                Email Status
              </h3>
              <p className="text-2xl font-bold text-green-600">Verified ✓</p>
              <p className="text-xs text-gray-500 mt-2">
                {auth?.is_email_verified ? "Confirmed" : "Pending"}
              </p>
            </div>

            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                Account Status
              </h3>
              <p className="text-2xl font-bold text-blue-600">All Set</p>
              <p className="text-xs text-gray-500 mt-2">Ready to use</p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="bg-white rounded-lg shadow-sm p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">
              Quick Actions
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <button
                onClick={() => navigate(`/profile/${profile.profile_name}`)}
                className="bg-blue-600 text-white px-4 py-3 rounded-lg hover:bg-blue-700 transition"
              >
                View Profile
              </button>
              <button
                onClick={() => navigate(`/profile/edit/${profile.profile_name}`)}
                className="bg-green-600 text-white px-4 py-3 rounded-lg hover:bg-green-700 transition"
              >
                Edit Profile
              </button>
            </div>
          </div>

          {/* Other Dashboard Widgets */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-6">
            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">
                Recent Activity
              </h3>
              <p className="text-gray-600">No recent activity</p>
            </div>

            <div className="bg-white rounded-lg shadow-sm p-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-4">
                Quick Stats
              </h3>
              <p className="text-gray-600">Stats go here</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // CASE B: Profile DOES NOT EXIST
  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Welcome Header */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h1 className="text-3xl font-bold text-gray-800 mb-2">
            Welcome, {auth?.full_name}! 👋
          </h1>
          <p className="text-gray-600">{auth?.email}</p>
        </div>

        {/* Complete Profile Card */}
        <div className="bg-orange-50 border-2 border-orange-300 rounded-lg p-8 mb-6">
          <div className="flex items-start gap-4">
            <div className="text-4xl">⚠️</div>
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-orange-900 mb-2">
                Complete Your Profile
              </h2>
              <p className="text-orange-800 mb-4">
                You have successfully verified your email and set a password. 
                Now complete your profile to unloc all features.
              </p>
              <button
                onClick={() => navigate("/profile/create")}
                className="bg-orange-600 text-white px-6 py-3 rounded-lg hover:bg-orange-700 transition font-semibold text-lg"
              >
                👉 Create Your Profile
              </button>
            </div>
          </div>
        </div>

        {/* Auth Status */}
        <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            Account Status
          </h3>
          <div className="space-y-2">
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Email Verified:</span>
              <span className="text-green-600 font-semibold">
                ✓ {auth?.is_email_verified ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Password Set:</span>
              <span className="text-green-600 font-semibold">
                ✓ {auth?.is_password_set ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Profile Status:</span>
              <span className="text-orange-600 font-semibold">
                ⚠️ Pending
              </span>
            </div>
          </div>
        </div>

        {/* Info Section */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-blue-900 mb-3">
            What's Next?
          </h3>
          <ul className="space-y-2 text-blue-800">
            <li className="flex items-start gap-2">
              <span className="text-blue-600 mt-1">1.</span>
              <span>Click "Create Your Profile" button above</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-600 mt-1">2.</span>
              <span>Fill in your personal or organization information</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-600 mt-1">3.</span>
              <span>Submit your profile for verification</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-blue-600 mt-1">4.</span>
              <span>Once approved, access full dashboard features</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
```

---

## 🔄 FLOW DIAGRAM

```
User Login Success
        ↓
Frontend redirects → /dashboard
        ↓
useEffect() calls get_dashboard_context
        ↓
Backend checks:
  - Session valid?
  - Universal User__ exists?
  - Universal Registration__ exists?
        ↓
Returns: { auth: {...}, profile: {...} }
        ↓
Frontend decides:
  - Profile exists? → Show dashboard + edit button
  - No profile? → Show "Complete Profile" card
```

---

## 🔐 SECURITY CHECKLIST

- ✅ Always include `credentials: "include"` in fetch (for cookies)
- ✅ Include CSRF token in request headers
- ✅ Check `authenticated` before rendering protected content
- ✅ Redirect to login if `authenticated === false`
- ✅ Never send sensitive data in URL
- ✅ Backend validates `frappe.session.user` every time

---

## 📌 KEY POINTS

| Aspect | Details |
|--------|---------|
| **Session** | Created automatically by Frappe after login() |
| **Token** | JWT token returned in login response (optional) |
| **Check on Load** | Call get_dashboard_context on every dashboard visit |
| **Trust Backend** | Frontend can't determine user state alone |
| **Conditional Render** | Show different UI based on profile.exists |
| **Redirect Logic** | Missing profile → /profile/create |

---

## 🚨 WHAT THIS SOLVES

✅ User can login but have no profile → Dashboard detects this  
✅ Frontend doesn't assume profile exists  
✅ Backend validates every request  
✅ Clear distinction: Auth ≠ Profile Complete  
✅ User knows exactly what step they're on  

---
