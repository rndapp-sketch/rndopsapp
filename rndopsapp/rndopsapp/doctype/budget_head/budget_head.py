# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt
import frappe
from frappe.model.document import Document


class BudgetHead(Document):
	pass


@frappe.whitelist()
def get_budget_head():
	budget_heads = frappe.get_all(
		"Budget Head",
		fields=["name", "budget_head"],  # include your actual fields
	)
	# print("budget_heads:", budget_heads)
	return budget_heads
