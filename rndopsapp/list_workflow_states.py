


import frappe
import os
import sys

bench_sites_path = "/home/prornd/project/frappe_dev/prornd/sites"
bench_apps_path = "/home/prornd/project/frappe_dev/prornd/apps"

REPORT_DIR = "/home/prornd/project/frappe_dev/prornd/apps/rndopsapp/rndopsapp"
REPORT_FILE = os.path.join(REPORT_DIR, "workflow_audit_report.md")

if __name__ == "__main__":

    if os.path.exists(bench_sites_path):
        os.chdir(bench_sites_path)
        if bench_sites_path not in sys.path:
            sys.path.append(bench_sites_path)

    if bench_apps_path not in sys.path:
        sys.path.append(bench_apps_path)

    frappe.init(site="prornd.local")
    frappe.connect()

    os.makedirs(REPORT_DIR, exist_ok=True)

    with open(REPORT_FILE, "w") as md:

        md.write("# Frappe Workflow Audit Report\n\n")

        md.write("Generated from system workflows.\n\n")

        md.write("---\n\n")

        # -----------------------------------------------------
        # GLOBAL WORKFLOW STATES
        # -----------------------------------------------------

        md.write("## Global Workflow States\n\n")

        global_states = frappe.db.sql(
            """
            SELECT *
            FROM `tabWorkflow State`
            ORDER BY name ASC
            """,
            as_dict=True,
        )

        if not global_states:
            md.write("No global states defined.\n\n")
        else:
            # Get headers from the first item, excluding internal fields
            headers = [k for k in global_states[0].keys() if k not in ["_user_tags", "_comments", "_assign", "_liked_by"]]
            
            md.write("| " + " | ".join(headers) + " |\n")
            md.write("|" + "|".join(["------"] * len(headers)) + "|\n")
            
            for gs in global_states:
                row = [str(gs.get(k, 'None')) for k in headers]
                md.write("| " + " | ".join(row) + " |\n")
            md.write("\n")

        md.write("\n---\n\n")

        # -----------------------------------------------------
        # ACTIVE WORKFLOWS
        # -----------------------------------------------------

        workflows = frappe.db.sql(
            "SELECT * FROM tabWorkflow",
            as_dict=True,
        )

        md.write("# Workflows\n\n")

        for wf in workflows:

            md.write(f"## Workflow: {wf['name']}\n\n")

            md.write("### Workflow Fields\n\n")

            md.write("| Field | Value |\n")
            md.write("|------|------|\n")

            for key, value in wf.items():

                if key in ["_user_tags", "_comments", "_assign", "_liked_by"]:
                    continue

                md.write(f"| {key} | {value} |\n")

            md.write("\n")

            # -----------------------------------------------------
            # STATES
            # -----------------------------------------------------

            states = frappe.db.sql(
                """
                SELECT *
                FROM `tabWorkflow Document State`
                WHERE parent = %s
                ORDER BY idx ASC
                """,
                (wf["name"],),
                as_dict=True,
            )

            md.write("### Workflow States\n\n")

            if not states:
                md.write("No states defined.\n\n")
            else:
                excluded_keys = ["_user_tags", "_comments", "_assign", "_liked_by", "parent", "parentfield", "parenttype"]
                headers = [k for k in states[0].keys() if k not in excluded_keys]
                
                md.write("| " + " | ".join(headers) + " |\n")
                md.write("|" + "|".join(["------"] * len(headers)) + "|\n")
                
                for s in states:
                    row = [str(s.get(k, 'None')).replace('\n', '<br>') for k in headers]
                    md.write("| " + " | ".join(row) + " |\n")
                md.write("\n")

            # -----------------------------------------------------
            # TRANSITIONS
            # -----------------------------------------------------

            transitions = frappe.db.sql(
                """
                SELECT *
                FROM `tabWorkflow Transition`
                WHERE parent = %s
                ORDER BY idx ASC
                """,
                (wf["name"],),
                as_dict=True,
            )

            md.write("### Workflow Transitions\n\n")

            if not transitions:
                md.write("No transitions defined.\n\n")
            else:
                excluded_keys = ["_user_tags", "_comments", "_assign", "_liked_by", "parent", "parentfield", "parenttype"]
                headers = [k for k in transitions[0].keys() if k not in excluded_keys]
                
                md.write("| " + " | ".join(headers) + " |\n")
                md.write("|" + "|".join(["------"] * len(headers)) + "|\n")
                
                for t in transitions:
                    row = [str(t.get(k, 'None')).replace('\n', '<br>') for k in headers]
                    md.write("| " + " | ".join(row) + " |\n")
                md.write("\n")

            md.write("---\n\n")

    print(f"Markdown report generated:\n{REPORT_FILE}")