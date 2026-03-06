# RndOpsApp API & DocType Implementation Guide

This document outlines the standard API pattern used for DocTypes in the `rndopsapp` application, enabling frontend interaction, dynamic workflows, and consistent data handling.

## 1. Standard API Pattern

Each core DocType implements a set of whitelisted Python methods to handle frontend operations. This pattern replaces standard Frappe desk views with custom API-driven interfaces.

### Core Methods

| Method Type | Function Naming Convention | Description |
| :--- | :--- | :--- |
| **Get Metdata** | `get_<doctype>_fields(doc_name=None)` | Returns field metadata (labels, types, options), prefill data (if `doc_name` provided), and link options (for dropdowns). |
| **Save Data** | `save_<doctype>_data(data)` | Creates a new document or updates an existing one. Handles child tables and file uploads. |
| **Edit Data** | `edit_<doctype>(data)` | Similar to save, but specifically for editing **Draft** documents. Enforces state checks. |
| **Get Actions** | `get_<doctype>_workflow_actions(docname)` | Returns a list of available workflow actions (e.g., "Approve", "Reject") based on the current state and user roles. |
| **Perform Action** | `perform_<doctype>_action(docname, action)` | Executes a workflow transition, updates the state, and handles submission/cancellation logic. |

---

## 2. Implemented DocTypes

The following DocTypes currently implement this pattern:

| DocType | Key API Methods |
| :--- | :--- |
| **Temporary Advance** | `get_temporary_advance_fields`, `perform_temporary_advance_action` |
| **Travel** | `get_travel_fields`, `perform_travel_workflow_action` |
| **Reimbursement** | `get_reimbursement_fields`, `save_reimbursement_data`, `perform_reimbursement_action` |
| **Advance Settlement** | `get_advance_settlement_fields` |
| **TA DA Settlement** | `get_ta_da_settlement_fields` |
| **Direct Purchase** | `get_direct_purchase_fields`, `save_direct_purchase_data`, `submit_direct_purchase`, `generate_p11_form`, `generate_sanction_sheet`, `generate_purchase_order` |
| **Fund Received** | `get_fund_received_fields` |
| **Project Proposal** | `get_project_proposal_fields` |
| **Rate Contract** | `get_rate_contract_fields` |
| **Deposit Slips** | `get_research_deposit_slip_fields`, `get_consultancy_deposit_slip_fields`, etc. |
| **Recruitment Adhoc Contractual** | `get_recruitment_adhoc_contractual_fields`, `save_recruitment_adhoc_contractual_data`, `perform_recruitment_adhoc_contractual_action`, `submit_recruitment_adhoc_contractual`, `get_recruitment_adhoc_contractual_workflow_actions` |

*(Note: exact function names may vary slightly, e.g., `_workflow_action` vs `_action`)*

---

## 3. Advanced API Payloads: Computation Rules & Downstream Workflows

The **Direct Purchase** module implementation (up to 2.5 Lakh) demonstrates advanced use of our API patterns, including transmitting client-side business logic to the UI and programmatically advancing through connected DocTypes.

### Direct Purchase: `computation_rules` Implementation
Instead of writing native JavaScript in React for calculations and conditional field visibility, the python backend (`get_direct_purchase_fields`) parses the Frappe configurations and passes them down securely:

```json
{
  "row_calculations": [
    {
      "table_fieldname": "table_gdxp",
      "target_field": "estimated_amount_total_price_in_rs",
      "formula": "quantity * estimatedprice",
      "trigger_fields": ["quantity", "estimatedprice"]
    }
  ],
  "conditional_visibility": [
    {
      "target_field": "table_teqd",
      "condition": "total_estimate > 200000",
      "on_show": { "min_rows": 3 },
      "on_hide": { "clear_rows": true }
    }
  ]
}
```

### Direct Purchase: Downstream Document Generators
For multi-stage forms, instead of building new APIs from scratch, we build "Generator" APIs that carry standard mappings across phases:

1. **`generate_p11_form(docname)`**: Pulls the `Items to be purchased` array, injects them into a new `P_11 Form` Draft, and registers the source as `RDP11Generated`.
2. **`generate_sanction_sheet(p11_docname, dp_docname)`**: Creates the financial sanction. Deliberately leaves `ss_other_charges` empty for manual intervention by RnD Staff.
3. **`generate_purchase_order(sanction_sheet_name, dp_docname)`**: Computes the final Purchase Order value but strictly drops internal RnD Staff markups (`ss_other_charges`) before authorizing.

---

## 4. Implementation Guide: How to Add a New DocType

Follow these steps to implement the API pattern for a new DocType (e.g., `My New Doc`).

### Step 1: Define the DocType
Create the DocType in Frappe as usual, adding all necessary fields. Ensure `workflow_state` field exists if using workflows.

### Step 2: Create the Python Controller
In `apps/rndopsapp/rndopsapp/doctype/my_new_doc/my_new_doc.py`:

#### A. Import Dependencies
```python
import frappe
import json
from frappe.model.document import Document
from frappe.utils.file_manager import save_file
```

#### B. Implement `get_my_new_doc_fields`
```python
@frappe.whitelist()
def get_my_new_doc_fields(doc_name=None):
    # 1. Fetch Metadata
    meta = frappe.get_meta("My New Doc")
    fields = []
    for f in meta.fields:
        field_data = {
            "fieldname": f.fieldname,
            "label": f.label,
            "fieldtype": f.fieldtype,
            "options": f.options,
            "mandatory": f.reqd,
            "read_only": f.read_only,
            "depends_on": f.depends_on, # For frontend logic
            "depends_on_eval": f.depends_on.replace("eval:", "") if f.depends_on and f.depends_on.startswith("eval:") else None
        }
        
        # Handle Child Tables: Fetch child fields metadata
        if f.fieldtype == "Table":
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [{
                "fieldname": cf.fieldname,
                "label": cf.label,
                "fieldtype": cf.fieldtype,
                "options": cf.options,
                "in_list_view": cf.in_list_view
            } for cf in child_meta.fields]
            
        fields.append(field_data)
    
    # 2. Prepare Containers
    prefill_data = {}
    link_options = {}

    # 3. Fetch Data (if doc_name provided)
    if doc_name:
        doc = frappe.get_doc("My New Doc", doc_name)
        prefill_data = doc.as_dict()
    
    # 4. Populate Link Options (e.g. for dropdowns)
    link_options["some_link_field"] = frappe.get_all("Some Master", fields=["name as value", "title as label"])

    # 5. Client Scripts (CRITICAL: Fetch enabled client scripts for frontend logic)
    client_scripts = []
    try:
        scripts = frappe.get_all("Client Script", filters={"dt": "My New Doc", "enabled": 1}, fields=["name", "script", "view"])
        for script in scripts:
            client_scripts.append({"name": script.name, "script": script.script, "view": script.view})
    except Exception:
        pass

    return {
        "fields": fields,
        "prefill_data": prefill_data,
        "link_options": link_options,
        "client_scripts": client_scripts # Return scripts to frontend
    }
```

#### C. Implement `save_my_new_doc_data`
```python
@frappe.whitelist()
def save_my_new_doc_data(data):
    if isinstance(data, str):
        data = json.loads(data)
    
    try:
        # Create or Get Doc
        if data.get("name"):
            doc = frappe.get_doc("My New Doc", data.get("name"))
        else:
            doc = frappe.new_doc("My New Doc")
        
        # Map Fields
        for field in ["field1", "field2", "workflow_state"]:
            if field in data:
                doc.set(field, data[field])
        
        # Handle Child Table: table_field
        items_data = data.get("table_field", [])
        if items_data:
            doc.set("table_field", []) # Clear existing
            for item in items_data:
                doc.append("table_field", item)
        
        # Save
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        return {"status": "error", "message": str(e)}
```

#### D. Implement Workflow Logic (If applicable)
```python
@frappe.whitelist()
def perform_my_new_doc_action(docname, action):
    # 1. Get Workflow
    wf_name = frappe.db.get_value("Workflow", {"document_type": "My New Doc", "is_active": 1}, "name")
    wf = frappe.get_doc("Workflow", wf_name)
    
    doc = frappe.get_doc("My New Doc", docname)
    current_state = doc.workflow_state
    
    # 2. Find Next State
    next_state = None
    for t in wf.transitions:
        if t.state == current_state and t.action == action:
            next_state = t.next_state
            break
            
    if not next_state:
        frappe.throw("Invalid Action")

    # 3. Update & Save
    doc.workflow_state = next_state
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    
    return {"status": "success", "next_state": next_state}
```

---

## 4. Frontend Integration Requirements

To consume these APIs, the frontend should:

1.  Call `get_<doctype>_fields` on load.
2.  Render inputs based on `fields` metadata.
3.  Populate dropdowns using `link_options`.
4.  If editing, populate values from `prefill_data`.
5.  On submit, collect form data and call `save_<doctype>_data`.
6.  For workflow actions, call `perform_<doctype>_action`.

## 5. Testing

Use the `README_SCRIPTS.md` guide to test these methods via standalone scripts before integrating with the frontend.
