# Copyright (c) 2025, rndops and contributors
# Mapper for Research Deposit Slip Document to DTO

import frappe
from frappe.utils import flt
from typing import List

from .dto import ResearchDepositSlipDTO
from ..common.dto_base import (
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)
from ..common.utils import fmt_date, get_fund_received_ref_number, get_department_id


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
                    "name"
                ) or doc.project_title
            except Exception:
                project_number = doc.project_title or ""
        return project_number

    @staticmethod
    def map_gst_details(doc) -> GstDetailsDTO:
        """
        Map GST details from document to GstDetailsDTO.

        Args:
            doc: Research Deposit Slip document

        Returns:
            GstDetailsDTO: GST details DTO
        """
        cgst_amount = flt(getattr(doc, 'cgst_9', 0))
        sgst_amount = flt(getattr(doc, 'sgst_9', 0))
        total_gst = flt(getattr(doc, 'total_gst', 0))

        cgst_percentage = None
        sgst_percentage = None
        igst_percentage = None
        igst_amount = 0

        if total_gst > 0:
            if cgst_amount > 0 or sgst_amount > 0:
                cgst_percentage = 9.0
                sgst_percentage = 9.0
            else:
                igst_amount = total_gst
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

        Args:
            doc: Research Deposit Slip document

        Returns:
            List[str]: List of ECS dates in ISO format
        """
        ecs_dates = []
        if hasattr(doc, "ecs_dates"):
            for row in doc.ecs_dates:
                if getattr(row, 'ecs_date', None):
                    ecs_dates.append(fmt_date(row.ecs_date))
        return ecs_dates

    @staticmethod
    def map_credit_distribution(doc) -> tuple:
        """
        Map credit distribution from child table to PDF and DPF lists.

        Args:
            doc: Research Deposit Slip document

        Returns:
            tuple: (pdf_list, dpf_list)
        """
        pdf_list = []
        dpf_list = []

        if hasattr(doc, "credit_distribution"):
            for row in doc.credit_distribution:
                label = (getattr(row, 'label', '') or "").upper()

                # Get employee_id and department_id
                employee_id = getattr(row, 'employee_id', None) or getattr(row, 'emp_id', None) or ""
                department_id = getattr(row, 'department_id', None) or getattr(row, 'dept_id', None)

                # Fetch dept_id from Department_prornd if department name is provided
                dept_name = getattr(row, 'department', None) or getattr(row, 'department_name', None)
                if dept_name and not department_id:
                    department_id = get_department_id(dept_name)

                if "PDF" in label or "PRINCIPAL" in label:
                    pdf_list.append(CreditDistributionPdfDTO(
                        employeeId=employee_id,
                        departmentId=int(department_id) if department_id else None,
                        pdfPercentage=flt(getattr(row, 'percentage_of_overhead', 0) or getattr(row, 'percentage', 0)),
                        pdfAmount=flt(getattr(row, 'amount', 0))
                    ))
                elif "DPF" in label or "DEPARTMENTAL" in label:
                    dpf_list.append(CreditDistributionDpfDTO(
                        departmentId=int(department_id) if department_id else None,
                        dpfPercentage=flt(getattr(row, 'percentage_of_overhead', 0) or getattr(row, 'percentage', 0)),
                        dpfAmount=flt(getattr(row, 'amount', 0))
                    ))

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

        # Map GST details
        gst_details = cls.map_gst_details(doc)

        # Map ECS dates
        ecs_dates = cls.map_ecs_dates(doc)

        # Map credit distributions
        pdf_list, dpf_list = cls.map_credit_distribution(doc)

        # Map credit distribution amounts
        swf_amount = flt(getattr(doc, 'staff_welfare_amount', 0))
        swf_percentage = 5.0

        stwf_amount = flt(getattr(doc, 'student_welfare_amount', 0))
        stwf_percentage = 5.0

        idf_amount = flt(getattr(doc, 'idf_amount', 0))
        idf_percentage = 40.0

        overhead_percentage = 15.0
        if hasattr(doc, 'overhead_percentage') and getattr(doc, 'overhead_percentage', None):
            overhead_percentage = flt(doc.overhead_percentage)

        # Build the DTO
        dto = ResearchDepositSlipDTO(
            projectNumber=project_number,
            fundReceivedRefNumber=fund_received_ref_number,
            depositSlipRefNumFab=doc.name,
            slipNumber=doc.name,
            category="RESEARCH",
            ecsAccountNo=getattr(doc, 'ecs_ac_no', '') or getattr(doc, 'ecs_acc_no', '') or "",
            bankName=getattr(doc, 'bank', '') or "",
            bmrNumber=getattr(doc, 'bmr_number', '') or "",
            amountReceived=flt(getattr(doc, 'amount_inclusive_gst_capital', 0) or getattr(doc, 'total_amount', 0)),
            amountInclusiveGst=flt(getattr(doc, 'amount_inclusive_gst_capital', 0) or getattr(doc, 'total_amount', 0)),
            gstType=gst_type,
            finalGstAmount=flt(getattr(doc, 'total_gst', 0)),
            finalTotalAmount=flt(getattr(doc, 'total_budget', 0)) if hasattr(doc, 'total_budget') else flt(getattr(doc, 'total_amount', 0)),
            totalOverheadPercentage=overhead_percentage,
            totalOverheadAmount=flt(getattr(doc, 'overhead_amount', 0)),
            netProjectAmount=flt(getattr(doc, 'project_balance_after_gst', 0)) if hasattr(doc, 'project_balance_after_gst') else flt(getattr(doc, 'prj_amount', 0)),
            depositDate=fmt_date(getattr(doc, 'creation', None)),
            createdAt=fmt_date(getattr(doc, 'creation', None)),
            updatedAt=fmt_date(getattr(doc, 'modified', None)),
            createdBy=getattr(doc, 'owner', ''),
            updatedBy=getattr(doc, 'modified_by', ''),
            status="APPROVED",
            ecsDates=ecs_dates,
            gstDetails=gst_details if gst_type != "NOGST" else None,
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

        return dto
