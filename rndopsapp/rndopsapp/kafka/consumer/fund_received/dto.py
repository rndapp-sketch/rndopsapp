# Copyright (c) 2025, rndops and contributors
# Fund Received Consumer DTO - Data Transfer Objects for Fund Received Kafka updates

from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class FundBudgetBreakupUpdateDTO:
    """Budget Breakup DTO for Fund Received update."""
    accountHeadId: Optional[str] = None
    accountHead: Optional[str] = None  # Alternative field name
    amount: float = 0.0
    remarks: str = ""


@dataclass
class TransactionDetailsUpdateDTO:
    """Transaction Details DTO for Fund Received update."""
    uniqueTransactionNumber: str = ""
    transactionReceivedDate: Optional[str] = None  # Can be string or array
    transactionAmount: float = 0.0


@dataclass
class FundReceivedUpdateDTO:
    """
    Fund Received Update DTO.
    Represents incoming Kafka message for Fund Received updates.
    """
    # Primary identifiers
    fundReceivedRefNumber: Optional[int] = None
    fundReceivedRefNumberFap: Optional[str] = None

    # Related documents
    sanctionLetterNo: Optional[str] = None
    projectNumber: Optional[str] = None

    # Amount and account
    amountReceived: Optional[float] = None
    iitgAccountNumber: Optional[str] = None

    # Status fields
    depositSlipStatus: bool = False
    fundReceivedStatus: Optional[str] = None

    # Timestamps
    depositeStatusUpdateTime: Optional[str] = None
    fundReceivedStatusUpdateTime: Optional[str] = None

    # Child tables
    fundBudgetBreakupList: List[FundBudgetBreakupUpdateDTO] = field(default_factory=list)
    transactionDetailsList: List[TransactionDetailsUpdateDTO] = field(default_factory=list)

    @classmethod
    def from_kafka_message(cls, message: dict) -> 'FundReceivedUpdateDTO':
        """
        Create DTO from Kafka message data payload.

        Args:
            message: The 'data' section of the Kafka message

        Returns:
            FundReceivedUpdateDTO: Populated DTO
        """
        # Handle None message
        if not message:
            return cls()
        
        # Parse budget breakup list
        budget_breakups = []
        for item in (message.get('fundBudgetBreakupList') or []):
            budget_breakups.append(FundBudgetBreakupUpdateDTO(
                accountHeadId=item.get('accountHeadId'),
                accountHead=item.get('accountHead'),
                amount=float(item.get('amount') or 0),
                remarks=item.get('remarks', '')
            ))

        # Parse transaction details list
        transactions = []
        for item in (message.get('transactionDetailsList') or []):
            # Handle date format - can be array or string
            date_value = item.get('transactionReceivedDate')
            if isinstance(date_value, list) and len(date_value) >= 3:
                date_str = f"{date_value[0]}-{date_value[1]:02d}-{date_value[2]:02d}"
            elif isinstance(date_value, str):
                date_str = date_value
            else:
                date_str = None

            transactions.append(TransactionDetailsUpdateDTO(
                uniqueTransactionNumber=item.get('uniqueTransactionNumber', ''),
                transactionReceivedDate=date_str,
                transactionAmount=float(item.get('transactionAmount') or 0)
            ))

        return cls(
            fundReceivedRefNumber=message.get('fundReceivedRefNumber'),
            fundReceivedRefNumberFap=message.get('fundReceivedRefNumberFap'),
            sanctionLetterNo=message.get('sanctionLetterNo'),
            projectNumber=message.get('projectNumber'),
            amountReceived=message.get('amountReceived'),
            iitgAccountNumber=message.get('iitgAccountNumber'),
            depositSlipStatus=message.get('depositSlipStatus', False),
            fundReceivedStatus=message.get('fundReceivedStatus'),
            depositeStatusUpdateTime=message.get('depositeStatusUpdateTime'),
            fundReceivedStatusUpdateTime=message.get('fundReceivedStatusUpdateTime'),
            fundBudgetBreakupList=budget_breakups,
            transactionDetailsList=transactions
        )
