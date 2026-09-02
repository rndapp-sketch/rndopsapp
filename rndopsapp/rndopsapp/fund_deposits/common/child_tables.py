# Copyright (c) 2025, rndops and contributors
# Shared Child Table Update Functions for Deposit Slip Consumer

from typing import List, Dict, Any
import frappe


class DepositSlipChildTableUpdater:
    """
    Handles child table updates for Deposit Slip documents.
    Follows delete-all-then-insert strategy.
    """

    @staticmethod
    def update_ecs_dates(
        parent_name: str,
        ecs_dates_list: List[Dict[str, Any]],
        child_doctype: str = "Deposit Slip ECS Date",
        parent_doctype: str = "Research Deposit Slip",
        parent_field: str = "ecs_dates"
    ) -> bool:
        """
        Update ECS Dates child table.
        Deletes all existing rows and inserts new ones.

        Args:
            parent_name: Name of parent document
            ecs_dates_list: List of ECS date row dictionaries
            child_doctype: Child doctype name
            parent_doctype: Parent doctype name
            parent_field: Parent field name for the child table

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not ecs_dates_list:
                print(f"[INFO] [CHILD TABLE] No ECS dates to update for {parent_name}")
                return True

            print(f"[UPDATE] [CHILD TABLE] Updating ECS Dates for {parent_name}...")

            # Step 1: DELETE all existing rows
            print(f"[DELETE] [CHILD TABLE] Deleting existing ECS dates for {parent_name}")
            frappe.db.delete(child_doctype, {'parent': parent_name, 'parenttype': parent_doctype})

            # Step 2: INSERT new rows
            print(f"[INSERT] [CHILD TABLE] Inserting {len(ecs_dates_list)} ECS date rows")
            for idx, item in enumerate(ecs_dates_list, start=1):
                child_doc = frappe.new_doc(child_doctype)
                child_doc.parent = parent_name
                child_doc.parenttype = parent_doctype
                child_doc.parentfield = parent_field
                child_doc.idx = idx

                # Map fields
                child_doc.ecs_date = item.get('ecs_date')
                child_doc.amount = item.get('amount', 0.0)

                # Insert without triggering validations
                child_doc.db_insert()

            frappe.db.commit()
            print(f"[OK] [CHILD TABLE] Successfully updated {len(ecs_dates_list)} ECS date rows")
            return True

        except Exception as e:
            error_msg = f"Error updating ECS dates for {parent_name}: {str(e)}"
            frappe.log_error(error_msg, "Deposit Slip Child Table Update Error")
            print(f"[ERROR] [CHILD TABLE] {error_msg}")
            frappe.db.rollback()
            return False

    @staticmethod
    def update_credit_distribution(
        parent_name: str,
        credit_dist_list: List[Dict[str, Any]],
        child_doctype: str = "Deposit Slip Credit Distribution",
        parent_doctype: str = "Research Deposit Slip",
        parent_field: str = "credit_distribution"
    ) -> bool:
        """
        Update Credit Distribution child table.
        Deletes all existing rows and inserts new ones.

        Args:
            parent_name: Name of parent document
            credit_dist_list: List of credit distribution row dictionaries
            child_doctype: Child doctype name
            parent_doctype: Parent doctype name
            parent_field: Parent field name for the child table

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not credit_dist_list:
                print(f"[INFO] [CHILD TABLE] No credit distribution to update for {parent_name}")
                return True

            print(f"[UPDATE] [CHILD TABLE] Updating Credit Distribution for {parent_name}...")

            # Step 1: DELETE all existing rows
            print(f"[DELETE] [CHILD TABLE] Deleting existing credit distribution for {parent_name}")
            frappe.db.delete(child_doctype, {'parent': parent_name, 'parenttype': parent_doctype})

            # Step 2: INSERT new rows
            print(f"[INSERT] [CHILD TABLE] Inserting {len(credit_dist_list)} credit distribution rows")
            for idx, item in enumerate(credit_dist_list, start=1):
                child_doc = frappe.new_doc(child_doctype)
                child_doc.parent = parent_name
                child_doc.parenttype = parent_doctype
                child_doc.parentfield = parent_field
                child_doc.idx = idx

                # Map fields
                child_doc.label = item.get('label', '')
                child_doc.employee_id = item.get('employee_id')
                child_doc.department_id = item.get('department_id')
                child_doc.percentage = item.get('percentage', 0.0)
                child_doc.percentage_of_overhead = item.get('percentage_of_overhead', 0.0)
                child_doc.amount = item.get('amount', 0.0)

                # Insert without triggering validations
                child_doc.db_insert()

            frappe.db.commit()
            print(f"[OK] [CHILD TABLE] Successfully updated {len(credit_dist_list)} credit distribution rows")
            return True

        except Exception as e:
            error_msg = f"Error updating credit distribution for {parent_name}: {str(e)}"
            frappe.log_error(error_msg, "Deposit Slip Child Table Update Error")
            print(f"[ERROR] [CHILD TABLE] {error_msg}")
            frappe.db.rollback()
            return False

    @classmethod
    def update_all_child_tables(
        cls,
        parent_name: str,
        ecs_dates_list: List[Dict[str, Any]],
        credit_dist_list: List[Dict[str, Any]],
        ecs_dates_doctype: str = "Deposit Slip ECS Date",
        credit_dist_doctype: str = "Deposit Slip Credit Distribution",
        parent_doctype: str = "Research Deposit Slip",
        ecs_dates_field: str = "ecs_dates",
        credit_dist_field: str = "credit_distribution"
    ) -> bool:
        """
        Update all child tables for a deposit slip.

        Args:
            parent_name: Name of parent document
            ecs_dates_list: List of ECS date row dictionaries
            credit_dist_list: List of credit distribution row dictionaries
            ecs_dates_doctype: ECS dates child doctype name
            credit_dist_doctype: Credit distribution child doctype name
            parent_doctype: Parent doctype name
            ecs_dates_field: Parent field for ECS dates
            credit_dist_field: Parent field for credit distribution

        Returns:
            bool: True if all updates successful, False otherwise
        """
        success = True

        # Update ECS dates
        if ecs_dates_list:
            success = cls.update_ecs_dates(
                parent_name,
                ecs_dates_list,
                child_doctype=ecs_dates_doctype,
                parent_doctype=parent_doctype,
                parent_field=ecs_dates_field
            ) and success

        # Update credit distribution
        if credit_dist_list:
            success = cls.update_credit_distribution(
                parent_name,
                credit_dist_list,
                child_doctype=credit_dist_doctype,
                parent_doctype=parent_doctype,
                parent_field=credit_dist_field
            ) and success

        return success
