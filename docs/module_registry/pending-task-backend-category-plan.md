# Plan: Move Research / Consultancy / Others splitting into `get_pending_task`

Companion to [project-category-splitting-logic.md](project-category-splitting-logic.md), which documents
the **current, frontend-only** implementation. This file plans the backend replacement: teach
[`get_pending_task`](module_registry.py) to classify each record into `Research` / `Consultancy` / `Others`
itself, and accept an optional `type` filter, so the client no longer has to fetch all 1000 Project
Registrations, run a two-pass per-doctype re-fetch `useEffect`, and filter client-side.

## 1. Goal

`get_pending_task(page_name="pending-task", type=None)` — one new optional parameter.

- `type` omitted → same shape as today, **plus** every record gets a `project_type` field and the
  response gets a top-level `tab_counts` object (`{"Research": N, "Consultancy": N, "Others": N}`).
- `type="Research" | "Consultancy" | "Others"` → `results` contains only records in that bucket
  (doctype groups that end up empty are dropped entirely, same as the existing `if mapped:` pattern),
  but `tab_counts` still reflects **all** buckets so the frontend can render tab badges without a
  second, unfiltered call.

Scope: this plan only covers `get_pending_task`, per the ask. Section 8 notes `get_task_registry` as a
natural follow-up once this lands, since `TaskRegistry.tsx` uses the exact same client-side logic today.

## 2. What moves server-side

Straight port of the three pieces documented in `project-category-splitting-logic.md` §2–4:

| Frontend (`projectTypeMapping.ts`) | Backend (`module_registry.py`) |
|---|---|
| `DOCTYPE_PR_LINKS` table | `DOCTYPE_PR_LINKS` dict (module-level constant) |
| `resolveProjectCategory()` | `_resolve_project_category()` |
| `normalizeProjectType()` | `_normalize_project_type()` |
| `prNameToType` / `prNoToType` maps | `_get_pr_type_maps()` |
| `HIDDEN_OTHERS_DOCTYPES` | `HIDDEN_OTHERS_DOCTYPES` (module-level constant, same two names) |

The two-pass dance (§5 of the companion doc) disappears entirely — the backend already has the raw
record before it maps it into the summary shape, so it can pull the one extra link field it needs in
the *same* `frappe.get_list` call instead of a follow-up per-doctype fetch.

## 3. Data structures

```python
# One dict entry per doctype that can appear on the Pending Task page.
# strategy tuple: (kind, field) where kind is one of:
#   "self"          record IS the Project Registration (looked up by its own name)
#   "pr_name"       field holds the PR's `name` (docname)
#   "pr_project_no" field holds the PR's `project_no`
#   "direct_type"   field already holds the project_type text (e.g. a fetch_from field)
DOCTYPE_PR_LINKS = {
	"Project Registration": {"primary": ("self", None)},

	"Account Head Payment":  {"primary": ("pr_name", "project_ref_number")},
	"Advance Settlement":    {"primary": ("pr_name", "project_name"), "fallback": ("pr_project_no", "project_code")},
	"Deposit slip":          {"primary": ("pr_name", "project_title")},
	"Deposit Slip Project Credit": {"primary": ("pr_name", "project_number")},
	"Disbursement of Honorarium":  {"primary": ("pr_name", "project_number")},
	"E Non Routine Deposit Slip":  {"primary": ("pr_name", "project_title")},
	"Fund Received":         {"primary": ("pr_name", "prjreg_title")},
	"Fund Sanction":         {"primary": ("direct_type", "project_type_linked"), "fallback": ("pr_name", "project_proposal")},
	"Indent Cum Sanction Sheet": {"primary": ("pr_name", "project_ref"), "fallback": ("pr_project_no", "project_no")},
	"Indent General Form":   {"primary": ("pr_name", "igf_project_title"), "fallback": ("pr_project_no", "igf_project_code")},
	"Loan Request":          {"primary": ("pr_name", "project_name"), "fallback": ("pr_project_no", "project_number")},
	"Miscellaneous Commit":  {"primary": ("pr_name", "project_number")},
	"myProjects":            {"primary": ("pr_name", "project_proposal")},
	"payments":              {"primary": ("pr_name", "project_id")},
	"Project Extension":     {"primary": ("pr_name", "project_ref"), "fallback": ("pr_project_no", "prj_num")},
	"Project Staff Resignation": {"primary": ("pr_project_no", "applicant_prj_num")},
	"Project Staff Extension":   {"primary": ("pr_project_no", "ex_proj_no")},
	"proprietary_purchase":  {"primary": ("pr_name", "project_ref"), "fallback": ("pr_project_no", "project_no")},
	"Rate Contract":         {"primary": ("pr_name", "project_number")},
	"Reimbursement":         {"primary": ("pr_name", "project_name"), "fallback": ("pr_project_no", "project_number")},
	"Research Consultancy Deposit Slip": {"primary": ("pr_name", "project_title"), "fallback": ("pr_project_no", "project_number")},
	"Research Deposit Slip": {"primary": ("pr_name", "project_title"), "fallback": ("pr_project_no", "project_no")},
	"standerdized_purchase": {"primary": ("pr_name", "project_ref"), "fallback": ("pr_project_no", "project_no")},
	"T Testing Deposit Slip":{"primary": ("pr_name", "project_title")},
	"Travel":                {"primary": ("pr_name", "travel_project_title"), "fallback": ("pr_project_no", "travel_project_number")},
	"UC Request":            {"primary": ("pr_name", "project_id")},

	"Direct Purchase":       {"primary": ("pr_project_no", "project_no")},
	"Disbursal of Consultancy": {"primary": ("pr_project_no", "disbursal_project_number")},
	"Disbursal of Honorarium":  {"primary": ("pr_project_no", "project_no")},
	"Endorsement Data":      {"primary": ("pr_project_no", "project_no")},
	"Extension Of Tenure Of Appointment": {"primary": ("pr_project_no", "project_number")},
	"P_11 Form":             {"primary": ("pr_project_no", "project_no")},
	"Recruitment Adhoc Contractual": {"primary": ("pr_project_no", "upfa_project_code")},
	"Selection Committee Report":    {"primary": ("pr_project_no", "project_number")},
	"repair_replacement":    {"primary": ("pr_project_no", "project_no")},
	"sanction_sheet":        {"primary": ("pr_project_no", "project_no")},
	"TA DA Settlement":      {"primary": ("pr_project_no", "project_no")},
	"Temporary Advance":     {"primary": ("pr_project_no", "project_code")},
	"Top Up Fellowship":     {"primary": ("pr_project_no", "project_no")},
}

HIDDEN_OTHERS_DOCTYPES = {"Kafka Commit Staging", "Project Number Generation"}
```

Kept as a plain module-level dict (not a class) to mirror the TS table 1:1 — a diff against
`projectTypeMapping.ts` should stay easy for anyone maintaining both sides.

## 4. Helper functions

```python
def _get_pr_type_maps():
	"""prNameToType / prNoToType, built from one lightweight Project Registration query."""
	prs = frappe.get_all(
		"Project Registration",
		fields=["name", "project_no", "project_type"],
		limit_page_length=0,  # no cap — mirrors the FE's limit:1000, but uncapped server-side
	)
	name_to_type, no_to_type = {}, {}
	for p in prs:
		if p.name:
			name_to_type[p.name] = p.project_type or ""
		if p.project_no:
			no_to_type[p.project_no] = p.project_type or ""
	return name_to_type, no_to_type


def _normalize_project_type(raw):
	t = (raw or "").lower()
	if "research" in t:
		return "Research"
	if "consult" in t:
		return "Consultancy"
	return "Others"


def _resolve_project_category(record, doctype, name_to_type, no_to_type):
	mapping = DOCTYPE_PR_LINKS.get(doctype)
	if not mapping:
		return "Others"

	def apply(strategy):
		kind, field = strategy
		if kind == "self":
			return name_to_type.get(record.get("name"))
		if kind == "direct_type":
			return record.get(field)
		if kind == "pr_name":
			return name_to_type.get(record.get(field))
		if kind == "pr_project_no":
			return no_to_type.get(record.get(field))
		return None

	primary = apply(mapping["primary"])
	if primary:
		return _normalize_project_type(primary)

	fallback = mapping.get("fallback")
	if fallback:
		val = apply(fallback)
		if val:
			return _normalize_project_type(val)

	return "Others"
```

Direct, line-for-line port of §4's TS — same primary → fallback → `"Others"` order, same
short-circuit on falsy values.

## 5. Wiring into `get_pending_task`

Three targeted edits to the existing function ([module_registry.py:38](module_registry.py#L38)), no
restructuring of the workflow/permission logic above it:

**a) Signature + one-time setup** (top of the function, alongside the existing role/dept lookups):

```python
@frappe.whitelist()
def get_pending_task(page_name="pending-task", type=None):
	...
	if type and type not in ("Research", "Consultancy", "Others"):
		frappe.throw(f"Invalid type '{type}'. Must be Research, Consultancy, or Others.")

	pr_name_to_type, pr_no_to_type = _get_pr_type_maps()
	tab_counts = {"Research": 0, "Consultancy": 0, "Others": 0}
```

**b) Field list augmentation** — right before the `frappe.get_list(...)` calls at
[module_registry.py:104](module_registry.py#L104) (Advance Settlement branch) and
[module_registry.py:231](module_registry.py#L231) (standard branch), append whichever link field(s)
`DOCTYPE_PR_LINKS[dt]` needs:

```python
category_mapping = DOCTYPE_PR_LINKS.get(dt)
category_fields = []
if category_mapping:
	for strategy in (category_mapping.get("primary"), category_mapping.get("fallback")):
		if strategy and strategy[0] != "self" and strategy[1] not in category_fields:
			if meta.has_field(strategy[1]):
				category_fields.append(strategy[1])

fields = ["name", title_field, status_field, "modified", "owner", "docstatus", "creation"] \
	+ extra_fields + category_fields
```

(`meta.has_field` guard matters — a few doctypes list a fallback field that doesn't exist on every
site/customization; skip it rather than let `frappe.get_list` error.)

**c) Resolve + filter**, in the per-record mapping loop at
[module_registry.py:247-276](module_registry.py#L247-L276):

```python
mapped = []
for r in records:
	... # existing head_field / Travel dept-head skip logic, unchanged

	category = _resolve_project_category(r, dt, pr_name_to_type, pr_no_to_type)
	if category == "Others" and dt in HIDDEN_OTHERS_DOCTYPES:
		continue  # never surface these in the Others bucket — same rule as the FE today

	tab_counts[category] += 1

	if type and category != type:
		continue  # doesn't match the requested tab, but already counted above

	mapped.append({
		"name": r.get("name"),
		"title": r.get(title_field),
		"status": r.get(status_field),
		"creation": r.get("creation"),
		"modified": r.get("modified"),
		"owner": r.get("owner"),
		"docstatus": r.get("docstatus"),
		"project_type": category,
	})
```

The same `_resolve_project_category` / `tab_counts` accumulation has to run for the Advance Settlement
branch too (§ "A) Special Case" at [module_registry.py:101-130](module_registry.py#L101-L130)), since it
builds its own `mapped` list outside the standard-branch code path.

**d) Response shape:**

```python
return {
	"page": page_name,
	"user": current_user,
	"tab_counts": tab_counts,
	"results": results,
}
```

`tab_counts` is always the full, unfiltered breakdown — computed once per request regardless of
whether `type` was passed, so the frontend can render all three tab badges from a single call even
when only one tab's rows are loaded.

## 6. Special cases

- **`Fund Sanction` (`direct_type`)** — no extra lookup needed at all; `project_type_linked` is a
  Frappe `fetch_from` field already sitting on the record, so appending it to `fields` and reading it
  straight off `r` in `apply()` is sufficient. No fallback query.
- **`Top Up Fellowship`** — the companion doc's §5 "Phase-2b" existed because the frontend's generic
  pass-2 fetch wasn't reliably covering it (TUF only stores `project_no`, no PR docname field at all).
  Server-side there's no such gap: `project_no` is fetched in the same `frappe.get_list` call as
  everything else, so **no special-cased second pass is needed here** — this is a straight
  simplification versus the FE, not a port.
- **`TA DA Settlement`** — the companion doc's note "(resolved via Travel → project_no)" is provenance,
  not a live join: the doctype has its own `project_no` field already populated at creation time.
  Treat it as a normal `pr_project_no` strategy; no Travel lookup required at request time.
- **Doctypes not in `DOCTYPE_PR_LINKS`** — `_resolve_project_category` returns `"Others"` immediately
  (no `category_fields` appended, no extra query cost) — matches `if (!mapping) return 'Others';` in
  the TS today.

## 7. Performance & caching

`_get_pr_type_maps()` is one query returning `name, project_no, project_type` for every Project
Registration — cheap (3 columns, no joins) but runs on every `get_pending_task` call. Two options,
in order of preference:

1. **Ship without caching first.** This single query replaces what the frontend currently does
   (fetch **all** PRs client-side *plus* N per-doctype re-fetch queries), so even uncached this is
   already strictly less backend + network work than today. Measure before optimizing further.
2. **If needed:** wrap in `frappe.cache().get_value("pr_type_maps", generator=..., expires_in_sec=60)`,
   and add a `doc_events` hook on `Project Registration` (`on_update`, `on_trash`) in `hooks.py` that
   calls `frappe.cache().delete_value("pr_type_maps")` so a project-type edit is reflected immediately
   rather than waiting out the TTL.

The per-doctype field augmentation (§5b) adds at most one or two extra columns to queries that already
run today — no additional round-trips.

## 8. Rollout

1. Land the backend change as purely additive (`type` optional, existing callers unaffected — they'll
   just start receiving `project_type` per record and `tab_counts`, which is safe to ignore).
2. Update `PendingTask.tsx` to pass `type: selectedProjectType` on the `get_pending_task` call and
   drop: the `useFrappeGetDocList("Project Registration", ...)` fetch, the `prNameToType`/`prNoToType`
   memo, the pass-2 `useEffect` (including the TUF phase-2b branch), `resolvedProjectTypes` state, and
   the client-side `HIDDEN_OTHERS_DOCTYPES` filter — all superseded by the backend response. Tab badge
   counts come from `tab_counts` instead of a client-side `.filter().length` over `visibleTasks`.
3. Leave `projectTypeMapping.ts` in place but unused by `PendingTask.tsx` until `TaskRegistry.tsx` is
   migrated the same way (§9) — only remove it once both pages are off it.
4. **Validation before removing the old client logic:** for a sample of real users/doctypes, diff the
   old client-computed `project_type` per task against the new `project_type` field returned by the
   backend. They must match exactly (same `DOCTYPE_PR_LINKS` table, same precedence rules) before the
   frontend two-pass code is deleted.

## 9. Follow-up (not in this plan's scope)

`TaskRegistry.tsx` calls `get_task_registry` and runs the identical client-side classification. Once
`get_pending_task` has shipped and been validated, apply the same `type` param + `tab_counts` pattern
to `get_task_registry` ([module_registry.py](module_registry.py), the `get_document_touch_history`
neighbor) so `DOCTYPE_PR_LINKS` / `_resolve_project_category` / `_normalize_project_type` end up with
exactly one caller-agnostic implementation on the backend, shared by both endpoints.
