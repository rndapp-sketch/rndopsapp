# # Copyright (c) 2025, rndops and contributors
# # For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class ModuleRegistry(Document):
# 	pass



# # -=-=-=-=-=
# import frappe
# from frappe.model.document import Document

# @frappe.whitelist()
# def get_pending_task(page_name="pending-task"):
# 	"""
# 	Fetch docs where the CURRENT USER has a pending action.
# 	FIXED: Handles Role names that contain commas (e.g. "staff, RnD").
# 	"""
	
# 	# 1. Get Current User Roles
# 	current_user = frappe.session.user
# 	user_roles = frappe.get_roles(current_user)
# 	is_system_manager = "System Manager" in user_roles

# 	print(f"\n--- DEBUG START: User '{current_user}' ---")
# 	# print(f"Your Roles: {user_roles}") # Commented out to reduce noise

# 	# 2. Get Parent Module Registry
# 	parent = frappe.get_all(
# 		"Module Registry", filters={"page_name": page_name}, fields=["name"], limit_page_length=1
# 	)

# 	if not parent:
# 		return {"results": []}

# 	parent_doc = frappe.get_doc("Module Registry", parent[0].name)
	
# 	child_rows = getattr(parent_doc, "doctype_name", []) or []
# 	print("child_rows:",child_rows)
# 	# Extract both doctype_name and mod_vis
# 	doctype_data = [(row.doctype_name, row.mod_vis) for row in child_rows if row.doctype_name]

# 	results = []

# 	# --- 4. Iterate Doctypes ---
# 	for dt, mod_vis in doctype_data:
# 		if not frappe.db.exists("DocType", dt):
# 			continue
# 		if not frappe.has_permission(dt, "read"):
# 			continue

# 		# --- WORKFLOW SELECTION ---
# 		wf_name = None
# 		# FORCE Workflow for Project Registration as per your requirement
# 		if dt == "Project Registration":
# 			wf_name = "pending_approval_prjReg"
# 		else:
# 			wf_name = frappe.get_value("Workflow", {"document_type": dt}, "name")

# 		# --- DETERMINE ACTIONABLE STATES ---

# 		# A) Special Case: Advance Settlement (No Workflow)
# 		if dt == "Advance Settlement" and not wf_name:
# 			# Fetch "Submitted" documents (docstatus=1)
# 			records = frappe.get_list(
# 				dt,
# 				filters={"docstatus": 1},
# 				fields=["name", "creation", "modified", "owner", "docstatus"],
# 				order_by="modified desc",
# 				limit_page_length=100
# 			)
			
# 			mapped = []
# 			for r in records:
# 				mapped.append({
# 					"name": r.name,
# 					"title": r.name,
# 					"status": "Submitted",
# 					"creation": r.creation,
# 					"modified": r.modified,
# 					"owner": r.owner,
# 					"docstatus": r.docstatus
# 				})
			
# 			if mapped:
# 				results.append({
# 					"doctype": dt,
# 					"mod_vis": mod_vis,
# 					"records": mapped
# 				})
			
# 			continue

# 		# B) Standard Case: Workflow
# 		if not wf_name or not frappe.db.exists("Workflow", wf_name):
# 			continue

# 		wf_doc = frappe.get_doc("Workflow", wf_name)
# 		status_field = wf_doc.workflow_state_field
		
# 		actionable_states = set()

# 		# --- SMARTER ROLE CHECK FUNCTION ---
# 		def check_roles(config_raw):
# 			"""
# 			Determines if the user has permission based on the workflow string.
# 			Handles cases where role names contain commas.
# 			"""
# 			if not config_raw: return False
# 			if is_system_manager: return True

# 			raw_str = str(config_raw).strip()
			
# 			# STRATEGY 1: Check Exact Match (Handles "staff, RnD")
# 			if raw_str in user_roles: return True

# 			# STRATEGY 2: Check Newline Split
# 			for part in raw_str.split('\n'):
# 				if part.strip() in user_roles: return True

# 			# STRATEGY 3: Check Comma Split
# 			for part in raw_str.split(','):
# 				if part.strip() in user_roles: return True
			
# 			return False

# 		# A) Check States table (Allow Edit)
# 		for state_row in wf_doc.states:
# 			if check_roles(state_row.allow_edit):
# 				actionable_states.add(state_row.state)

# 		# B) Check Transitions table (Allowed Action)
# 		for transition_row in wf_doc.transitions:
# 			if check_roles(transition_row.allowed):
# 				actionable_states.add(transition_row.state)

# 		# Exclude terminal/approved states — no pending action needed
# 		for excluded in ("Draft", "Endorsement Approved", "Sanction Approved"):
# 			actionable_states.discard(excluded)

# 		# Ado_RnD: restrict strictly to Associate-Dean pending states so the
# 		# inbox doesn't pick up transitions that merely share the role.
# 		if "Ado_RnD" in user_roles and not is_system_manager:
# 			ado_states = {"Pending Associate Dean", "Pending Associate Dean Approval"}
# 			actionable_states &= ado_states

# 		if not actionable_states:
# 			continue

# 		# --- DATA FETCHING ---
# 		meta = frappe.get_meta(dt)
		
# 		# Safeguard constraint: The doctype MUST have the status_field in its schema
# 		if not meta.has_field(status_field):
# 			continue

# 		title_field = (meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name"))

# 		# "Pending Head Approval" must be visible only to the specific head
# 		# whose email is stored on the document. Field name varies per doctype.
# 		head_field_map = {
# 			"Recruitment Adhoc Contractual": "head",
# 			"Project Registration": "head_approver",
# 			"Rate Contract": "current_approver",
# 		}
# 		head_field = head_field_map.get(dt)
# 		if head_field and not meta.has_field(head_field):
# 			head_field = None

# 		extra_fields = [head_field] if head_field else []

# 		try:
# 			records = frappe.get_list(
# 				dt,
# 				filters={
# 					status_field: ["in", list(actionable_states)],
# 					"docstatus": ["<", 2]
# 				},
# 				fields=["name", title_field, status_field, "modified", "owner", "docstatus", "creation"] + extra_fields,
# 				order_by="modified desc",
# 				limit_page_length=100
# 			)
# 		except Exception as e:
# 			frappe.log_error(f"Error fetching pending tasks for {dt}", f"get_pending_task API Error: {str(e)}")
# 			print(f"Skipping {dt} due to error: {str(e)}")
# 			continue

# 		mapped = []
# 		for r in records:
# 			# print("r:",r)
# 			if (
# 				head_field
# 				and r.get(status_field) == "Pending Head Approval"
# 				and not is_system_manager
# 			):
# 				head_email = (r.get(head_field) or "").strip().lower()
# 				if head_email != current_user.lower():
# 					continue

# 			mapped.append({
# 				"name": r.get("name"),
# 				"title": r.get(title_field),
# 				"status": r.get(status_field),
# 				"creation": r.get("creation"),
# 				"modified": r.get("modified"),
# 				"owner": r.get("owner"),
# 				"docstatus": r.get("docstatus")
# 			})

# 		if mapped:
# 			results.append({
# 				"doctype": dt,
# 				"mod_vis": mod_vis,  # Added mod_vis field
# 				"records": mapped
# 			})
# 			# print("results:", results)

# 	return {"page": page_name, "user": current_user, "results": results}


# @frappe.whitelist()
# def get_task_registry(debug=0):
# 	"""
# 	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_task_registry

# 	Returns all documents that were processed/moved/approved by the current user.
# 	Only accessible by roles: staff, hos, dean, adornd, head of department.

# 	Pass ?debug=1 to include per-doctype diagnostics (why each doctype was
# 	kept/dropped, plus per-method hit counts: modified_by / Version / Workflow Action).
# 	"""

# 	try:
# 		debug_flag = bool(int(debug))
# 	except (TypeError, ValueError):
# 		debug_flag = bool(debug)

# 	# 1. Get Current User and Roles
# 	current_user = frappe.session.user
# 	user_roles = frappe.get_roles(current_user)
	
# 	# Define allowed roles based on system roles
# 	allowed_roles = [
# 		"staff, RnD",
# 		"project staff",
# 		"Hos, RnD (Head of Section, RnD)",
# 		"Dean, RnD",
# 		"Ado_RnD",
# 		"HoD (Head of Department)",
# 		"HoS (Head of School)",
# 		"HoC (Head of Center)",
# 		"head_department_center_school",
# 		"Director",
# 		"RnD Accounts",
# 		"RnD Administration",
# 		"RnD HR",
# 		"RnD Purchase",
# 		"System Manager"  # Always allow System Manager for admin access
# 	]
	
# 	# Check if user has any of the allowed roles
# 	has_allowed_role = any(role in allowed_roles for role in user_roles)
	
# 	if not has_allowed_role:
# 		return {
# 			"success": False,
# 			"message": "Access denied. Only authorized RnD roles (staff, HoS, Dean, Ado_RnD, HoD, HoS, HoC, Director, RnD Accounts/Admin/HR/Purchase) can access this endpoint.",
# 			"results": []
# 		}
	
# 	print(f"\n--- DEBUG: get_task_registry for user '{current_user}' ---")
# 	print(f"User Roles: {user_roles}")
	
# 	# 2. Get all doctypes from the rndopsapp module (case-insensitive)
# 	rndops_doctypes = frappe.get_all(
# 		"DocType",
# 		filters=[["module", "like", "%rndopsapp%"]],
# 		fields=["name", "module"]
# 	)
	
# 	if not rndops_doctypes:
# 		# Try exact match as fallback
# 		rndops_doctypes = frappe.get_all(
# 			"DocType",
# 			filters={"module": "Rndopsapp"},
# 			fields=["name", "module"]
# 		)
	
# 	doctype_names = [dt.name for dt in rndops_doctypes]
# 	print(f"Doctypes in Rndopsapp module ({len(doctype_names)}): {doctype_names}")
	
# 	skipped_info = []  # Track why doctypes are skipped
# 	debug_info = []    # Populated only when debug_flag is True

# 	def _dbg(entry):
# 		if debug_flag:
# 			debug_info.append(entry)

# 	results = []

# 	# 3. For each doctype, find documents modified by the current user
# 	# where workflow_state has been changed (meaning they performed an action)
# 	for dt_name in doctype_names:
# 		# Skip child tables and non-workflow doctypes
# 		if not frappe.db.exists("DocType", dt_name):
# 			_dbg({"doctype": dt_name, "reason": "doctype row missing"})
# 			continue

# 		meta = frappe.get_meta(dt_name)

# 		# Skip child tables
# 		if meta.istable:
# 			_dbg({"doctype": dt_name, "reason": "child table (istable=1)"})
# 			continue

# 		# Check read permission
# 		if not frappe.has_permission(dt_name, "read"):
# 			skipped_info.append({"doctype": dt_name, "reason": "no read permission"})
# 			_dbg({"doctype": dt_name, "reason": "no read permission"})
# 			continue
		
# 		# Determine status field - can be workflow_state, status, or state
# 		status_field = None
# 		for field_name in ["workflow_state", "status", "state"]:
# 			if meta.has_field(field_name):
# 				status_field = field_name
# 				break
		
# 		try:
# 			# Method 1: Get documents modified by user (simple approach)
# 			# This finds docs where the user was the last one to modify
# 			fields_to_fetch = ["name", "modified", "owner", "creation", "docstatus"]
# 			if status_field:
# 				fields_to_fetch.append(status_field)
			
# 			modified_docs = frappe.get_list(
# 				dt_name,
# 				filters={
# 					"modified_by": current_user,
# 					"docstatus": ["<", 2]  # Exclude cancelled
# 				},
# 				fields=fields_to_fetch,
# 				order_by="modified desc",
# 				limit_page_length=50
# 			)
			
# 			# Method 2: Also get docs from Version/Activity Log where user performed workflow action
# 			# Query the Version doctype to find workflow state changes by this user
# 			version_docs = []
# 			try:
# 				versions = frappe.get_all(
# 					"Version",
# 					filters={
# 						"ref_doctype": dt_name,
# 						"owner": current_user
# 					},
# 					fields=["docname", "creation", "data"],
# 					order_by="creation desc",
# 					limit_page_length=100
# 				)
				
# 				# Filter versions that contain workflow_state changes
# 				for v in versions:
# 					if v.data and "workflow_state" in v.data:
# 						if v.docname not in [d.name for d in modified_docs]:
# 							# Get the document details
# 							if frappe.db.exists(dt_name, v.docname):
# 								doc_data = frappe.get_value(
# 									dt_name, 
# 									v.docname, 
# 									fields_to_fetch,
# 									as_dict=True
# 								)
# 								if doc_data and doc_data.docstatus < 2:
# 									version_docs.append(doc_data)
# 			except Exception as e:
# 				print(f"Version query error for {dt_name}: {str(e)}")
			
# 			# Method 3: Get docs from Workflow Action (where user completed an action)
# 			# This is crucial for doctypes without track_changes enabled (like Reimbursement)
# 			wf_action_docs = []
# 			try:
# 				wf_actions = frappe.get_all(
# 					"Workflow Action",
# 					filters={
# 						"reference_doctype": dt_name,
# 						"status": "Completed",
# 						"completed_by": current_user
# 					},
# 					fields=["reference_name", "creation"], # creation here is when action was requested/completed
# 					order_by="creation desc",
# 					limit_page_length=100
# 				)
				
# 				processed_names = {w.reference_name for w in wf_actions}
				
# 				# Filter out docs we already found to avoid double fetching
# 				existing_names = set(d.name for d in modified_docs)
# 				# Note: version_docs aren't fully resolved to names yet in scope, but we check duplicates later
				
# 				# Fetch details for these docs
# 				if processed_names:
# 					# Batch fetch
# 					placeholders = ", ".join(["%s"] * len(processed_names))
# 					fetched_wf_docs = frappe.db.sql(f"""
# 						SELECT {', '.join(fields_to_fetch)}
# 						FROM `tab{dt_name}`
# 						WHERE name IN ({placeholders}) AND docstatus < 2
# 					""", tuple(processed_names), as_dict=True)
					
# 					wf_action_docs = fetched_wf_docs
# 			except Exception as e:
# 				print(f"Workflow Action query error for {dt_name}: {str(e)}")
			
# 			# Combine and deduplicate
# 			all_doc_names = set()
# 			combined_docs = []

# 			for doc in modified_docs:
# 				if doc.name not in all_doc_names:
# 					all_doc_names.add(doc.name)
# 					combined_docs.append(doc)

# 			for doc in version_docs:
# 				if doc.name not in all_doc_names:
# 					all_doc_names.add(doc.name)
# 					combined_docs.append(doc)

# 			for doc in wf_action_docs:
# 				if doc.name not in all_doc_names:
# 					all_doc_names.add(doc.name)
# 					combined_docs.append(doc)

# 			# Diagnostics: per-method counts for this doctype
# 			has_workflow = bool(frappe.db.exists("Workflow", {"document_type": dt_name}))
# 			method_counts = {
# 				"method1_modified_by": len(modified_docs),
# 				"method2_versions": len(version_docs),
# 				"method3_workflow_action": len(wf_action_docs),
# 				"combined_unique": len(combined_docs),
# 			}

# 			if not combined_docs:
# 				_dbg({
# 					"doctype": dt_name,
# 					"reason": "no matching records for this user",
# 					"status_field": status_field,
# 					"has_workflow": has_workflow,
# 					"track_changes": bool(getattr(meta, "track_changes", 0)),
# 					"counts": method_counts,
# 				})
# 				continue
			
# 			# Get title field for better display
# 			title_field = meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
			
# 			# Fetch full details for display
# 			mapped = []
# 			for doc in combined_docs:
# 				# Get title value if different from name
# 				title_value = doc.name
# 				if title_field != "name":
# 					title_value = frappe.get_value(dt_name, doc.name, title_field) or doc.name
				
# 				mapped.append({
# 					"name": doc.name,
# 					"title": title_value,
# 					"status": doc.get(status_field) if status_field else None,
# 					"creation": doc.creation,
# 					"modified": doc.modified,
# 					"owner": doc.owner,
# 					"docstatus": doc.docstatus
# 				})
			
# 			# Sort by modified date descending
# 			mapped.sort(key=lambda x: x["modified"] if x["modified"] else "", reverse=True)
			
# 			if mapped:
# 				results.append({
# 					"doctype": dt_name,
# 					"count": len(mapped),
# 					"records": mapped
# 				})
# 				_dbg({
# 					"doctype": dt_name,
# 					"reason": "included",
# 					"status_field": status_field,
# 					"has_workflow": has_workflow,
# 					"track_changes": bool(getattr(meta, "track_changes", 0)),
# 					"counts": method_counts,
# 				})
# 				print(f"Found {len(mapped)} documents in {dt_name} processed by user")

# 		except Exception as e:
# 			print(f"Error processing {dt_name}: {str(e)}")
# 			_dbg({"doctype": dt_name, "reason": "exception", "error": str(e)})
# 			continue
	
# 	# Sort results by doctype name for consistent ordering
# 	results.sort(key=lambda x: x["doctype"])

# 	response = {
# 		"success": True,
# 		"user": current_user,
# 		"roles": user_roles,
# 		"doctypes_in_module": len(doctype_names),
# 		"total_doctypes_with_data": len(results),
# 		"total_documents": sum(r["count"] for r in results),
# 		"skipped": skipped_info,
# 		"results": results,
# 	}

# 	if debug_flag:
# 		response["debug"] = {
# 			"all_doctypes_in_module": sorted(doctype_names),
# 			"per_doctype": sorted(debug_info, key=lambda x: x.get("doctype", "")),
# 		}

# 	return response



# -=-=-=-=-=-=-=-=-=-


# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ModuleRegistry(Document):
	pass



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
	print("child_rows:",child_rows)
	# Extract both doctype_name and mod_vis
	doctype_data = [(row.doctype_name, row.mod_vis) for row in child_rows if row.doctype_name]

	results = []

	# --- 4. Iterate Doctypes ---
	for dt, mod_vis in doctype_data:
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

		# --- DETERMINE ACTIONABLE STATES ---

		# A) Special Case: Advance Settlement (No Workflow)
		if dt == "Advance Settlement" and not wf_name:
			# Fetch "Submitted" documents (docstatus=1)
			records = frappe.get_list(
				dt,
				filters={"docstatus": 1},
				fields=["name", "creation", "modified", "owner", "docstatus"],
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True
			)
			
			mapped = []
			for r in records:
				mapped.append({
					"name": r.name,
					"title": r.name,
					"status": "Submitted",
					"creation": r.creation,
					"modified": r.modified,
					"owner": r.owner,
					"docstatus": r.docstatus
				})
			
			if mapped:
				results.append({
					"doctype": dt,
					"mod_vis": mod_vis,
					"records": mapped
				})
			
			continue

		# B) Standard Case: Workflow
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
			if raw_str in user_roles: return True

			# STRATEGY 2: Check Newline Split
			for part in raw_str.split('\n'):
				if part.strip() in user_roles: return True

			# STRATEGY 3: Check Comma Split
			for part in raw_str.split(','):
				if part.strip() in user_roles: return True
			
			return False

		# A) Check States table (Allow Edit)
		for state_row in wf_doc.states:
			if check_roles(state_row.allow_edit):
				actionable_states.add(state_row.state)

		# B) Check Transitions table (Allowed Action)
		for transition_row in wf_doc.transitions:
			if check_roles(transition_row.allowed):
				actionable_states.add(transition_row.state)

		# Exclude terminal/approved states — no pending action needed
		for excluded in ("Draft", "Endorsement Approved", "Sanction Approved"):
			actionable_states.discard(excluded)

		# Ado_RnD: restrict strictly to Associate-Dean pending states so the
		# inbox doesn't pick up transitions that merely share the role.
		if "Ado_RnD" in user_roles and not is_system_manager:
			ado_states = {"Pending Associate Dean", "Pending Associate Dean Approval"}
			actionable_states &= ado_states

		if not actionable_states:
			continue

		# --- DATA FETCHING ---
		meta = frappe.get_meta(dt)
		
		# Safeguard constraint: The doctype MUST have the status_field in its schema
		if not meta.has_field(status_field):
			continue

		title_field = (meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name"))

		# "Pending Head Approval" must be visible only to the specific head
		# whose email is stored on the document. Field name varies per doctype.
		head_field_map = {
			"Recruitment Adhoc Contractual": "head",
			"Project Registration": "head_approver",
			"Rate Contract": "current_approver",
		}
		head_field = head_field_map.get(dt)
		if head_field and not meta.has_field(head_field):
			head_field = None

		extra_fields = [head_field] if head_field else []

		try:
			records = frappe.get_list(
				dt,
				filters={
					status_field: ["in", list(actionable_states)],
					"docstatus": ["<", 2]
				},
				fields=["name", title_field, status_field, "modified", "owner", "docstatus", "creation"] + extra_fields,
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True
			)
		except Exception as e:
			frappe.log_error(f"Error fetching pending tasks for {dt}", f"get_pending_task API Error: {str(e)}")
			print(f"Skipping {dt} due to error: {str(e)}")
			continue

		mapped = []
		for r in records:
			# print("r:",r)
			if (
				head_field
				and r.get(status_field) == "Pending Head Approval"
				and not is_system_manager
			):
				head_email = (r.get(head_field) or "").strip().lower()
				if head_email != current_user.lower():
					continue

			mapped.append({
				"name": r.get("name"),
				"title": r.get(title_field),
				"status": r.get(status_field),
				"creation": r.get("creation"),
				"modified": r.get("modified"),
				"owner": r.get("owner"),
				"docstatus": r.get("docstatus")
			})

		if mapped:
			results.append({
				"doctype": dt,
				"mod_vis": mod_vis,  # Added mod_vis field
				"records": mapped
			})
			# print("results:", results)

	return {"page": page_name, "user": current_user, "results": results}


@frappe.whitelist()
def get_task_registry(debug=0):
	"""
	Endpoint: /api/method/rndopsapp.rndopsapp.doctype.module_registry.module_registry.get_task_registry

	Returns all documents that were processed/moved/approved by the current user.
	Only accessible by roles: staff, hos, dean, adornd, head of department.

	Pass ?debug=1 to include per-doctype diagnostics (why each doctype was
	kept/dropped, plus per-method hit counts: modified_by / Version / Workflow Action).
	"""

	try:
		debug_flag = bool(int(debug))
	except (TypeError, ValueError):
		debug_flag = bool(debug)

	# 1. Get Current User and Roles
	current_user = frappe.session.user
	user_roles = frappe.get_roles(current_user)
	
	# Define allowed roles based on system roles
	allowed_roles = [
		"staff, RnD",
		"project staff",
		"Hos, RnD (Head of Section, RnD)",
		"Dean, RnD",
		"Ado_RnD",
		"HoD (Head of Department)",
		"HoS (Head of School)",
		"HoC (Head of Center)",
		"head_department_center_school",
		"Director",
		"RnD Accounts",
		"RnD Administration",
		"RnD HR",
		"RnD Purchase",
		"System Manager"  # Always allow System Manager for admin access
	]
	
	# Check if user has any of the allowed roles
	has_allowed_role = any(role in allowed_roles for role in user_roles)
	
	if not has_allowed_role:
		return {
			"success": False,
			"message": "Access denied. Only authorized RnD roles (staff, HoS, Dean, Ado_RnD, HoD, HoS, HoC, Director, RnD Accounts/Admin/HR/Purchase) can access this endpoint.",
			"results": []
		}
	
	print(f"\n--- DEBUG: get_task_registry for user '{current_user}' ---")
	print(f"User Roles: {user_roles}")
	
	# 2. Get all doctypes from the rndopsapp module (case-insensitive)
	rndops_doctypes = frappe.get_all(
		"DocType",
		filters=[["module", "like", "%rndopsapp%"]],
		fields=["name", "module"]
	)
	
	if not rndops_doctypes:
		# Try exact match as fallback
		rndops_doctypes = frappe.get_all(
			"DocType",
			filters={"module": "Rndopsapp"},
			fields=["name", "module"]
		)
	
	doctype_names = [dt.name for dt in rndops_doctypes]
	print(f"Doctypes in Rndopsapp module ({len(doctype_names)}): {doctype_names}")
	
	skipped_info = []  # Track why doctypes are skipped
	debug_info = []    # Populated only when debug_flag is True

	def _dbg(entry):
		if debug_flag:
			debug_info.append(entry)

	results = []

	# 3. For each doctype, find documents modified by the current user
	# where workflow_state has been changed (meaning they performed an action)
	for dt_name in doctype_names:
		# Skip child tables and non-workflow doctypes
		if not frappe.db.exists("DocType", dt_name):
			_dbg({"doctype": dt_name, "reason": "doctype row missing"})
			continue

		meta = frappe.get_meta(dt_name)

		# Skip child tables
		if meta.istable:
			_dbg({"doctype": dt_name, "reason": "child table (istable=1)"})
			continue

		# Check read permission
		if not frappe.has_permission(dt_name, "read"):
			skipped_info.append({"doctype": dt_name, "reason": "no read permission"})
			_dbg({"doctype": dt_name, "reason": "no read permission"})
			continue
		
		# Determine status field - can be workflow_state, status, or state
		status_field = None
		for field_name in ["workflow_state", "status", "state"]:
			if meta.has_field(field_name):
				status_field = field_name
				break
		
		try:
			# Method 1: Get documents modified by user (simple approach)
			# This finds docs where the user was the last one to modify
			fields_to_fetch = ["name", "modified", "owner", "creation", "docstatus"]
			if status_field:
				fields_to_fetch.append(status_field)
			
			modified_docs = frappe.get_list(
				dt_name,
				filters={
					"modified_by": current_user,
					"docstatus": ["<", 2]  # Exclude cancelled
				},
				fields=fields_to_fetch,
				order_by="modified desc",
				limit_page_length=1000,
				ignore_permissions=True
			)
			
			# Method 2: Also get docs from Version/Activity Log where user performed workflow action
			# Query the Version doctype to find workflow state changes by this user
			version_docs = []
			try:
				versions = frappe.get_all(
					"Version",
					filters={
						"ref_doctype": dt_name,
						"owner": current_user
					},
					fields=["docname", "creation", "data"],
					order_by="creation desc",
					limit_page_length=100
				)
				
				# Filter versions that contain workflow_state changes
				for v in versions:
					if v.data and "workflow_state" in v.data:
						if v.docname not in [d.name for d in modified_docs]:
							# Get the document details
							if frappe.db.exists(dt_name, v.docname):
								doc_data = frappe.get_value(
									dt_name, 
									v.docname, 
									fields_to_fetch,
									as_dict=True
								)
								if doc_data and doc_data.docstatus < 2:
									version_docs.append(doc_data)
			except Exception as e:
				print(f"Version query error for {dt_name}: {str(e)}")
			
			# Method 3: Get docs from Workflow Action (where user completed an action)
			# This is crucial for doctypes without track_changes enabled (like Reimbursement)
			wf_action_docs = []
			try:
				wf_actions = frappe.get_all(
					"Workflow Action",
					filters={
						"reference_doctype": dt_name,
						"status": "Completed",
						"completed_by": current_user
					},
					fields=["reference_name", "creation"], # creation here is when action was requested/completed
					order_by="creation desc",
					limit_page_length=100
				)
				
				processed_names = {w.reference_name for w in wf_actions}
				
				# Filter out docs we already found to avoid double fetching
				existing_names = set(d.name for d in modified_docs)
				# Note: version_docs aren't fully resolved to names yet in scope, but we check duplicates later
				
				# Fetch details for these docs
				if processed_names:
					# Batch fetch
					placeholders = ", ".join(["%s"] * len(processed_names))
					fetched_wf_docs = frappe.db.sql(f"""
						SELECT {', '.join(fields_to_fetch)}
						FROM `tab{dt_name}`
						WHERE name IN ({placeholders}) AND docstatus < 2
					""", tuple(processed_names), as_dict=True)
					
					wf_action_docs = fetched_wf_docs
			except Exception as e:
				print(f"Workflow Action query error for {dt_name}: {str(e)}")
			
			# Combine and deduplicate
			all_doc_names = set()
			combined_docs = []

			for doc in modified_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			for doc in version_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			for doc in wf_action_docs:
				if doc.name not in all_doc_names:
					all_doc_names.add(doc.name)
					combined_docs.append(doc)

			# Diagnostics: per-method counts for this doctype
			has_workflow = bool(frappe.db.exists("Workflow", {"document_type": dt_name}))
			method_counts = {
				"method1_modified_by": len(modified_docs),
				"method2_versions": len(version_docs),
				"method3_workflow_action": len(wf_action_docs),
				"combined_unique": len(combined_docs),
			}

			if not combined_docs:
				_dbg({
					"doctype": dt_name,
					"reason": "no matching records for this user",
					"status_field": status_field,
					"has_workflow": has_workflow,
					"track_changes": bool(getattr(meta, "track_changes", 0)),
					"counts": method_counts,
				})
				continue
			
			# Get title field for better display
			title_field = meta.title_field if meta.title_field else ("title" if meta.has_field("title") else "name")
			
			# Fetch full details for display
			mapped = []
			for doc in combined_docs:
				# Get title value if different from name
				title_value = doc.name
				if title_field != "name":
					title_value = frappe.get_value(dt_name, doc.name, title_field) or doc.name
				
				mapped.append({
					"name": doc.name,
					"title": title_value,
					"status": doc.get(status_field) if status_field else None,
					"creation": doc.creation,
					"modified": doc.modified,
					"owner": doc.owner,
					"docstatus": doc.docstatus
				})
			
			# Sort by modified date descending
			mapped.sort(key=lambda x: x["modified"] if x["modified"] else "", reverse=True)
			
			if mapped:
				results.append({
					"doctype": dt_name,
					"count": len(mapped),
					"records": mapped
				})
				_dbg({
					"doctype": dt_name,
					"reason": "included",
					"status_field": status_field,
					"has_workflow": has_workflow,
					"track_changes": bool(getattr(meta, "track_changes", 0)),
					"counts": method_counts,
				})
				print(f"Found {len(mapped)} documents in {dt_name} processed by user")

		except Exception as e:
			print(f"Error processing {dt_name}: {str(e)}")
			_dbg({"doctype": dt_name, "reason": "exception", "error": str(e)})
			continue
	
	# Sort results by doctype name for consistent ordering
	results.sort(key=lambda x: x["doctype"])

	response = {
		"success": True,
		"user": current_user,
		"roles": user_roles,
		"doctypes_in_module": len(doctype_names),
		"total_doctypes_with_data": len(results),
		"total_documents": sum(r["count"] for r in results),
		"skipped": skipped_info,
		"results": results,
	}

	if debug_flag:
		response["debug"] = {
			"all_doctypes_in_module": sorted(doctype_names),
			"per_doctype": sorted(debug_info, key=lambda x: x.get("doctype", "")),
		}

	return response