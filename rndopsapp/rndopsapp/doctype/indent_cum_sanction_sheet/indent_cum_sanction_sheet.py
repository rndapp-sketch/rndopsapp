# Copyright (c) 2025, rndops and contributors
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


# =============================================================================
# INDENT TYPE CONSTANTS
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

# Sub-DocType Mapping
SUB_DOCTYPE_MAP = {
	INDENT_TYPE_PROPRIETARY: "proprietary_purchase",
	INDENT_TYPE_STANDARDIZED: "standerdized_purchase",
	INDENT_TYPE_REPAIR: "Repair Replacement",
	INDENT_TYPE_AMC: "Annual Maintenance Contract",
	INDENT_TYPE_RATE_CONTRACT: "Rate Contract",
}

# Workflow Mapping
WORKFLOW_MAP = {
	INDENT_TYPE_PROPRIETARY: "Proprietary Purchase Workflow",
	INDENT_TYPE_STANDARDIZED: "Standardized Purchase Workflow",
	INDENT_TYPE_REPAIR: "Repair Replacement Workflow",
	INDENT_TYPE_AMC: "AMC Workflow",
	INDENT_TYPE_RATE_CONTRACT: "Rate Contract Workflow",
}


# =============================================================================
# DOCUMENT CONTROLLER
# =============================================================================


class IndentCumSanctionSheet(Document):
	def before_insert(self):
		"""Hook before document insertion."""
		self._validate_indent_type()

	def validate(self):
		"""Server-side validations: calculate totals and type-specific checks."""
		self._validate_indent_type()
		self._validate_indent_type_change()
		self.calculate_item_totals()
		self.calculate_repair_total()
		self.calculate_amc_total()

	def before_save(self):
		"""Hook before saving - update sub-doctype only for existing records."""
		if self.get("icss_indent_type") and not self.is_new():
			self._sync_sub_doctype()

	def after_insert(self):
		"""Hook after insertion - create sub-doctype once parent exists in DB."""
		if self.get("icss_indent_type"):
			self._sync_sub_doctype()
		self._log_lifecycle_event("Created")

	def on_update(self):
		"""Hook after save/update - publish save or workflow events."""
		workflow_action = getattr(self.flags, "icss_workflow_action", None)
		if workflow_action:
			self._log_lifecycle_event(f"Workflow Action: {workflow_action}")
			self.flags.icss_workflow_action = None
			return

		if not self.is_new():
			self._log_lifecycle_event("Saved")

	def on_submit(self):
		"""Hook on document submission - trigger sub-doctype workflow."""
		if self.get("sub_doctype_reference") and self.get("icss_indent_type"):
			self._perform_sub_doctype_workflow_action("Submit")
		workflow_action = getattr(self.flags, "icss_workflow_action", None)
		event_label = f"Workflow Action: {workflow_action}" if workflow_action else "Submitted"
		self._log_lifecycle_event(event_label)
		self.flags.icss_workflow_action = None

	def on_cancel(self):
		"""Hook on cancellation - publish cancel or workflow events."""
		workflow_action = getattr(self.flags, "icss_workflow_action", None)
		event_label = f"Workflow Action: {workflow_action}" if workflow_action else "Cancelled"
		self._log_lifecycle_event(event_label)
		self.flags.icss_workflow_action = None

	def on_update_after_submit(self):
		"""Hook after update on submitted document."""
		if self.get("sub_doctype_reference") and self.get("icss_indent_type"):
			self._sync_sub_doctype_after_submit()
		workflow_action = getattr(self.flags, "icss_workflow_action", None)
		if workflow_action:
			self._log_lifecycle_event(f"Workflow Action: {workflow_action}")
			self.flags.icss_workflow_action = None
			return
		self._log_lifecycle_event("Updated After Submit")

	# -------------------------------------------------------------------------
	# CORE DESIGN RULE: CENTRALIZED SUB-DOCTYPE MANAGEMENT
	# -------------------------------------------------------------------------

	def _validate_indent_type(self):
		"""Validate that indent_type is set and valid."""
		if not self.get("icss_indent_type"):
			return

		if self.get("icss_indent_type") not in INDENT_TYPES:
			frappe.throw(_("Invalid Indent Type: {0}").format(self.get("icss_indent_type")))

	def _validate_indent_type_change(self):
		"""Block indent_type changes after submission."""
		if self.docstatus > 0 and self.has_value_changed("icss_indent_type"):
			frappe.throw(_("Cannot change Indent Type after submission."))

	def _sync_sub_doctype(self):
		"""
		Create or update the sub-doctype record automatically.
		This is the single controller method for all sub-doctype operations.
		"""
		sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))

		if not sub_doctype_name:
			frappe.log_error(
				f"No sub-doctype mapping found for indent type: {self.get('icss_indent_type')}",
				"ICSS Sub-DocType Sync Error",
			)
			return

		# Check if sub-doctype record already exists
		if self.get("sub_doctype_reference"):
			try:
				sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))
			except frappe.DoesNotExistError:
				sub_doc = None
		else:
			sub_doc = None

		# Create new sub-doctype record if it doesn't exist
		if not sub_doc:
			sub_doc = self._create_sub_doctype_record(sub_doctype_name)
		else:
			# Update existing sub-doctype record
			self._map_parent_data_to_subdoctype(sub_doc)

		# Save sub-doctype
		self._save_sub_doctype(sub_doc)

		# Update parent reference
		if not self.get("sub_doctype_reference"):
			self.db_set("sub_doctype_reference", sub_doc.name, update_modified=False)

	def _create_sub_doctype_record(self, sub_doctype_name):
		"""
		Internal method: Create a new sub-doctype record.
		Must be called only from parent controller.
		"""
		sub_doc = frappe.new_doc(sub_doctype_name)

		# Assign mandatory linkage fields
		sub_doc.indent_cum_sanction_sheet_id = self.name
		sub_doc.project_ref = self.get("project_ref")
		sub_doc.project_no = self.get("project_no")
		sub_doc.indent_type = self.get("icss_indent_type")

		# Map parent data to sub-doctype
		self._map_parent_data_to_subdoctype(sub_doc)

		frappe.logger().info(f"ICSS: Created sub-doctype {sub_doctype_name} for parent {self.name}")

		return sub_doc

	def _map_parent_data_to_subdoctype(self, sub_doc):
		"""
		Internal method: Map relevant parent fields into the sub-doctype.
		Field mapping logic based on indent type.
		"""
		# Common fields mapping
		if hasattr(sub_doc, "project_ref"):
			sub_doc.project_ref = self.get("project_ref")
		if hasattr(sub_doc, "project_no"):
			sub_doc.project_no = self.get("project_no")
		if hasattr(sub_doc, "indent_cum_sanction_sheet_id"):
			sub_doc.indent_cum_sanction_sheet_id = self.name
		if hasattr(sub_doc, "indent_type"):
			sub_doc.indent_type = self.get("icss_indent_type")

		frappe.logger().info(f"ICSS: Mapped parent data to sub-doctype {sub_doc.doctype} - {sub_doc.name}")

	def _save_sub_doctype(self, sub_doc):
		"""
		Internal method: Save the sub-doctype record.
		Must be called only from parent controller.
		"""
		try:
			sub_doc.flags.ignore_permissions = True
			if sub_doc.is_new():
				sub_doc.insert(ignore_permissions=True)
			else:
				sub_doc.save(ignore_permissions=True)

			frappe.logger().info(f"ICSS: Saved sub-doctype {sub_doc.doctype} - {sub_doc.name}")
		except Exception as e:
			frappe.log_error(
				f"Error saving sub-doctype {sub_doc.doctype}: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Save Error",
			)
			frappe.throw(_("Failed to save sub-doctype record: {0}").format(str(e)))

	def _perform_sub_doctype_workflow_action(self, action):
		"""
		Internal method: Trigger workflow transition on the sub-doctype.
		Must be called only from parent controller.
		"""
		if not self.get("sub_doctype_reference"):
			return

		sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
		if not sub_doctype_name:
			return

		try:
			sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))

			# Get workflow for the sub-doctype
			workflow_name = WORKFLOW_MAP.get(self.get("icss_indent_type"))
			if not workflow_name:
				frappe.logger().info(
					f"ICSS: No workflow mapping found for indent type: {self.get('icss_indent_type')}"
				)
				return

			# Check if workflow exists
			if not frappe.db.exists("Workflow", {"document_type": sub_doctype_name, "is_active": 1}):
				frappe.logger().info(f"ICSS: No active workflow found for {sub_doctype_name}")
				return

			# Apply workflow action
			workflow = frappe.get_doc("Workflow", {"document_type": sub_doctype_name, "is_active": 1})
			current_state = sub_doc.workflow_state or "Draft"

			# Find matching transition
			for transition in workflow.transitions:
				if transition.state == current_state and transition.action == action:
					sub_doc.workflow_state = transition.next_state

					# Handle docstatus transitions
					state_doc = next((s for s in workflow.states if s.state == transition.next_state), None)
					if state_doc and state_doc.doc_status == "1" and sub_doc.docstatus == 0:
						sub_doc.submit()
					elif state_doc and state_doc.doc_status == "2" and sub_doc.docstatus != 2:
						sub_doc.cancel()
					else:
						sub_doc.save(ignore_permissions=True)

					break

			frappe.logger().info(
				f"ICSS: Performed workflow action '{action}' on sub-doctype {sub_doc.doctype} - {sub_doc.name}"
			)

		except Exception as e:
			frappe.log_error(
				f"Error performing workflow action on sub-doctype: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Workflow Error",
			)

	def _sync_sub_doctype_after_submit(self):
		"""
		Internal method: Sync sub-doctype after parent update.
		Must be called only from parent controller.
		"""
		if not self.get("sub_doctype_reference"):
			return

		sub_doctype_name = SUB_DOCTYPE_MAP.get(self.get("icss_indent_type"))
		if not sub_doctype_name:
			return

		try:
			sub_doc = frappe.get_doc(sub_doctype_name, self.get("sub_doctype_reference"))
			self._map_parent_data_to_subdoctype(sub_doc)

			# Update without changing docstatus
			sub_doc.flags.ignore_permissions = True
			sub_doc.save(ignore_permissions=True)

			frappe.logger().info(f"ICSS: Synced sub-doctype after submit {sub_doc.doctype} - {sub_doc.name}")

		except Exception as e:
			frappe.log_error(
				f"Error syncing sub-doctype after submit: {str(e)}\n{frappe.get_traceback()}",
				"ICSS Sub-DocType Sync Error",
			)

	def _log_lifecycle_event(self, event_label):
		"""Write ICSS lifecycle changes to server logs for debugging."""
		try:
			user_id = frappe.session.user if frappe.session.user and frappe.session.user != "Guest" else None
			user_display = user_id or "System"
			log_payload = {
				"event": event_label,
				"document": self.name,
				"workflow_state": self.workflow_state or "Draft",
				"docstatus": self.docstatus,
				"indent_type": self.get("icss_indent_type"),
				"project_ref": self.get("project_ref"),
				"project_no": self.get("project_no"),
				"triggered_by": user_display,
			}
			frappe.logger("icss_lifecycle").info(json.dumps(log_payload, default=str))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ICSS Lifecycle Log Error")

	# -------------------------------------------------------------------------
	# CALCULATION METHODS (Existing)
	# -------------------------------------------------------------------------

	def calculate_item_totals(self):
		"""Calculate row amounts for the items table and overall basic value."""
		total_basic = 0
		items = self.get("icss_items") or []
		for row in items:
			base = flt(row.icss_qty) * flt(row.icss_rate)
			discount = base * flt(row.icss_discount_percent) / 100
			gst = (base - discount) * flt(row.icss_gst_percent) / 100
			row.icss_amount = base - discount + gst
			total_basic += flt(row.icss_amount)

		self.icss_total_basic_value = total_basic

		# Grand total = basic + packing + freight + other
		self.icss_grand_total = (
			flt(self.icss_total_basic_value)
			+ flt(self.get("icss_packing_charges"))
			+ flt(self.get("icss_freight_charges"))
			+ flt(self.get("icss_other_charges"))
		)

	def calculate_repair_total(self):
		"""Grand total for repair section."""
		self.icss_repair_grand_total = flt(self.get("icss_repair_expenditure")) + flt(
			self.get("icss_repair_other_charges")
		)

	def calculate_amc_total(self):
		"""Grand total for AMC section."""
		amc_subtotal = flt(self.get("icss_amc_value")) + flt(self.get("icss_amc_other_charges"))
		gst_amount = amc_subtotal * flt(self.get("icss_amc_gst_percent")) / 100
		self.icss_amc_grand_total = amc_subtotal + gst_amount


# =============================================================================
# API ENDPOINTS
# =============================================================================


@frappe.whitelist()
def get_icss_indent_types():
	"""
	Returns all available indent type options for the Indent Cum Sanction Sheet.

	Returns:
		list[dict]: Each dict has ``value`` and ``label`` keys.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
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
# GET FIELDS  (Standard metadata API)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_icss_fields(doc_name=None):
	"""
	API to return Indent Cum Sanction Sheet field metadata, prefill data,
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
	else:
		# Prefill current user details
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

	# Declaration checkboxes default to unchecked
	prefill_data.setdefault("icss_declaration_sanctioned_accept", 0)
	prefill_data.setdefault("icss_declaration_nonsanctioned_accept", 0)
	prefill_data.setdefault("icss_repair_declaration_checkbox", 0)
	prefill_data.setdefault("icss_amc_declaration", 0)

	# ---- Link Options ----

	# Account Head
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

	# Users (for applicant / applying-for fields)
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

	# Departments
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
		for script in scripts:
			client_scripts.append(
				{
					"name": script.name,
					"script": script.script,
					"view": script.view,
				}
			)
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
				"trigger_fields": [
					"icss_total_basic_value",
					"icss_packing_charges",
					"icss_freight_charges",
					"icss_other_charges",
				],
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
# SAVE DATA  (Generic create / update)
# ---------------------------------------------------------------------------


@frappe.whitelist()
def save_icss_data(data):
	"""
	Creates or updates an Indent Cum Sanction Sheet document.
	Handles child tables (``icss_items``, ``icss_standardized_reasons``)
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

					# Handle file uploads inside child rows
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
										f"ICSS Child File Error ({cf.fieldname}): {e}",
										"ICSS Save Error",
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
							f"ICSS File Upload Error ({fieldname}): {str(e)}",
							"ICSS Save Error",
						)
				elif isinstance(value, str):
					# Keep existing URL
					doc.set(fieldname, value)

		# 5. Final Save
		doc.save(ignore_permissions=True)
		frappe.db.commit()

		return {"status": "success", "docname": doc.name}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Save Error")
		frappe.throw(_("Failed to save Indent Cum Sanction Sheet: {0}").format(str(e)))


@frappe.whitelist()
def save_icss_composite_data(data):
	"""
	Backward-compatible API alias for legacy clients.
	Delegates to ``save_icss_data``.
	"""
	return save_icss_data(data)


# ---------------------------------------------------------------------------
# INDENT-TYPE-SPECIFIC SAVE APIs
# ---------------------------------------------------------------------------


@frappe.whitelist()
def save_icss_proprietary_purchase_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Proprietary Purchase with Proprietary Certificate from the OEM**.

	Validates proprietary-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the proprietary option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_PROPRIETARY

		# Proprietary-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_items") or len(data.get("icss_items", [])) == 0:
			frappe.throw(_("At least one item is required in the Items table."))

		frappe.logger().info(f"ICSS Proprietary Purchase: Creating/updating for user {frappe.session.user}")

		return save_icss_data(data)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Proprietary Purchase Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_standardized_purchase_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Standardised / Emergent Purchase**.

	Validates standardized-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the standardized option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_STANDARDIZED

		# Standardized-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_items") or len(data.get("icss_items", [])) == 0:
			frappe.throw(_("At least one item is required in the Items table."))

		if not data.get("icss_standardized_reasons") or len(data.get("icss_standardized_reasons", [])) == 0:
			frappe.throw(_("At least one reason is required in the Standardized Reasons table."))

		frappe.logger().info(f"ICSS Standardized Purchase: Creating/updating for user {frappe.session.user}")

		return save_icss_data(data)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "ICSS Standardized Purchase Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def save_icss_repair_replacement_data(data):
	"""
	Creates or processes an Indent Cum Sanction Sheet for
	**Repair / Replacement**.

	Validates repair-specific required fields before delegating to
	the generic ``save_icss_data``.

	Args:
		data (str | dict): JSON payload. Must include ``icss_indent_type``
			set to the repair/replacement option.

	Returns:
		dict: ``{"status": "success", "docname": "..."}`` or error.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	try:
		if isinstance(data, str):
			data = json.loads(data)

		# Force correct indent type
		data["icss_indent_type"] = INDENT_TYPE_REPAIR

		# Repair-specific validation
		if not data.get("icss_applicant_webmail_id"):
			frappe.throw(_("Applicant Webmail ID is required."))

		if not data.get("icss_account_head"):
			frappe.throw(_("Account Head is required."))

		if not data.get("icss_repair_item_name"):
			frappe.throw(_("Repair Item Name is required for Repair/Replacement indent."))

		if not data.get("icss_repair_justification"):
			frappe.throw(_("Justification is required for Repair/Replacement indent."))

		frappe.logger().info(f"ICSS Repair/Replacement: Creating/updating for user {frappe.session.user}")

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
	Get available workflow actions for the current user based on
	the document's current workflow state.

	Args:
		docname (str): Name of the Indent Cum Sanction Sheet document.

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
def perform_icss_action(docname, action):
	"""
	Executes the selected workflow action and updates the document state.

	Args:
		docname (str): Name of the Indent Cum Sanction Sheet document.
		action  (str): Workflow action to perform (e.g. "Approve", "Reject").

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
			frappe.throw(_("No active workflow found for {0}.").format(DOCTYPE))

		workflow = frappe.get_doc("Workflow", workflow_name)

		next_state = None
		matched_transition = None

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
					except Exception as e:
						frappe.log_error(
							f"ICSS Workflow condition error: {str(e)}",
							"ICSS Workflow Error",
						)
						continue

				next_state = t.next_state
				matched_transition = t
				break

		if not next_state:
			frappe.throw(
				_(
					"No valid transition found for action '{0}' from state "
					"'{1}' matching your role and conditions."
				).format(action, current_state)
			)

		doc.workflow_state = next_state
		doc.flags.icss_workflow_action = action

		# Handle docstatus transitions (submit / cancel)
		state_doc = next((s for s in workflow.states if s.state == next_state), None)

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
			"next_actions": get_icss_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "ICSS Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def submit_icss(docname):
	"""
	Submit an Indent Cum Sanction Sheet document using Workflow transitions.

	Args:
		docname (str): Name of the document to submit.

	Returns:
		dict: Result from ``perform_icss_action``.

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
	return perform_icss_action(docname, "Submit")


# ---------------------------------------------------------------------------
# USER DETAILS HELPER
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_user_details_icss(user_email):
	"""
	Fetch user details (name, department, designation) for auto-populating
	applicant and applying-for fields.

	Args:
		user_email (str): The user's email / webmail ID.

	Returns:
		dict | None: ``{"full_name": ..., "department_name": ..., "designation_name": ...}``

	Authentication:
		Requires logged-in user (``@frappe.whitelist``).
	"""
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
		frappe.log_error(frappe.get_traceback(), _("ICSS Error fetching user details"))
		frappe.throw(_("An error occurred while fetching user details."))
