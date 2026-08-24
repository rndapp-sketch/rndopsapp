# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from rndopsapp.rndopsapp.kafka.producer.reimbursement import publish_commit_batch
from rndopsapp.rndopsapp.kafka.producer.reimbursement.batch_dto import AccountHeadCommitBatchItemDTO
from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import get_project_number, get_module_id

COMMIT_PAYMENT_API = "http://172.16.134.81:18080/api/commit-payment-transactions"


class PoCommitAdjustment(Document):
	pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_po_context(purchase_order_number):
	"""Return (dp_name, project_no) from a linked sanction_sheet."""
	if not purchase_order_number:
		return None, None
	try:
		ss = frappe.get_doc("sanction_sheet", purchase_order_number)
		dp_name = ss.get("app_id")
		project_no = ss.get("project_no") or (
			frappe.db.get_value("Direct Purchase", dp_name, "project_no") if dp_name else None
		)
		return dp_name, project_no
	except Exception:
		return None, None


def _fetch_transactions(project_number, account_head_id):
	"""
	GET COMMIT_PAYMENT_API for the given project + account head.
	Returns the transaction list, or [] on any error.
	"""
	import requests
	if not project_number or not account_head_id:
		return []
	try:
		resp = requests.get(
			COMMIT_PAYMENT_API,
			params={"projectNumber": project_number, "accountHeadId": account_head_id},
			headers={"Accept": "application/json"},
			timeout=10,
		)
		resp.raise_for_status()
		return resp.json() or []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Po Commit Adjustment: COMMIT_PAYMENT_API failed")
		return []


def _publish_batch_to_kafka(doc, project_number, account_head_id, transactions):
	"""
	Build AccountHeadCommitBatchItemDTO items and publish them as a single
	batch Kafka event to ``account-head-commit-batch-events``.

	- other_expenses == 'Yes' with settlement_accounts rows: one item per row.
	- Any other case: single item from the main doc fields; commitAmount is
	  taken from the referenced transaction (transactionId == doc.ref_details).

	Returns True if published successfully.
	"""
	ref_details_val = int(flt(doc.ref_details)) if doc.ref_details else None
	module_id       = get_module_id("Direct Purchase")
	module_id_str   = str(module_id) if module_id else None

	settlement_rows = [
		r for r in doc.get("settlement_accounts", [])
		if r.account_head and flt(r.amount)
	]

	items = []

	po_total = flt(doc.po_total_value)

	if doc.other_expenses == "Yes" and settlement_rows:
		for idx, row in enumerate(settlement_rows):
			row_account_head_id = frappe.db.get_value("Budget Head", row.account_head, "id")
			items.append(AccountHeadCommitBatchItemDTO(
				transactionCommitNumber=      idx + 1,
				projectNumber=                project_number,
				accountHeadId=                row_account_head_id,
				transactionReceivedRefNumber= ref_details_val,
				commitDate=                   today(),
				commitParticular=             row.particulars or doc.particulars or "",
				refDetails=                   ref_details_val,
				commitAmount=                 flt(row.amount),
				status=                       "COMMITTED",
				billAmount=                   po_total or None,
				moduleId=                     module_id_str,
				frapAppId=                    doc.name,
			))
	else:
		# commitAmount: prefer the referenced transaction's amount;
		# fall back to po_total_value when the transaction belongs to a
		# different account head and is not in the current transactions list.
		ref_commit_amount = None
		if ref_details_val:
			for tx in transactions:
				if tx.get("transactionId") == ref_details_val:
					ref_commit_amount = flt(tx.get("commitAmount", 0))
					break
		if ref_commit_amount is None:
			ref_commit_amount = po_total

		items.append(AccountHeadCommitBatchItemDTO(
			transactionCommitNumber=      1,
			projectNumber=                project_number,
			accountHeadId=                account_head_id,
			transactionReceivedRefNumber= ref_details_val,
			commitDate=                   today(),
			commitParticular=             doc.particulars or "",
			refDetails=                   ref_details_val,
			commitAmount=                 ref_commit_amount,
			status=                       "COMMITTED",
			billAmount=                   po_total or None,
			moduleId=                     module_id_str,
			frapAppId=                    doc.name,
		))

	return publish_commit_batch(
		doc_name=doc.name,
		items=items,
		partition_key=project_number or doc.name,
	)


# ---------------------------------------------------------------------------
# ENDPOINT 1 — fetch fields + link options
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_po_commit_adjustment_fields(doc_name=None, ref_doctype=None, ref_name=None):
	"""
	Return field metadata (with child-table field lists), link options for all
	Link/Table fields, saved document data when doc_name is provided, and
	the Kafka Commit Staging payload for the given ref_doctype/ref_name.
	"""
	meta = frappe.get_meta("Po Commit Adjustment")

	fields = []
	for f in meta.get("fields"):
		fd = {
			"fieldname":   f.fieldname,
			"label":       f.label,
			"fieldtype":   f.fieldtype,
			"options":     f.options,
			"mandatory":   f.reqd,
			"hidden":      f.hidden,
			"read_only":   f.read_only,
			"default":     f.default,
			"fetch_from":  f.fetch_from,
			"in_list_view": f.in_list_view,
			"depends_on":  f.depends_on,
		}
		if f.fieldtype == "Table" and f.options:
			fd["child_fields"] = [
				{
					"fieldname":    cf.fieldname,
					"label":        cf.label,
					"fieldtype":    cf.fieldtype,
					"options":      cf.options,
					"mandatory":    cf.reqd,
					"in_list_view": cf.in_list_view,
					"read_only":    cf.read_only,
				}
				for cf in frappe.get_meta(f.options).fields
			]
		fields.append(fd)

	doc_data = {}
	if doc_name and frappe.db.exists("Po Commit Adjustment", doc_name):
		doc_data = frappe.get_doc("Po Commit Adjustment", doc_name).as_dict()

	purchase_orders = frappe.get_all(
		"sanction_sheet",
		fields=["name as value", "name as label", "project_no", "app_id", "ss_grand_total"],
		limit_page_length=0,
	)
	account_heads = frappe.get_all(
		"Budget Head",
		fields=["name as value", "budget_head as label"],
		limit_page_length=0,
	)

	kafka_payload  = None
	transaction_id = None

	if ref_doctype and ref_name:
		rows = frappe.get_all(
			"Kafka Commit Staging",
			filters={"reference_doctype": ref_doctype, "reference_name": ref_name},
			fields=["name", "payload", "status"],
			order_by="modified desc",
			limit=1,
		)
		if rows:
			try:
				kafka_payload = {
					"staging_name": rows[0].name,
					"status":       rows[0].status,
					**json.loads(rows[0].payload or "{}"),
				}
			except Exception:
				kafka_payload = {"staging_name": rows[0].name, "status": rows[0].status}

		if kafka_payload:
			try:
				budget_head_name = kafka_payload.get("budget_head")
				frap_app_id      = kafka_payload.get("frap_app_id")

				# auto-fill account_head from budget_head label
				if budget_head_name:
					account_head_name = frappe.db.get_value(
						"Budget Head", {"budget_head": budget_head_name}, "name"
					)
					if account_head_name:
						doc_data["account_head"] = account_head_name

				account_head_id = frappe.db.get_value(
					"Budget Head", {"budget_head": budget_head_name}, "id"
				) if budget_head_name else None

				# auto-fill purchase_order_number from frap_app_id via sanction_sheet.app_id
				if frap_app_id:
					ss_name = frappe.db.get_value(
						"sanction_sheet", {"app_id": frap_app_id}, "name"
					)
					if ss_name:
						doc_data["purchase_order_number"] = ss_name

				# auto-fill particulars from commit_particular
				commit_particular = kafka_payload.get("commit_particular")
				if commit_particular:
					doc_data["particulars"] = commit_particular

				project_no = frappe.db.get_value(
					"Direct Purchase", frap_app_id, "project_no"
				) if frap_app_id else None

				project_number = get_project_number(project_no) if project_no else None

				transactions = _fetch_transactions(project_number, account_head_id)
				for tx in transactions:
					if tx.get("frapAppId") == frap_app_id:
						transaction_id = tx.get("transactionId")
						break
				if transactions:
					doc_data["total_committed_till_now"] = sum(
						flt(tx.get("commitAmount", 0)) for tx in transactions
					)
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Po Commit Adjustment: transaction lookup failed")

	if transaction_id is not None:
		doc_data["ref_details"] = transaction_id

	return {
		"fields":        fields,
		"doc_data":      doc_data,
		"kafka_payload": kafka_payload,
		"transaction_id": transaction_id,
		"link_options": {
			"purchase_order_number": [
				{
					"value":         r.value,
					"label":         r.label or r.value,
					"project_no":    r.project_no,
					"app_id":        r.app_id,
					"ss_grand_total": r.ss_grand_total,
				}
				for r in purchase_orders
			],
			"account_head": [{"value": r.value, "label": r.label or r.value} for r in account_heads],
			"settlement_accounts_account_head": [{"value": r.value, "label": r.label or r.value} for r in account_heads],
		},
	}


# ---------------------------------------------------------------------------
# ENDPOINT 2 — save + post batch commit
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_po_commit_adjustment_data(data):
	"""
	Insert or update a Po Commit Adjustment document (with MinIO file handling).

	After saving:
	1. Calls COMMIT_PAYMENT_API once to compute total_committed_till_now.
	2. Posts a batch commit to COMMIT_BATCH_API regardless of other_expenses value.
	"""
	from rndopsapp.minio import get_rnd_file_service
	import base64

	try:
		if isinstance(data, str):
			data = json.loads(data)

		doc_name = data.get("name")
		is_new   = False

		if doc_name and frappe.db.exists("Po Commit Adjustment", doc_name):
			doc = frappe.get_doc("Po Commit Adjustment", doc_name)
			if doc.docstatus != 0:
				frappe.throw(_("Cannot edit a submitted or cancelled document."))
		else:
			doc  = frappe.new_doc("Po Commit Adjustment")
			is_new = True

		meta     = frappe.get_meta("Po Commit Adjustment")
		deferred = []  # Table / Attach fields processed after initial insert

		for fieldname, value in data.items():
			if fieldname in ["name", "doctype", "docstatus"]:
				continue
			if not meta.has_field(fieldname):
				continue
			df = meta.get_field(fieldname)
			if df.fieldtype in ["Attach", "Attach Image", "Table"]:
				deferred.append((fieldname, value))
			elif value not in [None, ""]:
				doc.set(fieldname, value)

		doc.flags.ignore_permissions = True
		if is_new:
			doc.insert(ignore_mandatory=True)

		# ---- resolve project context and fetch existing transactions once ----
		_, project_no  = _resolve_po_context(doc.purchase_order_number)
		project_number = get_project_number(project_no) if project_no else ""
		account_head_id = (
			frappe.db.get_value("Budget Head", doc.account_head, "id")
			if doc.account_head else None
		)
		transactions = _fetch_transactions(project_number, account_head_id)

		# total committed for this PO + account head from the external source
		doc.total_committed_till_now = sum(flt(tx.get("commitAmount", 0)) for tx in transactions)

		# ---- process deferred (Table / Attach) fields ----
		_folder      = f"po_commit_adjustment/{doc.name}"
		file_service = get_rnd_file_service()

		for fieldname, value in deferred:
			df = meta.get_field(fieldname)

			if df.fieldtype == "Table":
				if isinstance(value, str):
					try:
						value = json.loads(value)
					except Exception:
						pass
				if isinstance(value, list):
					doc.set(fieldname, [])
					child_meta = frappe.get_meta(df.options)
					for child_row in value:
						row_dict = child_row.copy()
						if row_dict.get("name") and str(row_dict["name"]).startswith("new-"):
							del row_dict["name"]
						for k in ["creation", "modified", "owner", "modified_by", "docstatus",
								  "parent", "parentfield", "parenttype"]:
							row_dict.pop(k, None)
						for cf in child_meta.fields:
							if cf.fieldtype in ["Attach", "Attach Image"] and row_dict.get(cf.fieldname):
								f_val = row_dict[cf.fieldname]
								if isinstance(f_val, dict) and f_val.get("file_data"):
									try:
										content = base64.b64decode(f_val["file_data"])
										result  = file_service.save_file(
											filename=f_val.get("file_name", "attachment"),
											content=content,
											is_private=True,
											doctype="Po Commit Adjustment",
											docname=doc.name,
											folder=_folder,
										)
										if result.get("status"):
											row_dict[cf.fieldname] = result.get("file_url") or result.get("data", {}).get("file_url")
									except Exception as e:
										frappe.log_error(f"Child file error: {e}")
						doc.append(fieldname, row_dict)

			elif df.fieldtype in ["Attach", "Attach Image"]:
				if isinstance(value, dict) and value.get("file_data"):
					try:
						content = base64.b64decode(value["file_data"])
						result  = file_service.save_file(
							filename=value.get("file_name", "attachment"),
							content=content,
							is_private=True,
							doctype="Po Commit Adjustment",
							docname=doc.name,
							folder=_folder,
						)
						if result.get("status"):
							doc.set(fieldname, result.get("file_url") or result.get("data", {}).get("file_url"))
					except Exception as e:
						frappe.log_error(f"File upload error for {fieldname}: {str(e)}")
				elif isinstance(value, str):
					doc.set(fieldname, value)

		doc.save(ignore_permissions=True)
		frappe.db.commit()

		# ---- publish batch to Kafka (always, regardless of other_expenses) ----
		# The doc was already saved+committed above (line 414-415), so a publish
		# failure here can't be rolled back with frappe.db.rollback(). For a
		# newly-created doc we delete it outright so nothing is left half-synced;
		# for an update to a pre-existing doc, we surface a hard error (throw)
		# instead of the endpoint silently reporting "success".
		batch_result = None
		batch_error = None
		try:
			batch_result = _publish_batch_to_kafka(doc, project_number, account_head_id, transactions)
		except Exception as be:
			batch_error = str(be)
			frappe.log_error(frappe.get_traceback(), "Po Commit Adjustment: Kafka batch publish failed")

		if not batch_result:
			if is_new:
				doc.delete(ignore_permissions=True)
				frappe.db.commit()
				frappe.throw(
					_("Kafka batch publish failed ({0}). Po Commit Adjustment was not saved. Please try again.")
					.format(batch_error or "see error log")
				)
			else:
				frappe.throw(
					_("Kafka batch publish failed ({0}). Changes were saved locally but not synced.")
					.format(batch_error or "see error log")
				)

		return {
			"status":  "success",
			"docname": doc.name,
			"total_committed_till_now": doc.total_committed_till_now,
			"batch":   batch_result,
		}

	except frappe.ValidationError:
		raise  # Re-raise the Kafka-failure throw above without re-wrapping its message
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Po Commit Adjustment Save Error")
		frappe.throw(f"Failed to save Po Commit Adjustment: {str(e)}")
