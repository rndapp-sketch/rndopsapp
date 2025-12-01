# import frappe
# from frappe import _

# @frappe.whitelist()
# def get_dynamic_form_data(doctype_name):
#     """
#     Return comprehensive form data for any doctype.
    
#     Args:
#         doctype_name (str): The name of the doctype to fetch form data for
    
#     Returns:
#         dict: Contains 'fields' and 'link_options'
#     """
#     try:
#         # Validate doctype exists
#         if not frappe.get_meta(doctype_name):
#             frappe.throw(_("Doctype {0} does not exist").format(doctype_name))
        
#         # Fetch metadata
#         meta = frappe.get_meta(doctype_name)
        
#         # 1. Get Field Definitions
#         fields = _get_field_definitions(meta)
        
#         # 2. Get Options for Link and Select Fields
#         link_options = _get_link_options(fields)
        
#         return {
#             "fields": fields,
#             "link_options": link_options
#         }
    
#     except Exception as e:
#         frappe.log_error(frappe.get_traceback(), _("Error fetching form data for {0}").format(doctype_name))
#         return {"error": str(e)}


# # def _get_field_definitions(meta):
# #     """
# #     Extract field definitions from doctype metadata.
# #     Excludes layout fields like Section Break, Column Break, etc.
    
# #     Args:
# #         meta: Frappe meta object
    
# #     Returns:
# #         list: Field definitions with all necessary attributes
# #     """
# #     # Fields to skip (layout/structural fields)
# #     skip_fieldtypes = ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]
    
# #     fields = []
# #     for field in meta.fields:
# #         if field.fieldtype in skip_fieldtypes:
# #             continue
        
# #         fields.append({
# #             "fieldname": field.fieldname,
# #             "label": _(field.label),
# #             "fieldtype": field.fieldtype,
# #             "default": field.default,
# #             "mandatory": bool(field.reqd),
# #             "read_only": bool(field.read_only),
# #             "hidden": bool(field.hidden),
# #             "description": _(field.description) if field.description else None,
# #             "options": field.options,
# #         })
    
# #     return fields

# def _get_field_definitions(meta):
#     """
#     Extract field definitions.
#     Includes 'Table' fields and fetches their internal column definitions recursively.
#     """
#     # Fields to skip (Layout fields only). 
#     # Note: "Table" is NOT here, so it will be included.
#     skip_fieldtypes = ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]
    
#     fields = []
#     for field in meta.fields:
#         if field.fieldtype in skip_fieldtypes:
#             continue
        
#         # Base field definition
#         field_data = {
#             "fieldname": field.fieldname,
#             "label": _(field.label),
#             "fieldtype": field.fieldtype,
#             "default": field.default,
#             "mandatory": bool(field.reqd),
#             "read_only": bool(field.read_only),
#             "hidden": bool(field.hidden),
#             "description": _(field.description) if field.description else None,
#             "options": field.options, # For Table, this is the Child Doctype Name
#         }

#         # --- NEW LOGIC: Get Table Info ---
#         # If it is a Table, we fetch the fields of the Child Doctype linked in 'options'
#         if field.fieldtype == "Table" and field.options:
#             try:
#                 child_meta = frappe.get_meta(field.options)
#                 # Recursive call to get the columns of the child table
#                 field_data["table_columns"] = _get_field_definitions(child_meta)
#             except Exception:
#                 field_data["table_columns"] = []

#         fields.append(field_data)
    
#     return fields


# def _get_link_options(fields, limit=1000):
#     """
#     Fetch options for Link and Select fields.
    
#     Args:
#         fields (list): List of field definitions
#         limit (int): Maximum number of options to fetch per field
    
#     Returns:
#         dict: Field names mapped to their available options
#     """
#     link_options = {}
    
#     for field in fields:
#         if field["fieldtype"] == "Link" and field["options"]:
#             try:
#                 linked_doctype = field["options"]
                
#                 # Validate linked doctype exists
#                 if not frappe.get_meta(linked_doctype):
#                     link_options[field["fieldname"]] = []
#                     continue
                
#                 linked_meta = frappe.get_meta(linked_doctype)
#                 title_field = linked_meta.get_title_field()
                
#                 # Fetch options
#                 options_list = frappe.get_list(
#                     linked_doctype,
#                     fields=["name", title_field],
#                     limit_page_length=limit,
#                 )
                
#                 # Format for frontend: [{ value: '...', label: '...' }]
#                 link_options[field["fieldname"]] = [
#                     {
#                         "value": item["name"],
#                         "label": item.get(title_field, item["name"])
#                     }
#                     for item in options_list
#                 ]
            
#             except Exception as e:
#                 frappe.log_error(
#                     frappe.get_traceback(),
#                     _("Error fetching options for field {0}").format(field["fieldname"])
#                 )
#                 link_options[field["fieldname"]] = []
    
#     return link_options




# -=-=-=-=-=-=-


import frappe
from frappe import _

@frappe.whitelist()
def get_dynamic_form_data(doctype_name, doc_name=None):
    """
    Return comprehensive form data for any doctype.
    If doc_name is provided, returns prefill_data for editing.
    
    Args:
        doctype_name (str): The name of the doctype to fetch form data for
        doc_name (str, optional): The specific document name to fetch data for (Edit Mode)
    
    Returns:
        dict: Contains 'fields', 'link_options', and 'prefill_data'
    """
    try:
        # Validate doctype exists
        if not frappe.get_meta(doctype_name):
            frappe.throw(_("Doctype {0} does not exist").format(doctype_name))
        
        # Fetch metadata
        meta = frappe.get_meta(doctype_name)
        
        # 1. Get Field Definitions (Recursive for Child Tables)
        fields = _get_field_definitions(meta)
        
        # 2. Get Options for Link Fields (Recursive for Child Tables)
        link_options = _get_all_link_options(fields)

        # 3. Get Prefill Data (If doc_name is provided)
        prefill_data = {}
        if doc_name:
            if frappe.db.exists(doctype_name, doc_name):
                doc = frappe.get_doc(doctype_name, doc_name)
                # as_dict() serializes child tables and dates automatically
                prefill_data = doc.as_dict() 
            else:
                frappe.throw(_("Document {0} not found").format(doc_name))
        
        return {
            "fields": fields,
            "link_options": link_options,
            "prefill_data": prefill_data
        }
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Error fetching form data for {0}").format(doctype_name))
        return {"error": str(e)}


def _get_field_definitions(meta):
    """
    Extract field definitions.
    Includes 'Table' fields and fetches their internal column definitions recursively.
    """
    # Fields to skip (Layout fields only). 
    skip_fieldtypes = ["Section Break", "Column Break", "Tab Break", "Button", "Heading"]
    
    fields = []
    for field in meta.fields:
        if field.fieldtype in skip_fieldtypes:
            continue
        
        # Base field definition
        field_data = {
            "fieldname": field.fieldname,
            "label": _(field.label),
            "fieldtype": field.fieldtype,
            "default": field.default,
            "mandatory": bool(field.reqd),
            "read_only": bool(field.read_only),
            "hidden": bool(field.hidden),
            "description": _(field.description) if field.description else None,
            "options": field.options, # For Table, this is the Child Doctype Name
        }

        # --- Logic: Get Table Info ---
        # If it is a Table, we fetch the fields of the Child Doctype linked in 'options'
        if field.fieldtype == "Table" and field.options:
            try:
                child_meta = frappe.get_meta(field.options)
                # Recursive call to get the columns of the child table
                field_data["table_columns"] = _get_field_definitions(child_meta)
            except Exception:
                field_data["table_columns"] = []

        fields.append(field_data)
    
    return fields


def _get_all_link_options(fields_list):
    """
    Recursively fetches options for Link fields, including those inside Child Tables.
    """
    link_options = {}

    for field in fields_list:
        # 1. Handle Top-level Link Fields
        if field.get("fieldtype") == "Link" and field.get("options"):
            _fetch_link_options_for_field(field, link_options)

        # 2. Handle Child Table Fields (Recursion)
        # If this field is a Table and has processed columns
        if field.get("fieldtype") == "Table" and field.get("table_columns"):
            # Recurse into the table columns
            child_options = _get_all_link_options(field["table_columns"])
            # Merge child options into the main dictionary
            link_options.update(child_options)

    return link_options


def _fetch_link_options_for_field(field, link_options_dict, limit=1000):
    """
    Helper to execute the database query for a single Link field.
    Updates the link_options_dict in place.
    """
    try:
        linked_doctype = field["options"]
        
        # Validate linked doctype exists
        if not frappe.get_meta(linked_doctype):
            link_options_dict[field["fieldname"]] = []
            return

        linked_meta = frappe.get_meta(linked_doctype)
        title_field = linked_meta.get_title_field() or "name"
        
        # Fetch options from DB
        options_list = frappe.get_list(
            linked_doctype,
            fields=["name", title_field],
            limit_page_length=limit,
            ignore_permissions=True, # Set to False if you want strict permissions
            order_by=f"{title_field} asc"
        )
        
        # Format for frontend: [{ value: '...', label: '...' }]
        link_options_dict[field["fieldname"]] = [
            {
                "value": item["name"],
                "label": item.get(title_field) or item["name"]
            }
            for item in options_list
        ]
    except Exception:
        # Fail silently for specific fields to prevent breaking the whole form
        link_options_dict[field["fieldname"]] = []