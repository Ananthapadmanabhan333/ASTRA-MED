# Security: authentication, access control and audit (phases 5 and 7)

Phase 7 changes are marked *(phase 7)*. The full audit, with open items, is in
[PHASE7_AUDIT.md](PHASE7_AUDIT.md).

## Authentication

- **Accounts:** stored in `users`. Passwords are hashed with scrypt (N=2^15, r=8, p=3, 16-byte salt,
  per OWASP) and checked in constant time. A password needs at least 12 characters, must not contain
  the username and must not be repetitive.
- **Sessions:** server-side. The browser holds a random 256-bit token in an `HttpOnly`,
  `SameSite=Strict` cookie (`astra_session`; add `Secure` with `ASTRA_AUTH_COOKIE_SECURE=true` behind
  HTTPS). The database holds only its SHA-256 digest. A session ends after 8 hours, after 60 idle
  minutes, on logout, on a password change (other sessions) and when the role changes or the account
  is deactivated.
- **CSRF:** cookie-authenticated writes must echo the session's CSRF token in `X-CSRF-Token`. This is a
  double-submit check on top of SameSite=Strict.
- **Scripts:** `POST /api/auth/token` issues a bearer token (`Authorization: Bearer …`, no cookie, no
  CSRF token).
- **Brute force:**
  - every attempt takes the same scrypt work, even for unknown usernames;
  - a wrong username and a wrong password give the same error;
  - more than `ASTRA_AUTH_LOGIN_ATTEMPTS_PER_MINUTE` attempts from one client address get HTTP 429
    with `Retry-After`;
  - an account locks for 15 minutes after 5 failed sign-ins. *(phase 7)* A locked account now gets the
    same message and the same scrypt work as a wrong password, so a lockout does not confirm that a
    username exists. The audit log keeps the real reason.
- **WebSocket:** `/ws/health-monitoring` needs an allowed Origin and a session with `health:read`
  before it accepts (else close code 1008). The session is re-checked every 60 s.
- **Disabled auth:** `ASTRA_AUTH_ENABLED=false` grants every permission to every caller and logs a
  warning. It is refused when `ASTRA_ENVIRONMENT=production`. A wildcard CORS origin is always
  refused (credentials are allowed).
- **Production profile** *(phase 7)*: with `ASTRA_ENVIRONMENT=production` the API refuses to start
  unless authentication is on, cookies are `Secure`, the database is PostgreSQL and the schema is
  Alembic-managed (`ASTRA_DB_SCHEMA_MODE=migrate`). The interactive docs are off by default.

## Roles and permissions

Access is checked by permission, never by role name (`app/security/rbac.py`; `GET /api/auth/roles`).

| Permission | Flight surgeon | Mission operator | Analyst | Administrator |
| --- | :-: | :-: | :-: | :-: |
| `health:read` crew records, twin, AI, alerts | ✓ | ✓ | ✓ | |
| `space:read` NASA data | ✓ | ✓ | ✓ | ✓ |
| `alerts:manage` acknowledge / resolve | ✓ | ✓ | | |
| `simulation:control` scenarios, emergency runs | | ✓ | | |
| `reports:read` | ✓ | ✓ | | |
| `reports:write` create, export | ✓ | ✓ | | |
| `reports:review` sign-off states | ✓ | | | |
| `assistant:use` | ✓ | ✓ | ✓ | |
| `space:sync` | | ✓ | | ✓ |
| `models:manage` reload models | | | | ✓ |
| `system:maintain` consistency repair *(phase 7)* | | ✓ | | ✓ |
| `audit:read` | | | | ✓ |
| `users:manage` | | | | ✓ |

**Data access restrictions.**

- **Administrator:** separation of duties. The role manages accounts, the audit log, models and data
  sync, and cannot read crew health records.
- **Analyst:** read-only, with no incident reports and no actions.
- **Space routes:** the ones that expose crew data (radiation intelligence, mission timeline,
  correlation) also need `health:read`.
- **Assistant:** lists reports only for roles with `reports:read`.
- **Incident-report events** *(phase 7)*: the unified event history, timeline, counts, overview and
  live stream hide `incident_reports` events from roles without `reports:read`. The WebSocket hub
  records each connection's permissions and sends such events only to permitted sockets.
- **Model reload** *(phase 7)*: `POST /api/ai/models/reload` is mounted outside the `health:read`
  router, so administrators (who have `models:manage` but no crew access) can actually use it.

## Audit log

`audit_log` records, with user, role, client address, request ID and outcome:

- sign-ins (successful and failed, with the failure reason kept server-side only), logouts and
  password changes;
- every write (method and route template);
- access denials, de-duplicated to one entry per user and route per minute because dashboards poll;
- CSRF rejections and refused WebSocket connections;
- views of health records, once per user and resource per 5 minutes;
- report exports;
- assistant queries, as a hash of the question, not its text.

Entries hold identifiers only, never measurement values. Administrators read the log at
`GET /api/admin/audit` and on the **Users & audit log** page.

## Transport and headers

- **API responses:**
  - `Cache-Control: no-store` on all `/api` responses;
  - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`, except the interactive
    docs and PDFs;
  - `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
    `Cross-Origin-Resource-Policy: same-site` and a restrictive `Permissions-Policy`;
  - `Strict-Transport-Security` when cookies are marked Secure.
- **CORS:** allows credentials for the listed origins only.
- **Errors:** unhandled errors return the error envelope with CORS headers, never a stack trace.
- **TLS:** terminate it at a reverse proxy in any shared deployment and set
  `ASTRA_AUTH_COOKIE_SECURE=true`. The dashboard and the API must be served from the same site
  (for example `app.example.org` and `api.example.org`) for the `SameSite=Strict` cookie to be sent.

## Secrets

No secrets are committed. NASA and Anthropic keys are read only by the backend from the environment.
`httpx` request URLs (which carry NASA's `api_key` query parameter) are not logged.
`scripts/create_users.py dev` writes demo credentials to `backend/.dev-users.json`, which is
git-ignored, and refuses to run in production.

## Accounts

```bash
cd backend
.venv/Scripts/python scripts/create_users.py add alice --role flight_surgeon --name "Dr. A. Reyes"   # prompts for the password
.venv/Scripts/python scripts/create_users.py list
.venv/Scripts/python scripts/create_users.py dev     # local demo: one account per role, credentials in backend/.dev-users.json
```

## Limitations

- **Login throttle:** kept in process memory, so it is per API worker. Use a shared store (Redis)
  when running several.
- **Missing account features:** no multi-factor authentication and no self-service password reset
  (an administrator recreates the account).
- **Row-level access:** none. Every role with `health:read` sees the whole crew; a crew-member role
  limited to its own records would need filtering in every endpoint and in the WebSocket fan-out.
- **Audit log:** stored in the application database, with no tamper-evidence (hash chain or WORM
  storage). The read de-duplication is in memory.
- **Schema** *(phase 7)*: Alembic migrations (`backend/migrations`, baseline `0001`); production runs
  `alembic upgrade head` before deploying and the API refuses an out-of-date schema.
- **Hard lockout:** 5 failures lock an account for 15 minutes, so someone who knows a username can
  keep that account locked. Progressive backoff is the open fix.
- **Logs** *(phase 7)*: bound SQL parameters are never logged (`hide_parameters`); client-supplied
  `X-Request-ID` values are accepted only as plain tokens.
