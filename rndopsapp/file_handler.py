# Copyright (c) 2026, rndops and contributors
# Universal file handler to intercept ALL Frappe file uploads and redirect to MinIO

import frappe
from frappe import _
import os
import re
from rndopsapp.minio import get_rnd_file_service


def get_file_category_for_doctype(doctype, fieldname):
    """
    Dynamically determine file category based on doctype metadata and intelligent fallbacks.

    Resolution order:
    1. Check DocField custom property 'file_category' (if exists)
    2. Infer from field label (convert to lowercase, replace spaces)
    3. Infer from fieldname using pattern matching
    4. Default to 'attachments'

    Args:
        doctype: The doctype name (e.g., "Project Registration")
        fieldname: The field name (e.g., "upload_proj_prop")

    Returns:
        Category string (e.g., "proposal", "endorsement", "attachments")

    Examples:
        >>> get_file_category_for_doctype("Project Registration", "upload_proj_prop")
        "proposal"

        >>> get_file_category_for_doctype("Employee", "profile_image")
        "profile_images"

        >>> get_file_category_for_doctype("Task", "attachment")
        "attachments"
    """
    if not doctype or not fieldname:
        return "attachments"

    try:
        # Get DocField metadata
        meta = frappe.get_meta(doctype)
        field = meta.get_field(fieldname)

        if not field:
            return _infer_category_from_fieldname(fieldname)

        # 1. Check for custom 'file_category' property (if implemented)
        if hasattr(field, 'file_category') and field.file_category:
            return field.file_category.lower().replace(" ", "_")

        # 2. Check field options (can be used as category hint)
        if field.options and isinstance(field.options, str):
            # If options is set, use it as category
            category = field.options.strip()
            if category:
                return category.lower().replace(" ", "_")

        # 3. Infer from field label
        if field.label:
            category = _infer_category_from_label(field.label)
            if category:
                return category

        # 4. Infer from fieldname
        return _infer_category_from_fieldname(fieldname)

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"Category Resolution Error: {doctype}.{fieldname}")
        return "attachments"


def _infer_category_from_label(label):
    """
    Infer category from field label.

    Args:
        label: Field label (e.g., "Upload Project Proposal")

    Returns:
        Category string or None
    """
    if not label:
        return None

    label_lower = label.lower()

    # Pattern matching on label
    patterns = {
        'proposal': ['proposal', 'project proposal'],
        'endorsement': ['endorsement', 'endorse'],
        'sanction': ['sanction', 'approval order', 'approval letter'],
        'invoice': ['invoice', 'bill'],
        'receipt': ['receipt', 'payment proof'],
        'resume': ['resume', 'cv', 'curriculum vitae'],
        'profile_images': ['photo', 'image', 'picture', 'profile pic'],
        'documents': ['document', 'doc', 'certificate', 'proof'],
        'reports': ['report', 'analysis'],
        'contracts': ['contract', 'agreement'],
    }

    for category, keywords in patterns.items():
        for keyword in keywords:
            if keyword in label_lower:
                return category

    # Default: use label as-is (cleaned)
    return label.lower().replace(" ", "_")[:50]  # Limit length


def _infer_category_from_fieldname(fieldname):
    """
    Infer category from fieldname using pattern matching.

    Args:
        fieldname: Field name (e.g., "upload_proj_prop", "sanction_file")

    Returns:
        Category string

    Patterns:
        - *proposal* → proposal
        - *endorsement* → endorsement
        - *sanction* → sanction
        - *invoice* → invoice
        - *resume* → resume
        - *image*/*photo* → profile_images
        - *attachment* → attachments
        - Default → attachments
    """
    if not fieldname:
        return "attachments"

    fieldname_lower = fieldname.lower()

    # Pattern matching rules
    if 'proposal' in fieldname_lower or 'prop' in fieldname_lower:
        return "proposal"
    elif 'endorsement' in fieldname_lower or 'endorse' in fieldname_lower:
        return "endorsement"
    elif 'sanction' in fieldname_lower:
        return "sanction"
    elif 'invoice' in fieldname_lower:
        return "invoice"
    elif 'receipt' in fieldname_lower:
        return "receipt"
    elif 'resume' in fieldname_lower or 'cv' in fieldname_lower:
        return "resume"
    elif 'image' in fieldname_lower or 'photo' in fieldname_lower or 'picture' in fieldname_lower:
        return "profile_images"
    elif 'contract' in fieldname_lower or 'agreement' in fieldname_lower:
        return "contracts"
    elif 'report' in fieldname_lower:
        return "reports"
    elif 'document' in fieldname_lower or 'doc' in fieldname_lower:
        return "documents"
    elif 'attachment' in fieldname_lower or 'attach' in fieldname_lower:
        return "attachments"
    else:
        # Default fallback
        return "attachments"


def migrate_local_file_to_minio(file_url, doctype, docname, fieldname=None):
    """
    Migrate a file from local filesystem to MinIO.

    Args:
        file_url: Current local file URL (e.g., /files/file.pdf)
        doctype: Document type
        docname: Document name
        fieldname: Field name (optional)

    Returns:
        dict with status and new MinIO URL
    """
    try:
        # Check if already in MinIO (path starts with doctype name)
        if not (file_url.startswith("/files/") or file_url.startswith("/private/files/")):
            return {"status": False, "message": "File not local", "file_url": file_url}

        # Get File document
        file_doc = frappe.get_doc("File", {"file_url": file_url})

        # Read file from local disk
        site_path = frappe.get_site_path()
        file_path = os.path.join(site_path, file_url.lstrip("/"))

        if not os.path.exists(file_path):
            return {"status": False, "message": f"File not found: {file_path}"}

        with open(file_path, "rb") as f:
            file_content = f.read()

        # Get category
        category = get_file_category_for_doctype(doctype, fieldname)

        # Upload to MinIO
        file_service = get_rnd_file_service()

        upload_result = file_service.save_file(
            filename=file_doc.file_name,
            content=file_content,
            is_private=bool(file_doc.is_private),
            doctype=doctype,
            docname=docname,
            folder=category
        )

        if upload_result.get("status"):
            minio_url = upload_result.get("data", {}).get("file_url")

            # Delete old File doc
            frappe.delete_doc("File", file_doc.name, ignore_permissions=True)

            # Delete local file
            try:
                os.remove(file_path)
                frappe.logger().info(f"Deleted local file: {file_path}")
            except Exception as e:
                frappe.logger().warning(f"Could not delete local file: {file_path}")

            frappe.logger().info(f"Migrated {file_doc.file_name} to MinIO: {minio_url}")

            return {
                "status": True,
                "message": "File migrated to MinIO",
                "file_url": minio_url
            }
        else:
            return {
                "status": False,
                "message": upload_result.get("message")
            }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"MinIO Migration Error: {doctype}/{docname}")
        return {
            "status": False,
            "message": str(e)
        }


@frappe.whitelist()
def migrate_file(file_url, doctype, docname, fieldname=None):
    """
    Public API to manually migrate a file to MinIO.

    Usage:
        frappe.call('rndopsapp.rndopsapp.file_handler.migrate_file', {
            file_url: '/files/file.pdf',
            doctype: 'Project Registration',
            docname: '2026031901MeiTy000636',
            fieldname: 'upload_proj_prop'
        })
    """
    return migrate_local_file_to_minio(file_url, doctype, docname, fieldname)
