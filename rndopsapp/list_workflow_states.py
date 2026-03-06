
import frappe
import os
import sys
import json

# Set path to bench sites directory to ensure correct initialization
bench_sites_path = "/home/prornd/project/frappe_dev/prornd/sites"

if __name__ == "__main__":
    if os.path.exists(bench_sites_path):
        os.chdir(bench_sites_path)
        if bench_sites_path not in sys.path:
            sys.path.append(bench_sites_path)
    
    # Add apps directory to sys.path so rndopsapp module can be found
    bench_apps_path = "/home/prornd/project/frappe_dev/prornd/apps"
    if bench_apps_path not in sys.path:
        sys.path.append(bench_apps_path)
    
    # Initialize from sites directory
    frappe.init(site='prornd.local')
    frappe.connect()

    print("\nGLOBAL WORKFLOW STATES (Master List):")
    print("=====================================")
    # Get all defined Workflow States
    global_states = frappe.db.sql("SELECT name, icon, style FROM `tabWorkflow State` ORDER BY name ASC", as_dict=True)
    for gs in global_states:
        print(f"- {gs.name} (Icon: {gs.icon or 'None'}, Style: {gs.style or 'None'})")

    print("\n\nACTIVE WORKFLOWS & FULL DETAILS:")
    print("================================\n")

    # Get active workflows via SQL - Select ALL columns (*)
    active_workflows = frappe.db.sql("SELECT * FROM tabWorkflow WHERE is_active=1", as_dict=True)

    for wf in active_workflows:
        print(f"WORKFLOW: {wf['name']}")
        print("=" * 110)
        
        # Print ALL workflow fields as key-value pairs
        print("WORKFLOW TABLE FIELDS:")
        # Filter out internal/large fields for readability if desired, or print all
        for key, value in wf.items():
            # Skip very long or internal fields for cleaner output, unless requested "all" strictly
            if key in ["_user_tags", "_comments", "_assign", "_liked_by"]: 
                continue 
            print(f"  {key:<25}: {value}")
        
        print("\nWORKFLOW STATES & PERMISSIONS:")
        print("-" * 110)
        # Added ALLOWED EDIT ROLE column
        print(f"{'STATE':<30} | {'DOC STATUS':<10} | {'UPDATE FIELD':<15} | {'ALLOWED EDIT ROLE':<30}")
        print("-" * 110)

        states = frappe.db.sql("""
            SELECT state, doc_status, update_field, allow_edit
            FROM `tabWorkflow Document State`
            WHERE parent = %s
            ORDER BY idx ASC
        """, (wf['name'],), as_dict=True)

        for s in states:
            # allow_edit is the role allowed to edit in this state
            print(f"{s.state:<30} | {s.doc_status:<10} | {s.update_field or 'None':<15} | {s.allow_edit or 'None':<30}")
        
        print("\nTRANSITIONS (All Fields):")
        print("-" * 110)
        
        transitions = frappe.db.sql("""
            SELECT *
            FROM `tabWorkflow Transition`
            WHERE parent = %s
            ORDER BY idx ASC, state ASC
        """, (wf['name'],), as_dict=True)

        if not transitions:
            print("  (No transitions found)")
        
        for t in transitions:
            print("  TRANSITION:")
            for key, value in t.items():
                if key in ["_user_tags", "_comments", "_assign", "_liked_by", "parent", "parentfield", "parenttype"]:
                    continue
                if value is None: value = "None"
                # Handle long conditions or descriptions
                value_str = str(value)
                if len(value_str) > 100:
                    # Truncate very long values for display or keep them if critical? User said "all fields".
                    pass # Let's show full value if possible, maybe just indented on new line if multiline
                
                print(f"    {key:<25}: {value_str}")
            print("  " + "-" * 40)

        print("\n")
