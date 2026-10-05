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
                project_number = frappe.db.get_value(
                    "Project Registration",
                    project_ref,
                    "project_no"
                ) or ""
            except Exception:
                project_number = ""

        return project_number

    @staticmethod
    def get_account_type_fields(doc):
        """
        Fetch PFMS / bank-account fields from the linked Project Registration.

        Project Registration uses:
          - is_the_account_type_pfms (Yes/No) to distinguish PFMS vs. bank
          - scheme_name / enter_scheme_number when PFMS
          - bank_name / account_number when ordinary bank

        Returns:
            Tuple: (is_pfms, scheme_name_or_bank_name, scheme_number_or_account_number)
        """
        project_ref = doc.refnum_prj_num or doc.project_proposal
        if not project_ref:
            return False, None, None

        try:
            pr = frappe.db.get_value(
                "Project Registration",
                project_ref,
                [
                    "is_the_account_type_pfms",
                    "scheme_name",
                    "enter_scheme_number",
                    "bank_name",
                    "account_number",
                ],
                as_dict=True,
            )
        except Exception:
            return False, None, None

        if not pr:
            return False, None, None

        is_pfms = (pr.get("is_the_account_type_pfms") or "").strip().lower() == "yes"

        if is_pfms:
            scheme_name_bank_name = pr.get("scheme_name") or None
            scheme_number_account_number = pr.get("enter_scheme_number") or None
        else:
            scheme_name_bank_name = pr.get("bank_name") or None
            scheme_number_account_number = pr.get("account_number") or None

        return is_pfms, scheme_name_bank_name, scheme_number_account_number

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

        # Get PFMS / bank-account fields from linked Project Registration
        is_pfms, scheme_name_bank_name, scheme_number_account_number = \
            cls.get_account_type_fields(doc)

        # Map budget breakups
        budget_breakups = cls.map_budget_breakups(doc)

        return FundSanctionDTO(
            projectNumber=project_number,
            sanctionLetterNo=sanction_letter_no,
            sanctionLetterDate=str(doc.sanctioned_letter_date) if doc.sanctioned_letter_date else None,
            totalSanctionAmount=float(doc.total_sanctioned_amount or 0),
            isPfms=is_pfms,
            schemeNameBankName=scheme_name_bank_name,
            schemeNumberAccountNumber=scheme_number_account_number,
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
