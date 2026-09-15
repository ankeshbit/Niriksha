# NiriKsha — Database Master Reference

**Target Database Engine:** PostgreSQL 15+ (Hosted on Neon Serverless Cloud, AWS us-east-2)  
**ORM:** SQLAlchemy 2.0.52 (Declarative Base)  
**DBAPI Driver:** `psycopg` (v3.3.5 / `postgresql+psycopg://`)  
**Strict Architectural Rule:** SQLite is 100% prohibited at runtime, in development, and in testing.  

---

## 1. Relational Entity-Relationship (ER) Overview

```
+---------------------------------------------------------------------------------------------------------+
|                                              users                                                      |
| PK id VARCHAR(36)                                                                                       |
|    officer_id VARCHAR(50) UNIQUE                                                                        |
|    full_name, email, phone, designation, zone, password_hash, role, created_at, last_login_at               |
+---------------------------------------------------------------------------------------------------------+
       │ 1                                                │ 1
       │                                                  │
       │ N (assigned)                                     │ N (adjudicated)
       ▼                                                  ▼
+------------------------------------+       +------------------------------------+
|            inspections             |       |         inspector_reviews          |
| PK id VARCHAR(36)                  |       | PK id VARCHAR(36)                  |
|    inspection_number VARCHAR(50)   |       | FK check_id -> compliance_checks.id|
| FK inspector_id -> users.id        |       | FK officer_id -> users.id          |
|    location, status, overall_status|       |    action, remarks, reviewed_at    |
|    inspection_type, client_draft_id|       +------------------------------------+
|    created_at, finalized_at        |                        ▲
+------------------------------------+                        │ 1
       │ 1                   │ 1                              │ N
       ├─────────────────┐   ├──────────────────────────┐     │
       ▼ 1               ▼ N │                          ▼ N   │
+--------------+  +---------------+              +------------------------------------+
|   products   |  |product_images |              |         compliance_checks          |
| PK id        |  | PK id         |              | PK id VARCHAR(36)                  |
| FK inspect_id|  | FK inspect_id |              | FK inspection_id -> inspections.id |
| product_name |  | file_path     |              | FK rule_version_id -> rule_versions|
| brand_name   |  | view_type     |              |    rule_code, title, severity      |
| category     |  | blur_score    |              |    result_state, extracted_value   |
| batch_number |  | glare_score   |              |    explanation, adjudication_status|
+--------------+  | quality_score |              |    adjudication_notes,adjudicated_by|
                  | quality_status|              +------------------------------------+
                  +---------------+                        ▲ 1             │ 1
                         │ 1                               │               │
       ┌─────────────────┼─────────────────┐               │ N             │ N
       ▼ N               ▼ N               ▼ N             │               ▼
+--------------+  +---------------+  +---------------+     │         +----------------+
| ocr_results  |  | declarations  |  |   evidence    |     │         |    evidence    |
| PK id        |  | PK id         |  | PK id         |     │         | PK id          |
| FK image_id  |  | FK inspect_id |  | FK check_id   |─────┘         | FK check_id    |
| raw_text     |  | FK image_id   |  | FK image_id   |───────────────┤ FK image_id    |
| confidence   |  | field_name    |  | bounding_box  |               | bounding_box   |
| bounding_box |  | extracted_val |  | crop_image_path               | crop_image_path|
| created_at   |  | corrected_val |  | highlight_text                | highlight_text |
+--------------+  | placement_stat|  | reason        |               | reason         |
                  | font_size_stat|  +---------------+               +----------------+
                  | readability_st|
                  | valid_matrix  |
                  +---------------+

+------------------------------------+       +------------------------------------+
|              reports               |       |             audit_logs             |
| PK id VARCHAR(36)                  |       | PK id VARCHAR(36)                  |
| FK inspection_id -> inspections.id |       | FK inspection_id (ON DELETE NULL)  |
|    report_version INT              |       |    actor_id VARCHAR(100)           |
|    pdf_path VARCHAR(500)           |       |    action VARCHAR(100)             |
|    docx_path VARCHAR(500)          |       |    entity_type, entity_id          |
|    pdf_hash VARCHAR(64) (SHA-256)  |       |    old_value, new_value, details   |
|    legal_safety_statement TEXT     |       |    created_at TIMESTAMP            |
|    generated_at TIMESTAMP          |       +------------------------------------+
+------------------------------------+

+------------------------------------+       +------------------------------------+
|          product_listings          |       |        listing_comparisons         |
| PK id VARCHAR(36)                  |       | PK id VARCHAR(36)                  |
| FK inspection_id -> inspections.id |       | FK inspection_id -> inspections.id |
|    product_name, brand_name, mrp   |       | FK listing_id -> product_listings  |
|    net_quantity, manufacturer      |       | FK source_image_id -> product_image|
|    country_of_origin, consumer_care|       |    field_name, listing_value       |
|    listing_url, source             |       |    package_value, comparison_status|
+------------------------------------+       |    inspector_status, adjudicated_by|
                                             +------------------------------------+

+------------------------------------+       +------------------------------------+
|           rule_versions            |       |     inspection_number_counters     |
| PK id VARCHAR(36)                  |       | PK year INT (e.g. 2026)            |
|    rule_code VARCHAR(50)           |       |    next_number INT (atomic sequence|
|    version_number INT              |       +------------------------------------+
|    title, category, statutory_ref  |
|    rule_logic_description, severity|
|    is_active, created_at           |
+------------------------------------+
```

---

## 2. Complete Database Table Inventory

### 2.1 Table: `users`
**Purpose:** User credentials, officer directory, contact info, login tracking, and role assignment.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Unique user UUID |
| `officer_id` | VARCHAR(50) | No | None | UNIQUE, INDEX | Official badge/login ID (e.g. `DOCA-INSP-842`) |
| `full_name` | VARCHAR(100) | No | None | | Officer full name |
| `email` | VARCHAR(100) | Yes | None | | Official e-mail address |
| `phone` | VARCHAR(30) | Yes | None | | Official contact phone |
| `designation` | VARCHAR(100) | No | None | | Official title / rank |
| `zone` | VARCHAR(100) | No | None | | Enforcement jurisdiction / zone |
| `password_hash` | VARCHAR(255) | No | None | | Bcrypt password hash |
| `role` | VARCHAR(20) | No | `'INSPECTOR'` | | RBAC role: `INSPECTOR`, `SUPERVISOR`, `ADMIN` |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | User creation timestamp |
| `last_login_at` | TIMESTAMP | Yes | None | | Timestamp of current active session |
| `previous_login_at`| TIMESTAMP | Yes | None | | Timestamp of prior login (for UI greeting) |
| `password_updated_at`| TIMESTAMP | Yes | `utcnow()` | | Timestamp of last password change |

**Relationships:**
- `inspections` -> `relationship("Inspection", back_populates="inspector")`
- `reviews` -> `relationship("InspectorReview", back_populates="officer")`

---

### 2.2 Table: `inspections`
**Purpose:** Master inspection entity representing a physical or digital compliance audit of a packaged commodity.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Unique inspection UUID |
| `inspection_number` | VARCHAR(50) | No | None | UNIQUE, INDEX | Formatted sequence number: `LM-{YYYY}-{00001}` |
| `inspector_id` | VARCHAR(36) | No | None | FK -> `users.id` | Assignee / creator inspecting officer |
| `location` | VARCHAR(255) | No | None | INDEX | Inspection address, GPS string, or premises name |
| `status` | VARCHAR(30) | No | `'DRAFT'` | INDEX | Lifecycle state: `DRAFT`, `IMAGES_UPLOADED`, `ANALYZING`, `ANALYSIS_COMPLETE`, `NEEDS_REVIEW`, `COMPLETED` |
| `overall_status` | VARCHAR(50) | Yes | None | INDEX | Final legal outcome: `NO_POTENTIAL_VIOLATIONS`, `POTENTIAL_NON_COMPLIANCE`, `NEEDS_MANUAL_VERIFICATION`, `INSUFFICIENT_EVIDENCE` |
| `inspection_type` | VARCHAR(50) | No | `'PHYSICAL'` | | Inspection mode: `PHYSICAL`, `ONLINE_LISTING`, `HYBRID` |
| `notes` | TEXT | Yes | None | | Field officer remarks and context notes |
| `client_draft_id` | VARCHAR(100) | Yes | None | INDEX | Client-generated offline UUID for idempotency |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | INDEX | Creation timestamp |
| `finalized_at` | TIMESTAMP | Yes | None | | Timestamp when finalization gate completed |

**Cascade Deletion Behavior:**
- `product`: `cascade="all, delete-orphan"` (uselist=False)
- `images`: `cascade="all, delete-orphan"`
- `declarations`: `cascade="all, delete-orphan"`
- `compliance_checks`: `cascade="all, delete-orphan"`
- `report`: `cascade="all, delete-orphan"` (uselist=False)
- `listing`: `cascade="all, delete-orphan"` (uselist=False)
- `listing_comparisons`: `cascade="all, delete-orphan"`

---

### 2.3 Table: `products`
**Purpose:** Identity and classification of the commodity under inspection.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Product record UUID |
| `inspection_id` | VARCHAR(36) | No | None | UNIQUE, FK -> `inspections.id` | 1-to-1 link to parent inspection |
| `product_name` | VARCHAR(255) | No | None | INDEX | Declared product / trade name |
| `brand_name` | VARCHAR(255) | Yes | None | INDEX | Brand owner / brand name |
| `category` | VARCHAR(100) | No | None | | Category: `'Packaged Food'`, `'Personal Care / Household'` |
| `batch_number` | VARCHAR(100) | Yes | None | | Batch / lot identifier |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |

---

### 2.4 Table: `product_images`
**Purpose:** Photographic evidence of packaging panels with quality metrology scores.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Image record UUID |
| `inspection_id` | VARCHAR(36) | No | None | FK -> `inspections.id` | Parent inspection |
| `original_filename`| VARCHAR(255) | Yes | None | | Original filename as uploaded |
| `file_path` | VARCHAR(500) | No | None | | Relative path on server filesystem (`uploads/...`) |
| `mime_type` | VARCHAR(100) | Yes | `'image/jpeg'` | | MIME type (`image/jpeg`, `image/png`) |
| `file_size` | INTEGER | Yes | 0 | | File size in bytes |
| `width` | INTEGER | Yes | 0 | | Pixel width |
| `height` | INTEGER | Yes | 0 | | Pixel height |
| `sequence_order` | INTEGER | Yes | 1 | | Sequence index |
| `view_type` | VARCHAR(50) | No | None | | Panel slot: `'front'`, `'back'`, `'side'`, `'panel'`, `'other'` |
| `blur_score` | FLOAT | Yes | 0.0 | | Laplacian variance blur metric |
| `glare_score` | FLOAT | Yes | 0.0 | | Glare / specular reflection score |
| `quality_score` | FLOAT | Yes | 1.0 | | Composite quality score (0.0 - 1.0) |
| `quality_status`| VARCHAR(50) | Yes | `'GOOD'` | | Quality outcome: `'GOOD'`, `'WARNING'`, `'POOR'` |
| `quality_metadata_json`| TEXT | Yes | None | | Serialized JSON containing resolution, barcodes, etc. |
| `processing_status`| VARCHAR(50) | Yes | `'UPLOADED'` | | Processing stage: `'UPLOADED'`, `'QUALITY_CHECKED'` |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Upload timestamp |

---

### 2.5 Table: `ocr_results`
**Purpose:** Raw, immutable baseline text and bounding boxes extracted from genuine image pixels.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | OCR result UUID |
| `image_id` | VARCHAR(36) | No | None | FK -> `product_images.id` | Image from which text was recognized |
| `raw_text` | TEXT | No | None | | Complete concatenated normalized OCR text |
| `confidence` | FLOAT | No | None | | Mean recognition confidence score (0.0 - 1.0) |
| `bounding_boxes_json`| TEXT | No | None | | Serialized JSON array of `[x1, y1, x2, y2]` text boxes |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Extraction timestamp |

---

### 2.6 Table: `declarations`
**Purpose:** Structured statutory declaration fields preserving both AI extraction baseline and officer corrections.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Declaration record UUID |
| `inspection_id` | VARCHAR(36) | No | None | FK -> `inspections.id` | Parent inspection |
| `field_name` | VARCHAR(100) | No | None | | Canonical key: `commodity_name`, `manufacturer_details`, `net_quantity`, `mrp`, `date_of_manufacture_packing`, `consumer_care_details`, `country_of_origin`, `unit_sale_price` |
| `extracted_value` | TEXT | Yes | None | | Immutable OCR-extracted string |
| `normalized_value` | TEXT | Yes | None | | Cleaned/standardized text representation |
| `confidence` | FLOAT | Yes | 0.0 | | OCR recognition confidence |
| `bounding_box_json`| TEXT | Yes | None | | Bounding box `[x1, y1, x2, y2]` on source image |
| `extraction_status`| VARCHAR(50) | Yes | `'EXTRACTED'` | | Status: `EXTRACTED`, `NOT_FOUND`, `LOW_CONFIDENCE`, `NEEDS_REVIEW`, `CONFLICTING`, `OCR_UNAVAILABLE` |
| `corrected_value` | TEXT | Yes | None | | Officer-verified replacement value |
| `is_applicable` | BOOLEAN | Yes | True | | Applicability flag for this commodity |
| `verification_status`| VARCHAR(50) | Yes | `'UNVERIFIED'` | | Verification state: `UNVERIFIED`, `VERIFIED`, `CORRECTED`, `REQUIRES_REVIEW` |
| `verified_by` | VARCHAR(100) | Yes | None | | Officer ID who performed verification |
| `verified_at` | TIMESTAMP | Yes | None | | Verification timestamp |
| `correction_reason`| TEXT | Yes | None | | Officer rationale or conflict JSON |
| `source_image_id` | VARCHAR(36) | Yes | None | FK -> `product_images.id` (SET NULL) | Image where field was observed |
| `placement_status`| VARCHAR(50) | Yes | `'NOT_DETERMINABLE'` | | `PLACEMENT_COMPLIANT`, `PLACEMENT_NON_COMPLIANT`, `PLACEMENT_UNCERTAIN`, `NOT_DETERMINABLE`, `MANUAL_VERIFICATION_REQUIRED` |
| `placement_details_json`| TEXT | Yes | None | | Serialized panel classification details |
| `font_size_status`| VARCHAR(50) | Yes | `'FONT_SIZE_UNDETERMINABLE'` | | `FONT_SIZE_COMPLIANT`, `FONT_SIZE_NON_COMPLIANT`, `FONT_SIZE_UNCERTAIN`, `FONT_SIZE_UNDETERMINABLE`, `MANUAL_VERIFICATION_REQUIRED` |
| `font_size_details_json`| TEXT | Yes | None | | Millimetre measurement & calibration metadata |
| `readability_status`| VARCHAR(50) | Yes | `'NOT_OBSERVABLE'` | | `READABLE`, `POOR_READABILITY`, `UNREADABLE`, `UNCERTAIN`, `NOT_OBSERVABLE`, `MANUAL_VERIFICATION_REQUIRED` |
| `readability_details_json`| TEXT | Yes | None | | Crop Laplacian blur, contrast, and ML score |
| `format_status` | VARCHAR(50) | Yes | `'COMPLIANT'` | | `COMPLIANT`, `NON_COMPLIANT`, `POTENTIAL_MISLEADING`, `UNCERTAIN`, `NOT_APPLICABLE` |
| `format_details_json`| TEXT | Yes | None | | Syntax and legal format validation details |
| `validation_matrix_json`| TEXT | Yes | None | | Unified multi-dimensional compliance matrix row |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |
| `updated_at` | TIMESTAMP | Yes | `utcnow()` | | Last update timestamp |

---

### 2.7 Table: `rule_versions`
**Purpose:** Version-pinned statutory legal metrology rule registry.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Rule record UUID |
| `rule_code` | VARCHAR(50) | No | None | INDEX | Canonical rule identifier (e.g. `PCR_RULE_06_1_E`) |
| `version_number` | INTEGER | No | 1 | | Version number for immutable pinning |
| `title` | VARCHAR(255) | No | None | | Statutory title |
| `category` | VARCHAR(50) | No | None | | `CATEGORY_A_LEGAL`, `CATEGORY_B_DATA_QUALITY` |
| `statutory_reference`| VARCHAR(255)| No | None | | Exact legal citation under PCR 2011 |
| `rule_logic_description`| TEXT | No | None | | Statutory evaluation logic |
| `severity` | VARCHAR(50) | Yes | `'MAJOR'` | | `CRITICAL`, `MAJOR`, `MINOR`, `INFO` |
| `is_active` | BOOLEAN | Yes | True | | Active status flag |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |

---

### 2.8 Table: `compliance_checks`
**Purpose:** Deterministic rule evaluation findings with lifecycle tracking for human adjudication.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Check result UUID |
| `inspection_id` | VARCHAR(36) | No | None | FK -> `inspections.id` | Parent inspection |
| `rule_version_id`| VARCHAR(36) | No | None | FK -> `rule_versions.id` | Pinned statutory rule version |
| `rule_code` | VARCHAR(50) | No | None | | Snapshot of rule code |
| `title` | VARCHAR(255) | No | None | | Rule title |
| `severity` | VARCHAR(50) | Yes | `'MAJOR'` | | Rule severity |
| `result_state` | VARCHAR(50) | No | None | | Automated state: `PASS`, `POTENTIAL_NON_COMPLIANCE`, `INSUFFICIENT_EVIDENCE`, `NEEDS_MANUAL_VERIFICATION`, `NOT_APPLICABLE` |
| `extracted_value` | TEXT | Yes | None | | Snapshot of effective value evaluated |
| `explanation` | TEXT | No | None | | Detailed legal explanation and justification |
| `adjudication_status`| VARCHAR(50)| Yes | `'PENDING'` | | Officer lifecycle: `PENDING`, `CONFIRMED`, `DISMISSED`, `CORRECTED`, `NOT_APPLICABLE`, `NEEDS_MORE_EVIDENCE` |
| `adjudication_notes`| TEXT | Yes | None | | Mandatory remarks when dismissing or confirming |
| `adjudicated_by` | VARCHAR(100)| Yes | None | | Officer ID who adjudicated |
| `adjudicated_at` | TIMESTAMP | Yes | None | | Adjudication timestamp |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |

---

### 2.9 Table: `evidence`
**Purpose:** Photographic bounding-box crops linked to compliance checks, creating an audit-ready chain of custody.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Evidence record UUID |
| `check_id` | VARCHAR(36) | No | None | FK -> `compliance_checks.id`| Associated finding |
| `image_id` | VARCHAR(36) | Yes | None | FK -> `product_images.id` (SET NULL) | Source package photograph |
| `bounding_box_json`| TEXT | Yes | None | | Bounding box coordinates `[x1, y1, x2, y2]` |
| `crop_image_path`| VARCHAR(500) | Yes | None | | File path of cropped evidence region on disk |
| `highlight_text` | TEXT | No | None | | Text snippet or failure description highlighted |
| `reason` | TEXT | Yes | None | | Evidentiary rationale |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |

---

### 2.10 Table: `inspector_reviews`
**Purpose:** Immutable audit log of individual officer adjudication actions on compliance checks.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Review log UUID |
| `check_id` | VARCHAR(36) | No | None | FK -> `compliance_checks.id`| Adjudicated finding |
| `officer_id` | VARCHAR(36) | No | None | FK -> `users.id` | Adjudicating officer |
| `action` | VARCHAR(50) | No | None | | Decision: `CONFIRMED`, `DISMISSED`, `CORRECTED`, `NOT_APPLICABLE`, `NEEDS_MORE_EVIDENCE` |
| `remarks` | TEXT | Yes | None | | Officer remarks |
| `reviewed_at` | TIMESTAMP | Yes | `utcnow()` | | Timestamp of review |

---

### 2.11 Table: `reports`
**Purpose:** Official statutory PDF/DOCX inspection report metadata and cryptographic integrity seal.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Report record UUID |
| `inspection_id` | VARCHAR(36) | No | None | UNIQUE, FK -> `inspections.id` | 1-to-1 link to finalized inspection |
| `report_version` | INTEGER | No | 1 | | Version number (increments only on explicit regeneration) |
| `pdf_path` | VARCHAR(500) | No | None | | File path to generated PDF on disk |
| `docx_path` | VARCHAR(500) | Yes | None | | File path to generated editable DOCX on disk |
| `pdf_hash` | VARCHAR(64) | Yes | None | | SHA-256 cryptographic digest of PDF binary |
| `legal_safety_statement`| TEXT | No | None | | Statutory limitation clause (PCR 2011 Rule 19 notice) |
| `generated_at` | TIMESTAMP | Yes | `utcnow()` | | Generation timestamp |

---

### 2.12 Table: `audit_logs`
**Purpose:** System-wide immutable append-only audit trail for legal defensibility.
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Audit log UUID |
| `inspection_id` | VARCHAR(36) | Yes | None | FK -> `inspections.id` (SET NULL) | Associated inspection (preserves log if inspection deleted) |
| `actor_id` | VARCHAR(100) | No | None | | Officer ID or system process executing the action |
| `action` | VARCHAR(100) | No | None | | Event: `INSPECTION_CREATED`, `OCR_RUN`, `DECLARATION_UPDATED`, `FINDING_ADJUDICATED`, `INSPECTION_FINALIZED`, `REPORT_GENERATED`, `REPORT_DELETED`, `INSPECTION_DELETED` |
| `entity_type` | VARCHAR(100) | No | None | | Target entity: `inspection`, `declaration`, `compliance_check`, `report` |
| `entity_id` | VARCHAR(36) | Yes | None | | Primary key of modified entity |
| `old_value` | TEXT | Yes | None | | Previous state (JSON or string) |
| `new_value` | TEXT | Yes | None | | New state (JSON or string) |
| `details` | TEXT | Yes | None | | Contextual details, IP address, or reason |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Timestamp of occurrence |

---

### 2.13 Table: `inspection_number_counters`
**Purpose:** Atomic sequence generator for year-based inspection numbers (`LM-{YYYY}-{00001}`).
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `year` | INTEGER | No | None | PK | Year (e.g. `2026`) |
| `next_number` | INTEGER | No | 1 | | Next sequence integer to allocate |

**Concurrency Guarantee (AUDIT-CONCUR-01):**  
Allocated via database row-level locking:
```sql
UPDATE inspection_number_counters 
SET next_number = next_number + 1 
WHERE year = :year 
RETURNING next_number - 1;
```
Safe across unlimited concurrent Uvicorn workers, Gunicorn processes, or container replicas.

---

### 2.14 Table: `product_listings`
**Purpose:** Digital / e-commerce platform product information for multi-modal marketplace surveillance (PS 26034).
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Listing record UUID |
| `inspection_id` | VARCHAR(36) | No | None | UNIQUE, INDEX, FK -> `inspections.id` | 1-to-1 link to inspection |
| `product_name` | VARCHAR(255) | Yes | None | | Declared online product name |
| `brand_name` | VARCHAR(255) | Yes | None | | Online brand name |
| `mrp` | VARCHAR(100) | Yes | None | | Listed online price |
| `net_quantity` | VARCHAR(100) | Yes | None | | Listed net quantity |
| `manufacturer_details`| TEXT | Yes | None | | Listed manufacturer information |
| `importer_details` | TEXT | Yes | None | | Listed importer information |
| `country_of_origin`| VARCHAR(100) | Yes | None | | Listed country of origin |
| `consumer_care_details`| TEXT | Yes | None | | Listed consumer care contact |
| `date_information` | VARCHAR(150) | Yes | None | | Listed expiry / best before info |
| `seller_information`| TEXT | Yes | None | | E-commerce seller / merchant info |
| `product_description`| TEXT | Yes | None | | Raw listing description |
| `listing_url` | VARCHAR(1000)| Yes | None | | URL to online product listing |
| `source` | VARCHAR(50) | No | `'MANUAL_LISTING_INPUT'` | | Origin of listing data |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |
| `updated_at` | TIMESTAMP | Yes | `utcnow()` | | Update timestamp |

---

### 2.15 Table: `listing_comparisons`
**Purpose:** Field-by-field discrepancy comparison between physical package OCR and e-commerce listing (Rule 18(2A) & Rule 6(10)).
| Column Name | SQL Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | VARCHAR(36) | No | `uuid4()` | PK | Comparison item UUID |
| `inspection_id` | VARCHAR(36) | No | None | INDEX, FK -> `inspections.id` | Parent inspection |
| `listing_id` | VARCHAR(36) | No | None | INDEX, FK -> `product_listings.id` | Parent product listing |
| `field_name` | VARCHAR(100) | No | None | | Field: `mrp`, `net_quantity`, `commodity_name`, `manufacturer_details`, `country_of_origin`, `consumer_care_details` |
| `listing_value` | TEXT | Yes | None | | Value from e-commerce listing |
| `package_value` | TEXT | Yes | None | | Value from physical package OCR |
| `comparison_status`| VARCHAR(50) | No | None | | Comparison: `MATCH`, `MISMATCH`, `MISSING_ON_LISTING`, `MISSING_ON_PACKAGE`, `UNCERTAIN` |
| `difference_explanation`| TEXT | Yes | None | | Discrepancy analysis explanation |
| `package_ocr_evidence`| TEXT | Yes | None | | OCR evidence text snippet |
| `ocr_confidence` | FLOAT | Yes | 0.0 | | OCR confidence on package value |
| `source_image_id` | VARCHAR(36) | Yes | None | FK -> `product_images.id` (SET NULL) | Source image ID |
| `bounding_box_json`| TEXT | Yes | None | | Coordinate box on physical package |
| `applicable_rule_code`| VARCHAR(100)| Yes | None | | e.g. `PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING`, `PCR_RULE_06_10_ECOMMERCE_DECLARATION` |
| `inspector_status`| VARCHAR(50) | No | `'PENDING_REVIEW'`| | Officer status: `PENDING_REVIEW`, `VERIFIED_MATCH`, `CONFIRMED_DISCREPANCY`, `DISMISSED_DISCREPANCY` |
| `inspector_remarks`| TEXT | Yes | None | | Remarks entered during adjudication |
| `adjudicated_by` | VARCHAR(100) | Yes | None | | Officer ID who adjudicated |
| `adjudicated_at` | TIMESTAMP | Yes | None | | Timestamp of adjudication |
| `listing_provenance`| VARCHAR(50)| No | `'MANUAL_LISTING_INPUT'` | | Provenance tag |
| `package_provenance`| VARCHAR(50)| No | `'PACKAGE_OCR'` | | Provenance tag |
| `created_at` | TIMESTAMP | Yes | `utcnow()` | | Creation timestamp |
| `updated_at` | TIMESTAMP | Yes | `utcnow()` | | Update timestamp |

---

## 3. Entity Lifecycles and State Transition Rules

### 3.1 Inspection Entity Lifecycle
```
[DRAFT]
   │  Inspector enters product details & location (client_draft_id created)
   ▼
[IMAGES_UPLOADED]
   │  Front and back packaging panel photographs uploaded and validated
   ▼
[ANALYZING]
   │  PaddleOCR + PP-Structure layout + extraction running in background
   ▼
[ANALYSIS_COMPLETE]
   │  Declarations extracted, validation matrix derived, compliance checks run
   ▼
[NEEDS_REVIEW]
   │  At least one ComplianceCheck has adjudication_status == 'PENDING'
   │  (Inspector reviews findings, corrects declarations, confirms/dismisses)
   ▼
[COMPLETED / FINALIZED]
   │  All findings resolved (zero pending); final overall_status computed;
   │  Report generated (SHA-256 sealed); images & findings become IMMUTABLE.
```

### 3.2 Finding / ComplianceCheck Adjudication Lifecycle
```
Automated Rule Evaluation Output:
[result_state: PASS / POTENTIAL_NON_COMPLIANCE / INSUFFICIENT_EVIDENCE / NEEDS_MANUAL_VERIFICATION]
   │
   ▼
Initial State: [adjudication_status: PENDING]
   │
   ├─► CONFIRMED           (Officer confirms violation; advances to final potential non-compliance)
   ├─► DISMISSED           (Officer dismisses finding with statutory justification; cleared)
   ├─► CORRECTED           (Officer fixes declaration; triggers deterministic re-evaluation)
   ├─► NOT_APPLICABLE      (Officer notes statutory exemption; excluded from violation count)
   └─► NEEDS_MORE_EVIDENCE (Requests field officer to re-photograph packaging panel)
```
**Authoritative Finalization Invariant:**  
`POST /api/inspections/{id}/finalize` blocks if:
$$\text{COUNT}(\text{compliance\_checks where adjudication\_status} = \text{'PENDING'}) > 0$$

---

## 4. Connection Pooling and Serverless Resilience

```python
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # Discards dropped/cold connections on Neon compute sleep
    pool_recycle=300,    # Refreshes idle connections every 5 minutes
    echo=False
)
```
- Neon serverless compute enters sleep when idle. `pool_pre_ping=True` executes `SELECT 1` before checkout to seamlessly handle compute wake-up without throwing `500 OperationalError`.
- `pool_recycle=300` prevents dead sockets caused by AWS cloud NAT gateways dropping silent TCP connections after 350 seconds.
