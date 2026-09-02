# Copyright (c) 2025, rndops and contributors
# Consumer Mapper for Research Deposit Slip Updates

from typing import Dict, List, Any, Optional
from .dto import ResearchDepositSlipDTO


class ResearchDepositSlipConsumerMapper:
    """
    Maps ResearchDepositSlipDTO fields to Frappe document field updates.
    """

    # Field mapping: DTO field name -> Frappe field name
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
        "amountInclusiveGst": "amount_inclusive_gst_capital",
        "finalGstAmount": "total_gst",
        "finalTotalAmount": "total_budget",
        "totalOverheadPercentage": "overhead_percentage",
        "totalOverheadAmount": "overhead_amount",
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
        "igstAmount": "igst_amount",
        "totalGstAmount": "total_gst",
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

    # Status mapping: Kafka status -> Frappe workflow_state
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
        dto: ResearchDepositSlipDTO,
        field_mapping: Optional[Dict[str, str]] = None,
        exclude_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get parent document field updates from DTO.

        Args:
            dto: ResearchDepositSlipDTO instance
            field_mapping: Custom field mapping (uses DEFAULT_FIELD_MAPPING if None)
            exclude_fields: List of Frappe field names to exclude from updates

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

            # Special handling for status -> workflow_state
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

        return updates

    @classmethod
    def get_ecs_dates_updates(cls, dto: ResearchDepositSlipDTO) -> List[Dict[str, Any]]:
        """
        Get ECS dates child table updates from DTO.

        Args:
            dto: ResearchDepositSlipDTO instance

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
    def get_credit_distribution_updates(cls, dto: ResearchDepositSlipDTO) -> List[Dict[str, Any]]:
        """
        Get credit distribution child table updates from DTO.

        Args:
            dto: ResearchDepositSlipDTO instance

        Returns:
            list: List of credit distribution row dictionaries
        """
        credit_dist_rows = []

        # Add PDF (Principal Development Fund) entries
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

        # Add DPF (Departmental Fund) entries
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
        dto: ResearchDepositSlipDTO,
        field_mapping: Optional[Dict[str, str]] = None,
        exclude_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get all updates (parent and child tables) from DTO.

        Args:
            dto: ResearchDepositSlipDTO instance
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
