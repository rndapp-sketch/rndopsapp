# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
import requests

RECRUITMENT_BASE_URL = "https://iitg.ac.in/rndproj/recruitment/api"


def _get(path, timeout=15):
	"""Internal helper: GET from the external recruitment API."""
	url = f"{RECRUITMENT_BASE_URL}{path}"
	response = requests.get(url, timeout=timeout)
	response.raise_for_status()
	return response.json()


@frappe.whitelist(allow_guest=False)
def get_profile(candidate_id):
	"""
	Fetch a candidate's full profile from the external recruitment API.
	GET /api/candidates/{candidate_id}/profile
	"""
	try:
		data = _get(f"/candidates/{candidate_id}/profile")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"get_profile failed for candidate_id={candidate_id}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_applications(refNumParent):
	"""
	Fetch applications for a given recruitment reference number.
	GET /api/applications?refNumParent={refNumParent}
	"""
	try:
		data = _get(f"/applications?refNumParent={refNumParent}")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"get_applications failed for refNumParent={refNumParent}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def review_application(application_id):
	"""
	Fetch review details for a specific application.
	GET /api/applications/{application_id}/review
	"""
	try:
		data = _get(f"/applications/{application_id}/review")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"review_application failed for application_id={application_id}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_document(doc_id):
	"""
	Fetch metadata for a candidate document.
	GET /api/documents/{doc_id}
	"""
	try:
		data = _get(f"/documents/{doc_id}")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"get_document failed for doc_id={doc_id}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def view_document(doc_id):
	"""
	Fetch a viewable/download URL for a candidate document.
	GET /api/documents/{doc_id}/view
	"""
	try:
		data = _get(f"/documents/{doc_id}/view")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"view_document failed for doc_id={doc_id}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def get_post(post_id):
	"""
	Fetch details of a recruitment post.
	GET /api/posts/{post_id}
	"""
	try:
		data = _get(f"/posts/{post_id}")
		return {"status": "success", "data": data}
	except Exception as e:
		frappe.log_error(f"get_post failed for post_id={post_id}: {e}", "Recruitment API")
		return {"status": "error", "message": str(e)}
