import frappe
from frappe.tests.utils import FrappeTestCase
from rndopsapp.rndopsapp.rndopsapp.doctype.project_number_generation.project_number_generation import ProjectNumberGeneration

class TestProjectNumberGeneration(FrappeTestCase):
    def setUp(self):
        # Clear existing test data if any
        frappe.db.delete("Project Number Generation")
        # Clear naming series counters to start fresh
        frappe.db.delete("Series", {"name": ["like", "PRJ-%"]})

    def test_independent_sequence_per_employee(self):
        # Employee 391, Year 26
        doc1 = frappe.get_doc({
            "doctype": "Project Number Generation",
            "emp_id": "391",
            "current_year1": "26",
            "category": "C",
            "dept_initial": "CSE",
            "project_type": "SP",
            "emp_initial": "JD"
        }).insert()
        self.assertEqual(doc1.project_no, "0001")

        # Second record for Employee 391, Year 26 -> 0002
        doc2 = frappe.get_doc({
            "doctype": "Project Number Generation",
            "emp_id": "391",
            "current_year1": "26",
            "category": "C",
            "dept_initial": "CSE",
            "project_type": "SP",
            "emp_initial": "JD"
        }).insert()
        self.assertEqual(doc2.project_no, "0002")

        # Employee 221, Year 26 -> 0001 (Independent)
        doc3 = frappe.get_doc({
            "doctype": "Project Number Generation",
            "emp_id": "221",
            "current_year1": "26",
            "category": "C",
            "dept_initial": "ME",
            "project_type": "SP",
            "emp_initial": "AS"
        }).insert()
        self.assertEqual(doc3.project_no, "0001")

    def test_yearly_reset(self):
        # Employee 391, Year 26 -> 0001
        doc1 = frappe.get_doc({
            "doctype": "Project Number Generation",
            "emp_id": "391",
            "current_year1": "26",
            "category": "C",
            "dept_initial": "CSE",
            "project_type": "SP",
            "emp_initial": "JD"
        }).insert()
        self.assertEqual(doc1.project_no, "0001")

        # Employee 391, Year 27 -> 0001 (Reset)
        doc2 = frappe.get_doc({
            "doctype": "Project Number Generation",
            "emp_id": "391",
            "current_year1": "27",
            "category": "C",
            "dept_initial": "CSE",
            "project_type": "SP",
            "emp_initial": "JD"
        }).insert()
        self.assertEqual(doc2.project_no, "0001")
