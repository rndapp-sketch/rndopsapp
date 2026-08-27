# Copyright (c) 2025, rndops and contributors
# Mapper for Reimbursement Commit and Payment Documents to DTO

import frappe
from frappe.utils import flt, today
from datetime import datetime, timezone
from typing import Optional

from .dto import AccountHeadCommitDTO, AccountHeadPaymentDTO


# ==========================================
# Event Wrapper Classes
# ==========================================

class AccountHeadCommitEvent:
    """
    Event wrapper for Account Head Commit DTO.
    Provides the interface expected by the producer.
    """

    def __init__(self, dto: AccountHeadCommitDTO):
        self.data = dto
        self.eventType = "ACCOUNT_HEAD_COMMIT"

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        """
        Convert to Kafka message envelope format.

        Args:
            schema_version: Schema version for the payload

        Returns:
            dict: Wrapped payload ready for Kafka publishing
        """
        return {
            "schemaVersion": schema_version,
            "eventType": self.eventType,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "data": self.data.to_dict()
        }


class AccountHeadPaymentEvent:
    """
    Event wrapper for Account Head Payment DTO.
    Provides the interface expected by the producer.
    """

    def __init__(self, dto: AccountHeadPaymentDTO):
        self.data = dto
        self.eventType = "ACCOUNT_HEAD_PAYMENT"

    def to_kafka_payload(self, schema_version: str = "1.0") -> dict:
        """
        Convert to Kafka message envelope format.

        Args:
            schema_version: Schema version for the payload

        Returns:
            dict: Wrapped payload ready for Kafka publishing
        """
        return {
            "schemaVersion": schema_version,
            "eventType": self.eventType,
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "data": self.data.to_dict()
        }


# ==========================================
# Utility Functions
# ==========================================

def get_module_id(doctype_name: str, page_name: str = "pending-task") -> Optional[int]:
    """
    Get module ID (idx) from Module Registry for a given doctype.

    Args:
        doctype_name: Name of the doctype (e.g., "Reimbursement", "Travel", "Temporary Advance")
        page_name: Module Registry page name (default: "pending-task")

    Returns:
        int or None: Module idx if found (e.g., 5 for Reimbursement, 6 for Travel, 7 for Temporary Advance)
    """
    if not doctype_name:
        return None

    try:
        # Query Module Registry Item for the doctype - get idx field
        module_idx = frappe.db.get_value(
            "Module Registry Item",
            {
                "doctype_name": doctype_name,
                "parent": page_name,
                "parenttype": "Module Registry"
            },
            "idx"
        )
        return int(module_idx) if module_idx else None
    except Exception:
        return None


def resolve_budget_head_id(budget_head) -> Optional[int]:
    """
    Resolve Budget Head ID from name or string.

    Args:
        budget_head: Budget head name, ID, or string

    Returns:
        int or None: Budget head ID if found
    """
    if not budget_head:
        return None

    # If it's already a number, return it
    if isinstance(budget_head, (int, float)):
        return int(budget_head)

    # If it's a digit string, convert to int
    if isinstance(budget_head, str) and budget_head.isdigit():
        return int(budget_head)

    try:
        # Try by name (PK) → custom id field
        found_id = frappe.db.get_value("Budget Head", budget_head, "id")
        if found_id:
            return int(found_id)

        # Try by budget_head label field → custom id field
        found_id = frappe.db.get_value("Budget Head", {"budget_head": budget_head}, "id")
        if found_id:
            return int(found_id)

        # id field is NULL — fall back to Frappe's idx (row position integer)
        found_idx = frappe.db.get_value("Budget Head", budget_head, "idx")
        if found_idx:
            return int(found_idx)

        found_idx = frappe.db.get_value("Budget Head", {"budget_head": budget_head}, "idx")
        if found_idx:
            return int(found_idx)
    except Exception:
        pass

    return None


def get_project_number(project_ref: str) -> str:
    """
    Get project number from linked Project Registration.

    Lookup order:
      1. project_no field from Project Registration (the actual project number)
      2. The Project Registration document name itself (a valid project identifier)
      3. The raw input string as-is (it may already be the project number)

    Args:
        project_ref: Project reference (name, title, or project number)

    Returns:
        str: Project number
    """
    if not project_ref:
        return ""

    try:
        # Try to fetch project_no from Project Registration
        val = frappe.db.get_value(
            "Project Registration", 
            project_ref, 
            ["project_no", "name"],
            as_dict=True
        )
        if val:
            # Prefer project_no; fall back to document name
            return val.project_no or val.name
    except Exception:
        pass
    
    # If lookup fails entirely, return the input as-is
    # (it may already be the project number string)
    return str(project_ref)


# ==========================================
# Commit Mapper
# ==========================================

class AccountHeadCommitMapper:
    """
    Maps Frappe Reimbursement documents to AccountHeadCommitDTO.
    """

    @staticmethod
    def map_to_dto(
        doc,
        commit_amount: float,
        budget_head,
        project_name: str,
        bmr: Optional[str] = None,
        bill_amount: Optional[float] = None,
        frap_app_id: Optional[str] = None,
        ref_details: Optional[str] = None,
        module_id: Optional[int] = None,
        commit_particular: Optional[str] = None
    ) -> AccountHeadCommitDTO:
        """
        Map Frappe Reimbursement document to AccountHeadCommitDTO.

        Args:
            doc: Reimbursement Frappe document
            commit_amount: Commit amount
            budget_head: Budget head name or ID
            project_name: Project number
            bmr: BMR number (optional)
            bill_amount: Bill amount (optional)
            frap_app_id: Frap App ID (optional, defaults to project_name)
            commit_particular: Explicit particulars string (e.g. staged via
                commitPayment.submit_commit_data). Takes priority over the
                table_bosk/expenditure_details derivation below, which only
                applies to Reimbursement/Advance Settlement documents.

        Returns:
            AccountHeadCommitDTO: Mapped DTO ready for validation and publishing
        """
        account_head_id = resolve_budget_head_id(budget_head)

        if commit_particular:
            particulars = commit_particular
        else:
            # Build particulars from child table rows
            # Support both Reimbursement (table_bosk) and Advance Settlement (expenditure_details)
            particulars_list = []

            table_bosk = getattr(doc, 'table_bosk', None) or []
            for row in table_bosk:
                if getattr(row, 'particulars', None):
                    particulars_list.append(row.particulars)

            expenditure_details = getattr(doc, 'expenditure_details', None) or []
            print(f"[COMMIT_MAPPER] doc.name={doc.name} doctype={getattr(doc, 'doctype', '?')} expenditure_details count={len(expenditure_details)}")
            for row in expenditure_details:
                row_particulars = getattr(row, 'particulars', None)
                print(f"[COMMIT_MAPPER]   row particulars={row_particulars}")
                if row_particulars:
                    particulars_list.append(row_particulars)

            print(f"[COMMIT_MAPPER] final particulars_list={particulars_list}")
            particulars = ", ".join(particulars_list) if particulars_list else f"Commitment for {doc.name}"

        # Get module information — use explicit override first, then resolve from doc.module or doctype
        doctype_name = getattr(doc, 'doctype', '')
        doc_module = getattr(doc, 'module', None)
        if module_id is None:
            if doc_module:
                module_id = get_module_id(doc_module)
            if module_id is None:
                module_id = get_module_id(doctype_name) or 7
        print(f"[COMMIT_MAPPER] Mapping doctype '{doctype_name}' (module: '{doc_module}') to module_id: {module_id}")

        # Use explicit frap_app_id if provided, otherwise fall back to project_name
        resolved_frap_app_id = frap_app_id if frap_app_id is not None else (project_name or "")

        dto = AccountHeadCommitDTO(
            transactionCommitNumber=None,  # To be generated by backend
            projectNumber=get_project_number(project_name),
            accountHeadId=account_head_id,
            transactionReceivedRefNumber=8,  # Default value
            commitDate=today(),
            commitParticular=particulars,
            refDetails=ref_details,
            commitAmount=flt(commit_amount),
            status="COMMITTED",
            frapAppId=resolved_frap_app_id,
            moduleId=module_id,
            billAmount=flt(bill_amount) if bill_amount is not None else None
        )

        return dto

    @classmethod
    def map_to_event(
        cls,
        doc,
        commit_amount: float,
        budget_head,
        project_name: str,
        bmr: Optional[str] = None,
        bill_amount: Optional[float] = None,
        frap_app_id: Optional[str] = None,
        ref_details: Optional[str] = None,
        module_id: Optional[int] = None,
        commit_particular: Optional[str] = None
    ) -> AccountHeadCommitEvent:
        """
        Map Frappe Reimbursement document to AccountHeadCommitEvent.
        This wraps the DTO in an event envelope for Kafka publishing.

        Args:
            doc: Reimbursement Frappe document
            commit_amount: Commit amount
            budget_head: Budget head name or ID
            project_name: Project number
            bmr: BMR number (optional)
            bill_amount: Bill amount (optional)
            frap_app_id: Frap App ID (optional, defaults to project_name)
            module_id: optional int override (e.g. 14 for ICSS PO re-commit)
            commit_particular: Explicit particulars string, takes priority over
                the doc-derived table_bosk/expenditure_details fallback.

        Returns:
            AccountHeadCommitEvent: Event wrapper ready for Kafka publishing
        """
        dto = cls.map_to_dto(doc, commit_amount, budget_head, project_name, bmr, bill_amount, frap_app_id, ref_details, module_id, commit_particular)
        return AccountHeadCommitEvent(dto)


# ==========================================
# Payment Mapper
# ==========================================

class AccountHeadPaymentMapper:
    """
    Maps Frappe AccountHeadPayment documents to AccountHeadPaymentDTO.
    """

    @staticmethod
    def map_to_dto(
        doc,
        project_name: Optional[str] = None,
        payment_amount: Optional[float] = None,
        budget_head=None,
        bmr: Optional[str] = None,
        ref_details: Optional[str] = None,
        frap_app_id: Optional[str] = None,
        module_name: Optional[str] = None,
        bill_amount: Optional[float] = None
    ) -> AccountHeadPaymentDTO:
        """
        Map Frappe AccountHeadPayment document to AccountHeadPaymentDTO.

        Args:
            doc: AccountHeadPayment Frappe document or dict
            project_name: Optional override for project_ref_number
            payment_amount: Optional override for payment_amount
            budget_head: Optional override for budget_head
            bmr: Optional override for payment_bmr
            ref_details: Optional override for reference details
            frap_app_id: Optional override for Frap App ID
            module_name: Optional override for Module Name
            bill_amount: Optional bill amount (e.g. required by the downstream
                ledger for TA/DA Settlement payments). Defaults to the resolved
                payment_amount when not supplied, since for a settlement-style
                payment the amount paid out is the bill amount.

        Returns:
            AccountHeadPaymentDTO: Mapped DTO ready for validation and publishing
        """
        # Extract data from document or dict
        project_ref = project_name or getattr(doc, "project_ref_number", None)
        project_number = get_project_number(project_ref)
        commit_id = getattr(doc, "commit_id", None)
        payment_date_val = getattr(doc, "payment_date", today())
        payment_particular = getattr(doc, "payment_particular", None) or f"Payment for {getattr(doc, 'name', 'NEW')}"
        payment_ref_details = ref_details or getattr(doc, "payment_reference_details", None) or getattr(doc, "name", "")
        payment_amt = payment_amount or getattr(doc, "payment_amount", 0.0)
        resolved_bill_amount = flt(bill_amount) if bill_amount is not None else (flt(payment_amt) if payment_amt else None)
        payment_bmr = bmr or getattr(doc, "payment_bmr", None)
        payment_status = getattr(doc, "payment_status", "PENDING")
        bank_txn_num = getattr(doc, "bank_transaction_number", None)
        bank_txn_date = getattr(doc, "bank_transaction_date", today())

        # Resolve Budget Head ID
        budget_head_value = budget_head or getattr(doc, "budget_head", None)
        account_head_id = resolve_budget_head_id(budget_head_value)

        # Get module information
        doctype_name = getattr(doc, 'doctype', '')
        
        # Priority 1: explicitly passed module_name (if it's an int or digit string)
        # Priority 2: mapping from doctype
        # Priority 3: Fallback 7
        resolved_module_id = None
        if module_name:
            try:
                resolved_module_id = int(module_name)
            except (ValueError, TypeError):
                resolved_module_id = get_module_id(module_name)
                
        if resolved_module_id is None:
            resolved_module_id = get_module_id(doctype_name) or 7
            
        print(f"[PAYMENT_MAPPER] Mapping doctype/module_name to module_id: {resolved_module_id}")

        # Use explicit frap_app_id if provided, otherwise fall back to project_number
        resolved_frap_app_id = frap_app_id if frap_app_id is not None else (project_number or "")

        dto = AccountHeadPaymentDTO(
            transactionPaymentNumber=None,  # To be generated by backend
            transactionCommitNumber=commit_id,
            projectNumber=project_number,
            accountHeadId=account_head_id,
            paymentDate=payment_date_val,
            paymentParticular=payment_particular,
            paymentRefDetails=payment_ref_details,
            paymentAmount=flt(payment_amt),
            bmr=payment_bmr,
            paymentStatus=payment_status,
            bankTransactionNumber=bank_txn_num,
            bankTransactionDate=bank_txn_date,
            frapAppId=resolved_frap_app_id,
            moduleId=resolved_module_id,
            billAmount=resolved_bill_amount
        )

        return dto

    @classmethod
    def map_to_event(
        cls,
        doc,
        project_name: Optional[str] = None,
        payment_amount: Optional[float] = None,
        budget_head=None,
        bmr: Optional[str] = None,
        ref_details: Optional[str] = None,
        frap_app_id: Optional[str] = None,
        module_name: Optional[str] = None,
        bill_amount: Optional[float] = None
    ) -> AccountHeadPaymentEvent:
        """
        Map Frappe AccountHeadPayment document to AccountHeadPaymentEvent.
        This wraps the DTO in an event envelope for Kafka publishing.

        Args:
            doc: AccountHeadPayment Frappe document or dict
            project_name: Optional override for project_ref_number
            payment_amount: Optional override for payment_amount
            budget_head: Optional override for budget_head
            bmr: Optional override for payment_bmr
            ref_details: Optional override for reference details
            frap_app_id: Optional override for Frap App ID
            module_name: Optional override for Module Name
            bill_amount: Optional bill amount override (defaults to payment_amount)

        Returns:
            AccountHeadPaymentEvent: Event wrapper ready for Kafka publishing
        """
        dto = cls.map_to_dto(doc, project_name, payment_amount, budget_head, bmr, ref_details, frap_app_id, module_name, bill_amount)
        return AccountHeadPaymentEvent(dto)
