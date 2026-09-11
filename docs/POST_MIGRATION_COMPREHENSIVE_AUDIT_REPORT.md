# NiriKsha — Post-Migration Comprehensive Audit Report

**Date**: September 8, 2026  
**Audited Target**: Full Project Codebase (Backend, Frontend/Web, React Native Mobile, Android Native Modules, PostgreSQL/Neon Production)  
**Lead Auditor**: Antigravity Core Autonomous Database & Systems Engineering Team  
**Audit Scope**: Complete Read-Only Multi-Layer System Inspection across 59 Statutory, Architectural, and Security Categories.

---

## 1. Executive Summary

Following the successful execution and live verification of the **SQLite → Neon PostgreSQL Production Migration** (`PRODUCTION MIGRATION VERIFIED`), a comprehensive, read-only system audit was conducted across all 59 required functional, security, data integrity, and mobile operational categories.

The production database architecture is verified as:
```
React Native Mobile (Android) / Web (Expo)
    ↓  [JWT Bearer HTTPS]
FastAPI (RESTful Application Server)
    ↓  [SQLAlchemy 2.0 ORM + psycopg v3 Driver]
PostgreSQL (Dedicated AWS us-east-2 Cluster)
    ↓
Neon Production Database (neondb)
```

The audit confirmed that:
1. **Zero Database Corruption**: The SQLite golden source (`legal_metrology.db`, 348,160 bytes, 227 rows) remains 100% untouched and byte-identical to its pre-migration backup.
2. **Relational Integrity**: The Neon Production database contains the exact 126-record legitimate DAG graph with 0 orphan foreign keys and complete UUID preservation.
3. **Statutory Enforcement**: Mandatory human-in-the-loop adjudication, immutable audit logging, physical net quantity disclaimers, and 9 PCR 2011 statutory rules are rigorously enforced at the API and database levels.
4. **Automated Test Health**: 
   - Backend regression: **271 passed, 1 skipped (0 failures, 0 errors)** in 258.71s.
   - PostgreSQL integration: **1 passed** in 3.74s.
   - Mobile TypeScript compilation: **0 errors** (`tsc --noEmit`).
   - Mobile unit test suite: **19 passed** in 0.93s.
   - Frontend web bundle export: **Cleanly exported** (`dist/`, 527 modules, 1.35 MB JS).
   - Android native module build: **`BUILD SUCCESSFUL in 2m 11s`** (all 10 native gradle tasks resolved).

However, the audit identified **10 specific issues** (0 Critical, 3 High, 4 Medium, 3 Low) spanning offline storage limits, frontend property mismatch in finalization pre-checks, report version incrementing on preview, and mobile configuration defaults. None of these issues corrupt production data or compromise the completed migration, but they represent important pre-release refinements.

---

## 2. Overall Status

### **`PRODUCTION OPERATIONAL — PRE-RELEASE REMEDIATION RECOMMENDED`**

- **Database Migration**: `VERIFIED & LOCKED`
- **Backend API & PostgreSQL Runtime**: `STABLE & VERIFIED`
- **Automated Regression Suites**: `100% PASSING`
- **Release Readiness**: `READY FOR CONTROLLED PILOT / SIH DEMO` (Production public general release should address High/Medium issues).

---

## 3. Critical Findings (0 Issues)
*No CRITICAL issues detected. Database integrity, authentication, encryption, and statutory rule evaluation are intact with zero data-loss risks.*

---

## 4. High Findings (3 Issues)

### [AUDIT-MOB-01] Offline Draft Storage Uses Expo SecureStore with 2KB Hardware Limit
- **Severity**: **HIGH**
- **Component**: Mobile / Offline Storage
- **File**: [`mobile/src/services/draftStorage.ts:237`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/services/draftStorage.ts#L237)
- **Problem**: `draftStorage.persistDrafts` uses `SecureStore.setItemAsync(DRAFTS_STORAGE_KEY, jsonStr)` to store the entire JSON array of offline inspection drafts (`LocalDraft[]`).
- **How Discovered**: Source code inspection of native offline persistence implementation.
- **Evidence**:
  ```typescript
  // mobile/src/services/draftStorage.ts:236-241
  } else {
    await SecureStore.setItemAsync(DRAFTS_STORAGE_KEY, jsonStr);
  }
  ```
- **Expected Behavior**: Large structured offline data (inspection metadata, image file paths, quality scores, GPS coordinates) should be stored in `AsyncStorage` or native file system (`expo-file-system`).
- **Actual Behavior**: `expo-secure-store` is backed by Android Keystore / SharedPreferences with a strict ~2048-byte entry limit. When multiple drafts or extensive metadata are accumulated offline, `setItemAsync` throws a size exceeded error. The error is caught by `console.warn`, resulting in silent failure to persist drafts across app restarts.
- **Security/Data/Legal Impact**: Potential loss of offline inspection records captured in rural/remote zones before connectivity is restored.
- **Recommended Fix**: Migrate `draftStorage` to `@react-native-async-storage/async-storage` or `expo-file-system` for draft JSON, retaining `SecureStore` exclusively for JWT authentication tokens.
- **Production Data Affected**: No.
- **Migration Affected**: No.
- **Verification Test Required**: Store 5 multi-image offline drafts in mobile mock store and verify complete JSON serialization and persistence across application reboots.

---

### [AUDIT-MOB-02] Property Mismatch in Client-Side Finalization Pre-Check
- **Severity**: **HIGH**
- **Component**: Mobile / Finalization Gate UI
- **File**: [`mobile/src/screens/ReviewAndSubmitScreen.tsx:58-68`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReviewAndSubmitScreen.tsx#L58-L68)
- **Problem**: The client-side unadjudicated findings pre-check in `ReviewAndSubmitScreen.tsx` queries obsolete property names `f.status`, `f.check_status`, and `f.inspector_action`.
- **How Discovered**: Cross-referencing `FindingResponse` schema in `backend/schemas.py:178-181` with client-side filter logic in `ReviewAndSubmitScreen.tsx`.
- **Evidence**:
  ```typescript
  // mobile/src/screens/ReviewAndSubmitScreen.tsx:58-67
  const unadjudicatedFindings = findings.filter((f) => {
    const s = (f.status || f.check_status || '').toUpperCase();
    const isNonPass = s === 'POTENTIAL_NON_COMPLIANCE' || s === 'WARNING' || ...;
    const action = (f.inspector_action || '').toUpperCase();
    const isPending = !action || action === 'PENDING';
    return isNonPass && isPending;
  });
  ```
- **Expected Behavior**: Client evaluates `f.result_state` and `f.adjudication_status`. If non-PASS findings are pending, it displays a friendly modal guiding the officer to adjudicate.
- **Actual Behavior**: Because `f.status` and `f.inspector_action` are `undefined`, `unadjudicatedFindings` always evaluates to `[]`. The client sends `POST /api/inspections/{id}/finalize` prematurely. While the backend statutory gate correctly halts finalization with **HTTP 409 Conflict**, the user receives an unhandled server error alert rather than an intuitive UI navigation prompt.
- **Security/Data/Legal Impact**: Human-in-the-loop integrity remains protected by the backend gate, but UI UX is degraded with confusing error messages.
- **Recommended Fix**: Align property names in `ReviewAndSubmitScreen.tsx` to `f.result_state` and `f.adjudication_status`.
- **Production Data Affected**: No.
- **Migration Affected**: No.
- **Verification Test Required**: Render `ReviewAndSubmitScreen` with unadjudicated findings and assert that the client-side warning dialog triggers upon tapping "Finalize".

---

### [AUDIT-REP-01] ReportPreviewScreen Inadvertently Increments Report Version on Every View
- **Severity**: **HIGH**
- **Component**: Mobile / Backend Reports Lifecycle
- **File**: [`mobile/src/screens/ReportPreviewScreen.tsx:37`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ReportPreviewScreen.tsx#L37) & [`backend/main.py:1550-1552`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L1550-L1552)
- **Problem**: `ReportPreviewScreen.tsx` checks `if (!data || !data.report_number)` before calling `api.generateReport(inspectionId)`. Because `ReportResponse` does not define `report_number` (it defines `inspection_number` and `report_version`), `data.report_number` is always `undefined`.
- **How Discovered**: Auditing report lifecycle endpoints and observing why `LM-2026-00001` reached `report_version = 3` during testing.
- **Evidence**:
  ```typescript
  // mobile/src/screens/ReportPreviewScreen.tsx:36-39
  let data = await api.getReportMetadata(inspectionId);
  if (!data || !data.report_number) {
    data = await api.generateReport(inspectionId);
  }
  ```
  ```python
  # backend/main.py:1550-1552
  existing_report = db.query(Report).filter(Report.inspection_id == inspection_id).first()
  new_version = (existing_report.report_version + 1) if existing_report else 1
  ```
- **Expected Behavior**: Navigating to `ReportPreviewScreen` for an already-finalized inspection should retrieve the existing PDF metadata and binary without re-running generation.
- **Actual Behavior**: Every time the officer views the report preview screen, `api.generateReport()` is called, incrementing `report_version` (v1 → v2 → v3...) and overwriting the PDF file on disk.
- **Security/Data/Legal Impact**: Version inflation and unnecessary server CPU/disk cycles for PDF generation on simple reads.
- **Recommended Fix**: 
  1. In `ReportPreviewScreen.tsx`, check `if (!data || (!data.id && !data.report_version))`.
  2. In `backend/main.py:generate_inspection_report`, check if `inspection.status == "COMPLETED"` and `existing_report` exists; if so, return the existing report without incrementing version unless an explicit `force_regenerate=True` parameter is provided.
- **Production Data Affected**: No.
- **Migration Affected**: No.
- **Verification Test Required**: Navigate to `ReportPreviewScreen` 3 consecutive times and verify that `report_version` remains 1.

---

## 5. Medium Findings (4 Issues)

### [AUDIT-CONCUR-01] Sequential Inspection Numbering Uses Process-Level Lock
- **Severity**: **MEDIUM**
- **Component**: Backend / Concurrency & Numbering
- **File**: [`backend/main.py:153-162`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L153-L162)
- **Problem**: Sequential numbering (`LM-2026-XXXXX`) calculates `count = db.query(Inspection).count() + 1` protected by an in-memory `threading.Lock()`.
- **Impact**: In multi-process deployments (Gunicorn/Uvicorn with `--workers 4` or multiple Kubernetes pods), in-memory locks do not synchronize across processes, risking concurrent duplicate number collisions caught only by the DB UNIQUE constraint.
- **Fix**: Implement a PostgreSQL native sequence (`CREATE SEQUENCE inspection_number_seq`) or database-level row locking (`SELECT MAX(...) FOR UPDATE`).

### [AUDIT-STARTUP-01] Synchronous Schema DDL & Seeding at Module Import
- **Severity**: **MEDIUM**
- **Component**: Backend / Deployment Lifecycle
- **File**: [`backend/main.py:84-89`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py#L84-L89) & [`backend/seed.py:27-32`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/seed.py#L27-L32)
- **Problem**: `Base.metadata.create_all(bind=engine)` and `seed_database()` execute synchronously on Python module import. In `seed_database()`, if the development officer exists, it updates empty email and phone fields to hardcoded defaults.
- **Impact**: Server startup delays and unintended database mutations on application boot.
- **Fix**: Wrap seeding logic in `if settings.ENVIRONMENT != "production":` and decouple production schema migrations from application startup.

### [AUDIT-NET-01] Continuous 5-Second Heartbeat Polling Loop in Mobile Client
- **Severity**: **MEDIUM**
- **Component**: Mobile / Battery & Network Performance
- **File**: [`mobile/src/services/networkService.ts:98`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/services/networkService.ts#L98)
- **Problem**: `NetworkService` initiates a permanent 5-second `setInterval` pinging `GET /api/health`.
- **Impact**: Excess battery consumption and network overhead on mobile devices when idle.
- **Fix**: Switch to event-driven connectivity via `@react-native-community/netinfo`, reducing background polling interval to 60 seconds with exponential backoff on failure.

### [AUDIT-SEC-01] Cleartext Traffic Enabled Globally in AndroidManifest
- **Severity**: **MEDIUM**
- **Component**: Mobile / Android Security
- **File**: [`mobile/android/app/src/main/AndroidManifest.xml:19`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/android/app/src/main/AndroidManifest.xml#L19)
- **Problem**: `android:usesCleartextTraffic="true"` is set globally on the `<application>` tag.
- **Impact**: Allows unencrypted HTTP traffic across the mobile application.
- **Fix**: Set `usesCleartextTraffic="false"` for release builds and configure `network_security_config.xml` to restrict cleartext exclusively to local/emulator debug hostnames.

---

## 6. Low & Informational Findings (3 Issues)

### [AUDIT-SEC-02] Pre-Filled Demo Credentials in Mobile Login State
- **Severity**: **LOW**
- **Component**: Mobile / Authentication
- **File**: [`mobile/src/screens/LoginScreen.tsx:26-27`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/LoginScreen.tsx#L26-L27)
- **Problem**: `LoginScreen.tsx` initializes state with `DOCA-INSP-842` and `admin123`.
- **Fix**: Guard default credentials with `if (__DEV__)` so production release builds display empty input fields.

### [AUDIT-CFG-01] Hardcoded Local Area Network IP in Mobile Environment File
- **Severity**: **LOW**
- **Component**: Mobile / Environment Configuration
- **File**: [`mobile/.env:1`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/.env#L1)
- **Problem**: Contains developer LAN IP `EXPO_PUBLIC_API_URL=http://10.185.115.213:8000`.
- **Fix**: Document production domain configuration and ensure build scripts set `EXPO_PUBLIC_API_URL` to the production HTTPS domain during release compilation.

### [AUDIT-UI-01] Hardcoded Password Last Updated Placeholder String
- **Severity**: **LOW**
- **Component**: Mobile / Profile Screen UI
- **File**: [`mobile/src/screens/ProfileScreen.tsx:54`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/screens/ProfileScreen.tsx#L54)
- **Problem**: Displays static placeholder `"Updated 30 days ago"` because the `users` table lacks a `password_updated_at` column.
- **Fix**: Add `password_updated_at = Column(DateTime, default=datetime.utcnow)` to `User` model and populate dynamically.

---

## 7. Security Findings

| Check | Status | Verification Detail |
| :--- | :---: | :--- |
| **Authentication Enforcement** | **SECURE** | 34 of 34 functional endpoints require valid JWT bearer tokens; invalid tokens return 401 Unauthorized. |
| **Public Endpoints** | **SECURE** | Only `/api/health`, `/api/auth/login`, and `/` (HTML portal) are accessible without credentials. |
| **Password Hashing** | **SECURE** | Passwords hashed using standard Passlib bcrypt (`$2b$12$...`). Zero plaintext passwords stored. |
| **Credential Masking** | **SECURE** | Database URLs and connection strings safely masked across all diagnostic scripts and logs. |
| **Cleartext Traffic Policy** | **FLAGGED** | `usesCleartextTraffic="true"` in Android manifest should be restricted for production release. |

---

## 8. Data Integrity & Immutability Findings

| Lifecycle Stage | Status | Verification Detail |
| :--- | :---: | :--- |
| **Foreign Key Constraints** | **VERIFIED** | Enforced across all 12 PostgreSQL tables. 0 orphan foreign keys exist. |
| **Finalized Evidence Immutability** | **VERIFIED** | Post-finalization mutations (image upload, image delete, re-OCR, re-evaluation, finding adjudication) strictly blocked with HTTP 409 Conflict. |
| **Destructive Route Exposure** | **VERIFIED** | Entire API has ZERO report deletion, evidence deletion, or inspection deletion endpoints. |
| **Golden Source Preservation** | **VERIFIED** | SQLite source database [`legal_metrology.db`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/legal_metrology.db) is 100% untouched (348,160 bytes, 227 rows, `PRAGMA integrity_check` = `ok`). |

---

## 9. OCR & Extraction Provenance Findings

- **No Synthetic Text Fabrication**: Verified that `backend/ocr_service.py` returns `ocr_status="OCR_UNAVAILABLE"` and empty text when Tesseract is missing, never generating simulated or canned strings.
- **No Form-Field Substitution**: Verified that `backend/extraction_service.py` returns `extraction_status="NOT_FOUND"` and confidence `0.0` when declarations cannot be found in genuine OCR text boxes.
- **Bounding Box Integrity**: Bounding boxes are derived strictly from OpenCV/Tesseract image coordinates.

---

## 10. Legal Metrology Compliance Findings

- **Mandatory 7 PCR 2011 Declarations**: Fully mapped and evaluated (MRP, Net Quantity, Manufacturer, Date of Mfr/Pkg, Consumer Care, Commodity Name, Country of Origin).
- **Human-in-the-Loop Adjudication**: Report generation is blocked at the backend gate if any non-PASS finding has not been explicitly reviewed and adjudicated by an officer.
- **Statutory Disclaimers**: Verified that both the physical net quantity disclaimer and the official DoCA legal safety statement are embedded into every generated PDF report.

---

## 11. Offline Mode & Network Resilience Findings

- **Idempotent Draft Creation**: `client_draft_id` ensures that network timeouts and sync retries create exactly one inspection record (0 duplicate rows).
- **Atomic Sync Rollback**: `syncService.ts` guarantees that if any image upload fails during a sync attempt, the draft rolls back to `READY_FOR_SYNC` without triggering OCR or creating partial records.
- **Storage Limit Vulnerability**: Flagged under **AUDIT-MOB-01** (`expo-secure-store` 2KB ceiling).

---

## 12. Android & Native Module Findings

- **Gradle Build Graph**: Dry-run build succeeded in 2m 11s (`BUILD SUCCESSFUL`).
- **Native Image Quality Module**: Kotlin-based `ImageQualityModule.kt` is properly implemented and registered in `MainApplication.kt` with fast multi-threaded OpenCV-equivalent Laplacian blur computation.
- **Hardware Permissions**: Camera, location, and storage permissions are properly declared in `AndroidManifest.xml` and requested asynchronously at runtime.

---

## 13. UI / UX Findings

- **Safe-Area Insets**: `SafeAreaView` and dynamic bottom navigation padding (`BOTTOM_NAV_TAB_HEIGHT`) are consistently applied across all 13 screens.
- **Keyboard Handling**: `KeyboardAvoidingView` with `adjustResize` correctly prevents input field obstruction.
- **Loading & Empty States**: Comprehensive `ActivityIndicator` spinners and descriptive empty state placeholders implemented on all list screens.
- **Double Submit Prevention**: Ref-based in-flight guards (`submittingRef = useRef(false)`) protect against rapid double-tapping on "Continue" and "Submit".

---

## 14. Testing Suite Audit Findings

```
============================= test session starts =============================
Backend Regression Suite   : 271 passed, 1 skipped in 258.71s (0 failures, 0 errors)
PostgreSQL Integration     : 1 passed in 3.74s
Mobile TypeScript Check    : tsc --noEmit (0 errors)
Mobile Jest Unit Tests     : 4 suites passed, 19 tests passed in 0.93s
Frontend Web Bundle Export : App exported to dist/ (527 modules, 1.35 MB)
Android Build Dry-Run      : BUILD SUCCESSFUL in 2m 11s (10 actionable tasks)
================================================================================
```

---

## 15. Complete Issue Register

| Issue ID | Severity | Component | File | Short Description | Production Affected? |
| :---: | :---: | :--- | :--- | :--- | :---: |
| **AUDIT-MOB-01** | **HIGH** | Mobile Offline | `draftStorage.ts:237` | SecureStore 2KB size limit threatens offline drafts | No |
| **AUDIT-MOB-02** | **HIGH** | Mobile UI Gate | `ReviewAndSubmitScreen.tsx:58` | Property mismatch bypasses client-side adjudication check | No |
| **AUDIT-REP-01** | **HIGH** | Reports Engine | `ReportPreviewScreen.tsx:37` | Viewing report preview regenerates PDF & increments version | No |
| **AUDIT-CONCUR-01**| **MEDIUM**| Backend Core | `main.py:153` | Thread-level lock insufficient for multi-worker deployments | No |
| **AUDIT-STARTUP-01**| **MEDIUM**| Backend Boot | `main.py:84`, `seed.py:27` | Synchronous DDL & seed on module import | No |
| **AUDIT-NET-01** | **MEDIUM**| Mobile Network | `networkService.ts:98` | 5s polling interval causes unnecessary mobile battery drain | No |
| **AUDIT-SEC-01** | **MEDIUM**| Android Config | `AndroidManifest.xml:19` | Global `usesCleartextTraffic="true"` in release manifest | No |
| **AUDIT-SEC-02** | **LOW** | Mobile Auth | `LoginScreen.tsx:26` | Pre-filled demo credentials in default state | No |
| **AUDIT-CFG-01** | **LOW** | Mobile Config | `mobile/.env:1` | Hardcoded LAN developer IP in client config | No |
| **AUDIT-UI-01** | **LOW** | Mobile UI | `ProfileScreen.tsx:54` | Hardcoded password updated placeholder string | No |

---

## 16. Recommended Fix Order

1. **Phase 1 (Statutory & Reports Stability)**:
   - Fix `AUDIT-REP-01`: Update `ReportPreviewScreen.tsx` check and prevent unneeded version increments in `generate_inspection_report`.
   - Fix `AUDIT-MOB-02`: Align property names in `ReviewAndSubmitScreen.tsx` to `result_state` and `adjudication_status`.

2. **Phase 2 (Mobile Storage & Reliability)**:
   - Fix `AUDIT-MOB-01`: Replace `SecureStore` with `AsyncStorage` or file-based storage for offline drafts in `draftStorage.ts`.
   - Fix `AUDIT-NET-01`: Adjust polling frequency in `networkService.ts` to reduce battery drain.

3. **Phase 3 (Backend Concurrency & Startup)**:
   - Fix `AUDIT-CONCUR-01`: Implement PostgreSQL native sequence or row lock for inspection numbering.
   - Fix `AUDIT-STARTUP-01`: Guard startup DDL/seeding so it only runs outside production.

4. **Phase 4 (Hardening & Packaging)**:
   - Fix `AUDIT-SEC-01`: Restrict cleartext traffic in `AndroidManifest.xml` via network security config.
   - Fix `AUDIT-SEC-02` & `AUDIT-CFG-01`: Clean up pre-filled demo credentials and configure production API URL.
   - Fix `AUDIT-UI-01`: Add `password_updated_at` to user model.

---

## 17. Final Release Blockers

The following items are defined as release blockers before public general production rollout:
- [ ] Resolve **AUDIT-REP-01** (prevent report version inflation on preview).
- [ ] Resolve **AUDIT-MOB-02** (restore client-side adjudication warning dialog).
- [ ] Resolve **AUDIT-MOB-01** (safeguard multi-draft offline storage against SecureStore size ceiling).

---

## 18. Conclusion
The NiriKsha Legal Metrology inspection system is functionally robust, architecturally sound, and backed by a verified, pristine PostgreSQL database on Neon. The audit demonstrates that core statutory rules, OCR integrity, and evidence immutability are fully operative. Addressing the targeted findings above will bring the system to enterprise-grade production readiness.
