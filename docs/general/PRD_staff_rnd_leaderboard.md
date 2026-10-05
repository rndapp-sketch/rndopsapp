# PRD: Staff RnD Role Leaderboard & Profile Analytics

**Version:** 1.0  
**Date:** 2026-07-01  
**Author:** RnD Ops Team  
**Status:** Draft

---

## 1. Overview

This document defines the product requirements for a **Staff RnD Leaderboard** — a system that ranks RnD office staff members by their form-processing activity within the rndopsapp Frappe application. The feature provides visibility into workload distribution, throughput efficiency, and individual contribution metrics for all roles involved in the multi-stage approval workflow.

---

## 2. Problem Statement

The RnD operations office processes hundreds of forms across 40+ doctype categories (purchases, advances, travel, recruitment, project registration, etc.). Currently there is no visibility into:

- Which staff members are processing the most forms
- How long each person takes to action a pending form
- Whether workload is evenly distributed across the team
- Individual productivity trends over time
- Which form types create bottlenecks at each role

This creates blind spots for administrators trying to manage staffing capacity and identify high performers or overloaded personnel.

---

## 3. Goals

| Goal | Priority |
|------|----------|
| Rank RnD staff by total forms processed per period | P0 |
| Show per-user breakdown by form type and action taken | P0 |
| Track average processing time (time from assignment to action) | P1 |
| Enable filtering by date range, role, and form type | P1 |
| Individual staff profile page with full history | P1 |
| Trend charts (weekly / monthly throughput) | P2 |
| Export leaderboard data to CSV | P2 |

### Non-Goals

- Does not replace the existing workflow or approval chain
- Does not gamify or publicly rank staff in a competitive way by default (view is admin-only)
- Does not track forms created by Project Staff / Principal Investigators (submitter roles are tracked separately)
- Does not affect form routing or approvals

---

## 4. Roles in Scope

These are the roles whose form-processing actions are tracked in the leaderboard:

| Role | Workflow Stage Handled |
|------|----------------------|
| `staff, RnD` | Pending Staff Approval → forwards or rejects |
| `Hos, RnD (Head of Section, RnD)` | Pending HoS Approval |
| `Associate Dean, RND` | Pending Associate Dean |
| `Dean, RnD` | Pending Dean Approval |
| `Director` | Pending Director Approval |
| `Principal Investigator` | Pending PI Approval |
| `HoD (Head of Department)` | Pending HoD Approval |
| `Mentor` | Pending Mentor Approval |

> **Note:** `Project Staff`, `Independent Researcher`, `Permanent Employee`, and `Inspire Faculty` are *submitter* roles (they create forms at Draft state). Their creation metrics are tracked separately under "Forms Submitted" — they do not appear on the approver leaderboard.

---

## 5. Metrics Definitions

### 5.1 Core Metrics (per user, per period)

| Metric | Definition |
|--------|-----------|
| **Forms Processed** | Total unique form records where the user performed a workflow transition (Approve / Reject / Forward) |
| **Forms Approved** | Forms where the user transitioned to an Approve / Forward action |
| **Forms Rejected** | Forms where the user transitioned to a Rejected state |
| **Avg. Processing Time** | Mean time (hours) between when a form entered the user's queue (workflow_state set to their pending state) and when the user acted on it |
| **Forms Pending** | Count of forms currently in the user's pending state (live queue depth) |
| **Forms Submitted** | (Submitter roles only) Count of Draft → first workflow submission actions |

### 5.2 Leaderboard Score

The leaderboard ranks by **Forms Processed** within the selected period. Ties are broken by Avg. Processing Time (lower = better).

### 5.3 Form Type Breakdown

For each user, show counts split by form category:

| Category | Form Doctypes |
|----------|--------------|
| **Purchase** | Direct Purchase, Proprietary Purchase, Standardized Purchase, Repair & Replacement, Indent General Form, Indent Cum Sanction Sheet, Rate Contract, NIQ, AMC, DP PO |
| **Financial** | Temporary Advance, Advance Settlement, TA/DA Settlement, Reimbursement, Loan Request, P-11 Form |
| **Project** | Project Registration, Project Proposal, Project Extension, Fund Received, Fund Sanction, Project Sanction Details, UC Request |
| **HR / Staff** | Recruitment Adhoc Contractual, Project Staff Details, Extension of Tenure, Project Staff Resignation, Leave Module, Top Up Fellowship, Selection Committee Report |
| **Deposits** | Deposit Slip, Research Deposit Slip, Research Consultancy Deposit Slip, Disbursal of Consultancy, Disbursal of Honorarium, Disbursement of Honorarium |
| **Travel** | Travel |
| **IPR** | IPR Invention Disclosure |
| **Other** | Cancellation Request, Endorsement Data, Advance Settlement |

---

## 6. Feature Requirements

### 6.1 Leaderboard Page (`/rndops-leaderboard`)

**Access:** Users with `System Manager` or `staff, RnD` role (configurable).

**Filters:**
- **Period:** Today / This Week / This Month / This Quarter / Custom Date Range
- **Role:** All Roles / specific role dropdown
- **Form Category:** All / specific category (see Section 5.3)

**Leaderboard Table Columns:**

| # | Name | Role | Forms Processed | Approved | Rejected | Avg. Time (hrs) | Pending Now |
|---|------|------|----------------|----------|----------|-----------------|-------------|

- Ranked by Forms Processed descending
- Row click → opens individual staff profile
- Top 3 rows highlighted (gold / silver / bronze) — optional, togglable

**Summary Cards at Top:**
- Total forms processed (all staff, selected period)
- Fastest average processing time (min among all)
- Most active staff member name + count
- Total forms currently pending across all queues

### 6.2 Individual Staff Profile Page (`/rndops-leaderboard/<user_email>`)

**Header:** Full name, email, role(s), department, avatar/initials

**Stats Cards:**
- Forms Processed (this month)
- Forms Processed (all time)
- Approval Rate (%)
- Avg. Processing Time

**Form Breakdown Table:** Counts per form category (see 5.3), with approved / rejected split

**Recent Activity Feed:** Last 20 actions — date, form type, form name (link), action taken (Approved / Rejected / Forwarded), time taken

**Monthly Trend Chart:** Bar chart showing forms processed per month for the last 12 months

### 6.3 Admin Analytics View (`/rndops-leaderboard?tab=analytics`)

**Workload Distribution Chart:** Stacked bar chart — each role's share of total forms processed per month

**Bottleneck Heatmap:** Grid of [Role × Form Type] showing average processing time — highlights cells where avg time exceeds threshold (configurable, default 48 hours)

**Queue Depth Over Time:** Line chart showing pending-forms count per role per week (helps identify surges)

**Top Delayed Forms:** Table of forms that have been in a pending state longest (cross-user)

---

## 7. Data Model

### 7.1 Source of Truth

All 42 submittable doctypes share these standard Frappe fields used to derive metrics:

| Field | Source | Used For |
|-------|--------|---------|
| `owner` | All doctypes | Identifies form creator |
| `modified_by` | All doctypes | Identifies last actor |
| `modified` | All doctypes | Timestamp of last action |
| `workflow_state` | All doctypes | Current state |
| `creation` | All doctypes | Form submission time |

### 7.2 New Doctype: `Staff Activity Log`

To track **per-transition** events (not just the last modifier), a new log doctype is required. Frappe's built-in `Version` doctype can serve this purpose if `track_changes: 1` is enabled on target doctypes, but a dedicated log gives cleaner querying.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `user` | Link → User | Who performed the action |
| `doctype_name` | Data | Source doctype (e.g., "Direct Purchase") |
| `document_name` | Data | Name/ID of the document |
| `form_category` | Select | Category (Purchase / Financial / etc.) |
| `from_state` | Data | Workflow state before action |
| `to_state` | Data | Workflow state after action |
| `action` | Select | Approve / Reject / Forward / Submit |
| `timestamp` | Datetime | When the action happened |
| `time_in_queue` | Float | Hours the form was in user's queue before they acted |
| `project_no` | Data | Linked project number (if applicable) |

### 7.3 Log Population Strategy

**Hook:** Extend the existing `doc_events["*"]["on_update"]` in [hooks.py](rndopsapp/hooks.py) to call a new logger function alongside `commitPayment.check_workflow_and_publish`.

```python
# hooks.py
doc_events = {
    "*": {
        "on_update": [
            "rndopsapp.rndopsapp.commitPayment.check_workflow_and_publish",
            "rndopsapp.rndopsapp.activity_logger.log_workflow_transition"  # NEW
        ]
    }
}
```

**Logger logic (`activity_logger.py`):**

```python
TRACKED_DOCTYPES = {
    "Direct Purchase": "Purchase",
    "Proprietary Purchase": "Purchase",
    "Standerdized Purchase": "Purchase",
    "Temporary Advance": "Financial",
    "Travel": "Travel",
    "Reimbursement": "Financial",
    "Project Registration": "Project",
    "Recruitment Adhoc Contractual": "HR / Staff",
    # ... all 42 doctypes
}

APPROVAL_STATES = {
    "Approved", "Rejected", "Pending Staff Approval",
    "Pending HoS Approval", "Pending Associate Dean",
    "Pending Dean Approval", "Pending Director Approval",
    "Pending PI Approval", "Pending HoD Approval",
    "Pending Mentor Approval",
}

def log_workflow_transition(doc, method):
    if doc.doctype not in TRACKED_DOCTYPES:
        return
    if not hasattr(doc, 'workflow_state'):
        return
    # Detect state change via doc.get_doc_before_save()
    # Write Staff Activity Log entry
```

**Backfill:** A one-time migration script can backfill historical data by reading `modified_by`, `modified`, and `workflow_state` from all doctype tables. Exact per-transition history requires Frappe `Version` records if `track_changes` was enabled.

---

## 8. API Endpoints

All endpoints are whitelisted Frappe API methods returning JSON.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `rndopsapp.leaderboard.api.get_leaderboard` | GET | Returns ranked list with filters: `period`, `role`, `category` |
| `rndopsapp.leaderboard.api.get_staff_profile` | GET | Returns full profile for one user: `user`, `period` |
| `rndopsapp.leaderboard.api.get_analytics` | GET | Returns workload distribution data |
| `rndopsapp.leaderboard.api.get_pending_queue` | GET | Returns current queue depth per role |
| `rndopsapp.leaderboard.api.get_form_breakdown` | GET | Returns per-user, per-category counts |

---

## 9. UI/UX Specifications

### Page Structure

```
/rndops-leaderboard
├── Header: "RnD Staff Leaderboard"
├── Tab: Leaderboard | Analytics
├── Filter Bar: [Period ▾] [Role ▾] [Form Type ▾] [Export CSV]
├── Summary Cards: 4 metric tiles
└── Ranked Table (click → profile)

/rndops-leaderboard/<user>
├── Profile Header: Avatar | Name | Role | Department
├── Stat Cards: 4 tiles
├── Monthly Trend Chart
├── Form Breakdown Table
└── Recent Activity Feed (last 20 actions)
```

### Implementation as Frappe www Page

- Create `rndopsapp/www/rndops-leaderboard.py` (Python context provider)
- Create `rndopsapp/www/rndops-leaderboard.html` (Jinja template)
- Or implement as a Vue.js page under the existing `/frontend` route (see `website_route_rules` in [hooks.py](rndopsapp/hooks.py))

---

## 10. Implementation Plan

### Phase 1 — Data Layer (Week 1–2)

- [ ] Create `Staff Activity Log` doctype with fields defined in Section 7.2
- [ ] Implement `activity_logger.py` with `log_workflow_transition` function
- [ ] Register logger in `hooks.py` `doc_events`
- [ ] Write `TRACKED_DOCTYPES` map for all 42 submittable doctypes
- [ ] Write backfill migration script for historical data
- [ ] Unit tests for logger (correct state detection, edge cases)

### Phase 2 — API Layer (Week 2–3)

- [ ] Create `rndopsapp/leaderboard/` module with `api.py`
- [ ] Implement `get_leaderboard` with period/role/category filters
- [ ] Implement `get_staff_profile` with full history query
- [ ] Implement `get_pending_queue` (live queue depth)
- [ ] Implement `get_analytics` (distribution + heatmap data)
- [ ] Add permission checks (System Manager + `staff, RnD` role)

### Phase 3 — UI Layer (Week 3–4)

- [ ] Create leaderboard www page (Python + HTML or Vue.js route)
- [ ] Leaderboard table with filtering and sorting
- [ ] Summary cards
- [ ] Individual staff profile page
- [ ] Monthly trend chart (Chart.js or Frappe Charts)
- [ ] Bottleneck heatmap for analytics tab
- [ ] CSV export function
- [ ] Mobile-responsive layout

### Phase 4 — Testing & Rollout (Week 4–5)

- [ ] QA with real data on staging
- [ ] Performance test: leaderboard query with 12 months of data across 42 doctypes
- [ ] Add DB indexes on `Staff Activity Log` (`user`, `timestamp`, `doctype_name`)
- [ ] Confirm permissions: staff see own profile; managers see all
- [ ] Deploy and gather feedback from RnD office

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| Leaderboard page loads in < 2 seconds | 95th percentile |
| 100% of workflow transitions captured in activity log | From go-live date |
| Admin can filter and export within 3 clicks | Usability test |
| At least 80% of RnD staff can view their own profile | Adoption |
| Workload imbalance (max/min ratio) visible to admin | Dashboard available |

---

## 12. Open Questions

1. **Privacy:** Should individual staff be able to see each other's leaderboard, or only System Manager? Recommend: Self-view always allowed; full leaderboard only for managers/admins.
2. **Backfill depth:** How far back should historical data be backfilled — 6 months, 1 year, all time?
3. **Processing time baseline:** What is the SLA for each role to action a form? This determines "on time vs. delayed" classification in the heatmap.
4. **Tie-breaking on leaderboard:** Use Avg. Processing Time (lower = better) or alphabetical? Confirm with office head.
5. **Frappe Version tracking:** Should `track_changes: 1` be enabled on all 42 doctypes to get per-field history, or is the new `Staff Activity Log` sufficient?

---

## 13. References

- Workflow roles defined in: `rndopsapp/create_workflows.py`
- Workflow hook entry point: `rndopsapp/hooks.py` → `doc_events["*"]["on_update"]`
- Submittable doctypes list: all doctypes with `"is_submittable": 1` in their JSON under `rndopsapp/rndopsapp/doctype/`
- Active sessions page (pattern reference): `frappe/www/active_sessions.py`
- Existing www page: `rndopsapp/www/rndopsapp.html`
