# Copyright (c) 2025, rndops and contributors
# Validator for Research Deposit Slip DTO

from typing import List
import frappe
from .dto import ResearchDepositSlipDTO


class ValidationError(Exception):
    """Custom validation error"""
    pass


class ResearchDepositSlipValidator:
    """
    Validator for Research Deposit Slip DTO.
    Ensures data integrity before sending to Kafka.
    """

    @staticmethod
    def validate_required_fields(dto: ResearchDepositSlipDTO) -> List[str]:
        """
        Validate required fields in ResearchDepositSlipDTO.

        Args:
            dto: ResearchDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Required string fields
        if not dto.projectNumber or not dto.projectNumber.strip():
            errors.append("projectNumber is required")

        if not dto.depositSlipRefNumFab or not dto.depositSlipRefNumFab.strip():
            errors.append("depositSlipRefNumFab is required")

        if not dto.slipNumber or not dto.slipNumber.strip():
            errors.append("slipNumber is required")

        if dto.category != "RESEARCH":
            errors.append("category must be 'RESEARCH' for Research Deposit Slip")

        if not dto.gstType or dto.gstType not in ["NOGST", "CGST_SGST", "IGST"]:
            errors.append("gstType must be 'NOGST', 'CGST_SGST', or 'IGST'")

        if not dto.status or not dto.status.strip():
            errors.append("status is required")

        if not dto.createdBy or not dto.createdBy.strip():
            errors.append("createdBy is required")

        if not dto.updatedBy or not dto.updatedBy.strip():
            errors.append("updatedBy is required")

        # Date fields
        if not dto.depositDate or not dto.depositDate.strip():
            errors.append("depositDate is required")

        if not dto.createdAt or not dto.createdAt.strip():
            errors.append("createdAt is required")

        if not dto.updatedAt or not dto.updatedAt.strip():
            errors.append("updatedAt is required")

        return errors

    @staticmethod
    def validate_numeric_fields(dto: ResearchDepositSlipDTO) -> List[str]:
        """
        Validate numeric fields are non-negative.

        Args:
            dto: ResearchDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.amountReceived < 0:
            errors.append("amountReceived cannot be negative")

        if dto.amountInclusiveGst < 0:
            errors.append("amountInclusiveGst cannot be negative")

        if dto.finalGstAmount < 0:
            errors.append("finalGstAmount cannot be negative")

        if dto.finalTotalAmount < 0:
            errors.append("finalTotalAmount cannot be negative")

        if dto.totalOverheadAmount < 0:
            errors.append("totalOverheadAmount cannot be negative")

        if dto.netProjectAmount < 0:
            errors.append("netProjectAmount cannot be negative")

        if dto.totalOverheadPercentage < 0 or dto.totalOverheadPercentage > 100:
            errors.append("totalOverheadPercentage must be between 0 and 100")

        return errors

    @staticmethod
    def validate_credit_distributions(dto: ResearchDepositSlipDTO) -> List[str]:
        """
        Validate credit distribution details.

        Args:
            dto: ResearchDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Validate PDF (Principal Development Fund)
        if dto.creditDistributionPdf:
            for idx, pdf in enumerate(dto.creditDistributionPdf):
                if pdf.pdfAmount < 0:
                    errors.append(f"creditDistributionPdf[{idx}].pdfAmount cannot be negative")
                if pdf.pdfPercentage < 0 or pdf.pdfPercentage > 100:
                    errors.append(f"creditDistributionPdf[{idx}].pdfPercentage must be between 0 and 100")

        # Validate DPF (Departmental Fund)
        if dto.creditDistributionDpf:
            for idx, dpf in enumerate(dto.creditDistributionDpf):
                if dpf.dpfAmount < 0:
                    errors.append(f"creditDistributionDpf[{idx}].dpfAmount cannot be negative")
                if dpf.dpfPercentage < 0 or dpf.dpfPercentage > 100:
                    errors.append(f"creditDistributionDpf[{idx}].dpfPercentage must be between 0 and 100")

        # Validate SWF (Staff Welfare Fund)
        if dto.creditDistributionSwf:
            if dto.creditDistributionSwf.swfAmount < 0:
                errors.append("creditDistributionSwf.swfAmount cannot be negative")
            if dto.creditDistributionSwf.swfPercentage < 0 or dto.creditDistributionSwf.swfPercentage > 100:
                errors.append("creditDistributionSwf.swfPercentage must be between 0 and 100")

        # Validate IDF (Infrastructure Development Fund)
        if dto.creditDistributionIdf:
            if dto.creditDistributionIdf.idfAmount < 0:
                errors.append("creditDistributionIdf.idfAmount cannot be negative")
            if dto.creditDistributionIdf.idfPercentage < 0 or dto.creditDistributionIdf.idfPercentage > 100:
                errors.append("creditDistributionIdf.idfPercentage must be between 0 and 100")

        # Validate STWF (Student Welfare Fund)
        if dto.creditDistributionStwf:
            if dto.creditDistributionStwf.stwfAmount < 0:
                errors.append("creditDistributionStwf.stwfAmount cannot be negative")
            if dto.creditDistributionStwf.stwfPercentage < 0 or dto.creditDistributionStwf.stwfPercentage > 100:
                errors.append("creditDistributionStwf.stwfPercentage must be between 0 and 100")

        return errors

    @classmethod
    def validate(cls, dto: ResearchDepositSlipDTO, raise_exception: bool = True) -> List[str]:
        """
        Perform complete validation on ResearchDepositSlipDTO.

        Args:
            dto: ResearchDepositSlipDTO instance to validate
            raise_exception: If True, raises ValidationError on validation failure

        Returns:
            List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        all_errors = []

        all_errors.extend(cls.validate_required_fields(dto))
        all_errors.extend(cls.validate_numeric_fields(dto))
        all_errors.extend(cls.validate_credit_distributions(dto))

        if all_errors and raise_exception:
            error_message = "Research Deposit Slip DTO Validation Failed:\n" + "\n".join([f"  - {err}" for err in all_errors])
            frappe.log_error(error_message, "Research Deposit Slip DTO Validation Error")
            raise ValidationError(error_message)

        return all_errors

    @staticmethod
    def validate_and_log(dto: ResearchDepositSlipDTO) -> bool:
        """
        Validate DTO and log errors without raising exception.

        Args:
            dto: ResearchDepositSlipDTO instance

        Returns:
            bool: True if valid, False if validation errors exist
        """
        try:
            errors = ResearchDepositSlipValidator.validate(dto, raise_exception=False)
            if errors:
                error_message = "Research Deposit Slip DTO Validation Failed:\n" + "\n".join([f"  - {err}" for err in errors])
                frappe.log_error(error_message, "Research Deposit Slip DTO Validation Error")
                print(f"[ERROR] [VALIDATION] {error_message}")
                return False
            return True
        except Exception as e:
            frappe.log_error(str(e), "Research Deposit Slip Validation Exception")
            print(f"[ERROR] [VALIDATION] Unexpected error: {str(e)}")
            return False
