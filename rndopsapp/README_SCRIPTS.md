# Custom Scripting & Frappe Database Interaction

This guide explains how to write standalone Python scripts to interact with the Frappe framework, database, and your custom app modules.

## 1. Setting up a Standalone Script

To run a script outside of the standard web request (e.g., for testing, debugging, or cron jobs), you must initialize the Frappe environment.

### Boilerplate Code
Create a new file (e.g., `my_script.py`) in your bench directory or app folder and add this setup at the top:

```python
import frappe
import os
import sys

# 1. DEFINE PATHS
# Adjust these paths to point to your bench directory (e.g., /home/user/frappe-bench)
bench_path = "/home/prornd/project/frappe_dev/prornd"
sites_path = os.path.join(bench_path, "sites")
apps_path = os.path.join(bench_path, "apps")

# 2. SETUP ENVIRONMENT
# Change directory to site folder (required for frappe.init to find config)
if os.path.exists(sites_path):
    os.chdir(sites_path)

# Add paths to sys.path so Python can find 'frappe' and your 'apps'
if sites_path not in sys.path:
    sys.path.append(sites_path)
if apps_path not in sys.path:
    sys.path.append(apps_path)

# 3. INITIALIZE FRAPPE
# Connect to your site (replace 'prornd.local' with your actual site name)
frappe.init(site='prornd.local')
frappe.connect()

# NOW YOU CAN WRITE YOUR CODE BELOW
print("Frappe connected successfully!")
```

## 2. Running the Script

Use the Python executable from your virtual environment (`env`) to run the script:

```bash
# Navigate to your bench root directory
cd /home/prornd/project/frappe_dev/prornd

# Run the script
./env/bin/python apps/rndopsapp/rndopsapp/my_script.py
```

## 3. Database Interaction

Once connected, you can interact with the database using Frappe's ORM or raw SQL.

### Using `frappe.db.sql` (Raw SQL)
Use this for complex queries or when you want bypassing standard filters/hooks.

```python
# Returns a list of dictionaries
workflows = frappe.db.sql("""
    SELECT name, document_type 
    FROM `tabWorkflow` 
    WHERE is_active = 1
""", as_dict=True)

for wf in workflows:
    print(f"Active Workflow: {wf.name}")
```

### Using `frappe.get_all` / `frappe.get_list` (ORM)
Use this for standard queries. It respects permissions if you check them.

```python
# Get all active users
users = frappe.get_list("User", filters={"enabled": 1}, fields=["name", "email"])
for user in users:
    print(user.name, user.email)
```

### Loading & Updating a Document (`frappe.get_doc`)
Use this to work with a specific document, modify it, and save changes.

```python
# 1. Load document (DocType, Name)
doc = frappe.get_doc("Temporary Advance", "TA-2024-001")
print(f"Current Status: {doc.workflow_state}")

# 2. Modify
doc.workflow_state = "Approved"

# 3. Save
doc.save()
frappe.db.commit() # Important: Commit changes to DB
print("Document updated!")
```

## 4. Common Tables & Fields

In Frappe, database tables are prefixed with `tab` followed by the DocType Name.

- **Tasks/States**:
    - **Workflows**: `tabWorkflow`
    - **Workflow States**: `tabWorkflow Document State` (Child table defining states per workflow)
    - **Global States**: `tabWorkflow State` (Master list of all possible states)

- **How to specific see fields?**
    Run this SQL command in your script to see the table schema:
    ```python
    fields = frappe.db.sql("DESC `tabTemporary Advance`", as_dict=True)
    for f in fields:
        print(f["Field"], f["Type"]) 
    ```

## 5. Importing App Modules for Testing

Once you've added the `apps` path (see Section 1), you can import your custom app modules just like inside the framework.

```python
# Example: Importing a function from your app
from rndopsapp.rndopsapp.doctype.temporary_advance.temporary_advance import get_temporary_advance_fields

# Call your custom function
data = get_temporary_advance_fields(project_code="PROJ-123")
print("Fetched Data:", data)
```
