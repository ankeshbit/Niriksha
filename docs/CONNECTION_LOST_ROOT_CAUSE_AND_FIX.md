# NiriKsha — Connection Lost / "Failed to fetch" Post-Mortem & Remediation Report

**Document Version**: 1.0.0  
**Target Component**: Mobile App (React Native / Expo Web) & Network Diagnostics  
**Status**: Resolved & Fully Verified  

---

## 1. Executive Summary

During testing of the NiriKsha field inspection app in a desktop browser (Expo Web on `http://localhost:8081` connecting to the FastAPI backend on `http://localhost:8000`), the application frequently entered a stalled offline synchronization state:
- *"Inspection Saved Locally — Waiting for Connection"*
- *"Sync issue — draft preserved"*
- *"Connection Restored"* not progressing
- *"Uploading Images (0/0)"*
- Error logged: `TypeError: Failed to fetch`

The inspection was preserved as a local SQLite draft, but could not proceed online even when the FastAPI backend was online, healthy, and reachable.

### Core Investigation Finding
The failure was **not** caused by backend server downtime, database unavailability, or missing CORS headers. Instead, it was caused by a combination of five interrelated client-side defects in network reachability monitoring, timeout configuration, and indiscriminate error classification.

---

## 2. Root Cause Analysis

| # | Root Cause Category | Specific Vulnerability | File & Location | Impact |
|---|---|---|---|---|
| **RC-1** | **Health Check Timeout** | `checkReachability()` used an ultra-aggressive `2500ms` AbortController timeout. Any backend latency spike or cold-start flipped network status to `OFFLINE`. | `mobile/src/services/networkService.ts` | False `OFFLINE` state triggered during normal network operations. |
| **RC-2** | **Race Condition on Initial Check** | When `networkStatus === 'UNKNOWN'` and an initial reachability probe was in-flight (`isChecking === true`), `isServerReachable()` returned `false` instead of optimistic physical connectivity (`isPhysicalOnline()`). | `mobile/src/services/networkService.ts` | Early calls on app startup or screen navigation falsely assumed the server was unreachable. |
| **RC-3** | **Web Blob URI Expiry** | In `CaptureImagesScreen.tsx`, local image previews used `blob:http://localhost:8081/...` URIs. Re-fetching these blob URIs after navigation or component lifecycle events failed with browser-native `Failed to fetch`. | `mobile/src/screens/CaptureImagesScreen.tsx` | The catch handler misdiagnosed the local blob failure as an internet connectivity loss. |
| **RC-4** | **Brittle Error Matching** | `NewInspectionScreen.tsx` checked `err.message.includes('fetch')` to decide whether to save a draft offline. Any HTTP 401, 404, 422, JSON parsing error, or CORS abort matched and activated offline mode. | `mobile/src/screens/NewInspectionScreen.tsx` | API validation or client errors inappropriately forced inspections into offline draft mode. |
| **RC-5** | **PaddleOCR Timeout Starvation** | `api.runOCR()` executed PaddleOCR inference without an explicit timeout or with an inadequate window. Slow OCR processing on CPU/laptop took 60–120 seconds, causing browser-level fetch termination which was then treated as a server disconnection. | `mobile/src/services/api.ts` & `AnalyzingScreen.tsx` | Heavy AI inference triggered connection loss screens instead of showing progress. |

---

## 3. Implemented Fixes

### 3.1 RC-1 & RC-2: Robust Health Check & Optimistic Fallback (`networkService.ts`)
1. **Extended Timeout**: Increased probe timeout from `2500ms` to `8000ms` with jitter-free backoff.
2. **Timeout Distinction**: An `AbortError` during a reachability probe no longer flips status to `OFFLINE`. Only genuine socket/DNS failures (`NETWORK_UNREACHABLE`) change state.
3. **Optimistic Guard**: When state is `UNKNOWN` and a check is active, `isServerReachable()` now falls back to `isPhysicalOnline()` (which is `navigator.onLine` in web) rather than immediately reporting disconnected.

```typescript
// mobile/src/services/networkService.ts
public isServerReachable(): boolean {
  if (this.currentStatus === 'UNKNOWN' && this.isChecking) {
    return this.isPhysicalOnline(); // Optimistic while probe runs
  }
  return this.currentStatus === 'ONLINE';
}
```

### 3.2 RC-5: Structured Error Classification (`api.ts`)
Created a centralized `classifyFetchError()` and `isConnectivityError()` utility with explicit error typing:

```typescript
export type FetchErrorType =
  | 'NETWORK_UNREACHABLE' // Genuine connectivity failure
  | 'REQUEST_TIMEOUT'     // Request exceeded deadline
  | 'HTTP_ERROR'          // 4xx / 5xx response from server
  | 'AUTH_ERROR'          // 401 Unauthorized / 403 Forbidden
  | 'SERVER_ERROR'        // 500 Internal Server Error
  | 'BLOB_FETCH_ERROR'    // Browser-internal blob: URI failure
  | 'UNKNOWN_ERROR';
```

- Every `fetch()` call is wrapped with an `AbortController` using tiered timeouts:
  - Standard API requests: **30 seconds**
  - Image uploads: **60 seconds**
  - AI OCR processing (`api.runOCR`): **180 seconds**
- Distinguishes AbortController timeouts (`REQUEST_TIMEOUT`) from actual network drops (`NETWORK_UNREACHABLE`).

### 3.3 RC-3: Isolated Blob URI Handling (`CaptureImagesScreen.tsx`)
Separated local browser blob resolution from network API calls:
- Wrapped `fetch(imageUri)` in a dedicated try/catch block.
- If a blob URI expires or fails, it is categorized as `BLOB_FETCH_ERROR` with a descriptive message prompting the user to re-select the image, rather than falsely declaring the backend offline.

### 3.4 RC-4: Structured Error Handling in Creation Flow (`NewInspectionScreen.tsx`)
Replaced string-matching error inspection with structured classification:

```typescript
// BEFORE:
const isNetworkError = err.message.includes('fetch') || err.message.includes('Network');

// AFTER:
const classified = classifyFetchError(err, url);
const isNetworkIssue = isConnectivityError(classified);
if (isNetworkIssue) {
  // Preserve draft safely and enter offline sync flow
} else {
  // Present actionable error message to user (e.g. 401 Session Expired, 422 Invalid Input)
}
```

### 3.5 RC-5b: AI Analysis Feedback (`AnalyzingScreen.tsx`)
Updated `AnalyzingScreen.tsx` to handle `REQUEST_TIMEOUT` and `NETWORK_UNREACHABLE` distinctly:
- `REQUEST_TIMEOUT` displays: *"Analysis Taking Longer Than Expected — Large images or heavy server load. Retrying..."*
- Genuine network failures display: *"Connection Lost During Analysis — Progress saved locally."*

---

## 4. Safety & Invariant Guarantees

1. **Zero Draft Loss**: Offline drafts continue to be written to local SQLite (`draft-${uuid}`) before any remote sync attempt. If genuine connectivity is lost, the draft remains intact.
2. **Sync Idempotency**: All inspection creation requests pass `client_draft_id`. If a retried sync reaches the backend, `_fetch_existing_draft` returns the existing inspection record rather than creating a duplicate.
3. **Zero Production Mutation**: All automated tests and diagnostic scripts run against the isolated SQLite test database (`test_legal_metrology.db`). Neon production remains untouched.
4. **CORS Integrity**: Cross-origin requests from `http://localhost:8081` are cleanly permitted by the FastAPI CORS middleware without relying on insecure blanket wildcards in production.

---

## 5. Verification & Test Evidence

### 5.1 Pytest Suite (`tests/test_connection_fix.py` + Related Regressions)
Ran comprehensive automated regression tests validating health responsiveness, CORS, idempotency, multipart uploads, and auth status codes:

```
tests/test_connection_fix.py::test_health_responds_quickly PASSED
tests/test_connection_fix.py::test_cors_from_expo_web_origin PASSED
tests/test_connection_fix.py::test_create_inspection_with_client_draft_id PASSED
tests/test_connection_fix.py::test_sync_idempotency_no_duplicate_inspection PASSED
tests/test_connection_fix.py::test_image_upload_multipart PASSED
tests/test_connection_fix.py::test_unauthenticated_request_returns_401_not_network_error PASSED
tests/test_connection_fix.py::test_nonexistent_inspection_returns_404_not_network_error PASSED
tests/test_connection_fix.py::test_health_endpoint_stable_under_sequential_calls PASSED
tests/test_offline_and_idempotency.py (4 tests) PASSED
tests/test_rbac_authorization.py (9 tests) PASSED

Result: 21 passed in 4.11s (0 failures, 0 errors)
```

### 5.2 TypeScript Verification
```bash
$ npm run ts:check
> niriksha@1.0.0 ts:check
> tsc --noEmit
Exit code: 0 (0 type errors across all mobile components)
```

### 5.3 Mobile Unit Tests
```bash
$ npm test
Test Suites: 5 passed, 5 total
Tests:       32 passed, 32 total
Snapshots:   0 total
Time:        1.924 s
```

---

## 6. Conclusion

The persistent "Failed to fetch" issue has been resolved at the root cause level. The application now correctly differentiates between genuine network loss, client-side blob handling, HTTP-level application errors, and long-running AI inference, preventing false transitions into offline-sync lock.
