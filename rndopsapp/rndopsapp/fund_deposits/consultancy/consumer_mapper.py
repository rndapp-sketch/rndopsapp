# Copyright (c) 2025, rndops and contributors
# Consumer Mapper for Consultancy Deposit Slip Updates

from typing import Dict, List, Any, Optional
from .dto import ConsultancyDepositSlipDTO


class ConsultancyDoctypeConfig:
    """
    Configuration for different Consultancy Deposit Slip doctypes.
    """

    # Category to Doctype mapping
    CATEGORY_DOCTYPE_MAP = {
        "CONSULTANCY_D": "D Consultancy Deposit Slip",
        "CONSULTANCY_E": "E Non Routine Deposit Slip",
        "CONSULTANCY_T": "T Testing Deposit Slip",
        "OTHER_EVENT": "Other Event Deposit Slip",
    }

    # Default child table doctypes (can vary by parent doctype)
    DEFAULT_CONFIG = {
        "ecs_dates_child": "Deposit Slip ECS Date",
        "credit_dist_child": "Deposit Slip Credit Distribution",
    }

    @classmethod
    def get_doctype(cls, category: str) -> str:
        """
        Get doctype name for given category.

        Args:
            category: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT

        Returns:
            str: DocType name
        """
        return cls.CATEGORY_DOCTYPE_MAP.get(category, "D Consultancy Deposit Slip")

    @classmethod
    def get_config(cls, category: str) -> Dict[str, str]:
        """
        Get doctype configuration based on category.

        Args:
            category: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT

        Returns:
            dict: Configuration for the doctype
        """
        return {
            "doctype": cls.get_doctype(category),
            **cls.DEFAULT_CONFIG
        }


class ConsultancyDepositSlipConsumerMapper:
    """
    Maps ConsultancyDepositSlipDTO fields to Frappe document field updates.
    """

    # Base field mapping (common across all consultancy types)
    DEFAULT_FIELD_MAPPING = {
        # Basic fields
        "projectNumber": "project_number",
        "fundReceivedRefNumber": "fund_received_ref_number",
        "depositSlipRefNumFab": "name",  # Primary key (read-only)
        "slipNumber": "slip_number",
        "ecsAccountNo": "ecs_ac_no",
        "bankName": "bank",
        "bmrNumber": "bmr_number",

        # Amount fields
        "amountReceived": "amount_received",
        "amountInclusiveGst": "amount_inclusive_of_gst",
        "finalGstAmount": "total_gst",
        "finalTotalAmount": "total_amount",
        "totalOverheadPercentage": "overhead_percentage",
        "totalOverheadAmount": "total_overhead_amount",
        "netProjectAmount": "project_balance_after_gst",

        # GST type
        "gstType": "gst_type",

        # Dates
        "depositDate": "deposit_date",
        "createdAt": "created_at",
        "updatedAt": "updated_at",
        "createdBy": "created_by",
        "updatedBy": "updated_by",

        # Status -> workflow_state
        "status": "workflow_state",
    }

    # GST Details field mapping
    GST_DETAILS_MAPPING = {
        "cgstPercentage": "cgst_percentage",
        "cgstAmount": "cgst_9",
        "sgstPercentage": "sgst_percentage",
        "sgstAmount": "sgst_9",
        "igstPercentage": "igst_percentage",
        "igstAmount": "igst_18",
        "totalGstAmount": "total_gst",
    }

    # D Consultancy specific fields
    CONSULTANCY_D_DETAILS_MAPPING = {
        "gstTdsPercentage": "gst_tds_percentage",
        "gstTdsAmount": "gst_tds_amount",
        "amountReceivedAfterGstTds": "amount_after_gst_tds",
        "totalCostX": "total_cost_x",
        "consultancyChargeYPercentage": "consultancy_charge_y_percentage",
        "consultancyChargeY": "consultancy_charge_y",
        "operationalChargeZPercentage": "operational_charge_z_percentage",
        "operationalChargeZ": "operational_charge_z",
        "overHeadYPercentage": "overhead_from_y_multiplier",
        "overHeadYAmount": "overhead_from_y_amount",
        "overHeadZPercentage": "overhead_from_z_multiplier",
        "overHeadZAmount": "overhead_from_z_amount",
        "instituteSharePercentage": "institute_share_multiplier",
        "instituteShare": "institute_share_amount",
        "totalOverHeadInstituteShare": "total_overhead_institute_share",
    }

    # Credit distribution field mappings
    CREDIT_DIST_SWF_MAPPING = {
        "swfPercentage": "staff_welfare_percentage",
        "swfAmount": "staff_welfare_amount",
    }

    CREDIT_DIST_IDF_MAPPING = {
        "idfPercentage": "idf_percentage",
        "idfAmount": "idf_amount",
    }

    CREDIT_DIST_STWF_MAPPING = {
        "stwfPercentage": "student_welfare_percentage",
        "stwfAmount": "student_welfare_amount",
    }

    # Status mapping
    STATUS_MAPPING = {
        "APPROVED": "Approved",
        "DEPOSIT_RECEIVED": "Deposit Received",
        "PENDING": "Pending",
        "REJECTED": "Rejected",
    }

    @classmethod
    def map_status_to_workflow_state(cls, kafka_status: str) -> str:
        """Map Kafka status to Frappe workflow state."""
        return cls.STATUS_MAPPING.get(kafka_status, kafka_status)

    @classmethod
    def get_parent_field_updates(
        cls,
        dto: ConsultancyDepositSlipDTO,
        field_mapping: Optional[Dict[str, str]] = None,
        exclude_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get parent document field updates from DTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance
            field_mapping: Custom field mapping
            exclude_fields: Fields to exclude

        Returns:
            dict: Frappe field name -> value mapping
        """
        if field_mapping is None:
            field_mapping = cls.DEFAULT_FIELD_MAPPING

        if exclude_fields is None:
            exclude_fields = ['name', 'creation', 'owner']

        updates = {}

        # Map basic fields
        for dto_field, frappe_field in field_mapping.items():
            if frappe_field in exclude_fields:
                continue

            value = getattr(dto, dto_field, None)
            if value is None:
                continue

            if dto_field == "status":
                value = cls.map_status_to_workflow_state(value)

            updates[frappe_field] = value

        # Map GST details if present
        if dto.gstDetails:
            for dto_field, frappe_field in cls.GST_DETAILS_MAPPING.items():
                if frappe_field in exclude_fields:
                    continue

                value = getattr(dto.gstDetails, dto_field, None)
                if value is not None:
                    updates[frappe_field] = value

        # Map credit distribution amounts
        if dto.creditDistributionSwf:
            for dto_field, frappe_field in cls.CREDIT_DIST_SWF_MAPPING.items():
                if frappe_field in exclude_fields:
                    continue

                value = getattr(dto.creditDistributionSwf, dto_field, None)
                if value is not None:
                    updates[frappe_field] = value

        if dto.creditDistributionIdf:
            for dto_field, frappe_field in cls.CREDIT_DIST_IDF_MAPPING.items():
                if frappe_field in exclude_fields:
                    continue

                value = getattr(dto.creditDistributionIdf, dto_field, None)
                if value is not None:
                    updates[frappe_field] = value

        if dto.creditDistributionStwf:
            for dto_field, frappe_field in cls.CREDIT_DIST_STWF_MAPPING.items():
                if frappe_field in exclude_fields:
                    continue

                value = getattr(dto.creditDistributionStwf, dto_field, None)
                if value is not None:
                    updates[frappe_field] = value

        # Map consultancy D details if present
        if dto.consultancyDDetails and dto.category == "CONSULTANCY_D":
            for dto_field, frappe_field in cls.CONSULTANCY_D_DETAILS_MAPPING.items():
                if frappe_field in exclude_fields:
                    continue

                value = getattr(dto.consultancyDDetails, dto_field, None)
                if value is not None:
                    # Handle percentage to multiplier conversion
                    if "Percentage" in dto_field and "multiplier" in frappe_field:
                        value = value / 100.0
                    updates[frappe_field] = value

        # Map consultancy E/T/O details
        if dto.consultancyEDetails and dto.category == "CONSULTANCY_E":
            updates["consultancy_fee_x"] = dto.consultancyEDetails.consultancyFeeX_trainingFee

        if dto.consultancyTDetails and dto.category == "CONSULTANCY_T":
            updates["consultancy_fee_x"] = dto.consultancyTDetails.consultancyFeeX_trainingFee

        if dto.consultancyODetails and dto.category == "OTHER_EVENT":
            updates["training_fee"] = dto.consultancyODetails.consultancyFeeX_trainingFee

        return updates

    @classmethod
    def get_ecs_dates_updates(cls, dto: ConsultancyDepositSlipDTO) -> List[Dict[str, Any]]:
        """
        Get ECS dates child table updates from DTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            list: List of ECS date row dictionaries
        """
        ecs_dates_rows = []

        if dto.ecsDates:
            for ecs_date in dto.ecsDates:
                date_value = ecs_date.split('T')[0] if 'T' in ecs_date else ecs_date
                ecs_dates_rows.append({
                    "ecs_date": date_value,
                })

        return ecs_dates_rows

    @classmethod
    def get_credit_distribution_updates(cls, dto: ConsultancyDepositSlipDTO) -> List[Dict[str, Any]]:
        """
        Get credit distribution child table updates from DTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance

        Returns:
            list: List of credit distribution row dictionaries
        """
        credit_dist_rows = []

        # Add PDF entries
        if dto.creditDistributionPdf:
            for pdf in dto.creditDistributionPdf:
                credit_dist_rows.append({
                    "label": "PDF",
                    "employee_id": pdf.employeeId,
                    "department_id": pdf.departmentId,
                    "percentage": pdf.pdfPercentage,
                    "percentage_of_overhead": pdf.pdfPercentage,
                    "amount": pdf.pdfAmount,
                })

        # Add DPF entries
        if dto.creditDistributionDpf:
            for dpf in dto.creditDistributionDpf:
                credit_dist_rows.append({
                    "label": "DPF",
                    "department_id": dpf.departmentId,
                    "percentage": dpf.dpfPercentage,
                    "percentage_of_overhead": dpf.dpfPercentage,
                    "amount": dpf.dpfAmount,
                })

        return credit_dist_rows

    @classmethod
    def get_all_updates(
        cls,
        dto: ConsultancyDepositSlipDTO,
        field_mapping: Optional[Dict[str, str]] = None,
        exclude_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get all updates (parent and child tables) from DTO.

        Args:
            dto: ConsultancyDepositSlipDTO instance
            field_mapping: Custom field mapping
            exclude_fields: Fields to exclude from parent updates

        Returns:
            dict: Contains 'parent_fields', 'ecs_dates', 'credit_distribution'
        """
        return {
            "parent_fields": cls.get_parent_field_updates(dto, field_mapping, exclude_fields),
            "ecs_dates": cls.get_ecs_dates_updates(dto),
            "credit_distribution": cls.get_credit_distribution_updates(dto),
        }
