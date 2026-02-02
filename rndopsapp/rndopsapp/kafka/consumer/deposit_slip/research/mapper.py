# Copyright (c) 2025, rndops and contributors
# Research Deposit Slip Consumer Mapper

import frappe
from typing import Optional

from .dto import ResearchDepositSlipUpdateDTO


class ResearchDepositSlipConsumerMapper:
    """
    Maps Research Deposit Slip Update DTO to Frappe document updates.
    """

    DOCTYPE = "Research Deposit Slip"
    DOCTYPE_ALTERNATIVES = ["Research Consultancy Deposit Slip"]

    @classmethod
    def find_document(cls, dto: ResearchDepositSlipUpdateDTO) -> tuple:
        """
        Find Research Deposit Slip document.

        Args:
            dto: ResearchDepositSlipUpdateDTO with identifiers

        Returns:
            tuple: (doc_name, doctype) or (None, None)
        """
        # Primary lookup by depositSlipRefNumFab
        if dto.depositSlipRefNumFab:
            if frappe.db.exists(cls.DOCTYPE, dto.depositSlipRefNumFab):
                return dto.depositSlipRefNumFab, cls.DOCTYPE

            # Check alternative doctypes
            for alt_doctype in cls.DOCTYPE_ALTERNATIVES:
                if frappe.db.exists(alt_doctype, dto.depositSlipRefNumFab):
                    return dto.depositSlipRefNumFab, alt_doctype

        # Fallback: lookup by slipNumber
        if dto.slipNumber and dto.slipNumber != dto.depositSlipRefNumFab:
            if frappe.db.exists(cls.DOCTYPE, dto.slipNumber):
                return dto.slipNumber, cls.DOCTYPE

        return None, None

    @classmethod
    def apply_updates(cls, doc_name: str, doctype: str, dto: ResearchDepositSlipUpdateDTO) -> bool:
        """
        Apply DTO updates to Frappe document.

        Args:
            doc_name: Document name
            doctype: Document type
            dto: ResearchDepositSlipUpdateDTO with update data

        Returns:
            bool: True if successful
        """
        try:
            # Update amount fields
            if dto.amountReceived:
                frappe.db.set_value(doctype, doc_name, 'amount_inclusive_gst_capital', dto.amountReceived)

            if dto.totalOverheadAmount:
                frappe.db.set_value(doctype, doc_name, 'overhead_amount', dto.totalOverheadAmount)

            if dto.netProjectAmount:
                frappe.db.set_value(doctype, doc_name, 'project_balance_after_gst', dto.netProjectAmount)

            if dto.finalGstAmount:
                frappe.db.set_value(doctype, doc_name, 'total_gst', dto.finalGstAmount)

            # Update bank info
            if dto.ecsAccountNo:
                frappe.db.set_value(doctype, doc_name, 'ecs_ac_no', dto.ecsAccountNo)

            if dto.bankName:
                frappe.db.set_value(doctype, doc_name, 'bank', dto.bankName)

            if dto.bmrNumber:
                frappe.db.set_value(doctype, doc_name, 'bmr_number', dto.bmrNumber)

            # Update GST details (using typed DTO)
            if dto.gstDetails:
                if dto.gstDetails.cgstAmount:
                    frappe.db.set_value(doctype, doc_name, 'cgst_9', dto.gstDetails.cgstAmount)
                if dto.gstDetails.sgstAmount:
                    frappe.db.set_value(doctype, doc_name, 'sgst_9', dto.gstDetails.sgstAmount)

            # Update fund received ref number
            if dto.fundReceivedRefNumber:
                frappe.db.set_value(doctype, doc_name, 'fund_received_ref_number', dto.fundReceivedRefNumber)

            return True

        except Exception as e:
            frappe.log_error(
                f"Error applying updates to {doctype} {doc_name}: {str(e)}",
                "Research Deposit Slip Consumer Mapper Error"
            )
            return False

    @classmethod
    def update_credit_distributions(cls, doc_name: str, doctype: str, dto: ResearchDepositSlipUpdateDTO) -> bool:
        """
        Update credit distribution child table.

        Args:
            doc_name: Document name
            doctype: Document type
            dto: ResearchDepositSlipUpdateDTO with credit distribution data

        Returns:
            bool: True if successful
        """
        try:
            # Update static fields using typed DTOs
            if dto.creditDistributionSwf:
                swf_amount = dto.creditDistributionSwf.swfAmount
                if swf_amount:
                    frappe.db.set_value(doctype, doc_name, 'staff_welfare_amount', swf_amount)

            if dto.creditDistributionIdf:
                idf_amount = dto.creditDistributionIdf.idfAmount
                if idf_amount:
                    frappe.db.set_value(doctype, doc_name, 'idf_amount', idf_amount)

            if dto.creditDistributionStwf:
                stwf_amount = dto.creditDistributionStwf.stwfAmount
                if stwf_amount:
                    frappe.db.set_value(doctype, doc_name, 'student_welfare_amount', stwf_amount)

            return True

        except Exception as e:
            frappe.log_error(
                f"Error updating credit distributions for {doctype} {doc_name}: {str(e)}",
                "Research Deposit Slip Consumer Credit Distribution Error"
            )
            return False
