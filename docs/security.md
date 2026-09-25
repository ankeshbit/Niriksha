# SECURITY.md

## 1. Purpose

This file defines the security rules for the NiriKsha backend (`backend/`).
It documents what is already enforced in code, so an AI coding agent (or a
human) does not regress these protections while adding features.

**Scope note:** these rules govern `backend/` only. The mobile app
(`mobile/`) is a native client, is not subject to CORS, and is out of scope
for this file — do not let backend security changes require a mobile
rebuild unless explicitly agreed.

This system supports legal enforcement action under the Legal Metrology
(Packaged Commodities) Rules, 2011. Evidence integrity and audit
traceability are not just security hygiene here — they are part of the
product's legal defensibility. Treat any change touching evidence,
findings, or audit logs as security-sensitive, not just a data change.

## 2. Authentication & Authorization

- Auth is JWT-based, issued and verified in `backend/auth_service.py`
  using `python-jose`, signed with `settings.SECRET_KEY` /
  `settings.ALGORITHM` (HS256).
- Passwords are hashed with `bcrypt` via `backend/auth_utils.py`
  (`hash_password` / `verify_password`). Never store or compare plaintext
  passwords, and never swap this for a weaker/faster hash.
- Role-based access control is enforced server-side via `RoleChecker` /
  `require_roles(...)` in `backend/auth_service.py`, and via
  `verify_inspection_access()` in `backend/main.py` for
  inspection-scoped resources. Roles in use: `ADMIN`, `SUPERVISOR`,
  `INSPECTOR`.
  - `ADMIN`: full access across all inspections (read, write, adjudicate,
    finalize).
  - `SUPERVISOR`: read/oversight access across all inspections; write
    access (modifying findings, uploading evidence, adjudicating) only
    when also the assigned inspector.
  - `INSPECTOR`: scoped strictly to inspections where
    `inspection.inspector_id == current_user.id`.
- Never trust a role or user ID sent from the client. Authorization
  decisions must be made server-side against the authenticated user
  resolved from the JWT (`get_current_user`), not from a client-supplied
  field.
- New endpoints that touch inspection data must call
  `verify_inspection_access()` (or an equivalent explicit check) — do not
  rely on the JWT alone as proof of authorization to a specific resource.

## 3. Secrets & Environment Variables

- All secrets come from environment variables via `backend/config.py`
  (`pydantic-settings`). **No secret has a hardcoded fallback value in
  source** — this was a real vulnerability that was fixed and must not be
  reintroduced:
  - `SECRET_KEY` has no default. Startup fails with a clear `ValueError`
    if it is missing or blank.
  - `SEED_OFFICER_PASSWORD` / `SEED_SUPERVISOR_PASSWORD` have no default.
    `backend/seed.py` raises a clear error rather than seeding an account
    with a guessable password or crashing opaquely inside `bcrypt`.
- Never commit `.env`. `.env.example` must only ever contain variable
  names and comments, never real-looking placeholder secrets (e.g. do not
  reintroduce something like `SECRET_KEY=dev_secret_key_...`).
- Use separate credentials/databases for development and production —
  see `DATABASE.md` for the Postgres-only rule.

## 4. Production Startup Invariants

`backend/config.py` fails application startup (not just logs a warning)
if, when `ENVIRONMENT=production`:

- `SECRET_KEY` is missing or blank.
- `SEED_OFFICER_PASSWORD` or `SEED_SUPERVISOR_PASSWORD` is missing.
- `DEBUG=True`.
- `CORS_ORIGINS` resolves to a wildcard (`*`).
- `DATABASE_URL` is missing, is SQLite, or is not a PostgreSQL URL (see
  `DATABASE.md`).

These are intentional fail-fast guards, not bugs. If a change would need
to weaken one of these to "make a feature work," stop and flag it instead
of relaxing the check.

## 5. CORS

- CORS is configured in `backend/main.py`. Native mobile clients (the
  Android APK) are not subject to CORS at all — CORS only governs
  browser-based callers.
- In development (`ENVIRONMENT != "production"`), a wildcard origin is
  permitted (`allow_origins=["*"]` with an open origin regex) so that
  browser-based dev tooling (e.g. Expo web) works without extra config.
- In production, wildcard origins are rejected at startup (see §4).
  `CORS_ORIGINS` must be an explicit comma-separated allowlist, and no
  open origin regex is used.
- `allow_credentials=True` must never be combined with an open/wildcard
  origin in production — that combination is what made the original CORS
  config exploitable (any site could make credentialed requests).
- When reflecting CORS headers manually (e.g. in exception handlers),
  only reflect an origin that is actually in the allowlist — do not echo
  back arbitrary request origins.

## 6. Input Validation

- Validate all user-controlled input server-side, even if the mobile app
  already validates it client-side — the API must not trust the client.
- Use Pydantic schemas (`backend/schemas.py`) for request/response
  validation; reject unexpected fields and invalid types rather than
  silently coercing them.

## 7. API Error Handling

- The global exception handler (`backend/main.py`,
  `global_exception_handler`) is the single place controlling what error
  detail reaches API callers. Do not add other places that return
  `str(exc)` or a traceback to the client.
- Behavior:
  - Full traceback is always logged server-side
    (`logger.error(..., exc_info=exc)` + `traceback.print_exc()`).
  - If `settings.DEBUG is True`: response includes the exception message
    (local/dev only).
  - If `settings.DEBUG is False` (required in production, see §4):
    response body is the generic `{"detail": "Internal Server Error"}`.
- The response contract (`status_code=500`, JSON key `detail`) must stay
  stable — the mobile app depends on this shape. If you need to change
  it, treat it as an API contract change (see `API.md`) and flag it
  first.
- Do not log secrets, tokens, or full password values anywhere,
  including in the exception logging path.

## 8. Data Protection & Evidence Integrity

- `ComplianceCheck.extracted_value` (original OCR text) is immutable by
  design — officer corrections are stored separately, never overwriting
  the original extraction. Do not "simplify" this into a single mutable
  field; the original/corrected distinction is a legal requirement, not
  redundancy.
- `AuditLog` (`backend/models.py`) is an append-only record of actions
  (`OCR_RUN`, `DECLARATION_VERIFIED`, `FINDING_ADJUDICATED`, etc.) tied to
  an actor, entity, and old/new value. Any new state-changing action on
  inspection data should write an audit log entry, not skip it for
  convenience.
- Finalized/completed inspections are protected: uploading or deleting
  evidence images against a completed/finalized inspection, or one with a
  generated report, must return `409 Conflict` (see the `DEF-02` guards
  in `backend/main.py`). Do not bypass this to make an edit "just work."
- The finalization gate blocks report generation (`409`) while any
  finding remains unadjudicated. Do not add a code path that finalizes or
  generates a report around this check.
- Use the SQLAlchemy ORM / parameterized queries for all DB access — no
  raw string-interpolated SQL.

## 9. AI Agent Rules

The coding agent must:

- Never reintroduce a hardcoded fallback for `SECRET_KEY`,
  `SEED_OFFICER_PASSWORD`, `SEED_SUPERVISOR_PASSWORD`, or any other
  secret.
- Never widen CORS to a wildcard-with-credentials configuration in
  production, and never remove the production startup checks in §4 to
  make local testing more convenient.
- Never disable or bypass `get_current_user`, `RoleChecker` /
  `require_roles`, or `verify_inspection_access` to make an endpoint
  "just work."
- Never return raw exception text, stack traces, or internal file paths
  in an API response when `DEBUG=False`.
- Never overwrite `ComplianceCheck.extracted_value` or otherwise erase
  the original OCR value when implementing corrections.
- Never add a path that finalizes an inspection or generates a report
  while unadjudicated findings remain, or that mutates evidence on a
  finalized/completed inspection.
- Never skip writing an `AuditLog` entry for a new state-changing action
  on inspection/finding data.
- Ask for clarification when a requested change conflicts with this
  file, rather than silently relaxing a rule to complete the task.