# Copyright (c) 2025, rndops and contributors
# Mapper for Research Deposit Slip Document to DTO

import frappe
from frappe.utils import flt
from typing import List, Optional

from datetime import datetime, timezone
from .dto import (
    ResearchDepositSlipDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)


# ==========================================
# Event Wrapper Class
# ==========================================

class ResearchDepositSlipEvent:
    """
    Event wrapper for Research Deposit Slip DTO.
    Provides the interface expected by the producer.
    """

    def __init__(self, dto: ResearchDepositSlipDTO):
        self.data = dto
        self.eventType = "DEPOSIT_SLIP"

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        """
        Convert to Kafka message envelope format.

        Args:
            schema_version: Schema version for the payload

        Returns:
            dict: Wrapped payload ready for Kafka publishing
        """
        return {
            "schemaVersion": schema_version,
            "eventType": self.eventType,
            "timestamp": datetime.utcnow().isoformat(),
            "data": self.data.to_dict()
        }


# ==========================================
# Utility Functions
# ==========================================

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
    if " " not in date_str and "T" not in date_str:
        # If it's just a date (YYYY-MM-DD), append current time with microseconds
        current_time_str = datetime.now().strftime("T%H:%M:%S.%f")
        date_str += current_time_str
    
    # Simple string replacement for datetime string from frappe
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
        val = frappe.db.get_value("Department_prornd", department_name, "dept_id")
        return int(val) if val else None
    except Exception:
        return None


# ==========================================
# Research Deposit Slip Mapper
# ==========================================

class ResearchDepositSlipMapper:
    """
    Maps Frappe Research Deposit Slip document to ResearchDepositSlipDTO.
    Handles field name mapping and data transformation.
    """

    @staticmethod
    def get_project_number(doc) -> str:
        """
        Get project number from document.

        Args:
            doc: Research Deposit Slip document

        Returns:
            str: Project number
        """
        project_number = getattr(doc, 'project_number', '') or ""
        if not project_number and getattr(doc, 'project_title', None):
            try:
                project_number = frappe.db.get_value(
                    "Project Registration",
                    doc.project_title,
                    "project_no"
                ) or ""
            except Exception:
                project_number = ""
        return project_number

    @staticmethod
    def get_gst_type(doc) -> str:
        """
        Determine GST type from document.

        Args:
            doc: Research Deposit Slip document

        Returns:
            str: "NOGST", "CGST_SGST", or "IGST"
        """
        cgst_amount = flt(getattr(doc, 'cgst_9', 0))
        sgst_amount = flt(getattr(doc, 'sgst_9', 0))
        total_gst = flt(getattr(doc, 'total_gst', 0))

        if total_gst > 0:
            if cgst_amount > 0 or sgst_amount > 0:
                return "CGST_SGST"
            else:
                return "IGST"
        return "NOGST"

    @staticmethod
    def map_ecs_dates(doc) -> List[str]:
        """
        Map ECS dates from child table.
        Returns dates in YYYY-MM-DD format as required.

        Args:
            doc: Research Deposit Slip document

        Returns:
            List[str]: List of ECS dates in YYYY-MM-DD format
        """
        ecs_dates = []
        # Doctype uses 'ecs_date' (singular) for the child table
        ecs_table = getattr(doc, 'ecs_date', None) or getattr(doc, 'ecs_dates', None)
        if ecs_table:
            for row in ecs_table:
                date_val = getattr(row, 'ecs_date', None) or getattr(row, 'date', None)
                if date_val:
                    if hasattr(date_val, 'strftime'):
                        ecs_dates.append(date_val.strftime('%Y-%m-%d'))
                    else:
                        ecs_dates.append(str(date_val).split(' ')[0])
        return ecs_dates

    @staticmethod
    def map_credit_distribution(doc) -> tuple:
        """
        Map credit distribution from child tables to PDF and DPF lists.
        Only used for PDF and DPF tables now.

        Args:
            doc: Research Deposit Slip document

        Returns:
            tuple: (pdf_list, dpf_list)
        """
        pdf_list = []
        dpf_list = []

        # Get overhead amount for percentage calculations
        overhead_amount = flt(getattr(doc, 'overhead_amount', 0))

        # 1. Map PDF Credit Distribution (Using pdf_credit_distribution child table)
        if hasattr(doc, "pdf_credit_distribution") and doc.pdf_credit_distribution:
            for row in doc.pdf_credit_distribution:
                copi_user_id = getattr(row, 'select_copi_id', None)
                row_amount = flt(getattr(row, 'pdf_amount', 0))
                
                # Fetch employee_id directly from the child table row
                employee_id = getattr(row, 'employee_id', "")

                # Fetch department_id for Co-PI from User doctype
                copi_dept_id = None
                if copi_user_id:
                     copi_dept_name = frappe.db.get_value("User", copi_user_id, "department_name")
                     copi_dept_id = get_department_id(copi_dept_name)

                # Use percentage from child table
                pdf_percentage = flt(getattr(row, 'pdf_percentage', 0))

                pdf_list.append(CreditDistributionPdfDTO(
                    employeeId=employee_id,
                    departmentId=int(copi_dept_id) if copi_dept_id else None,
                    pdfPercentage=pdf_percentage,
                    pdfAmount=row_amount
                ))
        
        # 2. Map DPF Credit Distribution (Using dpf_credit_distributions child table)
        if hasattr(doc, "dpf_credit_distributions") and doc.dpf_credit_distributions:
            for row in doc.dpf_credit_distributions:
                # Use department_id directly from the child table
                dept_id_val = getattr(row, 'department_id', None)
                row_amount = flt(getattr(row, 'dpf_amount', 0))
                
                # Use percentage from child table
                dpf_percentage = flt(getattr(row, 'dpf_percentage', 0))

                dpf_list.append(CreditDistributionDpfDTO(
                    departmentId=int(dept_id_val) if dept_id_val else None,
                    dpfPercentage=dpf_percentage,
                    dpfAmount=row_amount
                ))

        # Fallback to old generic table if new tables are missing (for backward compatibility during migration)
        # But user gave new JSON, so we prioritize new tables. 
        # If new tables empty/missing, check old `credit_distribution`.
        if not pdf_list and not dpf_list and hasattr(doc, "credit_distribution") and doc.credit_distribution:
             # ... (keep old logic or remove? I'll remove based on "major changes" implication)
             pass

        return pdf_list, dpf_list

    @classmethod
    def map_to_dto(cls, doc) -> ResearchDepositSlipDTO:
        """
        Map Frappe Research Deposit Slip document to ResearchDepositSlipDTO.

        Args:
            doc: Research Deposit Slip Frappe Document object

        Returns:
            ResearchDepositSlipDTO: Mapped DTO ready for validation and publishing
        """
        # Get basic information
        project_number = cls.get_project_number(doc)
        gst_type = cls.get_gst_type(doc)
        fund_received_ref_number = get_fund_received_ref_number(
            getattr(doc, 'fund_received_ref', None)
        )

        # Map ECS dates
        ecs_dates = cls.map_ecs_dates(doc)

        # Map credit distributions
        pdf_list, dpf_list = cls.map_credit_distribution(doc)

        # Map credit distribution amounts from doctype fields
        # Staff Welfare Fund: 5% of overhead
        swf_amount = flt(getattr(doc, 'staff_welfare_amount', 0))
        swf_percentage = 5.0  # As per doctype description

        # Student Welfare Fund: 5% of overhead (doctype uses student_welfare_fund)
        stwf_amount = flt(getattr(doc, 'student_welfare_fund', 0) or getattr(doc, 'student_welfare_amount', 0))
        stwf_percentage = 5.0  # As per doctype description

        # IDF: 40% of overhead
        idf_amount = flt(getattr(doc, 'idf_amount', 0))
        idf_percentage = 40.0  # As per doctype description

        # DPF: 25% of overhead (single amount, not a list for Research)
        dpf_amount = flt(getattr(doc, 'dpf_amount', 0))
        dpf_percentage = 25.0  # As per doctype description

        # PDF: 25% of overhead (single amount, not a list for Research)
        pdf_amount = flt(getattr(doc, 'pdf_amount', 0))
        pdf_percentage = 25.0  # As per doctype description

        # Overhead percentage - calculate from total_amount and overhead_amount if available
        overhead_amount = flt(getattr(doc, 'overhead_amount', 0))
        total_amount = flt(getattr(doc, 'total_amount', 0))
        overhead_percentage = 10.0  # Default
        if total_amount > 0 and overhead_amount > 0:
            overhead_percentage = (overhead_amount / total_amount) * 100

        # Logic to remove automated PI Credit Distribution inclusion
        # We now rely solely on the pdf_credit_distribution child table.
        # PI details are not needed here for the list.

        # Build the DTO
        dto = ResearchDepositSlipDTO(
            projectNumber=project_number,
            fundReceivedRefNumber=fund_received_ref_number,
            slipNumber=doc.name,
            depositSlipRefNumFab=doc.name,  # Frappe deposit slip document name
            category="RESEARCH",
            ecsAccountNo=getattr(doc, 'ecs_scheme_no', '') or getattr(doc, 'ecs_ac_no', '') or "",
            bankName=getattr(doc, 'bank_name', '') or "",
            bmrNumber=getattr(doc, 'bmr_number', '') or getattr(doc, 'account_number', '') or "",
            amountReceived=flt(getattr(doc, 'total_amount', 0)),
            amountInclusiveGst=flt(getattr(doc, 'total_amount', 0)),  # No GST for research
            gstType=gst_type,
            finalGstAmount=0.0,  # No GST for research
            finalTotalAmount=flt(getattr(doc, 'grand_total', 0)),  # Grand total
            totalOverheadPercentage=overhead_percentage,
            totalOverheadAmount=overhead_amount,
            # netProjectAmount = total_amount - gst - overhead (after deduction of GST and overhead)
            netProjectAmount=flt(total_amount - overhead_amount),  # For research, no GST so just: total - overhead
            depositDate=fmt_date(getattr(doc, 'deposit_date', None) or getattr(doc, 'creation', None)),
            createdAt=fmt_date(getattr(doc, 'creation', None)),
            updatedAt=fmt_date(getattr(doc, 'modified', None)),
            createdBy=getattr(doc, 'owner', ''),
            updatedBy=getattr(doc, 'modified_by', ''),
            status="APPROVED",
            ecsDates=ecs_dates,
            creditDistributionSwf=CreditDistributionSwfDTO(
                swfPercentage=swf_percentage,
                swfAmount=swf_amount
            ),
            creditDistributionPdf=pdf_list,
            creditDistributionDpf=dpf_list,
            creditDistributionIdf=CreditDistributionIdfDTO(
                idfPercentage=idf_percentage,
                idfAmount=idf_amount
            ),
            creditDistributionStwf=CreditDistributionStwfDTO(
                stwfPercentage=stwf_percentage,
                stwfAmount=stwf_amount
            ),
        )

        # Store fundReceivedRefNumberFap (fund received document name) as extra attribute
        # This links the deposit slip back to the fund received document by name
        # dto.fundReceivedRefNumberFap = getattr(doc, 'fund_received_ref', '') or ''

        return dto

    @classmethod
    def map_to_event(cls, doc) -> ResearchDepositSlipEvent:
        """
        Map Frappe Research Deposit Slip document to ResearchDepositSlipEvent.
        This wraps the DTO in an event envelope for Kafka publishing.

        Args:
            doc: Research Deposit Slip Frappe Document object

        Returns:
            ResearchDepositSlipEvent: Event wrapper ready for Kafka publishing
        """
        dto = cls.map_to_dto(doc)
        return ResearchDepositSlipEvent(dto)
