# Copyright (c) 2025, rndops and contributors
# Project Registration Validator - Validates Project Registration DTO before publishing

import frappe
from typing import List
from .dto import ProjectDataDTO, ProjectEventDTO


class ValidationError(Exception):
    """Custom validation error for Project Registration."""
    pass


class ProjectRegistrationValidator:
    """
    Validator for Project Registration DTO.
    Ensures data integrity before sending to Kafka.
    """

    @staticmethod
    def validate_required_fields(dto: ProjectDataDTO) -> List[str]:
        """
        Validate required fields in ProjectDataDTO.

        Args:
            dto: ProjectDataDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Required string fields
        if not dto.projectNumber or not str(dto.projectNumber).strip():
            errors.append("projectNumber is required")

        if not dto.empId or not str(dto.empId).strip():
            errors.append("empId (PI Employee ID) is required")

        if not dto.projectType or not str(dto.projectType).strip():
            errors.append("projectType is required")

        if not dto.status or not str(dto.status).strip():
            errors.append("status is required")

        return errors

    @staticmethod
    def validate_numeric_fields(dto: ProjectDataDTO) -> List[str]:
        """
        Validate numeric fields are non-negative.

        Args:
            dto: ProjectDataDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if dto.totalBudgetAmount < 0:
            errors.append("totalBudgetAmount cannot be negative")

        if dto.overHeadAmountPercentage < 0:
            errors.append("overHeadAmountPercentage cannot be negative")

        if dto.overHeadAmountPercentage > 100:
            errors.append("overHeadAmountPercentage cannot exceed 100")

        if dto.overHeadAmount < 0:
            errors.append("overHeadAmount cannot be negative")

        if dto.budgetWithOverHeadAmount < 0:
            errors.append("budgetWithOverHeadAmount cannot be negative")

        if dto.gst < 0:
            errors.append("gst cannot be negative")

        if dto.grandTotal < 0:
            errors.append("grandTotal cannot be negative")

        return errors

    @staticmethod
    def validate_dates(dto: ProjectDataDTO) -> List[str]:
        """
        Validate date fields.

        Args:
            dto: ProjectDataDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Start date should be before completion date if both are present
        if dto.startDate and dto.completionDate:
            if dto.startDate > dto.completionDate:
                errors.append("startDate cannot be after completionDate")

        return errors

    @staticmethod
    def validate_department_centres(dto: ProjectDataDTO) -> List[str]:
        """
        Validate implemented department centres.

        Args:
            dto: ProjectDataDTO instance

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Department ID should match first element of implementedDeptCentres
        if dto.implementedDeptCentres and dto.departmentId:
            if str(dto.departmentId) not in dto.implementedDeptCentres:
                # Warning only, not a blocking error
                pass

        return errors

    @classmethod
    def validate(cls, dto: ProjectDataDTO, raise_exception: bool = True) -> List[str]:
        """
        Perform complete validation on ProjectDataDTO.

        Args:
            dto: ProjectDataDTO instance to validate
            raise_exception: If True, raises ValidationError on failure

        Returns:
            List of validation error messages (empty if valid)

        Raises:
            ValidationError: If validation fails and raise_exception is True
        """
        all_errors = []

        all_errors.extend(cls.validate_required_fields(dto))
        all_errors.extend(cls.validate_numeric_fields(dto))
        all_errors.extend(cls.validate_dates(dto))
        all_errors.extend(cls.validate_department_centres(dto))

        if all_errors and raise_exception:
            error_message = "Project Registration DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in all_errors])
            frappe.log_error(error_message, "Project Registration DTO Validation Error")
            raise ValidationError(error_message)

        return all_errors

    @classmethod
    def validate_event(cls, event: ProjectEventDTO, raise_exception: bool = True) -> List[str]:
        """
        Validate complete ProjectEventDTO.

        Args:
            event: ProjectEventDTO instance
            raise_exception: If True, raises ValidationError on failure

        Returns:
            List of validation error messages
        """
        errors = []

        if not event.schemaVersion:
            errors.append("schemaVersion is required")

        if not event.eventType:
            errors.append("eventType is required")

        if not event.timestamp:
            errors.append("timestamp is required")

        # Validate the nested data DTO
        data_errors = cls.validate(event.data, raise_exception=False)
        errors.extend(data_errors)

        if errors and raise_exception:
            error_message = "Project Event DTO Validation Failed:\n" + \
                "\n".join([f"  - {err}" for err in errors])
            frappe.log_error(error_message, "Project Event DTO Validation Error")
            raise ValidationError(error_message)

        return errors

    @staticmethod
    def validate_and_log(dto: ProjectDataDTO) -> bool:
        """
        Validate DTO and log errors without raising exception.

        Args:
            dto: ProjectDataDTO instance

        Returns:
            bool: True if valid, False if validation errors exist
        """
        try:
            errors = ProjectRegistrationValidator.validate(dto, raise_exception=False)
            if errors:
                error_message = "Project Registration DTO Validation Failed:\n" + \
                    "\n".join([f"  - {err}" for err in errors])
                frappe.log_error(error_message, "Project Registration DTO Validation Error")
                print(f"[ERROR] [VALIDATION] {error_message}")
                return False
            return True
        except Exception as e:
            frappe.log_error(str(e), "Project Registration Validation Exception")
            print(f"[ERROR] [VALIDATION] Unexpected error: {str(e)}")
            return False
