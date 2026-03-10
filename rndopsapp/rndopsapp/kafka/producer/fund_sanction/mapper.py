# Copyright (c) 2025, rndops and contributors
# Fund Sanction Mapper - Maps Frappe document to DTO

import frappe
from datetime import datetime
from typing import List

from .dto import FundSanctionDTO, BudgetBreakupDTO, FundSanctionEventDTO
from ...config import SCHEMA_VERSION_SANCTION
from ...utils import get_budget_head_id


class FundSanctionMapper:
    """
    Maps Frappe Fund Sanction document to FundSanctionDTO.
    Handles field name mapping and data transformation.
    """

    @staticmethod
    def map_budget_breakups(doc) -> List[BudgetBreakupDTO]:
        """
        Map budget breakup child table to list of BudgetBreakupDTO.

        Args:
            doc: Fund Sanction document

        Returns:
            List[BudgetBreakupDTO]: List of budget breakup DTOs
        """
        budget_breakups = []

        if not hasattr(doc, 'sanctioned_budget_breakup'):
            return budget_breakups

        for row in doc.sanctioned_budget_breakup:
            # Get account head ID
            account_head_id = getattr(row, 'b_id', None)

            # If b_id is missing, fetch from Budget Head
            if account_head_id is None and row.account_head:
                account_head_id = get_budget_head_id(row.account_head)

            # Get year budgets
            first_year = float(row.first_year_budget or 0)
            second_year = float(row.second_year_budget or 0)
            third_year = float(row.third_year_budget or 0)
            fourth_year = float(row.fourth_year_budget or 0)
            fifth_year = float(row.fifth_year_budget or 0)

            # Calculate accountHeadAmount
            account_head_amount = float(row.total_proposal_of_heads or 0)
            if account_head_amount == 0:
                account_head_amount = first_year + second_year + third_year + fourth_year + fifth_year

            budget_breakups.append(BudgetBreakupDTO(
                accountHeadId=account_head_id,
                accountHeadAmount=account_head_amount,
                firstYearBudget=first_year,
                secondYearBudget=second_year,
                thirdYearBudget=third_year,
                fourthYearBudget=fourth_year,
                fifthYearBudget=fifth_year
            ))

        return budget_breakups

    @staticmethod
    def get_project_number(doc) -> str:
        """
        Get project number from linked Project Registration.

        Args:
            doc: Fund Sanction document

        Returns:
            str: Project number
        """
        project_number = ""
        project_ref = doc.refnum_prj_num or doc.project_proposal
        
        if project_ref:
            try:
                # Check if it is a link to Project Registration
                # by trying to fetch project_no from it
                project_number = frappe.db.get_value(
                    "Project Registration", 
                    project_ref, 
                    "project_no"
                ) or ""
            except Exception:
                # If fetch fails, return empty string
                project_number = ""
        
        return project_number

    @classmethod
    def map_to_dto(cls, doc) -> FundSanctionDTO:
        """
        Map Frappe Fund Sanction document to FundSanctionDTO.

        Args:
            doc: Fund Sanction Frappe document

        Returns:
            FundSanctionDTO: Mapped DTO ready for validation and publishing
        """
        # Get project number
        project_number = cls.get_project_number(doc)
        sanction_letter_no = doc.sanctioned_letter_no

        # Map budget breakups
        budget_breakups = cls.map_budget_breakups(doc)

        return FundSanctionDTO(
            projectNumber=project_number,
            sanctionLetterNo=sanction_letter_no,
            sanctionLetterDate=str(doc.sanctioned_letter_date) if doc.sanctioned_letter_date else None,
            totalSanctionAmount=float(doc.total_sanctioned_amount or 0),
            budgetBreakups=budget_breakups
        )

    @classmethod
    def map_to_event(cls, doc) -> FundSanctionEventDTO:
        """
        Map Frappe document to FundSanctionEventDTO (complete Kafka message).

        Args:
            doc: Fund Sanction Frappe document

        Returns:
            FundSanctionEventDTO: Complete event DTO ready for Kafka
        """
        sanction_data = cls.map_to_dto(doc)

        return FundSanctionEventDTO(
            schemaVersion=SCHEMA_VERSION_SANCTION,
            eventType="FUND_SANCTION",
            timestamp=datetime.utcnow().isoformat(),
            data=sanction_data
        )
