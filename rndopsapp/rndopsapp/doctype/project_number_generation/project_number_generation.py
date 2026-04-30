import frappe
from frappe.model.document import Document
import json


CATEGORY_BY_PROJECT_TYPE = {"Research": "R", "Consultancy": "C", "Other": "O"}


def _financial_year(dt=None):
    """Indian FY (Apr-Mar) as a 4-digit string. Apr 2026 -> '2627'."""
    dt = dt or frappe.utils.now_datetime()
    if dt.month >= 4:
        start, end = dt.year, dt.year + 1
    else:
        start, end = dt.year - 1, dt.year
    return f"{str(start)[-2:]}{str(end)[-2:]}"


def _fetch_from_user(pi_email):
    """Resolve employee_id, pi_initials, department and dept_initials from User."""
    if not pi_email:
        return {}
    user = frappe.db.get_value(
        "User",
        pi_email,
        ["employee_id", "pi_initials", "department_name"],
        as_dict=True,
    )
    if not user:
        return {}
    dept_initials = None
    dept_name = None
    if user.department_name:
        dept_row = frappe.db.get_value(
            "Department_prornd",
            user.department_name,
            ["dept_initials", "dept_name"],
            as_dict=True,
        )
        if dept_row:
            dept_initials = dept_row.dept_initials
            dept_name = dept_row.dept_name
    return {
        "employee_id": user.employee_id,
        "pi_initials": user.pi_initials,
        "department_name": user.department_name,
        "dept_initials": dept_initials,
        "dept_name": dept_name,
    }


def _peek_next_sequence(fin_year):
    """Return the next 4+ digit sequential number for a financial year without consuming it."""
    series_key = f"PROJ-{fin_year}-"
    result = frappe.db.sql(
        "SELECT `current` FROM `tabSeries` WHERE `name` = %s", series_key
    )
    if result:
        current_series_val = int(result[0][0] or 0)
    else:
        max_result = frappe.db.sql(
            """
            SELECT MAX(CAST(project_no AS UNSIGNED))
            FROM `tabProject Number Generation`
            WHERE current_year1 = %s
            AND project_no IS NOT NULL AND project_no != ''
            """,
            fin_year,
        )
        current_series_val = int(max_result[0][0] or 0) if max_result else 0
    return str(current_series_val + 1).zfill(4)


class ProjectNumberGeneration(Document):
    def validate(self):
        if self.current_year1:
            self.current_year1 = str(self.current_year1).strip()[:4]
        if self.category:
            self.category = str(self.category).strip().upper()[:1]
        if self.dept_initial:
            self.dept_initial = str(self.dept_initial).strip().upper()[:4]
        if self.emp_id:
            self.emp_id = str(self.emp_id).strip().zfill(4)[-4:]
        if self.emp_initial:
            self.emp_initial = str(self.emp_initial).strip().upper()[:4]

        if (
            not self.current_year1
            or len(self.current_year1) != 4
            or not self.current_year1.isdigit()
        ):
            frappe.throw("Financial Year must be exactly 4 digits (e.g. 2627)")
        if self.category not in ("R", "C", "O"):
            frappe.throw("Category must be one of R, C, or O")
        if (
            not self.dept_initial
            or len(self.dept_initial) != 4
            or not self.dept_initial.isalpha()
        ):
            frappe.throw("Department Initials must be exactly 4 uppercase letters")
        if not self.emp_id or len(self.emp_id) != 4 or not self.emp_id.isdigit():
            frappe.throw("Employee ID must be 4 digits after zero-padding")
        if (
            not self.emp_initial
            or len(self.emp_initial) != 4
            or not self.emp_initial.isalpha()
        ):
            frappe.throw("PI Initials must be exactly 4 uppercase letters")

    def before_insert(self):
        if not self.current_year1:
            self.current_year1 = _financial_year()

    def autoname(self):
        from frappe.model.naming import getseries

        fin_year = self.current_year1 or _financial_year()
        self.current_year1 = fin_year

        cat = (self.category or "").upper()[:1]
        dept = (self.dept_initial or "").upper()[:4]
        eid = str(self.emp_id or "").zfill(4)[-4:]
        einit = (self.emp_initial or "").upper()[:4]

        series_key = f"PROJ-{fin_year}-"

        # Seed the counter from the highest existing project_no so legacy records
        # in this FY aren't re-used by a fresh sequence starting at 0001.
        if not frappe.db.sql("SELECT 1 FROM `tabSeries` WHERE `name` = %s", series_key):
            max_result = frappe.db.sql(
                """
                SELECT MAX(CAST(project_no AS UNSIGNED))
                FROM `tabProject Number Generation`
                WHERE current_year1 = %s
                AND project_no IS NOT NULL AND project_no != ''
                """,
                fin_year,
            )
            seed = int(max_result[0][0] or 0) if max_result else 0
            frappe.db.sql(
                "INSERT IGNORE INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
                (series_key, seed),
            )

        user_supplied = str(self.project_no or "").strip()
        if user_supplied.isdigit():
            # User-supplied number wins. Bump the series high-water mark so the
            # next auto-generation can't hand out the same value.
            padded = user_supplied.zfill(4)
            frappe.db.sql(
                "UPDATE `tabSeries` SET `current` = GREATEST(`current`, %s) WHERE `name` = %s",
                (int(padded), series_key),
            )
            self.project_no = padded
        else:
            # getseries pads to 4 minimum and grows past 9999 without overflow.
            self.project_no = getseries(series_key, 4)

        self.name = f"{fin_year}{cat}-{self.project_no}-{dept}{eid}{einit}"


@frappe.whitelist()
def get_project_number_generation_fields(doc_name=None):
    meta = frappe.get_meta("Project Number Generation")
    fields = []
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
            "depends_on_eval": f.depends_on.replace("eval:", "")
            if f.depends_on and f.depends_on.startswith("eval:")
            else None,
        }

        if f.fieldname == "project_no":
            field_data["read_only"] = 1

        if f.fieldtype == "Table":
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [
                {
                    "fieldname": cf.fieldname,
                    "label": cf.label,
                    "fieldtype": cf.fieldtype,
                    "options": cf.options,
                    "in_list_view": cf.in_list_view,
                    "read_only": cf.read_only,
                    "mandatory": cf.reqd,
                }
                for cf in child_meta.fields
            ]

        fields.append(field_data)

        if f.fieldname == "select_department" and f.fieldtype == "Link":
            try:
                link_options["select_department"] = frappe.get_all(
                    f.options,
                    fields=["name as value", "dept_name as label"],
                    order_by="dept_name asc",
                )
            except Exception:
                link_options["select_department"] = []

    prefill_data = {}
    calculated_project_no = None
    final_project_number = None

    if doc_name:
        try:
            proj_reg = frappe.get_doc("Project Registration", doc_name)

            pi_email = proj_reg.get("pi_userid") or proj_reg.get("pi_webmail") or ""

            user_data = _fetch_from_user(pi_email)
            employee_id = user_data.get("employee_id")
            pi_initials = user_data.get("pi_initials")

            # Department always comes from the project's implementation_department,
            # not the PI's user profile (they may be from a different department).
            department = proj_reg.get("implementation_department")
            dept_initials = None
            dept_name = None
            if department:
                dept_row = frappe.db.get_value(
                    "Department_prornd",
                    department,
                    ["dept_initials", "dept_name"],
                    as_dict=True,
                )
                if dept_row:
                    dept_initials = dept_row.dept_initials
                    dept_name = dept_row.dept_name

            fin_year = _financial_year()
            calculated_project_no = _peek_next_sequence(fin_year)

            category = CATEGORY_BY_PROJECT_TYPE.get(proj_reg.get("project_type"), "C")

            dept_formatted = (str(dept_initials or "").upper()[:4]) or "XXXX"
            eid_formatted = (str(employee_id or "").strip().zfill(4)[-4:]) if (employee_id and str(employee_id).strip()) else "XXXX"
            einit_formatted = (str(pi_initials or "").upper()[:4]) or "XXXX"

            preview_project_name = (
                f"{fin_year}{category}-{calculated_project_no}"
                f"-{dept_formatted}{eid_formatted}{einit_formatted}"
            )

            final_project_number = preview_project_name
            prefill_data = {
                "emp_id": eid_formatted,
                "current_year1": fin_year,
                "project_no": calculated_project_no,
                "select_department": department,
                "dept_name": dept_name,
                "dept_initial": dept_formatted,
                "category": category,
                "emp_initial": einit_formatted,
                "principal_investigator_name": proj_reg.get(
                    "principal_investigator_name"
                ),
                "pi_email": pi_email,
                "preview_project_name": preview_project_name,
            }
        except Exception as e:
            frappe.log_error(
                f"Error fetching Project Registration data: {str(e)}"
            )

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "calculated_project_no": calculated_project_no,
        "final_project_number": final_project_number,
        "link_options": link_options,
    }


@frappe.whitelist()
def save_project_number_generation_data(data, projrefno=None):
    """
    Save Project Number Generation data.

    The canonical source for emp_id, pi_initials (emp_initial) and department is
    the User record of the PI (resolved via Project Registration's pi_userid /
    pi_webmail). Anything missing from the incoming payload is filled from User
    before save so autoname has the full set.
    """
    if isinstance(data, str):
        data = json.loads(data)

    try:
        if data.get("name"):
            doc = frappe.get_doc("Project Number Generation", data.get("name"))
        else:
            doc = frappe.new_doc("Project Number Generation")

        allowable_fields = [
            "current_year1",
            "category",
            "select_department",
            "dept_initial",
            "emp_id",
            "emp_initial",
            "project_no",
            "workflow_state",
        ]

        for field in allowable_fields:
            if field in data:
                doc.set(field, data[field])

        pi_email = None
        if projrefno:
            try:
                proj_reg = frappe.get_doc("Project Registration", projrefno)
                pi_email = proj_reg.get("pi_userid") or proj_reg.get("pi_webmail")
                if not doc.category and proj_reg.get("project_type"):
                    doc.category = CATEGORY_BY_PROJECT_TYPE.get(
                        proj_reg.get("project_type"), "C"
                    )
            except Exception:
                pass

        if pi_email and (
            not doc.emp_id
            or not doc.emp_initial
            or not doc.select_department
            or not doc.dept_initial
        ):
            user_data = _fetch_from_user(pi_email)
            if not doc.emp_id and user_data.get("employee_id"):
                doc.emp_id = user_data.get("employee_id")
            if not doc.emp_initial and user_data.get("pi_initials"):
                doc.emp_initial = user_data.get("pi_initials")
            if not doc.select_department and user_data.get("department_name"):
                doc.select_department = user_data.get("department_name")
            if not doc.dept_initial and user_data.get("dept_initials"):
                doc.dept_initial = user_data.get("dept_initials")

        if doc.select_department and not doc.dept_initial:
            try:
                dept_doc = frappe.get_doc(
                    "Department_prornd", doc.select_department
                )
                if hasattr(dept_doc, "dept_initials"):
                    doc.dept_initial = dept_doc.dept_initials
            except Exception:
                pass

        if not doc.current_year1:
            doc.current_year1 = _financial_year()

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        if projrefno:
            try:
                if frappe.db.exists("Project Registration", projrefno):
                    frappe.db.set_value(
                        "Project Registration", projrefno, "project_no", doc.name
                    )
                    frappe.db.commit()
            except Exception as e:
                print(f"Error updating Project Registration {projrefno}: {e}")
                return {
                    "status": "success",
                    "docname": doc.name,
                    "warning": f"Project generated but failed to update Registration: {str(e)}",
                }

        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def perform_project_number_generation_action(docname, action):
    try:
        wf_name = frappe.db.get_value(
            "Workflow",
            {"document_type": "Project Number Generation", "is_active": 1},
            "name",
        )

        if not wf_name:
            return {
                "status": "error",
                "message": "No active workflow for Project Number Generation",
            }

        wf = frappe.get_doc("Workflow", wf_name)
        doc = frappe.get_doc("Project Number Generation", docname)
        current_state = doc.workflow_state

        next_state = None
        for t in wf.transitions:
            if t.state == current_state and t.action == action:
                next_state = t.next_state
                break

        if not next_state:
            frappe.throw("Invalid Action")

        doc.workflow_state = next_state
        doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {"status": "success", "next_state": next_state}

    except Exception as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
