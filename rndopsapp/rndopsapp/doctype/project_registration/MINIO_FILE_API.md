# MinIO File API — Project Registration

---

## Endpoint 1 — Get File Paths

```
POST http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_project_files_by_project_no
```

### Request

```json
{ "project_no": "2627R-0007-CSEN0804SRSH" }
```

### curl

```bash
curl -X POST "http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_project_files_by_project_no" \
  -H "Content-Type: application/json" \
  -d '{"project_no": "2627R-0007-CSEN0804SRSH"}'
```

### Response

```json
{
  "message": {
    "status": "success",
    "docname": "2026042001MKY6000342",
    "files": [
      "Project_Registration/2026042001MKY6000342/attachments/Unit 1 part 1.pdf",
      "Project_Registration/2026042001MKY6000342/attachments/sample.pdf",
      "Project_Registration/2026042001MKY6000342/endorsement/2026042001MKY6000342-Endorsement.pdf",
      "Project_Registration/2026042001MKY6000342/fund_sanction/542025009785_v1_616718.pdf",
      "Project_Registration/2026042001MKY6000342/fund_sanction/reimbursement_mky.pdf",
      "Project_Registration/2026042001MKY6000342/indent_general_form/2026051212000629/files/Reimbursement_Module.pdf"
    ]
  }
}
```

---

## Endpoint 2 — Download a File

```
POST http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_minio_project_file
```

Pass the `docname` and any `path` from the files array above.

### Request

```json
{
  "docname": "2026042001MKY6000342",
  "path": "Project_Registration/2026042001MKY6000342/attachments/sample.pdf"
}
```

### curl

```bash
curl -X POST "http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_minio_project_file" \
  -H "Content-Type: application/json" \
  -d '{
    "docname": "2026042001MKY6000342",
    "path": "Project_Registration/2026042001MKY6000342/attachments/sample.pdf"
  }' \
  -o sample.pdf
```

### Response

Binary file download — Frappe streams the file directly. The MinIO IP is not exposed to the client.

---

## Endpoint 3 — Get File Paths with Full MinIO URLs

```
POST http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_project_file_urls_by_project_no
```

Same as Endpoint 1 but each file entry includes the full MinIO URL.

### Request

```json
{ "project_no": "2627R-0007-CSEN0804SRSH" }
```

### curl

```bash
curl -X POST "http://172.16.131.206:8000/api/method/rndopsapp.rndopsapp.doctype.project_registration.project_registration.get_project_file_urls_by_project_no" \
  -H "Content-Type: application/json" \
  -d '{"project_no": "2627R-0007-CSEN0804SRSH"}'
```

### Response

```json
{
  "message": {
    "status": "success",
    "docname": "2026042001MKY6000342",
    "files": [
      {
        "path": "Project_Registration/2026042001MKY6000342/attachments/Unit 1 part 1.pdf",
        "url": "http://172.16.135.118:9000/prod-rnd-files/Project_Registration/2026042001MKY6000342/attachments/Unit 1 part 1.pdf"
      },
      {
        "path": "Project_Registration/2026042001MKY6000342/attachments/sample.pdf",
        "url": "http://172.16.135.118:9000/prod-rnd-files/Project_Registration/2026042001MKY6000342/attachments/sample.pdf"
      },
      {
        "path": "Project_Registration/2026042001MKY6000342/fund_sanction/542025009785_v1_616718.pdf",
        "url": "http://172.16.135.118:9000/prod-rnd-files/Project_Registration/2026042001MKY6000342/fund_sanction/542025009785_v1_616718.pdf"
      }
    ]
  }
}
```
