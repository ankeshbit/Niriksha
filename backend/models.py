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
    designation = Column(String(100), nullable=False)
    zone = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="INSPECTOR", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    inspections = relationship("Inspection", back_populates="inspector")
    reviews = relationship("InspectorReview", back_populates="officer")


class Inspection(Base):
    __tablename__ = "inspections"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_number = Column(String(50), unique=True, nullable=False, index=True)
    inspector_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    location = Column(String(255), nullable=False)
    
    # State Lifecycle: DRAFT -> IMAGES_UPLOADED -> ANALYZING -> ANALYSIS_COMPLETE -> NEEDS_REVIEW -> FINALIZED
    status = Column(String(30), default="DRAFT", nullable=False)
    
    # Final statutory status: NO_POTENTIAL_VIOLATIONS, POTENTIAL_NON_COMPLIANCE, NEEDS_MANUAL_VERIFICATION, INSUFFICIENT_EVIDENCE
    overall_status = Column(String(50), nullable=True)
    
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finalized_at = Column(DateTime, nullable=True)

    inspector = relationship("User", back_populates="inspections")
    product = relationship("Product", back_populates="inspection", uselist=False, cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="inspection", cascade="all, delete-orphan")
    declarations = relationship("Declaration", back_populates="inspection", cascade="all, delete-orphan")
    compliance_checks = relationship("ComplianceCheck", back_populates="inspection", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="inspection", uselist=False, cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    inspection_id = Column(String(36), ForeignKey("inspections.id"), unique=True, nullable=False)
    product_name = Column(String(255), nullable=False)
    brand_name = Column(String(255), nullable=True)
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
    confidence = Column(Float, nullable=False)
    bounding_boxes_json = Column(Text, nullable=False)  # Serialized coordinates array
    created_at = Column(DateTime, default=datetime.utcnow)

    image = relationship("ProductImage", back_populates="ocr_results")


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
    source_image_id = Column(String(36), ForeignKey("product_images.id"), nullable=True)
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
    image_id = Column(String(36), ForeignKey("product_images.id"), nullable=True)
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
    inspection_id = Column(String(36), ForeignKey("inspections.id"), nullable=True)
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
    legal_safety_statement = Column(Text, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    inspection = relationship("Inspection", back_populates="report")
