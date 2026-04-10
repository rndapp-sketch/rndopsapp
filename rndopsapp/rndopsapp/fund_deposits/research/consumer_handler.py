# Copyright (c) 2025, rndops and contributors
# Consumer Handler for Research Deposit Slip Updates

from typing import Dict, Any, Optional
import frappe
from .consumer_dto import ResearchDepositSlipUpdateMessageDTO
from .consumer_mapper import ResearchDepositSlipConsumerMapper
from .validator import ResearchDepositSlipValidator, ValidationError
from ..common.child_tables import DepositSlipChildTableUpdater


class ResearchDepositSlipConsumerHandler:
    """
    Main handler for consuming Research Deposit Slip update messages from Kafka.
    Orchestrates parsing, validation, mapping, and updating Frappe documents.
    """

    # Doctype for Research Deposit Slip
    DOCTYPE = "Research Deposit Slip"
    ECS_DATES_CHILD = "Deposit Slip ECS Date"
    CREDIT_DIST_CHILD = "Deposit Slip Credit Distribution"

    @staticmethod
    def update_parent_fields(
        doc_name: str,
        field_updates: Dict[str, Any],
        doctype: str = "Research Deposit Slip"
    ) -> bool:
        """
        Update parent document fields using direct DB updates.

        Args:
            doc_name: Document name (primary key)
            field_updates: Dictionary of field_name -> value
            doctype: DocType name

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not field_updates:
                print(f"[INFO] [PARENT UPDATE] No parent fields to update for {doc_name}")
                return True

            print(f"[UPDATE] [PARENT UPDATE] Updating {len(field_updates)} parent fields for {doc_name}")

            for field_name, value in field_updates.items():
                print(f"   [FIELD] Setting {field_name} = {value}")
                frappe.db.set_value(doctype, doc_name, field_name, value)

            frappe.db.commit()
            print(f"[OK] [PARENT UPDATE] Successfully updated parent fields for {doc_name}")
            return True

        except Exception as e:
            error_msg = f"Error updating parent fields for {doc_name}: {str(e)}"
            frappe.log_error(error_msg, "Research Deposit Slip Parent Update Error")
            print(f"[ERROR] [PARENT UPDATE] {error_msg}")
            frappe.db.rollback()
            return False

    @classmethod
    def handle_update(
        cls,
        message: Dict[str, Any],
        validate: bool = True,
        update_child_tables: bool = True
    ) -> bool:
        """
        Main handler for processing Research Deposit Slip update messages from Kafka.

        Args:
            message: Raw Kafka message dictionary
            validate: Whether to validate the message before processing
            update_child_tables: Whether to update child tables

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print("\n" + "="*80)
            print("[RESEARCH CONSUMER] Processing update message")
            print("="*80)

            # Step 1: Parse message to DTO
            print("[STEP 1] Parsing Kafka message to DTO...")
            message_dto = ResearchDepositSlipUpdateMessageDTO.from_dict(message)

            if not message_dto.data:
                print("[ERROR] [CONSUMER] No data found in message")
                return False

            deposit_slip_ref = message_dto.data.depositSlipRefNumFab
            gst_type = message_dto.data.gstType

            print(f"   [DATA] Deposit Slip Ref: {deposit_slip_ref}")
            print(f"   [DATA] Category: RESEARCH")
            print(f"   [DATA] GST Type: {gst_type}")
            print(f"   [DATA] Status: {message_dto.data.status}")

            # Step 2: Validate message
            if validate:
                print("\n[STEP 2] Validating message...")
                try:
                    errors = ResearchDepositSlipValidator.validate(message_dto.data, raise_exception=False)
                    if errors:
                        print(f"   [WARN] Validation warnings: {errors}")
                    print("   [OK] Basic validation passed")
                except ValidationError as ve:
                    print(f"   [ERROR] Validation failed: {str(ve)}")
                    return False

            # Step 3: Check if document exists
            if not frappe.db.exists(cls.DOCTYPE, deposit_slip_ref):
                print(f"[ERROR] [CONSUMER] Document {deposit_slip_ref} does not exist in {cls.DOCTYPE}")
                return False

            # Step 4: Map DTO to field updates
            print("\n[STEP 3] Mapping DTO to Frappe field updates...")
            all_updates = ResearchDepositSlipConsumerMapper.get_all_updates(message_dto.data)

            parent_fields = all_updates['parent_fields']
            ecs_dates = all_updates['ecs_dates']
            credit_distribution = all_updates['credit_distribution']

            print(f"   [DATA] Parent fields to update: {len(parent_fields)}")
            print(f"   [DATA] ECS dates rows: {len(ecs_dates)}")
            print(f"   [DATA] Credit distribution rows: {len(credit_distribution)}")

            # Step 5: Update parent fields
            print("\n[STEP 4] Updating parent document fields...")
            parent_success = cls.update_parent_fields(deposit_slip_ref, parent_fields, cls.DOCTYPE)

            if not parent_success:
                print("[ERROR] [CONSUMER] Failed to update parent fields")
                return False

            # Step 6: Update child tables
            if update_child_tables:
                print("\n[STEP 5] Updating child tables...")
                child_success = DepositSlipChildTableUpdater.update_all_child_tables(
                    parent_name=deposit_slip_ref,
                    ecs_dates_list=ecs_dates,
                    credit_dist_list=credit_distribution,
                    ecs_dates_doctype=cls.ECS_DATES_CHILD,
                    credit_dist_doctype=cls.CREDIT_DIST_CHILD,
                    parent_doctype=cls.DOCTYPE
                )

                if not child_success:
                    print("[WARN] [CONSUMER] Some child table updates failed")

            # Step 7: Final commit
            frappe.db.commit()

            print("\n" + "="*80)
            print(f"[OK] [RESEARCH CONSUMER] Successfully processed update for {deposit_slip_ref}")
            print("="*80 + "\n")

            return True

        except Exception as e:
            error_msg = f"Error handling research deposit slip update: {str(e)}"
            frappe.log_error(frappe.get_traceback(), "Research Deposit Slip Consumer Handler Error")
            print(f"\n[ERROR] [CONSUMER] {error_msg}")
            print("="*80 + "\n")
            frappe.db.rollback()
            return False

    @classmethod
    def dry_run(cls, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform a dry run without actually updating Frappe.
        Useful for testing and debugging.

        Args:
            message: Raw Kafka message dictionary

        Returns:
            dict: Contains validation results and planned updates
        """
        try:
            print("\n" + "="*80)
            print("[DRY RUN] [RESEARCH CONSUMER DRY RUN]")
            print("="*80)

            message_dto = ResearchDepositSlipUpdateMessageDTO.from_dict(message)

            if not message_dto.data:
                return {
                    "valid": False,
                    "error": "No data found in message",
                    "validation_errors": ["No data found in message"]
                }

            deposit_slip_ref = message_dto.data.depositSlipRefNumFab

            # Validate
            validation_errors = ResearchDepositSlipValidator.validate(
                message_dto.data, raise_exception=False
            )

            # Map updates
            all_updates = ResearchDepositSlipConsumerMapper.get_all_updates(message_dto.data)

            # Check if document exists
            doc_exists = frappe.db.exists(cls.DOCTYPE, deposit_slip_ref) if deposit_slip_ref else False

            result = {
                "valid": len(validation_errors) == 0 and doc_exists,
                "validation_errors": validation_errors,
                "deposit_slip_ref": deposit_slip_ref,
                "doctype": cls.DOCTYPE,
                "doc_exists": doc_exists,
                "category": "RESEARCH",
                "gst_type": message_dto.data.gstType,
                "status": message_dto.data.status,
                "parent_fields_count": len(all_updates['parent_fields']),
                "parent_fields": all_updates['parent_fields'],
                "ecs_dates_count": len(all_updates['ecs_dates']),
                "ecs_dates": all_updates['ecs_dates'],
                "credit_distribution_count": len(all_updates['credit_distribution']),
                "credit_distribution": all_updates['credit_distribution'],
            }

            if not doc_exists:
                result["validation_errors"].append(f"Document '{deposit_slip_ref}' does not exist")

            if result["valid"]:
                print("[OK] Dry run successful - No validation errors")
            else:
                print(f"[ERROR] Dry run found issues:")
                for error in result["validation_errors"]:
                    print(f"   - {error}")

            print("="*80 + "\n")
            return result

        except Exception as e:
            error_msg = f"Error during dry run: {str(e)}"
            frappe.log_error(frappe.get_traceback(), "Research Deposit Slip Consumer Dry Run Error")
            print(f"[ERROR] [DRY RUN] {error_msg}")
            return {
                "valid": False,
                "error": error_msg,
                "validation_errors": [error_msg]
            }


def handle_research_deposit_slip_update(message: Dict[str, Any], validate: bool = True) -> bool:
    """
    Convenience function to handle research deposit slip update from Kafka.

    Args:
        message: Raw Kafka message dictionary
        validate: Whether to validate before processing

    Returns:
        bool: True if successful, False otherwise
    """
    return ResearchDepositSlipConsumerHandler.handle_update(
        message,
        validate=validate,
        update_child_tables=True
    )
