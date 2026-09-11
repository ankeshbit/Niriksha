# NiriKsha — System Architecture & Technical Design

> **NiriKsha — SIH Prototype 2026 (Problem Statement 26034)**  
> *“Software System to check compliance of Packaged Commodities under Legal Metrology (Packaged Commodities) Rules, 2011 by scanning products, images and labels.”*

---

## 1. System Overview

**NiriKsha** is an AI-assisted legal metrology inspection and compliance decision-support system designed to evaluate packaged commodities against statutory declaration standards under the **Legal Metrology (Packaged Commodities) Rules, 2011 (PCR 2011)**.

The system enforces a **statutory safety principle**: AI and computer vision are strictly restricted to assistive roles (image ingestion, image quality assessment, text recognition, spatial coordinate detection, and structured field extraction). All legal compliance determinations and enforcement decisions are executed by a **deterministic statutory rule engine** coupled with a **human-in-the-loop inspector adjudication workflow**.

---

## 2. Technology Stack & Database Invariants

- **Field Inspector Mobile Client:** React Native + Expo + TypeScript (Android / iOS / Web).
- **Backend API Gateway:** FastAPI (Python 3.10+) running with Uvicorn.
- **Database Engine (STRICT INVARIANT):**
  - **Production:** Neon PostgreSQL (Cloud-native serverless PostgreSQL with TLS encryption).
  - **Testing:** Dedicated separate Neon PostgreSQL test database.
  - **SQLite:** **STRICTLY FORBIDDEN** for application runtime and automated testing. Zero local `.db` files, zero in-memory SQLite instances.
- **OCR Engine:** PaddleOCR CPU singleton (1024px dimension cap) with Tesseract fallback where configured.
- **Computer Vision:** OpenCV (Laplacian blur variance, luminance contrast analysis).
- **Report Engines:**
  - ReportLab (Formal sealed statutory PDF reports with SHA-256 integrity hash).
  - python-docx (Editable statutory Word reports with evidence plates).

---

## 3. High-Level Architecture Diagram

```mermaid
flowchart TD
    subgraph Client Layer [Field Inspector Terminal]
        A[React Native / Expo Mobile App<br/>Android / iOS / Web]
        A1[Offline Draft Storage<br/>AsyncStorage & SecureStore]
    end

    subgraph API Gateway & REST Layer
        C[FastAPI Application Server<br/>Uvicorn / Python 3.10+]
        D[JWT Authentication & RBAC<br/>INSPECTOR, SUPERVISOR, ADMIN]
        E[CORS & Static Asset Middleware]
    end

    subgraph Core AI & Vision Services
        F[Image Quality Assessment<br/>OpenCV Laplacian & Glare]
        G[PaddleOCR Singleton<br/>1024px Dim Limit + Spatial BBoxes]
        H[Multi-Panel Text Consolidation<br/>Cross-Image Conflict Detection]
    end

    subgraph Legal Metrology Compliance Engine [PCR 2011]
        I1[Placement Analysis Engine<br/>Rules 6, 7 & 12 PDP Validation]
        I2[Font Size Analysis Pipeline<br/>Rule 9 Table 1 Physical Thresholds]
        I3[Declaration Readability Engine<br/>Crop Laplacian Blur & Contrast]
        I4[Misleading / Format Validator<br/>MRP Tax Qualifiers & Metric Units]
        I5[Unified Compliance Matrix<br/>7-Dimensional Statutory Table]
    end

    subgraph Evidence & Statutory Reports
        J1[ReportLab PDF Engine<br/>Tamper-Evident SHA-256 Sealed Reports]
        J2[python-docx Export Engine<br/>Editable Official Word Documents]
        J3[Product Repository & History<br/>Chronological Surveillance Archive]
    end

    subgraph Persistence Layer [PostgreSQL ONLY]
        K[(Neon PostgreSQL Database<br/>Production / Test Isolation)]
        L[Local & Cloud Storage<br/>uploads/ & generated_reports/]
    end

    A -->|HTTPS / REST API| C
    A <-->|Local Sync| A1
    C --> D
    C --> E
    C --> F
    C --> G
    C --> H
    H --> I1
    H --> I2
    H --> I3
    H --> I4
    I1 & I2 & I3 & I4 --> I5
    I5 --> J1
    I5 --> J2
    I5 --> J3
    D & F & G & H & I5 & J1 & J2 & J3 <--> K
    F & J1 & J2 <--> L
```

---

## 4. End-to-End Inspection Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Inspector as Field Inspecting Officer
    participant App as Mobile App (React Native)
    participant API as FastAPI REST API
    participant CV as OpenCV Image Quality
    participant OCR as PaddleOCR Singleton
    participant CE as Compliance Engine (Placement / Font / Readability)
    participant DB as Neon PostgreSQL
    participant Report as PDF / DOCX Generators

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
    API->>OCR: PaddleOCR Singleton (1024px cap) + Layout Extraction
    OCR-->>API: Bounding Boxes, Confidence & Raw Transcripts
    API->>CE: Run Placement, Font-Size, Readability & Format Engines
    CE-->>API: Unified Compliance Matrix Table
    API->>DB: Store Declarations, Evidence & Matrix JSON
    API-->>App: Extracted Declarations + Compliance Matrix

    opt Inspector Adjudication
        Inspector->>App: Review Evidence, Adjust Declarations, Adjudicate Findings
        App->>API: PATCH /api/findings/{id}/adjudicate
        API->>DB: Update Adjudication Status (CONFIRMED / DISMISSED / MANUAL)
    end

    Inspector->>App: Finalize Inspection
    App->>API: POST /api/inspections/{id}/finalize
    API->>Report: Generate Immutable PDF (SHA-256) & DOCX
    API->>DB: Persist Sealed Reports & Mark Finalized
    API-->>App: Finalized Status & Download URLs
```

---

## 5. Compliance Engine Modules (PCR 2011)

1. **Placement Analysis (`backend/placement_service.py`):**  
   Evaluates Principal Display Panel (PDP) placement for Net Quantity and Commodity Name under Rules 6, 7 & 12. Distinguishes front PDP from information panels.
2. **Font-Size Analysis (`backend/font_size_service.py`):**  
   Evaluates character height against Rule 9 Table 1 thresholds (1.0mm, 2.0mm, 4.0mm, 6.0mm). Strictly enforces anti-fabrication: without physical calibration, returns `FONT_SIZE_UNDETERMINABLE` rather than guessing millimeters from pixels.
3. **Declaration Readability (`backend/readability_service.py`):**  
   Measures localized bounding box blur variance and contrast. Never converts observation defects or low confidence into automatic legal violations.
4. **Format & Misleading Validation (`backend/declaration_validation_service.py`):**  
   Validates mandatory statutory qualifiers (e.g. MRP "inclusive of all taxes", SI metric units, date plausibility, and consumer care channels).
5. **Unified Declaration Compliance Matrix:**  
   Generates a 7-dimensional compliance table displayed on the mobile terminal and statutory reports.

---

## 6. Security, RBAC & Immutability

- **Role-Based Access Control:** Field Inspectors are isolated to their own inspections. Supervisors and Admins possess audit and cross-district surveillance access.
- **Report Immutability:** Finalized reports are sealed with SHA-256 integrity hashes. Once generated, reports cannot be altered or deleted.
- **Database Safety Guard:** Hard safety guards in test configurations immediately terminate any destructive operations if the test database hostname or database matches production.
