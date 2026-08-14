# Travel / TA-DA Settlement Merge Report

Merge of remote branch `Travel-TADASetlle-OfficeApprovalform-Director-Approval`
(commit `fbc183f`) into `mythos_omni_v0.5` (commit `71c40f3`), common ancestor
`df45dbf`. **Staged, not committed** at the time of this report.

Rule applied: travel/TA-DA-related changes were merged in; everything else
the Travel branch touched was left as-is on our side (discarded).

---

## 1. Added

### New doctypes (from the Travel branch, no conflict — pulled in as-is)

| Doctype | Files |
|---|---|
| **TA DA Journey Particular** | `doctype/ta_da_journey_particular/{__init__.py, ta_da_journey_particular.json, ta_da_journey_particular.py}` |
| **TA DA Local Conveyance Particular** | `doctype/ta_da_local_conveyance_particular/{__init__.py, ta_da_local_conveyance_particular.json, ta_da_local_conveyance_particular.py}` |
| **TA DA Supporting Document** | `doctype/ta_da_supporting_document/{__init__.py, ta_da_supporting_document.json, ta_da_supporting_document.py}` |

### `TA DA Settlement` — restructured (774 lines changed in the JSON; effectively a rebuild)

New child tables wired in via `field_order`:

- `ta_da_journey_particulars_table` → **TA DA Journey Particular**
- `ta_da_local_conveyance_table` → **TA DA Local Conveyance Particular**
- `ta_da_supporting_docs` → **TA DA Supporting Document** (new `supporting_docs_section` + `submission_instructions_html`)

New **"For Office Use" section** (`for_office_use_section`), filled in only by
`staff, RnD` while the doc sits at *Pending Staff Approval*:
`railways_air_steamer_busfare`, `road_mileage`, `local_conveyance`,
`food_charges`, `cccommodation_charges`, `registration_fee_other`,
`total_admissible_amount`, `less_advance_paid_to_applicant`, `net_amount`.

`ta_da_settlement.py` (+192 lines): adds `OFFICE_USE_INPUT_FIELDS`,
`can_edit_office_use_fields()` (role gate: `staff, RnD` / `System Manager` /
`Administrator`), `_resolve_ta_da_project_docname()` (resolves the owning
Project Registration via the linked Travel doc, for MinIO file grouping),
and `_upload_ta_da_file_to_minio()`.

### `Travel` doctype — new field

- `director_signed_pdf` (Attach, hidden, `allow_on_submit`, `no_copy`,
  `read_only`) — the Director's signed review copy, uploaded by `staff, RnD`.
- `selection_arrangement` (Select, "Is Arrangement done?", `\nYes\nNo`) —
  **replaces** `alternative_arrangement` (see §2).
- `field_order`: `selection_arrangement` inserted before
  `travel_classes_arrangement`; `director_signed_pdf` inserted before
  `workflow_state`.

### `travel.py` — new Director Approval workflow support (+116 lines)

- `DIRECTOR_UPLOAD_ROLES = ["staff, RnD", "RnD Staff", "R&D Staff", "System Manager"]`
- `attach_director_pdf_travel(docname, file_url)` — `staff, RnD` attaches the
  signed PDF once the doc is `Pending Director Approval`.
- `get_pending_travel_director_uploads()` — lists Travel docs awaiting a
  Director-signed copy, for the staff upload screen.
- `get_travel_workflow_actions` / `perform_travel_action` now call
  `frappe.model.workflow.is_transition_condition_satisfied(transition, doc)`
  before allowing a transition — this is what actually gates the new
  Director-approval branch on `doc.nature_of_travel == "International"`
  (a real Workflow condition, not a doctype flag).
- `get_travel_fields()`: the injected SCL-balance HTML/`scl_balance` now
  computes for **the document's own traveler**
  (`related_data.webmail_id_travel`) when viewing an *existing* document,
  instead of always the current viewer — fixes an approver seeing their own
  (usually nonexistent) leave balance instead of the applicant's.

### `api.py` (+52 lines, both new, additive, no conflict)

- `get_declaration_html(doctype)` — returns every `fieldtype="HTML"`
  DocField's content on a doctype, keyed by fieldname (bypasses `DocField`
  permission restrictions for this read-only lookup). Built for Travel's and
  TA DA Settlement's declaration/instruction text in print PDFs.
- `get_user_designation(email)` — returns a `User`'s `designation_name`
  without hitting the `User` doctype's own read-permission restriction; used
  to label approvers in the Activity Log print section.

### Patch registration

- `rndopsapp/patchs/add_travel_director_approval_workflow.py` (new, 96 lines)
  — installs the `Pending Director Approval` workflow state/transitions.
- `rndopsapp/patches.txt` — added
  `rndopsapp.patchs.add_travel_director_approval_workflow` under
  `[post_model_sync]`, alongside the existing (ours)
  `rndopsapp.patchs.add_igf_director_approval_state`. Both lines kept.

---

## 2. Removed

- **`Travel.alternative_arrangement`** (Select, Yes/No) — field definition
  deleted outright, along with its `field_order` entry. Superseded by
  `selection_arrangement` (§1), which `travel_classes_arrangement`'s
  `depends_on` now targets instead
  (`eval:doc.selection_arrangement == 'Yes';`, replacing the old
  `eval:doc.if_traveler == 'Self';` — note this also happens to fix a
  pre-existing typo, `if_traveller` → `if_traveler`, as a side effect of the
  field being retargeted, not a deliberate typo fix on either side).

No other fields, functions, or files were deleted by this merge — everything
else in §1 is purely additive.

---

## 3. Explicitly excluded (kept exactly as ours, not travel-related)

The Travel branch touched several files outside the travel/TA-DA scope.
Per the "travel files merge, else keep mine" rule, these were **not** pulled in:

| File | What theirs changed | Why excluded |
|---|---|---|
| `doctype/miscellaneous_commit/{miscellaneous_commit.js, miscellaneous_commit.py, test_miscellaneous_commit.py}` | Added the same doctype we already have (byte-identical except trailing newline) | Unrelated module (Priyam's "Miscellaneous Commit"), not travel |
| `doctype/proprietary_purchase/proprietary_purchase.json` | `pp_supplier_details` fieldtype `Data` → `Small Text` (ours is already `Long Text`) | Unrelated doctype |
| `kafka/producer/reimbursement/mapper.py` | Added an optional `commit_particular_override` param to `AccountHeadCommitMapper.map_to_dto`/`map_to_event` | We already have the same feature under the name `commit_particular` — not travel-specific, kept ours |
| `kafka/producer/reimbursement/producer.py` | Docstring wording only (functionally identical to ours) | Not travel-specific |
| `rndopsapp/rndopsapp/commitPayment.py` | (a) `LEDGER_API_BASE_URL` / `ACCOUNT_HEAD_PAYMENTS_API_URL` / `ACCOUNT_HEAD_COMMIT_API_URL` repointed from `172.16.134.81:18080` to `172.16.135.27:18083`; (b) new `get_commit_staging_status()` helper; (c) `commit_particular` plumbing added to `check_workflow_and_publish`/`manually_publish_staged_commit` | (a) looks like their own dev-environment endpoint — do **not** want that repointed silently; (c) generic, not travel-specific. **Reverted to ours in full** — except (b), which was added back separately afterward (see below), since it's a standalone read-only lookup with no dependency on (a) or (c). |
| `kafka/config.py` | `KAFKA_BOOTSTRAP_SERVERS` repointed from `172.16.134.81:*` to `172.16.135.118:*` | Environment-specific, not travel. **Reverted to ours in full.** |

**Update:** `get_commit_staging_status(reference_name, statuses=None,
required_payload_keys=None)` was added back into `commitPayment.py`
afterward, on request — same function body as the Travel branch, inserted
just above `submit_commit_data`. The endpoint URLs
(`172.16.134.81:18080`) were left untouched; nothing else from that file's
Travel-branch diff was pulled in.

**Flag for follow-up:** if Travel/TA DA Settlement's kafka-commit flow ever
needs to go through `commitPayment.py`'s generic staged-republish path
(`check_workflow_and_publish` / `manually_publish_staged_commit`) rather than
`travel.py`'s own direct `perform_travel_action` → `kafka_publish_commit`
call, the `commit_particular` wiring in `commitPayment.py` will need to be
re-added separately — it was excluded here only because it wasn't isolated
from the unrelated URL change.

---

## 4. Conflict resolution reference

| File | Conflict | Resolution |
|---|---|---|
| `rndopsapp/patches.txt` | Both branches appended a different patch line at the same spot | Kept both lines |
| `doctype/travel/travel.json` | `travel_classes_arrangement.depends_on` (ours: typo-fixed old field; theirs: new field) | Took theirs — references the field that actually still exists after the merge |
| `doctype/travel/travel.json` | `modified` timestamp | Took the later of the two (cosmetic only) |
| `doctype/miscellaneous_commit/*` (3 files) | add/add | Kept ours (content was identical anyway) |
| `doctype/proprietary_purchase/proprietary_purchase.json` | content | Kept ours |
| `kafka/producer/reimbursement/mapper.py` | content | Kept ours |
| `kafka/producer/reimbursement/producer.py` | content | Kept ours |
| `commitPayment.py`, `kafka/config.py` | auto-merged cleanly by git, but carried unrelated changes | Manually reverted to ours (`git checkout HEAD --`) after the merge |

---

## 5. Validation performed

- No conflict markers (`<<<<<<<` / `=======` / `>>>>>>>`) remain anywhere in
  the tree.
- All touched/resolved `.py` files parse (`ast.parse`).
- All touched/resolved `.json` files parse (`json.load`).
- Merge is **staged only** — `git status` shows no `UU` entries; nothing has
  been committed or pushed.
