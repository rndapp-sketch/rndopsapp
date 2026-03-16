import frappe
import json
import os
from frappe.utils import flt, today
from rndopsapp.rndopsapp.kafka.producer.reimbursement.mapper import AccountHeadCommitMapper

JSON_FILE_NAME = "disbursement_of_honorarium_commits.json"

def get_json_file_path():
    """Returns the absolute path to the JSON file in the site's private files directory."""
    site_path = frappe.get_site_path('private', 'files')
    # Ensure directory exists
    if not os.path.exists(site_path):
        os.makedirs(site_path, exist_ok=True)
    return os.path.join(site_path, JSON_FILE_NAME)

def read_json_data():
    """Reads the JSON file and returns the list of commitments."""
    file_path = get_json_file_path()
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                if content.strip():
                    return json.loads(content)
        except Exception as e:
            frappe.log_error(f"Error reading {JSON_FILE_NAME}: {str(e)}", "Commit JSON Read Error")
    return []

def write_json_data(data):
    """Writes the list of commitments to the JSON file."""
    file_path = get_json_file_path()
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        frappe.log_error(f"Error writing to {JSON_FILE_NAME}: {str(e)}", "Commit JSON Write Error")
        return False

@frappe.whitelist()
def submit_commit_data(doctype, frapAppId, name, project_name, commit_amount, budget_head, bmr=None, bill_amount=None, refDetails=None):
    """
    Saves the commit data to a JSON file instead of publishing to Kafka immediately.
    """
    try:
        doc = frappe.get_doc(doctype, name)
        
        # We need to map the document to the DTO exactly how the Kafka producer would
        # using the existing Reimbursement mapper which we will extend
        dto = AccountHeadCommitMapper.map_to_dto(
            doc=doc,
            commit_amount=flt(commit_amount),
            budget_head=budget_head,
            project_name=project_name,
            bmr=bmr,
            bill_amount=flt(bill_amount) if bill_amount else None,
            frap_app_id=frapAppId,
            ref_details=refDetails
        )
        
        payload_data = dto.to_dict()
        
        # Load existing data
        commits = read_json_data()
        
        # Check if a commit for this frapAppId already exists and replace it, otherwise append
        existing_index = next((index for (index, d) in enumerate(commits) if d.get("frapAppId") == frapAppId), None)
        
        if existing_index is not None:
            commits[existing_index] = payload_data
        else:
            commits.append(payload_data)
        
        # Write back to file
        if write_json_data(commits):
            # Optional: Add a comment to the document for the Activity Stream
            try:
                frappe.get_doc({
                    "doctype": "Comment",
                    "comment_type": "Comment",
                    "reference_doctype": doctype,
                    "reference_name": name,
                    "content": f"Commitment data cached and pending final approval. Amount: {commit_amount}"
                }).insert(ignore_permissions=True)
            except Exception:
                pass # Ignore comment failures
                
            return {"status": "success", "message": "Commit data temporarily cached pending final approval."}
        else:
            return {"status": "error", "message": "Failed to write commit data to file."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Submit Commit JSON Data Error")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def get_pending_commits(project_number=None):
    """
    Returns the list of pending commits from the JSON file.
    If project_number is provided, filters the results.
    """
    commits = read_json_data()
    
    if project_number:
        # Filter by projectNumber
        commits = [c for c in commits if c.get("projectNumber") == project_number]
        
    return {"status": "success", "data": commits}
