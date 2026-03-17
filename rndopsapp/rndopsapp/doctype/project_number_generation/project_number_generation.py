import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
import json

class ProjectNumberGeneration(Document):
    def before_insert(self):
        # If project_no is empty or just '0', get the next serial number
        if not self.project_no or self.project_no == "0":
            # 1. Get Year (2 digits)
            year = str(self.current_year1 or frappe.utils.nowdate()[:4])[-2:]
            
            # 2. Get Emp ID (4 digits, padded)
            eid = str(self.emp_id or "0").zfill(4)[-4:]
            
            # 3. Independent naming series per employee and year
            # format: PRJ-EID-YY-.#### ensures unique sequence in tabSeries
            series_key = f"PRJ-{eid}-{year}-.####"
            
            # make_autoname handles concurrency safely via database locks
            generated_name = make_autoname(series_key)
            
            # 4. Extract the serial number part (last 4 digits) and pad it
            # generated_name will be e.g. "PRJ-0391-26-0001"
            self.project_no = generated_name.split('-')[-1].zfill(4)

    def autoname(self):
        # 1. Year (2)
        year = str(self.current_year1 or "26")[-2:]
        # 2. Category (1)
        cat = str(self.category or "C")[:1]
        # 3. Project No (4) - Leading 0s
        proj = str(self.project_no or "0").zfill(4)[-4:]
        # 4. Dept Initial (4) - Leading x
        dept = str(self.dept_initial or "").upper().rjust(4, 'x')[:4]
        # 5. Project Type (2)
        ptype = str(self.project_type or "SP")[:2]
        # 6. Emp ID (4) - Leading 0s
        eid = str(self.emp_id or "0").zfill(4)[-4:]
        # 7. Emp Initial (4) - Leading x
        einit = str(self.emp_initial or "").upper().rjust(4, 'x')[:4]

        # Total: 2+1+4+4+2+4+4 = 21
        self.name = f"{year}{cat}{dept}{ptype}{eid}{einit}{proj}"

@frappe.whitelist()
def get_project_number_generation_fields(doc_name=None):
    # 1. Fetch Metadata
    meta = frappe.get_meta("Project Number Generation")
    fields = []
    
    # 2. Prepare Link Options Containers
    link_options = {}

    for f in meta.fields:
        field_data = {
            "fieldname": f.fieldname,
            "label": f.label,
            "fieldtype": f.fieldtype,
            "options": f.options,
            "mandatory": f.reqd,
            "read_only": f.read_only,
            "hidden": f.hidden,
            "depends_on": f.depends_on,
            "depends_on_eval": f.depends_on.replace("eval:", "") if f.depends_on and f.depends_on.startswith("eval:") else None
        }
        
        # Handle Child Tables
        if f.fieldtype == "Table":
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [{
                "fieldname": cf.fieldname,
                "label": cf.label,
                "fieldtype": cf.fieldtype,
                "options": cf.options,
                "in_list_view": cf.in_list_view,
                "read_only": cf.read_only,
                "mandatory": cf.reqd
            } for cf in child_meta.fields]
            
        fields.append(field_data)
        
        # Pre-fetch Link Options if needed
        # 'Select Department' is a Link field to 'Department_prornd' (assumed from JSON 'options': 'Department_prornd')
        if f.fieldname == "select_department" and f.fieldtype == "Link":
            try:
                # Fetch all departments. Adjust fields if needed (e.g. name, department_name)
                # Assuming 'Department_prornd' is the doctype name from JSON options
                link_options["select_department"] = frappe.get_all(f.options, fields=["name as value", "name as label"]) 
            except Exception:
                link_options["select_department"] = []

    # 3. Prepare Prefill Data
    prefill_data = {}
    if doc_name:
        doc = frappe.get_doc("Project Number Generation", doc_name)
        prefill_data = doc.as_dict()

    # 4. Client Scripts
    client_scripts = []
    try:
        scripts = frappe.get_all("Client Script", filters={"dt": "Project Number Generation", "enabled": 1}, fields=["name", "script", "view"])
        for script in scripts:
            client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
    except Exception:
        pass

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "link_options": link_options,
        "client_scripts": client_scripts
    }

@frappe.whitelist()
def save_project_number_generation_data(data, projrefno=None):
    if isinstance(data, str):
        data = json.loads(data)
    
    try:
        # Create or Get Doc
        if data.get("name"):
            doc = frappe.get_doc("Project Number Generation", data.get("name"))
        else:
            doc = frappe.new_doc("Project Number Generation")
        
        # Map Fields
        # Based on JSON: current_year1, category, project_no, select_department, dept_initial, project_type, emp_id, emp_initial
        # Also workflow_state if it exists
        allowable_fields = [
            "current_year1", "category", "project_no", 
            "select_department", "dept_initial", 
            "project_type", "emp_id", "emp_initial",
            "workflow_state"
        ]
        
        for field in allowable_fields:
            if field in data:
                doc.set(field, data[field])
        
        # Note: 'dept_initial' fetch_from 'select_department.dept_initials'
        # If 'select_department' is set, we might want to manually fetch dept_initial if the frontend didn't send it
        # or if we want to enforce consistency.
        if doc.select_department and not doc.dept_initial:
             # Try to fetch dept_initial from the linked department if possible
             # options is 'Department_prornd'
             try:
                 dept_doc = frappe.get_doc("Department_prornd", doc.select_department)
                 if hasattr(dept_doc, "dept_initials"):
                     doc.dept_initial = dept_doc.dept_initials
             except Exception:
                 pass

        # Save handles autoname and before_insert
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        # Update Project Registration if projrefno is provided
        if projrefno:
            try:
                # Ensure we only update if the document exists
                if frappe.db.exists("Project Registration", projrefno):
                     frappe.db.set_value("Project Registration", projrefno, "project_no", doc.name)
                     frappe.db.commit()
            except Exception as e:
                # Log error but don't fail the main generation?
                # Or return partial success?
                print(f"Error updating Project Registration {projrefno}: {e}")
                # We can choose to throw or just warning. 
                # User request implies insertion, so maybe better to include in response.
                return {"status": "success", "docname": doc.name, "warning": f"Project generated but failed to update Registration: {str(e)}"}

        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def perform_project_number_generation_action(docname, action):
    # Check if a workflow exists
    try:
        wf_name = frappe.db.get_value("Workflow", {"document_type": "Project Number Generation", "is_active": 1}, "name")
        
        if not wf_name:
            # If no workflow, perhaps just a simple status change or no-op
            return {"status": "error", "message": "No active workflow for Project Number Generation"}

        wf = frappe.get_doc("Workflow", wf_name)
        doc = frappe.get_doc("Project Number Generation", docname)
        current_state = doc.workflow_state
        
        # Find Next State
        next_state = None
        for t in wf.transitions:
            if t.state == current_state and t.action == action:
                next_state = t.next_state
                break
                
        if not next_state:
            frappe.throw("Invalid Action")

        # Update & Save
        doc.workflow_state = next_state
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {"status": "success", "next_state": next_state}

    except Exception as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}

