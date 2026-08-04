# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.model.document import Document
from frappe.model.workflow import get_transitions

class RecruitmentAdhocContractual(Document):
	pass


@frappe.whitelist()
def get_recruitment_adhoc_contractual_fields(doc_name=None):
    """
    Returns field metadata, prefill data, and link options for the
    Recruitment Adhoc Contractual form (follows APPS_DOCUMENTATION.md pattern).
    """

    # 1. Fetch Metadata
    meta = frappe.get_meta("Recruitment Adhoc Contractual")
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
            "depends_on_eval": depends_on.replace("eval:", "").strip() if depends_on.startswith("eval:") else None,
            "mandatory_depends_on": mandatory_depends_on,
            "mandatory_depends_on_eval": mandatory_depends_on.replace("eval:", "").strip() if mandatory_depends_on.startswith("eval:") else None,
            "read_only_depends_on": read_only_depends_on,
            "read_only_depends_on_eval": read_only_depends_on.replace("eval:", "").strip() if read_only_depends_on.startswith("eval:") else None,
        }

        # Handle Child Tables: fetch child fields metadata
        if f.fieldtype == "Table" and f.options:
            try:
                child_meta = frappe.get_meta(f.options)
                field_data["child_fields"] = [{
                    "fieldname": cf.fieldname,
                    "label": cf.label,
                    "fieldtype": cf.fieldtype,
                    "options": getattr(cf, "options", None),
                    "mandatory": cf.reqd,
                    "hidden": getattr(cf, "hidden", 0),
                    "read_only": cf.read_only,
                    "in_list_view": getattr(cf, "in_list_view", 0),
                    "depends_on": getattr(cf, "depends_on", None),
                } for cf in child_meta.fields]
            except Exception:
                pass

        fields.append(field_data)

    # 2. Prepare Containers
    prefill_data = {}
    link_options = {}

    # 3. Fetch Data (if doc_name provided) or set new-doc defaults
    if doc_name:
        try:
            doc = frappe.get_doc("Recruitment Adhoc Contractual", doc_name)
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

    # amended_from → Recruitment Adhoc Contractual
    try:
        amended_docs = frappe.get_all(
            "Recruitment Adhoc Contractual",
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

    # 5. Client Scripts
    client_scripts = []
    try:
        scripts = frappe.get_all(
            "Client Script",
            filters={"dt": "Recruitment Adhoc Contractual", "enabled": 1},
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
def save_recruitment_adhoc_contractual_data(data):
    if isinstance(data, str):
        data = json.loads(data)

    try:
        # Create or Get Doc
        if data.get("name"):
            doc = frappe.get_doc("Recruitment Adhoc Contractual", data.get("name"))
        else:
            doc = frappe.new_doc("Recruitment Adhoc Contractual")

        # Fetch meta to map fields properly
        meta = frappe.get_meta("Recruitment Adhoc Contractual")

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
                    doc.set(f.fieldname, []) # Clear existing
                    for item in items_data:
                        doc.append(f.fieldname, item)

        # Save
        doc.save(ignore_permissions=True)

        # fetch_from fields (e.g. `head`) are overwritten by Frappe's ORM during save,
        # so persist the frontend-supplied value directly after save
        if "head" in data and data["head"]:
            frappe.db.set_value("Recruitment Adhoc Contractual", doc.name, "head", data["head"])

        # Resolve chairperson_name from chairperson_webmail_id (User lookup)
        # Priority: explicit email in payload → fallback to project head_approver
        chairperson_email = data.get("chairperson_webmail_id")
        if not chairperson_email:
            upfa_project_code = data.get("upfa_project_code")
            if upfa_project_code:
                project = frappe.db.get_value(
                    "Project Registration",
                    {"project_no": upfa_project_code},
                    ["head_approver"],
                    as_dict=True,
                )
                if project and project.get("head_approver"):
                    chairperson_email = project["head_approver"]

        if chairperson_email:
            user = frappe.db.get_value(
                "User",
                chairperson_email,
                ["first_name", "middle_name", "last_name"],
                as_dict=True,
            )
            if user:
                name_parts = [
                    (user.get("first_name") or "").strip(),
                    (user.get("middle_name") or "").strip(),
                    (user.get("last_name") or "").strip(),
                ]
                chairperson_name = " ".join(part for part in name_parts if part)
                frappe.db.set_value(
                    "Recruitment Adhoc Contractual",
                    doc.name,
                    {
                        "chairperson_webmail_id": chairperson_email,
                        "chairperson_name": chairperson_name,
                    },
                )

        frappe.db.commit()
        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_recruitment_adhoc_contractual_workflow_actions(docname):
    """
    Get available workflow actions for the current user based on document state.
    Utilizes standard Frappe workflow transition logic to ensure conditions and roles
    are handled consistently with the desk view.
    """


    doc = frappe.get_doc("Recruitment Adhoc Contractual", docname)
    transitions = get_transitions(doc)

    # Extract unique action names
    actions = list(dict.fromkeys([t.get("action") for t in transitions]))

    return actions


@frappe.whitelist()
def perform_recruitment_adhoc_contractual_action(docname, action):
    print("------=-==-=-=-=-=-=-=-=-=-=-=-RAC-=-=-=-=-=-=-=-=-=-=-=-")
    """
    Executes the selected workflow action and updates the document state.
    """
    print(f"\n--- [START] perform_recruitment_adhoc_contractual_action ---")
    print(f"Docname: {docname} | Action requested: {action}")

    try:
        doc = frappe.get_doc("Recruitment Adhoc Contractual", docname)
        current_state = doc.workflow_state or "Draft"
        user_roles = frappe.get_roles(frappe.session.user)

        print(f"Current State: '{current_state}' | User: {frappe.session.user}")
        print(f"User Roles: {user_roles}")

        workflow_name = frappe.db.get_value(
            "Workflow",
            {"document_type": "Recruitment Adhoc Contractual", "is_active": 1},
            "name"
        )

        print(f"Active Workflow Found: {workflow_name}")

        if not workflow_name:
            print("[ERROR] No active workflow found for Recruitment Adhoc Contractual.")
            frappe.throw("No active workflow found for Recruitment Adhoc Contractual.")

        workflow = frappe.get_doc("Workflow", workflow_name)

        next_state = None
        transition = None

        print("Iterating over workflow transitions...")
        for t in workflow.transitions:
            print(f"  Checking Transition -> State: '{t.state}', Action: '{t.action}'")

            if t.state == current_state and t.action == action:
                print(f"    [MATCH] State & Action match found!")

                allowed_roles = t.get("allowed") or []
                if isinstance(allowed_roles, str):
                    allowed_roles = [allowed_roles]

                print(f"    Allowed roles for transition: {allowed_roles}")

                if not (any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles):
                    print(f"    [FAIL] Role check failed.")
                    continue
                else:
                    print("    [PASS] Role check passed.")

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
                        continue

                next_state = t.next_state
                transition = t
                print(f"    [SUCCESS] Transition approved! Next state will be: '{next_state}'")
                break

        if not next_state:
            error_msg = f"No valid transition found for action '{action}' from state '{current_state}' matching your role and conditions."
            print(f"[ERROR] {error_msg}")
            frappe.throw(error_msg)

        doc.workflow_state = next_state
        state_doc = next((s for s in workflow.states if s.state == next_state), None)

        if state_doc:
            print(f"Target state doc_status: {state_doc.doc_status} (Current docstatus: {doc.docstatus})")

        # ============================================================
        # EDITED BY OJS | 2026-04-23 18:21 IST
        # START OF EDIT — Fix incorrect doc.cancel() on submitted workflow transitions
        # Root cause: all workflow states (except Draft) have doc_status=1. When a
        # submitted doc (docstatus=1) transitions to another doc_status=1 state, the
        # old elif branch incorrectly called doc.cancel() (docstatus=2).
        # Fix: only submit when going Draft→Submitted (docstatus 0→1).
        #      only cancel when the target state explicitly requires docstatus=2
        #      AND the current doc is still submitted (not already cancelled).
        #      All other transitions (submitted→submitted) safely use db.set_value.
        # ============================================================
        if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
            print("[ACTION] Submitting document (Draft → Submitted)...")
            doc.submit()
        elif state_doc and state_doc.doc_status == "2" and doc.docstatus == 1:
            # Only cancel if the workflow explicitly targets a Cancelled state
            # (doc_status=2) and the doc is currently submitted.
            print("[ACTION] Cancelling document (Submitted → Cancelled by workflow)...")
            doc.cancel()
        else:
            # Handles: submitted→submitted state transitions and any fallthrough.
            # Safest path — update only workflow_state, no docstatus change.
            print("[ACTION] Updating workflow_state via db.set_value...")
            frappe.db.set_value("Recruitment Adhoc Contractual", docname, "workflow_state", next_state)

            # Since db.set_value does NOT trigger on_update hooks,
            # manually call the Kafka publishing hook if state is now 'Approved'
            if next_state == "Approved":
                print("[KAFKA] State is 'Approved' — manually triggering check_workflow_and_publish...")
                from rndopsapp.rndopsapp.commitPayment import check_workflow_and_publish
                # Reload the doc so it reflects the updated workflow_state
                doc.reload()
                check_workflow_and_publish(doc)
        # END OF EDIT — OJS | 2026-04-23 18:21 IST
        # ============================================================

        frappe.db.commit()
        print(f"--- [END] perform_recruitment_adhoc_contractual_action SUCCESS ---\n")

        return {
            "status": "success",
            "message": f"Action '{action}' completed. New State: {next_state}",
            "docname": docname,
            "workflow_state": next_state,
            "next_actions": get_recruitment_adhoc_contractual_workflow_actions(docname)
        }

    except Exception as e:
        frappe.db.rollback()
        print(f"\n--- [EXCEPTION] perform_recruitment_adhoc_contractual_action ---")
        print(f"Error: {str(e)}")
        frappe.log_error(frappe.get_traceback(), f"Workflow Action Failed: {action} on {docname}")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_recruitment_adhoc_contractual(docname):
    """
    Submit a Recruitment Adhoc Contractual document using Workflow transitions.
    """
    return perform_recruitment_adhoc_contractual_action(docname, "Submit")


# ============================================================
# EDITED BY OJS | 2026-05-05 12:28 IST
# START OF EDIT — Add status parameter to filter by workflow_state
# ============================================================
@frappe.whitelist(allow_guest=True)
def get_recruitment_adhoc_contractual_by_webmail(pi_mail=None, project_no=None, webmail_id=None, status=None):
	"""
	Get all Recruitment Adhoc Contractual documents for a specific PI mail and project_no.
	"""
	return get_recruitment_adhoc_contractual_with_project_info(
		pi_mail=pi_mail,
		project_no=project_no,
		webmail_id=webmail_id,
		status=status,
	)
# END OF EDIT — OJS | 2026-05-05 12:28 IST
# ============================================================

# ============================================================
# EDITED BY OJS | 2026-05-05 12:31 IST
# START OF EDIT — Add get_recruitment_adhoc_contractual_with_project_info endpoint
# ============================================================
@frappe.whitelist(allow_guest=True)
def get_recruitment_adhoc_contractual_with_project_info(pi_mail=None, project_no=None, webmail_id=None, status=None):
	"""
	Same response as get_recruitment_adhoc_contractual_by_webmail, but each
	document is enriched with a `project_info` block containing the
	department name, PI name and funding agency name resolved via
	upfa_project_code -> Project Registration.project_no.

	Optional filter:
		status -> matches against workflow_state (e.g. "Approved").
	"""
	if webmail_id and not pi_mail:
		pi_mail = webmail_id

	try:
		filters = {}
		if pi_mail:
			filters["webmail_id"] = pi_mail
		if project_no:
			filters["upfa_project_code"] = project_no
		if status:
			status_clean = status.strip('"').strip("'").title()
			filters["workflow_state"] = status_clean

		doc_names = frappe.get_all(
			"Recruitment Adhoc Contractual",
			filters=filters,
			pluck="name",
		)

		project_cache = {}

		def resolve_project_info(project_code):
			if not project_code:
				return {
					"department_name": None,
					"pi_name": None,
					"funding_agency_name": None,
				}
			if project_code in project_cache:
				return project_cache[project_code]

			info = {
				"department_name": None,
				"pi_name": None,
				"funding_agency_name": None,
			}

			project = frappe.db.get_value(
				"Project Registration",
				{"project_no": project_code},
				["implementation_department", "principal_investigator_name", "funding_agen"],
				as_dict=True,
			)
			if project:
				info["pi_name"] = project.get("principal_investigator_name")

				if project.get("implementation_department"):
					info["department_name"] = frappe.db.get_value(
						"Department_prornd",
						project["implementation_department"],
						"dept_name",
					)

				if project.get("funding_agen"):
					info["funding_agency_name"] = frappe.db.get_value(
						"fundingagency_",
						project["funding_agen"],
						"funding_agency_name",
					)

			project_cache[project_code] = info
			return info

		PARENT_FIELDS = [
			"name",
			"owner",
			"creation",
			"workflow_state",
			"upfa_appointment_type",
			"webmail_id",
			"upfa_project_title",
			"upfa_project_code",
			"upfa_project_duration",
			"upfa_interview_date",
			"upfa_interview_time",
			"mode_of_interview",
			"upfa_interview_venue",
			"upfa_pi_contact",
			"last_date_of_appllication",
			"walk_in",
			"upfa_declaration_advertisement",
			"doctype",
			"upfa_selection_committee",
		]

		POST_DETAIL_FIELDS = [
			"name",
			"upfa_designation",
			"upfa_vacancies",
			"upfa_basic_pay",
			"upfa_hra_percent",
			"upfa_medical_required",
			"upfa_total_amount",
			"month_days",
			"upfa_duration_months",
			"upfa_qualification",
			"upfa_justification",
			"parent",
			"parenttype",
		]

		docs = []
		for name in doc_names:
			full = frappe.get_doc("Recruitment Adhoc Contractual", name).as_dict()
			doc_dict = {k: full.get(k) for k in PARENT_FIELDS}
			doc_dict["upfa_post_details"] = [
				{k: row.get(k) for k in POST_DETAIL_FIELDS}
				for row in (full.get("upfa_post_details") or [])
			]
			doc_dict["project_info"] = resolve_project_info(full.get("upfa_project_code"))
			docs.append(doc_dict)

		return {"status": "success", "data": docs}
	except Exception as e:
		return {"status": "error", "message": str(e)}
# END OF EDIT — OJS | 2026-05-05 12:31 IST
# ============================================================


# ============================================================
# EDITED BY OJS | 2026-04-14 12:23 IST
# START OF EDIT — Dynamic Designation Fetching via designation_type
# Replaced complex EmployeeClass→User→Designation chain with a
# direct filter on Designation_prornd.designation_type field.
# Added get_filtered_designations() for dynamic frontend calls.
# ============================================================

@frappe.whitelist(allow_guest=True)
def get_project_staff_designations():
	"""
	Returns a list of designations where designation_type = "Project Staff"
	directly from Designation_prornd doctype.
	"Other" is always appended at the end for custom user input.
	"""
	return get_filtered_designations(designation_type="Project Staff")


@frappe.whitelist(allow_guest=True)
def get_filtered_designations(designation_type=None):
	"""
	Returns designations from Designation_prornd filtered by designation_type.
	If designation_type is not provided, returns all designations.
	"Other" is always appended at the end to allow custom user input.

	Args:
		designation_type (str, optional): e.g. "Project Staff", "Permanent Staff", "Others"

	Returns:
		dict: {"status": "success", "data": [{"value": ..., "label": ...}, ...]}
	"""
	try:
		filters = {}
		if designation_type:
			filters["designation_type"] = designation_type

		designations = frappe.get_all(
			"Designation_prornd",
			filters=filters,
			fields=["name as value", "designation_prornd as label"],
			order_by="designation_prornd asc",
			limit=0,
		)

		data = [
			{"value": item["value"], "label": item.get("label") or item["value"]}
			for item in designations
		]

		# ============================================================
		# EDITED BY OJS | 2026-04-14 15:35 IST
		# START OF EDIT — Quick Entry Prepend
		# Replaced "Other" appended at the end with "CREATE_NEW" prepended at the top.
		# ============================================================
		data.insert(0, {
			"value": "CREATE_NEW",
			"label": "➕ Create New Designation..."
		})
		# END OF EDIT — OJS | 2026-04-14 15:35 IST
		# ============================================================

		return {"status": "success", "data": data}

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Error in get_filtered_designations")
		return {"status": "error", "message": str(e)}

@frappe.whitelist()
def update_chairperson_fields(docname, chairperson_webmail_id, chairperson_name):
    """
    Directly updates chairperson_webmail_id and chairperson_name on a
    Recruitment Adhoc Contractual document.
    Restricted to users with the 'Dean, RnD' role.
    """
    print(f"[update_chairperson_fields] Called by: {frappe.session.user}")
    print(f"[update_chairperson_fields] docname={docname}, email={chairperson_webmail_id}, name={chairperson_name}")

    user_roles = frappe.get_roles(frappe.session.user)
    print(f"[update_chairperson_fields] User roles: {user_roles}")

    if "Dean, RnD" not in user_roles:
        print(f"[update_chairperson_fields] Permission denied for user: {frappe.session.user}")
        frappe.throw("Not permitted", frappe.PermissionError)

    try:
        # Derive chairperson_name from User if not explicitly provided
        if not chairperson_name:
            user = frappe.db.get_value(
                "User",
                chairperson_webmail_id,
                ["first_name", "middle_name", "last_name"],
                as_dict=True,
            )
            if user:
                name_parts = [
                    (user.get("first_name") or "").strip(),
                    (user.get("middle_name") or "").strip(),
                    (user.get("last_name") or "").strip(),
                ]
                chairperson_name = " ".join(part for part in name_parts if part)
                print(f"[update_chairperson_fields] Derived name from User: {chairperson_name}")

        print(f"[update_chairperson_fields] Attempting db.set_value on {docname}")
        frappe.db.set_value(
            "Recruitment Adhoc Contractual",
            docname,
            {
                "chairperson_webmail_id": chairperson_webmail_id,
                "chairperson_name": chairperson_name,
            },
        )
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        print(f"[update_chairperson_fields] ERROR: {e}")
        frappe.log_error(frappe.get_traceback(), f"update_chairperson_fields failed for {docname}")
        return {"status": "error", "message": str(e)}
    else:
        print(f"[update_chairperson_fields] Success — chairperson_webmail_id={chairperson_webmail_id}, chairperson_name={chairperson_name}")
        return {
            "status": "success",
            "chairperson_webmail_id": chairperson_webmail_id,
            "chairperson_name": chairperson_name,
        }


# END OF EDIT — OJS | 2026-04-14 12:23 IST
# ============================================================

# ============================================================
# EDITED BY OJS | 2026-04-14 15:35 IST
# START OF EDIT — create_custom_designation for Recruitment Adhoc Contractual
# Mirrors the same logic from project_registration.py.
# Returns status="duplicate" when designation already exists so frontend alerts the user.
# ============================================================
@frappe.whitelist(allow_guest=True)
def create_custom_designation(designation_name, designation_type="Project Staff"):
	"""
	Checks for an existing designation (case-insensitive).
	Returns status="duplicate" with a message if already present.
	Otherwise creates a new Designation_prornd record and returns status="success".
	"""
	try:
		if not designation_name:
			return {"status": "error", "message": "Designation name is required"}

		designation_name = designation_name.strip()
		# Case-insensitive duplicate check across both name and designation_prornd fields
		existing = frappe.db.sql(
			"""SELECT name, designation_prornd FROM `tabDesignation_prornd`
			WHERE UPPER(designation_prornd)=%s OR UPPER(name)=%s LIMIT 1""",
			(designation_name.upper(), designation_name.upper()),
			as_dict=True
		)

		if existing:
			# Return a distinct "duplicate" status — frontend will alert the user
			return {
				"status": "duplicate",
				"designation_name": existing[0]["name"],
				"message": f"Designation '{existing[0].get('designation_prornd') or existing[0]['name']}' already exists in the system."
			}

		# Create new designation
		new_doc = frappe.get_doc({
			"doctype": "Designation_prornd",
			"designation_prornd": designation_name,
			"designation_type": designation_type
		})
		new_doc.insert(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "designation_name": new_doc.name}
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), f"Recruitment Adhoc Contractual Custom Designation Creation Error for {designation_name}")
		return {"status": "error", "message": str(e)}

# END OF EDIT — OJS | 2026-04-14 15:35 IST
# ============================================================


# ============================================================
# EDITED BY OJS | 2026-04-21 IST
# START OF EDIT — Single-field update endpoints
# Each endpoint updates exactly one field on a Recruitment Adhoc
# Contractual document (identified by docname) without touching
# any other field. All four target fields carry allow_on_submit=1
# so updates are safe on submitted documents as well.
#
# EDITED BY OJS | 2026-07-30
# UPDATE — Added a required `user` param to every endpoint below.
# These are allow_guest=True, so the Guest session has no permission
# to write; the caller now sends the acting user's username, which
# is validated against the User doctype and the write runs as that
# user (frappe.set_user) so it passes permission checks and
# modified_by is correctly attributed, then the session is restored.
# Also added print() statements so each request, rejection, success,
# and error shows up live in the bench terminal for quick debugging.
#
# EDITED BY OJS | 2026-07-30 (2)
# FIX — Frontend sends `user` as a bare webmail id (no @domain), per this
# doctype's own webmail_id convention, so frappe.db.exists("User", user)
# was failing for every request. Added _resolve_user() to look up the
# User whose name starts with "<user>@" when no exact match exists.
# ============================================================

def _resolve_user(user):
	"""Resolve `user` to a full User name (email).

	Callers may send either the full email (matches a User name directly) or
	just the webmail id without the domain (this doctype's own convention —
	see the webmail_id field description). In the latter case, look up the
	User whose name starts with "<user>@". Returns (resolved_name, error_message).
	"""
	if frappe.db.exists("User", user):
		return user, None

	if "@" not in user:
		matches = frappe.get_all("User", filters={"name": ["like", f"{user}@%"]}, pluck="name")
		if len(matches) == 1:
			return matches[0], None
		if len(matches) > 1:
			return None, f"user '{user}' is ambiguous, matches: {', '.join(matches)}"

	return None, f"User '{user}' not found"


def _update_single_field(docname, fieldname, value, user=None):
	"""Internal helper to update a single field on a Recruitment Adhoc Contractual doc.

	Runs as `user` (instead of Guest) so the write passes permission checks and
	`modified_by` reflects the actual acting user.
	"""
	print(f"[recruitment_adhoc_contractual] update requested — docname={docname!r} field={fieldname!r} value={value!r} user={user!r}")

	if not docname:
		print("[recruitment_adhoc_contractual] rejected — docname is required")
		return {"status": "error", "message": "docname is required"}

	if not user:
		print("[recruitment_adhoc_contractual] rejected — user is required")
		return {"status": "error", "message": "user is required"}

	resolved_user, resolve_error = _resolve_user(user)
	if resolve_error:
		print(f"[recruitment_adhoc_contractual] rejected — {resolve_error}")
		return {"status": "error", "message": resolve_error}
	if resolved_user != user:
		print(f"[recruitment_adhoc_contractual] resolved user '{user}' -> '{resolved_user}'")
	user = resolved_user

	if not frappe.db.exists("Recruitment Adhoc Contractual", docname):
		print(f"[recruitment_adhoc_contractual] rejected — document '{docname}' not found")
		return {"status": "error", "message": f"Document '{docname}' not found"}

	original_user = frappe.session.user
	try:
		frappe.set_user(user)
		frappe.db.set_value("Recruitment Adhoc Contractual", docname, fieldname, value)
		frappe.db.commit()
		print(f"[recruitment_adhoc_contractual] success — {docname}.{fieldname} = {value!r} (by {user})")
		return {"status": "success", "docname": docname, fieldname: value}
	except Exception as e:
		frappe.db.rollback()
		print(f"[recruitment_adhoc_contractual] error — {fieldname} update failed for {docname}: {e}")
		frappe.log_error(frappe.get_traceback(), f"update {fieldname} failed for {docname}")
		return {"status": "error", "message": str(e)}
	finally:
		frappe.set_user(original_user)


@frappe.whitelist(allow_guest=True)
def update_walk_in(docname, walk_in, user=None):
	"""Update only the walk_in field ('Yes' / 'No' / '')."""
	if walk_in not in ("", "Yes", "No", None):
		return {"status": "error", "message": "walk_in must be 'Yes', 'No', or empty"}
	return _update_single_field(docname, "walk_in", walk_in or "", user=user)


@frappe.whitelist(allow_guest=True)
def update_upfa_interview_date(docname, upfa_interview_date, user=None):
	"""Update only the upfa_interview_date field (Date, YYYY-MM-DD)."""
	return _update_single_field(docname, "upfa_interview_date", upfa_interview_date or None, user=user)


@frappe.whitelist(allow_guest=True)
def update_upfa_interview_time(docname, upfa_interview_time, user=None):
	"""Update only the upfa_interview_time field (Time, HH:MM:SS)."""
	return _update_single_field(docname, "upfa_interview_time", upfa_interview_time or None, user=user)


@frappe.whitelist(allow_guest=True)
def update_last_date_of_appllication(docname, last_date_of_appllication, user=None):
	"""Update only the last_date_of_appllication field (Date, YYYY-MM-DD)."""
	return _update_single_field(docname, "last_date_of_appllication", last_date_of_appllication or None, user=user)

# END OF EDIT — OJS | 2026-04-21 IST
# ============================================================
