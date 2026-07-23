import frappe
from frappe.model.document import Document


class UserDelegation(Document):
    def validate(self):
        if self.delegator_user == self.delegate_user:
            frappe.throw("Delegator and Delegate cannot be the same user.")

        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            frappe.throw("Valid From must be earlier than Valid To.")

    def before_insert(self):
        # Enforce: delegator must always be the session user (unless System Manager)
        if "System Manager" not in frappe.get_roles(frappe.session.user):
            self.delegator_user = frappe.session.user
