# Project Registration — Linked DocTypes Report

**Scanned:** every DocType in a module matching `%rndopsapp%` (live `frappe.get_meta()` scan, not a static code read)
**Target DocType:** `Project Registration`
**Source:** live DocType metadata (fields + `fetch_from`)
**Date:** 2026-08-25 (regenerated — the 2026-06-24 version had drifted: see Changelog)

---

## ✅ Section 1 — Direct Links (fieldtype=Link, options=Project Registration)

These DocTypes have a formal `Link` field whose `options` is exactly **`Project Registration`**.
The **PR Field Being Mapped** column shows which field of `Project Registration` the linking DocType stores or fetches from.

> [!NOTE]
> In Frappe, a `Link` field always stores the **`name`** (document ID / autoname) of the target record.
> `Project Registration` uses autoname format: `{YYYY}{MM}{DD}{01}{fund_agen_initials}{######}` (e.g. `202507300DIIT000001`)
> Any `fetch_from` fields then pull additional PR fields (like `project_no`, `project_type`, etc.) automatically.

| # | Linking DocType | Link Field Name | Link Label | PR Field Stored (name) | Fetched PR Fields (fetch_from) | Is Direct Link |
|---|----------------|----------------|------------|------------------------|-------------------------------|----------------|
| 1 | **AccountHeadPayment** | `project_ref_number` | Project Ref Number | `name` (PR document ID) | — | ✅ Yes |
| 2 | **Advance Settlement** | `project_name` | Project Name | `name` (PR document ID) | — | ✅ Yes |
| 3 | **AMC** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 4 | **Deposit slip** | `project_title` | Project Title | `name` (PR document ID) | — | ✅ Yes |
| 5 | **Deposit Slip Project Credit** | `project_number` | Project Number | `name` (PR document ID) | — | ✅ Yes |
| 6 | **Disbursement of Honorarium** | `project_number` | Project Number | `name` (PR document ID) | — | ✅ Yes |
| 7 | **E Non Routine Deposit Slip** | `project_title` | Project Title | `name` (PR document ID) | — | ✅ Yes |
| 8 | **Fund Received** | `prjreg_title` | Project Title | `name` (PR document ID) | — | ✅ Yes |
| 9 | **Fund Sanction** | `project_proposal` | Project Registered | `name` (PR document ID) | `project_type` → `project_type_linked` | ✅ Yes |
| 10 | **Indent Cum Sanction Sheet** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 11 | **Indent General Form** | `igf_project_title` | Project Title | `name` (PR document ID) | `project_no` → `igf_project_code` | ✅ Yes |
| 12 | **Loan Request** | `project_name` | Project Title | `name` (PR document ID) | `project_no` → `project_number` | ✅ Yes |
| 13 | **Miscellaneous Commit** | `project_number` | Project Number | `name` (PR document ID) | — | ✅ Yes — **added 2026-08-25**, missing from the prior version of this report |
| 14 | **myProjects** | `project_proposal` | Project Proposal | `name` (PR document ID) | `other_project_type_name` → `principal_investigator` | ✅ Yes |
| 15 | **payments** | `project_id` | Project Id | `name` (PR document ID) | — | ✅ Yes |
| 16 | **Project Extension** | `project_ref` | Select project reference number | `name` (PR document ID) | `project_no` → `prj_num` | ✅ Yes |
| 17 | **Project Registration** | `amended_from` | Amended From | `name` (PR document ID) | — | ✅ Yes (self-ref) |
| 18 | **Project Verification** | `project` | Project | `name` (PR document ID) | — | ✅ Yes — **added 2026-08-25**, missing from the prior version of this report |
| 19 | **proprietary_purchase** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 20 | **Rate Contract** | `project_number` | Project Number | `name` (PR document ID) | — | ✅ Yes |
| 21 | **Rate Contract** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 22 | **Reimbursement** | `project_name` | Project Name | `name` (PR document ID) | — | ✅ Yes |
| 23 | **repair_replacement** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 24 | **Research Consultancy Deposit Slip** | `project_title` | Project Title | `name` (PR document ID) | `project_no` → `project_number`; `consultancy_gstin` → `gstin_of_funding_agency`; `pi_userid` → `principal_investigator` | ✅ Yes |
| 25 | **Research Deposit Slip** | `project_title` | Project Title | `name` (PR document ID) | `project_no` → `project_no`; `funding_agen` → `funding_agency` | ✅ Yes |
| 26 | **standerdized_purchase** | `project_ref` | Project Reference | `name` (PR document ID) | — | ✅ Yes |
| 27 | **T Testing Deposit Slip** | `project_title` | Project Title | `name` (PR document ID) | — | ✅ Yes |
| 28 | **Travel** | `travel_project_title` | Project Title | `name` (PR document ID) | `project_no` → `travel_project_number` | ✅ Yes |
| 29 | **UC Request** | `project_id` | Select Project | `name` (PR document ID) | — | ✅ Yes |

> **Removed 2026-08-25:** `Top Up Fellowship`'s `project_code` field is no longer a `Link` — the doctype has since been reworked to a plain `project_no` **Data** field plus a separate `project_title` **Long Text** field. It's been moved to Section 2 below.

---

### PR Fields Referenced via `fetch_from` (from Direct Links)

This sub-table shows exactly which **Project Registration fields** are being pulled into linked DocTypes:

| Linked DocType | Link Field | `fetch_from` Expression | PR Field Fetched | Stored In (Local Field) | Local Label |
|---------------|-----------|------------------------|-----------------|-------------------------|-------------|
| Fund Sanction | `project_proposal` | `project_proposal.project_type` | `project_type` | `project_type_linked` | Project Type |
| Indent General Form | `igf_project_title` | `igf_project_title.project_no` | `project_no` | `igf_project_code` | Project Code |
| Loan Request | `project_name` | `project_name.project_no` | `project_no` | `project_number` | Project Number |
| myProjects | `project_proposal` | `project_proposal.other_project_type_name` | `other_project_type_name` | `principal_investigator` | Principal Investigator |
| Project Extension | `project_ref` | `project_ref.project_no` | `project_no` | `prj_num` | Project Number |
| Research Consultancy Deposit Slip | `project_title` | `project_title.project_no` | `project_no` | `project_number` | Project Number |
| Research Consultancy Deposit Slip | `project_title` | `project_title.consultancy_gstin` | `consultancy_gstin` | `gstin_of_funding_agency` | GSTIN of Funding Agency |
| Research Consultancy Deposit Slip | `project_title` | `project_title.pi_userid` | `pi_userid` | `principal_investigator` | Principal Investigator |
| Research Deposit Slip | `project_title` | `project_title.project_no` | `project_no` | `project_no` | Project No |
| Research Deposit Slip | `project_title` | `project_title.funding_agen` | `funding_agen` | `funding_agency` | Funding Agency |
| Travel | `travel_project_title` | `travel_project_title.project_no` | `project_no` | `travel_project_number` | Project Number |

---

## ⚠️ Section 2 — Indirect / Partial Links (Data Fields Storing PR Identifiers)

These DocTypes store Project Registration identifiers as plain `Data`/`Long Text` fields — **no Frappe FK enforcement**, populated programmatically, via `fetch_from`, or manually.

| # | DocType | Field Name | Field Type | PR Field It Stores | Is Direct Link | Notes |
|---|---------|-----------|------------|--------------------|----------------|-------|
| 1 | **AMC** | `project_no` | Data | `project_no` | ❌ No | Companion to `project_ref` Link |
| 2 | **Advance Settlement** | `project_code` | Data | `project_no` (PR project number) | ❌ No | Companion to `project_name` Link; stores PR's `project_no` |
| 3 | **Direct Purchase** | `project_no` | Data | `project_no` | ❌ No | Stores PR project number directly |
| 4 | **Disbursal of Consultancy** | `project_title` | Long Text | PR title/name (string) | ❌ No | Standalone doctype; plain text, no FK |
| 5 | **Disbursal of Consultancy** | `disbursal_project_number` | Data | `project_no` | ❌ No | ⚠️ Field `options` is literally `"Select\nPDF"` — a leftover from a copy-pasted Select field config; harmless since fieldtype is Data, but worth cleaning up |
| 6 | **Disbursal of Honorarium** | `project_name` | Long Text | PR name/title (string copy) | ❌ No | Plain text, no FK |
| 7 | **Disbursal of Honorarium** | `project_no` | Data | `project_no` | ❌ No | Name pattern match |
| 8 | **dp_po** | `project_no` | Data | `project_no` | ❌ No | Direct Purchase PO; name pattern match |
| 9 | **Endorsement Data** | `project_no` | Data | `project_no` | ❌ No | Name pattern match |
| 10 | **Endorsement Data** | `project_ref_num` | Data | `project_no` (likely) | ❌ No | Second, differently-named project field on the same doctype — worth confirming which one is authoritative |
| 11 | **Extension Of Tenure Of Appointment** | `project_number` | Data | `project_no` | ❌ No | Label = "Project No." |
| 12 | **Extension Of Tenure Of Appointment** | `project_title` | Small Text | PR title (string) | ❌ No | Label = "Project name" |
| 13 | **ICSS_PO** | `project_number` | Data | `project_no` | ❌ No | Indent Cum Sanction Sheet PO; name pattern match |
| 14 | **Indent Cum Sanction Sheet** | `project_no` | Data | `project_no` | ❌ No | Companion read-only display; populated from `project_ref` Link |
| 15 | **Indent General Form** | `igf_project_code` | Data | `project_no` (via fetch_from) | ❌ No | Auto-filled via `igf_project_title.project_no` |
| 16 | **Leave Module** | `project_no` | Data | `project_no` | ❌ No | Not present in the prior version of this report |
| 17 | **Loan Request** | `project_number` | Data | `project_no` (via fetch_from) | ❌ No | Anomaly: has `options=Project Registration` but type=Data; fetched via `project_name.project_no` |
| 18 | **myProjects** | `project_title`, `project_id` | Data | PR title / id (string copies) | ❌ No | Supplementary to its own Section-1 `project_proposal` Link |
| 19 | **NIQ** | `project_no` | Data | `project_no` | ❌ No | Name pattern match |
| 20 | **P_11 Form** | `project_no` | Data | `project_no` | ❌ No | Name pattern match |
| 21 | **Proforma_Invoice** | `project_no` | Data | `project_no` | ❌ No | Not present in the prior version of this report |
| 22 | **proprietary_purchase** | `project_no` | Data | `project_no` | ❌ No | Companion to `project_ref` Link |
| 23 | **Rate Contract** | `project_no` | Data | `project_no` | ❌ No | Companion to `project_number` / `project_ref` Links |
| 24 | **Recruitment Adhoc Contractual** | `upfa_project_code` | Data | `project_no` | ❌ No | Copied from linked PR; upfa prefix = unified project fetch area |
| 25 | **Recruitment Adhoc Contractual** | `upfa_project_title` | Long Text | PR title (string) | ❌ No | Not present in the prior version of this report |
| 26 | **Recruitment Adhoc Contractual** | `upfa_project_duration` | Data | PR duration (string) | ❌ No | Not present in the prior version of this report |
| 27 | **Reimbursement** | `project_number` | Data | `project_no` | ❌ No | Anomaly: `options=Project Registration` but type=Data |
| 28 | **repair_replacement** | `project_no` | Data | `project_no` | ❌ No | Name pattern match; companion to `project_ref` Link |
| 29 | **Research Consultancy Deposit Slip** | `project_number` | Data | `project_no` (via fetch_from) | ❌ No | Auto-filled via `project_title.project_no` |
| 30 | **Research Deposit Slip** | `project_no` | Data | `project_no` (via fetch_from) | ❌ No | Auto-filled via `project_title.project_no` |
| 31 | **sanction_sheet** | `project_no` | Data | `project_no` | ❌ No | Name pattern match |
| 32 | **Selection Committee Report** | `project_name` | Long Text | PR title (string) | ❌ No | Fetched via `interview_id.upfa_project_title` (indirect chain) |
| 33 | **Selection Committee Report** | `project_number` | Data | `project_no` | ❌ No | Fetched via `interview_id.upfa_project_code` (indirect chain) |
| 34 | **Staff Activity Log** | `project_no` | Data | `project_no` | ❌ No | Not present in the prior version of this report |
| 35 | **standerdized_purchase** | `project_no` | Data | `project_no` | ❌ No | Companion to `project_ref` Link |
| 36 | **TA DA Settlement** | `project_no` | Data | `travel_project_number` from Travel (which fetches from PR) | ❌ No | Indirect chain: `ta_da_travel_application.travel_project_number` |
| 37 | **Temporary Advance** | `project_code` | Data | `project_no` | ❌ No | Name pattern match |
| 38 | **Temporary Advance** | `project_name` | Long Text | PR title (string) | ❌ No | Plain text |
| 39 | **Top Up Fellowship** | `project_no` | Data | `project_no` | ❌ No | **Moved here 2026-08-25** — its `project_code` field is no longer a Link (see Section 1 note) |
| 40 | **Top Up Fellowship** | `project_title` | Long Text | PR title (string) | ❌ No | **Moved here 2026-08-25** |
| 41 | **Travel** | `travel_project_number` | Data | `project_no` (via fetch_from) | ❌ No | Auto-filled via `travel_project_title.project_no` |
| 42 | **User Delegation** | `project_names` | Long Text | PR names (JSON array) | ❌ No | Stores multiple PR `name` values as JSON string; no FK enforcement |

---

## 🧩 Section 3 — Related But Not a Per-Record Reference

These doctypes mention "project" fields but don't reference an *existing* Project Registration the way Sections 1–2 do — kept separate so they don't inflate the relationship count with a different kind of relationship:

| DocType | Field(s) | Why it's different |
|---------|---------|---------------------|
| **Project Proposal** | `project_title`, `project_objective`, `project_deliverables`, `other_project_type_name` | This is the *pre-registration* doctype — a Project Proposal is what later becomes a Project Registration once approved. Its project fields describe a project that doesn't have a PR record yet, so there's nothing to link to. |
| **Project Number Generation** | `project_no` | This doctype *generates* the `project_no` sequence that Project Registration then consumes — it's the source, not a consumer/reference. |
| **Kafka Event DLQ Log** | `project_number` | Internal dead-letter-queue log row carrying a project number for correlation/debugging — not a user-facing application. |
| **Kafka Payment DLQ Log** | `project_number` | Same as above — internal telemetry, not an application. |
| **Project Account and Scheme Details** | `existing_project_number` | Likely references a PR's `project_no`, but the doctype's exact usage wasn't confirmed against live data for this report — flagged for follow-up rather than asserted. |

---

## 🔑 Project Registration Fields Summary (Most Mapped)

| PR Field | Field Type | Description | Referenced By |
|----------|-----------|-------------|---------------|
| `name` (autoname) | Data | Primary document ID — format: `YYYYMMDDnFUND######` | All 29 direct Link rows (Section 1) |
| `project_no` | Data | Human-readable project number (assigned internally) | 20+ DocTypes via `fetch_from` or direct Data fields (Section 2) |
| `project_type` | Select | Research / Consultancy / Other | `Fund Sanction` → `project_type_linked` |
| `consultancy_gstin` | Data | GSTIN of funding agency | `Research Consultancy Deposit Slip` → `gstin_of_funding_agency` |
| `pi_userid` | Link (User) | Principal Investigator user | `Research Consultancy Deposit Slip` → `principal_investigator` |
| `funding_agen` | Link | Funding agency reference | `Research Deposit Slip` → `funding_agency` |
| `other_project_type_name` | Data | Custom project type name | `myProjects` → `principal_investigator` (mismatch — likely a bug) |

---

## 🔴 Notable Anomalies

| Issue | DocType | Field | Detail |
|-------|---------|-------|--------|
| `Data` field with `options = 'Project Registration'` | Loan Request | `project_number` | fieldtype=Data but options=Project Registration — no FK enforcement |
| `Data` field with `options = 'Project Registration'` | Reimbursement | `project_number` | Same anomaly |
| Stray `options` value on a Data field | Disbursal of Consultancy | `disbursal_project_number` | `options` is literally `"Select\nPDF"`, left over from what looks like a copy-pasted Select field — has no effect since the fieldtype is Data, but should be cleaned up |
| Mismatched fetch_from label | myProjects | `principal_investigator` | Fetches `other_project_type_name` from PR but stores it as "Principal Investigator" — likely a design bug |
| Self-referential Link | Project Registration | `amended_from` | Standard Frappe amendment field |
| Rate Contract has two Link fields | Rate Contract | `project_number`, `project_ref` | Both are Link to Project Registration — likely one is redundant |
| Two differently-named project fields | Endorsement Data | `project_no`, `project_ref_num` | Unclear which is authoritative — worth consolidating |

---

## 📊 Summary Count

| Category | Count |
|----------|-------|
| DocTypes with **Direct Links** (fieldtype=Link, options=Project Registration) | **28 unique doctypes (29 link rows)** |
| Unique PR fields referenced via `fetch_from` | **7** (`project_no`, `project_type`, `consultancy_gstin`, `pi_userid`, `funding_agen`, `other_project_type_name`, fetched in Travel too) |
| DocTypes with **Indirect Data references only** | **19 additional** (not already counted in Section 1) |
| Related but not a per-record reference (Section 3) | **5** (kept separate — see above) |
| Anomalous `Data` fields with `options=Project Registration` | **2** |
| **Total DocTypes with a direct-record PR relationship** (Section 1 ∪ Section 2) | **47** |

---

## 🗂️ Consolidated Alphabetical Index

| DocType | Direct Link Field(s) | PR Field Stored | Fetched PR Fields | Indirect Data Fields |
|---------|---------------------|----------------|-------------------|---------------------|
| AccountHeadPayment | `project_ref_number` | `name` | — | — |
| Advance Settlement | `project_name` | `name` | — | `project_code` → `project_no` |
| AMC | `project_ref` | `name` | — | `project_no` |
| Deposit slip | `project_title` | `name` | — | — |
| Deposit Slip Project Credit | `project_number` | `name` | — | — |
| Direct Purchase | — | — | — | `project_no` |
| Disbursal of Consultancy | — | — | — | `project_title`, `disbursal_project_number` |
| Disbursal of Honorarium | — | — | — | `project_name`, `project_no` |
| Disbursement of Honorarium | `project_number` | `name` | — | — |
| dp_po | — | — | — | `project_no` |
| E Non Routine Deposit Slip | `project_title` | `name` | — | — |
| Endorsement Data | — | — | — | `project_no`, `project_ref_num` |
| Extension Of Tenure Of Appointment | — | — | — | `project_number`, `project_title` |
| Fund Received | `prjreg_title` | `name` | — | — |
| Fund Sanction | `project_proposal` | `name` | `project_type` | — |
| ICSS_PO | — | — | — | `project_number` |
| Indent Cum Sanction Sheet | `project_ref` | `name` | — | `project_no` |
| Indent General Form | `igf_project_title` | `name` | `project_no` | `igf_project_code` |
| Leave Module | — | — | — | `project_no` |
| Loan Request | `project_name` | `name` | `project_no` | `project_number` (Data anomaly) |
| Miscellaneous Commit | `project_number` | `name` | — | — |
| myProjects | `project_proposal` | `name` | `other_project_type_name` | `project_title`, `project_id` |
| NIQ | — | — | — | `project_no` |
| P_11 Form | — | — | — | `project_no` |
| payments | `project_id` | `name` | — | — |
| Proforma_Invoice | — | — | — | `project_no` |
| Project Extension | `project_ref` | `name` | `project_no` | — |
| Project Registration | `amended_from` | `name` (self) | — | — |
| Project Verification | `project` | `name` | — | — |
| proprietary_purchase | `project_ref` | `name` | — | `project_no` |
| Rate Contract | `project_number`, `project_ref` | `name` | — | `project_no` |
| Recruitment Adhoc Contractual | — | — | — | `upfa_project_code`, `upfa_project_title`, `upfa_project_duration` |
| Reimbursement | `project_name` | `name` | — | `project_number` (Data anomaly) |
| repair_replacement | `project_ref` | `name` | — | `project_no` |
| Research Consultancy Deposit Slip | `project_title` | `name` | `project_no`, `consultancy_gstin`, `pi_userid` | `project_number` |
| Research Deposit Slip | `project_title` | `name` | `project_no`, `funding_agen` | `project_no` |
| sanction_sheet | — | — | — | `project_no` |
| Selection Committee Report | — | — | — | `project_name` (Long Text), `project_number` |
| Staff Activity Log | — | — | — | `project_no` |
| standerdized_purchase | `project_ref` | `name` | — | `project_no` |
| T Testing Deposit Slip | `project_title` | `name` | — | — |
| TA DA Settlement | — | — | — | `project_no` (via Travel chain) |
| Temporary Advance | — | — | — | `project_code`, `project_name` |
| Top Up Fellowship | — | — | — | `project_no`, `project_title` |
| Travel | `travel_project_title` | `name` | `project_no` | `travel_project_number` |
| UC Request | `project_id` | `name` | — | — |
| User Delegation | — | — | — | `project_names` (Long Text JSON) |

---

## Changelog

- **2026-08-25** — Regenerated against live DocType metadata instead of a static read. Changes from the 2026-06-24 version:
  - Added `Miscellaneous Commit` and `Project Verification` to Section 1 (both had a genuine `Link` to Project Registration that the prior version missed).
  - Moved `Top Up Fellowship` from Section 1 to Section 2 — its `project_code` field is no longer a `Link` (now a plain `project_no` Data field + separate `project_title` Long Text field).
  - Added 8 previously-missing doctypes to Section 2: `Leave Module`, `Proforma_Invoice`, `Staff Activity Log`, plus extra fields on `Disbursal of Consultancy`, `Endorsement Data`, `Extension Of Tenure Of Appointment`, `myProjects`, and `Recruitment Adhoc Contractual` that weren't in the prior audit.
  - Added Section 3 to separate out `Project Proposal`, `Project Number Generation`, the two Kafka DLQ logs, and `Project Account and Scheme Details` — these mention "project" fields but aren't a reference to an *existing* Project Registration the way everything else in this report is, so folding them into the main count would have been misleading.
  - Total relationship count moved from 45 (claimed, though the old alphabetical index only actually listed 43) to a verified **47**.
