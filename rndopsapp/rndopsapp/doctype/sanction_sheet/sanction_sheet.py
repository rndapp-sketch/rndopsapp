# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json
import frappe
from frappe import _
from frappe.model.document import Document

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

class sanction_sheet(Document):
	def validate(self):
		pass

# =============================================================================
# API ENDPOINTS for Sanction Sheet
# =============================================================================

@frappe.whitelist()
def get_sanction_sheet_fields(doc_name=None):
	"""
	API to return Sanction Sheet field metadata, prefill data, and client scripts.
	"""
	meta = frappe.get_meta("sanction_sheet")
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

		# Handle Child Tables
		if f.fieldtype == "Table" and f.options:
			try:
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
			except Exception:
				pass

		fields.append(field_data)

	prefill_data = {}
	link_options = {}

	if doc_name:
		try:
			doc = frappe.get_doc("sanction_sheet", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass

	# Fetch Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all("Client Script", filters={"dt": "sanction_sheet", "enabled": 1}, fields=["name", "script", "view"])
		for script in scripts:
			client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
	except Exception:
		pass

	return {
		"fields": fields,
		"prefill_data": prefill_data,
		"link_options": link_options,
		"client_scripts": client_scripts,
	}

@frappe.whitelist()
def save_sanction_sheet_data(data):
	"""
	Creates or updates a Sanction Sheet document.
	"""
	from frappe.utils.file_manager import save_file

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new = False

		if doc_name and frappe.db.exists("sanction_sheet", doc_name):
			doc = frappe.get_doc("sanction_sheet", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc = frappe.new_doc("sanction_sheet")
			is_new = True

		meta = frappe.get_meta("sanction_sheet")
		file_fields = []

		for fieldname, value in data.items():
			if fieldname in ["name", "doctype", "docstatus"]:
				continue
			if not meta.has_field(fieldname):
				continue

			df = meta.get_field(fieldname)

			if df.fieldtype in ["Attach", "Attach Image", "Table"]:
				file_fields.append((fieldname, value))
			else:
				if value not in [None, ""]:
					doc.set(fieldname, value)

		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)
		else:
			doc.save(ignore_permissions=True)

		# Handle Tables & Files
		for fieldname, value in file_fields:
			df = meta.get_field(fieldname)
			if df.fieldtype == "Table" and isinstance(value, list):
				doc.set(fieldname, [])
				child_meta = frappe.get_meta(df.options)
				for child_row in value:
					row_dict = child_row.copy()
					for cf in child_meta.fields:
						if cf.fieldtype in ["Attach", "Attach Image"] and row_dict.get(cf.fieldname):
							f_val = row_dict[cf.fieldname]
							if isinstance(f_val, dict) and f_val.get("file_data"):
								try:
									saved_file = save_file(
										f_val.get("file_name", "attachment"),
										f_val["file_data"],
										"sanction_sheet",
										doc.name,
										decode=True,
										is_private=1,
										df=cf.fieldname
									)
									row_dict[cf.fieldname] = saved_file.file_url
								except Exception as e:
									frappe.log_error(f"Child File Error: {e}")
					doc.append(fieldname, row_dict)
			elif df.fieldtype in ["Attach", "Attach Image"]:
				if isinstance(value, dict) and value.get("file_data"):
					try:
						saved_file = save_file(
							value.get("file_name", "attachment"),
							value["file_data"],
							"sanction_sheet",
							doc.name,
							decode=True,
							is_private=1,
							df=fieldname
						)
						doc.set(fieldname, saved_file.file_url)
					except Exception:
						pass
				elif isinstance(value, str):
					doc.set(fieldname, value)

		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Sanction Sheet Save Error")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_sanction_sheet_workflow_actions(docname):
	doc = frappe.get_doc("sanction_sheet", docname)
	current_state = doc.workflow_state or "Draft"
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value("Workflow", {"document_type": "sanction_sheet", "is_active": 1}, "name")
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
def perform_sanction_sheet_action(docname, action):
	try:
		doc = frappe.get_doc("sanction_sheet", docname)
		current_state = doc.workflow_state or "Draft"
		user_roles = frappe.get_roles(frappe.session.user)

		workflow_name = frappe.db.get_value("Workflow", {"document_type": "sanction_sheet", "is_active": 1}, "name")
		if not workflow_name:
			frappe.throw("No active workflow found for Sanction Sheet.")

		workflow = frappe.get_doc("Workflow", workflow_name)
		next_state = None

		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]

				if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
					continue

				if t.condition:
					try:
						if not frappe.safe_eval(t.condition, None, {"doc": doc}):
							continue
					except Exception:
						continue

				next_state = t.next_state
				break

		if not next_state:
			frappe.throw(f"No valid transition found for action '{action}'.")

		doc.workflow_state = next_state
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
			doc.submit()
		elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
			doc.cancel()
		else:
			doc.save(ignore_permissions=True)

		frappe.db.commit()

		# Trigger direct purchase status update if Sanction Sheet reaches final approved state
		if next_state == "SancSheetApproved" and doc.amended_from:
			# Find the Direct Purchase document linked to the P_11 Form
			try:
				p11 = frappe.get_doc("P_11 Form", doc.amended_from)
				if p11.amended_from:
					frappe.db.set_value("Direct Purchase", p11.amended_from, "workflow_state", "SancSheetApproved")
					frappe.db.commit()
			except Exception:
				pass

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"next_actions": get_sanction_sheet_workflow_actions(docname)
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Sanction Sheet Action Error")
		return {"status": "error", "message": str(e)}
