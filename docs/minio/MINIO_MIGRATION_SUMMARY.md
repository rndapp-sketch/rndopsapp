# MinIO Storage Migration — Project Registration Module

## Summary

Successfully migrated the Project Registration module from local filesystem storage to MinIO object storage.

## Date
March 19, 2026

## Changes Made

### 1. Configuration (✅ Completed)
- **File**: `/home/osintpc/frappe/prornd/sites/prornd.local/site_config.json`
- **Action**: Added MinIO configuration:
  ```json
  {
    "minio_endpoint": "172.16.135.118:9000",
    "minio_access_key": "jxs8v77h5a9YHuhpKFoy",
    "minio_secret_key": "54gteWjr3XZAPKqaG22J3yZUDk4DBeKphovzL2om",
    "minio_bucket": "rnd-files"
  }
  ```
  **Note**: Port **9000** is the S3 API endpoint. Port 9001 is the MinIO Console UI.

### 2. Code Modifications (✅ Completed)

#### File: `project_registration.py`

**Location**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_registration/project_registration.py`

**Changes**:

1. **Added Import** (Line 18):
   ```python
   from rndopsapp.minio import get_rnd_file_service
   ```

2. **Modified `generate_endorsement_pdf()`** (Lines 29-85):
   - **Before**: Used `os.makedirs()` and `open()` to write HTML/PDF to `/private/files/Endorsement/`
   - **After**: Uses `get_rnd_file_service().save_file()` to upload to MinIO
   - **Result**: Files stored at MinIO path: `private/Project Registration/{docname}/Endorsement/{year}/{month}/{hash}/{filename}`

3. **Modified `save_project_data()` — HTML/PDF Generation** (Lines 1034-1086):
   - **Before**: Created `/public/files/Endorsement/` directory and wrote files locally
   - **After**: Uploads HTML and PDF to MinIO with `is_private=False`
   - **Result**: Public files accessible via MinIO presigned URLs

4. **Modified `save_project_data()` — Base64 Attach Fields** (Lines 1003-1071):
   - **Before**: Passed Base64 dict to Frappe ORM for local file handling
   - **After**: Intercepts Base64 data, decodes it, and uploads to MinIO
   - **Handles**:
     - Parent document Attach fields (e.g., `upload_proj_prop`)
     - Child table Attach fields (e.g., `sanction_file` in `sanction_related_files`)
   - **Result**: Field value set to MinIO file URL instead of local path

5. **Modified `save_project_draft()` — HTML/PDF Generation** (Lines 1508-1566):
   - **Before**: Wrote HTML/PDF to `/private/files/Endorsement/`
   - **After**: Uploads to MinIO with `is_private=True`
   - **Result**: Draft endorsement files stored privately in MinIO

### 3. Unit Tests (✅ Completed)

**File**: `test_project_registration.py`

**Location**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_registration/test_project_registration.py`

**Added**: `TestMinIOFileUpload` class with 3 test methods:

1. **`test_generate_endorsement_pdf_calls_minio`** (Lines 212-264):
   - Mocks `get_rnd_file_service()`
   - Verifies `save_file()` called twice (HTML + PDF)
   - Validates correct parameters: filename, content, is_private, doctype, docname, folder

2. **`test_no_local_filesystem_writes`** (Lines 266-299):
   - Patches `os.makedirs` and `builtins.open`
   - Confirms no local filesystem operations occur

3. **`test_generate_endorsement_pdf_handles_minio_failure`** (Lines 301-333):
   - Simulates MinIO connection failure
   - Ensures graceful error handling without exceptions

## Architecture Decision

**Option A (Implemented)**: Explicit API Interception

- **Scope**: Intercepts file uploads at the API level (`save_project_data()`, `save_project_draft()`)
- **Frappe Attach Fields**: Left unchanged for Frappe desk UI compatibility
- **Custom Frontend**: Decodes Base64 and uploads via RNDFileService before ORM processing
- **Benefit**: Non-invasive, minimal risk to Frappe core file handling

**Option B (Not Implemented)**: Full Frappe File Upload Override
- Would require hooking into Frappe's `/api/method/upload_file` endpoint
- Higher complexity and risk of breaking Frappe desk functionality

## Backward Compatibility

**Existing Files**:
- Files already stored locally (`/private/files/Endorsement/`, `/public/files/Endorsement/`) remain accessible
- No migration of old files performed in this phase
- Old file URLs continue to work

**New Files**:
- All new uploads go to MinIO
- File URLs in database point to MinIO paths (e.g., `/private/Project Registration/...`)

## File Path Structure in MinIO

### Endorsement Files (Private)
```
private/Project Registration/{docname}/Endorsement/{year}/{month}/{hash[:2]}/{hash[2:4]}/{hash}_{filename}
```
Example:
```
private/Project Registration/PROJ-001/Endorsement/2026/03/ab/cd/abcd1234_PROJ-001-Endorsement.pdf
```

### Endorsement Files (Public) — via save_project_data()
```
public/Project Registration/{docname}/Endorsement/{year}/{month}/{hash[:2]}/{hash[2:4]}/{hash}_{filename}
```

### Attach Field Files
```
private/Project Registration/{docname}/{fieldname}/{year}/{month}/{hash[:2]}/{hash[2:4]}/{hash}_{filename}
```
Example:
```
private/Project Registration/PROJ-001/upload_proj_prop/2026/03/ab/cd/abcd1234_proposal.pdf
```

## Deduplication

The `RNDFileService` in `minio.py` performs SHA-256 content hashing:
- If a file with the same content already exists, it returns the existing file URL
- Prevents duplicate storage
- Frappe `File` doctype uses `content_hash` field for tracking

## Testing

### Automated Tests
Run unit tests:
```bash
cd /home/osintpc/frappe/prornd
bench --site prornd.local run-tests --app rndopsapp --module rndopsapp.rndopsapp.doctype.project_registration.test_project_registration
```

### Manual Verification

#### Prerequisites
1. Verify MinIO server is running at `http://172.16.135.118:9001`
2. Credentials from `credentials.json` are valid
3. Bucket `rnd-files` exists

#### Test Steps

1. **Start Development Server**:
   ```bash
   cd /home/osintpc/frappe/prornd && bench start
   ```

2. **Test via API** (simulate frontend):
   - Call `save_project_data` with Base64 file payload
   - Verify file appears in MinIO console under `public/Project Registration/.../`

3. **Test via Frappe Desk**:
   - Create/update a Project Registration document
   - Add HTML content to `text_editor_zwfu` field
   - Save document
   - Check MinIO console for HTML and PDF files

4. **Verify File Access**:
   - Use `get_rnd_file_service().get_signed_url(file_url)` to generate presigned URL
   - Access URL in browser to confirm file downloads correctly

5. **Check Frappe File Records**:
   - Navigate to File doctype in Frappe desk
   - Filter by `attached_to_doctype = "Project Registration"`
   - Verify `file_url` fields point to MinIO paths (not `/private/files/...`)

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `site_config.json` | 10-13 | Added MinIO configuration |
| `project_registration.py` | 18, 29-85, 1003-1071, 1034-1086, 1508-1566 | MinIO integration |
| `test_project_registration.py` | 18, 205-333 | Added MinIO unit tests |

## Dependencies

- **MinIO Python SDK**: Already installed (imported in `minio.py`)
- **Existing Module**: `rndopsapp.rndopsapp.minio.py` (no changes needed)

## Next Steps (Optional Future Enhancements)

1. **Migrate Existing Files**:
   - Write migration script to move old local files to MinIO
   - Update File doctype records with new MinIO URLs

2. **Add Cleanup Job**:
   - Create scheduled job to delete local files after MinIO upload confirmed

3. **Monitoring**:
   - Add metrics for upload success/failure rates
   - Dashboard for MinIO storage usage

4. **Extend to Other Modules**:
   - Apply same pattern to other doctypes with file uploads

## Rollback Plan

If issues arise:

1. **Revert Code Changes**:
   ```bash
   cd /home/osintpc/frappe/prornd/apps/rndopsapp
   git checkout project_registration.py test_project_registration.py
   ```

2. **Remove MinIO Config**:
   - Edit `site_config.json` and remove MinIO keys

3. **Restart Server**:
   ```bash
   bench restart
   ```

## Support

- **MinIO Service Code**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/minio.py`
- **Credentials**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/credentials.json`
- **MinIO Console**: `http://172.16.135.118:9001`

---

**Migration Completed**: March 19, 2026
**Performed By**: Claude Code Assistant
**Status**: ✅ All tasks completed successfully
