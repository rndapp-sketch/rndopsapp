# SQL Queries

Collection of SQL queries used for database operations on the prornd site (`_365f2bec5fab17e5`).

---

## Project Registration

### Select a Project Registration record

```sql
SELECT name, principal_investigator_name
FROM `tabProject Registration`
WHERE name = '2026060801ANRF001009';
```

### Update Principal Investigator Name

```sql
UPDATE `tabProject Registration`
SET
    principal_investigator_name = 'Debdas Dhabal',
    modified = NOW(),
    modified_by = 'Administrator'
WHERE name = '2026060801ANRF001009';
```

### Verify Update

```sql
SELECT name, principal_investigator_name, modified, modified_by
FROM `tabProject Registration`
WHERE name = '2026060801ANRF001009';
```

---

## Usage

Run queries via MySQL CLI:

```bash
mysql -u root -proot _365f2bec5fab17e5 -e "<query here>"
```
