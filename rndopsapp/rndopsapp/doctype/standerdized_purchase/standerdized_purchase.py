# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


# =============================================================================
# HELPER
# =============================================================================

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


DOCTYPE = "standerdized_purchase"
DOCTYPE_LABEL = "Standardized Purchase"


# =============================================================================
# DOCUMENT CONTROLLER
# =============================================================================

class standerdized_purchase(Document):

	def validate(self):
		"""Server-side calculations: row amounts and grand total."""
		self.calculate_totals()

	def calculate_totals(self):
		"""Calculate row amounts for the items table and overall totals."""
		total_basic = 0
		for row in (self.get("details_of_items_to_be_purchased") or []):
			base = flt(row.icss_qty) * flt(row.icss_rate)
			discount = base * flt(row.icss_discount_percent) / 100
			gst = (base - discount) * flt(row.icss_gst_percent) / 100
			row.icss_amount = base - discount + gst
			total_basic += flt(row.icss_amount)

		self.sp_total_basic_value = total_basic
		self.sp_grand_total = (
			flt(self.sp_total_basic_value)
			+ flt(self.sp_pack_and_frwd)
			+ flt(self.sp_freight)
			+ flt(self.sp_other_charges)
		)


# =============================================================================
# API ENDPOINTS
# =============================================================================


@frappe.whitelist()
def get_standerdized_purchase_fields(doc_name=None):
	"""
	API to return Standardized Purchase field metadata, prefill data,
	link options, child table metadata, client scripts, and computation rules.

	Args:
		doc_name (str, optional): If provided, returns prefill data for editing.

	Returns:
		dict: ``fields``, ``prefill_data``, ``link_options``,
		      ``client_scripts``, ``computation_rules``.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	meta = frappe.get_meta(DOCTYPE)

	# ---- Field Metadata ----
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

		# Child Tables: include child field metadata
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
				if cf.fieldtype == "Link" and getattr(cf, "link_filters", None):
					cf_data["link_filters"] = cf.link_filters
				child_fields_list.append(cf_data)
			field_data["child_fields"] = child_fields_list

		fields.append(field_data)

	# ---- Prefill Data ----
	prefill_data = {}
	link_options = {}

	if doc_name:
		try:
			doc = frappe.get_doc(DOCTYPE, doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass

	# Declaration checkboxes default to unchecked
	prefill_data.setdefault("sp_dec_1", 0)
	prefill_data.setdefault("sp_dec_2", 0)
	prefill_data.setdefault("sp_dec_3", 0)

	# ---- Client Scripts ----
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": DOCTYPE, "enabled": 1},
			fields=["name", "script", "view"],
		)
		for script in scripts:
			client_scripts.append({
				"name": script.name,
				"script": script.script,
				"view": script.view,
			})
	except Exception:
		pass

	# ---- Computation Rules ----
	computation_rules = {
		"row_calculations": [
			{
				"table_fieldname": "details_of_items_to_be_purchased",
				"target_field": "icss_amount",
				"formula": "(icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100) + (((icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100)) * icss_gst_percent / 100)",
				"trigger_fields": ["icss_qty", "icss_rate", "icss_discount_percent", "icss_gst_percent"],
				"description": "Row amount = (Qty × Rate) - Discount% + GST%",
			}
		],
		"aggregations": [
			{
				"target_field": "sp_total_basic_value",
				"source_table": "details_of_items_to_be_purchased",
				"source_field": "icss_amount",
				"operation": "sum",
				"description": "Total basic value = sum of all item amounts",
			}
		],
		"computed_fields": [
			{
				"target_field": "sp_grand_total",
				"formula": "sp_total_basic_value + sp_pack_and_frwd + sp_freight + sp_other_charges",
				"trigger_fields": [
					"sp_total_basic_value",
					"sp_pack_and_frwd",
					"sp_freight",
					"sp_other_charges",
				],
				"description": "Grand total = Basic Value + Packing + Freight + Other Charges",
			},
		],
	}

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
		"computation_rules": computation_rules,
	}


# ---------------------------------------------------------------------------
# SAVE DATA
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_standerdized_purchase_data(data):
	"""
	Creates or updates a Standardized Purchase document.
	Handles child tables (``details_of_items_to_be_purchased``)
	and file uploads (Attach fields).

	Args:
		data (str | dict): JSON payload with document field values.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	from frappe.utils.file_manager import save_file

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new = False

		# 1. Initialize Document
		if doc_name and frappe.db.exists(DOCTYPE, doc_name):
			doc = frappe.get_doc(DOCTYPE, doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc(DOCTYPE)
			is_new = True

		meta = frappe.get_meta(DOCTYPE)

		# 2. First Pass: Set standard fields (skip files and tables)
		deferred_fields = []

		for fieldname, value in data.items():
			if fieldname in ("name", "doctype", "docstatus"):
				continue
			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)

			if df.fieldtype in ("Attach", "Attach Image"):
				deferred_fields.append((fieldname, value))
			elif df.fieldtype == "Table":
				deferred_fields.append((fieldname, value))
			else:
				if value not in (None, ""):
					doc.set(fieldname, value)

		# 3. Create / Initial Save to get Name
		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)
		else:
			doc.save(ignore_permissions=True)

		# 4. Second Pass: Process Files and Child Tables
		for fieldname, value in deferred_fields:
			df = meta.get_field(fieldname)

			if df.fieldtype == "Table":
				rows = value if isinstance(value, list) else []
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)

				for child_row in rows:
					row_dict = dict(child_row or {})

					for cf in child_meta.fields:
						if cf.fieldtype in ("Attach", "Attach Image") and row_dict.get(cf.fieldname):
							f_val = row_dict[cf.fieldname]
							if isinstance(f_val, dict) and f_val.get("file_data"):
								try:
									saved_file = save_file(
										f_val.get("file_name", "attachment"),
										f_val["file_data"],
										DOCTYPE,
										doc.name,
										decode=True,
										is_private=1,
										df=cf.fieldname,
									)
									row_dict[cf.fieldname] = saved_file.file_url
								except Exception as e:
									frappe.log_error(
										f"SP Child File Error ({cf.fieldname}): {e}",
										"Standardized Purchase Save Error",
									)

					doc.append(fieldname, row_dict)

			elif df.fieldtype in ("Attach", "Attach Image"):
				if isinstance(value, dict) and value.get("file_data"):
					try:
						saved_file = save_file(
							value.get("file_name", "attachment"),
							value["file_data"],
							DOCTYPE,
							doc.name,
							decode=True,
							is_private=1,
							df=fieldname,
						)
						doc.set(fieldname, saved_file.file_url)
					except Exception as e:
						frappe.log_error(
							f"SP File Upload Error ({fieldname}): {str(e)}",
							"Standardized Purchase Save Error",
						)
				elif isinstance(value, str):
					doc.set(fieldname, value)

		# 5. Final Save
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Standardized Purchase Save Error")
		frappe.throw(_("Failed to save Standardized Purchase: {0}").format(str(e)))


# ---------------------------------------------------------------------------
# WORKFLOW ACTIONS
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_standerdized_purchase_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.

	Args:
		docname (str): Name of the Standardized Purchase document.

	Returns:
		list[str]: Available action names (de-duplicated).

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	doc = frappe.get_doc(DOCTYPE, docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow",
		{"document_type": DOCTYPE, "is_active": 1},
		"name",
	)

	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue

		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]

		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			if transition.condition:
				try:
					if not frappe.safe_eval(transition.condition, None, {"doc": doc}):
						continue
				except Exception:
					continue

			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


@frappe.whitelist()
def perform_standerdized_purchase_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.

	Args:
		docname (str): Name of the Standardized Purchase document.
		action  (str): Workflow action to perform.

	Returns:
		dict: ``{"status": "success", "workflow_state": "...", ...}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		doc = frappe.get_doc(DOCTYPE, docname)
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)

		workflow_name = frappe.db.get_value(
			"Workflow",
			{"document_type": DOCTYPE, "is_active": 1},
			"name",
		)

		if not workflow_name:
			frappe.throw(_("No active workflow found for {0}.").format(DOCTYPE_LABEL))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]

				if not (
					any(role in user_roles for role in allowed_roles)
					or "System Manager" in user_roles
				):
					continue

				if t.condition:
					try:
						if not frappe.safe_eval(t.condition, None, {"doc": doc}):
							continue
					except Exception as e:
						frappe.log_error(
							f"SP Workflow condition error: {str(e)}",
							"Standardized Purchase Workflow Error",
						)
						continue

				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(
				_("No valid transition found for action '{0}' from state "
				  "'{1}' matching your role and conditions.").format(action, current_state)
			)

		doc.workflow_state = next_state

		state_doc = next(
			(s for s in workflow.states if s.state == next_state), None
		)

		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_standerdized_purchase_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Standardized Purchase Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_standerdized_purchase(docname):
	"""
	Submit a Standardized Purchase document using Workflow transitions.

	Args:
		docname (str): Name of the document to submit.

	Returns:
		dict: Result from ``perform_standerdized_purchase_action``.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	return perform_standerdized_purchase_action(docname, "Submit")
