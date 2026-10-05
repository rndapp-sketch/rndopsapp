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

    def _path(self, filename, file_hash, private, doctype=None, docname=None, folder=None, use_hash=False):
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
        if use_hash:
            unique_filename = f"{file_hash[:8]}_{filename}"
        else:
            unique_filename = filename
        parts.append(unique_filename)

        return "/".join(parts)

    def _parse(self, url):
        return url.strip("/")

    def _mime(self, filename):
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # -------------------------
    # CORE OPERATIONS
    # -------------------------

    # ── OJS EDIT START ───────────────────────────────────────────────────────
    # Author      : OJS
    # Date        : 2026-06-01
    # Time        : 15:36 IST
    # Description : save_file is now idempotent on path.
    #               If a tabFile row already exists for the same file_url
    #               (same MinIO path), the object is overwritten in MinIO and
    #               the existing tabFile row is updated — no duplicate is
    #               created.  If no record exists, the path is created in
    #               MinIO and a fresh tabFile row is inserted.
    # ─────────────────────────────────────────────────────────────────────────
    def save_file(self, filename, content, is_private=True, doctype=None, docname=None, folder=None, use_hash=False):
        print(f"\n[MINIO] >>> save_file called")
        print(f"[MINIO]   filename   : {filename}")
        print(f"[MINIO]   doctype    : {doctype}")
        print(f"[MINIO]   docname    : {docname}")
        print(f"[MINIO]   folder     : {folder}")
        print(f"[MINIO]   is_private : {is_private}")
        print(f"[MINIO]   content len: {len(content) if content else 0}")

        try:
            data = self._bytes(content)
            file_hash = self._hash(data)
            print(f"[MINIO]   file_hash  : {file_hash}")

            path = self._path(filename, file_hash, is_private, doctype, docname, folder, use_hash=use_hash)
            mime = self._mime(filename)
            file_url = f"/{path}"
            print(f"[MINIO]   minio path : {path}")
            print(f"[MINIO]   file_url   : {file_url}")
            print(f"[MINIO]   mime type  : {mime}")

            # ── Check whether a tabFile record already exists at this path ──
            existing_name = frappe.db.get_value("File", {"file_url": file_url}, "name")

            # ── Upload (overwrite if already present) ──────────────────────
            # MinIO put_object always overwrites; no pre-creation of "folders"
            # needed — the path is just a key prefix.
            print(f"[MINIO]   {'Overwriting' if existing_name else 'Uploading'} object in MinIO...")
            self.storage.upload(path, data, mime)
            print(f"[MINIO]   MinIO upload SUCCESS")

            now = frappe.utils.now()

            try:
                if existing_name:
                    # ── PATH EXISTS: update the existing tabFile row ───────
                    print(f"[MINIO]   Path already exists (tabFile: {existing_name}). Updating record...")
                    frappe.db.sql("""
                        UPDATE `tabFile`
                        SET
                            file_name     = %(file_name)s,
                            content_hash  = %(content_hash)s,
                            file_size     = %(file_size)s,
                            is_private    = %(is_private)s,
                            modified      = %(modified)s,
                            modified_by   = %(modified_by)s
                        WHERE name = %(name)s
                    """, {
                        "name": existing_name,
                        "file_name": filename,
                        "content_hash": file_hash,
                        "file_size": len(data),
                        "is_private": 1 if is_private else 0,
                        "modified": now,
                        "modified_by": frappe.session.user,
                    })
                    frappe.db.commit()
                    print(f"[MINIO]   tabFile row updated: {existing_name}")
                else:
                    # ── PATH IS NEW: insert a fresh tabFile row ───────────
                    print(f"[MINIO]   Path is new. Inserting tabFile row...")
                    file_doc_name = frappe.generate_hash(length=10)
                    frappe.db.sql("""
                        INSERT INTO `tabFile`
                            (name, file_name, file_url, is_private,
                             attached_to_doctype, attached_to_name,
                             content_hash, file_size,
                             owner, creation, modified, modified_by, docstatus, idx)
                        VALUES
                            (%(name)s, %(file_name)s, %(file_url)s, %(is_private)s,
                             %(attached_to_doctype)s, %(attached_to_name)s,
                             %(content_hash)s, %(file_size)s,
                             %(owner)s, %(creation)s, %(modified)s, %(modified_by)s, 0, 0)
                    """, {
                        "name": file_doc_name,
                        "file_name": filename,
                        "file_url": file_url,
                        "is_private": 1 if is_private else 0,
                        "attached_to_doctype": doctype,
                        "attached_to_name": docname,
                        "content_hash": file_hash,
                        "file_size": len(data),
                        "owner": frappe.session.user,
                        "creation": now,
                        "modified": now,
                        "modified_by": frappe.session.user,
                    })
                    frappe.db.commit()
                    print(f"[MINIO]   tabFile row inserted: {file_doc_name}")

            except Exception as meta_err:
                print(f"[MINIO]   WARNING: Frappe metadata save failed: {meta_err}")
                logger.warning(f"File uploaded to MinIO but Frappe metadata save failed: {meta_err}")

            print(f"[MINIO] <<< save_file SUCCESS: {file_url}\n")
            return self._resp(True, "File saved", {
                "file_url": file_url,
                "path": path,
                "hash": file_hash,
                "existed": bool(existing_name),
            })

        except Exception as e:
            print(f"[MINIO] <<< save_file FAILED: {e}\n")
            logger.exception("Save failed")
            return self._resp(False, str(e))
    # ── OJS EDIT END ─────────────────────────────────────────────────────────

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