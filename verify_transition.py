
import frappe
from rndopsapp.rndopsapp.doctype.travel.travel import perform_travel_action

# Mocking the session and roles mechanism is hard in a script without full test runner, 
# asking the user to verify is more practical.
# However, we can try to inspect the code logic or run a lightweight test if possible.

# Instead of a complex mock, I will write a script that attempts to simulate the finding logic 
# by reading the workflow definition and manual testing the logic I just added, 
# but since I cannot easily mock frappe.session.user globally for a function call in a script
# effectively without side effects, I will rely on the code change I just made which is quite explicit.

# But wait, I can use `frappe.set_user("ls@iitg.ac.in")` if that user exists!
# The user mentioned "ls@iitg.ac.in".

try:
    frappe.connect()
    
    # Check if we can switch user context
    target_user = "ls@iitg.ac.in"
    if not frappe.db.exists("User", target_user):
        print(f"User {target_user} does not exist, cannot verify with this user.")
    else:
        # Create a test Travel doc in Draft state
        doc = frappe.new_doc("Travel")
        doc.applicant_name_travel = "Test User"
        doc.save()
        print(f"Created test doc: {doc.name}")

        # Login as the user
        frappe.set_user(target_user)
        print(f"Switched user to: {frappe.session.user}")
        
        # Verify roles
        roles = frappe.get_roles(target_user)
        print(f"Roles: {roles}")
        
        # Try to perform action
        # Note: This might send emails or actual workflow updates, which is fine for a test doc.
        try:
            result = perform_travel_action(doc.name, "Submit")
            print("Action Result:", result)
            
            if result.get("workflow_state") == "Pending Head Approval":
                print("SUCCESS: Transitioned to 'Pending Head Approval'")
            else:
                print(f"FAILURE: Transitioned to '{result.get('workflow_state')}'")
                
        except Exception as e:
            print(f"Error during action: {e}")
            
        # Cleanup
        frappe.set_user("Administrator")
        frappe.delete_doc("Travel", doc.name)
        print("Cleaned up test doc.")

except Exception as e:
    print(f"Script Error: {e}")

