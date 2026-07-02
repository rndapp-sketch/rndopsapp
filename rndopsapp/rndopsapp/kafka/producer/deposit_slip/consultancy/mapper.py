# Copyright (c) 2025, rndops and contributors
# Mapper for Consultancy Deposit Slip Documents to DTO
# Supports: D Consultancy, E Non Routine, T Testing, Other Event

import frappe
from frappe.utils import flt
from typing import List, Optional
from datetime import datetime

from .dto import (
    ConsultancyDepositSlipDTO,
    ConsultancyDDetailsDTO,
    ConsultancyEDetailsDTO,
    ConsultancyTDetailsDTO,
    ConsultancyODetailsDTO,
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)


# ==========================================
# Event Wrapper Class
# ==========================================

class ConsultancyDepositSlipEvent:
    """
    Event wrapper for Consultancy Deposit Slip DTO.
    Provides the interface expected by the producer.
    """

    def __init__(self, dto: ConsultancyDepositSlipDTO):
        self.data = dto
        self.eventType = "DEPOSIT_SLIP"

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
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
        # If it's just a date (YYYY-MM-DD), append current time as requested
        # "add the time when it is producing"
        current_time_str = datetime.now().strftime("T%H:%M:%S.%f")
        date_str += current_time_str
    
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
# Consultancy Deposit Slip Mapper
# ==========================================

class ConsultancyDepositSlipMapper:
    """
    Maps Frappe Consultancy Deposit Slip documents to ConsultancyDepositSlipDTO.
    Auto-detects category from doctype.
    """

    # Doctype to Category mapping
    DOCTYPE_CATEGORY_MAP = {
        "D Consultancy Deposit Slip": "CONSULTANCY_D",
        "E Non Routine Deposit Slip": "CONSULTANCY_E",
        "T Testing Deposit Slip": "CONSULTANCY_T",
        "Other Event Deposit Slip": "OTHER_EVENT",
    }

    @classmethod
    def get_category(cls, doc) -> str:
        """
        Get category from document doctype.

        Args:
            doc: Frappe document

        Returns:
            str: Category (CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT)
        """
        doctype = doc.doctype
        return cls.DOCTYPE_CATEGORY_MAP.get(doctype, "CONSULTANCY_D")

    @staticmethod
    def get_project_number(doc) -> str:
        """
        Get project number from document.

        Args:
            doc: Consultancy Deposit Slip document

        Returns:
            str: Project number
        """
        # project_number is a direct numeric/code field on Research-type slips.
        # consultancy_title and event_title are free-text titles — never use them as a project number.
        # For E Non Routine / T Testing, project_title is a Link → Project Registration;
        # look up project_no from there.
        # For Other Event / D Consultancy (no project link on the slip itself),
        # trace back via fund_received_ref → Fund Received.prjreg_title → Project Registration.project_no.
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

        if not project_number and getattr(doc, 'fund_received_ref', None):
            try:
                prjreg = frappe.db.get_value(
                    "Fund Received",
                    doc.fund_received_ref,
                    "prjreg_title"
                )
                if prjreg:
                    project_number = frappe.db.get_value(
                        "Project Registration",
                        prjreg,
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
            doc: Consultancy Deposit Slip document

        Returns:
            str: "NOGST", "CGST_SGST", or "IGST"
        """
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

    @staticmethod
    def map_gst_details(doc, gst_type: str) -> Optional[GstDetailsDTO]:
        """
        Map GST details from document to GstDetailsDTO.

        Args:
            doc: Consultancy Deposit Slip document
            gst_type: GST type

        Returns:
            GstDetailsDTO or None if NOGST
        """
        if gst_type == "NOGST":
            return None

        cgst_amount = flt(getattr(doc, 'cgst_9', 0))
        sgst_amount = flt(getattr(doc, 'sgst_9', 0))
        igst_amount = flt(getattr(doc, 'igst_18', 0) or getattr(doc, 'igst_18_on_consultancy', 0))
        total_gst = flt(getattr(doc, 'total_gst', 0))

        cgst_percentage = None
        sgst_percentage = None
        igst_percentage = None

        if gst_type == "CGST_SGST":
            cgst_percentage = 9.0
            sgst_percentage = 9.0
        elif gst_type == "IGST":
            igst_percentage = 18.0

        return GstDetailsDTO(
            cgstPercentage=cgst_percentage,
            cgstAmount=cgst_amount if cgst_amount > 0 else None,
            sgstPercentage=sgst_percentage,
            sgstAmount=sgst_amount if sgst_amount > 0 else None,
            igstPercentage=igst_percentage,
            igstAmount=igst_amount if igst_amount > 0 else None,
            totalGstAmount=total_gst
        )

    @staticmethod
    def map_ecs_dates(doc) -> List[str]:
        """
        Map ECS dates from child table.

        Args:
            doc: Consultancy Deposit Slip document

        Returns:
            List[str]: List of ECS dates in ISO format
        """
        ecs_dates = []
        if hasattr(doc, "ecs_dates"):
            for row in doc.ecs_dates:
                if getattr(row, 'ecs_date', None):
                    ecs_dates.append(str(row.ecs_date)[:10])
        return ecs_dates

    @staticmethod
    def map_credit_distribution(doc) -> tuple:
        """
        Map credit distribution from child tables to PDF and DPF lists.
        Only used for PDF and DPF tables now.

        Args:
            doc: Consultancy Deposit Slip document

        Returns:
            tuple: (pdf_list, dpf_list)
        """
        pdf_list = []
        dpf_list = []

        # 1. Map PDF Credit Distribution (Co-PIs)
        # Check for new table `pdf_credit_distribution`
        if hasattr(doc, "pdf_credit_distribution") and doc.pdf_credit_distribution:
            for row in doc.pdf_credit_distribution:
                copi_user_id = getattr(row, 'select_copi_id', None)
                if not copi_user_id:
                    continue

                # Fetch employee_id for Co-PI from User doctype
                copi_employee_id = ""
                if copi_user_id:
                     copi_emp_details = frappe.db.get_value("User", copi_user_id, "employee_id")
                     copi_employee_id = copi_emp_details or ""

                pdf_list.append(CreditDistributionPdfDTO(
                    employeeId=copi_employee_id,
                    departmentId=None, 
                    pdfPercentage=flt(getattr(row, 'pdf_percentage', 0)),
                    pdfAmount=flt(getattr(row, 'pdf_amount', 0))
                ))
        
        # 2. Map DPF Credit Distribution
        # Check for new table `dpf_credit_distributions`
        if hasattr(doc, "dpf_credit_distributions") and doc.dpf_credit_distributions:
            for row in doc.dpf_credit_distributions:
                dept_name = getattr(row, 'select_dpf_dept_center_school', None)
                dept_id = get_department_id(dept_name)
                
                dpf_list.append(CreditDistributionDpfDTO(
                    departmentId=int(dept_id) if dept_id else None,
                    dpfPercentage=flt(getattr(row, 'dpf_percentage', 0)),
                    dpfAmount=flt(getattr(row, 'dpf_amount', 0))
                ))

        # Fallback to old generic table if new tables are missing (for backward compatibility)
        if not pdf_list and not dpf_list and hasattr(doc, "credit_distribution") and doc.credit_distribution:
             # Basic fallback or just ignore based on request for "major changes"
             # I will keeping this part removed to strictly follow the new structure as user implied.
             pass

        return pdf_list, dpf_list

    @staticmethod
    def map_consultancy_d_details(doc) -> ConsultancyDDetailsDTO:
        """
        Map Consultancy D specific details.

        Args:
            doc: D Consultancy Deposit Slip document

        Returns:
            ConsultancyDDetailsDTO
        """
        return ConsultancyDDetailsDTO(
            gstTdsPercentage=flt(getattr(doc, 'gst_tds_percentage', 0) or 2.0),
            gstTdsAmount=flt(getattr(doc, 'gst_tds_amount', 0)),
            amountReceivedAfterGstTds=flt(getattr(doc, 'amount_after_gst_tds', 0)),
            totalCostX=flt(getattr(doc, 'total_cost_x', 0)),
            consultancyChargeYPercentage=flt(getattr(doc, 'consultancy_charge_y_percentage', 0) or 50.0),
            consultancyChargeY=flt(getattr(doc, 'consultancy_charge_y', 0)),
            operationalChargeZPercentage=flt(getattr(doc, 'operational_charge_z_percentage', 0) or 50.0),
            operationalChargeZ=flt(getattr(doc, 'operational_charge_z', 0)),
            overHeadYPercentage=flt(getattr(doc, 'overhead_from_y_multiplier', 0) * 100 or 10.0),
            overHeadYAmount=flt(getattr(doc, 'overhead_from_y_amount', 0)),
            overHeadZPercentage=flt(getattr(doc, 'overhead_from_z_multiplier', 0) * 100 or 10.0),
            overHeadZAmount=flt(getattr(doc, 'overhead_from_z_amount', 0)),
            instituteSharePercentage=flt(getattr(doc, 'institute_share_multiplier', 0) * 100 or 20.0),
            instituteShare=flt(getattr(doc, 'institute_share_amount', 0)),
            totalOverHeadInstituteShare=flt(getattr(doc, 'total_overhead_institute_share', 0))
        )

    @staticmethod
    def map_consultancy_e_details(doc) -> ConsultancyEDetailsDTO:
        """
        Map Consultancy E specific details.

        Args:
            doc: E Non Routine Deposit Slip document

        Returns:
            ConsultancyEDetailsDTO
        """
        consultancy_fee = flt(getattr(doc, 'consultancy_fee_x', 0) or getattr(doc, 'training_fee', 0))
        return ConsultancyEDetailsDTO(
            consultancyFeeX_trainingFee=consultancy_fee
        )

    @staticmethod
    def map_consultancy_t_details(doc) -> ConsultancyTDetailsDTO:
        """
        Map Consultancy T specific details.

        Args:
            doc: T Testing Deposit Slip document

        Returns:
            ConsultancyTDetailsDTO
        """
        consultancy_fee = flt(getattr(doc, 'consultancy_fee_x', 0) or getattr(doc, 'training_fee', 0))
        return ConsultancyTDetailsDTO(
            consultancyFeeX_trainingFee=consultancy_fee
        )

    @staticmethod
    def map_consultancy_o_details(doc) -> ConsultancyODetailsDTO:
        """
        Map Other Event specific details.

        Args:
            doc: Other Event Deposit Slip document

        Returns:
            ConsultancyODetailsDTO
        """
        consultancy_fee = flt(getattr(doc, 'training_fee', 0) or getattr(doc, 'consultancy_fee_x', 0))
        return ConsultancyODetailsDTO(
            consultancyFeeX_trainingFee=consultancy_fee
        )

    @classmethod
    def map_to_dto(cls, doc) -> ConsultancyDepositSlipDTO:
        """
        Map Frappe Consultancy Deposit Slip document to ConsultancyDepositSlipDTO.
        Auto-detects category from doctype.

        Args:
            doc: Consultancy Deposit Slip Frappe Document

        Returns:
            ConsultancyDepositSlipDTO: Mapped DTO ready for validation and publishing
        """
        category = cls.get_category(doc)
        project_number = cls.get_project_number(doc)
        gst_type = cls.get_gst_type(doc)
        fund_received_ref_number = get_fund_received_ref_number(
            getattr(doc, 'fund_received_ref', None)
        )

        # Map GST details
        gst_details = cls.map_gst_details(doc, gst_type)

        # Map ECS dates
        ecs_dates = cls.map_ecs_dates(doc)

        # Map credit distributions
        pdf_list, dpf_list = cls.map_credit_distribution(doc)

        # Map credit distribution amounts
        swf_amount = flt(getattr(doc, 'staff_welfare_amount', 0) or getattr(doc, 'staff_welfare_t_testing_fund', 0))
        swf_percentage = 5.0

        stwf_amount = flt(getattr(doc, 'student_welfare_amount', 0) or getattr(doc, 'student_welfare_t_testing_fund', 0))
        stwf_percentage = 5.0

        idf_amount = flt(getattr(doc, 'idf_amount', 0) or getattr(doc, 'idf_t_testing_fee', 0))
        idf_percentage = 40.0

        dpf_amount = flt(getattr(doc, 'dpf_amount', 0) or getattr(doc, 'dpf_t_testing_fee', 0))
        dpf_percentage = 50.0

        # Get amount field based on doctype
        amount_received = flt(
            getattr(doc, 'amount_inclusive_of_gst', 0) or
            getattr(doc, 'amount_inclusive_gst_capital', 0) or
            getattr(doc, 'total_amount', 0)
        )

        overhead_percentage = flt(getattr(doc, 'overhead_percentage', 0) or getattr(doc, 'overhead_multiplier', 0) * 100 or 10.0)
        overhead_amount = flt(getattr(doc, 'overhead_amount', 0) or getattr(doc, 'total_overhead_amount', 0))

        # Map category-specific details
        consultancy_d_details = None
        consultancy_e_details = None
        consultancy_t_details = None
        consultancy_o_details = None

        if category == "CONSULTANCY_D":
            consultancy_d_details = cls.map_consultancy_d_details(doc)
        elif category == "CONSULTANCY_E":
            consultancy_e_details = cls.map_consultancy_e_details(doc)
        elif category == "CONSULTANCY_T":
            consultancy_t_details = cls.map_consultancy_t_details(doc)
        elif category == "OTHER_EVENT":
            consultancy_o_details = cls.map_consultancy_o_details(doc)

        # Build the DTO
        dto = ConsultancyDepositSlipDTO(
            projectNumber=project_number,
            fundReceivedRefNumber=fund_received_ref_number,
            depositSlipRefNumFab=doc.name,
            slipNumber=doc.name,
            category=category,
            ecsAccountNo=getattr(doc, 'ecs_ac_no', '') or getattr(doc, 'ecs_acc_no', '') or "",
            bankName=getattr(doc, 'bank', '') or "",
            bmrNumber=getattr(doc, 'bmr_number', '') or "",
            amountReceived=amount_received,
            amountInclusiveGst=amount_received,
            gstType=gst_type,
            finalGstAmount=flt(getattr(doc, 'total_gst', 0)),
            finalTotalAmount=flt(getattr(doc, 'total_amount', 0) or amount_received),
            totalOverheadPercentage=overhead_percentage,
            totalOverheadAmount=overhead_amount,
            netProjectAmount=flt(getattr(doc, 'project_balance_after_gst', 0) or getattr(doc, 'prj_amount', 0)),
            depositDate=fmt_date(getattr(doc, 'creation', None)),
            createdAt=fmt_date(getattr(doc, 'creation', None)),
            updatedAt=fmt_date(getattr(doc, 'modified', None)),
            createdBy=getattr(doc, 'owner', ''),
            updatedBy=getattr(doc, 'modified_by', ''),
            status="APPROVED",
            ecsDates=ecs_dates,
            gstDetails=gst_details,
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
            consultancyDDetails=consultancy_d_details,
            consultancyEDetails=consultancy_e_details,
            consultancyTDetails=consultancy_t_details,
            consultancyODetails=consultancy_o_details,
        )

        # Store fundReceivedRefNumberFap (fund received document name) as extra attribute
        # This links the deposit slip back to the fund received document by name
        # dto.fundReceivedRefNumberFap = getattr(doc, 'fund_received_ref', '') or ''

        return dto

    @classmethod
    def map_to_event(cls, doc) -> ConsultancyDepositSlipEvent:
        """
        Map Frappe Consultancy Deposit Slip document to ConsultancyDepositSlipEvent.
        Wraps the DTO in an event envelope for Kafka publishing.
        """
        dto = cls.map_to_dto(doc)
        return ConsultancyDepositSlipEvent(dto)
