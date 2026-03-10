# Copyright (c) 2025, rndops and contributors
# Consultancy Deposit Slip Consumer Mapper

import frappe
from typing import Optional, Tuple

from .dto import ConsultancyDepositSlipUpdateDTO


# Category to Doctype mapping
CATEGORY_DOCTYPE_MAP = {
    "CONSULTANCY_D": "D Consultancy Deposit Slip",
    "CONSULTANCY_E": "E Non Routine Deposit Slip",
    "CONSULTANCY_T": "T Testing Deposit Slip",
    "OTHER_EVENT": "Other Event Deposit Slip",
}


class ConsultancyDepositSlipConsumerMapper:
    """
    Maps Consultancy Deposit Slip Update DTO to Frappe document updates.
    Handles D, E, T, and Other Event doctypes.
    """

    @classmethod
    def get_doctype_for_category(cls, category: str) -> str:
        """Get Frappe doctype for category."""
        return CATEGORY_DOCTYPE_MAP.get(category, "D Consultancy Deposit Slip")

    @classmethod
    def find_document(cls, dto: ConsultancyDepositSlipUpdateDTO) -> Tuple[Optional[str], Optional[str]]:
        """
        Find Consultancy Deposit Slip document.

        Args:
            dto: ConsultancyDepositSlipUpdateDTO with identifiers

        Returns:
            tuple: (doc_name, doctype) or (None, None)
        """
        # Get expected doctype based on category
        expected_doctype = cls.get_doctype_for_category(dto.category)

        # Primary lookup by depositSlipRefNumFab in expected doctype
        if dto.depositSlipRefNumFab:
            if frappe.db.exists(expected_doctype, dto.depositSlipRefNumFab):
                return dto.depositSlipRefNumFab, expected_doctype

            # Check all consultancy doctypes
            for cat, doctype in CATEGORY_DOCTYPE_MAP.items():
                if frappe.db.exists(doctype, dto.depositSlipRefNumFab):
                    return dto.depositSlipRefNumFab, doctype

        # Fallback: lookup by slipNumber
        if dto.slipNumber and dto.slipNumber != dto.depositSlipRefNumFab:
            if frappe.db.exists(expected_doctype, dto.slipNumber):
                return dto.slipNumber, expected_doctype

        return None, None

    @classmethod
    def apply_updates(cls, doc_name: str, doctype: str, dto: ConsultancyDepositSlipUpdateDTO) -> bool:
        """
        Apply DTO updates to Frappe document.

        Args:
            doc_name: Document name
            doctype: Document type
            dto: ConsultancyDepositSlipUpdateDTO with update data

        Returns:
            bool: True if successful
        """
        try:
            # Update amount fields
            if dto.amountReceived:
                frappe.db.set_value(doctype, doc_name, 'amount_inclusive_of_gst', dto.amountReceived)

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
                if dto.gstDetails.igstAmount:
                    frappe.db.set_value(doctype, doc_name, 'igst_18', dto.gstDetails.igstAmount)

            # Update fund received ref number
            if dto.fundReceivedRefNumber:
                frappe.db.set_value(doctype, doc_name, 'fund_received_ref_number', dto.fundReceivedRefNumber)

            return True

        except Exception as e:
            frappe.log_error(
                f"Error applying updates to {doctype} {doc_name}: {str(e)}",
                "Consultancy Deposit Slip Consumer Mapper Error"
            )
            return False

    @classmethod
    def update_credit_distributions(cls, doc_name: str, doctype: str, dto: ConsultancyDepositSlipUpdateDTO) -> bool:
        """
        Update credit distribution fields.

        Args:
            doc_name: Document name
            doctype: Document type
            dto: ConsultancyDepositSlipUpdateDTO with credit distribution data

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
                "Consultancy Deposit Slip Consumer Credit Distribution Error"
            )
            return False
