import json
import sys
import os

# Add the app directory to sys.path so we can import modules
sys.path.append('/home/prornd/project/frappe_dev/prornd/apps/rndopsapp')

from rndopsapp.rndopsapp.transaction_dto import AccountHeadCommitDTO, AccountHeadPaymentDTO

def test_dto_json():
    # Test Commit DTO
    commit_dto = AccountHeadCommitDTO(
        transactionCommitNumber=None,
        projectNumber="TEST-PRJ-001",
        accountHeadId=1,
        transactionReceivedRefNumber=9,
        commitDate="2026-01-15",
        commitParticular="Purchase of I-Pad",
        refDetails="R&D-IISI-XXXX004",
        commitAmount=20000.00,
        status="COMMITTED"
    )
    
    commit_json = commit_dto.to_dict()
    print("COMMIT JSON:")
    print(json.dumps(commit_json, indent=2))
    
    expected_commit = {
      "transactionCommitNumber": None,
      "projectNumber": "TEST-PRJ-001",
      "accountHeadId": 1,
      "transactionReceivedRefNumber": 9,
      "commitDate": "2026-01-15",
      "commitParticular": "Purchase of I-Pad",
      "refDetails": "R&D-IISI-XXXX004",
      "commitAmount": 20000.00,
      "status": "COMMITTED"
    }

    assert commit_json == expected_commit, "Commit JSON mismatch!"


    # Test Payment DTO
    payment_dto = AccountHeadPaymentDTO(
        transactionPaymentNumber=None,
        transactionCommitNumber=1,
        projectNumber="TEST-PRJ-001",
        accountHeadId=1,
        paymentDate="2026-01-20",
        paymentParticular="Payment for Purchase of I-Pad",
        paymentRefDetails="PAY-R&D-IISI-XXXX004",
        paymentAmount=20000.00,
        bmr="BMR-TEST-002",
        paymentStatus="PAID",
        bankTransactionNumber="BANK-TXN-123456",
        bankTransactionDate="2026-01-20"
    )

    payment_json = payment_dto.to_dict()
    print("\nPAYMENT JSON:")
    print(json.dumps(payment_json, indent=2))

    expected_payment = {
      "transactionPaymentNumber": None,
      "transactionCommitNumber": 1,
      "projectNumber": "TEST-PRJ-001",
      "accountHeadId": 1,
      "paymentDate": "2026-01-20",
      "paymentParticular": "Payment for Purchase of I-Pad",
      "paymentRefDetails": "PAY-R&D-IISI-XXXX004",
      "paymentAmount": 20000.00,
      "bmr": "BMR-TEST-002",
      "paymentStatus": "PAID",
      "bankTransactionNumber": "BANK-TXN-123456",
      "bankTransactionDate": "2026-01-20"
    }

    assert payment_json == expected_payment, "Payment JSON mismatch!"
    print("\nVerification Successful!")

if __name__ == "__main__":
    test_dto_json()
