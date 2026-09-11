# NiriKsha — Deployment & Infrastructure Guide

**Project:** NiriKsha (SIH 2026 Problem Statement 26034)  
**Architecture:** React Native / Expo Mobile Client + FastAPI Backend + Neon PostgreSQL

---

## 1. Database Infrastructure Requirements

### STRICT DATABASE INVARIANT: PostgreSQL ONLY
NiriKsha is architected exclusively for PostgreSQL. SQLite is strictly forbidden across all environments (production, staging, and automated testing).

### Production Database (Neon PostgreSQL)
- **Host:** Neon Cloud Serverless PostgreSQL (`c-5.us-east-2.aws.neon.tech`).
- **Connection Scheme:** `postgresql+psycopg://...` or `postgresql://...`
- **TLS/SSL:** Enforced (`sslmode=require&channel_binding=require`).
- **Connection Pooling:** Enabled via Neon pooler endpoint (`-pooler`).

### Test Database (Separate Neon PostgreSQL)
- **Requirement:** A completely separate PostgreSQL database instance must be allocated for automated tests.
- **Safety Pre-Condition:** `TEST_DATABASE_URL` must point to a distinct database from `DATABASE_URL`. Hard safety assertions in `tests/conftest.py` immediately abort if the normalized hostname or database name matches production.

---

## 2. Environment Variables Configuration

| Variable | Scope | Description | Example / Allowed Values |
|---|---|---|---|
| `DATABASE_URL` | Backend | Production Neon PostgreSQL connection string | `postgresql://neondb_owner:***@ep-super-sky-ayqsbq9r-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require` |
| `TEST_DATABASE_URL` | Backend/Test | Dedicated Neon PostgreSQL test connection string | `postgresql://neondb_owner:***@ep-jolly-shape-ayqkx0yp-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require` |
| `SECRET_KEY` | Backend | Cryptographic secret for signing JWT tokens | 64+ char random hex string |
| `ALGORITHM` | Backend | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Backend | Token validity duration | `480` (8 hours) |
| `ENVIRONMENT` | Backend | Execution environment | `production` / `development` / `testing` |
| `DEBUG` | Backend | FastApi debug mode | `False` |
| `EXPO_PUBLIC_API_URL` | Mobile | Public HTTPS backend URL baked into client bundle | `https://api.niriksha.gov.in` |
| `MAX_OCR_DIMENSION` | Backend | Preprocessing downscale cap for PaddleOCR | `1024` |

---

## 3. Backend Deployment (Render / Railway / Cloud Run / VPS)

### Build & Run Commands
```bash
# 1. Install dependencies
pip install -r backend/requirements.txt

# 2. Verify schema and apply migrations to Neon PostgreSQL
python -m backend.schema_migration

# 3. Start high-performance ASGI server
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Health Check Verification
```bash
curl -f https://your-backend-host/api/health
# Response: {"status": "ok", "service": "NiriKsha Legal Metrology Inspection API", "database_backend": "postgresql"}
```

---

## 4. Mobile Client Deployment (Expo / EAS)

### 1. Build Verification
```powershell
cd mobile
npm install
npm run ts:check
```

### 2. Configure EAS Cloud Build
```powershell
eas login
eas build:configure
```

### 3. Generate Android APK (Field Inspector Testing)
```powershell
$env:EXPO_PUBLIC_API_URL = "https://your-api.example.com"
eas build --platform android --profile preview
```

### 4. Generate Production Release (Google Play AAB)
```powershell
$env:EXPO_PUBLIC_API_URL = "https://your-api.example.com"
eas build --platform android --profile production
```

---

## 5. Offline Field Inspection Support
- Field inspectors can capture images and metadata in areas without cellular connectivity.
- Data is stored securely in encrypted local storage (`AsyncStorage` / `SecureStore`).
- Once connectivity is restored, the mobile client synchronizes drafts with the central Neon PostgreSQL repository and triggers automated OCR/rule compliance evaluation.