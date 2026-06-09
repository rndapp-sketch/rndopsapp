# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

import base64
import datetime
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from rndopsapp.minio import get_rnd_file_service
from rndopsapp.file_handler import get_file_category_for_doctype
from rndopsapp.rndopsapp.doctype.project_registration.project_registration import notify_mattermost

# =============================================================================
# CONSTANTS
# =============================================================================

INDENT_TYPE_PROPRIETARY = "Proprietary Purchase with Proprietary certificate from the OEM"
INDENT_TYPE_STANDARDIZED = "Standerdised/ Emergent Purchase"
INDENT_TYPE_REPAIR = "Repair/ Repleacement"
INDENT_TYPE_AMC = "Annual Maintenance Contract"
INDENT_TYPE_RATE_CONTRACT = "Rate Contract Purchase"

INDENT_TYPES = [
    INDENT_TYPE_PROPRIETARY,
    INDENT_TYPE_STANDARDIZED,
    INDENT_TYPE_REPAIR,
    INDENT_TYPE_AMC,
    INDENT_TYPE_RATE_CONTRACT,
]

DOCTYPE = "Indent Cum Sanction Sheet"

# Corrected child doctype names
SUB_DOCTYPE_MAP = {
    INDENT_TYPE_PROPRIETARY: "proprietary_purchase",
    INDENT_TYPE_STANDARDIZED: "standerdized_purchase",
    INDENT_TYPE_REPAIR: "repair_replacement",
    INDENT_TYPE_AMC: "AMC",
    INDENT_TYPE_RATE_CONTRACT: "Rate Contract",
}

WORKFLOW_MAP = {
    INDENT_TYPE_PROPRIETARY: "Proprietary Purchase Workflow",
    INDENT_TYPE_STANDARDIZED: "Standardized Purchase Workflow",
    INDENT_TYPE_REPAIR: "Repair Replacement Workflow",
    INDENT_TYPE_AMC: "AMC Workflow",
    INDENT_TYPE_RATE_CONTRACT: "Rate Contract Workflow",
}

# Dynamic put-back: target label → next workflow state
ICSS_PUT_BACK_TARGETS = {
    "Requestor": "Draft",
    "PI": "Pending PI Approval",
    "Staff": "Pending Staff Approval",
    "HoS": "Pending HoS Approval",
}

# Which roles can put back from each state, and to which targets
ICSS_PUT_BACK_RULES = {
    "Pending PI Approval": {
        "roles": ["Permanent Employee", "head_approver_1", "HoD", "System Manager"],
        "targets": ["Requestor"],
    },
    "Pending Staff Approval": {
        "roles": ["staff, RnD", "System Manager"],
        "targets": ["PI", "Requestor"],
    },
    "Pending HoS Approval": {
        "roles": ["Hos, RnD (Head of Section, RnD)", "System Manager"],
        "targets": ["Staff", "PI", "Requestor"],
    },
    "Pending Dean Approval": {
        "roles": ["Dean, RnD", "System Manager"],
        "targets": ["HoS", "Staff", "PI", "Requestor"],
    },
    "Pending Associate Dean": {
        "roles": ["Ado_RnD", "System Manager"],
        "targets": ["HoS", "Staff", "PI", "Requestor"],
    },
}

# Roles that bypass PI approval on initial submit and go directly to Staff
DIRECT_SUBMIT_ROLES = ["Permanent Employee", "head_approver_1", "HoD", "System Manager"]

# Director approval thresholds (in INR)
DIRECTOR_THRESHOLD_EQUIPMENT = 1_000_000      # 10 lakhs
DIRECTOR_THRESHOLD_NON_EQUIPMENT = 300_000    # 3 lakhs

# HoS routing threshold
HOS_ROUTING_THRESHOLD = 100_000               # 1 lakh

# States where put-back is blocked
PUT_BACK_BLOCKED_STATES = {"PO Delivered", "PO Generated", "Pending PO Generation"}


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================


def extract_eval_expression(expression):
    if not expression:
        return None
    expression = str(expression).strip()
    if expression.startswith("eval:"):
        return expression[5:].strip()
    return expression


def _get_icss_approval_amount(doc):
    """Return normalized approval amount for workflow routing, based on indent type."""
    indent_type = doc.get("icss_indent_type") or ""
    if indent_type == INDENT_TYPE_REPAIR:
        return flt(doc.get("icss_repair_grand_total"))
    if indent_type == INDENT_TYPE_AMC:
        return flt(doc.get("icss_amc_grand_total"))
    return flt(doc.get("icss_grand_total"))


def _is_icss_director_approval_required(doc):
    """
    Return True if Director approval is required based on account head and amount.

    Equipment + amount > 10L  → required
    Non-equipment + amount > 3L → required
    """
    amount = _get_icss_approval_amount(doc)
    account_head = doc.get("icss_account_head") or doc.get("icss_other_account_head") or ""
    account_head_text = str(account_head)

    try:
        budget_head = frappe.db.get_value(
            "Budget Head",
            account_head,
            ["budget_head", "name"],
            as_dict=True,
        )
        if budget_head:
            account_head_text = (
                budget_head.get("budget_head") or budget_head.get("name") or account_head_text
            )
    except Exception:
        pass

    is_equipment = "equipment" in account_head_text.lower()
    if is_equipment:
        return amount > DIRECTOR_THRESHOLD_EQUIPMENT
    return amount > DIRECTOR_THRESHOLD_NON_EQUIPMENT


def _resolve_initial_submit_next_state(user_roles):
    """Return the correct first-pending state based on initiator roles."""
    if any(role in user_roles for role in DIRECT_SUBMIT_ROLES):
        return "Pending Staff Approval"
    return "Pending PI Approval"


def _resolve_hos_next_state(doc):
    """Return the next state after HoS approval based on approval amount."""
    amount = _get_icss_approval_amount(doc)
    if amount > HOS_ROUTING_THRESHOLD:
        return "Pending Dean Approval"
    return "Pending Associate Dean"


def _get_available_icss_put_back_action_rows(doc, user_roles=None):
    """Return list of put-back action dicts for current user and workflow state."""
    current_state = doc.workflow_state or "Draft"
    if current_state in PUT_BACK_BLOCKED_STATES:
        return []

    if user_roles is None:
        user_roles = frappe.get_roles(frappe.session.user)

    rules = ICSS_PUT_BACK_RULES.get(current_state)
    if not rules:
        return []

    allowed_roles = rules.get("roles", [])
    if not (any(r in user_roles for r in allowed_roles) or "System Manager" in user_roles):
        return []

    rows = []
    for target in rules.get("targets", []):
        next_state = ICSS_PUT_BACK_TARGETS.get(target)
        if next_state:
            rows.append({
                "target": target,
                "label": f"Put Back to {target}",
                "next_state": next_state,
            })
    return rows


def _clear_icss_director_fields_for_put_back(docname, current_state):
    """Clear director approval tracking fields when putting back from Dean stage."""
    if current_state == "Pending Dean Approval":
        frappe.db.set_value(
            DOCTYPE,
            docname,
            {
                "send_to_director": 0,
                "director_signed_pdf": None,
                "director_approval_required": 0,
            },
            update_modified=False,
        )


def _add_icss_put_back_comment(docname, target, next_state, current_state, reason):
    """Insert a workflow audit comment for put-back actions."""
    try:
        reason_text = f" Reason: {reason}" if reason else ""
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Workflow",
            "reference_doctype": DOCTYPE,
            "reference_name": docname,
            "content": (
                f"Put back to {target} ({next_state}) by {frappe.session.user} "
                f"from {current_state}.{reason_text}"
            ),
        }).insert(ignore_permissions=True)
    except Exception:
        pass


def _save_icss_file_to_minio(filename, file_data, doctype, docname, folder, is_private=True):
    """
    Upload file_data (base64 string or raw bytes) to MinIO.

    Path in bucket: {doctype}/{docname}/application/{folder}/{filename}
    Returns the MinIO file_url string.
    """
    if isinstance(file_data, str):
        if "," in file_data:
            # strip data:mime/type;base64, prefix
            file_data = file_data.split(",", 1)[1]
        raw = base64.b64decode(file_data)
    else:
        raw = bytes(file_data)

    svc = get_rnd_file_service()
    result = svc.save_file(
        filename=filename,
        content=raw,
        is_private=is_private,
        doctype=doctype,
        docname=docname,
        folder=f"application/{folder}",
    )
    if not result.get("status"):
        frappe.throw(_("File upload to storage failed: {0}").format(result.get("message")))
    return result["data"]["file_url"]


def _save_doc_from_payload(doctype, data, linkage_fields=None):
    """
    Generic helper: create or update a Frappe doc from a dict payload.

    Handles standard fields, Table fields, and Attach fields.
    ``linkage_fields`` is a dict of {fieldname: value} to always set (e.g. parent ID).
    """
    doc_name = data.get("name")
    is_new = False

    if doc_name and frappe.db.exists(doctype, doc_name):
        doc = frappe.get_doc(doctype, doc_name)
    else:
        doc = frappe.new_doc(doctype)
        is_new = True

    meta = frappe.get_meta(doctype)

    # Apply linkage fields first
    if linkage_fields:
        for fieldname, value in linkage_fields.items():
            if meta.has_field(fieldname) and value is not None:
                doc.set(fieldname, value)
            elif hasattr(doc, fieldname) and value is not None:
                setattr(doc, fieldname, value)

    # First pass: set simple fields; defer files and tables
    deferred = []
    skip = {"name", "doctype", "docstatus"}
    if linkage_fields:
        skip.update(linkage_fields.keys())

    for fieldname, value in data.items():
        if fieldname in skip:
            continue
        if not meta.has_field(fieldname):
            continue
        df = meta.get_field(fieldname)
        if df.fieldtype in ("Attach", "Attach Image", "Table"):
            deferred.append((fieldname, value, df))
        else:
            if value not in (None, ""):
                doc.set(fieldname, value)

    doc.flags.ignore_permissions = True
    if is_new:
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    # Second pass: files and child tables
    for fieldname, value, df in deferred:
        if df.fieldtype == "Table":
            rows = value if isinstance(value, list) else []
            doc.set(fieldname, [])
            child_meta = frappe.get_meta(df.options)
            for row in (rows or []):
                row_dict = dict(row or {})
                # Strip system fields from child rows
                for sf in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                    row_dict.pop(sf, None)
                # Handle file uploads inside child rows
                for cf in child_meta.fields:
                    if cf.fieldtype in ("Attach", "Attach Image") and row_dict.get(cf.fieldname):
                        f_val = row_dict[cf.fieldname]
                        if isinstance(f_val, dict) and f_val.get("file_data"):
                            try:
                                _folder = get_file_category_for_doctype(doctype, cf.fieldname)
                                row_dict[cf.fieldname] = _save_icss_file_to_minio(
                                    f_val.get("file_name", "attachment"),
                                    f_val["file_data"],
                                    doctype,
                                    doc.name,
                                    _folder,
                                )
                            except Exception as e:
                                frappe.log_error(f"ICSS child file upload error: {e}", "ICSS Save")
                doc.append(fieldname, row_dict)

        elif df.fieldtype in ("Attach", "Attach Image"):
            if isinstance(value, dict) and value.get("file_data"):
                try:
                    _folder = get_file_category_for_doctype(doctype, fieldname)
                    doc.set(fieldname, _save_icss_file_to_minio(
                        value.get("file_name", "attachment"),
                        value["file_data"],
                        doctype,
                        doc.name,
                        _folder,
                    ))
                except Exception as e:
                    frappe.log_error(f"ICSS file upload error ({fieldname}): {e}", "ICSS Save")
            elif isinstance(value, str) and value:
                doc.set(fieldname, value)

    doc.save(ignore_permissions=True)
    return doc


# =============================================================================
# DOCUMENT CONTROLLER
# =============================================================================


class IndentCumSanctionSheet(Document):
    def before_insert(self):
        self._validate_indent_type()

    def validate(self):
        self._validate_indent_type()
        self._validate_indent_type_change()
        self.calculate_item_totals()
        self.calculate_repair_total()
        self.calculate_amc_total()
        self._update_director_approval_required()

    def before_save(self):
        """Update sub-doctype only for existing records; skip for new docs and when flagged."""
        if self.flags.get("skip_icss_subdoctype_sync") or self.is_new():
            return
        if self.get("icss_indent_type"):
            self._sync_sub_doctype()

    def after_insert(self):
        if not self.flags.get("skip_icss_subdoctype_sync") and self.get("icss_indent_type"):
            self._sync_sub_doctype()
        self._log_lifecycle_event("Created")

    def on_update(self):
        workflow_action = getattr(self.flags, "icss_workflow_action", None)
        if workflow_action:
            self._log_lifecycle_event(f"Workflow Action: {workflow_action}")
            self.flags.icss_workflow_action = None
            return
        if not self.is_new():
            self._log_lifecycle_event("Saved")

    def on_submit(self):
        if self.get("sub_doctype_reference") and self.get("icss_indent_type"):
            self._perform_sub_doctype_workflow_action("Submit")
        workflow_action = getattr(self.flags, "icss_workflow_action", None)
        event_label = f"Workflow Action: {workflow_action}" if workflow_action else "Submitted"
        self._log_lifecycle_event(event_label)
        self.flags.icss_workflow_action = None

    def on_cancel(self):
        workflow_action = getattr(self.flags, "icss_workflow_action", None)
        event_label = f"Workflow Action: {workflow_action}" if workflow_action else "Cancelled"
        self._log_lifecycle_event(event_label)
        self.flags.icss_workflow_action = None

    def on_update_after_submit(self):
        if self.get("sub_doctype_reference") and self.get("icss_indent_type"):
            self._sync_sub_doctype_after_submit()
        workflow_action = getattr(self.flags, "icss_workflow_action", None)
        if workflow_action:
            self._log_lifecycle_event(f"Workflow Action: {workflow_action}")
            self.flags.icss_workflow_action = None
            return
        self._log_lifecycle_event("Updated After Submit")

    # -------------------------------------------------------------------------
    # VALIDATION
    # -------------------------------------------------------------------------

    def _validate_indent_type(self):
        if not self.get("icss_indent_type"):
            return
        if self.get("icss_indent_type") not in INDENT_TYPES:
            frappe.throw(_("Invalid Indent Type: {0}").format(self.get("icss_indent_type")))

    def _validate_indent_type_change(self):
        if self.docstatus > 0 and self.has_value_changed("icss_indent_type"):
            frappe.throw(_("Cannot change Indent Type after submission."))

    def _update_director_approval_required(self):
        """Pre-calculate director_approval_required for frontend display."""
        try:
            self.director_approval_required = 1 if _is_icss_director_approval_required(self) else 0
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # SUB-DOCTYPE MANAGEMENT
    # -------------------------------------------------------------------------

    def _sync_sub_doctype(self):
        sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
        if not sub_doctype_name:
            frappe.log_error(
                f"No sub-doctype mapping for indent type: {self.get('icss_indent_type')}",
                "ICSS Sub-DocType Sync Error",
            )
            return

        sub_doc = None
        if self.get("sub_doctype_reference"):
            try:
                sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))
            except frappe.DoesNotExistError:
                sub_doc = None

        if not sub_doc:
            sub_doc = self._create_sub_doctype_record(sub_doctype_name)
        else:
            self._map_parent_data_to_subdoctype(sub_doc)

        self._save_sub_doctype(sub_doc)

        if not self.get("sub_doctype_reference"):
            self.db_set("sub_doctype_reference", sub_doc.name, update_modified=False)

    def _create_sub_doctype_record(self, sub_doctype_name):
        sub_doc = frappe.new_doc(sub_doctype_name)
        self._map_parent_data_to_subdoctype(sub_doc)
        return sub_doc

    def _map_parent_data_to_subdoctype(self, sub_doc):
        for field, value in [
            ("indent_cum_sanction_sheet_id", self.name),
            ("project_ref", self.get("project_ref")),
            ("project_no", self.get("project_no")),
            ("indent_type", self.get("icss_indent_type")),
        ]:
            if meta_has_or_attr(sub_doc, field):
                setattr(sub_doc, field, value)

    def _save_sub_doctype(self, sub_doc):
        try:
            sub_doc.flags.ignore_permissions = True
            if sub_doc.is_new():
                sub_doc.insert(ignore_permissions=True)
            else:
                sub_doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(
                f"Error saving sub-doctype {sub_doc.doctype}: {e}\n{frappe.get_traceback()}",
                "ICSS Sub-DocType Save Error",
            )
            frappe.throw(_("Failed to save sub-doctype record: {0}").format(str(e)))

    def _sync_sub_doctype_workflow_state(self, next_state):
        """Directly sync child doctype workflow_state to match parent."""
        if not self.get("sub_doctype_reference") or not self.get("icss_indent_type"):
            return
        sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
        if not sub_doctype_name:
            return
        try:
            if frappe.db.exists(sub_doctype_name, self.get("sub_doctype_reference")):
                frappe.db.set_value(
                    sub_doctype_name,
                    self.get("sub_doctype_reference"),
                    "workflow_state",
                    next_state,
                    update_modified=False,
                )
        except Exception as e:
            frappe.log_error(f"ICSS child workflow sync error: {e}", "ICSS Child Workflow Sync")

    def _perform_sub_doctype_workflow_action(self, action):
        if not self.get("sub_doctype_reference"):
            return
        sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
        if not sub_doctype_name:
            return
        try:
            if not frappe.db.exists("Workflow", {"document_type": sub_doctype_name, "is_active": 1}):
                return
            sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))
            workflow = frappe.get_doc("Workflow", {"document_type": sub_doctype_name, "is_active": 1})
            current_state = sub_doc.workflow_state or "Draft"
            for transition in workflow.transitions:
                if transition.state == current_state and transition.action == action:
                    sub_doc.workflow_state = transition.next_state
                    state_doc = next(
                        (s for s in workflow.states if s.state == transition.next_state), None
                    )
                    if state_doc and state_doc.doc_status == "1" and sub_doc.docstatus == 0:
                        sub_doc.submit()
                    elif state_doc and state_doc.doc_status == "2" and sub_doc.docstatus != 2:
                        sub_doc.cancel()
                    else:
                        sub_doc.save(ignore_permissions=True)
                    break
        except Exception as e:
            frappe.log_error(
                f"Error in sub-doctype workflow action: {e}\n{frappe.get_traceback()}",
                "ICSS Sub-DocType Workflow Error",
            )

    def _sync_sub_doctype_after_submit(self):
        if not self.get("sub_doctype_reference"):
            return
        sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
        if not sub_doctype_name:
            return
        try:
            sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))
            self._map_parent_data_to_subdoctype(sub_doc)
            sub_doc.flags.ignore_permissions = True
            sub_doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(
                f"Error syncing sub-doctype after submit: {e}\n{frappe.get_traceback()}",
                "ICSS Sub-DocType Sync Error",
            )

    # -------------------------------------------------------------------------
    # CALCULATIONS
    # -------------------------------------------------------------------------

    def calculate_item_totals(self):
        total_basic = 0
        for row in (self.get("icss_items") or []):
            base = flt(row.icss_qty) * flt(row.icss_rate)
            discount = base * flt(row.icss_discount_percent) / 100
            gst = (base - discount) * flt(row.icss_gst_percent) / 100
            row.icss_amount = base - discount + gst
            total_basic += flt(row.icss_amount)
        self.icss_total_basic_value = total_basic
        self.icss_grand_total = (
            flt(self.get("icss_total_basic_value"))
            + flt(self.get("icss_packing_charges"))
            + flt(self.get("icss_freight_charges"))
            + flt(self.get("icss_other_charges"))
        )

    def calculate_repair_total(self):
        self.icss_repair_grand_total = flt(self.get("icss_repair_expenditure")) + flt(
            self.get("icss_repair_other_charges")
        )

    def calculate_amc_total(self):
        amc_subtotal = flt(self.get("icss_amc_value")) + flt(self.get("icss_amc_other_charges"))
        gst_amount = amc_subtotal * flt(self.get("icss_amc_gst_percent")) / 100
        self.icss_amc_grand_total = amc_subtotal + gst_amount

    # -------------------------------------------------------------------------
    # LOGGING
    # -------------------------------------------------------------------------

    def _log_lifecycle_event(self, event_label):
        try:
            log_payload = {
                "event": event_label,
                "document": self.name,
                "workflow_state": self.workflow_state or "Draft",
                "docstatus": self.docstatus,
                "indent_type": self.get("icss_indent_type"),
                "project_ref": self.get("project_ref"),
                "project_no": self.get("project_no"),
                "triggered_by": frappe.session.user or "System",
            }
            frappe.logger("icss_lifecycle").info(json.dumps(log_payload, default=str))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "ICSS Lifecycle Log Error")


def meta_has_or_attr(doc, fieldname):
    """Check if a doc has a field (either via meta or attribute)."""
    try:
        meta = frappe.get_meta(doc.doctype)
        if meta.has_field(fieldname):
            return True
    except Exception:
        pass
    return hasattr(doc, fieldname)


# =============================================================================
# API ENDPOINTS
# =============================================================================


@frappe.whitelist()
def get_icss_indent_types():
    """Return all available ICSS indent type options."""
    try:
        meta = frappe.get_meta(DOCTYPE)
        df = meta.get_field("icss_indent_type")
        if not df:
            frappe.throw(_("Field 'icss_indent_type' not found in {0}").format(DOCTYPE))
        raw_options = (df.options or "").split("\n")
        options = [opt.strip() for opt in raw_options if opt.strip()]
        return {
            "status": "success",
            "indent_types": [{"value": opt, "label": opt} for opt in options],
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Get Indent Types Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# GET PARENT FIELDS
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_icss_fields(doc_name=None):
    """
    Return ICSS field metadata, prefill data, link options, client scripts,
    and computation rules.  When doc_name is provided, the prefill_data also
    contains a nested ``child_document`` key with the linked child doctype data.
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
        if f.fieldtype == "Table" and f.options:
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [
                {
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
                for cf in child_meta.fields
            ]
        fields.append(field_data)

    # ---- Prefill Data ----
    prefill_data = {}
    link_options = {}

    if doc_name:
        try:
            doc = frappe.get_doc(DOCTYPE, doc_name)
            prefill_data = doc.as_dict()

            # Compute director_approval_required fresh
            try:
                prefill_data["director_approval_required"] = (
                    1 if _is_icss_director_approval_required(doc) else 0
                )
            except Exception:
                pass

            # Embed nested child document
            indent_type = doc.get("icss_indent_type")
            sub_ref = doc.get("sub_doctype_reference")
            if indent_type and sub_ref:
                child_doctype_name = SUB_DOCTYPE_MAP.get(indent_type)
                if child_doctype_name:
                    try:
                        child_doc = frappe.get_doc(child_doctype_name, sub_ref)
                        prefill_data["child_document"] = child_doc.as_dict()
                        prefill_data["child_doctype"] = child_doctype_name
                    except Exception:
                        pass
        except Exception:
            pass
    else:
        user = frappe.session.user
        if user and user != "Guest":
            try:
                user_doc = frappe.get_doc("User", user)
                prefill_data["icss_applicant_webmail_id"] = user
                prefill_data["icss_applicant_name"] = user_doc.full_name
                prefill_data["icss_applicant_department__centre__section"] = user_doc.department_name
                prefill_data["icss_applicant_designation"] = getattr(user_doc, "designation_name", "")
            except Exception:
                pass

    prefill_data.setdefault("icss_declaration_sanctioned_accept", 0)
    prefill_data.setdefault("icss_declaration_nonsanctioned_accept", 0)
    prefill_data.setdefault("icss_repair_declaration_checkbox", 0)
    prefill_data.setdefault("icss_amc_declaration", 0)

    # ---- Link Options ----
    try:
        account_heads = frappe.get_all(
            "Budget Head",
            fields=["name as value", "budget_head as label"],
            limit_page_length=0,
        )
        link_options["icss_account_head"] = [
            {"value": r["value"], "label": r.get("label") or r["value"]} for r in account_heads
        ]
    except Exception:
        link_options["icss_account_head"] = []

    try:
        users = frappe.get_all(
            "User",
            filters={"enabled": 1},
            fields=["name as value", "full_name as label"],
            limit_page_length=0,
        )
        link_options["icss_applicant_webmail_id"] = users
        link_options["icss_applying_for_mail"] = users
    except Exception:
        link_options["icss_applicant_webmail_id"] = []
        link_options["icss_applying_for_mail"] = []

    try:
        departments = frappe.get_all(
            "Department_prornd",
            fields=["name as value", "dept_name as label"],
            limit_page_length=0,
        )
        link_options["icss_applicant_department__centre__section"] = departments
        link_options["icss_applying_for_department_centre_section"] = departments
    except Exception:
        link_options["icss_applicant_department__centre__section"] = []

    # ---- Client Scripts ----
    client_scripts = []
    try:
        scripts = frappe.get_all(
            "Client Script",
            filters={"dt": DOCTYPE, "enabled": 1},
            fields=["name", "script", "view"],
        )
        client_scripts = [
            {"name": s.name, "script": s.script, "view": s.view} for s in scripts
        ]
    except Exception:
        pass

    # ---- Computation Rules ----
    computation_rules = {
        "row_calculations": [
            {
                "table_fieldname": "icss_items",
                "target_field": "icss_amount",
                "formula": "(icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100) + (((icss_qty * icss_rate) - ((icss_qty * icss_rate) * icss_discount_percent / 100)) * icss_gst_percent / 100)",
                "trigger_fields": ["icss_qty", "icss_rate", "icss_discount_percent", "icss_gst_percent"],
                "description": "Row amount = (Qty × Rate) - Discount% + GST%",
            }
        ],
        "aggregations": [
            {
                "target_field": "icss_total_basic_value",
                "source_table": "icss_items",
                "source_field": "icss_amount",
                "operation": "sum",
                "description": "Total basic value = sum of all item amounts",
            }
        ],
        "computed_fields": [
            {
                "target_field": "icss_grand_total",
                "formula": "icss_total_basic_value + icss_packing_charges + icss_freight_charges + icss_other_charges",
                "trigger_fields": ["icss_total_basic_value", "icss_packing_charges", "icss_freight_charges", "icss_other_charges"],
                "description": "Grand total = Basic Value + Packing + Freight + Other Charges",
            },
            {
                "target_field": "icss_repair_grand_total",
                "formula": "icss_repair_expenditure + icss_repair_other_charges",
                "trigger_fields": ["icss_repair_expenditure", "icss_repair_other_charges"],
                "description": "Repair grand total = Repair Expenditure + Other Charges",
            },
            {
                "target_field": "icss_amc_grand_total",
                "formula": "(icss_amc_value + icss_amc_other_charges) + ((icss_amc_value + icss_amc_other_charges) * icss_amc_gst_percent / 100)",
                "trigger_fields": ["icss_amc_value", "icss_amc_other_charges", "icss_amc_gst_percent"],
                "description": "AMC grand total = (AMC Value + Other Charges) + GST%",
            },
        ],
        "auto_populate": [
            {
                "trigger_field": "icss_applicant_webmail_id",
                "context": "parent",
                "api": "rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_user_details_icss",
                "api_param": "user_email",
                "field_map": {
                    "full_name": "icss_applicant_name",
                    "department_name": "icss_applicant_department__centre__section",
                    "designation_name": "icss_applicant_designation",
                },
                "description": "Auto-fill applicant details when webmail ID is selected",
            },
            {
                "trigger_field": "icss_applying_for_mail",
                "context": "parent",
                "api": "rndopsapp.rndopsapp.doctype.indent_cum_sanction_sheet.indent_cum_sanction_sheet.get_user_details_icss",
                "api_param": "user_email",
                "field_map": {
                    "full_name": "icss_applying_for_name",
                    "department_name": "icss_applying_for_department_centre_section",
                    "designation_name": "icss_applying_for_designation",
                },
                "description": "Auto-fill applying-for details when webmail ID is selected",
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
# GET CHILD FIELDS
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_icss_child_fields(indent_type, child_docname=None):
    """
    Return field metadata for the child doctype matching ``indent_type``.

    When ``child_docname`` is provided, also returns prefill data from
    the existing child document.
    """
    if not indent_type:
        return {"status": "error", "message": "indent_type is required"}

    child_doctype_name = SUB_DOCTYPE_MAP.get(indent_type)
    if not child_doctype_name:
        return {
            "status": "error",
            "message": f"No child doctype found for indent type: {indent_type}",
        }

    try:
        meta = frappe.get_meta(child_doctype_name)
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
                "depends_on_eval": extract_eval_expression(f.depends_on),
                "mandatory_depends_on": f.mandatory_depends_on,
                "mandatory_depends_on_eval": extract_eval_expression(f.mandatory_depends_on),
            }
            if f.fieldtype == "Table" and f.options:
                try:
                    child_meta = frappe.get_meta(f.options)
                    field_data["child_fields"] = [
                        {
                            "fieldname": cf.fieldname,
                            "label": cf.label,
                            "fieldtype": cf.fieldtype,
                            "options": cf.options,
                            "mandatory": cf.reqd,
                            "in_list_view": cf.in_list_view,
                            "read_only": cf.read_only,
                            "default": cf.default,
                        }
                        for cf in child_meta.fields
                    ]
                except Exception:
                    field_data["child_fields"] = []
            fields.append(field_data)

        prefill_data = {}
        if child_docname and frappe.db.exists(child_doctype_name, child_docname):
            try:
                child_doc = frappe.get_doc(child_doctype_name, child_docname)
                prefill_data = child_doc.as_dict()
            except Exception:
                pass

        return {
            "status": "success",
            "indent_type": indent_type,
            "child_doctype": child_doctype_name,
            "fields": fields,
            "prefill_data": prefill_data,
            "link_options": {},
            "computation_rules": {},
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Get Child Fields Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# SAVE DATA (flat and composite)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def save_icss_data(data):
    """
    Create or update a flat (parent-only) Indent Cum Sanction Sheet document.

    If the payload contains a ``parent`` or ``child`` key, delegates to
    ``save_icss_composite_data`` for backward compatibility.
    """
    try:
        if isinstance(data, str):
            data = json.loads(data)

        # Guard: redirect composite payload to the correct function
        if isinstance(data, dict) and ("parent" in data or "child" in data):
            return save_icss_composite_data(data)

        doc = _save_doc_from_payload(DOCTYPE, data)
        frappe.db.commit()
        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ✅ [ICSS] Saved                             │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Docname     : {doc.name}\n"
            f" State       : {doc.workflow_state or 'Draft'}\n"
            f" Indent Type : {doc.get('icss_indent_type') or '-'}\n"
            f" Applicant   : {doc.get('icss_applicant_name') or '-'}\n"
            f" User        : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            "```"
        )
        return {"status": "success", "docname": doc.name}

    except Exception as e:
        _tb = frappe.get_traceback()
        frappe.db.rollback()
        frappe.log_error(_tb, "ICSS Save Error")
        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ❌ [ICSS] Save Error                        │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Exception : {type(e).__name__}: {str(e)}\n"
            f" User      : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            f"---TRACEBACK---\n{_tb}\n"
            "```",
            urgent=True,
        )
        frappe.throw(_("Failed to save Indent Cum Sanction Sheet: {0}").format(str(e)))


@frappe.whitelist()
def save_icss_composite_data(data):
    """
    Save an ICSS parent + child in a single transaction.

    Payload shape::

        {
            "parent": { ...parent fields... },
            "child":  { "doctype": "proprietary_purchase", ...child fields... }
        }

    A flat (non-composite) payload is handled by ``save_icss_data`` instead.
    """
    try:
        if isinstance(data, str):
            data = json.loads(data)

        # Backward compat: no parent/child keys → flat save
        if not isinstance(data, dict) or ("parent" not in data and "child" not in data):
            return save_icss_data(data)

        parent_data = dict(data.get("parent") or {})
        child_data = dict(data.get("child") or {})

        # ── SAVE PARENT ──────────────────────────────────────────────
        doc_name = parent_data.get("name")
        is_new_parent = not (doc_name and frappe.db.exists(DOCTYPE, doc_name))

        if is_new_parent:
            parent_doc = frappe.new_doc(DOCTYPE)
        else:
            parent_doc = frappe.get_doc(DOCTYPE, doc_name)
            if parent_doc.docstatus != 0:
                frappe.throw(_("Cannot edit a submitted or cancelled document."))

        parent_meta = frappe.get_meta(DOCTYPE)
        parent_deferred = []

        for fieldname, value in parent_data.items():
            if fieldname in ("name", "doctype", "docstatus"):
                continue
            if not parent_meta.has_field(fieldname):
                continue
            df = parent_meta.get_field(fieldname)
            if df.fieldtype in ("Attach", "Attach Image", "Table"):
                parent_deferred.append((fieldname, value, df))
            elif value not in (None, ""):
                parent_doc.set(fieldname, value)

        parent_doc.flags.ignore_permissions = True
        parent_doc.flags.skip_icss_subdoctype_sync = True  # we handle child explicitly

        if is_new_parent:
            parent_doc.insert(ignore_mandatory=True)
        else:
            parent_doc.save(ignore_permissions=True)

        # Second pass: parent tables and files
        for fieldname, value, df in parent_deferred:
            if df.fieldtype == "Table":
                rows = value if isinstance(value, list) else []
                parent_doc.set(fieldname, [])
                for row in (rows or []):
                    row_dict = dict(row or {})
                    for sf in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                        row_dict.pop(sf, None)
                    parent_doc.append(fieldname, row_dict)
            elif df.fieldtype in ("Attach", "Attach Image"):
                if isinstance(value, dict) and value.get("file_data"):
                    try:
                        _folder = get_file_category_for_doctype(DOCTYPE, fieldname)
                        parent_doc.set(fieldname, _save_icss_file_to_minio(
                            value.get("file_name", "attachment"),
                            value["file_data"],
                            DOCTYPE,
                            parent_doc.name,
                            _folder,
                        ))
                    except Exception as e:
                        frappe.log_error(f"ICSS composite parent file upload error ({fieldname}): {e}", "ICSS Save")
                elif isinstance(value, str) and value:
                    parent_doc.set(fieldname, value)

        parent_doc.save(ignore_permissions=True)

        # ── SAVE CHILD ───────────────────────────────────────────────
        indent_type = parent_doc.get("icss_indent_type")
        child_doctype_name = SUB_DOCTYPE_MAP.get(indent_type) if indent_type else None
        child_doc = None
        child_docname = None

        if child_doctype_name and child_data:
            existing_ref = parent_doc.get("sub_doctype_reference")
            if existing_ref and frappe.db.exists(child_doctype_name, existing_ref):
                child_doc = frappe.get_doc(child_doctype_name, existing_ref)
            else:
                child_doc = frappe.new_doc(child_doctype_name)

            # Always ensure linkage fields are set
            linkage = {
                "indent_cum_sanction_sheet_id": parent_doc.name,
                "project_ref": parent_doc.get("project_ref"),
                "project_no": parent_doc.get("project_no"),
                "indent_type": indent_type,
            }

            child_meta = frappe.get_meta(child_doctype_name)
            child_deferred = []
            skip_child = {"name", "doctype", "docstatus"} | set(linkage.keys())

            for lf, lv in linkage.items():
                if meta_has_or_attr(child_doc, lf) and lv is not None:
                    setattr(child_doc, lf, lv)

            for fieldname, value in child_data.items():
                if fieldname in skip_child:
                    continue
                if not child_meta.has_field(fieldname):
                    continue
                df = child_meta.get_field(fieldname)
                if df.fieldtype in ("Attach", "Attach Image", "Table"):
                    child_deferred.append((fieldname, value, df))
                elif value not in (None, ""):
                    if df.fieldtype == "Link" and df.options and isinstance(value, str):
                        # Resolve label → name if value doesn't exist as a record name
                        if not frappe.db.exists(df.options, value):
                            linked_meta = frappe.get_meta(df.options)
                            title_field = linked_meta.title_field or "name"
                            resolved = frappe.db.get_value(df.options, {title_field: value}, "name")
                            if resolved:
                                value = resolved
                    child_doc.set(fieldname, value)

            child_doc.flags.ignore_permissions = True
            if child_doc.is_new():
                child_doc.insert(ignore_permissions=True)
            else:
                child_doc.save(ignore_permissions=True)

            # Second pass for child
            for fieldname, value, df in child_deferred:
                if df.fieldtype == "Table":
                    rows = value if isinstance(value, list) else []
                    child_doc.set(fieldname, [])
                    for row in (rows or []):
                        row_dict = dict(row or {})
                        for sf in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                            row_dict.pop(sf, None)
                        child_doc.append(fieldname, row_dict)
                elif df.fieldtype in ("Attach", "Attach Image"):
                    if isinstance(value, dict) and value.get("file_data"):
                        try:
                            _folder = get_file_category_for_doctype(child_doctype_name, fieldname)
                            child_doc.set(fieldname, _save_icss_file_to_minio(
                                value.get("file_name", "attachment"),
                                value["file_data"],
                                child_doctype_name,
                                child_doc.name,
                                _folder,
                            ))
                        except Exception as e:
                            frappe.log_error(f"ICSS composite child file upload error ({fieldname}): {e}", "ICSS Save")
                    elif isinstance(value, str) and value:
                        child_doc.set(fieldname, value)

            child_doc.save(ignore_permissions=True)
            child_docname = child_doc.name

            # Link child back to parent
            current_ref = parent_doc.get("sub_doctype_reference")
            if not current_ref or current_ref != child_docname:
                frappe.db.set_value(
                    DOCTYPE, parent_doc.name, "sub_doctype_reference", child_docname,
                    update_modified=False,
                )

        frappe.db.commit()

        # ── BUILD RESPONSE ───────────────────────────────────────────
        parent_doc.reload()
        response_data = parent_doc.as_dict()
        if child_doc:
            child_doc.reload()
            response_data["child_document"] = child_doc.as_dict()
            response_data["child_doctype"] = child_doctype_name

        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ✅ [ICSS] Saved (Composite)                 │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Docname     : {parent_doc.name}\n"
            f" State       : {parent_doc.workflow_state or 'Draft'}\n"
            f" Indent Type : {parent_doc.get('icss_indent_type') or '-'}\n"
            f" Applicant   : {parent_doc.get('icss_applicant_name') or '-'}\n"
            f" Child Doc   : {child_docname or '-'}\n"
            f" User        : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            "```"
        )
        return {
            "status": "success",
            "docname": parent_doc.name,
            "parent_doctype": DOCTYPE,
            "child_doctype": child_doctype_name,
            "child_docname": child_docname,
            "data": response_data,
        }

    except Exception as e:
        _tb = frappe.get_traceback()
        frappe.db.rollback()
        frappe.log_error(_tb, "ICSS Composite Save Error")
        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ❌ [ICSS] Composite Save Error              │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Exception : {type(e).__name__}: {str(e)}\n"
            f" User      : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            f"---TRACEBACK---\n{_tb}\n"
            "```",
            urgent=True,
        )
        frappe.throw(_("Failed to save ICSS: {0}").format(str(e)))


# ---------------------------------------------------------------------------
# TYPE-SPECIFIC SAVE WRAPPERS (backward compat)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def save_icss_proprietary_purchase_data(data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        data["icss_indent_type"] = INDENT_TYPE_PROPRIETARY
        if not data.get("icss_applicant_webmail_id"):
            frappe.throw(_("Applicant Webmail ID is required."))
        if not data.get("icss_account_head"):
            frappe.throw(_("Account Head is required."))
        if not (data.get("icss_items") or []):
            frappe.throw(_("At least one item is required."))
        return save_icss_data(data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Proprietary Purchase Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_standardized_purchase_data(data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        data["icss_indent_type"] = INDENT_TYPE_STANDARDIZED
        if not data.get("icss_applicant_webmail_id"):
            frappe.throw(_("Applicant Webmail ID is required."))
        if not data.get("icss_account_head"):
            frappe.throw(_("Account Head is required."))
        if not (data.get("icss_items") or []):
            frappe.throw(_("At least one item is required."))
        if not (data.get("icss_standardized_reasons") or []):
            frappe.throw(_("At least one standardized reason is required."))
        return save_icss_data(data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Standardized Purchase Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_repair_replacement_data(data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        data["icss_indent_type"] = INDENT_TYPE_REPAIR
        if not data.get("icss_applicant_webmail_id"):
            frappe.throw(_("Applicant Webmail ID is required."))
        if not data.get("icss_account_head"):
            frappe.throw(_("Account Head is required."))
        if not data.get("icss_repair_item_name"):
            frappe.throw(_("Repair Item Name is required."))
        if not data.get("icss_repair_justification"):
            frappe.throw(_("Justification is required."))
        return save_icss_data(data)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Repair Replacement Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# WORKFLOW ACTIONS
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_icss_workflow_actions(docname):
    """
    Return available workflow actions for the current user.

    Filters out generic 'Put Back' workflow table actions and appends
    dynamic put-back labels from the backend engine.
    """
    doc = frappe.get_doc(DOCTYPE, docname)
    current_state = doc.workflow_state or "Draft"
    user_roles = frappe.get_roles(frappe.session.user)

    workflow_name = frappe.db.get_value(
        "Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name"
    )
    if not workflow_name:
        return []

    workflow = frappe.get_doc("Workflow", workflow_name)
    allowed_actions = []

    for transition in workflow.get("transitions", []):
        if transition.state != current_state:
            continue
        # Skip generic "Put Back" workflow table actions (handled dynamically)
        if (transition.action or "").strip().lower() == "put back":
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

    # De-duplicate while preserving order
    seen = set()
    unique_actions = []
    for a in allowed_actions:
        if a not in seen:
            seen.add(a)
            unique_actions.append(a)

    # Append dynamic put-back action labels
    put_back_rows = _get_available_icss_put_back_action_rows(doc, user_roles)
    for row in put_back_rows:
        label = row["label"]
        if label not in seen:
            seen.add(label)
            unique_actions.append(label)

    return unique_actions


@frappe.whitelist()
def perform_icss_action(docname, action):
    """
    Execute a workflow action on an ICSS document.

    Special routing:
    - Initial submit (Draft → *): backend decides next state based on user roles.
    - HoS forward (Pending HoS Approval → *): backend decides next state based on amount.
    - Dean Approve: blocked if Director approval required but PDF not uploaded.
    - Put Back to <target>: delegated to ``put_back_icss``.
    """
    try:
        # Delegate put-back actions
        if action.startswith("Put Back to "):
            target_label = action[len("Put Back to "):]
            if target_label in ICSS_PUT_BACK_TARGETS:
                return put_back_icss(docname, target_label)
            frappe.throw(_("Unknown put-back target: {0}").format(target_label))

        doc = frappe.get_doc(DOCTYPE, docname)
        current_state = doc.workflow_state or "Draft"
        user_roles = frappe.get_roles(frappe.session.user)

        workflow_name = frappe.db.get_value(
            "Workflow", {"document_type": DOCTYPE, "is_active": 1}, "name"
        )
        if not workflow_name:
            frappe.throw(_("No active workflow found for {0}.").format(DOCTYPE))

        workflow = frappe.get_doc("Workflow", workflow_name)

        # ── STEP 1: find matching transition (validates role permission) ──
        next_state = None
        matched_transition = None

        for t in workflow.transitions:
            if t.state != current_state or t.action != action:
                continue
            allowed_roles = t.get("allowed") or []
            if isinstance(allowed_roles, str):
                allowed_roles = [allowed_roles]
            if not (any(r in user_roles for r in allowed_roles) or "System Manager" in user_roles):
                continue
            if t.condition:
                try:
                    if not frappe.safe_eval(t.condition, None, {"doc": doc}):
                        continue
                except Exception as e:
                    frappe.log_error(f"ICSS workflow condition error: {e}", "ICSS Workflow")
                    continue
            next_state = t.next_state
            matched_transition = t
            break

        if not next_state:
            frappe.throw(
                _(
                    "No valid transition found for action '{0}' from state '{1}' "
                    "with your current roles."
                ).format(action, current_state)
            )

        # ── STEP 2: backend routing overrides ────────────────────────────
        if current_state == "Draft":
            # Initial submit routing: permanent employees skip PI stage
            next_state = _resolve_initial_submit_next_state(user_roles)

        elif current_state == "Pending HoS Approval":
            # Amount-based routing
            next_state = _resolve_hos_next_state(doc)

        # ── STEP 3: Director approval gate ───────────────────────────────
        if action == "Approve" and current_state == "Pending Dean Approval":
            if _is_icss_director_approval_required(doc):
                if not (doc.get("director_signed_pdf") or "").strip():
                    frappe.throw(
                        _(
                            "Cannot approve: Director approval is required and the "
                            "Director-signed PDF has not been uploaded by Staff yet."
                        )
                    )

        # ── STEP 4: Apply state change ────────────────────────────────────
        frappe.db.set_value(
            DOCTYPE, docname, "workflow_state", next_state, update_modified=True
        )
        doc.reload()
        doc.flags.icss_workflow_action = action

        # Handle docstatus transitions if workflow state requires submission/cancellation
        state_doc = next(
            (s for s in workflow.states if s.state == next_state), None
        )
        if state_doc and state_doc.doc_status == "1" and doc.docstatus == 0:
            doc.flags.skip_icss_subdoctype_sync = True
            doc.submit()
        elif state_doc and state_doc.doc_status == "2" and doc.docstatus != 2:
            doc.flags.skip_icss_subdoctype_sync = True
            doc.cancel()

        # Sync child workflow state
        doc._sync_sub_doctype_workflow_state(next_state)

        frappe.db.commit()

        doc.reload()

        # db.set_value bypasses on_update hooks, so check_workflow_and_publish never fires
        # naturally. Explicitly call it here so Kafka staging docs are published when the
        # workflow state matches their trigger_state (e.g. "Pending PO Generation").
        try:
            from rndopsapp.rndopsapp.commitPayment import check_workflow_and_publish as _kafka_check
            doc._doc_before_save = None  # clear so idempotency guard doesn't block this explicit call
            _kafka_check(doc)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "ICSS Kafka Publish Error")

        response_data = doc.as_dict()

        # Include nested child data
        sub_ref = doc.get("sub_doctype_reference")
        indent_type = doc.get("icss_indent_type")
        if sub_ref and indent_type:
            child_doctype_name = SUB_DOCTYPE_MAP.get(indent_type)
            if child_doctype_name and frappe.db.exists(child_doctype_name, sub_ref):
                try:
                    child_doc = frappe.get_doc(child_doctype_name, sub_ref)
                    response_data["child_document"] = child_doc.as_dict()
                    response_data["child_doctype"] = child_doctype_name
                except Exception:
                    pass

        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ✅ [ICSS] Workflow Action                   │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time        : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Docname     : {docname}\n"
            f" Action      : {action}\n"
            f" New State   : {next_state}\n"
            f" Indent Type : {doc.get('icss_indent_type') or '-'}\n"
            f" Applicant   : {doc.get('icss_applicant_name') or '-'}\n"
            f" User        : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            "```"
        )
        return {
            "status": "success",
            "message": f"Action '{action}' completed. New state: {next_state}",
            "docname": docname,
            "workflow_state": next_state,
            "next_actions": get_icss_workflow_actions(docname),
            "data": response_data,
        }

    except Exception as e:
        _tb = frappe.get_traceback()
        frappe.db.rollback()
        frappe.log_error(_tb, "ICSS Action Error")
        notify_mattermost(
            "```\n"
            "┌──────────────────────────────────────────────┐\n"
            "│  ❌ [ICSS] Workflow Action Error             │\n"
            "├──────────────────────────────────────────────┤\n"
            f" Time      : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} IST\n"
            f" Docname   : {docname}\n"
            f" Action    : {action}\n"
            f" Exception : {type(e).__name__}: {str(e)}\n"
            f" User      : {frappe.session.user}\n"
            "└──────────────────────────────────────────────┘\n"
            f"---TRACEBACK---\n{_tb}\n"
            "```",
            urgent=True,
        )
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_icss(docname):
    """Submit an ICSS document via the workflow Submit action."""
    return perform_icss_action(docname, "Submit")


# ---------------------------------------------------------------------------
# PUT-BACK ENGINE
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_available_icss_put_back_actions(docname):
    """
    Return the put-back actions available to the current user for an ICSS document.

    Frontend uses this to render a put-back dropdown.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        actions = _get_available_icss_put_back_action_rows(doc)
        return {
            "status": "success",
            "docname": docname,
            "current_state": doc.workflow_state or "Draft",
            "actions": actions,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Put-Back Actions Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def put_back_icss(docname, target, reason=None):
    """
    Apply a backward state movement (put-back) on an ICSS document.

    Validates role, current state, and allowed target before applying.
    Creates an audit comment and syncs child doctype workflow state.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        current_state = doc.workflow_state or "Draft"
        user_roles = frappe.get_roles(frappe.session.user)

        # Validate blocked states
        if current_state in PUT_BACK_BLOCKED_STATES:
            frappe.throw(
                _("Put-back is not allowed from state '{0}'.").format(current_state)
            )

        # Validate target
        next_state = ICSS_PUT_BACK_TARGETS.get(target)
        if not next_state:
            frappe.throw(_("Unknown put-back target: {0}").format(target))

        # Validate rules for current state
        rules = ICSS_PUT_BACK_RULES.get(current_state)
        if not rules:
            frappe.throw(
                _("Put-back is not configured for state '{0}'.").format(current_state)
            )

        allowed_roles = rules.get("roles", [])
        if not (any(r in user_roles for r in allowed_roles) or "System Manager" in user_roles):
            frappe.throw(_("You do not have permission to put back from '{0}'.").format(current_state))

        if target not in rules.get("targets", []):
            frappe.throw(
                _("Put-back to '{0}' is not allowed from '{1}'.").format(target, current_state)
            )

        # Clear Director approval fields when putting back from Dean stage
        _clear_icss_director_fields_for_put_back(docname, current_state)

        # Apply state change directly
        frappe.db.set_value(DOCTYPE, docname, "workflow_state", next_state, update_modified=True)

        # Sync child doctype
        doc.reload()
        doc._sync_sub_doctype_workflow_state(next_state)

        # Audit trail
        _add_icss_put_back_comment(docname, target, next_state, current_state, reason)

        frappe.db.commit()

        doc.reload()
        response_data = doc.as_dict()

        sub_ref = doc.get("sub_doctype_reference")
        indent_type = doc.get("icss_indent_type")
        if sub_ref and indent_type:
            child_doctype_name = SUB_DOCTYPE_MAP.get(indent_type)
            if child_doctype_name and frappe.db.exists(child_doctype_name, sub_ref):
                try:
                    response_data["child_document"] = frappe.get_doc(
                        child_doctype_name, sub_ref
                    ).as_dict()
                    response_data["child_doctype"] = child_doctype_name
                except Exception:
                    pass

        return {
            "status": "success",
            "docname": docname,
            "from": current_state,
            "to": next_state,
            "target": target,
            "next_actions": get_icss_workflow_actions(docname),
            "data": response_data,
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ICSS Put-Back Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# DIRECTOR APPROVAL APIS
# ---------------------------------------------------------------------------


@frappe.whitelist()
def update_send_to_director_icss(docname, send_to_director):
    """
    Dean marks an ICSS as requiring offline Director approval.

    Allowed roles: Dean, RnD / System Manager.
    ICSS must be in 'Pending Dean Approval'.
    Director approval threshold must be met.
    One-way: cannot clear once set.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        user_roles = frappe.get_roles(frappe.session.user)

        if not (any(r in user_roles for r in ["Dean, RnD", "System Manager"])):
            frappe.throw(_("Only Dean, RnD or System Manager can mark send to Director."))

        if (doc.workflow_state or "") != "Pending Dean Approval":
            frappe.throw(
                _("Send to Director can only be set when ICSS is in 'Pending Dean Approval'.")
            )

        if not _is_icss_director_approval_required(doc):
            frappe.throw(
                _("Director approval is not required for this ICSS (below threshold).")
            )

        send_val = int(send_to_director) if send_to_director is not None else 0

        # One-way: cannot clear
        if doc.send_to_director and not send_val:
            frappe.throw(_("Cannot clear 'Send to Director' once it has been set."))

        frappe.db.set_value(
            DOCTYPE,
            docname,
            {
                "send_to_director": send_val,
                "director_approval_required": 1,
            },
            update_modified=True,
        )
        frappe.db.commit()

        return {
            "status": "success",
            "docname": docname,
            "workflow_state": doc.workflow_state,
            "send_to_director": send_val,
            "director_approval_required": 1,
            "director_signed_pdf": doc.get("director_signed_pdf"),
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ICSS Update Send To Director Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def attach_director_pdf_icss(docname, file_url=None, file_name=None, file_data=None):
    """
    Staff/R&D attaches the Director-approved signed ICSS PDF.

    Allowed roles: staff, RnD / System Manager.
    ICSS must be in 'Pending Dean Approval' with send_to_director = 1.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        user_roles = frappe.get_roles(frappe.session.user)

        rnd_roles = ["staff, RnD", "RnD Staff", "R&D Staff", "System Manager"]
        if not any(r in user_roles for r in rnd_roles):
            frappe.throw(_("Only Staff/R&D or System Manager can attach the Director PDF."))

        if (doc.workflow_state or "") != "Pending Dean Approval":
            frappe.throw(
                _("Director PDF can only be attached when ICSS is in 'Pending Dean Approval'.")
            )

        if not _is_icss_director_approval_required(doc):
            frappe.throw(_("Director approval is not required for this ICSS."))

        if not doc.get("send_to_director"):
            frappe.throw(
                _("Please mark 'Send to Director' first before attaching the signed PDF.")
            )

        # Resolve file URL
        resolved_url = None
        if file_url:
            resolved_url = str(file_url).strip()
        elif file_name and file_data:
            resolved_url = _save_icss_file_to_minio(
                file_name, file_data, DOCTYPE, docname, "director_pdf", is_private=True
            )

        if not resolved_url:
            frappe.throw(_("A file URL or file data must be provided."))

        frappe.db.set_value(
            DOCTYPE, docname, "director_signed_pdf", resolved_url, update_modified=True
        )
        frappe.db.commit()

        return {
            "status": "success",
            "docname": docname,
            "workflow_state": doc.workflow_state,
            "send_to_director": 1,
            "director_approval_required": 1,
            "director_signed_pdf": resolved_url,
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ICSS Attach Director PDF Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_pending_director_uploads_icss():
    """
    Return ICSS documents in 'Pending Dean Approval' that have been flagged for
    Director PDF upload.  Includes records with and without the PDF so Staff/R&D
    can view or replace.
    """
    try:
        records = frappe.get_all(
            DOCTYPE,
            filters={
                "workflow_state": "Pending Dean Approval",
                "send_to_director": 1,
            },
            fields=[
                "name",
                "icss_indent_type",
                "icss_applicant_name",
                "icss_applicant_webmail_id",
                "project_ref",
                "project_no",
                "icss_account_head",
                "icss_other_account_head",
                "director_signed_pdf",
                "director_approval_required",
                "send_to_director",
                "workflow_state",
                "modified",
            ],
            order_by="modified desc",
        )
        return {"status": "success", "data": records}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Pending Director Uploads Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_icss_director_approval_status(docname):
    """
    Return Director approval status and computed fields for a single ICSS document.
    Useful for Dean UI to show the correct approval controls.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        approval_amount = _get_icss_approval_amount(doc)
        director_required = _is_icss_director_approval_required(doc)

        account_head = doc.get("icss_account_head") or doc.get("icss_other_account_head") or ""
        account_head_text = str(account_head)
        try:
            bh = frappe.db.get_value("Budget Head", account_head, "budget_head")
            if bh:
                account_head_text = bh
        except Exception:
            pass

        return {
            "status": "success",
            "docname": docname,
            "workflow_state": doc.workflow_state,
            "approval_amount": approval_amount,
            "account_head": account_head_text,
            "director_approval_required": 1 if director_required else 0,
            "send_to_director": doc.get("send_to_director") or 0,
            "director_signed_pdf": doc.get("director_signed_pdf"),
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ICSS Director Approval Status Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# SIGNED PO DELIVERY
# ---------------------------------------------------------------------------


@frappe.whitelist()
def upload_icss_signed_po(docname, file_url=None, file_name=None, file_data=None):
    """
    Staff/R&D uploads the final signed/generated PO file and moves ICSS to
    'PO Delivered'.

    Accepts:
    - ``file_url``: already-uploaded MinIO path
    - ``file_name`` + ``file_data``: base64 upload
    - Multipart upload is handled by the Frappe file upload handler before this
      API is called; the resulting URL can then be passed as ``file_url``.
    """
    try:
        doc = frappe.get_doc(DOCTYPE, docname)
        current_state = doc.workflow_state or ""

        if current_state not in ("PO Generated", "PO Delivered"):
            frappe.throw(
                _(
                    "Signed PO can only be uploaded when ICSS is in 'PO Generated' "
                    "(current state: {0})."
                ).format(current_state)
            )

        # Resolve file URL
        resolved_url = None
        if file_url:
            resolved_url = str(file_url).strip()
        elif file_name and file_data:
            resolved_url = _save_icss_file_to_minio(
                file_name, file_data, DOCTYPE, docname, "signed_po", is_private=False
            )

        if not resolved_url:
            frappe.throw(_("A file URL or file data must be provided."))

        # Update fields and move to PO Delivered
        frappe.db.set_value(
            DOCTYPE,
            docname,
            {
                "icss_signed_po_file": resolved_url,
                "workflow_state": "PO Delivered",
            },
            update_modified=True,
        )

        # Sync child workflow state
        doc.reload()
        doc._sync_sub_doctype_workflow_state("PO Delivered")

        frappe.db.commit()

        return {
            "status": "success",
            "workflow_state": "PO Delivered",
            "signed_po_attachment": resolved_url,
            "icss_signed_po_file": resolved_url,
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "ICSS Upload Signed PO Error")
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# USER DETAILS
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_user_details_icss(user_email):
    """Fetch user details for auto-populating applicant fields."""
    if not user_email:
        frappe.throw(_("User Email is required."))
    try:
        user_email = str(user_email).strip('"').strip("'")
        user_doc = frappe.get_doc("User", user_email)
        result = {
            "full_name": user_doc.full_name,
            "department_name": user_doc.department_name,
            "designation_name": getattr(user_doc, "designation_name", ""),
        }
        if user_doc.department_name:
            try:
                dept_doc = frappe.get_doc("Department_prornd", user_doc.department_name)
                result["department_name"] = dept_doc.dept_name
            except Exception:
                pass
        return result
    except frappe.DoesNotExistError:
        return None
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ICSS Error fetching user details")
        frappe.throw(_("An error occurred while fetching user details."))
