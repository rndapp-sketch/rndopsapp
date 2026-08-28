"""
Frappe API layer for Chatwoot user-to-user messaging.
Chatwoot is the single source of truth — no chat data is stored in Frappe DB.
Only contact_id is cached on the Frappe User record.
"""

import time
import requests
import frappe
from frappe import _
from rndopsapp.config import CHATWOOT_BASE_URL

ACCOUNT_ID = 2
INBOX_ID = 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_token():
    token = frappe.conf.get("chatwoot_api_token")
    if not token:
        frappe.throw(_("Chatwoot API token not configured in site_config.json (key: chatwoot_api_token)"))
    return token


def _headers():
    return {
        "api_access_token": _get_token(),
        "Content-Type": "application/json",
    }


def _api(method, path, max_retries=5, **kwargs):
    url = f"{CHATWOOT_BASE_URL}/api/v1/accounts/{ACCOUNT_ID}{path}"
    kwargs.setdefault("timeout", 15)
    delay = 2
    for attempt in range(max_retries):
        resp = getattr(requests, method)(url, headers=_headers(), **kwargs)
        if resp.status_code == 429:
            wait = delay * (2 ** attempt)
            frappe.logger().warning(f"Chatwoot 429 on {url}, retrying in {wait}s (attempt {attempt + 1})")
            time.sleep(wait)
            continue
        if not resp.ok:
            frappe.log_error(
                f"Chatwoot {method.upper()} {url} → {resp.status_code}: {resp.text}",
                "Chatwoot API Error",
            )
            frappe.throw(_(f"Chatwoot API error {resp.status_code}: {resp.text}"))
        return resp.json()
    frappe.throw(_(f"Chatwoot API rate limit exceeded after {max_retries} retries: {url}"))


# ---------------------------------------------------------------------------
# Chatwoot contact helpers
# ---------------------------------------------------------------------------

def _search_contact_by_email(email):
    """Return Chatwoot contact dict or None."""
    data = _api("get", "/contacts/search", params={"q": email, "include_contacts": True})
    payload = data.get("payload")
    if isinstance(payload, list):
        contacts = payload
    elif isinstance(payload, dict):
        contacts = payload.get("contacts", [])
    else:
        contacts = []
    for contact in contacts:
        if contact.get("email") == email:
            return contact
    return None


def _create_contact(email, name):
    data = _api("post", "/contacts", json={"email": email, "name": name, "identifier": email})
    payload = data.get("payload", {})
    if isinstance(payload, dict) and "contact" in payload:
        return payload["contact"]
    return payload or data


def _attach_contact_to_inbox(contact_id):
    _api(
        "post",
        f"/contacts/{contact_id}/contact_inboxes",
        json={"inbox_id": INBOX_ID, "source_id": str(contact_id)},
    )


def _has_contact_id_column():
    return frappe.db.has_column("User", "chatwoot_contact_id")


def _get_cached_contact_id(email):
    if not _has_contact_id_column():
        return None
    return frappe.db.get_value("User", email, "chatwoot_contact_id")


def _set_cached_contact_id(email, contact_id):
    if not _has_contact_id_column():
        return
    frappe.db.set_value("User", email, "chatwoot_contact_id", contact_id, update_modified=False)


def find_or_create_contact(email):
    """
    Find Chatwoot contact by email or create one.
    Caches contact_id on the Frappe User if the custom field exists.
    Returns contact_id (int).
    """
    cached_id = _get_cached_contact_id(email)
    if cached_id:
        return int(cached_id)

    user_doc = frappe.get_doc("User", email)
    name = user_doc.full_name or email

    contact = _search_contact_by_email(email)
    if not contact:
        contact = _create_contact(email, name)

    contact_id = contact.get("id")
    if not contact_id:
        frappe.throw(_("Failed to obtain Chatwoot contact ID for " + email))

    _set_cached_contact_id(email, contact_id)
    return int(contact_id)


def attach_inbox(contact_id):
    _attach_contact_to_inbox(contact_id)


# ---------------------------------------------------------------------------
# Chatwoot conversation helpers
# ---------------------------------------------------------------------------

def _get_contact_conversations(contact_id):
    data = _api("get", f"/contacts/{contact_id}/conversations")
    return data.get("payload", [])


def _find_conversation_between(sender_contact_id, receiver_contact_id):
    """
    Find an existing conversation that involves both contacts on INBOX_ID.
    Chatwoot conversations are per-inbox, so we look for a conversation where
    the contact matches either participant and the meta contains both sides.
    Strategy: fetch sender's conversations, look for one whose meta participant
    matches the receiver.
    """
    for conv in _get_contact_conversations(sender_contact_id):
        if conv.get("inbox_id") != INBOX_ID:
            continue
        meta = conv.get("meta", {})
        sender_meta = meta.get("sender", {})
        # Chatwoot stores the contact who initiated — check both directions
        if sender_meta.get("id") in (sender_contact_id, receiver_contact_id):
            # Also verify the other party appears in assignee or participants
            # For simplicity, match conversations where additional_attributes
            # carry our custom tag, or fall back to label matching.
            labels = conv.get("labels", [])
            tag = _conversation_label(sender_contact_id, receiver_contact_id)
            if tag in labels:
                return conv
    return None


def _conversation_label(contact_a, contact_b):
    ids = sorted([contact_a, contact_b])
    return f"p2p-{ids[0]}-{ids[1]}"


def find_or_create_conversation(sender_contact_id, receiver_contact_id):
    """Return conversation_id (int) for the pair, creating one if needed."""
    existing = _find_conversation_between(sender_contact_id, receiver_contact_id)
    if existing:
        return existing["id"]

    label = _conversation_label(sender_contact_id, receiver_contact_id)
    data = _api(
        "post",
        "/conversations",
        json={
            "inbox_id": INBOX_ID,
            "contact_id": sender_contact_id,
            "additional_attributes": {
                "receiver_contact_id": receiver_contact_id,
            },
            "labels": [label],
        },
    )
    conv = data.get("data") or data
    return conv["id"]


def _chatwoot_send_message(conversation_id, content, sender_name):
    return _api(
        "post",
        f"/conversations/{conversation_id}/messages",
        json={
            "content": content,
            "message_type": "outgoing",
            "private": False,
            "content_attributes": {"sender_name": sender_name},
        },
    )


def fetch_messages(conversation_id):
    data = _api("get", f"/conversations/{conversation_id}/messages")
    return data.get("payload", data)


# ---------------------------------------------------------------------------
# Public Frappe API endpoints
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_message(receiver_email, message):
    """
    Send a message from the current logged-in user to receiver_email.
    """
    sender_email = frappe.session.user
    if sender_email == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)
    if sender_email == receiver_email:
        frappe.throw(_("Cannot send a message to yourself"))

    if not frappe.db.exists("User", receiver_email):
        frappe.throw(_(f"User '{receiver_email}' not found"))

    sender_contact_id = find_or_create_contact(sender_email)
    receiver_contact_id = find_or_create_contact(receiver_email)

    attach_inbox(sender_contact_id)
    attach_inbox(receiver_contact_id)

    conversation_id = find_or_create_conversation(sender_contact_id, receiver_contact_id)

    sender_doc = frappe.get_doc("User", sender_email)
    sender_name = sender_doc.full_name or sender_email

    _chatwoot_send_message(conversation_id, message, sender_name)

    return {"success": True, "conversation_id": conversation_id}


@frappe.whitelist()
def get_conversation(other_user_email):
    """
    Return the conversation_id between the current user and other_user_email.
    Creates the conversation if it does not exist.
    """
    current_email = frappe.session.user
    if current_email == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)

    if not frappe.db.exists("User", other_user_email):
        frappe.throw(_(f"User '{other_user_email}' not found"))

    my_contact_id = find_or_create_contact(current_email)
    other_contact_id = find_or_create_contact(other_user_email)

    conversation_id = find_or_create_conversation(my_contact_id, other_contact_id)
    return {"conversation_id": conversation_id}


@frappe.whitelist()
def get_messages(conversation_id):
    """
    Fetch full message history for a conversation from Chatwoot.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)

    conversation_id = int(conversation_id)
    messages = fetch_messages(conversation_id)
    return {"messages": messages}



@frappe.whitelist()
def list_conversations():
    """
    List all Chatwoot conversations for the current logged-in user.
    """
    current_email = frappe.session.user
    if current_email == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)

    contact_id = find_or_create_contact(current_email)
    conversations = _get_contact_conversations(contact_id)

    result = []
    for conv in conversations:
        if conv.get("inbox_id") != INBOX_ID:
            continue
        result.append({
            "id": conv["id"],
            "status": conv.get("status"),
            "created_at": conv.get("created_at"),
            "labels": conv.get("labels", []),
            "last_activity_at": conv.get("last_activity_at"),
            "meta": conv.get("meta", {}),
        })

    return {"conversations": result}


@frappe.whitelist()
def migrate_users_to_chatwoot():
    """
    One-time migration: sync all active Frappe users to Chatwoot contacts.
    Safe to re-run — skips users who already have a cached contact_id.
    Requires System Manager role.
    """
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Managers can run this migration"), frappe.PermissionError)

    users = frappe.get_all(
        "User",
        filters={"enabled": 1, "user_type": "System User"},
        fields=["name", "full_name", "email"],
    )

    results = {"synced": [], "skipped": [], "failed": []}
    total = len(users)
    print(f"\n[Chatwoot Migration] Starting — {total} users to process\n")

    for i, user in enumerate(users, 1):
        email = user["name"]

        if email in ("Guest", "Administrator"):
            print(f"  [{i}/{total}] SKIP  {email} (system user)")
            results["skipped"].append({"email": email, "reason": "system user"})
            continue

        cached_id = _get_cached_contact_id(email)
        if cached_id:
            print(f"  [{i}/{total}] SKIP  {email} (already mapped → contact {cached_id})")
            results["skipped"].append({"email": email, "reason": "already mapped", "contact_id": cached_id})
            continue

        try:
            contact_id = find_or_create_contact(email)
            attach_inbox(contact_id)
            results["synced"].append({"email": email, "contact_id": contact_id})
            print(f"  [{i}/{total}] OK    {email} → contact {contact_id}")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"migrate_users_to_chatwoot: {email}")
            results["failed"].append({"email": email, "error": str(e)})
            print(f"  [{i}/{total}] FAIL  {email} — {e}")

        time.sleep(0.3)

    summary = {
        "total": total,
        "synced": len(results["synced"]),
        "skipped": len(results["skipped"]),
        "failed": len(results["failed"]),
    }
    results["summary"] = summary
    print(f"\n[Chatwoot Migration] Done — synced: {summary['synced']}  skipped: {summary['skipped']}  failed: {summary['failed']}\n")
    return results


@frappe.whitelist()
def list_user_contacts(search=None, page=1):
    """
    List contacts directly from Chatwoot.
    Optionally filter by name/email with `search`.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)

    page = max(1, frappe.utils.cint(page))

    if search:
        data = _api("get", "/contacts/search", params={"q": search, "page": page, "include_contacts": True})
        payload = data.get("payload")
        if isinstance(payload, list):
            contacts_raw = payload
            meta = {}
        elif isinstance(payload, dict):
            contacts_raw = payload.get("contacts", [])
            meta = payload.get("meta", {})
        else:
            contacts_raw, meta = [], {}
    else:
        data = _api("get", "/contacts", params={"page": page})
        contacts_raw = data.get("payload", [])
        meta = data.get("meta", {})

    contacts = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "email": c.get("email"),
            "phone_number": c.get("phone_number"),
            "avatar_url": c.get("avatar_url"),
            "created_at": c.get("created_at"),
            "last_activity_at": c.get("last_activity_at"),
        }
        for c in contacts_raw
    ]

    return {"contacts": contacts, "meta": meta}
