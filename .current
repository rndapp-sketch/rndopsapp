# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.model.workflow import get_transitions


class SelectionCommitteeReport(Document):
	pass


@frappe.whitelist()
def get_selection_committee_report_fields(doc_name=None):
	"""
	Returns field metadata, prefill data, and link options for the
	Selection Committee Report form (follows APPS_DOCUMENTATION.md pattern).
	"""

	# 1. Fetch Metadata
	meta = frappe.get_meta("Selection Committee Report")
	fields = []
	for f in meta.fields:
		depends_on = getattr(f, "depends_on", None) or ""
		mandatory_depends_on = getattr(f, "mandatory_depends_on", None) or ""
		read_only_depends_on = getattr(f, "read_only_depends_on", None) or ""

		field_data = {
			"fieldname": f.fieldname,
			"label": f.label,
			"fieldtype": f.fieldtype,
			"options": getattr(f, "options", None),
			"mandatory": f.reqd,
			"read_only": f.read_only,
			"hidden": getattr(f, "hidden", 0),
			"description": getattr(f, "description", "") or "",
			"default": getattr(f, "default", None),
			"in_list_view": getattr(f, "in_list_view", 0),
			# Conditional logic for frontend
			"depends_on": depends_on,
			"depends_on_eval": depends_on.replace("eval:", "").strip()
			if depends_on.startswith("eval:")
			else None,
			"mandatory_depends_on": mandatory_depends_on,
			"mandatory_depends_on_eval": mandatory_depends_on.replace("eval:", "").strip()
			if mandatory_depends_on.startswith("eval:")
			else None,
			"read_only_depends_on": read_only_depends_on,
			"read_only_depends_on_eval": read_only_depends_on.replace("eval:", "").strip()
			if read_only_depends_on.startswith("eval:")
			else None,
		}

		# Handle Child Tables: fetch child fields metadata
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				field_data["child_fields"] = [
					{
						"fieldname": cf.fieldname,
						"label": cf.label,
						"fieldtype": cf.fieldtype,
						"options": getattr(cf, "options", None),
						"mandatory": cf.reqd,
						"hidden": getattr(cf, "hidden", 0),
						"read_only": cf.read_only,
						"in_list_view": getattr(cf, "in_list_view", 0),
						"depends_on": getattr(cf, "depends_on", None),
					}
					for cf in child_meta.fields
				]
			except Exception:
				pass

		fields.append(field_data)

	# 2. Prepare Containers
	prefill_data = {}
	link_options = {}

	# 3. Fetch Data (if doc_name provided) or set new-doc defaults
	if doc_name:
		try:
			doc = frappe.get_doc("Selection Committee Report", doc_name)
			prefill_data = doc.as_dict()
		except Exception:
			pass
	else:
		# New-doc defaults: auto-fill the logged-in user's info
		try:
			current_user = frappe.session.user
			if current_user and current_user not in ["Administrator", "Guest"]:
				prefill_data["webmail_id"] = current_user

				# Try fetching PI head/mentor from the User record
				user_doc = frappe.get_doc("User", current_user)
				head = getattr(user_doc, "piheadmentor_user_id", None)
				if head:
					prefill_data["head"] = head
		except Exception:
			pass

	# 4. Populate Link Options

	# webmail_id → User (enabled, non-guest)
	try:
		users = frappe.get_all(
			"User",
			filters={"enabled": 1, "user_type": "System User"},
			fields=["name as value", "full_name as label"],
			limit_page_length=0,
		)
		link_options["webmail_id"] = users
		link_options["chairperson_webmail_id"] = users
	except Exception:
		pass

	# upfa_department → Department_prornd
	try:
		departments = frappe.get_all(
			"Department_prornd",
			fields=["name as value", "name as label"],
			limit_page_length=200,
		)
		link_options["upfa_department"] = departments
	except Exception:
		pass

	# amended_from → Selection Committee Report
	try:
		amended_docs = frappe.get_all(
			"Selection Committee Report",
			fields=["name as value", "name as label"],
			limit_page_length=200,
		)
		link_options["amended_from"] = amended_docs
	except Exception:
		pass

	# Project options: fetch projects linked to current user (as PI)
	try:
		current_user = frappe.session.user
		projects = frappe.get_all(
			"Project Registration",
			filters={"pi_webmail_id": current_user},
			fields=[
				"name as value",
				"project_title as label",
				"project_title",
				"project_no",
				"department",
				"project_duration",
			],
			limit_page_length=200,
			order_by="modified desc",
		)
		link_options["project_registration"] = projects
	except Exception:
		pass

	# Child Table Link Options: fetch options for Link fields inside child tables
	for f in meta.fields:
		if f.fieldtype == "Table" and f.options:
			try:
				child_meta = frappe.get_meta(f.options)
				for cf in child_meta.fields:
					if cf.fieldtype == "Link" and cf.options:
						# Skip if already populated
						if cf.fieldname in link_options or cf.options in link_options:
							continue
						try:
							child_link_docs = frappe.get_all(
								cf.options,
								fields=["name as value", "name as label"],
								limit_page_length=0,
							)
							link_options[cf.fieldname] = child_link_docs
							link_options[cf.options] = child_link_docs
						except Exception:
							pass
			except Exception:
				pass

	# 5. Client Scripts
	client_scripts = []
	try:
		scripts = frappe.get_all(
			"Client Script",
			filters={"dt": "Selection Committee Report", "enabled": 1},
			fields=["name", "script", "view"],
		)
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
def save_selection_committee_report_data(data):
	if isinstance(data, str):
		data = json.loads(data)

	try:
		# Create or Get Doc
		if data.get("name"):
			doc = frappe.get_doc("Selection Committee Report", data.get("name"))
		else:
			doc = frappe.new_doc("Selection Committee Report")

		# Fetch meta to map fields properly
		meta = frappe.get_meta("Selection Committee Report")

		# Map Fields
		for f in meta.fields:
			if f.fieldtype != "Table" and f.fieldname in data:
				doc.set(f.fieldname, data[f.fieldname])

		if "workflow_state" in data:
			doc.set("workflow_state", data["workflow_state"])

		# Handle Child Tables
		for f in meta.fields:
			if f.fieldtype == "Table":
				items_data = data.get(f.fieldname, [])
				if items_data and isinstance(items_data, list):
					doc.set(f.fieldname, [])  # Clear existing
					for item in items_data:
						doc.append(f.fieldname, item)

		# Save
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		import traceback
		return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@frappe.whitelist()
def get_selection_committee_report_workflow_actions(docname):
	"""
	Get available workflow actions for the current user based on document state.
	"""
	doc = frappe.get_doc("Selection Committee Report", docname)
	transitions = get_transitions(doc)

	# Extract unique action names
	actions = list(dict.fromkeys([t.get("action") for t in transitions]))

	return actions


@frappe.whitelist()
def perform_selection_committee_report_action(docname, action):
	"""
	Perform a workflow action on the document.
	"""
	print(f"========== DEBUG: perform_selection_committee_report_action CALLED ==========")
	print(f"docname: {docname}, action: {action}")
	try:
		from frappe.model.workflow import apply_workflow
		print("Imported apply_workflow")

		doc = frappe.get_doc("Selection Committee Report", docname)
		print(f"Fetched doc: {doc.name}, current state: {doc.workflow_state}")

		# apply_workflow handles transitions, permissions, and status updates
		updated_doc = apply_workflow(doc, action)
		print(f"apply_workflow completed. updated_doc state: {updated_doc.workflow_state}")

		frappe.db.commit()
		print("frappe.db.commit() successful")

		new_state = updated_doc.workflow_state

		res = {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {new_state}",
			"docname": docname,
			"workflow_state": new_state,
			"next_actions": get_selection_committee_report_workflow_actions(docname),
		}
		print(f"Returning success: {res}")
		return res
	except Exception as e:
		frappe.db.rollback()
		import traceback
		print(f"========== DEBUG ERROR ==========")
		print(f"Exception: {str(e)}")
		print(traceback.format_exc())
		print(f"=================================")
		return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}


@frappe.whitelist()
def submit_selection_committee_report(docname):
	"""
	Submit a Selection Committee Report document using Workflow transitions.
	"""
	return perform_selection_committee_report_action(docname, "Submit")


@frappe.whitelist(allow_guest=True)
def get_selection_committee_report_by_webmail(pi_mail=None, project_no=None, webmail_id=None):
	"""
	Get all Selection Committee Report documents for a specific PI mail and project_no.
	"""
	# Handle legacy parameter if passed by frontend
	if webmail_id and not pi_mail:
		pi_mail = webmail_id

	try:
		filters = {}
		if pi_mail:
			filters["webmail_id"] = pi_mail
		if project_no:
			filters["upfa_project_code"] = project_no

		doc_names = frappe.get_all("Selection Committee Report", filters=filters, pluck="name")

		docs = [frappe.get_doc("Selection Committee Report", name).as_dict() for name in doc_names]

		return {"status": "success", "data": docs}
	except Exception as e:
		return {"status": "error", "message": str(e)}

