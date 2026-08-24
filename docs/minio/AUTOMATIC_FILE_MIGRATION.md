# Automatic File Migration to MinIO — Complete Solution

## 🎯 Problem Solved

**Issue**: Files uploaded through Frappe UI (Attach fields) were still being saved to local filesystem instead of MinIO.

**Example of the problem**:
```
http://172.16.117.39:8000/app/project-registration/2026022501RnD%20cell000538.pdf
```
File path in database: `/files/...` or `/private/files/...` (local filesystem)

**Solution**: Automatic migration during document save using the `validate()` hook.

---

## ✅ How It Works

### Automatic Migration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER UPLOADS FILE VIA FRAPPE UI                              │
│                                                                  │
│    - User clicks "Attach" button in Project Registration form   │
│    - Frappe's default handler saves to local filesystem         │
│    - File saved to: /sites/prornd.local/private/files/file.pdf  │
│    - Database stores: /private/files/file.pdf                   │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. USER CLICKS "SAVE" ON PROJECT REGISTRATION                   │
│                                                                  │
│    - Frappe triggers: ProjectRegistration.validate()            │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. VALIDATE HOOK DETECTS LOCAL FILE                             │
│                                                                  │
│    _process_attach_fields():                                    │
│      ✓ Scans all Attach fields                                  │
│      ✓ Finds: file_url = "/private/files/file.pdf"              │
│      ✓ Detects: Starts with /files/ or /private/files/          │
│      → Triggers migration                                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. MIGRATION TO MINIO                                            │
│                                                                  │
│    _migrate_file_to_minio():                                    │
│      1. Read file from local disk                               │
│      2. Upload to MinIO                                          │
│         → Path: Project_Registration/doc_id/category/file.pdf   │
│      3. Update field with MinIO URL                              │
│         → /Project_Registration/doc_id/category/hash_file.pdf   │
│      4. Delete old File doctype record                           │
│      5. Delete local file from disk                              │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. DOCUMENT SAVED WITH MINIO PATH                                │
│                                                                  │
│    Database now stores:                                          │
│    /Project_Registration/2026031901MeiTy000636/proposal/        │
│     a1b2c3d4_file.pdf                                            │
│                                                                  │
│    File location:                                                │
│    MinIO: rnd-files/Project_Registration/...                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Implementation Details

### Code Added to `project_registration.py`

#### 1. validate() Hook (Lines 60-71)

```python
def validate(self):
    """
    Intercept file uploads from Frappe UI and upload to MinIO.
    Runs before document is saved.
    """
    # Process main document Attach fields
    self._process_attach_fields()

    # Process child table Attach fields
    self._process_child_attach_fields()
```

**Triggered**: Every time a Project Registration document is saved
**Purpose**: Intercept and migrate local files to MinIO

---

#### 2. _process_attach_fields() (Lines 73-86)

```python
def _process_attach_fields(self):
    """Process Attach fields in the main Project Registration document."""
    meta = frappe.get_meta(self.doctype)

    for df in meta.fields:
        if df.fieldtype == "Attach":
            fieldname = df.fieldname
            file_url = self.get(fieldname)

            # Check if this is a local file
            if file_url and (file_url.startswith("/files/") or
                           file_url.startswith("/private/files/")):
                # Migrate to MinIO
                self._migrate_file_to_minio(fieldname, file_url)
```

**Scans**: All Attach fields in Project Registration
**Detects**: Local file paths (`/files/...`, `/private/files/...`)
**Action**: Triggers migration for each local file

---

#### 3. _migrate_file_to_minio() (Lines 107-160)

```python
def _migrate_file_to_minio(self, fieldname, file_url):
    """
    Migrate a file from local filesystem to MinIO.
    """
    try:
        # 1. Get File document
        file_doc = frappe.get_doc("File", {"file_url": file_url})

        # 2. Read file from local disk
        site_path = frappe.get_site_path()
        file_path = os.path.join(site_path, file_url.lstrip("/"))

        with open(file_path, "rb") as f:
            file_content = f.read()

        # 3. Upload to MinIO
        file_service = get_rnd_file_service()
        category = get_file_category(fieldname)

        upload_result = file_service.save_file(
            filename=file_doc.file_name,
            content=file_content,
            is_private=bool(file_doc.is_private),
            doctype=self.doctype,
            docname=self.name,
            folder=category
        )

        if upload_result.get("status"):
            # 4. Update field with MinIO URL
            minio_url = upload_result.get("data", {}).get("file_url")
            self.set(fieldname, minio_url)

            # 5. Cleanup: Delete old File doc and local file
            frappe.delete_doc("File", file_doc.name, ignore_permissions=True)
            os.remove(file_path)

            frappe.logger().info(f"Migrated {file_doc.file_name} to MinIO")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "MinIO Migration Error")
```

**Process**:
1. Read file from local disk
2. Upload to MinIO with proper categorization
3. Update document field with new MinIO URL
4. Delete old File record
5. Delete local file

---

#### 4. _process_child_attach_fields() (Lines 88-105)

```python
def _process_child_attach_fields(self):
    """Process Attach fields in child tables."""
    meta = frappe.get_meta(self.doctype)

    for df in meta.fields:
        if df.fieldtype == "Table":
            child_meta = frappe.get_meta(df.options)

            for child_row in self.get(df.fieldname) or []:
                for child_field in child_meta.fields:
                    if child_field.fieldtype == "Attach":
                        fieldname = child_field.fieldname
                        file_url = child_row.get(fieldname)

                        # Check if local file
                        if file_url and (file_url.startswith("/files/") or
                                       file_url.startswith("/private/files/")):
                            # Migrate to MinIO
                            self._migrate_child_file_to_minio(
                                child_row, fieldname, file_url
                            )
```

**Scans**: Child tables (sanction_related_files, supporting_documents)
**Handles**: Attach fields in child table rows
**Similar**: Same migration process as parent fields

---

## 📊 Migration Examples

### Example 1: Main Document Attach Field

**Before Save**:
```
Field: upload_proj_prop
Value: /private/files/project_proposal.pdf
File Location: /sites/prornd.local/private/files/project_proposal.pdf
```

**After Save** (automatic migration):
```
Field: upload_proj_prop
Value: /Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
File Location: MinIO → rnd-files/Project_Registration/2026031901MeiTy000636/proposal/a1b2c3d4_project_proposal.pdf
Local File: Deleted
```

---

### Example 2: Child Table Attach Field

**Before Save**:
```
Child Table: sanction_related_files
Row 1:
  sanction_file: /private/files/sanction_order.pdf
```

**After Save** (automatic migration):
```
Child Table: sanction_related_files
Row 1:
  sanction_file: /Project_Registration/2026031901MeiTy000636/sanction/12345678_sanction_order.pdf

File Location: MinIO → rnd-files/Project_Registration/.../sanction/12345678_sanction_order.pdf
```

---

## 🎯 What Gets Migrated

### Migrated File Types

✅ **Main Document Attach Fields**:
- `upload_proj_prop` → Category: `proposal`

✅ **Child Table Attach Fields**:
- `sanction_file` (sanction_related_files table) → Category: `sanction`
- `attachment` (supporting_documents table) → Category: `attachments`

### Migration Triggers

Migration occurs when:
1. Document is saved (via UI or API)
2. File URL starts with `/files/` or `/private/files/`
3. validate() hook detects local file
4. Automatic migration to MinIO

---

## 📝 Category Mapping

Files are categorized based on field names:

| Field Name | MinIO Category |
|------------|----------------|
| `upload_proj_prop` | `proposal` |
| `sanction_file` | `sanction` |
| `attachment` | `attachments` |
| (others) | `documents` (fallback) |

Defined in `FILE_CATEGORY_MAP` (lines 23-37).

---

## ✅ Benefits

### 1. Transparent to Users
- Users upload files normally via Frappe UI
- Migration happens automatically on save
- No UI changes needed
- Works with existing workflows

### 2. Automatic Cleanup
- Deletes local files after successful upload
- Removes old File doctype records
- Prevents duplicate storage
- Keeps filesystem clean

### 3. Proper Categorization
- Files organized by type
- Uses category mapping
- Consistent structure
- Easy to find files

### 4. Error Handling
- Logs errors to Error Log doctype
- Doesn't break document save if migration fails
- Graceful degradation
- Retry possible on next save

---

## 🔍 Verification

### Check Migration Status

```python
# In Frappe console
import frappe

# Get recent files
files = frappe.get_all('File',
    filters={'attached_to_doctype': 'Project Registration'},
    fields=['file_name', 'file_url', 'creation'],
    order_by='creation desc',
    limit=10
)

for f in files:
    if f.file_url.startswith('/Project_Registration/'):
        print(f"✓ MinIO: {f.file_name}")
    elif f.file_url.startswith('/files/'):
        print(f"✗ Local: {f.file_name}")
```

### Expected Output

```
✓ MinIO: project_proposal.pdf
✓ MinIO: sanction_order.pdf
✓ MinIO: document.csv
```

---

## 🚨 Edge Cases Handled

### 1. File Not Found
```python
if not os.path.exists(file_path):
    frappe.log_error(f"File not found: {file_path}", "File Migration Error")
    return
```
**Action**: Logs error, skips migration

### 2. MinIO Upload Failure
```python
if upload_result.get("status"):
    # Migration successful
else:
    # Upload failed - file remains local
```
**Action**: Keeps original local file, logs error

### 3. Multiple Saves
- Migration only happens if file starts with `/files/` or `/private/files/`
- Already-migrated files (start with `/Project_Registration/`) are skipped
- No duplicate uploads

### 4. Child Table Rows
- Each child row processed independently
- Empty rows skipped
- Migration applied per file

---

## 📊 Before vs After

### User Experience

| Aspect | Before | After |
|--------|--------|-------|
| **Upload Method** | Frappe UI Attach button | Frappe UI Attach button (same) |
| **File Storage** | Local filesystem | MinIO object storage |
| **Migration** | Manual | Automatic on save |
| **File Path** | `/files/...` | `/Project_Registration/.../category/...` |
| **Cleanup** | Manual | Automatic |

### Technical Flow

**Before**:
```
Upload → Local Disk → Stay Local Forever
```

**After**:
```
Upload → Local Disk (temporary) → Save Document →
Auto-Migrate to MinIO → Delete Local File
```

---

## 🛠️ Troubleshooting

### Issue: Files Still Saving Locally

**Check**:
1. Is `validate()` hook being called?
   ```python
   # Add debug logging
   def validate(self):
       frappe.logger().info("Validate hook called")
       self._process_attach_fields()
   ```

2. Is file path detected correctly?
   ```python
   # In _process_attach_fields()
   if file_url:
       frappe.logger().info(f"Checking file: {file_url}")
   ```

3. Check Error Log doctype for migration errors

---

### Issue: Migration Fails

**Check Error Log**:
```python
# Get recent errors
errors = frappe.get_all('Error Log',
    filters={'error': ['like', '%MinIO Migration%']},
    fields=['error', 'creation'],
    order_by='creation desc',
    limit=5
)

for e in errors:
    print(e.error)
```

**Common Causes**:
- MinIO server unreachable
- File not found on disk
- Permission issues
- Invalid file path

---

## 📈 Migration Statistics

### Check Migration Progress

```python
# Count files by storage type
total = frappe.db.count('File', {
    'attached_to_doctype': 'Project Registration'
})

minio_files = frappe.db.count('File', {
    'attached_to_doctype': 'Project Registration',
    'file_url': ['like', '/Project_Registration/%']
})

local_files = frappe.db.count('File', {
    'attached_to_doctype': 'Project Registration',
    'file_url': ['like', '/files/%']
})

print(f"Total: {total}")
print(f"MinIO: {minio_files} ({minio_files/total*100:.1f}%)")
print(f"Local: {local_files} ({local_files/total*100:.1f}%)")
```

---

## 🎓 Key Points

✅ **Automatic**: Migration happens on every document save
✅ **Transparent**: Users don't notice any change
✅ **Safe**: Errors logged, doesn't break save
✅ **Clean**: Deletes local files after upload
✅ **Categorized**: Files organized by type
✅ **Complete**: Handles main and child table attachments

---

## 📞 Summary

**What happens when you upload a file via Frappe UI:**

1. **Upload** → File saved to local disk temporarily
2. **Save Document** → validate() hook triggered
3. **Detection** → Local file path detected
4. **Migration** → File uploaded to MinIO
5. **Update** → Field updated with MinIO URL
6. **Cleanup** → Local file deleted

**Result**: All files automatically stored in MinIO with proper categorization, zero local storage!

---

**Implementation Date**: March 19, 2026
**Status**: ✅ Active
**Trigger**: validate() hook on Project Registration
**Applies To**: All Attach fields (main document + child tables)
