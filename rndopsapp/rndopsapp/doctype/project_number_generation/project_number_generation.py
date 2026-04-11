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
        if not self.current_year1:
            self.current_year1 = frappe.utils.now_datetime().year

    def autoname(self):
        # autoname runs first in Frappe's lifecycle, so getseries must be here
        # to ensure project_no is available when the name is assembled.
        from frappe.model.naming import getseries

        current_year = frappe.utils.now_datetime().year

        # 1. Year (2 digits)
        year = str(current_year)[-2:]

        # 2. Category (1)
        cat = str(self.category or "C")[:1]

        # 3. Dept Initial (4) - repeat last char if shorter than 4
        dept_raw = str(self.dept_initial or "A").upper()
        dept = dept_raw.ljust(4, dept_raw[-1])[:4]

        # 4. Project Type (2)
        ptype = str(self.project_type or "SP")[:2]

        # 5. Emp ID (4) - zero-padded
        eid = str(self.emp_id or "0").zfill(4)[-4:]

        # 6. Emp Initial (4) - always 4 chars from generation logic; repeat last char as safety net
        einit_raw = str(self.emp_initial or "A").upper()
        einit = einit_raw.ljust(4, einit_raw[-1])[:4]

        # 7. Project No (4) - global sequential, resets each year
        series_key = f"PROJ-{current_year}-"

        # If tabSeries row doesn't exist yet (projects created before this logic),
        # seed it from the MAX project_no of existing records so numbering continues
        # correctly instead of restarting from 0001.
        if not frappe.db.sql("SELECT 1 FROM `tabSeries` WHERE `name` = %s", series_key):
            max_result = frappe.db.sql("""
                SELECT MAX(CAST(project_no AS UNSIGNED))
                FROM `tabProject Number Generation`
                WHERE current_year1 = %s
                AND project_no IS NOT NULL AND project_no != ''
            """, current_year)
            seed = int(max_result[0][0] or 0) if max_result else 0
            # INSERT IGNORE handles concurrent race — only one thread wins, others skip
            frappe.db.sql(
                "INSERT IGNORE INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
                (series_key, seed)
            )

        self.project_no = getseries(series_key, 4)
        proj = self.project_no

        # Total: 2+1+4+2+4+4+4 = 21
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
            proj_reg = frappe.get_doc("Project Registration", doc_name)

            pi_email = proj_reg.get("pi_userid") or proj_reg.get("pi_webmail") or ""
            pi_employee_id = proj_reg.get("pi_employee_id")

            current_year = frappe.utils.now_datetime().year
            year_2digit = str(current_year)[-2:]

            # Preview next global sequential number (read-only peek, not consumed)
            series_key = f"PROJ-{current_year}-"
            result = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s", series_key)
            if result:
                current_series_val = int(result[0][0] or 0)
            else:
                # Series not seeded yet — read MAX project_no from existing records
                max_result = frappe.db.sql("""
                    SELECT MAX(CAST(project_no AS UNSIGNED))
                    FROM `tabProject Number Generation`
                    WHERE current_year1 = %s
                    AND project_no IS NOT NULL AND project_no != ''
                """, current_year)
                current_series_val = int(max_result[0][0] or 0) if max_result else 0
            calculated_project_no = str(current_series_val + 1).zfill(4)

            # Department initial
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

            # Emp initial from PI name; fill short slots from username chars, never use X
            pi_name = proj_reg.get("principal_investigator_name", "")
            username_chars = pi_email.split("@")[0].upper()

            if pi_name:
                name_parts = [p for p in pi_name.strip().split() if p]
                if len(name_parts) == 1:
                    source = name_parts[0].upper() + username_chars
                    emp_initial = source[:4]
                else:
                    part1 = name_parts[0].upper()
                    part2 = name_parts[1].upper()
                    init = part1[:2] + part2[:2]
                    if len(init) < 4:
                        extra = (part1[2:] + part2[2:]
                                 + "".join(p.upper() for p in name_parts[2:])
                                 + username_chars)
                        init = init + extra
                    emp_initial = init[:4]
            else:
                emp_initial = username_chars[:4] if username_chars else "UNKN"

            # Category and project type
            project_type_mapping = {"Research": "R", "Consultancy": "C", "Other": "O"}
            category = project_type_mapping.get(proj_reg.get("project_type"), "C")

            proj_type_from_reg = proj_reg.get("project_type", "")
            project_type_code = "SP"
            if "Consultancy" in proj_type_from_reg:
                project_type_code = "CN"
            elif "Research" in proj_type_from_reg:
                project_type_code = "SP"
            elif "Other" in proj_type_from_reg:
                project_type_code = "OT"

            # Preview project name (mirrors autoname logic)
            dept_raw = (dept_initial or "A").upper()
            dept_formatted = dept_raw.ljust(4, dept_raw[-1])[:4]
            eid_formatted = str(pi_employee_id or "0").zfill(4)[-4:]
            einit_raw = emp_initial or "A"
            einit_formatted = einit_raw.ljust(4, einit_raw[-1])[:4]
            preview_project_name = f"{year_2digit}{category[:1]}{dept_formatted}{project_type_code[:2]}{eid_formatted}{einit_formatted}{calculated_project_no}"

            final_project_number = preview_project_name
            prefill_data = {
                "emp_id": pi_employee_id,
                "current_year1": year_2digit,
                "project_no": calculated_project_no,
                "select_department": implementation_dept,
                "dept_initial": dept_initial,
                "category": category,
                "project_type": project_type_code,
                "emp_initial": emp_initial,
                "principal_investigator_name": proj_reg.get("principal_investigator_name"),
                "pi_email": pi_email,
                "preview_project_name": preview_project_name
            }
        except Exception as e:
            frappe.log_error(f"Error fetching Project Registration data: {str(e)}")

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

