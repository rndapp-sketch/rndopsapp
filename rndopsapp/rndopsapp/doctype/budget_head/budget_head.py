# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt
import frappe
import requests
from frappe.model.document import Document


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
	external_url = "http://172.16.134.81:18080/api/account-heads/createAccountHead"
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
