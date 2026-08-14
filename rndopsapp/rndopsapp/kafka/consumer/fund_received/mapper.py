# Copyright (c) 2025, rndops and contributors
# Fund Received Consumer Mapper - Maps Kafka DTO to Frappe document updates

import frappe
from typing import Optional

from .dto import FundReceivedUpdateDTO

# Dedicated system user (User doctype, enabled=0, login disabled) so
# ledger-driven comments/notifications are attributed to "Account Portal"
# rather than "Administrator" — the consumer runs in a background thread
# under the Administrator session, but this content originates from the
# external ledger, not an actual admin action. Same "Account Portal" label
# already used for the external-portal comments merged into
# api.py::get_project_activity (see DOCTYPE_TO_COMMENT_CATEGORIES there).
ACCOUNT_PORTAL_USER = 'account.portal@rndopsapp.local'


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
                filters = {'prjreg_title': prj_reg_name}
                if frappe.db.has_column('Fund Received', 'sanctioned_letter_no'):
                    filters['sanctioned_letter_no'] = dto.sanctionLetterNo
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
    #
    # Pending Rectification / Pending Reconciliation / Rejected sit at the
    # same priority as PENDING_APPROVAL (2), not higher — they represent the
    # ledger flagging a document sideways out of that stage, not genuine
    # forward progress. That's also what lets a later ledger-sent APPROVED
    # move a document forward past any of these 3 without requiring a manual
    # step first — confirmed against real historical data, where REJECTED
    # was followed by APPROVED directly.
    _STATE_PRIORITY = {
        'Draft':                                                 0,
        'Pending Misc. Staff Approval':                          1,
        'PENDING_APPROVAL':                                      2,
        'Pending Rectification':                                 2,
        'Pending Reconciliation':                                2,
        'Rejected':                                               2,
        'Pending Misc. Staff Approval(Deposit Slip Pending)':    3,
        'Pending HoS Approval':                                  4,
        'Approved':                                              5,
        'Fund Received':                                         6,
    }

    # fundReceivedStatus values the external ledger sends, all mapped to real
    # states in the fund_received_with_kafka Workflow. PENDING_RECONCILIATION /
    # PENDING_RECTIFICATION / REJECTED were added as new workflow states
    # (Pending Reconciliation / Pending Rectification / Rejected) specifically
    # so they're visible in the workflow UI and actionable — Pending
    # Rectification has a staff, RnD-only "Forward" transition back to
    # PENDING_APPROVAL (which re-publishes to Kafka automatically, see
    # perform_fund_received_action's `next_state == "PENDING_APPROVAL"`
    # block). Pending Reconciliation / Rejected are intentionally passive —
    # no new transition — matching how the ledger itself supersedes them.
    _WORKFLOW_MAPPED_STATUSES = {
        'PENDING_APPROVAL', 'PENDING_RECONCILIATION', 'PENDING_RECTIFICATION',
        'APPROVED', 'REJECTED',
    }

    _LEDGER_STATUS_TO_WORKFLOW_STATE = {
        'PENDING_APPROVAL': 'PENDING_APPROVAL',
        'PENDING_RECONCILIATION': 'Pending Reconciliation',
        'PENDING_RECTIFICATION': 'Pending Rectification',
        'REJECTED': 'Rejected',
        # APPROVED handled separately below — it maps to the *next* stage of
        # the approval workflow, not a same-named state.
    }

    @classmethod
    def map_status(cls, kafka_status: Optional[str]) -> Optional[str]:
        """
        Map Kafka status to Frappe workflow state. Returns None for any
        status with no corresponding workflow state (see
        _WORKFLOW_MAPPED_STATUSES) — apply_updates leaves workflow_state
        untouched in that case.

        Args:
            kafka_status: Status from Kafka message

        Returns:
            str or None: Frappe workflow state, or None if not workflow-mapped
        """
        if not kafka_status:
            return None

        status_upper = kafka_status.upper()

        if status_upper not in cls._WORKFLOW_MAPPED_STATUSES:
            return None

        if status_upper == 'APPROVED':
            # External APPROVED → awaiting deposit slip from Misc. Staff
            return 'Pending Misc. Staff Approval(Deposit Slip Pending)'

        return cls._LEDGER_STATUS_TO_WORKFLOW_STATE[status_upper]

    @classmethod
    def update_ledger_status(cls, doc_name: str, dto: FundReceivedUpdateDTO) -> None:
        """
        Records the raw fundReceivedStatus in the `ledger_status` field —
        separate from workflow_state, see _WORKFLOW_MAPPED_STATUSES — and
        notifies the document owner when it changes, so ledger-only statuses
        like PENDING_RECTIFICATION / PENDING_RECONCILIATION / REJECTED are
        visible to users even though they don't move the approval workflow.

        Entirely additive and best-effort: no-ops if the `ledger_status`
        column doesn't exist (same frappe.db.has_column guard used by every
        other field in apply_updates), and never raises — a notification
        failure must not fail the Kafka message.
        """
        if not dto.fundReceivedStatus or not frappe.db.has_column('Fund Received', 'ledger_status'):
            return

        try:
            new_status = dto.fundReceivedStatus.upper()
            previous_status = frappe.db.get_value('Fund Received', doc_name, 'ledger_status')

            if previous_status == new_status:
                return  # unchanged — don't re-notify on a replayed/duplicate message

            frappe.db.set_value(
                'Fund Received', doc_name, 'ledger_status', new_status, update_modified=False
            )
            cls._notify_ledger_status_change(doc_name, previous_status, new_status)
        except Exception:
            frappe.log_error(
                f"Failed to record/notify ledger_status for Fund Received {doc_name}",
                "Fund Received Ledger Status Error",
            )

    @staticmethod
    def _notify_ledger_status_change(doc_name: str, previous_status: Optional[str], new_status: str) -> None:
        """Comment (audit trail, same convention as the existing [Forward]/[Put
        Back] comments on this doctype) + Notification Log (bell-icon alert
        for the document owner). Both best-effort — logged, never raised."""
        extra = {
            'PENDING_APPROVAL': ' This Fund Received is now pending approval at the ledger.',
            'PENDING_RECTIFICATION': ' The external ledger has flagged this Fund Received for correction.',
            'PENDING_RECONCILIATION': ' The external ledger is reconciling this Fund Received against bank records.',
            'REJECTED': ' The external ledger rejected this Fund Received.',
            'APPROVED': ' The external ledger approved this Fund Received.',
        }.get(new_status, '')
        message = (
            f"Ledger status changed to {new_status}"
            + (f" (was {previous_status})" if previous_status else "")
            + "."
            + extra
        )

        try:
            comment = frappe.get_doc({
                'doctype': 'Comment',
                'comment_type': 'Comment',
                'reference_doctype': 'Fund Received',
                'reference_name': doc_name,
                'content': f"[Ledger Status] {message}",
                'owner': ACCOUNT_PORTAL_USER,
            })
            comment.insert(ignore_permissions=True)
            # insert() only pre-fills owner when unset — force it in case a
            # future frappe version starts overwriting an explicitly-set one.
            if comment.owner != ACCOUNT_PORTAL_USER:
                frappe.db.set_value('Comment', comment.name, 'owner', ACCOUNT_PORTAL_USER)
        except Exception:
            frappe.log_error(
                f"Failed to add ledger-status comment on Fund Received {doc_name}",
                "Fund Received Ledger Status Notify Error",
            )

        try:
            owner = frappe.db.get_value('Fund Received', doc_name, 'owner')
            if owner and owner not in ('Administrator', 'Guest'):
                from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
                enqueue_create_notification([owner], {
                    'type': 'Alert',
                    'document_type': 'Fund Received',
                    'document_name': doc_name,
                    'subject': f"Fund Received {doc_name}: {message}",
                    'from_user': ACCOUNT_PORTAL_USER,
                })
        except Exception:
            frappe.log_error(
                f"Failed to notify owner of ledger-status change on Fund Received {doc_name}",
                "Fund Received Ledger Status Notify Error",
            )

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

            # Record the raw ledger status (separate from workflow_state — see
            # _WORKFLOW_MAPPED_STATUSES above) and notify on change. Best-effort:
            # never allowed to fail this whole update.
            cls.update_ledger_status(doc_name, dto)

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
