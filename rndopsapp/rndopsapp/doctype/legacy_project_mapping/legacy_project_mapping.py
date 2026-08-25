import frappe
from frappe.model.document import Document


class LegacyProjectMapping(Document):
	def validate(self):
		self.pragati_project_no = frappe.db.get_value(
			"Project Registration", self.project_registration, "project_no"
		)
