# NiriKsha — PostgreSQL & Neon Migration Audit

**Audit Date**: September 8, 2026  
**Auditor**: Antigravity System Audit & Migration Agent  
**Source Architecture**: FastAPI + SQLAlchemy 2.0 + SQLite (`legal_metrology.db`)  
**Target Architecture**: FastAPI + SQLAlchemy 2.0 + PostgreSQL (`psycopg` v3 driver) + Neon Serverless PostgreSQL  
**Statutory Reference**: Legal Metrology Act, 2009 & Legal Metrology (Packaged Commodities) Rules, 2011  

---

## 1. Executive Summary

This comprehensive audit evaluates every component of the current NiriKsha database layer to guarantee a zero-downtime, non-destructive migration from SQLite to PostgreSQL hosted on Neon.

The NiriKsha backend was architected with clean SQLAlchemy 2.0 ORM abstractions, which significantly minimizes dialect incompatibility. However, specific differences between SQLite's dynamic loose typing and PostgreSQL's strict typing, serverless pooling nuances in Neon, and test isolation requirements must be systematically addressed.

---

## 2. Component-by-Component Audit Findings

### 2.1 Engine & Connection Configuration (`backend/database.py`)
- **Current Implementation**:
  - Checks `if settings.DATABASE_URL.startswith("sqlite"): connect_args = {"check_same_thread": False}`.
  - Non-SQLite branch configures pooling: `pool_size=10, max_overflow=20, pool_pre_ping=True, pool_recycle=300`.
- **PostgreSQL / Neon Compatibility**:
  - **psycopg (v3) Driver**: Target URL format must be `postgresql+psycopg://user:password@host/dbname?sslmode=require`.
  - **Neon Serverless Pooling**: Neon uses PgBouncer connection pooling. When connecting through a transaction pooler or autoscaling serverless branch, `pool_pre_ping=True` and `pool_recycle=300` are essential to prevent stale connections during compute wake-up.
  - **Dialect Guard**: `connect_args={"check_same_thread": False}` must only ever be passed when `url.drivername.startswith("sqlite")`.

### 2.2 Environment Configuration (`backend/config.py` & `.env`)
- **Current Implementation**:
  - `DATABASE_URL: str = "sqlite:///./legal_metrology.db"` default in `Settings`.
- **PostgreSQL / Neon Compatibility**:
  - `DATABASE_URL` must be configurable via environment variable (`.env` or system environment).
  - In production, missing or unconfigured `DATABASE_URL` must fail loudly with a clear, descriptive error rather than silently falling back to a local SQLite database.
  - Production Neon credentials must never be committed to source control or logged in plain text.

### 2.3 ORM Data Models (`backend/models.py`)

All 12 SQLAlchemy models were audited for column types, constraints, and relationships:

| Model | Table Name | Key Column Types | PostgreSQL Compatibility Findings & Required Actions |
| :--- | :--- | :--- | :--- |
| `User` | `users` | `String(36)`, `String(50)`, `DateTime`, `String(255)` | Fully compatible. `String(36)` generates `VARCHAR(36)`. `DateTime` generates `TIMESTAMP WITHOUT TIME ZONE`. |
| `Inspection` | `inspections` | `String(36)`, `String(50)`, `String(100)`, `Text`, `DateTime` | Fully compatible. `client_draft_id` is indexed `VARCHAR(100)`. `inspection_number` has `unique=True, index=True`. |
| `Product` | `products` | `String(36)`, `String(255)`, `DateTime` | Fully compatible. 1:1 foreign key `inspection_id` has `unique=True`. |
| `ProductImage` | `product_images` | `String(36)`, `Integer`, `Float`, `Text` | Fully compatible. `quality_metadata_json` is `Text`. In PG `TEXT` handles arbitrary serialized JSON. |
| `OCRResult` | `ocr_results` | `String(36)`, `Float`, `Text` | Fully compatible. `bounding_boxes_json` stored as `Text`. |
| `Declaration` | `declarations` | `String(36)`, `Boolean`, `Float`, `Text`, `DateTime` | **Boolean Compatibility**: SQLite stores booleans as integer 0/1; PostgreSQL has native `BOOLEAN`. SQLAlchemy ORM handles this automatically, but raw migration scripts must cast `0/1` to `False/True`. |
| `RuleVersion` | `rule_versions` | `String(36)`, `String(50)`, `Integer`, `Boolean`, `Text` | Fully compatible. `rule_code` is indexed. `is_active` is `Boolean`. |
| `ComplianceCheck` | `compliance_checks`| `String(36)`, `String(50)`, `Text`, `DateTime` | Fully compatible. Foreign keys point to `inspections.id` and `rule_versions.id`. |
| `Evidence` | `evidence` | `String(36)`, `Text`, `DateTime` | Fully compatible. `check_id` points to `compliance_checks.id`, `image_id` points to `product_images.id`. |
| `InspectorReview` | `inspector_reviews` | `String(36)`, `String(50)`, `Text`, `DateTime` | Fully compatible. Foreign keys to `compliance_checks.id` and `users.id`. |
| `AuditLog` | `audit_logs` | `String(36)`, `String(100)`, `Text`, `DateTime` | Fully compatible. `inspection_id` is nullable foreign key. |
| `Report` | `reports` | `String(36)`, `Integer`, `String(500)`, `Text`, `DateTime` | Fully compatible. `inspection_id` has `unique=True`. Note: Minor cosmetic dead code in property `download_url` cleaned up. |

### 2.4 Foreign Keys & Cascade Constraints
- In SQLite, foreign keys are disabled unless explicitly enabled via `PRAGMA foreign_keys = ON;`.
- In PostgreSQL, foreign keys are **strictly enforced on every statement**.
- Insertion order during migration must strictly follow the Directed Acyclic Graph (DAG):
  `users` + `rule_versions` → `inspections` → `products` + `product_images` → `ocr_results` → `declarations` → `compliance_checks` → `evidence` + `inspector_reviews` → `reports` + `audit_logs`.

### 2.5 Sequence & Sequential Number Generation
- Current inspection number generator:
  ```python
  def generate_inspection_number(db: Session) -> str:
      count = db.query(Inspection).count() + 1
      return f"LM-2026-{count:05d}"
  ```
- In PostgreSQL, `_inspection_number_lock` serializes access within a worker process. In multi-worker environments, concurrent transactions calling `count()` could potentially generate colliding numbers. However, `inspection_number` has a `UNIQUE` constraint, and `create_inspection` catches `IntegrityError` and retries.
- For maximum reliability on PostgreSQL, query `SELECT COALESCE(MAX(CAST(SUBSTRING(inspection_number FROM 9) AS INTEGER)), 0) FROM inspections` or count while retaining the `_inspection_number_lock`.

### 2.6 Timestamps & Datetime Handling
- SQLite stores datetimes as naive ISO-8601 strings (e.g. `'2026-09-04 18:53:09.445012'`).
- PostgreSQL stores them as `TIMESTAMP WITHOUT TIME ZONE`.
- Migration script must parse string representations into Python `datetime` objects before insertion so PostgreSQL does not reject invalid string formats.

### 2.7 Raw SQL & SQLite-Specific Syntax
- Audit scanned all occurrences of `text(...)` and raw SQL in the codebase:
  1. `backend/main.py:350`: `db.execute(text("SELECT 1"))` — Standard ANSI SQL, 100% portable.
  2. `backend/schema_migration.py:20`: `SELECT {column} FROM {table} LIMIT 0` — Standard ANSI SQL, 100% portable.
  3. `backend/schema_migration.py:60`: `CREATE INDEX IF NOT EXISTS ...` — Supported in PostgreSQL 9.5+.
- **Zero SQLite-specific PRAGMAs or functions** (e.g. `PRAGMA table_info`, `datetime('now')`, `last_insert_rowid()`) are used in production backend endpoints.

### 2.8 Search & String Matching Queries
- In `backend/main.py:149`: `Inspection.notes.like(f"%[client_draft_id:{client_draft_id}]%")`.
- SQLite `LIKE` is case-insensitive for ASCII; PostgreSQL `LIKE` is case-sensitive (`ILIKE` is case-insensitive).
- Because `[client_draft_id:...]` uses exact lowercase tags, `like` works identical across both dialects. For enhanced robustness, `ilike` can be used.

### 2.9 Test Environment & Neon Safety Guard (`tests/conftest.py`)
- Currently, tests strictly require `test_legal_metrology.db` and reject `legal_metrology.db`.
- **Critical Safety Guard for Neon**:
  - Tests must NEVER point to the production Neon connection string.
  - If `DATABASE_URL` contains `neon.tech` or `pooler.supabase.com` or production host, test session initialization must raise `RuntimeError("Tests cannot run against the production database.")` immediately.
  - Automated tests can continue using an isolated SQLite database (`test_legal_metrology.db`) for fast local CI/CD, or a dedicated ephemeral test database when run against PostgreSQL.

---

## 3. Compatibility Summary Matrix

| Feature / Pattern | SQLite Behavior | PostgreSQL / Neon Behavior | Action Required |
| :--- | :--- | :--- | :--- |
| Driver | Built-in `sqlite3` | Requires `psycopg` (v3) | Add `psycopg[binary]>=3.1.0` to `backend/requirements.txt` |
| Connection String | `sqlite:///./legal_metrology.db` | `postgresql+psycopg://...` | Configure in `.env`, validate in `config.py` |
| Primary Keys | String UUID (36 chars) | `VARCHAR(36)` | Zero model change needed; 100% compatible |
| JSON Fields | `Text` column | `Text` column (or `JSONB`) | Retain `Text` for zero drift with existing serialization |
| Booleans | Integer `0` / `1` | Native `BOOLEAN` (`true`/`false`) | Map `0/1` to `bool` during data migration |
| Foreign Keys | Disabled unless PRAGMA set | Strictly enforced on every operation | Migrate in topological DAG order |
| Pooling | Single-file locking | Neon PgBouncer pooler | Use `pool_pre_ping=True, pool_recycle=300` |
| Test Safety | Blocks `legal_metrology.db` | Must block production Neon URL | Enhance `tests/conftest.py` with Neon safety guard |
