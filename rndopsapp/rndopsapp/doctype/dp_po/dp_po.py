# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, money_in_words


class dp_po(Document):
    def validate(self):
        self._calculate_row_totals()
        self._calculate_grand_total()
        self._set_amount_in_words()

    def _calculate_row_totals(self):
        for row in self.get("items", []):
            base = flt(row.qty) * flt(row.unit_price)
            row.total = base - flt(row.discount) + flt(row.gst)

    def _calculate_grand_total(self):
        self.grand_total = sum(flt(row.total) for row in self.get("items", []))

    def _set_amount_in_words(self):
        if self.grand_total:
            self.amount_in_words = money_in_words(self.grand_total)


# =============================================================================
# API ENDPOINTS
# =============================================================================

DOCTYPE = "dp_po"

DEFAULT_TERMS = """<ol>
  <li>
    <strong>Reference for Correspondence:</strong> Our P.O. No. indicated above must be mentioned invariably in all future
    Correspondences such as Order Acknowledgement, Bank Guarantee, Proforma Invoice, Challan, Final Bill, Money receipt,
    Packages, etc. relating to this Order.
  </li>
  <li>
    <strong>Vendor Profile:</strong> The vendor is requested to fill in form VP (1), enclosed herewith, and submit the
    same along with the bills/invoice. This is mandatory as payment will be made by ECS only.
  </li>
  <li>
    <strong>Price:</strong> Price inclusive of all duties and taxes and F.O.R., IIT Guwahati.
  </li>
  <li>
    <strong>Delivery:</strong>
    <ol type="a">
      <li><strong>Time Limit:</strong> Maximum within 16-18 weeks from the date of receipt of this Purchase Order.</li>
      <li>
        <strong>Safe Delivery responsibility of supplier:</strong> All aspects of safe delivery shall be the exclusive
        responsibility of the vendor. At the destination site, the package will be opened only in the presence of IITG
        user/representative and vendor's representative. The intact condition of the package and the seal/indicators for
        not being tampered with shall form the basis for certifying the receipt in good condition.
      </li>
      <li>
        <strong>Insurance:</strong> The supplier is to establish &lsquo;All Risk Transit Insurance&rsquo; coverage till
        door delivery at IIT Guwahati.
      </li>
      <li><strong>Part Delivery:</strong> Part delivery is not allowed.</li>
    </ol>
  </li>
  <li>
    <strong>Penalty for Delayed Delivery:</strong> The date of delivery shall be strictly adhered to, except in cases of
    Force Majeure or extension of the delivery date duly approved by IIT Guwahati. In the event of delayed delivery and
    acceptance by the end user, the vendor shall be liable for a penalty deduction at the rate of 0.5% per week or part
    thereof of the value of the entire consignment, subject to a maximum of 10% (ten percent).<br><br>
    For the purpose of this clause, part of a week shall be treated as a full week. In case of delayed delivery, IIT
    Guwahati reserves the right not to accept the consignment.
  </li>
  <li>
    <strong>Payment:</strong> 100% payment against delivery, installation, and acceptance of ordered goods in good
    condition at IIT Guwahati.
  </li>
  <li>
    <strong>Warranty:</strong> 01 year from the date of delivery, installation, and acceptance of ordered goods in good
    condition at IIT Guwahati. Warranty certificate will have to be enclosed with the equipment.
  </li>
  <li>
    <strong>GST Deduction:</strong> GST Deduction at source as per Order/notification of the Govt. of India will be
    applicable.
  </li>
  <li>
    <strong>Bank Charges:</strong> All Bank and other charges to the supplier&rsquo;s account.
  </li>
  <li>
    <strong>Performance Bank Guarantee:</strong> The supplier shall furnish an unconditional Performance Bank Guarantee
    (PBG) in the form of a Fixed Deposit or Bank Guarantee (including e-Bank Guarantee) as per the format enclosed at
    ANNEXURE&ndash;II issued by any Commercial Bank of India, as per the prescribed slab indicated below. In case of
    foreign procurement, submission of the PBG by the local agent shall be mandatory. Where the PBG is issued by a
    foreign bank, the same shall be duly endorsed by its corresponding bank in India.<br><br>
    The validity of the PBG shall cover the entire warranty period plus an additional period of two (02) months from the
    date of installation/commissioning of the equipment.<br><br>
    In the event of failure to submit the PBG within the stipulated timeframe, IIT Guwahati reserves the right to
    withhold or deduct an amount equivalent to the PBG value from the payment due to the supplier, without requiring
    further consent. Such amount shall be retained until submission of the requisite PBG.<br><br>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;width:60%;text-align:center;">
      <thead>
        <tr style="background-color:#f2f2f2;">
          <th>Slab</th>
          <th>PO / Contract Value</th>
          <th>PBG Rate</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>1</td>
          <td>&#8377; 5,00,000/- to &#8377; 15,00,000/-</td>
          <td>3%</td>
        </tr>
        <tr>
          <td>2</td>
          <td>&#8377; 15,00,000/- to &#8377; 25,00,000/-</td>
          <td>4%</td>
        </tr>
        <tr>
          <td>3</td>
          <td>Above &#8377; 25,00,000/-</td>
          <td>5%</td>
        </tr>
      </tbody>
    </table>
    <br>
    By submitting the PBG, the vendor is understood to have guaranteed that,
    <ol type="i">
      <li>The Purchase Order (PO) shall be executed as per the terms and conditions mentioned therein.</li>
      <li>The equipment shall function satisfactorily for a period up to 60 days after the warranty period.</li>
      <li>The equipment and components are free from poor workmanship, bad quality, and faulty designs.</li>
      <li>The vendor shall at his/their own cost rectify/replace the defects, if any, during the guarantee period.</li>
      <li>The guarantee is to the extent as per the slabs mentioned in the pre-page.</li>
    </ol>
    <strong>Condition for invoking PBG:</strong> In case of failure to comply with the guarantees above, IITG may
    terminate the contract/purchase order in whole or in part and forfeit the PBG. In addition, IITG may, at its
    discretion, procure upon such terms and in such manner as it deems appropriate, goods similar to the undelivered
    items/products, and the defaulting supplier/vendor shall be liable to compensate IITG for any extra expenditure
    involved.
  </li>
  <li>
    <strong>Termination for default:</strong>
    <ol type="i">
      <li>If the supplier fails to deliver any or all the services within the time period(s) specified in the purchase
        order or any extension thereof granted by IITG.</li>
      <li>If the supplier fails to perform any other obligation(s) under the contract.</li>
      <li>
        If the equipment or any of its components is found to have poor workmanship, faulty designs, poor performance,
        and bad quality of materials used. Under the above circumstances, the Competent Authority, IITG may terminate
        the contract/purchase order in whole or in part and forfeit the EMD/PBG as applicable or impose any other
        penalty as deemed fit. In addition to the above, IITG may at its discretion also take the following action:
        IITG may procure, upon such terms and in such manner as it deems appropriate, goods similar to the undelivered
        items/products and the defaulting supplier shall be liable to compensate IITG for any extra expenditure
        involved.
      </li>
    </ol>
  </li>
  <li>
    <strong>Applicable Law:</strong>
    <ol type="i">
      <li>The contract shall be governed by the laws and procedures established by Govt. of India and subject to
        exclusive jurisdiction of Competent Court and Forum in Guwahati only.</li>
      <li>Any dispute arising out of this purchase shall be referred to the Director, IIT Guwahati. If either of the
        parties is dissatisfied with the decision, the dispute shall be referred to the decision of an Arbitrator, who
        should be acceptable to both the parties, and shall be appointed by the Director of IITG. The decision of such
        Arbitrator shall be final and binding on both the parties.</li>
    </ol>
  </li>
</ol>"""


@frappe.whitelist()
def get_dp_po_fields(doc_name=None):
    """Return dp_po field metadata, prefill data, and link options."""
    meta = frappe.get_meta(DOCTYPE)

    fields = []
    for f in meta.get("fields"):
        field_data = {
            "fieldname": f.fieldname,
            "label": f.label,
            "fieldtype": f.fieldtype,
            "options": f.options,
            "mandatory": f.reqd,
            "hidden": f.hidden,
            "read_only": f.read_only,
            "default": f.default,
            "description": f.description,
        }
        if f.fieldtype == "Table" and f.options:
            child_meta = frappe.get_meta(f.options)
            field_data["child_fields"] = [
                {
                    "fieldname": cf.fieldname,
                    "label": cf.label,
                    "fieldtype": cf.fieldtype,
                    "mandatory": cf.reqd,
                    "in_list_view": cf.in_list_view,
                }
                for cf in child_meta.fields
            ]
        fields.append(field_data)

    prefill_data = {}
    if doc_name:
        try:
            doc = frappe.get_doc(DOCTYPE, doc_name)
            prefill_data = doc.as_dict()
        except Exception:
            pass
    else:
        prefill_data["terms_and_conditions"] = DEFAULT_TERMS

    return {"fields": fields, "prefill_data": prefill_data}


@frappe.whitelist()
def save_dp_po_data(data):
    """Create or update a dp_po document from a JSON payload."""
    try:
        if isinstance(data, str):
            data = json.loads(data)

        doc_name = data.get("name")
        if doc_name and frappe.db.exists(DOCTYPE, doc_name):
            doc = frappe.get_doc(DOCTYPE, doc_name)
        else:
            doc = frappe.new_doc(DOCTYPE)

        meta = frappe.get_meta(DOCTYPE)
        deferred_tables = []

        for fieldname, value in data.items():
            if fieldname in ("name", "doctype", "docstatus"):
                continue
            if not meta.has_field(fieldname):
                continue
            df = meta.get_field(fieldname)
            if df.fieldtype == "Table":
                deferred_tables.append((fieldname, value))
            elif value not in (None, ""):
                doc.set(fieldname, value)

        doc.flags.ignore_permissions = True
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)

        for fieldname, rows in deferred_tables:
            doc.set(fieldname, [])
            for row in (rows or []):
                row_dict = dict(row)
                for sf in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
                    row_dict.pop(sf, None)
                doc.append(fieldname, row_dict)

        doc.save(ignore_permissions=True)
        frappe.db.commit()

        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "DP PO Save Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def generate_dp_po_from_sanction_sheet(dp_docname, sanction_sheet_name):
    """
    Create a dp_po document pre-populated from the Direct Purchase and its
    linked Sanction Sheet.  Returns the new dp_po docname.
    """
    try:
        dp_doc = frappe.get_doc("Direct Purchase", dp_docname)
        ss_doc = frappe.get_doc("sanction_sheet", sanction_sheet_name)

        # Check if a dp_po already exists for this Direct Purchase
        existing = frappe.db.get_value(DOCTYPE, {"direct_purchase_ref": dp_docname}, "name")
        if existing:
            return {"status": "success", "docname": existing, "message": "dp_po already exists."}

        doc = frappe.new_doc(DOCTYPE)
        doc.direct_purchase_ref = dp_docname
        doc.sanction_sheet_ref = sanction_sheet_name

        # Applicant details from Direct Purchase
        doc.applicant = (
            dp_doc.applying_for_name
            if dp_doc.get("register_for") == "Other"
            else dp_doc.get("applicant_name")
        )
        doc.department = (
            dp_doc.applying_for_department
            if dp_doc.get("register_for") == "Other"
            else dp_doc.get("applicant_department")
        )
        doc.project_no = dp_doc.get("project_no") or ""
        doc.file_no = dp_doc.get("file_no") or ""

        # Account head — resolve label from Budget Head
        account_head_id = dp_doc.get("account_head") or ""
        if account_head_id:
            bh_label = frappe.db.get_value("Budget Head", account_head_id, "budget_head")
            doc.account_head = bh_label or account_head_id
        else:
            doc.account_head = account_head_id

        # Funding agency from Project Registration
        if dp_doc.get("project_no"):
            funding_agent = frappe.db.get_value(
                "Project Registration", {"project_no": dp_doc.project_no}, "funding_agen"
            )
            funding_agency = (
                frappe.db.get_value("fundingagency_", funding_agent, "funding_agency_name")
                if funding_agent
                else None
            )
            doc.funding_agency = funding_agency or ""

        # Grand total from Sanction Sheet
        doc.grand_total = flt(ss_doc.get("ss_grand_total") or dp_doc.get("total_estimate"))

        # Copy items from Sanction Sheet child table (table_bttk)
        for row in ss_doc.get("table_bttk", []):
            doc.append("items", {
                "item_name": row.get("item_name") or "",
                "make": row.get("item_make") or "",
                "model": row.get("item_model") or "",
                "qty": flt(row.get("item_quantity")),
                "unit_price": flt(row.get("item_unit_price")),
                "discount": flt(row.get("item_discount")),
                "gst": flt(row.get("item_gst")),
                "total": flt(row.get("dp_total_price")),
            })

        # Default terms
        doc.terms_and_conditions = DEFAULT_TERMS

        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

        return {"status": "success", "docname": doc.name}

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "DP PO Generate Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def get_dp_po_by_direct_purchase(dp_docname):
    """Return the dp_po docname linked to a Direct Purchase, if any."""
    try:
        doc_name = frappe.db.get_value(DOCTYPE, {"direct_purchase_ref": dp_docname}, "name")
        if doc_name:
            doc = frappe.get_doc(DOCTYPE, doc_name)
            return {"status": "success", "docname": doc_name, "data": doc.as_dict()}
        return {"status": "success", "docname": None, "data": None}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "DP PO Fetch Error")
        return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=False)
def ref_details_id(commitAmount=None, budgetHead=None, projectName=None, frapAppId=None):
    """Proxy to external account-head-commit ref-details API."""
    import requests

    if not commitAmount:
        frappe.throw(_("commitAmount is required"), frappe.MandatoryError)
    if not projectName:
        frappe.throw(_("projectName is required"), frappe.MandatoryError)
    if not frapAppId:
        frappe.throw(_("frapAppId is required"), frappe.MandatoryError)

    params = {
        "commitAmount": commitAmount,
        "projectNumber": projectName,
        "frapAppId": frapAppId,
    }
    if budgetHead:
        params["budgetHead"] = budgetHead

    url = "http://172.16.134.81:18080/api/account-head-commit/ref-details"

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return {"refDetailsId": data.get("refDetailsId")}
    except requests.exceptions.RequestException as e:
        frappe.log_error(str(e), "ref_details_id API Error")
        frappe.throw(_("Failed to fetch ref details: {0}").format(str(e)))
