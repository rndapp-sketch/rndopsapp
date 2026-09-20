# Copyright (c) 2026, rndops and contributors
# Loan Settlement Mapper - Maps Frappe Loan Settlement document to DTO

from datetime import datetime

from .dto import (
    LoanSettlementBudgetBreakupDTO,
    LoanSettlementDTO,
    LoanSettlementEventDTO,
)
from ...config import SCHEMA_VERSION_LOAN_SETTLEMENT


class LoanSettlementMapper:
    """
    Maps a Loan Settlement Frappe document to the Accounts service's settlement payload.

    Three identifiers are easy to confuse here (see docs/loan-settlement-implementation.md):
      - loanNumber  -> the Accounts service's own integer loan id, stored on our doc as
                       ledger_loan_number. NOT our Loan Request docname.
      - frapAppId   -> our Loan Request docname (their loanNumberFap). NOT the
                       Fund Received docname.
      - fundReceivedRefNumberFap
                    -> the Fund Received docname. This IS the Fund Received one, and it
                       must match what fund_received/mapper.py publishes for the same
                       receipt (it sends doc.name) — that equality is the join.
    """

    @classmethod
    def map_to_dto(cls, doc) -> LoanSettlementDTO:
        ledger_loan_number = getattr(doc, "ledger_loan_number", None)
        settlement_date = getattr(doc, "settlement_date", None)
        loan_number = int(ledger_loan_number) if ledger_loan_number else None
        project_number = getattr(doc, "project_number", None) or ""

        breakup = []
        for row in getattr(doc, "budget_breakup", None) or []:
            head_id = getattr(row, "account_head_id", None)
            breakup.append(
                LoanSettlementBudgetBreakupDTO(
                    accountHeadId=int(head_id) if head_id else None,
                    amount=float(getattr(row, "return_amount", 0) or 0),
                )
            )

        return LoanSettlementDTO(
            loanNumber=loan_number,
            projectNumber=project_number,
            loanSettlementNumber=doc.name,
            frapAppId=getattr(doc, "loan_reference", None) or None,
            # The Fund Received docname — byte-for-byte what Fund Received's own event
            # publishes as fundReceivedRefNumberFap, so Accounts can join the two.
            fundReceivedRefNumberFap=getattr(doc, "fund_received_reference", None) or None,
            settlementAmount=float(getattr(doc, "settlement_amount", 0) or 0),
            settlementDate=str(settlement_date) if settlement_date else None,
            settlementMode=getattr(doc, "settlement_mode", None) or None,
            remarks=getattr(doc, "remarks", None) or None,
            # Always PENDING: every settlement we publish is awaiting the Accounts
            # side's confirm / reject / rectify decision.
            settlementStatus="PENDING",
            loanSettlementBudgetBreakupDetails=breakup,
        )

    @classmethod
    def map_to_event(cls, doc) -> LoanSettlementEventDTO:
        dto = cls.map_to_dto(doc)
        return LoanSettlementEventDTO(
            schemaVersion=SCHEMA_VERSION_LOAN_SETTLEMENT,
            eventType="LOAN_SETTLEMENT",
            timestamp=datetime.utcnow().isoformat(),
            data=dto,
        )
