# Permanent Staff Registration

Self-registration that creates a Frappe `User` for a permanent staff member.

- **Code:** `rndopsapp/rndopsapp/user_api/permanent_staff_api.py`
- **Auth check:** `verify_external_user()` in `rndopsapp/external_auth.py`
- **Base path:** `/api/method/rndopsapp.rndopsapp.user_api.permanent_staff_api.`
- **Login required:** No. All five endpoints allow Guest.

## Flow

1. The form loads and calls `get_permanent_staff_registration_options`.
2. The applicant selects a department. The form calls `get_department_head` and fills the head field.
3. The applicant types an Employee ID. The form calls `check_employee_id`.
4. The form generates PI Initials and calls `check_pi_initials`.
5. The applicant submits. The form calls `register_permanent_staff`.
6. The applicant logs in through the normal login with their institute password.

## Login before registration

`POST /api/method/login` with correct credentials and no `User` returns HTTP **403**:

```json
{
  "exc_type": "RegistrationRequiredError",
  "external_auth": true,
  "registration_required": true,
  "email": "username@iitg.ac.in"
}
```

The response also carries the readable text in `_server_messages`. No session is created.

- Check `registration_required`, then open the registration form with `email` filled in. Registration needs the password again.
- A wrong password still returns 401, so account status is revealed only to someone who knows the password.
- This applies to every institute account without a `User`, not only permanent staff.
- An email outside `iitg.ac.in` keeps the previous login failure.

## Endpoints

Frappe wraps every successful response in a `message` key.

### 1. `get_permanent_staff_registration_options` (GET)

No parameters. Returns all departments, and the designations whose type is `Permanent Staff`.

```json
{
  "message": {
    "status": "success",
    "departments": [{ "value": "<department id>", "label": "<department name>" }],
    "designations": [{ "value": "<designation id>", "label": "<designation name>" }]
  }
}
```

Show `label` to the applicant and send `value` back to the API.

### 2. `get_department_head` (GET)

| Parameter | Required | Description |
|---|---|---|
| `department` | Yes | Department id (`value` from the options) |

```json
{
  "message": {
    "status": "success",
    "data": { "user": "head@iitg.ac.in", "full_name": "Head Name" }
  }
}
```

`data` is `null` when the department has no head, or the head's account is disabled. An unknown department returns an error.

### 3. `check_employee_id` (GET or POST)

| Parameter | Required | Description |
|---|---|---|
| `employee_id` | Yes | ID to check |

```json
{
  "message": {
    "status": "success",
    "available": false,
    "message": "Employee ID 12345 is already registered."
  }
}
```

- `available` is `false` for an empty, badly formatted or already registered ID. `message` says which.
- Allowed format: 1 to 20 characters from letters, numbers, `/`, `_` and `-`.
- The check looks only at `User.employee_id`.
- The response never says who holds an ID.
- Limit: 120 requests per 60 seconds per IP.

### 4. `check_pi_initials` (GET or POST)

| Parameter | Required | Description |
|---|---|---|
| `pi_initials` | Yes | Value to check. Not case-sensitive |

Returns `status`, `available` and `message`, as `check_employee_id` does. `available` is `false` for an empty, badly formatted or taken value. Limit: 120 requests per 60 seconds per IP.

### 5. `register_permanent_staff` (POST)

| Parameter | Required | Description |
|---|---|---|
| `email` | Yes | `@iitg.ac.in` address |
| `password` | Yes | Institute password. Sent to the auth service, not stored |
| `first_name` | Yes | |
| `middle_name` | No | |
| `last_name` | No | |
| `employee_id` | Yes | Must be unused |
| `department_name` | Yes | Department id |
| `designation_name` | Yes | Id of a `Permanent Staff` designation |
| `pi_initials` | No | Unused PI Initials. Saved in upper case |

The head is not a parameter. The server derives it from `department_name`.

Request:

```json
{
  "email": "username@iitg.ac.in",
  "password": "<institute password>",
  "first_name": "First",
  "last_name": "Last",
  "employee_id": "12345",
  "department_name": "<department id>",
  "designation_name": "<designation id>"
}
```

Response:

```json
{
  "message": {
    "status": "success",
    "docname": "username@iitg.ac.in",
    "department_head": { "user": "head@iitg.ac.in", "full_name": "Head Name" },
    "message": "Registration successful. You can now log in."
  }
}
```

Limit: 20 requests per hour per IP. Failed attempts count too.

#### Validation order

1. Email domain and characters.
2. Required fields.
3. Department and designation exist.
4. The auth service accepts the username and password.
5. No `User` exists with that email or username.
6. Employee ID is well formed and unused.
7. PI Initials, if sent, are well formed and unused.

Duplicate checks run after authentication, so an unauthenticated caller cannot find out which accounts exist.

#### Errors

| Case | HTTP status |
|---|---|
| Wrong domain, missing field, invalid department or designation | 417 |
| Credentials rejected, or auth service unreachable | 401 |
| Email or username already registered | 409 |
| Employee ID invalid or already registered | 417 |
| PI Initials invalid or taken | 417 |
| Rate limit exceeded | 429 |

An unreachable auth service gives the applicant the same message as a wrong password. The real cause is in the Error Log under `ExternalAuth`. If the frontend redirects to login on every 401, exclude this endpoint.

## User record created

| Field | Value |
|---|---|
| `email` | Lower-cased input |
| `username` | Part of the email before `@` |
| `first_name`, `middle_name`, `last_name` | From the request |
| `enabled` | `1` |
| `user_type` | `System User` |
| `send_welcome_email` | `0` |
| `employee_id` | From the request |
| `pi_initials` | From the request, upper-cased, or empty |
| `empclass` | `5r4emiig95` (`P - Permanent Employee`) |
| `department_name` | From the request |
| `designation_name` | From the request |
| `piheadmentor_user_id` | Department head, or empty |
| Roles | `Permanent Employee` |

`empclass` is a hard-coded record id (`PERMANENT_EMPCLASS`). Confirm it matches on each server.

## Frontend notes

- Debounce `check_employee_id` by about 300 to 500 ms, and ignore responses for an outdated value.
- Call `get_department_head` on every department change. Show the head as read-only.
- Allow submission when the head is `null`.
- Send the password only in the POST body, over HTTPS. Do not store or log it.

## PI Initials rules

The server enforces the format (`^[A-Z]{3}[A-Z0-9]$`) and uniqueness. The frontend generates the value using these proposed rules (no official rule was found):

1. Uppercase letters only. Remove titles (`Dr`, `Prof`, `Mr`, `Mrs`, `Ms`), spaces and symbols. Ignore the middle name.
2. First and last name: first 2 letters of each (`Himanshu Gupta` → `HIGU`).
3. One name only, or a part with 1 letter: first 4 letters of the joined name (`Prateek` → `PRAT`).
4. Fewer than 4 letters: pad with `X` (`Om` → `OMXX`).
5. If taken: first letter of first name + first 3 of last name (`HGUP`), then first 3 letters of the initial value + `1` to `9` (`HIG1`).

If `pi_initials` is empty, project numbers for this PI end in `XXXX`.

## Configuration

| Setting | Source |
|---|---|
| Auth service URL | `external_auth_url` in site config, else `EXTERNAL_AUTH_URL` in `static_config.py` |
| Test account | `allow_test_login` in site config (see below) |
| Email domain | `INSTITUTE_EMAIL_DOMAIN` in `static_config.py` |

## Test account

For testing registration and login without a real institute account.

| Field | Value |
|---|---|
| Email | `test_user@iitg.ac.in` |
| Password | `test_login_password` in site config |

Enable it per site:

```bash
bench --site <site> set-config allow_test_login 1
bench --site <site> set-config test_login_password "<choose a password>"
```

Disable it with the same command and `0`. It is off unless set, and refuses every password until `test_login_password` is set.

- Before the `User` exists, login returns `registration_required` (see above). Register with `register_permanent_staff`.
- Log in with the email or with `test_user`, through `/api/method/login`.
- The auth service is not called for this account.
- It works only for registration and login. `verify_external_user()` (used by Workflow Override) does not accept it.
- To repeat a registration test, delete the `test_user@iitg.ac.in` User first.

> **Warning:** Never enable this on production. Anyone who knows the password can log in, and the account receives the `Permanent Employee` role. Setting the flag to `0` disables the test password but does not delete the User or end its sessions.

## Known limitations

- **Permanent status is not verified.** The auth service confirms only the username and password. Anyone with an institute login and no `User` record can register and receive the `Permanent Employee` role. Options: create accounts disabled until RnD HR approves them, or check against an approved list.
- **Department heads are incomplete.** On `prornd.local`, 35 of 81 departments had a head recorded (checked 27 November 2026).
- **Employee ID ownership is not verified.** The first applicant to enter an unused ID gets it.

## Testing

Verified on `prornd.local` by calling the Python functions directly, with `verify_external_user` mocked and the transaction rolled back.

| Case | Result |
|---|---|
| Valid registration | User created with the fields above |
| Rejected credentials | Refused |
| Non-institute domain | Refused |
| Existing user | Refused |
| Existing Employee ID | Refused |
| Department head lookup | Head returned |
| Employee ID check before and after registration | Available, then taken |

Not yet tested: calls over HTTP, the real auth service, rate limits and the HTTP status codes listed above. The repository has no automated test for this module.
