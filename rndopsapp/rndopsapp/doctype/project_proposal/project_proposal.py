# Copyright (c) 2025, rndops and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document

# class ProjectProposal(Document):
# 	pass



# frappe_dev/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_proposal/project_proposal.py


# project_proposal.py (CORRECTED for f-string SyntaxError)

import frappe
from frappe.utils import get_url, nowdate, formatdate, now_datetime
from frappe.model.document import Document
# from frappe.exceptions import ValidationError, DocumentError
from frappe.exceptions import ValidationError

class ProjectProposal(Document):
    def validate(self):
        pass
    def on_submit(self):
        pass

@frappe.whitelist()
def get_initial_endorsement_html(docname, print_format):
    try:
        project_proposal = frappe.get_doc('Project Proposal', docname)
        print_format_doc = frappe.get_doc('Print Format', print_format)
        context = {"doc": project_proposal, "frappe": frappe}
        html_content = frappe.render_template(print_format_doc.html, context)
        frappe.logger().warning(f"Generated HTML for Project Proposal {docname}: {html_content}")
        return {"success": True, "html": html_content}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement HTML Generation Error")
        return {"success": False, "error": str(e), "html": ""}


@frappe.whitelist()
def save_edited_endorsement_and_generate_pdf(docname, edited_content):
    try:
        project_proposal = frappe.get_doc('Project Proposal', docname)

        if project_proposal.docstatus != 0 or project_proposal.endorsement_status != 'Draft':
            raise ValidationError("Document is not in 'Draft' state or already submitted. Cannot generate and submit for endorsement.")

        project_proposal.edited_endorsement_content = edited_content
        project_proposal.save(ignore_permissions=True)

        pdf_file = frappe.get_print(
            'Project Proposal',
            docname,
            print_format='Project Endorsement Letterhead',
            as_pdf=True,
            no_letterhead=False
        )

        if not pdf_file:
            frappe.log_error(f"Failed to generate PDF for Project Proposal {docname}", "Endorsement Generation Error")
            raise ValidationError("Failed to generate endorsement PDF. Please try again or contact support.")

        try:
            max_file_size_setting = frappe.get_system_settings("max_file_size")
            if isinstance(max_file_size_setting, str):
                try:
                    max_file_size = frappe.parse_json(max_file_size_setting)
                except frappe.exceptions.InvalidJsonError:
                    max_file_size = 1048576
            else:
                max_file_size = max_file_size_setting
            max_file_size = max_file_size or 1048576
        except Exception:
            max_file_size = 1048576

        if len(pdf_file) > max_file_size:
            frappe.msgprint(f"Endorsement PDF size ({len(pdf_file)} bytes) exceeds maximum allowed file size ({max_file_size} bytes). PDF not attached.")
            frappe.log_error(f"Endorsement PDF for {project_proposal.name} exceeded max file size. Not attached.", "Endorsement File Size Error")
        else:
            frappe.get_doc({
                "doctype": "File",
                "file_name": f"Project Endorsement - {project_proposal.name}.pdf",
                "attached_to_doctype": "Project Proposal",
                "attached_to_name": project_proposal.name,
                "content": pdf_file,
                "is_private": 1
            }).insert(ignore_permissions=True)

        project_proposal.endorsement_status = 'Pending Approval'
        project_proposal.submit()

        frappe.msgprint("Project Proposal submitted for endorsement.")

        dean_rnd_users_data = frappe.get_all(
            'Has Role',
            filters={'role': 'Dean, RnD'},
            pluck='parent',
            distinct=True
        )

        if dean_rnd_users_data:
            # CORRECTED: Construct URL outside the main f-string for clarity and to prevent syntax issues
            proposal_url = get_url(f"/app/project-proposal/{project_proposal.name}")
            frappe.send_notification(
                recipients=dean_rnd_users_data,
                subject=f"Action Required: Project Endorsement for {project_proposal.project_title}",
                message=f"""
                    The project proposal "{project_proposal.project_title}" from {project_proposal.principal_investigator_name}
                    is awaiting your endorsement.

                    Please review and take action.
                    <p><a href='{proposal_url}' target='_blank'>Click here to view the Project Proposal</a></p>
                """,
                doctype="Project Proposal",
                name=project_proposal.name,
                for_doctype="Project Proposal",
                for_email_account=None,
            )
            frappe.msgprint("Notification sent to Dean, RnD.")
        else:
            frappe.msgprint("No users found with 'Dean, RnD' role to notify. Ensure the role is assigned and valid.")

        return {"success": True, "message": "Endorsement processed and submitted for approval."}

    except ValidationError as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Validation Error")
        frappe.throw(f"Validation Error: {e}")
        return {"success": False, "error": str(e)}
    except DocumentError as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Workflow/Document Error")
        frappe.throw(f"Workflow or Document Error during submission: {e}. Check your workflow configuration (transitions, roles).")
        return {"success": False, "error": str(e)}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Processing Error")
        frappe.throw(f"An unexpected error occurred during endorsement processing: {e}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def generate_endorsement_pdf_and_notify(docname):
    try:
        project_proposal = frappe.get_doc('Project Proposal', docname)

        if project_proposal.docstatus != 0 or project_proposal.endorsement_status != 'Draft':
            raise ValidationError("Document is not in 'Draft' state or already submitted. Cannot generate and submit for endorsement.")

        pdf_file = frappe.get_print(
            'Project Proposal',
            docname,
            print_format='Project Endorsement Letterhead',
            as_pdf=True,
            no_letterhead=False
        )

        if not pdf_file:
            frappe.log_error(f"Failed to generate PDF for Project Proposal {docname}", "Endorsement Generation Error")
            raise ValidationError("Failed to generate endorsement PDF. Please try again or contact support.")

        try:
            max_file_size_setting = frappe.get_system_settings("max_file_size")
            if isinstance(max_file_size_setting, str):
                try:
                    max_file_size = frappe.parse_json(max_file_size_setting)
                except frappe.exceptions.InvalidJsonError:
                    max_file_size = 1048576
            else:
                max_file_size = max_file_size_setting
            max_file_size = max_file_size or 1048576
        except Exception:
            max_file_size = 1048576

        if len(pdf_file) > max_file_size:
            frappe.msgprint(f"Endorsement PDF size ({len(pdf_file)} bytes) exceeds maximum allowed file size ({max_file_size} bytes). PDF not attached.")
            frappe.log_error(f"Endorsement PDF for {project_proposal.name} exceeded max file size. Not attached.", "Endorsement File Size Error")
        else:
            frappe.get_doc({
                "doctype": "File",
                "file_name": f"Project Endorsement - {project_proposal.name}.pdf",
                "attached_to_doctype": "Project Proposal",
                "attached_to_name": project_proposal.name,
                "content": pdf_file,
                "is_private": 1
            }).insert(ignore_permissions=True)

        project_proposal.endorsement_status = 'Pending Approval'
        project_proposal.submit()

        frappe.msgprint("Project Proposal submitted for endorsement.")

        dean_rnd_users_data = frappe.get_all(
            'Has Role',
            filters={'role': 'Dean, RnD'},
            pluck='parent',
            distinct=True
        )

        if dean_rnd_users_data:
            # CORRECTED: Construct URL outside the main f-string
            proposal_url = get_url(f"/app/project-proposal/{project_proposal.name}")
            frappe.send_notification(
                recipients=dean_rnd_users_data,
                subject=f"Action Required: Project Endorsement for {project_proposal.project_title}",
                message=f"""
                    The project proposal "{project_proposal.project_title}" from {project_proposal.principal_investigator_name}
                    is awaiting your endorsement.

                    Please review and take action.
                    <p><a href='{proposal_url}' target='_blank'>Click here to view the Project Proposal</a></p>
                """,
                doctype="Project Proposal",
                name=project_proposal.name,
                for_doctype="Project Proposal",
                for_email_account=None,
            )
            frappe.msgprint("Notification sent to Dean, RnD.")
        else:
            frappe.msgprint("No users found with 'Dean, RnD' role to notify. Ensure the role is assigned and valid.")

        return {"success": True, "message": "Endorsement processed and submitted for approval."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Processing Error")
        frappe.throw(f"An unexpected error occurred during endorsement processing: {e}")
        return {"success": False, "error": str(e)}


@frappe.whitelist()
def process_endorsement(docname, action):
    try:
        doc = frappe.get_doc("Project Proposal", docname)
        if doc.endorsement_status != "Pending Approval":
            raise ValidationError("Endorsement cannot be processed unless in 'Pending Approval' state.")

        if action == 'Approved':
            doc.endorsement_status = 'Approved'
            if not doc.approver_name:
                doc.approver_name = frappe.session.user_fullname
            if not doc.approver_date:
                doc.approver_date = now_datetime()
            frappe.msgprint("Project Endorsement Approved.")
        elif action == 'Rejected':
            doc.endorsement_status = 'Rejected'
            frappe.msgprint("Project Endorsement Rejected.")
        elif action == 'Put Back':
            doc.endorsement_status = 'Put Back'
            doc.approver_signature = None
            doc.approver_name = None
            doc.approver_date = None
            frappe.msgprint("Project Endorsement Put Back for corrections.")
        else:
            raise ValidationError("Invalid endorsement action.")

        doc.save(ignore_permissions=True)

        # CORRECTED: Construct URL outside the main f-string
        proposal_url = get_url(f"/app/project-proposal/{doc.name}")
        # frappe.send_notification(
        #     recipients=[doc.pi_userid],
        #     subject=f"Project Endorsement for {doc.project_title} {action}",
        #     message=f"Your project proposal \"{doc.project_title}\" has been {action} by the Dean, RnD. "
        #             f"<p><a href='{proposal_url}' target='_blank'>Click here to view your Project Proposal</a></p>",
        #     doctype="Project Proposal",
        #     name=doc.name
        # )

        # This is what you likely had, causing the error
        frappe.send_notification(
            recipients=[user_id],
            subject=f"Project Proposal Endorsement Pending: {doc.name}",
            message=f"Project Proposal {doc.name} - {doc.project_title} requires your endorsement.",
            doctype="Project Proposal",
            name=doc.name
        )

        return {"success": True, "message": f"Endorsement {action} successfully."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Endorsement Action Error")
        frappe.throw(f"Error processing endorsement action: {e}")
    


# Keep your original generate_endorsement_pdf_and_notify if it's used elsewhere
# but for the "Generate Endorsement" button, the client script will now call
# open_endorsement_preview_dialog which then calls save_edited_endorsement_and_generate_pdf
# so the original function might become redundant for the button's action.
# I've essentially replaced its core logic with save_edited_endorsement_and_generate_pdf.



# -------------------------Manish [24-10-2025] V4----------------------------

# import frappe
# from frappe.utils import get_url
# from frappe.model.document import Document

# # Define the controller class for your Project Proposal doctype
# class ProjectProposal(Document):
#     def validate(self):
#         # Optional: Add server-side validation here, mirroring or extending client-side checks
#         pass

#     def on_submit(self):
#         # Optional: Logic to run specifically when the document is submitted
#         # This will be triggered by project_proposal.submit()
#         pass

#     # You can add more lifecycle hooks (on_update, before_save, etc.) here as needed.



# @frappe.whitelist()
# def generate_endorsement_pdf_and_notify(docname):
#     """
#     Generates the endorsement PDF, updates status, submits for workflow,
#     and creates a Frappe notification for the Dean, RnD role.
#     """
#     try:
#         project_proposal = frappe.get_doc('Project Proposal', docname)

#         # Ensure the document is in a Draft state before proceeding with submission logic
#         if project_proposal.docstatus != 0 or project_proposal.endorsement_status != 'Draft':
#             frappe.throw("Document is not in 'Draft' state or already submitted. Cannot generate and submit for endorsement.")

#         # 1. Generate PDF (for archival/review) - REVERTED TO ORIGINAL
#         pdf_file = frappe.get_print(
#             'Project Proposal',
#             docname,
#             print_format='Project Endorsement Letterhead', # Name of your custom print format
#             as_pdf=True,
#             no_letterhead=False
#         )

#         if not pdf_file:
#             frappe.log_error(f"Failed to generate PDF for Project Proposal {docname}", "Endorsement Generation Error")
#             frappe.throw("Failed to generate endorsement PDF. Please try again or contact support.")

#         # Optionally, save the PDF as an attachment to the Project Proposal document
#         try:
#             max_file_size_setting = frappe.get_system_settings("max_file_size")
#             max_file_size = frappe.parse_json(max_file_size_setting) if isinstance(max_file_size_setting, str) else max_file_size_setting
#             max_file_size = max_file_size or 1048576 # Default to 1MB
#         except Exception:
#             max_file_size = 1048576 # Fallback if setting is corrupted

#         if len(pdf_file) > max_file_size:
#             frappe.msgprint(f"Endorsement PDF size ({len(pdf_file)} bytes) exceeds maximum allowed file size ({max_file_size} bytes). PDF not attached.")
#             frappe.log_error(f"Endorsement PDF for {project_proposal.name} exceeded max file size. Not attached.", "Endorsement File Size Error")
#         else:
#             frappe.get_doc({
#                 "doctype": "File",
#                 "file_name": f"Project Endorsement - {project_proposal.name}.pdf",
#                 "attached_to_doctype": "Project Proposal",
#                 "attached_to_name": project_proposal.name,
#                 "content": pdf_file,
#                 "is_private": 1
#             }).insert(ignore_permissions=True)


#         # 2. Update endorsement status to 'Pending Approval' and Submit
#         project_proposal.endorsement_status = 'Pending Approval'
#         project_proposal.submit()

#         frappe.msgprint("Project Proposal submitted for endorsement.")


#         # 3. Create a Frappe Notification for Dean, RnD role
#         dean_rnd_users = frappe.get_list('User', filters={'roles': 'Dean, RnD'}, pluck='name')

#         if dean_rnd_users:
#             frappe.send_notification(
#                 recipients=dean_rnd_users,
#                 subject=f"Action Required: Project Endorsement for {project_proposal.project_title}",
#                 message=f"""
#                     The project proposal "{project_proposal.project_title}" from {project_proposal.principal_investigator_name}
#                     is awaiting your endorsement.

#                     Please review and take action.
#                     <p><a href='{get_url(f"/app/project-proposal/{project_proposal.name}")}' target='_blank'>Click here to view the Project Proposal</a></p>
#                 """,
#                 doctype="Project Proposal",
#                 name=project_proposal.name,
#                 for_doctype="Project Proposal",
#                 for_email_account=None,
#             )
#             frappe.msgprint("Notification sent to Dean, RnD.")
#         else:
#             frappe.msgprint("No users found with 'Dean, RnD' role to notify. Ensure the role is assigned and valid.")

#         return {"success": True, "message": "Endorsement processed and submitted for approval."}

#     except frappe.exceptions.ValidationError as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Validation Error")
#         frappe.throw(f"Validation Error: {e}")
#         return {"success": False, "error": str(e)}
#     except frappe.exceptions.WorkflowStateError as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Workflow Error")
#         frappe.throw(f"Workflow Error: {e}. Check your workflow configuration (transitions, roles).")
#         return {"success": False, "error": str(e)}
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Processing Error")
#         frappe.throw(f"An unexpected error occurred during endorsement processing: {e}")
#         return {"success": False, "error": str(e)}

        

# @frappe.whitelist()      
# def generate_endorsement_pdf_and_notify(docname):
#     """
#     Generates the endorsement PDF, updates status, submits for workflow,
#     and creates a Frappe notification for the Dean, RnD role.
#     """
#     try:
#         project_proposal = frappe.get_doc('Project Proposal', docname)

#         # Ensure the document is in a Draft state before proceeding with submission logic
#         if project_proposal.docstatus != 0 or project_proposal.endorsement_status != 'Draft':
#             frappe.throw("Document is not in 'Draft' state or already submitted. Cannot generate and submit for endorsement.")

#         # 1. Generate PDF (for archival/review)
#         pdf_file = frappe.get_print(
#             'Project Proposal',
#             docname,
#             print_format='Project Endorsement Letterhead', # Name of your custom print format
#             as_pdf=True,
#             no_letterhead=False
#         )

#         if not pdf_file:
#             frappe.log_error(f"Failed to generate PDF for Project Proposal {docname}", "Endorsement Generation Error")
#             # It's usually good to still throw an error if PDF generation is crucial
#             frappe.throw("Failed to generate endorsement PDF. Please try again or contact support.")


#         # Optionally, save the PDF as an attachment to the Project Proposal document
#         try:
#             max_file_size_setting = frappe.get_system_settings("max_file_size")
#             max_file_size = frappe.parse_json(max_file_size_setting) if isinstance(max_file_size_setting, str) else max_file_size_setting
#             max_file_size = max_file_size or 1048576 # Default to 1MB
#         except Exception:
#             max_file_size = 1048576 # Fallback if setting is corrupted

#         if len(pdf_file) > max_file_size:
#             frappe.msgprint(f"Endorsement PDF size ({len(pdf_file)} bytes) exceeds maximum allowed file size ({max_file_size} bytes). PDF not attached.")
#             frappe.log_error(f"Endorsement PDF for {project_proposal.name} exceeded max file size. Not attached.", "Endorsement File Size Error")
#         else:
#             frappe.get_doc({
#                 "doctype": "File",
#                 "file_name": f"Project Endorsement - {project_proposal.name}.pdf",
#                 "attached_to_doctype": "Project Proposal",
#                 "attached_to_name": project_proposal.name,
#                 "content": pdf_file,
#                 "is_private": 1
#             }).insert(ignore_permissions=True)


#         # 2. Update endorsement status to 'Pending Approval' and Submit
#         # This will trigger the workflow based on the "Submit for Endorsement" transition
#         project_proposal.endorsement_status = 'Pending Approval'
#         project_proposal.submit() # This will trigger the workflow and set docstatus to 1

#         frappe.msgprint("Project Proposal submitted for endorsement.")


#         # 3. Create a Frappe Notification for Dean, RnD role
#         dean_rnd_users = frappe.get_list('User', filters={'roles': 'Dean, RnD'}, pluck='name')

#         if dean_rnd_users:
#             frappe.send_notification(
#                 recipients=dean_rnd_users,
#                 subject=f"Action Required: Project Endorsement for {project_proposal.project_title}",
#                 message=f"""
#                     The project proposal "{project_proposal.project_title}" from {project_proposal.principal_investigator_name}
#                     is awaiting your endorsement.

#                     Please review and take action.
#                     <p><a href='{get_url(f"/app/project-proposal/{project_proposal.name}")}' target='_blank'>Click here to view the Project Proposal</a></p>
#                 """,
#                 doctype="Project Proposal",
#                 name=project_proposal.name,
#                 for_doctype="Project Proposal",
#                 for_email_account=None,
#             )
#             frappe.msgprint("Notification sent to Dean, RnD.")
#         else:
#             frappe.msgprint("No users found with 'Dean, RnD' role to notify. Ensure the role is assigned and valid.")

#         return {"success": True, "message": "Endorsement processed and submitted for approval."}

#     except frappe.exceptions.ValidationError as e:
#         # Catch Frappe ValidationErrors explicitly, e.g., if submit() fails a validation hook
#         frappe.log_error(frappe.get_traceback(), "Endorsement Validation Error")
#         frappe.throw(f"Validation Error: {e}")
#         return {"success": False, "error": str(e)}
#     except frappe.exceptions.WorkflowStateError as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Workflow Error")
#         frappe.throw(f"Workflow Error: {e}. Check your workflow configuration (transitions, roles).")
#         return {"success": False, "error": str(e)}
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Processing Error")
#         frappe.throw(f"An unexpected error occurred during endorsement processing: {e}")
#         return {"success": False, "error": str(e)}


# -------------------------Manish [22-10-2025] V3----------------------------

# import frappe
# from frappe.utils import get_url
# # from frappe.core.doctype.file.file import get_max_file_size # This import is not directly used in the current code, can be removed if not needed elsewhere

# # Import the base Document class for your Doctype controller
# from frappe.model.document import Document

# # Define the controller class for your Project Proposal doctype
# # This class name MUST match your doctype name (e.g., 'Project Proposal' -> class ProjectProposal)
# class ProjectProposal(Document):
#     # You can add methods here that are specific to your Project Proposal doctype
#     # For example, methods to validate fields, calculate values, or custom logic
#     # For this specific scenario, simply defining the class is enough to resolve the ImportError.
#     def validate(self):
#         # Example: Add some custom validation logic here if needed
#         # frappe.msgprint(f"Validating Project Proposal: {self.name}")
#         pass

#     def on_submit(self):
#         # Example: Logic to run when the document is submitted
#         # frappe.msgprint(f"Project Proposal {self.name} has been submitted.")
#         pass

# # Your existing whitelisted function follows below
# @frappe.whitelist()
# def generate_endorsement_pdf_and_notify(docname):
#     """
#     Generates the endorsement PDF, updates status, submits for workflow,
#     and creates a Frappe notification for the Dean, RnD role.
#     """
#     try:
#         # frappe.get_doc will now successfully find the ProjectProposal class
#         project_proposal = frappe.get_doc('Project Proposal', docname)

#         # 1. Generate PDF (for archival/review, not emailing as attachment)
#         # This PDF will be available in the document's attachments or print menu.
#         pdf_file = frappe.get_print(
#             'Project Proposal',
#             docname,
#             print_format='Project Endorsement Letterhead', # Name of your custom print format
#             as_pdf=True,
#             no_letterhead=False # Use letterhead as set in print format
#         )

#         if not pdf_file:
#             frappe.log_error(f"Failed to generate PDF for Project Proposal {docname}", "Endorsement Generation Error")
#             # If PDF generation is critical, you might want to frappe.throw here
#             # frappe.throw("Failed to generate endorsement PDF.")


#         # Optionally, save the PDF as an attachment to the Project Proposal document
#         if pdf_file:
#             # Check for file size before attaching, Frappe has a limit (default 1MB)
#             max_file_size = frappe.get_system_settings("max_file_size") or 1048576 # Default to 1MB if setting not found
#             if len(pdf_file) > max_file_size:
#                 frappe.msgprint(f"Endorsement PDF size ({len(pdf_file)} bytes) exceeds maximum allowed file size ({max_file_size} bytes). PDF not attached.")
#                 frappe.log_error(f"Endorsement PDF for {project_proposal.name} exceeded max file size. Not attached.", "Endorsement File Size Error")
#             else:
#                 frappe.get_doc({
#                     "doctype": "File",
#                     "file_name": f"Project Endorsement - {project_proposal.name}.pdf",
#                     "attached_to_doctype": "Project Proposal",
#                     "attached_to_name": project_proposal.name,
#                     "content": pdf_file,
#                     "is_private": 1 # Keep private if only for internal review
#                 }).insert(ignore_permissions=True)


#         # 2. Update endorsement status to 'Pending Approval' and Submit
#         if project_proposal.docstatus == 0: # If draft
#             project_proposal.endorsement_status = 'Pending Dean Approval'
#             # The submit() method will trigger the workflow
#             # It also sets docstatus to 1 (Submitted)
#             project_proposal.submit()
#             frappe.msgprint("Project Proposal submitted for endorsement.")
#         elif project_proposal.docstatus == 1 and project_proposal.endorsement_status == 'Draft':
#             # This handles cases where the doc might have been submitted (docstatus 1)
#             # but endorsement_status was manually reverted to 'Draft'.
#             project_proposal.set('endorsement_status', 'Pending Dean Approval')
#             project_proposal.save(ignore_permissions=True)
#             frappe.msgprint("Project Proposal endorsement status updated.")
#         else:
#              # If docstatus is not 0 (Draft) or 1 (Submitted), or endorsement_status is not 'Draft'
#              # then we are not initiating a new submission.
#              # This might happen if someone clicks the button on an already pending/approved doc.
#              frappe.msgprint("Project Proposal is already in a workflow state or submitted. No action taken.")
#              return {"success": False, "error": "Document not in a state to be submitted for endorsement."}


#         # 3. Create a Frappe Notification for Dean, RnD role
#         dean_rnd_users = frappe.get_list('User', filters={'roles': 'Dean, RnD'}, pluck='name')

#         if dean_rnd_users:
#             frappe.send_notification(
#                 recipients=dean_rnd_users,
#                 subject=f"Action Required: Project Endorsement for {project_proposal.project_title}",
#                 message=f"""
#                     The project proposal "{project_proposal.project_title}" from {project_proposal.principal_investigator_name}
#                     is awaiting your endorsement.

#                     Please review and take action.
#                     <p><a href='{get_url(f"/app/project-proposal/{project_proposal.name}")}' target='_blank'>Click here to view the Project Proposal</a></p>
#                 """,
#                 doctype="Project Proposal",
#                 name=project_proposal.name,
#                 for_doctype="Project Proposal",
#                 for_email_account=None,
#             )
#             frappe.msgprint("Notification sent to Dean, RnD.")
#         else:
#             frappe.msgprint("No users found with 'Dean, RnD' role to notify. Ensure the role is assigned.")

#         return {"success": True, "message": "Endorsement processed and submitted for approval."}

#     except frappe.exceptions.WorkflowStateError as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Workflow Error")
#         frappe.throw(f"Workflow Error: {e}. Check your workflow configuration.")
#         return {"success": False, "error": str(e)}
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), "Endorsement Processing Error")
#         frappe.throw(f"An error occurred during endorsement processing: {e}")
#         return {"success": False, "error": str(e)}

# ------------------------21-10-2025 [Manish V2]----------------------------

# import frappe
# from frappe.model.document import Document

# class ProjectProposal(Document):
#     def validate(self):
#         """Basic validation before saving the document."""
#         if not self.project_title:
#             frappe.throw("Project Title is required.")
#         if not self.proposer_name:
#             frappe.throw("Proposer Name is required.")

#     def before_save(self):
#         """Auto-generate a unique proposal ID if missing."""
#         if not self.proposal_id:
#             self.proposal_id = self._generate_proposal_id()

#     def _generate_proposal_id(self):
#         """Generate a unique proposal ID like PROP-00001"""
#         last_id = frappe.db.get_value("Project Proposal", {}, "proposal_id", order_by="creation desc")
#         if last_id and last_id.startswith("PROP-"):
#             num = int(last_id.split("-")[1]) + 1
#         else:
#             num = 1
#         return f"PROP-{num:05d}"

#     def on_submit(self):
#         """Handle actions after proposal is submitted."""
#         frappe.msgprint(f"Project Proposal '{self.name}' has been submitted for review.")

#     def on_update_after_submit(self):
#         """Allow certain fields to be edited after submission if necessary."""
#         frappe.msgprint("You’ve updated a submitted Project Proposal.")

#     def endorse_proposal(self):
#         """Mark the proposal as Endorsed."""
#         self.status = "Endorsed"
#         self.db_update()
#         frappe.msgprint("Project Proposal endorsed successfully.")

#     def approve_proposal(self):
#         """Mark the proposal as Approved."""
#         self.status = "Approved"
#         self.db_update()
#         frappe.msgprint("Project Proposal approved successfully.")

#     def reject_proposal(self, reason=None):
#         """Reject the proposal with an optional reason."""
#         self.status = "Rejected"
#         if reason:
#             self.rejection_reason = reason
#         self.db_update()
#         frappe.msgprint("Project Proposal rejected.")

#     def put_back_proposal(self):
#         """Revert proposal back to Draft for correction."""
#         self.status = "Draft"
#         self.db_update()
#         frappe.msgprint("Proposal moved back to Draft.")

# # Optional: whitelisted methods (for buttons)
# @frappe.whitelist()
# def generate_endorsement(docname):
#     """Create an Endorsement record for this proposal."""
#     doc = frappe.get_doc("Project Proposal", docname)
#     if doc.status != "Draft":
#         frappe.throw("Only Draft proposals can be endorsed.")
#     doc.endorse_proposal()
#     return {"status": "success", "message": "Endorsement generated successfully."}





# --------------21-10-2025 10:15:00 [Manish V1]-------------- 

# import frappe
# from frappe.utils import now


# @frappe.whitelist()
# def generate_endorsement(docname):
#     doc = frappe.get_doc("Project Proposal", docname)
#     doc.endorsement_status = "Pending Approval"
#     doc.save(ignore_permissions=True)

#     # Assign to DoRnD and allow commenting
#     frappe.share.add(
#         "Project Proposal",
#         doc.name,
#         "dornd@iitg.ac.in",
#         flags={"share": True, "read": 1, "write": 1, "comment": 1}
#     )

#     # Notify DoRnD
#     frappe.sendmail(
#         recipients=["dornd@iitg.ac.in"],
#         subject=f"New Endorsement Pending: {doc.project_title}",
#         message=f"A new project proposal ({doc.name}) is awaiting your review and approval."
#     )

#     frappe.msgprint("Endorsement sent to DoRnD for approval.")
#     return "success"


# @frappe.whitelist()
# def process_endorsement(docname, action):
#     doc = frappe.get_doc("Project Proposal", docname)
#     doc.endorsement_status = action
#     doc.approver_name = frappe.session.user
#     doc.approver_date = now()

#     # Optional: attach digital signature automatically if available
#     user_signature = frappe.db.get_value("User", frappe.session.user, "user_image")
#     if action == "Approved" and user_signature:
#         doc.approver_signature = user_signature

#     # If Put Back → make editable again
#     if action == "Put Back":
#         doc.docstatus = 0  # revert to draft so staff can edit

#     doc.save(ignore_permissions=True)
#     frappe.msgprint(f"Endorsement {action} successfully.")

#     # Notify the document owner
#     frappe.sendmail(
#         recipients=[doc.owner],
#         subject=f"Endorsement {action}: {doc.project_title}",
#         message=f"Your project proposal '{doc.project_title}' has been {action.lower()} by DoRnD."
#     )

#     return "success"
