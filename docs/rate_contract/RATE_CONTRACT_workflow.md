# Rate Contract — Complete Workflow Documentation

## Overview

| Property | Value |
|---|---|
| **DocType** | `Rate Contract` |
| **Autoname** | `{YYYY}{MM}{DD}{11}RATE{######}` |
| **Module** | Rndopsapp |
| **Is Submittable** | Yes (docstatus 0 → 1 → 2) |
| **Backend Module** | `rndopsapp.rndopsapp.doctype.rate_contract.rate_contract` |
| **Workflow States Defined** | None (states: []) |
| **Linked Parent DocType** | `Indent Cum Sanction Sheet` (via `indent_cum_sanction_sheet_id`) |

The Rate Contract doctype captures purchase requisitions under Annual Rate Contract (ARC) for two categories: **P3** (Chemicals/Glassware/Plasticware) and **P4** (UPS/Batteries/Cartridges/Gas/Furniture). The document follows a simple draft → submit lifecycle via API; a multi-stage approval workflow (`Rate Contract Workflow`) is referenced in the codebase but **not yet implemented** in the doctype JSON.

---

## 1. Document Lifecycle (Current Implementation)

```
[Draft]  ──[save_rate_contract()]──→  [Saved / Draft]
                                             │
                                    [submit_rate_contract()]
                                             │
                                        [Submitted]
                                      (docstatus = 1)
```

| State | Docstatus | Meaning |
|---|---|---|
| Draft | 0 | Document created, editable |
| Submitted | 1 | Document locked; no further edits |
| Cancelled | 2 | Document cancelled (terminal) |

### Workflow State Field

- Fieldname: `workflow_state`
- Fieldtype: Data
- Hidden: 1, Read-only: 1
- Currently not populated by any workflow engine (field exists for future use)

---

## 2. Form Types — P3 vs P4

The Rate Contract has two distinct form layouts controlled by `select_form_type`:

| Form Type | Full Value | Use Case |
|---|---|---|
| P3 | `P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)` | Chemicals, Glassware, Plasticware, Filtration, Custom Services, Mixed Catalogue, Gas Refilling |
| P4 | `P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)` | UPS Batteries, HP Printer Cartridges, Gas Refilling, Copier Papers, UPS and Transformers, Furniture |

---

## 3. Complete Field Schema

### 3.1 Amendment & ICSS Link

| Fieldname | Fieldtype | Label | Notes |
|---|---|---|---|
| `amended_from` | Link → Rate Contract | Amended From | Read-only, no-copy, search-indexed |
| `indent_cum_sanction_sheet_id` | Link → Indent Cum Sanction Sheet | Indent Cum Sanction Sheet ID | Read-only; set when created from ICSS |
| `project_no` | Data | Project Number | Read-only; synced from ICSS |
| `project_ref` | Link → Project Registration | Project Reference | Read-only |
| `indent_type` | Data | Indent Type | Read-only; synced from ICSS |

### 3.2 Form Selection

| Fieldname | Fieldtype | Label | Options |
|---|---|---|---|
| `select_form_type` | Select | Select Form Type | `Select`, `P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)`, `P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)` |

Default: `Select`

### 3.3 Project & Account Head

| Fieldname | Fieldtype | Label | Notes |
|---|---|---|---|
| `project_number` | Link → Project Registration | Project Number | User selects project |
| `account_head` | Link → Budget Head | Account Head | `in_filter: 1` |
| `other_account_head` | Data | — | Shown only when `account_head == "sn5dcvqgs8"` |

### 3.4 Other PI Fields (Conditional)

Shown only when: `doc.is_project_of_other_pi == "Yes" && doc.piheadmentor_user_id_other_pi == frappe.session.user`

| Fieldname | Fieldtype | Label | Notes |
|---|---|---|---|
| `other_pi_email` | Link → User | Webmail-ID of other PI | Triggers fetch of other PI details |
| `name_other_pi` | Data | Name of other PI | `fetch_from: other_pi_email.full_name` |
| `emp_class_other_pi` | Data | Employee class other PI | `fetch_from: other_pi_email.empclass`, read-only |
| `other_pi_dept` | Data | Department | `fetch_from: other_pi_email.department_name`, read-only |
| `piheadmentor_user_id_other_pi` | Select | PI/Head/Mentor User Id (Other PI) | `fetch_from: other_pi_email.piheadmentor_user_id`, read-only |

### 3.5 P3 Form Fields (Chemicals/Glassware/Plasticware)

Shown when: `select_form_type == "P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)"`

| Fieldname | Fieldtype | Label | Mandatory | Notes |
|---|---|---|---|---|
| `item_type` | Select | Item Type | Yes (P3 only) | Options: Chemicals, Glassware, Plasticware, Filtration, Custom Services, Mixed Catalogue, Gas Refilling |
| `principal_supplier` | Link → Principal Supplier | Principal Supplier | — | Filtered by `item_type` via `get_principal_suppliers_by_item_type()` |
| `principal_address` | Small Text | Principal Supplier Details | — | Read-only; auto-filled on supplier select |
| `agreement_no` | Data | Agreement Number | Yes (P3 only) | Read-only; auto-filled from Principal Supplier |
| `local_supplier` | Data | Select Local Supplier | — | `in_list_view: 1` |
| `local_address` | Small Text | Local Supplier Details | — | Read-only |
| `local_email` | Data | Local Supplier Email | — | Read-only; shown only for P3 |
| `certify_authorized_firm` | Check | Certified that items are for my experiments and procured from the authorized firm only | Yes (P3 only) | Default: 0 |
| `certify_current_prices` | Check | Certified that Cat No, Page No and Prices are as per CURRENT APPLICABLE PRICE LIST | Yes (P3 only) | Default: 0 |
| `certify_delivery_time` | Check | Materials to be delivered within two weeks from PO date | Yes (P3 only) | Default: 0 |

### 3.6 P4 Form Fields (UPS/Batteries/Cartridges/Gas/Furniture)

Shown when: `select_form_type == "P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)"`

| Fieldname | Fieldtype | Label | Mandatory | Notes |
|---|---|---|---|---|
| `p4_item_type` | Select | Select P4 Item Type | Yes (P4 only) | Options: UPS Batteries, HP Printer Cartridges, Gas Refilling, Copier Papers, UPS and Transformers, Furniture |
| `select_vendor` | Link → Principal Supplier | Select Vendor | Yes (P4 only) | Filtered by `p4_item_type` via `get_vendors_by_p4_item_type()` |
| `vendor_address` | Small Text | Vendor Address | — | Read-only; auto-filled on vendor select |
| `vendor_email` | Data | Vendor Email | — | Read-only; auto-filled on vendor select |
| `justification` | Small Text | Justification | Yes (P4 only) | Free text |

### 3.7 Items Table (Child DocType: Rate Contract Purchase Item Detail)

| Fieldname | Fieldtype | Label | In List View |
|---|---|---|---|
| `item_description` | Small Text | Item Description | Yes |
| `cat_no` | Data | Cat No | Yes |
| `page_no` | Int | Page No | — |
| `unit_rate` | Currency | Unit Rate | — |
| `quantity` | Float | Quantity | — |
| `discount_percentage` | Percent | Discount % | — |
| `gst_percentage` | Percent | GST % | — |
| `amount` | Currency | Amount | — (read-only, computed) |

Child doctype properties: `istable: 1`, `editable_grid: 1`, grid page length: 50

### 3.8 Financial Totals

| Fieldname | Fieldtype | Label | Notes |
|---|---|---|---|
| `rate_contract_total` | Currency | Rate Contract Total | Read-only; sum of item amounts |
| `rate_contract_packing` | Currency | Packing/Freight Etc. | User-entered |
| `rate_contract_grand_total` | Currency | Grand Total | Read-only; total + packing; visible when > 0 |
| `amount_in_words` | Small Text | Amount in Words | Read-only |

### 3.9 Workflow

| Fieldname | Fieldtype | Label | Notes |
|---|---|---|---|
| `workflow_state` | Data | Workflow State | Hidden, read-only; placeholder for future workflow engine |

---

## 4. Conditional Display Logic

### P3 Section visibility
```
depends_on: eval:doc.select_form_type=='P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)'
```
Fields shown: `item_type`, `principal_supplier`, `principal_address`, `agreement_no`, `local_supplier`, `local_address`, `local_email`, `certify_authorized_firm`, `certify_current_prices`, `certify_delivery_time`

### P4 Section visibility
```
depends_on: eval:doc.select_form_type=="P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)"
```
Fields shown: `p4_item_type`, `select_vendor`, `vendor_address`, `vendor_email`, `justification`

### Items + Totals visibility (shared)
```
depends_on: eval: doc.select_form_type == "P4..." || doc.select_form_type == "P3..."
```
Hides items table and totals until a form type is selected.

### Other Account Head
```
depends_on: eval:doc.account_head == "sn5dcvqgs8"
```
Shows `other_account_head` free-text field when the "Others" Budget Head is selected.

### Other PI Section (submitter context)
```
depends_on: eval:doc.is_project_of_other_pi == "Yes" && doc.piheadmentor_user_id_other_pi == frappe.session.user
```
Shows other PI identity fields only to the current session's PI/Head/Mentor.

---

## 5. Business Rules and Validations

### 5.1 Document Edit Guard

```python
if doc.docstatus != 0:
    frappe.throw("Cannot edit a submitted or cancelled document.")
```
Applied in `save_rate_contract()` — prevents updates to any submitted or cancelled document.

### 5.2 Items Validation

Only rows where `item_description` or `cat_no` is present are saved:
```python
if item.get("item_description") or item.get("cat_no"):
    doc.append("items", {...})
```

### 5.3 P3 Mandatory Rules

All three certify checkboxes must be checked (`mandatory_depends_on`) before the P3 form can be submitted. All are mandatory when `select_form_type == P3`.

### 5.4 P4 Mandatory Rules

`p4_item_type`, `select_vendor`, and `justification` are all mandatory when `select_form_type == P4`.

### 5.5 Supplier Auto-Fill Chain (P3)

```
User selects item_type
  → get_principal_suppliers_by_item_type(item_type) → filtered supplier list
    → User selects principal_supplier
      → get_principal_supplier_details(principal_supplier) → fills principal_address, agreement_no
        → get_local_suppliers_by_principal(principal_supplier) → filtered local supplier list
          → User selects local_supplier
            → get_local_supplier_details(local_supplier) → fills local_address, local_email
```

### 5.6 Vendor Auto-Fill Chain (P4)

```
User selects p4_item_type
  → get_vendors_by_p4_item_type(p4_item_type) → filtered vendor list
    → User selects select_vendor
      → get_vendor_details(vendor) → fills vendor_address, vendor_email
```

---

## 6. API Endpoints

All endpoints are `@frappe.whitelist()`.

| Endpoint | Purpose |
|---|---|
| `get_rate_contract_fields(doc_name=None)` | Returns field metadata, prefill_data (with current user info), link options, child table fields |
| `save_rate_contract(doc_data)` | Create or update a Rate Contract; handles items child table; returns `{status, docname}` |
| `submit_rate_contract(docname)` | Submit a draft Rate Contract (docstatus 0 → 1) |
| `get_principal_suppliers_by_item_type(item_type)` | Filtered Principal Suppliers for P3 item type selection |
| `get_local_suppliers_by_principal(principal_supplier)` | Filtered Local Suppliers from a Principal Supplier's child table |
| `get_vendors_by_p4_item_type(p4_item_type)` | Filtered vendors (Principal Suppliers) for P4 item type |
| `get_principal_supplier_details(principal_supplier)` | Returns `principal_address`, `agreement_no` for a given supplier |
| `get_local_supplier_details(local_supplier)` | Returns `local_address`, `local_email` for a given local supplier |
| `get_vendor_details(vendor)` | Returns `vendor_address`, `vendor_email` for a P4 vendor |
| `get_form_type_config()` | Returns P3/P4 visible/hidden field lists for frontend field visibility control |

### `get_rate_contract_fields()` Response Shape

```json
{
  "fields": [ { "fieldname": "...", "label": "...", "fieldtype": "...",
                "depends_on": "eval:...", "depends_on_eval": "...",
                "mandatory_depends_on": "eval:...", "mandatory_depends_on_eval": "...",
                "read_only_depends_on": "eval:...", "read_only_depends_on_eval": "..." } ],
  "prefill_data": {
    "email_id": "<current_user>",
    "indentor": "<current_user>",
    "applicant_designation": "...",
    "applicant_department": "...",
    "items": []
  },
  "link_options": {
    "email_id": [...],
    "indentor": [...],
    "project_number": [...],
    "account_head": [...],
    "principal_supplier": [...],
    "local_supplier": [...],
    "select_vendor": [...],
    "amended_from": [...]
  },
  "related_data": { ... },
  "child_table_fields": {
    "items": [ { "fieldname": "...", "label": "...", ... } ]
  }
}
```

---

## 7. Link Relationships

```
Rate Contract
  ├─ amended_from            → Rate Contract (self; amendment chain)
  ├─ indent_cum_sanction_sheet_id → Indent Cum Sanction Sheet (parent ICSS)
  ├─ project_number          → Project Registration
  ├─ project_ref             → Project Registration (read-only; from ICSS)
  ├─ account_head            → Budget Head
  ├─ other_pi_email          → User
  ├─ principal_supplier      → Principal Supplier (P3)
  │     └─ Local Supplier Detail (child table of Principal Supplier)
  └─ select_vendor           → Principal Supplier (P4)
```

---

## 8. Permissions

| Role | Create | Read | Write | Submit | Delete |
|---|---|---|---|---|---|
| `System Manager` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `All_ProRnd_User` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `Permanent Employee` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `Ado_RnD` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `head_approver_1` | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## 9. ICSS Integration

Rate Contract is one of the sub-doctypes created from an Indent Cum Sanction Sheet:

**ICSS Indent Type → Child DocType mapping (from `indent_cum_sanction_sheet.py`):**
```python
"Rate Contract Purchase": "Rate Contract"
```

**Sub-DocType Workflow mapping (referenced but not yet built):**
```python
"Rate Contract Purchase": "Rate Contract Workflow"
```

When an ICSS with `indent_type = "Rate Contract Purchase"` is saved:
- A `Rate Contract` record is created/updated
- Fields synced: `indent_cum_sanction_sheet_id`, `project_ref`, `project_no`, `indent_type`
- The Rate Contract's `sub_doctype_reference` is stored on the parent ICSS

---

## 10. Planned Workflow (Not Yet Implemented)

The `workflow_state` field and `"Rate Contract Workflow"` name reference indicate the following approval workflow is **planned** but not yet built:

Based on the system architecture of sibling doctypes, the expected states are:

| # | State | Docstatus | Role |
|---|---|---|---|
| 1 | `Draft` | 0 | `All_ProRnd_User` |
| 2 | `Pending PI Approval` | 1 | `Permanent Employee` |
| 3 | `Pending Staff Approval` | 1 | `staff, RnD` |
| 4 | `Pending HoS Approval` | 1 | `Hos, RnD (Head of Section, RnD)` |
| 5 | `Pending Associate Dean` | 1 | `Ado_RnD` |
| 6 | `Pending Dean Approval` | 1 | `Dean, RnD` |
| 7 | `Approved` | 1 | `staff, RnD` |
| 8 | `Rejected` | 2 | `Administrator` |

Amount-based routing at HoS (same as ICSS):
- amount ≤ ₹1,00,000 → Pending Associate Dean
- amount > ₹1,00,000 → Pending Dean Approval

**Amount field:** `rate_contract_grand_total`

---

## 11. Form Type Configuration (Frontend Reference)

```json
{
  "P3": {
    "form_type": "P3 (CHEMICALS/GLASSWARE/PLASTIC WARE UNDER RC)",
    "visible_fields": [
      "item_type", "principal_supplier", "principal_address",
      "agreement_no", "local_supplier", "local_address", "local_email",
      "certify_authorized_firm", "certify_current_prices", "certify_delivery_time"
    ],
    "hidden_fields": [
      "p4_item_type", "select_vendor", "vendor_address", "vendor_email", "justification"
    ]
  },
  "P4": {
    "form_type": "P4 (UPS, UPS BATTERY, HP PRINTER CARTRIDGES,GAS,FURNITURE ETC. UNDER RC)",
    "visible_fields": [
      "p4_item_type", "select_vendor", "vendor_address", "vendor_email", "justification"
    ],
    "hidden_fields": [
      "item_type", "principal_supplier", "principal_address",
      "agreement_no", "local_supplier", "local_address", "local_email",
      "certify_authorized_firm", "certify_current_prices", "certify_delivery_time"
    ]
  }
}
```

---

## 12. Implementation Status Summary

| Feature | Status |
|---|---|
| DocType schema (all fields) | Implemented |
| Child doctype (Rate Contract Purchase Item Detail) | Implemented |
| P3 / P4 form type split | Implemented |
| Supplier/vendor auto-fill chain | Implemented |
| Field-level conditional visibility | Implemented |
| Save API (`save_rate_contract`) | Implemented |
| Submit API (`submit_rate_contract`) | Implemented |
| Permissions for 5 roles | Implemented |
| ICSS sub-doctype link | Implemented |
| Multi-stage approval workflow (`Rate Contract Workflow`) | **Not yet implemented** |
| `workflow_state` population | **Not yet implemented** |
| Workflow actions (Forward, Approve, Reject, Put Back) | **Not yet implemented** |
| Amount-based routing at HoS stage | **Not yet implemented** |
