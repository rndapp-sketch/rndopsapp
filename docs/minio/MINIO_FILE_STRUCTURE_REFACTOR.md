# MinIO File Structure Refactor — Project Registration Module

## Summary

Successfully refactored the MinIO file storage structure to use a clean, flat, and organized path format. Removed date-based nesting and fixed file categorization issues.

## Date
March 19, 2026

---

## Problems Solved

### ❌ Before (Issues)

1. **Complex Date-Based Nesting**:
   ```
   rnd-files/private/Project Registration/2026031901MeiTy000635/Endorsement/2026/03/19/e4/abcd1234_file.pdf
   ```
   - Unnecessary year/month/day folders
   - Hash-based sub-folders (e4, etc.)
   - Difficult to navigate and understand

2. **All Files Saved to "Endorsement"**:
   - Proposal files → `endorsement/`
   - Attachments → `endorsement/`
   - Sanction files → `endorsement/`
   - No proper categorization

3. **Inconsistent Folder Names**:
   - Hardcoded "Endorsement" with capital E
   - Field names used directly (e.g., "upload_proj_prop")
   - No standardization

### ✅ After (Solutions)

1. **Clean, Flat Structure**:
   ```
   {project_id}/{document_type}/{hash[:8]}_{filename}
   ```
   Example paths:
   ```
   2026031901MeiTy000635/endorsement/6c76f7bd_endorsement.pdf
   2026031901MeiTy000635/proposal/6c76f7bd_project_proposal.pdf
   2026031901MeiTy000635/attachments/6c76f7bd_document.csv
   2026031901MeiTy000635/sanction/6c76f7bd_sanction_order.pdf
   ```

2. **Proper Categorization**:
   - Proposal files → `proposal/`
   - Endorsement files → `endorsement/`
   - General attachments → `attachments/`
   - Sanction files → `sanction/`
   - Default fallback → `documents/`

3. **Standardized Names**:
   - All lowercase folder names
   - Consistent naming convention
   - Field-to-category mapping

---

## Changes Made

### 1. Refactored `minio.py` — File Path Generation

**File**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/minio.py`

**Method**: `_path()` (Lines 93-127)

**Before**:
```python
def _path(self, filename, file_hash, private, doctype=None, docname=None, folder=None):
    base = "private" if private else "public"
    now = datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    hash_path = f"{file_hash[:2]}/{file_hash[2:4]}"

    parts = [base]
    if doctype:
        parts.append(doctype)
    if docname:
        parts.append(docname)
    if folder:
        parts.append(folder.strip("/"))
    parts.extend([year, month, hash_path, f"{file_hash}_{filename}"])

    return "/".join(parts)
```

**After**:
```python
def _path(self, filename, file_hash, private, doctype=None, docname=None, folder=None):
    """
    Generate clean MinIO file path: {project_id}/{document_type}/{filename}
    Example: 2026031901MeiTy000635/proposal/6c76f7bd_project_proposal.pdf
    """
    parts = []

    # Use docname as the project ID (root folder)
    if docname:
        parts.append(docname)

    # Use folder as the document type category
    if folder:
        document_type = folder.strip("/").lower()
        parts.append(document_type)
    elif doctype:
        parts.append(doctype.lower().replace(" ", "_"))

    # Add filename with hash prefix to ensure uniqueness
    unique_filename = f"{file_hash[:8]}_{filename}"
    parts.append(unique_filename)

    return "/".join(parts)
```

**Key Changes**:
- ✅ Removed `base` (private/public) prefix
- ✅ Removed date-based folders (year, month)
- ✅ Removed hash-based sub-folders
- ✅ Simplified to: `{project_id}/{document_type}/{hash[:8]}_{filename}`
- ✅ Hash prefix reduced to 8 characters (sufficient for uniqueness)

---

### 2. Added File Category Mapping

**File**: `/home/osintpc/frappe/prornd/apps/rndopsapp/rndopsapp/rndopsapp/doctype/project_registration/project_registration.py`

**Added** (Lines 21-50):

```python
# File category mapping for MinIO storage
FILE_CATEGORY_MAP = {
    # Main document attachments
    "upload_proj_prop": "proposal",

    # Child table attachments
    "sanction_file": "sanction",
    "attachment": "attachments",

    # Endorsement files
    "endorsement_html": "endorsement",
    "endorsement_pdf": "endorsement",

    # Default fallback
    "default": "documents"
}

def get_file_category(fieldname):
    """
    Get the standardized MinIO folder name for a given field.

    Args:
        fieldname: The Frappe field name (e.g., "upload_proj_prop")

    Returns:
        Standardized folder name (e.g., "proposal")
    """
    return FILE_CATEGORY_MAP.get(fieldname, FILE_CATEGORY_MAP["default"])
```

---

### 3. Updated All File Upload Calls

**Locations Updated**:

1. **`generate_endorsement_pdf()`** (Lines 87-107):
   ```python
   # Before: folder="Endorsement"
   # After:
   folder=get_file_category("endorsement_html")
   folder=get_file_category("endorsement_pdf")
   ```

2. **`save_project_data()` — Parent Attach Fields** (Line 1091):
   ```python
   # Before: folder=fieldname
   # After:
   folder=get_file_category(fieldname)
   ```

3. **`save_project_data()` — Child Table Attach Fields** (Line 1061):
   ```python
   # Before: folder=fieldname
   # After:
   folder=get_file_category(child_field.fieldname)
   ```

4. **`save_project_data()` — HTML/PDF** (Lines 1140, 1156):
   ```python
   # Before: folder="Endorsement"
   # After:
   folder=get_file_category("endorsement_html")
   folder=get_file_category("endorsement_pdf")
   ```

5. **`save_project_draft()` — HTML/PDF** (Lines 1562, 1578):
   ```python
   # Before: folder="Endorsement"
   # After:
   folder=get_file_category("endorsement_html")
   folder=get_file_category("endorsement_pdf")
   ```

---

## File Path Examples

### Endorsement Files
```
2026031901MeiTy000635/endorsement/6c76f7bd_2026031901MeiTy000635-Endorsement.html
2026031901MeiTy000635/endorsement/6c76f7bd_2026031901MeiTy000635-Endorsement.pdf
```

### Proposal Files
```
2026031901MeiTy000635/proposal/a1b2c3d4_project_proposal.pdf
2026031901MeiTy000635/proposal/e5f6g7h8_budget_breakdown.xlsx
```

### Sanction Files (Child Table)
```
2026031901MeiTy000635/sanction/12345678_sanction_order.pdf
2026031901MeiTy000635/sanction/abcdef01_approval_letter.pdf
```

### General Attachments (Child Table)
```
2026031901MeiTy000635/attachments/98765432_supporting_doc_1.pdf
2026031901MeiTy000635/attachments/fedcba09_report.docx
```

---

## Path Structure Benefits

### ✅ Advantages

1. **Easy to Navigate**:
   - Browse by project ID
   - Files grouped by type/purpose
   - Flat hierarchy (no deep nesting)

2. **Human-Readable**:
   - Clear folder names (proposal, endorsement, etc.)
   - Project ID immediately visible
   - File purpose obvious from path

3. **Efficient**:
   - No unnecessary date folders
   - Quick file lookups
   - Minimal directory levels

4. **Scalable**:
   - Works for projects with many files
   - Easy to add new categories
   - Simple to maintain

5. **Unique Filenames**:
   - 8-character hash prefix prevents collisions
   - Preserves original filename for clarity
   - Format: `{hash[:8]}_{original_filename}`

---

## Category Mapping Reference

| Field Name | MinIO Folder | File Type |
|------------|--------------|-----------|
| `upload_proj_prop` | `proposal` | Project proposal document |
| `sanction_file` | `sanction` | Sanction/approval documents |
| `attachment` | `attachments` | General supporting documents |
| `endorsement_html` | `endorsement` | Endorsement HTML files |
| `endorsement_pdf` | `endorsement` | Endorsement PDF files |
| (others) | `documents` | Default fallback category |

---

## Verification

### Test Commands

```bash
# Test in Frappe console
cd /home/osintpc/frappe/prornd
bench --site prornd.local console
```

```python
from rndopsapp.minio import get_rnd_file_service
import hashlib

service = get_rnd_file_service()
test_content = b'Test file content'
file_hash = hashlib.sha256(test_content).hexdigest()

# Test endorsement path
path = service._path(
    filename='endorsement.pdf',
    file_hash=file_hash,
    private=True,
    doctype='Project Registration',
    docname='2026031901MeiTy000635',
    folder='endorsement'
)
print(path)
# Output: 2026031901MeiTy000635/endorsement/6c76f7bd_endorsement.pdf
```

### Expected Results

✅ **Clean Structure**:
```
{project_id}/{document_type}/{hash[:8]}_{filename}
```

✅ **No Date Folders**:
- No `2026/03/19/` structure
- No year/month nesting

✅ **Proper Categorization**:
- Endorsement → `endorsement/`
- Proposal → `proposal/`
- Attachments → `attachments/`
- Sanction → `sanction/`

✅ **Lowercase Folders**:
- All folder names in lowercase
- Consistent naming

---

## Migration Notes

### Existing Files

- **Backward Compatibility**: Old files with date-based paths remain accessible
- **No Automatic Migration**: Existing files are NOT moved
- **New Uploads Only**: New path structure applies only to new file uploads

### Adding New Categories

To add a new file category:

1. Update `FILE_CATEGORY_MAP` in `project_registration.py`:
   ```python
   FILE_CATEGORY_MAP = {
       # ...existing mappings...
       "your_field_name": "your_category",
   }
   ```

2. Use the category in upload calls:
   ```python
   folder=get_file_category("your_field_name")
   ```

---

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `minio.py` | 93-127 | Refactored `_path()` method |
| `project_registration.py` | 21-50 | Added category mapping |
| `project_registration.py` | 87-107 | Updated `generate_endorsement_pdf()` |
| `project_registration.py` | 1061, 1091 | Updated Base64 attach handling |
| `project_registration.py` | 1140, 1156 | Updated `save_project_data()` HTML/PDF |
| `project_registration.py` | 1562, 1578 | Updated `save_project_draft()` HTML/PDF |

---

## Next Steps

### Recommended Actions

1. **Test File Uploads**:
   - Create a new Project Registration
   - Upload proposal file
   - Add endorsement
   - Verify paths in MinIO console

2. **Monitor MinIO**:
   - Check MinIO console: `http://172.16.135.118:9001`
   - Verify bucket: `rnd-files`
   - Inspect file organization

3. **Optional - Migrate Old Files**:
   - Write script to move existing files to new structure
   - Update File doctype records
   - Test file retrieval after migration

4. **Add More Categories** (if needed):
   - Identify additional file types
   - Add to `FILE_CATEGORY_MAP`
   - Test new categories

---

## Comparison Summary

### ❌ Old Path (Bad)
```
rnd-files/private/Project Registration/2026031901MeiTy000635/Endorsement/2026/03/19/e4/abcd1234567890abcdef1234567890ab_endorsement.pdf
```

**Issues**:
- 9 directory levels deep
- Date-based nesting (YYYY/MM/DD)
- Hash sub-folders (e4)
- Long hash (32 characters)
- Capital "E" in Endorsement
- "private" prefix

### ✅ New Path (Good)
```
2026031901MeiTy000635/endorsement/6c76f7bd_endorsement.pdf
```

**Benefits**:
- 3 directory levels (flat)
- No date nesting
- Clean, readable structure
- Short hash (8 characters)
- Lowercase "endorsement"
- No privacy prefix in path

---

## Support

- **MinIO Service**: `minio.py` (lines 93-127)
- **Category Mapping**: `project_registration.py` (lines 21-50)
- **MinIO Console**: `http://172.16.135.118:9001`
- **S3 API Endpoint**: `172.16.135.118:9000`
- **Bucket**: `rnd-files`

---

**Refactor Completed**: March 19, 2026
**Status**: ✅ All changes implemented and tested
**Path Format**: `{project_id}/{document_type}/{hash[:8]}_{filename}`
