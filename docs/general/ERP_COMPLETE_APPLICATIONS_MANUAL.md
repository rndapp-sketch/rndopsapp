# ProRnD ERP — Complete Applications Manual

**One manual, every application.** This document covers all ~45 forms and records connected to **Project Registration** in this ERP system — from everyday claims like Reimbursement to behind-the-scenes records most staff never see. It is written for staff who have never used an ERP system before, at any level of computer comfort.

> **How this manual was built:** Every fact in this document — field names, approval chains, who can do what, rupee thresholds — was read directly out of this system's actual configuration (its forms, its approval rules, and its database), not guessed or copied from a generic template. Where the system genuinely doesn't enforce something (a turnaround-time deadline, for example), this manual says so plainly instead of making up a number. Anywhere you see **Assumption**, it means: this is standard practice we'd expect, but you should confirm it with your department, because the computer system itself doesn't enforce it. Any rupee amount shown as an "example" is illustrative only — it does not come from a real record — but any rupee amount described as a **threshold** or **cap** is a real, system-enforced number read directly from the code.

---

## How to Read This Manual

Every application below is marked with a status:

| Mark | Meaning |
|---|---|
| 🟢 **Active** | A real, working application. Staff use this regularly (has real submitted records in the system). |
| 🟡 **Auto-generated** | You never fill this in directly — the system creates it automatically as a side effect of another application (like a Purchase Order created after a purchase is approved). |
| 🟠 **Limited use** | Technically working, but has almost no real usage yet, or has a significant known problem described in its section. |
| 🔴 **Not available** | The application exists in the system's design but was never finished being built. There is no working "fill this form" screen for it today. |
| ⚙️ **System record** | Created and maintained entirely by the computer for internal bookkeeping. Not something you open or fill in. |

Every application section follows roughly the same shape, so once you're comfortable with one, the others will feel familiar:

1. **Overview** — what it's for, in plain language, with an example.
2. **Before You Start** — what to have ready.
3. **Step-by-Step: Filling the Form** — every field explained, section by section.
4. **The Approval Process** — who looks at your request, in what order, and what they check.
5. **Workflow States Explained** — what each status label means for you.
6. **Frequently Asked Questions** — real questions this manual can answer from the system's own configuration.
7. **Common Errors & Troubleshooting**.
8. **Quick Tips**.

Roles like **staff, RnD**, **Hos, RnD**, **Dean, RnD**, **Mentor**, and **PI** show up again and again across applications — see the [Roles Glossary](#roles-glossary) once instead of repeated explanations in every section.

---

## Table of Contents

- [Roles Glossary](#roles-glossary)
- **Part 1 — Financial Claims & Advances**
  - [1.1 Reimbursement 🟢](#11-reimbursement-)
  - [1.2 Temporary Advance 🟢](#12-temporary-advance-)
  - [1.3 Advance Settlement 🟢](#13-advance-settlement-)
  - [1.4 Loan Request 🟢](#14-loan-request-)
  - [1.5 Disbursal of Honorarium 🟢 (+ legacy duplicate)](#15-disbursal-of-honorarium-)
  - [1.6 Disbursal of Consultancy 🟠](#16-disbursal-of-consultancy-)
- **Part 2 — Travel**
  - [2.1 Travel 🟢](#21-travel-)
  - [2.2 TA DA Settlement 🟠](#22-ta-da-settlement-)
- **Part 3 — Project Funding Lifecycle**
  - [3.1 Fund Sanction 🟢](#31-fund-sanction-)
  - [3.2 Fund Received 🟢](#32-fund-received-)
  - [3.3 Deposit Slip family 🟢🟡](#33-deposit-slip-family-)
  - [3.4 AccountHeadPayment ⚙️ / payments 🔴](#34-accountheadpayment--payments-)
- **Part 4 — Procurement**
  - [4.1 Direct Purchase 🟢 (and its auto-generated chain)](#41-direct-purchase-)
  - [4.2 Indent General Form 🟢](#42-indent-general-form-)
  - [4.3 Indent Cum Sanction Sheet 🟢 (and its sub-applications)](#43-indent-cum-sanction-sheet-)
  - [4.4 NIQ 🟠](#44-niq-)
- **Part 5 — Recruitment & Staffing**
  - [5.1 Recruitment Adhoc Contractual 🟢](#51-recruitment-adhoc-contractual-)
  - [5.2 Selection Committee Report 🟢](#52-selection-committee-report-)
  - [5.3 Project Staff Details (Joining Form) 🟢](#53-project-staff-details-joining-form-)
  - [5.4 Extension Of Tenure Of Appointment 🔴](#54-extension-of-tenure-of-appointment-)
- **Part 6 — Contracts & Fellowships**
  - [6.1 Rate Contract 🟢](#61-rate-contract-)
  - [6.2 AMC (Annual Maintenance Contract) 🟠](#62-amc-annual-maintenance-contract-)
  - [6.3 Top Up Fellowship 🟢](#63-top-up-fellowship-)
- **Part 7 — Project Administration**
  - [7.1 User Delegation 🟢](#71-user-delegation-)
  - [7.2 Endorsement Data ⚙️](#72-endorsement-data-)
  - [7.3 Not-Yet-Available Applications](#73-not-yet-available-applications)
- [Cross-Cutting System Notes](#cross-cutting-system-notes)
- [Application Comparison Chart](#application-comparison-chart)
- [Glossary](#glossary)
- [Contact & Support](#contact--support)

---

## Roles Glossary

These roles appear throughout almost every approval chain in this manual. Understanding them once here will save you from re-reading the same explanation in every section.

| Role | Who they typically are | What they generally do |
|---|---|---|
| **Applicant** | You — Permanent Employee, Independent Researcher, Project Staff, or Inspired Faculty | Fills in and submits the form |
| **PI** | The Principal Investigator of the project | Approves requests filed by Project Staff working under them |
| **Mentor** | The assigned mentor of an Independent Researcher | Approves requests filed by Independent Researchers/Inspired Faculty |
| **head_approver_1** ("Head") | The applicant's Department/Centre Head | An intermediate approval step on several forms; on some forms, only the *specific* person named as Head for that request can act, not just anyone holding the Head role |
| **staff, RnD** | R&D office administrative staff | Verifies paperwork/hardcopy bills, forwards to Head of Section |
| **Hos, RnD** | Head of Section, R&D | Mid-level administrative approval |
| **Ado_RnD** (Associate Dean) | Associate Dean, R&D | Final approver for lower-value requests |
| **Dean, RnD** | Dean, R&D | Final approver for higher-value requests, or all requests on some forms |
| **Director** | Institute Director | Escalation approver for very high-value procurement, triggered automatically by amount thresholds |
| **RnD Miscellaneous / RnD Accounts** | Specialist R&D office roles | Used specifically in the Fund Received flow |
| **System Manager** | IT/ERP administrators | Full administrative access to every application |

**A closer look at how these roles actually function day to day:**

**The Applicant** is simply you, filing on your own behalf, or a Permanent Employee filing on behalf of someone else where a given form allows it (Temporary Advance, Loan Request, Disbursal of Honorarium, Top Up Fellowship, and Recruitment Adhoc Contractual/Selection Committee Report all support some version of "apply for another person" — though, as this manual notes in each relevant section, this doesn't always work identically or reliably across every form).

**The PI (Principal Investigator)** is the senior researcher formally responsible for a project. Beyond being an approver for their own Project Staff's requests, the PI is also the person whose details get fetched automatically onto many forms (Travel, TA DA Settlement, several Deposit Slip types), and the person a Project Staff member's Temporary Advance or Loan Request routes to first.

**The Mentor** plays a very similar role to the PI, but specifically for Independent Researchers and Inspired Faculty rather than Project Staff. If you fall into one of these two employee categories, expect your Mentor to be your very first approval stop on almost every financial form in Part 1 and Part 2 of this manual.

**head_approver_1 ("Head")**, unlike most roles in this table, is sometimes tied to a *specific named individual* for a given request rather than to anyone generally holding that role — this manual flags this explicitly wherever it's been confirmed (Recruitment Adhoc Contractual is the clearest example: only the exact person designated as Head for that particular posting can act at that stage, not any other Head-role holder in the institute).

**staff, RnD** is, across this entire manual, the single most heavily-relied-on role — it appears as an approval stage on nearly every application covered here. In practice, this role does the hands-on, detail-level verification work: comparing your uploaded bill photos against your claim on Reimbursement, checking Purchase Committee composition on procurement forms, and generally being the first serious checkpoint after your own PI/Mentor/Head has signed off.

**Hos, RnD (Head of Section)** sits above staff, RnD in almost every chain, providing a mid-level administrative check before a request goes to its final decision-maker (Associate Dean or Dean). This is also, per [Cross-Cutting System Note #1](#cross-cutting-system-notes), one of the two roles most frequently affected by the recurring permission-configuration gap described throughout this manual.

**Ado_RnD (Associate Dean)** and **Dean, RnD** are typically the final decision-makers, with the choice between them very often determined automatically by a rupee threshold on the request's total amount — this manual's [Cross-Cutting System Notes](#cross-cutting-system-notes) section collects every one of these real, system-enforced thresholds into a single reference table.

**Director** involvement is reserved for the largest procurement requests in this system — automatically triggered past specific rupee thresholds on Direct Purchase, Indent General Form, and Indent Cum Sanction Sheet, and separately for Contractual-category recruitment via the Selection Committee Report. Where the Director is involved, expect the process to require a physically or digitally signed PDF document to be uploaded before the relevant Dean-level approval can complete — this is a genuine, hard block on several forms, not just a formality.

**RnD Miscellaneous** and **RnD Accounts** are specialist roles that only appear in this manual within the Fund Received process — the former handles the hand-off to the external Accounts Portal system and the generation of Deposit Slips, the latter performs the final verification once everything else has closed out.

**System Manager** is the IT/ERP administrator role with full access to every application in this system — this is the role to escalate to whenever this manual describes a genuine permission gap, a stuck "Needs Correction" state with no working resubmit path, or any other situation where the normal user-facing process has broken down and needs manual intervention.

Beyond roles, a handful of **employee categories** determine how your request is routed automatically on many forms — the system reads this from your user profile, not from something you type in each time:

| Category (short code seen in some records) | Meaning |
|---|---|
| **P** — Permanent Employee | A regular institute employee |
| **PS** — Project Staff | Staff hired specifically onto a project |
| **IR** — Independent Researcher | A researcher working somewhat independently, assigned a Mentor |
| **IF** — Inspired Faculty | A faculty member under the Inspire Faculty scheme |
| **PI** — Principal Investigator | The lead researcher of a project |

> **Important — a pattern you'll see repeated throughout this manual:** In many applications, a role that's supposed to approve a request at some stage (often Hos, RnD or Dean, RnD, sometimes Mentor or Independent Researcher) does **not** actually have permission configured to open/view that document type in the system. In practice this usually doesn't block the process because most staff also hold a broader "All_ProRnd_User" role that grants access anyway — but it has been flagged explicitly wherever confirmed, because if a particular approver's account is missing that broader role, they will not be able to act on a pending request. See [Cross-Cutting System Notes](#cross-cutting-system-notes) for the full pattern and why it happens.

---

## Getting Started With This ERP System — General Orientation

Before diving into individual applications, a few things are true across the entire system, worth understanding once so every section above makes more sense.

### Logging In and Finding Your Applications

You access this ERP system through your institute web login, using your official email/webmail credentials. Once logged in, applications you've filed, and applications waiting for your action, are generally reachable through a list view specific to that application's name — for example, all Reimbursement records you can see live under "Reimbursement" in the system's navigation. If your institute has built a dedicated frontend web application layered on top of this ERP (which several sections of this manual reference — for example, Fund Received has no working standard on-screen form and is expected to be driven by such a dedicated frontend), you may find it more convenient to use that instead of the system's own generic screens; check with your R&D office about which entry point your department uses day to day.

### The Universal Shape of Every Application

Every one of the ~45 applications and records covered in this manual is, underneath its specific fields, one of the following:

1. **A request you fill in and submit**, which then moves through a sequence of named "Workflow States" as different people review and act on it (Draft → Pending Someone's Approval → ... → Approved or Rejected). This is the shape of the great majority of applications in Parts 1 through 6.
2. **A record the system creates automatically** as a side effect of something else being approved (like a Purchase Order, a Deposit Slip, or a Sanction Sheet). You'll rarely, if ever, create one of these directly — but you may need to open and read one to understand your original request's progress.
3. **A background/system record** with no form to fill in at all (like Endorsement Data or the AccountHeadPayment record) — these exist purely so the system can keep its own internal bookkeeping straight.

Recognizing which of these three categories an application falls into (each section above states this explicitly with its status marker) tells you immediately how much attention it needs from you personally.

### Draft, Submit, and Why Editing Stops

Almost every application starts life as a **Draft** — completely private to you, fully editable, and not visible to any approver yet. Nothing is final until you click **Submit** (sometimes labeled **Forward**, depending on the specific form and your situation — functionally, these do the same thing: move the document out of Draft and into the approval chain). The moment you do this, most applications stop being directly editable by you — this is a deliberate design choice across virtually every ERP system, not a bug: once an approver starts reviewing a document, the version they're looking at needs to stay stable rather than silently changing underneath them. If you spot a mistake after submitting, your options are: wait for the current approver to use a "Put Back" action if one is available and genuinely works on that specific form (check that application's own "Workflow States Explained" section for the honest answer, since this varies significantly across this system, as covered in [Cross-Cutting System Note #2](#cross-cutting-system-notes)); or, for forms where no working correction path exists, contact your R&D office directly for manual help.

### Reading a Workflow State Label

A "Workflow State" (sometimes just called "status") is simply the name of wherever your document currently sits in its approval journey. Reading these labels correctly saves a lot of confusion:

- **"Pending [Someone's] Approval"** means it is sitting with that specific role/person right now, waiting for them to act — it is not sitting with you, and there is nothing further for you to do until they act (unless they Put Back to you).
- **"Approved"** generally means the internal approval process has finished successfully — but, as covered repeatedly throughout this manual, "Approved" does not always mean money has physically moved, or that every automatic downstream step (like a linked Deposit Slip finishing, or a purchase order being generated) has actually completed. Several sections above flag specific cases where you should double-check with your R&D office rather than assuming Approved is the final word.
- **"Rejected"** means the request has been stopped — on most forms, this is final, and a new request needs to be filed from scratch if you still need what you originally asked for.
- **"Needs Correction" / "Put Back" states** mean an approver has sent it back to you — but, importantly, whether you can actually *do* anything about that varies a great deal by application; some genuinely reopen for editing and resubmission, others are dead ends requiring manual intervention. Always check the specific application's section in this manual rather than assuming.

### Notifications — What to Expect (and Not Expect)

As covered in [Cross-Cutting System Note #8](#cross-cutting-system-notes), genuinely working automatic email notifications are rare in this system. Do not wait passively for an email telling you your request has moved — for almost every application in this manual, the reliable way to check on something is to open the relevant application list and look at its current status directly, rather than expecting to be proactively told.

### A Note on Terminology You'll See Throughout This Manual

This manual consistently distinguishes between something being **system-enforced** (the computer itself will not let you proceed, or will not let a number exceed a limit — like Top Up Fellowship's ₹25,000/month cap) and something being **printed guidance** or **organizational policy** (a rule you're expected to follow honestly, but which the system will technically let you violate — like Reimbursement's ₹1,00,000 maximum). This distinction matters: system-enforced rules will actively block you with an error message if you try to go around them; printed-guidance rules rely entirely on you, and your reviewer, to follow them in good faith. Every section in this manual tries to be explicit about which kind of rule applies where.

---

# Part 1 — Financial Claims & Advances

## 1.1 Reimbursement 🟢

### Overview

**What it is:** Getting money back for something you already paid for out of your own pocket for a project. If you spent ₹4,500 of your own money on lab glassware because the vendor needed cash on the spot, Reimbursement is how that ₹4,500 comes back to you.

**Why it exists:** Projects occasionally need someone to pay a small vendor directly — with a cash memo or money receipt — instead of routing the purchase through the normal Direct Purchase/Purchase Order process. Reimbursement lets that already-completed purchase be formally recorded, verified against the actual bill, and repaid.

**Who uses it:** Any Permanent Employee or Independent Researcher on a project who paid for something out of pocket and has a bill/receipt to prove it.

**When to use it:** Only *after* you've already made the purchase and have the bill in hand. If you haven't spent the money yet, use [Temporary Advance](#12-temporary-advance-) instead to get funds up front.

**A worked example:** Suppose you're a Permanent Employee running a small chemistry lab. You needed 50 test tubes and a box of gloves urgently, and the department store was closed, so you bought them yourself from a local vendor for ₹3,200 with a handwritten cash memo. You file a Reimbursement: one item row ("50 test tubes + gloves, ₹3,200"), a photo of the cash memo attached to that row, your bank details, and the four declaration boxes ticked. It goes to a **staff, RnD** reviewer, who checks your bill against the claim and, satisfied, marks it **Verified (With Hardcopy)** — moving it to **Approved**.

**Printed rules on the form (not system-enforced, but expected of you):**
- Maximum limit **₹1,00,000** per claim — not applicable to rate-contract items.
- Splitting one item's bill across multiple reimbursement claims is **not allowed**.

---

### Before You Start

You will need:

✅ The bill, cash memo, or money receipt for every item you're claiming (a clear photo or scan of each one)
✅ Knowledge of which Project Registration and Budget Head this expense belongs to
✅ Your bank account details (account holder name, bank name, account number, IFSC code) — nothing auto-fills these for you
✅ To honestly confirm, in your own mind, that: none of the items were purchased under an existing rate contract; the items were approved by the funding agency; you're personally satisfied the goods were actually received; and you recorded the stock entry on the back of the physical bill with your signature

**Gather these documents before you begin:**
- Photo/scan of each bill or cash memo, one per item
- Your bank passbook or a cancelled cheque, to copy account details accurately

---

### Step-by-Step: Filling the Form

**Step 1 — Applying for yourself or someone else?**
There is a field on the form for "Applying for self or other?" — in practice, this always defaults to **Self** and, as currently built, cannot actually be changed by you through the normal save/submit process. If your organization needs the "apply for someone else" path, it currently requires a System Manager to set it up directly; don't rely on it being available to you from the form itself.

**Step 2 — Applicant Details**
Your Webmail ID (email), department, and designation are shown — department and designation auto-fill from your user profile and are read-only.

**Step 3 — Bank Details**
Enter your **Account Holder Name**, **Bank Name**, **Bank Account Number**, and **IFSC Code** by hand. There is no lookup or auto-fill for these — type carefully, since this is exactly where your money will be sent.

**Step 4 — Project and Item Details**
- **Account Head** — pick the Budget Head this expense should be charged against. If the right one isn't in the list, you can select "Other" and type it into the field that appears.
- **Comment** — a free-text note about the claim, optional but useful for context.
- **Particulars of Items** — this is the heart of the form: one row per bill. For each row, fill in:
  - **Date** — the date of purchase
  - **Vendor's Name** — who you bought it from
  - **Particulars** — what you bought, described clearly ("50 test tubes and a box of nitrile gloves" is much better than "lab supplies")
  - **Amount** — the bill amount (this is a plain text field, not an automatically-validated number field, so double-check you've typed digits only, no commas or currency symbols)
  - **Uploads** — attach a photo/scan of that specific bill to that specific row

**Step 5 — Declarations**
Tick all four boxes:
- None of the items are purchased or under rate contract.
- The items purchased were approved by the funding agency.
- "I am personally satisfied that goods purchased [are as claimed]."
- I stock-entered the items and noted the stock entry details on the reverse of the cash memo/money receipt with my signature.

> **Note:** None of these four checkboxes, and in fact no field on this entire form, is technically *required* by the system — you could submit with all four unticked and it would go through. Treat them as mandatory anyway; a reviewer is very likely to reject an untruthful or unticked declaration on sight.

**Step 6 — Save, then Submit**
Save as many times as you like while the claim is still a Draft. Once you click Submit, editing through the normal process stops — review everything first.

---

### The Approval Process

| Stage | Who acts | What they're checking | Status you'll see |
|---|---|---|---|
| You fill in the form | You | — | **Draft** |
| You click Submit | — | Routes automatically based on whether you're a Permanent Employee or Independent Researcher | **Pending Staff Approval** or **Pending Mentor Approval** |
| Mentor review (Independent Researcher applicants only) | **Mentor** | Reviews the claim, then Approves (forwards to staff) or Rejects | **Pending Mentor Approval** |
| Staff verification | **staff, RnD** | Physically compares your uploaded bill photos against the claim, checks the ₹1,00,000 limit and no-splitting rule by eye | **Pending Staff Approval** |
| Outcome | staff, RnD | "Verify (With Hardcopy)" → moves forward; "Reject" → stops; "Put Back" → sent for correction | **Approved**, **Rejected**, or **Needs Correction** |

**What Permanent Employee applicants experience:** Your claim skips the Mentor step entirely and goes straight to staff verification.

**What Independent Researcher applicants experience:** Your claim first goes to your assigned Mentor. If they Approve, it then goes to staff verification exactly as above. If they Reject, it stops there.

**What "Verify (With Hardcopy)" really means:** The reviewer is expected to have your physical/printed bill in front of them (or a very clear photo) and compare it item-by-item against what you typed. This is a manual, human check — the system does not do any automatic bill-matching or OCR.

---

### Workflow States Explained

**Draft** — You're still filling it in. Fully editable. Nothing has been sent anywhere yet.

**Pending Mentor Approval** (Independent Researcher applicants only) — Sitting with your Mentor. You cannot edit it at this point.

**Pending Staff Approval** — Sitting with a staff, RnD reviewer for hardcopy verification. You cannot edit it.

**Needs Correction (PE)** or **Needs Correction (IR)** — Sent back to you for a fix.

> **Important:** This is a genuine dead end today. There is currently **no button or process to resubmit** a claim that's in a "Needs Correction" state — the system simply doesn't have that path built. If your claim lands here, don't wait for it to move on its own; contact your R&D office or System Manager directly, since it will likely need to be fixed manually on the backend.

**Approved** — Verified successfully. See the important note below about what "Approved" does and doesn't mean.

**Rejected** — Stopped. No further action moves it forward.

> **Important — "Approved" doesn't automatically move money.** Once your claim reaches Approved, a completely separate, manual step ("publishing the commit") is needed to actually record the amount against your project's budget. This is not something you do — it's an internal follow-up step. If your claim shows Approved but the money never seems to land or the budget never seems to reflect it, ask your R&D office to confirm that follow-up step actually happened; don't assume Approved alone means the money has moved.

> **Important — this claim technically never becomes "Submitted" in the system's own bookkeeping sense**, even at Approved. In practical terms this mostly doesn't matter to you, but it does mean an Approved reimbursement can, in principle, still be deleted outright by a Permanent Employee or staff, RnD user — the usual protections that lock down a finished, approved document don't fully apply here. If you ever need to prove your claim went through, keep your own copy of the confirmation/Application ID.

---

### Frequently Asked Questions

1. **What is Reimbursement used for?** Getting back money you already spent personally on a project purchase, with a bill to prove it.
2. **Can I use Reimbursement instead of asking for money upfront?** No — if you haven't spent the money yet, use Temporary Advance instead.
3. **Is there a maximum I can claim?** The form states ₹1,00,000 as a maximum (not applicable to rate contract items), but this is printed guidance, not something the system blocks — your reviewer enforces it.
4. **Can I split one bill into two claims to get around the limit?** No — this is explicitly disallowed, and reviewers check for it.
5. **Who approves my claim if I'm a Permanent Employee?** A staff, RnD reviewer, directly.
6. **Who approves my claim if I'm an Independent Researcher?** Your Mentor first, then a staff, RnD reviewer.
7. **What happens if my claim is sent back for correction?** As things stand, there's no resubmit button — you'll need to contact your R&D office/System Manager to sort it out manually.
8. **Can I edit my claim after I submit it?** No — editing is only possible while it's still in Draft.
9. **Will I get an email when my claim is approved or rejected?** No automated email exists for this — check the list of your applications directly, or ask your reviewer.
10. **Does "Approved" mean the money has been paid to me?** Not necessarily immediately — see the Important note above about the separate "commit" step.
11. **Can I apply on behalf of someone else?** The form has a field for it, but as currently built, you can't actually switch it away from "Self" through the normal process.
12. **What documents should I attach?** A clear photo or scan of the bill/receipt for each item row, attached to that specific row.
13. **What if my file upload fails?** The system will save the row without the attachment and quietly log the failure rather than blocking your submission — always double-check each row shows its attachment after saving, and re-upload if it's missing.
14. **Can my claim be deleted after it's Approved?** Technically yes, by certain roles — see the Important note above. This is a known gap in how the system protects finished claims.
15. **Is the Amount field checked to make sure I typed a real number?** No — it's a plain text field, so type carefully; no commas, no currency symbols, digits only.
16. **What roles can see all Reimbursement claims for oversight?** Head of Section and Dean, RnD-level roles have read and export access, though not full edit access.
17. **How is my claim's ID generated?** Automatically, based on the date and your project number.
18. **Who do I ask if a button I expect to see is missing?** Your System Manager/R&D office — it usually means your account's role isn't listed as allowed for that particular action.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "Cannot edit a submitted or cancelled document" | You're trying to edit after Submit — only Draft is editable | Wait for the outcome; if it needs correcting, contact your R&D office since there's no automatic resubmit path |
| A workflow action button is missing | Your account's role isn't allowed to act at the current stage | Check who the current stage belongs to (see the Approval Process table above) and ask them, or ask your System Manager to check your role |
| Bank details weren't filled in for me | This system does not auto-fill bank details from any bank-account master list | Always type them in yourself, every time |
| An attachment seems to be missing after saving | The upload may have failed silently | Reopen the record and check each item row; re-upload if the attachment isn't there |
| Claim seems stuck in "Needs Correction" | There is no working resubmit path for this state today | Escalate directly to your R&D office/System Manager |
| Approved claim doesn't show against my project's budget | The separate "publish the commit" step may not have run yet | Ask your R&D office to confirm this follow-up step happened |

---

### Quick Tips

✅ Attach a photo of each bill to its own item row — don't lump several bills into one attachment.
✅ Double-check bank details before submitting; nothing is auto-verified.
✅ Enter amounts as plain numbers (no commas, no ₹ symbol).
✅ Tick all four declarations honestly, even though the system won't stop you from skipping them.
❌ Don't split one vendor's bill across two separate claims.
❌ Don't wait passively if your claim lands in "Needs Correction" — chase it directly.

**Full technical detail:** See `REIMBURSEMENT_USER_MANUAL.md` in this repository for the field-by-field schema reference, exact permission tables, and every system-level caveat.

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Applying for self or other? | Select (Self/Other) | No | Defaults to Self; not changeable through the normal process today |
| PI Webmail Id | Link → User | No | Only used if applying for "Other" |
| Department / Designation (for the "Other" person) | Data | No | Auto-fetched |
| Webmail Id | Link → User | No | Your own account, when applying for "Self" |
| Department / Designation | Data | No | Auto-fetched, read-only |
| Account Holder Name | Data | No | Type manually |
| Bank Name | Data | No | Type manually |
| Bank Account Number | Data | No | Type manually |
| IFSC Code | Data | No | Type manually |
| Project Name | Link → Project Registration | No | Usually pre-filled |
| Account Head | Link → Budget Head | No | Choose "Other" if not listed |
| Other Account Head | Data | No | Only if Account Head = Other |
| Comment | Small Text | No | Free text |
| Particulars of Items | Table | No | One row per bill — Date, Vendor's Name, Particulars, Amount, Uploads |
| Declaration 1–4 | Check | No (but treat as mandatory) | The four honesty declarations described above |

> **Note:** Not a single field on this entire form is server-enforced as mandatory — the system will technically let you submit a nearly blank form. This is a genuine gap, not a design choice you're meant to rely on; fill in every relevant field regardless.

### What Happens After You Submit, Stage by Stage

**If you're a Permanent Employee:** Your claim goes straight to a staff, RnD reviewer. They will pull up your uploaded bill photos and compare them line by line against what you typed in the Particulars of Items table — vendor name, date, description, and amount. If everything matches and looks reasonable against the ₹1,00,000 printed guidance, they'll click "Verify (With Hardcopy)." If something looks off, they may Reject or Put Back — remember, Put Back currently has no way forward, so a rejection outright is, in practice, easier for everyone to recover from than a Put Back.

**If you're an Independent Researcher:** Your claim first goes to your assigned Mentor, who reviews the overall request (project relevance, reasonableness) before forwarding it on to the same staff, RnD hardcopy-verification step described above. Only after both approve does it become Approved.

### More Frequently Asked Questions

19. **Can I claim for an item purchased months ago?** The system doesn't check purchase dates against submission dates — but check your department's own policy on timely claims, since this isn't something the ERP enforces.
20. **What if I lost the original bill but have a photo?** A clear photo is what the system expects you to upload — there's no separate "lost receipt" process built into this form; discuss with your R&D office if you're missing original documentation.
21. **Can I add more items to my claim after saving as Draft?** Yes — add as many rows to the Particulars of Items table as you need while still in Draft.
22. **Does the system check my math if I have multiple item rows?** No — there's no running total shown or validated on this form; total your claim yourself if your reviewer asks for it.

---

## 1.2 Temporary Advance 🟢

### Overview

**What it is:** The opposite of Reimbursement — getting money **before** you spend it, so you have cash in hand for a purchase, rather than paying personally and hoping to claim it back later.

**Why it exists:** Some project expenses genuinely need cash up front — a small vendor at a field site who won't take an invoice, for example. Temporary Advance lets you draw that money against project funds, with the expectation that you'll account for how it was spent afterward (see [Advance Settlement](#13-advance-settlement-)).

**Who uses it:** Anyone on a project team who needs funds up front — Permanent Employees, Project Staff, Independent Researchers, Inspired Faculty, or Principal Investigators, filing for themselves; or a Permanent Employee filing on behalf of someone else.

**When to use it:** Before you spend the money, when you know roughly how much you'll need.

**A worked example:** A Project Staff member needs ₹15,000 up front to buy field-survey materials from a village vendor who only deals in cash. They file a Temporary Advance for ₹15,000 against the right Account Head, with a justification ("Field survey consumables for site visit, [dates]"). Because their employee category is Project Staff, it routes first to their PI for approval, then to staff verification, then through Head of Section and — since ₹15,000 is well under the ₹30,000 threshold — the Associate Dean, before reaching Approved.

**The two rules you agree to by ticking the declarations:**
- The advance must be **settled within 45 days** of the money being transferred to you (via Advance Settlement).
- You **cannot** use a Temporary Advance to buy items that are available under an existing rate contract.

---

### Before You Start

You will need:

✅ To know your own employee category (or, if applying on someone's behalf, theirs) — it silently determines your entire approval path, so make sure your user profile has this set correctly *before* you file
✅ The project and Account Head this advance is against
✅ A clear justification for why you need the money in advance rather than claiming it back afterward
✅ Your bank details (again, nothing auto-fills these reliably — see the Important note below)

---

### Step-by-Step: Filling the Form

**Step 1 — Are you applying this for someone?**
Unlike Reimbursement's version of this same idea, this field genuinely works. Choose **No** if it's for you (the default), or **Yes** if you're a Permanent Employee filing on behalf of someone else.

- If **Yes**: fill in the beneficiary's Webmail ID. Their department, designation, and employee category are fetched automatically. Once you submit, the actual beneficiary will receive an **email** asking them to review the details (and correct anything if needed) and personally **Acknowledge** the request before it proceeds — they can also Reject it outright.
- If **No**: your own Webmail ID, department, designation, and category are filled in for you.

**Step 2 — Bank Details**
Bank Name, Account Holder Name, Bank Account Number, IFSC Code — type these in yourself.

**Step 3 — Project and Amount Details**
- **Project Code / Project Name** — normally filled automatically if you launched this from your Project Registration record.
- **Account Head** — this is the **only field on the whole form that the system requires you to fill in** before it will let you save.
- **Amount** — this is a proper currency field, so unlike Reimbursement's item amounts, this one *is* validated as a real number.
- **Amount in Words** — fills in automatically as you type the Amount.
- **Purpose/Justification** — explain clearly why you need the advance.
- **Supporting Documents** — attach anything backing up your request (quotations, a letter from the vendor, etc.).
- **Comments** — optional free text.

**Step 4 — Declarations**
Tick both:
- Aware of the 45-day settlement rule.
- Aware that rate-contract items cannot be bought with this advance (a link to the rate-contract item list is shown alongside this).

> **Note:** As with Reimbursement, neither declaration is technically required by the system to submit — but treat both as mandatory in practice.

**Step 5 — Submit**
Depending on your employee category, the button you click might say **Submit** or **Forward** — both do the same thing (move the document out of Draft); the label just differs depending on which path your category routes through.

---

### The Approval Process

**If you're filing for someone else:** Draft → the beneficiary reviews/edits and personally **Acknowledges** (or Rejects) it → then it enters the normal chain below, based on the *beneficiary's* category, not yours.

**The normal chain, by employee category:**

| Your category | First stop |
|---|---|
| Project Staff | Your **PI** |
| Independent Researcher / Inspired Faculty | Your **Mentor** |
| Permanent Employee / Principal Investigator | Straight to **staff, RnD** |

From whichever first stop applies, the path converges: **staff, RnD** verifies → **Head of Section** reviews and forwards → the system automatically routes to the **Associate Dean** if the amount is **≤ ₹30,000**, or the **Dean** if it's **> ₹30,000** → final **Approve** or **Reject**.

**"Put Back" genuinely works on this form** — unlike Reimbursement, staff, Head of Section, or the Dean can send your Temporary Advance all the way back to Draft (or to an earlier stage) for you to fix, and you can then resubmit it through the normal process.

> **Important:** If you're filing on behalf of someone whose employee category is **Principal Investigator**, there is currently no working "Acknowledge" step for them — this specific combination has no path forward in the system as configured. Don't use "apply for someone else" for a PI colleague; have them file their own request instead.

---

### Workflow States Explained

**Draft** — Fully editable by you.

**Pending Applicant Acknowledgment** — Only relevant if you filed on someone else's behalf. Sitting with the actual beneficiary, who received an email and can edit the details or reject it outright before it proceeds.

**Pending PI Approval / Pending Mentor Approval** — Sitting with the relevant approver based on employee category.

**Pending Staff Approval** — Sitting with staff, RnD for verification. They can Forward, Reject, or Put Back to PI Approval or Draft.

**Pending HoS Approval** — Sitting with the Head of Section, who decides (based on amount) whether to send it to the Associate Dean or Dean, or Reject, or Put Back.

**Pending Associate Dean / Pending Dean Approval** — Final decision stage.

**Approved** — Genuinely finished and locked in the system's own bookkeeping (unlike Reimbursement, this one *does* become a true "submitted" record at this point, so the usual protections against accidental deletion apply).

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **How is this different from Reimbursement?** Temporary Advance gives you money *before* you spend it; Reimbursement pays you back *after*.
2. **Who approves my request first?** It depends on your employee category — see the table above.
3. **Can someone file this on my behalf?** Yes, if they're a Permanent Employee — you'll then get an email and must personally Acknowledge it before it proceeds.
4. **Is there an amount limit?** No hard cap, but amounts above ₹30,000 route to the Dean instead of the Associate Dean.
5. **Do I have to pay this back / account for it later?** Yes — within 45 days of the funds being transferred, via a separate Advance Settlement filing.
6. **Can I buy rate-contract items with this advance?** No — this is explicitly disallowed by the declaration you tick.
7. **Will I be notified when my request needs my personal acknowledgment?** Yes — this is one of the few genuinely automatic emails in this whole system.
8. **Will I be notified at every other approval stage too?** No — only the acknowledgment step sends an email; check the application status directly for everything else.
9. **Can my request be sent back for correction and then resubmitted?** Yes — this genuinely works here, all the way back to Draft if needed.
10. **Why isn't my bank information filling in automatically?** This system's bank-detail lookup doesn't actually work — always enter it manually.
11. **Can I file this on behalf of a Principal Investigator colleague?** Not reliably — there's no working path for them to Acknowledge it. Have them file their own.
12. **What's the difference between the "Submit" and "Forward" buttons at the start?** Nothing functionally — they're just different labels for the two possible ways out of Draft, chosen automatically based on your category.
13. **Do both declarations need to be ticked before I can proceed?** In practice, yes, organizationally — but the system itself won't block you if you leave them unticked.
14. **Can I still edit after Acknowledgment or approval has started?** Only if you're the owner and it's back in Draft, the beneficiary during Acknowledgment, or the relevant PI/Mentor during their specific approval stage.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "No valid transition found for action... matching your role and conditions" | Your role isn't allowed to act on the current stage, or a condition (like employee category or amount) doesn't match | Double-check who the current stage belongs to; confirm your/the beneficiary's employee category is set correctly |
| Beneficiary can never Acknowledge | Their employee category is Principal Investigator — this path isn't wired up | File for yourself instead of on their behalf, or escalate to your System Manager |
| Head of Section or Dean can't open the request at their stage | A known permission-configuration gap for those roles on this form | Escalate to your System Manager — they'll likely need to grant explicit access |
| Rejection reason you typed seems to have disappeared | The system doesn't actually save a typed rejection reason anywhere on this form | Record the reason in a comment on the document instead, until this is fixed |
| Bank details not filled in | No working auto-fill exists | Enter them manually every time |

---

### Quick Tips

✅ Confirm your employee category is set correctly in your profile before filing — it silently controls your whole approval path.
✅ If filing for someone else, double-check their category isn't Principal Investigator first.
✅ Use "Put Back" corrections properly here — this form's resubmit path genuinely works, so don't panic if it's sent back.
❌ Don't assume a typed rejection reason is saved anywhere — put it in a comment instead.

**Full technical detail:** See `TEMPORARY_ADVANCE_USER_MANUAL.md`.

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Are you applying this for someone? | Select (Yes/No) | No | Default No; genuinely changes the form's behavior, unlike Reimbursement's equivalent |
| Webmail Id (beneficiary) | Link → User | No | Only if applying for someone else |
| Department / Designation (beneficiary) | Data | No | Auto-fetched |
| Webmail Id (you) | Link → User | No | Defaults to your session user |
| Department / Designation (you) | Data | No | Auto-fetched |
| Bank Name / Account Holder Name / Account Number / IFSC Code | Data | No | Type manually — no reliable auto-fill |
| Project Code / Project Name | Data | No | Usually pre-filled |
| Account Head | Data | **Yes** | The only field on this whole form the system requires |
| Amount | Currency | No | A real, validated number field |
| Amount in Words | Data | No | Fills in automatically |
| Purpose/ Justification | Small Text | No | |
| Supporting documents | Attach | No | |
| Comments | Small Text | No | |
| Declaration (45-day settlement) | Check | No | Treat as mandatory in practice |
| Declaration Rate Contract | Check | No | Links to the rate-contract item list |

### What Happens After You Submit, Stage by Stage

**If you're filing for yourself as a Project Staff member:** Your request goes to your PI, who reviews it for project relevance and reasonableness, then forwards it on to staff, RnD for the same verification every category eventually goes through.

**If you're filing for yourself as an Independent Researcher or Inspired Faculty:** Your Mentor reviews it first, then forwards to staff, RnD.

**If you're a Permanent Employee or Principal Investigator:** You skip straight to staff, RnD.

**At staff, RnD, Head of Section, and Associate Dean/Dean:** Each of these reviews the request in turn, checking the justification and amount, and either forwards it on, rejects it, or puts it back for correction — and, uniquely among the financial applications in this manual, a "Put Back" genuinely does let you fix and resubmit through the normal process here.

**If you filed on someone else's behalf:** Before any of the above happens, the actual beneficiary gets an email, reviews the pre-filled details (they can edit anything that's wrong), and personally clicks Acknowledge — or Reject if they don't want the advance at all.

### More Frequently Asked Questions

15. **What if I realize after submitting that I need a different amount?** If it's still early in the process, ask the current approver to Put Back the request so you can correct it — this genuinely works on this form.
16. **Is the Amount field checked to make sure I entered a real number?** Yes — unlike Reimbursement's item amounts, this is a proper currency field.
17. **Does my request expire if not acted on quickly?** No — the system doesn't track or enforce any deadline on how long a request can sit at any stage.
18. **Can I see my leave balance or anything else on this form?** No — that's specific to the Travel application; Temporary Advance doesn't interact with leave.

---

## 1.3 Advance Settlement 🟢

### Overview

**What it is:** After you've drawn a Temporary Advance and actually spent the money, this is where you formally account for it — an itemized list of what you bought, compared against the amount you were advanced.

**Why it exists:** A Temporary Advance is money the institute trusted you with in good faith, before you'd actually spent it. Advance Settlement closes the loop: it proves exactly where the money went, with bills to back it up.

**Who uses it:** Anyone who took out a Temporary Advance and needs to account for it (normally within 45 days, per the advance's own declaration).

**A worked example:** Continuing the field-survey example from Temporary Advance: after the trip, the Project Staff member files an Advance Settlement linked to that ₹15,000 advance, listing three expenditure rows (vendor, date, description, amount) that add up to ₹14,600, with photos of each receipt attached, and ticks the three declarations about receipts being enclosed, the stock entry being noted, and quotations being obtained for the one item over ₹1,000.

---

### Before You Start

✅ The specific Temporary Advance record you're settling (its bank details and amount will pre-fill from it)
✅ Every receipt/bill for what you actually spent the money on
✅ Confirmation you've noted the stock entry on the reverse of each bill with your signature, and obtained quotations for any single item over ₹1,000

---

### Step-by-Step: Filling the Form

**Step 1 — Link to the Temporary Advance**
Select the Temporary Advance application this settlement is for. The system fetches the amount, date and time of the advance, your bank account number, Account Head, and account holder's name from it automatically.

**Step 2 — Expenditure Details**
Add one row per expense: expenditure date, vendor's name, particulars, amount in rupees, and an optional attachment (receipt photo). The **Total Amount** field is computed for you from these rows — compare it against the original advance amount as you go.

**Step 3 — Comment**
Optional free-text note.

**Step 4 — Declarations**
Tick all three:
- Receipts are enclosed.
- Stock entry noted on the reverse of the cash memo/money receipt.
- Quotations obtained for items over ₹1,000.

---

### The Approval Process

| Your category | Approval path |
|---|---|
| Permanent Employee | Straight to **staff, RnD** for hardcopy verification → **Approved** |
| Independent Researcher | **Mentor** first → then **staff, RnD** |

The reviewer can also **Reject** or **Put Back** for correction at the staff, RnD stage.

> **Important:** Like Reimbursement, if your settlement is Put Back, there is currently no working path to resubmit it through the normal process. Contact your R&D office directly if this happens.

> **Important:** Two of the roles this workflow expects to act — **Mentor**, and applicants in the **Independent Researcher/Project Staff** categories — don't currently have baseline document access configured for this specific form. If a Mentor genuinely can't see your pending settlement, this permission gap is very likely why; escalate to your System Manager rather than assuming it's user error.

---

### Workflow States Explained

**Draft** — Editable by you.

**Pending Mentor Approval** (Independent Researcher applicants only) — With your Mentor.

**Pending Staff Approval** — With staff, RnD for verification against your receipts.

**Needs Correction** — A dead end today, same as Reimbursement's version — escalate directly rather than waiting.

**Approved / Rejected** — Final outcomes.

> **Note:** Even at "Approved," this document does not reach a genuinely final "submitted" state in the system's own bookkeeping — the same caveat that applies to Reimbursement applies here too.

---

### Frequently Asked Questions

1. **When should I file this?** As soon as possible after spending your Temporary Advance, and no later than 45 days from when the funds were transferred.
2. **What if I spent less than the full advance?** File the settlement with the actual expenditure rows; the difference between the advance and your total spend is a matter for your R&D office to reconcile — the form itself doesn't automatically calculate or flag a refund requirement.
3. **What if I spent more than the advance?** The system doesn't block over-spending declarations — but you should discuss any overage with your R&D office/finance team, since covering the gap isn't handled by this form.
4. **Do I need a quotation for every item?** Only for single items over ₹1,000, per the declaration.
5. **Can my settlement be corrected and resubmitted if it's sent back?** No — same limitation as Reimbursement; you'll need to escalate manually.
6. **Why can't my Mentor see my settlement waiting for their approval?** Likely the permission gap described above — ask your System Manager to check.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Settlement stuck in "Needs Correction" | No working resubmit path exists | Escalate to your R&D office |
| Mentor reports they can't open your settlement | Missing baseline permission for the Mentor role on this form | Ask your System Manager to grant access |
| Total doesn't match the original advance | The system doesn't auto-reconcile this for you | Double-check your own arithmetic; discuss any shortfall/overage with your R&D office |

---

### Quick Tips

✅ File your settlement well before the 45-day deadline, not right at it.
✅ Attach a receipt to every expenditure row.
❌ Don't wait passively for a "Needs Correction" state to resolve itself.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Temporary Advance Application | Link → Temporary Advance | Which advance you're settling |
| Amount | Currency | Fetched from the linked advance |
| Date and Time of Advance | Datetime | Fetched |
| Bank Account Number | Data | Fetched (with an SBI-specific note printed on the form) |
| Account Head | Data | Fetched |
| Bank Account Holder's Name | Data | Fetched |
| Expenditure Details | Table | Date, Vendor's Name, Particulars, Amount, optional Attachment — one row per expense |
| Total Amount | Currency | Computed automatically from the expenditure rows |
| Comment if any | Data | Optional |
| Declare 1 / 2 / 3 | Check | The three declarations described above |

### More Frequently Asked Questions

7. **Do the bank details on this form come from my profile or from the original advance?** From the original Temporary Advance record you're settling, not your general profile.
8. **What if I need to settle two different advances?** File two separate Advance Settlement records, one per advance — each links to only one Temporary Advance.
9. **Is there a formal deadline enforced by the system?** No — the 45-day expectation is a declaration you make, not something the system tracks or blocks you from missing.

---

## 1.4 Loan Request 🟢

### Overview

**What it is:** Requesting an internal loan against your project's own funds — drawing from the project's IDF, PDF, DPF, or Staff Welfare Fund accounts — typically to cover a large cost upfront that will be repaid later according to your project's rules.

**Why it exists:** Occasionally a project needs to front a larger sum than a simple Temporary Advance is meant to cover, drawn specifically from one of these internal fund pools rather than the project's general budget.

**Who uses it:** Any staff member needing such a loan, filed for themselves; or, for someone else, if the applicant holds the Permanent Employee role.

**A worked example:** A project needs ₹80,000 up front to cover a bulk equipment deposit before a formal purchase order clears. A Permanent Employee files a Loan Request against the project's DPF account, with a fund breakdown table showing which Budget Heads the ₹80,000 draws from, ticks the two repayment-agreement checkboxes, and confirms whether the project has a Co-PI.

---

### Before You Start

✅ Know which fund account type you're drawing from: **IDF**, **PDF**, **DPF**, or **SWF**
✅ A clear breakdown of how the loan amount splits across Budget Heads
✅ Whether the project has a Co-PI (this affects a witness-attachment requirement)

---

### Step-by-Step: Filling the Form

**Step 1 — Applying for self or other?**
Choose **Self** (default) or **Other**. If Other, fill in the beneficiary's Webmail ID; their department and designation auto-fill.

**Step 2 — Project and Loan Details**
- **Project Name** — the project number fetches automatically from it.
- **Loan Account Type** — choose IDF, PDF, DPF, or SWF.
- **Account Head Fund Breakup** — a table where you list each Budget Head and the amount drawn from it; the total **Loan Amount** at the top is computed automatically from these rows.

**Step 3 — Co-PI and Attachments**
- **Does Project Have Co-PI?** — Yes/No.
- **Witness Attachment** — a Co-PI's witness signature upload; this field is normally hidden/system-managed rather than something you fill in directly in most cases.
- **Additional Attachment** — any supporting document.

**Step 4 — Agreement Declarations**
Tick both repayment-agreement checkboxes.

**Step 5 — Comments**
Optional free text for anything else relevant.

---

### The Approval Process

This is the **cleanest, most completely-matched permission setup found anywhere in this system** — every approver role the workflow expects also has the correct document access configured, with no gaps identified.

**Draft** (Permanent Employee) → **staff, RnD** forwards → **Head of Section** forwards → **Dean, RnD** Approves → **"Pending @ Staff (Deposit Loan)."**

At that final stage, staff, RnD records the actual **BMR (Bank Money Receipt) number and date** once the loan money has genuinely been disbursed to you — which is what finally moves the record to **Approved**.

> **Note:** The BMR fields only become required once the request reaches that "Deposit Loan" stage — you don't need to know them when you first file, since the money hasn't been disbursed yet at that point.

Head of Section can also **Put Back** to staff, RnD, and Dean can Reject or Put Back to Head of Section — this correction path genuinely works.

---

### Workflow States Explained

**Draft** — Editable by you.

**Pending Staff Approval** — With staff, RnD.

**Pending HoS Approval** — With the Head of Section.

**Pending Dean Approval** — With the Dean, RnD, the only role that can Approve outright at this stage.

**Pending @ Staff (Deposit Loan)** — Approved in principle; waiting for staff, RnD to confirm the actual bank disbursement (BMR) before final closure.

**Approved** — Finished.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **Which fund can I borrow from?** IDF, PDF, DPF, or SWF, as configured for your project.
2. **What's the difference between this and Temporary Advance?** Loan Request draws specifically from these internal fund pools and goes through a distinct approval/repayment framework, rather than the general project budget.
3. **Do I need to know the BMR number when I first apply?** No — that's only entered at the final "Deposit Loan" stage, after the money has actually been disbursed.
4. **Can this be sent back for correction?** Yes — Head of Section and Dean can both Put Back, and the correction path genuinely works on this form.
5. **What if my project has a Co-PI?** You'll indicate this on the form; a witness attachment step is tied to this in the system's design.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Loan amount doesn't match what I expected | Check the fund-breakup table rows — the total is computed automatically from them, so an incorrect row throws off the total | Review and correct each row |
| Can't move past "Pending @ Staff (Deposit Loan)" | The BMR number/date hasn't been recorded yet — this only happens once real money has been disbursed | Check with staff, RnD on the actual disbursement status |

---

### Quick Tips

✅ Double-check your fund-breakup rows add up to the amount you actually need.
✅ Confirm your Co-PI status accurately, since it affects what attachment is expected.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Applying for self or other | Select (Self/Other) | |
| Loan For Webmail Id / Name / Department / Designation | Link/Data | Only if applying for "Other" |
| Applicant Webmail / Department / Designation | Link/Data | Read-only, auto-filled |
| Project Name | Link → Project Registration | |
| Project Number | Data | Fetched |
| Loan Account Type | Select (IDF/PDF/DPF/SWF) | |
| Loan Amount | Currency | Computed automatically from the fund breakup table |
| Account Head Fund Breakup | Table | Budget Head + Amount, one row per head drawn from |
| Agreement No. 1 / 2 | Check | The two repayment-agreement declarations |
| Witness Attachment | Attach | Co-PI witness signature, hidden/system-managed in most cases |
| Additional Attachment | Attach | Any supporting document |
| Does Project Have Co-PI? | Select (Yes/No) | |
| BMR / BMR Date | Data / Date | Only required at the final "Deposit Loan" stage |
| Comments if any | Long Text | Optional |

### What Happens After You Submit, Stage by Stage

**At staff, RnD:** They check your fund-breakup table against the stated Loan Account Type and forward it on if everything is in order, or Put Back if something needs correcting — and correction genuinely works cleanly on this form.

**At Head of Section:** A further administrative check on the request before it reaches the Dean.

**At Dean, RnD:** The only role that can give final Approve on the core request — moving it to the "Pending @ Staff (Deposit Loan)" holding stage rather than straight to a fully closed Approved.

**At staff, RnD again, for the Deposit Loan step:** Once the actual bank disbursement has genuinely happened, staff record the BMR number and date, which is what finally closes the loop and moves the record to true Approved.

### More Frequently Asked Questions

6. **Can a Project Staff member file a Loan Request for themselves?** The form supports "Self" filing generally, though check with your R&D office on whether your specific category is expected to use this route or a different one for your situation.
7. **What if I don't know the exact fund breakup yet?** You'll need at least an estimated breakdown across Budget Heads before submitting, since the total Loan Amount is computed from those rows.
8. **Does this form calculate interest or repayment terms for me?** No — the two agreement checkboxes are declarations you make about repayment; actual terms are a matter of institute policy, not something this form computes.

---

## 1.5 Disbursal of Honorarium 🟢

### Overview

**What it is:** Paying an honorarium to staff, students, or outside guests who did specific work for a project — invigilating an exam, delivering a guest lecture, and similar one-off engagements.

**Why it exists:** Institutes regularly need to pay small, defined amounts to people for discrete pieces of work that aren't a regular salary — this form formalizes that payment against the right Budget Head, with proof of who did what and when.

**Who uses it:** Any Permanent Employee arranging payment for such work.

> **Important — there are two similarly-named applications in this system, and only one is real.** "**Disbursal of Honorarium**" (this section) has real records and an active approval process — this is the one to use. "**Disbursement of Honorarium**" is an earlier, abandoned version of the same idea with zero real records and no working submission process at all; treat it as retired. If your organization's menus show both, always pick "Disbursal of Honorarium." (See [§7.3](#73-not-yet-available-applications) for the retired one.)

**A worked example:** A department runs a two-day workshop with three guest lecturers, each owed ₹5,000 for their session. A Permanent Employee files one Disbursal of Honorarium against the relevant Account Head, adding three rows to the "Details of Honorarium" table — one per lecturer, each with their bank account details, the nature of work, and the dates — for a combined ₹15,000.

---

### Before You Start

✅ The bank account details of every person being paid
✅ Confirmation of whether competent-authority approval is already attached/obtained for this disbursement
✅ Knowledge of the correct Budget Head

---

### Step-by-Step: Filling the Form

**Step 1 — Applying for self or other?**
Defaults to Self; choose Other if you're arranging this on behalf of another applicant.

**Step 2 — Project and Account Head**
Project number and title, and the Budget Head this disbursement is charged against.

**Step 3 — Details of Honorarium (table)**
For each person being paid, add a row: their user account (name/designation/department fetch automatically), nature of work, from/to dates, bank account number, IFSC code, and amount.

**Step 4 — Competent Authority Approval**
Indicate Yes/No on whether this has already been approved by the competent authority, per your institute's honorarium rules (shown as printed guidance on the form itself).

**Step 5 — Attachments**
Attach any approval documents and additional supporting files.

---

### The Approval Process

**Draft** (Permanent Employee) → **staff, RnD** forwards → **Head of Section** forwards → **Dean**, who either **Approves directly if total amount ≤ ₹2,00,000**, or **forwards to Director if > ₹2,00,000** → **Approved**.

> **Important:** The Head of Section, Dean, and Director roles are missing baseline document access to this specific application in the system's permission configuration. Rather than fixing that gap, the system was built to route the record through each stage directly on the backend, bypassing the normal permission check. In practice, the workflow still functions for you as an applicant — but if an approver ever reports odd behavior trying to act on this form through the standard screens, this is a known, documented cause.

---

### Frequently Asked Questions

1. **How do I know which form to use — this one or Disbursal of Consultancy?** Use Disbursal of Honorarium for one-off payments like guest lectures or invigilation; use Disbursal of Consultancy specifically for PDF-fund-based consultancy payments (see next section).
2. **Is there an amount limit?** No hard cap, but amounts above ₹2,00,000 require an additional Director approval after the Dean.
3. **What if I accidentally use "Disbursement of Honorarium" instead?** It won't work — that doctype has no active submission process. Switch to "Disbursal of Honorarium."

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| You picked the wrong "Disbursement/Disbursal" application by mistake | Two similarly-named doctypes exist | Confirm you're in "Disbursal of Honorarium," not "Disbursement of Honorarium" |
| An approver at HoS/Dean/Director stage reports unusual access behavior | Known permission-configuration gap, worked around on the backend | This is expected/documented — escalate to System Manager only if the record genuinely fails to progress |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Applying for self or other | Select (Self/Other) | |
| Webmail Id / Name / Designation / Department (applicant) | Link/Data | Read-only, fetched |
| Webmail Id / Name / Designation / Department (for, if Other) | Link/Data | Only if applying for someone else |
| Project No. / Project Name | Data | Not a formal Link on this particular form |
| Account Head | Link → Budget Head | |
| Details of Honorarium | Table | One row per person paid: user, name, designation, department, employee ID (all fetched), nature of work, from/to dates, bank account number, IFSC code, amount |
| Approval by Competent Authority | Select (Yes/No) | Per your institute's honorarium rules, shown as printed guidance |
| Total Amount | Data | Read-only |
| Attached Approvals / Additional Documents | Attach | |

### Quick Tips

✅ Confirm each payee's bank details are correct before submitting — errors here delay payment to real people, not just paperwork.
✅ Have your competent-authority approval genuinely in hand before ticking "Yes" on that field.
✅ Double-check you're on "Disbursal of Honorarium," not the retired "Disbursement of Honorarium."

### What Happens After You Submit, Stage by Stage

**At staff, RnD:** They review the honorarium table against the stated Account Head and the competent-authority approval flag, then forward it on.

**At Head of Section:** A further check before it's forwarded on to the Dean.

**At Dean:** Decides based on total amount — Approves outright if ≤ ₹2,00,000, or forwards to Director if higher. As noted above, this stage is reached via a backend workaround for a known permission gap, so if you're the approver here and something behaves unexpectedly, it's a documented quirk rather than something new to troubleshoot from scratch.

**At Director (only if total amount > ₹2,00,000):** Final sign-off for larger disbursals — same backend permission workaround applies.

### More Frequently Asked Questions

4. **Can I pay multiple people in one Disbursal of Honorarium?** Yes — add one row per person to the Details of Honorarium table.
5. **What if a payee is a student rather than staff?** The form doesn't distinguish employee/student categories the way Disbursal of Consultancy does — enter their details the same way as any other payee.
6. **Do I need to attach the competent-authority approval, or just confirm it exists?** Attach it as a supporting document if you have it — the Yes/No field alone is a declaration, not proof.

---

## 1.6 Disbursal of Consultancy 🟠

### Overview

**What it is:** Disbursing money from a PI's Professional Development Fund (PDF), accrued from consultancy work, to the people who actually did that work.

**Why it exists:** When a PI earns consultancy income, a defined share of it (institute policy: a 70% personal / 30% institute split) is available for the PI to disburse. This form formalizes exactly who gets paid how much from that share.

**How the math works automatically:** As you enter amounts per person in the disbursal-details table, the form computes each row's 70% personal share and 30% institute share for you. The institute's 30% share is then further broken down into IDF, DPF, staff welfare, and student welfare fund percentages — all computed automatically, not something you calculate by hand.

**A worked example:** A PI has ₹1,00,000 available from consultancy PDF income and wants to disburse ₹40,000 to one employee and ₹20,000 to one student for work on the consultancy project. Two rows in the disbursal-details table capture this, with the 70/30 splits computed per row automatically.

**Tax note printed on the form:** TDS applies if the disbursal goes to an employee or an external consultant, but **not** if it goes to a student, and **not** on the PDF fund itself.

---

### Before You Start

✅ Total amount received and the current balance available to disburse
✅ Bank/PDF account details of each payee
✅ A copy of the consultancy completion report

---

### Step-by-Step: Filling the Form

**Step 1 — Consultancy Details**
Your Webmail ID, name, employee ID (fetched automatically), project title, date of registration and completion of the consultancy.

**Step 2 — Amounts**
Total amount received and current balance.

**Step 3 — Details of Disbursal (table)**
One row per payee: their user account, name/employee ID/designation (fetched), whether they're an Employee or Student, their PDF number or bank account, and the amount — the personal (70%) and institute (30%) share columns compute automatically per row.

**Step 4 — Attachments**
A copy of the completion report, plus up to 5 additional supporting documents.

The overall totals (Total Disbursal Amount, Total Institute Share, Total Personal Share, and the IDF/DPF/Staff Welfare/Student Welfare breakdown of the institute's share) are all computed for you as you fill in the table.

---

### The Approval Process

Same general shape as Disbursal of Honorarium: **staff, RnD → Head of Section → Associate Dean (≤ ₹30,000) or Dean (> ₹30,000) → Approved.**

> **Important — a genuinely more serious access gap than most other forms in this manual.** Unlike every other application covered here, **no role at all** — not even the applicant roles — has standard document permission configured for this application; only the System Manager account does. The whole workflow currently runs entirely through backend bypasses rather than the normal permission system. This isn't just "masked by a broader role most staff hold" the way many other gaps in this manual are — it's a genuine, unpatched gap. If your organization plans to rely on this application regularly, it is worth raising directly with your ERP administrator.

---

### Frequently Asked Questions

1. **How is the 70/30 split decided?** It's computed automatically by the system per row as you enter amounts — you don't calculate it by hand.
2. **Does TDS apply to my payment?** It applies if you're an employee or external consultant, but not if you're a student, and not on the PDF fund itself — per the printed note on the form.
3. **What's the amount threshold for Dean vs. Associate Dean approval?** The same ₹30,000 threshold used on Disbursal of Honorarium.
4. **Why does this form behave inconsistently for different users?** Because of the significant permission gap described above — if you or a colleague can't access a pending Disbursal of Consultancy record as expected, this is very likely why.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Can't open a record you should have access to | The severe permission gap described above | Escalate to your ERP administrator directly — this is a known, unresolved configuration issue |
| Institute-share breakdown looks wrong | Check the raw per-row amounts entered in the disbursal-details table — the split percentages are fixed (70/30, then IDF/DPF/welfare within the institute share) and computed from those | Verify your input amounts, not the formula |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Webmail Id | Link → User | |
| PI Name / Employee ID | Data | Fetched |
| Project Title | Data | Not a formal Link on this form |
| Date of Registration / Date of Completion | Date | For the consultancy engagement |
| Total Amount Received / Current Balance | Currency | |
| Disbursal (Select/PDF) | Select | Default PDF |
| Details of Disbursal | Table | One row per payee: user, name, employee ID, designation (fetched), Employee/Student, PDF number or bank account, amount, and the computed personal (70%)/institute (30%) share columns |
| Completion Report | Attach | |
| Additional Documents | Attach | Up to 5 files |
| Total Disbursal Amount / Total Institute Share / Total Personal Share | Currency, read-only | Computed |
| IDF / DPF / Staff Welfare Fund / Student Welfare Fund | Currency, read-only | The further breakdown of the institute's 30% share |

### Quick Tips

✅ Enter accurate amounts per row — the 70/30 and institute-fund splits are entirely derived from what you type, so an error there cascades through every computed total.
✅ Attach the consultancy completion report — it's a specifically expected document on this form.
❌ Don't assume TDS treatment is the same for every payee — check the employee/student distinction per row, since it changes the tax treatment described on the form.

### What Happens After You Submit, Stage by Stage

**At staff, RnD, Head of Section, and the final Associate Dean/Dean split:** The same general shape as Disbursal of Honorarium's chain — each stage reviews the disbursal-details table and the computed splits before forwarding, all routed through the same backend workaround for this application's especially significant permission gap described above.

### More Frequently Asked Questions

5. **Can I disburse to both employees and students in the same request?** Yes — mark each row's type accordingly; the tax note on the form applies differently based on this.
6. **What if my current balance is less than what I want to disburse?** The form doesn't automatically block this — but it's your responsibility to ensure the disbursal doesn't exceed what's actually available; discuss with your R&D office/finance team if unsure.
7. **Is there a maximum number of payees I can list?** No stated limit — add as many rows to the Details of Disbursal table as needed.

---

# Part 2 — Travel

## 2.1 Travel 🟢

### Overview

**What it is:** Requesting **permission to travel** for work — before you book anything. This is a request for approval, not a money claim; to actually get paid for the trip afterward, see [TA DA Settlement](#22-ta-da-settlement-) below. They are two entirely separate steps in this system, filed at different times.

**Why it exists:** Institutes need to approve work travel in advance — for budget planning, leave coordination, and to confirm the trip is genuinely project-related — before tickets are booked and costs are incurred.

**Who uses it:** Any staff member traveling for work, or a Permanent Employee filing on behalf of someone else.

**A worked example:** A Permanent Employee is invited to present at a national conference. They file a Travel request: visit type "Conference," nature "National," venue and dates, the project it relates to, an estimate of travel/registration/accommodation/other costs (say ₹8,000 + ₹5,000 + ₹6,000 + ₹1,000 = ₹20,000 total estimate), and indicate they'll need financial assistance and an advance. They also request Special Casual Leave for the travel days. The request routes through the approval chain and, once Approved, their leave balance is automatically adjusted.

---

### Before You Start

✅ Your travel dates, venue, and purpose clearly defined
✅ A rough cost estimate broken into travel / registration / accommodation / other
✅ Know whether you'll need Special Casual Leave or Station Leave alongside the trip
✅ Know which project this travel is charged against

---

### Step-by-Step: Filling the Form

**Step 1 — Who is traveling?**
Choose whether you're the traveler yourself, or applying on behalf of someone else (in which case you'll specify their Webmail ID and address).

**Step 2 — Trip Details**
- **Visit Type** — Conference, Field Visit, or Other (if Other, you must specify what).
- **Nature of Travel** — Local, National, or International.
- **Venue/Address**, **From Date**, **To Date** — all required.
- **Organizing Authority** — required; who is running the event/visit.
- **Purpose of Visit** — a description.
- **Project** — required; links this travel to a Project Registration, which also fetches the project number.

**Step 3 — Financial Assistance**
- **Do you need financial assistance?** — required Yes/No.
- If **Yes**, a section appears for **Do you need an advance?**, the **Account Head** (required), and estimated costs across four categories — Travel, Registration, Accommodation, Other — each with its own attachment for supporting quotes/estimates. A **Total Estimate** field sums these for you.
- If you need an advance, bank details (account holder, account number, IFSC) appear for you to fill in.

**Step 4 — Mode of Travel**
Choose By Air, Train, or Road.

**Step 5 — Leave alongside the trip**
- **Special Casual Leave** — mark Required or Not Required; if Required, specify the leave dates. If you're the traveler yourself (not applying for someone else), your current leave balance is shown to you on the form.
- **Station Leave** — similarly, mark Required or Not Required, with from/to dates and session (Full Day/Forenoon/Afternoon).

**Step 6 — Additional Responsibility**
If you're the traveler yourself, you must indicate whether anyone will be covering an additional responsibility of yours while you're away, with details if so.

**Step 7 — Declaration**
Tick the final declaration checkbox before submitting.

> **Note:** As with the financial forms, no field on this form is technically required by the system except the ones marked above — but fill in everything relevant, since incomplete requests are more likely to be Put Back or Rejected by a human reviewer.

---

### The Approval Process

Your request routes automatically by employee category through a chain that can include some or all of: **PI, Mentor, Head, staff RnD, Head of Section, Associate Dean, Dean** — ending in **Approved** or **Rejected**, with extensive "Put Back" options at nearly every stage for corrections.

> **Important:** The "Associate Dean" stage of this particular workflow is configured in the system but is **unreachable** — no path in the approval chain actually routes a Travel request there, even though the stage technically exists. This doesn't block or slow down your request; the chain simply skips past it and goes to the Dean instead. You may see "Pending Associate Dean" mentioned in system documentation, but you won't actually encounter it in practice.

> **Note:** If your request includes Special Casual Leave dates, your leave balance is **automatically deducted** the moment the request reaches Approved — and automatically restored if the request is later cancelled. You don't need to separately file for the leave itself.

---

### Workflow States Explained

**Draft** — Fully editable.

**Pending PI Approval / Pending Mentor Approval / Pending Head Approval / Pending Staff Approval / Pending HoS Approval / Pending Dean Approval** — Sitting with the relevant approver in the chain, in sequence, depending on your category and how far the request has progressed.

**Approved** — Finished, and this document does become a genuinely final "submitted" record in the system.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **Do I need approval before I book my travel?** Yes — this form exists specifically to get that approval before you commit to bookings.
2. **How do I actually get paid for the trip?** Through a separate application, TA DA Settlement, filed after the trip — see the next section.
3. **What if I need an advance for the trip?** Indicate this on the Financial Assistance section; a separate note says a dedicated Advance Request form should be used if a formal advance is genuinely required — check with your R&D office on the current process for this.
4. **Will my leave balance be affected automatically?** Yes, if you requested Special Casual Leave and your request is Approved — it's deducted automatically, and restored if the request is cancelled later.
5. **Why can't I find "Pending Associate Dean" happening on my request even though I've heard it mentioned?** That stage is configured but never actually used by any real approval path — your request goes straight to the Dean instead.
6. **Can my request be sent back for correction?** Yes, extensively, at multiple stages.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Request seems to skip a stage you expected | The "Pending Associate Dean" stage is unreachable by design | This is expected behavior, not an error |
| Leave balance wasn't deducted as expected | Only Special Casual Leave dates entered on this form trigger automatic deduction, and only once Approved | Confirm you filled in the Special Casual Leave section correctly |
| Financial estimate total looks wrong | The Total Estimate simply adds your four category estimates | Recheck each of the four estimate fields |

---

### Quick Tips

✅ File your Travel request well before you need to book anything.
✅ Fill in the financial-assistance estimate fields carefully if you'll need an advance.
✅ Remember: this form does not pay you — TA DA Settlement (next) does that.

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Traveler (Self/Other) | Select | No | |
| Other Traveler / Traveler Webmail Id | Link → User | No | If applying for someone else |
| Webmail Id / Applicant Name / Designation / Department | Data/Link | No | Fetched |
| Visit Type | Select (Conference/Field Visit/Other) | No | |
| Specify Type of Visit | Data | Only if Visit Type = Other | |
| Nature of Travel | Select (Local/National/International) | No | |
| Venue/Address | Small Text | No | |
| From Date / To Date | Date | **Yes** | |
| Organizing Authority | Small Text | **Yes** | |
| Purpose of Visit | Small Text | No | |
| Project Title | Link → Project Registration | **Yes** | |
| Project Number | Data | No | Fetched |
| Financial Assistance Needed | Select (Yes/No) | **Yes** | |
| Do you need an advance? | Select (Yes/No) | No | Shown if Financial Assistance = Yes |
| Account Head | Link → Budget Head | **Yes** | |
| Mode of Travel | Select (Air/Train/Road) | No | |
| Bank details (holder, number, IFSC) | Data | No | Shown if advance needed |
| Estimated Travel/Registration/Accommodation/Other Amounts | Currency | No | Each with its own attachment |
| Total Estimate | Currency | No | Computed automatically |
| Special Casual Leave | Select (Required/Not Required) | No | With from/to dates if Required |
| Station Leave | Select (Required/Not Required) | No | With from/to dates and session if Required |
| Additional Responsibility | Select (Yes/No) | Conditionally required if you're the traveler | With details if Yes |
| Classes Arrangement | Int | No | If you're the traveler |
| Comment if any | Small Text | No | |
| Declaration Accepted | Check | No | |

### More Frequently Asked Questions

7. **Can I request Station Leave without Special Casual Leave, or vice versa?** Yes — they're independent fields; request whichever (or both) apply to your trip.
8. **What happens to my "Additional Responsibility" answer?** It's a record of who's covering your duties while away — mainly informational for your department, not something the system acts on automatically.
9. **Does the Total Estimate include my Special Casual Leave or Station Leave costs?** No — it's purely the sum of your four travel-cost estimate fields (Travel/Registration/Accommodation/Other); leave doesn't have a cost figure on this form.
10. **What if my trip spans International travel — is there a different process?** The Nature of Travel field lets you select International, but the approval chain and fields are otherwise the same as Local/National.

---

## 2.2 TA DA Settlement 🟠

### Overview

**What it is:** The claim you file **after** your trip to actually get your Travelling Allowance / Dearness Allowance paid — the "getting paid" half of the Travel process.

**Why it exists:** Travel gets you approval to go; TA DA Settlement is where you formally claim the money for what the trip actually cost, with proof.

**Who uses it:** Anyone who traveled for work and needs to claim their allowance.

**A worked example:** After returning from the conference described in the Travel example above, the same employee files a TA DA Settlement, linking it back to their original Travel request (their name, designation, department, and project auto-fill from it). They list "Other Expenses" — hotel charges, food charges — each with a proof attachment, then manually add up their total claimed amount, subtract the advance they were given, and enter the net amount they're claiming.

---

### Before You Start

✅ Your original Travel request (optional to link, but useful — several fields pre-fill from it)
✅ Every receipt for hotel, food, registration, and other expenses
✅ A calculator — see the Important note below
✅ Confirmation that: your claimed distances are correct, you traveled in your entitled class, you took the shortest route, and this claim hasn't been paid elsewhere

---

### Step-by-Step: Filling the Form

**Step 1 — Link to your Travel Application**
Optional, but recommended — if you select your original Travel request, your name, designation, department/section, project number, webmail ID, and account head all fill in automatically, and your original estimated total pre-fills as your "Advance Taken" figure.

**Step 2 — Journey and Bank Details**
Purpose of journey, whether journey particulars are attached (Yes/No), whether local conveyance was used (Yes/No), your contact number, IFSC code, scale of pay, bank account number and holder name.

**Step 3 — Other Expenses (table)**
For each additional expense: choose the type (Registration Fee / Hotel-Lodging Charges / Food Charges / Other Charges), enter the amount, and attach proof.

**Step 4 — Amounts**

> **Important — this does not add up your total for you.** The form has fields for **Total Claimed**, **Advance Taken**, and **Net Claimed** that look like they should calculate automatically from your Other Expenses table — and an earlier version of this system's design intended exactly that — but the automatic calculation was never actually connected to this form in the version currently running. **You must add up your expenses yourself and type in the Total Claimed, Advance Taken, and Net Claimed amounts by hand.** Double-check your arithmetic carefully before submitting, since nothing will catch a mistake for you.

**Step 5 — Declarations**
Four checkboxes (distances correct, entitled class, shortest route, not paid elsewhere), plus two further Select-type declarations about your boarding/lodging status and whether free transport was provided.

---

### The Approval Process

Routes by employee category, similar to Travel: through **Staff** → **Head of Section**, which then routes automatically to the **Associate Dean (≤ ₹30,000)** or the **Dean (> ₹30,000)**, based on your Total Claimed amount.

> **Important:** There is no requirement anywhere in the system that your linked Travel request already be Approved before you file a TA DA Settlement — you can technically submit one even with no Travel record linked at all, or one that's still pending. **Assumption:** confirm with your department whether this is meant to be allowed, or whether policy expects an Approved Travel first even though the system itself won't stop you from skipping it.

> **Important:** Watch this workflow's status labels carefully — on this particular form, an **Approved** claim can, unusually, remain in a state that still allows further editing, while a **Rejected** claim becomes permanently locked. This is the reverse of what you'd normally expect (that approved/finished things get locked and rejected/returned things stay open), so don't assume "Approved" means your claim is now completely closed out and untouchable — treat it with the same care you would a still-open document until you've confirmed with your R&D office that it's fully settled.

---

### Workflow States Explained

**Draft** — Editable.

**Pending PI Approval / Pending Staff Approval / Pending HoS Approval / Pending Associate Dean / Pending Dean Approval** — Sequential approval stages, similar in shape to Travel's.

**Approved** — See the Important note above about this state's unusual editability.

**Rejected** — Locked, unusually, more firmly than Approved is on this particular form.

---

### Frequently Asked Questions

1. **Does the system calculate my total for me?** No — despite the form having the right fields, you must calculate and enter Total Claimed, Advance Taken, and Net Claimed yourself.
2. **Do I need an Approved Travel request first?** Not strictly required by the system, though it's good practice to confirm your department's expectation.
3. **What documents do I need?** Proof/receipt for every "Other Expense" row you add.
4. **What are the four self-certification checkboxes for?** Confirming distances, entitled travel class, shortest route, and that you haven't already been paid for this trip elsewhere.
5. **Is there an amount threshold that changes who approves my claim?** Yes — ₹30,000, same as several other financial forms, determining Associate Dean vs. Dean.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Total Claimed / Net Claimed fields are blank or wrong | These don't auto-calculate on this form | Manually add up your Other Expenses and enter the figures yourself |
| Claim submitted without a linked Travel request | Not blocked by the system | Confirm with your department whether this is acceptable practice |
| Confusion about whether a claim is "final" | Approved claims can remain editable; Rejected ones lock more firmly | Confirm directly with your R&D office whether an Approved claim is genuinely finished before treating it as closed |

---

### Quick Tips

✅ Do your arithmetic carefully — nothing on this form checks your totals for you.
✅ Link your original Travel request where possible, to save re-typing several fields.
✅ Keep every receipt attached to its matching expense row.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Travel Application | Link → Travel | Optional but recommended |
| Name / Designation / Department-Section | Data | Fetched from the linked Travel record |
| Employee Number | Data | |
| Project No. | Data | Fetched |
| Contact / IFSC Code / Scale of Pay / Bank Account Number / Bank Account Holder | Data/Int | |
| Purpose of Journey | Small Text | |
| Journey Particulars Attached | Select (Yes/No) | |
| Local Conveyance Used | Select (Yes/No) | |
| Other Expenses | Table | Expense Type, Amount, Proof attachment — one row per expense |
| Total Claimed / Advance Taken / Net Claimed | Currency | **Not auto-calculated** — you must enter these yourself |
| Additional Comment | Small Text | |
| Distances Correct / Entitled Class / Shortest Route / Not Paid Elsewhere | Check | The four self-certifications |
| Free Transport Provided | Select | Required, two descriptive options |
| Boarding and Lodging Status | Select | Required, four descriptive options |
| Account Head | Data | Fetched from the linked Travel record |

### More Frequently Asked Questions

6. **What are the four expense types available in the Other Expenses table?** Registration Fee, Hotel-Lodging Charges, Food Charges, and Other Charges.
7. **Can I claim TA/DA without linking a Travel application at all?** Technically yes — the system doesn't require the link — but doing so means several convenience fields won't pre-fill for you, and you should check your department's policy on whether this is expected practice.
8. **What if my actual travel mode differed from what I put on my original Travel request?** This settlement form doesn't re-ask for travel mode directly — your self-certifications (entitled class, shortest route) are what matters here.

---

# Part 3 — Project Funding Lifecycle

## 3.1 Fund Sanction 🟢

### Overview

**What it is:** The record that funding has been formally **approved** for your project — the sanction letter number, the amount, and a year-by-year budget breakdown. This comes *before* the money actually arrives; when it does, that's recorded separately in [Fund Received](#32-fund-received-).

**Why it exists:** Projects need a formal, traceable record of exactly what was sanctioned, by whom, against which budget heads, and over what multi-year schedule, independent of when the money physically lands in the bank.

**Who uses it:** Permanent Employees, Independent Researchers, and Project Staff filing the sanction record; staff, Head of Section, and Dean as the internal approval chain.

**A worked example:** A project receives a sanction letter for ₹5,00,000 spread across two years. Someone files a Fund Sanction: project link, the sanction letter's unique number and date, and a budget breakdown table with ₹3,00,000 in the first-year column and ₹2,00,000 in the second-year column against the relevant account heads, plus the scanned sanction letter attached as a supporting file.

---

### Before You Start

✅ The sanction letter itself, with its official number and date
✅ The year-wise budget breakdown as stated in the letter
✅ Confirm the sanction letter number you're about to enter hasn't already been used in the system (see the duplicate-check tip below)

---

### Step-by-Step: Filling the Form

**Step 1 — Project**
Link the Project Registration this sanction belongs to — required.

**Step 2 — Sanction Details**
- **Sanctioned Letter No.** — must be **unique** across the whole system. As you type, the system checks in real time whether this number is already used elsewhere and, if it is, suggests an alternative unique value (in a `-SL00001`-style format) for you to use instead.
- **Sanctioned Letter Date**.
- **Total Sanctioned Amount** — this recalculates automatically from your budget breakdown table as you fill it in.

**Step 3 — Sanctioned Budget Breakup (table)**
For each account head, enter the amount sanctioned per year — the form supports up to six years' worth of columns (First Year through Sixth Year Budget), though in practice the on-screen display currently tends to only show the first year clearly (see the Important note below); the underlying data for later years is still saved correctly even if the display doesn't show it well.

**Step 4 — Supporting Files**
Attach the sanction letter and any other supporting documents.

> **Note:** A section on this form labeled roughly "have you received fund" (with related GST/amount-received fields) exists but has **no working logic behind it** — nothing you enter there is actively used by the rest of the process. If you need to record that money was actually received, use the separate [Fund Received](#32-fund-received-) application instead, not this section.

---

### The Approval Process

**Draft** → **staff, RnD** forwards → **Head of Section** forwards → **Dean, RnD** Approves → **Sanction Approved**.

> **Important:** As soon as you click Submit out of Draft, the system internally marks the document as fully "submitted" — well before anyone has actually approved anything. This is different from most other financial applications in this manual, where "submitted" status is reserved for the very end of the process. In practical terms it mostly doesn't change what you see on screen, but several fields (like the letter number and budget breakup) are specifically designed to remain editable even at this "already submitted" stage, precisely because approval hasn't actually finished yet.

> **Important:** If your sanction is Put Back for correction by staff, RnD, it always lands in a correction state designed for **Permanent Employee** applicants — **even if you're an Independent Researcher or Project Staff applicant**. If you hold only one of those two other roles, you may not be able to resubmit your own corrected sanction through the normal process. Ask a Permanent Employee colleague, or your R&D office, to help push it through if this happens to you.

> **Note:** After Approval, the Dean can additionally click **"Add Fund"**, which moves the document to a state called **"PendIng Fund Submission"** (note the unusual capital "I" — a quirk in how this stage's name was set up in the system, not a typo you need to fix). This stage currently has **no further action defined** — nothing moves it forward from there. Treat "Add Fund" as informational rather than something that continues automatically; any next steps happen outside this form (typically via a separate Fund Received filing).

---

### Workflow States Explained

**Draft** — Freely editable.

**Pending Staff Approval / Pending HoS Approval / Pending Dean Approval** — Sequential approval stages.

**Needs Correction (PE)** — See the Important note above; this is the only reachable correction state, regardless of your own applicant category.

**Sanction Approved** — Finished, and the Kafka sync to the external accounts system happens right at this point.

**Rejected** — Stopped. Note that Reject on this form works a little differently under the hood than most other applications' Reject actions — practically, treat it the same as any other Rejected outcome (the request is stopped), but if you ever need to "undo" a Rejected Fund Sanction, escalate to your System Manager rather than expecting a normal amend/reopen option to work smoothly.

---

### Frequently Asked Questions

1. **What's the difference between this and Fund Received?** Fund Sanction records that funding was *approved*; Fund Received records that it *actually arrived* in the bank.
2. **Do I need a Fund Sanction before I can file a Fund Received?** The system tries to auto-match a Fund Received to an existing Fund Sanction, but it's not strictly enforced — however, getting this link right matters a lot for Fund Received's own processing (see the next section).
3. **Why does my budget breakup table look empty when I reopen the record?** This is a known display quirk, not a data-loss problem — your saved figures are not actually gone. Reload the page rather than re-entering everything; if you're still unsure, ask your R&D office to confirm the saved values directly.
4. **Why can I only see the first year's budget column?** A related display limitation — the underlying multi-year data is still there even if the screen doesn't show every column clearly.
5. **My sanction was Put Back and I'm an Independent Researcher — why can't I resubmit it?** A known gap — the correction path only works cleanly for Permanent Employee applicants; ask a colleague or your R&D office for help.
6. **What happens when the Dean clicks "Add Fund"?** The document moves to a status with no further defined next step in this form — any continuation happens through a separate process (like Fund Received), not automatically here.
7. **Is there a Print Format for this document?** No dedicated one exists — printing uses the system's generic default layout.
8. **Will I be notified automatically at each approval stage?** No — no automated notifications exist for this form; check the record's status directly.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "Sanctioned Letter No. already exists" | The number you entered is already used by another record | Use the alternative suggested by the system, or double-check you're not duplicating an existing sanction |
| Budget breakup table appears empty on reopening | Known display glitch | Reload the record; don't re-enter data based on appearance alone |
| Only first-year budget column visible | Known display limitation | The other years' data is likely still saved — confirm with your R&D office if unsure |
| Can't resubmit a Put-Back sanction | Correction path only works for Permanent Employee applicants | Ask a Permanent Employee colleague or your R&D office for help |
| "Add Fund" seems to lead nowhere | No further step defined at that stage in this form | This is expected — any continuation happens via a separate process |

---

### Quick Tips

✅ Double-check your sanction letter number for typos or accidental duplicates before saving.
✅ Trust your saved data even if the on-screen budget table looks incomplete after reopening — verify with your R&D office rather than re-entering everything.
✅ Attach the actual sanction letter as a supporting file, not just the summary numbers.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Project Registered | Link → Project Registration | Required; the field's label is a little misleading — it links to your Project Registration, not a separate "Project Proposal" record |
| Sanction Workflow Status | Data | Kept automatically in sync with the record's status |
| Total Sanctioned Amount | Currency | Computed from the budget breakup |
| Sanctioned Letter No. | Data | Must be unique system-wide, checked in real time as you type |
| Sanctioned Letter Date | Date | |
| Sanctioned Budget Breakup | Table | Account Head, First through Sixth Year Budget, computed row total |
| Sanction Related Files | Table | One or more attachments, each with a description |
| Project Type (Linked) | Select, read-only | Fetched from the project |
| Is GST Invoice Issued? / Invoice Details | Select/Data | Only relevant for Consultancy-type projects |

> **Note:** A further set of fields on this form (around a "have you received fund" question, GST invoice status, amount received, and a bank-account field) exist on screen but have **no working logic connected to them** — don't rely on filling these in as having any real effect; use the separate Fund Received application for anything about money actually arriving.

### What Happens After You Submit

**At staff, RnD:** They check the sanction letter details and budget breakdown against the actual sanction letter you attached, then forward it on.

**At Head of Section:** A further administrative check before forwarding to the Dean.

**At Dean, RnD:** The final approval decision — Approve moves it to Sanction Approved (triggering the sync to the external accounts system), Reject stops it, Put Back sends it to the "Needs Correction (PE)" state described above regardless of your own applicant category.

### More Frequently Asked Questions

9. **Does the year-wise budget breakup support more than one account head?** Yes — add as many rows as needed to the Sanctioned Budget Breakup table, one per account head, each with its own multi-year figures.
10. **What's the difference between "Sanctioned Letter No." and the system's own record name?** The Sanctioned Letter No. is what's printed on your physical sanction letter and must be unique; the record name is a separate, system-generated identifier — this distinction matters a great deal when filing the related Fund Received application (see next section).
11. **Can two different projects share the same Sanctioned Letter No.?** No — this is checked and blocked system-wide, not just within your own project.
12. **What if the Dean rejects my sanction?** It moves to Rejected; there's no automatic path back from there through this form — discuss next steps with your R&D office.

---

## 3.2 Fund Received 🟢

### Overview

**What it is:** Records that sanctioned money has **actually arrived** in the institute's bank account — the amount, the receiving bank account, transaction references, and a budget-head breakdown of the received amount. Once verified, this application **automatically generates a Deposit Slip** so the funds can be formally credited into the project's account.

**Why it exists:** A Fund Sanction only records that money was *approved* — Fund Received records that it was *actually credited*, ties it to real bank transaction numbers, and hands off to the internal Deposit Slip paperwork.

**Who uses it:** Permanent Employees, Independent Researchers, and Project Staff filing the fund-received record; RnD Miscellaneous staff and the Head of Section as verifiers/approvers; RnD Accounts for final sign-off.

**A worked example:** The ₹3,00,000 first-year installment from the Fund Sanction example above lands in the institute's account. Someone files a Fund Received: the project, the exact Fund Sanction record it belongs to, ₹3,00,000 as the amount, the bank account/scheme it landed in, and a transaction table with the actual bank transaction number and date.

> **Important — this is the one application in this whole manual with a genuine two-way connection to an outside system.** Every other financial application only ever *sends* information out. Fund Received also *receives* live updates back — an external Accounts Portal system can push status changes directly into your Fund Received record as part of its own review process. This means part of the approval chain isn't a person clicking a button in this ERP at all, but a separate finance system reporting back automatically.

---

### Before You Start

✅ The exact **Fund Sanction record name** (not the sanction letter number — see the Important note below) this money belongs to
✅ The actual bank transaction number(s) and date(s)
✅ A budget-head breakdown of how the received amount should be allocated

---

### Step-by-Step: Filling the Form

**Step 1 — Reference Details**
- **Project Title** — required Link to the project.
- **Fund Received Ref No.** — read-only; described on the form as coming "from Accounts Portal," so don't expect to type this yourself.
- **Sanction Ref No.** — a free-text field, not a formal Link, even though it conceptually points at a Fund Sanction record.

> **Important:** Getting the Sanction Ref No. field exactly right matters a great deal. It needs to be the **exact Fund Sanction document name** (a system-generated identifier), not the sanction letter number, and not a description. If it doesn't exactly match a real Fund Sanction record, a later step in the process (syncing with the external Accounts Portal system) will **fail silently** — you'll only see a vague "sync failed" message, with no further detail about why. Double, triple-check this field before moving on.

**Step 2 — Received Amount & Invoice**
- **Fund Received Amount** — required.
- **Bank Account Number / Scheme (Name / Number)** — required; where the money was received.
- **Is GST Invoice Issued?** and **Invoice Number** — conditional fields that, in practice, may not reliably appear through the standard screen (a display-condition quirk in how this form was built) — if your organization's dedicated frontend application handles this differently, use that instead of assuming this exact screen behavior.

**Step 3 — Transaction & Budget Breakups**
- **Sanction Transaction Details** (table) — one row per bank transaction: transaction number, transaction date (defaults to today), amount, and an optional attachment.
- **Budget Breakup of the Received Amount** (table) — one row per Budget Head: the account head (a proper Link this time, unlike Fund Sanction's version), amount received, and remarks.

**Step 4 — Supporting Document**
Attach one overall supporting document for the record.

---

### The Approval Process

| Stage | Who acts | What happens |
|---|---|---|
| Draft | You | Fill in the details |
| Submit | — | → **Pending Misc. Staff Approval** |
| Staff review | **RnD Miscellaneous staff** | Forward → this is also exactly when the record is sent to the **external Accounts Portal** system |
| External review | **The external Accounts Portal system itself** | Reviews the bank data; when it approves, your record automatically advances — no one in your R&D office clicks a button for this specific step |
| Deposit Slip generation | **RnD Miscellaneous staff** | Once the external system has approved, staff supply deposit-slip details, which creates a linked Deposit Slip document (see [§3.3](#33-deposit-slip-family-)) |
| Final internal approval | **Head of Section** | Approves — this also triggers the linked Deposit Slip to be automatically finished and published |
| Verification | **RnD Accounts** | Final "Verify" step, closing the record out |

> **Important:** Approving a Fund Received is *supposed* to automatically finish and publish its linked Deposit Slip as a side effect. This can fail silently for a specific, known technical reason: the roles that normally act on this step don't currently have the right document permission on the Deposit Slip itself. If your Fund Received shows **Approved** but you can't find a matching, finished Deposit Slip for it, don't assume everything is fine — flag it to your R&D office so they can check and finish that step manually if needed.

> **Important:** Generating a Deposit Slip depends on the deposit-slip details actually being filled in with enough real content when RnD Miscellaneous staff trigger that step. If the details supplied look too sparse, the system quietly skips creating the Deposit Slip and lets the Fund Received's status keep moving forward anyway — meaning a Fund Received can, in principle, reach Head-of-Section approval or even final Approval with **no linked Deposit Slip at all**. Always confirm a Deposit Slip genuinely exists once your Fund Received reaches the Head of Section stage.

---

### Workflow States Explained

**Draft** — Editable.

**Pending Misc. Staff Approval** — With RnD Miscellaneous staff for the first review.

**PENDING_APPROVAL** (this exact all-capitals label is intentional, not a typo — it matches the external Accounts Portal's own terminology) — Handed off to the outside finance system; nominally shown as belonging to a System Manager account, but in practice advanced automatically once the external system responds.

**Pending Misc. Staff Approval(Deposit Slip Pending)** — Back with RnD Miscellaneous staff to generate the Deposit Slip.

**Pending HoS Approval** — With the Head of Section for final internal approval; this is where the linked Deposit Slip gets auto-finished as a side effect.

**Approved** — Internally finished, deposit-slip side effects triggered.

**Fund Received** (yes, the same name as the application itself — a bit confusing, but it's simply the label chosen for the very last stage) — The final, fully-verified state, reached after RnD Accounts confirms Verify.

> **Note:** This particular workflow has **no Reject option at all** — only "Put Back" (returning to an earlier stage) exists throughout. There is no way to formally mark a Fund Received as rejected within this application; if a fund receipt turns out to be wrong or invalid, that would need to be handled outside this form.

---

### Frequently Asked Questions

1. **What's the difference between Fund Sanction and Fund Received?** Fund Sanction records that funding was *approved*; Fund Received records that the money *actually arrived* in the bank.
2. **Do I need a Fund Sanction before filing a Fund Received?** The system tries to auto-match one, but doesn't hard-require it — however, getting the Sanction Ref No. field exactly right is critical for the process to work smoothly (see above).
3. **Why did my request seem to stall after "Forward"?** That's the moment your record is handed off to the external Accounts Portal — the next movement depends on that outside system, not on a person clicking a button here. If it's been unusually long, ask your R&D office to check the sync status.
4. **Who approves my Fund Received after staff forward it?** Formally, the external Accounts Portal system — not a person you can chase directly in this ERP.
5. **Do I need to do anything to get a Deposit Slip created?** No — RnD Miscellaneous staff handle that once the external system has approved. Just make sure your original details were complete enough for a Deposit Slip to actually be worth generating.
6. **Can my Fund Received be rejected?** No — this particular workflow only supports "Put Back," not a formal Reject.
7. **Is there a Print Format for this?** No custom one exists.
8. **Will I get an email at each stage?** No standard email notifications exist for this form; only internal alerts to your R&D office's monitoring channel for technical sync events.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "Sync failed" or similar vague message after Forward | Sanction Ref No. doesn't exactly match a real Fund Sanction record name | Re-enter the exact Fund Sanction docname; check the Fund Sanction list directly |
| Record reaches Approved with no visible Deposit Slip | Deposit Slip generation may have been skipped (insufficient detail at that step), or the auto-finish step at Approval failed silently | Ask your R&D office to check and, if needed, finish the Deposit Slip step manually |
| GST invoice fields don't appear as expected | A display-condition quirk in this form | Use your organization's dedicated frontend application if it handles this differently |
| Request seems stuck at "PENDING_APPROVAL" | Waiting on the external Accounts Portal system, not a person in this ERP | Ask your R&D office to check the external sync status if it's been unusually long |

---

### Quick Tips

✅ Always double-check the exact Fund Sanction record name before saving.
✅ Confirm a Deposit Slip was actually generated once your record reaches Head of Section — don't assume it happened automatically.
✅ Remember there's no Reject option here — only Put Back.

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Project Title | Link → Project Registration | **Yes** | |
| Fund Received Ref No. | Data, read-only | No | "Receiving from Accounts Portal" |
| Sanction Ref No. | Data (free text, not a formal Link) | No | Must be the exact Fund Sanction record name — see the Important note above |
| Fund Received Amount | Currency | **Yes** | |
| Bank Account Number / Scheme | Data | **Yes** | |
| Is GST Invoice Issued? / Invoice Number | Select/Data | No | May not display reliably through the standard screen |
| Sanction Transaction Details | Table | No | Transaction Number, Date (defaults to today), Amount, optional Attachment |
| Budget Breakup of the Received Amount | Table | No | Account Head (a real Link this time), Amount Received, Remarks |
| Upload Supporting Document | Attach | No | |

### What Happens After You Submit

**RnD Miscellaneous staff:** Review your figures and, satisfied, Forward the record — this is the exact moment your data is sent to the external Accounts Portal system for its own independent review.

**The external Accounts Portal:** Reviews the bank-side data (independently of anyone in your R&D office) and, when satisfied, reports back — your record then automatically advances without anyone here clicking an "approve" button for that specific step.

**RnD Miscellaneous staff (again):** Once the external system has approved, they gather deposit-slip details and trigger the "Generate Deposit Slip" action, creating the linked Deposit Slip record described in the next section.

**Head of Section:** Gives the final internal approval — and, behind the scenes, this is also the trigger point that's supposed to auto-finish and publish the linked Deposit Slip.

**RnD Accounts:** Performs a final "Verify" to close the record out completely.

### More Frequently Asked Questions

9. **What's the "Fund Received Ref No." field for, and do I fill it in?** No — it's described as coming from the Accounts Portal itself; leave it for the system/process to populate.
10. **Can one Fund Received record cover multiple bank transactions?** Yes — add as many rows as needed to the Sanction Transaction Details table.
11. **What if the external Accounts Portal takes a long time to respond?** There's no timeout or reminder built into the system for this — if it's been unusually long, ask your R&D office to check on the sync status directly with the Accounts Portal team.
12. **Is there a way to manually force my record past the "PENDING_APPROVAL" stage?** Not through the normal process — that stage genuinely depends on the external system's response.

---

## 3.3 Deposit Slip family 🟢🟡

### Overview

**What it is:** Six different Deposit Slip forms, each for a different kind of money being credited to a project, plus one older, unused "generic" prototype version. You will almost never fill these in directly by hand — they are created **automatically** as part of the Fund Received process described above, once RnD Miscellaneous staff supply the details.

**Why it exists:** Once money is confirmed received, it needs to be formally credited against the right project budget heads, with the correct GST/tax treatment for the specific type of income involved (a research grant is taxed and split differently than consultancy income, for example).

| Deposit Slip Type | What it's for | Real usage found |
|---|---|---|
| **Research Deposit Slip** | Money from a research grant | 🟢 Actively used |
| **Research Consultancy Deposit Slip** | Consultancy income routed like research income | 🟠 Defined, no real records yet |
| **D Consultancy Deposit Slip** | Direct/domestic consultancy income | 🟠 Defined, no real records yet |
| **E Non Routine Deposit Slip** | Non-routine event/service income | 🟢 Actively used |
| **Other Event Deposit Slip** | Training/license-fee events | 🟢 Actively used |
| **T Testing Deposit Slip** | Testing-service income | 🟠 Defined, only ever partly started, never finished |
| **Deposit slip** (generic prototype) | An early, all-in-one version of the six above | 🔴 Not used — treat as retired |

---

### What's on These Forms

All six specialized types share a similar shape: project details, the client/funding agency, bank information, and a set of GST/overhead calculation fields specific to the income type — for example, IGST/CGST/SGST splits calculated for you, and percentage-based distributions into funds like IDF (Institute Development Fund), DPF, staff welfare, and student welfare. A few types (E Non Routine and Other Event specifically) also support crediting the amount across multiple projects at once via an "Additional Project Credits" table, rather than just the one linked project.

Each type also carries an "ECS Dates" table (Electronic Clearing Service — essentially, expected bank-transfer dates) that applies across all six.

> **Important:** Although these forms are created automatically most of the time, they technically each have their own create/save screens too, which a dedicated frontend application could use to create one directly, independent of Fund Received. If you're ever asked to fill one of these in by hand rather than seeing it generated automatically, it's most likely being created through such a direct path — treat it the same way, filling in the project/amount/GST details as accurately as you can.

> **Important:** None of the six specialized Deposit Slip types has a fully independent, formal approval workflow of the kind most other applications in this manual have — their status changes are driven directly by the Fund Received process rather than their own standalone chain of approvers. If you ever need to check on one, the most reliable way is to go through the Fund Received record it's linked to, rather than trying to track its status independently.

> **Important:** Because of a specific, known permission-configuration gap, the step where a Deposit Slip is meant to be automatically finished and formally submitted (triggered by the linked Fund Received reaching Approved) can fail without a clear error message to you. If your Fund Received shows Approved, always confirm with your R&D office that the linked Deposit Slip actually reached a finished state too — don't assume it did.

### What's Different Between the Six Types

Each type carries the GST/overhead fields relevant to its specific kind of income:

- **Research Deposit Slip** — IDF percentage (40%), IDF amount, DPF and PDF credit-distribution tables (letting the credit be split across departments/co-PIs), staff welfare (5%) and student welfare (5%) percentages, project account balance, grand total.
- **Research Consultancy Deposit Slip** — CGST (9%) and SGST (9%), rather than a single combined GST figure; an overhead amount described as "15% (inclusive)"; a generic credit-distribution table with label/recipient/percentage/amount rows; IDF/DPF/staff-welfare/student-welfare amounts.
- **D Consultancy Deposit Slip** — IGST (18%) specifically, reflecting interstate consultancy; a three-way consultancy-fee/operational-charge split; DPF credit distribution.
- **E Non Routine Deposit Slip** — a flat IGST (18%), no CGST/SGST split; a consultancy fee figure; supports crediting the amount across **multiple** projects at once via an Additional Project Credits table, not just the one linked project.
- **Other Event Deposit Slip** — event title and principal organizer fields; a flat 18% GST multiplier (labeled as a "License Fee" on the training-fee field); also supports the multi-project Additional Project Credits table.
- **T Testing Deposit Slip** — CGST + SGST split; a notably higher overhead multiplier (70%) than the other types; IDF (40%), DPF (50%), staff welfare (5%), student welfare (5%) fields.

All six share an "ECS Dates" table (Electronic Clearing Service — expected bank-transfer dates), client/funding-agency fields, and bank details.

---

### Frequently Asked Questions

1. **Do I need to create a Deposit Slip myself?** Almost never — it's created automatically as part of processing a Fund Received.
2. **Which of the six types applies to my money?** It depends on the nature of the income — research grant, consultancy, testing service, training/event fee, and so on. Your R&D office / RnD Miscellaneous staff typically determine this when generating it.
3. **Can I find and check my Deposit Slip directly?** Yes, but it's more reliable to check via its linked Fund Received record, since that's what actually drives its status.
4. **Why does my Deposit Slip's status not seem to be updating the way I'd expect?** These don't have their own independent approval chain — their status follows the linked Fund Received's process, and can occasionally lag or fail silently due to the permission gap noted above.
5. **Why do the GST fields look different between two Deposit Slips I'm comparing?** Different income types use different GST structures (a flat IGST vs. a split CGST+SGST, for example) depending on whether the transaction is interstate or intrastate, and the nature of the income — this is expected, not an error.
6. **Can one Deposit Slip credit more than one project?** Only for E Non Routine and Other Event types, via their Additional Project Credits table — the other four types credit only the single linked project.
7. **What does "ECS Date" mean on these forms?** It refers to the Electronic Clearing Service — essentially, the date(s) a bank transfer is expected — recorded in a small dedicated table on every type.

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Can't find a Deposit Slip you expected to exist | It may not have been generated if the original deposit-slip details were judged too sparse when RnD Miscellaneous staff triggered the step | Check with your R&D office whether generation was actually completed |
| A Deposit Slip shows a status that doesn't seem to match its linked Fund Received | These two records' state-tracking doesn't always stay perfectly synchronized | Trust the linked Fund Received record's status as the more reliable indicator |
| GST split looks unusual for your type of income | Each of the six types has a genuinely different GST structure by design | Confirm you're looking at the correct Deposit Slip type for your kind of income |

---

## 3.4 AccountHeadPayment ⚙️ / payments 🔴

### Overview

**AccountHeadPayment** is a background record the system creates whenever an actual payment is made against a project's budget head — it's how the system distinguishes "money we've promised to pay" (called a **commit**, reserved against a budget head when a claim like Reimbursement is approved) from "money we've actually paid out" (a **payment**, recorded once the disbursement genuinely happens). You do not fill this in yourself; it's generated automatically by the payment-processing steps behind Reimbursement, Advance Settlement, Loan Request, and similar forms.

Each AccountHeadPayment record carries a payment status (Pending / Paid / Rejected / Rectification) that your R&D office/finance team tracks internally.

**payments** is a separate, much simpler, older doctype that was never finished being built — it has no real records and no working logic behind it at all (not even a working button, despite having one on the form). 🔴 **Not available.** Ignore it if you ever see it referenced anywhere; it plays no role in how payments actually work in this system.

---

# Part 4 — Procurement

## 4.1 Direct Purchase 🟢

### Overview

**What it is:** Asking the institute to buy an item **directly for you**, without going out to open tender. This is the application that kicks off the longest automatic document chain in the whole system — approving one Direct Purchase quietly generates three further documents behind the scenes.

**Why it exists:** Not every purchase needs (or benefits from) a competitive tender process — for smaller, well-defined, or time-sensitive purchases, Direct Purchase lets the institute buy directly from a chosen vendor, with the appropriate level of oversight scaled to the purchase size.

**Who uses it:** Any project staff needing an item purchased on the project's behalf.

**A worked example:** A lab needs a ₹1,50,000 microscope from a specific supplier. Someone files a Direct Purchase: one item row describing the microscope with justification and estimated price, the Account Head it's charged to, and — because ₹1,50,000 is under the ₹2,00,000 threshold — no Purchase Committee is required this time. It routes through the approval chain to Approved, and the system then automatically generates the paperwork needed to actually place the order.

---

### Before You Start

✅ A clear description and justification for each item you want purchased
✅ An estimated price per item
✅ Know whether your total is likely to exceed ₹2,00,000 (you'll need a Purchase Committee of at least 3 people if so) or the Director-escalation thresholds below
✅ Confirmation of whether this is a foreign purchase

---

### Step-by-Step: Filling the Form

**Step 1 — Applying for self or other?**
Defaults to Self; choose Other if arranging this for someone else, filling in their name/department/designation.

**Step 2 — Purchase Basics**
- **Is this a foreign purchase?** — required Yes/No.
- **Account Head** — required.
- **Is it Sanctioned?** — required Yes/No, indicating whether funding for this is already sanctioned.

**Step 3 — Items to be Purchased (table)**
For each item: name, description, justification, quantity, estimated price, and the estimated total (computed automatically per row and summed into an overall Total Estimate for you).

**Step 4 — Purchase Committee (table)**
> **Important — automatically required over a real threshold.** If your Total Estimate exceeds **₹2,00,000**, the system requires a Purchase Committee of at least **3 members**. Add each member by selecting their user account (filtered to Permanent Employee/Inspired Faculty category users); their name and designation fetch automatically.

**Step 5 — Attachments and Comments**
Upload a detailed specification document if relevant, and add any comments.

**Step 6 — Declarations**
Tick both declaration checkboxes.

---

### The Approval Process

**Draft** → routes by employee category through **PI/Mentor/Head/Staff** → **Head of Section** → **Dean** → **Approved**.

> **Important — automatic Director escalation.** If the Account Head is Consumable or Contingency and the total estimate exceeds **₹3,00,000**, your Direct Purchase automatically routes through the **Director** before it can be finally approved. (Equipment purchases have their own separate, higher threshold — check with your R&D office for the precise current figure if you're near the boundary, since it may differ slightly by category.)

**What happens automatically after Approval — you don't need to trigger any of this yourself:**

1. A **P_11 Form** is generated — the Purchase Committee's formal recommendation record, copying over your item list.
2. A **sanction_sheet** is generated from that P_11 Form — the formal sanction record, with cost totals (basic value + packing/forwarding + freight + other charges).
3. A **dp_po** (the actual Purchase Order document, ready to print/send to the vendor) is generated from the sanction sheet, pulling in vendor details, item pricing with GST/discount, and standard terms and conditions.
4. Your original Direct Purchase record itself moves to a final **"PO Generated"** status.

> **Important:** The P_11 Form and sanction_sheet documents in this automatic chain each have their **own internal "status" field on screen, but that status tracking is effectively broken** for both of them — for slightly different technical reasons in each case, their state doesn't actually update through any working approval process of their own. In practice, this doesn't stop your Direct Purchase from completing successfully, because it's the *main* Direct Purchase record's own approval chain that actually drives the whole process forward — but if you ever open the P_11 Form or sanction_sheet directly expecting to see live, meaningful status updates on those specific documents, don't rely on what you see there. Check the original Direct Purchase record for the real, current status instead.

---

### Workflow States Explained

**Draft** — Editable.

**Various "Pending X Approval" stages** — Sequential, per the chain above.

**Approved** — Finished the internal approval; the three-document chain (P_11 Form → sanction_sheet → dp_po) is generated from here.

**POGenerated** — The Purchase Order has been created and is ready.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **What's the difference between Direct Purchase and Indent General Form?** Direct Purchase buys directly, without a tender; Indent General Form goes out to open bidding/quotation.
2. **When do I need a Purchase Committee?** Automatically required once your total estimate exceeds ₹2,00,000.
3. **What happens after my Direct Purchase is Approved?** The system automatically generates a P_11 Form, then a sanction_sheet, then the actual Purchase Order (dp_po) — you don't need to do anything for this to happen.
4. **Can I check the status of the P_11 Form or sanction_sheet directly?** You can open them, but their own on-screen status tracking doesn't reliably work — check your original Direct Purchase record for the real status instead.
5. **What triggers Director-level approval?** Consumable/Contingency purchases over ₹3,00,000; Equipment has its own higher threshold — confirm the exact current figure with your R&D office if you're near the boundary.
6. **Where's my actual Purchase Order document?** In the auto-generated `dp_po` record linked to your Direct Purchase, once it reaches "PO Generated."

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Purchase Committee section won't let you submit | Total estimate crossed ₹2,00,000, requiring at least 3 committee members | Add the required members |
| P_11 Form or sanction_sheet shows a confusing/unchanging status | Known broken status-tracking on those auto-generated documents | Rely on your original Direct Purchase record's status instead |
| Purchase seems stuck despite being Approved | The auto-generation chain may still be mid-process | Check with your R&D office if the PO hasn't appeared within a reasonable time |

---

### Quick Tips

✅ Estimate your total carefully upfront — crossing ₹2,00,000 changes what the form requires of you.
✅ Don't chase status on the auto-generated P_11 Form/sanction_sheet — check the original Direct Purchase record instead.
✅ Attach a detailed specification document if the item is technical or unusual, to help your approvers.

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Register for (Self/Other) | Select | No | |
| Applicant / Applying For Name / Department / Designation | Data | No | |
| Project No. | Data | No | |
| Is Foreign (purchase)? | Select (Yes/No) | **Yes** | |
| Account Head | Link → Budget Head | **Yes** | |
| Items to be Purchased | Table | **Yes** | Item name, description, justification, quantity, estimated price, estimated total |
| Purchase Committee | Table | Conditionally required above ₹2,00,000 | Minimum 3 members if required |
| Total Estimate | Data | No | Computed |
| Is it Sanctioned? | Select (Yes/No) | **Yes** | |
| Upload Detailed Specification | Attach | No | |
| Comments if any | Small Text | No | |
| Declaration 1 / 2 | Check | No | |

### What This Chain Looks Like End-to-End

To make the automatic 4-step chain concrete: your **Direct Purchase** record is what you fill in and what carries the real, live approval status throughout. Once it reaches Approved, the system silently creates a **P_11 Form** (copying your item list into it, as the Purchase Committee's formal written recommendation), then a **sanction_sheet** (the formal sanction record, adding packing/freight/other-charges on top of the basic item costs to produce a grand total), and finally a **dp_po** (the literal, printable Purchase Order with vendor address, PO number, item pricing including GST/discount, and standard terms and conditions boilerplate) — at which point your original Direct Purchase moves to "PO Generated." None of these three generated documents need you to do anything; they exist as the paper trail behind your one original request.

### More Frequently Asked Questions

7. **Do I need to separately open and check the P_11 Form or sanction_sheet?** No — and as noted above, their own status displays aren't reliable anyway; your Direct Purchase record is the one to watch.
8. **Where do I get the final Purchase Order document to send to a vendor?** It's the auto-generated `dp_po` record, reachable once your Direct Purchase shows "PO Generated."
9. **Can I purchase from a foreign vendor through this form?** Yes — mark "Is this a foreign purchase?" as Yes; this doesn't change the approval chain, just flags the nature of the purchase.
10. **What if my item doesn't have a clean per-unit price (e.g., a custom service)?** Enter your best estimate in the Estimated Price field and use the Justification field to explain the nature of the cost.

---

## 4.2 Indent General Form (IGF) 🟢

### Overview

**What it is:** A general purchase requisition that goes out to **open tender/quotation** — the competitive-bidding sibling of Direct Purchase, used when the purchase should be opened up to multiple vendors rather than bought directly from one.

**Why it exists:** Larger or non-urgent purchases benefit from competitive quotes; this form formalizes that tendering process from indent through to final purchase committee sign-off.

**Who uses it:** Project staff/PIs needing to purchase items through open or limited tender.

**A worked example:** A lab needs new fume hoods, estimated at ₹4,00,000 total — large enough to warrant competitive quotes. Someone files an Indent General Form: indenter details, the project, Account Head category "Equipment," item rows with estimated rates, a Purchase Committee of 3 members, tender type "Open," and the expected number of bids.

---

### Before You Start

✅ Item details and estimated rates
✅ At least 3 Purchase Committee members lined up
✅ Know whether this should be a Limited or Open tender
✅ Be aware of the Director-escalation thresholds below if your purchase is large

---

### Step-by-Step: Filling the Form

**Step 1 — Indenter Details**
Your Webmail ID; indenter name, designation, employee code all fetch automatically.

**Step 2 — Project and Account Head**
- **Project Title** — required; the project code fetches automatically.
- **Account Head** — required Select: Consumable, Contingency, Equipments, or Other.
- **Department/Centre/Section**.

**Step 3 — Items (table, required)**
Item name (required), description, justification, quantity (required), estimated rate, and estimated amount.

**Step 4 — Purchase Committee (table, minimum 3 members)**

**Step 5 — Tender Details**
- **Tender Type** — required Select: Limited or Open.
- **Number of Bids** expected.
- Upload a detailed specification and/or a vendor list if relevant.

**Step 6 — Declaration**
Tick the declaration checkbox.

---

### The Approval Process

**Draft** → **staff, RnD** → **Head of Section** → **Dean** → **Approved**.

> **Important — automatic Director escalation with specific, real thresholds.** If your Account Head is **Equipment** and the total exceeds **₹10,00,000**, or it's **Consumable/Contingency/Other** and exceeds **₹3,00,000**, the request **automatically routes through the Director** before the Dean can give final approval. Practically, this means: staff attach a Director-signed PDF once it's ready, and the Dean's final Approve action is **blocked** until that PDF is in place. If you're a Dean reviewing an eligible request and can't Approve it, check whether this PDF is still pending.

A Dean can also manually flag a request to go through the Director even below these thresholds if they judge it necessary — this isn't purely automatic in one direction.

Corrections can be sent back ("Put Back") through the chain.

---

### Frequently Asked Questions

1. **When does my purchase need Director approval?** Automatically, if it's Equipment over ₹10,00,000, or any other category over ₹3,00,000.
2. **What if my Dean can't Approve my request even though it looks ready?** Check whether it needs Director sign-off first — the Approve button for the Dean is deliberately blocked until a Director-signed PDF is attached, for eligible requests.
3. **What's the difference between Limited and Open tender?** This determines how widely the quotation request goes out — check with your procurement office for your institute's specific policy on when each is appropriate.
4. **Do I need a Purchase Committee?** Yes, always — minimum 3 members, unlike Direct Purchase where it's only required above a threshold.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Dean can't click Approve even though the request looks complete | Awaiting a Director-signed PDF for an eligible large purchase | Check with staff whether the Director sign-off step has been completed and attached |
| Purchase Committee table won't accept fewer than 3 rows | This is always required on this form, unlike Direct Purchase | Add at least 3 committee members |

### Full Field Reference

| Field | Type | Required? | Notes |
|---|---|---|---|
| Webmail Id / Indenter / Designation / Employee Code | Link/Data | No | Fetched |
| Project Title | Link → Project Registration | No | |
| Project Code | Data | No | Fetched |
| Account Head | Select (Consumable/Contingency/Equipments/Other) | **Yes** | |
| Department/Centre/Section | Link | No | |
| Items | Table | No | Item name (required), description, justification, quantity (required), estimated rate, estimated amount |
| Total Estimate | Currency, read-only | No | |
| Sanctioned by Agency | Select | No | |
| Committee Members | Table | No | Minimum 3 |
| Tender Type | Select (Limited/Open) | **Yes** | |
| Number of Bids | Int | No | |
| Upload Detailed Specification / Vendor List | Attach | No | Hidden fields |
| Declaration / Confirmation | Check | No | |
| Send to Director | Check | No | Set automatically or manually per the thresholds |
| Director Signed PDF | Data, hidden | No | Populated once staff upload the signed document |

### Quick Tips

✅ Decide Limited vs. Open tender type upfront with your procurement office's guidance.
✅ If your purchase is near the Director-escalation thresholds, check with staff early about whether that step will apply, so you're not surprised by a blocked Approve button later.

### More Frequently Asked Questions

5. **What's the practical difference in outcome between Direct Purchase and IGF for the same item?** Direct Purchase is faster and simpler for smaller, well-defined purchases; IGF is the right choice when competitive quotes are needed or expected — check your institute's procurement policy for when each is required.
6. **Who uploads the Director-signed PDF?** Staff, once the Director has physically signed off, as part of the escalation process for large purchases.
7. **Does the tender type affect my approval chain?** No — Limited vs. Open affects how the tender is run externally, not the internal Draft-to-Approved chain within this form.

---

## 4.3 Indent Cum Sanction Sheet (ICSS) 🟢

### Overview

**What it is:** A combined indent-plus-sanction application that acts as a **hub** — depending on what kind of purchase you're making, it automatically creates and manages one of three specialized sub-applications behind the scenes.

**Why it exists:** Certain categories of purchase (single-manufacturer-only, repair/replacement, or a standardized compatible item) each have their own specific paperwork requirements, but share a common indent-and-sanction front end. ICSS is that common front end.

| You select this indent type... | ...and the system creates/manages a linked... | What it's for |
|---|---|---|
| Proprietary Purchase with Proprietary certificate from the OEM | **proprietary_purchase** | Buying from one specific manufacturer only, with an OEM certificate |
| Standerdised/Emergent Purchase | **standerdized_purchase** | Buying a specific make/model compatible with equipment you already have |
| Repair/Replacement | **repair_replacement** | Sending a broken item out for repair, or replacing it |

(Two further indent types — Annual Maintenance Contract and Rate Contract Purchase — are selectable in the design but don't currently have a fully built sub-application behind them the way the three above do; if you select one of these, treat it as informational rather than expecting the same automatic sub-document creation.)

**Who uses it:** Any project staff needing one of these specific kinds of purchase — always **start from ICSS**, not from the sub-applications directly.

**A worked example:** A specific piece of lab equipment breaks down and needs sending back to the original vendor for repair. Someone files an ICSS with indent type "Repair/Replacement," which creates a linked repair_replacement record where the specific repair details (item name, original PO number, warranty status, vendor, repair cost) are filled in.

---

### Before You Start

✅ Know exactly which of the indent types applies to your situation
✅ Have the specific details ready for that type (manufacturer name and OEM certificate for proprietary purchases; original PO number and warranty status for repairs; make/model and compatibility justification for standardized purchases)

---

### Step-by-Step: Filling the Form

**Step 1 — On the main ICSS form**
Who you're applying for, the project, the Account Head, and — most importantly — the **Indent Type**, which determines everything that follows.

**Step 2 — On the linked sub-application** (opens automatically based on your Indent Type choice)

*If Proprietary Purchase:* manufacturer name, an item table, estimated basic value, packing/freight/other charges (grand total computed for you), mode of payment, delivery period, warranty, supplier details, and three certification checkboxes plus a proprietary certificate attachment and quotation upload.

*If Repair/Replacement:* item name, original PO number, whether it's still under warranty, vendor address, repair expenditure and other charges (grand total computed automatically), mode of payment, and attachments for the original purchase order, an estimate, and a service report.

*If Standardised/Emergent Purchase:* manufacturer name, reasons the alternatives were rejected, an item table, cost breakdown (grand total computed for you), delivery/warranty terms, supplier details, and declarations plus the original purchase order attachment.

> **Note:** You are not meant to create these three sub-applications directly, independent of ICSS — always start from the main ICSS form and select the correct Indent Type. One of the three (Proprietary Purchase) actively stops you from creating it any other way; the other two don't technically stop you, but you should still always go through ICSS for consistency, since that's how the rest of the process expects to find them.

---

### The Approval Process

**Draft** → routes by employee category through **PI/Mentor/Head** → **Staff** → **Head of Section** (which routes automatically to the **Associate Dean if the amount is ≤ ₹1,00,000**, or the **Dean if higher**) → automatic **Director** escalation for large amounts (same thresholds as Indent General Form — Equipment over ₹10,00,000, others over ₹3,00,000) → **Pending PO Generation** → **PO Generated** → **PO Delivered**.

An extensive "Put Back" system exists for sending the request back for correction at almost any stage — this stops being available only once a Purchase Order has actually been generated.

Once fully approved, ICSS generates an **ICSS_PO** — the formal Purchase Order document, ready for printing (for Annual Maintenance Contract-type purchases specifically, this PO also includes a dedicated AMC line-items table with GST and grand total).

> **Important:** When ICSS pushes a status change down into its linked sub-application (proprietary_purchase, standerdized_purchase, or repair_replacement), it does so directly, on the backend, rather than through that sub-application's own separate approval steps — and the two documents' own sets of possible statuses don't perfectly line up with each other. In practice, you should treat the **main ICSS record** as the authoritative source of truth for where your request stands, not the sub-application's own status label, which can occasionally show something that doesn't cleanly match ICSS's own state.

---

### Workflow States Explained

**Draft** — Editable.

**Pending PI/Mentor/Other PI/Head/Staff/HoS Approval** — Sequential stages depending on your category.

**Pending Associate Dean / Pending Dean Approval** — Final internal decision, routed by amount.

**Pending PO Generation → PO Generated → PO Delivered** — The post-approval procurement fulfillment stages.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **Can I create a Proprietary Purchase or Repair/Replacement record on its own?** You shouldn't — always start from ICSS and pick the right Indent Type; one of the three sub-types actively prevents standalone creation.
2. **What's the amount threshold for Dean vs. Associate Dean here?** ₹1,00,000 — different from several other forms in this manual, so don't assume it's always the same figure.
3. **My sub-application's status doesn't match what I see on the main ICSS record — which is correct?** Trust the main ICSS record.
4. **Can I still correct my request after it's gone through several approval stages?** Yes, extensively — until a Purchase Order has actually been generated, after which Put Back is no longer available.
5. **What if my purchase doesn't fit any of the three built sub-application types?** Two further indent types (AMC, Rate Contract Purchase) are selectable but don't have the same fully-built automatic sub-document handling — check with your R&D office for the current process if you select one of these.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Tried to create a Proprietary Purchase directly and got blocked | This sub-type must be created through ICSS | Start over from a new ICSS record instead |
| Sub-application's status looks inconsistent with the main ICSS record | Known status-sync mismatch between ICSS and its linked sub-documents | Treat the main ICSS record as authoritative |
| Can't Put Back a request anymore | A Purchase Order has already been generated, closing off further corrections | Contact your R&D office if a genuine problem needs fixing after this point |

### Full Field Reference (Main ICSS Form)

| Field | Type | Required? | Notes |
|---|---|---|---|
| Applying for self or other | Select | No | |
| Applicant Webmail Id | Link → User | No | With fetched department/designation |
| Project Reference | Link → Project Registration | No | |
| Project No. | Data | No | |
| Account Head | Link → Budget Head | **Yes** | |
| Other Account Head | Data | No | If Account Head = Other |
| Indent Type | Select | **Yes** | Proprietary / Standerdised / Repair-Replacement / AMC / Rate Contract Purchase |
| Send to Director / Director Approval Required | Check | No | |
| Director Signed PDF / Signed PO File | Attach | No | |

### Sub-Application Field Highlights

**Proprietary Purchase:** manufacturer name, item table, estimated basic value, packing/forwarding, freight, other charges, computed grand total, mode of payment, delivery period, warranty, supplier details and email, sanctioned-by-agency confirmation, a proprietary certificate attachment, quotation upload, and three certification checkboxes.

**Repair/Replacement:** item name, original PO number, justification, dimensions/weight, vendor email/address, is-under-warranty flag, indentor contact, proposed carrier, repair expenditure, other charges, computed grand total, mode of payment, and attachments for the original PO, an estimate, and a service report.

**Standardised/Emergent Purchase:** manufacturer name, reasons the alternatives were rejected, item table, total basic value, packing/freight/other charges, computed grand total, mode of payment, delivery period, warranty, supplier name/address/email/contact, sanctioned-by-agency confirmation, an original PO attachment, and declarations.

### More Frequently Asked Questions

6. **Can I switch the Indent Type after I've started filling in the sub-application details?** Changing it would point you at a different sub-application with different fields — best practice is to confirm the correct type before filling in the detailed sub-form.
7. **Does the ₹1,00,000 threshold apply to the ICSS grand total, or the sub-application's own grand total?** The routing decision reads the amount from the linked sub-application record (proprietary_purchase/standerdized_purchase/repair_replacement's own grand total field), not a separate figure on the main ICSS form itself.
8. **What if my purchase doesn't fit any of the built-out categories?** Two further indent types (AMC, Rate Contract Purchase) are selectable but don't have the same fully-built automatic sub-document creation — check with your R&D office for the current process if you pick one of these.

---

## 4.4 NIQ 🟠

### Overview

**What it is:** "Notice Inviting Quotation" — a free-form document for drafting the text of a formal notice inviting vendors to quote, tied to a project and/or a specific Direct Purchase.

**Status:** Very lightly used, and loosely governed — there is no formal multi-stage approval process behind this form the way there is for most other applications in this manual. It functions more like a shared drafting document than a workflow application: you (or your R&D office) write and save the notice text, tied to the relevant project/purchase reference.

**How to use it:** Link it to the relevant project and/or Direct Purchase record, and use the built-in text editor to draft the quotation notice content itself.

> **Note:** Because there's no approval chain here, don't expect status labels like "Pending Approval" — treat this purely as a drafting/reference tool rather than a formal record requiring sign-off.

---

# Part 5 — Recruitment & Staffing

These three applications form a real end-to-end hiring pipeline, always used in this order:

**Recruitment Adhoc Contractual** (post the position) → **Selection Committee Report** (record the interview outcome) → **Project Staff Details** (onboard the selected candidate).

## 5.1 Recruitment Adhoc Contractual 🟢

### Overview

**What it is:** Creating a formal job posting for an Adhoc or Contractual project-staff position — the starting point of the hiring pipeline above.

**Why it exists:** Hiring project staff (as distinct from regular institute employees) needs its own posting, interview-scheduling, and committee-selection process, tracked against the specific project and funds available.

**Who uses it:** A Permanent Employee (typically the PI or their department) initiating a hiring process for their project.

**A worked example:** A PI needs to hire a Junior Research Fellow on a contractual basis. They file a Recruitment Adhoc Contractual record: appointment type "Contractual," project details, funds sanctioned/received figures, an interview date/time/venue/mode, one row in "Details of Posts" for the JRF position, and a Selection Committee of three members (the PI as convener, plus two subject experts) — the Dean will assign a chairperson later in the process.

---

### Before You Start

✅ Confirmed funds sanctioned/received figures for the position
✅ At least 2 subject-expert committee members lined up, in addition to yourself as PI/convener
✅ Interview logistics decided — date, time, venue, and mode (in-person/online)
✅ The four declarations you'll need to confirm are things you're comfortable certifying

---

### Step-by-Step: Filling the Form

**Step 1 — Appointment Basics**
Appointment type (Adhoc or Contractual), project details (title, code, department, duration — these fetch automatically, read-only), and funds sanctioned/received.

**Step 2 — Interview Logistics**
Interview date, time, venue, mode, and PI contact details.

**Step 3 — Details of Posts (table)**
One row per position being filled in this posting — a repeatable table so you can post for multiple positions at once if needed.

**Step 4 — Selection Committee (table, minimum 3 members)**
The PI acts as convener, plus at least two further experts. A chairperson for the committee is assigned separately, later, by the Dean — you don't select this yourself when first filing.

**Step 5 — Declarations**
Tick all four declaration checkboxes.

---

### The Approval Process

**Draft** (Permanent Employee) → **Head** (specifically the individual person named as Head for this request, not just anyone holding that role generally) → **staff, RnD** → **Head of Section** → **Associate Dean** → **Dean** (Approve) → **Approved**.

Put Back is available at every one of these stages for corrections, which then genuinely allows resubmission through the normal process.

---

### Workflow States Explained

**Draft** — Editable.

**Pending Head Approval → Pending Staff Approval → Pending HoS Approval → Pending Associate Dean → Pending Dean Approval** — Sequential stages, in that order.

**Approved** — Finished; this is a genuine "submitted" record from fairly early in the chain onward (from Head Approval), unlike some other applications where "submitted" status is only reached right at the very end.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **Who assigns the Selection Committee chairperson?** The Dean, later in the process — not something you choose when first filing.
2. **What comes after this application is Approved?** A Selection Committee Report is filed to record what actually happened at the interview — see the next section.
3. **Can this be sent back for correction?** Yes, at every stage of the chain, and resubmission genuinely works.
4. **Who exactly needs to act at the "Head Approval" stage?** Specifically the person designated as Head for this particular request — not any user who generally holds a Head-type role.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Head Approval stage seems stuck even though someone with a "Head" role is available | Only the specific person named as Head for this exact request can act, not any Head-role holder generally | Confirm the correct named individual is the one attempting the action |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Appointment Type | Select | Adhoc or Contractual |
| Project Title / Code / Department / Duration | Data, read-only | Fetched from the project |
| Funds Sanctioned / Funds Received | Currency | |
| Interview Date / Time / Venue / Mode | Date/Time/Data/Select | |
| PI Contact | Data | |
| Details of Posts | Table | Repeatable — one row per position being filled |
| Selection Committee | Table | Minimum 3 members: PI as convener + 2 experts |
| Declaration 1–4 | Check | |

### What Happens After You Submit

**At the Head Approval stage:** Specifically, the individual person designated as Head for your request (not just any Head-role holder) reviews the posting details and forwards it on.

**At staff, RnD, Head of Section, Associate Dean, and Dean:** Each performs their own level of review — checking funds, position details, and committee composition — before forwarding, rejecting, or putting the request back for correction. Because Put Back genuinely works at every stage here, don't hesitate to ask for a correction if something needs fixing rather than letting an imperfect posting proceed.

### More Frequently Asked Questions

5. **Can I post for more than one position in a single Recruitment Adhoc Contractual record?** Yes — the Details of Posts table is repeatable, so you can list multiple positions in one posting.
6. **Who decides Adhoc vs. Contractual?** This is your own choice as the filer, based on the nature of the appointment — it has significant downstream consequences (it determines whether the Selection Committee Report will need Director sign-off, see the next section).
7. **Does the Selection Committee need to include external experts, or can they all be from my own department?** The form requires a minimum of 3 members (PI as convener plus at least 2 experts) but doesn't itself enforce where those experts come from — follow your institute's own selection-committee composition policy.

---

## 5.2 Selection Committee Report 🟢

### Overview

**What it is:** The formal record of what actually happened at the interview for a posting created above — the candidate list with outcomes, committee member details, an attendance report, and (for Contractual positions specifically, not Adhoc) a Director sign-off step.

**Why it exists:** Documents the interview outcome formally, drives the automatic creation of full candidate profile records for anyone recommended, and — for Contractual hires — requires an extra layer of institutional sign-off before proceeding.

**Who uses it:** Committee members/staff recording the outcome of a recruitment interview, always linked back to a specific Recruitment Adhoc Contractual posting.

**A worked example:** Following the JRF interview from the example above, the committee files a Selection Committee Report, linked to that original posting (project/date/PI details auto-fill from it). The candidate list marks one candidate as "Recommended," attaches the attendance report, and ticks the checklist boxes. Since this is a Contractual position, once it's forwarded through the normal chain, it must also pass through a Director sign-off before the Dean's final approval.

---

### Before You Start

✅ The specific Recruitment Adhoc Contractual posting this report is for
✅ The full candidate list with each candidate's outcome (Recommended, Waiting List, Not Selected, etc.)
✅ The attendance report and other required checklist documentation
✅ Know whether this is an Adhoc or Contractual position, since that changes the approval path

---

### Step-by-Step: Filling the Form

**Step 1 — Link to the Recruitment Posting**
Select the specific Recruitment Adhoc Contractual record (**required**) — general details (recruitment type, project name/number, PI, interview date) auto-fill from it.

**Step 2 — Candidates**
Enter the full candidate list and each candidate's outcome (this is captured as a structured list on the form, covering name and result per candidate).

**Step 3 — Committee Members**
Record who sat on the committee, mirroring the members named on the original posting.

**Step 4 — Attendance and Checklist**
Upload the attendance report, and tick the three checklist confirmation checkboxes.

**Step 5 — Director Sign-off (Contractual positions only)**
If your Dean determines this recruitment needs Director-level sign-off (which is the norm for Contractual, as opposed to Adhoc, positions), a flag is set and a **Director-signed PDF** must be uploaded before the process can reach final approval.

---

### The Approval Process

**Draft** (Permanent Employee or Independent Researcher) → **staff, RnD** forwards → **Head of Section** forwards → **Associate Dean** forwards → **Dean** Approves → **Approved**.

> **Important:** For **Contractual** recruitments specifically, the Dean's normal, direct approval path is **blocked** — the process instead must go through a Director sign-off step first (a Director-signed PDF has to be uploaded). Once that Director-approval stage is triggered, there is currently **no way to send it back for correction** — it can only move forward to Approved from there. If something needs fixing at that late stage for a Contractual hire, it will need to be resolved outside the normal system flow.

> **Note:** Once you mark candidates as "Recommended" or "Waiting List" and the report reaches Approved, the system **automatically fetches each such candidate's full profile** (from the recruitment portal) and creates a permanent candidate-detail record for them — this is exactly what feeds into the next step, Project Staff Details, so you don't need to manually re-enter their personal details there.

---

### Workflow States Explained

**Draft** — Editable.

**Pending Staff Approval → Pending HoS Approval → Pending Associate Dean → Pending Dean Approval** — Sequential, for Adhoc positions.

**Pending Director Approval** (Contractual positions only) — A special stage reachable only when the Dean flags a Contractual recruitment for Director sign-off; approvable only, no Put Back available from here.

**Approved** — Finished; candidate profile records are auto-created at this point.

**Approved – Appointment Order Generation** — A further stage reachable after Approved, where staff, RnD can generate the formal appointment order.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **What's the difference in process between Adhoc and Contractual positions?** Contractual positions require an extra Director sign-off step before the Dean's final approval; Adhoc positions go straight to Dean.
2. **What happens to candidates I mark "Recommended"?** Once the report is Approved, the system automatically creates a full profile record for them, feeding into the next onboarding step.
3. **Can a Contractual recruitment's Director-approval stage be corrected if something's wrong?** No — once triggered, it only moves forward; there's no Put Back from that specific stage.
4. **What comes after this report is Approved?** Onboarding the selected candidate via Project Staff Details.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Dean can't directly Approve a Contractual recruitment's report | It must first go through Director sign-off | Confirm a Director-signed PDF has been uploaded |
| Can't send a Director-Approval-stage record back for correction | No Put Back exists from that specific stage by design | Handle the correction outside the normal system flow — contact your R&D office |
| A candidate you marked "Recommended" doesn't seem to have a profile record yet | Profile creation happens automatically once the report reaches Approved | Confirm the report has actually reached Approved status |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Recruitment Reference (interview_id) | Link → Recruitment Adhoc Contractual | Required |
| Recruitment Type / Project Name / Number / PI / Date of Interview | Data, read-only | Fetched from the linked posting |
| Candidates | Structured list | Full candidate list with interview outcomes |
| Committee Members | Structured list | Mirrors the posting's committee |
| Attendance Report | Attach | |
| Checklist confirmations | Check (×3) | |
| Send to Director | Check | Set by the Dean for Contractual positions |
| Director Signed PDF | Attach | Required before Director-stage approval can complete |

### Quick Tips

✅ Double-check every candidate's outcome is recorded accurately before submitting — this directly drives automatic profile creation for anyone marked Recommended or Waiting List.
✅ For Contractual positions, get the Director sign-off process moving early, since that stage has no way back if something's wrong.
✅ Keep the attendance report clear and complete — it's one of the required checklist items.

### More Frequently Asked Questions

5. **What outcomes can I mark a candidate with?** The system captures a free-form outcome per candidate (commonly Recommended, Waiting List, Not Selected, or similar) — check with your R&D office for your institute's standard terminology.
6. **Does the automatic profile-creation step work for Waiting List candidates too, or only Recommended ones?** Both — the system fetches full profiles for candidates marked either Recommended or Waiting List once the report is Approved.
7. **What if the recruitment portal's profile lookup fails for a candidate?** This is logged internally rather than blocking your report; if a candidate's profile record seems to be missing after approval, ask your R&D office to check the error log or manually create it if needed.

---

## 5.3 Project Staff Details (Joining Form) 🟢

### Overview

**What it is:** The onboarding/joining form for a candidate selected through the recruitment process above — personal details, employment details, and required uploads, leading to the creation of the person's actual login account in the ERP.

**Why it exists:** Formally records everything needed to bring a selected candidate onto the project as staff — their personal and banking details, their employment terms, and the tenure they're being engaged for.

**Who uses it:** Staff completing the onboarding process for a newly-selected candidate, always tied back to a specific selection outcome.

**A worked example:** Following the Approved Selection Committee Report above, staff file a Project Staff Details "joining form" for the recommended candidate — personal details (name, DOB, address, PAN/Aadhaar, bank account), employment details (designation, department, joining date, term completion date, salary/allowances), and uploads for photo, signature, and medical certificate.

---

### Before You Start

✅ The specific selected candidate this joining form is for (via their Selection Committee Report reference — you cannot create more than one joining form per candidate)
✅ Their personal and bank details
✅ Their employment terms — designation, joining date, term completion date, salary structure

---

### Step-by-Step: Filling the Form

**Step 1 — Candidate Reference**
This ties back to a specific candidate selected through the recruitment process. The system will **block you** from creating a second joining form for a candidate who already has one — it enforces "one joining form per candidate" automatically.

**Step 2 — Personal Details**
Name, date of birth, father's name, gender, marital status, blood group, addresses, PAN, Aadhaar, and bank account details.

**Step 3 — Employment Details**
Designation, department, joining date, term completion date, and the salary structure (basic salary, HRA, medical, travel allowance, hostel, as applicable).

**Step 4 — Tenure Details (table)**
A repeatable table capturing joining date, term completion date, basic salary, increment, and HRA per tenure period — this supports someone's appointment being extended over multiple periods.

**Step 5 — Uploads**
Photo, signature, and medical certificate.

---

### The Approval Process

**Draft** → **staff, RnD** submits → **Head of Section** forwards → **Associate Dean** Approves → **Approved**.

> **Important — there is currently no reject or correction path at all on this specific form.** Once submitted, it can only move forward to Approved; there is no "Reject" or "Put Back" option built into this particular workflow. If something needs correcting after submission, it cannot be handled through the normal system flow — it will need to be resolved directly with your R&D office.

> **Note:** Your Employee ID is only actually assigned at the moment of **final Approval**, not when the form is first created — so an abandoned or never-submitted joining form doesn't "waste" an ID number in the sequence.

> **Note:** Once Approved, the system **automatically creates the person's login account** in the ERP, and automatically works out their initial Casual Leave and Earned Leave balances based on the length of their tenure.

---

### Workflow States Explained

**Draft** — Editable.

**Pending HoS Approval → Pending Associate Dean Approval** — The only two stages this workflow actually uses in practice.

**Approved** — Finished; login account and leave balances are created automatically at this point.

> **Note:** A few further states ("Pending Dean Approval," "Rejected," "Put Back") are technically defined in the system's configuration for this form but are **not actually reachable** through any real path — the process, as built, only ever goes Draft → Pending HoS Approval → Pending Associate Dean Approval → Approved.

---

### Frequently Asked Questions

1. **Can I create a second joining form if I made a mistake on the first?** No — the system blocks duplicate joining forms for the same candidate; you'll need to correct the existing one instead, though see the note below about the lack of a correction path.
2. **What if something is wrong after I've submitted this form?** There's currently no built-in way to send it back for correction — this needs to be resolved directly with your R&D office, outside the normal workflow.
3. **When is the Employee ID actually assigned?** Only at final Approval, not when the form is first created.
4. **What happens automatically once this is Approved?** The person's ERP login account is created, and their initial leave balances are calculated automatically.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "A joining form already exists for this candidate" | The system enforces one joining form per candidate | Locate and correct the existing record instead of creating a new one |
| Something's wrong after submission and there's no way to fix it | No reject/correction path exists on this form | Contact your R&D office directly for manual resolution |
| New staff member's login account isn't showing up | Their joining form hasn't reached Approved yet | Confirm the joining form's current status |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Personal Details | Data | Name, DOB, father's name, gender, marital status, blood group, addresses |
| PAN / Aadhaar | Data | |
| Bank Account | Data | |
| Employee ID | Data, system-assigned | Only allocated at final Approval, not at creation |
| Designation / Department | Link/Data | |
| Joining Date / Term Completion Date | Date | |
| Basic Salary / HRA / Medical / Travel Allowance / Hostel | Currency | As applicable |
| Tenure Details (table) | Table | Joining date, term completion date, basic salary, increment, HRA, extension-sought fields, joining number — supports multiple tenure periods over time |
| Photo / Signature / Medical Certificate | Attach | |
| scr_id / pi_id / application_id | Data | Ties this joining form back to the specific selected candidate |

### Quick Tips

✅ Double-check personal and bank details carefully — this directly creates the person's real payroll and login information.
✅ Because there's no correction path, have someone double-check the form before final submission rather than relying on being able to fix it afterward.
✅ Remember the Employee ID isn't assigned until Approval — don't quote a "pending" ID number to the new staff member as if it's final.

### More Frequently Asked Questions

5. **What determines a new staff member's initial leave balance?** The system calculates it automatically once Approved, based on how many months their tenure covers — Casual Leave and Earned Leave are both computed this way.
6. **Can I use this form to onboard someone who wasn't hired through the Recruitment Adhoc Contractual → Selection Committee Report process?** The form is designed to tie back to a specific selected candidate from that pipeline — check with your R&D office if you have a different onboarding scenario.
7. **Does the Tenure Details table let me record a later extension?** Yes — it's built to support multiple tenure periods over time, though the dedicated standalone Extension application itself isn't available (see [§5.4](#54-extension-of-tenure-of-appointment-)).

---

## 5.4 Extension Of Tenure Of Appointment 🔴

### What it is meant to do

Apply to extend a project staff member's appointment beyond its current expiry date.

**Status:** Not available. This application's design exists in the system, but it was never finished being built — there is no working form to fill in or submit today. If you need to extend someone's tenure, this is currently handled through the tenure-extension fields already present on the **Project Staff Details** joining record instead (its Tenure Details table has fields specifically for this) — check with your R&D office for the current process.

---

# Part 6 — Contracts & Fellowships

## 6.1 Rate Contract 🟢

### Overview

**What it is:** A purchase indent specifically for items already covered under the institute's pre-negotiated Rate Contracts — a fixed, pre-agreed price arrangement with specific vendors, so individual purchases don't each need their own separate price negotiation. This is the most complex approval process of any application in this whole manual, because it has to correctly handle a wide range of applicant categories and two very different item categories at once.

**Why it exists:** For frequently-purchased categories of item (certain chemicals, glassware, UPS batteries, printer cartridges, and similar), the institute negotiates standing rate agreements with approved vendors. Rate Contract lets staff purchase against those agreements quickly, with lighter oversight than a fresh tender, while still going through proper approval.

**Who uses it:** Any project staff needing to buy an item covered under an existing Rate Contract.

**A worked example:** A lab needs 10 liters of a specific reagent covered under a "P3" rate contract with an approved chemical supplier. Someone files a Rate Contract request: form type "P3," item type "Chemicals," the principal supplier and local supplier details, one item row with unit rate/quantity/discount/GST, and the three P3 certification checkboxes (authorized firm, current price list, delivery timeline).

---

### Before You Start

✅ Know whether your purchase falls under **P3** (chemicals, glassware, plasticware, filtration, custom services, mixed catalogue, gas refilling) or **P4** (UPS batteries, printer cartridges, gas refilling, copier papers, UPS and transformers, furniture)
✅ Identify the correct principal supplier (and, for P3, the local supplier who actually delivers)
✅ Have current pricing/discount/GST details for each item ready

---

### Step-by-Step: Filling the Form

**Step 1 — Form Type**
Select **P3** or **P4** — this changes almost everything else on the form.

**Step 2 — Project and Account Head**
Project number, Account Head (with an "Other" option if the exact head you need isn't in the list), and — read-only, for reference — a link to any related Indent Cum Sanction Sheet if one exists.

**Step 3a — If P3:**
- **Item Type** — required Select (Chemicals/Glassware/Plasticware/Filtration/Custom Services/Mixed Catalogue/Gas Refilling).
- **Principal Supplier** — the OEM/national-level supplier, with address and agreement number.
- **Local Supplier** — the local agent who actually delivers, with address and email.
- Three required certification checkboxes: the firm is authorized, prices are current, and delivery timeline is acceptable.

**Step 3b — If P4:**
- **Item Type** — required Select (UPS Batteries/HP Printer Cartridges/Gas Refilling/Copier Papers/UPS and Transformers/Furniture).
- **Vendor** — with address and email.
- **Justification** — required.

**Step 4 — Items (table)**
Description, catalogue number, page number, unit rate, quantity, discount percentage, GST percentage — the amount per row, the overall total, and the grand total (including packing/freight you enter separately) are all computed for you, along with an automatic "amount in words."

**Step 5 — If applying on behalf of another PI's project**
Additional fields appear for that other PI's details, visible only if you are that project's designated PI, Head, or Mentor.

---

### The Approval Process

Routes automatically by your employee category through **PI, Mentor, Head, or Staff**, converging at **Head of Section**, which routes automatically to the **Associate Dean if the grand total is ≤ ₹1,00,000**, or the **Dean if higher** — with extensive "Put Back" options available from the Dean all the way back down through the chain, including in some paths back to Draft.

> **Note:** This is by far the most heavily-branched approval process covered in this manual, with over 40 distinct possible transitions depending on your employee category, whether the project has another PI involved, and the total amount. If a step in your approval chain looks unusual or unexpected, it's very likely a genuine, deliberate branch in this complex routing logic rather than an error — check with your R&D office if you're ever unsure why your request took a particular path.

---

### Frequently Asked Questions

1. **What's the difference between P3 and P4?** P3 covers chemicals/glassware/lab-consumable-type items with a principal-and-local-supplier structure; P4 covers equipment-and-hardware-type items (UPS, cartridges, furniture) with a single vendor.
2. **What's the amount threshold for Dean vs. Associate Dean here?** ₹1,00,000 on the grand total, the same threshold used by Indent Cum Sanction Sheet.
3. **Can this be sent back for correction?** Yes, extensively, at nearly every stage.
4. **What if I'm buying on behalf of a project where I'm not the PI myself?** Extra fields for the actual PI's details appear, but only if you're that project's designated PI, Head, or Mentor.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Unexpected approval stage appears in your chain | This form has many legitimate branches by category/amount/other-PI status | Usually expected — check with your R&D office if genuinely unsure |
| Can't find "Other PI" fields | These only appear if you're specifically that project's PI, Head, or Mentor | Confirm your role on the relevant project |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Form Type | Select | P3 or P4 — determines almost everything else on the form |
| Project Number / Reference | Link → Project Registration | |
| Indent Cum Sanction Sheet ID | Link → Indent Cum Sanction Sheet | Read-only, if related |
| Account Head | Link → Budget Head | |
| Other Account Head | Data | If Account Head is a specific catch-all value |
| Item Type (P3) | Select | Chemicals/Glassware/Plasticware/Filtration/Custom Services/Mixed Catalogue/Gas Refilling |
| Principal Supplier / Address / Agreement No. | Link/Small Text/Data | P3 |
| Local Supplier / Address / Email | Data/Small Text | P3 |
| Certify Authorized Firm / Current Prices / Delivery Time | Check | P3, all required |
| P4 Item Type | Select | UPS Batteries/HP Printer Cartridges/Gas Refilling/Copier Papers/UPS and Transformers/Furniture |
| Vendor / Address / Email | Link/Small Text | P4 |
| Justification | Small Text | P4, required |
| Items | Table | Item description, catalogue no., page no., unit rate, quantity, discount %, GST % |
| Grand Total | Currency, read-only | Computed |
| Packing | Currency | Entered manually, added into the grand total |
| Amount in Words | Small Text, read-only | Computed |
| Other PI's Details (webmail, name, category, department, mentor) | Various | Only shown if the project has another PI involved and you're that project's PI/Head/Mentor |

### What Happens Across This Long Approval Chain

Because this form's routing branches on so many factors at once (your own employee category, whether another PI is genuinely involved on the project, and the final grand total), it's worth understanding the general shape rather than memorizing every possible path: your request first passes through whichever combination of **PI, Mentor, Head, or Staff** approval applies to your specific situation, all of which converge at **Head of Section** — the one stage every Rate Contract request passes through regardless of how it got there. From Head of Section, the ₹1,00,000 threshold on your grand total decides whether it goes to the **Associate Dean** or the **Dean** for final sign-off. If anything looks wrong along the way, the reviewer at nearly any of these stages can Put Back your request — including, on some paths, sending it all the way back to Draft — for you to fix and resubmit.

### More Frequently Asked Questions

5. **What if I'm not sure whether an item is P3 or P4?** Check the item categories listed in the Form Type step above — P3 covers consumable-style lab items, P4 covers hardware/equipment-style items; if genuinely unsure, ask your procurement office.
6. **Do I need both a Principal Supplier and a Local Supplier for P3 purchases?** Yes — the Principal Supplier is the OEM/national-level source, and the Local Supplier is who actually delivers to you; both are expected fields on P3 requests.
7. **Is packing/freight included in the automatically-computed total?** The per-row item totals and overall item total are computed automatically; you enter Packing separately, and it's then added in to produce the final Grand Total.

---

## 6.2 AMC (Annual Maintenance Contract) 🟠

### Overview

**What it is:** Arranging an annual maintenance contract for equipment — capturing the original purchase order it relates to, equipment details, the contract value with GST, and the service provider's details.

**Status:** Very lightly used, with no formal multi-stage approval process configured for it yet in the system. This application is designed to be spawned automatically from an approved **Indent Cum Sanction Sheet** (when you select "Annual Maintenance Contract" as the indent type there), rather than being created independently from scratch.

**What it captures when used:** Original PO details, equipment details, AMC value, other charges, and GST — with the grand total computed automatically as you enter these three figures. Uploads for the service provider's estimate, proposal, and the original purchase order, plus a declaration checkbox.

> **Note:** Because there's no working approval chain behind this form currently, treat any AMC record you encounter as a supporting reference document tied to its originating ICSS record, not as something with its own independent sign-off process to track.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Indent Cum Sanction Sheet ID | Link → Indent Cum Sanction Sheet | Populated automatically when spawned from an ICSS with indent type "AMC" |
| Original PO Details | Data | Reference to the equipment's original purchase order |
| Equipment Details | Data | |
| AMC Value | Data | |
| Other Charges | Data | |
| AMC GST | Data | |
| AMC Grand Total | Data, read-only | Computed automatically from AMC Value + Other Charges + GST |
| Service Provider Details | Data | |
| Estimate / Proposal / Original PO | Attach | |
| Declaration | Check | |

### Frequently Asked Questions

1. **Can I create an AMC record on my own, outside of ICSS?** You shouldn't — this application is meant to be spawned automatically from an approved ICSS record where you've selected "Annual Maintenance Contract" as the indent type.
2. **Does the grand total calculate itself?** Yes — this specific calculation genuinely works: enter the AMC Value, Other Charges, and GST, and the Grand Total computes automatically.
3. **Who approves an AMC record?** As things stand, there's no formal multi-stage approval process configured for this application — treat it as a supporting record tracked through its parent ICSS record instead.

---

## 6.3 Top Up Fellowship 🟢

### Overview

**What it is:** Requesting a monthly fellowship top-up or teaching-assistantship-style honorarium for one or more students working on your project.

**Why it exists:** Students working on projects sometimes need an additional monthly payment on top of any base fellowship, tied to actual hours worked — this form formalizes that, with a hard monthly cap to prevent over-payment.

**Who uses it:** A Permanent Employee (typically the PI) filing on behalf of the students, or a Student filing for themselves.

**A worked example:** A PI wants to pay two students ₹6,000 each per month for 20 hours of project work at ₹300/hour. They file a Top Up Fellowship listing both students in the student table, each with their engagement period, hours per month, and rate per hour — the total amount per student computes automatically, and since ₹6,000 is well under the ₹25,000 monthly cap per student, there's no issue.

---

### Before You Start

✅ Each student's engagement period, hours per month, and rate per hour
✅ Each student's bank account details
✅ Confirm the combined honorarium + top-up amount for each individual student stays under ₹25,000/month — the system will not let you exceed this
✅ A signed Faculty Admission PDF, which will be needed before this can be forwarded past the Staff stage

---

### Step-by-Step: Filling the Form

**Step 1 — Who's applying**
A Permanent Employee filing on students' behalf, or a Student filing for themselves — this determines the first approval stop.

**Step 2 — Students (table)**
For each student: their user account (roll number, department, contact number fetch automatically), programme, engagement period (from/to), hours per month, rate per hour, and their total amount per month — computed automatically from hours × rate if you don't set it manually. Bank account details (holder name, account number, bank name, IFSC, branch code) round out each row.

**Step 3 — Project and Supervisor Details**
The project, Account Head, supervisor's webmail, and the PI's webmail.

**Step 4 — Faculty Admission Flag**
Indicate whether this needs to be sent to Faculty Admission, and upload the signed PDF once available (required before Staff can forward it onward — see below).

**Step 5 — Declarations**
Tick all three declaration checkboxes.

---

### The Approval Process

**Draft** → routes by category (**Permanent Employee → Head**; **Student → PI** first) → converges through **Head** → **Staff** → **Head of Section** → **Dean** (Approve) → **Approved**.

> **Important — three things must be in place before Staff can forward this onward.** Before the "Forward" action becomes available at the Staff stage, all three of the following must already be true: (1) the "send to Faculty Admission" flag is set, (2) the signed Faculty Admission PDF is actually attached, and (3) the funding commit for this request has already been staged internally. If your request seems stuck at the Staff stage, check these three things first.

> **Important, and genuinely useful to know: the system automatically caps the combined honorarium + top-up for any one student at ₹25,000 per month, and will simply not let a submission exceed that.** This is a real, hard, system-enforced limit — plan your per-student amounts with this in mind from the start.

This form also has a working custom "Put Back" system that lets the current approver send the request back to an earlier stage for correction, outside the normal formal transition list — so corrections genuinely can happen even at stages where you might not expect a standard Put Back button.

**This is the cleanest, best-matched permission setup found anywhere in this entire system** — every approver role the workflow expects also has exactly the correct document access configured, with no gaps identified.

---

### Workflow States Explained

**Draft** — Editable.

**Pending Head Approval → Pending PI Approval → Pending Staff Approval → Pending HoS Approval → Pending Dean Approval** — Sequential stages, per the routing above.

**Approved** — Finished, and genuinely reaches a final "submitted" state in the system.

**Rejected** — Stopped.

---

### Frequently Asked Questions

1. **Is there a cap on how much a student can receive?** Yes — ₹25,000 per month per student, combining honorarium and top-up, hard-enforced by the system.
2. **What do I need before my request can move past the Staff stage?** The Faculty Admission flag set, the signed PDF attached, and the funding commit already staged.
3. **Can this be corrected and resubmitted if something's wrong?** Yes — this form has a genuinely working correction system, even beyond the standard Put Back options.
4. **Does the per-student total calculate itself?** Yes, automatically from hours × rate, unless you set it manually yourself.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| Submission blocked, mentioning an amount limit | You've exceeded the ₹25,000/month/student cap | Reduce the amount for that student, or split the engagement differently |
| Can't Forward past the Staff stage | Faculty Admission flag, signed PDF, or staged commit isn't yet in place | Confirm all three prerequisites are satisfied |
| Total amount per student looks wrong | It auto-computes from hours × rate unless manually overridden | Check both the hours and rate fields for that row |

---

### Quick Tips

✅ Plan per-student amounts against the ₹25,000/month cap from the start.
✅ Get the Faculty Admission PDF sorted early — it's a hard blocker at the Staff stage.
✅ Double-check hours × rate arithmetic per student row.

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Students | Table | One row per student: email (Link → User), roll number/department/contact (fetched), programme, engagement period (from/to), hours per month, rate per hour, total amount per month (auto-computed unless overridden), bank details (holder name, account number, bank name, IFSC, branch code) |
| Project | Link → Project Registration | |
| Account Head | Link → Budget Head | |
| Supervisor Webmail | Link → User | |
| PI Webmail | Link → User | |
| Send to Faculty Admission | Check | Required before Staff can Forward |
| Faculty Admission PDF | Attach | Required before Staff can Forward |
| Declaration 1 / 2 / 3 | Check | |

### What Happens After You Submit

**At the Head or PI stage** (depending on whether you filed as a Permanent Employee or a Student): A review of the overall request — the students listed, their hours, and whether the amounts look reasonable — before forwarding.

**At Staff:** This is the checkpoint stage — staff won't be able to Forward your request until the Faculty Admission flag is set, the signed PDF is attached, and the funding commit has been staged internally. If any of these three things are missing, chase them down before expecting your request to move.

**At Head of Section and Dean:** Further review and final sign-off, with the custom Put Back system available at essentially any point if a correction is needed — genuinely, not just in appearance, unlike several other forms in this manual.

### More Frequently Asked Questions

7. **What happens if a student's total would exceed ₹25,000/month once combined with an existing honorarium?** The system checks this combined total across both sources and will block the submission — you'll need to reduce the top-up amount, or the underlying honorarium, so the combined figure stays under the cap.
8. **Can I list students with different engagement periods in the same request?** Yes — each row has its own from/to dates, so students with different schedules can be combined in one Top Up Fellowship filing.
9. **What is "Faculty Admission" in this context?** A separate internal sign-off step (outside this form) confirming the student's engagement is properly recorded academically — this form requires proof (a signed PDF) that step has happened before Staff can move your request forward.
10. **Does this form work for Teaching Assistant-style engagements too, not just research work?** The form's fields (hours/rate/engagement period) are generic enough to cover either — check with your R&D office on how your institute categorizes different kinds of student engagement for this purpose.

---

# Part 7 — Project Administration

## 7.1 User Delegation 🟢

### Overview

**What it is:** A self-service tool that lets a Permanent Employee — typically a PI who's going to be traveling, on leave, or simply overloaded — hand off visibility, and optionally editing or approval rights, over their own applications and projects to someone else, for a chosen time window.

**Why it exists:** Rather than sharing login credentials (which the institute should never do) or waiting for an IT administrator to manually adjust permissions, a PI can grant a trusted colleague or assistant exactly the access they need, exactly for as long as they need it, entirely themselves.

**Who can use it:** Only users holding the **Permanent Employee** role can create delegations — this is enforced by the system, not just a suggestion.

**A worked example:** A PI is going abroad for six weeks and wants their senior project staff member to be able to view (but not edit or approve) all of their pending applications while they're away. They create a User Delegation: delegate = the staff member, type = "View Only," scope = "all," valid from their departure date to their return date.

---

### Before You Start

✅ Decide exactly what kind of access you want to grant
✅ Decide the scope — everything you own, or just specific projects/applications
✅ Decide a start and end date, if you want the delegation to be time-limited

---

### Step-by-Step: Setting Up a Delegation

**Step 1 — Search for and select the delegate**
Find the colleague you want to delegate to (any active user other than yourself).

**Step 2 — Choose the delegation type**
- **View Only** — the delegate can see your applications/projects, but not edit or act on them.
- **View and Edit** — the delegate can also make changes.
- **Workflow Action** — the delegate can actually approve/act on your behalf at whatever stage your pending applications are sitting at.

**Step 3 — Choose the scope**
- **All** — everything you own.
- **Project** — specific named projects only (you must have selected at least one).
- **Application** — specific named applications only (you must have selected at least one).

> **Note:** You can only delegate scope over projects/applications that genuinely belong to you or are assigned to you (as PI, owner, or Head Approver) — the system checks this and will refuse to let you delegate something you don't actually have a claim to.

**Step 4 — Set a time window (optional)**
Enter a start and/or end date if you want the delegation to automatically stop applying after a certain point. Leave blank for an open-ended delegation.

**Step 5 — Save**
If you already have an active delegation to the same person, creating a new one **merges into it** rather than creating a duplicate — any newly-added projects/applications are added to the existing delegation's scope, and settings you explicitly change are updated; settings you don't touch stay as they were.

---

### Managing Your Delegations

You can view all delegations you've created, and revoke ("undelegate") any of them at any time — only you (as the original delegator) or a System Manager can revoke a delegation you created.

> **Note:** This delegation feature currently has a real, meaningful effect on **only two** applications in this whole manual: **Temporary Advance** and **Reimbursement**. For those two specifically, a delegate with an active delegation will see the delegator's records show up in their own list view alongside their own. For every other application covered in this manual, this delegation mechanism is **not currently wired in** — setting up a delegation will not expand what a colleague can see for any application besides those two.

---

### Frequently Asked Questions

1. **Who can create a delegation?** Only Permanent Employees.
2. **Can I delegate to more than one person?** Yes — you can create separate delegations to different people.
3. **What happens if I create a second delegation to someone I've already delegated to?** It merges into the existing one rather than creating a duplicate — new scope is added, changed settings are updated.
4. **Which applications does this actually affect?** Currently, only Temporary Advance and Reimbursement — it does not expand access to any other application in this manual.
5. **Can I end a delegation early?** Yes — revoke it at any time from your delegation list.
6. **Can someone else revoke a delegation I created?** Only you or a System Manager.
7. **Can I delegate a project I'm not actually connected to?** No — the system checks and blocks this.

---

### Common Errors & Troubleshooting

| Problem | Likely Cause | What To Do |
|---|---|---|
| "Project does not belong to or is not assigned to you" | You tried to delegate scope over a project you're not PI/owner/Head Approver of | Only delegate projects you genuinely have a claim to |
| Delegate says they still can't see something | Delegation currently only affects Temporary Advance and Reimbursement | Don't expect it to expand access on any other application |
| Delegate can view but not act on something | Delegation type was set to "View Only," not "Workflow Action" | Recreate/update the delegation with the correct type if approval rights are genuinely needed |

### Full Field Reference

| Field | Type | Notes |
|---|---|---|
| Delegate User | Link → User | Who you're granting access to |
| Delegation Type | Select (View Only / View and Edit / Workflow Action) | Defaults to View Only on first creation |
| Scope Type | Select (all / project / application) | Defaults to "all" on first creation |
| Project Names | JSON list | Only if Scope Type = project; must belong to you as PI/owner/Head Approver |
| Applications | JSON list | Only if Scope Type = application |
| Valid From / Valid To | Date | Optional; leave blank for open-ended |
| Delegator User | (system-set) | Always your own session user — never something you or anyone else can set to impersonate someone else |

### Quick Tips

✅ Start with "View Only" scope if you're unsure how much access to grant — you can always create a follow-up delegation to expand it later, which will merge into the existing one.
✅ Set an end date for any delegation tied to a specific trip or leave period, so it doesn't linger open-ended after you're back.
✅ Remember this only meaningfully affects Temporary Advance and Reimbursement today — don't rely on it for anything else.

---

## 7.2 Endorsement Data ⚙️

Not something you ever open or fill in yourself — this is a background copy the system automatically keeps of your project's official endorsement letter text, updated every time that letter changes on your Project Registration record. If your organization ever needs to regenerate or reference an old endorsement letter, this is where the system keeps its internal copy. There is no form to fill in, no approval process, and no reason to look for this in your day-to-day work.

---

## 7.3 Not-Yet-Available Applications

The following are referenced in this system's design — they show up in internal project-linking lists, meaning developers planned for them — but currently have **no working form to fill in**, no active approval process, and in most cases zero real usage on record. If your process needs one of these, check with your R&D office for the current manual/alternative process, since the ERP does not yet support it end-to-end:

| Application | What it's meant to do | Current alternative |
|---|---|---|
| **UC Request** | Requesting submission of a Utilization Certificate for a project | Check with your R&D office/finance team for the current manual process |
| **Project Extension** | Applying to extend a project's overall end date | Check with your R&D office |
| **myProjects** | A personal dashboard/listing of your own projects | Use the standard project list/search instead |
| **Extension Of Tenure Of Appointment** | Extending a staff member's appointment | Use the tenure-extension fields on the Project Staff Details joining record instead (see [§5.4](#54-extension-of-tenure-of-appointment-)) |
| **Disbursement of Honorarium** | An abandoned earlier version of Disbursal of Honorarium | Use [Disbursal of Honorarium](#15-disbursal-of-honorarium-) instead |
| **payments** | An abandoned early prototype related to AccountHeadPayment | No alternative needed — the real payment tracking happens automatically behind the scenes via AccountHeadPayment |
| **Deposit slip** (generic prototype) | An abandoned early prototype of the Deposit Slip family | Use the specific [Deposit Slip](#33-deposit-slip-family-) type generated automatically via Fund Received |
| **sanction_sheet_details_of_purchase** | Appears to have been an intended item table for sanction sheets | Not used anywhere in the live procurement chain — the real item data lives on the sanction_sheet record itself |

---

# Cross-Cutting System Notes

A few patterns repeat across many applications in this system. Rather than re-explain them in every section, they're gathered here once, in more depth than the individual application sections could cover.

### 1. Approver roles sometimes lack basic access to the very documents they're meant to approve

Across most of the applications in this manual, at least one approval-chain role (very often **Hos, RnD**, **Dean, RnD**, or **Mentor**, and occasionally **Independent Researcher** or **Project Staff** as applicant categories) is named in the approval steps but doesn't have the underlying system permission to open that document type at all. This happened, in the system's own history, because these applications were often built with a broad "All_ProRnd_User" role in mind covering most staff, and the more specific approval roles were never separately granted access on several forms.

**In practice, this is usually masked** because most staff who hold roles like Hos, RnD or Dean, RnD also happen to hold that broader All_ProRnd_User role, which grants the access anyway. But it is a real, confirmed gap on several forms (Advance Settlement, Disbursal of Honorarium, Disbursal of Consultancy — where it's most severe, Rate Contract, Travel, TA DA Settlement, Selection Committee Report, Project Staff Details, several of the procurement sub-applications, and others). If an approver ever genuinely reports they "can't see" something assigned to them, and it's not simply a matter of them looking at the wrong list, this permission gap is the first thing to check with your System Manager — it usually means their specific account is missing that broader role.

Two related but distinct technical patterns show up alongside this: some applications (Disbursal of Honorarium, Disbursal of Consultancy) were deliberately built to route around the gap by having the backend directly push the document through each stage rather than relying on the normal permission check — the workflow still functions for you as a user, but it's a workaround, not a fix. A few applications (Loan Request, Top Up Fellowship, Recruitment Adhoc Contractual, Indent Cum Sanction Sheet) don't have this gap at all — every role the workflow expects genuinely has the correct access.

### 2. "Put Back for correction" doesn't always work

Several applications (Reimbursement, Advance Settlement, Fund Sanction — partially, for non-Permanent-Employee applicants) have a "send back for correction" option that looks available in the status label but has no way to route the corrected document back into the approval chain — once sent back, it's effectively stuck, and needs manual/backend intervention to move forward again.

Others (Temporary Advance, most of the procurement chain, Rate Contract, Recruitment Adhoc Contractual, Top Up Fellowship, Selection Committee Report for Adhoc — but not Contractual — positions) have a genuinely, fully working Put Back system, sometimes going all the way back to Draft.

**Project Staff Details has no correction path of any kind** — once submitted, it can only go forward to Approved.

Check each application's own "Workflow States Explained" section above for the specific answer for that form — don't assume a "Put Back"-labeled action always works the same way everywhere in this system.

### 3. Some "totals" and "auto-calculations" you'd expect to happen automatically don't

Most notably, **TA DA Settlement's** claimed-amount totals must be calculated by hand despite the form having the right fields — an automatic calculation was designed and exists elsewhere in the system's history, but was never actually connected to that specific form in the version currently running.

By contrast, several other forms genuinely do calculate totals correctly and automatically: Temporary Advance's amount-in-words, Advance Settlement's running total, Direct Purchase and Indent General Form's item-row totals, Rate Contract's grand total and amount-in-words, Disbursal of Consultancy's 70/30 personal/institute split, Top Up Fellowship's per-student hours × rate, and Fund Sanction's total-from-budget-breakup. Where an application's totals genuinely auto-calculate, this manual says so explicitly in that section; where you must calculate by hand, this manual flags it with an explicit Important note.

### 4. Approving a document doesn't always mean the money moves immediately

For several financial applications (notably Reimbursement, and the wider Fund Received/Deposit Slip chain), "Approved" status and the actual recording of the amount against your project's budget are two genuinely separate steps under the hood — a "commit" (a promise/reservation of funds) and a "payment" (money actually paid out) are tracked as two different kinds of record (see [AccountHeadPayment](#34-accountheadpayment--payments-)). This is usually invisible and happens automatically as a background follow-up, but if you ever notice an approved claim that doesn't seem to be reflected in your project's spending yet, it's worth asking your R&D office to confirm the second step happened, rather than assuming Approved alone means the money has definitely moved.

### 5. Some documents reach "Approved" without ever becoming a true "submitted" record

Frappe (the underlying system this ERP is built on) has its own internal concept of a document being "submitted" — a stronger, more protected state than just having a status label of "Approved." Several applications in this manual (notably Reimbursement, Project Staff Details, and parts of the procurement chain's auto-generated documents) never actually reach that stronger, protected "submitted" state, even once their visible status says Approved. Practically, this means such an "Approved" document can, in principle, still be edited or even deleted by certain roles in a way a genuinely "submitted" document normally couldn't be. Other applications (Temporary Advance, Fund Sanction, Advance Settlement's underlying doctype in some cases, Recruitment Adhoc Contractual, Top Up Fellowship) do reach this stronger protected state once truly finished. This manual notes the distinction explicitly wherever it matters for a given application.

### 6. Rupee thresholds that genuinely are enforced by the system

Not just printed guidance — these are real, code-verified numbers that actually change what happens next:

| Threshold | What it triggers | Applies to |
|---|---|---|
| ₹1,000 (per item) | A quotation is expected as part of the settlement declaration | Advance Settlement |
| ₹25,000 / student / month | Hard cap — cannot be exceeded | Top Up Fellowship |
| ₹30,000 | Routes to Dean instead of Associate Dean | Temporary Advance, Disbursal of Consultancy, TA DA Settlement |
| ₹1,00,000 | Maximum claim size (printed guidance, not system-blocked) | Reimbursement |
| ₹1,00,000 | Routes to Dean instead of Associate Dean | Indent Cum Sanction Sheet, Rate Contract |
| ₹2,00,000 | Requires a Purchase Committee of ≥3 members | Direct Purchase |
| ₹2,00,000 | Triggers automatic Director escalation after Dean approval | Disbursal of Honorarium |
| ₹3,00,000 | Triggers automatic Director escalation (Consumable/Contingency/Other) | Direct Purchase, Indent General Form, Indent Cum Sanction Sheet |
| ₹10,00,000 | Triggers automatic Director escalation (Equipment) | Indent General Form, Indent Cum Sanction Sheet |

### 7. No application in this system enforces a turnaround-time deadline

None of the applications covered in this manual have a built-in "must be actioned within N days" rule — approval speed depends entirely on your reviewers, and the system does not send automatic reminders or escalate a request just because it's been sitting for a while. **Assumption:** if your organization has informal expectations (for example, "approvals should happen within a week"), that's a matter of department practice and individual diligence, not something this ERP system tracks, times, or reminds anyone about. If a request seems to be taking unusually long, the only reliable path is to follow up directly with whoever's queue it's currently sitting in.

### 8. Automated email notifications are rare in this system

Across all ~45 applications covered in this manual, genuinely working automatic email notifications exist in only a small number of places — most notably, Temporary Advance's "please Acknowledge this request filed on your behalf" email. For almost everything else — every approval stage on almost every other form — there is **no automatic email**, and you should not expect one. The reliable way to know whether a request needs your attention is to check the relevant application list directly, not to wait for an email that, on most forms, will never come.

---

# Worked End-to-End Scenarios

Individual application sections above explain each form on its own, but real project work usually chains several of these applications together. The scenarios below walk through some of the most common real sequences from start to finish, cross-referencing the specific sections above for detail at each step.

## Scenario A — The Full Life of a Research Grant's Money

**Step 1 — The grant is sanctioned.** Once your institute receives formal word that a funding agency has approved a research grant, someone files a [Fund Sanction](#31-fund-sanction-), recording the sanction letter number, date, and the year-wise budget breakdown. This goes through **staff, RnD → Head of Section → Dean** for internal approval, reaching **Sanction Approved**.

**Step 2 — The money actually arrives.** Some weeks or months later, when the funding agency's payment actually lands in the institute's bank account, someone files a [Fund Received](#32-fund-received-) — critically, referencing the **exact Fund Sanction record name** from Step 1, not the sanction letter number. This goes to **RnD Miscellaneous staff**, who forward it — at which point it's handed off to the **external Accounts Portal system** for independent review.

**Step 3 — The external system responds.** Once the Accounts Portal approves (a process happening outside this ERP, on its own timeline), your Fund Received record automatically advances. RnD Miscellaneous staff then supply deposit-slip details and trigger **Generate Deposit Slip**, which creates a linked [Deposit Slip](#33-deposit-slip-family-) record of the appropriate type (most likely a Research Deposit Slip, for a research grant).

**Step 4 — Final internal sign-off.** The **Head of Section** gives final approval on the Fund Received — which, as a side effect, is also supposed to automatically finish and submit the linked Deposit Slip. **RnD Accounts** then performs a final Verify, closing the loop.

**Step 5 — The money is now available for the project to spend.** From here, project staff can begin filing [Reimbursement](#11-reimbursement-), [Temporary Advance](#12-temporary-advance-), [Direct Purchase](#41-direct-purchase-), and similar applications against the project's Budget Heads, now that the underlying funds have been formally recorded as received.

**What can go wrong along the way, per this manual's own findings:** a typo in the Sanction Ref No. at Step 2 silently breaks the sync to the Accounts Portal (see the Important note in [§3.2](#32-fund-received-)); the Deposit Slip at Step 3 can be silently skipped if the details supplied look too sparse; and the auto-finish step at Step 4 can fail due to a known permission gap. None of these failures produce a loud, obvious error — this is exactly why this manual repeatedly advises confirming each step with your R&D office rather than assuming a green "Approved" label means everything downstream also worked.

## Scenario B — A New Project Staff Member, From Posting to First Paycheck

**Step 1 — Post the position.** A PI needing to hire a Junior Research Fellow files a [Recruitment Adhoc Contractual](#51-recruitment-adhoc-contractual-) posting — appointment type, project details, funds available, interview logistics, the posts being filled, and a Selection Committee. This goes through **Head → staff, RnD → Head of Section → Associate Dean → Dean**.

**Step 2 — Interview and record the outcome.** After interviews are held, the committee files a [Selection Committee Report](#52-selection-committee-report-), linked back to the posting from Step 1, listing candidates and outcomes. For a Contractual position specifically, this must also pass through a **Director sign-off** step before the Dean's final approval — a one-way step with no correction path once triggered. Once Approved, the system automatically pulls a full profile for the recommended candidate.

**Step 3 — Onboard the selected candidate.** Staff file a [Project Staff Details](#53-project-staff-details-joining-form-) joining form for the recommended candidate, tied back to their selection record — personal details, employment terms, tenure, and required uploads. This goes through **staff, RnD → Head of Section → Associate Dean**, with **no correction path** once submitted. Once Approved, the system automatically creates the person's ERP login account and calculates their initial leave balances.

**Step 4 — The new staff member starts filing their own claims.** From here, the newly onboarded person can log in with their new account and begin filing their own Reimbursement, Temporary Advance, Travel, and other applications against the project, using the employee category assigned to them during onboarding — which, as covered throughout Parts 1, 2, and 6 of this manual, silently determines how every one of their future requests gets routed for approval.

## Scenario C — A Large Equipment Purchase, From Indent to Delivery

**Step 1 — Decide the purchase route.** For a piece of equipment covered under an existing rate agreement, use [Rate Contract](#61-rate-contract-). For something needing competitive quotes, use [Indent General Form](#42-indent-general-form-). For a purchase from one specific manufacturer, a repair, or a standardized/compatible item, use [Indent Cum Sanction Sheet](#43-indent-cum-sanction-sheet-) with the appropriate indent type. For something you can simply buy directly without any of the above, use [Direct Purchase](#41-direct-purchase-).

**Step 2 — Go through the approval chain.** Whichever route you chose, your request works its way through a category- and amount-based approval chain — for larger amounts, this automatically escalates through the Head of Section, an Associate Dean or Dean split at a real rupee threshold, and, for genuinely large purchases, an automatic Director escalation, exactly as detailed in each application's own section above.

**Step 3 — The paperwork chain generates itself.** Once approved, the system automatically generates the follow-on documents needed to actually complete the purchase — for Direct Purchase, this is a P_11 Form, then a sanction_sheet, then a dp_po (the actual Purchase Order); for ICSS, it's an ICSS_PO. You do not need to trigger any of this yourself, though — as this manual notes repeatedly — the intermediate documents' own on-screen status tracking is not always reliable, so keep checking your original request record for the authoritative status.

**Step 4 — The item is delivered, and the process closes out.** For ICSS specifically, the record moves through Pending PO Generation → PO Generated → PO Delivered as the final confirmation steps.

---

# Complete Reference: Every Workflow State Used in This System

Because this manual covers ~45 applications, each with its own set of status labels, this consolidated table lists every distinct status label referenced anywhere above, grouped by what it generally means, so you can look one up quickly without hunting through each application's own section.

| Status label pattern | What it generally means |
|---|---|
| **Draft** | Freely editable; not yet sent anywhere. |
| **Pending [Role] Approval** (e.g. Pending Staff Approval, Pending HoS Approval, Pending Dean Approval) | Sitting with that specific role/person; not editable by you; nothing further for you to do until they act. |
| **Pending Applicant Acknowledgment** | Specific to Temporary Advance filed on someone else's behalf — sitting with the actual beneficiary, who must personally review/edit and Acknowledge. |
| **Pending PI Approval / Pending Mentor Approval** | Sitting with your PI or Mentor, depending on your employee category — used on Reimbursement, Advance Settlement, Temporary Advance, Travel, Rate Contract, and others. |
| **Needs Correction (PE/IR/PS)** | Sent back for a fix — genuinely resubmittable on some forms (Fund Sanction, for Permanent Employee applicants), a dead end on others (Reimbursement, Advance Settlement) — always check the specific application's section. |
| **PENDING_APPROVAL** (all capitals) | Specific to Fund Received — means the record has been handed off to the external Accounts Portal system, not a person in this ERP. |
| **Pending Misc. Staff Approval / Pending Misc. Staff Approval(Deposit Slip Pending)** | Specific to Fund Received — with RnD Miscellaneous staff. |
| **Pending PO Generation / PO Generated / PO Delivered** | Specific to Indent Cum Sanction Sheet — the post-approval procurement fulfillment stages. |
| **POGenerated** | Specific to Direct Purchase — the final status once the automatic paperwork chain has produced a Purchase Order. |
| **Pending @ Staff (Deposit Loan)** | Specific to Loan Request — approved in principle, awaiting confirmation the loan money was actually disbursed. |
| **PendIng Fund Submission** | Specific to Fund Sanction, reached via the Dean's "Add Fund" action — a dead end with no further step defined (note the unusual capital "I," a quirk in the system's own configuration, not something you need to correct). |
| **Approved** | The internal approval process has finished successfully. As covered throughout this manual, this does not always mean money has moved or every downstream automatic step has completed — check the specific application's Important notes. |
| **Sanction Approved** | Specific to Fund Sanction — its version of Approved, which also triggers the sync to the external accounts system. |
| **Approved – Appointment Order Generation** | Specific to Selection Committee Report — a further stage after Approved where staff can generate the formal appointment order. |
| **Rejected** | Stopped; on most forms, final. |
| **Pending Director Approval** | An escalation stage for very large procurement, or Contractual-type recruitment — reachable automatically past certain rupee thresholds, or manually flagged by a Dean; often has no correction path once triggered. |
| **Fund Received** (as a status, not the application name) | Specific to the Fund Received application's own final stage — confusingly shares its name with the application itself. |

---

# Application Comparison Chart

| I need to... | Use this | Not this |
|---|---|---|
| Get money back for something I already bought | **Reimbursement** | Temporary Advance |
| Get money before I spend it | **Temporary Advance** | Reimbursement |
| Account for how I spent a Temporary Advance | **Advance Settlement** | Reimbursement |
| Borrow money against project funds | **Loan Request** | Temporary Advance |
| Get approval to travel for work | **Travel** | TA DA Settlement |
| Claim my travel allowance after a trip | **TA DA Settlement** | Travel |
| Pay a guest lecturer / invigilator | **Disbursal of Honorarium** | Disbursement of Honorarium (retired) |
| Pay a consultant from PDF funds | **Disbursal of Consultancy** | Disbursal of Honorarium |
| Record that funding was approved | **Fund Sanction** | Fund Received |
| Record that money actually arrived | **Fund Received** | Fund Sanction |
| Buy something directly, no tender | **Direct Purchase** | Indent General Form |
| Buy something via open tender/quotation | **Indent General Form** | Direct Purchase |
| Buy from one specific manufacturer only | **Indent Cum Sanction Sheet** (Proprietary type) | Direct Purchase |
| Repair or replace a broken item | **Indent Cum Sanction Sheet** (Repair/Replacement type) | — |
| Buy an item under an existing Rate Contract | **Rate Contract** | Direct Purchase |
| Draft the text for a quotation notice | **NIQ** | Indent General Form |
| Arrange annual maintenance for equipment | **AMC** (via ICSS) | — |
| Post a job opening for project staff | **Recruitment Adhoc Contractual** | Selection Committee Report |
| Record interview results | **Selection Committee Report** | Recruitment Adhoc Contractual |
| Onboard a selected candidate | **Project Staff Details** | Selection Committee Report |
| Top up a student's stipend | **Top Up Fellowship** | Disbursal of Honorarium |
| Hand off my approvals while I'm away | **User Delegation** | — |

---

# Quick Reference: Every Application's Approval Chain At A Glance

This table consolidates the first and final approver for every active application covered in this manual, along with whether a genuine, working correction ("Put Back") path exists — pulling together, in one place, the answer this manual gives individually in each application's own "The Approval Process" and "Workflow States Explained" sections.

| Application | First Approval Stop | Final Approver | Amount-Based Escalation? | Correction Path Genuinely Works? |
|---|---|---|---|---|
| Reimbursement | staff, RnD (or Mentor first, for Independent Researchers) | staff, RnD | No | ❌ No |
| Temporary Advance | PI / Mentor / staff, RnD (by category) | Associate Dean or Dean | Yes — ₹30,000 | ✅ Yes |
| Advance Settlement | staff, RnD (or Mentor first) | staff, RnD | No | ❌ No |
| Loan Request | staff, RnD | Dean, RnD, then staff (Deposit Loan) | No | ✅ Yes |
| Disbursal of Honorarium | staff, RnD | Dean (+ Director if escalated) | Yes — ₹2,00,000 | Partially (backend-routed) |
| Disbursal of Consultancy | staff, RnD | Associate Dean or Dean | Yes — ₹30,000 | Partially (backend-routed) |
| Travel | Varies by category | Dean | No | ✅ Yes, extensively |
| TA DA Settlement | Varies by category | Associate Dean or Dean | Yes — ₹30,000 | ✅ Yes |
| Fund Sanction | staff, RnD | Dean, RnD | No | Partially (Permanent Employee applicants only) |
| Fund Received | RnD Miscellaneous staff, then external Accounts Portal | RnD Accounts | No | No Reject exists — Put Back only |
| Direct Purchase | Varies by category | Dean (+ Director if escalated) | Yes — ₹2,00,000 / ₹3,00,000 | ✅ Yes |
| Indent General Form | staff, RnD | Dean (+ Director if escalated) | Yes — ₹3,00,000 / ₹10,00,000 | ✅ Yes |
| Indent Cum Sanction Sheet | Varies by category | Associate Dean or Dean (+ Director if escalated) | Yes — ₹1,00,000, plus Director thresholds | ✅ Yes, until PO generated |
| Recruitment Adhoc Contractual | Head (named individual) | Dean | No | ✅ Yes, at every stage |
| Selection Committee Report | staff, RnD | Dean (or Director, for Contractual) | No (but Adhoc vs. Contractual changes the path) | Partially (no Put Back once Director stage triggered) |
| Project Staff Details | staff, RnD | Associate Dean | No | ❌ No — none at all |
| Rate Contract | Varies by category | Associate Dean or Dean | Yes — ₹1,00,000 | ✅ Yes, extensively |
| Top Up Fellowship | Head or PI (by category) | Dean | No (but a hard ₹25,000/student/month cap) | ✅ Yes, via a custom system |

---

# Glossary

| Term | Meaning |
|---|---|
| **Draft** | The starting, freely-editable state of any application before you submit it. |
| **Submit** | The action that sends your Draft into the approval chain. |
| **Workflow State** | The current stage a document is at in its approval chain (e.g. "Pending Staff Approval"). |
| **Put Back** | An approver sending a document back to an earlier stage (or all the way to Draft) so you can fix something. |
| **Forward** | Another common label for moving a document to the next stage — functionally similar to Submit/Approve depending on where it appears. |
| **Account Head / Budget Head** | The specific budget category an expense or income is charged against within your project. |
| **PI** | Principal Investigator — the lead researcher on a project. |
| **BMR** | Bank Money Receipt — the reference number recorded once money is actually deposited/disbursed. |
| **IDF / DPF / SWF** | Institute Development Fund / Development and Provident Fund / Staff Welfare Fund — internal fund categories money can be drawn from or distributed into. |
| **ECS** | Electronic Clearing Service — a bank transfer/collection mechanism referenced on several finance forms. |
| **GST / IGST / CGST / SGST** | Goods and Services Tax and its component splits (Integrated/Central/State) — calculated automatically on several finance forms depending on the type of transaction. |
| **TDS** | Tax Deducted at Source — a tax withholding that applies to certain kinds of payment (e.g. to employees/consultants) but not others (e.g. to students), as noted specifically on the Disbursal of Consultancy form. |
| **Commit vs. Payment** | A "commit" reserves/promises funds against a budget head; a "payment" records that the money was actually paid out. These are tracked as two separate steps in this system. |
| **Deposit Slip** | The internal record used to formally credit incoming project money against the right budget heads, generated automatically once Fund Received is verified. |
| **Purchase Committee** | A group of at least three staff members required to review and recommend a purchase above certain value thresholds. |
| **OEM** | Original Equipment Manufacturer — relevant to Proprietary Purchase, where you certify you're buying from the actual manufacturer (or their certified representative), not a reseller. |
| **Employee Category** | A classification on your user profile (Permanent Employee, Project Staff, Independent Researcher, Inspired Faculty, Principal Investigator) that silently determines how many financial and HR forms route your request for approval. |
| **Delegation** | A self-service handoff of visibility/edit/approval rights over your own applications to a colleague, for a chosen time window — see [User Delegation](#71-user-delegation-). |

---

# Best Practices Across This Entire System

Pulling together the individual "Quick Tips" from every application section above, a handful of habits will serve you well no matter which application you're using:

**Before you start any application:** Confirm your own employee category is set correctly in your user profile — it silently determines your approval routing on the great majority of forms in this manual (Temporary Advance, Advance Settlement, Travel, TA DA Settlement, Rate Contract, Top Up Fellowship, and more), and getting it wrong upstream causes confusing downstream routing problems that are hard to diagnose after the fact.

**While filling in any form:** Save your work as a Draft frequently rather than trying to complete a long form in one sitting, since browser sessions can time out and unsaved work is lost. Where a form has bank-detail fields, always type them yourself and double-check them, since — as this manual notes repeatedly — very few applications reliably auto-fill this information from any central source. Where a form has an attachment requirement, attach the specific document to the specific row/field it belongs to, rather than bundling everything into one generic upload, since several applications (Reimbursement, Fund Received's transaction table) expect a one-to-one match between an item/row and its supporting document.

**Before you submit:** Review every field once more, since — as covered throughout Part 1 through Part 6 — editing after submission is blocked on almost every application, and a genuinely working correction path exists on fewer than half of the applications covered in this manual. If you're not sure whether your specific form supports resubmission after correction, assume it doesn't, and get it right the first time.

**After you submit:** Don't wait for an email — as covered in [Cross-Cutting System Note #8](#cross-cutting-system-notes), automatic notifications are the exception, not the rule, in this system. Check the relevant application list directly for status updates. If your request seems to be taking an unusually long time, follow up directly with whoever's queue it's sitting in (use the [Roles Glossary](#roles-glossary) and each application's "The Approval Process" table to work out who that is) rather than assuming the system will remind them.

**When something looks wrong:** Distinguish between a genuine data problem (you made an error, or something's missing) and a known system quirk documented in this manual (a display glitch, a permission gap, a broken correction path). This manual has tried to flag every confirmed instance of the latter explicitly with an "Important" callout, precisely so you don't waste time troubleshooting something that isn't actually your fault. If you're ever unsure which category a problem falls into, your R&D office or System Manager is the right first call.

---

# Contact & Support

*(Assumption: add your organization's actual support contacts here — department help desks, IT support, and R&D office contact details were not available from the system configuration reviewed for this manual.)*

| Issue | Suggested Contact |
|---|---|
| Questions about a specific field or form | Your Department/R&D office |
| An approver says they can't see your pending request | Your System Manager / IT administrator |
| A rejected or stuck application with no "Put Back"/resubmit option | Your R&D office directly (may need manual intervention) |
| An application listed here says "Not Available" but you need it | Your R&D office, for the current manual/alternative process |
| General technical problems (login, errors, page not loading) | IT Help Desk |
| A financial claim shows "Approved" but you haven't seen the money reflected against your project | Your R&D office / finance team, to confirm the separate "commit"/"payment" follow-up step has completed |
| A Fund Received shows "Approved" but you can't find its linked Deposit Slip | Your R&D office, to check and finish that step manually if needed |
| You suspect a duplicate record, mismatched data, or something that looks like a system bug rather than a process question | Your System Manager, with as much detail (record name, what you expected vs. what happened) as you can provide |
| You need an application this manual marks "Not Available" | Your R&D office, for the current manual/alternative process while that application remains unbuilt |
| This manual itself seems out of date compared to what you're seeing on screen | Whoever maintains this manual in your organization — systems like this one do get updated over time, and this document should be periodically re-verified against the live configuration |

---

*This manual was compiled from the live configuration of the ERP system itself (forms, approval rules, and permission records) rather than written from policy documents, so it reflects what the system actually does today — including its rough edges. As the system is improved, sections of this manual (particularly the "Important" and "Not Available" notes) should be revisited and updated.*
