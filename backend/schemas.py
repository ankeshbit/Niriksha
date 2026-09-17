from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Literal, Optional, List, Dict, Any
from datetime import datetime

class HealthCheckResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    database: str
    version: str = "1.0.0"
    database_backend: Optional[str] = None
    database_host: Optional[str] = None
    database_driver: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    officer_id: str
    full_name: str
    designation: str
    zone: str
    email: Optional[str] = None
    phone: Optional[str] = None
    role: str = "INSPECTOR"
    last_login_at: Optional[datetime] = None
    previous_login_at: Optional[datetime] = None

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
    last_login_at: Optional[datetime] = None
    previous_login_at: Optional[datetime] = None

class CreateUserRequest(BaseModel):
    officer_id: str = Field(..., description="Unique badge/officer identifier")
    full_name: str = Field(..., description="Officer full legal name")
    password: str = Field(..., min_length=6, description="Initial temporary/permanent password")
    designation: str = Field(..., description="Official designation, e.g. Legal Metrology Officer")
    zone: str = Field(..., description="Jurisdictional zone, e.g. Northern Zone")
    role: Literal["INSPECTOR", "SUPERVISOR", "ADMIN"] = Field("INSPECTOR", description="System RBAC role")
    email: Optional[str] = Field(None, description="Official email address")
    phone: Optional[str] = Field(None, description="Official contact phone number")

class UpdateProfileRequest(BaseModel):
    email: Optional[str] = Field(None, description="Inspector email address")
    phone: Optional[str] = Field(None, description="Inspector phone number")

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password for verification")
    new_password: str = Field(..., min_length=6, description="New secure password")

# Valid Legal Metrology commodity categories (PCR 2011 scope)
INSPECTION_CATEGORIES = Literal["Packaged Food", "Household/Personal Care"]

class CreateInspectionRequest(BaseModel):
    product_name: str = Field(..., description="Name of the packaged commodity")
    category: INSPECTION_CATEGORIES = Field(..., description="Product category: 'Packaged Food' or 'Household/Personal Care'")
    brand_name: Optional[str] = Field(None, description="Brand name")
    location: str = Field(..., description="Inspection location")
    batch_number: Optional[str] = Field(None, description="Batch / Lot number")
    notes: Optional[str] = Field(None, description="Additional inspection notes")
    client_draft_id: Optional[str] = Field(None, description="Client-generated local draft UUID for idempotent sync")
    inspection_type: Optional[str] = Field("PHYSICAL", description="Analysis mode: PHYSICAL, ONLINE_LISTING, or HYBRID")

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    batch_number: Optional[str] = None

class ImageQualityDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
    engine: Optional[str] = "BlurDetection2"
    status: Optional[str] = None
    quality_decision: Optional[str] = None
    image_id: Optional[str] = None
    timestamp: Optional[str] = None

class QualityCheckResponse(BaseModel):
    status: str  # "ACCEPTABLE" | "BLURRY"
    quality_decision: str  # "QUALITY_ACCEPTED" | "QUALITY_REJECTED"
    blur_score: float
    engine: str = "BlurDetection2"
    image_id: Optional[str] = None
    timestamp: str
    reason: str
    quality_status: str  # "GOOD" | "WARNING" | "POOR"
    quality_score: float
    details: Optional[ImageQualityDetails] = None

class BarcodeItemResponse(BaseModel):
    """Structured Barcode / QR Code Evidence Item."""
    type: str                                    # e.g., 'EAN13', 'QRCODE', 'CODE128', 'UPCA'
    value: str                                   # Decoded digits or string
    confidence: Optional[float] = None           # Strict invariant: null unless decoder provides one
    source_image_id: Optional[str] = None        # ID of image where detected
    source_image_path: Optional[str] = None
    bbox: Optional[List[int]] = None             # [x1, y1, x2, y2]
    timestamp: Optional[str] = None
    decoder: str = "pyzbar"                      # 'pyzbar' or 'opencv'
    ocr_corroboration: Optional[str] = None      # 'CORROBORATING', 'EVIDENCE_CONFLICT', 'NO_OCR_BARCODE'
    conflicting_ocr_value: Optional[str] = None

class BarcodeInspectionSummaryResponse(BaseModel):
    """Consolidated Barcode Evidence across an inspection."""
    detected: bool = False
    items: List[BarcodeItemResponse] = []
    has_conflict: bool = False
    conflict_description: Optional[str] = None
    consolidated_value: Optional[str] = None
    barcode_type: Optional[str] = None

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
    barcodes: Optional[List[BarcodeItemResponse]] = None
    created_at: datetime

class OCRTextBoxResponse(BaseModel):
    text: str
    confidence: float
    bbox: List[int]
    sequence: int
    image_id: Optional[str] = None
    engine: Optional[str] = None
    timestamp: Optional[str] = None

class OCRResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    image_id: str
    raw_text: str
    normalized_text: Optional[str] = None
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
    extraction_method: Optional[str] = "AI/OCR"
    corrected_value: Optional[str] = None
    is_applicable: bool = True
    verification_status: str = "UNVERIFIED"
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    correction_reason: Optional[str] = None
    source_image_id: Optional[str] = None
    has_conflict: bool = False
    conflicts: Optional[List[Dict[str, Any]]] = None
    source_images: Optional[List[str]] = None
    raw_text: Optional[str] = None
    layout_region: Optional[str] = None
    layout_bbox: Optional[List[int]] = None
    # PS 26034 Extended Analytical & Legal Validation Attributes
    placement_status: Optional[str] = "NOT_DETERMINABLE"
    placement_details: Optional[Dict[str, Any]] = None
    font_size_status: Optional[str] = "FONT_SIZE_UNDETERMINABLE"
    font_size_details: Optional[Dict[str, Any]] = None
    readability_status: Optional[str] = "NOT_OBSERVABLE"
    readability_details: Optional[Dict[str, Any]] = None
    format_status: Optional[str] = "COMPLIANT"
    format_details: Optional[Dict[str, Any]] = None
    validation_matrix: Optional[Dict[str, Any]] = None
    created_at: datetime

class DeclarationMatrixRowSchema(BaseModel):
    field_name: str
    field_label: str
    is_present: bool
    is_correct: str
    readability_status: str
    placement_status: str
    font_size_status: str
    format_status: str
    overall_status: str
    extracted_value: Optional[str] = None
    effective_value: Optional[str] = None
    confidence: float = 0.0
    bounding_box: Optional[List[int]] = None
    source_image_id: Optional[str] = None
    view_type: Optional[str] = None
    statutory_reference: Optional[str] = None
    findings: List[str] = []
    explanation: Optional[str] = None

class DeclarationValidationMatrixResponse(BaseModel):
    inspection_id: str
    rows: List[DeclarationMatrixRowSchema]
    total_mandatory: int
    compliant_count: int
    potential_violation_count: int
    manual_verification_count: int
    generated_at: str

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
    category: Optional[str] = "CATEGORY_A_LEGAL"
    status: Optional[str] = None
    adjudication: Optional[str] = None
    description: Optional[str] = None
    is_pending_adjudication: bool = False

class ComplianceSummaryResponse(BaseModel):
    inspection_id: str
    inspection_number: Optional[str] = None
    overall_status: str
    evaluation_completed: bool = False
    # Semantically clear bucket names (mutually exclusive, cover all rows)
    compliant_checks: int = 0           # PASS + NOT_APPLICABLE + DISMISSED/CORRECTED
    no_potential_violations: int = 0     # backward-compat alias for compliant_checks
    potential_non_compliance: int = 0
    needs_manual_verification: int = 0
    warnings: int = 0                    # CATEGORY_B_DATA_QUALITY only when not already in another bucket
    pending_adjudication_count: int = 0  # Non-PASS checks awaiting inspector adjudication
    total_findings: int = 0              # total ComplianceCheck rows for this inspection
    findings: List[FindingResponse] = []
    total_mandatory: int = 7
    mandatory_detected: int = 0
    mandatory_missing: int = 0
    mandatory_correct: int = 0
    mandatory_uncertain: int = 0
    placement_compliant: int = 0
    placement_uncertain: int = 0
    placement_non_compliant: int = 0
    readability_good: int = 0
    readability_uncertain: int = 0
    readability_poor: int = 0
    font_size_compliant: int = 0
    font_size_non_compliant: int = 0
    font_size_undeterminable: int = 0
    listing_comparison_matched: int = 0
    listing_comparison_mismatched: int = 0
    listing_comparison_uncertain: int = 0
    potential_violations_count: int = 0
    manual_verification_count: int = 0
    timestamp: str

class UpdateDeclarationRequest(BaseModel):
    corrected_value: Optional[str] = None
    verification_status: Optional[str] = "VERIFIED"
    correction_reason: Optional[str] = None
    is_applicable: Optional[bool] = None

class AdjudicateFindingRequest(BaseModel):
    action: Optional[str] = Field(None, description="Action: CONFIRMED, DISMISSED, NEEDS_MORE_EVIDENCE, NOT_APPLICABLE, CORRECTED")
    adjudication_action: Optional[str] = Field(None, description="Alias for action")
    notes: Optional[str] = Field(None, description="Inspector justification or findings remarks")
    corrected_value: Optional[str] = Field(None, description="Inspector-provided corrected value (for CORRECTED action)")

    @model_validator(mode="after")
    def normalize_action(self):
        raw = (self.action or self.adjudication_action or "").strip().upper()
        mapping = {
            "CONFIRM_COMPLIANT": "DISMISSED",  # If inspector confirms compliant, finding is dismissed
            "CONFIRM": "CONFIRMED",
            "DISMISS": "DISMISSED",
            "REJECT": "DISMISSED",
            "NEED_MORE_EVIDENCE": "NEEDS_MORE_EVIDENCE",
            "MORE_EVIDENCE": "NEEDS_MORE_EVIDENCE",
            "NA": "NOT_APPLICABLE",
            "CORRECT": "CORRECTED"
        }
        self.action = mapping.get(raw, raw)
        return self

class RunOCRResponse(BaseModel):
    inspection_id: str
    status: str
    total_images_processed: int
    declarations_count: int
    ocr_results: List[OCRResultResponse]
    declarations: List[DeclarationResponse]
    conflicts: List[Dict[str, Any]] = []
    barcodes: Optional[BarcodeInspectionSummaryResponse] = None

class EvaluateInspectionResponse(BaseModel):
    inspection_id: str
    status: str
    overall_status: str
    total_rules_evaluated: int
    passed_count: int
    potential_non_compliance_count: int
    insufficient_evidence_count: int
    conflicts: List[Dict[str, Any]] = []
    physical_quantity_disclaimer: Optional[str] = (
        "Physical net quantity requires appropriate physical verification/testing "
        "and cannot be conclusively determined from package photographs alone."
    )
    findings: List[FindingResponse]

class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    report_version: int
    pdf_path: str
    download_url: str
    docx_path: Optional[str] = None
    docx_download_url: Optional[str] = None
    legal_safety_statement: str
    generated_at: datetime
    inspection_number: Optional[str] = None
    product_name: Optional[str] = None
    location: Optional[str] = None
    overall_status: Optional[str] = None
    pdf_hash: Optional[str] = None

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
    client_draft_id: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None

class InspectionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_number: str
    inspector_id: str
    location: str
    status: str
    inspection_type: str = "PHYSICAL"
    overall_status: Optional[str] = None
    notes: Optional[str] = None
    client_draft_id: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None
    product: Optional[ProductResponse] = None
    images: List[ProductImageResponse] = []
    declarations: List[DeclarationResponse] = []
    compliance_checks: List[FindingResponse] = []
    report: Optional[ReportResponse] = None
    barcodes: Optional[BarcodeInspectionSummaryResponse] = None
    listing: Optional[Any] = None

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

class BlockingImage(BaseModel):
    image_id: str
    view_type: str
    quality_status: str
    reason: str

class BlockingReason(BaseModel):
    type: str  # MISSING_IMAGE_EVIDENCE, IMAGE_QUALITY, CORRUPTED_IMAGE, OCR_INCOMPLETE, RULE_EVALUATION_INCOMPLETE, INSUFFICIENT_EVIDENCE, NEEDS_MORE_EVIDENCE
    image_id: Optional[str] = None
    rule_code: Optional[str] = None
    reason: str

class ReportEligibilityResponse(BaseModel):
    can_generate_report: bool
    status: str  # 'READY' | 'REPORT_BLOCKED'
    reason: Optional[str] = None
    message: str
    blocking_images: List[BlockingImage] = []
    blocking_reasons: List[BlockingReason] = []

# ----------------- Enforcement Dashboard Schemas -----------------

class DashboardKPISummaryResponse(BaseModel):
    """Dynamic Legal Metrology Enforcement KPIs calculated from live DB."""
    total_inspections: int
    completed_inspections: int
    pending_verification: int
    potential_non_compliance: int
    compliant_inspections: int
    reports_generated: int
    manual_verification_required: int

class DashboardInspectionListItem(BaseModel):
    """Detailed inspection item for dashboard registry."""
    id: str
    inspection_number: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    inspector_id: str
    inspector_name: str
    location: str
    created_at: datetime
    status: str
    overall_status: Optional[str] = None
    has_report: bool = False
    report_version: Optional[int] = None
    pending_actions_count: int = 0

class DashboardInspectionsListResponse(BaseModel):
    """Paginated, filterable inspections list for dashboard."""
    total: int
    items: List[DashboardInspectionListItem]
    limit: int
    offset: int

class PendingActionItem(BaseModel):
    """Specific inspection action requiring officer verification or adjudication."""
    inspection_id: str
    inspection_number: str
    product_name: str
    action_type: str  # OCR_UNCERTAINTY, MISSING_DECLARATION, CONFLICTING_DECLARATION, POTENTIAL_NON_COMPLIANCE, PENDING_ADJUDICATION
    title: str
    description: str
    severity: str  # CRITICAL, WARNING, INFO
    created_at: datetime

class DashboardPendingActionsResponse(BaseModel):
    """Actionable queue of pending enforcement tasks."""
    total: int
    items: List[PendingActionItem]

class ComplianceAnalyticsResponse(BaseModel):
    """Compliance rates and breakdown analytics."""
    has_sufficient_data: bool
    total_evaluated: int
    compliance_rate: float
    potential_non_compliance_rate: float
    manual_verification_rate: float
    findings_by_field: Dict[str, int]
    findings_by_rule: Dict[str, int]
    findings_by_category: Dict[str, int]
    inspections_over_time: List[Dict[str, Any]]

class EnforcementActivityResponse(BaseModel):
    """Jurisdictional and inspector enforcement activity."""
    inspections_by_location: List[Dict[str, Any]]
    inspections_by_inspector: List[Dict[str, Any]]
    non_compliance_by_location: List[Dict[str, Any]]
    top_flagged_rules: List[Dict[str, Any]]
    repeatedly_inspected_products: List[Dict[str, Any]]


# ===========================================================================
# Repository & Search Schemas (PS 26034)
# ===========================================================================

class RepositoryInspectionItem(BaseModel):
    """Comprehensive inspection record for the Inspection Repository & Global Search."""
    id: str
    inspection_number: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    manufacturer: Optional[str] = None
    batch_number: Optional[str] = None
    location: str
    inspector_id: str
    inspector_name: str
    status: str
    overall_status: Optional[str] = None
    findings_count: int = 0
    non_compliant_count: int = 0
    has_report: bool = False
    report_id: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None


class RepositoryInspectionsResponse(BaseModel):
    """Paginated search response for the Inspection Repository."""
    items: List[RepositoryInspectionItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class RepositoryProductItem(BaseModel):
    """Aggregated product entity for the Product Repository."""
    product_key: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    manufacturer: Optional[str] = None
    inspection_count: int
    last_inspection_date: Optional[datetime] = None
    latest_compliance_status: Optional[str] = None
    latest_inspection_id: Optional[str] = None


class RepositoryProductsResponse(BaseModel):
    """Paginated response for the Product Repository catalogue."""
    items: List[RepositoryProductItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class RepositoryReportItem(BaseModel):
    """Statutory report record with search metadata and retrieval links."""
    id: str
    inspection_id: str
    inspection_number: str
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    category: Optional[str] = None
    report_version: int
    download_url: str
    inspector_id: Optional[str] = None
    inspector_name: Optional[str] = None
    generated_at: datetime
    legal_safety_statement: str
    overall_status: Optional[str] = None
    pdf_hash: Optional[str] = None


class RepositoryReportsResponse(BaseModel):
    """Paginated search response for the Statutory Reports Archive."""
    items: List[RepositoryReportItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserListItemResponse(BaseModel):
    """Officer record for admin user management."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    officer_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: str
    zone: str
    role: str
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class UpdateUserRoleRequest(BaseModel):
    """Request payload to change an officer's role."""
    role: Literal["INSPECTOR", "SUPERVISOR", "ADMIN"] = Field(
        ...,
        description="New role to assign to the officer (INSPECTOR, SUPERVISOR, ADMIN)"
    )


# ----------------- Product Information & Online Listing Schemas (PS 26034) -----------------

class ProductListingCreateRequest(BaseModel):
    product_name: Optional[str] = Field(None, description="Listing product name")
    brand_name: Optional[str] = Field(None, description="Listing brand name")
    mrp: Optional[str] = Field(None, description="Listing MRP / retail price (e.g. ₹55.00)")
    net_quantity: Optional[str] = Field(None, description="Listing net quantity (e.g. 500 g)")
    manufacturer_details: Optional[str] = Field(None, description="Manufacturer/Packer name and address")
    importer_details: Optional[str] = Field(None, description="Importer name and address")
    country_of_origin: Optional[str] = Field(None, description="Declared country of origin")
    consumer_care_details: Optional[str] = Field(None, description="Consumer care contact details")
    date_information: Optional[str] = Field(None, description="Date information if declared")
    seller_information: Optional[str] = Field(None, description="Seller / vendor entity name")
    product_description: Optional[str] = Field(None, description="Product description on listing")
    listing_url: Optional[str] = Field(None, description="Listing reference URL or identifier")


class ProductListingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    mrp: Optional[str] = None
    net_quantity: Optional[str] = None
    manufacturer_details: Optional[str] = None
    importer_details: Optional[str] = None
    country_of_origin: Optional[str] = None
    consumer_care_details: Optional[str] = None
    date_information: Optional[str] = None
    seller_information: Optional[str] = None
    product_description: Optional[str] = None
    listing_url: Optional[str] = None
    source: str = "MANUAL_LISTING_INPUT"
    created_at: datetime
    updated_at: Optional[datetime] = None


class ListingComparisonItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    inspection_id: str
    listing_id: str
    field_name: str
    listing_value: Optional[str] = None
    package_value: Optional[str] = None
    comparison_status: str  # 'MATCH', 'MISMATCH', 'MISSING_ON_LISTING', 'MISSING_ON_PACKAGE', 'UNCERTAIN'
    difference_explanation: Optional[str] = None
    package_ocr_evidence: Optional[str] = None
    ocr_confidence: float = 0.0
    source_image_id: Optional[str] = None
    bounding_box_json: Optional[str] = None
    applicable_rule_code: Optional[str] = None
    inspector_status: str = "PENDING_REVIEW"
    inspector_remarks: Optional[str] = None
    adjudicated_by: Optional[str] = None
    adjudicated_at: Optional[datetime] = None
    listing_provenance: str = "MANUAL_LISTING_INPUT"
    package_provenance: str = "PACKAGE_OCR"
    created_at: datetime
    updated_at: Optional[datetime] = None


class ListingComparisonSummaryResponse(BaseModel):
    inspection_id: str
    inspection_number: str
    total_fields_compared: int
    matches_count: int
    mismatches_count: int
    missing_on_listing_count: int
    missing_on_package_count: int
    uncertain_count: int
    has_discrepancies: bool
    listing: Optional[ProductListingResponse] = None
    comparisons: List[ListingComparisonItemResponse] = []


class AdjudicateComparisonRequest(BaseModel):
    status: Literal["VERIFIED_MATCH", "CONFIRMED_DISCREPANCY", "DISMISSED_DISCREPANCY"] = Field(
        ...,
        description="Adjudication outcome: VERIFIED_MATCH, CONFIRMED_DISCREPANCY, or DISMISSED_DISCREPANCY"
    )
    remarks: Optional[str] = Field(None, description="Inspector justification notes")


# ----------------- Supervisor Role & Management Schemas -----------------

class DeleteInspectionRequest(BaseModel):
    """Payload requiring explicit confirmation of inspection number before destructive deletion."""
    confirmation_inspection_number: str = Field(
        ...,
        description="Must match the exact inspection number (e.g. LM-2026-00023) to confirm deletion."
    )
    reason: Optional[str] = Field(None, description="Management justification or audit reason for deletion.")


class DeleteInspectionResponse(BaseModel):
    success: bool = True
    message: str
    inspection_id: str
    inspection_number: str


class DeleteReportResponse(BaseModel):
    success: bool = True
    message: str
    inspection_id: str
    report_id: Optional[str] = None


class SupervisorDashboardResponse(BaseModel):
    """Real-time management metrics aggregated strictly from Neon PostgreSQL."""
    total_inspections: int
    today_inspections: int
    completed_inspections: int
    pending_inspections: int
    manual_verification_required: int
    potential_non_compliance: int
    reports_generated: int
    active_inspectors_count: int
    recent_submissions: List[RecentInspectionItem] = []
    inspections_by_inspector: List[Dict[str, Any]] = []
    inspections_by_category: Dict[str, int] = {}
    inspections_by_status: Dict[str, int] = {}
    inspections_by_date: List[Dict[str, Any]] = []
    inspections_requiring_attention: List[Dict[str, Any]] = []


class SupervisorInspectorSummary(BaseModel):
    inspector_id: str
    officer_id: str
    full_name: str
    designation: str
    zone: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_inspections: int
    completed_inspections: int
    pending_inspections: int
    potential_non_compliance: int
    manual_verification_required: int
    reports_generated: int
    last_active: Optional[datetime] = None


class SupervisorInspectorsListResponse(BaseModel):
    inspectors: List[SupervisorInspectorSummary] = []
    total_count: int = 0


class SupervisorInspectionSummaryItem(BaseModel):
    """Lightweight summary model for Supervisor repository listing (omits heavy OCR/declarations)."""
    id: str
    inspection_number: str
    product_name: str
    brand_name: Optional[str] = None
    category: str
    location: str
    inspector_id: Optional[str] = None
    inspector_name: Optional[str] = None
    status: str
    overall_status: Optional[str] = None
    created_at: datetime
    finalized_at: Optional[datetime] = None
    has_report: bool = False
    report_id: Optional[str] = None
    findings_count: int = 0
    non_compliant_count: int = 0


class SupervisorInspectionsListResponse(BaseModel):
    """Paginated response for Supervisor All Inspections repository."""
    items: List[SupervisorInspectionSummaryItem] = []
    total_count: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1



