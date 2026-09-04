# NiriKsha Repository Cleanup Audit

**Audit Date:** September 2, 2026  
**Project:** NiriKsha — AI-Assisted Legal Metrology Packaged-Commodity Inspection System (SIH Prototype 2026)  
**Safety Status:** PRE-DELETION AUDIT COMPLETED. ZERO FILES MODIFIED OR DELETED.

---

## Executive Summary & Safety Confirmation

A complete repository-wide audit was performed covering all 2,757 project files, databases, build artifacts, tests, documentation, and dependencies across both the Python FastAPI backend and the React Native / Expo mobile application.

- **Automated Test Suite Status:** **77 / 77 passing automated tests** verified via `pytest tests/`.
- **TypeScript Static Verification:** **0 errors** verified via `mobile run ts:check` (`tsc --noEmit`).
- **Database Safety Isolation:** Verified active database (`legal_metrology.db`), historical backup (`legal_metrology_backup_before_demo_reset_20260902_005830.db`), and isolated pytest database (`test_legal_metrology.db`).
- **No changes have been executed:** All findings below are candidates for user review and approval.

---

## Repository statistics

### Core Project Overview
| Component | Metric | Notes |
| :--- | :--- | :--- |
| **Total Project Files (Root & Source)** | **2,757 files** | Excludes external SDKs/node_modules/venvs |
| **Total Project Size (Root & Source)** | **450.13 MB** | Project source, databases, media & artifacts |
| **Full Disk Footprint (with SDKs/Builds/Venvs)** | **~5,138.83 MB (~5.02 GB)** | Total directory size on local disk |

### Detailed Category Breakdown
| Category | File Count | Size (MB) | Tracked in Git? | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Source** (`backend/`) | 22 files | 0.32 MB | Yes | FastAPI app, rule engine, OCR, extraction, auth, migrations |
| **Mobile App** (`mobile/` src & android config) | 69 files | 7.51 MB | Yes | React Native, Expo screens, components, services, navigation |
| **Tests & Test Fixtures** (`tests/`) | 23 files | 0.79 MB | Yes | 77 pytest test items, conftest, 8 image fixtures, manual E2E |
| **Documentation & PRD** (`docs/`) | 20 files | 0.45 MB | Yes | Architecture, API, Setup, Testing, PRD (.docx & .txt), screenshots |
| **Database Schema** (`database/schema.sql`) | 1 file | 0.01 MB | Yes | Authoritative SQL DDL schema |
| **Active SQLite Database** (`legal_metrology.db`) | 1 file | 14.79 MB | No (`.gitignore`) | Live DB with 1 seeded demo inspection (`LM-2026-00001`) |
| **Historical Database Backup** (`legal_metrology_backup...db`) | 1 file | 14.79 MB | No (`.gitignore`) | Snapshot before demo reset (1,531 historical records) |
| **Pytest Database** (`test_legal_metrology.db`) | 1 file | 2.46 MB | No (`.gitignore`) | Temporary/isolated database for automated pytest suite |
| **Uploads Directory** (`uploads/`) | 1,802 files | 97.05 MB | No (`.gitkeep` only) | Physical product images & inspection uploads |
| **Generated Reports Directory** (`generated_reports/`) | 690 files | 5.34 MB | No (`.gitkeep` only) | Official PDF compliance reports (v1, v2, v3, v4) |
| **Stand-alone Prebuilt APK** (`LegalMetrology_Inspection_v1.0.apk`) | 1 file | 159.48 MB | No (`.gitignore`) | Standalone Android APK binary |
| **Android Tools ZIP** (`cmdline-tools.zip`) | 1 file | 146.47 MB | No (`.gitignore`) | Leftover unextracted archive from setup script |
| **Stitch UI Prototypes** (`stitch_screens/`) | 32 files | 0.62 MB | No (`.gitignore`) | Downloaded Stitch mockups/prototypes |
| **Utility Scripts** (`scripts/`) | 2 files | 0.01 MB | Yes | Android SDK setup & Stitch screen downloader |
| **Root Configs & Docs** (`.env`, `README.md`, etc.) | 5 files | 0.02 MB | Yes | Environment configs, `.gitignore`, project readme |

### Heavy External Dependencies (Ignored on Disk)
| Dependency / Cache Directory | File Count | Size (MB) | Purpose |
| :--- | :--- | :--- | :--- |
| `android-sdk/` | 21,962 files | 2,429.95 MB | Local Android SDK, build-tools, NDK, platforms |
| `mobile/node_modules/` | 38,177 files | 849.33 MB | Node.js runtime packages for Expo / React Native |
| `mobile/android/app/build/` | 1,181 files | 578.72 MB | Gradle compilation outputs & intermediate DEX/AAR caches |
| `venv/` | 10,101 files | 418.65 MB | **Primary active Python virtual environment** (all 77 tests pass) |
| `jdk-17/` | 488 files | 300.91 MB | Embedded OpenJDK 17 for Gradle/Android builds |
| `.venv/` | 4,809 files | 77.83 MB | **Redundant/incomplete secondary virtual environment** |
| `mobile/android/.gradle/` | 101 files | 9.05 MB | Local Gradle daemon cache |
| `.git/` | 308 files | 4.74 MB | Git repository history & objects |
| `.pytest_cache/` | 5 files | 0.01 MB | Pytest execution cache |

---

## Definitely safe to delete

| File | Size | Reason | Evidence |
| :--- | :--- | :--- | :--- |
| `cmdline-tools.zip` | 146.47 MB | Temporary downloaded archive from `scripts/setup_android_sdk.py`. | The contents were extracted to `android-sdk/cmdline-tools/latest`. The zip file is completely unused by application code, build scripts, and tests. Ignored by `.gitignore` (`*.zip`). |
| `scratch/` (temporary test/audit scripts) | ~0.05 MB | One-off scratch scripts created during analysis (`scratch/detailed_audit.py`, `scratch/check_uploads_and_reports.py`, etc.). | Not referenced in any module, build pipeline, or test suite. Ignored by `.gitignore`. |

---

## Generated/rebuildable files

| Path | Size | Reason | Safe to regenerate? |
| :--- | :--- | :--- | :--- |
| `mobile/android/app/build/` | 578.72 MB | Native Android build intermediate outputs, class files, and APK build caches. | **YES.** Automatically regenerated by running `npx expo run:android` or `./gradlew assembleDebug`. |
| `mobile/android/.gradle/` | 9.05 MB | Local Gradle daemon cache. | **YES.** Regenerated automatically on next Gradle task execution. |
| `mobile/.expo/` | 0.03 MB | Expo local dev server state and metro cache. | **YES.** Automatically regenerated when launching `npx expo start`. |
| `backend/__pycache__/` & `tests/__pycache__/` | ~0.40 MB | Python bytecode compilation cache (`*.pyc`). | **YES.** Regenerated automatically by Python interpreter. |
| `.pytest_cache/` | 0.01 MB | Pytest test session and failure tracking cache. | **YES.** Regenerated automatically on next `pytest` run. |
| `test_legal_metrology.db` | 2.46 MB | Isolated SQLite database generated during pytest runs. | **YES.** The test fixture in `tests/conftest.py` automatically initializes and creates this database during test execution. |
| `generated_reports/` (283 orphan PDF files from previous test iterations) | ~2.20 MB | Test PDFs generated during development iterations that are not referenced in the active demo database. | **YES.** Reports can be regenerated at any time via the statutory PDF report generation endpoint `/api/inspections/{id}/report/pdf`. |
| `mobile/node_modules/` | 849.33 MB | Installed npm packages. | **YES.** Can be reinstalled with `npm install` inside `mobile/`. |

---

## Possible duplicates/obsolete files

| File | Reason | Evidence | Recommendation |
| :--- | :--- | :--- | :--- |
| `.venv/` | Redundant secondary virtual environment (77.83 MB, 4,809 files). | The active environment is `venv/` (418.65 MB), which contains all required dependencies (OpenCV, Tesseract, Pillow, PyPDF, ReportLab, FastAPI) and where all 77 pytest tests pass. `.venv/` is incomplete (missing `PIL`, `pypdf`, etc.). | **Delete `.venv/`** to reclaim ~78 MB and prevent virtual environment confusion. |
| `LegalMetrology_Inspection_v1.0.apk` | Standalone pre-built Android release binary (159.48 MB) in repository root. | Not tracked in git (`*.apk` in `.gitignore`). Not needed for running backend or mobile dev servers. | **User Review:** Delete if APK is not actively being tested on physical hardware, or move to external release storage. |
| `stitch_screens/` | Downloaded HTML UI prototype files and design exports (0.62 MB, 32 files). | Generated via `scripts/download_screens.js` during initial UI design phase. All UI is now implemented in TypeScript (`mobile/src/screens/`). Tracked screenshots exist in `docs/screenshots/`. | **Safe to delete / archive.** |
| `legal_metrology_backup_before_demo_reset_20260902_005830.db` | Pre-demo database backup (14.79 MB) containing 1,531 historical test inspections. | Created prior to running `backend/seed_demo_inspection.py`. Not referenced by active FastAPI backend (which points to `legal_metrology.db`). | **Keep as backup or archive** outside repository root if disk cleanup is desired. |
| `docs/prd/extracted_prd.txt` | Plain text duplicate of `docs/prd/Legal_Metrology_MVP_PRD.docx` (26.3 KB). | Extracted for fast developer text inspection during development. Both are tracked in git. | **Retain:** Keep both as lightweight documentation context. |

---

## Potentially unused source files

| File | Referenced? | Dynamic risk | Recommendation |
| :--- | :--- | :--- | :--- |
| `scripts/download_screens.js` | Standalone script (11.8 KB). | No dynamic risk. Used during Stitch UI design synchronization. | **Retain:** Kept in `scripts/` as a design synchronization utility. |
| `scripts/setup_android_sdk.py` | Standalone setup script (779 B). | No dynamic risk. Used for one-time developer machine SDK setup. | **Retain:** Kept in `scripts/` for reproducible environment setup. |
| `backend/schema_migration.py` | CLI migration script (1.6 KB). | No dynamic risk. Idempotent DDL helper for adding `email` and `phone` columns. | **Retain:** Kept as a safe migration utility. |
| `tests/create_fixtures.py` | Standalone test image generator (4.7 KB). | No dynamic risk. Generates test image fixtures in `tests/fixtures/`. | **Retain:** Essential for regenerating synthetic package images. |
| `tests/manual_e2e.py` | Standalone manual verification script (4.2 KB). | No dynamic risk. Provides interactive CLI verification of OCR and report generation. | **Retain:** Useful manual diagnostic tool. |
| `tests/qa_hardening_audit.py` | Standalone QA audit script (7.3 KB). | No dynamic risk. Validates system invariants, rule deterministic outputs, and report structure. | **Retain:** Hardening audit tool. |

---

## Dependency candidates

### Python Dependencies (`backend/requirements.txt`)
| Dependency | Used? | Evidence | Recommendation |
| :--- | :--- | :--- | :--- |
| `fastapi>=0.109.0` | **YES** | Imported across 12 files in `backend/` and `tests/`. | **Retain** (Core API) |
| `uvicorn[standard]>=0.27.0` | **YES** | Primary ASGI server used in CLI startup (`uvicorn backend.main:app`). | **Retain** (Core Server) |
| `pydantic>=2.6.0` | **YES** | Data validation in `backend/schemas.py`, `rule_engine/models.py`. | **Retain** (Core Validation) |
| `pydantic-settings>=2.1.0` | **YES** | Settings configuration in `backend/config.py`. | **Retain** (Core Config) |
| `sqlalchemy>=2.0.25` | **YES** | ORM models and database engine in `backend/database.py`, `backend/models.py`. | **Retain** (Core ORM) |
| `python-multipart>=0.0.9` | **YES** | Required by FastAPI for handling multipart form uploads (`UploadFile`, `File(...)`). | **Retain** (Image Uploads) |
| `python-jose[cryptography]>=3.3.0` | **YES** | JWT token generation and verification in `backend/auth_service.py`. | **Retain** (Authentication) |
| `passlib[bcrypt]>=1.7.4` | **YES** | Password hashing abstraction in `backend/auth_utils.py`. | **Retain** (Security) |
| `bcrypt>=4.0.1,<4.2.0` | **YES** | Direct password hashing implementation. | **Retain** (Security) |
| `python-dotenv>=1.0.1` | **YES** | Environment variable management for `.env` loading. | **Retain** (Config) |
| `httpx>=0.26.0` | **YES** | Fast HTTP client for FastAPI `TestClient` across test suite. | **Retain** (Testing / Client) |
| `pytest>=8.0.0` | **YES** | Automated test runner (77 automated test items). | **Retain** (Test Framework) |
| `reportlab>=4.0.0` | **YES** | Statutory inspection report PDF generation in `backend/report_service.py`. | **Retain** (PDF Engine) |
| `opencv-python>=4.8.0` | **YES** | Blur detection, glare detection, bounding box crops in `backend/image_quality.py`. | **Retain** (CV Pipeline) |
| `numpy>=1.24.0` | **YES** | Array manipulation for OpenCV and image quality scoring. | **Retain** (CV Engine) |
| `Pillow>=10.0.0` | **YES** | Image processing for OCR and report PDF embedding. | **Retain** (Image Processing) |
| `pypdf>=4.0.0` | **YES** | PDF verification in test suite (`tests/test_e2e_mobile_workflow.py`, `test_phase5.py`). | **Retain** (PDF Verification) |
| `pytesseract>=0.3.10` | **YES** | OCR text extraction in `backend/ocr_service.py`. | **Retain** (OCR Engine) |

*Summary:* 100% of Python dependencies in `backend/requirements.txt` are actively required and used. No unused Python dependencies exist.

### Mobile npm Dependencies (`mobile/package.json`)
| Dependency | Used? | Evidence | Recommendation |
| :--- | :--- | :--- | :--- |
| `@expo/metro-runtime` | **YES** | Metro runtime for development bundling. | **Retain** |
| `@expo/vector-icons` | **YES** | MaterialIcons, Feather, Ionicons across all screens and components. | **Retain** |
| `@react-navigation/native` | **YES** | Core navigation stack in `AppNavigator.tsx`. | **Retain** |
| `@react-navigation/native-stack` | **YES** | Native stack navigation for all 10 app screens. | **Retain** |
| `expo` | **YES** | Expo framework SDK 51. | **Retain** |
| `expo-camera` | **YES** | Camera capture in `CaptureImagesScreen.tsx`. | **Retain** |
| `expo-file-system` | **YES** | PDF report file downloading and storage. | **Retain** |
| `expo-image-picker` | **YES** | Package photo selection from gallery. | **Retain** |
| `expo-secure-store` | **YES** | Secure storage for JWT auth tokens in `authStorage.ts`. | **Retain** |
| `expo-sharing` | **YES** | Native OS share sheet for PDF reports in `ReportPreviewScreen.tsx`. | **Retain** |
| `expo-status-bar` | **YES** | Status bar styling. | **Retain** |
| `react`, `react-dom`, `react-native` | **YES** | React Native core runtime. | **Retain** |
| `react-native-safe-area-context` | **YES** | Device safe area insets handling. | **Retain** |
| `react-native-screens` | **YES** | Native screen performance container. | **Retain** |
| `react-native-web` | **YES** | Web preview capability. | **Retain** |
| `@babel/core`, `@types/react`, `typescript` | **YES** | TypeScript typechecking and compilation. | **Retain** |

*Summary:* 100% of npm dependencies in `mobile/package.json` are actively required. No unused dependencies exist.

---

## Required files (Must Remain)

The following core files and directories must NOT be deleted:
1. **`backend/`**: `main.py`, `models.py`, `schemas.py`, `database.py`, `config.py`, `auth.py`, `auth_service.py`, `auth_utils.py`, `image_quality.py`, `ocr_service.py`, `extraction_service.py`, `report_service.py`, `supabase_storage.py`, `seed.py`, `seed_demo_inspection.py`, `schema_migration.py`, `rule_engine/` (`engine.py`, `models.py`, `registry.py`, `__init__.py`).
2. **`mobile/`**: `App.tsx`, `index.ts`, `app.json`, `tsconfig.json`, `package.json`, `package-lock.json`, `src/components/`, `src/screens/`, `src/navigation/`, `src/services/`, `src/theme/`, `assets/`, `android/`.
3. **`tests/`**: `conftest.py`, `create_fixtures.py`, `manual_e2e.py`, `qa_hardening_audit.py`, `test_e2e_mobile_workflow.py`, `test_final_corrections.py`, `test_foundation.py`, `test_phase2.py`, `test_phase3.py`, `test_phase4.py`, `test_phase5.py`, `test_phase6.py`, `tests/fixtures/` (all 8 images).
4. **`database/schema.sql`**: Authoritative database schema DDL.
5. **`legal_metrology.db`**: Active primary SQLite database with demo inspection `LM-2026-00001`.
6. **`docs/`**: `api.md`, `architecture.md`, `setup.md`, `testing.md`, `prd/Legal_Metrology_MVP_PRD.docx`, `prd/extracted_prd.txt`, `screenshots/` (all 13 UI screenshots).
7. **`generated_reports/.gitkeep` & `uploads/.gitkeep`**: Git directory keepers.
8. **`.env` & `.env.example` & `.gitignore` & `README.md`**: Essential repository metadata and configs.
9. **`venv/`**: Active Python virtual environment with all dependencies and 77 passing tests.

---

## Recommended cleanup

> [!IMPORTANT]
> **NONE of the commands below have been executed.** They are listed here for your explicit review and approval.

### Phase 1: High-Yield Immediate Safe Deletions (~384 MB savings)
Deletes obsolete downloaded archives, redundant virtualenv, and temporary scratch tools without touching any tracked code:

```powershell
# 1. Remove leftover unextracted Android SDK zip archive (~146.5 MB)
Remove-Item -Path "cmdline-tools.zip" -Force -ErrorAction SilentlyContinue

# 2. Remove redundant secondary virtual environment (.venv) (~77.8 MB)
# (Active environment is venv/ with all 77 passing tests)
Remove-Item -Recurse -Force -Path ".venv" -ErrorAction SilentlyContinue

# 3. Remove Stitch prototype design files (~0.62 MB)
Remove-Item -Recurse -Force -Path "stitch_screens" -ErrorAction SilentlyContinue

# 4. Remove standalone pre-built Android APK binary (~159.5 MB) [OPTIONAL - USER CONFIRMATION]
Remove-Item -Path "LegalMetrology_Inspection_v1.0.apk" -Force -ErrorAction SilentlyContinue

# 5. Clean scratch directory used during auditing
Remove-Item -Recurse -Force -Path "scratch" -ErrorAction SilentlyContinue
```

### Phase 2: Build Cache & Intermediate Rebuildable Cleanup (~588 MB savings)
Deletes generated compilation outputs that are recreated automatically during development:

```powershell
# 1. Clean Gradle native Android build cache (~578.7 MB)
Remove-Item -Recurse -Force -Path "mobile\android\app\build" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force -Path "mobile\android\.gradle" -ErrorAction SilentlyContinue

# 2. Clean Expo / Metro cache (~0.03 MB)
Remove-Item -Recurse -Force -Path "mobile\.expo" -ErrorAction SilentlyContinue

# 3. Clean Python bytecode and Pytest caches (~0.4 MB)
Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force
Remove-Item -Recurse -Force -Path ".pytest_cache" -ErrorAction SilentlyContinue
```

### Total Potential Space Reclaimed
- **Phase 1 (Safe Artifacts & Redundant venv):** **~384.4 MB**
- **Phase 2 (Build & Intermediate Caches):** **~588.2 MB**
- **Combined Storage Savings:** **~972.6 MB (~0.95 GB)**

---

## Next Steps

Awaiting user approval before executing any cleanup commands.
