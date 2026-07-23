# MinIO File Path Storage — Complete Explanation

## 📊 What Gets Saved Where

### Summary
- **MinIO**: Stores the actual file content
- **Frappe DB**: Stores only the file path (metadata)

---

## 🗂️ File Path Components

### Input Parameters
```python
filename = "project_proposal.pdf"
doctype = "Project Registration"
docname = "2026031901MeiTy000636"
folder = "proposal"
file_hash = "a1b2c3d4e5f67890abcdef..."  # SHA-256
```

### Generated Path
```
Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
```

### Stored in Frappe DB (file_url)
```
/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
```

**Note**: The leading `/` is added in `minio.py` line 161:
```python
file_url = f"/{path}"
```

---

## 📝 Frappe Database Storage

### File Doctype Record

When a file is uploaded, a record is created in the `File` doctype:

```json
{
  "doctype": "File",
  "name": "a1b2c3d4e5f67890abcdef...",
  "file_name": "project_proposal.pdf",
  "file_url": "/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf",
  "is_private": 1,
  "attached_to_doctype": "Project Registration",
  "attached_to_name": "2026031901MeiTy000636",
  "content_hash": "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
  "file_size": 524288,
  "mime_type": "application/pdf"
}
```

### Key Fields Explained

| Field | Value | Purpose |
|-------|-------|---------|
| `file_name` | `project_proposal.pdf` | Original filename (display name) |
| `file_url` | `/Project_Registration/.../a1b2c3d4_project_proposal.pdf` | MinIO object path |
| `attached_to_doctype` | `Project Registration` | Parent doctype |
| `attached_to_name` | `2026031901MeiTy000636` | Parent document ID |
| `is_private` | `1` or `0` | Access control flag |
| `content_hash` | `a1b2c3d4...` (64 chars) | SHA-256 for deduplication |
| `file_size` | `524288` | Size in bytes |
| `mime_type` | `application/pdf` | File content type |

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. FILE UPLOAD REQUEST                                          │
│                                                                  │
│   POST /api/method/save_project_data                            │
│   Body: {                                                        │
│     "upload_proj_prop": {                                        │
│       "file_name": "project_proposal.pdf",                       │
│       "file_data": "data:application/pdf;base64,..."            │
│     }                                                            │
│   }                                                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. DECODE & PROCESS                                              │
│                                                                  │
│   project_registration.py:                                       │
│   - Decode Base64 → bytes                                        │
│   - Get category: get_file_category("upload_proj_prop")         │
│     → "proposal"                                                 │
│   - Call: file_service.save_file(...)                           │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. GENERATE PATH (minio.py)                                      │
│                                                                  │
│   Input:                                                         │
│     filename = "project_proposal.pdf"                            │
│     doctype = "Project Registration"                             │
│     docname = "2026031901MeiTy000636"                            │
│     folder = "proposal"                                          │
│                                                                  │
│   Process:                                                       │
│     hash = SHA256(file_bytes) = "a1b2c3d4..."                    │
│     path = _path(filename, hash, ...)                            │
│                                                                  │
│   Generated Path:                                                │
│     "Project_Registration/2026031901MeiTy000636/                 │
│      proposal/a1b2c3d4_project_proposal.pdf"                     │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. UPLOAD TO MINIO                                               │
│                                                                  │
│   storage.upload(                                                │
│     object_name="Project_Registration/.../a1b2c3d4_proposal.pdf"│
│     data=file_bytes,                                             │
│     content_type="application/pdf"                               │
│   )                                                              │
│                                                                  │
│   MinIO Location:                                                │
│   rnd-files/Project_Registration/2026031901MeiTy000636/         │
│   proposal/a1b2c3d4_project_proposal.pdf                         │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. SAVE METADATA IN FRAPPE                                       │
│                                                                  │
│   file_url = f"/{path}"                                          │
│   → "/Project_Registration/2026031901MeiTy000636/               │
│       proposal/a1b2c3d4_project_proposal.pdf"                    │
│                                                                  │
│   frappe.get_doc({                                               │
│     "doctype": "File",                                           │
│     "file_name": "project_proposal.pdf",                         │
│     "file_url": "/Project_Registration/...",  ← STORED IN DB    │
│     "attached_to_doctype": "Project Registration",               │
│     "attached_to_name": "2026031901MeiTy000636",                 │
│     "content_hash": "a1b2c3d4...",                               │
│     "is_private": 1                                              │
│   }).insert()                                                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. RETURN RESPONSE                                               │
│                                                                  │
│   {                                                              │
│     "status": True,                                              │
│     "message": "File saved",                                     │
│     "data": {                                                    │
│       "file_url": "/Project_Registration/.../a1b2c3d4_file.pdf",│
│       "hash": "a1b2c3d4..."                                      │
│     }                                                            │
│   }                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔍 File Retrieval Flow

### When File is Accessed

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. REQUEST FILE                                                  │
│                                                                  │
│   GET /api/method/get_file?file_url=/Project_Registration/...   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. PARSE FILE_URL (minio.py)                                     │
│                                                                  │
│   file_url = "/Project_Registration/.../a1b2c3d4_file.pdf"      │
│   path = _parse(file_url)                                        │
│   → "Project_Registration/.../a1b2c3d4_file.pdf"                │
│     (removes leading /)                                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. RETRIEVE FROM MINIO                                           │
│                                                                  │
│   data = storage.get(path)                                       │
│   → Downloads file bytes from MinIO                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. RETURN FILE CONTENT                                           │
│                                                                  │
│   Response:                                                      │
│     Content-Type: application/pdf                                │
│     Body: <file bytes>                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔗 Presigned URL Generation

For secure temporary access:

```python
from rndopsapp.minio import get_rnd_file_service

service = get_rnd_file_service()
file_url = "/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_proposal.pdf"

result = service.get_signed_url(file_url, expiry=300)

if result.get("status"):
    download_url = result['data']['url']
    # Returns: http://172.16.135.118:9000/rnd-files/Project_Registration/...?X-Amz-...
    # Valid for 5 minutes (300 seconds)
```

---

## 📊 Database Query Examples

### Get All Files for a Project

```sql
SELECT
    name,
    file_name,
    file_url,
    is_private,
    file_size,
    creation
FROM `tabFile`
WHERE
    attached_to_doctype = 'Project Registration'
    AND attached_to_name = '2026031901MeiTy000636'
ORDER BY creation DESC;
```

### Result:
```
┌─────────────┬───────────────────────┬───────────────────────────────────────┬────────────┬───────────┬─────────────────────┐
│ name        │ file_name             │ file_url                              │ is_private │ file_size │ creation            │
├─────────────┼───────────────────────┼───────────────────────────────────────┼────────────┼───────────┼─────────────────────┤
│ abc123...   │ project_proposal.pdf  │ /Project_Registration/.../proposal... │ 1          │ 524288    │ 2026-03-19 10:30:00 │
│ def456...   │ endorsement.pdf       │ /Project_Registration/.../endorsem... │ 1          │ 102400    │ 2026-03-19 10:25:00 │
│ ghi789...   │ document.csv          │ /Project_Registration/.../attachme... │ 1          │ 8192      │ 2026-03-19 10:20:00 │
└─────────────┴───────────────────────┴───────────────────────────────────────┴────────────┴───────────┴─────────────────────┘
```

### Get Files by Category

```sql
SELECT
    file_name,
    file_url
FROM `tabFile`
WHERE
    attached_to_doctype = 'Project Registration'
    AND file_url LIKE '%/proposal/%'
ORDER BY creation DESC;
```

---

## 🎯 Key Takeaways

### What's Stored in Frappe Database?

✅ **Metadata Only**:
- File name (original)
- File path (MinIO object key with leading `/`)
- File size
- MIME type
- Content hash (SHA-256)
- Attachment info (doctype, docname)
- Privacy flag

❌ **NOT Stored**:
- File content (bytes)
- File is stored in MinIO, not Frappe DB

### File Path Format in Database

```
file_url = "/{doctype}/{document_id}/{category}/{hash[:8]}_{filename}"
```

**Example**:
```
/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
```

### Why Leading `/`?

- **Convention**: Frappe file URLs typically start with `/`
- **Relative Path**: Indicates it's a path within the storage system
- **Consistency**: Matches Frappe's standard file_url format
- **Parsing**: Easy to strip the `/` when accessing MinIO (line 132: `return url.strip("/")`)

---

## 🔧 Code Reference

### Path Generation (minio.py Lines 93-130)

```python
def _path(self, filename, file_hash, private, doctype=None, docname=None, folder=None):
    parts = []

    if doctype:
        normalized_doctype = doctype.replace(" ", "_")
        parts.append(normalized_doctype)  # Level 1

    if docname:
        parts.append(docname)  # Level 2

    if folder:
        document_type = folder.strip("/").lower()
        parts.append(document_type)  # Level 3

    unique_filename = f"{file_hash[:8]}_{filename}"
    parts.append(unique_filename)  # Level 4

    return "/".join(parts)
    # Returns: "Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf"
```

### File URL Creation (minio.py Line 161)

```python
path = self._path(filename, file_hash, is_private, doctype, docname, folder)
# path = "Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf"

file_url = f"/{path}"
# file_url = "/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf"
```

### File URL Parsing (minio.py Line 132)

```python
def _parse(self, url):
    return url.strip("/")
    # Input: "/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf"
    # Output: "Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf"
```

---

## 📈 Storage Breakdown

### MinIO (Object Storage)
```
Location: http://172.16.135.118:9000
Bucket: rnd-files
Object Key: Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
Content: [ACTUAL FILE BYTES]
```

### Frappe Database (MariaDB)
```
Table: tabFile
Record:
  file_name: "project_proposal.pdf"
  file_url: "/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf"
  attached_to_doctype: "Project Registration"
  attached_to_name: "2026031901MeiTy000636"
  content_hash: "a1b2c3d4e5f67890..."
  is_private: 1
```

### Relationship
```
Frappe File.file_url → MinIO Object Key
(strip leading /)
```

---

## ✅ Summary

| Aspect | Details |
|--------|---------|
| **MinIO Path** | `Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf` |
| **Frappe file_url** | `/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_file.pdf` |
| **Difference** | Leading `/` added for Frappe convention |
| **Storage** | MinIO = file bytes, Frappe = metadata only |
| **Retrieval** | Use file_url to fetch from MinIO |
| **Format** | `/{Doctype}/{ID}/{Category}/{Hash8}_{Filename}` |

🎯 **The file path in Frappe DB is just a pointer to the actual file in MinIO!**

---

**Date**: March 19, 2026
**Format**: `/{Doctype}/{ID}/{Category}/{Hash}_{File}`
**Storage**: MinIO (bytes) + Frappe (metadata)
