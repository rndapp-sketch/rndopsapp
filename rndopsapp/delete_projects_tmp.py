import frappe

def execute():
    projects = [
        "2026040501000118"
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