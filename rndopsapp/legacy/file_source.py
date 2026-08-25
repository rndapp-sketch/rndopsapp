"""Reads legacy project Excel files from whichever store holds them.

The Proman and R&D OPS file trees live on two separate Tomcat servers in
production, each serving its own `/usr/tomcat_1/webapps/rnd/Upload/RNDIITG/PROJECT`
over HTTP. In development both trees are just directories on a local disk.
Which backend is used, and where each system's root is, comes entirely from
`site_config.json` -- no code changes between environments.

    "legacy_file_backend": "http",
    "legacy_file_sources": {
        "Proman":  {"base_url": "http://<proman-ip>:8080/rnd/Upload/RNDIITG/PROJECT"},
        "R&D OPS": {"base_url": "http://<rndops-ip>:8080/rnd/Upload/RNDIITG/PROJECT"}
    }

A source may also override the backend per system (`"backend": "local"`),
which is what lets one system be migrated to HTTP ahead of the other.
"""

import os
import posixpath
from urllib.parse import quote

import frappe
import requests

CONNECT_TIMEOUT = 5
DEFAULT_READ_TIMEOUT = 15
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 64 * 1024


class LegacyFileError(Exception):
	pass


def safe_rel_path(rel_path):
	"""Normalise a stored relative path, rejecting anything that could escape the root."""
	if not rel_path:
		raise LegacyFileError("Empty legacy file path")

	candidate = str(rel_path).replace("\\", "/").strip()
	if "\x00" in candidate or candidate.startswith("/") or ":" in candidate:
		raise LegacyFileError(f"Invalid legacy file path: {rel_path}")

	normalized = posixpath.normpath(candidate)
	if normalized in (".", "..") or normalized.startswith(("../", "/")):
		raise LegacyFileError(f"Invalid legacy file path: {rel_path}")

	return normalized


def _source_config(source_system):
	sources = frappe.conf.get("legacy_file_sources") or {}
	config = sources.get(source_system)
	if not config:
		raise LegacyFileError(
			f"No legacy file source configured for '{source_system}'. "
			f"Add it under 'legacy_file_sources' in site_config.json."
		)
	return config


def _read_local(root, rel_path):
	root_real = os.path.realpath(root)
	full = os.path.realpath(os.path.join(root_real, rel_path))

	# realpath resolves symlinks, so this also catches a link pointing outside the tree.
	if full != root_real and not full.startswith(root_real + os.sep):
		raise LegacyFileError("Resolved legacy file path escapes the configured root")

	if not os.path.isfile(full):
		raise FileNotFoundError(rel_path)

	with open(full, "rb") as handle:
		return handle.read()


def _read_http(base_url, rel_path, read_timeout, max_bytes):
	# Department folders contain spaces and '&' -- both must be percent-encoded.
	url = base_url.rstrip("/") + "/" + quote(rel_path, safe="/")
	response = requests.get(url, timeout=(CONNECT_TIMEOUT, read_timeout), stream=True)

	if response.status_code == 404:
		raise FileNotFoundError(rel_path)
	response.raise_for_status()

	chunks = []
	total = 0
	for chunk in response.iter_content(CHUNK_SIZE):
		total += len(chunk)
		if total > max_bytes:
			raise LegacyFileError(
				f"Legacy file '{rel_path}' exceeds the {max_bytes} byte limit"
			)
		chunks.append(chunk)

	return b"".join(chunks)


def read_legacy_file(source_system, rel_path):
	"""Return the raw bytes of one legacy file. Raises FileNotFoundError if absent."""
	rel_path = safe_rel_path(rel_path)
	config = _source_config(source_system)
	backend = config.get("backend") or frappe.conf.get("legacy_file_backend") or "http"

	if backend == "local":
		root = config.get("root")
		if not root:
			raise LegacyFileError(f"Legacy file source '{source_system}' has no 'root' configured")
		return _read_local(root, rel_path)

	if backend == "http":
		base_url = config.get("base_url")
		if not base_url:
			raise LegacyFileError(f"Legacy file source '{source_system}' has no 'base_url' configured")
		return _read_http(
			base_url,
			rel_path,
			frappe.conf.get("legacy_file_timeout") or DEFAULT_READ_TIMEOUT,
			frappe.conf.get("legacy_file_max_bytes") or DEFAULT_MAX_BYTES,
		)

	raise LegacyFileError(f"Unknown legacy file backend '{backend}'")
