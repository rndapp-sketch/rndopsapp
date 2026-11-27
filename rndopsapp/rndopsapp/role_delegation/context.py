"""
Per-request acting profile.

While acting, the request runs as the delegator, so lists, ownership rules and
named-approver checks all see the delegator, with only the delegated roles. The
login session still belongs to the delegate: the swap lasts one request and is
never saved. Roles are replaced through Frappe's request-local role cache; the
shared Redis cache is never written.

Because modified_by and owner show the delegator while acting, the Role
Delegation Log is the record of who really did what.
"""

import functools
import inspect

import frappe
from frappe import _

from rndopsapp.rndopsapp.role_delegation import service
from rndopsapp.rndopsapp.role_delegation.audit import log
from rndopsapp.rndopsapp.role_delegation.constants import (
	ACTING_BASE_ROLES,
	APPLICANT_FIELDS,
	BACKWARD_ACTION_PREFIXES,
	BLOCKED_METHODS,
	EXEMPT_METHODS,
	HEADER,
	PROTECTED_DOCTYPES,
	SELF_PROFILE,
	SESSION_KEY,
	UNLOGGED_DOCTYPES,
)

_UNSAFE_METHODS = ("POST", "PUT", "PATCH", "DELETE")


class ProfileMismatch(frappe.ValidationError):
	http_status_code = 409


class DelegationEnded(frappe.ValidationError):
	http_status_code = 409


def acting():
	"""The current request's acting context, or None on the user's own profile."""
	return getattr(frappe.local, "role_delegation", None)


def actual_user():
	"""The person really making the request, also while acting."""
	ctx = acting()
	return ctx.user if ctx else frappe.session.user


def delegated_document_names(doctype):
	"""
	Documents of this type acted on for the current delegator. Some handlers write
	the state without touching modified_by, so history queries can miss them.
	"""
	ctx = acting()
	if not ctx:
		return []
	return frappe.get_all(
		"Role Delegation Log",
		filters={
			"delegator": ctx.delegator,
			"event": "action",
			"result": "Success",
			"ref_doctype": doctype,
		},
		pluck="ref_name",
		distinct=True,
	)


# ---------------------------------------------------------------- auth hook


def apply_acting_profile():
	"""auth_hooks entry: validate the session's grant and apply its roles."""
	frappe.local.role_delegation = None

	user = frappe.session.user
	if user in (None, "", "Guest") or frappe.get_request_header("Authorization"):
		return
	if _requested_method() in EXEMPT_METHODS:
		return

	header = (frappe.get_request_header(HEADER) or "").strip()
	stored = (frappe.local.session.data or {}).get(SESSION_KEY)

	if not service.is_enabled() or not stored:
		# A tab that believes it is acting must not run as the user's own profile.
		if header and header != SELF_PROFILE:
			_mismatch(user, None, header)
		return

	grant = service.load_grant(stored)
	error = service.grant_error(grant, user) if grant else "This delegation no longer exists."
	if error:
		log("denied", user, grant, result="Failed", delegation=stored, message=error,
			endpoint=_requested_method())
		service.end_acting(error, grant)
		frappe.throw(
			_("{0} You are back on your own profile.").format(error), DelegationEnded
		)

	unsafe = frappe.local.request.method in _UNSAFE_METHODS
	if (unsafe and header != grant.name) or (header and header != grant.name):
		_mismatch(user, grant, header)

	frappe.local.role_delegation = frappe._dict(
		name=grant.name,
		user=user,
		delegator=grant.delegator,
		roles=[r.role for r in grant.roles],
		depth=0,
		logged=False,
		ref=None,
		writes={},
	)
	if _requested_method() in BLOCKED_METHODS:
		_deny(None, None, None, "Switch back to your own profile to do this.")
	apply_identity()


def _mismatch(user, grant, header):
	if service.is_enabled():
		log("denied", user, grant, result="Failed", endpoint=_requested_method(),
			message=f"profile mismatch: request sent '{header or 'no header'}'")
		frappe.db.commit()
	frappe.throw(_("Your active profile has changed. Reload and try again."), ProfileMismatch)


def _requested_method():
	"""
	The RPC method this request will run, or None. `cmd` is checked first because
	Frappe runs it in preference to the URL path.
	"""
	if frappe.form_dict.get("cmd"):
		return frappe.form_dict.get("cmd")
	parts = [p for p in frappe.local.request.path.split("/") if p]
	if parts[:2] == ["api", "method"] and len(parts) == 3:
		return parts[2]
	if parts[:1] == ["api"] and parts[1:2] in (["v1"], ["v2"]) and parts[2:3] == ["method"] and len(parts) == 4:
		return parts[3]
	return None


def apply_identity():
	"""Run the rest of the request as the delegator, with the delegated roles."""
	ctx = acting()
	if not ctx:
		return
	if frappe.local.session.user != ctx.delegator:
		# A copy: frappe.local.session is the object Frappe saves back to the
		# login session, which must keep belonging to the delegate.
		session = frappe._dict(frappe.local.session)
		session.user = ctx.delegator
		frappe.local.session = session
	roles = sorted(set(ctx.roles) | set(ACTING_BASE_ROLES))
	# frappe.cache.hget reads this request-local dict before Redis.
	# Never write these values with frappe.cache.hset.
	frappe.local.cache.setdefault(frappe.cache.make_key("roles"), {})[ctx.delegator] = roles
	frappe.local.role_permissions = {}
	frappe.local.user_perms = None


# ---------------------------------------------------------------- approval guard


def guarded_action(doctype=None, default_action=None):
	"""
	Decorator for workflow handlers taking `docname` (and `doctype` / `action` if
	not given here). Place it under @frappe.whitelist() so the check runs outside
	the handler's own try/except.
	"""

	def decorator(fn):
		signature = inspect.signature(fn)

		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			if not service.is_enabled() or (acting() and acting().depth):
				return fn(*args, **kwargs)

			bound = signature.bind(*args, **kwargs).arguments
			ref_doctype = bound.get("doctype") or doctype
			docname = bound.get("docname")
			action = str(bound.get("action") or default_action or "")
			backward = _is_backward(action)

			_check(ref_doctype, docname, action, backward)

			ctx = acting()
			if ctx:
				ctx.depth += 1
			try:
				result = fn(*args, **kwargs)
			except Exception as e:
				if ctx:
					frappe.db.rollback()
					_log_action(ref_doctype, docname, action, False, str(e))
					frappe.db.commit()
				raise
			finally:
				if ctx:
					ctx.depth -= 1

			failed = isinstance(result, dict) and result.get("status") in ("error", "failed")
			if backward and not failed:
				_supersede(ref_doctype, docname)
			if ctx:
				_log_action(
					ref_doctype, docname, action, not failed,
					result.get("message") if failed else None, superseded=backward,
				)
				if not failed:
					_add_comment(ref_doctype, docname, action)
			if ctx or (backward and not failed):
				frappe.db.commit()
			return result

		return wrapper

	return decorator


def check_workflow_change(doc, method=None):
	"""
	doc_events guard for state changes made outside the decorated handlers, such
	as Frappe's own workflow endpoint.
	"""
	if not getattr(frappe.local, "request", None) or not service.is_enabled():
		return
	ctx = acting()
	if (ctx and ctx.depth) or doc.is_new() or not doc.meta.has_field("workflow_state"):
		return
	before = doc.get_doc_before_save()
	if not before or before.get("workflow_state") == doc.get("workflow_state"):
		return
	if doc.doctype.startswith("Role Delegation"):
		return
	action = f"{before.get('workflow_state')} -> {doc.get('workflow_state')}"
	_check(doc.doctype, doc.name, action, backward=False)
	if ctx:
		ctx.ref = (doc.doctype, doc.name, action)


def _check(doctype, docname, action, backward):
	ctx = acting()
	if ctx:
		request = getattr(frappe.local, "request", None)
		if request and request.method not in _UNSAFE_METHODS:
			_deny(doctype, docname, action, "Workflow actions must be sent as POST while acting.")
		# set_user or a cache clear earlier in the request may have dropped the override.
		apply_identity()
		# Neither side may approve their own application through a delegation.
		if _is_applicant(doctype, docname, ctx.user):
			_deny(doctype, docname, action,
				"You cannot act as a delegate on your own application.")
		if _is_applicant(doctype, docname, ctx.delegator):
			_deny(doctype, docname, action,
				"You cannot use this delegation on the delegator's own application.")
	elif not backward and docname and frappe.db.exists(
		"Role Delegation Log",
		{
			"actual_user": frappe.session.user,
			"ref_doctype": doctype,
			"ref_name": docname,
			"event": "action",
			"result": "Success",
			"superseded": 0,
		},
	):
		_deny(doctype, docname, action,
			"You already acted on this application as a delegate, so you cannot approve it again.")


def _deny(doctype, docname, action, message):
	frappe.db.rollback()
	log("denied", actual_user(), acting(), result="Failed", ref_doctype=doctype,
		ref_name=docname, workflow_action=action, message=message)
	frappe.db.commit()
	if acting():
		acting().logged = True
	frappe.throw(_(message), frappe.PermissionError)


def _is_applicant(doctype, docname, user):
	if not (doctype and docname) or not frappe.db.exists(doctype, docname):
		return False
	meta = frappe.get_meta(doctype)
	fields = ["owner"] + [f for f in APPLICANT_FIELDS.get(doctype, ()) if meta.has_field(f)]
	row = frappe.db.get_value(doctype, docname, fields, as_dict=True) or {}
	return user.lower() in {str(v).strip().lower() for v in row.values() if v}


def _is_backward(action):
	return action.strip().lower().startswith(BACKWARD_ACTION_PREFIXES)


def _supersede(doctype, docname):
	"""A returned document starts a new approval cycle."""
	frappe.db.set_value(
		"Role Delegation Log",
		{"ref_doctype": doctype, "ref_name": docname, "superseded": 0},
		"superseded",
		1,
		update_modified=False,
	)


# ---------------------------------------------------------------- while acting


def protect_accounts(doc, method=None):
	"""doc_events: a delegate cannot change accounts or delegations."""
	ctx = acting()
	if not ctx:
		return
	own_account = doc.doctype == "User" and doc.name in (ctx.user, ctx.delegator)
	if own_account or doc.doctype in PROTECTED_DOCTYPES:
		_deny(doc.doctype, doc.name, method, "Switch back to your own profile to do this.")


def record_write(doc, method=None):
	"""doc_events: remember every document this acting request writes."""
	ctx = acting()
	if ctx and doc.doctype not in UNLOGGED_DOCTYPES and not doc.meta.istable:
		ctx.writes.setdefault((doc.doctype, doc.name), method)


# ---------------------------------------------------------------- audit


def _log_action(doctype, docname, action, ok, message=None, superseded=False):
	ctx = acting()
	log(
		"action", ctx.user, ctx, result="Success" if ok else "Failed",
		endpoint=_requested_method() if getattr(frappe.local, "request", None) else None,
		ref_doctype=doctype, ref_name=docname, workflow_action=action,
		message=message, superseded=int(superseded),
	)
	ctx.logged = True


def _add_comment(doctype, docname, action):
	ctx = acting()
	if not (doctype and docname) or not frappe.db.exists(doctype, docname):
		return
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": doctype,
			"reference_name": docname,
			"content": f"{action}: {ctx.user}, acting as {', '.join(ctx.roles)} for {ctx.delegator}",
		}
	).insert(ignore_permissions=True)


def log_acting_request(response=None, request=None):
	"""
	after_request: record the documents written while acting, and any write request
	the approval guard did not already record. On failure Frappe has rolled back
	by now, so commit here.
	"""
	ctx = acting()
	if not ctx or not request:
		return
	unsafe = request.method in _UNSAFE_METHODS
	if not (ctx.writes or (unsafe and not ctx.logged)):
		return
	try:
		ok = bool(response) and response.status_code < 400
		failure = None if ok else f"HTTP {getattr(response, 'status_code', '?')}"
		if unsafe and not ctx.logged:
			doctype, docname, action = ctx.ref or (None, None, None)
			_log_action(doctype, docname, action, ok, failure)
			if ok and ctx.ref:
				_add_comment(doctype, docname, action)
		for (doctype, docname), method in ctx.writes.items():
			log(
				"write", ctx.user, ctx, result="Success" if ok else "Failed",
				endpoint=_requested_method(), ref_doctype=doctype, ref_name=docname,
				message=failure or method,
			)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Role delegation request log failed")
		frappe.db.commit()
