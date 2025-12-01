# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ModuleRegistry(Document):
	pass


# @frappe.whitelist()
# def get_pending_task(page_name="pending-task", status_value="Pending Staff Approval"):
# 	"""
# 	Endpoint: /api/method/your_app.your_module.doctype.module_registry.module_registry.get_pending_task
# 	Fetch all doctypes listed in the Module Registry doc (where page_name matches)
# 	and return docs whose status/workflow field equals status_value.
# 	"""

# 	# --- 1) get parent Module Registry doc ---
# 	parent = frappe.get_all(
# 		"Module Registry", filters={"page_name": page_name}, fields=["name"], limit_page_length=1
# 	)

# 	if not parent:
# 		return {"results": []}

# 	parent_doc = frappe.get_doc("Module Registry", parent[0].name)
# 	print("parent_doc:", parent_doc)

# 	# --- 2) read child doctypes from child table `doctype_name` ---
# 	child_rows = getattr(parent_doc, "doctype_name", []) or []
# 	doctypes = [row.doctype_name for row in child_rows if row.doctype_name]
# 	print("parent_doc:", doctypes)

# 	results = []

# 	# --- 3) iterate doctypes ---
# 	for dt in doctypes:
# 		# check doctype exists
# 		if not frappe.db.exists("DocType", dt):
# 			continue

# 		# ensure user has read permission
# 		if not frappe.has_permission(dt, "read"):
# 			continue

# 		meta = frappe.get_meta(dt)

# 		# find the correct status/workflow field
# 		status_field = None
# 		for f in ("workflow_state", "status", "state"):
# 			if meta.has_field(f):
# 				status_field = f
# 				break

# 		if not status_field:
# 			continue  # skip doctypes without status field

# 		# pick title field for display
# 		title_field = (
# 			meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
# 		)

# 		# fetch matching docs
# 		records = frappe.get_list(
# 			dt,
# 			filters={status_field: status_value},
# 			fields=["name", title_field],
# 			order_by="modified desc",
# 			limit_page_length=100,
# 		)

# 		mapped = []
# 		for r in records:
# 			mapped.append({"name": r.get("name"), "title": r.get(title_field)})

# 		if mapped:
# 			results.append({"doctype": dt, "records": mapped})

# 	return {"page": page_name, "status_value": status_value, "results": results}

# @frappe.whitelist()
# def get_pending_task(page_name):
#     """
#     Fetch docs where the CURRENT USER can EDIT or TRANSITION.
#     Includes Debug Prints to find missing doctypes.
#     """
#     print(f"\n--- DEBUG: get_pending_task for '{page_name}' ---")

#     # 1. Get User Roles
#     current_user = frappe.session.user
#     user_roles = frappe.get_roles(current_user)
#     is_system_manager = "System Manager" in user_roles
#     print(f"User: {current_user}, Roles: {user_roles}")

#     # 2. Get Parent Module Registry
#     parent = frappe.get_all("Module Registry", filters={"page_name": page_name}, fields=["name"], limit=1)
#     if not parent:
#         print("❌ No Module Registry found for this page_name.")
#         return {"results": []}

#     parent_doc = frappe.get_doc("Module Registry", parent[0].name)
    
#     # 3. Get child doctypes
#     child_rows = getattr(parent_doc, "doctype_name", []) or []
#     doctypes = [row.doctype_name for row in child_rows if row.doctype_name]
#     print(f"Found Doctypes in Registry: {doctypes}")

#     results = []

#     # Helper function
#     def has_common_role(allowed_role_config):
#         if not allowed_role_config: return False
#         if is_system_manager: return True
        
#         config_roles = []
#         if isinstance(allowed_role_config, list):
#             config_roles = [str(r).strip() for r in allowed_role_config]
#         else:
#             raw = str(allowed_role_config)
#             for sep in [",", "\n", ";"]:
#                 if sep in raw:
#                     config_roles = [p.strip() for p in raw.split(sep) if p.strip()]
#                     break
#             if not config_roles:
#                 config_roles = [raw.strip()]
        
#         # Intersection check
#         return any(r in user_roles for r in config_roles)

#     # --- LOOP ---
#     for dt in doctypes:
#         print(f"\nChecking Doctype: {dt}")

#         if not frappe.db.exists("DocType", dt):
#             print(f"  ❌ Skipped: Doctype {dt} does not exist.")
#             continue

#         if not frappe.has_permission(dt, "read"):
#             print(f"  ❌ Skipped: No read permission for {dt}.")
#             continue

#         # Check Workflow
#         wf_name = frappe.get_value("Workflow", {"document_type": dt, "is_active": 1}, "name")
#         if not wf_name:
#             print(f"  ❌ Skipped: No Active Workflow found for {dt}.")
#             continue
        
#         print(f"  ✅ Workflow Found: {wf_name}")
#         wf_doc = frappe.get_doc("Workflow", wf_name)
#         status_field = wf_doc.workflow_state_field
        
#         # Calculate Actionable States
#         actionable_states = set()

#         # Check States (Allow Edit)
#         for state_row in wf_doc.states:
#             if has_common_role(state_row.allow_edit):
#                 actionable_states.add(state_row.state)

#         # Check Transitions (Allowed Action)
#         for transition_row in wf_doc.transitions:
#             if has_common_role(transition_row.allowed):
#                 actionable_states.add(transition_row.state)

#         if not actionable_states:
#             print(f"  ❌ Skipped: User has no valid actions in ANY state for {dt}.")
#             continue

#         print(f"  ✅ Actionable States for User: {actionable_states}")

#         # Fetch Documents
#         records = frappe.get_list(
#             dt,
#             filters={status_field: ["in", list(actionable_states)]},
#             fields=["name", "modified"], # Fetch minimal first to debug count
#             limit_page_length=100
#         )
        
#         print(f"  📄 Found {len(records)} documents in these states.")

#         if not records:
#             continue

#         # If we have records, fetch details
#         # (Re-fetching purely for constructing the result nicely, or use the list above)
#         meta = frappe.get_meta(dt)
#         title_field = (meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name"))
        
#         # Manual fetch to ensure we get the display fields
#         full_records = frappe.get_list(
#             dt,
#             filters={"name": ["in", [r.name for r in records]]},
#             fields=["name", title_field, status_field, "modified", "owner"],
#             order_by="modified desc"
#         )

#         mapped = []
#         for r in full_records:
#             mapped.append({
#                 "name": r.get("name"), 
#                 "title": r.get(title_field),
#                 "status": r.get(status_field),
#                 "modified": r.get("modified"),
#                 "owner": r.get("owner")
#             })

#         results.append({"doctype": dt, "records": mapped})

#     return {
#         "page": page_name, 
#         "user": current_user,
#         "results": results
#     }



# -=-=-=-=-=
import frappe
from frappe.model.document import Document

@frappe.whitelist()
def get_pending_task(page_name="pending-task"):
	"""
	Fetch docs where the CURRENT USER has a pending action.
	FIXED: Handles Role names that contain commas (e.g. "staff, RnD").
	"""
	
	# 1. Get Current User Roles
	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)
	is_system_manager = "System Manager" in user_roles

	print(f"\n--- DEBUG START: User '{current_user}' ---")
	# print(f"Your Roles: {user_roles}") # Commented out to reduce noise

	# 2. Get Parent Module Registry
	parent = frappe.get_all(
		"Module Registry", filters={"page_name": page_name}, fields=["name"], limit_page_length=1
	)

	if not parent:
		return {"results": []}

	parent_doc = frappe.get_doc("Module Registry", parent[0].name)
	child_rows = getattr(parent_doc, "doctype_name", []) or []
	doctypes = [row.doctype_name for row in child_rows if row.doctype_name]

	results = []

	# --- 4. Iterate Doctypes ---
	for dt in doctypes:
		if not frappe.db.exists("DocType", dt):
			continue
		if not frappe.has_permission(dt, "read"):
			continue

		# --- WORKFLOW SELECTION ---
		wf_name = None
		# FORCE Workflow for Project Registration as per your requirement
		if dt == "Project Registration":
			wf_name = "pending_approval_prjReg"
		else:
			wf_name = frappe.get_value("Workflow", {"document_type": dt}, "name")

		if not wf_name or not frappe.db.exists("Workflow", wf_name):
			continue

		wf_doc = frappe.get_doc("Workflow", wf_name)
		status_field = wf_doc.workflow_state_field
		
		actionable_states = set()

		# --- SMARTER ROLE CHECK FUNCTION ---
		def check_roles(config_raw):
			"""
			Determines if the user has permission based on the workflow string.
			Handles cases where role names contain commas.
			"""
			if not config_raw: return False
			if is_system_manager: return True

			raw_str = str(config_raw).strip()
			
			# STRATEGY 1: Check Exact Match (Handles "staff, RnD")
			# If the config is exactly one role that the user has
			if raw_str in user_roles:
				return True

			# STRATEGY 2: Check Newline Split (Standard for multiple roles)
			# If config is "Role A\nRole B"
			for part in raw_str.split('\n'):
				if part.strip() in user_roles:
					return True

			# STRATEGY 3: Check Comma Split (Legacy/CSV config)
			# Only do this if Strategy 1 & 2 failed.
			# Be careful: this breaks "staff, RnD" if "staff" isn't a role.
			# But it is necessary if config is "Manager, Auditor"
			for part in raw_str.split(','):
				if part.strip() in user_roles:
					return True
			
			return False

		# A) Check States table (Allow Edit)
		for state_row in wf_doc.states:
			if check_roles(state_row.allow_edit):
				actionable_states.add(state_row.state)

		# B) Check Transitions table (Allowed Action)
		for transition_row in wf_doc.transitions:
			if check_roles(transition_row.allowed):
				actionable_states.add(transition_row.state)

		if not actionable_states:
			continue

		# --- DATA FETCHING ---
		meta = frappe.get_meta(dt)
		title_field = (meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name"))

		records = frappe.get_list(
			dt,
			filters={
				status_field: ["in", list(actionable_states)],
				"docstatus": ["<", 2] 
			},
			fields=["name", title_field, status_field, "modified", "owner", "docstatus", "creation"],
			order_by="modified desc",
			limit_page_length=100
		)

		mapped = []
		for r in records:
			print("r:",r)
			mapped.append({
				"name": r.get("name"), 
				"title": r.get(title_field),
				"status": r.get("workflow_state"),
				"creation": r.get("creation"),
				"modified": r.get("modified"),
				"owner": r.get("owner"),
				"docstatus": r.get("docstatus")
			})

		if mapped:
			results.append({"doctype": dt, "records": mapped})
			print("results:",results)

	return {"page": page_name, "user": current_user, "results": results}