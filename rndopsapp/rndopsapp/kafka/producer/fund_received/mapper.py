# Copyright (c) 2025, rndops and contributors
# Fund Received Mapper - Maps Frappe document to DTO

import frappe
from datetime import datetime
from typing import List, Optional

from .dto import (
    FundReceivedDTO,
    FundBudgetBreakupDTO,
    TransactionDetailsDTO,
    FundReceivedEventDTO,
)
from ...config import SCHEMA_VERSION_FUND_RECEIVED
from ...utils import get_budget_head_id


class FundReceivedMapper:
    """
    Maps Frappe Fund Received document to FundReceivedDTO.
    Handles field name mapping and data transformation.
    """

    @staticmethod
    def get_sanction_letter_no(doc) -> Optional[str]:
        """
        Get sanction letter number from document or linked Fund Sanction.

        Args:
            doc: Fund Received document

        Returns:
            str or None: Sanction letter number
        """
        # First check if Fund Received has its own field
        sanction_letter_no = getattr(doc, 'sanctioned_letter_no', None)

        # If not available, fetch from linked Fund Sanction document
        sanction_ref = getattr(doc, 'sanction_ref_no', None)
        if sanction_ref and not sanction_letter_no:
            try:
                sanction_doc = frappe.db.get_value(
                    "Fund Sanction",
                    sanction_ref,
                    ["sanctioned_letter_no"],
                    as_dict=True
                )
                if sanction_doc:
                    sanction_letter_no = sanction_doc.get("sanctioned_letter_no")
            except Exception:
                pass

        return sanction_letter_no

    @staticmethod
    def map_budget_breakups(doc) -> List[FundBudgetBreakupDTO]:
        """
        Map budget breakup child table to list of FundBudgetBreakupDTO.

        Args:
            doc: Fund Received document

        Returns:
            List[FundBudgetBreakupDTO]: List of budget breakup DTOs
        """
        budget_breakups = []

        if not hasattr(doc, 'received_amt_breakup') or not doc.received_amt_breakup:
            return budget_breakups

        for row in doc.received_amt_breakup:
            # Get account head ID
            account_head_id = getattr(row, 'b_id', None)

            # If b_id is missing, fetch from Budget Head
            if account_head_id is None and row.account_head:
                account_head_id = get_budget_head_id(row.account_head)

            # Get amount and remarks
            amount = float(getattr(row, 'amount_received', 0) or 0)
            remarks = getattr(row, 'remarks', None) or getattr(row, 'description', None) or ""

            budget_breakups.append(FundBudgetBreakupDTO(
                accountHeadId=str(account_head_id) if account_head_id else None,
                amount=amount,
                remarks=remarks
            ))

        return budget_breakups

    @staticmethod
    def map_transaction_details(doc) -> List[TransactionDetailsDTO]:
        """
        Map transaction details child table to list of TransactionDetailsDTO.

        Args:
            doc: Fund Received document

        Returns:
            List[TransactionDetailsDTO]: List of transaction details DTOs
        """
        transaction_details = []

        if not hasattr(doc, 'fund_transactions') or not doc.fund_transactions:
            return transaction_details

        for row in doc.fund_transactions:
            unique_txn_number = getattr(row, 'transaction_number', "") or ""
            txn_date = getattr(row, 'transaction_date', None)
            txn_amount = float(getattr(row, 'amount', 0) or 0)

            transaction_details.append(TransactionDetailsDTO(
                uniqueTransactionNumber=unique_txn_number,
                transactionReceivedDate=str(txn_date) if txn_date else None,
                transactionAmount=txn_amount
            ))

        return transaction_details

    @staticmethod
    def get_linked_deposit_slip(doc) -> tuple:
        """
        Find linked deposit slip for this Fund Received document.

        Args:
            doc: Fund Received document

        Returns:
            tuple: (deposit_slip_name, deposit_slip_doctype) or (None, None)
        """
        # List of potential Deposit Slip doctypes
        deposit_doctypes = [
            "Research Deposit Slip",
            "Research Consultancy Deposit Slip",
            "D Consultancy Deposit Slip",
            "E Non Routine Deposit Slip",
            "Other Event Deposit Slip",
            "T Testing Deposit Slip"
        ]

        for dt in deposit_doctypes:
            try:
                ds_name = frappe.db.get_value(dt, {"fund_received_ref": doc.name}, "name")
                if ds_name:
                    return ds_name, dt
            except Exception:
                pass

        return None, None

    @staticmethod
    def get_project_number(doc) -> str:
        """
        Get project number from linked Project Registration.

        Args:
            doc: Fund Received document

        Returns:
            str: Project number
        """
        project_number = ""
        prjreg_title = getattr(doc, 'prjreg_title', None)
        
        if prjreg_title:
            try:
                # Check if prjreg_title is a link to Project Registration
                # by trying to fetch project_no from it
                project_number = frappe.db.get_value(
                    "Project Registration", 
                    prjreg_title, 
                    "project_no"
                ) or ""
            except Exception:
                # If fetch fails, return empty string
                project_number = ""
        
        return project_number

    @classmethod
    def map_to_dto(cls, doc) -> FundReceivedDTO:
        """
        Map Frappe Fund Received document to FundReceivedDTO.

        Args:
            doc: Fund Received Frappe document

        Returns:
            FundReceivedDTO: Mapped DTO ready for validation and publishing
        """
        # Get sanction details
        sanction_ref = getattr(doc, 'sanction_ref_no', None)
        sanction_letter_no = cls.get_sanction_letter_no(doc)
        
        # Get project number
        project_number = cls.get_project_number(doc)

        # Map child tables
        budget_breakups = cls.map_budget_breakups(doc)
        transaction_details = cls.map_transaction_details(doc)

        # Get current timestamp
        current_timestamp = datetime.utcnow().isoformat()

        # Find linked deposit slip
        deposit_slip_name, deposit_slip_doctype = cls.get_linked_deposit_slip(doc)
        has_deposit_slip = deposit_slip_name is not None

        return FundReceivedDTO(
            fundReceivedRefNumberFap=doc.name,
            sanctionNumber=sanction_ref,
            sanctionLetterNo=sanction_letter_no,
            projectNumber=project_number,
            amountReceived=float(getattr(doc, 'fund_received_amt', 0) or 0),
            iitgAccountNumber=getattr(doc, 'bank_account', None) or "",
            depositSlipStatus=has_deposit_slip,
            fundReceivedStatus="PENDING_APPROVAL",
            depositeStatusUpdateTime=current_timestamp,
            fundReceivedStatusUpdateTime=current_timestamp,
            fundBudgetBreakupList=budget_breakups,
            transactionDetailsList=transaction_details
        )

    @classmethod
    def map_to_event(cls, doc) -> FundReceivedEventDTO:
        """
        Map Frappe document to FundReceivedEventDTO (complete Kafka message).

        Args:
            doc: Fund Received Frappe document

        Returns:
            FundReceivedEventDTO: Complete event DTO ready for Kafka
        """
        fund_received_data = cls.map_to_dto(doc)

        return FundReceivedEventDTO(
            schemaVersion=SCHEMA_VERSION_FUND_RECEIVED,
            eventType="FUND_RECEIVED",
            timestamp=datetime.utcnow().isoformat(),
            data=fund_received_data
        )
