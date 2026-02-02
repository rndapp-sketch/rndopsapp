# Copyright (c) 2025, rndops and contributors
# Consumer DTO for Consultancy Deposit Slip Update Messages

from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .dto import (
    ConsultancyDepositSlipDTO,
    ConsultancyDDetailsDTO,
    ConsultancyEDetailsDTO,
    ConsultancyTDetailsDTO,
    ConsultancyODetailsDTO,
)
from ..common.dto_base import (
    GstDetailsDTO,
    CreditDistributionSwfDTO,
    CreditDistributionPdfDTO,
    CreditDistributionDpfDTO,
    CreditDistributionIdfDTO,
    CreditDistributionStwfDTO,
)


@dataclass
class ConsultancyDepositSlipUpdateMessageDTO:
    """
    Kafka message envelope for Consultancy Deposit Slip updates.
    """
    schemaVersion: str = "1.0"
    eventType: str = "DEPOSIT_SLIP_CONSULTANCY"
    timestamp: str = ""
    data: Optional[ConsultancyDepositSlipDTO] = None

    @classmethod
    def from_dict(cls, message: Dict[str, Any]) -> 'ConsultancyDepositSlipUpdateMessageDTO':
        """
        Create ConsultancyDepositSlipUpdateMessageDTO from Kafka message dictionary.

        Args:
            message: Raw Kafka message dictionary

        Returns:
            ConsultancyDepositSlipUpdateMessageDTO instance
        """
        data_dict = message.get('data', {})

        # Parse nested GST details
        gst_details = None
        if 'gstDetails' in data_dict and data_dict['gstDetails']:
            gst_dict = data_dict['gstDetails']
            gst_details = GstDetailsDTO(
                cgstPercentage=gst_dict.get('cgstPercentage'),
                cgstAmount=gst_dict.get('cgstAmount'),
                sgstPercentage=gst_dict.get('sgstPercentage'),
                sgstAmount=gst_dict.get('sgstAmount'),
                igstPercentage=gst_dict.get('igstPercentage'),
                igstAmount=gst_dict.get('igstAmount'),
                totalGstAmount=gst_dict.get('totalGstAmount', 0.0)
            )

        # Parse credit distribution SWF
        swf = None
        if 'creditDistributionSwf' in data_dict and data_dict['creditDistributionSwf']:
            swf_dict = data_dict['creditDistributionSwf']
            swf = CreditDistributionSwfDTO(
                swfPercentage=swf_dict.get('swfPercentage', 0.0),
                swfAmount=swf_dict.get('swfAmount', 0.0)
            )

        # Parse credit distribution PDF list
        pdf_list = []
        if 'creditDistributionPdf' in data_dict and data_dict['creditDistributionPdf']:
            for pdf_dict in data_dict['creditDistributionPdf']:
                pdf_list.append(CreditDistributionPdfDTO(
                    employeeId=pdf_dict.get('employeeId', ''),
                    departmentId=pdf_dict.get('departmentId'),
                    pdfPercentage=pdf_dict.get('pdfPercentage', 0.0),
                    pdfAmount=pdf_dict.get('pdfAmount', 0.0)
                ))

        # Parse credit distribution DPF list
        dpf_list = []
        if 'creditDistributionDpf' in data_dict and data_dict['creditDistributionDpf']:
            for dpf_dict in data_dict['creditDistributionDpf']:
                dpf_list.append(CreditDistributionDpfDTO(
                    departmentId=dpf_dict.get('departmentId'),
                    dpfPercentage=dpf_dict.get('dpfPercentage', 0.0),
                    dpfAmount=dpf_dict.get('dpfAmount', 0.0)
                ))

        # Parse credit distribution IDF
        idf = None
        if 'creditDistributionIdf' in data_dict and data_dict['creditDistributionIdf']:
            idf_dict = data_dict['creditDistributionIdf']
            idf = CreditDistributionIdfDTO(
                idfPercentage=idf_dict.get('idfPercentage', 0.0),
                idfAmount=idf_dict.get('idfAmount', 0.0)
            )

        # Parse credit distribution STWF
        stwf = None
        if 'creditDistributionStwf' in data_dict and data_dict['creditDistributionStwf']:
            stwf_dict = data_dict['creditDistributionStwf']
            stwf = CreditDistributionStwfDTO(
                stwfPercentage=stwf_dict.get('stwfPercentage', 0.0),
                stwfAmount=stwf_dict.get('stwfAmount', 0.0)
            )

        # Parse ECS dates
        ecs_dates = data_dict.get('ecsDates', [])
        if ecs_dates is None:
            ecs_dates = []

        # Parse consultancy D details
        consultancy_d = None
        if 'consultancyDDetails' in data_dict and data_dict['consultancyDDetails']:
            cd_dict = data_dict['consultancyDDetails']
            consultancy_d = ConsultancyDDetailsDTO(
                gstTdsPercentage=cd_dict.get('gstTdsPercentage', 0.0),
                gstTdsAmount=cd_dict.get('gstTdsAmount', 0.0),
                amountReceivedAfterGstTds=cd_dict.get('amountReceivedAfterGstTds', 0.0),
                totalCostX=cd_dict.get('totalCostX', 0.0),
                consultancyChargeYPercentage=cd_dict.get('consultancyChargeYPercentage', 0.0),
                consultancyChargeY=cd_dict.get('consultancyChargeY', 0.0),
                operationalChargeZPercentage=cd_dict.get('operationalChargeZPercentage', 0.0),
                operationalChargeZ=cd_dict.get('operationalChargeZ', 0.0),
                overHeadYPercentage=cd_dict.get('overHeadYPercentage', 0.0),
                overHeadYAmount=cd_dict.get('overHeadYAmount', 0.0),
                overHeadZPercentage=cd_dict.get('overHeadZPercentage', 0.0),
                overHeadZAmount=cd_dict.get('overHeadZAmount', 0.0),
                instituteSharePercentage=cd_dict.get('instituteSharePercentage', 0.0),
                instituteShare=cd_dict.get('instituteShare', 0.0),
                totalOverHeadInstituteShare=cd_dict.get('totalOverHeadInstituteShare', 0.0)
            )

        # Parse consultancy E details
        consultancy_e = None
        if 'consultancyEDetails' in data_dict and data_dict['consultancyEDetails']:
            ce_dict = data_dict['consultancyEDetails']
            consultancy_e = ConsultancyEDetailsDTO(
                consultancyFeeX_trainingFee=ce_dict.get('consultancyFeeX_trainingFee', 0.0)
            )

        # Parse consultancy T details
        consultancy_t = None
        if 'consultancyTDetails' in data_dict and data_dict['consultancyTDetails']:
            ct_dict = data_dict['consultancyTDetails']
            consultancy_t = ConsultancyTDetailsDTO(
                consultancyFeeX_trainingFee=ct_dict.get('consultancyFeeX_trainingFee', 0.0)
            )

        # Parse consultancy O (Other Event) details
        consultancy_o = None
        if 'consultancyODetails' in data_dict and data_dict['consultancyODetails']:
            co_dict = data_dict['consultancyODetails']
            consultancy_o = ConsultancyODetailsDTO(
                consultancyFeeX_trainingFee=co_dict.get('consultancyFeeX_trainingFee', 0.0)
            )

        # Create ConsultancyDepositSlipDTO from data
        deposit_slip_dto = ConsultancyDepositSlipDTO(
            projectNumber=data_dict.get('projectNumber', ''),
            fundReceivedRefNumber=data_dict.get('fundReceivedRefNumber', 0),
            depositSlipRefNumFab=data_dict.get('depositSlipRefNumFab', ''),
            slipNumber=data_dict.get('slipNumber', ''),
            category=data_dict.get('category', 'CONSULTANCY_D'),
            ecsAccountNo=data_dict.get('ecsAccountNo', ''),
            bankName=data_dict.get('bankName', ''),
            bmrNumber=data_dict.get('bmrNumber', ''),
            amountReceived=data_dict.get('amountReceived', 0.0),
            amountInclusiveGst=data_dict.get('amountInclusiveGst', 0.0),
            gstType=data_dict.get('gstType', 'NOGST'),
            finalGstAmount=data_dict.get('finalGstAmount', 0.0),
            finalTotalAmount=data_dict.get('finalTotalAmount', 0.0),
            totalOverheadPercentage=data_dict.get('totalOverheadPercentage', 0.0),
            totalOverheadAmount=data_dict.get('totalOverheadAmount', 0.0),
            netProjectAmount=data_dict.get('netProjectAmount', 0.0),
            depositDate=data_dict.get('depositDate', ''),
            createdAt=data_dict.get('createdAt', ''),
            updatedAt=data_dict.get('updatedAt', ''),
            createdBy=data_dict.get('createdBy', ''),
            updatedBy=data_dict.get('updatedBy', ''),
            status=data_dict.get('status', 'APPROVED'),
            ecsDates=ecs_dates,
            gstDetails=gst_details,
            creditDistributionSwf=swf,
            creditDistributionPdf=pdf_list,
            creditDistributionDpf=dpf_list,
            creditDistributionIdf=idf,
            creditDistributionStwf=stwf,
            consultancyDDetails=consultancy_d,
            consultancyEDetails=consultancy_e,
            consultancyTDetails=consultancy_t,
            consultancyODetails=consultancy_o,
        )

        return cls(
            schemaVersion=message.get('schemaVersion', '1.0'),
            eventType=message.get('eventType', 'DEPOSIT_SLIP_CONSULTANCY'),
            timestamp=message.get('timestamp', ''),
            data=deposit_slip_dto
        )
