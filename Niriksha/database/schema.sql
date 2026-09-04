-- =============================================================================
-- SIH 2026 Legal Metrology Packaged-Commodity Inspection System
-- Complete PostgreSQL Schema for Supabase
-- =============================================================================

-- Enable UUID extension if required
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users / Inspectors
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    officer_id VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(30),
    designation VARCHAR(100) NOT NULL,
    zone VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) DEFAULT 'INSPECTOR',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Inspections Lifecycle
CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    inspection_number VARCHAR(50) UNIQUE NOT NULL,
    inspector_id TEXT REFERENCES users(id) ON DELETE RESTRICT,
    location VARCHAR(200) NOT NULL,
    status VARCHAR(50) DEFAULT 'DRAFT',
    overall_status VARCHAR(50) DEFAULT 'NEEDS_MANUAL_VERIFICATION',
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP WITH TIME ZONE
);

-- 3. Products Metadata (1:1 with inspection)
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    inspection_id TEXT UNIQUE REFERENCES inspections(id) ON DELETE CASCADE,
    product_name VARCHAR(200) NOT NULL,
    brand_name VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,
    batch_number VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Product Images (Front / Back / Side panel views)
CREATE TABLE IF NOT EXISTS product_images (
    id TEXT PRIMARY KEY,
    inspection_id TEXT REFERENCES inspections(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    view_type VARCHAR(50) NOT NULL,
    sequence_order INTEGER DEFAULT 0,
    quality_score FLOAT DEFAULT 1.0,
    quality_status VARCHAR(30) DEFAULT 'GOOD',
    blur_score FLOAT,
    glare_score FLOAT,
    resolution_status VARCHAR(30),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Raw OCR Results (Layer 1: Immutable AI baseline)
CREATE TABLE IF NOT EXISTS ocr_results (
    id TEXT PRIMARY KEY,
    image_id TEXT REFERENCES product_images(id) ON DELETE CASCADE,
    raw_text TEXT,
    confidence FLOAT,
    bounding_box_json TEXT,
    is_immutable BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Statutory Declarations (7 Core Fields + Origin)
CREATE TABLE IF NOT EXISTS declarations (
    id TEXT PRIMARY KEY,
    inspection_id TEXT REFERENCES inspections(id) ON DELETE CASCADE,
    field_type VARCHAR(50) NOT NULL,
    extracted_value TEXT,
    ocr_confidence VARCHAR(30),
    confidence_score FLOAT,
    bounding_box_json TEXT,
    source_image_id TEXT,
    corrected_value TEXT,
    verification_status VARCHAR(50) DEFAULT 'UNVERIFIED',
    verified_by TEXT,
    correction_reason TEXT,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Rule Versions (Immutable statutory citations)
CREATE TABLE IF NOT EXISTS rule_versions (
    id TEXT PRIMARY KEY,
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    version_number INTEGER DEFAULT 1,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50) NOT NULL,
    statutory_reference TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 8. Compliance Checks (Layer 2: Deterministic Rule Findings)
CREATE TABLE IF NOT EXISTS compliance_checks (
    id TEXT PRIMARY KEY,
    inspection_id TEXT REFERENCES inspections(id) ON DELETE CASCADE,
    rule_version_id TEXT REFERENCES rule_versions(id),
    rule_code VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    severity VARCHAR(30) NOT NULL,
    result_state VARCHAR(50) NOT NULL,
    extracted_value TEXT,
    explanation TEXT,
    adjudication_status VARCHAR(50) DEFAULT 'PENDING',
    adjudication_notes TEXT,
    adjudicated_by TEXT,
    adjudicated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Evidence Linking
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    check_id TEXT REFERENCES compliance_checks(id) ON DELETE CASCADE,
    image_id TEXT REFERENCES product_images(id) ON DELETE SET NULL,
    bounding_box_json TEXT,
    crop_image_path VARCHAR(500),
    highlight_text TEXT,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 10. Inspector Reviews (Layer 3: Human Adjudication History)
CREATE TABLE IF NOT EXISTS inspector_reviews (
    id TEXT PRIMARY KEY,
    check_id TEXT REFERENCES compliance_checks(id) ON DELETE CASCADE,
    officer_id TEXT NOT NULL,
    action VARCHAR(50) NOT NULL,
    remarks TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 11. Reports (Layer 4: Versioned Statutory PDF Reports)
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    inspection_id TEXT UNIQUE REFERENCES inspections(id) ON DELETE CASCADE,
    report_version INTEGER DEFAULT 1,
    pdf_path VARCHAR(500) NOT NULL,
    legal_safety_statement TEXT NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 12. Audit Logs (Immutable Append-Only Security Trail)
CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    actor_id VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    inspection_id VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    details TEXT,
    ip_address VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for optimal performance
CREATE INDEX IF NOT EXISTS idx_inspections_officer ON inspections(inspector_id);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status, overall_status);
CREATE INDEX IF NOT EXISTS idx_declarations_inspection ON declarations(inspection_id);
CREATE INDEX IF NOT EXISTS idx_checks_inspection ON compliance_checks(inspection_id);
CREATE INDEX IF NOT EXISTS idx_audit_inspection ON audit_logs(inspection_id);
