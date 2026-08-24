# Copyright (c) 2025, rndops and contributors
# Fund Received Consumer Mapper - Maps Kafka DTO to Frappe document updates

import frappe
from typing import Optional

from .dto import FundReceivedUpdateDTO
from ...utils import resolve_budget_head_name


class FundReceivedConsumerMapper:
    """
    Maps Fund Received Update DTO to Frappe document field updates.
    """

    @classmethod
    def find_document(cls, dto: FundReceivedUpdateDTO) -> Optional[str]:
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

        # Fallback: Find by sanction letter and project. prjreg_title is a Link
        # field holding a Project Registration docname, not the raw project
        # number, so resolve project_no -> docname first before filtering on it.
        if dto.sanctionLetterNo and dto.projectNumber:
            prj_reg_name = cls.get_project_registration_name(dto.projectNumber)
            if prj_reg_name:
                filters = {
                    'sanctioned_letter_no': dto.sanctionLetterNo,
                    'prjreg_title': prj_reg_name
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
                 or None if no Project Registration has this project_no (yet).
                 NOTE: prjreg_title is a Link field to Project Registration, so it
                 must only ever be set to a real docname — never to the raw
                 project_number. Callers must skip the update when this returns None
                 rather than falling back to the raw value, which would corrupt the
                 link (see apps/rndopsapp .../kafka/consumer/fund_received/mapper.py
                 history for the bug this guards against).
        """
        if not project_number:
            return None

        # Search Project Registration where project_no matches
        return frappe.db.get_value(
            'Project Registration',
            {'project_no': project_number},
            'name'
        )

    # Ordered workflow states — higher index = further along in the workflow.
    # Source of truth: fund_received_with_kafka workflow (verified from DB).
    # The Kafka consumer must NEVER move a document backward.
    _STATE_PRIORITY = {
        'Draft':                                                 0,
        'Pending Misc. Staff Approval':                          1,
        'PENDING_APPROVAL':                                      2,
        'Pending Misc. Staff Approval(Deposit Slip Pending)':    3,
        'Pending HoS Approval':                                  4,
        'Approved':                                              5,
        'Fund Received':                                         6,
    }

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
            # External APPROVED → awaiting deposit slip from Misc. Staff
            return 'Pending Misc. Staff Approval(Deposit Slip Pending)'
        elif status_upper == 'PENDING_APPROVAL':
            # Kafka intermediate state — matches the actual Frappe workflow state name
            return 'PENDING_APPROVAL'
        else:
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
            if dto.sanctionLetterNo and frappe.db.has_column('Fund Received', 'sanctioned_letter_no'):
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'sanctioned_letter_no', dto.sanctionLetterNo
                )

            # Map and apply project_number → look up Project Registration name.
            # prjreg_title is a Link field: only ever write a real Project
            # Registration docname into it, never the raw project number — if no
            # Project Registration has this project_no yet, skip the update and
            # leave prjreg_title untouched rather than corrupting the link.
            if dto.projectNumber and frappe.db.has_column('Fund Received', 'prjreg_title'):
                prj_reg_name = cls.get_project_registration_name(dto.projectNumber)
                if prj_reg_name:
                    frappe.db.set_value(
                        'Fund Received', doc_name,
                        'prjreg_title', prj_reg_name
                    )
                else:
                    frappe.logger().warning(
                        f"[FundReceivedConsumerMapper] No Project Registration found for "
                        f"project_no='{dto.projectNumber}' — skipped prjreg_title update on "
                        f"{doc_name} to avoid writing an invalid Link value."
                    )

            # Map and apply amount_received
            if dto.amountReceived is not None and frappe.db.has_column('Fund Received', 'fund_received_amt'):
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'fund_received_amt', dto.amountReceived
                )

            # Map and apply bank_account
            if dto.iitgAccountNumber and frappe.db.has_column('Fund Received', 'bank_account'):
                frappe.db.set_value(
                    'Fund Received', doc_name,
                    'bank_account', dto.iitgAccountNumber
                )

            # Map and apply workflow_state — only move FORWARD, never backward.
            # Uses a single conditional SQL UPDATE (atomic check+apply) to avoid
            # a TOCTOU race with the Frappe workflow action handlers: MariaDB MVCC
            # means a plain SELECT reads the transaction snapshot while a separate
            # UPDATE writes to the latest row version, so a Python-level
            # read-then-update can silently overwrite a state that was advanced by
            # another process between the read and the write.
            if frappe.db.has_column('Fund Received', 'workflow_state'):
                new_status = cls.map_status(dto.fundReceivedStatus)
                if new_status:
                    new_priority = cls._STATE_PRIORITY.get(new_status, 0)

                    # Build list of states whose priority is <= new_priority
                    # (the only states from which this transition is allowed).
                    allowed_from_states = [
                        state for state, pri in cls._STATE_PRIORITY.items()
                        if pri <= new_priority
                    ]

                    if not allowed_from_states:
                        frappe.logger().warning(
                            f"[FundReceivedConsumerMapper] No allowed-from states for "
                            f"{doc_name}: target='{new_status}' (priority {new_priority}), skipped."
                        )
                    else:
                        # Single atomic UPDATE: only applies when current state is
                        # in the allowed set, preventing any backward movement even
                        # under concurrent requests.
                        placeholders = ', '.join(['%s'] * len(allowed_from_states))
                        rows_affected = frappe.db.sql(
                            f"""
                            UPDATE `tabFund Received`
                            SET workflow_state = %s,
                                modified = NOW()
                            WHERE name = %s
                              AND workflow_state IN ({placeholders})
                            """,
                            [new_status, doc_name] + allowed_from_states,
                        )
                        if not rows_affected:
                            # Read current state only for the warning log
                            current_status = frappe.db.get_value(
                                'Fund Received', doc_name, 'workflow_state'
                            ) or ''
                            frappe.logger().warning(
                                f"[FundReceivedConsumerMapper] Skipped backward state change for "
                                f"{doc_name}: current='{current_status}' "
                                f"→ '{new_status}' (priority {new_priority}) ignored."
                            )

            # Map and apply fund_received_ref_number
            if dto.fundReceivedRefNumber is not None and frappe.db.has_column('Fund Received', 'fund_received_ref_number'):
                try:
                    frappe.db.set_value(
                        'Fund Received', doc_name,
                        'fund_received_ref_number', int(dto.fundReceivedRefNumber)
                    )
                except (ValueError, TypeError):
                    frappe.db.set_value(
                        'Fund Received', doc_name,
                        'fund_received_ref_number', dto.fundReceivedRefNumber
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
                # account_head is a Link to Budget Head — it must hold the
                # Budget Head DOCNAME, never the raw incoming accountHeadId.
                # Writing the numeric id here corrupts the link the same way
                # the prjreg_title bug did (see get_project_registration_name
                # above): get_budget_head_id() then can't resolve it, and the
                # next outbound publish emits accountHeadId: null for the row.
                raw_head = item.accountHeadId or item.accountHead
                resolved_head = resolve_budget_head_name(raw_head)
                if not resolved_head:
                    frappe.logger().warning(
                        f"[FundReceivedConsumerMapper] Could not resolve Budget Head "
                        f"'{raw_head}' for {doc_name} — storing raw value."
                    )
                child_doc.account_head = resolved_head or raw_head
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
