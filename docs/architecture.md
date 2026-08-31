# NiriKsha — System Architecture & Technical Design

> **NiriKsha — SIH Prototype 2026 (For demonstration and evaluation purposes only)**

---

## 1. System Overview

**NiriKsha** is an AI-assisted legal metrology inspection and compliance decision-support system designed to evaluate packaged commodities against statutory declaration standards under the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)**.

The system enforces a **statutory safety principle**: AI and computer vision are strictly restricted to assistive roles (image ingestion, image quality assessment, text recognition, and structured field extraction). All legal compliance determinations and enforcement decisions are executed by a **deterministic statutory rule engine** coupled with a **human-in-the-loop inspector adjudication workflow**.

---

## 2. High-Level Architecture

```mermaid
flowchart TD
    subgraph Client Layer
        A[React Native / Expo Mobile App<br/>Android / iOS / Web]
        B[Static Inspection Portal<br/>FastAPI Mounted UI]
    end

    subgraph API Gateway & REST Layer
        C[FastAPI Application Server<br/>Uvicorn / Python 3.10+]
        D[JWT Authentication & RBAC]
        E[CORS & Static Asset Middleware]
    end

    subgraph Application Core Services
        F[Image Quality Assessment<br/>OpenCV Laplacian & Glare]
        G[Modular OCR Coordinator<br/>Morphological / Tesseract / CLAHE]
        H[Declaration Extraction Service<br/>Regex & Heuristic Parsers]
        I[Deterministic PCR Rule Engine<br/>Statutory Rules 6-1-A to G]
        J[ReportLab PDF Engine<br/>Inspection Certificate Generation]
    end

    subgraph Data & Storage Layer
        K[(Relational Database<br/>SQLite / PostgreSQL Supabase)]
        L[Local & Cloud Storage<br/>uploads/ & generated_reports/]
    end

    A -->|HTTPS / JSON & Multipart| C
    B -->|HTTP| C
    C --> D
    C --> E
    C --> F
    C --> G
    C --> H
    C --> I
    C --> J
    D --> K
    F --> L
    G --> K
    H --> K
    I --> K
    J --> L
    J --> K
```

---

## 3. End-to-End Inspection Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Inspector as Field Inspecting Officer
    participant App as Mobile App (React Native)
    participant API as FastAPI REST API
    participant CV as OpenCV Image Quality
    participant OCR as Modular OCR & Extraction
    participant RE as Deterministic Rule Engine
    participant DB as Relational Database
    participant PDF as ReportLab Service

    Inspector->>App: Authenticate (Officer ID + Password)
    App->>API: POST /api/auth/login
    API-->>App: JWT Access Token (HS256)

    Inspector->>App: Create New Inspection (Commodity, Brand, Batch, Location)
    App->>API: POST /api/inspections
    API->>DB: Persist Inspection Record (Status: DRAFT)
    API-->>App: Inspection Details

    Inspector->>App: Capture & Upload Package Images (Front, Back, Side)
    App->>API: POST /api/inspections/{id}/images
    API->>CV: Assess Quality (Blur, Glare, Resolution)
    CV-->>API: Quality Metrics (GOOD / WARNING / POOR)
    API->>DB: Store Image & Quality Metadata
    API-->>App: Upload Result & Quality Flags

    Inspector->>App: Trigger Automated Declaration Extraction
    App->>API: POST /api/inspections/{id}/ocr
    API->>OCR: Preprocess (CLAHE) + OCR + Field Parser
    OCR-->>API: 7 Structured Declarations (with Bounding Boxes & Confidence)
    API->>DB: Store Raw OCR & Structured Declarations
    API-->>App: Declarations List

    opt Inspector Correction
        Inspector->>App: Correct Misread Value / Unit
        App->>API: PATCH /api/declarations/{id}
        API->>DB: Store Corrected Value (Original OCR Preserved Immutably)
    end

    Inspector->>App: Run Statutory Evaluation
    App->>API: POST /api/inspections/{id}/evaluate
    API->>RE: Evaluate Declarations against PCR 2011 Rules
    RE-->>API: Findings (PASS / POTENTIAL_NON_COMPLIANCE / INSUFFICIENT_EVIDENCE / NOT_APPLICABLE)
    API->>DB: Persist Compliance Checks & Evidence Links
    API-->>App: Findings & Photographic Evidence Overlays

    Inspector->>App: Adjudicate Findings (Confirm / Dismiss / Correct / Request Image / N/A)
    App->>API: PATCH /api/findings/{id}/adjudicate
    API->>DB: Save Decision & Statutory Notes in Audit Log

    Inspector->>App: Finalize Inspection
    App->>API: POST /api/inspections/{id}/finalize
    Note over API: HTTP 409 Gate: Blocks finalization if any finding is unresolved
    API->>PDF: Compile Official Inspection Report PDF
    PDF-->>API: Generated PDF Binary
    API->>DB: Update Status (COMPLETED) & Save Report Record
    API-->>App: Finalized Inspection & PDF Download URL
```

---

## 4. Component Deep Dives

### 4.1 Mobile Application (`mobile/`)
- **Framework**: React Native 0.74.5 with Expo SDK 51.
- **Language**: TypeScript (`tsconfig.json` with strict mode enabled).
- **Navigation**: Native Stack Navigator (`@react-navigation/native-stack`) managing authenticated officer flows.
- **State & Storage**: `expo-secure-store` for JWT persistence, `expo-file-system` and `expo-sharing` for report caching and PDF distribution.
- **Offline Drafts**: Local state management allowing inspection registration in offline or low-connectivity retail environments.

### 4.2 REST API & Gateway (`backend/main.py`)
- **Framework**: FastAPI with asynchronous endpoints.
- **Security**: OAuth2 Bearer scheme with JWT (HS256) signature verification and bcrypt password hashing.
- **Error Handling**: Standardized HTTP status codes with structured error payloads (`401` Unauthorized, `404` Not Found, `409` Conflict / Unresolved Findings Gate, `422` Validation Error).
- **CORS**: Configured for cross-origin local development and mobile network connectivity.

### 4.3 Image Quality Assessment (`backend/image_quality.py`)
- **Blur Detection**: Calculates the variance of the Laplacian operator on grayscale package images. Scores below the threshold indicate motion or focus blur.
- **Glare & Exposure Analysis**: Computes pixel luminance percentiles (95th and 5th percentiles) to detect specular reflection on glossy laminate packaging or underexposed low-light captures.
- **Dimension Check**: Validates minimum resolution requirements (800x600 px) to ensure sufficient DPI for optical character extraction.

### 4.4 OCR & Declaration Extraction (`backend/ocr_service.py`, `backend/extraction_service.py`)
- **Image Preprocessing**: Non-destructive CLAHE (Contrast Limited Adaptive Histogram Equalization) on a derived image copy.
- **Text Region Detection**: Morphological rectangular dilation kernels `(20, 3)` merge character contours into horizontal text line bounding boxes `[x1, y1, x2, y2]`.
- **Statutory Extraction**: Heuristic and regular expression parsing maps raw OCR text blocks to 7 mandatory declaration fields defined under Rule 6(1) of PCR 2011.

### 4.5 Deterministic Rule Engine (`backend/rule_engine/`)
The rule engine evaluates structured declarations against codified statutory logic without non-deterministic LLM variance.

| Statutory Rule | Code | Requirement |
|---|---|---|
| **Rule 6(1)(a)** | `PCR_RULE_06_1_A` | Name and complete address of the Manufacturer, Packer, or Importer. |
| **Rule 6(1)(b)** | `PCR_RULE_06_1_B` | Country of Origin for imported commodities. |
| **Rule 6(1)(c)** | `PCR_RULE_06_1_C` | Net Quantity in standard metric SI units (`g`, `kg`, `ml`, `l`, `m`, `cm`, `number/units`). |
| **Rule 6(1)(d)** | `PCR_RULE_06_1_D` | Month and Year of manufacture, packing, or import. |
| **Rule 6(1)(e)** | `PCR_RULE_06_1_E` | Maximum Retail Price (MRP) formatted with statutory tax qualifier ("inclusive of all taxes" / "incl. of all taxes"). |
| **Rule 6(1)(f)** | `PCR_RULE_06_1_F` | Common or generic name of the packaged commodity. |
| **Rule 6(1)(g)** | `PCR_RULE_06_1_G` | Consumer care details (name/designation, address, telephone number, email). |

### 4.6 Statutory Report Generation (`backend/report_service.py`)
- **Engine**: ReportLab PDF library.
- **Output**: Formal Inspection Certificate PDF including:
  - Inspection metadata (Number, Date, Officer ID, Location, Commodity Details)
  - Statutory findings table with rule references, extracted values, and compliance states
  - Photographic evidence block showing cropped package labels and bounding boxes
  - Inspector adjudication actions, notes, and digital sign-off
  - Official statutory disclaimer stating the advisory and decision-support nature of the system

---

## 5. Database Schema & Relationships

```mermaid
erDiagram
    USERS ||--o{ INSPECTIONS : conducts
    USERS ||--o{ INSPECTOR_REVIEWS : records
    INSPECTIONS ||--|| PRODUCTS : inspects
    INSPECTIONS ||--o{ PRODUCT_IMAGES : contains
    INSPECTIONS ||--o{ DECLARATIONS : has
    INSPECTIONS ||--o{ COMPLIANCE_CHECKS : evaluates
    INSPECTIONS ||--o{ AUDIT_LOGS : logs
    INSPECTIONS ||--o| REPORTS : generates
    COMPLIANCE_CHECKS ||--o{ EVIDENCE : links
    COMPLIANCE_CHECKS ||--o{ INSPECTOR_REVIEWS : adjudicates

    USERS {
        string id PK
        string officer_id UK
        string full_name
        string designation
        string zone
        string password_hash
        string role
    }

    INSPECTIONS {
        string id PK
        string inspection_number UK
        string inspector_id FK
        string location
        string status
        string overall_status
        datetime created_at
        datetime finalized_at
    }

    PRODUCTS {
        string id PK
        string inspection_id FK
        string product_name
        string brand_name
        string category
        string batch_number
    }

    PRODUCT_IMAGES {
        string id PK
        string inspection_id FK
        string file_path
        string view_type
        float blur_score
        float glare_score
        float quality_score
        string quality_status
    }

    DECLARATIONS {
        string id PK
        string inspection_id FK
        string field_name
        string extracted_value
        string corrected_value
        string verification_status
        float confidence
    }

    COMPLIANCE_CHECKS {
        string id PK
        string inspection_id FK
        string rule_code
        string rule_name
        string result_state
        string adjudication_action
        string officer_notes
    }

    AUDIT_LOGS {
        string id PK
        string inspection_id FK
        string actor_id FK
        string action
        string details_json
        datetime created_at
    }

    REPORTS {
        string id PK
        string inspection_id FK
        string report_number UK
        integer report_version
        string pdf_path
        datetime generated_at
    }
```
