# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document
from frappe.model.workflow import get_transitions
from rndopsapp.minio import get_rnd_file_service
from rndopsapp.rndopsapp.recruitment_api.recruitment_api import get_profile as _recruitment_get_profile


class SelectionCommitteeReport(Document):
	pass


def _format_address(addr):
	"""Format an address dict into a readable string."""
	parts = [
		addr.get("houseNum", ""),
		addr.get("streetName", ""),
		addr.get("locality", ""),
		addr.get("city", ""),
		addr.get("district", ""),
		addr.get("state", ""),
		addr.get("country", ""),
		addr.get("pincode", ""),
	]
	return ", ".join(p.strip() for p in parts if p and p.strip())


def _fetch_candidate_profile(candidate_id):
	"""Fetch candidate profile via recruitment_api. Returns the profile dict or None."""
	try:
		result = _recruitment_get_profile(candidate_id)
		if result.get("status") == "success":
			return result.get("data")
		frappe.log_error(f"get_profile returned error for ID {candidate_id}: {result.get('message')}", "Selection Candidate Details")
		return None
	except Exception as e:
		frappe.log_error(f"Failed to fetch candidate profile for ID {candidate_id}: {e}", "Selection Candidate Details")
		return None


def _create_selection_candidate_details(doc):
	"""
	For each candidate in the SCR's `candidates` JSON field, fetch the external
	profile and insert a Selection Candidate Details record.
	Called on Submit workflow action.
	"""
	candidates_raw = doc.get("candidates")
	if not candidates_raw:
		return

	if isinstance(candidates_raw, str):
		try:
			candidates = json.loads(candidates_raw)
		except Exception:
			frappe.log_error("Could not parse SCR candidates JSON", "Selection Candidate Details")
			return
	else:
		candidates = candidates_raw

	if not isinstance(candidates, list):
		return

	for candidate in candidates:
		candidate_id = candidate.get("candidate_id")
		if not candidate_id:
			continue

		# Only insert Recommended and Waiting List candidates
		if (candidate.get("recommendation") or "").strip().lower() not in ("recommended", "waiting list"):
			continue

		# Fetch external profile
		profile = _fetch_candidate_profile(candidate_id)

		# --- Build field values ---
		user_data = (profile or {}).get("user", {})
		cand_data = (profile or {}).get("candidate", {})
		addresses = (profile or {}).get("address", [])
		education = (profile or {}).get("education", [])
		employment = (profile or {}).get("employment", [])

		# Name: prefer profile API values, fall back to SCR candidate_name split
		first_name = (user_data.get("first_name") or "").strip()
		last_name = (user_data.get("last_name") or "").strip()
		if not first_name and not last_name:
			full_name_parts = (candidate.get("candidate_name") or "").strip().split(" ", 1)
			first_name = full_name_parts[0]
			last_name = full_name_parts[1] if len(full_name_parts) > 1 else ""

		# Addresses
		permanent_addr = ""
		correspondence_addr = ""
		for addr in addresses:
			addr_type = (addr.get("addrType") or "").lower()
			if addr_type == "permanent" and not permanent_addr:
				permanent_addr = _format_address(addr)
			elif addr_type == "correspondence" and not correspondence_addr:
				correspondence_addr = _format_address(addr)

		# Education & employment IDs (stored as comma-separated)
		edu_ids = ",".join(str(e["id"]) for e in education if e.get("id"))
		emp_ids = ",".join(str(e["id"]) for e in employment if e.get("id"))

		# HRA amount calculation from percentage string e.g. "20%"
		hra_str = str(candidate.get("hra") or "")
		basic_pay = candidate.get("basic_pay") or 0
		hra_amount = ""
		try:
			pct = float(hra_str.replace("%", "").strip())
			hra_amount = str(round(basic_pay * pct / 100))
		except Exception:
			hra_amount = hra_str

		# Date of birth: strip time component if present
		dob_raw = cand_data.get("date_of_birth") or ""
		dob = dob_raw.split("T")[0] if "T" in dob_raw else dob_raw

		# Skip if a record for this candidate+application already exists
		application_id = candidate.get("application_id")
		if frappe.db.exists(
			"Selection Candidate Details",
			{"candidate_id": int(candidate_id), "application_id": int(application_id or 0)},
		):
			continue

		new_doc = frappe.new_doc("Selection Candidate Details")
		new_doc.candidate_id = int(candidate_id)
		new_doc.interview_id = doc.name
		new_doc.application_id = int(application_id) if application_id else None
		new_doc.post_id = str(candidate.get("recruitment_post_id") or "")
		new_doc.selection_status = candidate.get("recommendation") or ""
		new_doc.wl_number = str(candidate.get("waitlist_no") or "")

		new_doc.candidate_name = first_name
		new_doc.candidate_surname = last_name
		new_doc.father_name = (cand_data.get("father_name") or "").strip()
		new_doc.gender = cand_data.get("gender") or ""
		new_doc.marital_status = cand_data.get("marital_status") or ""
		new_doc.date_of_birth = dob
		new_doc.citizenship = cand_data.get("citizenship") or ""

		new_doc.phone_num = cand_data.get("phone_number") or ""
		new_doc.email = user_data.get("email") or ""

		new_doc.permanent_address = permanent_addr
		new_doc.correspondence_address = correspondence_addr

		new_doc.educational_details_id = edu_ids
		new_doc.employment_details_id = emp_ids

		new_doc.basic_pay_recommended_by_committee = str(basic_pay)
		new_doc.hra_required_by_committee = hra_str
		new_doc.hra_amount_by_committee = hra_amount
		new_doc.medical_amount_by_committee = str(candidate.get("medical_required") or "")
		new_doc.total_amount_by_committee = str(candidate.get("total_amount") or "")
		new_doc.duration_of_appointment_by_committee = str(candidate.get("upfa_duration_months") or "")
		new_doc.justification_by_committee = candidate.get("justification") or ""

		new_doc.flags.ignore_permissions = True
		new_doc.insert()

	frappe.db.commit()


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
			limit_page_length=0,
		)
		link_options["upfa_department"] = departments
	except Exception:
		pass

	# amended_from → Selection Committee Report
	try:
		amended_docs = frappe.get_all(
			"Selection Committee Report",
			fields=["name as value", "name as label"],
			limit_page_length=0,
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
			limit_page_length=0,
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
	import base64

	if isinstance(data, str):
		data = json.loads(data)

	# Extract attendance_report file payload before field mapping.
	# Frontend sends it as {"file_data": "data:...;base64,...", "file_name": "..."}
	attendance_file = data.pop("attendance_report", None)
	if not isinstance(attendance_file, dict):
		# Already a stored URL string — put it back so the field mapper sets it normally
		if attendance_file:
			data["attendance_report"] = attendance_file
		attendance_file = None

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

		# Allow linking to cancelled documents (e.g. a cancelled Recruitment Adhoc
		# Contractual that the SCR was originally created against).
		doc.flags.ignore_links = True

		# Save
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		# --- Handle attendance_report file upload (base64 payload) ---
		if attendance_file:
			filename = attendance_file.get("file_name") or attendance_file.get("filename")
			content_b64 = attendance_file.get("file_data") or attendance_file.get("content") or ""

			if not filename or not content_b64:
				frappe.db.rollback()
				return {"status": "error", "message": "attendance_report: file_name and file_data are required"}

			if content_b64.startswith("data:"):
				content_b64 = content_b64.split(",", 1)[1]

			file_content = base64.b64decode(content_b64)

			project_id = doc.project_number or data.get("project_number")
			if not project_id:
				frappe.db.rollback()
				return {"status": "error", "message": "project_number is required to upload attendance_report"}

			file_service = get_rnd_file_service()
			upload_result = file_service.save_file(
				filename=filename,
				content=file_content,
				is_private=True,
				doctype="Project Registration",
				docname=project_id,
				folder="scr",
			)

			if not upload_result.get("status"):
				frappe.db.rollback()
				return {"status": "error", "message": f"MinIO upload failed: {upload_result.get('message')}"}

			doc.attendance_report = upload_result["data"]["file_url"]
			doc.flags.ignore_links = True
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

	# START MKY 2026-05-14 14:00 IST Hide Approve for Contractual in Pending Dean Approval
	if (doc.workflow_state or "") == "Pending Dean Approval" and (doc.get("recruitment_type") or "").strip().lower() != "adhoc":
		if "Approve" in actions:
			actions.remove("Approve")
	# END MKY

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

		# START MKY 2026-05-14 14:00 IST Prevent direct Dean approval for Contractual
		if action == "Approve" and (doc.workflow_state or "") == "Pending Dean Approval" and (doc.get("recruitment_type") or "").strip().lower() != "adhoc":
			frappe.throw("Contractual recruitment requires Director Approval. Use the Send for Director Approval action instead.")
		# END MKY

		# Director-PDF gate: SCR cannot be Approved
		# until Staff has uploaded the Director-signed scan (if flagged).
		# START MKY 2026-05-14 14:00 IST Update PDF gate state to Pending Director Approval
		if (
			action == "Approve"
			and (doc.workflow_state or "") == "Pending Director Approval"
			and not (doc.get("director_signed_pdf") or "").strip()
		):
			frappe.throw(
				"Cannot approve: the Director-signed PDF has not been uploaded "
				"by Staff yet."
			)
		# END MKY

		# apply_workflow handles transitions, permissions, and status updates
		updated_doc = apply_workflow(doc, action)
		print(f"apply_workflow completed. updated_doc state: {updated_doc.workflow_state}")

		frappe.db.commit()
		print("frappe.db.commit() successful")

		# On Submit: create Selection Candidate Details records from candidates JSON
		if action == "Approve":
			print("Action is Submit — creating Selection Candidate Details records")
			try:
				_create_selection_candidate_details(updated_doc)
				print("Selection Candidate Details records created successfully")
			except Exception as scd_exc:
				import traceback as _tb
				frappe.log_error(
					f"Failed to create Selection Candidate Details for {docname}: {scd_exc}\n{_tb.format_exc()}",
					"Selection Candidate Details",
				)
				print(f"Warning: Selection Candidate Details creation failed: {scd_exc}")

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


# ============================================================
# Director hardcopy / PDF flow (mirrors Recruitment Adhoc Contractual)
# Dean ticks "Send for Director Approval" on a Contractual SCR.
# Staff uploads the Director-signed scan via /director-pdf-upload.
# Dean's Approve action unlocks once director_signed_pdf is set.
# ============================================================

@frappe.whitelist()
def update_send_to_director_scr(docname, send_to_director):
	"""
	Dean opts the SCR into the Director-hardcopy flow. One-way (cannot clear).
	Restricted to "Dean, RnD" / "System Manager".
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if "Dean, RnD" not in user_roles and "System Manager" not in user_roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	doc = frappe.get_doc("Selection Committee Report", docname)
	if doc.docstatus != 0:
		frappe.throw("Cannot update Director Approval flag after document is submitted.")

	# START MKY 2026-05-14 13:45 IST Ensure it only applies to Contractual
	if (doc.get("recruitment_type") or "").strip().lower() == "adhoc":
		frappe.throw("Director Approval flow is only applicable for Contractual recruitment.")
	# END MKY

	if frappe.utils.cint(doc.get("send_to_director")):
		return {"status": "success", "docname": docname, "send_to_director": 1}

	if not frappe.utils.cint(send_to_director):
		frappe.throw("send_to_director can only be set, not cleared.")

	# START MKY 2026-05-14 13:35 IST Update workflow_state when send_to_director is set
	frappe.db.set_value(
		"Selection Committee Report", docname, {
			"send_to_director": 1,
			"workflow_state": "Pending Director Approval"
		}
	)
	# END MKY
	frappe.db.commit()
	return {"status": "success", "docname": docname, "send_to_director": 1}


@frappe.whitelist()
def attach_director_pdf_scr(docname, file_url):
	"""
	Staff binds an already-uploaded file URL to director_signed_pdf.
	Replacing an existing PDF is allowed.
	Restricted to "staff, RnD" / "System Manager".
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if "staff, RnD" not in user_roles and "System Manager" not in user_roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	if not file_url:
		frappe.throw("file_url is required")

	doc = frappe.get_doc("Selection Committee Report", docname)
	if doc.docstatus != 0:
		frappe.throw("Cannot attach Director signed PDF after document is submitted.")
	if not frappe.utils.cint(doc.get("send_to_director")):
		frappe.throw("This document is not flagged for Director approval.")

	frappe.db.set_value(
		"Selection Committee Report", docname, "director_signed_pdf", file_url
	)
	frappe.db.commit()
	return {
		"status": "success",
		"docname": docname,
		"director_signed_pdf": file_url,
	}


@frappe.whitelist()
def backfill_selection_candidate_details(dry_run=False):
	"""
	One-time backfill: for every submitted SCR that has candidates data,
	create missing Selection Candidate Details records.

	dry_run=True  → only report which SCRs/candidates would be processed,
	               nothing is inserted.

	Restricted to System Manager.
	Call via:
	  bench execute rndopsapp.rndopsapp.doctype.selection_committee_report.selection_committee_report.backfill_selection_candidate_details
	or the whitelisted API (System Manager only).
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if "System Manager" not in user_roles:
		frappe.throw("Not permitted", frappe.PermissionError)

	dry_run = bool(dry_run)

	# Fetch every SCR that has candidates data
	all_scr = frappe.get_all(
		"Selection Committee Report",
		filters=[["candidates", "is", "set"]],
		fields=["name", "workflow_state", "candidates"],
		limit_page_length=0,
	)

	results = []
	inserted_total = 0
	skipped_total = 0

	for scr_row in all_scr:
		docname = scr_row["name"]
		candidates_raw = scr_row.get("candidates") or ""
		if not candidates_raw:
			continue

		try:
			candidates = json.loads(candidates_raw) if isinstance(candidates_raw, str) else candidates_raw
		except Exception:
			results.append({"name": docname, "error": "Could not parse candidates JSON"})
			continue

		if not isinstance(candidates, list):
			continue

		doc_inserted = 0
		doc_skipped = 0

		for candidate in candidates:
			candidate_id = candidate.get("candidate_id")
			application_id = candidate.get("application_id")
			if not candidate_id:
				continue

			already_exists = frappe.db.exists(
				"Selection Candidate Details",
				{"candidate_id": int(candidate_id), "application_id": int(application_id or 0)},
			)
			if already_exists:
				doc_skipped += 1
				continue

			doc_inserted += 1
			if not dry_run:
				# Re-use the full creation logic by calling the helper with the full doc
				pass

		if doc_inserted > 0 and not dry_run:
			try:
				doc = frappe.get_doc("Selection Committee Report", docname)
				_create_selection_candidate_details(doc)
			except Exception as e:
				import traceback as _tb
				results.append({
					"name": docname,
					"error": str(e),
					"traceback": _tb.format_exc(),
				})
				continue

		inserted_total += doc_inserted
		skipped_total += doc_skipped
		results.append({
			"name": docname,
			"workflow_state": scr_row.get("workflow_state"),
			"candidates_count": len(candidates),
			"would_insert" if dry_run else "inserted": doc_inserted,
			"skipped_existing": doc_skipped,
		})

	return {
		"status": "success",
		"dry_run": dry_run,
		"scr_processed": len(results),
		"total_inserted": 0 if dry_run else inserted_total,
		"total_would_insert": inserted_total if dry_run else None,
		"total_skipped_existing": skipped_total,
		"details": results,
	}


@frappe.whitelist()
def get_pending_director_uploads_scr():
	"""
	Returns SCR docs that Dean has flagged for Director approval.
	Includes both pending uploads and already-uploaded docs (so Staff can
	replace if needed).
	"""
	docs = frappe.get_all(
		"Selection Committee Report",
		# START MKY 2026-05-14 13:35 IST Support the new Pending Director Approval state
		filters={
			"send_to_director": 1,
			"workflow_state": ["in", ["Pending Dean Approval", "Pending Director Approval"]],
			"docstatus": 0,
		},
		# END MKY
		fields=[
			"name",
			"interview_id",
			"principal_investigator",
			"project_number",
			"project_name",
			"upfa_department",
			"director_signed_pdf",
			"modified",
			"workflow_state",
		],
		order_by="modified desc",
	)
	return {"status": "success", "data": docs}
# ============================================================

