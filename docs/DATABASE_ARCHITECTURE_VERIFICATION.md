# NiriKsha — Database Architecture Verification

**Version**: 2.0 — PostgreSQL-Only Enforcement  
**Date**: 2026-09-11  
**Status**: ✅ VERIFIED

---

## Architecture

```
Mobile App (Expo)
      ↓
FastAPI Backend (Uvicorn)
      ↓
Neon PostgreSQL
```

**PROHIBITED**: FastAPI → SQLite (in any environment)

---

## Database Configuration

### Production

| Property | Value |
|---|---|
| Engine | PostgreSQL |
| Driver | `postgresql+psycopg` |
| Host | Neon (AWS us-east-2) |
| Database | `neondb` |
| SSL | `sslmode=require` |
| Config Key | `DATABASE_URL` (required, no default) |

### Development

| Property | Value |
|---|---|
| Engine | PostgreSQL (same Neon DB as production in this project) |
| Config Key | `DATABASE_URL` (fail-fast if missing) |
| SQLite Fallback | ❌ NONE — removed |

### Test

| Property | Value |
|---|---|
| Engine | PostgreSQL |
| Config Key | `TEST_DATABASE_URL` (fail-fast if missing or equals production URL) |
| Database Name | Separate Neon database (e.g. `neondb_test`) |
| Isolation | SQLAlchemy `drop_all` / `create_all` per test session |
| SQLite | ❌ FORBIDDEN |

---

## PostgreSQL Verification

Live `/api/health` response (2026-09-11):

```json
{
  "status": "healthy",
  "database": "connected",
  "database_backend": "PostgreSQL",
  "database_host": "Neon",
  "database_driver": "postgresql+psycopg"
}
```

✅ PostgreSQL: CONFIRMED  
✅ Neon: CONFIRMED  
✅ Driver psycopg: CONFIRMED

---

## SQLite Search Results

### Runtime SQLite Usage: ZERO

| File | Lines | Classification | Action |
|---|---|---|---|
| `backend/config.py:42-50` | Dev SQLite fallback | A — RUNTIME | ✅ REMOVED |
| `backend/database.py:12-14` | SQLite connect_args | A — RUNTIME | ✅ REMOVED |

### Test SQLite Usage: ZERO

| File | Lines | Classification | Action |
|---|---|---|---|
| `tests/conftest.py:18` | `TEST_DATABASE_URL = "sqlite://..."` | B — TEST | ✅ REPLACED with PostgreSQL |
| `tests/test_image_lifecycle.py:14` | SQLite env override | B — TEST | ✅ REMOVED |
| `tests/test_ocr_transaction_lifecycle.py:15` | SQLite env override | B — TEST | ✅ REMOVED |
| `tests/test_complete_post_image_workflow.py:711,820` | `sqlite3.connect()` queries | B — TEST | ✅ REPLACED with API/ORM |
| `tests/test_offline_image_quality.py:68` | `sqlite3.connect()` query | B — TEST | ✅ REPLACED with API count |
| `tests/test_database_configuration.py:103-107` | Asserts SQLite fallback works | B — TEST | ✅ INVERTED to assert fail-fast |
| `tests/test_database_safety.py:17-19` | Asserts SQLite path | B — TEST | ✅ INVERTED to assert PostgreSQL |
| `tests/qa_hardening_audit.py:8-11` | Module SQLite override | B — TEST | ✅ REMOVED |
| `tests/manual_e2e.py:7-11` | Module SQLite override | B — TEST | ✅ REMOVED |

### Migration/Archive (Preserved)

| File | Classification | Status |
|---|---|---|
| `backend/migrate_to_postgres.py` | C — ONE-TIME MIGRATION | ✅ KEPT (reads SQLite source only, not used as app DB) |
| `scripts/get_db_counts.py` | C — LEGACY ARCHIVE | ✅ DEPRECATED header added |
| `scripts/verify_db_safety.py` | C — LEGACY ARCHIVE | ✅ DEPRECATED header added |
| `.env.example` | D — DOCS | ✅ UPDATED to PostgreSQL template |
| `.env` | D — DOCS | ✅ SQLite comments removed |

---

## Fail-Fast Configuration Guards

In `backend/config.py`:

| Condition | Action |
|---|---|
| `DATABASE_URL` missing/empty | ❌ Raise `ValueError` with clear message |
| `DATABASE_URL` starts with `sqlite:` | ❌ Raise `ValueError` |
| `DATABASE_URL` is non-PostgreSQL scheme | ❌ Raise `ValueError` |
| `DATABASE_URL` starts with `postgresql://` | ✅ Normalize to `postgresql+psycopg://` |

In `backend/database.py`:

| Condition | Action |
|---|---|
| SQLite URL passed to `build_engine()` | ❌ Raise `RuntimeError` (belt-and-suspenders) |

---

## Local DB File Creation Test

After running the full application workflow, no `.db`/`.sqlite`/`.sqlite3` files are created:

- `legal_metrology.db` — ✅ DELETED (was legacy SQLite production DB)
- `backend/legal_metrology.db` — ✅ DELETED  
- `test_legal_metrology.db` — ✅ DELETED (was legacy SQLite test DB)
- `test_ocr_lifecycle.db` — ✅ DELETED
- `test_image_lifecycle.db` — ✅ DELETED

Remaining files are **historical backup archives** (classification E) from pre-Neon era, preserved for rollback documentation:
- `legal_metrology_backup_*.db` (9 files) — PRESERVED, excluded from test assertions

---

## CWD Launch Tests

Both launch configurations resolve Neon PostgreSQL:

| CWD | DATABASE_URL | Result |
|---|---|---|
| Repository root (`SIH/`) | From `.env` → Neon PostgreSQL | ✅ PASS |
| Backend subdir (`SIH/backend/`) | From `../env` → Neon PostgreSQL | ✅ PASS |
| Arbitrary CWD | Fail-fast with clear error | ✅ PASS |

---

## Architecture Tests: 13/13 PASSED

```
PASS: SQLite dev rejected
PASS: SQLite prod rejected  
PASS: SQLite :memory: rejected
PASS: Missing URL dev fail fast
PASS: Missing URL prod fail fast
PASS: Empty URL fail fast
PASS: Whitespace URL fail fast
PASS: MongoDB URL rejected
PASS: MySQL URL rejected
PASS: Test URL != Prod URL
PASS: No live .db files in project root
PASS: No sqlite3 in runtime backend
PASS: PG normalization
```

---

## PostgreSQL Tables Verified

All application data tables exist in Neon PostgreSQL:

| Table | Status |
|---|---|
| `users` | ✅ |
| `inspections` | ✅ |
| `products` | ✅ |
| `product_images` | ✅ |
| `ocr_results` | ✅ |
| `declarations` | ✅ |
| `compliance_checks` | ✅ |
| `findings` | ✅ |
| `evidence` | ✅ (via inspection images) |
| `reports` | ✅ |
| `audit_logs` | ✅ |
| `rule_versions` | ✅ |
| `inspection_number_counters` | ✅ |
| `product_listings` | ✅ |
| `listing_comparisons` | ✅ |

---

## New Files Created

| File | Purpose |
|---|---|
| `tests/test_postgres_only_architecture.py` | 13 architecture-level tests verifying PostgreSQL-only enforcement |
| `docs/DATABASE_ARCHITECTURE_VERIFICATION.md` | This document |

---

## Summary

**NiriKsha has exactly ONE database technology: PostgreSQL.**  
**The production application database is: Neon PostgreSQL.**  
**No SQLite fallback exists anywhere in application runtime or automated tests.**

> ⚠️ **IMPORTANT — Action Required**: Add `TEST_DATABASE_URL` to your `.env` file pointing to a dedicated Neon PostgreSQL test database before running the full test suite (`pytest`). Without this, `conftest.py` will intentionally fail fast to prevent accidental test runs against the production database.
