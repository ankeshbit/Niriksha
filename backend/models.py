import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Enum
)
from sqlalchemy.orm import relationship
from backend.database import Base

def generate_uuid() -> str:
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    officer_id = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    designation = Column(String(100), nullable=False)
    zone = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="INSPECTOR", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    previous_login_at = Column(DateTime, nullable=True)
    password_updated_at = Column(DateTime, default=datetime.utcnow, nullable=True)

    inspections = relationship("Inspection", back_populates="inspector")
    reviews = relationship("InspectorReview", back_populates="officer")


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_number = Column(String(50), unique=True, nullable=False, index=True)
    inspector_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    location = Column(String(255), nullable=False, index=True)
    
    # State Lifecycle: DRAFT -> IMAGES_UPLOADED -> OCR_PROCESSING -> EXTRACTION_COMPLETE
    #  -> RULE_EVALUATION_COMPLETE -> COMPLETED
    status = Column(String(30), default="DRAFT", nullable=False, index=True)
    
    # Final statutory status: NO_POTENTIAL_VIOLATIONS, POTENTIAL_NON_COMPLIANCE, NEEDS_MANUAL_VERIFICATION, INSUFFICIENT_EVIDENCE
    overall_status = Column(String(50), nullable=True, index=True)
    
    # Mode: PHYSICAL, ONLINE_LISTING, HYBRID (PS 26034)
    inspection_type = Column(String(50), default="PHYSICAL", nullable=False)
    
    notes = Column(Text, nullable=True)
    client_draft_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    finalized_at = Column(DateTime, nullable=True)

    inspector = relationship("User", back_populates="inspections")
    product = relationship("Product", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="inspection", cascade="all, delete-orphan")
    declarations = relationship("Declaration", back_populates="inspection", cascade="all, delete-orphan")
    compliance_checks = relationship("ComplianceCheck", back_populates="inspection", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    listing = relationship("ProductListing", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    listing_comparisons = relationship("ListingComparison", back_populates="inspection", cascade="all, delete-orphan")
    ocr_jobs = relationship("OCRJob", back_populates="inspection", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), unique=True, nullable=False)
    product_name = Column(String(255), nullable=False, index=True)
    brand_name = Column(String(255), nullable=True, index=True)
    category = Column(String(100), nullable=False)  # 'Packaged Food', 'Personal Care / Household'
    batch_number = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="product")


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    original_filename = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), default="image/jpeg")
    file_size = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    sequence_order = Column(Integer, default=1)
    view_type = Column(String(50), nullable=False)  # 'front', 'back', 'panel', 'side', 'other'
    blur_score = Column(Float, default=0.0)
    glare_score = Column(Float, default=0.0)
    quality_score = Column(Float, default=1.0)
    quality_status = Column(String(50), default="GOOD")  # 'GOOD', 'WARNING', 'POOR'
    quality_metadata_json = Column(Text, nullable=True)
    processing_status = Column(String(50), default="UPLOADED")  # 'UPLOADED', 'QUALITY_CHECKED'
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="images")
    ocr_results = relationship("OCRResult", back_populates="image", cascade="all, delete-orphan")
    evidence_items = relationship("Evidence", back_populates="image")


class OCRResult(Base):
    """Layer 1: Raw OCR Extraction (Immutable Baseline)"""
    __tablename__ = "ocr_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    image_id = Column(String(36), ForeignKey("product_images.id"), nullable=False)
    raw_text = Column(Text, nullable=False)
    normalized_text = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False)
    bounding_boxes_json = Column(Text, nullable=False)  # Serialized coordinates array
    created_at = Column(DateTime, default=datetime.utcnow)

    image = relationship("ProductImage", back_populates="ocr_results")


class OCRJob(Base):
    """Layer 1: Persistent OCR Job State Machine (Crash & Restart Resilient)"""
    __tablename__ = "ocr_jobs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(30), default="PENDING", nullable=False, index=True)  # PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED
    current_stage = Column(String(50), default="QUEUED", nullable=False)        # QUEUED, INITIALIZING, OCR_FRONT, OCR_BACK, CONSOLIDATING, COMPLETED, FAILED
    progress_percent = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True)
    worker_id = Column(String(100), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=2, nullable=False)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    ocr_summary_json = Column(Text, nullable=True)

    inspection = relationship("Inspection", back_populates="ocr_jobs")


class Declaration(Base):
    """Layer 1: Structured Extracted Declarations (Preserves AI baseline & Officer Corrections)"""
    __tablename__ = "declarations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    field_name = Column(String(100), nullable=False)  # commodity_name, manufacturer_details, net_quantity, mrp, date_of_manufacture_packing, consumer_care_details, country_of_origin
    extracted_value = Column(Text, nullable=True)  # Original immutable OCR text
    normalized_value = Column(Text, nullable=True)
    confidence = Column(Float, default=0.0)  # Original extraction confidence
    bounding_box_json = Column(Text, nullable=True)  # [x1, y1, x2, y2]
    extraction_status = Column(String(50), default="EXTRACTED")  # 'EXTRACTED', 'NOT_FOUND', 'LOW_CONFIDENCE', 'NEEDS_REVIEW', 'NOT_APPLICABLE'
    corrected_value = Column(Text, nullable=True)  # Officer verified correction
    is_applicable = Column(Boolean, default=True)
    verification_status = Column(String(50), default="UNVERIFIED")  # 'UNVERIFIED', 'VERIFIED', 'CORRECTED', 'REQUIRES_REVIEW'
    verified_by = Column(String(100), nullable=True)  # Officer ID
    verified_at = Column(DateTime, nullable=True)
    correction_reason = Column(Text, nullable=True)
    source_image_id = Column(String(36), ForeignKey("product_images.id", ondelete="SET NULL"), nullable=True)
    # PS 26034 Extended Analytical & Legal Validation Attributes
    placement_status = Column(String(50), default="NOT_DETERMINABLE")  # PLACEMENT_COMPLIANT, PLACEMENT_NON_COMPLIANT, PLACEMENT_UNCERTAIN, NOT_DETERMINABLE, NOT_APPLICABLE, MANUAL_VERIFICATION_REQUIRED
    placement_details_json = Column(Text, nullable=True)
    font_size_status = Column(String(50), default="FONT_SIZE_UNDETERMINABLE")  # FONT_SIZE_COMPLIANT, FONT_SIZE_NON_COMPLIANT, FONT_SIZE_UNCERTAIN, FONT_SIZE_UNDETERMINABLE, NOT_APPLICABLE, MANUAL_VERIFICATION_REQUIRED
    font_size_details_json = Column(Text, nullable=True)
    readability_status = Column(String(50), default="NOT_OBSERVABLE")  # READABLE, POOR_READABILITY, UNREADABLE, UNCERTAIN, NOT_OBSERVABLE, MANUAL_VERIFICATION_REQUIRED
    readability_details_json = Column(Text, nullable=True)
    format_status = Column(String(50), default="COMPLIANT")  # COMPLIANT, NON_COMPLIANT, POTENTIAL_MISLEADING, UNCERTAIN, NOT_APPLICABLE
    format_details_json = Column(Text, nullable=True)
    validation_matrix_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="declarations")

    @property
    def effective_value(self) -> Optional[str]:
        """Returns verified correction if present; otherwise original extracted value."""
        if self.corrected_value is not None and self.corrected_value.strip():
            return self.corrected_value.strip()
        return self.extracted_value.strip() if self.extracted_value else None


class RuleVersion(Base):
    """Statutory Legal Metrology Rule Registry with Immutable Version Pinning"""
    __tablename__ = "rule_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    rule_code = Column(String(50), index=True, nullable=False)
    version_number = Column(Integer, default=1, nullable=False)
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)  # 'CATEGORY_A_LEGAL', 'CATEGORY_B_DATA_QUALITY'
    statutory_reference = Column(String(255), nullable=False)  # e.g., 'Rule 6(1)(e), Legal Metrology (PC) Rules, 2011'
    rule_logic_description = Column(Text, nullable=False)
    severity = Column(String(50), default="MAJOR")  # 'CRITICAL', 'MAJOR', 'MINOR', 'INFO'
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    checks = relationship("ComplianceCheck", back_populates="rule_version")


class ComplianceCheck(Base):
    """Layer 2: Deterministic Rule Engine Results (Potential Non-Compliance Findings)"""
    __tablename__ = "compliance_checks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False)
    rule_version_id = Column(String(36), ForeignKey("rule_versions.id"), nullable=False)
    rule_code = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    severity = Column(String(50), default="MAJOR")
    
    # Result States: PASS, POTENTIAL_NON_COMPLIANCE, INSUFFICIENT_EVIDENCE, NOT_APPLICABLE
    result_state = Column(String(50), nullable=False)
    extracted_value = Column(Text, nullable=True)  # Snapshot of effective value evaluated
    explanation = Column(Text, nullable=False)
    
    # Human Adjudication Lifecycle: PENDING, CONFIRMED, DISMISSED, NEEDS_MORE_EVIDENCE
    adjudication_status = Column(String(50), default="PENDING")
    adjudication_notes = Column(Text, nullable=True)
    adjudicated_by = Column(String(100), nullable=True)
    adjudicated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="compliance_checks")
    rule_version = relationship("RuleVersion", back_populates="checks")
    evidence = relationship("Evidence", back_populates="check", cascade="all, delete-orphan")
    reviews = relationship("InspectorReview", back_populates="check", cascade="all, delete-orphan")


class Evidence(Base):
    """Layer 2: Photographic Evidence & Bounding Boxes Traceable to Label Regions"""
    __tablename__ = "evidence"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    check_id = Column(String(36), ForeignKey("compliance_checks.id"), nullable=False)
    image_id = Column(String(36), ForeignKey("product_images.id", ondelete="SET NULL"), nullable=True)
    bounding_box_json = Column(Text, nullable=True)  # [x1, y1, x2, y2]
    crop_image_path = Column(String(500), nullable=True)
    highlight_text = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    check = relationship("ComplianceCheck", back_populates="evidence")
    image = relationship("ProductImage", back_populates="evidence_items")


class InspectorReview(Base):
    """Layer 3: Human-in-the-Loop Adjudication Log (Immutable Audit Trail)"""
    __tablename__ = "inspector_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    check_id = Column(String(36), ForeignKey("compliance_checks.id"), nullable=False)
    officer_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # Actions: CONFIRMED, DISMISSED, NOT_APPLICABLE, NEEDS_MORE_EVIDENCE
    action = Column(String(50), nullable=False)
    remarks = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, default=datetime.utcnow)

    check = relationship("ComplianceCheck", back_populates="reviews")
    officer = relationship("User", back_populates="reviews")


class AuditLog(Base):
    """Immutable System Audit Log for Legal Enforcement Integrity"""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id", ondelete="SET NULL"), nullable=True)
    actor_id = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)  # e.g. OCR_RUN, DECLARATION_VERIFIED, FINDING_ADJUDICATED
    entity_type = Column(String(100), nullable=False)  # 'inspection', 'declaration', 'compliance_check'
    entity_id = Column(String(36), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Report(Base):
    """Layer 4: Official Statutory Compliance Inspection Report"""
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), unique=True, nullable=False)
    report_version = Column(Integer, default=1, nullable=False)
    pdf_path = Column(String(500), nullable=False)
    docx_path = Column(String(500), nullable=True)
    pdf_hash = Column(String(64), nullable=True)
    legal_safety_statement = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="report")

    @property
    def download_url(self) -> str:
        return f"/api/inspections/{self.inspection_id}/report/pdf"

    @property
    def docx_download_url(self) -> str:
        return f"/api/inspections/{self.inspection_id}/report/docx"


class InspectionNumberCounter(Base):
    """AUDIT-CONCUR-01: Atomic sequence counter for year-based inspection numbers."""
    __tablename__ = "inspection_number_counters"

    year = Column(Integer, primary_key=True)
    next_number = Column(Integer, nullable=False, default=1)


class ProductListing(Base):
    """Product Information / E-Commerce Online Listing Details (PS 26034)"""
    __tablename__ = "product_listings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), unique=True, nullable=False, index=True)
    product_name = Column(String(255), nullable=True)
    brand_name = Column(String(255), nullable=True)
    mrp = Column(String(100), nullable=True)
    net_quantity = Column(String(100), nullable=True)
    manufacturer_details = Column(Text, nullable=True)
    importer_details = Column(Text, nullable=True)
    country_of_origin = Column(String(100), nullable=True)
    consumer_care_details = Column(Text, nullable=True)
    date_information = Column(String(150), nullable=True)
    seller_information = Column(Text, nullable=True)
    product_description = Column(Text, nullable=True)
    listing_url = Column(String(1000), nullable=True)
    source = Column(String(50), default="MANUAL_LISTING_INPUT", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="listing")
    comparisons = relationship("ListingComparison", back_populates="listing", cascade="all, delete-orphan")


class ListingComparison(Base):
    """Field-by-Field Evidence Discrepancy Comparison between Online Listing and Package (PS 26034)"""
    __tablename__ = "listing_comparisons"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=False, index=True)
    listing_id = Column(String(36), ForeignKey("product_listings.id"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)  # 'mrp', 'net_quantity', 'product_name', 'brand_name', 'manufacturer_details', 'country_of_origin', 'consumer_care_details', etc.
    listing_value = Column(Text, nullable=True)
    package_value = Column(Text, nullable=True)
    comparison_status = Column(String(50), nullable=False)  # 'MATCH', 'MISMATCH', 'MISSING_ON_LISTING', 'MISSING_ON_PACKAGE', 'UNCERTAIN'
    difference_explanation = Column(Text, nullable=True)
    package_ocr_evidence = Column(Text, nullable=True)
    ocr_confidence = Column(Float, default=0.0)
    source_image_id = Column(String(36), ForeignKey("product_images.id", ondelete="SET NULL"), nullable=True)
    bounding_box_json = Column(Text, nullable=True)
    applicable_rule_code = Column(String(100), nullable=True)  # e.g. PCR_RULE_18_2A_ONLINE_PRICE_OVERCHARGING, PCR_RULE_06_10_ECOMMERCE_DECLARATION
    inspector_status = Column(String(50), default="PENDING_REVIEW", nullable=False)  # 'PENDING_REVIEW', 'VERIFIED_MATCH', 'CONFIRMED_DISCREPANCY', 'DISMISSED_DISCREPANCY'
    inspector_remarks = Column(Text, nullable=True)
    adjudicated_by = Column(String(100), nullable=True)
    adjudicated_at = Column(DateTime, nullable=True)
    listing_provenance = Column(String(50), default="MANUAL_LISTING_INPUT", nullable=False)
    package_provenance = Column(String(50), default="PACKAGE_OCR", nullable=False)  # 'PACKAGE_OCR', 'INSPECTOR_CORRECTED', 'NOT_APPLICABLE'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="listing_comparisons")
    listing = relationship("ProductListing", back_populates="comparisons")
    source_image = relationship("ProductImage")
