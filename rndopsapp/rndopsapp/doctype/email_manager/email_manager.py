# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class EmailManager(Document):
	def on_update(self):
		self._clear_cache()

	def on_trash(self):
		self._clear_cache()

	def _clear_cache(self):
		from rndopsapp.rndopsapp.email.workflow_monitor import clear_config_cache

		clear_config_cache()
