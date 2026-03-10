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
        Handles field name differences between DocTypes.
        """
        try:
            # Map DTO fields to DocType-specific field names
            # Default to Research Deposit Slip names
            f_map = {
                'amount': 'total_amount',
                'overhead': 'overhead_amount',
                'balance': 'project_account_balance',
                'gst': None, # Not present in Research DS
                'ecs': 'account_number',
                'bank': 'bank_name',
                'bmr': 'bmr_number', # Assuming this field might exist or will be added
                'cgst': None,
                'sgst': None,
                'ref': 'fund_received_ref'
            }

            if doctype == "Research Consultancy Deposit Slip":
                f_map.update({
                    'amount': 'amount_inclusive_gst_capital',
                    'overhead': 'overhead_amount',
                    'balance': 'project_balance_after_gst',
                    'gst': 'total_gst',
                    'ecs': 'ecs_ac_no',
                    'bank': 'bank',
                    'cgst': 'cgst_9',
                    'sgst': 'sgst_9',
                    'ref': 'fund_received_ref'
                })

            # Update amount fields
            if dto.amountReceived and f_map['amount']:
                frappe.db.set_value(doctype, doc_name, f_map['amount'], dto.amountReceived)

            if dto.totalOverheadAmount and f_map['overhead']:
                frappe.db.set_value(doctype, doc_name, f_map['overhead'], dto.totalOverheadAmount)

            if dto.netProjectAmount and f_map['balance']:
                frappe.db.set_value(doctype, doc_name, f_map['balance'], dto.netProjectAmount)

            if dto.finalGstAmount and f_map['gst']:
                frappe.db.set_value(doctype, doc_name, f_map['gst'], dto.finalGstAmount)

            # Update bank info
            if dto.ecsAccountNo and f_map['ecs']:
                frappe.db.set_value(doctype, doc_name, f_map['ecs'], dto.ecsAccountNo)

            if dto.bankName and f_map['bank']:
                frappe.db.set_value(doctype, doc_name, f_map['bank'], dto.bankName)

            if dto.bmrNumber and f_map.get('bmr'):
                # Only set if field exists to avoid errors on DocTypes without it
                if frappe.get_meta(doctype).has_field(f_map['bmr']):
                     frappe.db.set_value(doctype, doc_name, f_map['bmr'], dto.bmrNumber)

            # Update GST details
            if dto.gstDetails:
                if dto.gstDetails.cgstAmount and f_map['cgst']:
                    frappe.db.set_value(doctype, doc_name, f_map['cgst'], dto.gstDetails.cgstAmount)
                if dto.gstDetails.sgstAmount and f_map['sgst']:
                    frappe.db.set_value(doctype, doc_name, f_map['sgst'], dto.gstDetails.sgstAmount)

            # Update fund received ref number
            if dto.fundReceivedRefNumber and f_map['ref']:
                frappe.db.set_value(doctype, doc_name, f_map['ref'], dto.fundReceivedRefNumber)

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
        Handles field name differences.
        """
        try:
            # Field mapping
            # Default to Research Deposit Slip
            f_map = {
                'swf': 'staff_welfare_amount', # Exists in both?
                # Research: staff_welfare_amount (field 143) - YES
                # Consultancy: staff_welfare_amount (field 179) - YES

                'idf': 'idf_amount',
                # Research: idf_amount (field 124) - YES
                # Consultancy: idf_amount (field 167) - YES

                'stwf': 'student_welfare_fund' # Research fieldname
            }

            if doctype == "Research Consultancy Deposit Slip":
                f_map['stwf'] = 'student_welfare_amount'

            # Update static fields using typed DTOs
            if dto.creditDistributionSwf:
                swf_amount = dto.creditDistributionSwf.swfAmount
                if swf_amount and f_map['swf']:
                    frappe.db.set_value(doctype, doc_name, f_map['swf'], swf_amount)

            if dto.creditDistributionIdf:
                idf_amount = dto.creditDistributionIdf.idfAmount
                if idf_amount and f_map['idf']:
                    frappe.db.set_value(doctype, doc_name, f_map['idf'], idf_amount)

            if dto.creditDistributionStwf:
                stwf_amount = dto.creditDistributionStwf.stwfAmount
                if stwf_amount and f_map['stwf']:
                    frappe.db.set_value(doctype, doc_name, f_map['stwf'], stwf_amount)

            return True

        except Exception as e:
            frappe.log_error(
                f"Error updating credit distributions for {doctype} {doc_name}: {str(e)}",
                "Research Deposit Slip Consumer Credit Distribution Error"
            )
            return False
