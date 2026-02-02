# Copyright (c) 2025, rndops and contributors
# Validator for Consultancy Deposit Slip DTO
# Supports: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT

from typing import List
import frappe
from .dto import ConsultancyDepositSlipDTO


class ValidationError(Exception):
    """Custom validation error"""
    pass


class ConsultancyDepositSlipValidator:
    """
    Validator for Consultancy Deposit Slip DTO.
    Ensures data integrity before sending to Kafka.
    """

    VALID_CATEGORIES = ["CONSULTANCY_D", "CONSULTANCY_E", "CONSULTANCY_T", "OTHER_EVENT"]

    @staticmethod
    def validate_required_fields(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate required fields in ConsultancyDepositSlipDTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not dto.depositSlipRefNumFab or not dto.depositSlipRefNumFab.strip():
            errors.append("depositSlipRefNumFab is required")

        if not dto.slipNumber or not dto.slipNumber.strip():
            errors.append("slipNumber is required")

        if dto.category not in ConsultancyDepositSlipValidator.VALID_CATEGORIES:
            errors.append(f"category must be one of: {ConsultancyDepositSlipValidator.VALID_CATEGORIES}")

        if not dto.gstType or dto.gstType not in ["NOGST", "CGST_SGST", "IGST"]:
            errors.append("gstType must be 'NOGST', 'CGST_SGST', or 'IGST'")

        if not dto.status or not dto.status.strip():
            errors.append("status is required")

        if not dto.createdBy or not dto.createdBy.strip():
            errors.append("createdBy is required")

        if not dto.updatedBy or not dto.updatedBy.strip():
            errors.append("updatedBy is required")

        if not dto.depositDate or not dto.depositDate.strip():
            errors.append("depositDate is required")

        if not dto.createdAt or not dto.createdAt.strip():
            errors.append("createdAt is required")

        if not dto.updatedAt or not dto.updatedAt.strip():
            errors.append("updatedAt is required")

        return errors

    @staticmethod
    def validate_numeric_fields(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate numeric fields are non-negative.

        Args:
            dto: ConsultancyDepositSlipDTO instance

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
    def validate_gst_details(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate GST details consistency.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.gstType == "NOGST":
            return errors

        if not dto.gstDetails:
            if dto.finalGstAmount > 0:
                errors.append("gstDetails required when finalGstAmount > 0")
            return errors

        gst = dto.gstDetails

        if dto.gstType == "CGST_SGST":
            if not gst.cgstAmount or gst.cgstAmount <= 0:
                errors.append("cgstAmount is required for CGST_SGST type")
            if not gst.sgstAmount or gst.sgstAmount <= 0:
                errors.append("sgstAmount is required for CGST_SGST type")

        elif dto.gstType == "IGST":
            if not gst.igstAmount or gst.igstAmount <= 0:
                errors.append("igstAmount is required for IGST type")

        return errors

    @staticmethod
    def validate_credit_distributions(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate credit distribution details.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.creditDistributionPdf:
            for idx, pdf in enumerate(dto.creditDistributionPdf):
                if pdf.pdfAmount < 0:
                    errors.append(f"creditDistributionPdf[{idx}].pdfAmount cannot be negative")
                if pdf.pdfPercentage < 0 or pdf.pdfPercentage > 100:
                    errors.append(f"creditDistributionPdf[{idx}].pdfPercentage must be between 0 and 100")

        if dto.creditDistributionDpf:
            for idx, dpf in enumerate(dto.creditDistributionDpf):
                if dpf.dpfAmount < 0:
                    errors.append(f"creditDistributionDpf[{idx}].dpfAmount cannot be negative")
                if dpf.dpfPercentage < 0 or dpf.dpfPercentage > 100:
                    errors.append(f"creditDistributionDpf[{idx}].dpfPercentage must be between 0 and 100")

        if dto.creditDistributionSwf:
            if dto.creditDistributionSwf.swfAmount < 0:
                errors.append("creditDistributionSwf.swfAmount cannot be negative")

        if dto.creditDistributionIdf:
            if dto.creditDistributionIdf.idfAmount < 0:
                errors.append("creditDistributionIdf.idfAmount cannot be negative")

        if dto.creditDistributionStwf:
            if dto.creditDistributionStwf.stwfAmount < 0:
                errors.append("creditDistributionStwf.stwfAmount cannot be negative")

        return errors

    @staticmethod
    def validate_consultancy_d_details(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate Consultancy D specific details.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.category != "CONSULTANCY_D":
            return errors

        if not dto.consultancyDDetails:
            errors.append("consultancyDDetails is required for CONSULTANCY_D category")
            return errors

        cd = dto.consultancyDDetails

        if cd.gstTdsAmount < 0:
            errors.append("consultancyDDetails.gstTdsAmount cannot be negative")
        if cd.amountReceivedAfterGstTds < 0:
            errors.append("consultancyDDetails.amountReceivedAfterGstTds cannot be negative")
        if cd.totalCostX < 0:
            errors.append("consultancyDDetails.totalCostX cannot be negative")
        if cd.consultancyChargeY < 0:
            errors.append("consultancyDDetails.consultancyChargeY cannot be negative")
        if cd.operationalChargeZ < 0:
            errors.append("consultancyDDetails.operationalChargeZ cannot be negative")
        if cd.overHeadYAmount < 0:
            errors.append("consultancyDDetails.overHeadYAmount cannot be negative")
        if cd.overHeadZAmount < 0:
            errors.append("consultancyDDetails.overHeadZAmount cannot be negative")
        if cd.instituteShare < 0:
            errors.append("consultancyDDetails.instituteShare cannot be negative")
        if cd.totalOverHeadInstituteShare < 0:
            errors.append("consultancyDDetails.totalOverHeadInstituteShare cannot be negative")

        return errors

    @staticmethod
    def validate_consultancy_e_details(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate Consultancy E specific details.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.category != "CONSULTANCY_E":
            return errors

        if not dto.consultancyEDetails:
            errors.append("consultancyEDetails is required for CONSULTANCY_E category")
        elif dto.consultancyEDetails.consultancyFeeX_trainingFee < 0:
            errors.append("consultancyEDetails.consultancyFeeX_trainingFee cannot be negative")

        return errors

    @staticmethod
    def validate_consultancy_t_details(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate Consultancy T specific details.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.category != "CONSULTANCY_T":
            return errors

        if not dto.consultancyTDetails:
            errors.append("consultancyTDetails is required for CONSULTANCY_T category")
        elif dto.consultancyTDetails.consultancyFeeX_trainingFee < 0:
            errors.append("consultancyTDetails.consultancyFeeX_trainingFee cannot be negative")

        return errors

    @staticmethod
    def validate_consultancy_o_details(dto: ConsultancyDepositSlipDTO) -> List[str]:
        """
        Validate Other Event specific details.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.category != "OTHER_EVENT":
            return errors

        if not dto.consultancyODetails:
            errors.append("consultancyODetails is required for OTHER_EVENT category")
        elif dto.consultancyODetails.consultancyFeeX_trainingFee < 0:
            errors.append("consultancyODetails.consultancyFeeX_trainingFee cannot be negative")

        return errors

    @classmethod
    def validate(cls, dto: ConsultancyDepositSlipDTO, raise_exception: bool = True) -> List[str]:
        """
        Perform complete validation on ConsultancyDepositSlipDTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance to validate
            raise_exception: If True, raises ValidationError on validation failure

        Returns:
            List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        all_errors = []

        all_errors.extend(cls.validate_required_fields(dto))
        all_errors.extend(cls.validate_numeric_fields(dto))
        all_errors.extend(cls.validate_gst_details(dto))
        all_errors.extend(cls.validate_credit_distributions(dto))
        all_errors.extend(cls.validate_consultancy_d_details(dto))
        all_errors.extend(cls.validate_consultancy_e_details(dto))
        all_errors.extend(cls.validate_consultancy_t_details(dto))
        all_errors.extend(cls.validate_consultancy_o_details(dto))

        if all_errors and raise_exception:
            error_message = "Consultancy Deposit Slip DTO Validation Failed:\n" + "\n".join([f"  - {err}" for err in all_errors])
            frappe.log_error(error_message, "Consultancy Deposit Slip DTO Validation Error")
            raise ValidationError(error_message)

        return all_errors

    @staticmethod
    def validate_and_log(dto: ConsultancyDepositSlipDTO) -> bool:
        """
        Validate DTO and log errors without raising exception.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            bool: True if valid, False if validation errors exist
        """
        try:
            errors = ConsultancyDepositSlipValidator.validate(dto, raise_exception=False)
            if errors:
                error_message = "Consultancy Deposit Slip DTO Validation Failed:\n" + "\n".join([f"  - {err}" for err in errors])
                frappe.log_error(error_message, "Consultancy Deposit Slip DTO Validation Error")
                print(f"[ERROR] [VALIDATION] {error_message}")
                return False
            return True
        except Exception as e:
            frappe.log_error(str(e), "Consultancy Deposit Slip Validation Exception")
            print(f"[ERROR] [VALIDATION] Unexpected error: {str(e)}")
            return False
