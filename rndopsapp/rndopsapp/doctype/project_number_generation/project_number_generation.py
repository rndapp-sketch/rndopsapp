import frappe
from frappe.model.document import Document
from frappe.model.naming import make_autoname
import json

class ProjectNumberGeneration(Document):
    def validate(self):
        # Ensure fields respect their max char lengths to prevent Frappe truncation errors
        if self.dept_initial:
            self.dept_initial = str(self.dept_initial).strip()[:4]
        if self.emp_initial:
            self.emp_initial = str(self.emp_initial).strip()[:4]
        if self.emp_id:
            self.emp_id = str(self.emp_id).strip()[:5]

    def before_insert(self):
        # Auto-generate project_no based on PI and year - no manual entry allowed
        # 1. Get current year dynamically from current date
        current_year = frappe.utils.now_datetime().year

        # 2. Get PI email from the calling context (should be passed from save function)
        # If not available, fall back to emp_id based counting
        pi_email = getattr(self, '_pi_email', None)

        if pi_email:
            # 3a. Count existing projects for this PI (by email) in current year
            # Only count Project Registration records where project_no is populated
            existing_count = frappe.db.sql("""
                SELECT COUNT(*)
                FROM `tabProject Registration`
                WHERE (pi_userid = %s OR pi_webmail = %s)
                AND project_no IS NOT NULL
                AND project_no != ''
                AND SUBSTRING(project_no, 1, 2) = %s
            """, (pi_email, pi_email, str(current_year)[-2:]))[0][0]
        else:
            # 3b. Fallback: Count by emp_id (normalized to handle leading zeros)
            normalized_emp_id = str(self.emp_id).lstrip('0') if self.emp_id else "0"
            existing_count = frappe.db.sql("""
                SELECT COUNT(*)
                FROM `tabProject Number Generation`
                WHERE CAST(emp_id AS UNSIGNED) = %s
                AND current_year1 = %s
            """, (normalized_emp_id, current_year))[0][0]

        # 4. Next project number is count + 1 (resets each year)
        next_project_no = existing_count + 1

        # 5. Format as 4 digits with leading zeros
        self.project_no = str(next_project_no).zfill(4)

        # 6. Set current_year1 if not already set
        if not self.current_year1:
            self.current_year1 = current_year

    def autoname(self):
        # 1. Year (2 digits) - dynamically get last 2 digits of current year
        current_year = frappe.utils.now_datetime().year
        year = str(current_year)[-2:]

        # 2. Category (1)
        cat = str(self.category or "C")[:1]

        # 3. Project No (4) - Leading 0s (auto-generated in before_insert)
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

        # Force project_no to be read-only - it's auto-generated
        if f.fieldname == "project_no":
            field_data["read_only"] = 1

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

    # 3. Prepare Prefill Data from Project Registration
    prefill_data = {}
    calculated_project_no = None
    final_project_number = None

    if doc_name:
        try:
            # doc_name should be Project Registration docname
            proj_reg = frappe.get_doc("Project Registration", doc_name)

            # Get PI details from Project Registration
            # Use pi_userid or pi_webmail as the primary identifier
            pi_email = proj_reg.get("pi_userid") or proj_reg.get("pi_webmail")
            pi_employee_id = proj_reg.get("pi_employee_id")

            if pi_email:
                # Get current year dynamically
                current_year = frappe.utils.now_datetime().year
                year_2digit = str(current_year)[-2:]

                # Count existing Project Registration records for this PI in current year
                # Only count records where project_no is populated (not NULL or empty)
                existing_projects = frappe.db.sql("""
                    SELECT COUNT(*)
                    FROM `tabProject Registration`
                    WHERE (pi_userid = %s OR pi_webmail = %s)
                    AND project_no IS NOT NULL
                    AND project_no != ''
                    AND SUBSTRING(project_no, 1, 2) = %s
                """, (pi_email, pi_email, year_2digit))[0][0]

                # Next project number
                next_project_no = existing_projects + 1
                calculated_project_no = str(next_project_no).zfill(4)

                # Get implementation department and dept_initial
                implementation_dept = proj_reg.get("implementation_department")
                dept_initial = None

                if implementation_dept:
                    try:
                        dept_doc = frappe.get_doc("Department_prornd", implementation_dept)
                        dept_initial = dept_doc.get("dept_initials")
                        if dept_initial:
                            dept_initial = str(dept_initial).strip()[:4]
                    except Exception:
                        pass

                # Extract PI initials from full name
                pi_name = proj_reg.get("principal_investigator_name", "")
                emp_initial = ""

                if pi_name:
                    # Split name into words and get initials
                    name_parts = pi_name.strip().split()
                    initials = "".join([part[0].upper() for part in name_parts if part])

                    # If we have less than 4 characters, pad with subsequent letters from the last name
                    if len(initials) < 4 and name_parts:
                        last_name = name_parts[-1].upper()
                        # Add subsequent letters from last name
                        char_index = 1
                        while len(initials) < 4 and char_index < len(last_name):
                            initials += last_name[char_index]
                            char_index += 1

                    # If still less than 4, pad with 'X'
                    emp_initial = initials.ljust(4, 'X')[:4]
                else:
                    emp_initial = "XXXX"

                # Get project type and category from Project Registration
                project_type_mapping = {
                    "Research": "R",
                    "Consultancy": "C",
                    "Other": "O"
                }
                category = project_type_mapping.get(proj_reg.get("project_type"), "C")

                # Apply autoname formatting logic to generate preview
                # Format: YY + Category + DeptInitial + ProjectType + EmpID + EmpInitial + ProjectNo
                # Example: 26CxxxxSP0391xxxx0001

                # Get project_type from Project Registration (map to 2-char code)
                proj_type_from_reg = proj_reg.get("project_type", "")
                project_type_code = "SP"  # Default
                if "Consultancy" in proj_type_from_reg:
                    project_type_code = "CN"
                elif "Research" in proj_type_from_reg:
                    project_type_code = "SP"
                elif "Other" in proj_type_from_reg:
                    project_type_code = "OT"

                # Format fields according to autoname logic
                year_formatted = year_2digit
                cat_formatted = category[:1] if category else "C"
                dept_formatted = (dept_initial or "").upper().rjust(4, 'x')[:4]
                ptype_formatted = project_type_code[:2]
                eid_formatted = str(pi_employee_id or "0").zfill(4)[-4:]
                einit_formatted = emp_initial[:4]  # Already formatted to 4 chars
                proj_no_formatted = calculated_project_no

                # Generate final project number with all fields
                preview_project_name = f"{year_formatted}{cat_formatted}{dept_formatted}{ptype_formatted}{eid_formatted}{einit_formatted}{proj_no_formatted}"

                # Store the final project number for return
                final_project_number = preview_project_name

                # Pre-fill data with PI information
                prefill_data = {
                    "emp_id": pi_employee_id,
                    "current_year1": year_2digit,  # Last 2 digits only
                    "project_no": calculated_project_no,
                    "select_department": implementation_dept,
                    "dept_initial": dept_initial,
                    "category": category,
                    "project_type": project_type_code,
                    "emp_initial": emp_initial,  # Auto-extracted from PI name
                    "principal_investigator_name": proj_reg.get("principal_investigator_name"),
                    "pi_email": pi_email,
                    "preview_project_name": preview_project_name
                }
        except Exception as e:
            frappe.log_error(f"Error fetching Project Registration data: {str(e)}")
            pass

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
        "calculated_project_no": calculated_project_no,
        "final_project_number": final_project_number,
        "link_options": link_options,
        # "client_scripts": client_scripts
    }

@frappe.whitelist()
def save_project_number_generation_data(data, projrefno=None):
    """
    Save Project Number Generation data

    Args:
        data (str or dict): JSON string or dictionary containing:
            - current_year1: Year (2 digits) - will be auto-filled if not provided
            - category: Category (C/R/O) - auto-filled from project type
            - select_department: Department link - auto-filled from implementation_department
            - dept_initial: Department initials - auto-filled from department
            - project_type: Project type code (SP/CN/OT) - auto-filled
            - emp_id: Employee ID - auto-filled from PI
            - emp_initial: Employee initials - auto-extracted from PI name
            - workflow_state: Optional workflow state
        projrefno (str): Project Registration document name for linking

    Returns:
        dict: {"status": "success", "docname": generated_doc_name}
    """
    if isinstance(data, str):
        data = json.loads(data)

    try:
        # Create or Get Doc
        if data.get("name"):
            doc = frappe.get_doc("Project Number Generation", data.get("name"))
        else:
            doc = frappe.new_doc("Project Number Generation")

        # Map Fields - Accept all fields from frontend
        # Note: project_no is excluded - it's auto-generated in before_insert
        allowable_fields = [
            "current_year1", "category",
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

        # Get PI email from Project Registration if projrefno is provided
        if projrefno:
            try:
                proj_reg = frappe.get_doc("Project Registration", projrefno)
                pi_email = proj_reg.get("pi_userid") or proj_reg.get("pi_webmail")
                if pi_email:
                    # Pass PI email to the document for use in before_insert
                    doc._pi_email = pi_email
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

