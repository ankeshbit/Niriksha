# NiriKsha Technology Stack Audit

**Audit basis:** repository source, imports, package manifests, runtime configuration, native Android project, Dockerfile, migration code, and tests. Documentation was used only to locate candidates; a technology is marked active only where executable code/configuration confirms it.

## Technology Inventory

| Layer | Technology | Purpose | Status | Evidence |
|---|---|---|---|---|
| Mobile | Expo SDK 51 | React Native application framework and tooling | ACTIVE | `mobile/package.json`; `mobile/app.json`; `mobile/App.tsx` |
| Mobile | React Native 0.74.5 | Cross-platform native UI runtime | ACTIVE | `mobile/package.json`; `mobile/App.tsx` |
| Mobile | TypeScript 5.3 | Mobile source language and type checking | ACTIVE | `mobile/package.json`; `mobile/tsconfig.json`; `.tsx`/`.ts` sources |
| Mobile | React 18.2 | Component runtime | ACTIVE | `mobile/package.json`; `mobile/App.tsx` |
| Mobile | React Navigation 6 native stack | Screen navigation | ACTIVE | `mobile/src/navigation/AppNavigator.tsx`; `mobile/package.json` |
| Mobile | `react-native-safe-area-context` | Safe-area layout | ACTIVE | `mobile/App.tsx`; screen imports |
| Mobile | `react-native-screens` | Native navigation screen integration | ACTIVE | `mobile/package.json`; React Navigation native stack |
| Mobile | Expo Vector Icons / MaterialIcons, Feather, Ionicons | UI icons | ACTIVE | `mobile/package.json`; `mobile/src` icon imports |
| Mobile | Expo Image Picker | Camera and gallery image capture/selection | ACTIVE | `mobile/src/screens/CaptureImagesScreen.tsx`; `mobile/app.json` |
| Mobile | Expo Camera | Native camera permission/config integration | ACTIVE | `mobile/package.json`; `mobile/app.json`; generated Android Maven config |
| Mobile | Expo FileSystem | Local file URI/download handling | ACTIVE | `mobile/package.json`; report/file service imports |
| Mobile | Expo Sharing | Native report sharing | ACTIVE | `mobile/package.json`; `mobile/src/screens/ReportPreviewScreen.tsx` |
| Mobile | Expo SecureStore | Native secure JWT/profile persistence | ACTIVE | `mobile/src/services/authStorage.ts` |
| Mobile | AsyncStorage | Native offline draft JSON persistence | ACTIVE | `mobile/src/services/draftStorage.ts`; package manifest |
| Mobile | Web `localStorage` | Web token/profile/draft persistence fallback | OPTIONAL | `mobile/src/services/authStorage.ts`; `mobile/src/services/draftStorage.ts` |
| Mobile | React Native NetInfo | Native connectivity events | ACTIVE | `mobile/src/services/networkService.ts`; package manifest |
| Mobile | Browser online/focus/visibility events | Web connectivity lifecycle | OPTIONAL | `mobile/src/services/networkService.ts` |
| Mobile | Expo Location | GPS/site auto-fill capability | ACTIVE | `mobile/app.json`; location service/screen imports |
| Mobile | Expo Splash Screen / Status Bar | Startup splash and status-bar control | ACTIVE | `mobile/App.tsx`; package manifest |
| Mobile | Expo AV | Intro video/audio playback capability | OPTIONAL | `mobile/package.json`; intro screen usage |
| Mobile | Custom Android Kotlin native module | High-performance Laplacian image-quality check | ACTIVE | `mobile/android/.../ImageQualityModule.kt`; `ImageQualityPackage.kt`; `MainApplication.kt` |
| Mobile | Expo Modules autolinking | Native module/package linking | ACTIVE | `mobile/android/settings.gradle`; `MainApplication.kt` |
| Mobile | Android Gradle + Kotlin + React Native New Architecture/Hermes flags | Android build/runtime | ACTIVE | `mobile/android/build.gradle`; `MainApplication.kt`; `MainActivity.kt` |
| Mobile | Jest | Screen/unit test runner | ACTIVE | `mobile/package.json`; `mobile/src/screens/__tests__` |
| Mobile | Expo CLI / Metro | Development and bundling | ACTIVE | `mobile/package.json`; `mobile/index.ts` |
| Backend | Python 3.12 container runtime | Backend runtime | ACTIVE | `Dockerfile`; Python source |
| Backend | FastAPI | HTTP API framework, dependency injection, OpenAPI | ACTIVE | `backend/main.py`; `backend/requirements.txt` |
| Backend | Uvicorn | ASGI production server | ACTIVE | `Dockerfile`; `backend/requirements.txt` |
| Backend | Starlette middleware/static serving | FastAPI runtime substrate and file endpoints | ACTIVE | `backend/main.py`; FastAPI dependency |
| Backend | Pydantic v2 / pydantic-settings | Request/response schemas and environment settings | ACTIVE | `backend/schemas.py`; `backend/config.py`; requirements |
| Backend | SQLAlchemy 2 | ORM, sessions, relationships, queries | ACTIVE | `backend/database.py`; `backend/models.py`; `backend/main.py` |
| Backend | psycopg 3 | PostgreSQL driver | ACTIVE | `backend/requirements.txt`; `backend/database.py`; `.env` database URL |
| Backend | `python-multipart` | Multipart upload/form parsing | ACTIVE | FastAPI `UploadFile`/`File` routes in `backend/main.py`; requirements |
| Backend | JWT via `python-jose` HS256 | Bearer access tokens | ACTIVE | `backend/auth_service.py`; `backend/config.py` |
| Backend | bcrypt | Password hashing and verification | ACTIVE | `backend/auth_utils.py`; `backend/seed.py`; requirements |
| Backend | FastAPI OAuth2PasswordBearer | Token extraction dependency | ACTIVE | `backend/auth_service.py` |
| Backend | Custom RBAC and ownership checks | Inspector/supervisor/admin authorization | ACTIVE | `backend/auth_service.py`; `verify_inspection_access()` in `backend/main.py`; `backend/schemas.py` |
| Backend | Threading locks | Process-local draft/idempotency race protection | ACTIVE | `_creation_lock` in `backend/main.py` |
| Backend | PostgreSQL row locking / `SKIP LOCKED` | Durable OCR worker job claiming and concurrency | ACTIVE | `backend/ocr_job_service.py`; `backend/schema_migration.py` |
| Backend | SQLAlchemy metadata + custom idempotent DDL migration | Schema creation/migration | ACTIVE | `backend/schema_migration.py`; startup in `backend/main.py` |
| Backend | PostgreSQL/Neon | Required database backend/provider | ACTIVE | `backend/config.py` rejects SQLite; `backend/database.py`; `.env`/`.env.example` |
| Backend | Local filesystem directories | Uploads, generated reports, evidence crops | ACTIVE | `backend/config.py`; `backend/main.py`; `backend/storage_service.py` |
| Backend | Durable database-backed OCR job state machine | Crash/restart resilient asynchronous processing | ACTIVE | `OCRJob` in `backend/models.py`; `backend/ocr_job_service.py`; startup worker |
| Backend | Pillow | Image metadata/decoding and report image operations | ACTIVE | `backend/main.py`; `backend/report_service.py`; requirements |
| Backend | OpenCV + NumPy | Image quality, blur, crops, layout, OCR preprocessing, QR/barcode fallback | ACTIVE | `backend/image_quality.py`; `backend/blur_detection`; `backend/layout_service.py`; requirements |
| Backend | Pandas | Feature/data processing in metrology analyzers | ACTIVE | `backend/font_size_service.py`; `backend/readability_service.py`; requirements |
| Backend | PaddleOCR PP-OCRv4 | Primary OCR engine when enabled/available | ACTIVE | `backend/ocr_service.py`; `backend/config.py`; requirements |
| Backend | PaddlePaddle / PaddleX | PaddleOCR runtime dependencies | ACTIVE | `backend/ocr_service.py`; requirements |
| Backend | Tesseract + pytesseract | OCR alternative when discoverable | FALLBACK | `backend/ocr_service.py`; Docker installs `tesseract-ocr`; `backend/config.py` |
| Backend | OpenCV morphological OCR region segmenter | Text-region boxes without fabricating text | FALLBACK | `MorphologicalOpenCVOCREngine` in `backend/ocr_service.py` |
| Backend | pyzbar / libzbar | Primary barcode and QR decoder | ACTIVE | `backend/barcode_service.py`; Docker installs `libzbar0`; requirements |
| Backend | OpenCV QRCodeDetector / BarcodeDetector | Barcode/QR decoding fallback | FALLBACK | `_decode_with_opencv()` in `backend/barcode_service.py` |
| Backend | python-barcode | Barcode generation/report utility dependency | OPTIONAL | `backend/requirements.txt`; no production import confirmed in service path |
| Backend | python-docx | Editable DOCX report generation | ACTIVE | `backend/report_service.py`; `backend/reportlab_report_service.py`; requirements |
| Backend | ReportLab | PDF report generation | ACTIVE | `backend/reportlab_report_service.py`; `backend/report_service.py`; requirements |
| Backend | pypdf / pypdfium2 | PDF inspection/rendering utility support | OPTIONAL | requirements; no primary report-generation path confirmed |
| Backend | qrcode | QR generation utility dependency | OPTIONAL | requirements; no active production import confirmed |
| Backend | scikit-learn + joblib | Optional trained font/readability model inference | OPTIONAL | `backend/font_size_service.py`; `backend/readability_service.py`; `backend/ml_models` |
| Backend | Custom Laplacian/BlurDetection2 | Deterministic image quality and localized readability metrics | ACTIVE | `backend/blur_detection`; `backend/image_quality.py`; `backend/readability_service.py` |
| Compliance | Deterministic Python rule engine | PCR rule registry, evaluation, finding generation | ACTIVE | `backend/rule_engine/engine.py`; `models.py`; `registry.py`; imported by `backend/main.py` |
| Compliance | RuleVersion registry/version pinning | Database-managed rule versions and statutory references | ACTIVE | `RuleVersion` in `backend/models.py`; `backend/seed.py` |
| Compliance | Declaration validation matrix | Presence, format, misleading-quantity, currency/date/contact checks | ACTIVE | `backend/declaration_validation_service.py` |
| Compliance | Placement analyzer | PDP/information/secondary panel assessment | ACTIVE | `backend/placement_service.py` |
| Compliance | Font-size analyzer | Calibrated optical metrology and PCR Rule 7(2) checks | ACTIVE | `backend/font_size_service.py` |
| Compliance | Readability analyzer | Local crop readability/manual-verification routing | ACTIVE | `backend/readability_service.py` |
| Compliance | Online listing comparison | Physical-package versus listing evidence checks | ACTIVE | `backend/listing_service.py`; routes in `backend/main.py` |
| Compliance | Human adjudication / inspector verification | Pending, confirmed, dismissed, evidence review lifecycle | ACTIVE | `ComplianceCheck`/`InspectorReview` in `backend/models.py`; adjudication routes in `backend/main.py` |
| Compliance | Evidence records and bounding boxes | Traceable image evidence for findings | ACTIVE | `Evidence` in `backend/models.py`; `backend/main.py`; `backend/schemas.py` |
| AI | Qwen2.5-VL model interface | Optional contextual region interpretation through OpenAI-compatible HTTP | OPTIONAL | `backend/vlm_service.py`; disabled by default in `backend/config.py` |
| AI | Mock Qwen provider | Deterministic test/CI VLM substitute | FALLBACK | `MockQwenVLProvider` in `backend/vlm_service.py`; provider setting `mock` |
| AI | OpenAI-compatible VLM endpoint/vLLM/SGLang/Ollama/HF | Possible VLM serving backends, not bundled | OPTIONAL | `OpenAICompatibleVLMProvider` in `backend/vlm_service.py`; configurable endpoint |
| AI | Google Gemini API | Configuration/dependency candidate only | UNUSED | `GEMINI_API_KEY` in `backend/config.py` and Google packages in root requirements; no active service call confirmed |
| AI | Local trained readability/font models | Inference when model artifacts load successfully | OPTIONAL | `backend/ml_models`; lazy `joblib.load()` in analyzers |
| Reports | Report versioning and persistence | Reuse/regenerate report metadata and files | ACTIVE | `Report` model; `backend/report_service.py`; report routes in `backend/main.py` |
| Reports | SHA-256 | PDF integrity hash | ACTIVE | `hashlib` and `pdf_hash` in `backend/report_service.py`; migration/model |
| Reports | FastAPI FileResponse/static mounts | Report/image download and serving | ACTIVE | `/reports-static` and `/uploads` mounts in `backend/main.py` |
| Security | CORS middleware | Cross-origin API access | ACTIVE | `CORSMiddleware` in `backend/main.py`; `CORS_ORIGINS` in config |
| Security | Environment-file settings | Secrets and deployment configuration | ACTIVE | `backend/config.py`; `.env`; `.env.example`; `python-dotenv` dependency |
| Testing | pytest | Backend test framework | ACTIVE | `pytest.ini`; `tests/`; requirements |
| Testing | httpx/TestClient utilities | API/integration testing | ACTIVE | `tests/`; requirements |
| Testing | Jest | Mobile screen tests | ACTIVE | `mobile/package.json`; `mobile/src/screens/__tests__` |
| Testing | TypeScript compiler | Mobile static type checking | ACTIVE | `mobile/package.json` script `ts:check`; `mobile/tsconfig.json` |
| Testing | Playwright/Detox/Maestro/Appium | E2E runner | UNUSED | No executable dependency/config/source found; Python manual E2E scripts are not these tools |
| Dev tooling | npm package manager | Mobile dependency/build scripts | ACTIVE | `mobile/package.json`; `mobile/package-lock.json` |
| Dev tooling | Gradle wrapper / Android SDK / JDK 17 | Native Android compilation | ACTIVE | `mobile/android`; repository `android-sdk`; `jdk-17` |
| Dev tooling | Docker | Reproducible backend image and startup | ACTIVE | `Dockerfile` |
| Dev tooling | Git/GitHub | Source control metadata/workflow | ACTIVE | `.git`; repository structure; no checked-in CI workflow found |
| Dev tooling | ESLint/Prettier | Linting/formatting | UNUSED | No config or package usage found |
| Infrastructure | Render-style `$PORT` container startup | Port-configurable production server pattern | OPTIONAL | `Dockerfile` uses `$PORT`; no checked-in hosting manifest proves provider |
| Infrastructure | Neon cloud PostgreSQL | External managed DB target | ACTIVE | Runtime config explicitly requires PostgreSQL and detects Neon in `backend/database.py` |
| Infrastructure | Redis | Cache/job broker candidate | UNUSED | No Redis dependency, import, config, or runtime usage found |
| Infrastructure | Supabase | Historical integration reference | HISTORICAL | Migration comments/docs mention Supabase; no active Supabase SDK/client/storage path |
| Infrastructure | SQLite | Historical/local database reference | HISTORICAL | `schema_migration.py` comments and old docs; runtime config and engine explicitly reject SQLite |

## NiriKsha Tech Stack

**Mobile**
- Expo SDK 51 with React Native 0.74.5, React 18, and TypeScript.
- React Navigation native stack, safe-area context, Expo icons, camera/image picker, filesystem, sharing, location, splash screen, and status bar.
- SecureStore for JWT/profile data; AsyncStorage for offline drafts; NetInfo plus browser connectivity events for sync recovery.
- Custom Kotlin Android ImageQualityModule with a TypeScript/web Laplacian fallback.

**Backend**
- Python 3.12, FastAPI, Uvicorn/ASGI, Pydantic v2, SQLAlchemy 2, psycopg 3.
- Multipart uploads, filesystem storage, database-backed OCR jobs, process locks, and PostgreSQL `SKIP LOCKED` job claiming.
- bcrypt password hashing, python-jose JWT, OAuth2 bearer extraction, custom RBAC/resource ownership checks.

**Database & Storage**
- PostgreSQL, configured for Neon, accessed through SQLAlchemy and psycopg.
- Local filesystem for uploads, evidence crops, and generated PDF/DOCX reports.
- SQLAlchemy models plus idempotent custom migration DDL; no Redis/cache layer.

**AI / OCR / Computer Vision**
- PaddleOCR PP-OCRv4 is the configured primary OCR engine.
- Tesseract/pytesseract and OpenCV morphological segmentation are fallbacks.
- OpenCV/NumPy provide blur, brightness, contrast, layout and crop processing; pyzbar is primary barcode/QR decoding with OpenCV fallback.
- Qwen2.5-VL is an optional disabled contextual assistant; its mock provider supports deterministic tests.
- Font/readability scikit-learn models are optional artifact-driven inference, with deterministic optical rules and manual-review gates.

**Legal Metrology / Compliance**
- Deterministic, versioned PCR 2011 rule registry and compliance engine.
- Declaration validation matrix, placement, font-size, readability, online-listing comparison, finding/evidence generation, and inspector adjudication.
- The VLM can provide candidates/region interpretation but is explicitly prevented from making final legal decisions.

**Reports**
- ReportLab PDF and python-docx DOCX generation.
- Pillow/OpenCV image embedding/crops, SHA-256 PDF integrity hashes, database report metadata/versioning, and FastAPI static/FileResponse download serving.

**Security**
- HS256 JWT access tokens with expiry, bcrypt password hashes, OAuth2 bearer dependency, and role/resource authorization.
- CORS is configuration-driven but defaults to permissive `*` when unset.
- Upload MIME/size checks, path-based storage service, evidence traceability, environment-backed secrets, and audit-log entities.

**Deployment / Infrastructure**
- Docker Python 3.12 image; Uvicorn single-worker process with the durable in-process OCR worker.
- Neon PostgreSQL is the required managed database target.
- Native Android Gradle build via Expo prebuild/autolinking; no checked-in CI/CD workflow or hosting manifest proves a specific frontend/backend host.

**Testing**
- pytest backend suite with API/integration utilities and repository-specific QA/manual E2E scripts.
- Jest mobile screen tests and TypeScript `tsc --noEmit` verification.
- No Playwright, Detox, Maestro, Appium, ESLint, or Prettier execution surface was found.

**Developer Tools**
- npm/package-lock, Expo CLI/Metro, TypeScript compiler, Gradle/Android SDK/JDK 17, Python pip requirements, Docker, and Git.

## Core Technologies for Presentation

| Technology | Why it matters in NiriKsha | Where it is used |
|---|---|---|
| Expo + React Native | Delivers one field-inspection app across Android and web preview | `mobile/` |
| TypeScript | Gives the mobile workflow typed screen/API contracts | `mobile/src`, `tsconfig.json` |
| FastAPI | Provides the typed, documented inspection API | `backend/main.py` |
| Uvicorn/ASGI | Runs the production API server | `Dockerfile` |
| PostgreSQL on Neon | Durable managed store for inspections and legal evidence | `backend/database.py`, config |
| SQLAlchemy 2 | Maps inspections, OCR, findings, evidence and reports | `backend/models.py` |
| PaddleOCR PP-OCRv4 | Extracts package declarations from label images | `backend/ocr_service.py` |
| OpenCV + NumPy | Performs quality gates, preprocessing, geometry and CV analysis | `backend/image_quality.py`, layout/readability services |
| Tesseract | Provides an OCR fallback when PaddleOCR is unavailable | `backend/ocr_service.py`, Dockerfile |
| pyzbar + OpenCV barcode detection | Adds barcode/QR evidence and OCR corroboration | `backend/barcode_service.py` |
| Deterministic PCR rule engine | Converts extracted evidence into reviewable legal-metrology findings | `backend/rule_engine/` |
| Human adjudication workflow | Keeps the inspector accountable for statutory decisions | compliance checks, review/finalize routes |
| Offline draft sync | Supports field work without continuous connectivity | `mobile/src/services/draftStorage.ts`, `syncService.ts` |
| Expo SecureStore | Protects mobile access tokens on native devices | `mobile/src/services/authStorage.ts` |
| Durable OCR job worker | Survives restarts and exposes progress/retry state | `backend/ocr_job_service.py`, `OCRJob` |
| ReportLab | Produces official PDF reports | `backend/reportlab_report_service.py` |
| python-docx | Produces editable compliance reports | report service |
| SHA-256 | Makes generated PDF integrity verifiable | report model/service |
| Custom Kotlin image-quality module | Runs fast offline blur/quality checks on Android | `mobile/android/.../ImageQualityModule.kt` |
| Jest + pytest | Verifies mobile screens and backend behavior | `mobile/src/screens/__tests__`, `tests/` |
| Docker | Packages backend and native OCR/system libraries consistently | `Dockerfile` |

## Architecture Stack

```text
Mobile App
  Expo SDK 51 + React Native 0.74.5 + TypeScript
  React Navigation, Expo ImagePicker/Camera, SecureStore, AsyncStorage, NetInfo
        |
        v
API Layer
  FastAPI + Pydantic v2 + python-multipart + CORS
  Uvicorn ASGI server; JWT bearer authentication
        |
        v
Backend Services
  SQLAlchemy 2 + psycopg 3
  Auth/RBAC, inspection lifecycle, filesystem storage
  Durable OCRJob worker, threading lock, PostgreSQL SKIP LOCKED
        |
        v
OCR / Computer Vision / Compliance Engine
  PaddleOCR PP-OCRv4 primary; Tesseract/OpenCV fallbacks
  OpenCV/NumPy quality, layout, readability, placement and font analysis
  pyzbar/OpenCV barcode decoding; optional scikit-learn models
  Versioned deterministic PCR rule engine and inspector adjudication
        |
        v
Database & Durable Storage
  Neon PostgreSQL via SQLAlchemy
  Local uploads, evidence crops, generated reports
        |
        v
Reports / Evidence
  ReportLab PDF + python-docx DOCX
  Pillow/OpenCV image embedding, SHA-256 PDF hash
  Database report metadata/versioning and FastAPI downloads
```

## Removed / Unused / Historical Technologies

- **SQLite:** not part of the current backend. Runtime settings and engine reject all SQLite URLs. Remaining references are migration comments and older documentation.
- **Supabase:** historical migration wording remains, but there is no active Supabase SDK, client, storage adapter, or API call in the current backend.
- **Redis:** no dependency, import, configuration, or runtime use.
- **Gemini:** API key/configuration and Google packages remain in the root environment, but no active Gemini call is part of the production request path.
- **Qwen2.5-VL:** implemented as an optional provider but disabled by default; the default provider is the deterministic mock. It should be presented as optional research capability, not active production AI.
- **Tesseract and OpenCV morphological OCR:** real implemented fallbacks, not primary OCR.
- **OpenCV barcode/QR detector:** real fallback when pyzbar returns no result or is unavailable.
- **python-barcode, qrcode, pypdf/pypdfium2:** declared utilities without confirmed active production use in the primary report path; classify as optional until a call site is added.
- **scikit-learn/joblib models:** optional because model loading is artifact-dependent; analyzers retain deterministic optical behavior when artifacts are absent.
- **Playwright, Detox, Maestro, Appium:** no actual test framework/configuration found.
- **ESLint and Prettier:** no actual package/config/script found.
- **Specific backend hosting provider:** Docker and `$PORT` are verified; no checked-in Render/Railway/Fly/Vercel manifest proves a provider. Neon is verified as the database target, not as the API host.

## Verification Notes

The inventory above deliberately uses repository-relative evidence. The primary active stack is verified by these exact files and symbols:

- **Mobile runtime and build:** `mobile/package.json` dependencies/scripts; `mobile/App.tsx`; `mobile/index.ts`; `mobile/app.json`; `mobile/android/build.gradle`; `mobile/android/settings.gradle`; `mobile/android/.../MainApplication.kt` and `MainActivity.kt`.
- **Navigation/UI:** `mobile/src/navigation/AppNavigator.tsx`; screen/component imports under `mobile/src`; `@expo/vector-icons` imports; theme tokens under `mobile/src/theme`.
- **Mobile capture/offline/auth/network:** `CaptureImagesScreen.tsx`, `authStorage.ts`, `draftStorage.ts`, `networkService.ts`, `syncService.ts`, `imageQualityService.ts`.
- **API/backend:** `backend/main.py` imports and route handlers; `backend/config.py`; `backend/schemas.py`; `backend/database.py`; `backend/models.py`.
- **Authentication/security:** `backend/auth_service.py`, `backend/auth_utils.py`, `backend/main.py` access checks and CORS middleware.
- **Database/migrations/jobs:** `backend/models.py` (`OCRJob`, `RuleVersion`, `Evidence`, `Report`); `backend/schema_migration.py`; `backend/ocr_job_service.py`; `database/schema.sql`.
- **OCR/CV:** `backend/ocr_service.py`, `backend/image_quality.py`, `backend/blur_detection/`, `backend/layout_service.py`, `backend/font_size_service.py`, `backend/readability_service.py`.
- **Barcodes:** `backend/barcode_service.py`; `backend/schemas.py`; Docker `libzbar0` installation.
- **Optional VLM:** `backend/vlm_service.py`; `VLM_ENABLED=False`, provider/model settings in `backend/config.py`.
- **Compliance:** `backend/rule_engine/`; `backend/declaration_validation_service.py`; `backend/placement_service.py`; `backend/listing_service.py`; `backend/main.py` evaluation/adjudication/finalization routes.
- **Reports/storage:** `backend/report_service.py`; `backend/reportlab_report_service.py`; `backend/storage_service.py`; report/upload static mounts in `backend/main.py`.
- **Deployment/testing:** `Dockerfile`; `pytest.ini`; `tests/`; `mobile/package.json` Jest and `ts:check` scripts.

### Caveat on configuration security

The code is environment-driven, but `backend/config.py` contains development fallback/default seed credentials and a default JWT secret. Production deployment must override these values through `.env`/environment variables and restrict `CORS_ORIGINS`; the audit marks the mechanisms as active without treating the defaults as production-safe secrets.
