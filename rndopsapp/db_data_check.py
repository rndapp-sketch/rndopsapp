import frappe
import json
import os
import sys

# Set path to bench root so frappe can find sites and logs
bench_path = "/home/prornd/project/frappe_dev/prornd"
os.chdir(bench_path)
sys.path.append(bench_path)

# Ensure logs directory exists to prevent FileNotFoundError
log_dir = os.path.join(bench_path, "logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Initialize and Connect
frappe.init(site='prornd.local', sites_path='sites')
frappe.connect()

def get_workflow_details(workflow_name):
    # Querying the database for all transition details
    transitions = frappe.db.sql("""
        SELECT 
            state, 
            action, 
            next_state, 
            allowed, 
            `condition` 
        FROM 
            `tabWorkflow Transition` 
        WHERE 
            parent = %s
        ORDER BY 
            state ASC
    """, (workflow_name,), as_dict=True)

    print(f"{'STATE':<25} | {'ACTION':<15} | {'NEXT STATE':<25} | {'ROLE':<20}")
    print("-" * 95)

    for row in transitions:
        state = row.get('state')
        action = row.get('action')
        next_s = row.get('next_state')
        role = row.get('allowed')
        cond = row.get('condition')

        print(f"{state:<25} | {action:<15} | {next_s:<25} | {role:<20}")
        if cond:
            # Print the condition on a new line for clarity
            print(f"   ↳ Condition: {cond.strip()}")
            print("-" * 95)

# Execute
get_workflow_details("Temp_adv_workflow")