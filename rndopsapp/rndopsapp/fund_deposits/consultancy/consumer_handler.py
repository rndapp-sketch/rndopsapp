# Copyright (c) 2025, rndops and contributors
# Consumer Handler for Consultancy Deposit Slip Updates

from typing import Dict, Any, Optional
import frappe
from .consumer_dto import ConsultancyDepositSlipUpdateMessageDTO
from .consumer_mapper import ConsultancyDepositSlipConsumerMapper, ConsultancyDoctypeConfig
from .validator import ConsultancyDepositSlipValidator, ValidationError
from ..common.child_tables import DepositSlipChildTableUpdater


class ConsultancyDepositSlipConsumerHandler:
    """
    Main handler for consuming Consultancy Deposit Slip update messages from Kafka.
    Supports: CONSULTANCY_D, CONSULTANCY_E, CONSULTANCY_T, OTHER_EVENT
    """

    @staticmethod
    def update_parent_fields(
        doc_name: str,
        field_updates: Dict[str, Any],
        doctype: str
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
            frappe.log_error(error_msg, "Consultancy Deposit Slip Parent Update Error")
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
        Main handler for processing Consultancy Deposit Slip update messages from Kafka.

        Args:
            message: Raw Kafka message dictionary
            validate: Whether to validate the message before processing
            update_child_tables: Whether to update child tables

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print("\n" + "="*80)
            print("[CONSULTANCY CONSUMER] Processing update message")
            print("="*80)

            # Step 1: Parse message to DTO
            print("[STEP 1] Parsing Kafka message to DTO...")
            message_dto = ConsultancyDepositSlipUpdateMessageDTO.from_dict(message)

            if not message_dto.data:
                print("[ERROR] [CONSUMER] No data found in message")
                return False

            deposit_slip_ref = message_dto.data.depositSlipRefNumFab
            category = message_dto.data.category
            gst_type = message_dto.data.gstType

            print(f"   [DATA] Deposit Slip Ref: {deposit_slip_ref}")
            print(f"   [DATA] Category: {category}")
            print(f"   [DATA] GST Type: {gst_type}")
            print(f"   [DATA] Status: {message_dto.data.status}")

            # Step 2: Determine doctype from category
            doctype = ConsultancyDoctypeConfig.get_doctype(category)
            print(f"   [DATA] DocType: {doctype}")

            # Step 3: Validate message
            if validate:
                print("\n[STEP 2] Validating message...")
                try:
                    errors = ConsultancyDepositSlipValidator.validate(message_dto.data, raise_exception=False)
                    if errors:
                        print(f"   [WARN] Validation warnings: {errors}")
                    print("   [OK] Basic validation passed")
                except ValidationError as ve:
                    print(f"   [ERROR] Validation failed: {str(ve)}")
                    return False

            # Step 4: Check if document exists
            if not frappe.db.exists(doctype, deposit_slip_ref):
                print(f"[ERROR] [CONSUMER] Document {deposit_slip_ref} does not exist in {doctype}")
                return False

            # Step 5: Map DTO to field updates
            print("\n[STEP 3] Mapping DTO to Frappe field updates...")
            all_updates = ConsultancyDepositSlipConsumerMapper.get_all_updates(message_dto.data)

            parent_fields = all_updates['parent_fields']
            ecs_dates = all_updates['ecs_dates']
            credit_distribution = all_updates['credit_distribution']

            print(f"   [DATA] Parent fields to update: {len(parent_fields)}")
            print(f"   [DATA] ECS dates rows: {len(ecs_dates)}")
            print(f"   [DATA] Credit distribution rows: {len(credit_distribution)}")

            # Step 6: Update parent fields
            print("\n[STEP 4] Updating parent document fields...")
            parent_success = cls.update_parent_fields(deposit_slip_ref, parent_fields, doctype)

            if not parent_success:
                print("[ERROR] [CONSUMER] Failed to update parent fields")
                return False

            # Step 7: Update child tables
            if update_child_tables:
                print("\n[STEP 5] Updating child tables...")
                config = ConsultancyDoctypeConfig.get_config(category)
                child_success = DepositSlipChildTableUpdater.update_all_child_tables(
                    parent_name=deposit_slip_ref,
                    ecs_dates_list=ecs_dates,
                    credit_dist_list=credit_distribution,
                    ecs_dates_doctype=config['ecs_dates_child'],
                    credit_dist_doctype=config['credit_dist_child'],
                    parent_doctype=doctype
                )

                if not child_success:
                    print("[WARN] [CONSUMER] Some child table updates failed")

            # Step 8: Final commit
            frappe.db.commit()

            print("\n" + "="*80)
            print(f"[OK] [CONSULTANCY CONSUMER] Successfully processed update for {deposit_slip_ref}")
            print("="*80 + "\n")

            return True

        except Exception as e:
            error_msg = f"Error handling consultancy deposit slip update: {str(e)}"
            frappe.log_error(frappe.get_traceback(), "Consultancy Deposit Slip Consumer Handler Error")
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
            print("[DRY RUN] [CONSULTANCY CONSUMER DRY RUN]")
            print("="*80)

            message_dto = ConsultancyDepositSlipUpdateMessageDTO.from_dict(message)

            if not message_dto.data:
                return {
                    "valid": False,
                    "error": "No data found in message",
                    "validation_errors": ["No data found in message"]
                }

            deposit_slip_ref = message_dto.data.depositSlipRefNumFab
            category = message_dto.data.category
            doctype = ConsultancyDoctypeConfig.get_doctype(category)

            # Validate
            validation_errors = ConsultancyDepositSlipValidator.validate(
                message_dto.data, raise_exception=False
            )

            # Map updates
            all_updates = ConsultancyDepositSlipConsumerMapper.get_all_updates(message_dto.data)

            # Check if document exists
            doc_exists = frappe.db.exists(doctype, deposit_slip_ref) if deposit_slip_ref else False

            result = {
                "valid": len(validation_errors) == 0 and doc_exists,
                "validation_errors": validation_errors,
                "deposit_slip_ref": deposit_slip_ref,
                "doctype": doctype,
                "doc_exists": doc_exists,
                "category": category,
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
                result["validation_errors"].append(f"Document '{deposit_slip_ref}' does not exist in {doctype}")

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
            frappe.log_error(frappe.get_traceback(), "Consultancy Deposit Slip Consumer Dry Run Error")
            print(f"[ERROR] [DRY RUN] {error_msg}")
            return {
                "valid": False,
                "error": error_msg,
                "validation_errors": [error_msg]
            }


def handle_consultancy_deposit_slip_update(message: Dict[str, Any], validate: bool = True) -> bool:
    """
    Convenience function to handle consultancy deposit slip update from Kafka.

    Args:
        message: Raw Kafka message dictionary
        validate: Whether to validate before processing

    Returns:
        bool: True if successful, False otherwise
    """
    return ConsultancyDepositSlipConsumerHandler.handle_update(
        message,
        validate=validate,
        update_child_tables=True
    )
