from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class HealthCheckResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    database: str
    version: str = "1.0.0"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    officer_id: str
    full_name: str
    designation: str
    zone: str
    email: Optional[str] = None
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    officer_id: str = Field(..., description="Officer ID / Username")
    password: str = Field(..., description="Password")

class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    officer_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: str
    zone: str
    role: str

class UpdateProfileRequest(BaseModel):
    email: Optional[str] = Field(None, description="Inspector email address")
    phone: Optional[str] = Field(None, description="Inspector phone number")

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=6, description="New secure password")

class CreateInspectionRequest(BaseModel):
    product_name: str = Field(..., description="Name of the packaged commodity")
    category: str = Field(..., description="Product category: 'Packaged Food' or 'Household/Personal Care'")
    brand_name: Optional[str] = Field(None, description="Brand name")
    location: str = Field(..., description="Inspection location")
    batch_number: Optional[str] = Field(None, description="Batch / Lot number")
    notes: Optional[str] = Field(None, description="Additional inspection notes")
    client_draft_id: Optional[str] = Field(None, description="Client-generated local draft UUID for idempotent sync")

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    batch_number: Optional[str] = None

class ImageQualityDetails(BaseModel):
    quality_status: str
    quality_score: float
    blur_score: float
    blur_ok: bool
    brightness_score: float
    brightness_ok: bool
    contrast_score: float
    contrast_ok: bool
    resolution_ok: bool
    width: int
    height: int
    warnings: List[str]
    recommendation: str

class ProductImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    original_filename: Optional[str] = None
    file_path: str
    view_type: str
    mime_type: str
    file_size: int
    width: int
    height: int
    sequence_order: int
    quality_status: str
    quality_score: float
    quality_details: Optional[ImageQualityDetails] = None
    created_at: datetime

class OCRTextBoxResponse(BaseModel):
    text: str
    confidence: float
    bbox: List[int]
    sequence: int
    image_id: Optional[str] = None

class OCRResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    image_id: str
    raw_text: str
    confidence: float
    bounding_boxes: List[OCRTextBoxResponse] = []
    created_at: datetime

class DeclarationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    field_name: str
    extracted_value: Optional[str] = None
    normalized_value: Optional[str] = None
    effective_value: Optional[str] = None
    confidence: float = 0.0
    bounding_box: Optional[List[int]] = None
    extraction_status: str = "EXTRACTED"
    corrected_value: Optional[str] = None
    is_applicable: bool = True
    verification_status: str = "UNVERIFIED"
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    correction_reason: Optional[str] = None
    source_image_id: Optional[str] = None
    created_at: datetime

class UpdateDeclarationRequest(BaseModel):
    corrected_value: Optional[str] = None
    verification_status: Optional[str] = "VERIFIED"
    correction_reason: Optional[str] = None
    is_applicable: Optional[bool] = None

class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    check_id: str
    image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None
    crop_image_path: Optional[str] = None
    highlight_text: str
    reason: Optional[str] = None
    created_at: datetime

class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    rule_version_id: str
    rule_code: str
    rule_version_number: Optional[int] = None
    statutory_reference: Optional[str] = None
    title: str
    severity: str
    result_state: str
    extracted_value: Optional[str] = None
    explanation: str
    adjudication_status: str = "PENDING"  # PENDING, CONFIRMED, DISMISSED, NEEDS_MORE_EVIDENCE, NOT_APPLICABLE, CORRECTED
    adjudication_notes: Optional[str] = None
    adjudicated_by: Optional[str] = None
    adjudicated_at: Optional[datetime] = None
    created_at: datetime
    evidence_items: List[EvidenceResponse] = []

class AdjudicateFindingRequest(BaseModel):
    action: str = Field(..., description="Action: CONFIRMED, DISMISSED, NEEDS_MORE_EVIDENCE, NOT_APPLICABLE, CORRECTED")
    notes: Optional[str] = Field(None, description="Inspector justification or findings remarks")
    corrected_value: Optional[str] = Field(None, description="Inspector-provided corrected value (for CORRECTED action)")

class RunOCRResponse(BaseModel):
    inspection_id: str
    status: str
    total_images_processed: int
    declarations_count: int
    ocr_results: List[OCRResultResponse]
    declarations: List[DeclarationResponse]

class EvaluateInspectionResponse(BaseModel):
    inspection_id: str
    status: str
    overall_status: str
    total_rules_evaluated: int
    passed_count: int
    potential_non_compliance_count: int
    insufficient_evidence_count: int
    findings: List[FindingResponse]

class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    report_version: int
    pdf_path: str
    download_url: str
    legal_safety_statement: str
    generated_at: datetime
    inspection_number: Optional[str] = None
    product_name: Optional[str] = None
    location: Optional[str] = None
    overall_status: Optional[str] = None

class FinalizeInspectionRequest(BaseModel):
    final_status: Optional[str] = None
    officer_notes: Optional[str] = None

class FinalizeInspectionResponse(BaseModel):
    inspection_id: str
    inspection_number: str
    status: str
    overall_status: str
    finalized_at: datetime
    report: ReportResponse

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: Optional[str] = None
    actor_id: str
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    details: Optional[str] = None
    created_at: datetime

class InspectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_number: str
    inspector_id: str
    location: str
    status: str
    overall_status: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None

class InspectionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_number: str
    inspector_id: str
    location: str
    status: str
    overall_status: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None
    product: Optional[ProductResponse] = None
    images: List[ProductImageResponse] = []
    declarations: List[DeclarationResponse] = []
    compliance_checks: List[FindingResponse] = []
    report: Optional[ReportResponse] = None

class RecentInspectionItem(BaseModel):
    id: str
    inspection_number: str
    product_name: str
    location: str
    status: str
    overall_status: Optional[str] = None
    created_at: datetime

class DashboardStatsResponse(BaseModel):
    total_inspections: int
    needs_manual_verification: int
    verified_inspections: int
    potential_non_compliance: int
    recent_inspections: List[RecentInspectionItem]
