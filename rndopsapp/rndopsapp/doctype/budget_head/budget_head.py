# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt
import frappe
import requests
from frappe.model.document import Document
from rndopsapp.static_config import ACCOUNT_PORTAL_ACCOUNT_HEADS


class BudgetHead(Document):
	pass


@frappe.whitelist(allow_guest=True)
def get_budget_head():
	budget_heads = frappe.get_all(
		"Budget Head",
		fields=["name", "id", "budget_head"],
		order_by="id asc",
	)
	return budget_heads


@frappe.whitelist()
def get_budget_heads_by_project(project_no):
	"""Return the unique budget heads used in the Fund Sanction(s) of a project,
	in the Fund Received entries linked to those sanctions, and in the Fund Breakup
	of the project's Loan Request(s). Heads that appear in a Loan Request also carry
	`loan_amount`, the total requested for that head across those loans."""
	if not project_no:
		frappe.throw("project_no is required")

	# project_no is a field on Project Registration; sanctions link by its name
	project_ids = frappe.get_all(
		"Project Registration", filters={"project_no": project_no}, pluck="name"
	) + [project_no]

	sanctions = frappe.get_all(
		"Fund Sanction",
		filters=[["docstatus", "<", 2]],
		or_filters=[
			["project_proposal", "in", project_ids],
			["refnum_prj_num", "in", project_ids],
		],
		pluck="name",
	)

	raw_heads = []
	if sanctions:
		received = frappe.get_all(
			"Fund Received",
			filters={"sanction_ref_no": ["in", sanctions], "docstatus": ["<", 2]},
			pluck="name",
		)

		raw_heads = frappe.get_all(
			"Project Sanctioned Budget",
			filters={"parent": ["in", sanctions], "parenttype": "Fund Sanction"},
			pluck="account_head",
		)
		raw_heads += frappe.get_all(
			"Project Received Budget",
			filters={
				"parent": ["in", sanctions + received],
				"parenttype": ["in", ["Fund Sanction", "Fund Received"]],
			},
			pluck="account_head",
		)

	# Loan Request keeps the human-readable project number in `project_number` (Data)
	# and the Project Registration name in `project_name` (Link); match on either.
	# Draft / rejected / cancelled loans don't count.
	project_nos = {project_no} | set(
		frappe.get_all(
			"Project Registration", filters={"name": ["in", project_ids]}, pluck="project_no"
		)
	)
	loans = frappe.get_all(
		"Loan Request",
		filters=[
			["docstatus", "<", 2],
			["workflow_state", "not in", ["Draft", "Rejected", "Cancelled"]],
		],
		or_filters=[
			["project_number", "in", [n for n in project_nos if n]],
			["project_name", "in", project_ids],
		],
		pluck="name",
	)
	loan_amount_by_head = {}
	if loans:
		for row in frappe.get_all(
			"Loan Amount Accounthead Breakup",
			filters={"parent": ["in", loans], "parenttype": "Loan Request"},
			fields=["budget_head", "account_head_amount"],
		):
			head = (row.budget_head or "").strip()
			if head:
				loan_amount_by_head[head] = loan_amount_by_head.get(head, 0) + (row.account_head_amount or 0)
		raw_heads += list(loan_amount_by_head)

	raw_heads = {h.strip() for h in raw_heads if h and h.strip()}
	if not raw_heads:
		return []

	# Values may be Budget Head names (links), numeric ids or the plain head text (Data field)
	heads = list(raw_heads)
	records = frappe.get_all(
		"Budget Head",
		or_filters=[
			["name", "in", heads],
			["budget_head", "in", heads],
			["id", "in", [h for h in heads if h.isdigit()]],
		],
		fields=["name", "id", "budget_head"],
		order_by="id asc",
	)
	matched = (
		{r.name for r in records}
		| {r.budget_head for r in records}
		| {str(r.id) for r in records}
	)
	unknown = sorted(raw_heads - matched)

	result = records + [{"name": h, "id": None, "budget_head": h} for h in unknown]
	if loan_amount_by_head:
		for r in result:
			if r["name"] in loan_amount_by_head:
				r["loan_amount"] = loan_amount_by_head[r["name"]]
	return result


@frappe.whitelist(allow_guest=True)
def add_budget_head(budget_head_name):
	from frappe.utils import now

	# Get the current max id
	max_id = frappe.db.sql(
		"SELECT IFNULL(MAX(id), 0) FROM `tabBudget Head`"
	)[0][0]
	new_id = int(max_id) + 1

	# Generate a unique name for the record
	doc_name = frappe.generate_hash("", 10)
	creation = now()

	# Direct DB insert — bypasses ORM, server scripts, and permissions
	frappe.db.sql(
		"""INSERT INTO `tabBudget Head`
		(`name`, `creation`, `modified`, `modified_by`, `owner`,
		 `docstatus`, `budget_head`, `id`)
		VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
		(doc_name, creation, creation, "Administrator", "Administrator",
		 0, budget_head_name, new_id),
	)
	frappe.db.commit()

	# Send the head name to the external accounting API
	external_url = ACCOUNT_PORTAL_ACCOUNT_HEADS
	try:
		ext_response = requests.post(
			external_url,
			json={"accountHeadName": budget_head_name},
			headers={"Content-Type": "application/json"},
			timeout=10,
		)
		ext_result = ext_response.json() if ext_response.ok else ext_response.text
	except Exception as e:
		ext_result = f"External API call failed: {str(e)}"

	return {
		"id": new_id,
		"budget_head": budget_head_name,
		"name": doc_name,
		"external_api_response": ext_result,
	}
