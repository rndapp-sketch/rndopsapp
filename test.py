import frappe

doc = frappe.get_doc("Project Registration", "2026040601MeiTy000122")
data = doc.as_dict()
dept = data.get("implementation_department")
print(f"Implementation Department: {dept}")

try:
    dept_doc = frappe.get_doc("Department_prornd", dept)
    print(f"dept_head is: {dept_doc.dept_head}")
except Exception as e:
    print(f"Error getting dept: {e}")

doc.department_head = dept_doc.dept_head
doc.head_approver = dept_doc.dept_head
print(f"Before save: doc.head_approver={doc.head_approver}")

doc.save(ignore_permissions=True)
print(f"After save: doc.head_approver={doc.head_approver}")
