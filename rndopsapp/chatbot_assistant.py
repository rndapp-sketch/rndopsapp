"""
Simple, non-streaming chat with a locally hosted Ollama model.

Isolated on purpose: this module never writes to the database. It only
(a) reads live workflow_state/status for a document the user names in their
message, through Frappe's normal permission checks, and (b) hands that plus
the conversation to the LLM. It must never be given a path to submit,
approve, reject, or otherwise mutate any document.

Non-streaming by design: the site currently runs on Werkzeug's dev server
(`bench serve`), which is unreliable for long-lived streaming/chunked HTTP
responses (confirmed: intermittent net::ERR_INCOMPLETE_CHUNKED_ENCODING).
A plain request/response has a known Content-Length and sidesteps that
class of bug entirely — the trade-off is no incremental token rendering,
the full reply arrives in one shot.

Model: Ollama, running locally (default model: gemma4:e2b — override via
site_config.json key "chatbot_ollama_model").
"""

import json
import os
import re
import threading
import time

import frappe
from frappe import _
import requests
from rndopsapp.config import OLLAMA_BASE_URL, MATTERMOST_POSTS_URL


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_OLLAMA_URL = OLLAMA_BASE_URL
DEFAULT_OLLAMA_MODEL = "gemma4:e2b"

# Same Mattermost server/token already used elsewhere in this app
# (see rndopsapp/kafka/utils.py) — reused here to log every question asked
# to Pragati into the "Issues_ProRnd UI" channel for visibility/debugging.
_MM_URL = MATTERMOST_POSTS_URL
_MM_TOKEN = "Bearer fmjih41b4iymicttnuhinsqime"
_MM_PRAGATI_CHANNEL = "3xn7xtobgjg4zk3fbdtsbip6we"  # "Issues_ProRnd UI"

# DocTypes Pragati is allowed to look up live status for, when a user
# mentions one by name/ID. Sourced from PROJECT_REGISTRATION_LINKS_TO_APPLICATION.md
# — every application module linked to Project Registration. Not all of
# these have a workflow_state field or an active Workflow record; the
# lookup below skips those gracefully rather than erroring.
TRACKED_DOCTYPES = [
    "AccountHeadPayment",
    "Advance Settlement",
    "AMC",
    "Deposit slip",
    "Deposit Slip Project Credit",
    "Direct Purchase",
    "Disbursal of Consultancy",
    "Disbursal of Honorarium",
    "Disbursement of Honorarium",
    "dp_po",
    "E Non Routine Deposit Slip",
    "Endorsement Data",
    "Extension Of Tenure Of Appointment",
    "Fund Received",
    "Fund Sanction",
    "ICSS_PO",
    "Indent Cum Sanction Sheet",
    "Indent General Form",
    "Loan Request",
    "myProjects",
    "NIQ",
    "P_11 Form",
    "payments",
    "Project Extension",
    "Project Registration",
    "Project Staff Details",
    "proprietary_purchase",
    "Rate Contract",
    "Recruitment Adhoc Contractual",
    "Reimbursement",
    "repair_replacement",
    "Research Consultancy Deposit Slip",
    "Research Deposit Slip",
    "sanction_sheet",
    "Selection Committee Report",
    "standerdized_purchase",
    "T Testing Deposit Slip",
    "TA DA Settlement",
    "Temporary Advance",
    "Top Up Fellowship",
    "Travel",
    "UC Request",
    "User Delegation",
]

SYSTEM_PROMPT = """Your name is Pragati. You are a helpful assistant for RnD Ops staff.

Rules you must always follow:
1. You are Pragati. Always speak in the first person as Pragati. Never reveal, confirm, or \
speculate about what underlying model, engine, provider, or technology powers you — if asked \
"what model/LLM are you" or similar, simply say you're Pragati and redirect to how you can help.
2. You are read-only. You cannot and must never claim to submit, forward, approve, reject, or \
edit anything on the user's behalf. If asked to perform an action, explain which button they need \
to click themselves and who else needs to act, if you know from the live status given to you.
3. Keep answers short and in plain, non-technical language — the audience is office staff, not \
developers.
4. If a "Live status" section is given below, use it as ground truth for that specific document \
— don't guess or invent workflow steps, statuses, or roles beyond what it tells you. If no Live \
status is given but the user is clearly asking about a specific document/form, say you couldn't \
find that record rather than guessing. Never invent an additional named section of your own (an \
"Activity Log", a table of past actions, user names, or timestamps) that isn't explicitly present \
in what's given to you below — if it isn't there, you don't have it.
5. When asked "what's next" / "what happens now" about a document, use its "possible_next_steps" \
list (action, moves_to_state, roles_who_can_do_it) to give a concrete answer — name the action and \
who does it, don't just say "wait for approval". If "possible_next_steps" is empty, say this looks \
like the final stage rather than guessing what comes after.
6. If a "Reference material" section is given below, it's excerpted from this project's own \
documentation — prefer it over general knowledge for "how does X work" / "what is Y" questions. \
Never mention file names, source labels, or that you were "given documentation" — just answer \
naturally, as if you simply know this about the system. If nothing relevant is given and you \
don't already know the answer, say so rather than guessing.
7. If "Live status" includes a "linked_documents" list, that is the complete, real set of \
application documents currently linked to that project — nothing else exists. When the user asks \
about a specific document type (e.g. "direct purchase", "reimbursement"), find the matching entry \
there by doctype and report its actual workflow_state. If no entry matches that doctype, tell the \
user no such document has been linked to this project yet — never invent a status for it.
8. If "Live status" includes a "recent_activity" list, that is the real, permission-checked \
activity timeline for that document (each entry has type, label, user, timestamp, and content when \
relevant) — use only those entries to answer "who did what / activity / history / log" questions, \
in the order given. If "recent_activity" is absent and the user asks for activity/history, say you \
don't have that information rather than fabricating names, dates, or actions.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_user_or_throw():
    user = frappe.session.user
    if user == "Guest":
        frappe.throw(_("Please log in to use the assistant."), frappe.AuthenticationError)
    return user


def get_request_status(doctype, docname, user):
    """Read-only: current workflow state + who needs to act next for one
    document. Permission-checked against the requesting user — never
    returns data the user isn't allowed to see."""
    if doctype not in TRACKED_DOCTYPES:
        return None
    if not frappe.db.exists(doctype, docname):
        return None
    if not frappe.has_permission(doctype, doc=docname, user=user):
        return None

    doc = frappe.get_doc(doctype, docname)
    state = doc.get("workflow_state") or None

    # possible_next_steps: every action available from the current state —
    # what happens if it's taken (next_state) and who is allowed to take it.
    # This is what lets Pragati answer "what's next", not just "who's blocking it".
    possible_next_steps = []
    all_states = []
    if state:
        workflow_name = frappe.db.get_value(
            "Workflow", {"document_type": doctype, "is_active": 1}, "name"
        )
        if workflow_name:
            workflow = frappe.get_doc("Workflow", workflow_name)
            all_states = [s.state for s in workflow.states]
            for t in workflow.transitions:
                if t.state != state:
                    continue
                allowed = t.get("allowed") or []
                if isinstance(allowed, str):
                    allowed = [allowed]
                possible_next_steps.append({
                    "action": t.action,
                    "moves_to_state": t.next_state,
                    "roles_who_can_do_it": allowed,
                })

    waiting_on_roles = list(dict.fromkeys(
        role for step in possible_next_steps for role in step["roles_who_can_do_it"]
    ))

    return {
        "doctype": doctype,
        "docname": docname,
        "workflow_state": state,
        "docstatus": doc.docstatus,
        "waiting_on_roles": waiting_on_roles,
        "possible_next_steps": possible_next_steps,
        "all_workflow_states_in_order": all_states,
        "last_modified": str(doc.modified),
    }


def _detect_doctype_hints(message):
    """DocTypes explicitly named in the message (case-insensitive substring
    match), to narrow down which doctype an ID likely belongs to."""
    lower = message.lower()
    return [dt for dt in TRACKED_DOCTYPES if dt.lower() in lower]


def _extract_id_candidates(message):
    """Best-effort extraction of document-ID-looking tokens from free text:
    quoted strings first (most reliable, since staff often paste IDs in
    quotes), then any alphanumeric token that mixes letters and digits
    (e.g. 2026050401MeiTy000502), then long pure-numeric tokens (e.g. plain
    Direct Purchase autonames like 2026061522001141, which have no letters
    at all — the mixed-token pattern above would never match these)."""
    candidates = []
    candidates += re.findall(r'"([^"]+)"', message)
    candidates += re.findall(r"'([^']+)'", message)
    candidates += re.findall(r"\b(?=\w*\d)(?=\w*[A-Za-z])[A-Za-z0-9_-]{6,}\b", message)
    # 10+ digits to avoid false positives on small numbers in casual conversation.
    candidates += re.findall(r"\b\d{10,}\b", message)

    seen = set()
    out = []
    for c in candidates:
        c = c.strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


_ACTIVITY_KEYWORDS = (
    "activity", "log", "history", "track", "timeline",
    "who did", "action taken", "actions taken", "what happened",
)


def _wants_activity(message):
    """Whether the user is actually asking for a history/activity trail, as
    opposed to a plain status check — gates the extra _get_activity lookup
    below so a normal "what's the status" question doesn't pay for it."""
    lower = message.lower()
    return any(kw in lower for kw in _ACTIVITY_KEYWORDS)


def _recent_activity(doctype, docname, user, limit=6):
    """Real, permission-checked activity timeline for one document (comments,
    workflow changes, assignments, edits), via the same
    rndopsapp.rndopsapp.api.get_document_activity used elsewhere in the app.
    Returns [] rather than raising — this is a bonus enrichment, and the
    caller already confirmed read access to the document itself, but the
    activity call re-checks permission on its own and could still fail for
    other reasons (e.g. missing Version tracking)."""
    try:
        from rndopsapp.rndopsapp.api import get_document_activity
        entries = get_document_activity(doctype, docname) or []
    except Exception:
        return []
    return entries[:limit]


def _project_registration_status(identifier, user, include_activity=False):
    """Resolve `identifier` to a Project Registration exactly the way the PR
    Lookup page does (rndopsapp.rndopsapp.api.lookup_project_direct): match
    against the document name first, then against project_no — a plain Data
    field that never matches the doctype-exists check TRACKED_DOCTYPES relies
    on. On a hit, enrich the status with project_no/title and the real
    workflow_state of every application document linked to this project (via
    the same PR Link Graph the /pr_link_graph page uses), so follow-up
    questions about one specific application type can be answered from actual
    linked documents instead of guessed. Returns None if nothing matches or
    the user can't see the PR."""
    if frappe.db.exists("Project Registration", identifier):
        pr_name = identifier
    else:
        pr_name = frappe.db.get_value("Project Registration", {"project_no": identifier}, "name")
    if not pr_name:
        return None

    status = get_request_status("Project Registration", pr_name, user)
    if not status:
        return None

    try:
        from rndopsapp.rndopsapp.doctype.project_registration.project_registration import (
            get_pr_link_graph,
        )
        graph = get_pr_link_graph(pr_name)
    except Exception:
        graph = None

    if graph and graph.get("status") == "success":
        status["project_no"] = graph["pr"].get("project_no")
        status["project_title"] = graph["pr"].get("project_title")
        status["linked_documents"] = [
            {"doctype": n["doctype"], "name": n["name"], "workflow_state": n["workflow_state"] or None}
            for n in graph["nodes"]
            if n["type"] != "root" and frappe.has_permission(n["doctype"], doc=n["name"], user=user)
        ]

    if include_activity:
        activity = _recent_activity("Project Registration", pr_name, user)
        if activity:
            status["recent_activity"] = activity

    return status


def _find_live_status(message, user, want_activity=False):
    """Best-effort: if the message seems to name a specific document, find
    it (scoped to doctypes the user can actually see) and return its live
    status. Returns None if nothing matches — this is a bonus, not required
    for the chat to function."""
    candidates = _extract_id_candidates(message)
    if not candidates:
        return None

    # Prefer resolving to a Project Registration first — most staff questions
    # ("what is my project registration status", "Project No 2627R-...") are
    # really about the PR, identified by its human-readable project_no rather
    # than its autoname.
    for candidate in candidates:
        try:
            status = _project_registration_status(candidate, user, include_activity=want_activity)
        except Exception:
            status = None
        if status:
            return status

    search_doctypes = _detect_doctype_hints(message) or TRACKED_DOCTYPES

    for docname in candidates:
        for doctype in search_doctypes:
            try:
                status = get_request_status(doctype, docname, user)
            except Exception:
                continue
            if status:
                if want_activity:
                    activity = _recent_activity(doctype, docname, user)
                    if activity:
                        status["recent_activity"] = activity
                return status
    return None


# ---------------------------------------------------------------------------
# Knowledge base — every .md file in this app, auto-discovered, chunked,
# and retrieved with simple keyword matching (no extra dependencies/vector
# DB — good enough for "how does X module work" style questions).
# ---------------------------------------------------------------------------

_KB_CACHE = {"loaded_at": 0, "chunks": []}
_KB_CACHE_TTL_SECONDS = 300


# Extra files outside the app tree to fold into the knowledge base, on top
# of everything _discover_md_files() finds under apps/rndopsapp/. Paths are
# built from the bench root so this stays portable across environments.
EXTRA_KNOWLEDGE_FILES = [
    os.path.join(frappe.utils.get_bench_path(), "ERP_COMPLETE_APPLICATIONS_MANUAL.md"),
]


def _discover_md_files():
    """Every .md file anywhere under this app (apps/rndopsapp/), not just
    the top-level ones — includes per-doctype implementation docs too — plus
    any EXTRA_KNOWLEDGE_FILES that live outside the app tree."""
    app_root = os.path.dirname(frappe.get_app_path("rndopsapp"))
    paths = []
    for dirpath, _dirnames, filenames in os.walk(app_root):
        for fname in filenames:
            if fname.lower().endswith(".md"):
                paths.append(os.path.join(dirpath, fname))

    for extra_path in EXTRA_KNOWLEDGE_FILES:
        if os.path.exists(extra_path) and extra_path not in paths:
            paths.append(extra_path)

    return paths


# Cap on a single chunk's size. Some manuals have very long "## Application"
# sections (Overview through Quick Tips, 15K+ chars) — a single retrieval
# slot that big can dominate the context budget or exceed a small Ollama
# num_ctx window. Cut long chunks down further, on "### " subsection
# boundaries where possible so we don't cut off mid-explanation, and prefer
# whichever piece actually matched the query.
_MAX_CHUNK_CHARS = 3000


def _split_oversized_chunk(source, text):
    if len(text) <= _MAX_CHUNK_CHARS:
        return [{"source": source, "text": text}]

    pieces = re.split(r"\n(?=### )", text)
    if len(pieces) == 1:
        # No subsections to split on — hard-cut with a note, better than a
        # single enormous chunk that crowds out everything else.
        return [{"source": source, "text": text[:_MAX_CHUNK_CHARS] + "\n[...truncated...]"}]

    out = []
    heading = pieces[0].split("\n", 1)[0]  # the "## ..." title, kept as context on each sub-piece
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if not piece.startswith("##") and heading:
            piece = f"{heading}\n{piece}"
        out.append({"source": source, "text": piece[:_MAX_CHUNK_CHARS]})
    return out


def _read_knowledge_files():
    bench_path = frappe.utils.get_bench_path()
    app_root = os.path.dirname(frappe.get_app_path("rndopsapp"))
    chunks = []
    for file_path in _discover_md_files():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        # Label relative to whichever root actually contains this file —
        # app-tree docs relative to the app, extra files (e.g. the bench-root
        # manual) relative to the bench, so labels read cleanly either way.
        is_in_app_tree = os.path.commonpath([file_path, app_root]) == app_root
        label = os.path.relpath(file_path, app_root if is_in_app_tree else bench_path)

        # Split on top-level "## " headings only (not "###" and deeper) so
        # each chunk keeps its subsections (Overview, Approval Process, FAQ,
        # etc.) attached to the section title they belong to, instead of
        # scattering them as disconnected fragments with no context.
        sections = re.split(r"\n(?=## )", content)
        for section in sections:
            section = section.strip()
            if section:
                chunks.extend(_split_oversized_chunk(label, section))

    return chunks


def _get_knowledge_chunks():
    now = time.time()
    if now - _KB_CACHE["loaded_at"] > _KB_CACHE_TTL_SECONDS or not _KB_CACHE["chunks"]:
        _KB_CACHE["chunks"] = _read_knowledge_files()
        _KB_CACHE["loaded_at"] = now
    return _KB_CACHE["chunks"]


def _score_chunk(query_words, chunk_text):
    chunk_words = set(re.findall(r"[a-z0-9]+", chunk_text.lower()))
    return len(query_words & chunk_words)


def _retrieve_knowledge(query, top_k=4, max_per_source=2):
    """Best-matching chunks by keyword overlap, capped per source file so one
    long doc that happens to share a lot of vocabulary can't crowd out every
    slot — a couple of chunks from 2-3 different docs is more useful than
    four chunks from a single tangentially-related one."""
    query_words = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not query_words:
        return []

    scored = []
    for chunk in _get_knowledge_chunks():
        score = _score_chunk(query_words, chunk["text"])
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)

    picked = []
    per_source_count = {}
    for score, chunk in scored:
        source = chunk["source"]
        if per_source_count.get(source, 0) >= max_per_source:
            continue
        picked.append(chunk)
        per_source_count[source] = per_source_count.get(source, 0) + 1
        if len(picked) >= top_k:
            break
    return picked


def _mm_post_async(text):
    """Fire-and-forget Mattermost post. Never blocks the chat response and
    never raises, even if Mattermost is unreachable — this is visibility/
    logging only, not a critical path."""
    def _post():
        try:
            requests.post(
                _MM_URL,
                json={"channel_id": _MM_PRAGATI_CHANNEL, "message": text},
                headers={"Authorization": _MM_TOKEN, "Content-Type": "application/json"},
                timeout=(2, 3),
            )
        except Exception:
            pass

    threading.Thread(target=_post, daemon=True).start()


def _ollama_config():
    base_url = frappe.conf.get("chatbot_ollama_url") or DEFAULT_OLLAMA_URL
    model = frappe.conf.get("chatbot_ollama_model") or DEFAULT_OLLAMA_MODEL
    think = frappe.conf.get("chatbot_ollama_think")
    think = False if think is None else bool(think)
    return base_url, model, think


def _safe_log_error(title):
    """frappe.log_error can itself raise in unusual contexts — never let a
    logging failure mask or replace the real error being reported."""
    try:
        frappe.log_error(frappe.get_traceback(), title)
    except Exception:
        pass


def _call_ollama(messages):
    """Single blocking call to Ollama — no streaming. Returns the full reply
    text (and thinking text, if the model/config produced any)."""
    base_url, model, think = _ollama_config()
    resp = requests.post(
        f"{base_url}/api/chat",
        json={"model": model, "messages": messages, "stream": False, "think": think},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    message = data.get("message", {}) or {}
    return {
        "content": (message.get("content") or "").strip(),
        "thinking": (message.get("thinking") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@frappe.whitelist()
def chat(message, history=None):
    """
    Simple, non-streaming chat with the local Ollama model.

    message  - the staff member's question, plain text
    history  - optional list of {"role": "user"|"assistant", "content": str}
               from earlier turns in the same conversation, for follow-ups

    Returns a plain JSON object: {"reply": "...", "thinking": "..."}.
    """
    user = _current_user_or_throw()
    _mm_post_async(f"**Pragati question** from `{user}`:\n{message}")

    if isinstance(history, str):
        try:
            history = json.loads(history)
        except Exception:
            history = []
    history = history or []

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        want_activity = _wants_activity(message)
        live_status = _find_live_status(message, user, want_activity=want_activity)
        if not live_status and history:
            # Follow-up question (e.g. "what's next?") with no ID of its own —
            # re-check the earlier turns in this conversation for a document
            # that was already named, so status stays fresh/live rather than
            # relying on whatever the previous reply happened to say in text.
            # want_activity still reflects the CURRENT message's intent, not
            # the prior text used only to re-find which document is meant.
            prior_user_text = " ".join(
                h.get("content", "") for h in history if h.get("role") == "user"
            )
            if prior_user_text:
                live_status = _find_live_status(prior_user_text, user, want_activity=want_activity)
    except Exception:
        live_status = None
    if live_status:
        messages.append({
            "role": "system",
            "content": f"Live status for the document mentioned:\n{json.dumps(live_status)}",
        })

    try:
        matched_chunks = _retrieve_knowledge(message)
    except Exception:
        matched_chunks = []
    if matched_chunks:
        ref_text = "\n\n".join(f"[{c['source']}]\n{c['text']}" for c in matched_chunks)
        messages.append({"role": "system", "content": f"Reference material:\n{ref_text}"})

    messages.extend(history)
    messages.append({"role": "user", "content": message})

    try:
        result = _call_ollama(messages)
    except Exception as e:
        _safe_log_error("chatbot_assistant: chat failed")
        frappe.throw(
            _(
                f"Pragati couldn't reach the model — {e}. "
                "Check that Ollama is running and reachable from this server, "
                "and that the configured model name matches what `ollama list` shows."
            )
        )

    if result["content"]:
        _mm_post_async(f"**Pragati reply** to `{user}`:\n{result['content']}")

    result["used_sources"] = [c["source"] for c in matched_chunks]
    return result
