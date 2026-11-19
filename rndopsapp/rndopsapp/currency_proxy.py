"""
Currency exchange-rate API proxy.

Forwards GET requests from this Frappe site to the self-hosted currency-rate server
(Docker, default http://172.16.131.206:7070) and returns the upstream response unchanged —
status code, body and content type. Every query parameter is passed through, so any
current or future parameter (base, quotes, date, from, to, providers,
group, expand, scope, ...) works without a code change.

Endpoint (any logged-in user):

    GET /api/method/rndopsapp.rndopsapp.currency_proxy.proxy?path=/v2/rates&base=USD&quotes=INR

Only the documented v2 routes are proxied (see ALLOWED_PATHS); anything else
is rejected with a validation error (HTTP 417), so this can't be used to reach other URLs on the upstream host.

Configuration: set `currency_api_url` in the site config to point somewhere other than the
default (CURRENCY_API_BASE_URL below), e.g. when the container is on another host.

From other Python code use `currency_get(path, params)` — it returns parsed JSON and
raises on errors. See docs/currency/currency_proxy.md.
"""

import json
import re

import frappe
import requests
from frappe import _
from werkzeug.wrappers import Response


# Self-hosted currency-rate server. Override per site with `currency_api_url` in the site config.
CURRENCY_API_BASE_URL = "http://172.16.131.206:7070"

CONNECT_TIMEOUT = 3  # seconds
READ_TIMEOUT = 30  # seconds
MAX_RESPONSE_BYTES = 50 * 1024 * 1024  # refuse to buffer more than 50 MB from upstream

# Optional output-format suffix the API accepts on a path, e.g. /v2/rates.csv
_FORMAT = r"(?:\.(?:json|csv|ndjson))?"
# Currency code / provider or dataset key (dataset keys contain a dot, e.g. "nbp.b").
_SEG = r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}"

# The nine v2 routes of the currency API, plus its OpenAPI document.
ALLOWED_PATHS = [
	re.compile(rf"^/v2/rates{_FORMAT}$"),
	re.compile(rf"^/v2/rate/{_SEG}/{_SEG}{_FORMAT}$"),
	re.compile(rf"^/v2/coverage{_FORMAT}$"),
	re.compile(rf"^/v2/currencies{_FORMAT}$"),
	re.compile(rf"^/v2/currency/{_SEG}{_FORMAT}$"),
	re.compile(rf"^/v2/providers{_FORMAT}$"),
	re.compile(rf"^/v2/providers/{_SEG}{_FORMAT}$"),
	re.compile(rf"^/v2/providers/{_SEG}/rates{_FORMAT}$"),
	re.compile(rf"^/v2/providers/{_SEG}/rate/{_SEG}/{_SEG}{_FORMAT}$"),
	re.compile(r"^/v2/openapi\.json$"),
]

# Accept values forwarded to upstream; anything else falls back to JSON.
_FORWARDED_ACCEPT = ("application/json", "application/x-ndjson", "text/csv")

# Query keys that belong to Frappe's own request handling, never sent upstream.
_FRAPPE_PARAMS = {"cmd", "path", "_"}

# Upstream response headers worth passing on.
_PASSTHROUGH_HEADERS = ("Retry-After", "Cache-Control", "ETag", "Last-Modified")


def get_base_url():
	return (frappe.conf.get("currency_api_url") or CURRENCY_API_BASE_URL).rstrip("/")


def _normalize_path(path):
	"""Validate `path` against ALLOWED_PATHS and return it normalised ('/v2/...')."""
	path = (path or "").strip()
	if not path:
		frappe.throw(_("`path` is required, e.g. /v2/rates"), frappe.ValidationError)
	if not path.startswith("/"):
		path = "/" + path
	# Guard against traversal / odd encodings before matching.
	if ".." in path or "//" in path or "%" in path or "?" in path or "#" in path:
		frappe.throw(_("Invalid path"), frappe.ValidationError)
	if not any(pattern.match(path) for pattern in ALLOWED_PATHS):
		frappe.throw(_("Path '{0}' is not a currency API route").format(path), frappe.ValidationError)
	return path


def _upstream_error(status, message):
	"""A currency-API-style JSON error body: {"status": ..., "message": ...}."""
	return Response(
		json.dumps({"status": status, "message": message}),
		status=status,
		mimetype="application/json",
	)


def _fetch(path, params, accept=None):
	"""One GET to the currency server. Returns the requests.Response; raises requests errors."""
	return requests.get(
		f"{get_base_url()}{path}",
		params=params,
		headers={"Accept": accept or "application/json"},
		timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
		allow_redirects=False,  # never follow a redirect off the configured host
		stream=True,
	)


def _read_body(upstream):
	"""Read the upstream body, refusing anything beyond MAX_RESPONSE_BYTES."""
	chunks, size = [], 0
	for chunk in upstream.iter_content(chunk_size=65536):
		size += len(chunk)
		if size > MAX_RESPONSE_BYTES:
			raise ValueError("Currency service response too large")
		chunks.append(chunk)
	return b"".join(chunks)


@frappe.whitelist(methods=["GET"])
def proxy(path=None):
	"""
	Proxy a GET request to the currency API and return its response unchanged.

	path   API route, e.g. /v2/rates, /v2/rate/USD/INR, /v2/providers/FBIL/rates
	other  every other query parameter is forwarded as-is (repeated keys included)

	The upstream status code, body and content type are returned as they are, so errors
	(400/404/422/503) reach the caller exactly as the currency server sent them. Send
	`Accept: application/x-ndjson` or `text/csv`, or use the `.csv` path suffix, for those formats.
	"""
	path = _normalize_path(path or frappe.form_dict.get("path"))

	# frappe.request.args holds the raw query string, including repeated keys.
	params = [
		(key, value)
		for key, values in frappe.request.args.lists()
		if key not in _FRAPPE_PARAMS
		for value in values
	]

	accept_header = (frappe.request.headers.get("Accept") or "").lower()
	accept = next((a for a in _FORWARDED_ACCEPT if a in accept_header), None)

	try:
		upstream = _fetch(path, params, accept)
		body = _read_body(upstream)
	except requests.Timeout:
		frappe.log_error(title="Currency Proxy", message=f"Currency service timeout: {path}")
		return _upstream_error(504, "Currency service did not respond in time")
	except requests.RequestException as e:
		frappe.log_error(title="Currency Proxy", message=f"Currency service unreachable: {path}: {e}")
		return _upstream_error(503, "Currency service unavailable")
	except ValueError:
		return _upstream_error(502, "Currency service response too large")
	finally:
		try:
			upstream.close()
		except Exception:
			pass

	response = Response(body, status=upstream.status_code)
	response.headers["Content-Type"] = upstream.headers.get("Content-Type", "application/json")
	for header in _PASSTHROUGH_HEADERS:
		if header in upstream.headers:
			response.headers[header] = upstream.headers[header]
	return response


def currency_get(path, params=None, accept=None):
	"""
	Server-side helper (not whitelisted): GET a currency API route and return parsed JSON.

	    currency_get("/v2/rate/USD/INR")                -> {"date": ..., "rate": ...}
	    currency_get("/v2/rates", {"base": "USD", "quotes": "INR", "from": "2026-11-01"})

	Raises frappe.ValidationError for a bad path, and frappe.ValidationError with the upstream
	message for any non-2xx answer or an unreachable server.
	"""
	path = _normalize_path(path)
	try:
		upstream = _fetch(path, params or {}, accept)
		body = _read_body(upstream)
	except requests.RequestException as e:
		frappe.log_error(title="Currency Proxy", message=f"Currency service unreachable: {path}: {e}")
		frappe.throw(_("Currency service unavailable"), frappe.ValidationError)
	except ValueError:
		frappe.throw(_("Currency service response too large"), frappe.ValidationError)

	if upstream.status_code >= 400:
		try:
			message = json.loads(body).get("message") or body[:200].decode("utf-8", "replace")
		except Exception:
			message = body[:200].decode("utf-8", "replace")
		frappe.throw(
			_("Currency service error {0}: {1}").format(upstream.status_code, message), frappe.ValidationError
		)
	return json.loads(body)
