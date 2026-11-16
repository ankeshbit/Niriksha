-- =============================================================================
-- SIH 2026 Legal Metrology Packaged-Commodity Inspection System (NiriKsha)
-- Canonical PostgreSQL DDL Schema Definition
-- Fully synchronized with backend/models.py (17 Tables)
-- =============================================================================

-- Enable UUID extension if required
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Users / Inspectors
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    officer_id VARCHAR(50) UNIQUE NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(30),
    designation VARCHAR(100) NOT NULL,
    zone VARCHAR(100) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'INSPECTOR',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP WITHOUT TIME ZONE,
    previous_login_at TIMESTAMP WITHOUT TIME ZONE,
    password_updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_users_officer_id ON users (officer_id);

-- 2. Inspections Lifecycle
CREATE TABLE IF NOT EXISTS inspections (
    id VARCHAR(36) PRIMARY KEY,
    inspection_number VARCHAR(50) UNIQUE NOT NULL,
    inspector_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    location VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    overall_status VARCHAR(50),
    inspection_type VARCHAR(50) NOT NULL DEFAULT 'PHYSICAL',
    notes TEXT,
    client_draft_id VARCHAR(100),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finalized_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_inspections_inspection_number ON inspections (inspection_number);
CREATE INDEX IF NOT EXISTS ix_inspections_inspector_id ON inspections (inspector_id);
CREATE INDEX IF NOT EXISTS ix_inspections_location ON inspections (location);
CREATE INDEX IF NOT EXISTS ix_inspections_status ON inspections (status);
CREATE INDEX IF NOT EXISTS ix_inspections_overall_status ON inspections (overall_status);
CREATE INDEX IF NOT EXISTS ix_inspections_client_draft_id ON inspections (client_draft_id);
CREATE INDEX IF NOT EXISTS ix_inspections_created_at ON inspections (created_at);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections (status, overall_status);

-- 3. Products Metadata (1:1 with inspection)
CREATE TABLE IF NOT EXISTS products (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) UNIQUE NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    product_name VARCHAR(255) NOT NULL,
    brand_name VARCHAR(255),
    category VARCHAR(100) NOT NULL,
    batch_number VARCHAR(100),
    product_key VARCHAR(64),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_products_product_name ON products (product_name);
CREATE INDEX IF NOT EXISTS ix_products_brand_name ON products (brand_name);
CREATE INDEX IF NOT EXISTS ix_products_product_key ON products (product_key);

-- 4. Product Images (Multi-panel photographic views)
CREATE TABLE IF NOT EXISTS product_images (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    original_filename VARCHAR(255),
    file_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100) DEFAULT 'image/jpeg',
    file_size INTEGER DEFAULT 0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    sequence_order INTEGER DEFAULT 1,
    view_type VARCHAR(50) NOT NULL,
    blur_score FLOAT DEFAULT 0.0,
    glare_score FLOAT DEFAULT 0.0,
    quality_score FLOAT DEFAULT 1.0,
    quality_status VARCHAR(50) DEFAULT 'GOOD',
    quality_metadata_json TEXT,
    processing_status VARCHAR(50) DEFAULT 'UPLOADED',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_product_images_inspection_id ON product_images (inspection_id);

-- 5. Raw OCR Results (Layer 1: Immutable AI baseline)
CREATE TABLE IF NOT EXISTS ocr_results (
    id VARCHAR(36) PRIMARY KEY,
    image_id VARCHAR(36) NOT NULL REFERENCES product_images(id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    normalized_text TEXT,
    confidence FLOAT NOT NULL,
    bounding_boxes_json TEXT NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ocr_results_image_id ON ocr_results (image_id);

-- 6. OCR Jobs (Layer 1: Crash-resilient asynchronous task queue state)
CREATE TABLE IF NOT EXISTS ocr_jobs (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    current_stage VARCHAR(50) NOT NULL DEFAULT 'QUEUED',
    progress_percent INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    heartbeat_at TIMESTAMP WITHOUT TIME ZONE,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    worker_id VARCHAR(100),
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    error_code VARCHAR(50),
    error_message TEXT,
    ocr_summary_json TEXT
);

CREATE INDEX IF NOT EXISTS ix_ocr_jobs_inspection_id ON ocr_jobs (inspection_id);
CREATE INDEX IF NOT EXISTS ix_ocr_jobs_status ON ocr_jobs (status);
CREATE INDEX IF NOT EXISTS ix_ocr_jobs_created_at ON ocr_jobs (created_at);
CREATE INDEX IF NOT EXISTS ix_ocr_jobs_heartbeat_at ON ocr_jobs (heartbeat_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ocr_jobs_active_per_inspection ON ocr_jobs (inspection_id) WHERE status IN ('PENDING', 'PROCESSING');

-- 7. Statutory Declarations (7 Core Rule 6 declarations + statutory validation attributes)
CREATE TABLE IF NOT EXISTS declarations (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    extracted_value TEXT,
    normalized_value TEXT,
    confidence FLOAT DEFAULT 0.0,
    bounding_box_json TEXT,
    extraction_status VARCHAR(50) DEFAULT 'EXTRACTED',
    corrected_value TEXT,
    is_applicable BOOLEAN DEFAULT TRUE,
    verification_status VARCHAR(50) DEFAULT 'UNVERIFIED',
    verified_by VARCHAR(100),
    verified_at TIMESTAMP WITHOUT TIME ZONE,
    correction_reason TEXT,
    source_image_id VARCHAR(36) REFERENCES product_images(id) ON DELETE SET NULL,
    placement_status VARCHAR(50) DEFAULT 'NOT_DETERMINABLE',
    placement_details_json TEXT,
    font_size_status VARCHAR(50) DEFAULT 'FONT_SIZE_UNDETERMINABLE',
    font_size_details_json TEXT,
    readability_status VARCHAR(50) DEFAULT 'NOT_OBSERVABLE',
    readability_details_json TEXT,
    format_status VARCHAR(50) DEFAULT 'COMPLIANT',
    format_details_json TEXT,
    validation_matrix_json TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_declarations_inspection_id ON declarations (inspection_id);

-- 8. Rule Versions (Codified statutory rules with immutable version pinning)
CREATE TABLE IF NOT EXISTS rule_versions (
    id VARCHAR(36) PRIMARY KEY,
    rule_code VARCHAR(50) NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    statutory_reference VARCHAR(255) NOT NULL,
    rule_logic_description TEXT NOT NULL,
    severity VARCHAR(50) DEFAULT 'MAJOR',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_rule_versions_rule_code ON rule_versions (rule_code);

-- 9. Compliance Checks (Layer 2: Deterministic Rule Engine Findings)
CREATE TABLE IF NOT EXISTS compliance_checks (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    rule_version_id VARCHAR(36) NOT NULL REFERENCES rule_versions(id),
    rule_code VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    severity VARCHAR(50) DEFAULT 'MAJOR',
    result_state VARCHAR(50) NOT NULL,
    extracted_value TEXT,
    explanation TEXT NOT NULL,
    adjudication_status VARCHAR(50) DEFAULT 'PENDING',
    adjudication_notes TEXT,
    adjudicated_by VARCHAR(100),
    adjudicated_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_compliance_checks_inspection_id ON compliance_checks (inspection_id);
CREATE INDEX IF NOT EXISTS ix_compliance_checks_inspection_id_result_state_adjudication_status ON compliance_checks (inspection_id, result_state, adjudication_status);

-- 10. Evidence Linking (Photographic crops & bounding box references)
CREATE TABLE IF NOT EXISTS evidence (
    id VARCHAR(36) PRIMARY KEY,
    check_id VARCHAR(36) NOT NULL REFERENCES compliance_checks(id) ON DELETE CASCADE,
    image_id VARCHAR(36) REFERENCES product_images(id) ON DELETE SET NULL,
    bounding_box_json TEXT,
    crop_image_path VARCHAR(500),
    highlight_text TEXT NOT NULL,
    reason TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_evidence_check_id ON evidence (check_id);

-- 11. Inspector Reviews (Layer 3: Human Adjudication Audit Log)
CREATE TABLE IF NOT EXISTS inspector_reviews (
    id VARCHAR(36) PRIMARY KEY,
    check_id VARCHAR(36) NOT NULL REFERENCES compliance_checks(id) ON DELETE CASCADE,
    officer_id VARCHAR(36) NOT NULL REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    remarks TEXT,
    reviewed_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_inspector_reviews_check_id ON inspector_reviews (check_id);

-- 12. Audit Logs (Immutable Append-Only Security Trail)
CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) REFERENCES inspections(id) ON DELETE SET NULL,
    actor_id VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(36),
    old_value TEXT,
    new_value TEXT,
    details TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_inspection_id ON audit_logs (inspection_id);

-- 13. Reports (Layer 4: Versioned Statutory PDF & DOCX Inspection Certificates)
CREATE TABLE IF NOT EXISTS reports (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) UNIQUE NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    report_version INTEGER NOT NULL DEFAULT 1,
    pdf_path VARCHAR(500) NOT NULL,
    docx_path VARCHAR(500),
    pdf_hash VARCHAR(64),
    legal_safety_statement TEXT NOT NULL,
    generated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 14. Inspection Number Counters (AUDIT-CONCUR-01: Atomic Sequence Counters)
CREATE TABLE IF NOT EXISTS inspection_number_counters (
    year INTEGER PRIMARY KEY,
    next_number INTEGER NOT NULL DEFAULT 1
);

-- 15. Product Listings (E-Commerce Online Commodity Declarations)
CREATE TABLE IF NOT EXISTS product_listings (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) UNIQUE NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    product_name VARCHAR(255),
    brand_name VARCHAR(255),
    mrp VARCHAR(100),
    net_quantity VARCHAR(100),
    manufacturer_details TEXT,
    importer_details TEXT,
    country_of_origin VARCHAR(100),
    consumer_care_details TEXT,
    date_information VARCHAR(150),
    seller_information TEXT,
    product_description TEXT,
    listing_url VARCHAR(1000),
    source VARCHAR(50) NOT NULL DEFAULT 'MANUAL_LISTING_INPUT',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_product_listings_inspection_id ON product_listings (inspection_id);

-- 16. Listing Comparisons (Package vs Online Marketplace Discrepancies)
CREATE TABLE IF NOT EXISTS listing_comparisons (
    id VARCHAR(36) PRIMARY KEY,
    inspection_id VARCHAR(36) NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    listing_id VARCHAR(36) NOT NULL REFERENCES product_listings(id) ON DELETE CASCADE,
    field_name VARCHAR(100) NOT NULL,
    listing_value TEXT,
    package_value TEXT,
    comparison_status VARCHAR(50) NOT NULL,
    difference_explanation TEXT,
    package_ocr_evidence TEXT,
    ocr_confidence FLOAT DEFAULT 0.0,
    source_image_id VARCHAR(36) REFERENCES product_images(id) ON DELETE SET NULL,
    bounding_box_json TEXT,
    applicable_rule_code VARCHAR(100),
    inspector_status VARCHAR(50) NOT NULL DEFAULT 'PENDING_REVIEW',
    inspector_remarks TEXT,
    adjudicated_by VARCHAR(100),
    adjudicated_at TIMESTAMP WITHOUT TIME ZONE,
    listing_provenance VARCHAR(50) NOT NULL DEFAULT 'MANUAL_LISTING_INPUT',
    package_provenance VARCHAR(50) NOT NULL DEFAULT 'PACKAGE_OCR',
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_listing_comparisons_inspection_id ON listing_comparisons (inspection_id);
CREATE INDEX IF NOT EXISTS ix_listing_comparisons_listing_id ON listing_comparisons (listing_id);

-- 17. Stored Files (Crash-resilient Bytea Persistence for Images & Reports)
CREATE TABLE IF NOT EXISTS stored_files (
    storage_key VARCHAR(500) PRIMARY KEY,
    content_type VARCHAR(100) NOT NULL DEFAULT 'image/jpeg',
    file_size INTEGER NOT NULL DEFAULT 0,
    file_data BYTEA NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_stored_files_storage_key ON stored_files (storage_key);
