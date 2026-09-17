# NiriKsha — Environment Setup & Installation Guide

> **NiriKsha — SIH Prototype 2026 (For demonstration and evaluation purposes only)**

This document provides step-by-step instructions to set up, configure, and execute the **NiriKsha** inspection platform across both backend and mobile layers.

---

## 1. Prerequisites

Ensure the following tools are installed on your host development workstation:

| Component | Required Version | Verification Command |
|---|---|---|
| **Python** | 3.10+ | `python --version` |
| **Node.js** | 18.x or 20.x | `node --version` |
| **npm** | 9.x or 10.x | `npm --version` |
| **Git** | 2.x+ | `git --version` |
| **Java JDK** *(optional, for Android native build)* | OpenJDK 17 | `java -version` |
| **Android SDK** *(optional, for native APK build)* | API Level 34 | `sdkmanager --version` |

---

## 2. Repository Preparation

Clone the repository and inspect the directory structure:

```bash
git clone https://github.com/ankeshbit/SIH.git
cd SIH
```

---

## 3. Backend Setup (FastAPI & Python)

### 3.1 Create and Activate Virtual Environment

**On Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.2 Install Dependencies

Install all required backend packages from `backend/requirements.txt`:

```bash
pip install -r backend/requirements.txt
```

### 3.3 Configure Environment Variables

Copy the provided environment template to `.env`:

```bash
# Windows PowerShell
Copy-Item .env.example .env

# macOS / Linux
cp .env.example .env
```

By default, `.env` is configured to use the local zero-configuration SQLite database (`sqlite:///./legal_metrology.db`). For local evaluation, no additional credentials are required.

### 3.4 Start the FastAPI Backend Server

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Once started, verify the backend endpoints:
- **Interactive OpenAPI Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Alternative ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check API**: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)
- **Static Inspection Portal**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 4. Mobile Application Setup (React Native / Expo)

### 4.1 Install Node Dependencies

Navigate to the `mobile/` directory and install dependencies:

```bash
cd mobile
npm install
```

### 4.2 Verify TypeScript Compilation

Run the static TypeScript type checker to verify code correctness:

```bash
npm run ts:check
```

### 4.3 Start the Expo Metro Bundler

```bash
npm run start
```

This launches the interactive Expo developer menu. You can:
- Press `w` to open the web version in your default browser.
- Press `a` to run on a connected Android emulator or device via ADB.
- Scan the displayed QR code with the **Expo Go** app on an Android device connected to the same local network.

### 4.4 Configuring API Host for Physical Android Devices

When testing on a physical Android device or emulator, `127.0.0.1` refers to the device itself. Update `mobile/src/services/api.ts` with your workstation's LAN IP:

```typescript
// mobile/src/services/api.ts
const API_BASE_URL = Platform.OS === 'android' 
  ? 'http://10.0.2.2:8000'    // Android Emulator host loopback
  : 'http://192.168.1.X:8000'; // Replace with workstation LAN IP for physical device
```

And start the FastAPI server listening on all interfaces:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 5. Seed Demonstration Credentials

The application includes a pre-seeded demonstration inspector account in `backend/seed.py`:

| Role | Officer ID | Password | Designation | Zone |
|---|---|---|---|---|
| **Field Inspecting Officer** | `DOCA-INSP-842` | `admin123` | Senior Inspector (Legal Metrology) | Northern Zone - Delhi HQ |

---

## 6. Database Configuration: Neon PostgreSQL

NiriKsha is architected exclusively for PostgreSQL. SQLite is strictly forbidden across all environments.

1. Create a PostgreSQL project on [Neon](https://neon.tech).
2. Configure `.env` with your Neon PostgreSQL connection string:
   ```dotenv
   DATABASE_URL=postgresql+psycopg://user:password@host.neon.tech/dbname?sslmode=require&channel_binding=require
   TEST_DATABASE_URL=postgresql+psycopg://user:password@host.neon.tech/dbname_test?sslmode=require&channel_binding=require
   ```
3. Run migrations to initialize the schema:
   ```bash
   python -m backend.schema_migration
   ```
4. Start the FastAPI server. The application automatically verifies PostgreSQL connectivity during startup.

---

## 7. Environment Variable Reference

| Variable | Type | Default Value | Description |
|---|---|---|---|
| `PROJECT_NAME` | String | `"Legal Metrology Packaged-Commodity Inspection System"` | Application title. |
| `ENVIRONMENT` | String | `"development"` | Runtime environment mode. |
| `DEBUG` | Boolean | `True` | Enables verbose error messages and tracebacks. |
| `DATABASE_URL` | String | (Required) | Neon PostgreSQL connection URI (`postgresql+psycopg://...`). |
| `TEST_DATABASE_URL` | String | (Required for tests) | Dedicated Neon PostgreSQL test connection URI. |
| `SECRET_KEY` | String | (Pre-configured dev key) | Secret key for signing HS256 JWT tokens. |
| `ALGORITHM` | String | `"HS256"` | JWT token hashing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Integer | `1440` | JWT expiration duration in minutes (24 hours). |
| `UPLOAD_DIR` | String | `"./uploads"` | Directory for stored product images (must be on persistent disk). |
| `REPORTS_DIR` | String | `"./generated_reports"` | Directory for generated statutory PDF reports (must be on persistent disk). |
