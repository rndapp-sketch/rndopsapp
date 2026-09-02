# Copyright (c) 2025, rndops and contributors
# Shared utilities for Fund Deposits modules

import frappe
from typing import Optional


def fmt_date(d) -> str:
    """
    Format dates in ISO 8601 format with T separator.

    Args:
        d: Date value (can be datetime, date, or string)

    Returns:
        str: ISO 8601 formatted date string or empty string if None
    """
    if not d:
        return ""
    date_str = str(d)
    return date_str.replace(' ', 'T')


def get_fund_received_ref_number(fund_received_ref: str) -> int:
    """
    Get fund received reference number from linked Fund Received document.

    Args:
        fund_received_ref: Fund Received document name

    Returns:
        int: Fund received reference number or 0 if not found
    """
    if not fund_received_ref:
        return 0
    try:
        val = frappe.db.get_value("Fund Received", fund_received_ref, "fund_received_ref_number")
        return int(val) if val else 0
    except Exception:
        return 0


def get_department_id(department_name: Optional[str]) -> Optional[int]:
    """
    Fetch department ID from Department_prornd doctype.

    Args:
        department_name: Department document name

    Returns:
        int or None: Department ID if found
    """
    if not department_name:
        return None
    try:
        return frappe.db.get_value("Department_prornd", department_name, "dept_id")
    except Exception:
        return None


def get_project_number(doc) -> str:
    """
    Get project number from document.

    Args:
        doc: Frappe document with project_title or project_number field

    Returns:
        str: Project number
    """
    project_number = getattr(doc, 'project_number', '') or ""
    if not project_number and getattr(doc, 'project_title', None):
        try:
            project_number = frappe.db.get_value(
                "Project Registration",
                doc.project_title,
                "name"
            ) or doc.project_title
        except Exception:
            project_number = doc.project_title or ""
    return project_number


def determine_gst_type(doc) -> str:
    """
    Determine GST type from document fields.

    Args:
        doc: Frappe document with GST-related fields

    Returns:
        str: "NOGST", "CGST_SGST", or "IGST"
    """
    from frappe.utils import flt

    cgst_amount = flt(getattr(doc, 'cgst_9', 0))
    sgst_amount = flt(getattr(doc, 'sgst_9', 0))
    igst_amount = flt(getattr(doc, 'igst_18', 0) or getattr(doc, 'igst_18_on_consultancy', 0))
    total_gst = flt(getattr(doc, 'total_gst', 0))

    if total_gst > 0 or cgst_amount > 0 or sgst_amount > 0 or igst_amount > 0:
        if cgst_amount > 0 or sgst_amount > 0:
            return "CGST_SGST"
        else:
            return "IGST"
    return "NOGST"
