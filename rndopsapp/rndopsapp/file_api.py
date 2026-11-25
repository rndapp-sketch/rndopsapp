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


def _find_in_document_folder(service, key):
	"""Another object key with the same file name under "<doctype>/<docname>/", or None."""
	parts = key.split("/")
	if len(parts) < 3:
		return None
	prefix = "/".join(parts[:2]) + "/"
	try:
		matches = sorted(
			o.object_name
			for o in service.storage.list_prefix(prefix)
			if o.object_name.rsplit("/", 1)[-1] == parts[-1]
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "file_api: folder fallback failed")
		return None
	return matches[0] if matches else None


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

	service = get_rnd_file_service()
	result = service.get_file(key)
	if not result.get("status"):
		# The folder in a stored/guessed path can be wrong (e.g. ".../attachments/x.pdf"
		# while the object sits in ".../proposal/x.pdf"). Look for the same file name
		# elsewhere under the same document folder before giving up.
		alt_key = _find_in_document_folder(service, key)
		if alt_key:
			key = alt_key
			result = service.get_file(key)
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


def _safe_segment(value, label):
	"""One object-key path segment (a doctype, document name or folder), or throw."""
	raw = str(value or "").strip().strip("/")
	if not raw or "/" in raw or "\\" in raw or "\x00" in raw or raw in (".", ".."):
		frappe.throw(_("Invalid {0}").format(label), frappe.ValidationError)
	return raw


@frappe.whitelist()
def list_files(docname, doctype="Project Registration", folder=None):
	"""
	List the MinIO files stored for a document, so the caller does not have to know
	the file names or folders in advance.

	    GET /api/method/rndopsapp.rndopsapp.file_api.list_files?docname=<project>[&folder=fund_received]

	Files are stored as "<Doctype_with_underscores>/<docname>/<folder>/<file>". Project and
	Fund Received attachments both sit under the Project Registration folder of the project
	(Fund Received uses the folders "fund_received" / "fundreceived").

	Args:
		docname: the document name, e.g. the project's Project Registration name.
		doctype: defaults to "Project Registration".
		folder: optional - only list this folder (e.g. "fund_received").

	Returns {"docname", "doctype", "total", "folders": {folder: count}, "files": [...]}.
	Each file has `file_url`, which can be passed straight to get_file. Same access rule as
	get_file: any logged-in user.
	"""
	doctype_dir = _safe_segment(doctype, "doctype").replace(" ", "_")
	doc_dir = _safe_segment(docname, "docname")
	prefix = f"{doctype_dir}/{doc_dir}/"
	if folder:
		prefix += _safe_segment(folder, "folder").lower() + "/"

	from rndopsapp.minio import get_rnd_file_service

	try:
		objects = get_rnd_file_service().storage.list_prefix(prefix)
	except Exception:
		frappe.log_error(title="file_api: list_files failed", message=frappe.get_traceback())
		frappe.throw(_("Could not list files. Please try again later."))

	files = []
	folders = {}
	for obj in objects:
		key = obj.object_name
		if key.endswith("/"):
			continue
		rest = key[len(f"{doctype_dir}/{doc_dir}/"):].split("/")
		file_name = rest[-1]
		folder_name = "/".join(rest[:-1])
		folders[folder_name] = folders.get(folder_name, 0) + 1
		files.append({
			"file_name": file_name,
			"folder": folder_name,
			"file_url": "/" + key,
			"size": obj.size,
			"content_type": mimetypes.guess_type(file_name)[0] or "application/octet-stream",
			"last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
		})

	files.sort(key=lambda f: (f["folder"], f["file_name"].lower()))
	return {
		"docname": doc_dir,
		"doctype": doctype,
		"total": len(files),
		"folders": folders,
		"files": files,
	}
