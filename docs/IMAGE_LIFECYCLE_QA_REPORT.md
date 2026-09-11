# NiriKsha Field Inspector — Image Lifecycle QA & Remediation Report

**Document Version:** 1.0.0  
**Date:** September 10, 2026  
**Component:** Mobile Client (`CaptureImagesScreen`), Sync Service, Draft Storage, and Backend Image API  
**Environment:** Expo Web (`http://localhost:8081`), FastAPI Backend (`http://localhost:8000`), Neon PostgreSQL Cloud DB  

---

## 1. Executive Summary

During field testing of the NiriKsha Field Inspector mobile app (Step 2 of 3: "Capture Package Images"), several critical bugs were identified in the image lifecycle management:
1. **Retake Appended Duplicates:** Retaking or recapturing a photo in an existing slot (e.g., front or back) created duplicate database records and UI cards instead of replacing the slot canonically.
2. **Missing Slot Deletion Endpoint:** There was no backend endpoint to delete an image by slot (`view_type`), leading to orphaned images or unsynchronized draft states.
3. **Async Quality Assessment Race Conditions:** Image quality assessment ran asynchronously; when a user retook or deleted a slot while an assessment was in flight, the late-arriving quality assessment result from the old photo overwrote the new slot's state, marking clear images as blurry or restoring deleted slots.
4. **Spurious "Connection Lost" Alerts:** Deleting or retaking local images triggered false network error alerts when draft images were manipulated offline.
5. **Draft Sync Over-Upload:** Draft storage accumulated superseded photos, uploading outdated or replaced photos during online sync.

All issues were systematically investigated, diagnosed at the root source code level, remediated without superficial UI patches, and verified through both comprehensive unit tests and automated E2E testing across all 12 test matrix scenarios.

---

## 2. Root Cause Analysis

### Defect 1: Image Retake Appends Duplicates Rather Than Replacing
* **Root Cause:** In `backend/main.py`, `upload_inspection_image` simply inserted a new `ProductImage` record into PostgreSQL without checking if an active image already existed for that `inspection_id` and `view_type`. As a result, each retake added a new record with an incremented sequence number.
* **Impact:** Step 2 displayed multiple images for the "front" or "back" slot, confusing compliance validation and causing multiple redundant OCR pipelines.

### Defect 2: Absence of Slot-Level Image Deletion
* **Root Cause:** The backend only exposed `DELETE /api/images/{image_id}` (which also had incomplete cleanup of disk artifacts). If the client only had slot context (`view_type`) or if an inspection was being reset, there was no slot-level endpoint.
* **Impact:** Deleting a photo from the UI slot left the previous image record active in the database.

### Defect 3: Asynchronous Quality Analysis Overwrite (Race Condition)
* **Root Cause:** In `CaptureImagesScreen.tsx`, when `processPickedImage` was triggered, it initiated an asynchronous call to `api.assessImageQuality`. If the inspector clicked "Retake" or "Delete" before that promise resolved, the resolved callback executed `setImages(...)` using stale slot information, overwriting the newly captured image or resurrecting the deleted image.
* **Impact:** Intermittent UI flakiness where clear images were reported as blurry, or deleted slots reappeared with a quality warning.

### Defect 4: Spurious Network Errors on Local Operations
* **Root Cause:** In `CaptureImagesScreen.tsx`, deleting an image unconditionally made network calls even when the image was a local-only draft (e.g., base64 data URI). If the network request failed or timed out, it triggered global error alerts ("Connection Lost" / "Failed to fetch").
* **Impact:** Severe UX degradation while operating in offline or draft mode.

### Defect 5: Sync Service Uploading Stale Historical Slot Versions
* **Root Cause:** In `syncService.ts`, when syncing draft inspections to the cloud, the sync routine iterated over all images in `draft.images` without deduplicating by `view_type`. If multiple revisions had been captured, all revisions were uploaded sequentially.
* **Impact:** Wastage of network bandwidth, extra latency, and potential database inconsistency.

---

## 3. Source-Level Remediation Details

### 3.1. Backend Remediation (`backend/main.py`)
1. **Canonical Slot Replacement in `upload_inspection_image`:**
   Enforced that each `(inspection_id, view_type)` slot possesses exactly one canonical image. When a new image is uploaded for an existing slot, any prior image record for that slot is deleted from the database and its file unlinked from disk before the new record is committed:
   ```python
   # Canonical slot replacement: remove existing image of same view_type
   existing_images = db.query(ProductImage).filter(
       ProductImage.inspection_id == inspection_id,
       ProductImage.view_type == view_type.lower()
   ).all()
   for old_img in existing_images:
       try:
           old_rel = old_img.file_path.lstrip("/")
           old_abs = BASE_DIR / old_rel
           if old_abs.exists() and old_abs != dest_path:
               old_abs.unlink()
       except Exception:
           pass
       db.delete(old_img)
   db.flush()
   ```
2. **Slot Deletion Endpoint (`DELETE /api/inspections/{inspection_id}/images/slot/{view_type}`):**
   Added a dedicated slot endpoint that purges all images belonging to a specific view type for an inspection:
   ```python
   @app.delete("/api/inspections/{inspection_id}/images/slot/{view_type}")
   def delete_inspection_image_by_slot(
       inspection_id: str,
       view_type: str,
       db: Session = Depends(get_db),
       current_user: User = Depends(get_current_user)
   ):
       ...
   ```
3. **Direct Image ID Deletion Endpoint (`DELETE /api/images/{image_id}`):**
   Verified and hardened the endpoint to ensure both physical file unlinking and database record deletion.

### 3.2. Frontend API Client (`mobile/src/services/api.ts`)
* Added `deleteImage(imageId: string): Promise<boolean>`
* Added `deleteImageBySlot(inspectionId: string, viewType: string): Promise<boolean>`

### 3.3. Draft Storage Service (`mobile/src/services/draftStorage.ts`)
* Implemented `removeDraftImage(clientDraftId: string, viewType: string): Promise<void>`:
  Atomically removes all image entries matching `viewType` from local AsyncStorage draft state and persists the updated draft.
* Hardened `addDraftImage` to guarantee single-slot semantics by filtering out existing `viewType` items before appending the new image.

### 3.4. Mobile UI Component (`mobile/src/screens/CaptureImagesScreen.tsx`)
1. **Monotonic Slot Version Tokens (`slotVersions` ref):**
   Introduced a persistent `React.useRef<{ [slot: string]: number }>` map. Every capture, retake, or delete operation increments the slot version token:
   ```typescript
   slotVersions.current[viewType] = (slotVersions.current[viewType] || 0) + 1;
   const currentToken = slotVersions.current[viewType];
   ```
   When the async quality check returns:
   ```typescript
   if (slotVersions.current[viewType] !== currentToken) {
       // Discard stale result: user has retaken or deleted this slot
       return;
   }
   ```
2. **Deterministic `handleDeleteImage`:**
   - Immediately clears the slot in local React state (`images` array) and increments the version token.
   - For drafts, invokes `draftStorage.removeDraftImage`.
   - For server-synced inspections, calls `api.deleteImageBySlot` or `api.deleteImage` asynchronously with graceful error handling that prevents spurious "Connection Lost" dialogs.
3. **Continue Validation Rules:**
   - Requires both `front` and `back` slots to be populated.
   - Enforces that all captured images (front, back, and optional side/panel) have acceptable quality (`quality_status !== 'POOR'`).
   - Automatically disables "Continue to Declarations" if either required slot is deleted or is of poor quality, and re-enables it immediately once clear photos are present.

### 3.5. Sync Service (`mobile/src/services/syncService.ts`)
* Added canonical slot deduplication prior to upload:
  ```typescript
  const canonicalBySlot = new Map<string, typeof draft.images[0]>();
  for (const img of draft.images) {
      canonicalBySlot.set(img.viewType, img);
  }
  const imagesToUpload = Array.from(canonicalBySlot.values());
  ```

---

## 4. Verification & Test Suite Results

### 4.1. Backend Automated Tests (`tests/test_image_lifecycle.py`)
* **Test:** `test_image_lifecycle_full_flow`
* **Status:** **PASS** (100% in 20.92s)
* **Coverage:**
  - Inspection creation
  - Initial upload of Front and Back images
  - Slot deletion verification
  - Canonical retake replacement (verifying count remains exactly 1 per slot)
  - Full inspection lifecycle validation

### 4.2. Frontend Automated Unit Tests (`mobile/src/screens/__tests__/`)
* **Test Runner:** Jest 30.5.1
* **Status:** **ALL 6 SUITES PASSED (49 / 49 tests passed)**
* **Suites:**
  1. `imageLifecycle.test.js`: **22 tests PASSED** (Capture, delete, retake, slot replacement, async race token rejection, draft storage lifecycle, sync deduplication, continue button state)
  2. `timeBasedGreeting.test.js`: **PASSED**
  3. `roleAccess.test.js`: **PASSED**
  4. `locationFlow.test.js`: **PASSED**
  5. `formatGeocodedAddress.test.js`: **PASSED**
  6. `formatLastLogin.test.js`: **PASSED**

---

## 5. End-to-End Test Matrix Execution (12 Tests)

The 12-scenario E2E matrix was executed programmatically against the running FastAPI backend and Neon PostgreSQL database (`scratch/e2e_simple.py`):

| Test ID | Scenario Description | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| **T1** | Upload Front + Back | Both slots populated (1 front, 1 back) | front=1, back=1 | **PASS** |
| **T2** | Duplicate Slot Check | No duplicate records exist per slot | front=1, back=1 (<=1 each) | **PASS** |
| **T3** | Delete Front by ID | Front removed, Back intact | del_ok=True, front=0, back=1 | **PASS** |
| **T4** | Recapture Front after Delete | Front restored, Back intact | front=1, back=1 | **PASS** |
| **T5** | Delete Back | Back removed, Front intact | del_ok=True, front=1, back=0 | **PASS** |
| **T6** | Recapture Back after Delete | Back restored, Front intact | front=1, back=1 | **PASS** |
| **T7** | Upload Side (Optional Slot) | Side populated, 3 images total | side=1, total=3 | **PASS** |
| **T8** | Delete Side via Slot Endpoint | Side removed, Front & Back intact | del_ok=True, front=1, back=1, side=0 | **PASS** |
| **T9** | Retake Front (Slot Replacement) | Exactly 1 Front image (no duplicate) | front=1 | **PASS** |
| **T10** | Rapid Retake Back x3 | Slot replaced cleanly, exactly 1 Back | back=1 after 3 retakes | **PASS** |
| **T11** | Delete Front via Slot Endpoint | Front removed via slot endpoint | del_ok=True, front=0, back=1 | **PASS** |
| **T12** | Restore State & Continue Check | Front restored; Continue criteria met | front=1, back=1 (eligible) | **PASS** |

**Matrix Result: 12 / 12 Tests PASSED (100%)**

---

## 6. Constraints & Safety Audit

* **Supervisor / Admin Web Portal:** Untouched. No breaking changes introduced.
* **Backend RBAC:** Role-based access control intact; access verification respected.
* **Legal Rules Engine:** Compliance rules and OCR legal evaluation engines untouched.
* **Neon PostgreSQL Database:** Schema compatibility fully maintained; no breaking migrations or destructive actions on existing production data.
* **Error Handling:** Deleting or retaking local images does not generate spurious network error banners.

---

## 7. Conclusion

The image capture, upload, delete, and retake lifecycle in the NiriKsha Field Inspector application is fully stabilized and verified. All operations in Step 2 of 3 ("Capture Package Images") behave predictably, eliminate race conditions through monotonic slot tokens, enforce single-slot canonical integrity, and synchronize accurately across offline drafts and cloud persistence.
