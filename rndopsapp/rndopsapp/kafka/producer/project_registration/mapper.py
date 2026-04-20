# Copyright (c) 2025, rndops and contributors
# Project Registration Mapper - Maps Frappe document to DTO

import frappe
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple

from .dto import ProjectDataDTO, ProjectEventDTO
from ...config import SCHEMA_VERSION_PROJECT
from ...utils import get_department_id, get_funding_agency_id


class ProjectRegistrationMapper:
    """
    Maps Frappe Project Registration document to ProjectDataDTO.
    Handles field name mapping and data transformation.
    """

    @staticmethod
    def get_department_centres(doc) -> Tuple[List[str], Optional[str]]:
        """
        Extract department centres from implementation_department field.

        Args:
            doc: Project Registration document

        Returns:
            Tuple: (list of dept_ids, primary department_id)
        """
        dept_centres = []
        imp_dept = getattr(doc, "implementation_department", None)

        # Check if it's a list (Child Table)
        if isinstance(imp_dept, list):
            for row in imp_dept:
                d_link = getattr(row, "department", None)
                d_id = get_department_id(d_link)
                if d_id:
                    dept_centres.append(str(d_id))
        # Check if it's a single link
        elif isinstance(imp_dept, str) and imp_dept:
            d_id = get_department_id(imp_dept)
            if d_id:
                dept_centres.append(str(d_id))

        # Extract primary department_id from the first department
        department_id = dept_centres[0] if dept_centres else None

        return dept_centres, department_id

    @staticmethod
    def get_funding_agency(doc) -> Optional[str]:
        """
        Get funding agency ID from document.

        Args:
            doc: Project Registration document

        Returns:
            str or None: Funding agency ID
        """
        funding_agency_id = getattr(doc, "funding_agency_id", None)
        if not funding_agency_id:
            funding_agen_link = getattr(doc, "funding_agen", None)
            if funding_agen_link:
                funding_agency_id = get_funding_agency_id(funding_agen_link)

        return funding_agency_id

    @staticmethod
    def calculate_budget_amounts(
        total_budget_amount: float,
        overhead_amount: float,
        gst_amount: float
    ) -> Tuple[float, float]:
        """
        Calculate totalBudgetAmount and overHeadAmountPercentage.

        Args:
            total_budget_amount: Original total budget amount
            overhead_amount: Overhead amount
            gst_amount: GST amount

        Returns:
            Tuple: (calculated_total_budget, overhead_percentage)
        """
        calculated_total = total_budget_amount - (overhead_amount + gst_amount)

        if total_budget_amount > 0:
            overhead_pct = (overhead_amount / total_budget_amount) * 100
        else:
            overhead_pct = 0.0

        return calculated_total, overhead_pct

    @staticmethod
    def get_category_d_amounts(doc) -> Tuple[float, float, float, float]:
        """
        Get financial amounts for Category D (Technology Transfer / Research Based).

        Args:
            doc: Project Registration document

        Returns:
            Tuple: (overhead_amount, gst_amount, grand_total, budget_with_overhead)
        """
        overhead_amount = float(getattr(doc, 'cat_d_total_overhead', 0) or 0)
        gst_amount = float(getattr(doc, 'cat_d_gst_amt', 0) or 0)
        grand_total = float(getattr(doc, 'cat_d_grand_total_calc', 0) or 0)
        budget_with_overhead = float(getattr(doc, 'cat_d_project_cost_excl_gst', 0) or 0)

        return overhead_amount, gst_amount, grand_total, budget_with_overhead

    @staticmethod
    def get_category_ef_amounts(doc) -> Tuple[float, float, float, float]:
        """
        Get financial amounts for Category E/F (Non-routine / Testing).

        Args:
            doc: Project Registration document

        Returns:
            Tuple: (overhead_amount, gst_amount, grand_total, budget_with_overhead)
        """
        overhead_amount = 0.0
        gst_amount = float(getattr(doc, 'cat_ef_gst', 0) or 0)
        grand_total = float(getattr(doc, 'cat_ef_grand_total', 0) or 0)
        budget_with_overhead = float(getattr(doc, 'cat_ef_total_amount', 0) or 0)

        return overhead_amount, gst_amount, grand_total, budget_with_overhead

    @staticmethod
    def get_research_amounts(doc, base_total_budget: float) -> Tuple[float, float, float, float]:
        """
        Get financial amounts for Research projects.

        Args:
            doc: Project Registration document
            base_total_budget: Base total budget amount

        Returns:
            Tuple: (overhead_amount, gst_amount, grand_total, budget_with_overhead)
        """
        # First try document-level fields
        overhead_amount = float(getattr(doc, 'overhead_research', 0) or getattr(doc, 'overhead_consultancy', 0) or 0)
        gst_amount = float(getattr(doc, 'service_tax_research', 0) or getattr(doc, 'service_tax_consultancy', 0) or 0)

        # If document-level fields are 0, extract from proposed_budget_breakup
        if overhead_amount == 0 or gst_amount == 0:
            budget_breakup = getattr(doc, 'proposed_budget_breakup', []) or []
            for row in budget_breakup:
                account_head = getattr(row, 'account_head', '').strip().lower()
                row_amount = float(getattr(row, 'total_proposal_of_heads', 0) or 0)

                if overhead_amount == 0 and account_head == 'overhead':
                    overhead_amount = row_amount
                elif gst_amount == 0 and account_head == 'gst':
                    gst_amount = row_amount

        grand_total = float(getattr(doc, 'total_budget_amount', 0) or getattr(doc, 'grand_total_consultancy', 0) or 0)
        budget_with_overhead = float(
            getattr(doc, 'budget_including_overhead_research', 0) or
            getattr(doc, 'budget_including_overhead_consultancy', 0) or 0
        )

        # If budget_with_overhead is 0, calculate as: sum - GST
        if budget_with_overhead == 0:
            budget_with_overhead = base_total_budget - gst_amount

        return overhead_amount, gst_amount, grand_total, budget_with_overhead

    @classmethod
    def map_to_dto(cls, doc) -> ProjectDataDTO:
        """
        Map Frappe Project Registration document to ProjectDataDTO.

        Args:
            doc: Project Registration Frappe document

        Returns:
            ProjectDataDTO: Mapped DTO ready for validation and publishing
        """
        # Get department centres and primary department
        dept_centres, department_id = cls.get_department_centres(doc)

        # Get funding agency ID
        funding_agency_id = cls.get_funding_agency(doc)

        # Parse dates - default to today and today + 1 month if missing
        today = date.today()
        start_date = doc.prj_start_date or getattr(doc, 'start_date', None) or today
        completion_date = doc.prj_end_date or getattr(doc, 'completion_date', None) or (today + timedelta(days=30))

        # Apply/Verdict Dates
        apply_date = doc.creation if doc.creation else datetime.utcnow()

        # Determine project type and category
        is_consultancy = doc.project_type == "Consultancy"
        consultancy_category = getattr(doc, 'consultancy_category', '')
        is_category_d = is_consultancy and 'Category D' in consultancy_category
        is_category_ef = is_consultancy and (
            'Category E' in consultancy_category or
            'Category F' in consultancy_category
        )

        # Get base total budget
        base_total_budget = float(doc.total_budget_amount or 0)

        # Map financial fields based on category
        if is_category_d:
            overhead_amount, gst_amount, grand_total, budget_with_overhead = \
                cls.get_category_d_amounts(doc)
        elif is_category_ef:
            overhead_amount, gst_amount, grand_total, budget_with_overhead = \
                cls.get_category_ef_amounts(doc)
        else:
            overhead_amount, gst_amount, grand_total, budget_with_overhead = \
                cls.get_research_amounts(doc, base_total_budget)

        # Calculate total budget and overhead percentage
        calculated_total_budget, overhead_percentage = cls.calculate_budget_amounts(
            base_total_budget, overhead_amount, gst_amount
        )

        # Build ProjectDataDTO
        return ProjectDataDTO(
            projectNumber=doc.project_no or doc.name,
            empId=doc.pi_employee_id or "",
            departmentId=department_id or "",
            projectType=doc.project_type or "",
            projectCategory=doc.consultancy_category or doc.project_type or "",
            fundingAgencyType=doc.funding_agency_type or "",
            fundingAgencyId=funding_agency_id or "",
            projectScheme=doc.funding_agency_schemes or "",
            totalBudgetAmount=calculated_total_budget,
            overHeadAmountPercentage=overhead_percentage,
            overHeadAmount=overhead_amount,
            budgetWithOverHeadAmount=budget_with_overhead,
            gst=gst_amount,
            grandTotal=grand_total,
            startDate=start_date,
            completionDate=completion_date,
            durationMonths=str(doc.project_duration_months) if doc.project_duration_months else "00",
            durationInDays=str(doc.project_duration_days) if doc.project_duration_days else "0",
            status=doc.workflow_state or "",
            applyDate=apply_date,
            implementedDeptCentres=dept_centres
        )

    @classmethod
    def map_to_event(cls, doc) -> ProjectEventDTO:
        """
        Map Frappe document to ProjectEventDTO (complete Kafka message).

        Args:
            doc: Project Registration Frappe document

        Returns:
            ProjectEventDTO: Complete event DTO ready for Kafka
        """
        project_data = cls.map_to_dto(doc)

        return ProjectEventDTO(
            schemaVersion=SCHEMA_VERSION_PROJECT,
            eventType="PROJECT_REGISTRATION",
            timestamp=datetime.utcnow(),
            data=project_data
        )
