# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


def extract_eval_expression(expression):
	"""
	Extracts the JavaScript expression from a Frappe 'eval:' string.
	Returns the expression without 'eval:' prefix for frontend evaluation.
	"""
	if not expression:
		return None

	expression = str(expression).strip()

	if expression.startswith("eval:"):
		return expression[5:].strip()

	return expression


class DirectPurchase(Document):

	def validate(self):
		"""Server-side mirror of the client script calculations and validations."""
		self.calculate_totals()
		self.validate_purchase_committee()

	def calculate_totals(self):
		"""Calculate row totals and overall total estimate (mirrors client script)."""
		from frappe.utils import flt

		total = 0
		for row in self.get("table_gdxp", []):
			row.estimated_amount_total_price_in_rs = flt(row.quantity) * flt(row.estimatedprice)
			total += flt(row.estimated_amount_total_price_in_rs)

		self.total_estimate = total

	def validate_purchase_committee(self):
		"""Require minimum 3 Purchase Committee members when total > ₹2,00,000."""
		from frappe.utils import flt

		if flt(self.total_estimate) > 200000:
			row_count = len(self.get("table_teqd", []))
			if row_count < 3:
				frappe.throw(
					_("Minimum 3 Purchase Committee members are required "
					  "when Total Estimate exceeds ₹2,00,000.")
				)


# =============================================================================
# API ENDPOINTS
# =============================================================================

@frappe.whitelist()
def get_direct_purchase_fields(doc_name=None):
	"""
	API to return Direct Purchase field metadata, prefill data,
	link options, child table metadata, and client scripts.
	"""
	meta = frappe.get_meta("Direct Purchase")

	fields = []
	for f in meta.get("fields"):
		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": f.options,
			"mandatory": f.reqd,
			"hidden": f.hidden,
			"read_only": f.read_only,
			"default": f.default,
			"description": f.description,
			"depends_on": f.depends_on,
			"mandatory_depends_on": f.mandatory_depends_on,
			"read_only_depends_on": f.read_only_depends_on,
			"depends_on_eval": extract_eval_expression(f.depends_on),
			"mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
			"read_only_depends_on_eval": extract_eval_expression(f.read_only_depends_on),
		}

		# Handle Child Tables: include child field metadata
		if f.fieldtype == "Table" and f.options:
			child_meta = frappe.get_meta(f.options)
			child_fields_list = []
			for cf in child_meta.fields:
				cf_data = {
					"fieldname": cf.fieldname,
					"label": cf.label,
					"fieldtype": cf.fieldtype,
					"options": cf.options,
					"mandatory": cf.reqd,
					"in_list_view": cf.in_list_view,
					"read_only": cf.read_only,
					"fetch_from": cf.fetch_from,
					"default": cf.default,
				}
				# Include link_filters for Link fields (e.g. webmail_id filtered by empclass)
				if cf.fieldtype == "Link" and getattr(cf, "link_filters", None):
					cf_data["link_filters"] = cf.link_filters
				child_fields_list.append(cf_data)
			field_data["child_fields"] = child_fields_list

		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	# ---- Prefill current user details ----
	if doc_name:
		try:
			doc = frappe.get_doc("Direct Purchase", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	else:
		user = frappe.session.user
		if user and user != "Guest":
			try:
				user_doc = frappe.get_doc("User", user)
				prefill_data["applicant_name"] = user_doc.full_name
				prefill_data["applicant_department"] = user_doc.department_name
				prefill_data["applicant_designation"] = user_doc.designation_name
			except Exception:
				pass

	# Declaration checkboxes default to unchecked
	prefill_data.setdefault("dec_1", 0)
	prefill_data.setdefault("dec_2", 0)

	# ---- Link Options / Dropdown Options ----

	# Account Head options (from Budget Head, same pattern as Temporary Advance)
	try:
		account_heads = frappe.get_all(
			"Budget Head",
			fields=["name as value", "budget_head as label"],
			limit_page_length=0,
		)
		link_options["account_head"] = [
			{"value": r["value"], "label": r.get("label") or r["value"]} for r in account_heads
		]
	except Exception:
		link_options["account_head"] = []

	# Users list (for applying_for fields — all enabled users)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1},
			fields=["name as value", "full_name as label"],
			limit_page_length=0,
		)
		link_options["applying_for_name"] = users
	except Exception:
		link_options["applying_for_name"] = []

	# Purchase Committee webmail_id — filtered by empclass
	# Include full_name + designation_name so React can auto-fill pc_name & designation locally
	try:
		# Look up empclass IDs matching the target employee classes
		empclass_ids = frappe.get_all(
			"EmployeeClass_prornd",
			filters={"empclass_name": ["in", ["P - Permanent Employee", "IF - Inspired Faculty"]]},
			pluck="name",
		)
		user_filters = {"enabled": 1}
		if empclass_ids:
			user_filters["empclass"] = ["in", empclass_ids]

		committee_users_raw = frappe.get_all(
			"User",
			filters=user_filters,
			fields=["name", "full_name", "designation_name"],
			limit_page_length=0,
		)
		# Build options with extra fields for auto-populate
		committee_users = []
		for u in committee_users_raw:
			committee_users.append({
				"value": u.name,
				"label": u.full_name or u.name,
				"full_name": u.full_name,
				"designation_name": u.designation_name,
			})
		link_options["webmail_id"] = committee_users
	except Exception:
		link_options["webmail_id"] = []

	# ---- Other-PI picker ----
	# Same source the other Other-PI modules use, so the type-to-search list is
	# identical across Travel / IGF / ICSS / Reimbursement / Direct Purchase.
	try:
		from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import (
			_get_permanent_employee_options,
		)

		link_options["dp_other_pi_id"] = _get_permanent_employee_options()
	except Exception:
		link_options["dp_other_pi_id"] = []

	# ---- Client Scripts ----
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "Direct Purchase", "enabled": 1},
			fields=["name", "script", "view"]
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view
			})
	except Exception:
		pass

	# ---- Computation Rules (derived from client script) ----
	# These encode the client script logic in a structured format
	# so the React frontend can implement them without parsing raw JS.
	computation_rules = {
		# Row-level calculation: estimated_amount = quantity * estimatedprice
		"row_calculations": [
			{
				"table_fieldname": "table_gdxp",
				"target_field": "estimated_amount_total_price_in_rs",
				"formula": "quantity * estimatedprice",
				"trigger_fields": ["quantity", "estimatedprice"],
				"description": "Row total = Quantity × Estimated Rate",
			}
		],
		# Parent-level aggregation: total_estimate = SUM of all row totals
		"aggregations": [
			{
				"target_field": "total_estimate",
				"source_table": "table_gdxp",
				"source_field": "estimated_amount_total_price_in_rs",
				"operation": "sum",
				"description": "Total Estimate = sum of all row amounts",
			}
		],
		# Conditional visibility: show/hide fields based on computed values
		"conditional_visibility": [
			{
				"target_field": "table_teqd",
				"condition": "total_estimate > 200000",
				"description": "Purchase Committee table visible only when Total Estimate > ₹2,00,000",
				"on_show": {
					"min_rows": 3,
					"description": "Auto-add 3 empty rows when table becomes visible",
				},
				"on_hide": {
					"clear_rows": True,
					"description": "Clear all committee rows when hidden",
				},
			}
		],
		# Validation rules applied before save
		"validations": [
			{
				"condition": "total_estimate > 200000",
				"check": "table_teqd.length >= 3",
				"error_message": "Minimum 3 Purchase Committee members are required when Total Estimate exceeds ₹2,00,000.",
			}
		],
		# Auto-populate rules: fetch and fill related fields when a trigger field changes
		"auto_populate": [
			{
				"trigger_field": "webmail_id",
				"context": "child_table",
				"table_fieldname": "table_teqd",
				"api": "rndopsapp.doctype.direct_purchase.direct_purchase.get_user_details_direct_purchase",
				"api_param": "user_email",
				"field_map": {
					"full_name": "pc_name",
					"designation_name": "designation"
				},
				"description": "When webmail_id is selected, auto-fill pc_name and designation from User"
			},
			{
				"trigger_field": "applying_for_name",
				"context": "parent",
				"api": "rndopsapp.doctype.direct_purchase.direct_purchase.get_user_details_direct_purchase",
				"api_param": "user_email",
				"field_map": {
					"full_name": "applying_for_name",
					"department_name": "applying_for_department",
					"designation_name": "applying_for_designation"
				},
				"description": "When applying_for user is selected, fill name/dept/designation"
			}
		],
	}

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
		"computation_rules": computation_rules,
	}


@frappe.whitelist()
def save_direct_purchase_data(data):
	"""
	Creates or updates a Direct Purchase document.
	Handles child tables and file uploads (Attach fields) via MinIO.
	"""
	from rndopsapp.minio import get_rnd_file_service
	import base64

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new = False

		# 1. Initialize Document
		if doc_name and frappe.db.exists("Direct Purchase", doc_name):
			doc = frappe.get_doc("Direct Purchase", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("Direct Purchase")
			is_new = True

		meta = frappe.get_meta("Direct Purchase")

		# 2. First Pass: Set standard fields (skip files and tables)
		file_fields = []

		for fieldname, value in data.items():
			if fieldname in ["name", "doctype", "docstatus"]:
				continue

			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)

			if df.fieldtype in ["Attach", "Attach Image"]:
				file_fields.append((fieldname, value))
			elif df.fieldtype == "Table":
				file_fields.append((fieldname, value))
			else:
				if value not in [None, ""]:
					doc.set(fieldname, value)

		# 3. Create/Save Initial Document to get Name (if new)
		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)

		# 4. Second Pass: Process Files and Tables (now we have doc.name)

		# Resolve Project Registration docname from project_no for correct MinIO path:
		# rnd-files/Project_Registration/{project_docname}/directpurchase/{doc.name}/
		_proj_no = doc.project_no or data.get("project_no")
		_project_docname = None
		if _proj_no:
			_project_docname = frappe.db.get_value(
				"Project Registration", {"project_no": _proj_no}, "name"
			)
		# Fall back to attaching directly to Direct Purchase if no project found
		_file_doctype = "Project Registration" if _project_docname else "Direct Purchase"
		_file_docname = _project_docname if _project_docname else doc.name
		_folder = f"directpurchase/{doc.name}"

		# Only connect to object storage (MinIO) once we actually have a file to
		# upload. Building the client eagerly made every save fail — including
		# saves with no attachments at all — wherever the MinIO endpoint is not
		# configured, e.g. local/dev environments. Same fix as
		# indent_general_form.save_indent_general_form_data.
		_file_service_cache = {}

		def file_service_lazy():
			if "client" not in _file_service_cache:
				_file_service_cache["client"] = get_rnd_file_service()
			return _file_service_cache["client"]

		for fieldname, value in file_fields:
			df = meta.get_field(fieldname)

			if df.fieldtype == "Table":
				if isinstance(value, str):
					try:
						value = json.loads(value)
					except Exception:
						pass

				if isinstance(value, list):
					doc.set(fieldname, [])  # Clear existing
					child_meta = frappe.get_meta(df.options)

					for child_row in value:
						row_dict = child_row.copy()
						
						# Remove 'name' for new rows to allow Frappe to auto-generate proper names
						if row_dict.get("name") and str(row_dict.get("name")).startswith("new-"):
							del row_dict["name"]

						# Remove internal properties not needed for appending
						for k in ["creation", "modified", "owner", "modified_by", "docstatus", "parent", "parentfield", "parenttype"]:
							row_dict.pop(k, None)

						# Handle files in child row
						for cf in child_meta.fields:
							if cf.fieldtype in ["Attach", "Attach Image"] and row_dict.get(cf.fieldname):
								f_val = row_dict[cf.fieldname]
								if isinstance(f_val, dict) and f_val.get("file_data"):
									try:
										content = base64.b64decode(f_val["file_data"])
										result = file_service_lazy().save_file(
											filename=f_val.get("file_name", "attachment"),
											content=content,
											is_private=True,
											doctype=_file_doctype,
											docname=_file_docname,
											folder=_folder
										)
										if result.get("status"):
											row_dict[cf.fieldname] = result.get("file_url") or result.get("data", {}).get("file_url")
									except Exception as e:
										frappe.log_error(f"Child File Error: {e}")

						doc.append(fieldname, row_dict)

			elif df.fieldtype in ["Attach", "Attach Image"]:
				if isinstance(value, dict) and value.get("file_data"):
					try:
						content = base64.b64decode(value["file_data"])
						result = file_service_lazy().save_file(
							filename=value.get("file_name", "attachment"),
							content=content,
							is_private=True,
							doctype=_file_doctype,
							docname=_file_docname,
							folder=_folder
						)
						if result.get("status"):
							doc.set(fieldname, result.get("file_url") or result.get("data", {}).get("file_url"))
					except Exception as e:
						frappe.log_error(f"File Upload Error for {fieldname}: {str(e)}")

				elif isinstance(value, str):
					# Keep existing URL
					doc.set(fieldname, value)

		# 5. Final Save
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Direct Purchase Save Error")
		frappe.throw(f"Failed to save Direct Purchase: {str(e)}")


@frappe.whitelist()
def get_direct_purchase_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Direct Purchase", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	print(f"\n--- [GET_ACTIONS] docname={docname}, current_state='{current_state}', user={frappe.session.user}")
	print(f"    User Roles: {user_roles}")

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": "Direct Purchase", "is_active": 1},
		"name"
	)

	if not workflow_name:
		return []

	# Only the specifically-assigned Other PI (or a System Manager) may act on a
	# purchase parked in 'Pending Other PI'. The transition is role-gated on
	# "Permanent Employee", which the applicant usually is too — so without this
	# the applicant was offered a Forward button they could not actually use
	# (perform_direct_purchase_action throws on click).
	if current_state == "Pending Other PI":
		is_system_manager = "System Manager" in user_roles
		assigned_pi = (doc.get("dp_other_pi_id") or "").lower()
		if not is_system_manager and assigned_pi != (frappe.session.user or "").lower():
			return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		print(f"    Transition: state='{transition.state}' action='{transition.action}' allowed='{transition.allowed}'")

		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			print(f"      [PASS] Role check passed")
			if transition.condition:
				print(f"      Condition: {transition.condition}")
				try:
					eval_context = {
						"doc": doc,
						"flt": frappe.utils.flt,
						"cint": frappe.utils.cint,
						"frappe": frappe._dict(
							db=frappe._dict(
								get_value=frappe.db.get_value,
								get_list=frappe.db.get_list,
								get_single_value=frappe.db.get_single_value,
							),
							utils=frappe._dict(
								flt=frappe.utils.flt,
								cint=frappe.utils.cint,
							),
							session=frappe.session,
						),
					}
					result = frappe.safe_eval(transition.condition, None, eval_context)
					print(f"      Condition result: {result}")
					if not result:
						print(f"      [SKIP] Condition is False")
						continue
				except Exception as e:
					print(f"      [ERROR] Condition eval failed: {str(e)}")
					continue

			allowed_actions.append(transition.action)
			print(f"      [ADDED] action='{transition.action}'")
		else:
			print(f"      [FAIL] Role check. Expected one of: {transition_roles}")

	print(f"    Final allowed_actions: {list(dict.fromkeys(allowed_actions))}")

	return list(dict.fromkeys(allowed_actions))


# @frappe.whitelist()
# def perform_direct_purchase_action(docname, action):
# 	"""
# 	Executes the selected workflow action and updates the document state.
# 	"""
# 	try:
# 		doc = frappe.get_doc("Direct Purchase", docname)
# 		current_state = doc.workflow_state or "Draft"
# 		user_roles = frappe.get_roles(frappe.session.user)

# 		workflow_name = frappe.db.get_value(
# 			"Workflow",
# 			{"document_type": "Direct Purchase", "is_active": 1},
# 			"name"
# 		)

# 		if not workflow_name:
# 			frappe.throw("No active workflow found for Direct Purchase.")

# 		workflow = frappe.get_doc("Workflow", workflow_name)

# 		next_state = None
# 		transition = None

# 		for t in workflow.transitions:
# 			if t.state == current_state and t.action == action:
# 				allowed_roles = t.get("allowed") or []
# 				if isinstance(allowed_roles, str):
# 					allowed_roles = [allowed_roles]

# 				if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
# 					continue

# 				if t.condition:
# 					try:
# 						if not frappe.safe_eval(t.condition, None, {"doc": doc}):
# 							continue
# 					except Exception as e:
# 						frappe.log_error(f"Workflow condition error: {str(e)}", "Workflow Error")
# 						continue

# 				next_state = t.next_state
# 				transition = t
# 				break

# 		if not next_state:
# 			frappe.throw(
# 				f"No valid transition found for action '{action}' from state "
# 				f"'{current_state}' matching your role and conditions."
# 			)

# 		doc.workflow_state = next_state

# 		state_doc = next((s for s in workflow.states if s.state == next_state), None)

# 		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
# 			doc.submit()
# 		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
# 			doc.cancel()
# 		else:
# 			doc.save(ignore_permissions=True)

# 		frappe.db.commit()

# 		return {
# 			"status": "success",
# 			"message": f"Action '{action}' completed. New State: {next_state}",
# 			"docname": docname,
# 			"workflow_state": next_state,
# 			"next_actions": get_direct_purchase_workflow_actions(docname)
# 		}

# 	except Exception as e:
# 		frappe.db.rollback()
# 		frappe.log_error(frappe.get_traceback(), "Direct Purchase Action Error")
# 		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_direct_purchase_pi_projects(pi=None):
	"""Projects owned by the (session) PI — used by the Other-PI approval step."""
	from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import get_pi_projects

	return get_pi_projects(pi)


@frappe.whitelist()
def get_direct_purchase_project_account_heads(project_name):
	"""Account heads for a given project — used by the Other-PI approval step."""
	from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import get_project_account_heads

	return get_project_account_heads(project_name)


@frappe.whitelist()
def perform_direct_purchase_action(docname, action, extra_data=None):
	print("------=-==-=-=-=-=-=-=-=-=-=-=-DP-=-=-=-=-=-=-=-=-=-=-=-")
	"""
	Executes the selected workflow action and updates the document state.
	"""
	print(f"\n--- [START] perform_direct_purchase_action ---")
	print(f"Docname: {docname} | Action requested: {action}")
	
	try:
		doc = frappe.get_doc("Direct Purchase", docname)
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)
		
		print(f"Current State: '{current_state}' | User: {frappe.session.user}")
		print(f"User Roles: {user_roles}")

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": "Direct Purchase", "is_active": 1},
			"name"
		)

		print(f"Active Workflow Found: {workflow_name}")

		if not workflow_name:
			print("[ERROR] No active workflow found for Direct Purchase.")
			frappe.throw("No active workflow found for Direct Purchase.")

		workflow = frappe.get_doc("Workflow", workflow_name)

		# --- Other-PI routing -------------------------------------------------
		# On Submit, a purchase charged to another PI's project goes to that
		# specific PI first (Pending Other PI) rather than straight down the
		# normal chain. Mirrors perform_indent_general_form_action.
		if (
			action == "Submit"
			and current_state == "Draft"
			and (doc.get("dp_other_pi") or "").strip() == "Other"
		):
			if not doc.get("dp_other_pi_id"):
				frappe.throw("Please select the Other PI before submitting.")
			doc.workflow_state = "Pending Other PI"
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			return {"status": "success", "next_state": "Pending Other PI"}

		# At the Other-PI step only the assigned PI (or a System Manager) may
		# act, and approving means charging one of THEIR OWN projects.
		if current_state == "Pending Other PI":
			is_system_manager = "System Manager" in user_roles
			assigned_pi = (doc.get("dp_other_pi_id") or "").lower()
			if not is_system_manager and assigned_pi != (frappe.session.user or "").lower():
				frappe.throw("You are not authorised to act on this purchase.")

			if action in ("Forward", "Approve"):
				from rndopsapp.rndopsapp.doctype.reimbursement.reimbursement import get_pi_projects

				data = extra_data
				if isinstance(data, str):
					data = json.loads(data or "{}")
				data = data or {}

				project_name = (data.get("project_name") or "").strip()
				if not project_name:
					frappe.throw("Please select a project before approving.")

				owns = next(
					(p for p in get_pi_projects() if p.get("value") == project_name), None
				)
				if not owns:
					frappe.throw("Selected project does not belong to you.")

				doc.project_no = (
					owns.get("project_no") or owns.get("project_number") or project_name
				)
				# The Other-PI picker lists a project's account heads by LABEL
				# ("Overhead"), but Direct Purchase.account_head is a Link to
				# Budget Head, whose docnames are hashes ("h1lhg99vfq").
				# Assigning the label directly fails link validation with
				# "Could not find Account Head: Overhead", so resolve it.
				account_head = (data.get("account_head") or "").strip()
				if account_head:
					resolved = None
					if frappe.db.exists("Budget Head", account_head):
						resolved = account_head
					else:
						resolved = frappe.db.get_value(
							"Budget Head", {"budget_head": account_head}, "name"
						)
					if resolved:
						doc.account_head = resolved
					else:
						# Leave whatever the applicant chose rather than blanking
						# the field, but make the mismatch visible.
						frappe.msgprint(
							_("Account head {0} has no matching Budget Head; left unchanged.").format(
								account_head
							),
							indicator="orange",
							alert=True,
						)

				doc.workflow_state = "Pending Staff Approval"
				doc.save(ignore_permissions=True)
				frappe.db.commit()
				return {"status": "success", "next_state": "Pending Staff Approval"}
			# Reject / Put Back fall through to the normal transition resolver.

		next_state = None
		transition = None

		print("Iterating over workflow transitions...")
		for t in workflow.transitions:
			# Debug transition match
			print(f"  Checking Transition -> State: '{t.state}', Action: '{t.action}'")
			
			if t.state == current_state and t.action == action:
				print(f"    [MATCH] State & Action match found!")
				
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]
				
				print(f"    Allowed roles for transition: {allowed_roles}")

				# Role check
				if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
					print(f"    [FAIL] Role check failed.")
					print(f"           - Workflow expects one of: {allowed_roles}")
					print(f"           - User actually has: {user_roles}")
					print(f"           -> TIP: Make sure the Role Name in the Workflow exactly matches the Role Name assigned to the user.")
					continue
				else:
					print("    [PASS] Role check passed.")

				# Condition check
				if t.condition:
					print(f"    Evaluating condition: {t.condition}")
					try:
						eval_context = {
							"doc": doc,
							"flt": frappe.utils.flt,
							"cint": frappe.utils.cint,
							"frappe": frappe._dict(
								db=frappe._dict(
									get_value=frappe.db.get_value,
									get_list=frappe.db.get_list,
									get_single_value=frappe.db.get_single_value,
								),
								utils=frappe._dict(
									flt=frappe.utils.flt,
									cint=frappe.utils.cint,
								),
								session=frappe.session,
							),
						}
						if not frappe.safe_eval(t.condition, None, eval_context):
							print("    [FAIL] Condition evaluated to False.")
							continue
						print("    [PASS] Condition evaluated to True.")
					except Exception as e:
						print(f"    [ERROR] Workflow condition error: {str(e)}")
						frappe.log_error(f"Workflow condition error: {str(e)}", "Workflow Error")
						continue

				# Successful transition found
				next_state = t.next_state
				transition = t
				print(f"    [SUCCESS] Transition approved! Next state will be: '{next_state}'")
				break
			else:
				# Just skip quietly if not matching current state/action
				pass

		if not next_state:
			error_msg = f"No valid transition found for action '{action}' from state '{current_state}' matching your role and conditions."
			print(f"[ERROR] {error_msg}")
			frappe.throw(error_msg)

		doc.workflow_state = next_state
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc:
			print(f"Target state doc_status: {state_doc.doc_status} (Current docstatus: {doc.docstatus})")

		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
			print("[ACTION] Submitting document...")
			doc.submit()
		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
			print("[ACTION] Cancelling document...")
			doc.cancel()
		else:
			print("[ACTION] Updating workflow_state via db.set_value (bypassing Frappe workflow sandbox)...")
			frappe.db.set_value("Direct Purchase", docname, "workflow_state", next_state)

			# Since db.set_value does NOT trigger on_update hooks,
			# manually call the Kafka publishing hook if state is now 'Approved'
			if next_state == "Approved":
				print("[KAFKA] State is 'Approved' — manually triggering check_workflow_and_publish...")
				from rndopsapp.rndopsapp.commitPayment import check_workflow_and_publish
				# Reload the doc so it reflects the updated workflow_state
				doc.reload()
				check_workflow_and_publish(doc)

		frappe.db.commit()
		print(f"--- [END] perform_direct_purchase_action SUCCESS ---\n")

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_direct_purchase_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		print(f"\n--- [EXCEPTION] perform_direct_purchase_action ---")
		print(f"Error: {str(e)}")
		frappe.log_error(frappe.get_traceback(), "Direct Purchase Action Error")
		return {"status": "error", "message": str(e)}




@frappe.whitelist()
def submit_direct_purchase(docname):
	"""
	Submit a Direct Purchase document using Workflow transitions.
	"""
	return perform_direct_purchase_action(docname, "Submit")


@frappe.whitelist()
def get_user_details_direct_purchase(user_email):
	"""
	Fetch user details (name, department, designation) for auto-populating
	Purchase Committee rows and Applying For fields.
	Called by React when a webmail_id is selected.
	"""
	if not user_email:
		frappe.throw(_("User Email is required."))

	try:
		user_email = str(user_email).strip('"').strip("'")
		user_doc = frappe.get_doc("User", user_email)

		result = {
			"full_name": user_doc.full_name,
			"department_name": user_doc.department_name,
			"designation_name": user_doc.designation_name,
		}

		# Resolve department link to actual name
		if user_doc.department_name:
			try:
				dept_doc = frappe.get_doc("Department_prornd", user_doc.department_name)
				result["department_name"] = dept_doc.dept_name
			except Exception:
				pass

		return result

	except frappe.DoesNotExistError:
		return None
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), _("Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))


# =============================================================================
# DOWNSTREAM WORKFLOW GENERATORS (RDP-11, Sanction Sheet, PO)
# =============================================================================

@frappe.whitelist()
def generate_p11_form(docname):
	"""
	Generates a P_11 Form Draft based on the approved Direct Purchase document.
	Maps child table rows from Direct Purchase to the P_11 Form.
	"""
	try:
		dp_doc = frappe.get_doc("Direct Purchase", docname)
		
		# Validation: Check if it's already in the correct state
		if dp_doc.workflow_state == "RDP11Generated":
			return {"status": "success", "message": "P_11 Form was already generated."}

		p11 = frappe.new_doc("P_11 Form")
		p11.name = dp_doc.name
		p11.currency = "INR"
		p11.total_basic_value = dp_doc.total_estimate
		p11.grand_total = dp_doc.total_estimate

		# Map the child table (Items to be purchased -> P 11 item table)
		for row in dp_doc.get("table_gdxp", []):
			p11.append("table_hsrb", {
				"item_name": row.itemname,
				"item_description": row.itemdesciption,
				"item_quantity": row.quantity,
				"item_unit_price": row.estimatedprice,
				"dp_total_price": row.estimated_amount_total_price_in_rs
			})

		p11.insert(ignore_permissions=True)
		
		# Update Direct Purchase state via perform_direct_purchase_action (if applicable) or directly
		frappe.db.set_value("Direct Purchase", dp_doc.name, "workflow_state", "RDP11Generated")
		frappe.db.commit()

		return {
			"status": "success", 
			"docname": p11.name, 
			"message": f"Successfully generated P_11 Form: {p11.name}"
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "P_11 Form Generation Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def generate_sanction_sheet(p11_docname, dp_docname=None):
	"""
	Generates a Sanction Sheet document from a verified P_11 Form.
	"""
	try:
		p11_doc = frappe.get_doc("P_11 Form", p11_docname)
		
		ss = frappe.new_doc("sanction_sheet")
		ss.amended_from = p11_doc.name
		
		# If we have the Original Direct Purchase, map Applicant Details
		if dp_docname:
			dp_doc = frappe.get_doc("Direct Purchase", dp_docname)
			applicant = dp_doc.applying_for_name if dp_doc.register_for == "Other" else dp_doc.applicant_name
			dept = dp_doc.applying_for_department if dp_doc.register_for == "Other" else dp_doc.applicant_department
			
			ss.ss_applicant_name = applicant
			ss.ss_department_for_purchase = dept
			ss.ss_account_head = dp_doc.account_head
			ss.ss_actual_expenditure = dp_doc.total_estimate 

		ss.ss_total_es_basic_value = p11_doc.total_basic_value
		ss.ss_pack_forward = p11_doc.packing_and_forwarding
		ss.ss_freight = p11_doc.freight
		ss.ss_other_charges = p11_doc.other_charges
		ss.ss_grand_total = p11_doc.grand_total

		# Map the child table over
		for row in p11_doc.get("table_hsrb", []):
			ss.append("table_bttk", {
				"item_name": row.item_name,
				"item_description": row.item_description,
				"item_quantity": row.item_quantity,
				"item_unit_price": row.item_unit_price,
				"dp_total_price": row.dp_total_price,
				"item_make": row.item_make,
				"item_model": row.item_model,
				"item_discount": row.item_discount,
				"item_gst": row.item_gst
			})

		ss.insert(ignore_permissions=True)
		
		# Update dp_doc status if passed
		if dp_docname:
			frappe.db.set_value("Direct Purchase", dp_docname, "workflow_state", "SancSheetGenerated")
			frappe.db.commit()

		return {
			"status": "success", 
			"docname": ss.name, 
			"message": f"Successfully generated Sanction Sheet: {ss.name}"
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Sanction Sheet Generation Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def generate_purchase_order(sanction_sheet_name, dp_docname=None):
	"""
	Finalizes the Purchase Order stage on the original Direct Purchase document.
	Calculates the final authorized PO value explicitly excluding 'ss_other_charges'.
	"""
	try:
		ss_doc = frappe.get_doc("sanction_sheet", sanction_sheet_name)
		
		# Calculate final PO value (excluding 'ss_other_charges')
		final_po_total = (
			frappe.utils.flt(ss_doc.ss_total_es_basic_value) + 
			frappe.utils.flt(ss_doc.ss_pack_forward) + 
			frappe.utils.flt(ss_doc.ss_freight)
		)
			
		if dp_docname:
			# Transition master workflow state to POGenerated
			frappe.db.set_value("Direct Purchase", dp_docname, "workflow_state", "POGenerated")
			frappe.db.commit()
			
		return {
			"status": "success",
			"message": f"Direct Purchase marked as POGenerated. Final Authorized PO Value: {final_po_total} (excluding Other Charges)."
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "PO Generation Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def upload_po_document(docname, app_id, project_no):
	"""
	Endpoint to upload a Purchase Order PDF or Image to object storage (MinIO).
	Saves the file inside: prod-rnd-files/Project_Registration/{project_docname}/directpurchase/{app_id}/
	"""
	print(f"[PO UPLOAD START] -> docname={docname}, app_id={app_id}, project_no={project_no}")
	import sys; sys.stdout.flush()

	from rndopsapp.minio import get_rnd_file_service

	if "file" in frappe.request.files:
		file_obj = frappe.request.files["file"]
		filename = file_obj.filename
		content = file_obj.stream.read()
	elif frappe.local.uploaded_file:
		content = frappe.local.uploaded_file
		filename = frappe.local.uploaded_filename
	else:
		print("[PO UPLOAD ERROR] No file attached")
		return {"status": False, "message": "No file attached"}

	try:
		file_service = get_rnd_file_service()

		# Resolve Project Registration docname from project_no field
		project_docname = frappe.db.get_value(
			"Project Registration", {"project_no": project_no}, "name"
		)
		if not project_docname:
			print(f"[PO UPLOAD ERROR] No Project Registration found for project_no: {project_no}")
			return {"status": False, "message": f"No Project Registration found for project_no: {project_no}"}

		print(f"[PO UPLOAD] Found project_docname: {project_docname}")

		# Path: rnd-files/Project_Registration/{project_docname}/directpurchase/{app_id}/po/
		folder_path = f"directpurchase/{app_id}/po"

		# Prepare file data for MinIO
		data = file_service._bytes(content)
		file_hash = file_service._hash(data)
		path = file_service._path(
			filename=filename, 
			file_hash=file_hash, 
			private=True, 
			doctype="Project Registration", 
			docname=project_docname, 
			folder=folder_path,
			use_hash=False
		)
		mime = file_service._mime(filename)

		print(f"[PO UPLOAD] Generated MinIO path: {path}")

		# Upload directly to object storage WITHOUT creating a Frappe File doc
		# This bypasses Frappe's `URL must start with http` File doctype validation.
		file_service.storage.upload(path, data, mime)
		
		full_minio_path = f"prod-rnd-files/{path}"
		print(f"[PO UPLOAD] Successful MinIO upload directly. Path: {full_minio_path}")
		import sys; sys.stdout.flush()

		# Update the corresponding Sanction Sheet's file_path using purely SQL
		if frappe.db.exists("sanction_sheet", docname):
			frappe.db.sql(
				"""UPDATE `tabsanction_sheet` SET file_path = %s, modified = NOW() WHERE name = %s""",
				(full_minio_path, docname)
			)
			frappe.db.commit()
			print(f"[PO UPLOAD] Successfully updated DB for sanction_sheet: {docname}")
		else:
			print(f"[PO UPLOAD WARNING] The specified sanction_sheet docname '{docname}' does not exist. Cannot update file_path.")

		return {"status": True, "message": "File saved and path stored", "data": {"path": path, "file_url": full_minio_path}}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "PO Upload Error (Direct Purchase)")
		print(f"\n[PO UPLOAD FATAL ERROR] {str(e)}")
		print(frappe.get_traceback())
		return {"status": False, "message": str(e)}

@frappe.whitelist()
def get_po_document(docname, app_id, project_no):
	"""
	Endpoint to download the uploaded Purchase Order document directly from MinIO.
	"""
	from rndopsapp.minio import get_rnd_file_service

	try:
		# Resolve Project Registration docname from project_no field
		project_docname = frappe.db.get_value(
			"Project Registration", {"project_no": project_no}, "name"
		)
		if not project_docname:
			frappe.local.response.http_status_code = 404
			return {"status": False, "message": f"No Project Registration found for project_no: {project_no}"}

		folder_path = f"directpurchase/{app_id}/po"
		minio_prefix = f"Project_Registration/{project_docname}/{folder_path}/"

		file_service = get_rnd_file_service()

		# Search MinIO directly — upload_po_document skips creating a Frappe File doc
		objects = file_service.storage.list_prefix(minio_prefix)

		if not objects:
			frappe.local.response.http_status_code = 404
			return {"status": False, "message": "No PO document found for this direct purchase."}

		# Take the most recently modified object
		latest = sorted(objects, key=lambda o: o.last_modified, reverse=True)[0]
		object_name = latest.object_name
		filename = object_name.split("/")[-1]

		# Fetch file bytes from MinIO
		content = file_service.storage.get(object_name)

		if content is None:
			frappe.local.response.http_status_code = 404
			return {"status": False, "message": "File not found in storage."}

		# Serve the bytes as a downloadable file
		frappe.local.response.filename = filename
		frappe.local.response.filecontent = content
		frappe.local.response.type = "download"

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "PO Download Error (Direct Purchase)")
		if hasattr(frappe.local, "response"):
			frappe.local.response.http_status_code = 500
		return {"status": False, "message": str(e)}
