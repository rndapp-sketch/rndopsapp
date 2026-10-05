import frappe

def execute():
    # Get all users
    users = frappe.get_all("User")
    
    for user in users:
        # Check if they are missing Notification Settings
        if not frappe.db.exists("Notification Settings", user.name):
            doc = frappe.new_doc("Notification Settings")
            doc.name = user.name  # The name MUST match the User ID exactly
            doc.insert(ignore_permissions=True, ignore_mandatory=True)
            print(f"Created Notification Settings for {user.name}")
            
    frappe.db.commit()
    print("All missing notification settings have been created!")



# osintpc@osint-Desktop-PC:~/frappe/prornd$ bench --site prornd.local execute rndopsapp.fix_users.execute