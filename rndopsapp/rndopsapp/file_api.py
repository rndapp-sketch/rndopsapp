# Copyright (c) 2026, rndops and contributors
# For license information, please see license.txt

"""
Authenticated read route for files stored in MinIO.

The browser calls this instead of talking to MinIO, so the MinIO host/port and bucket
are never exposed and every read goes through a Frappe permission check:

    GET /api/method/rndopsapp.rndopsapp.file_api.get_file?file_url=<object key>[&download=1]

`file_url` is whatever an Attach field stores - "/Project_Registration/<docname>/<folder>/<file>",
a "/prod-rnd-files/..." path, or a full MinIO URL. Only the object key is used; a URL's host
is never fetched.

Access: any logged-in user may read any file. There is no per-document permission check;
the only gate is a valid session (the endpoint is not allow_guest) plus path sanitising,
so a key can never escape the bucket's object namespace or reach the local filesystem.
"""

import mimetypes
from urllib.parse import urlparse

import frappe
from frappe import _

# Rendered in the browser when not downloading. Anything else (HTML endorsements, SVG, ...)
# is always sent as an attachment: served inline from this origin it would run with the
# viewer's session.
INLINE_CONTENT_TYPES = {
	"application/pdf",
	"image/png",
	"image/jpeg",
	"image/gif",
	"image/webp",
	"text/plain",
}

def _bucket_names():
	names = {"prod-rnd-files"}
	configured = frappe.conf.get("minio_bucket")
	if configured:
		names.add(configured)
	return names


def _normalise_key(file_url):
	"""The MinIO object key for a stored Attach value, or throw on anything unsafe."""
	raw = str(file_url or "").strip()
	if not raw:
		frappe.throw(_("file_url is required"), frappe.ValidationError)

	if raw.lower().startswith(("http://", "https://")):
		raw = urlparse(raw).path

	parts = raw.strip("/").split("/")
	# "/prod-rnd-files/<key>" and "http://host:9000/prod-rnd-files/<key>" carry the bucket.
	if parts and parts[0] in _bucket_names():
		parts = parts[1:]

	if not parts or any(p in ("", ".", "..") for p in parts) or "\\" in raw or "\x00" in raw:
		frappe.throw(_("Invalid file path"), frappe.ValidationError)

	return "/".join(parts)


@frappe.whitelist()
def get_file(file_url=None, download=0):
	"""
	Stream one MinIO file to the logged-in caller.

	Args:
		file_url: the stored Attach value / object key (see module docstring).
		download: truthy to force a download; otherwise PDFs and images render inline.
	"""
	key = _normalise_key(file_url)

	from rndopsapp.minio import get_rnd_file_service

	result = get_rnd_file_service().get_file(key)
	if not result.get("status"):
		frappe.throw(_("File not found"), frappe.DoesNotExistError)

	filename = key.rsplit("/", 1)[-1]
	# Frappe's raw responder runs the name through unicode-escape decoding.
	safe_filename = filename.replace("\\", "").replace('"', "").replace("\n", "").replace("\r", "")
	content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

	inline = content_type in INLINE_CONTENT_TYPES and not frappe.utils.cint(download)

	frappe.response["filename"] = safe_filename
	frappe.response["filecontent"] = result["data"]["content"]
	frappe.response["content_type"] = content_type
	frappe.response["type"] = "download"
	frappe.response["display_content_as"] = "inline" if inline else "attachment"
