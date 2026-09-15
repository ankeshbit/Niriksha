# NiriKsha — LLM 10-Minute Technical Quickstart

**Target Audience:** AI Coding & Reasoning Models (Claude, GPT, Gemini) tasked with modifying, debugging, or analyzing NiriKsha.  
**System Identity:** AI-Assisted Legal Metrology Packaged-Commodity Inspection System (SIH 2026 Problem Statement 26034).  
**Core Motto:** *“AI assists, deterministic rules evaluate, photographic evidence supports, the Inspecting Officer decides.”*  

---

## 1. Core Mental Model in 60 Seconds

NiriKsha is an automated compliance surveillance tool for Legal Metrology Inspectors enforcing the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)**.

1. **Central Entity:** An `Inspection` (e.g. `LM-2026-00042`) moves through a strict state machine:  
   `DRAFT` ➔ `IMAGES_UPLOADED` ➔ `ANALYZING` ➔ `ANALYSIS_COMPLETE` ➔ `NEEDS_REVIEW` ➔ `COMPLETED`
2. **Optical Layer:** Package photographs (front, back, side) are evaluated for blur via `BlurDetection2`, then processed via a `PaddleOCR 3.x` CPU singleton (with Tesseract fallback) and `PP-Structure` layout analyzer.
3. **Extraction:** A deterministic spatial regex engine extracts 8 statutory declarations (`commodity_name`, `manufacturer_details`, `net_quantity`, `mrp`, `date_of_manufacture_packing`, `consumer_care_details`, `country_of_origin`, `unit_sale_price`). Cross-image verification aggregates declarations and flags conflicts.
4. **Analytical Metrology:** Declarations are audited across 3 dimensions:
   - **Placement:** PDP (front panel) vs. Information Panel (Rules 6, 7 & 12).
   - **Readability:** Local crop Laplacian variance, contrast, and classical ML (`readability_model.joblib`).
   - **Font Size:** Numeral height against Rule 9 Table 1 thresholds + classical ML (`font_size_model.joblib`). **Crucial:** Uncalibrated images strictly return `FONT_SIZE_UNDETERMINABLE` — never fabricated millimetres.
5. **Rule Engine:** The `DeterministicRuleEngine` evaluates effective declarations against 12 version-pinned PCR 2011 rules. AI is strictly excluded from legal adjudication.
6. **Adjudication:** The Inspecting Officer reviews findings (`CONFIRMED`, `DISMISSED`, `CORRECTED`, `NOT_APPLICABLE`). The finalization gate blocks report generation until zero findings remain pending.
7. **Statutory Report:** A formal multi-page ReportLab PDF is generated, cryptographically sealed with a SHA-256 hash, and mirrored as an editable DOCX.

---

## 2. The 7 Files to Read First

| # | File Path | Why Read First |
|---|---|---|
| 1 | [`backend/models.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/models.py) | Complete relational database schema, all 15 SQLAlchemy tables, foreign keys, lifecycle states, and relationships. |
| 2 | [`backend/rule_engine/engine.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/rule_engine/engine.py) | Deterministic statutory rule evaluator, evidence generation, and the anti-fabrication safety rule. |
| 3 | [`backend/rule_engine/registry.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/rule_engine/registry.py) | Pinned statutory PCR 2011 rules, exact legal citations, PDF page references, and severity levels. |
| 4 | [`backend/ocr_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/ocr_service.py) | PaddleOCR 3.x singleton, JIT warmup amortization, Tesseract fallback, coordinate mapping, and box deduplication. |
| 5 | [`backend/extraction_service.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/extraction_service.py) | PP-Structure layout integration, regex extraction for 8 fields, and multi-image conflict resolution. |
| 6 | [`backend/main.py`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/backend/main.py) | FastAPI endpoints, RBAC dependencies, finalization gate, atomic number generator, and supervisor deletion handlers. |
| 7 | [`mobile/src/services/syncService.ts`](file:///c:/Users/ankes/OneDrive/Desktop/SIH/mobile/src/services/syncService.ts) | Offline draft synchronization engine, idempotent inspection creation, and image upload pipeline. |

---

## 3. Critical Invariants (DO NOT BREAK)

1. **PostgreSQL / Neon is the Sole Database Backend:**  
   SQLite is strictly forbidden in production, development, and test runs. `backend/config.py` and `backend/database.py` reject SQLite schemes immediately.
2. **Never Allow Test Database == Production Database:**  
   `conftest.py` and `verify_test_database_safety()` actively abort if `TEST_DATABASE_URL` resolves to the same host and database identity as `DATABASE_URL`.
3. **No Synthetic Text Fabrication:**  
   OCR and morphological engines must NEVER manufacture character text if pixels do not contain readable text. If OCR is unreadable or fails, it returns `OCR_UNAVAILABLE` or empty string.
4. **The Safety Rule: Non-Detection is NOT an Automatic Violation:**  
   Blurred images, OCR non-detections, low confidence, and uncalibrated font measurements route strictly to `INSUFFICIENT_EVIDENCE`, `NEEDS_MANUAL_VERIFICATION`, or `FONT_SIZE_UNDETERMINABLE`. The system must NEVER convert AI uncertainty into a statutory violation.
5. **Inspector is the Sole Legal Adjudicator:**  
   Automated rule engine outputs are *preliminary findings*. A finding only becomes a statutory non-compliance if an Inspecting Officer explicitly marks it `CONFIRMED`.
6. **Strict Finalization Gate:**  
   `POST /api/inspections/{id}/finalize` must fail with HTTP 400 Bad Request if any finding remains with `adjudication_status == 'PENDING'`.
7. **Official Evidence Immutability:**  
   Once an inspection is `COMPLETED` or a report is generated, its package images and declarations cannot be deleted or mutated by inspectors (`HTTP 409 Conflict`). Only a Supervisor with explicit written reason can delete a report or inspection.
8. **Atomic Concurrency Numbering:**  
   Inspection numbers (`LM-{YYYY}-{00001}`) are generated atomically via row-level locks on `inspection_number_counters` (`RETURNING next_number - 1`). Never replace this with Python threading locks or `COUNT(*) + 1`.
9. **One Draft = One Inspection (Idempotency):**  
   Field offline drafts carry a `client_draft_id` (`draft-UUID`). Calling `POST /api/inspections` multiple times with the same draft ID returns the existing inspection and never creates duplicates.

---

## 4. Common Pitfalls & Mistakes to Avoid

- ❌ **Do NOT assume SQLite is available for quick tests.** You must have a real Neon PostgreSQL URL configured in `TEST_DATABASE_URL`.
- ❌ **Do NOT run concurrent PaddleOCR inferences on CPU.** PaddleOCR uses a singleton with shared BLAS thread pools. Benchmarks proved concurrent threads corrupt character buffers and slow down CPU execution by 15%. Keep `OCR_CONCURRENT_IMAGES = 1`.
- ❌ **Do NOT fabricate font heights in mm.** If an image lacks physical scale markers (e.g. known package dimensions or barcode calibration), return `FONT_SIZE_UNDETERMINABLE`.
- ❌ **Do NOT re-evaluate rules using raw OCR values if corrected values exist.** Always use `declaration.effective_value` (`corrected_value` if present, else `extracted_value`).
- ❌ **Do NOT bypass the finalization gate in test scripts.** Test scripts verifying report generation must adjudicate all pending findings first.
- ❌ **Do NOT store draft images as base64 in AsyncStorage.** Android SecureStore has a 2KB hardware limit, and AsyncStorage will exhaust memory. Images are stored as file URIs.

---

## 5. Commands to Run Before & After Modifying Code

### Verify Environment & Test Suite (Python Backend)
```bash
# 1. Check Python test collection (must collect 522 tests)
venv\Scripts\pytest.exe --collect-only -q

# 2. Run targeted regression test suite
venv\Scripts\pytest.exe tests/test_database_safety.py tests/test_final_corrections.py -v

# 3. Run full backend regression suite (requires active Neon TEST_DATABASE_URL)
venv\Scripts\pytest.exe -v
```

### Verify Mobile App (React Native / TypeScript)
```bash
# 1. Type check mobile codebase
cd mobile
npm run ts:check

# 2. Run mobile Jest test suite (13 suites, 138 tests)
npm test
```
