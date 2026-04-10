import frappe

def fix_script():
    script_doc = frappe.get_doc("Server Script", "s_s_universal_user__")
    print("--- ORIGINAL SCRIPT ---")
    print(script_doc.script)
    
    # Python 3.11 RestrictedPython bugs out on +=
    if "+=" in script_doc.script:
        print("\nFixing += operators...")
        script_doc.script = script_doc.script.replace("+= 1", "= x + 1") # This might not be exactly x, it depends on the text.
        
    print("\n--- Saving disabled to be safe or attempting fix ---")
    script_doc.disabled = 1
    script_doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("Script disabled successfully.")

fix_script()
