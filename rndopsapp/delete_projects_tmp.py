import frappe

def execute():
    projects = [
        "2026040201000105"
# "2026040701ADA000135"
#         "2026040601000134",
# "2026040601000133",
# "2026040601000132",
# "2026040601MeiTy000122",
# "2026040501ADA000121",
    ]
    
    deleted = []
    not_found = []
    
    for project in projects:
        if frappe.db.exists("Project Registration", project):
            try:
                # Get doc status
                docstatus = frappe.db.get_value("Project Registration", project, "docstatus")
                
                # If submitted, force cancel it without running triggers
                if docstatus == 1:
                    frappe.db.set_value("Project Registration", project, "docstatus", 2)
                    frappe.db.commit() # commit docstatus change so delete works
                
                frappe.delete_doc("Project Registration", project, ignore_permissions=True, force=True)
                deleted.append(project)
            except Exception as e:
                print(f"Failed to delete {project} normally: {e}")
                
                try:
                    # Last resort: raw SQL to bypass all checks
                    frappe.db.sql("DELETE FROM `tabProject Registration` WHERE name = %s", (project,))
                    deleted.append(project + " (raw SQL)")
                except Exception as e2:
                     print(f"SQL check failed for {project}: {e2}")
                     not_found.append(project)
        else:
            not_found.append(project)
            
    frappe.db.commit()
    print(f"Deleted: {deleted}")
    print(f"Not found: {not_found}")


# bench --site prornd.local execute rndopsapp.delete_projects_tmp.execute


# Hardcoded gate password shared by the Danger Zone / restricted admin actions
# in kafka_control.html (delete projects, delete doctype records, clear mattermost, workflow override).
ADMIN_ACTION_PASSWORD = "password@123"


@frappe.whitelist()
def delete_project_registrations(projects, override_password=None):
    """
    Delete one or more Project Registration documents AND their MinIO files.
    Accepts `projects` as a comma-separated string or JSON list.
    Only accessible by System Manager.
    """
    import json
    from rndopsapp.minio import get_rnd_file_service

    if override_password != ADMIN_ACTION_PASSWORD:
        return {"status": "error", "message": "Incorrect password. No projects were deleted."}

    user_roles = frappe.get_roles(frappe.session.user)
    if "System Manager" not in user_roles:
        frappe.throw("Only System Manager can delete Project Registrations.", frappe.PermissionError)

    # Parse input
    if isinstance(projects, str):
        projects = projects.strip()
        if projects.startswith("["):
            projects = json.loads(projects)
        else:
            projects = [p.strip() for p in projects.split(",") if p.strip()]

    deleted = []
    not_found = []
    errors = []

    try:
        file_service = get_rnd_file_service()
        minio_available = True
    except Exception as e:
        minio_available = False
        print(f"MinIO unavailable: {e}")

    for project in projects:
        if not frappe.db.exists("Project Registration", project):
            not_found.append(project)
            continue

        minio_note = ""

        # --- 1. Delete MinIO files ---
        if minio_available:
            try:
                # Path pattern used by RNDFileService._path: Project_Registration/{docname}/...
                prefix = f"Project_Registration/{project}/"
                objects = file_service.storage.list_prefix(prefix)
                count = 0
                for obj in objects:
                    file_service.storage.delete(obj.object_name)
                    count += 1

                # Clean up Frappe File metadata records attached to this doc
                frappe.db.delete("File", {
                    "attached_to_doctype": "Project Registration",
                    "attached_to_name": project
                })
                frappe.db.commit()
                minio_note = f" (+{count} MinIO file(s) purged)"
            except Exception as e:
                minio_note = f" (MinIO cleanup error: {str(e)})"

        # --- 2. Delete Frappe document ---
        try:
            docstatus = frappe.db.get_value("Project Registration", project, "docstatus")
            if docstatus == 1:
                frappe.db.set_value("Project Registration", project, "docstatus", 2)
                frappe.db.commit()

            frappe.delete_doc("Project Registration", project, ignore_permissions=True, force=True)
            frappe.db.commit()
            deleted.append(project + minio_note)
        except Exception as e:
            try:
                frappe.db.sql("DELETE FROM `tabProject Registration` WHERE name = %s", (project,))
                frappe.db.commit()
                deleted.append(project + " (raw SQL)" + minio_note)
            except Exception as e2:
                errors.append(f"{project}: {str(e2)}")

    return {
        "deleted": deleted,
        "not_found": not_found,
        "errors": errors
    }