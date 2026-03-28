# Copyright (c) 2025, rndops and contributors
# Fund Received Consumer Mapper - Maps Kafka DTO to Frappe document updates

import frappe
from typing import Optional

from .dto import FundReceivedUpdateDTO


class FundReceivedConsumerMapper:
    """
    Maps Fund Received Update DTO to Frappe document field updates.
    """

    @staticmethod
    def find_document(dto: FundReceivedUpdateDTO) -> Optional[str]:
        """
        Find Fund Received document by various identifiers.

        Args:
            dto: FundReceivedUpdateDTO with identifiers

        Returns:
            str or None: Document name if found
        """
        # Primary lookup by FAP reference number
        if dto.fundReceivedRefNumberFap:
            if frappe.db.exists('Fund Received', dto.fundReceivedRefNumberFap):
                return dto.fundReceivedRefNumberFap

        # Fallback: Lookup by reference number
        if dto.fundReceivedRefNumber:
            ref_num_str = str(dto.fundReceivedRefNumber)
            if frappe.db.exists('Fund Received', ref_num_str):
                return ref_num_str

        # Fallback: Find by sanction letter and project
        if dto.sanctionLetterNo and dto.projectNumber:
            filters = {
                'sanctioned_letter_no': dto.sanctionLetterNo,
                'prjreg_title': dto.projectNumber
            }
            found_name = frappe.db.get_value('Fund Received', filters, 'name')
            if found_name:
                return found_name

        return None

    @staticmethod
    def get_project_registration_name(project_number: str) -> Optional[str]:
        """
        Look up the Project Registration document name from project_no field.

        Args:
            project_number: The project_no value (e.g. '26RBSBESP0391LSAH0015')

        Returns:
            str: Project Registration document name (e.g. '2026032701DST000704'),
                 or the original project_number if not found.
        """
        if not project_number:
            return project_number

        # Search Project Registration where project_no matches
        prj_name = frappe.db.get_value(
            'Project Registration',
            {'project_no': project_number},
            'name'
        )

        if prj_name:
            return prj_name

        # Fallback: return original project_number if no match found
        return project_number

    @staticmethod
    def map_status(kafka_status: Optional[str]) -> Optional[str]:
        """
        Map Kafka status to Frappe workflow state.

        Args:
            kafka_status: Status from Kafka message

        Returns:
            str: Frappe workflow state
        """
        if not kafka_status:
            return None

        status_upper = kafka_status.upper()

        if status_upper == 'APPROVED':
            return 'Pending Misc. Staff Approval(Deposit Slip Pending)'
        elif status_upper == 'PENDING_APPROVAL':
            return 'Pending Approval'
        elif status_upper == 'REJECTED':
            return 'Rejected'
        else:
            # Default: Title case the status
            return kafka_status.title()

    @classmethod
    def apply_updates(cls, doc_name: str, dto: FundReceivedUpdateDTO) -> bool:
        """
        Apply DTO updates to Frappe document using direct DB updates.

        Args:
            doc_name: Fund Received document name
            dto: FundReceivedUpdateDTO with update data

        Returns:
            bool: True if successful
        """
        try:
            # Map and apply sanction_letter_no
            if dto.sanctionLetterNo:
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'sanctioned_letter_no', dto.sanctionLetterNo
                )

            # Map and apply project_number → look up Project Registration name
            if dto.projectNumber:
                prj_reg_name = cls.get_project_registration_name(dto.projectNumber)
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'prjreg_title', prj_reg_name
                )

            # Map and apply amount_received
            if dto.amountReceived is not None:
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'fund_received_amt', dto.amountReceived
                )

            # Map and apply bank_account
            if dto.iitgAccountNumber:
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'bank_account', dto.iitgAccountNumber
                )

            # Map and apply workflow_state
            new_status = cls.map_status(dto.fundReceivedStatus)
            if new_status:
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'workflow_state', new_status
                )

            # Map and apply fund_received_ref_number
            if dto.fundReceivedRefNumber is not None:
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'fund_received_ref_number', int(dto.fundReceivedRefNumber)
                )

            return True

        except Exception as e:
            frappe.log_error(
                f"Error applying updates to Fund Received {doc_name}: {str(e)}",
                "Fund Received Consumer Mapper Error"
            )
            return False

    @classmethod
    def update_budget_breakup(cls, doc_name: str, dto: FundReceivedUpdateDTO) -> bool:
        """
        Update Fund Budget Breakup child table.

        Args:
            doc_name: Fund Received document name
            dto: FundReceivedUpdateDTO with budget breakup data

        Returns:
            bool: True if successful
        """
        if not dto.fundBudgetBreakupList:
            return True

        try:
            child_doctype = 'Project Received Budget'
            parent_field = 'received_amt_breakup'

            # Clear existing items
            frappe.db.delete(child_doctype, {'parent': doc_name})

            # Add new items
            for idx, item in enumerate(dto.fundBudgetBreakupList, start=1):
                child_doc = frappe.new_doc(child_doctype)
                child_doc.parent = doc_name
                child_doc.parenttype = 'Fund Received'
                child_doc.parentfield = parent_field
                child_doc.idx = idx
                child_doc.account_head = item.accountHeadId or item.accountHead
                child_doc.amount_received = item.amount
                child_doc.remarks = item.remarks
                child_doc.db_insert()

            return True

        except Exception as e:
            frappe.log_error(
                f"Error updating budget breakup for {doc_name}: {str(e)}",
                "Fund Received Consumer Budget Error"
            )
            return False

    @classmethod
    def update_transaction_details(cls, doc_name: str, dto: FundReceivedUpdateDTO) -> bool:
        """
        Update Transaction Details child table.

        Args:
            doc_name: Fund Received document name
            dto: FundReceivedUpdateDTO with transaction data

        Returns:
            bool: True if successful
        """
        if not dto.transactionDetailsList:
            return True

        try:
            child_doctype = 'Project Fund Transaction'
            parent_field = 'fund_transactions'

            # Clear existing items
            frappe.db.delete(child_doctype, {'parent': doc_name})

            # Add new items
            for idx, item in enumerate(dto.transactionDetailsList, start=1):
                child_doc = frappe.new_doc(child_doctype)
                child_doc.parent = doc_name
                child_doc.parenttype = 'Fund Received'
                child_doc.parentfield = parent_field
                child_doc.idx = idx
                child_doc.transaction_number = item.uniqueTransactionNumber
                child_doc.transaction_date = item.transactionReceivedDate
                child_doc.amount = item.transactionAmount
                child_doc.db_insert()

            return True

        except Exception as e:
            frappe.log_error(
                f"Error updating transaction details for {doc_name}: {str(e)}",
                "Fund Received Consumer Transaction Error"
            )
            return False
