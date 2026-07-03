"""
Diagnostic + fix for ICSS 2026061710001203 routing to Associate Dean incorrectly.

Run:
    bench --site prornd.local execute rndopsapp.fix_icss_state.check
    bench --site prornd.local execute rndopsapp.fix_icss_state.fix
"""

import frappe
from frappe.utils import flt

DOCNAME = "2026061710001203"
DOCTYPE = "Indent Cum Sanction Sheet"
HOS_THRESHOLD = 100_000


def check():
    row = frappe.db.sql(
        """
        SELECT name, workflow_state, docstatus, icss_indent_type,
               icss_grand_total, icss_repair_grand_total, icss_amc_grand_total,
               sub_doctype_reference
        FROM `tabIndent Cum Sanction Sheet`
        WHERE name = %s
        """,
        (DOCNAME,),
        as_dict=True,
    )
    if not row:
        print(f"Document '{DOCNAME}' not found.")
        return

    r = row[0]
    print("=" * 60)
    print(f"ICSS: {DOCNAME}")
    print("=" * 60)
    print(f"  workflow_state        : {repr(r.workflow_state)}")
    print(f"  docstatus             : {r.docstatus}")
    print(f"  icss_indent_type      : {repr(r.icss_indent_type)}")
    print(f"  sub_doctype_reference : {repr(r.sub_doctype_reference)}")
    print(f"  icss_grand_total      : {r.icss_grand_total}")
    print(f"  icss_repair_grand_total: {r.icss_repair_grand_total}")
    print(f"  icss_amc_grand_total  : {r.icss_amc_grand_total}")

    # Fetch Rate Contract grand total if applicable
    if r.icss_indent_type == "Rate Contract Purchase" and r.sub_doctype_reference:
        rc_total = frappe.db.get_value(
            "Rate Contract", r.sub_doctype_reference, "rate_contract_grand_total"
        )
        print(f"\n  Linked Rate Contract  : {r.sub_doctype_reference}")
        print(f"  rate_contract_grand_total: {rc_total}")
        routing_amount = flt(rc_total)
    elif r.icss_indent_type == "Repair/ Repleacement":
        routing_amount = flt(r.icss_repair_grand_total)
    elif r.icss_indent_type == "Annual Maintenance Contract":
        routing_amount = flt(r.icss_amc_grand_total)
    else:
        routing_amount = flt(r.icss_grand_total)

    print(f"\n  Routing amount        : {routing_amount}")
    print(f"  Threshold             : {HOS_THRESHOLD}")

    if routing_amount > HOS_THRESHOLD:
        print(f"  → SHOULD GO TO: Pending Dean Approval")
    else:
        print(f"  → SHOULD GO TO: Pending Associate Dean  (amount is 0 or below threshold)")
    print("=" * 60)


def check_rc():
    """Check rate_contract_grand_total vs computed value for the linked Rate Contract."""
    rc_name = "2026061711RATE001204"

    row = frappe.db.sql(
        """
        SELECT
            name, workflow_state, docstatus,
            rate_contract_total,
            rate_contract_packing,
            rate_contract_grand_total
        FROM `tabRate Contract`
        WHERE name = %s
        """,
        (rc_name,),
        as_dict=True,
    )
    if not row:
        print(f"Rate Contract '{rc_name}' not found.")
        return

    r = row[0]
    print("=" * 60)
    print(f"Rate Contract: {rc_name}")
    print("=" * 60)
    print(f"  workflow_state           : {repr(r.workflow_state)}")
    print(f"  docstatus                : {r.docstatus}")
    print(f"  rate_contract_total      : {r.rate_contract_total}")
    print(f"  rate_contract_packing    : {r.rate_contract_packing}")
    print(f"  rate_contract_grand_total: {r.rate_contract_grand_total}")

    # Recompute from items
    items = frappe.db.sql(
        """
        SELECT unit_rate, quantity, discount_percentage, gst_percentage, amount
        FROM `tabRate Contract Purchase Item Detail`
        WHERE parent = %s
        ORDER BY idx
        """,
        (rc_name,),
        as_dict=True,
    )
    print(f"\n  Items ({len(items)} rows):")
    computed_total = 0
    for i, it in enumerate(items, 1):
        base     = (it.unit_rate or 0) * (it.quantity or 0)
        after_d  = base * (1 - (it.discount_percentage or 0) / 100)
        with_gst = after_d * (1 + (it.gst_percentage or 0) / 100)
        computed_total += with_gst
        print(f"    Row {i}: rate={it.unit_rate} qty={it.quantity} "
              f"disc={it.discount_percentage}% gst={it.gst_percentage}% "
              f"stored_amount={it.amount}  recomputed={round(with_gst, 2)}")

    from frappe.utils import flt
    computed_grand = computed_total + flt(r.rate_contract_packing)
    print(f"\n  Stored  rate_contract_total      : {r.rate_contract_total}")
    print(f"  Recomputed items total           : {round(computed_total, 2)}")
    print(f"  Stored  rate_contract_grand_total: {r.rate_contract_grand_total}")
    print(f"  Recomputed grand total           : {round(computed_grand, 2)}")

    if abs(flt(r.rate_contract_grand_total) - computed_grand) < 0.01:
        print(f"\n  ✓ Stored grand total matches recomputed value.")
    else:
        print(f"\n  ✗ MISMATCH — stored {r.rate_contract_grand_total} vs recomputed {round(computed_grand, 2)}")
    print("=" * 60)


def fix():
    row = frappe.db.sql(
        """SELECT workflow_state, docstatus, icss_indent_type, sub_doctype_reference
           FROM `tabIndent Cum Sanction Sheet` WHERE name = %s""",
        (DOCNAME,),
        as_dict=True,
    )
    if not row:
        print(f"Document '{DOCNAME}' not found.")
        return

    r = row[0]
    current = r.workflow_state

    # Determine correct target state
    if r.icss_indent_type == "Rate Contract Purchase" and r.sub_doctype_reference:
        rc_total = frappe.db.get_value(
            "Rate Contract", r.sub_doctype_reference, "rate_contract_grand_total"
        )
        routing_amount = flt(rc_total)
    else:
        routing_amount = 0

    target = "Pending Dean Approval" if routing_amount > HOS_THRESHOLD else "Pending Associate Dean"
    print(f"  routing_amount: {routing_amount}  →  correct state: {target}")

    if current == target:
        print(f"  Already at '{target}' — nothing to do.")
        return

    frappe.db.sql(
        "UPDATE `tabIndent Cum Sanction Sheet` SET workflow_state = %s WHERE name = %s",
        (target, DOCNAME),
    )
    frappe.db.commit()
    print(f"  workflow_state: {repr(current)} → '{target}'")
