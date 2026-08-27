# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Loan Settlement — settling an outstanding project loan out of an incoming Fund Received.

Flow (see docs/loan-settlement-implementation.md in prornd-ui):
  1. The Fund Received form shows a modal listing the project's unsettled loans
     (get_active_loan_for_project).
  2. The user picks loans + Full/Partial amounts; save_loan_settlement_requests creates
     one Loan Settlement doc per loan, BEFORE Fund Received is submitted.
  3. Fund Received submission links itself to those docs (fund_received.py) — no Kafka.
  4. staff, RnD later fills in remarks + settlement mode; perform_loan_settlement_action
     transitions to "Processed" and THAT is when the Kafka event is published, so the
     payload carries every field including mode/remarks.

Outstanding balances are always read live from the Accounts service, never recomputed
here — it is the system of record and also sees settlements made through other channels.
"""

import json
from concurrent.futures import ThreadPoolExecutor

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

# Accounts service (ledger) base — same host as commitPayment.LEDGER_API_BASE_URL
ACCOUNTS_API_BASE_URL = "http://172.16.135.27:18083/api"

LOAN_DETAILS_BY_PROJECT_URL = ACCOUNTS_API_BASE_URL + "/loan-details/project/{project_number}"
LOAN_SETTLEMENT_SUMMARY_URL = ACCOUNTS_API_BASE_URL + "/loan-settlement/loan/{loan_number}/summary"

REQUEST_TIMEOUT = 10

# A loan is "still open" if its status is anything other than SETTLED.
SETTLED_STATUS = "SETTLED"

STAFF_ROLES = ["staff, RnD", "RnD Staff", "R&D Staff", "System Manager"]

STATE_PENDING_STAFF = "Pending Staff Processing"
STATE_PROCESSED = "Processed"


class LoanSettlement(Document):
	pass


# ---------------------------------------------------------------------------
# Accounts service lookups
# ---------------------------------------------------------------------------

def _get_project_number(project_name):
	"""Resolve a Project Registration docname to its human-readable project_no."""
	if not project_name:
		return None
	# Callers may pass either the docname or the project_no itself.
	project_no = frappe.db.get_value("Project Registration", project_name, "project_no")
	return project_no or project_name


def get_loan_settlement_summary(ledger_loan_number):
	"""
	Authoritative outstanding balance for a loan, from the Accounts service.

	Returns {"outstanding_amount", "total_settled", "loan_status"}; raises on failure so
	callers can decide whether to fail open (listing) or hard-fail (validation).
	"""
	url = LOAN_SETTLEMENT_SUMMARY_URL.format(loan_number=ledger_loan_number)
	response = requests.get(url, timeout=REQUEST_TIMEOUT)
	response.raise_for_status()
	data = response.json() or {}
	return {
		"outstanding_amount": flt(data.get("outstandingAmount")),
		"total_settled": flt(data.get("totalSettled")),
		"loan_status": data.get("updatedLoanStatus"),
	}


def _budget_head_map(account_head_ids):
	"""
	{accountHeadId: (Budget Head docname, label)} for the ids the Accounts service reported.

	The ledger identifies heads by its own integer id; our Link fields want the docname;
	and the Fund Received budget breakup is populated from sanction rows that hold the
	human label ("Manpower"). All three are needed downstream, so resolve once and carry
	both. Ids we cannot resolve are simply absent — the caller keeps the raw id so the
	head still shows up rather than vanishing.
	"""
	ids = [int(i) for i in account_head_ids if i not in (None, "")]
	if not ids:
		return {}

	rows = frappe.get_all(
		"Budget Head", filters={"id": ["in", ids]}, fields=["name", "id", "budget_head"]
	)
	return {
		int(row["id"]): (row["name"], row.get("budget_head"))
		for row in rows
		if row.get("id") is not None
	}


def _prorate(heads, target):
	"""
	Split `target` across `heads` in proportion to each head's loan amount.

	Used for Full settlements. When nothing has been settled yet, target == the loan
	total and each head gets back exactly what was drawn against it — the plain reading
	of "full amount against all budget heads". Once a loan is partially settled the
	outstanding is smaller than the sum of the heads, and proportional is the only
	split that stays consistent with how the loan was drawn (the Accounts service does
	not expose per-head settled figures, so there is nothing more precise to use).

	Rounding residue lands on the largest head, so the parts always re-sum to `target`
	exactly — the Fund Received check downstream compares these to the paisa.
	"""
	target = flt(target, 2)
	total = flt(sum(flt(h.get("loan_amount")) for h in heads), 2)
	if not heads or total <= 0:
		return []

	allocations = [flt(flt(h.get("loan_amount")) * target / total, 2) for h in heads]

	residue = flt(target - sum(allocations), 2)
	if residue:
		biggest = max(range(len(heads)), key=lambda i: flt(heads[i].get("loan_amount")))
		allocations[biggest] = flt(allocations[biggest] + residue, 2)

	return [
		{**head, "return_amount": amount}
		for head, amount in zip(heads, allocations)
	]


def _loan_budget_heads(loan, head_map=None):
	"""Normalise the ledger's loanBudgetBreakupDetails into our head shape."""
	rows = loan.get("loanBudgetBreakupDetails") or []
	if head_map is None:
		head_map = _budget_head_map([r.get("accountHeadId") for r in rows])

	heads = []
	for row in rows:
		head_id = row.get("accountHeadId")
		head_id = int(head_id) if head_id not in (None, "") else None
		docname, label = head_map.get(head_id, (None, None))
		heads.append({
			"account_head_id": head_id,
			"account_head": docname,
			"account_head_label": label or docname or (str(head_id) if head_id else None),
			"loan_amount": flt(row.get("amount")),
		})
	return heads


@frappe.whitelist()
def get_active_loan_for_project(project_name):
	"""
	Every not-fully-settled loan for a project, enriched with its live outstanding balance.

	Returns [] when the project has no loans, all of them are settled, or the Accounts
	service is unreachable — an empty list simply means "don't show the modal", so a
	ledger outage never blocks an otherwise-unrelated Fund Received submission.
	"""
	project_number = _get_project_number(project_name)
	if not project_number:
		return {"status": "success", "data": []}

	try:
		response = requests.get(
			LOAN_DETAILS_BY_PROJECT_URL.format(project_number=project_number),
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		loans = response.json() or []
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Loan Settlement - Fetch Project Loans Failed")
		return {"status": "success", "data": []}

	open_loans = [
		loan for loan in loans
		if (loan.get("loanStatus") or "").upper() != SETTLED_STATUS
	]
	if not open_loans:
		return {"status": "success", "data": []}

	# Resolve every head id across every loan in one query rather than per loan.
	head_map = _budget_head_map([
		row.get("accountHeadId")
		for loan in open_loans
		for row in (loan.get("loanBudgetBreakupDetails") or [])
	])

	# One /summary call per open loan — issued concurrently so the modal isn't gated
	# on N sequential round-trips (same approach commitPayment.py uses for head balances).
	def _enrich(loan):
		budget_heads = _loan_budget_heads(loan, head_map)
		base = {
			"budget_heads": budget_heads,
			"ledger_loan_number": loan.get("loanNumber"),
			"loan_reference": loan.get("loanNumberFap"),
			"loan_amount": flt(loan.get("loanAmount")),
			"loan_status": loan.get("loanStatus"),
			"loan_received_date": loan.get("loanReceivedDate"),
			"loan_type": loan.get("loanType"),
			"bmr": loan.get("bmr"),
			"project_number": loan.get("projectNumber") or project_number,
		}

		try:
			summary = get_loan_settlement_summary(loan.get("loanNumber"))
		except Exception:
			frappe.log_error(
				frappe.get_traceback(),
				f"Loan Settlement - Summary Failed (loan {loan.get('loanNumber')})",
			)
			# Still surface the loan. Silently hiding it looks identical to "this
			# project has no loans", leaving the user unaware a loan exists at all.
			# But do NOT guess the outstanding balance — falling back to the full
			# loan amount could let someone over-settle a partially settled loan —
			# so flag it unverifiable and let the UI block selecting it.
			return {
				**base,
				"outstanding_amount": None,
				"total_settled": None,
				"balance_unavailable": True,
			}

		if summary["outstanding_amount"] <= 0:
			# Balance reached zero even though the status hasn't caught up yet.
			return None

		return {
			**base,
			"outstanding_amount": summary["outstanding_amount"],
			"total_settled": summary["total_settled"],
			"balance_unavailable": False,
		}

	with ThreadPoolExecutor(max_workers=8) as executor:
		enriched = list(executor.map(_enrich, open_loans))

	return {"status": "success", "data": [loan for loan in enriched if loan]}


# ---------------------------------------------------------------------------
# Creating settlement requests (called from the Fund Received modal)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def save_loan_settlement_requests(project_name, loans):
	"""
	Create one Loan Settlement doc per selected loan.

	Runs when the user clicks "Settle the Loan" in the modal — deliberately BEFORE the
	Fund Received document exists, so fund_received_reference starts blank and is filled
	in later (fund_received.py). Nothing is published to Kafka here.

	`loans` is a list of {loan_reference, ledger_loan_number, settlement_type,
	settlement_amount, budget_breakup}. Every entry is re-validated against a *fresh*
	Accounts service read — the figures the modal displayed may be minutes stale by now,
	and the head-wise split is re-derived (Full) or re-checked (Partial) against the
	loan's own budget heads as the ledger reports them right now.

	Either every settlement is created or none are: a validation failure throws, so the
	user can correct it in the modal rather than ending up with a half-saved batch.
	"""
	if isinstance(loans, str):
		loans = json.loads(loans)

	if not loans:
		frappe.throw(_("No loans were selected for settlement."))

	project_docname = project_name
	project_number = _get_project_number(project_name)
	if not frappe.db.exists("Project Registration", project_docname):
		# Caller passed a project_no rather than a docname — resolve it back.
		project_docname = frappe.db.get_value(
			"Project Registration", {"project_no": project_number}, "name"
		)

	# Head-wise loan amounts, read fresh so a Full settlement is split against what the
	# ledger says today rather than what the modal was rendered from.
	try:
		response = requests.get(
			LOAN_DETAILS_BY_PROJECT_URL.format(project_number=project_number),
			timeout=REQUEST_TIMEOUT,
		)
		response.raise_for_status()
		loans_by_number = {
			int(loan.get("loanNumber")): loan
			for loan in (response.json() or [])
			if loan.get("loanNumber") is not None
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Loan Settlement - Head Refetch Failed")
		frappe.throw(
			_("Could not read the loan's budget heads from the Accounts service. Please try again.")
		)

	created = []

	for entry in loans:
		loan_reference = entry.get("loan_reference")
		ledger_loan_number = entry.get("ledger_loan_number")
		settlement_type = entry.get("settlement_type")

		if not ledger_loan_number:
			frappe.throw(_("Missing loan number for one of the selected loans."))
		if settlement_type not in ("Full", "Partial"):
			frappe.throw(_("Select Full or Partial settlement for loan {0}.").format(loan_reference))

		# --- Re-validate against the Accounts service (never trust the client figure) ---
		try:
			summary = get_loan_settlement_summary(ledger_loan_number)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Loan Settlement - Revalidation Failed")
			frappe.throw(
				_("Could not verify the current balance for loan {0}. Please try again.").format(
					loan_reference or ledger_loan_number
				)
			)

		outstanding = summary["outstanding_amount"]

		if (summary["loan_status"] or "").upper() == SETTLED_STATUS or outstanding <= 0:
			frappe.throw(
				_("Loan {0} has already been fully settled. Please refresh and try again.").format(
					loan_reference or ledger_loan_number
				)
			)

		if settlement_type == "Full":
			# "Full" must mean actually full — re-derive rather than trusting the client.
			settlement_amount = outstanding
		else:
			settlement_amount = flt(entry.get("settlement_amount"))
			if settlement_amount <= 0:
				frappe.throw(
					_("Enter a settlement amount greater than zero for loan {0}.").format(
						loan_reference or ledger_loan_number
					)
				)
			if settlement_amount > outstanding:
				frappe.throw(
					_("Settlement amount for loan {0} exceeds its outstanding balance of {1}.").format(
						loan_reference or ledger_loan_number, outstanding
					)
				)

		# --- Head-wise return ------------------------------------------------
		label = loan_reference or ledger_loan_number
		ledger_loan = loans_by_number.get(int(ledger_loan_number))
		if not ledger_loan:
			frappe.throw(
				_("Loan {0} is no longer listed against this project. Please refresh and try again.").format(label)
			)

		loan_heads = _loan_budget_heads(ledger_loan)
		if not loan_heads:
			frappe.throw(
				_("Loan {0} has no budget head breakup in the Accounts service, so it cannot be settled head-wise.").format(label)
			)

		if settlement_type == "Full":
			# Derived, never taken from the client: "Full" means the whole outstanding,
			# spread across the heads the loan was drawn against.
			breakup = _prorate(loan_heads, settlement_amount)
		else:
			breakup = _validate_partial_breakup(entry.get("budget_breakup"), loan_heads, settlement_amount, label)

		doc = frappe.get_doc({
			"doctype": "Loan Settlement",
			"loan_reference": loan_reference,
			"ledger_loan_number": ledger_loan_number,
			"project": project_docname,
			"project_number": entry.get("project_number") or project_number,
			"settlement_type": settlement_type,
			"settlement_amount": settlement_amount,
			"settlement_date": nowdate(),
			"loan_amount_at_request": flt(entry.get("loan_amount")),
			"outstanding_at_request": outstanding,
			"requested_by": frappe.session.user,
			"publish_status": "Pending",
			"workflow_state": STATE_PENDING_STAFF,
			"budget_breakup": [
				{
					"account_head": row["account_head"],
					"account_head_id": row["account_head_id"],
					"loan_amount": row["loan_amount"],
					"return_amount": row["return_amount"],
				}
				for row in breakup
			],
		})
		doc.insert(ignore_permissions=True)
		created.append(doc.name)

	frappe.db.commit()

	# The caller (the Fund Received form) prefills and locks itself from this, so the
	# figures it enforces are the server's, not the ones the modal happened to show.
	return {
		"status": "success",
		"data": created,
		"requirements": get_settlement_requirements(created),
	}


def _validate_partial_breakup(rows, loan_heads, settlement_amount, label):
	"""
	Check a user-entered head-wise return for a Partial settlement.

	The user types a total and then how much of it comes back against each head; those
	have to agree, or the Fund Received built from them would not reconcile.
	"""
	if isinstance(rows, str):
		rows = json.loads(rows)

	heads_by_id = {h["account_head_id"]: h for h in loan_heads}
	entered = {}

	for row in rows or []:
		head_id = row.get("account_head_id")
		head_id = int(head_id) if head_id not in (None, "") else None
		if head_id not in heads_by_id:
			frappe.throw(
				_("Loan {0} was not drawn against account head {1}, so nothing can be returned to it.").format(
					label, row.get("account_head") or head_id
				)
			)

		amount = flt(row.get("return_amount"))
		if amount < 0:
			frappe.throw(_("Return amounts for loan {0} cannot be negative.").format(label))
		if amount > flt(heads_by_id[head_id]["loan_amount"]):
			frappe.throw(
				_("Return against {0} for loan {1} exceeds the {2} drawn against that head.").format(
					heads_by_id[head_id]["account_head"] or head_id,
					label,
					flt(heads_by_id[head_id]["loan_amount"]),
				)
			)
		entered[head_id] = flt(entered.get(head_id, 0) + amount, 2)

	total = flt(sum(entered.values()), 2)
	if abs(total - flt(settlement_amount, 2)) >= 0.01:
		frappe.throw(
			_("Head-wise return for loan {0} totals {1}, which does not match the settlement amount of {2}.").format(
				label, total, flt(settlement_amount, 2)
			)
		)

	# Heads with nothing returned are dropped — they would only publish zero-amount rows.
	return [
		{**heads_by_id[head_id], "return_amount": amount}
		for head_id, amount in entered.items()
		if amount > 0
	]


@frappe.whitelist()
def discard_loan_settlement_requests(settlement_names):
	"""
	Delete draft settlements so the user can redo them from the modal.

	Used when someone realises mid-form that they got the amount wrong: rather than
	editing the saved settlements in place, the old ones are discarded and fresh ones
	created. That is deliberate — `loanSettlementNumber` is an idempotency key on the
	Accounts side (§7.4), so a settlement doc must never be reused for different
	figures. A new attempt gets a new number.

	Deliberately narrow: only a settlement that is still a draft in every sense can go.
	Anything already linked to a Fund Received, past staff processing, or published is
	refused, so this can never erase a real record — it only ever removes something
	created minutes ago in the very form still open on screen.
	"""
	if isinstance(settlement_names, str):
		try:
			settlement_names = json.loads(settlement_names)
		except ValueError:
			settlement_names = [settlement_names]

	deleted, skipped = [], []
	user = frappe.session.user
	is_admin = "System Manager" in frappe.get_roles(user)

	for name in settlement_names or []:
		if not frappe.db.exists("Loan Settlement", name):
			continue

		doc = frappe.get_doc("Loan Settlement", name)
		blocked = (
			doc.fund_received_reference
			or (doc.workflow_state or STATE_PENDING_STAFF) != STATE_PENDING_STAFF
			or doc.publish_status == "Published"
			or doc.docstatus != 0
			or not (doc.owner == user or is_admin)
		)
		if blocked:
			skipped.append(name)
			continue

		frappe.delete_doc("Loan Settlement", name, force=True, ignore_permissions=True)
		deleted.append(name)

	frappe.db.commit()

	if skipped:
		frappe.throw(
			_("These loan settlements can no longer be changed: {0}. They have already been submitted or processed.").format(
				", ".join(skipped)
			)
		)

	return {"status": "success", "data": deleted}


@frappe.whitelist()
def get_settlement_requirements(settlement_names):
	"""
	What a Fund Received must cover to satisfy these settlements.

	Returns the minimum total, the minimum per Budget Head, and whether the figures are
	an exact target or a floor:

	  - every settlement Partial -> `exact`. The user already declared precisely how much
	    is coming in and where it goes, so the Fund Received is pinned to it.
	  - any settlement Full      -> a floor. A receipt that clears a loan in full is
	    usually larger than the loan, with the excess being ordinary project funds.
	"""
	if isinstance(settlement_names, str):
		try:
			settlement_names = json.loads(settlement_names)
		except ValueError:
			settlement_names = [settlement_names]

	if not settlement_names:
		return {"total": 0, "heads": {}, "head_labels": {}, "exact": False, "settlements": []}

	total = 0
	heads = {}
	head_labels = {}
	settlements = []
	has_full = False

	for name in settlement_names:
		if not frappe.db.exists("Loan Settlement", name):
			continue
		doc = frappe.get_doc("Loan Settlement", name)
		if doc.settlement_type == "Full":
			has_full = True
		total = flt(total + flt(doc.settlement_amount), 2)

		rows = []
		for row in doc.get("budget_breakup") or []:
			head = row.account_head
			label = (
				frappe.db.get_value("Budget Head", head, "budget_head") if head else None
			) or head
			if head:
				heads[head] = flt(flt(heads.get(head, 0)) + flt(row.return_amount), 2)
				head_labels[head] = label
			rows.append({
				"account_head": head,
				"account_head_label": label,
				"account_head_id": row.account_head_id,
				"loan_amount": flt(row.loan_amount),
				"return_amount": flt(row.return_amount),
			})

		settlements.append({
			"name": doc.name,
			"loan_reference": doc.loan_reference,
			"ledger_loan_number": doc.ledger_loan_number,
			"settlement_type": doc.settlement_type,
			"settlement_amount": flt(doc.settlement_amount),
			"budget_breakup": rows,
		})

	return {
		"total": total,
		"heads": heads,
		"head_labels": head_labels,
		"exact": not has_full,
		"settlements": settlements,
	}


@frappe.whitelist()
def get_loan_settlements_for_fund_received(fund_received):
	"""Read-only listing for the Fund Received detail view."""
	if not fund_received:
		return {"status": "success", "data": []}

	rows = frappe.get_all(
		"Loan Settlement",
		filters={"fund_received_reference": fund_received},
		fields=[
			"name", "loan_reference", "ledger_loan_number", "settlement_type",
			"settlement_amount", "settlement_date", "settlement_mode", "remarks",
			"publish_status", "workflow_state",
		],
		order_by="creation asc",
	)

	for row in rows:
		row["budget_breakup"] = frappe.get_all(
			"Loan Settlement Budget Breakup",
			filters={"parent": row["name"], "parenttype": "Loan Settlement"},
			fields=["account_head", "account_head_id", "loan_amount", "return_amount"],
			order_by="idx asc",
		)

	return {"status": "success", "data": rows}


@frappe.whitelist()
def get_loan_settlement_details(docname):
	"""Full document for the staff processing screen."""
	if not frappe.db.exists("Loan Settlement", docname):
		frappe.throw(_("Loan Settlement {0} not found.").format(docname))

	doc = frappe.get_doc("Loan Settlement", docname)
	data = doc.as_dict()

	# Live outstanding for context, best-effort only.
	try:
		summary = get_loan_settlement_summary(doc.ledger_loan_number)
		data["current_outstanding"] = summary["outstanding_amount"]
		data["current_loan_status"] = summary["loan_status"]
	except Exception:
		data["current_outstanding"] = None
		data["current_loan_status"] = None

	return {"status": "success", "data": data}


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_loan_settlement_workflow_actions(docname):
	"""Available workflow actions for the current user, given the document's state."""
	doc = frappe.get_doc("Loan Settlement", docname)
	current_state = doc.get("workflow_state") or STATE_PENDING_STAFF
	user_roles = frappe.get_roles(frappe.session.user)

	workflow_name = frappe.db.get_value(
		"Workflow", {"document_type": "Loan Settlement", "is_active": 1}, "name"
	)
	if not workflow_name:
		return []

	workflow = frappe.get_doc("Workflow", workflow_name)
	allowed_actions = []

	for transition in workflow.get("transitions", []):
		if transition.state != current_state:
			continue
		transition_roles = transition.get("allowed") or []
		if isinstance(transition_roles, str):
			transition_roles = [transition_roles]
		if any(role in user_roles for role in transition_roles) or "System Manager" in user_roles:
			allowed_actions.append(transition.action)

	return list(dict.fromkeys(allowed_actions))


def _publish_and_record(doc):
	"""
	Publish a processed settlement to Kafka and record the outcome on the doc.

	Deliberately never raises: a Kafka outage must not roll back a legitimate workflow
	transition or block staff from finishing their work. A failure just leaves
	publish_status = "Failed", which is visible in the UI and retryable (retry_publish).
	"""
	from rndopsapp.rndopsapp.kafka.producer.loan_settlement import publish_loan_settlement

	try:
		published = publish_loan_settlement(doc)
		if published:
			frappe.db.set_value("Loan Settlement", doc.name, {
				"publish_status": "Published",
				"publish_error": None,
			}, update_modified=False)
			return True

		frappe.db.set_value("Loan Settlement", doc.name, {
			"publish_status": "Failed",
			"publish_error": "Producer returned False (see Error Log).",
		}, update_modified=False)
		return False
	except Exception as e:
		frappe.db.set_value("Loan Settlement", doc.name, {
			"publish_status": "Failed",
			"publish_error": str(e)[:500],
		}, update_modified=False)
		frappe.log_error(frappe.get_traceback(), f"Loan Settlement Publish Error ({doc.name})")
		return False


@frappe.whitelist()
def perform_loan_settlement_action(docname, action, settlement_mode=None, remarks=None):
	"""
	Execute a workflow action.

	On "Process" (staff, RnD): saves settlement_mode + remarks, moves to Processed, and
	publishes the settlement to Kafka — this is the ONLY publish point for the feature,
	which is why the payload can carry mode/remarks at all (see module docstring).
	"""
	try:
		doc = frappe.get_doc("Loan Settlement", docname)
		current_state = doc.get("workflow_state") or STATE_PENDING_STAFF

		is_processing = action == "Process" and current_state == STATE_PENDING_STAFF

		if is_processing:
			user_roles = frappe.get_roles(frappe.session.user)
			if not any(role in user_roles for role in STAFF_ROLES):
				frappe.throw(
					_("Only staff, RnD can process a loan settlement."), frappe.PermissionError
				)
			if not settlement_mode:
				frappe.throw(_("Select a settlement mode before processing."))

			doc.db_set("settlement_mode", settlement_mode, update_modified=False)
			doc.db_set("remarks", remarks or "", update_modified=False)
			doc = frappe.get_doc("Loan Settlement", docname)

		workflow_name = frappe.db.get_value(
			"Workflow", {"document_type": "Loan Settlement", "is_active": 1}, "name"
		)
		if not workflow_name:
			frappe.throw(_("No active workflow found for Loan Settlement."))

		workflow = frappe.get_doc("Workflow", workflow_name)
		user_roles = frappe.get_roles(frappe.session.user)

		next_state = None
		for t in workflow.transitions:
			if t.state == current_state and t.action == action:
				allowed_roles = t.get("allowed") or []
				if isinstance(allowed_roles, str):
					allowed_roles = [allowed_roles]
				if any(role in user_roles for role in allowed_roles) or "System Manager" in user_roles:
					next_state = t.next_state
					break

		if not next_state:
			frappe.throw(
				_("No valid transition found for action '{0}' from state '{1}'.").format(
					action, current_state
				)
			)

		state_doc = next((s for s in workflow.states if s.state == next_state), None)

		if state_doc and state_doc.doc_status == 1 and doc.docstatus == 0:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_workflow = True
			doc.submit()
			frappe.db.set_value("Loan Settlement", docname, "workflow_state", next_state)
		elif state_doc and state_doc.doc_status == 2 and doc.docstatus != 2:
			doc.flags.ignore_permissions = True
			doc.flags.ignore_workflow = True
			doc.cancel()
			frappe.db.set_value("Loan Settlement", docname, "workflow_state", next_state)
		else:
			doc.db_set("workflow_state", next_state, update_modified=True)

		frappe.db.commit()

		# Publish AFTER the transition is durably committed, and outside its transaction,
		# so a Kafka failure can never undo the staff member's work.
		published = None
		if next_state == STATE_PROCESSED:
			doc = frappe.get_doc("Loan Settlement", docname)
			published = _publish_and_record(doc)
			frappe.db.commit()

		return {
			"status": "success",
			"message": f"Action '{action}' completed. New State: {next_state}",
			"docname": docname,
			"workflow_state": next_state,
			"published": published,
			"next_actions": get_loan_settlement_workflow_actions(docname),
		}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(frappe.get_traceback(), "Loan Settlement Action Error")
		return {"status": "error", "message": str(e)}


@frappe.whitelist()
def retry_publish_loan_settlement(docname):
	"""
	Re-publish a settlement whose first publish failed.

	Safe to call repeatedly: the Accounts service treats loanSettlementNumber as an
	idempotency key, so a duplicate is skipped rather than double-settled.
	"""
	user_roles = frappe.get_roles(frappe.session.user)
	if not any(role in user_roles for role in STAFF_ROLES):
		frappe.throw(_("You are not permitted to perform this action."), frappe.PermissionError)

	if not frappe.db.exists("Loan Settlement", docname):
		frappe.throw(_("Loan Settlement {0} not found.").format(docname))

	doc = frappe.get_doc("Loan Settlement", docname)

	if doc.workflow_state != STATE_PROCESSED:
		frappe.throw(_("Only a processed settlement can be published."))

	published = _publish_and_record(doc)
	frappe.db.commit()

	if published:
		return {"status": "success", "message": "Settlement published successfully."}

	return {
		"status": "error",
		"message": frappe.db.get_value("Loan Settlement", docname, "publish_error")
		or "Publish failed. See Error Log.",
	}
