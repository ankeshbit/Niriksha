# MASTER PROJECT CONTEXT REPORT: NIRIKSHA

**Document Classification:** Definitive LLM System & Architecture Context Document  
**Target Audience:** Advanced AI Coding, Reasoning, and Architecture Models (Claude, GPT, Gemini)  
**System Name:** NiriKsha — AI-Assisted Legal Metrology Packaged-Commodity Inspection System  
**Problem Statement:** Smart India Hackathon (SIH) 2026 — Problem Statement 26034  
**Nodal Authority:** Department of Consumer Affairs (DoCA), Ministry of Consumer Affairs, Food & Public Distribution, Government of India  
**Statutory Framework:** Legal Metrology Act, 2009 & Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)  
**Database Backend:** PostgreSQL 15+ on Neon Serverless Cloud (`postgresql+psycopg://`)  
**Core Motto:** *“AI assists, deterministic rules evaluate, photographic evidence supports, the Inspecting Officer decides.”*  

---

## PART 1 — PROJECT IDENTITY

### 1.1 Project Name & Purpose
- **Official Name:** NiriKsha (Hindi: *निरीक्षा* — "Close Inspection / Surveillance")
- **Formal Title:** Software System to Check Compliance of Packaged Commodities under Legal Metrology (Packaged Commodities) Rules, 2011 by Scanning Products, Images, and Labels.
- **Problem Statement Code:** SIH 2026 PS 26034.
- **Real-World Problem Being Solved:** Under the Legal Metrology (Packaged Commodities) Rules, 2011, every packaged good sold in India (food, cosmetics, electronics, personal care) must bear mandatory declarations: Maximum Retail Price (MRP) inclusive of all taxes, net quantity in standard metric units, manufacturer/packer/importer name and complete postal address, date/month/year of manufacture or packing, consumer care contact details, and country of origin. Currently, field inspectors manually examine hundreds of product packages daily in retail shops, warehouses, and e-commerce fulfillment hubs. Manual audits are slow, error-prone, subject to subjective bias, and lack an evidentiary chain of custody capable of withstanding scrutiny in legal courts.
- **The NiriKsha Solution:** A field-grade mobile-and-backend software suite that captures multi-panel package photographs, performs real-time optical quality checks, runs on-device and serverless OCR (PaddleOCR 3.x singleton with layout analysis), deterministically extracts statutory declarations, evaluates compliance against 12 version-pinned legal metrology rules, flags discrepancies between physical packaging and e-commerce listings, provides an inspector-in-the-loop adjudication workflow, and generates tamper-evident, SHA-256 sealed statutory inspection reports in ReportLab PDF and editable Word DOCX formats.

### 1.2 Target Users
1. **Field Inspecting Officers (Legal Metrology Inspectors):** Carry the mobile application into physical retail stores, wholesale markets, and logistics hubs. Capture multi-panel package images, review OCR extractions, adjudicate preliminary findings, and submit official statutory inspection dossiers.
2. **Supervisory Officers / Zonal Controllers:** Oversee enforcement operations across geographic zones, monitor inspection registries, review 18-attribute inspection dossiers, analyze inspector performance, and execute audited administrative corrections or cancellations.
3. **Department Administrators / Directors:** Manage user accounts, configure zonal assignments, inspect audit logs, and oversee state/national compliance analytics.

### 1.3 Core Workflow Summary
```
Field Capture (front, back, side panels)
    └── Quality Check (BlurDetection2 score >= 150)
            └── Modular OCR (PaddleOCR 3.x + PP-Structure layout)
                    └── Declarations Extraction (8 statutory fields)
                            └── Analytical Metrology (Placement, Readability, Font Size)
                                    └── Deterministic Rule Engine (12 PCR 2011 clauses)
                                            └── Preliminary Findings
                                                    └── Inspector Adjudication (Confirm / Dismiss / Correct)
                                                            └── Finalization Gate (zero pending)
                                                                    └── SHA-256 Sealed Statutory Report
```

### 1.4 Project Goals & Non-Goals
#### Project Goals:
- **Zero Fabrication:** Never hallucinate character text, bounding boxes, or statutory compliance.
- **Evidence-First Legal Integrity:** Every finding must be linked to a photographic bounding-box crop and statutory rule citation.
- **Safety Rule:** OCR non-detection or optical blur must NEVER automatically become a legal violation conviction.
- **Cloud-Native Serverless Database:** Sole production source of truth is Neon PostgreSQL using `psycopg3`.
- **Field Resilience:** Full offline draft creation and image capture in warehouses with zero cellular reception, followed by idempotent auto-sync upon reconnection.

#### Non-Goals:
- **No Autonomous Prosecution:** AI does NOT convict or fine businesses. The inspecting officer is the sole legal adjudicator.
- **No Physical Net Mass Verification:** The system evaluates printed label declarations. It does NOT weigh or measure physical commodities (Rule 19 Physical Mass Limitation).
- **No SQLite Runtime:** SQLite is banned from production, development, and test runs.

### 1.5 Current Maturity & Status
- **Backend API:** 100% Implemented and verified on FastAPI 0.141.1 with 58 endpoints.
- **Database Architecture:** 100% Migrated and verified on PostgreSQL / Neon (15 relational tables).
- **Test Suite:** 522 Pytest tests passing across 61 test files; 138 Jest tests passing across 13 suites.
- **Mobile Application:** Expo 51 / React Native 0.74 with 20 screens covering Inspector and Supervisor flows.

---

## PART 2 — COMPLETE TECHNOLOGY STACK

### 2.1 Frontend & Mobile Ecosystem
| Technology | Version | Location / Usage | Why Used & Configuration |
|---|---|---|---|
| **React Native** | `0.74.5` | `mobile/` | Cross-platform native mobile foundation for Android field devices. |
| **Expo** | `~51.0.28` | `mobile/` | Managed build runtime with native prebuild support (`expo run:android`). |
| **TypeScript** | `~5.3.3` | `mobile/src/` | Compile-time type safety across navigation, API clients, and domain models. |
| **React Navigation** | `@react-navigation/native` `^6.1.18`, `@react-navigation/native-stack` `^6.10.1` | `mobile/src/navigation/` | Stack navigation managing 20 screens with fade transitions. |
| **AsyncStorage** | `@react-native-async-storage/async-storage` `^1.23.1` | `mobile/src/services/draftStorage.ts` | Persistent local storage for offline inspection drafts. Replaced SecureStore (AUDIT-MOB-01). |
| **NetInfo** | `@react-native-community/netinfo` `^11.3.1` | `mobile/src/services/networkService.ts` | Native network reachability listeners triggering automated background sync. |
| **Expo Camera** | `~15.0.16` | `mobile/src/screens/CaptureImagesScreen.tsx` | High-resolution hardware camera capture for packaging panels. |
| **Expo Location** | `~17.0.1` | `mobile/src/screens/NewInspectionScreen.tsx` | GPS coordinates and reverse geocoding for inspection location. |
| **Expo AV** | `~14.0.7` | `mobile/src/screens/IntroScreen.tsx` | Hardware-accelerated video playback for DoCA branding sequence. |
| **Expo FileSystem** | `~17.0.1` | `mobile/src/services/api.ts` | Local file management, multipart upload streaming, and cache cleanup. |
| **Expo Sharing** | `~12.0.1` | `mobile/src/screens/ReportPreviewScreen.tsx` | Native Android share sheet for sharing generated PDF reports. |
| **Native Android** | Gradle 8.3, AGP 8.4, Kotlin 1.9.23, SDK 34, NDK 26.1 | `mobile/android/` | Custom Android build configuration with `network_security_config.xml`. |

### 2.2 Backend & Machine Learning Stack
| Technology | Version | Location / Usage | Why Used & Configuration |
|---|---|---|---|
| **Python** | `3.10.11` | Root / `backend/` | Primary backend runtime environment. |
| **FastAPI** | `0.141.1` | `backend/main.py` | High-performance asynchronous REST API framework. |
| **Uvicorn** | `0.52.4` | Server launcher | ASGI production server running at port 8000. |
| **SQLAlchemy** | `2.0.52` | `backend/database.py`, `backend/models.py` | Relational ORM with connection pooling (`pool_pre_ping=True`, `pool_recycle=300`). |
| **Psycopg** | `3.3.5` (`psycopg`, `psycopg-binary`) | Database driver | Modern PostgreSQL 15+ DBAPI driver supporting binary protocol and Neon cloud. |
| **Pydantic** | `2.13.4`, `pydantic-settings` `2.15.0` | `backend/schemas.py`, `backend/config.py` | Strict data validation, schema serialization, and env configuration. |
| **PaddleOCR & PaddlePaddle** | `paddleocr` `3.7.0`, `paddlepaddle` `3.3.1`, `paddlex` `3.7.2` | `backend/ocr_service.py` | Primary deep-learning OCR engine with textline orientation detection. |
| **PyTesseract** | `0.3.13` | `backend/ocr_service.py` | Secondary fallback OCR engine with automatic binary detection. |
| **OpenCV** | `opencv-contrib-python` `4.10.0.84`, `opencv-python-headless` `4.9.0.80` | `backend/image_quality.py`, `backend/ocr_service.py` | Image preprocessing (Otsu, CLAHE, Adaptive thresholding) and blur analysis. |
| **Scikit-Learn** | `1.7.2` | `backend/ml_models/` | Classical ML models for font size estimation and declaration readability. |
| **ReportLab** | `5.0.1` | `backend/report_service.py`, `backend/reportlab_report_service.py` | Formal statutory PDF generation with official DoCA styling and SHA-256 seal. |
| **python-docx** | `1.2.0` | `backend/report_service.py` | Editable Word DOCX report export mirroring official PDF structure. |
| **PyZbar & python-barcode** | `pyzbar` `0.1.9`, `python-barcode` `0.16.1` | `backend/barcode_service.py` | 1D EAN-13/Code-128 barcode and 2D QR code detection. |
| **python-jose & passlib** | `python-jose` `3.5.0`, `passlib` `1.7.4`, `bcrypt` `5.0.0` | `backend/auth_service.py`, `backend/auth_utils.py` | Cryptographic JWT creation and Bcrypt password hashing. |

---

## PART 3 — REPOSITORY STRUCTURE

```
SIH/
├── backend/                              # FastAPI Backend Application Root
│   ├── auth_service.py                   # JWT generation, get_current_user, RoleChecker RBAC
│   ├── auth_utils.py                     # Bcrypt hashing & verification
│   ├── barcode_service.py                # 1D/2D barcode & QR scanning via pyzbar
│   ├── blur_detection/                   # Resolution-normalized blur analysis module
│   │   └── detection.py                  # Core estimate_blur implementation
│   ├── compliance_summary_utils.py       # Canonical compliance metrics computation
│   ├── config.py                         # Pydantic Settings, fail-fast Neon DB validation
│   ├── database.py                       # SQLAlchemy engine, SessionLocal, get_db, safety guards
│   ├── declaration_validation_service.py # Unified 8-attribute compliance matrix generator
│   ├── extraction_service.py             # PP-Structure layout + spatial regex extractor
│   ├── font_size_service.py              # Rule 9 Table 1 font size analyzer + ML regressor
│   ├── image_quality.py                  # BlurDetection2 wrapper with OpenCV
│   ├── layout_service.py                 # Spatial layout parsing (Title, Table, Address, Care)
│   ├── listing_service.py                # E-commerce listing vs. package OCR discrepancy comparator
│   ├── main.py                           # 4,778-line FastAPI application, 58 endpoints
│   ├── ml_models/                        # Serialized scikit-learn models, scalers, metadata
│   │   ├── font_size_model.joblib        # GradientBoostingRegressor for character height
│   │   ├── readability_model.joblib      # LogisticRegression for crop legibility
│   │   └── model_metadata.json           # Model hyperparameter & training provenance
│   ├── models.py                         # 15 SQLAlchemy database models
│   ├── ocr_service.py                    # Modular OCR coordinator (PaddleOCR singleton + Tesseract)
│   ├── placement_service.py              # PDP vs Information Panel spatial classifier
│   ├── readability_service.py            # Crop-level Laplacian variance, contrast & ML evaluator
│   ├── report_components.py              # Reusable ReportLab flowables & document sections
│   ├── report_service.py                 # Master report coordinator (ReportLab PDF + python-docx)
│   ├── report_styles.py                  # Official DoCA typography & color palette
│   ├── reportlab_report_service.py       # Multi-page statutory PDF builder
│   ├── rule_engine/                      # Deterministic PCR 2011 statutory rule engine
│   │   ├── engine.py                     # DeterministicRuleEngine evaluation logic
│   │   ├── legal_provenance.py           # Statutory provenance mapping to 2011 gazette
│   │   ├── models.py                     # RuleEvaluationResult, StatutoryRuleDefinition
│   │   └── registry.py                   # 12 version-pinned PCR 2011 rule definitions
│   ├── schema_migration.py               # Safe schema migration runner
│   ├── schemas.py                        # Pydantic request/response validation schemas
│   ├── seed.py                           # Database seeder for officer accounts & rules
│   ├── supabase_storage.py               # Optional Supabase object storage adapter
│   └── vlm_service.py                    # Qwen2.5-VL vision-language model integration adapter
├── database/                             # Database DDL & Schemas
│   └── schema.sql                        # Raw PostgreSQL DDL definition
├── docs/                                 # Architectural Audits, QA Reports & Traceability
│   ├── DATABASE_ARCHITECTURE_VERIFICATION.md
│   ├── FINAL_FULL_SYSTEM_QA_REPORT.md
│   ├── POSTGRES_NEON_MIGRATION_REPORT.md
│   ├── POST_REMEDIATION_FINAL_AUDIT_REPORT.md
│   └── SIH_PS_26034_TRACEABILITY.md
├── mobile/                               # React Native / Expo Mobile Application Root
│   ├── App.tsx                           # Mobile entry point
│   ├── app.json                          # Expo configuration
│   ├── android/                          # Native Android Studio project
│   │   ├── app/src/main/AndroidManifest.xml
│   │   ├── app/src/main/res/xml/network_security_config.xml
│   │   └── build.gradle
│   ├── package.json                      # Mobile dependencies & npm test script
│   └── src/
│       ├── navigation/                   # React Navigation stack & route types
│       │   ├── AppNavigator.tsx          # 20-screen createNativeStackNavigator
│       │   └── types.ts                  # RootStackParamList definition
│       ├── screens/                      # 20 Mobile Screen Implementations
│       │   ├── AnalyzingScreen.tsx       # Live OCR progress & polling
│       │   ├── CaptureImagesScreen.tsx   # Front, back, side camera capture & quality gate
│       │   ├── DashboardScreen.tsx       # Field officer metrics & recent inspections
│       │   ├── DraftOfflineScreen.tsx    # Unsynced local draft vault & sync progress
│       │   ├── EvidenceReviewScreen.tsx  # Bounding-box photographic crops viewer
│       │   ├── ExtractedDeclarationsScreen.tsx # 8 fields review & edit modal
│       │   ├── FindingsScreen.tsx        # Preliminary findings & adjudication actions
│       │   ├── InspectionsScreen.tsx     # Searchable inspection repository
│       │   ├── IntroScreen.tsx           # Official DoCA branding video launch screen
│       │   ├── ListingComparisonScreen.tsx # E-commerce listing vs package comparison
│       │   ├── LoginScreen.tsx           # Officer credential authentication
│       │   ├── NewInspectionScreen.tsx   # Inspection initialization & GPS location
│       │   ├── ProfileScreen.tsx         # Officer details & password management
│       │   ├── ReportPreviewScreen.tsx   # PDF viewer, share sheet, DOCX download
│       │   ├── ReportsListScreen.tsx     # Completed statutory reports archive
│       │   ├── ReviewAndSubmitScreen.tsx # Final review & submission gate
│       │   ├── SupervisorAllInspectionsScreen.tsx # Zonal inspection dossier list
│       │   ├── SupervisorDashboardScreen.tsx     # Jurisdiction-wide supervisory metrics
│       │   ├── SupervisorInspectionDetailScreen.tsx # 18-attribute dossier viewer
│       │   └── SupervisorInspectorsScreen.tsx    # Inspector roster & activity tracker
│       │   └── __tests__/                # 13 Jest mobile integration test suites (138 tests)
│       └── services/                     # Mobile Services Layer
│           ├── api.ts                    # Axios/fetch HTTP client with dynamic host resolution
│           ├── authStorage.ts            # Secure token & user session storage
│           ├── draftStorage.ts           # AsyncStorage offline draft queue
│           ├── imageQualityService.ts    # On-device image quality pre-check
│           ├── networkService.ts         # NetInfo connectivity listener
│           └── syncService.ts            # Offline draft background synchronization engine
├── tests/                                # Backend Pytest Test Suite Root (61 files, 522 tests)
│   ├── conftest.py                       # PostgreSQL test database setup & isolation guards
│   ├── test_complete_post_image_workflow.py # Full end-to-end integration workflow
│   ├── test_deterministic_rule_engine.py # PCR 2011 rule engine tests
│   ├── test_inspection_number_concurrency.py # Atomic counter race condition tests
│   ├── test_postgres_only_architecture.py   # Strict anti-SQLite enforcement tests
│   ├── test_report_immutability.py          # Report tamper-proofing tests
│   └── test_supervisor_management.py        # Supervisor RBAC & deletion tests
├── generated_reports/                    # Local storage for sealed PDF and DOCX reports
├── uploads/                              # Local storage for raw packaging panel photographs
├── requirements.txt                      # Complete Python dependency lockfile
└── pytest.ini                            # Pytest configuration
```

---

## PART 4 — SYSTEM ARCHITECTURE

### 4.1 Master Architecture Diagram
```
[Android Native App (Expo 51)]
         │
         │  HTTPS REST JSON / Multipart Form-Data
         │  (JWT Bearer Token in Authorization Header)
         ▼
[FastAPI Application Gateway (Uvicorn :8000)]
         │
         ├──► CORS & Host Whitelist Middleware
         ├──► OAuth2 Security Dependency (RoleChecker: INSPECTOR | SUPERVISOR | ADMIN)
         └──► Global Exception Handler (CORS Header Preserving)
         │
         ├──► Image Quality Subsystem (BlurDetection2 / OpenCV)
         ├──► OCR Coordinator (PaddleOCR 3.x Singleton + JIT Warmup Thread)
         ├──► Spatial Layout & Extraction (PP-Structure + Regex Extractor)
         ├──► Analytical Metrology (Placement, Readability, Font Size ML Models)
         ├──► Deterministic Rule Engine (12 Pinned PCR 2011 Rules)
         ├──► E-Commerce Comparison Service (Rule 18(2A) & Rule 6(10))
         └──► Statutory Report Builder (ReportLab PDF + python-docx DOCX)
         │
         ▼
[SQLAlchemy 2.0 ORM Tier]
         │  Connection Pool (pool_pre_ping=True, pool_recycle=300)
         ▼
[Neon Serverless PostgreSQL Database (AWS us-east-2)]
         │  (15 Relational Tables)
         ▼
[Local Persistent Storage]
         ├── uploads/             (Packaging Panel Images)
         └── generated_reports/   (Sealed Statutory Reports)
```

### 4.2 Architecture Boundaries & Invariants
1. **Frontend / Backend Boundary:** The mobile client is strictly a data capture and presentation layer. It never computes legal compliance, never determines font size in millimeters, and never decides whether a product violates the law. All analytical and statutory logic resides on the backend.
2. **Database Boundary:** Neon PostgreSQL is the sole authorized database backend. SQLite is strictly rejected by `config.py` and `database.py`. The test suite must run against a distinct Neon test database; connecting tests to the production database raises an immediate fatal error.
3. **Machine Learning Boundary:** Machine learning models (`font_size_model.joblib`, `readability_model.joblib`) are used strictly for optical feature extraction and character height estimation. ML models are completely forbidden from making legal determinations. All legal decisions are evaluated by the deterministic rule engine and finalized by the human officer.

---

## PART 5 — END-TO-END USER WORKFLOWS

### 5.1 Field Inspector Workflow (Step-by-Step)

```
[1. Login] ───────────────► POST /api/auth/login ────────► Token & Profile returned
     │
     ▼
[2. Dashboard] ───────────► GET /api/dashboard/summary ──► Count cards & recents
     │
     ▼
[3. Create Inspection] ───► POST /api/inspections ───────► Atomic LM-2026-000XX allocated
     │                      (with client_draft_id)
     ▼
[4. Capture Images] ──────► POST /api/inspections/{id}/images
     │                      (Front, Back, Side panel images uploaded & validated)
     ▼
[5. Run OCR & Analyze] ──► POST /api/inspections/{id}/ocr
     │                      (PaddleOCR + PP-Structure layout + extraction)
     ▼
[6. Review Declarations] ─► GET /api/inspections/{id}/declarations
     │   (Optional Edit)  ─► PATCH /api/declarations/{id}
     ▼
[7. Evaluate Rules] ──────► POST /api/inspections/{id}/evaluate
     │                      (Deterministic rule engine generates preliminary findings)
     ▼
[8. Adjudicate Findings] ─► POST /api/findings/{id}/adjudicate
     │                      (Officer marks CONFIRMED, DISMISSED, CORRECTED, or NOT_APPLICABLE)
     ▼
[9. Finalize Gate] ───────► POST /api/inspections/{id}/finalize
     │                      (Blocks if any finding is PENDING; locks evidence)
     ▼
[10. Statutory Report] ───► POST /api/inspections/{id}/report
                            (Generates SHA-256 sealed PDF & editable DOCX)
```

### 5.2 Supervisor Workflow (Step-by-Step)

```
[1. Supervisor Login] ────► POST /api/auth/login (Role: SUPERVISOR)
     │
     ▼
[2. Zonal Dashboard] ─────► GET /api/supervisor/dashboard (Jurisdiction-wide metrics)
     │
     ▼
[3. Inspection Dossier] ──► GET /api/supervisor/inspections (18-attribute dossier repository)
     │
     ▼
[4. Inspector Roster] ────► GET /api/supervisor/inspectors (Activity & scan volume per officer)
     │
     ▼
[5. Supervisory Actions]:
     ├── DELETE /api/inspections/{id}/report
     │     (Deletes PDF/DOCX, reverts inspection to ANALYSIS_COMPLETE, writes audit log)
     └── DELETE /api/inspections/{id}
           (Cascade deletes all relational entities & unlinks images; audit log survives)
```

---

## PART 6 — AUTHENTICATION & ROLE-BASED ACCESS CONTROL (RBAC)

### 6.1 Authentication Mechanism
- **Algorithm:** HMAC-SHA256 (`HS256`) via `python-jose`.
- **Token Format:** JSON Web Token (JWT) with claims:
  - `sub`: Official Officer ID (e.g. `DOCA-INSP-842`)
  - `role`: Authorization Role (`INSPECTOR`, `SUPERVISOR`, `ADMIN`)
  - `exp`: Expiration timestamp (default: 24 hours / 1440 minutes).
- **Password Storage:** Bcrypt with automatic salt generation via `passlib.context.CryptContext(schemes=["bcrypt"])`.

### 6.2 Roles and Permission Matrix
| Operation / Endpoint Group | INSPECTOR | SUPERVISOR | ADMIN | Enforcement Mechanism |
|---|:---:|:---:|:---:|---|
| Create Inspection / Upload Images | ✅ | ❌ | ✅ | Backend `RoleChecker(["INSPECTOR", "ADMIN"])` |
| View Own Assigned Inspections | ✅ | ✅ | ✅ | Backend database filter `inspector_id == user.id` |
| View All Zonal Inspections | ❌ | ✅ | ✅ | Backend `RoleChecker(["SUPERVISOR", "ADMIN"])` |
| Adjudicate Findings | ✅ | ❌ | ✅ | Backend check: only assigned officer or admin can adjudicate |
| Finalize Inspection | ✅ | ❌ | ✅ | Backend check: only assigned officer or admin can finalize |
| Delete Generated Report | ❌ | ✅ | ✅ | Backend `RoleChecker(["SUPERVISOR", "ADMIN"])` + reason required |
| Cascade Delete Inspection | ❌ | ✅ | ✅ | Backend `RoleChecker(["SUPERVISOR", "ADMIN"])` + confirmation required |
| Manage User Roles & Accounts | ❌ | ❌ | ✅ | Backend `RoleChecker(["ADMIN"])` |

### 6.3 Seeded Accounts (Configuration Baseline)
- **Field Inspector:** `DOCA-INSP-842` | Password: `admin123` | Role: `INSPECTOR`
- **Supervisory Officer:** `DOCA-SUP-101` | Password: Configured via `SEED_SUPERVISOR_PASSWORD` | Role: `SUPERVISOR`
- **Department Director:** `DOCA-ADMIN-001` | Password: `admin123` | Role: `ADMIN`

---

## PART 7 — DATABASE MASTER MAP

*(See `NIRIKSHA_DATABASE_REFERENCE.md` for full column schemas and DDL definitions).*

### 7.1 Relational Schema Summary
The database consists of 15 tables hosted on Neon PostgreSQL:
1. `users` — Officer directory and credentials.
2. `inspections` — Master compliance audit records.
3. `products` — Inspected packaged commodity trade names, brands, and categories.
4. `product_images` — Uploaded packaging panel photographs and blur metrology scores.
5. `ocr_results` — Immutable baseline raw OCR text and bounding-box coordinates.
6. `declarations` — 8 statutory declaration records with optical verification and matrix flags.
7. `rule_versions` — Pinned statutory rule registry for legal repeatability.
8. `compliance_checks` — Rule evaluation findings with adjudication lifecycle states.
9. `evidence` — Photographic bounding-box crops supporting non-compliance findings.
10. `inspector_reviews` — Human-in-the-loop adjudication decision log.
11. `reports` — Statutory inspection reports sealed with SHA-256 hashes.
12. `audit_logs` — Immutable, append-only system audit trail.
13. `inspection_number_counters` — Atomic year-based sequence counters (`LM-2026-00042`).
14. `product_listings` — E-commerce online marketplace product information.
15. `listing_comparisons` — Discrepancy comparison between package OCR and online listings.

---

## PART 8 — API MASTER REFERENCE

*(See `NIRIKSHA_API_REFERENCE.md` for full parameter, body, and response payload catalogs across all 58 endpoints).*

### 8.1 API Group Summary
- **Authentication & Profile:** 5 endpoints (`/api/auth/*`, `/api/health`)
- **Dashboard & KPIs:** 6 endpoints (`/api/dashboard/*`)
- **Search & Repository:** 8 endpoints (`/api/repository/*`, `/api/inspections/search`, `/api/products/*`)
- **Inspection Management:** 4 endpoints (`/api/inspections`, `/api/inspections/{id}`, etc.)
- **Image Metrology:** 6 endpoints (`/api/inspections/{id}/images`, `/api/images/*`, `/api/quality-check`)
- **OCR & Declarations:** 8 endpoints (`/api/inspections/{id}/ocr`, `/api/declarations/*`, etc.)
- **Findings & Adjudication:** 8 endpoints (`/api/findings/*`, `/api/inspections/{id}/evaluate`, etc.)
- **Statutory Reports:** 7 endpoints (`/api/reports/*`, `/api/inspections/{id}/report/*`)
- **E-Commerce Surveillance:** 5 endpoints (`/api/inspections/{id}/listing/*`)
- **Supervisory Oversight:** 5 endpoints (`/api/supervisor/*`, destructive deletes)
- **Rules Registry & Users:** 6 endpoints (`/api/rules/*`, `/api/users/*`)

---

## PART 9 — FRONTEND SCREEN MAP

The mobile application is structured around a 20-screen React Navigation native stack:

1. **`IntroScreen`:** Official Department of Consumer Affairs branding sequence with hardware-accelerated video playback.
2. **`LoginScreen`:** Officer badge ID and password authentication with network connectivity detection.
3. **`DashboardScreen`:** Officer enforcement metrics, daily scan volume, pending adjudication alert cards, and quick navigation.
4. **`NewInspectionScreen`:** Package classification, trade name input, and GPS/reverse-geocoded location capture.
5. **`CaptureImagesScreen`:** Multi-panel photographic capture (front, back, side) with on-device blur assessment and image slot management.
6. **`AnalyzingScreen`:** Asynchronous OCR and layout analysis progress monitor with animated stage indicators and retry logic.
7. **`ExtractedDeclarationsScreen`:** Review of 8 extracted declarations, matrix badges (placement, readability, font size), and officer edit modal.
8. **`FindingsScreen`:** Tabbed view of preliminary findings (`All` vs. `Pending Adjudication`) with photographic evidence cards and 4 adjudication buttons.
9. **`EvidenceReviewScreen`:** Full-screen zoomable viewer for bounding-box crops and raw OCR text snippets.
10. **`ReviewAndSubmitScreen`:** Final inspection audit screen displaying complete compliance summary; enforces the zero-pending finalization gate.
11. **`ReportPreviewScreen`:** In-app preview of generated statutory report, SHA-256 verification hash, native share sheet, and DOCX download.
12. **`ReportsListScreen`:** Searchable archive of all completed and sealed inspection reports.
13. **`ProfileScreen`:** Officer credentials, jurisdiction zone, last login timestamp, and password change modal.
14. **`DraftOfflineScreen`:** Local vault of unsynced offline inspection drafts with manual sync trigger and status progress bars.
15. **`InspectionsScreen`:** Searchable registry of ongoing and historical inspections.
16. **`ListingComparisonScreen`:** Side-by-side comparison screen evaluating physical package OCR against online e-commerce listings.
17. **`SupervisorDashboardScreen`:** Jurisdiction-wide supervisory overview displaying zonal compliance rates and active inspector volume.
18. **`SupervisorAllInspectionsScreen`:** 18-attribute full inspection dossier table with multi-parameter filtering.
19. **`SupervisorInspectorsScreen`:** Inspector roster displaying inspection counts, violation detection ratios, and activity status.
20. **`SupervisorInspectionDetailScreen`:** Deep-dive dossier viewer enabling administrative report deletion or cascade cancellation.

---

## PART 10 — OCR SYSTEM

### 10.1 OCR Engine Hierarchy & Coordination
The optical character recognition pipeline is implemented in [`backend/ocr_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/ocr_service.py) via `ModularOCRService`:
1. **Primary Engine — PaddleOCR 3.x:**  
   - Initialized as a process-level singleton (`PaddleOCREngine._instance`).
   - Uses deep-learning text detection and recognition models with textline orientation classification (`use_textline_orientation=True`).
   - Maps 4-point polygon coordinates `[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]` to axis-aligned bounding boxes `[x1, y1, x2, y2]`.
   - Normalizes recognition confidence scores to a `0.0 - 1.0` float.
2. **Secondary Fallback Engine — Tesseract OCR:**  
   - Automatically discovers Tesseract binary across system PATH and standard installation paths (`find_tesseract_binary()`).
   - Configures `TESSDATA_PREFIX` to point to repository `backend/tessdata`.
   - Operates on multi-thresholded image variants if PaddleOCR fails.
3. **Tertiary Segmenter — Morphological OpenCV:**  
   - Uses adaptive thresholding and horizontal rectangular structuring elements to detect candidate text lines.
   - **Critical Invariant:** Detects geometric bounding boxes, but NEVER manufactures character text. Returns empty strings.

### 10.2 Performance Optimization & JIT Warmup
- **Warmup Amortization:** Cold-start PaddleOCR inference requires ~60-70 seconds on CPU due to kernel JIT compilation. `backend/main.py` launches `_startup_ocr_warmup()` in a background daemon thread at server startup, executing a synthetic 100x50 white image inference. Subsequent real requests execute at warm speed (~15-20 seconds per image).
- **Sequential Singleton Safety:** Benchmarking proved concurrent multi-threaded PaddleOCR CPU inferences corrupt shared BLAS thread memory and degrade speed by 15%. `OCR_CONCURRENT_IMAGES = 1` enforces safe sequential processing.

### 10.3 Preprocessing Pipeline
`ModularOCRService._prepare_variants()` generates 4 in-memory image variants without writing temporary files to disk:
1. **Otsu Thresholding:** Optimal binarization for high-contrast labels.
2. **CLAHE:** Contrast Limited Adaptive Histogram Equalization for glossy, reflective foil packaging.
3. **Adaptive Gaussian Thresholding:** Robust against uneven ambient lighting.
4. **Inverted Otsu:** For light text printed on dark packaging backgrounds.

### 10.4 The Core Safety Rule
**OCR non-detection or low confidence must NEVER automatically become a legal conviction.**  
If OCR fails or confidence is below 0.60:
- The declaration status becomes `LOW_CONFIDENCE` or `NOT_FOUND`.
- The rule engine evaluates the finding as `INSUFFICIENT_EVIDENCE` or `NEEDS_MANUAL_VERIFICATION`.
- It NEVER creates a `POTENTIAL_NON_COMPLIANCE` unless verified missing on a clear image by an inspecting officer.

---

## PART 11 — DECLARATION EXTRACTION

The statutory declaration extraction pipeline is implemented in [`backend/extraction_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/extraction_service.py):

### 11.1 The 8 Statutory Extracted Fields
1. **`commodity_name`:** Common or generic name of commodity (e.g. *Organic Oats*, *Toilet Soap*).
2. **`manufacturer_details`:** Complete name and physical postal address of manufacturer, packer, or importer.
3. **`net_quantity`:** Net weight, volume, or measure in SI units (g, kg, ml, L, count).
4. **`mrp`:** Maximum Retail Price with mandatory tax qualifier (*inclusive of all taxes*).
5. **`date_of_manufacture_packing`:** Month and year of manufacture, packaging, or import.
6. **`consumer_care_details`:** Contact person name, address, telephone (10-digit/1800), and email.
7. **`country_of_origin`:** Mandatory country of origin declaration (especially for imported commodities).
8. **`unit_sale_price`:** Unit price per gram/ml (mandated under GSR 779(E) 2021 amendment).

### 11.2 Spatial Layout Integration (PP-Structure)
`backend/layout_service.py` segments OCR boxes into functional regions before extraction:
- **`COMMODITY_TITLE_REGION`:** Disqualifies nutrition tables, ingredients, and marketing slogans.
- **`ADDRESS_REGION`:** Clusters multi-line premise, street, city, state, and 6-digit PIN codes.
- **`PRICE_DATE_REGION`:** Associates "MRP" labels with numerical currency and date blocks.

### 11.3 Cross-Image Merging & Conflict Resolution
When an inspection contains front, back, and side panel photographs, `cross_image_verification()` merges declarations:
- **Scenario A (Agreement):** High-confidence extractions match across panels -> merged with highest confidence.
- **Scenario B (Genuine Conflict):** Two reliable (>=0.85 conf) panels report contradictory values (e.g. Front: "500g", Back: "400g") -> flagged as `CONFLICTING` / `NEEDS_MANUAL_VERIFICATION`.
- **Scenario C (Noise Discarded):** One high-confidence extraction agrees; one low-confidence noisy reading differs -> high-confidence reading is kept; low-confidence noise is discarded.
- **Scenario D (Insufficient Evidence):** All readings across panels are low confidence -> merged as `LOW_CONFIDENCE` / `NEEDS_MANUAL_VERIFICATION`.

---

## PART 12 — COMPLIANCE & STATUTORY RULE ENGINE

Implemented in [`backend/rule_engine/engine.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/rule_engine/engine.py), the `DeterministicRuleEngine` evaluates effective declarations against 12 version-pinned rules:

### 12.1 Pinned Statutory Rules Registry
| Rule Code | Statutory Citation | Exact Description | Category | Severity |
|---|---|---|---|---|
| `PCR_RULE_06_1_E` | Rule 6(1)(e) & Rule 2(m) | MRP in Indian Rupees inclusive of all taxes | Category A | CRITICAL |
| `PCR_RULE_06_1_A` | Rule 6(1)(a) & Explanations | Name & complete address of manufacturer/packer | Category A | CRITICAL |
| `PCR_RULE_06_1_C` | Rule 6(1)(c) & Rules 11-13 | Net quantity in standard metric units (kg, g, L, ml) | Category A | CRITICAL |
| `PCR_RULE_06_1_D` | Rule 6(1)(d) & Explanations | Month and year of manufacture or packing | Category A | MAJOR |
| `PCR_RULE_06_1_G` | Rule 6(2) | Consumer grievance redressal phone, email, address | Category A | MAJOR |
| `PCR_RULE_06_1_F` | Rule 6(1)(b) | Generic or common commodity identification | Category A | MAJOR |
| `PCR_RULE_06_1_B` | Rule 6(1)(a) Proviso & Rule 10 | Country of origin (verified on imported goods) | Category A | MAJOR |
| `PCR_RULE_UNIT_SALE_PRICE`| GSR 779(E) Amendment | Unit sale price declaration (Rs. per g/ml) | Category A | MINOR |
| `DATA_QUAL_PHONE_SYNTAX` | Rule 6(2) Guidelines | 10-digit mobile, landline, or 1800 toll-free syntax | Category B | MINOR |
| `DATA_QUAL_DATE_PLAUSIBILITY`| Rule 6(1)(d) Standards | Chronological plausibility & future-date check | Category B | MINOR |
| `PCR_RULE_06_10_ECOMMERCE_DECLARATION`| Rule 6(10) | E-commerce mandatory digital display | Category A | MAJOR |
| `PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING`| Rule 18(2A) & Sec 36(1) | Prohibition of online sale above printed MRP | Category A | CRITICAL |

### 12.2 Rule Evaluation States
- `PASS`: Requirement satisfied by verified/effective declaration.
- `POTENTIAL_NON_COMPLIANCE`: Clear violation (e.g. MRP missing mandatory tax qualifier).
- `INSUFFICIENT_EVIDENCE`: Package image blurred or text unreadable.
- `NEEDS_MANUAL_VERIFICATION`: Cross-image conflict or missing country of origin on unverified domestic good.
- `NOT_APPLICABLE`: Rule legally exempt for this commodity size or context.

---

## PART 13 — FONT SIZE, READABILITY & PLACEMENT

### 13.1 Font Size & Numeral Height Analysis
Implemented in [`backend/font_size_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/font_size_service.py):
- **Statutory Standard:** PCR 2011 Rule 9, Table 1 specifies mandatory minimum numeral heights:
  - Net Quantity $\le 50\text{ g/ml}$: Minimum height $1.0\text{ mm}$ (Normal), $2.0\text{ mm}$ (Molded).
  - Net Quantity $50\text{ g/ml} - 200\text{ g/ml}$: Minimum height $2.0\text{ mm}$ (Normal), $4.0\text{ mm}$ (Molded).
  - Net Quantity $200\text{ g/ml} - 1000\text{ g/ml}$: Minimum height $4.0\text{ mm}$ (Normal), $6.0\text{ mm}$ (Molded).
  - Net Quantity $> 1\text{ kg/L}$: Minimum height $6.0\text{ mm}$ (Normal), $6.0\text{ mm}$ (Molded).
- **ML Integration:** `font_size_model.joblib` (`GradientBoostingRegressor`) predicts physical height.
- **Critical Anti-Fabrication Rule:** Pixel height alone is NOT physical millimeters. If an image lacks physical calibration references (known package dimensions or barcode calibration scale), the system strictly returns `FONT_SIZE_UNDETERMINABLE` or `MANUAL_VERIFICATION_REQUIRED`. It NEVER fabricates millimeters from uncalibrated pixels.

### 13.2 Declaration Readability Analysis
Implemented in [`backend/readability_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/readability_service.py):
- **Statutory Standard:** Rules 6 & 7 require declarations to be conspicuous, legible, and prominent.
- Evaluates localized bounding-box crop:
  - Local Laplacian blur variance.
  - Michelson & RMS contrast.
  - Optical character visibility & OCR confidence.
  - Classical ML inference via `readability_model.joblib` (`LogisticRegression`).
- **Quality Gate:** Requires at least 200 crop pixels. Below this gate, routes to `UNCERTAIN` — never an automatic violation.

### 13.3 Declaration Placement Analysis
Implemented in [`backend/placement_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/placement_service.py):
- **Statutory Standard:** Rules 7 & 12 require Net Quantity and Commodity Name on the **Principal Display Panel (PDP / Front Panel)**.
- Manufacturer address, consumer care, and date information may appear on the **Information Panel (Back/Side)**.
- If panel boundaries cannot be determined with certainty, routes to `PLACEMENT_UNCERTAIN` or `MANUAL_VERIFICATION_REQUIRED`.

---

## PART 14 — FINDINGS & ADJUDICATION LIFECYCLE

### 14.1 Finding Lifecycle
1. Rule Engine runs ➔ Compliance checks created with `adjudication_status = 'PENDING'`.
2. Each non-pass check creates an associated `evidence` record with a cropped image file path.
3. The Inspecting Officer inspects the finding in `FindingsScreen.tsx`.

### 14.2 Supported Adjudication Actions
- `CONFIRMED`: Officer agrees the package violates the statutory rule. The finding transitions to confirmed non-compliance.
- `DISMISSED`: Officer overrules the finding (e.g. declaration was handwritten or embossed). Requires mandatory statutory justification in remarks.
- `CORRECTED`: Officer fixes an OCR misread. Triggers automatic re-evaluation of dependent rules.
- `NOT_APPLICABLE`: Officer marks commodity exempt under specific rule provisos.
- `NEEDS_MORE_EVIDENCE`: Officer flags photograph as inadequate, requesting panel re-capture.

### 14.3 Authoritative Finalization Gate
`POST /api/inspections/{id}/finalize` enforces:
$$\text{COUNT}(\text{compliance\_checks where adjudication\_status} = \text{'PENDING'}) == 0$$
If any finding is pending, the API returns HTTP 400 Bad Request, blocking report generation.

---

## PART 15 — STATUTORY REPORT GENERATION

Implemented in [`backend/report_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/report_service.py) and [`backend/reportlab_report_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/reportlab_report_service.py):

### 15.1 Statutory Report Structure (ReportLab PDF)
1. **Official Header:** Ministry of Consumer Affairs, DoCA emblem, national coat-of-arms styling.
2. **Inspection Dossier Block:** Unique inspection number, date, inspecting officer name, badge ID, zone, location.
3. **Commodity Identification:** Declared trade name, brand owner, category, batch number.
4. **Packaging Panels Evidence Plate:** High-resolution photographs of front, back, and side packaging panels.
5. **Sealed Statutory Declarations Table:** The 8 verified declarations with verification provenance.
6. **Unified Compliance Matrix:** 8-dimensional table (`| Declaration | Present | Correct | Readable | Placement | Font Size | Format | Status |`).
7. **Statutory Findings & Rule Violations:** Rule code, legal citation, violation explanation, and officer remarks.
8. **Photographic Evidence Crops:** Bounding-box crops highlighting physical package defects.
9. **Rule 19 Statutory Notice:** Mandatory disclaimer that inspection evaluates printed packaging labels and does not certify physical net contents.
10. **Officer Cryptographic Sign-Off:** Digital signature block with date and SHA-256 seal.

### 15.2 Tamper-Evident Hashing & Immutability
- Upon generation, a cryptographic SHA-256 digest is calculated over the raw PDF binary.
- Hash is saved in `reports.pdf_hash` and displayed on the report title block.
- **Idempotency Guard (AUDIT-REP-01):** Once generated, viewing the report returns the existing file. Version numbers increment only upon explicit re-generation.
- Editable Word DOCX mirrors are generated via `python-docx`.

---

## PART 16 — OFFLINE ARCHITECTURE & SYNCHRONIZATION

### 16.1 What Works 100% Offline
- Creation of inspection drafts in `NewInspectionScreen.tsx`.
- Reverse geocoding fallback (GPS string stored if reverse geocoding API unreachable).
- Multi-panel camera capture (front, back, side) saved to native device file storage.
- On-device image quality pre-check (`imageQualityService.ts`).
- Storage of drafts in native `AsyncStorage` under `legal_metrology_offline_drafts_v1`.
- Local draft queue management in `DraftOfflineScreen.tsx`.

### 16.2 What DOES NOT Work Offline
- PaddleOCR and Tesseract character recognition (requires backend compute).
- PyZbar barcode and QR decoding.
- Deterministic legal rule evaluation.
- Analytical ML models (font size regressor, readability classifier).
- ReportLab PDF and DOCX generation.
- Supervisor dossier management and audit log recording.

### 16.3 Synchronization Engine (`syncService.ts`)
- Automated background sync triggered by `@react-native-community/netinfo` transition from `OFFLINE` to `ONLINE`.
- Step 1: `POST /api/inspections` with `client_draft_id`. If draft was previously synced, backend returns existing record without duplicating.
- Step 2: Uploads panel images sequentially. If ANY image upload fails, sync aborts, rolls back to `READY_FOR_SYNC`, and preserves all local images.
- Step 3: Once all images are confirmed, triggers `POST /api/inspections/{id}/ocr`.

---

## PART 17 — SUPERVISORY SYSTEM

Implemented in [`backend/main.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py:4206-4750):

### 17.1 Supervisory Capabilities
- **Zonal Dashboard (`/api/supervisor/dashboard`):** Aggregates total scans, compliance percentages, violation distribution, and active inspector counts across the jurisdiction.
- **18-Attribute Dossier Repository (`/api/supervisor/inspections`):** Search, filter, and review complete dossiers across all officers in the zone.
- **Inspector Roster (`/api/supervisor/inspectors`):** Tracks officer scan volume, violation rates, and last login timestamps.
- **Administrative Report Deletion (`DELETE /api/inspections/{id}/report`):** Requires written statutory justification. Deletes PDF/DOCX files from disk, removes `reports` record, reverts inspection status to `ANALYSIS_COMPLETE`, and writes permanent audit log.
- **Cascade Inspection Deletion (`DELETE /api/inspections/{id}`):** Deletes entire relational tree and unlinks images from disk. Associated audit log records survive with `inspection_id = NULL`.

### 17.2 What Supervisors CANNOT Do
- Supervisors CANNOT alter or forge an inspector's recorded field observations.
- Supervisors CANNOT tamper with raw OCR transcripts stored in `ocr_results`.
- Inspectors are strictly forbidden (HTTP 403) from calling any `/api/supervisor/*` endpoint.

---

## PART 18 — DATA INTEGRITY & SECURITY

1. **SQL Injection Protection:** 100% parameterized queries via SQLAlchemy 2.0 ORM. Raw SQL queries use `sqlalchemy.text()` with bound parameters.
2. **File Upload Security:** Enforces strict MIME-type whitelist (`image/jpeg`, `image/png`, `image/webp`). Rejects zero-byte files and files exceeding 15MB. Filenames are sanitized via UUID generation to prevent directory traversal (`../../`).
3. **Protected Image Binary Access:** Image downloads via `/api/images/{id}/file` verify that the requesting officer owns the inspection or possesses supervisory oversight.
4. **Android Network Security:** Cleartext traffic disabled globally in production. `network_security_config.xml` permits cleartext HTTP only to explicit development hosts (`10.0.2.2`, `127.0.0.1`, LAN).
5. **Cross-Inspector Isolation:** Field inspectors querying dashboards or repositories only receive inspections matching their `inspector_id`.

---

## PART 19 — ENVIRONMENT & DEPLOYMENT

### 19.1 Environment Configurations
- **Development:** FastAPI on `127.0.0.1:8000`. Android reaches host via `10.0.2.2:8000` (or `adb reverse tcp:8000 tcp:8000`). Database is Neon PostgreSQL.
- **Production:** Uvicorn ASGI behind Nginx reverse proxy with TLS 1.3 termination. Neon PostgreSQL with `sslmode=require`. Startup DDL and seeding disabled (`ENVIRONMENT=production`).

### 19.2 Mandatory Environment Variables (`.env`)
```bash
# Core Settings
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://user:password@ep-host.us-east-2.aws.neon.tech/neondb?sslmode=require
SECRET_KEY=your-secure-random-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Test Database Isolation (Mandatory for test execution)
TEST_DATABASE_URL=postgresql+psycopg://user:password@ep-test-host.us-east-2.aws.neon.tech/neondb_test?sslmode=require

# OCR Configuration
OCR_ENGINE=auto
PADDLE_OCR_ENABLED=true
PADDLE_OCR_LANG=en
MAX_OCR_DIMENSION=1024
OCR_CONCURRENT_IMAGES=1
OCR_WARMUP_ON_STARTUP=true

# Mobile Configuration (mobile/.env)
EXPO_PUBLIC_API_URL=http://10.0.2.2:8000
```

---

## PART 20 — TESTING & QUALITY ASSURANCE

### 20.1 Actual Current Test Counts
- **Backend Test Suite (Pytest):** **522 automated tests** across 61 test files.
  - Execution command: `venv\Scripts\pytest.exe -v`
  - Collection verification: `venv\Scripts\pytest.exe --collect-only -q` (522 tests collected in 5.24s).
- **Mobile Test Suite (Jest):** **138 automated tests** across 13 test suites.
  - Execution command: `cd mobile && npm test`
  - Results: 13 passed, 13 total; 138 passed, 138 total in 32.54s.

### 20.2 Test Coverage Matrix
| Subsystem | Test Type | File Location | Key Test Assertions |
|---|---|---|---|
| Concurrency & Numbering | Concurrency / Load | `tests/test_inspection_number_concurrency.py` | 10 & 25 concurrent worker threads allocating sequential numbers without duplicates or gaps |
| PostgreSQL Architecture | Configuration Safety | `tests/test_postgres_only_architecture.py` | Rejection of SQLite schemes, fail-fast on missing DATABASE_URL |
| Test DB Safety | Isolation | `tests/test_database_safety.py` | Verification that TEST_DATABASE_URL != DATABASE_URL |
| Rule Engine | Unit & Deterministic | `tests/test_deterministic_rule_engine.py` | Complete package PASS, missing fields POTENTIAL_NON_COMPLIANCE |
| Adjudication Lifecycle | State Machine | `tests/test_findings_pending_adjudication.py` | Canonical pending counts across CONFIRMED, DISMISSED, CORRECTED |
| Report Immutability | Security & Tamper | `tests/test_report_immutability.py` | Blocked deletions by inspectors, SHA-256 hash preservation |
| Mobile Navigation & Sync | E2E & Component | `mobile/src/screens/__tests__/*` | 15/15 specification tests passing for adjudication, offline draft queue |

---

## PART 21 — CURRENT MEASURED PERFORMANCE

All measurements taken on standard x86_64 host (Intel Core i7 / 16GB RAM):
- **Health Probe (`GET /api/health`):** $15\text{ ms} - 25\text{ ms}$.
- **Dashboard Summary (`GET /api/dashboard/summary`):** $45\text{ ms} - 70\text{ ms}$ (PostgreSQL indexed query).
- **Package Image Upload (1080p JPEG, 2MB):** $180\text{ ms} - 240\text{ ms}$ (including BlurDetection2 quality assessment).
- **PaddleOCR Cold-Start Inference (First Run):** ~65 seconds (amortized to 0 ms for users via startup background warmup).
- **PaddleOCR Warm Sequential Inference:** $14\text{ s} - 18\text{ s}$ per packaging panel image.
- **PP-Structure Layout & Regex Extraction:** $120\text{ ms} - 250\text{ ms}$.
- **Deterministic Rule Engine Evaluation:** $35\text{ ms} - 55\text{ ms}$ across all 12 statutory rules.
- **ReportLab PDF Report Generation:** $450\text{ ms} - 800\text{ ms}$ (multi-page A4 with embedded evidence crops and SHA-256 hash).
- **python-docx DOCX Generation:** $150\text{ ms} - 220\text{ ms}$.

---

## PART 22 — KNOWN LIMITATIONS & ARCHITECTURAL WORKAROUNDS

| Issue / Limitation | Severity | Current State | Workaround / Mechanism | Relevant Files |
|---|:---:|---|---|---|
| **CPU OCR Latency** | MEDIUM | PaddleOCR CPU takes ~15s per image | Amortized startup JIT warmup thread; sequential single-worker execution prevents CPU thrashing | `backend/ocr_service.py`, `backend/main.py` |
| **Physical Font Size Calibration** | LOW | Cannot measure mm without scale reference | Strictly returns `FONT_SIZE_UNDETERMINABLE` if uncalibrated; prevents false convictions | `backend/font_size_service.py` |
| **Android Cleartext in Dev** | LOW | HTTP required for local dev | Dedicated `network_security_config.xml` whitelists only `10.0.2.2` and localhost; cleartext disabled for all other hosts | `mobile/android/.../network_security_config.xml` |
| **Android SecureStore 2KB Limit** | RESOLVED | SecureStore loses large drafts | Migrated draft vault to `@react-native-async-storage/async-storage` | `mobile/src/services/draftStorage.ts` |
| **Report Version Inflation on View** | RESOLVED | Opening preview created v2, v3 | Added idempotency check in `generate_inspection_report` returning existing report if file exists | `backend/main.py`, `mobile/src/screens/ReportPreviewScreen.tsx` |

---

## PART 23 — PROJECT HISTORY & AUDIT TIMELINE

1. **Phase 1 — Initial SIH Prototype:** Built with basic Flask/FastAPI prototypes and local SQLite storage.
2. **Phase 2 — Legal Metrology Engine:** Implemented deterministic rule engine mapped to PCR 2011 clauses.
3. **Phase 3 — Post-Migration PostgreSQL Enforcement (`ea37b41`):** Complete elimination of SQLite from runtime and test suites; migration of all relational schemas to Neon Serverless PostgreSQL (`psycopg3`).
4. **Phase 4 — Audit Remediation & Hardening (`822d7df`, `f8b87ee`):**
   - Implemented atomic sequence numbering via `inspection_number_counters` (AUDIT-CONCUR-01).
   - Fixed report preview version inflation and established report idempotency (AUDIT-REP-01).
   - Migrated offline draft storage to AsyncStorage (AUDIT-MOB-01).
   - Aligned review screen finalization gate with schema properties (AUDIT-MOB-02).
   - Integrated trained ML models (`font_size_model.joblib`, `readability_model.joblib`).
5. **Phase 5 — Supervisory Subsystem & ReportLab Sealing (`ddd62b3`):** Added 18-attribute supervisor dossier repository, audited report/inspection deletion, and cryptographic SHA-256 PDF sealing.
6. **Phase 6 — OCR Optimization & Physical Device Polishing (`a9185f4`, `3a7f8d0`, `77ec172`):** Implemented startup JIT warmup thread, resolved physical Android device video rendering, and fixed dashboard registry layout.

---

## PART 24 — DEVELOPMENT CONVENTIONS & CHANGE-IMPACT RULES

### 24.1 Naming & Architecture Conventions
- **Database Models (`backend/models.py`):** Table names in `snake_case` plural (`compliance_checks`, `product_images`). Primary keys are `VARCHAR(36)` UUIDs.
- **Pydantic Schemas (`backend/schemas.py`):** Request models suffixed with `Request` (`CreateInspectionRequest`), responses with `Response` (`InspectionResponse`).
- **Mobile Components (`mobile/src/screens/`):** React functional components suffixed with `Screen` (`DashboardScreen.tsx`). Strict TypeScript types in `navigation/types.ts`.

### 24.2 Dependency & Change-Impact Rules
- **"If you modify `Inspection` or `Product` in `backend/models.py`":**
  1. Update `backend/schemas.py` (`InspectionResponse`, `InspectionDetailResponse`).
  2. Update `backend/main.py` route serializers.
  3. Update `mobile/src/screens/NewInspectionScreen.tsx`, `DashboardScreen.tsx`, `ReviewAndSubmitScreen.tsx`.
  4. Update `backend/report_service.py` PDF/DOCX templates.
  5. Run `tests/test_complete_post_image_workflow.py`.
- **"If you modify OCR or Extraction in `backend/ocr_service.py` or `backend/extraction_service.py`":**
  1. Ensure no character text is manufactured on empty/noisy pixels.
  2. Verify bounding box scaling between preprocessed and original image dimensions.
  3. Check cross-image conflict logic in `cross_image_verification()`.
  4. Run `tests/test_paddleocr_integration.py` and `tests/test_real_package_acceptance.py`.
- **"If you modify the Rule Engine in `backend/rule_engine/`":**
  1. Never change rule definitions without verifying the statutory reference in `PCR 2011`.
  2. Maintain the safety rule: uncertainty ➔ `INSUFFICIENT_EVIDENCE` or `NEEDS_MANUAL_VERIFICATION`.
  3. Run `tests/test_deterministic_rule_engine.py` and `tests/test_final_corrections.py`.

---

## PART 25 — CRITICAL PROJECT INVARIANTS — DO NOT BREAK

1. **PostgreSQL/Neon is the Sole Database Backend:** SQLite is strictly forbidden across production, dev, and test.
2. **Production/Test Database Isolation:** Test runner aborts immediately if `TEST_DATABASE_URL` matches `DATABASE_URL`.
3. **No Synthetic Text Fabrication:** OCR and OpenCV modules must never manufacture character text from thin air.
4. **The Safety Rule:** Optical blur or low confidence must never automatically create a legal violation.
5. **Inspector is the Final Adjudicator:** Automated findings are preliminary. Only an officer's `CONFIRMED` decision creates a statutory violation.
6. **Strict Finalization Gate:** Inspections cannot be finalized or generate reports while any finding remains `PENDING`.
7. **Report Hash Sealing:** Generated PDF reports must have their SHA-256 hash calculated over the exact binary and stored in `reports.pdf_hash`.
8. **Atomic Concurrency Numbering:** Inspection numbers must be allocated via atomic SQL `UPDATE ... RETURNING` on `inspection_number_counters`.
9. **Draft Idempotency:** Submitting the same `client_draft_id` multiple times must never create duplicate inspections.
10. **Evidence Immutability:** Once an inspection is finalized or has a generated report, its images and declarations cannot be deleted or mutated by inspectors.

---

## PART 26 — "HOW TO THINK ABOUT THIS PROJECT"

When reasoning about NiriKsha, view it as a **statutory evidentiary pipeline**:
- It is NOT an e-commerce catalog or a generic document scanner.
- It is a legal enforcement tool whose outputs may be presented in Indian consumer courts or appellate tribunals under the Legal Metrology Act, 2009.
- Therefore, **false positives (falsely accusing a business of a crime due to a blurred image or OCR misread) are catastrophic**. The architecture is deliberately engineered with conservative safety gates: if the AI is unsure, it flags the issue for human inspection rather than claiming a violation.
- Every piece of data must be traceable: from the physical package panel image, to the pixel bounding-box crop, to the raw OCR text, to the officer's correction, to the deterministic rule clause, to the signed PDF report hash.

---

## PART 27 — FILE-LEVEL KNOWLEDGE MAP

| File Path | Core Purpose | Critical Symbols / Classes | Depends On | Used By | Safe to Modify? |
|---|---|---|---|---|:---:|
| `backend/main.py` | Primary API Gateway | `app`, `allocate_inspection_number`, `generate_inspection_report` | `models`, `schemas`, `services` | Uvicorn, Mobile Client | ⚠️ HIGH RISK |
| `backend/models.py` | Relational ORM Models | `User`, `Inspection`, `Declaration`, `ComplianceCheck`, `Report` | SQLAlchemy Base | All backend modules | ⚠️ CRITICAL |
| `backend/database.py` | DB Engine & Connection Pool | `engine`, `get_db`, `verify_test_database_safety` | `config.py` | `main.py`, `models.py` | ⚠️ CRITICAL |
| `backend/config.py` | App Configuration & Guards | `Settings`, `validate_database_url` | `pydantic-settings` | Entire backend | ⚠️ CRITICAL |
| `backend/rule_engine/engine.py` | Deterministic Rule Evaluator | `DeterministicRuleEngine.evaluate_inspection` | `registry.py`, `models.py` | `main.py` | ⚠️ HIGH RISK |
| `backend/rule_engine/registry.py` | Statutory Rule Definitions | `STATUTORY_RULE_REGISTRY` | `models.py` | `engine.py`, `seed.py` | ⚠️ HIGH RISK |
| `backend/ocr_service.py` | OCR Coordinator & Engines | `ModularOCRService`, `PaddleOCREngine` | OpenCV, PaddleOCR | `main.py`, `extraction.py`| ⚠️ HIGH RISK |
| `backend/extraction_service.py` | Statutory Field Extractor | `DeterministicRegexExtractor`, `cross_image_verification` | `layout_service.py` | `main.py` | ⚠️ HIGH RISK |
| `backend/report_service.py` | Statutory Report Generator | `StatutoryReportGenerator.generate_pdf` | ReportLab, python-docx | `main.py` | ⚠️ MEDIUM RISK |
| `mobile/src/services/api.ts` | Mobile HTTP Client | `api`, `classifyFetchError`, `getApiBaseUrl` | NetInfo, authStorage | All mobile screens | ⚠️ HIGH RISK |
| `mobile/src/services/syncService.ts` | Offline Sync Coordinator | `syncService.syncDraft` | `api.ts`, `draftStorage.ts` | `NewInspection`, `DraftOffline` | ⚠️ HIGH RISK |

---

## PART 28 — QUICK START FOR ANOTHER LLM

If you have only 10 minutes to understand or modify NiriKsha:
1. **Read these 3 files first:** `backend/models.py`, `backend/rule_engine/engine.py`, `backend/main.py`.
2. **Remember the golden rule:** *Never manufacture character text, never convert OCR uncertainty into a legal violation, never use SQLite.*
3. **Run this before touching code:** `venv\Scripts\pytest.exe --collect-only -q` (must collect 522 tests).
4. **Run this after touching backend code:** `venv\Scripts\pytest.exe tests/test_database_safety.py tests/test_final_corrections.py -v`.
5. **Run this after touching mobile code:** `cd mobile && npm test` (must pass 138 tests).

---

## PART 29 — UNKNOWN / UNVERIFIED INFORMATION

To maintain strict technical accuracy, the following items could not be independently verified from the repository state:
1. **Live Production Neon Credentials:** Production database credentials are not checked into the repository (only environment variable references and `.env.example` templates exist).
2. **Physical Cloud Storage Deployment:** Supabase storage adapter (`backend/supabase_storage.py`) exists in code but is currently bypassed in favor of local persistent directories (`uploads/`, `generated_reports/`).
3. **Qwen2.5-VL Remote Endpoint:** The vision-language model integration (`backend/vlm_service.py`) operates in mock mode by default (`VLM_PROVIDER=mock`, `VLM_ENABLED=False`) unless connected to a live vLLM/OpenAI-compatible inference server.
