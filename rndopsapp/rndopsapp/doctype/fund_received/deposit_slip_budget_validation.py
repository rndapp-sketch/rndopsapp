# Copyright (c) 2026, rndops and contributors
# Shared Overhead/GST <-> Budget Head reconciliation for Deposit Slips.
# See DEPOSIT_SLIP_OVERHEAD_GST_BUDGET_HEAD_IMPLEMENTATION.md (repo root) for the full spec.

import frappe
from frappe import _
from rndopsapp.rndopsapp.kafka.utils import resolve_budget_head_name

OVERHEAD_BUDGET_HEAD_LABEL = "Overhead"
GST_BUDGET_HEAD_LABEL = "GST"
AMOUNT_TOLERANCE = 0.01

# Saved-doc field lookup, keyed by the actual Frappe doctype name.
OVERHEAD_FIELD_BY_DOCTYPE = {
	"Research Deposit Slip": "overhead_amount",
	"Research Consultancy Deposit Slip": "overhead_amount",
	"D Consultancy Deposit Slip": "total_overhead_amount",
	"E Non Routine Deposit Slip": "overhead_amount",
	"T Testing Deposit Slip": "overhead_amount",
	"Other Event Deposit Slip": "overhead_amount",
}

GST_FIELD_BY_DOCTYPE = {
	"Research Consultancy Deposit Slip": "total_gst",
	"D Consultancy Deposit Slip": "total_gst",
	"E Non Routine Deposit Slip": "total_gst",
	"T Testing Deposit Slip": "total_gst",
	"Other Event Deposit Slip": "gst_final",
	# "Research Deposit Slip" intentionally absent — no GST concept for that type.
}

# Raw-payload lookup, keyed by the frontend `deposit_slip_type` string used in
# FundReceivedDetails.tsx / perform_fund_received_action's `deposit_slip_type` param.
OVERHEAD_FIELD_BY_TYPE = {
	"research_deposit_slip": "overhead_amount",
	"research_consultancy": "overhead_amount",
	"d_consultancy": "total_overhead_amount",
	"e_non_routine": "overhead_amount",
	"t_testing": "overhead_amount",
	"other_event": "overhead_amount",
}

GST_FIELD_BY_TYPE = {
	"research_consultancy": "total_gst",
	"d_consultancy": "total_gst",
	"e_non_routine": "total_gst",
	"t_testing": "total_gst",
	"other_event": "gst_final",
	# "research_deposit_slip" intentionally absent — no GST concept for that type.
}


def _flt(value):
	try:
		return float(value or 0)
	except (TypeError, ValueError):
		return 0.0


def resolve_budget_head_amount(rows, label):
	"""
	Sum `amount_received` across every budget-breakup row in `rows` whose
	`account_head` resolves (via Budget Head.budget_head, case-insensitive)
	to `label` (e.g. "Overhead" or "GST").

	`rows` is a budget breakup child table — either a Fund Received's
	`received_amt_breakup` or a Deposit Slip's `fund_budget_breakup` mirror.
	A Fund Received doc is also accepted for backwards compatibility.

	Returns (funded: bool, total_amount: float). `funded` is True as soon as at
	least one matching row exists, even if its amount happens to be 0 — a row
	that was drained to 0 by a prior transfer (see allocate_deposit_slip_budget_heads)
	still counts as "the head exists on this breakup".
	"""
	# Backwards compat: accept a Fund Received doc directly.
	if rows is not None and hasattr(rows, "received_amt_breakup"):
		rows = rows.received_amt_breakup

	if not rows:
		return False, 0.0

	total = 0.0
	matched = False
	label_lower = label.strip().lower()

	for row in rows:
		account_head = row.account_head
		if not account_head:
			continue

		# account_head may hold a docname, a numeric Budget Head id, or the raw
		# label — resolve_budget_head_name() normalises all three.
		resolved = resolve_budget_head_name(account_head)
		head_label = frappe.db.get_value("Budget Head", resolved, "budget_head") if resolved else None
		if not head_label:
			head_label = account_head

		if str(head_label).strip().lower() == label_lower:
			matched = True
			total += _flt(row.amount_received)

	return matched, total


def _check_one(label, doc_amount, fr_funded, fr_total):
	"""
	Returns an error message string, or None if this item is fine.
	Mirrors the 3-outcome table in §3.1 of the implementation doc, plus the
	genuine-mismatch case for when both sides have a value.
	"""
	doc_amount = _flt(doc_amount)
	fr_total = _flt(fr_total)

	if not fr_funded and doc_amount <= 0:
		# Rule 1 — nothing on either side, nothing to reconcile.
		return None

	if fr_funded and doc_amount <= 0:
		# Rule 2 — Fund Received already set money aside, but this Deposit
		# Slip isn't accounting for it. Block immediately, no modal.
		return _(
			"Fund Received has {0} allocated to the '{1}' budget head, but this "
			"Deposit Slip does not show any {1} amount. Correct the Deposit Slip "
			"before submitting."
		).format(frappe.utils.fmt_money(fr_total), label)

	if not fr_funded and doc_amount > 0:
		# Defensive fallback — this combination should already have been
		# resolved via allocate_deposit_slip_budget_heads (Rule 3) before this
		# function is ever reached. If it wasn't, treat it as a mismatch.
		return _(
			"This Deposit Slip requires {0} of {1}, but Fund Received has no '{1}' "
			"budget head allocation yet. Use the budget head allocation step "
			"before submitting."
		).format(frappe.utils.fmt_money(doc_amount), label)

	if abs(fr_total - doc_amount) > AMOUNT_TOLERANCE:
		return _(
			"Deposit Slip {1} ({0}) does not match the '{1}' budget head "
			"allocation on Fund Received ({2}). Update the allocation and try "
			"again."
		).format(frappe.utils.fmt_money(doc_amount), label, frappe.utils.fmt_money(fr_total))

	return None


def validate_overhead_gst_budget_heads(overhead_amount, gst_amount, breakup_rows, has_gst_field=True):
	"""
	Core comparison, independent of whether a Deposit Slip doc exists yet.
	Raises frappe.throw (via frappe.ValidationError) if either the Overhead
	or GST reconciliation fails. has_gst_field=False skips the GST check
	entirely (Research Deposit Slip has no GST concept).

	`breakup_rows` is the budget breakup to reconcile against — either a
	Deposit Slip's own `fund_budget_breakup` snapshot or a Fund Received's
	live `received_amt_breakup` (a Fund Received doc is also accepted).
	"""
	errors = []

	overhead_funded, overhead_total = resolve_budget_head_amount(breakup_rows, OVERHEAD_BUDGET_HEAD_LABEL)
	overhead_error = _check_one(OVERHEAD_BUDGET_HEAD_LABEL, overhead_amount, overhead_funded, overhead_total)
	if overhead_error:
		errors.append(overhead_error)

	if has_gst_field:
		gst_funded, gst_total = resolve_budget_head_amount(breakup_rows, GST_BUDGET_HEAD_LABEL)
		gst_error = _check_one(GST_BUDGET_HEAD_LABEL, gst_amount, gst_funded, gst_total)
		if gst_error:
			errors.append(gst_error)

	if errors:
		frappe.throw("<br>".join(errors), title=_("Budget Head Reconciliation Failed"))


def validate_overhead_gst_budget_heads_for_doc(ds_doc, fr_doc):
	"""
	Wrapper for the call sites where a saved Deposit Slip doc already exists.

	Reconciles against the Deposit Slip's OWN `fund_budget_breakup` snapshot
	when it has one, falling back to the Fund Received's live
	`received_amt_breakup` otherwise (slips created before that mirror field
	existed).

	Why the snapshot wins: the mirror is the breakup as it stood when this slip
	was created — exactly what was validated at submission time and what the
	slip's own Kafka payload carries. The live Fund Received breakup can be
	rewritten afterwards by anything else touching the document (historically,
	a replayed Kafka message reverting an Overhead/GST allocation), which would
	fail an otherwise-consistent slip at approval time through no fault of the
	slip.
	"""
	doctype = ds_doc.doctype
	overhead_field = OVERHEAD_FIELD_BY_DOCTYPE.get(doctype)
	gst_field = GST_FIELD_BY_DOCTYPE.get(doctype)

	overhead_amount = ds_doc.get(overhead_field) if overhead_field else 0
	gst_amount = ds_doc.get(gst_field) if gst_field else 0

	breakup_rows = ds_doc.get("fund_budget_breakup") if ds_doc.meta.has_field("fund_budget_breakup") else None
	if not breakup_rows:
		breakup_rows = fr_doc.received_amt_breakup if fr_doc else None

	validate_overhead_gst_budget_heads(
		overhead_amount, gst_amount, breakup_rows, has_gst_field=bool(gst_field)
	)


def validate_overhead_gst_budget_heads_for_payload(deposit_slip_type, deposit_slip_data, fr_doc):
	"""
	Wrapper for the immediate submission call site (perform_fund_received_action,
	"Pending HoS Approval" branch), where only the raw `deposit_slip_data` dict
	is available and no Deposit Slip doc has been created yet.

	Reconciles against the Fund Received's live breakup — correct here, because
	no Deposit Slip snapshot exists yet and the slip about to be created will
	take its mirror from exactly this breakup.
	"""
	if not deposit_slip_type or not deposit_slip_data:
		return

	key = str(deposit_slip_type).strip().lower()
	overhead_field = OVERHEAD_FIELD_BY_TYPE.get(key)
	gst_field = GST_FIELD_BY_TYPE.get(key)

	overhead_amount = deposit_slip_data.get(overhead_field) if overhead_field else 0
	gst_amount = deposit_slip_data.get(gst_field) if gst_field else 0

	validate_overhead_gst_budget_heads(
		overhead_amount,
		gst_amount,
		fr_doc.received_amt_breakup if fr_doc else None,
		has_gst_field=bool(gst_field),
	)
