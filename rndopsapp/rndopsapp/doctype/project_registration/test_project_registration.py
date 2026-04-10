# Copyright (c) 2025, rndops and Contributors
# See license.txt

# import frappe
# from frappe.tests.utils import FrappeTestCase


# class TestProjectRegistration(FrappeTestCase):
# 	pass

# test_project_registration.py

# File: rndopsapp/doctype/project_registration/test_project_registration.py

import frappe
import unittest
import os
from frappe.utils import nowdate

# IMPORTANT: Adjust this import path to match your app and api.py file location
from rndopsapp.api import submit_project_registration, handle_approval_action

class TestProjectRegistration(unittest.TestCase):
    def setUp(self):
        """
        This method runs before each test. It will fetch existing users, not create them.
        """
        # --- Fetch Existing Users ---
        self.pi_user = frappe.get_doc("User", "ls@iitg.ac.in") # Lingraj Sahoo - A regular PI
        self.hod_civil = frappe.get_doc("User", "hodcivil@iitg.ac.in") # Head of Civil Engineering
        self.hod_bio = frappe.get_doc("User", "hodbio@iitg.ac.in") # Head of Bioengineering
        self.staff_user = frappe.get_doc("User", "mky@iisi.iitg.ac.in") # Manish Yadav - Staff, RnD
        self.hos_user = frappe.get_doc("User", "hosiisi@iitg.ac.in") # HOS, RnD
        self.dean_user = frappe.get_doc("User", "dornd@iitg.ac.in") # Dean, RnD
        self.ir_user = frappe.get_doc("User", "priyam96@iisi.iitg.ac.in") # Priyam Kurmi - Independent Researcher

        # --- Fetch Existing Departments ---
        self.civil_dept = frappe.get_doc("Department_prornd", {"dept_name": "Civil Engineering"})
        self.bio_dept = frappe.get_doc("Department_prornd", {"dept_name": "Biosciences & Bioengineering"})

        # Create a single dummy file for all tests to use
        self.dummy_file = _create_dummy_file()

    def tearDown(self):
        """
        This method runs after each test to clean up transactional data.
        """
        frappe.db.rollback()
        frappe.set_user("Administrator")

    # --- TEST CASES START HERE ---

    def test_01_permanent_employee_submission_to_correct_hod(self):
        """
        Test Case 1: A regular PI (ls@iitg.ac.in) from Bioengineering submits a form.
        Expected Outcome: It should go to the Head of Bioengineering (hodbio@iitg.ac.in).
        """
        # 1. Impersonate the regular PI user
        frappe.set_user(self.pi_user.name)

        # 2. Create and save a draft document
        doc = self._create_base_project_doc(owner_user=self.pi_user, implementation_dept=self.bio_dept)
        doc.insert()
        
        # 3. Call the submit function
        submit_project_registration(doc.name)
        doc.reload()

        # 4. Assert the results are correct
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.workflow_state, "Pending HoD Approval")
        self.assertEqual(doc.head_approver, self.hod_bio.name) # Must go to HoD of Bioengineering
        self.assertTrue(frappe.share.get_shared("Project Registration", doc.name, self.hod_bio.name))

    def test_02_hod_self_approval_bypass(self):
        """
        Test Case 2: An HoD (hodcivil@iitg.ac.in) submits a project for their own department (Civil).
        Expected Outcome: Skips the HoD step and goes directly to Staff.
        """
        # 1. Impersonate the HoD
        frappe.set_user(self.hod_civil.name)

        # 2. Create and save a draft for their own department
        doc = self._create_base_project_doc(owner_user=self.hod_civil, implementation_dept=self.civil_dept)
        doc.insert()
        
        # 3. Submit
        submit_project_registration(doc.name)
        doc.reload()

        # 4. Assert
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.workflow_state, "Pending Staff Approval")
        
        comments = frappe.get_all("Comment", filters={"reference_doctype": "Project Registration", "reference_name": doc.name})
        self.assertTrue(any("Skipping Head Approval step" in c.content for c in comments))

    def test_03_hod_submits_for_different_department(self):
        """
        Test Case 3: An HoD (hodcivil) submits a project to be implemented in another department (Bio).
        Expected Outcome: It should go to the Head of the IMPLEMENTATION department (hodbio).
        """
        # 1. Impersonate HoD of Civil
        frappe.set_user(self.hod_civil.name)

        # 2. Create the draft, but for a different department
        doc = self._create_base_project_doc(owner_user=self.hod_civil, implementation_dept=self.bio_dept)
        doc.insert()

        # 3. Submit
        submit_project_registration(doc.name)
        doc.reload()

        # 4. Assert
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.workflow_state, "Pending HoD Approval")
        self.assertEqual(doc.head_approver, self.hod_bio.name) # Must go to the OTHER HoD
        self.assertTrue(frappe.share.get_shared("Project Registration", doc.name, self.hod_bio.name))

    def test_04_full_approval_chain(self):
        """
        Test Case 4: Test the full approval chain from Staff to Dean.
        """
        # --- Stage 1: PI submits to HoD ---
        frappe.set_user(self.pi_user.name)
        doc = self._create_base_project_doc(self.pi_user, self.bio_dept)
        doc.insert()
        submit_project_registration(doc.name)
        doc.reload()
        self.assertEqual(doc.workflow_state, "Pending HoD Approval")

        # --- Stage 2: HoD approves to Staff ---
        frappe.set_user(self.hod_bio.name) # Impersonate the approver
        handle_approval_action(doc.name, "Approve", "Looks good, forwarded to Staff.")
        doc.reload()
        self.assertEqual(doc.workflow_state, "Pending Staff Approval")

        # --- Stage 3: Staff approves to HoS ---
        frappe.set_user(self.staff_user.name)
        handle_approval_action(doc.name, "Approve", "Verified by Staff.")
        doc.reload()
        self.assertEqual(doc.workflow_state, "Pending HoS Approval")

        # --- Stage 4: HoS approves to Dean ---
        frappe.set_user(self.hos_user.name)
        handle_approval_action(doc.name, "Approve", "Verified by HoS.")
        doc.reload()
        self.assertEqual(doc.workflow_state, "Pending Dean Approval")
        
        # --- Stage 5: Dean approves to Final State ---
        frappe.set_user(self.dean_user.name)
        handle_approval_action(doc.name, "Approve", "Final approval granted.")
        doc.reload()
        self.assertEqual(doc.workflow_state, "Approved")
        self.assertEqual(doc.docstatus, 1) # Should remain submitted

    # --- Helper method to create a pre-filled document ---
    def _create_base_project_doc(self, owner_user, implementation_dept):
        # The client script does the heavy lifting, so we just need to replicate its output.
        applicant_department = frappe.db.get_value("User", owner_user.name, "department_name")
        head_of_implementation_dept = frappe.db.get_value("Department_prornd", implementation_dept.name, "dept_head")

        doc = frappe.new_doc("Project Registration")
        doc.owner = owner_user.name
        doc.pi_webmail = owner_user.name
        doc.applicant_type = owner_user.empclass # This comes from the User's profile
        
        # This data is what the client script would have figured out
        doc.applicant_department = applicant_department
        doc.implementation_department = implementation_dept.name
        doc.head_approver = head_of_implementation_dept
        doc.department_head = head_of_implementation_dept

        # --- Fill only the absolutely mandatory fields for the test ---
        doc.registering_for = "Own"
        doc.project_title = f"Automated Test - {random_string(5)}"
        doc.is_additional_pi_from_iitg = "Yes"
        doc.is_single_department = "Yes"
        doc.project_type = "Research"
        doc.project_duration_months = 12
        doc.involves_international_travel = "No"
        doc.space_required = "No"
        doc.total_budget_amount = 50000
        doc.need_endorsement_copy = "No"
        doc.have_sanction_details = "No" # Important for triggering the workflow

        return doc


# --- Helper function to create a dummy file (outside the class) ---
def _create_dummy_file():
    # Check if a test file already exists to avoid creating duplicates
    if frappe.db.exists("File", {"file_name": "test_upload.pdf"}):
        return frappe.get_doc("File", {"file_name": "test_upload.pdf"})
        
    file = frappe.new_doc("File")
    file.file_name = "test_upload.pdf"
    file.content = "This is a test file for automated testing."
    file.is_private = 1
    file.insert(ignore_permissions=True)
    return file