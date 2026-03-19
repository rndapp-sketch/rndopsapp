import io
import hashlib
import mimetypes
import logging
from datetime import datetime, timedelta
from typing import Optional, Union

import frappe
from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

logger = logging.getLogger("rnd_file_service")


# =====================================================
# STORAGE LAYER
# =====================================================

class ObjectStorageService:
    def __init__(self, endpoint, access_key, secret_key, bucket, secure=False):
        self.bucket = bucket
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def upload(self, object_name: str, data: bytes, content_type=None):
        self.client.put_object(
            self.bucket,
            object_name,
            io.BytesIO(data),
            len(data),
            content_type=content_type
        )

    def get(self, object_name: str) -> Optional[bytes]:
        try:
            res = self.client.get_object(self.bucket, object_name)
            return res.read()
        except S3Error as e:
            if e.code == "NoSuchKey":
                return None
            raise

    def delete(self, object_name: str):
        self.client.remove_object(self.bucket, object_name)

    def list_prefix(self, prefix):
        return list(self.client.list_objects(self.bucket, prefix=prefix, recursive=True))

    def presigned_url(self, object_name: str, expiry: int):
        return self.client.presigned_get_object(
            self.bucket,
            object_name,
            expires=timedelta(seconds=expiry),
        )


# =====================================================
# MAIN SERVICE
# =====================================================

class RNDFileService:

    def __init__(self, storage: ObjectStorageService):
        self.storage = storage

    # -------------------------
    # HELPERS
    # -------------------------

    def _resp(self, status, message, data=None):
        return {"status": status, "message": message, "data": data or {}}

    def _bytes(self, content: Union[str, bytes]) -> bytes:
        if isinstance(content, bytes):
            return content
        if isinstance(content, str):
            return content.encode("utf-8")
        raise TypeError("Content must be str or bytes")

    def _hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _path(self, filename, file_hash, private, doctype=None, docname=None, folder=None):
        """
        Generate clean MinIO file path: {doctype}/{project_id}/{document_type}/{filename}

        Example: Project_Registration/2026031901MeiTy000635/proposal/6c76f7bd_project_proposal.pdf

        Args:
            filename: Original filename
            file_hash: SHA256 hash of file content
            private: Whether file is private (not used in new structure)
            doctype: Document type (e.g., "Project Registration")
            docname: Document name/ID (e.g., "2026031901MeiTy000635")
            folder: Document category (e.g., "proposal", "endorsement", "attachments")
        """
        parts = []

        # Use doctype as the top-level folder (for multi-doctype organization)
        if doctype:
            # Normalize doctype name: replace spaces with underscores, use title case
            normalized_doctype = doctype.replace(" ", "_")
            parts.append(normalized_doctype)

        # Use docname as the project ID (second level)
        if docname:
            parts.append(docname)

        # Use folder as the document type category (third level)
        if folder:
            # Normalize folder name to lowercase for consistency
            document_type = folder.strip("/").lower()
            parts.append(document_type)

        # Add filename with hash prefix to ensure uniqueness
        # Format: {hash[:8]}_{original_filename}
        unique_filename = f"{file_hash[:8]}_{filename}"
        parts.append(unique_filename)

        return "/".join(parts)

    def _parse(self, url):
        return url.strip("/")

    def _mime(self, filename):
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # -------------------------
    # CORE OPERATIONS
    # -------------------------

    def save_file(self, filename, content, is_private=True, doctype=None, docname=None, folder=None):
        try:
            data = self._bytes(content)
            file_hash = self._hash(data)

            # ✅ Deduplication
            existing = frappe.db.get_value("File", {"content_hash": file_hash}, "file_url")
            if existing:
                return self._resp(True, "File already exists", {
                    "file_url": existing,
                    "hash": file_hash
                })

            path = self._path(filename, file_hash, is_private, doctype, docname, folder)
            mime = self._mime(filename)

            # Upload to MinIO
            self.storage.upload(path, data, mime)

            file_url = f"/{path}"

            # Save metadata in Frappe
            doc = frappe.get_doc({
                "doctype": "File",
                "file_name": filename,
                "file_url": file_url,
                "is_private": is_private,
                "attached_to_doctype": doctype,
                "attached_to_name": docname,
                "content_hash": file_hash,
                "file_size": len(data),
                "mime_type": mime,
            })
            doc.insert(ignore_permissions=True)

            return self._resp(True, "File saved", {
                "file_url": file_url,
                "path": path,
                "hash": file_hash
            })

        except Exception as e:
            logger.exception("Save failed")
            return self._resp(False, str(e))

    def get_file(self, file_url):
        try:
            path = self._parse(file_url)
            data = self.storage.get(path)

            if data is None:
                return self._resp(False, "File not found")

            return self._resp(True, "File fetched", {"content": data})

        except Exception as e:
            logger.exception("Fetch failed")
            return self._resp(False, str(e))

    def delete_file(self, file_url):
        try:
            path = self._parse(file_url)

            # delete from storage
            self.storage.delete(path)

            # delete metadata
            file_doc = frappe.get_doc("File", {"file_url": file_url})
            frappe.delete_doc("File", file_doc.name, ignore_permissions=True)

            return self._resp(True, "File deleted")

        except Exception as e:
            logger.exception("Delete failed")
            return self._resp(False, str(e))

    def get_signed_url(self, file_url, expiry=300):
        try:
            url = self.storage.presigned_url(self._parse(file_url), expiry)
            return self._resp(True, "Signed URL generated", {
                "url": url,
                "expires_in": expiry
            })
        except Exception as e:
            logger.exception("Signed URL failed")
            return self._resp(False, str(e))

    # -------------------------
    # BULK DELETE (NEW 🔥)
    # -------------------------

    def delete_by_document(self, doctype, docname, is_private=True):
        try:
            base = "private" if is_private else "public"
            prefix = f"{base}/{doctype}/{docname}/"

            objects = self.storage.list_prefix(prefix)

            for obj in objects:
                self.storage.delete(obj.object_name)

            frappe.db.delete("File", {
                "attached_to_doctype": doctype,
                "attached_to_name": docname
            })

            return self._resp(True, "All files deleted for document")

        except Exception as e:
            logger.exception("Bulk delete failed")
            return self._resp(False, str(e))


# =====================================================
# FACTORY
# =====================================================

def get_rnd_file_service():
    return RNDFileService(
        ObjectStorageService(
            endpoint=frappe.conf.minio_endpoint,
            access_key=frappe.conf.minio_access_key,
            secret_key=frappe.conf.minio_secret_key,
            bucket=frappe.conf.minio_bucket,
            secure=False,
        )
    )