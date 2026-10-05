# Copyright (c) 2026, rndops and contributors
# Loan Request Mapper - Maps Frappe Loan Request document to DTO

import frappe
from datetime import datetime
from typing import List
from frappe.utils import today

from .dto import LoanRequestDTO, LoanBudgetBreakupDTO, LoanRequestEventDTO
from ...config import SCHEMA_VERSION_LOAN_REQUEST
from ...utils import get_budget_head_id


class LoanRequestMapper:

    @staticmethod
    def get_project_number(doc) -> str:
        """
        Resolve project number from the Loan Request document.
        Tries project_number field first, then looks up project_name.project_no.
        """
        # project_number is a Data field already set on the doc
        project_number = getattr(doc, 'project_number', None) or ""
        if project_number:
            return project_number

        # Fallback: look up from linked Project Registration
        project_name = getattr(doc, 'project_name', None)
        if project_name:
            try:
                project_number = frappe.db.get_value(
                    "Project Registration", project_name, "project_no"
                ) or ""
            except Exception:
                pass

        return project_number

    @staticmethod
    def get_loan_type(doc) -> str:
        """
        Extract short loan type code from loan_account_type select value.
        e.g. "IDF (Institute Development Fund)" → "IDF"
        """
        loan_account_type = getattr(doc, 'loan_account_type', None) or ""
        if loan_account_type and "(" in loan_account_type:
            return loan_account_type.split("(")[0].strip()
        return loan_account_type

    @staticmethod
    def map_budget_breakups(doc, project_number: str) -> List[LoanBudgetBreakupDTO]:
        """
        Map account_head_fund_breakup child table rows to LoanBudgetBreakupDTO list.
        """
        breakups = []
        rows = getattr(doc, 'account_head_fund_breakup', None) or []

        for row in rows:
            budget_head = getattr(row, 'budget_head', None)
            account_head_id = None

            if budget_head:
                # Resolve integer id from Budget Head doctype
                raw_id = frappe.db.get_value("Budget Head", budget_head, "id")
                if raw_id is not None:
                    account_head_id = str(raw_id)
                else:
                    # Fall back to utils helper
                    resolved = get_budget_head_id(budget_head)
                    account_head_id = str(resolved) if resolved is not None else None

            amount = float(getattr(row, 'account_head_amount', 0) or 0)

            breakups.append(LoanBudgetBreakupDTO(
                accountHeadId=account_head_id,
                amount=amount,
                projectNumber=project_number,
                remarks="",
            ))

        return breakups

    @classmethod
    def map_to_dto(cls, doc) -> LoanRequestDTO:
        project_number = cls.get_project_number(doc)
        loan_type = cls.get_loan_type(doc)
        budget_breakups = cls.map_budget_breakups(doc, project_number)
        loan_amount = float(getattr(doc, 'loan_amount', 0) or 0)

        bmr = getattr(doc, 'bmr', None) or None
        bmr_date = getattr(doc, 'bmr_date', None)
        bmr_date_str = str(bmr_date) if bmr_date else None

        return LoanRequestDTO(
            loanStatus="LOAN_APPROVED",
            loanReceivedDate=str(today()),
            projectNumber=project_number,
            loanNumberFap=doc.name,
            receivedFrom="",           # No receivedFrom field in Loan Request doctype
            loanType=loan_type,
            loanAmount=loan_amount,
            depositStatus="SUBMITTED",
            bmr=bmr,
            bmrDate=bmr_date_str,
            loanBudgetBreakupDetails=budget_breakups,
        )

    @classmethod
    def map_to_event(cls, doc) -> LoanRequestEventDTO:
        dto = cls.map_to_dto(doc)
        return LoanRequestEventDTO(
            schemaVersion=SCHEMA_VERSION_LOAN_REQUEST,
            eventType="LOAN_REQUEST",
            timestamp=datetime.utcnow().isoformat(),
            data=dto,
        )
