class AccountHeadCommitDTO:
    def __init__(
        self,
        transactionCommitNumber=None,
        projectNumber=None,
        accountHeadId=None,
        transactionReceivedRefNumber=None,
        commitDate=None,
        commitParticular=None,
        refDetails=None,
        commitAmount=0.0,
        status="COMMITTED"
    ):
        self.transactionCommitNumber = transactionCommitNumber
        self.projectNumber = projectNumber
        self.accountHeadId = accountHeadId
        self.transactionReceivedRefNumber = transactionReceivedRefNumber
        self.commitDate = commitDate
        self.commitParticular = commitParticular
        self.refDetails = refDetails
        self.commitAmount = commitAmount
        self.status = status

    def to_dict(self):
        return {
            "transactionCommitNumber": self.transactionCommitNumber,
            "projectNumber": self.projectNumber,
            "accountHeadId": self.accountHeadId,
            "transactionReceivedRefNumber": self.transactionReceivedRefNumber,
            "commitDate": self.commitDate,
            "commitParticular": self.commitParticular,
            "refDetails": self.refDetails,
            "commitAmount": self.commitAmount,
            "status": self.status
        }

class AccountHeadPaymentDTO:
    def __init__(
        self,
        transactionPaymentNumber=None,
        transactionCommitNumber=None,
        projectNumber=None,
        accountHeadId=None,
        paymentDate=None,
        paymentParticular=None,
        paymentRefDetails=None,
        paymentAmount=0.0,
        bmr=None,
        paymentStatus="PAID",
        bankTransactionNumber=None,
        bankTransactionDate=None
    ):
        self.transactionPaymentNumber = transactionPaymentNumber
        self.transactionCommitNumber = transactionCommitNumber
        self.projectNumber = projectNumber
        self.accountHeadId = accountHeadId
        self.paymentDate = paymentDate
        self.paymentParticular = paymentParticular
        self.paymentRefDetails = paymentRefDetails
        self.paymentAmount = paymentAmount
        self.bmr = bmr
        self.paymentStatus = paymentStatus
        self.bankTransactionNumber = bankTransactionNumber
        self.bankTransactionDate = bankTransactionDate

    def to_dict(self):
        return {
            "transactionPaymentNumber": self.transactionPaymentNumber,
            "transactionCommitNumber": self.transactionCommitNumber,
            "projectNumber": self.projectNumber,
            "accountHeadId": self.accountHeadId,
            "paymentDate": self.paymentDate,
            "paymentParticular": self.paymentParticular,
            "paymentRefDetails": self.paymentRefDetails,
            "paymentAmount": self.paymentAmount,
            "bmr": self.bmr,
            "paymentStatus": self.paymentStatus,
            "bankTransactionNumber": self.bankTransactionNumber,
            "bankTransactionDate": self.bankTransactionDate
        }
