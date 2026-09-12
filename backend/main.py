import os
import sys
import re
import json
import uuid
import time
import shutil
import hashlib
import threading
import logging
from pathlib import Path

logger = logging.getLogger("backend.main")

# Ensure project root is in sys.path regardless of whether uvicorn is launched from root or backend/
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from typing import List, Optional
from datetime import datetime
from PIL import Image

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    Query,
    UploadFile,
    File,
    Form,
    Body
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import text, or_, and_, func, distinct, case, desc, asc
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.database import get_db, engine, Base, get_database_backend_info
from backend.models import (
    User,
    RuleVersion,
    Inspection,
    Product,
    ProductImage,
    OCRResult,
    Declaration,
    ComplianceCheck,
    Evidence,
    InspectorReview,
    AuditLog,
    Report,
    InspectionNumberCounter,
    ProductListing,
    ListingComparison
)
from backend.schemas import (
    HealthCheckResponse,
    LoginRequest,
    TokenResponse,
    UserProfileResponse,
    CreateInspectionRequest,
    InspectionResponse,
    InspectionDetailResponse,
    RecentInspectionItem,
    DashboardStatsResponse,
    ProductImageResponse,
    ImageQualityDetails,
    QualityCheckResponse,
    OCRTextBoxResponse,
    OCRResultResponse,
    DeclarationResponse,
    UpdateDeclarationRequest,
    RunOCRResponse,
    EvidenceResponse,
    FindingResponse,
    AdjudicateFindingRequest,
    EvaluateInspectionResponse,
    AuditLogResponse,
    ReportResponse,
    FinalizeInspectionRequest,
    FinalizeInspectionResponse,
    UpdateProfileRequest,
    ChangePasswordRequest,
    BarcodeItemResponse,
    BarcodeInspectionSummaryResponse,
    DashboardKPISummaryResponse,
    DashboardInspectionListItem,
    DashboardInspectionsListResponse,
    PendingActionItem,
    DashboardPendingActionsResponse,
    ComplianceAnalyticsResponse,
    EnforcementActivityResponse,
    RepositoryInspectionItem,
    RepositoryInspectionsResponse,
    RepositoryProductItem,
    RepositoryProductsResponse,
    RepositoryReportItem,
    RepositoryReportsResponse,
    UserListItemResponse,
    UpdateUserRoleRequest,
    ProductListingCreateRequest,
    ProductListingResponse,
    ListingComparisonItemResponse,
    ListingComparisonSummaryResponse,
    AdjudicateComparisonRequest,
    DeclarationValidationMatrixResponse,
    DeclarationMatrixRowSchema,
    ComplianceSummaryResponse,
    DeleteInspectionRequest,
    DeleteInspectionResponse,
    DeleteReportResponse,
    SupervisorDashboardResponse,
    SupervisorInspectorSummary,
    SupervisorInspectorsListResponse,
    SupervisorInspectionSummaryItem,
    SupervisorInspectionsListResponse
)
from backend.auth_utils import verify_password, hash_password
from backend.auth_service import (
    create_access_token,
    get_current_user,
    require_roles,
    require_inspector,
    require_supervisor_or_admin,
    require_supervisor,
    require_admin
)
from backend.image_quality import assess_image_quality, assess_blur_blur_detection2
from backend.ocr_service import ocr_service
from backend.barcode_service import barcode_service, BarcodeItem
from backend.extraction_service import extraction_service, cross_image_verification
from backend.declaration_validation_service import declaration_validation_engine
from backend.rule_engine import (
    rule_engine,
    get_rule_by_code,
    STATUTORY_RULE_REGISTRY,
    RuleResultState
)
from backend.listing_service import execute_listing_comparison
from backend.report_service import report_generator
from backend.compliance_summary_utils import compute_canonical_compliance_metrics
from backend.supabase_storage import storage_service
from backend.seed import seed_database
from backend.schema_migration import migrate

# AUDIT-STARTUP-01: Only auto-create schema and seed in non-production environments.
# Production schema management should be explicit (via migrations or manual seed).
if settings.ENVIRONMENT != "production":
    Base.metadata.create_all(bind=engine)
    try:
        migrate()
    except Exception as e:
        print(f"[Warning] Schema migration error on startup: {e}")
    try:
        seed_database()
    except Exception as e:
        print(f"[Warning] Seed error on startup: {e}")
else:
    # Production: verify database connectivity only
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[Startup] Production database connectivity verified.")
    except Exception as e:
        print(f"[Startup] WARNING: Production database connectivity check failed: {e}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Backend API for NiriKsha — AI-Assisted Legal Metrology Packaged-Commodity Inspection System (SIH 2026 Problem Statement 26034)"
)

# CORS Configuration
_raw_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_cors_origins = ["*"] if ("*" in _raw_origins or not _raw_origins) else _raw_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"^https?://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal Server Error: {str(exc)}"}
    )
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    return response



# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
STITCH_DIR = BASE_DIR / "stitch_screens"
UPLOADS_DIR = BASE_DIR / "uploads"
REPORTS_DIR = BASE_DIR / "generated_reports"

UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# Mount Static Assets
if STITCH_DIR.exists():
    app.mount("/stitch", StaticFiles(directory=str(STITCH_DIR), html=True), name="stitch")

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/reports-static", StaticFiles(directory=str(REPORTS_DIR)), name="reports_static")

# ── OCR Startup Warmup ────────────────────────────────────────────────────────
# Fires PaddleOCR's first inference (JIT/kernel compilation) in a background
# daemon thread immediately at server startup.  This amortizes the cold-start
# cost (~60-70s per image) so the FIRST real inspection request runs at warm
# speed (~15-20s per image).  The warmup is non-blocking and non-fatal.
@app.on_event("startup")
async def _startup_ocr_warmup():
    if not getattr(settings, "OCR_WARMUP_ON_STARTUP", True):
        logger.info("[OCR_WARMUP_DISABLED] OCR_WARMUP_ON_STARTUP=False, skipping")
        return
    import threading
    warmup_thread = threading.Thread(
        target=ocr_service.warmup_inference,
        name="ocr-warmup",
        daemon=True  # Will not block clean shutdown
    )
    warmup_thread.start()
    logger.info("[OCR_WARMUP_THREAD_STARTED] PaddleOCR warmup launched in background thread")

# ----------------- Helper Functions -----------------

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

# Process-level lock to prevent TOCTOU race on draft idempotency within the process.
# Inspection number allocation itself is atomic at the database level via inspection_number_counters.
_creation_lock = threading.Lock()

def verify_inspection_access(
    inspection: Inspection,
    current_user: User,
    allow_supervisory: bool = True
) -> bool:
    """
    Server-side Role-Based Access Control & Resource Isolation for Inspections.
    - ADMIN: Full access across all inspections (read, write, adjudicate, finalize).
    - SUPERVISOR: Read/oversight access across all inspections when allow_supervisory is True.
      If allow_supervisory is False (e.g. modifying findings, uploading evidence, adjudicating),
      access is denied unless they are the assigned inspector.
    - INSPECTOR: Scoped strictly to inspections where inspection.inspector_id == current_user.id.
    """
    user_role = (current_user.role or "INSPECTOR").upper()
    is_owner = (inspection.inspector_id == current_user.id)

    if user_role == "ADMIN":
        return True

    if is_owner:
        return True

    if allow_supervisory and user_role == "SUPERVISOR":
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Access forbidden: You do not have authorization for inspection '{inspection.inspection_number}'."
    )

def _fetch_existing_draft(db: Session, inspector_id: str, client_draft_id: str):
    """Re-query a draft inspection by client_draft_id. Used for idempotent conflict recovery."""
    return db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.images),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.report)
    ).filter(
        Inspection.inspector_id == inspector_id,
        or_(
            Inspection.client_draft_id == client_draft_id,
            Inspection.notes.like(f"%[client_draft_id:{client_draft_id}]%")
        )
    ).first()

def allocate_inspection_number(db: Session, year: Optional[int] = None) -> str:
    """Atomically allocates a sequential, official Legal Metrology inspection number.

    AUDIT-CONCUR-01: Truly atomic allocation backed by the inspection_number_counters
    table with database row-level locking. Safe across multiple workers, processes,
    and containers without requiring Python-level locks.

    Format: LM-YYYY-NNNNN (e.g., LM-2026-00001)
    """
    target_year = year or datetime.utcnow().year
    prefix = f"LM-{target_year}-"

    try:
        # 1. Initialize counter row if missing (idempotent across concurrent workers)
        max_existing = db.execute(
            text(
                "SELECT MAX(CAST(SUBSTR(inspection_number, :offset) AS INTEGER)) "
                "FROM inspections WHERE inspection_number LIKE :pattern"
            ),
            {"offset": len(prefix) + 1, "pattern": f"{prefix}%"}
        ).scalar()
        initial_next = (max_existing or 0) + 1

        db.execute(
            text(
                "INSERT INTO inspection_number_counters (year, next_number) "
                "VALUES (:year, :initial_next) "
                "ON CONFLICT (year) DO NOTHING"
            ),
            {"year": target_year, "initial_next": initial_next}
        )

        # 2. Atomically increment and return the allocated sequence number
        allocated_seq = db.execute(
            text(
                "UPDATE inspection_number_counters "
                "SET next_number = next_number + 1 "
                "WHERE year = :year "
                "RETURNING next_number - 1"
            ),
            {"year": target_year}
        ).scalar()
    except Exception:
        # Fallback if table does not exist yet in early bootstrap/test phase
        InspectionNumberCounter.__table__.create(db.get_bind(), checkfirst=True)
        max_existing = db.execute(
            text(
                "SELECT MAX(CAST(SUBSTR(inspection_number, :offset) AS INTEGER)) "
                "FROM inspections WHERE inspection_number LIKE :pattern"
            ),
            {"offset": len(prefix) + 1, "pattern": f"{prefix}%"}
        ).scalar()
        initial_next = (max_existing or 0) + 1
        db.execute(
            text(
                "INSERT INTO inspection_number_counters (year, next_number) "
                "VALUES (:year, :initial_next) "
                "ON CONFLICT (year) DO NOTHING"
            ),
            {"year": target_year, "initial_next": initial_next}
        )
        allocated_seq = db.execute(
            text(
                "UPDATE inspection_number_counters "
                "SET next_number = next_number + 1 "
                "WHERE year = :year "
                "RETURNING next_number - 1"
            ),
            {"year": target_year}
        ).scalar()

    if allocated_seq is None:
        allocated_seq = initial_next

    return f"{prefix}{int(allocated_seq):05d}"

# Backwards-compatible alias
generate_inspection_number = allocate_inspection_number

def log_audit(
    db: Session,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    inspection_id: Optional[str] = None,
    old_val: Optional[str] = None,
    new_val: Optional[str] = None,
    details: Optional[str] = None
):
    audit = AuditLog(
        inspection_id=inspection_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_val,
        new_value=new_val,
        details=details
    )
    db.add(audit)
    db.flush()

def serialize_image_response(img: ProductImage) -> ProductImageResponse:
    quality_details = None
    barcode_items = None
    if img.quality_metadata_json:
        try:
            meta = json.loads(img.quality_metadata_json)
            quality_details = ImageQualityDetails(**meta)
            if "barcodes" in meta and isinstance(meta["barcodes"], list):
                barcode_items = [BarcodeItemResponse(**b) for b in meta["barcodes"]]
        except Exception:
            quality_details = None

    return ProductImageResponse(
        id=img.id,
        inspection_id=img.inspection_id,
        original_filename=img.original_filename,
        file_path=img.file_path,
        view_type=img.view_type,
        mime_type=img.mime_type or "image/jpeg",
        file_size=img.file_size or 0,
        width=img.width or 0,
        height=img.height or 0,
        sequence_order=img.sequence_order or 1,
        quality_status=img.quality_status or "GOOD",
        quality_score=img.quality_score or 1.0,
        quality_details=quality_details,
        barcodes=barcode_items,
        created_at=img.created_at
    )

def serialize_ocr_result(res: OCRResult) -> OCRResultResponse:
    boxes = []
    if res.bounding_boxes_json:
        try:
            raw_boxes = json.loads(res.bounding_boxes_json)
            boxes = [OCRTextBoxResponse(**b) for b in raw_boxes]
        except Exception:
            boxes = []

    return OCRResultResponse(
        id=res.id,
        image_id=res.image_id,
        raw_text=res.raw_text,
        confidence=res.confidence,
        bounding_boxes=boxes,
        created_at=res.created_at
    )

def serialize_declaration(decl: Declaration) -> DeclarationResponse:
    bbox = None
    if decl.bounding_box_json:
        try:
            bbox = json.loads(decl.bounding_box_json)
        except Exception:
            bbox = None

    has_conflict = getattr(decl, "extraction_status", "") == "CONFLICTING"
    conflicts = None
    source_images = None
    raw_text = None
    layout_region = None
    layout_bbox = None
    if decl.correction_reason:
        try:
            cdata = json.loads(decl.correction_reason)
            if isinstance(cdata, dict):
                has_conflict = cdata.get("conflict", has_conflict)
                conflicts = cdata.get("candidates", conflicts)
                source_images = cdata.get("source_images", source_images)
                raw_text = cdata.get("raw_text")
                layout_region = cdata.get("layout_region")
                layout_bbox = cdata.get("layout_bbox")
        except Exception:
            pass

    if decl.verification_status == "CORRECTED":
        extraction_method = "INSPECTOR_CORRECTED"
    elif decl.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"]:
        extraction_method = "MANUAL"
    else:
        extraction_method = "AI/OCR"

    return DeclarationResponse(
        id=decl.id,
        inspection_id=decl.inspection_id,
        field_name=decl.field_name,
        extracted_value=decl.extracted_value,
        normalized_value=decl.normalized_value,
        effective_value=decl.effective_value,
        confidence=decl.confidence,
        bounding_box=bbox,
        extraction_status=decl.extraction_status,
        extraction_method=extraction_method,
        corrected_value=decl.corrected_value,
        is_applicable=decl.is_applicable,
        verification_status=decl.verification_status,
        verified_by=decl.verified_by,
        verified_at=decl.verified_at,
        correction_reason=decl.correction_reason,
        source_image_id=decl.source_image_id,
        has_conflict=has_conflict,
        conflicts=conflicts,
        source_images=source_images,
        raw_text=raw_text,
        layout_region=layout_region,
        layout_bbox=layout_bbox,
        placement_status=getattr(decl, "placement_status", "NOT_DETERMINABLE") or "NOT_DETERMINABLE",
        placement_details=json.loads(decl.placement_details_json) if getattr(decl, "placement_details_json", None) else None,
        font_size_status=getattr(decl, "font_size_status", "FONT_SIZE_UNDETERMINABLE") or "FONT_SIZE_UNDETERMINABLE",
        font_size_details=json.loads(decl.font_size_details_json) if getattr(decl, "font_size_details_json", None) else None,
        readability_status=getattr(decl, "readability_status", "NOT_OBSERVABLE") or "NOT_OBSERVABLE",
        readability_details=json.loads(decl.readability_details_json) if getattr(decl, "readability_details_json", None) else None,
        format_status=getattr(decl, "format_status", "COMPLIANT") or "COMPLIANT",
        format_details=json.loads(decl.format_details_json) if getattr(decl, "format_details_json", None) else None,
        validation_matrix=json.loads(decl.validation_matrix_json) if getattr(decl, "validation_matrix_json", None) else None,
        created_at=decl.created_at
    )

def get_inspection_by_id_or_number(db: Session, identifier: str) -> Optional[Inspection]:
    """
    Resolves an inspection by UUID or human-readable inspection_number (e.g. 'LM-2026-00023').
    Guarantees deterministic lookup regardless of which identifier caller provides.
    """
    if not identifier:
        return None
    ident = str(identifier).strip()
    return db.query(Inspection).filter(
        or_(
            Inspection.id == ident,
            Inspection.inspection_number == ident
        )
    ).first()

def serialize_finding(check: ComplianceCheck) -> FindingResponse:
    evidence_items = []
    for ev in check.evidence:
        bbox = None
        if ev.bounding_box_json:
            try:
                bbox = json.loads(ev.bounding_box_json)
            except Exception:
                bbox = None
        evidence_items.append(EvidenceResponse(
            id=ev.id,
            check_id=ev.check_id,
            image_id=ev.image_id,
            bounding_box=bbox,
            crop_image_path=ev.crop_image_path,
            highlight_text=ev.highlight_text,
            reason=ev.reason,
            created_at=ev.created_at
        ))

    # Pull rule version metadata for traceability
    rule_ver = check.rule_version if check.rule_version else None
    rule_version_number = rule_ver.version_number if rule_ver else None
    statutory_reference = rule_ver.statutory_reference if rule_ver else None
    category = rule_ver.category if rule_ver else "CATEGORY_A_LEGAL"

    return FindingResponse(
        id=check.id,
        inspection_id=check.inspection_id,
        rule_version_id=check.rule_version_id,
        rule_code=check.rule_code,
        rule_version_number=rule_version_number,
        statutory_reference=statutory_reference,
        title=check.title,
        severity=check.severity,
        result_state=check.result_state,
        extracted_value=check.extracted_value,
        explanation=check.explanation,
        adjudication_status=check.adjudication_status or "PENDING",
        adjudication_notes=check.adjudication_notes,
        adjudicated_by=check.adjudicated_by,
        adjudicated_at=check.adjudicated_at,
        created_at=check.created_at,
        evidence_items=evidence_items,
        category=category,
        status=check.result_state,
        adjudication=check.adjudication_status or "PENDING",
        description=check.explanation
    )

def serialize_report(rep: Report) -> ReportResponse:
    insp = rep.inspection
    return ReportResponse(
        id=rep.id,
        inspection_id=rep.inspection_id,
        report_version=rep.report_version,
        pdf_path=rep.pdf_path,
        download_url=f"/api/inspections/{rep.inspection_id}/report/pdf",
        docx_path=getattr(rep, "docx_path", None),
        docx_download_url=f"/api/inspections/{rep.inspection_id}/report/docx",
        legal_safety_statement=rep.legal_safety_statement,
        generated_at=rep.generated_at,
        inspection_number=insp.inspection_number if insp else None,
        product_name=insp.product.product_name if (insp and insp.product) else None,
        location=insp.location if insp else None,
        overall_status=insp.overall_status if insp else None,
        pdf_hash=getattr(rep, "pdf_hash", None)
    )

# ----------------- Health & Auth Endpoints -----------------

@app.get("/api/health", response_model=HealthCheckResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check verifying API and Database connectivity."""
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"disconnected ({str(e)})"

    info = get_database_backend_info()
    return HealthCheckResponse(
        status="healthy" if db_status == "connected" else "degraded",
        app_name=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        database=db_status,
        database_backend=info.get("database_backend"),
        database_host=info.get("database_host"),
        database_driver=info.get("database_driver"),
        version="1.0.0"
    )

@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """Authenticates an enforcement officer and returns a JWT access token."""
    officer = db.query(User).filter(User.officer_id == req.officer_id.strip()).first()
    if not officer or not verify_password(req.password, officer.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Officer ID or password"
        )

    # Capture previous login timestamp before updating to current session time
    previous_login_at = officer.last_login_at
    current_login_at = datetime.utcnow()

    officer.previous_login_at = previous_login_at
    officer.last_login_at = current_login_at

    access_token = create_access_token(data={"sub": officer.officer_id, "role": officer.role})
    log_audit(db, officer.officer_id, "LOGIN_SUCCESS", "user", officer.id, details="Officer logged in successfully")
    db.commit()
    db.refresh(officer)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        officer_id=officer.officer_id,
        full_name=officer.full_name,
        designation=officer.designation,
        zone=officer.zone,
        email=officer.email,
        phone=officer.phone,
        role=officer.role or "INSPECTOR",
        last_login_at=officer.last_login_at,
        previous_login_at=previous_login_at
    )

@app.get("/api/auth/me", response_model=UserProfileResponse, tags=["Authentication"])
def get_profile(current_user: User = Depends(get_current_user)):
    """Returns the authenticated officer profile."""
    return current_user

@app.patch("/api/auth/me", response_model=UserProfileResponse, tags=["Authentication"])
def update_profile(
    req: UpdateProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Updates authenticated officer contact information."""
    if req.email is not None:
        current_user.email = req.email.strip()
    if req.phone is not None:
        current_user.phone = req.phone.strip()
    
    log_audit(
        db,
        current_user.officer_id,
        "PROFILE_UPDATED",
        "user",
        current_user.id,
        details=f"Officer contact details updated. Email: {current_user.email}, Phone: {current_user.phone}"
    )
    db.commit()
    db.refresh(current_user)
    return current_user

@app.post("/api/auth/change-password", tags=["Authentication"])
def change_password(
    req: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Verifies existing password and updates to new password hash."""
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long"
        )
    
    current_user.password_hash = hash_password(req.new_password)
    log_audit(
        db,
        current_user.officer_id,
        "PASSWORD_CHANGED",
        "user",
        current_user.id,
        details="Officer password updated successfully"
    )
    db.commit()
    return {"status": "success", "message": "Password changed successfully"}

@app.post("/api/auth/logout", status_code=status.HTTP_200_OK, tags=["Authentication"])
def logout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Logs out the authenticated officer and records an audit trail event."""
    log_audit(
        db,
        current_user.officer_id,
        "LOGOUT",
        "user",
        current_user.id,
        details="Officer logged out successfully"
    )
    db.commit()
    return {"message": "Successfully logged out"}

# ----------------- Dashboard Endpoints -----------------

def _parse_dashboard_date_filter(date_str: str, is_end_date: bool = False) -> datetime:
    """Safely parses ISO / YYYY-MM-DD date strings for dashboard filtering."""
    try:
        trimmed = date_str.strip()
        if "T" in trimmed or " " in trimmed:
            clean = trimmed.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        else:
            d = datetime.strptime(trimmed, "%Y-%m-%d")
            if is_end_date:
                return datetime(d.year, d.month, d.day, 23, 59, 59, 999999)
            return datetime(d.year, d.month, d.day, 0, 0, 0)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format for '{date_str}'. Expected YYYY-MM-DD or ISO 8601 string."
        ) from exc


@app.get("/api/dashboard", response_model=DashboardStatsResponse, tags=["Dashboard"])
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns real aggregate metric cards and recent inspections for the dashboard (backward compatible)."""
    query = db.query(Inspection)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)

    total_inspections = query.count()
    needs_manual_verification = query.filter(
        Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION"
    ).count()
    verified_inspections = query.filter(
        Inspection.overall_status == "NO_POTENTIAL_VIOLATIONS"
    ).count()
    potential_non_compliance = query.filter(
        Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE"
    ).count()

    recent_objs = query.order_by(Inspection.created_at.desc()).limit(5).all()
    recent_items = [
        RecentInspectionItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=insp.product.product_name if insp.product else "Unnamed Commodity",
            location=insp.location,
            status=insp.status,
            overall_status=insp.overall_status,
            created_at=insp.created_at
        )
        for insp in recent_objs
    ]

    return DashboardStatsResponse(
        total_inspections=total_inspections,
        needs_manual_verification=needs_manual_verification,
        verified_inspections=verified_inspections,
        potential_non_compliance=potential_non_compliance,
        recent_inspections=recent_items
    )


@app.get("/api/dashboard/summary", response_model=DashboardKPISummaryResponse, tags=["Dashboard"])
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Computes all 7 dynamic Legal Metrology Enforcement KPIs calculated strictly from live DB."""
    query = db.query(Inspection)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)

    total_inspections = query.count()
    completed_inspections = query.filter(
        or_(Inspection.status == "COMPLETED", Inspection.finalized_at.isnot(None))
    ).count()
    pending_verification = query.filter(
        Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION"
    ).count()
    potential_non_compliance = query.filter(
        Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE"
    ).count()
    compliant_inspections = query.filter(
        Inspection.overall_status.in_(["NO_POTENTIAL_VIOLATIONS", "VERIFIED_COMPLIANT"])
    ).count()

    # Reports generated: inspections that have an associated Report record
    reports_generated = query.join(Report, Inspection.id == Report.inspection_id).count()

    # Inspections requiring manual verification: overall_status is NEEDS_MANUAL_VERIFICATION,
    # or has declarations in CONFLICTING / NOT_FOUND / NEEDS_REVIEW,
    # or findings in FAIL with PENDING adjudication
    unresolved_decl_subq = db.query(distinct(Declaration.inspection_id)).filter(
        Declaration.extraction_status.in_(["NOT_FOUND", "CONFLICTING", "LOW_CONFIDENCE", "NEEDS_REVIEW"])
    )
    unresolved_check_subq = db.query(distinct(ComplianceCheck.inspection_id)).filter(
        ComplianceCheck.result_state == "POTENTIAL_NON_COMPLIANCE",
        ComplianceCheck.adjudication_status == "PENDING"
    )

    manual_verification_required = query.filter(
        or_(
            Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION",
            Inspection.id.in_(unresolved_decl_subq),
            Inspection.id.in_(unresolved_check_subq)
        )
    ).count()

    return DashboardKPISummaryResponse(
        total_inspections=total_inspections,
        completed_inspections=completed_inspections,
        pending_verification=pending_verification,
        potential_non_compliance=potential_non_compliance,
        compliant_inspections=compliant_inspections,
        reports_generated=reports_generated,
        manual_verification_required=manual_verification_required
    )


@app.get("/api/dashboard/inspections", response_model=DashboardInspectionsListResponse, tags=["Dashboard"])
def get_dashboard_inspections(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: DRAFT, IMAGES_UPLOADED, OCR_PROCESSING, EXTRACTION_COMPLETE, RULE_EVALUATION_COMPLETE, COMPLETED"),
    overall_status_filter: Optional[str] = Query(None, alias="overall_status", description="Filter by overall_status: NO_POTENTIAL_VIOLATIONS, POTENTIAL_NON_COMPLIANCE, NEEDS_MANUAL_VERIFICATION, INSUFFICIENT_EVIDENCE"),
    start_date: Optional[str] = Query(None, description="ISO Start date filter (YYYY-MM-DD or ISO)"),
    end_date: Optional[str] = Query(None, description="ISO End date filter (YYYY-MM-DD or ISO)"),
    category: Optional[str] = Query(None, description="Product category filter"),
    location: Optional[str] = Query(None, description="Location substring filter"),
    inspector_id: Optional[str] = Query(None, description="Inspector ID filter (Admin only)"),
    has_report: Optional[bool] = Query(None, description="Filter whether official report has been generated"),
    search: Optional[str] = Query(None, description="Search term across inspection number, product name, brand, location"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns a paginated, multi-criteria filterable list of inspections for the enforcement dashboard."""
    query = db.query(Inspection).join(Inspection.product).outerjoin(Inspection.inspector).outerjoin(Inspection.report)

    # Authorization / Isolation
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        if inspector_id and inspector_id != current_user.id and inspector_id != current_user.officer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: Inspectors cannot query another officer's inspections."
            )
        query = query.filter(Inspection.inspector_id == current_user.id)
    elif inspector_id:
        query = query.filter(
            or_(
                Inspection.inspector_id == inspector_id,
                User.officer_id == inspector_id
            )
        )

    # Status and Overall Status filters
    if status_filter:
        query = query.filter(Inspection.status == status_filter.strip())
    if overall_status_filter:
        query = query.filter(Inspection.overall_status == overall_status_filter.strip())

    # Date filters
    if start_date:
        parsed_start = _parse_dashboard_date_filter(start_date, is_end_date=False)
        query = query.filter(Inspection.created_at >= parsed_start)
    if end_date:
        parsed_end = _parse_dashboard_date_filter(end_date, is_end_date=True)
        query = query.filter(Inspection.created_at <= parsed_end)

    # Product category filter
    if category:
        query = query.filter(Product.category == category.strip())

    # Location filter
    if location:
        query = query.filter(Inspection.location.ilike(f"%{location.strip()}%"))

    # Report generated filter
    if has_report is True:
        query = query.filter(Report.id.isnot(None))
    elif has_report is False:
        query = query.filter(Report.id.is_(None))

    # Search keyword
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Inspection.inspection_number.ilike(term),
                Product.product_name.ilike(term),
                Product.brand_name.ilike(term),
                Inspection.location.ilike(term)
            )
        )

    total_count = query.count()
    rows = query.options(
        joinedload(Inspection.product),
        joinedload(Inspection.inspector),
        joinedload(Inspection.report),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks)
    ).order_by(Inspection.created_at.desc()).offset(offset).limit(limit).all()

    items: List[DashboardInspectionListItem] = []
    for insp in rows:
        p_name = insp.product.product_name if insp.product else "Unnamed Commodity"
        b_name = insp.product.brand_name if insp.product else None
        c_name = insp.product.category if insp.product else "Packaged Commodity"
        i_name = insp.inspector.full_name if insp.inspector else (insp.inspector_id or "Inspector")

        # Compute pending actions for this inspection
        p_count = 0
        if insp.declarations:
            p_count += sum(1 for d in insp.declarations if d.extraction_status in ("NOT_FOUND", "CONFLICTING"))
        if insp.compliance_checks:
            p_count += sum(1 for c in insp.compliance_checks if c.result_state in ("FAIL", "POTENTIAL_NON_COMPLIANCE") and c.adjudication_status == "PENDING")

        has_rep = insp.report is not None
        rep_ver = insp.report.report_version if has_rep else None

        items.append(DashboardInspectionListItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=p_name,
            brand_name=b_name,
            category=c_name,
            inspector_id=insp.inspector_id,
            inspector_name=i_name,
            location=insp.location,
            created_at=insp.created_at,
            status=insp.status,
            overall_status=insp.overall_status,
            has_report=has_rep,
            report_version=rep_ver,
            pending_actions_count=p_count
        ))

    return DashboardInspectionsListResponse(
        total=total_count,
        items=items,
        limit=limit,
        offset=offset
    )


@app.get("/api/dashboard/pending-actions", response_model=DashboardPendingActionsResponse, tags=["Dashboard"])
def get_dashboard_pending_actions(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns an actionable queue of pending enforcement checks requiring officer adjudication."""
    insp_query = db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.images)
    ).filter(
        Inspection.status != "COMPLETED",
        Inspection.finalized_at.is_(None)
    )

    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        insp_query = insp_query.filter(Inspection.inspector_id == current_user.id)

    inspections = insp_query.order_by(Inspection.created_at.desc()).limit(100).all()
    actions: List[PendingActionItem] = []

    for insp in inspections:
        prod_name = insp.product.product_name if insp.product else "Unnamed Commodity"

        # 1. Unadjudicated non-compliance findings
        for chk in (insp.compliance_checks or []):
            if chk.result_state == "POTENTIAL_NON_COMPLIANCE" and chk.adjudication_status == "PENDING":
                actions.append(PendingActionItem(
                    inspection_id=insp.id,
                    inspection_number=insp.inspection_number,
                    product_name=prod_name,
                    action_type="PENDING_ADJUDICATION",
                    title=f"Adjudicate Violation: {chk.rule_code}",
                    description=f"{chk.title or 'Rule violation detected'} requires statutory officer adjudication.",
                    severity="CRITICAL",
                    created_at=insp.created_at
                ))

        # 2. Conflicting declarations across multi-image views
        for decl in (insp.declarations or []):
            if decl.extraction_status == "CONFLICTING":
                actions.append(PendingActionItem(
                    inspection_id=insp.id,
                    inspection_number=insp.inspection_number,
                    product_name=prod_name,
                    action_type="CONFLICTING_DECLARATION",
                    title=f"Conflicting {decl.field_name.replace('_', ' ').title()}",
                    description="Multiple contradictory values detected across package panels. Manual verification required.",
                    severity="CRITICAL",
                    created_at=insp.created_at
                ))
            elif decl.extraction_status == "NOT_FOUND":
                actions.append(PendingActionItem(
                    inspection_id=insp.id,
                    inspection_number=insp.inspection_number,
                    product_name=prod_name,
                    action_type="MISSING_DECLARATION",
                    title=f"Missing {decl.field_name.replace('_', ' ').title()}",
                    description="Mandatory statutory declaration was not identified by OCR on uploaded panels.",
                    severity="WARNING",
                    created_at=insp.created_at
                ))

        # 3. Image quality warnings / blur
        for img in (insp.images or []):
            if img.quality_status == "POOR":
                actions.append(PendingActionItem(
                    inspection_id=insp.id,
                    inspection_number=insp.inspection_number,
                    product_name=prod_name,
                    action_type="OCR_UNCERTAINTY",
                    title="Image Quality Warning",
                    description=f"Image for view '{img.view_type}' is degraded or blurry. New image may be required.",
                    severity="WARNING",
                    created_at=img.created_at or insp.created_at
                ))

    # Sort actions by severity (CRITICAL first) then created_at desc
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    actions.sort(key=lambda a: (severity_order.get(a.severity, 3), -a.created_at.timestamp()))
    limited_actions = actions[:limit]

    return DashboardPendingActionsResponse(
        total=len(actions),
        items=limited_actions
    )


@app.get("/api/dashboard/analytics", response_model=ComplianceAnalyticsResponse, tags=["Dashboard"])
def get_dashboard_analytics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Computes compliance rates, rule breakdowns, and timeline distributions from real DB records."""
    query = db.query(Inspection)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)

    # Total evaluated inspections
    evaluated_query = query.filter(Inspection.overall_status.isnot(None))
    total_evaluated = evaluated_query.count()

    if total_evaluated == 0:
        return ComplianceAnalyticsResponse(
            has_sufficient_data=False,
            total_evaluated=0,
            compliance_rate=0.0,
            potential_non_compliance_rate=0.0,
            manual_verification_rate=0.0,
            findings_by_field={},
            findings_by_rule={},
            findings_by_category={},
            inspections_over_time=[]
        )

    compliant_count = evaluated_query.filter(
        Inspection.overall_status.in_(["NO_POTENTIAL_VIOLATIONS", "VERIFIED_COMPLIANT"])
    ).count()
    non_compliant_count = evaluated_query.filter(
        Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE"
    ).count()
    manual_verif_count = evaluated_query.filter(
        Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION"
    ).count()

    comp_rate = round((compliant_count / total_evaluated) * 100, 1)
    non_comp_rate = round((non_compliant_count / total_evaluated) * 100, 1)
    manual_rate = round((manual_verif_count / total_evaluated) * 100, 1)

    # Findings by declaration field (missing or conflicting)
    decl_q = db.query(
        Declaration.field_name,
        func.count(Declaration.id)
    ).join(Inspection, Declaration.inspection_id == Inspection.id).filter(
        Declaration.extraction_status.in_(["NOT_FOUND", "CONFLICTING"])
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        decl_q = decl_q.filter(Inspection.inspector_id == current_user.id)
    findings_by_field = dict(decl_q.group_by(Declaration.field_name).all())

    # Findings by rule code
    rule_q = db.query(
        ComplianceCheck.rule_code,
        func.count(ComplianceCheck.id)
    ).join(Inspection, ComplianceCheck.inspection_id == Inspection.id).filter(
        ComplianceCheck.result_state == "POTENTIAL_NON_COMPLIANCE"
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        rule_q = rule_q.filter(Inspection.inspector_id == current_user.id)
    findings_by_rule = dict(rule_q.group_by(ComplianceCheck.rule_code).all())

    # Findings by product category
    cat_q = db.query(
        Product.category,
        func.count(distinct(Inspection.id))
    ).join(Inspection, Product.inspection_id == Inspection.id).filter(
        Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE"
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        cat_q = cat_q.filter(Inspection.inspector_id == current_user.id)
    findings_by_category = dict(cat_q.group_by(Product.category).all())

    # Inspections over time (grouped by date)
    date_col = func.date(Inspection.created_at)
    time_q = db.query(
        date_col.label("insp_date"),
        func.count(Inspection.id).label("total"),
        func.sum(case((Inspection.overall_status.in_(["NO_POTENTIAL_VIOLATIONS", "VERIFIED_COMPLIANT"]), 1), else_=0)).label("compliant"),
        func.sum(case((Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE", 1), else_=0)).label("non_compliant")
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        time_q = time_q.filter(Inspection.inspector_id == current_user.id)
    time_rows = time_q.group_by("insp_date").order_by("insp_date").all()

    inspections_over_time = [
        {
            "date": str(r.insp_date),
            "total": int(r.total or 0),
            "compliant": int(r.compliant or 0),
            "non_compliant": int(r.non_compliant or 0)
        }
        for r in time_rows
    ]

    return ComplianceAnalyticsResponse(
        has_sufficient_data=True,
        total_evaluated=total_evaluated,
        compliance_rate=comp_rate,
        potential_non_compliance_rate=non_comp_rate,
        manual_verification_rate=manual_rate,
        findings_by_field=findings_by_field,
        findings_by_rule=findings_by_rule,
        findings_by_category=findings_by_category,
        inspections_over_time=inspections_over_time
    )


@app.get("/api/dashboard/enforcement", response_model=EnforcementActivityResponse, tags=["Dashboard"])
def get_dashboard_enforcement(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aggregates jurisdictional and officer enforcement activity strictly from DB records."""
    insp_q = db.query(Inspection)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        insp_q = insp_q.filter(Inspection.inspector_id == current_user.id)

    # 1. Inspections by location
    loc_q = db.query(
        Inspection.location,
        func.count(Inspection.id).label("count")
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        loc_q = loc_q.filter(Inspection.inspector_id == current_user.id)
    loc_rows = loc_q.group_by(Inspection.location).order_by(func.count(Inspection.id).desc()).limit(10).all()
    inspections_by_location = [{"location": r[0] or "Unknown Location", "count": int(r[1])} for r in loc_rows]

    # 2. Inspections by inspector
    insp_user_q = db.query(
        Inspection.inspector_id,
        User.officer_id,
        User.full_name,
        func.count(Inspection.id).label("count")
    ).outerjoin(User, Inspection.inspector_id == User.id)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        insp_user_q = insp_user_q.filter(Inspection.inspector_id == current_user.id)
    insp_user_rows = insp_user_q.group_by(Inspection.inspector_id, User.officer_id, User.full_name).order_by(func.count(Inspection.id).desc()).limit(10).all()
    inspections_by_inspector = [
        {
            "inspector_id": r[0],
            "officer_id": r[1] or "N/A",
            "name": r[2] or "Inspector",
            "count": int(r[3])
        }
        for r in insp_user_rows
    ]

    # 3. Non-compliance by location
    non_comp_loc_q = db.query(
        Inspection.location,
        func.count(Inspection.id).label("count")
    ).filter(Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE")
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        non_comp_loc_q = non_comp_loc_q.filter(Inspection.inspector_id == current_user.id)
    non_comp_rows = non_comp_loc_q.group_by(Inspection.location).order_by(func.count(Inspection.id).desc()).limit(10).all()
    non_compliance_by_location = [{"location": r[0] or "Unknown Location", "count": int(r[1])} for r in non_comp_rows]

    # 4. Most frequently flagged rules
    rule_q = db.query(
        ComplianceCheck.rule_code,
        ComplianceCheck.title,
        func.count(ComplianceCheck.id).label("count")
    ).join(Inspection, ComplianceCheck.inspection_id == Inspection.id).filter(
        ComplianceCheck.result_state == "POTENTIAL_NON_COMPLIANCE"
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        rule_q = rule_q.filter(Inspection.inspector_id == current_user.id)
    top_rule_rows = rule_q.group_by(ComplianceCheck.rule_code, ComplianceCheck.title).order_by(func.count(ComplianceCheck.id).desc()).limit(10).all()
    top_flagged_rules = [
        {
            "rule_code": r[0],
            "title": r[1] or r[0],
            "count": int(r[2])
        }
        for r in top_rule_rows
    ]

    # 5. Repeatedly inspected products
    prod_q = db.query(
        Product.product_name,
        Product.brand_name,
        Product.category,
        func.count(Inspection.id).label("count")
    ).join(Inspection, Product.inspection_id == Inspection.id)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        prod_q = prod_q.filter(Inspection.inspector_id == current_user.id)
    repeat_rows = prod_q.group_by(
        Product.product_name, Product.brand_name, Product.category
    ).having(func.count(Inspection.id) > 1).order_by(func.count(Inspection.id).desc()).limit(10).all()

    repeatedly_inspected_products = [
        {
            "product_name": r[0],
            "brand_name": r[1],
            "category": r[2],
            "inspection_count": int(r[3])
        }
        for r in repeat_rows
    ]

    return EnforcementActivityResponse(
        inspections_by_location=inspections_by_location,
        inspections_by_inspector=inspections_by_inspector,
        non_compliance_by_location=non_compliance_by_location,
        top_flagged_rules=top_flagged_rules,
        repeatedly_inspected_products=repeatedly_inspected_products
    )


# ===========================================================================
# Repository & Global Search Endpoints (PS 26034)
# ===========================================================================

def _generate_product_key(product_name: str, brand_name: Optional[str], category: str) -> str:
    """Generates a stable, deterministic 16-hex identifier for an inspected product entity."""
    clean_p = (product_name or "").strip().lower()
    clean_b = (brand_name or "").strip().lower()
    clean_c = (category or "").strip().lower()
    return hashlib.sha256(f"{clean_p}|{clean_b}|{clean_c}".encode("utf-8")).hexdigest()[:16]


@app.get("/api/repository/inspections", response_model=RepositoryInspectionsResponse, tags=["Repository & Search"])
@app.get("/api/inspections/search", response_model=RepositoryInspectionsResponse, tags=["Repository & Search"])
@app.get("/api/inspections/history", response_model=RepositoryInspectionsResponse, tags=["Repository & Search"])
def search_repository_inspections(
    search: Optional[str] = Query(None, description="Search across ID, product, brand, category, manufacturer, inspector, location, batch, report"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by lifecycle status"),
    overall_status_filter: Optional[str] = Query(None, alias="overall_status", description="Filter by compliance outcome"),
    start_date: Optional[str] = Query(None, description="Start date ISO/YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date ISO/YYYY-MM-DD"),
    category: Optional[str] = Query(None, description="Product category filter"),
    location: Optional[str] = Query(None, description="Location substring"),
    inspector_id: Optional[str] = Query(None, description="Inspector ID filter (Admin/Supervisor only)"),
    finding_type: Optional[str] = Query(None, description="Rule code, title, severity, or result state"),
    has_report: Optional[bool] = Query(None, description="Filter by report presence"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Global search and retrieval facility for previously inspected products and history."""
    query = db.query(Inspection).join(Inspection.product).outerjoin(Inspection.inspector).outerjoin(Inspection.report)

    # Authorization & isolation
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        if inspector_id and inspector_id != current_user.id and inspector_id != current_user.officer_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: Inspectors cannot query another officer's repository records."
            )
        query = query.filter(Inspection.inspector_id == current_user.id)
    elif inspector_id:
        query = query.filter(
            or_(
                Inspection.inspector_id == inspector_id,
                User.officer_id == inspector_id
            )
        )

    # Search keyword across multiple fields
    if search and search.strip():
        term = f"%{search.strip()}%"
        decl_subq = db.query(Declaration.inspection_id).filter(
            or_(
                and_(
                    Declaration.field_name.in_(["manufacturer_name", "manufacturer_details"]),
                    or_(Declaration.extracted_value.ilike(term), Declaration.corrected_value.ilike(term))
                ),
                and_(
                    Declaration.field_name.in_(["batch_code", "lot_number"]),
                    or_(Declaration.extracted_value.ilike(term), Declaration.corrected_value.ilike(term))
                )
            )
        )
        query = query.filter(
            or_(
                Inspection.id.ilike(term),
                Inspection.inspection_number.ilike(term),
                Product.product_name.ilike(term),
                Product.brand_name.ilike(term),
                Product.category.ilike(term),
                Product.batch_number.ilike(term),
                Inspection.location.ilike(term),
                User.officer_id.ilike(term),
                User.full_name.ilike(term),
                Report.id.ilike(term),
                Inspection.id.in_(decl_subq)
            )
        )

    # Filters
    if status_filter:
        query = query.filter(Inspection.status == status_filter.strip())
    if overall_status_filter:
        query = query.filter(Inspection.overall_status == overall_status_filter.strip())
    if category:
        query = query.filter(Product.category == category.strip())
    if location:
        query = query.filter(Inspection.location.ilike(f"%{location.strip()}%"))
    if has_report is True:
        query = query.filter(Report.id.isnot(None))
    elif has_report is False:
        query = query.filter(Report.id.is_(None))

    if start_date:
        parsed_start = _parse_dashboard_date_filter(start_date, is_end_date=False)
        query = query.filter(Inspection.created_at >= parsed_start)
    if end_date:
        parsed_end = _parse_dashboard_date_filter(end_date, is_end_date=True)
        query = query.filter(Inspection.created_at <= parsed_end)

    if finding_type and finding_type.strip():
        ft = finding_type.strip()
        chk_subq = db.query(ComplianceCheck.inspection_id).filter(
            or_(
                ComplianceCheck.rule_code.ilike(f"%{ft}%"),
                ComplianceCheck.title.ilike(f"%{ft}%"),
                ComplianceCheck.severity.ilike(ft),
                ComplianceCheck.result_state.ilike(ft)
            )
        )
        query = query.filter(Inspection.id.in_(chk_subq))

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    rows = query.options(
        joinedload(Inspection.product),
        joinedload(Inspection.inspector),
        joinedload(Inspection.report),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks)
    ).order_by(Inspection.created_at.desc()).offset(offset).limit(page_size).all()

    items: List[RepositoryInspectionItem] = []
    for insp in rows:
        p_name = insp.product.product_name if insp.product else "Unnamed Commodity"
        b_name = insp.product.brand_name if insp.product else None
        c_name = insp.product.category if insp.product else "Packaged Commodity"
        batch_val = insp.product.batch_number if insp.product else None
        i_name = insp.inspector.full_name if insp.inspector else (insp.inspector_id or "Inspector")
        i_officer_id = insp.inspector.officer_id if insp.inspector else insp.inspector_id

        # Derive manufacturer and batch from declarations if available
        mfg_val = None
        for d in (insp.declarations or []):
            if d.field_name in ("manufacturer_name", "manufacturer_details") and not mfg_val:
                mfg_val = d.corrected_value or d.extracted_value
            if d.field_name in ("batch_code", "lot_number") and not batch_val:
                batch_val = d.corrected_value or d.extracted_value

        checks = insp.compliance_checks or []
        non_comp = sum(1 for c in checks if c.result_state == "POTENTIAL_NON_COMPLIANCE")

        items.append(RepositoryInspectionItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=p_name,
            brand_name=b_name,
            category=c_name,
            manufacturer=mfg_val,
            batch_number=batch_val,
            location=insp.location,
            inspector_id=i_officer_id,
            inspector_name=i_name,
            status=insp.status,
            overall_status=insp.overall_status,
            findings_count=len(checks),
            non_compliant_count=non_comp,
            has_report=insp.report is not None,
            report_id=insp.report.id if insp.report else None,
            created_at=insp.created_at,
            finalized_at=insp.finalized_at
        ))

    return RepositoryInspectionsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/api/repository/products", response_model=RepositoryProductsResponse, tags=["Repository & Search"])
@app.get("/api/products/search", response_model=RepositoryProductsResponse, tags=["Repository & Search"])
def get_repository_products(
    search: Optional[str] = Query(None, description="Search across product name, brand, category, manufacturer"),
    category: Optional[str] = Query(None, description="Category filter"),
    compliance_status: Optional[str] = Query(None, description="Latest compliance status filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Aggregated catalogue of scanned products with surveillance history."""
    base_q = db.query(Inspection).join(Product, Inspection.id == Product.inspection_id)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        base_q = base_q.filter(Inspection.inspector_id == current_user.id)

    inspections = base_q.options(
        joinedload(Inspection.product),
        joinedload(Inspection.declarations)
    ).order_by(Inspection.created_at.desc()).all()

    # Group strictly by explicit identity: (product_name, brand_name, category)
    # Never infer identity solely from similar names. If distinct, present separate records.
    groups: Dict[str, Dict[str, Any]] = {}
    for insp in inspections:
        prod = insp.product
        if not prod:
            continue
        key = _generate_product_key(prod.product_name, prod.brand_name, prod.category)
        if key not in groups:
            mfg_val = None
            for d in (insp.declarations or []):
                if d.field_name in ("manufacturer_name", "manufacturer_details") and not mfg_val:
                    mfg_val = d.corrected_value or d.extracted_value

            groups[key] = {
                "product_key": key,
                "product_name": prod.product_name,
                "brand_name": prod.brand_name,
                "category": prod.category,
                "manufacturer": mfg_val,
                "inspection_count": 1,
                "last_inspection_date": insp.created_at,
                "latest_compliance_status": insp.overall_status,
                "latest_inspection_id": insp.id
            }
        else:
            groups[key]["inspection_count"] += 1
            if not groups[key]["manufacturer"]:
                for d in (insp.declarations or []):
                    if d.field_name in ("manufacturer_name", "manufacturer_details"):
                        groups[key]["manufacturer"] = d.corrected_value or d.extracted_value
                        break

    product_list = list(groups.values())

    # Apply search filter
    if search and search.strip():
        term = search.strip().lower()
        product_list = [
            p for p in product_list
            if term in p["product_name"].lower()
            or (p["brand_name"] and term in p["brand_name"].lower())
            or term in p["category"].lower()
            or (p["manufacturer"] and term in p["manufacturer"].lower())
        ]

    # Apply category filter
    if category:
        cat_lower = category.strip().lower()
        product_list = [p for p in product_list if p["category"].lower() == cat_lower]

    # Apply compliance_status filter
    if compliance_status:
        cs_lower = compliance_status.strip().lower()
        product_list = [p for p in product_list if (p["latest_compliance_status"] or "").lower() == cs_lower]

    total = len(product_list)
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    start_idx = (page - 1) * page_size
    paged = product_list[start_idx:start_idx + page_size]

    return RepositoryProductsResponse(
        items=[RepositoryProductItem(**p) for p in paged],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/api/repository/products/{product_key}/inspections", response_model=RepositoryInspectionsResponse, tags=["Repository & Search"])
@app.get("/api/products/{product_key}/history", response_model=RepositoryInspectionsResponse, tags=["Repository & Search"])
def get_product_inspection_history(
    product_key: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves the complete chronological inspection history for an identified product entity."""
    base_q = db.query(Inspection).join(Product, Inspection.id == Product.inspection_id)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        base_q = base_q.filter(Inspection.inspector_id == current_user.id)

    all_inspections = base_q.options(
        joinedload(Inspection.product),
        joinedload(Inspection.inspector),
        joinedload(Inspection.report),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks)
    ).order_by(Inspection.created_at.desc()).all()

    matching = [
        insp for insp in all_inspections
        if insp.product and _generate_product_key(insp.product.product_name, insp.product.brand_name, insp.product.category) == product_key
    ]

    total = len(matching)
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    offset = (page - 1) * page_size
    paged = matching[offset:offset + page_size]

    items: List[RepositoryInspectionItem] = []
    for insp in paged:
        p_name = insp.product.product_name if insp.product else "Unnamed Commodity"
        b_name = insp.product.brand_name if insp.product else None
        c_name = insp.product.category if insp.product else "Packaged Commodity"
        batch_val = insp.product.batch_number if insp.product else None
        i_name = insp.inspector.full_name if insp.inspector else (insp.inspector_id or "Inspector")
        i_officer_id = insp.inspector.officer_id if insp.inspector else insp.inspector_id

        mfg_val = None
        for d in (insp.declarations or []):
            if d.field_name in ("manufacturer_name", "manufacturer_details") and not mfg_val:
                mfg_val = d.corrected_value or d.extracted_value
            if d.field_name in ("batch_code", "lot_number") and not batch_val:
                batch_val = d.corrected_value or d.extracted_value

        checks = insp.compliance_checks or []
        non_comp = sum(1 for c in checks if c.result_state == "POTENTIAL_NON_COMPLIANCE")

        items.append(RepositoryInspectionItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=p_name,
            brand_name=b_name,
            category=c_name,
            manufacturer=mfg_val,
            batch_number=batch_val,
            location=insp.location,
            inspector_id=i_officer_id,
            inspector_name=i_name,
            status=insp.status,
            overall_status=insp.overall_status,
            findings_count=len(checks),
            non_compliant_count=non_comp,
            has_report=insp.report is not None,
            report_id=insp.report.id if insp.report else None,
            created_at=insp.created_at,
            finalized_at=insp.finalized_at
        ))

    return RepositoryInspectionsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.get("/api/repository/reports", response_model=RepositoryReportsResponse, tags=["Repository & Search"])
def search_repository_reports(
    search: Optional[str] = Query(None, description="Search by report ID, inspection number, product, brand, inspector"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    inspector_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search and retrieval facility for statutory inspection reports."""
    query = db.query(Report).join(Inspection, Report.inspection_id == Inspection.id).outerjoin(Product, Inspection.id == Product.inspection_id).outerjoin(User, Inspection.inspector_id == User.id)

    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)
    elif inspector_id:
        query = query.filter(
            or_(
                Inspection.inspector_id == inspector_id,
                User.officer_id == inspector_id
            )
        )

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Report.id.ilike(term),
                Inspection.id.ilike(term),
                Inspection.inspection_number.ilike(term),
                Product.product_name.ilike(term),
                Product.brand_name.ilike(term),
                User.officer_id.ilike(term),
                User.full_name.ilike(term)
            )
        )

    if start_date:
        parsed_start = _parse_dashboard_date_filter(start_date, is_end_date=False)
        query = query.filter(Report.generated_at >= parsed_start)
    if end_date:
        parsed_end = _parse_dashboard_date_filter(end_date, is_end_date=True)
        query = query.filter(Report.generated_at <= parsed_end)

    total = query.count()
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    offset = (page - 1) * page_size

    rows = query.options(
        joinedload(Report.inspection).joinedload(Inspection.product),
        joinedload(Report.inspection).joinedload(Inspection.inspector)
    ).order_by(Report.generated_at.desc()).offset(offset).limit(page_size).all()

    items: List[RepositoryReportItem] = []
    for r in rows:
        insp = r.inspection
        prod = insp.product if insp else None
        officer = insp.inspector if insp else None

        items.append(RepositoryReportItem(
            id=r.id,
            inspection_id=r.inspection_id,
            inspection_number=insp.inspection_number if insp else "Unknown",
            product_name=prod.product_name if prod else None,
            brand_name=prod.brand_name if prod else None,
            category=prod.category if prod else None,
            report_version=r.report_version,
            download_url=f"/api/inspections/{r.inspection_id}/report/pdf",
            inspector_id=officer.officer_id if officer else None,
            inspector_name=officer.full_name if officer else None,
            generated_at=r.generated_at,
            legal_safety_statement=r.legal_safety_statement,
            overall_status=insp.overall_status if insp else None,
            pdf_hash=getattr(r, "pdf_hash", None)
        ))

    return RepositoryReportsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


# ----------------- Inspection Endpoints -----------------

@app.post("/api/inspections", response_model=InspectionDetailResponse, status_code=status.HTTP_201_CREATED, tags=["Inspections"])
def create_inspection(
    req: CreateInspectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_inspector)
):
    """Creates a new inspection in DRAFT status with associated product details."""
    if not req.product_name.strip():
        raise HTTPException(status_code=400, detail="Product name is required")
    if not req.location.strip():
        raise HTTPException(status_code=400, detail="Inspection location is required")
    # NOTE: category is validated by Pydantic Literal — invalid values never reach here.

    # Dedicated draft id for offline idempotency
    draft_id: Optional[str] = req.client_draft_id.strip() if req.client_draft_id and req.client_draft_id.strip() else None

    # --- Fast path (no lock) ---
    # If the inspection is already committed (e.g., a delayed retry) skip the lock entirely.
    if draft_id:
        existing = _fetch_existing_draft(db, current_user.id, draft_id)
        if existing:
            return existing

    # --- Atomic allocation & creation (AUDIT-CONCUR-01) ---
    # Draft idempotency within process is guarded by _creation_lock.
    # Inspection number allocation is atomic at the database row level via inspection_number_counters.
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        with _creation_lock:
            # Re-check draft idempotency inside lock: the winning thread may have committed while we waited.
            if draft_id:
                existing = _fetch_existing_draft(db, current_user.id, draft_id)
                if existing:
                    return existing

            # Atomically allocate the next sequential number from DB counter
            inspection_number = allocate_inspection_number(db)

            notes_val = req.notes.strip() if req.notes and req.notes.strip() else None

            new_inspection = Inspection(
                inspection_number=inspection_number,
                inspector_id=current_user.id,
                location=req.location.strip(),
                status="DRAFT",
                inspection_type=req.inspection_type or "PHYSICAL",
                notes=notes_val,
                client_draft_id=draft_id
            )
            db.add(new_inspection)
            db.flush()  # assigns new_inspection.id before the commit

            new_product = Product(
                inspection_id=new_inspection.id,
                product_name=req.product_name.strip(),
                brand_name=req.brand_name.strip() if req.brand_name else None,
                category=req.category.strip(),
                batch_number=req.batch_number.strip() if req.batch_number else None
            )
            db.add(new_product)

            log_audit(
                db, current_user.officer_id,
                "INSPECTION_CREATED", "inspection",
                new_inspection.id, new_inspection.id,
                details=f"Created {inspection_number}"
            )

            try:
                db.commit()
            except IntegrityError as exc:
                # Defensive safety net: if the DB-level UNIQUE constraint fires,
                # roll back and retry with a freshly allocated number.
                db.rollback()
                if draft_id:
                    winner = _fetch_existing_draft(db, current_user.id, draft_id)
                    if winner:
                        return winner
                if attempt < MAX_RETRIES - 1:
                    continue
                raise HTTPException(
                    status_code=409,
                    detail="Inspection number conflict — please retry."
                ) from exc

            db.refresh(new_inspection)
            return new_inspection

    return new_inspection


@app.get("/api/inspections", response_model=List[InspectionDetailResponse], tags=["Inspections"])
def list_inspections(
    status: Optional[str] = Query(None, description="Filter by inspection status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists inspections with optional status filtering and pagination."""
    query = db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.images),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.report)
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)
    if status:
        query = query.filter(Inspection.status == status)
    return query.order_by(Inspection.created_at.desc()).offset(offset).limit(limit).all()

@app.get("/api/inspections/recent", response_model=List[RecentInspectionItem], tags=["Inspections"])
def get_recent_inspections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns top 5 most recent inspections."""
    query = db.query(Inspection).options(
        joinedload(Inspection.product)
    )
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        query = query.filter(Inspection.inspector_id == current_user.id)
    recent_objs = query.order_by(Inspection.created_at.desc()).limit(5).all()
    return [
        RecentInspectionItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=insp.product.product_name if insp.product else "Unnamed Commodity",
            location=insp.location,
            status=insp.status,
            overall_status=insp.overall_status,
            created_at=insp.created_at
        )
        for insp in recent_objs
    ]

@app.get("/api/inspections/{inspection_id}", response_model=InspectionDetailResponse, tags=["Inspections"])
def get_inspection_details(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves single inspection details by ID or inspection number."""
    inspection = db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.images),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.report),
        joinedload(Inspection.listing)
    ).filter(
        or_(
            Inspection.id == inspection_id,
            Inspection.inspection_number == inspection_id
        )
    ).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)
    return inspection

# ----------------- Image Endpoints -----------------

@app.post("/api/inspections/{inspection_id}/images", response_model=ProductImageResponse, status_code=status.HTTP_201_CREATED, tags=["Images"])
async def upload_inspection_image(
    inspection_id: str,
    file: UploadFile = File(..., description="Package label image"),
    view_type: str = Form("front", description="Image view type: front, back, panel, side, other"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Uploads a package image for an inspection, stores it safely on disk, and runs quality assessment."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent image upload/replacement on completed/finalized inspections or generated reports
    if inspection.status == "COMPLETED" or inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Official inspection evidence cannot be modified, uploaded, or replaced after inspection finalization or report generation."
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file.content_type}'. Allowed types: JPEG, PNG, WEBP."
        )

    content = await file.read()
    file_size = len(content)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds maximum size of 15MB")
    if file_size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        from io import BytesIO
        pil_img = Image.open(BytesIO(content))
        pil_img.verify()
        pil_img = Image.open(BytesIO(content))
        width, height = pil_img.size
        img_format = pil_img.format.lower()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted image file: {str(e)}")

    target_dir = UPLOADS_DIR / "inspections" / inspection_id
    target_dir.mkdir(parents=True, exist_ok=True)

    file_ext = ".jpg" if img_format == "jpeg" else f".{img_format}"
    orig_stem = re.sub(r'[^a-zA-Z0-9_-]', '_', Path(file.filename or 'img').stem)
    safe_filename = f"{uuid.uuid4().hex}_{orig_stem}_{view_type.lower()}{file_ext}"
    dest_path = target_dir / safe_filename

    # Use Supabase Storage Service (with local filesystem fallback)
    rel_file_path = storage_service.upload_image(
        inspection_id=inspection_id,
        filename=safe_filename,
        file_bytes=content,
        content_type=file.content_type
    )

    try:
        quality_res = assess_image_quality(str(dest_path))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image quality assessment failed: {str(e)}")

    # Canonical slot replacement: remove any existing image of the same view_type
    # to guarantee retake does not create duplicate or stale images in the DB or on disk.
    existing_images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id,
        ProductImage.view_type == view_type.lower()
    ).all()
    for old_img in existing_images:
        try:
            old_rel = old_img.file_path.lstrip("/")
            old_abs = BASE_DIR / old_rel
            if old_abs.exists() and old_abs != dest_path:
                old_abs.unlink()
        except Exception:
            pass
        db.delete(old_img)
    db.flush()

    seq_order = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).count() + 1

    product_image = ProductImage(
        inspection_id=inspection_id,
        original_filename=file.filename,
        file_path=rel_file_path,
        mime_type=file.content_type,
        file_size=file_size,
        width=width,
        height=height,
        sequence_order=seq_order,
        view_type=view_type.lower(),
        blur_score=quality_res.blur_score,
        glare_score=quality_res.brightness_score,
        quality_score=quality_res.quality_score,
        quality_status=quality_res.quality_status,
        quality_metadata_json=json.dumps(quality_res.to_dict()),
        processing_status="QUALITY_CHECKED"
    )
    db.add(product_image)

    if inspection.status == "DRAFT":
        inspection.status = "IMAGES_UPLOADED"

    log_audit(db, current_user.officer_id, "IMAGE_UPLOADED", "image", product_image.id, inspection_id, details=f"Uploaded {view_type} image")
    db.commit()
    db.refresh(product_image)

    return serialize_image_response(product_image)

@app.get("/api/inspections/{inspection_id}/images", response_model=List[ProductImageResponse], tags=["Images"])
def list_inspection_images(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists all uploaded package images for an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id
    ).order_by(ProductImage.sequence_order.asc()).all()

    return [serialize_image_response(img) for img in images]

@app.get("/api/images/{image_id}", response_model=ProductImageResponse, tags=["Images"])
def get_image_metadata(
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves metadata and quality scores for a specific image."""
    img = db.query(ProductImage).filter(ProductImage.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image record not found")
    verify_inspection_access(img.inspection, current_user, allow_supervisory=True)

    return serialize_image_response(img)

@app.get("/api/images/{image_id}/file", tags=["Images"])
def get_image_binary(
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Streams original binary image file for viewing."""
    img = db.query(ProductImage).filter(ProductImage.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image record not found")
    verify_inspection_access(img.inspection, current_user, allow_supervisory=True)

    clean_rel = img.file_path.lstrip("/")
    abs_path = BASE_DIR / clean_rel
    if not abs_path.exists():
        if storage_service.is_configured:
            try:
                # Fallback: fetch from Supabase Storage
                filename = abs_path.name
                url = f"{storage_service.supabase_url}/storage/v1/object/{storage_service.bucket_images}/inspections/{img.inspection_id}/{filename}"
                headers = {"Authorization": f"Bearer {storage_service.supabase_key}"}
                import httpx
                response = httpx.get(url, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(abs_path, "wb") as f:
                        f.write(response.content)
                else:
                    raise HTTPException(status_code=404, detail="Image file not found on disk or storage bucket")
            except Exception as e:
                raise HTTPException(status_code=404, detail=f"Image file not found and storage fallback failed: {str(e)}")
        else:
            raise HTTPException(status_code=404, detail="Image file not found on disk")

    return FileResponse(str(abs_path), media_type=img.mime_type or "image/jpeg")

@app.delete("/api/images/{image_id}", status_code=status.HTTP_200_OK, tags=["Images"])
def delete_inspection_image(
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deletes an uploaded package image record and removes file from disk."""
    img = db.query(ProductImage).filter(ProductImage.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image record not found")
    verify_inspection_access(img.inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent deletion of images belonging to completed/finalized inspections or generated reports
    if img.inspection.status == "COMPLETED" or img.inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Official inspection evidence cannot be deleted after inspection finalization or report generation."
        )

    clean_rel = img.file_path.lstrip("/")
    abs_path = BASE_DIR / clean_rel
    if abs_path.exists():
        try:
            abs_path.unlink()
        except Exception:
            pass

    inspection_id = img.inspection_id
    db.delete(img)
    db.commit()

    remaining_count = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).count()
    if remaining_count == 0:
        insp = db.query(Inspection).filter(Inspection.id == inspection_id).first()
        if insp and insp.status == "IMAGES_UPLOADED":
            insp.status = "DRAFT"
            db.commit()

    return {"message": "Image deleted successfully", "image_id": image_id}

@app.delete("/api/inspections/{inspection_id}/images/slot/{view_type}", status_code=status.HTTP_200_OK, tags=["Images"])
def delete_inspection_image_by_slot(
    inspection_id: str,
    view_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Deletes an uploaded package image by its view type slot (front, back, side)."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    if inspection.status == "COMPLETED" or inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Official inspection evidence cannot be deleted after inspection finalization or report generation."
        )

    images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id,
        ProductImage.view_type == view_type.lower()
    ).all()

    for img in images:
        clean_rel = img.file_path.lstrip("/")
        abs_path = BASE_DIR / clean_rel
        if abs_path.exists():
            try:
                abs_path.unlink()
            except Exception:
                pass
        db.delete(img)
    db.commit()

    remaining_count = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).count()
    if remaining_count == 0:
        if inspection.status == "IMAGES_UPLOADED":
            inspection.status = "DRAFT"
            db.commit()

    return {"message": f"Images for slot {view_type} deleted successfully", "deleted_count": len(images)}


@app.post("/api/quality-check", response_model=QualityCheckResponse, tags=["Images"])
async def check_image_quality_endpoint(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    On-demand package image quality evaluation powered by BlurDetection2 and OpenCV.
    Accepts raw image bytes, evaluates blur with resolution normalization, glare,
    contrast, and resolution without requiring an existing inspection ID.
    Returns structured data matching the BlurDetection2 contract.
    """
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Must be JPEG or PNG."
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    try:
        quality_res = assess_image_quality(content, image_id=file.filename)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Corrupted or invalid image: {str(ve)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quality check failed: {str(e)}"
        )

    details = ImageQualityDetails(**quality_res.to_dict())

    return QualityCheckResponse(
        status=quality_res.status,
        quality_decision=quality_res.quality_decision,
        blur_score=quality_res.blur_score,
        engine=quality_res.engine,
        image_id=file.filename,
        timestamp=quality_res.timestamp,
        reason=quality_res.recommendation,
        quality_status=quality_res.quality_status,
        quality_score=quality_res.quality_score,
        details=details
    )

import threading
_ocr_active_events: dict = {}
_ocr_active_lock = threading.Lock()

def _build_existing_ocr_response(inspection_id: str, db: Session) -> Optional[RunOCRResponse]:
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection or inspection.status != "EXTRACTION_COMPLETE":
        return None
    existing_decls = db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all()
    if not existing_decls:
        return None
    images = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).all()
    img_ids = [img.id for img in images]
    existing_ocr = db.query(OCRResult).filter(OCRResult.image_id.in_(img_ids)).all() if img_ids else []

    conflicts_list = []
    for d in existing_decls:
        if d.correction_reason:
            try:
                cdata = json.loads(d.correction_reason)
                if isinstance(cdata, dict) and cdata.get("conflict"):
                    conflicts_list.append(cdata)
            except Exception:
                pass

    per_img_bc = {}
    for img in images:
        if img.quality_metadata_json:
            try:
                q_meta = json.loads(img.quality_metadata_json)
                if "barcodes" in q_meta:
                    from backend.schemas import BarcodeItem
                    per_img_bc[img.id] = [BarcodeItem(**b) for b in q_meta["barcodes"]]
            except Exception:
                pass
    cons_bc = barcode_service.consolidate_multi_image_barcodes(per_img_bc) if per_img_bc else None

    logger.info(
        f"[OCR_IDEMPOTENT_REUSE] inspection_id={inspection_id} "
        f"Returning existing {len(existing_decls)} declarations and {len(existing_ocr)} OCR results without re-running"
    )
    return RunOCRResponse(
        inspection_id=str(inspection_id),
        status="EXTRACTION_COMPLETE",
        total_images_processed=len(images),
        declarations_count=len(existing_decls),
        ocr_results=[serialize_ocr_result(r) for r in existing_ocr],
        declarations=[serialize_declaration(d) for d in existing_decls],
        conflicts=conflicts_list,
        barcodes=BarcodeInspectionSummaryResponse(**cons_bc.model_dump()) if cons_bc else None
    )

from contextlib import contextmanager

@contextmanager
def _ocr_concurrency_guard(inspection_id: str):
    with _ocr_active_lock:
        event = _ocr_active_events.get(inspection_id)
        if event is None:
            event = threading.Event()
            _ocr_active_events[inspection_id] = event
            is_primary = True
        else:
            is_primary = False
    try:
        yield is_primary, event
    finally:
        if is_primary:
            with _ocr_active_lock:
                ev = _ocr_active_events.pop(inspection_id, None)
                if ev:
                    ev.set()

@app.post("/api/inspections/{inspection_id}/ocr", response_model=RunOCRResponse, tags=["OCR & Declarations"])
def run_inspection_ocr_and_extraction(
    inspection_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Executes OCR and structured declaration parsing on uploaded package images."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent OCR re-run/modification on completed/finalized inspections or generated reports
    if inspection.status == "COMPLETED" or inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot run or modify OCR for an inspection that has been finalized or has an official report."
        )

    # 1. Fast path: Idempotent re-use of already extracted declarations
    if not force:
        cached_resp = _build_existing_ocr_response(inspection_id, db)
        if cached_resp:
            return cached_resp

    images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id
    ).order_by(ProductImage.sequence_order.asc()).all()

    if not images:
        raise HTTPException(status_code=400, detail="Cannot run OCR: No images uploaded for this inspection")

    with _ocr_concurrency_guard(inspection_id) as (is_primary_worker, in_flight_event):
        if not is_primary_worker:
            logger.info(f"[OCR_CONCURRENCY_WAIT] inspection_id={inspection_id} Waiting for active OCR inference")
            db.close()
            in_flight_event.wait(timeout=600.0)
            cached_resp = _build_existing_ocr_response(inspection_id, db)
            if cached_resp:
                return cached_resp
            reloaded = db.query(Inspection).filter(Inspection.id == inspection_id).first()
            if reloaded and reloaded.status == "OCR_PROCESSING":
                raise HTTPException(status_code=504, detail="OCR processing timed out on concurrent worker")

        t_ocr_req_start = time.time()
        ocr_req_id = uuid.uuid4().hex[:8]
        logger.info(
            f"[OCR_START] req_id={ocr_req_id} inspection_id={inspection_id} "
            f"num_images={len(images)}"
        )

        inspection.status = "OCR_PROCESSING"
        db.commit()

    # --- CRITICAL: Extract ALL needed primitive values before closing the session ---
    # After db.close(), ALL ORM objects (inspection, images, current_user) become detached.
    # Any attribute access on detached ORM objects raises DetachedInstanceError.
    # We must eagerly convert all needed ORM attributes to plain Python values NOW.

    image_specs = [
        (img.id, img.file_path, img.quality_metadata_json)
        for img in images
    ]
    _product = inspection.product  # trigger lazy load while session still active
    product_ctx = {
        "product_name": _product.product_name if _product else "",
        "brand_name": _product.brand_name if _product else "",
        "category": _product.category if _product else "Packaged Food"
    }
    # Extract all primitive fields needed after OCR
    inspector_officer_id: str = str(current_user.officer_id)
    inspection_id_str: str = str(inspection_id)

    # CRITICAL: Close/return the connection to the pool IMMEDIATELY before PaddleOCR inference.
    # Neon (Serverless PostgreSQL) enforces a 5-minute idle-in-transaction timeout.
    # PaddleOCR on CPU can take 2–10 minutes per image without downscaling.
    # After db.commit(), SQLAlchemy still holds a connection open for the next query.
    # db.close() returns the connection to the pool; the session can reconnect later.
    db.close()
    logger.info(f"[DB_SESSION_CLOSED] req_id={ocr_req_id} Connection returned to pool before OCR inference")

    all_raw_text_parts = []
    all_boxes = []
    per_image_declarations = {}
    per_image_barcodes = {}
    ocr_processed_items = []

    # ------------------------------------------------------------------
    # SEQUENTIAL PER-IMAGE OCR
    # Images are processed sequentially.  Concurrent inference on the shared
    # PaddleOCR CPU singleton was benchmarked and rejected:
    #   - Concurrent 2-img (warm): 38.58s — 15% SLOWER than sequential
    #   - img1 accuracy dropped: 3→2 boxes, conf 0.99→0.69, corrupted text
    # Root cause: PaddleOCR shares BLAS thread pools; concurrent predict()
    # calls on the same singleton cause CPU bandwidth contention and
    # non-deterministic buffer reads that corrupt OCR output.
    # With OCR_WARMUP_ON_STARTUP=True, warm sequential latency is ~33s for
    # 2 images — a 4.23x improvement over the 142s cold baseline.
    # ------------------------------------------------------------------
    for idx, (img_id, img_file_path, img_quality_meta) in enumerate(image_specs, 1):
        clean_rel = img_file_path.lstrip("/")
        abs_path = BASE_DIR / clean_rel
        if not abs_path.exists():
            logger.warning(f"[IMAGE_LOAD_MISSING] req_id={ocr_req_id} path={abs_path}")
            continue

        t_img_start = time.time()
        logger.info(f"[IMAGE_{idx}_OCR_START] req_id={ocr_req_id} img_id={img_id} path={clean_rel}")
        ocr_data = ocr_service.process_image(str(abs_path), image_id=img_id)
        t_img_ocr = time.time() - t_img_start
        logger.info(
            f"[IMAGE_{idx}_OCR_END] req_id={ocr_req_id} img_id={img_id} "
            f"duration={t_img_ocr:.2f}s boxes={len(ocr_data.text_boxes)} "
            f"mean_conf={ocr_data.mean_confidence:.2f} engine={ocr_data.engine_used}"
        )

        # Barcode & QR Code decoding + OCR cross-validation
        t_bc_start = time.time()
        img_barcodes = barcode_service.detect_and_decode(str(abs_path), source_image_id=img_id, source_image_path=img_file_path)
        img_barcodes = barcode_service.cross_validate_with_ocr(img_barcodes, ocr_data.raw_text)
        per_image_barcodes[img_id] = img_barcodes
        t_bc = time.time() - t_bc_start

        # Extract declarations for this individual image
        t_decl_start = time.time()
        logger.info(f"[DECLARATION_EXTRACTION_START] req_id={ocr_req_id} idx={idx} img_id={img_id}")
        img_ctx = dict(product_ctx)
        img_ctx["ocr_status"] = getattr(ocr_data, "ocr_status", "OCR_SUCCESS")
        img_items = extraction_service.extract_declarations(
            full_text=ocr_data.raw_text,
            text_boxes=ocr_data.text_boxes,
            product_context=img_ctx,
            image_id=img_id,
            image_path=img_file_path
        )
        t_decl = time.time() - t_decl_start
        logger.info(f"[DECLARATION_EXTRACTION_END] req_id={ocr_req_id} idx={idx} items={len(img_items)} duration={t_decl:.2f}s")
        per_image_declarations[img_id] = img_items

        if ocr_data.raw_text:
            all_raw_text_parts.append(ocr_data.raw_text)
        all_boxes.extend(ocr_data.text_boxes)

        ocr_processed_items.append((img_id, ocr_data, img_barcodes))

    logger.info(f"[DB_WRITE_START] req_id={ocr_req_id} Reconnecting DB session for persistence")
    # Re-connect to DB to persist OCR and barcode results in a fast, dedicated transaction
    saved_ocr_results = []
    for img_id, ocr_data, img_barcodes in ocr_processed_items:
        existing_ocr = db.query(OCRResult).filter(OCRResult.image_id == img_id).first()
        boxes_dict = [b.model_dump() for b in ocr_data.text_boxes]
        
        if existing_ocr:
            existing_ocr.raw_text = ocr_data.raw_text
            existing_ocr.confidence = ocr_data.mean_confidence
            existing_ocr.bounding_boxes_json = json.dumps(boxes_dict)
            ocr_record = existing_ocr
        else:
            ocr_record = OCRResult(
                image_id=img_id,
                raw_text=ocr_data.raw_text,
                confidence=ocr_data.mean_confidence,
                bounding_boxes_json=json.dumps(boxes_dict)
            )
            db.add(ocr_record)

        saved_ocr_results.append(ocr_record)

        # Persist barcode items in image quality metadata for fast retrieval
        try:
            db_img = db.query(ProductImage).filter(ProductImage.id == img_id).first()
            if db_img:
                meta = json.loads(db_img.quality_metadata_json) if db_img.quality_metadata_json else {}
                meta["barcodes"] = [b.model_dump() for b in img_barcodes]
                db_img.quality_metadata_json = json.dumps(meta)
        except Exception:
            pass

    db.flush()

    # Consolidate multi-image barcode evidence
    consolidated_barcodes = barcode_service.consolidate_multi_image_barcodes(per_image_barcodes)

    combined_full_text = "\n".join(all_raw_text_parts)
    primary_image_id = image_specs[0][0] if image_specs else None

    # Cross-image verification and conflict detection across all images
    logger.info(f"[CROSS_IMAGE_CONSOLIDATION_START] req_id={ocr_req_id}")
    merged_items, detected_conflicts = cross_image_verification(per_image_declarations)
    logger.info(
        f"[CROSS_IMAGE_CONSOLIDATION_END] req_id={ocr_req_id} "
        f"merged_declarations={len(merged_items)} conflicts={len(detected_conflicts)}"
    )

    # Fallback to combined text if any field was not found in per-image scans
    combined_items = extraction_service.extract_declarations(
        full_text=combined_full_text,
        text_boxes=all_boxes,
        product_context=product_ctx,
        image_id=primary_image_id
    )
    combined_map = {item.field_name: item for item in combined_items if item.extracted_value and item.extraction_status not in ["NOT_FOUND", "OCR_UNAVAILABLE"]}

    for item in merged_items:
        if (not item.extracted_value or item.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"]) and item.field_name in combined_map:
            fb = combined_map[item.field_name]
            item.extracted_value = fb.extracted_value
            item.normalized_value = fb.normalized_value
            item.confidence = fb.confidence
            item.bounding_box = fb.bounding_box
            item.extraction_status = fb.extraction_status
            item.source_image_id = primary_image_id

    db.query(Declaration).filter(Declaration.inspection_id == inspection_id).delete()
    db.flush()

    saved_declarations = []
    for item in merged_items:
        meta_dict = {}
        if item.has_conflict:
            meta_dict = {
                "conflict": True,
                "candidates": item.conflicts,
                "source_images": item.source_images
            }
            item.extraction_status = "CONFLICTING"
            v_status = "NEEDS_MANUAL_VERIFICATION"
        elif item.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"]:
            v_status = "NEEDS_MANUAL_VERIFICATION"
        else:
            v_status = "UNVERIFIED"

        if item.raw_text or item.layout_region:
            meta_dict["raw_text"] = item.raw_text
            meta_dict["layout_region"] = item.layout_region
            meta_dict["layout_bbox"] = item.layout_bbox

        reason_val = json.dumps(meta_dict) if meta_dict else None

        decl = Declaration(
            inspection_id=inspection_id,
            field_name=item.field_name,
            extracted_value=item.extracted_value,
            normalized_value=item.normalized_value,
            confidence=item.confidence,
            bounding_box_json=json.dumps(item.bounding_box) if item.bounding_box else None,
            extraction_status=item.extraction_status,
            is_applicable=item.is_applicable,
            verification_status=v_status,
            correction_reason=reason_val,
            source_image_id=item.source_image_id or primary_image_id
        )
        db.add(decl)
        saved_declarations.append(decl)

    # Build and persist Unified Declaration Compliance Matrix (Placement, Font Size, Readability, Format)
    try:
        all_imgs = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id_str).all()
        matrix_rows = declaration_validation_engine.build_declaration_matrix(saved_declarations, all_imgs)
        matrix_row_map = {r.field_name: r for r in matrix_rows}
        for decl in saved_declarations:
            r = matrix_row_map.get(decl.field_name)
            if r:
                decl.placement_status = r.placement_status
                decl.placement_details_json = json.dumps({"expected_panel": r.placement_status, "statutory_ref": r.statutory_reference})
                decl.font_size_status = r.font_size_status
                decl.font_size_details_json = json.dumps({"status": r.font_size_status})
                decl.readability_status = r.readability_status
                decl.readability_details_json = json.dumps({"status": r.readability_status, "confidence": decl.confidence})
                decl.format_status = r.format_status
                decl.format_details_json = json.dumps({"findings": r.findings, "explanation": r.explanation})
                decl.validation_matrix_json = json.dumps(r.model_dump())
    except Exception as e:
        logger.warning(f"[DECLARATION_MATRIX_BUILD_WARN] {e}")

    # Re-attach inspection to session for final status update and audit log
    # (The session auto-reconnects to the DB on this query)
    db_inspection = db.query(Inspection).filter(Inspection.id == inspection_id_str).first()
    if db_inspection:
        db_inspection.status = "EXTRACTION_COMPLETE"
    log_audit(
        db,
        inspector_officer_id,
        "OCR_AND_EXTRACTION_COMPLETED",
        "inspection",
        inspection_id_str,
        inspection_id_str,
        details=f"Extracted {len(saved_declarations)} statutory declarations. Conflicts: {len(detected_conflicts)}"
    )
    db.commit()
    t_db_end = time.time()
    logger.info(
        f"[DB_WRITE_END] req_id={ocr_req_id} saved_decls={len(saved_declarations)} "
        f"db_status={db_inspection.status if db_inspection else 'UNKNOWN'}"
    )

    final_status = db_inspection.status if db_inspection else "EXTRACTION_COMPLETE"
    total_req_time = t_db_end - t_ocr_req_start

    logger.info(
        f"[HTTP_RESPONSE_START] req_id={ocr_req_id} total_elapsed={total_req_time:.2f}s "
        f"status={final_status}"
    )

    response_obj = RunOCRResponse(
        inspection_id=inspection_id_str,
        status=final_status,
        total_images_processed=len(image_specs),
        declarations_count=len(saved_declarations),
        ocr_results=[serialize_ocr_result(r) for r in saved_ocr_results],
        declarations=[serialize_declaration(d) for d in saved_declarations],
        conflicts=detected_conflicts,
        barcodes=BarcodeInspectionSummaryResponse(**consolidated_barcodes.model_dump()) if consolidated_barcodes else None
    )

    logger.info(f"[HTTP_RESPONSE_END] req_id={ocr_req_id} Returning 200 OK")
    return response_obj

@app.get("/api/inspections/{inspection_id}/barcodes", response_model=BarcodeInspectionSummaryResponse, tags=["Barcodes"])
def get_inspection_barcodes(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves consolidated barcode and QR code evidence for an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id
    ).order_by(ProductImage.sequence_order.asc()).all()

    per_image_barcodes = {}
    for img in images:
        clean_rel = img.file_path.lstrip("/")
        abs_path = BASE_DIR / clean_rel

        items = []
        if img.quality_metadata_json:
            try:
                meta = json.loads(img.quality_metadata_json)
                if "barcodes" in meta and isinstance(meta["barcodes"], list):
                    items = [BarcodeItem(**b) for b in meta["barcodes"]]
            except Exception:
                items = []

        if not items and abs_path.exists():
            items = barcode_service.detect_and_decode(str(abs_path), source_image_id=img.id, source_image_path=img.file_path)
            ocr_rec = db.query(OCRResult).filter(OCRResult.image_id == img.id).first()
            if ocr_rec and ocr_rec.raw_text:
                items = barcode_service.cross_validate_with_ocr(items, ocr_rec.raw_text)

        per_image_barcodes[img.id] = items

    summary = barcode_service.consolidate_multi_image_barcodes(per_image_barcodes)
    return BarcodeInspectionSummaryResponse(**summary.model_dump())

@app.get("/api/inspections/{inspection_id}/ocr", response_model=List[OCRResultResponse], tags=["OCR & Declarations"])
def get_inspection_ocr_results(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves raw OCR text and bounding boxes for all images in an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    image_ids = [img.id for img in inspection.images]
    ocr_results = db.query(OCRResult).filter(OCRResult.image_id.in_(image_ids)).all() if image_ids else []

    return [serialize_ocr_result(r) for r in ocr_results]

@app.get("/api/inspections/{inspection_id}/declarations", response_model=List[DeclarationResponse], tags=["OCR & Declarations"])
def get_inspection_declarations(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves extracted structured declarations for an inspection."""
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    declarations = db.query(Declaration).filter(
        Declaration.inspection_id == inspection.id
    ).order_by(Declaration.created_at.asc()).all()

    return [serialize_declaration(d) for d in declarations]

@app.get("/api/inspections/{inspection_id}/declarations/{field_name}", response_model=DeclarationResponse, tags=["OCR & Declarations"])
def get_single_declaration(
    inspection_id: str,
    field_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves a single declaration field by name."""
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    decl = db.query(Declaration).filter(
        Declaration.inspection_id == inspection.id,
        Declaration.field_name == field_name
    ).first()

    if not decl:
        raise HTTPException(status_code=404, detail=f"Declaration field '{field_name}' not found")

    return serialize_declaration(decl)

@app.get("/api/inspections/{inspection_id}/declaration-validation", response_model=DeclarationValidationMatrixResponse, tags=["OCR & Declarations"])
def get_inspection_declaration_validation(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the Unified Declaration Compliance Matrix for an inspection.
    Evaluates Presence, Correctness, Readability, Placement, Font Size, and Format under PCR 2011.
    """
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection.id).all()
    images = db.query(ProductImage).filter(ProductImage.inspection_id == inspection.id).all()

    matrix_rows = declaration_validation_engine.build_declaration_matrix(declarations, images)

    compliant_count = sum(1 for r in matrix_rows if r.overall_status == "COMPLIANT")
    pot_viol_count = sum(1 for r in matrix_rows if r.overall_status == "POTENTIAL_NON_COMPLIANCE")
    manual_ver_count = sum(1 for r in matrix_rows if r.overall_status == "MANUAL_VERIFICATION_REQUIRED")

    row_schemas = [DeclarationMatrixRowSchema(**r.model_dump()) for r in matrix_rows]

    return DeclarationValidationMatrixResponse(
        inspection_id=inspection.id,
        rows=row_schemas,
        total_mandatory=len(row_schemas),
        compliant_count=compliant_count,
        potential_violation_count=pot_viol_count,
        manual_verification_count=manual_ver_count,
        generated_at=datetime.utcnow().isoformat()
    )

@app.get("/api/inspections/{inspection_id}/compliance-summary", response_model=ComplianceSummaryResponse, tags=["Rule Engine & Adjudication"])
def get_inspection_compliance_summary(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns the aggregate statutory compliance summary for an inspection.
    Includes mandatory detection, placement, readability, font size, listing discrepancy metrics,
    and live inspection-specific rule compliance finding metrics.
    """
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    real_inspection_id = inspection.id

    declarations = db.query(Declaration).filter(Declaration.inspection_id == real_inspection_id).all()
    images = db.query(ProductImage).filter(ProductImage.inspection_id == real_inspection_id).all()
    listing_comps = db.query(ListingComparison).filter(ListingComparison.inspection_id == real_inspection_id).all()

    matrix_rows = declaration_validation_engine.build_declaration_matrix(declarations, images)
    summary_data = declaration_validation_engine.compute_compliance_summary(matrix_rows, listing_comps)

    checks = db.query(ComplianceCheck).filter(
        ComplianceCheck.inspection_id == real_inspection_id
    ).options(joinedload(ComplianceCheck.rule_version), joinedload(ComplianceCheck.evidence)).order_by(ComplianceCheck.created_at.asc()).all()

    evaluation_completed = (
        inspection.status in ("RULE_EVALUATION_COMPLETE", "REPORT_GENERATED", "COMPLETED")
        or len(checks) > 0
    )

    # Canonical mutually exclusive compliance metrics
    metrics = compute_canonical_compliance_metrics(checks)
    compliant_checks = metrics["compliant_checks"]
    no_potential_violations = compliant_checks
    potential_non_compliance = metrics["potential_non_compliance"]
    needs_manual_verification = metrics["needs_manual_verification"]
    warnings = metrics["warnings"]

    serialized_findings = [serialize_finding(c) for c in checks]

    logger.info(
        "Compliance summary for %s (id=%s): total_checks=%d, compliant=%d, non_comp=%d, manual=%d, warnings=%d, completed=%s",
        inspection.inspection_number, real_inspection_id, len(checks),
        compliant_checks, potential_non_compliance, needs_manual_verification, warnings, evaluation_completed
    )

    return ComplianceSummaryResponse(
        inspection_id=real_inspection_id,
        inspection_number=inspection.inspection_number,
        evaluation_completed=evaluation_completed,
        compliant_checks=compliant_checks,
        no_potential_violations=no_potential_violations,
        potential_non_compliance=potential_non_compliance,
        needs_manual_verification=needs_manual_verification,
        warnings=warnings,
        total_findings=len(checks),
        findings=serialized_findings,
        **summary_data.model_dump()
    )

@app.patch("/api/declarations/{declaration_id}", response_model=DeclarationResponse, tags=["OCR & Declarations"])
def update_declaration(
    declaration_id: str,
    req: UpdateDeclarationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Updates an extracted declaration with officer verification or correction.
    Preserves original OCR value and original confidence immutably.
    """
    decl = db.query(Declaration).filter(Declaration.id == declaration_id).first()
    if not decl:
        raise HTTPException(status_code=404, detail="Declaration record not found")
    verify_inspection_access(decl.inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent declaration modification on completed/finalized inspections or generated reports
    if decl.inspection.status == "COMPLETED" or decl.inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Official inspection declarations cannot be modified after inspection finalization or report generation."
        )

    old_val = decl.effective_value

    if req.corrected_value is not None:
        decl.corrected_value = req.corrected_value.strip()
        decl.verification_status = req.verification_status if req.verification_status else "CORRECTED"
    elif req.verification_status is not None:
        decl.verification_status = req.verification_status

    if req.correction_reason is not None:
        decl.correction_reason = req.correction_reason.strip()
    if req.is_applicable is not None:
        decl.is_applicable = req.is_applicable

    decl.verified_by = current_user.officer_id
    decl.verified_at = datetime.utcnow()

    log_audit(
        db,
        current_user.officer_id,
        "DECLARATION_VERIFIED",
        "declaration",
        decl.id,
        decl.inspection_id,
        old_val=old_val,
        new_val=decl.effective_value,
        details=f"Field {decl.field_name} verified/corrected"
    )

    db.commit()
    db.refresh(decl)
    return serialize_declaration(decl)

# ----------------- Deterministic Rule Engine & Adjudication Endpoints -----------------

@app.post("/api/inspections/{inspection_id}/evaluate", response_model=EvaluateInspectionResponse, tags=["Rule Engine & Adjudication"])
def evaluate_inspection_rules(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Executes the deterministic Legal Metrology rule engine against verified/effective declarations.
    Generates potential non-compliance findings with photographic evidence and statutory references.
    AI is strictly excluded from compliance adjudication.
    """
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent rule re-evaluation on completed/finalized inspections or generated reports
    if inspection.status == "COMPLETED" or inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot evaluate or modify rules for an inspection that has been finalized or has an official report."
        )

    declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection.id).all()
    images = db.query(ProductImage).filter(ProductImage.inspection_id == inspection.id).all()

    product_data = {
        "product_name": inspection.product.product_name if inspection.product else "",
        "brand_name": inspection.product.brand_name if inspection.product else "",
        "category": inspection.product.category if inspection.product else "Packaged Food"
    }

    # Execute deterministic rule engine
    eval_results = rule_engine.evaluate_inspection(inspection.id, product_data, declarations, images)

    # Idempotent replacement of previous checks and evidence for this inspection
    existing_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection.id).all()
    check_ids = [c.id for c in existing_checks]
    if check_ids:
        db.query(Evidence).filter(Evidence.check_id.in_(check_ids)).delete(synchronize_session=False)
        db.query(ComplianceCheck).filter(ComplianceCheck.id.in_(check_ids)).delete(synchronize_session=False)
    db.flush()

    # Prefetch all rule versions in a single query to eliminate per-rule WAN roundtrips
    existing_rule_vers = {rv.rule_code: rv for rv in db.query(RuleVersion).all()}

    checks_to_add = []
    evidence_to_add = []
    findings = []
    passed_count = 0
    non_comp_count = 0
    insufficient_count = 0

    for res in eval_results:
        rule_ver = existing_rule_vers.get(res.rule_code)
        if not rule_ver:
            statutory_def = STATUTORY_RULE_REGISTRY.get(res.rule_code)
            if statutory_def:
                rule_ver = RuleVersion(
                    rule_code=statutory_def.rule_code,
                    version_number=statutory_def.rule_version,
                    title=statutory_def.title,
                    category=statutory_def.category,
                    statutory_reference=statutory_def.statutory_reference,
                    rule_logic_description=statutory_def.description,
                    severity=statutory_def.severity.value,
                    is_active=True
                )
                db.add(rule_ver)
                db.flush()
                existing_rule_vers[res.rule_code] = rule_ver
            else:
                # UNKNOWN RULE: Do NOT silently invent a rule!
                # It must NOT produce an automated compliance finding.
                rule_ver = existing_rule_vers.get("UNKNOWN_RULE")
                if not rule_ver:
                    rule_ver = db.query(RuleVersion).filter(RuleVersion.rule_code == "UNKNOWN_RULE").first()
                    if not rule_ver:
                        rule_ver = RuleVersion(
                            rule_code="UNKNOWN_RULE",
                            version_number=1,
                            title="Unknown Statutory Rule",
                            category="CATEGORY_UNKNOWN",
                            statutory_reference="UNVERIFIED - Unknown Rule Code",
                            rule_logic_description="Unverified statutory rule code requiring legal verification. Automated findings are prohibited.",
                            severity="MAJOR",
                            is_active=False
                        )
                        db.add(rule_ver)
                        db.flush()
                    existing_rule_vers["UNKNOWN_RULE"] = rule_ver
                
                res.result_state = RuleResultState.NEEDS_MANUAL_VERIFICATION
                res.title = f"Unknown Rule: {res.rule_code}"
                res.explanation = f"Needs Legal Verification: Rule code '{res.rule_code}' is unknown and unverified in the statutory Legal Metrology registry. The system will not invent arbitrary legal rules."
        rule_version_id = rule_ver.id
        check_id = str(uuid.uuid4())
        created_now = datetime.utcnow()

        check = ComplianceCheck(
            id=check_id,
            inspection_id=inspection.id,
            rule_version_id=rule_version_id,
            rule_code=res.rule_code,
            title=res.title,
            severity=res.severity.value,
            result_state=res.result_state.value,
            extracted_value=res.effective_value_used,
            explanation=res.explanation,
            adjudication_status="PENDING",
            created_at=created_now
        )
        checks_to_add.append(check)

        evidence_resp_items = []
        for ev_data in res.evidence_items:
            ev_id = str(uuid.uuid4())
            evidence = Evidence(
                id=ev_id,
                check_id=check_id,
                image_id=ev_data.image_id,
                bounding_box_json=json.dumps(ev_data.bounding_box) if ev_data.bounding_box else None,
                highlight_text=ev_data.highlight_text,
                reason=ev_data.reason,
                created_at=created_now
            )
            evidence_to_add.append(evidence)
            evidence_resp_items.append(EvidenceResponse(
                id=ev_id,
                check_id=check_id,
                image_id=ev_data.image_id,
                bounding_box=ev_data.bounding_box,
                crop_image_path=None,
                highlight_text=ev_data.highlight_text,
                reason=ev_data.reason,
                created_at=created_now
            ))

        findings.append(FindingResponse(
            id=check_id,
            inspection_id=inspection.id,
            rule_version_id=rule_version_id,
            rule_code=res.rule_code,
            rule_version_number=rule_ver.version_number if rule_ver else None,
            statutory_reference=rule_ver.statutory_reference if rule_ver else None,
            title=res.title,
            severity=res.severity.value,
            result_state=res.result_state.value,
            extracted_value=res.effective_value_used,
            explanation=res.explanation,
            adjudication_status="PENDING",
            adjudication_notes=None,
            adjudicated_by=None,
            adjudicated_at=None,
            created_at=created_now,
            evidence_items=evidence_resp_items
        ))

        if res.result_state == "PASS":
            passed_count += 1
        elif res.result_state == "POTENTIAL_NON_COMPLIANCE":
            non_comp_count += 1
        elif res.result_state in ["INSUFFICIENT_EVIDENCE", "NEEDS_MANUAL_VERIFICATION"]:
            insufficient_count += 1

    db.add_all(checks_to_add)
    db.add_all(evidence_to_add)

    # Update Inspection Status based on Rule Results
    if non_comp_count > 0:
        inspection.overall_status = "POTENTIAL_NON_COMPLIANCE"
    elif insufficient_count > 0:
        inspection.overall_status = "NEEDS_MANUAL_VERIFICATION"
    else:
        inspection.overall_status = "NO_POTENTIAL_VIOLATIONS"

    inspection.status = "RULE_EVALUATION_COMPLETE"

    # Collect conflicts from declarations for audit and response
    conflicts_list = []
    for d in declarations:
        if getattr(d, "extraction_status", "") == "CONFLICTING" or (d.correction_reason and d.correction_reason.startswith('{"conflict":')):
            try:
                cdata = json.loads(d.correction_reason)
                conflicts_list.append({
                    "field_name": d.field_name,
                    "candidates": cdata.get("candidates", []),
                    "source_images": cdata.get("source_images", [])
                })
            except Exception:
                pass

    log_audit(
        db,
        current_user.officer_id,
        "RULE_EVALUATION_EXECUTED",
        "inspection",
        inspection_id,
        inspection_id,
        details=f"Evaluated {len(eval_results)} statutory rules. Passed: {passed_count}, Potential Violations: {non_comp_count}, Insufficient/Manual: {insufficient_count}, Conflicts: {len(conflicts_list)}"
    )

    db.commit()
    db.refresh(inspection)

    return EvaluateInspectionResponse(
        inspection_id=inspection.id,
        status=inspection.status,
        overall_status=inspection.overall_status,
        total_rules_evaluated=len(eval_results),
        passed_count=passed_count,
        potential_non_compliance_count=non_comp_count,
        insufficient_evidence_count=insufficient_count,
        conflicts=conflicts_list,
        findings=findings
    )

@app.get("/api/inspections/{inspection_id}/findings", response_model=List[FindingResponse], tags=["Rule Engine & Adjudication"])
def get_inspection_findings(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all potential findings and compliance check results for an inspection."""
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    checks = db.query(ComplianceCheck).filter(
        ComplianceCheck.inspection_id == inspection.id
    ).order_by(ComplianceCheck.created_at.asc()).all()

    return [serialize_finding(c) for c in checks]

@app.get("/api/findings/{finding_id}", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
def get_single_finding(
    finding_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves details of a specific finding and its attached photographic evidence."""
    check = db.query(ComplianceCheck).filter(ComplianceCheck.id == finding_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Finding record not found")
    verify_inspection_access(check.inspection, current_user, allow_supervisory=True)

    return serialize_finding(check)

@app.patch("/api/findings/{finding_id}/adjudicate", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
@app.post("/api/findings/{finding_id}/adjudicate", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
@app.post("/api/compliance-checks/{finding_id}/adjudicate", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
def adjudicate_finding(
    finding_id: str,
    req: AdjudicateFindingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Records inspector adjudication on a potential non-compliance finding.
    Actions: CONFIRMED (confirms legal violation), DISMISSED (dismisses finding with reason), NEEDS_MORE_EVIDENCE.
    """
    valid_actions = {"CONFIRMED", "DISMISSED", "NEEDS_MORE_EVIDENCE", "NOT_APPLICABLE", "CORRECTED"}
    if req.action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action '{req.action}'. Allowed: {sorted(valid_actions)}")

    check = db.query(ComplianceCheck).filter(ComplianceCheck.id == finding_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Finding record not found")
    verify_inspection_access(check.inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent adjudication change on completed/finalized inspections or generated reports
    if check.inspection.status == "COMPLETED" or check.inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Official inspection findings cannot be adjudicated or modified after inspection finalization or report generation."
        )

    old_status = check.adjudication_status
    check.adjudication_status = req.action
    check.adjudication_notes = req.notes.strip() if req.notes else None
    check.adjudicated_by = current_user.officer_id
    check.adjudicated_at = datetime.utcnow()

    # For CORRECTED action: store the corrected value note for reference
    if req.action == "CORRECTED" and req.corrected_value:
        corrected_note = f"Inspector correction: {req.corrected_value.strip()}"
        if req.notes:
            check.adjudication_notes = f"{corrected_note} | Reason: {req.notes.strip()}"
        else:
            check.adjudication_notes = corrected_note

    review = InspectorReview(
        check_id=check.id,
        officer_id=current_user.id,
        action=req.action,
        remarks=check.adjudication_notes
    )
    db.add(review)

    # Recalculate Inspection Overall Status based on active findings
    # Only PENDING findings that are POTENTIAL_NON_COMPLIANCE or INSUFFICIENT_EVIDENCE are "unresolved"
    inspection = check.inspection
    all_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection.id).all()

    resolved_actions = {"CONFIRMED", "DISMISSED", "NOT_APPLICABLE", "CORRECTED"}

    has_confirmed_violations = any(
        c.adjudication_status == "CONFIRMED"
        for c in all_checks
    )
    has_pending_non_comp = any(
        c.result_state == "POTENTIAL_NON_COMPLIANCE" and c.adjudication_status == "PENDING"
        for c in all_checks
    )
    has_pending_insufficient = any(
        (c.result_state == "INSUFFICIENT_EVIDENCE" or c.adjudication_status == "NEEDS_MORE_EVIDENCE")
        and c.adjudication_status not in resolved_actions
        for c in all_checks
    )

    if has_confirmed_violations or has_pending_non_comp:
        inspection.overall_status = "POTENTIAL_NON_COMPLIANCE"
    elif has_pending_insufficient:
        inspection.overall_status = "NEEDS_MANUAL_VERIFICATION"
    else:
        inspection.overall_status = "NO_POTENTIAL_VIOLATIONS"

    log_audit(
        db,
        current_user.officer_id,
        "FINDING_ADJUDICATED",
        "compliance_check",
        check.id,
        inspection.id,
        old_val=old_status,
        new_val=req.action,
        details=f"Finding {check.rule_code} adjudicated as {req.action}. Notes: {req.notes}"
    )

    db.commit()
    db.refresh(check)
    return serialize_finding(check)

@app.get("/api/findings/{finding_id}/evidence", response_model=List[EvidenceResponse], tags=["Rule Engine & Adjudication"])
def get_finding_evidence(
    finding_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all attached photographic evidence items for a finding."""
    check = db.query(ComplianceCheck).filter(ComplianceCheck.id == finding_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Finding record not found")
    verify_inspection_access(check.inspection, current_user, allow_supervisory=True)

    evidence_items = db.query(Evidence).filter(Evidence.check_id == finding_id).all()
    res = []
    for ev in evidence_items:
        bbox = None
        if ev.bounding_box_json:
            try:
                bbox = json.loads(ev.bounding_box_json)
            except Exception:
                bbox = None
        res.append(EvidenceResponse(
            id=ev.id,
            check_id=ev.check_id,
            image_id=ev.image_id,
            bounding_box=bbox,
            crop_image_path=ev.crop_image_path,
            highlight_text=ev.highlight_text,
            reason=ev.reason,
            created_at=ev.created_at
        ))
    return res

@app.post("/api/findings/{finding_id}/request-new-image", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
def request_new_image_for_finding(
    finding_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Inspector requests a new/additional image for a specific finding.
    This does NOT resolve the finding — it stays PENDING (or becomes NEEDS_MORE_EVIDENCE).
    The old finding history is preserved. A new audit entry is created.
    After calling this, the frontend should navigate to CaptureImages to capture a new image,
    then re-run OCR/evaluation.
    """
    check = db.query(ComplianceCheck).filter(ComplianceCheck.id == finding_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Finding record not found")
    verify_inspection_access(check.inspection, current_user, allow_supervisory=False)

    # DEF-02: Prevent requesting new evidence on completed/finalized inspections or generated reports
    if check.inspection.status == "COMPLETED" or check.inspection.report is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot request new images for an inspection that has been finalized or has an official report."
        )

    # Mark as needs more evidence but do NOT resolve
    old_status = check.adjudication_status
    check.adjudication_status = "NEEDS_MORE_EVIDENCE"
    check.adjudication_notes = "Inspector requested new/additional photographic evidence for this finding."

    review = InspectorReview(
        check_id=check.id,
        officer_id=current_user.id,
        action="NEEDS_MORE_EVIDENCE",
        remarks="Inspector requested new/additional photographic evidence."
    )
    db.add(review)

    log_audit(
        db,
        current_user.officer_id,
        "REQUEST_NEW_IMAGE",
        "compliance_check",
        check.id,
        check.inspection_id,
        old_val=old_status,
        new_val="NEEDS_MORE_EVIDENCE",
        details=f"Inspector requested new image for finding {check.rule_code}. Inspector must re-capture and re-analyze."
    )

    db.commit()
    db.refresh(check)
    return serialize_finding(check)



@app.post("/api/inspections/{inspection_id}/report", response_model=ReportResponse, tags=["Reports"])
def generate_inspection_report(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    force_regenerate: bool = False
):
    """Generates an official Statutory Legal Metrology Inspection Report PDF from real database records.

    Idempotency: If the inspection is already COMPLETED and a report with a valid PDF
    exists on disk, returns the existing report without incrementing the version number,
    unless force_regenerate=True is explicitly passed.
    """
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)
    real_inspection_id = inspection.id

    # --- Idempotency guard for finalized inspections (AUDIT-REP-01) ---
    existing_report = db.query(Report).filter(Report.inspection_id == real_inspection_id).first()
    if (
        existing_report
        and inspection.status == "COMPLETED"
        and not force_regenerate
        and existing_report.pdf_path
        and Path(existing_report.pdf_path).exists()
    ):
        # Ensure DOCX also exists at same version without incrementing
        if not existing_report.docx_path or not Path(existing_report.docx_path).exists():
            existing_report.docx_path = report_generator.generate_docx(
                inspection=inspection,
                product=inspection.product,
                inspector=inspection.inspector or current_user,
                declarations=db.query(Declaration).filter(Declaration.inspection_id == real_inspection_id).all(),
                compliance_checks=db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == real_inspection_id).all(),
                evidence_items=db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == real_inspection_id).all(),
                report_version=existing_report.report_version
            )
            db.commit()
            db.refresh(existing_report)
        return serialize_report(existing_report)

    product = inspection.product
    inspector = inspection.inspector or current_user
    declarations = db.query(Declaration).filter(Declaration.inspection_id == real_inspection_id).all()
    compliance_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == real_inspection_id).all()
    evidence_items = db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == real_inspection_id).all()

    # Determine version: preserve version if recovering missing PDF for COMPLETED inspection;
    # otherwise increment version for new report generation.
    # Determine version and deterministic report record ID
    if existing_report and inspection.status == "COMPLETED" and not force_regenerate:
        # PDF missing on disk for finalized — regenerate at same version
        new_version = existing_report.report_version
        report_record_id = existing_report.id
    elif existing_report:
        new_version = existing_report.report_version + 1
        report_record_id = existing_report.id
    else:
        new_version = 1
        report_record_id = str(uuid.uuid4())

    pdf_path, pdf_hash = report_generator.generate_pdf_with_hash(
        inspection=inspection,
        product=product,
        inspector=inspector,
        declarations=declarations,
        compliance_checks=compliance_checks,
        evidence_items=evidence_items,
        report_version=new_version,
        report_id=report_record_id,
    )

    docx_path = report_generator.generate_docx(
        inspection=inspection,
        product=product,
        inspector=inspector,
        declarations=declarations,
        compliance_checks=compliance_checks,
        evidence_items=evidence_items,
        report_version=new_version
    )

    # Upload PDF report to Supabase Storage if configured
    if storage_service.is_configured:
        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            storage_service.upload_report_pdf(real_inspection_id, new_version, pdf_bytes)
        except Exception as e:
            print(f"[SupabaseStorage] Warning: Failed to upload report PDF to Supabase: {e}")

    safety_statement = (
        "This official inspection report was generated by the AI-Assisted Legal Metrology Packaged-Commodity Inspection System (DoCA). "
        "Compliance evaluations were executed via deterministic PCR 2011 rule verification under designated inspecting officer authority."
    )

    if existing_report:
        existing_report.report_version = new_version
        existing_report.pdf_path = pdf_path
        existing_report.docx_path = docx_path
        existing_report.pdf_hash = pdf_hash
        existing_report.legal_safety_statement = safety_statement
        existing_report.generated_at = datetime.utcnow()
        report_record = existing_report
    else:
        report_record = Report(
            id=report_record_id,
            inspection_id=real_inspection_id,
            report_version=new_version,
            pdf_path=pdf_path,
            docx_path=docx_path,
            pdf_hash=pdf_hash,
            legal_safety_statement=safety_statement
        )
        db.add(report_record)

    log_audit(
        db,
        current_user.officer_id,
        "REPORT_GENERATED",
        "report",
        report_record.id,
        real_inspection_id,
        details=f"Generated statutory PDF & DOCX inspection reports v{new_version} ({inspection.inspection_number})"
    )

    db.commit()
    db.refresh(report_record)

    return serialize_report(report_record)

@app.get("/api/inspections/{inspection_id}/report", response_model=ReportResponse, tags=["Reports"])
def get_inspection_report_metadata(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves metadata of the statutory inspection report."""
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    report_record = db.query(Report).filter(Report.inspection_id == inspection.id).first()
    if not report_record:
        # Auto-generate if not yet generated
        return generate_inspection_report(inspection.id, db, current_user)

    return serialize_report(report_record)

@app.get("/api/inspections/{inspection_id}/report/pdf", tags=["Reports"])
def stream_inspection_report_pdf(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Streams the official PDF binary for viewing or download."""
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    report_record = db.query(Report).filter(Report.inspection_id == inspection.id).first()
    if not report_record or not Path(report_record.pdf_path).exists():
        generate_inspection_report(inspection.id, db, current_user)
        report_record = db.query(Report).filter(Report.inspection_id == inspection.id).first()

    pdf_file = Path(report_record.pdf_path)
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="Generated PDF report file not found on disk")

    filename = f"LM_Report_{inspection.inspection_number}.pdf"
    return FileResponse(
        str(pdf_file),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )

@app.get("/api/inspections/{inspection_id}/report/docx", tags=["Reports"])
def stream_inspection_report_docx(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Streams the official editable Microsoft Word (.docx) compliance report.
    Authorization: Inspector can download their own report; Supervisor/Admin can access any report.
    Idempotency: Exporting does NOT increment report version or alter records.
    """
    inspection = get_inspection_by_id_or_number(db, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    report_record = db.query(Report).filter(Report.inspection_id == inspection.id).first()
    if not report_record:
        generate_inspection_report(inspection.id, db, current_user)
        report_record = db.query(Report).filter(Report.inspection_id == inspection.id).first()

    # Ensure DOCX is available on disk at current version
    docx_file = Path(report_record.docx_path) if getattr(report_record, "docx_path", None) else None
    if not docx_file or not docx_file.exists():
        declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection.id).all()
        compliance_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection.id).all()
        evidence_items = db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection.id).all()
        gen_docx = report_generator.generate_docx(
            inspection=inspection,
            product=inspection.product,
            inspector=inspection.inspector or current_user,
            declarations=declarations,
            compliance_checks=compliance_checks,
            evidence_items=evidence_items,
            report_version=report_record.report_version
        )
        report_record.docx_path = gen_docx
        db.commit()
        db.refresh(report_record)
        docx_file = Path(gen_docx)

    if not docx_file.exists():
        raise HTTPException(status_code=404, detail="Generated DOCX report file not found on disk")

    safe_insp_num = (inspection.inspection_number or "UNKNOWN").replace("-", "_").replace("/", "_")
    filename = f"LM_Report_{safe_insp_num}.docx"
    return FileResponse(
        str(docx_file),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/inspections/{inspection_id}/finalize", response_model=FinalizeInspectionResponse, tags=["Inspections"])
def finalize_inspection(
    inspection_id: str,
    req: FinalizeInspectionRequest = Body(default=FinalizeInspectionRequest()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Finalizes the inspection lifecycle based on human adjudication, marks status as COMPLETED,
    and produces the finalized official statutory inspection report.
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    # Fast-path idempotency: If already finalized and report exists, return existing record
    if inspection.status == "COMPLETED" and inspection.report:
        return FinalizeInspectionResponse(
            inspection_id=inspection.id,
            inspection_number=inspection.inspection_number,
            status=inspection.status,
            overall_status=inspection.overall_status,
            finalized_at=inspection.finalized_at,
            report=serialize_report(inspection.report)
        )

    all_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection.id).all()

    # REPORT-BLOCKING GATE: Block finalization if any non-PASS finding is still PENDING adjudication
    resolved_actions = {"CONFIRMED", "DISMISSED", "NOT_APPLICABLE", "CORRECTED"}
    unresolved = [
        c for c in all_checks
        if c.result_state != "PASS" and c.adjudication_status not in resolved_actions
    ]
    if unresolved:
        unresolved_descriptions = [{"rule_code": c.rule_code, "title": c.title, "adjudication_status": c.adjudication_status} for c in unresolved]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "UNRESOLVED_FINDINGS",
                "message": f"Cannot finalize inspection: {len(unresolved)} finding(s) require inspector adjudication before the report can be generated.",
                "unresolved_findings": unresolved_descriptions
            }
        )

    # Calculate final status from resolved adjudications
    has_confirmed_violations = any(
        c.adjudication_status == "CONFIRMED"
        for c in all_checks
    )
    has_insufficient = any(
        c.result_state == "INSUFFICIENT_EVIDENCE" and c.adjudication_status == "NEEDS_MORE_EVIDENCE"
        for c in all_checks
    )

    # Inspector Final Decision & Adjudication Safety (Requirement 11)
    if req.final_status and req.final_status in [
        "NO_POTENTIAL_VIOLATIONS", "POTENTIAL_NON_COMPLIANCE", "NEEDS_MANUAL_VERIFICATION",
        "COMPLIANT", "NON_COMPLIANT"
    ]:
        status_map = {
            "COMPLIANT": "NO_POTENTIAL_VIOLATIONS",
            "NON_COMPLIANT": "POTENTIAL_NON_COMPLIANCE",
        }
        inspection.overall_status = status_map.get(req.final_status, req.final_status)
    elif has_confirmed_violations:
        inspection.overall_status = "POTENTIAL_NON_COMPLIANCE"
    elif has_insufficient:
        inspection.overall_status = "NEEDS_MANUAL_VERIFICATION"
    elif len(all_checks) > 0 and all(c.result_state == "PASS" for c in all_checks):
        inspection.overall_status = "NO_POTENTIAL_VIOLATIONS"
    else:
        # If no statutory checks were evaluated or evidence is unverified,
        # never automatically mark compliant. Route to manual verification.
        inspection.overall_status = "NEEDS_MANUAL_VERIFICATION"

    inspection.status = "COMPLETED"
    inspection.finalized_at = datetime.utcnow()
    if req.officer_notes:
        inspection.notes = req.officer_notes.strip()

    # Generate statutory PDF report
    try:
        report_res = generate_inspection_report(inspection_id, db, current_user)
    except Exception as e:
        db.commit()  # Preserve finalized status, decisions, and audit trail
        raise HTTPException(
            status_code=500,
            detail=f"Inspection submitted, but the official report could not be generated: {str(e)}. Please retry report generation."
        )

    log_audit(
        db,
        current_user.officer_id,
        "INSPECTION_FINALIZED",
        "inspection",
        inspection.id,
        inspection.id,
        details=f"Inspection {inspection.inspection_number} finalized with status: {inspection.overall_status}"
    )

    db.commit()
    db.refresh(inspection)

    return FinalizeInspectionResponse(
        inspection_id=inspection.id,
        inspection_number=inspection.inspection_number,
        status=inspection.status,
        overall_status=inspection.overall_status,
        finalized_at=inspection.finalized_at,
        report=report_res
    )

@app.get("/api/reports", response_model=List[ReportResponse], tags=["Reports"])
def list_all_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lists all generated statutory reports across inspections."""
    q = db.query(Report).join(Inspection, Report.inspection_id == Inspection.id)
    if current_user.role not in ("ADMIN", "SUPERVISOR"):
        q = q.filter(Inspection.inspector_id == current_user.id)
    reports = q.order_by(Report.generated_at.desc()).all()
    return [serialize_report(r) for r in reports]

@app.get("/api/reports/{report_id}", response_model=ReportResponse, tags=["Reports"])
def get_report_by_id(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves a statutory inspection report by its unique Report ID."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    inspection = report.inspection
    if not inspection:
        inspection = db.query(Inspection).filter(Inspection.id == report.inspection_id).first()

    if inspection:
        verify_inspection_access(inspection, current_user, allow_supervisory=True)

    return serialize_report(report)

@app.get("/api/reports/{report_id}/docx", tags=["Reports"])
def stream_report_by_id_docx(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves the editable DOCX compliance report by Report ID.
    Authorization: Inspector can access their own report; Supervisor/Admin can access any report.
    Idempotency: Exporting does NOT increment report version.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    inspection = report.inspection
    if not inspection:
        inspection = db.query(Inspection).filter(Inspection.id == report.inspection_id).first()

    if inspection:
        verify_inspection_access(inspection, current_user, allow_supervisory=True)

    # Ensure DOCX exists on disk at current version
    docx_file = Path(report.docx_path) if getattr(report, "docx_path", None) else None
    if not docx_file or not docx_file.exists():
        declarations = db.query(Declaration).filter(Declaration.inspection_id == report.inspection_id).all()
        compliance_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == report.inspection_id).all()
        evidence_items = db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == report.inspection_id).all()
        gen_docx = report_generator.generate_docx(
            inspection=inspection,
            product=inspection.product if inspection else None,
            inspector=inspection.inspector if inspection else current_user,
            declarations=declarations,
            compliance_checks=compliance_checks,
            evidence_items=evidence_items,
            report_version=report.report_version
        )
        report.docx_path = gen_docx
        db.commit()
        db.refresh(report)
        docx_file = Path(gen_docx)

    if not docx_file.exists():
        raise HTTPException(status_code=404, detail="Generated DOCX report file not found on disk")

    safe_insp_num = (inspection.inspection_number if inspection else "UNKNOWN").replace("-", "_").replace("/", "_")
    filename = f"LM_Report_{safe_insp_num}.docx"
    return FileResponse(
        str(docx_file),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@app.get("/api/rules/{rule_code}", tags=["Rules"])
def get_rule_details(
    rule_code: str,
    current_user: User = Depends(get_current_user)
):
    """Retrieves official statutory metadata and description for a specific rule code."""
    rule = get_rule_by_code(rule_code)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule code '{rule_code}' not found in registry")
    return rule.model_dump()

@app.get("/api/inspections/{inspection_id}/audit-logs", response_model=List[AuditLogResponse], tags=["Audit Trail"])
def get_inspection_audit_logs(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves the complete immutable audit trail for an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    logs = db.query(AuditLog).filter(
        AuditLog.inspection_id == inspection_id
    ).order_by(AuditLog.created_at.desc()).all()

    return logs

@app.get("/api/rules", tags=["Rules"])
def list_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns the list of registered statutory Legal Metrology rules."""
    rules = db.query(RuleVersion).filter(RuleVersion.is_active == True).all()
    return [
        {
            "id": r.id,
            "rule_code": r.rule_code,
            "version_number": r.version_number,
            "title": r.title,
            "category": r.category,
            "statutory_reference": r.statutory_reference,
            "rule_logic_description": r.rule_logic_description,
            "severity": r.severity
        }
        for r in rules
    ]

# ----------------- User Management Endpoints (Admin Only) -----------------

@app.get("/api/users", response_model=List[UserListItemResponse], tags=["User Management"])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Admin-only: lists all registered enforcement officers and their roles."""
    users = db.query(User).order_by(User.created_at.asc()).all()
    return users


@app.patch("/api/users/{user_id}/role", response_model=UserListItemResponse, tags=["User Management"])
def update_user_role(
    user_id: str,
    req: UpdateUserRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Admin-only: updates an officer's role (INSPECTOR, SUPERVISOR, ADMIN)."""
    target_user = db.query(User).filter(or_(User.id == user_id, User.officer_id == user_id)).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Officer record not found")

    old_role = target_user.role
    target_user.role = req.role

    log_audit(
        db,
        current_user.officer_id,
        "USER_ROLE_UPDATED",
        "user",
        target_user.id,
        old_val=old_role,
        new_val=req.role,
        details=f"Admin updated role of {target_user.officer_id} from {old_role} to {req.role}"
    )
    db.commit()
    db.refresh(target_user)
    return target_user


# ----------------- Product Listing & Online Compliance Endpoints (PS 26034) -----------------

@app.post(
    "/api/inspections/{inspection_id}/listing",
    response_model=ProductListingResponse,
    status_code=status.HTTP_200_OK,
    tags=["Product Listing & E-Commerce Compliance"]
)
def save_product_listing(
    inspection_id: str,
    req: ProductListingCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Creates or updates product listing information for an inspection.
    Enforces inspector access and records audit provenance.
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    listing = db.query(ProductListing).filter(ProductListing.inspection_id == inspection_id).first()
    is_new = False
    if not listing:
        is_new = True
        listing = ProductListing(inspection_id=inspection_id)
        db.add(listing)

    # Clean and assign fields without synthesizing or inferring unprovided values
    listing.product_name = req.product_name.strip() if req.product_name else None
    listing.brand_name = req.brand_name.strip() if req.brand_name else None
    listing.mrp = req.mrp.strip() if req.mrp else None
    listing.net_quantity = req.net_quantity.strip() if req.net_quantity else None
    listing.manufacturer_details = req.manufacturer_details.strip() if req.manufacturer_details else None
    listing.importer_details = req.importer_details.strip() if req.importer_details else None
    listing.country_of_origin = req.country_of_origin.strip() if req.country_of_origin else None
    listing.consumer_care_details = req.consumer_care_details.strip() if req.consumer_care_details else None
    listing.date_information = req.date_information.strip() if req.date_information else None
    listing.seller_information = req.seller_information.strip() if req.seller_information else None
    listing.product_description = req.product_description.strip() if req.product_description else None
    listing.listing_url = req.listing_url.strip() if req.listing_url else None
    listing.source = "MANUAL_LISTING_INPUT"

    # Update inspection mode if currently default physical
    if inspection.inspection_type == "PHYSICAL":
        inspection.inspection_type = "ONLINE_LISTING"

    log_audit(
        db,
        current_user.officer_id,
        "PRODUCT_LISTING_CREATED" if is_new else "PRODUCT_LISTING_UPDATED",
        "product_listing",
        inspection_id,
        inspection_id=inspection_id,
        details=f"Product listing information {'saved' if is_new else 'updated'} by inspector"
    )

    db.commit()
    db.refresh(listing)
    return listing


@app.get(
    "/api/inspections/{inspection_id}/listing",
    response_model=ProductListingResponse,
    tags=["Product Listing & E-Commerce Compliance"]
)
def get_product_listing(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves product listing details associated with an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    listing = db.query(ProductListing).filter(ProductListing.inspection_id == inspection_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="No product listing found for this inspection")
    return listing


@app.post(
    "/api/inspections/{inspection_id}/listing/compare",
    response_model=ListingComparisonSummaryResponse,
    tags=["Product Listing & E-Commerce Compliance"]
)
def run_listing_comparison(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compares online listing data against extracted physical package declarations.
    Detects discrepancies deterministically according to Legal Metrology provisions.
    Does NOT automatically create legal violations; preserves findings for inspector adjudication.
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    try:
        comparisons = execute_listing_comparison(db, inspection_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    listing = db.query(ProductListing).filter(ProductListing.inspection_id == inspection_id).first()

    matches = sum(1 for c in comparisons if c.comparison_status == "MATCH")
    mismatches = sum(1 for c in comparisons if c.comparison_status == "MISMATCH")
    missing_listing = sum(1 for c in comparisons if c.comparison_status == "MISSING_ON_LISTING")
    missing_pkg = sum(1 for c in comparisons if c.comparison_status == "MISSING_ON_PACKAGE")
    uncertain = sum(1 for c in comparisons if c.comparison_status == "UNCERTAIN")
    has_disc = (mismatches > 0 or missing_listing > 0 or missing_pkg > 0)

    log_audit(
        db,
        current_user.officer_id,
        "PRODUCT_LISTING_COMPARED",
        "listing_comparison",
        inspection_id,
        inspection_id=inspection_id,
        details=(
            f"Comparison completed: {len(comparisons)} fields evaluated. "
            f"{matches} matches, {mismatches} mismatches, {missing_listing} missing on listing, {uncertain} uncertain."
        )
    )

    return ListingComparisonSummaryResponse(
        inspection_id=inspection_id,
        inspection_number=inspection.inspection_number,
        total_fields_compared=len(comparisons),
        matches_count=matches,
        mismatches_count=mismatches,
        missing_on_listing_count=missing_listing,
        missing_on_package_count=missing_pkg,
        uncertain_count=uncertain,
        has_discrepancies=has_disc,
        listing=listing,
        comparisons=comparisons
    )


@app.get(
    "/api/inspections/{inspection_id}/listing/comparison",
    response_model=ListingComparisonSummaryResponse,
    tags=["Product Listing & E-Commerce Compliance"]
)
def get_listing_comparison(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves previous comparison results between online listing and physical package."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=True)

    listing = db.query(ProductListing).filter(ProductListing.inspection_id == inspection_id).first()
    comparisons = db.query(ListingComparison).filter(ListingComparison.inspection_id == inspection_id).all()

    matches = sum(1 for c in comparisons if c.comparison_status == "MATCH")
    mismatches = sum(1 for c in comparisons if c.comparison_status == "MISMATCH")
    missing_listing = sum(1 for c in comparisons if c.comparison_status == "MISSING_ON_LISTING")
    missing_pkg = sum(1 for c in comparisons if c.comparison_status == "MISSING_ON_PACKAGE")
    uncertain = sum(1 for c in comparisons if c.comparison_status == "UNCERTAIN")
    has_disc = (mismatches > 0 or missing_listing > 0 or missing_pkg > 0)

    return ListingComparisonSummaryResponse(
        inspection_id=inspection_id,
        inspection_number=inspection.inspection_number,
        total_fields_compared=len(comparisons),
        matches_count=matches,
        mismatches_count=mismatches,
        missing_on_listing_count=missing_listing,
        missing_on_package_count=missing_pkg,
        uncertain_count=uncertain,
        has_discrepancies=has_disc,
        listing=listing,
        comparisons=comparisons
    )


@app.post(
    "/api/inspections/{inspection_id}/listing/comparisons/{comparison_id}/adjudicate",
    response_model=ListingComparisonItemResponse,
    tags=["Product Listing & E-Commerce Compliance"]
)
def adjudicate_listing_comparison(
    inspection_id: str,
    comparison_id: str,
    req: AdjudicateComparisonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Inspector adjudication on a specific discrepancy item.
    Enforces inspector authority as the final arbiter.
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    verify_inspection_access(inspection, current_user, allow_supervisory=False)

    comparison = db.query(ListingComparison).filter(
        ListingComparison.id == comparison_id,
        ListingComparison.inspection_id == inspection_id
    ).first()
    if not comparison:
        raise HTTPException(status_code=404, detail="Listing comparison record not found")

    old_status = comparison.inspector_status
    comparison.inspector_status = req.status
    comparison.inspector_remarks = req.remarks.strip() if req.remarks else None
    comparison.adjudicated_by = current_user.officer_id
    comparison.adjudicated_at = datetime.utcnow()

    log_audit(
        db,
        current_user.officer_id,
        "LISTING_COMPARISON_ADJUDICATED",
        "listing_comparison",
        comparison.id,
        inspection_id=inspection_id,
        old_val=old_status,
        new_val=req.status,
        details=f"Comparison item for '{comparison.field_name}' adjudicated as {req.status}"
    )

    db.commit()
    db.refresh(comparison)
    return comparison


# ----------------- Root Navigation Page -----------------

@app.get("/", response_class=HTMLResponse, tags=["Root"])
def root_index():
    """Serves the Stitch Navigation Index and Backend Status verification page."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NiriKsha — Legal Metrology Field Inspection System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>body { font-family: 'Inter', sans-serif; }</style>
</head>
<body class="bg-slate-50 text-slate-900 min-h-screen p-6">
    <div class="max-w-4xl mx-auto space-y-6">
        <header class="bg-[#031635] text-white p-6 rounded-xl shadow-md flex items-center justify-between">
            <div>
                <span class="text-xs font-semibold uppercase tracking-wider text-blue-300">Department of Consumer Affairs (DoCA)</span>
                <h1 class="text-2xl font-bold mt-1">NiriKsha</h1>
                <p class="text-sm text-slate-300 mt-1">AI-Assisted Legal Metrology Inspection System • NiriKsha — SIH Prototype 2026</p>
            </div>
            <a href="/stitch/code/01_login.html" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-lg transition">Launch App →</a>
        </header>

        <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <h2 class="text-lg font-bold text-slate-800 mb-2">System Status & Verification</h2>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
                <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
                    <p class="text-slate-500 text-xs uppercase font-semibold">API Health</p>
                    <p class="text-emerald-700 font-bold text-base mt-1">✓ Healthy (FastAPI)</p>
                    <a href="/api/health" class="text-blue-600 hover:underline text-xs" target="_blank">View /api/health →</a>
                </div>
                <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
                    <p class="text-slate-500 text-xs uppercase font-semibold">Deterministic Rule Engine</p>
                    <p class="text-emerald-700 font-bold text-base mt-1">✓ Active (PCR 2011)</p>
                    <p class="text-slate-500 text-xs">Rule Evaluation & Adjudication Engine</p>
                </div>
                <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
                    <p class="text-slate-500 text-xs uppercase font-semibold">PDF Report Generator</p>
                    <p class="text-emerald-700 font-bold text-base mt-1">✓ ReportLab Engine</p>
                    <a href="/api/rules" class="text-blue-600 hover:underline text-xs" target="_blank">View /api/rules →</a>
                </div>
            </div>
        </section>

        <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <div class="flex items-center justify-between mb-4">
                <h2 class="text-lg font-bold text-slate-800">Finalized Stitch Screens (13 Screens Preserved)</h2>
                <span class="text-xs text-slate-500 font-medium">100% Exact Stitch Markup & Styling</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <a href="/stitch/code/01_login.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">01. Login (Final Refinement)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/02_dashboard.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">02. Dashboard (Standardized Nav)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/04_new_inspection_step1.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">03. New Inspection - Step 1</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/09_capture_images_warning.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">04. Capture Images (Quality Warning)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/12_analyzing.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">05. Analyzing...</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/03_extracted_declarations.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">06. Extracted Declarations</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/05_findings.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">07. Findings (Final Refinement)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/06_evidence_review.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">08. Evidence Review (Final Polish)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/13_step3_review_and_submit.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">09. Step 3: Review & Submit</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/07_inspection_report_preview.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">10. Inspection Report Preview</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/08_reports_list.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">11. Reports List (Archive)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/10_profile.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">12. Profile (Final)</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
                <a href="/stitch/code/11_draft_saved_offline.html" class="p-3 bg-slate-50 hover:bg-blue-50 border border-slate-200 rounded-lg flex items-center justify-between group transition">
                    <span class="font-medium text-slate-800 text-sm group-hover:text-blue-900">13. Draft Saved / Offline State</span>
                    <span class="text-xs text-blue-600 font-semibold">Launch →</span>
                </a>
            </div>
        </section>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


# ===========================================================================
# SUPERVISOR MANAGEMENT ENDPOINTS (NIRIKSHA ROLE-BASED ACCESS CONTROL)
# ===========================================================================

@app.get("/api/supervisor/dashboard", response_model=SupervisorDashboardResponse, tags=["Supervisor Management"])
def get_supervisor_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_admin)
):
    """
    Returns real-time management KPIs aggregated across ALL Field Inspectors.
    Every metric is computed live from Neon PostgreSQL — zero hardcoded / fake data.
    """
    total_inspections = db.query(Inspection).count()
    
    # Today's Inspections
    today_inspections = db.query(Inspection).filter(
        func.date(Inspection.created_at) == func.current_date()
    ).count()

    # Completed vs Pending Inspections
    completed_inspections = db.query(Inspection).filter(
        or_(Inspection.status == "COMPLETED", Inspection.finalized_at.isnot(None))
    ).count()
    pending_inspections = db.query(Inspection).filter(
        and_(Inspection.status != "COMPLETED", Inspection.finalized_at.is_(None))
    ).count()

    # Compliance states
    potential_non_compliance = db.query(Inspection).filter(
        Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE"
    ).count()

    # Reports generated
    reports_generated = db.query(Report).count()

    # Active inspectors (distinct inspectors who submitted inspections)
    active_inspectors_count = db.query(func.count(distinct(Inspection.inspector_id))).scalar() or 0

    # Inspections requiring manual verification
    unresolved_decl_subq = db.query(distinct(Declaration.inspection_id)).filter(
        Declaration.extraction_status.in_(["NOT_FOUND", "CONFLICTING", "LOW_CONFIDENCE", "NEEDS_REVIEW"])
    )
    unresolved_check_subq = db.query(distinct(ComplianceCheck.inspection_id)).filter(
        ComplianceCheck.result_state == "POTENTIAL_NON_COMPLIANCE",
        ComplianceCheck.adjudication_status == "PENDING"
    )
    manual_verification_required = db.query(Inspection).filter(
        or_(
            Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION",
            Inspection.id.in_(unresolved_decl_subq),
            Inspection.id.in_(unresolved_check_subq)
        )
    ).count()

    # Recent Submissions (limit 10)
    recent_objs = db.query(Inspection).order_by(Inspection.created_at.desc()).limit(10).all()
    recent_submissions = [
        RecentInspectionItem(
            id=insp.id,
            inspection_number=insp.inspection_number,
            product_name=insp.product.product_name if insp.product else "Unnamed Commodity",
            location=insp.location,
            status=insp.status,
            overall_status=insp.overall_status,
            created_at=insp.created_at
        )
        for insp in recent_objs
    ]

    # Grouping by Inspector
    insp_user_rows = db.query(
        User.id,
        User.officer_id,
        User.full_name,
        User.zone,
        func.count(Inspection.id).label("total"),
        func.sum(case((or_(Inspection.status == "COMPLETED", Inspection.finalized_at.isnot(None)), 1), else_=0)).label("completed"),
        func.sum(case((Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE", 1), else_=0)).label("non_compliant"),
        func.sum(case((Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION", 1), else_=0)).label("manual_verification")
    ).join(Inspection, User.id == Inspection.inspector_id).group_by(
        User.id, User.officer_id, User.full_name, User.zone
    ).all()

    inspections_by_inspector = [
        {
            "inspector_id": r[0],
            "officer_id": r[1] or "N/A",
            "full_name": r[2] or "Inspector",
            "zone": r[3] or "Field",
            "total": int(r[4] or 0),
            "completed": int(r[5] or 0),
            "pending": int((r[4] or 0) - (r[5] or 0)),
            "non_compliant": int(r[6] or 0),
            "manual_verification": int(r[7] or 0),
        }
        for r in insp_user_rows
    ]

    # Category breakdown
    cat_rows = db.query(
        Product.category,
        func.count(Inspection.id)
    ).join(Inspection, Product.inspection_id == Inspection.id).group_by(Product.category).all()
    inspections_by_category = {r[0] or "Other": int(r[1]) for r in cat_rows}

    # Status breakdown
    status_rows = db.query(
        Inspection.status,
        func.count(Inspection.id)
    ).group_by(Inspection.status).all()
    inspections_by_status = {r[0]: int(r[1]) for r in status_rows}

    # Timeline distribution
    time_rows = db.query(
        func.date(Inspection.created_at).label("insp_date"),
        func.count(Inspection.id).label("total"),
        func.sum(case((Inspection.overall_status.in_(["NO_POTENTIAL_VIOLATIONS", "VERIFIED_COMPLIANT"]), 1), else_=0)).label("compliant"),
        func.sum(case((Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE", 1), else_=0)).label("non_compliant")
    ).group_by("insp_date").order_by("insp_date").all()

    inspections_by_date = [
        {
            "date": str(r.insp_date),
            "total": int(r.total or 0),
            "compliant": int(r.compliant or 0),
            "non_compliant": int(r.non_compliant or 0)
        }
        for r in time_rows
    ]

    # Inspections requiring attention
    attention_objs = db.query(Inspection).filter(
        or_(
            Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION",
            Inspection.id.in_(unresolved_decl_subq),
            Inspection.id.in_(unresolved_check_subq)
        )
    ).order_by(Inspection.created_at.desc()).limit(10).all()

    inspections_requiring_attention = [
        {
            "id": insp.id,
            "inspection_number": insp.inspection_number,
            "product_name": insp.product.product_name if insp.product else "Unnamed Commodity",
            "inspector": insp.inspector.full_name if insp.inspector else "Field Inspector",
            "officer_id": insp.inspector.officer_id if insp.inspector else "N/A",
            "location": insp.location,
            "created_at": insp.created_at.isoformat() if insp.created_at else None,
            "overall_status": insp.overall_status
        }
        for insp in attention_objs
    ]

    return SupervisorDashboardResponse(
        total_inspections=total_inspections,
        today_inspections=today_inspections,
        completed_inspections=completed_inspections,
        pending_inspections=pending_inspections,
        manual_verification_required=manual_verification_required,
        potential_non_compliance=potential_non_compliance,
        reports_generated=reports_generated,
        active_inspectors_count=active_inspectors_count,
        recent_submissions=recent_submissions,
        inspections_by_inspector=inspections_by_inspector,
        inspections_by_category=inspections_by_category,
        inspections_by_status=inspections_by_status,
        inspections_by_date=inspections_by_date,
        inspections_requiring_attention=inspections_requiring_attention
    )


@app.get("/api/supervisor/inspectors", response_model=SupervisorInspectorsListResponse, tags=["Supervisor Management"])
def get_supervisor_inspectors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_admin)
):
    """
    Returns the list of all Field Inspectors dynamically from the database,
    along with their real enforcement metrics and workload statistics.
    """
    inspectors = db.query(User).filter(User.role == "INSPECTOR").order_by(User.full_name).all()
    
    # Precompute inspector metrics via group-by
    stats_map = {}
    stats_rows = db.query(
        Inspection.inspector_id,
        func.count(Inspection.id).label("total"),
        func.sum(case((or_(Inspection.status == "COMPLETED", Inspection.finalized_at.isnot(None)), 1), else_=0)).label("completed"),
        func.sum(case((Inspection.overall_status == "POTENTIAL_NON_COMPLIANCE", 1), else_=0)).label("non_compliant"),
        func.sum(case((Inspection.overall_status == "NEEDS_MANUAL_VERIFICATION", 1), else_=0)).label("manual_verification"),
        func.max(Inspection.created_at).label("last_active")
    ).group_by(Inspection.inspector_id).all()

    for r in stats_rows:
        stats_map[r[0]] = {
            "total": int(r[1] or 0),
            "completed": int(r[2] or 0),
            "non_compliant": int(r[3] or 0),
            "manual_verification": int(r[4] or 0),
            "last_active": r[5]
        }

    # Precompute reports per inspector
    rep_rows = db.query(
        Inspection.inspector_id,
        func.count(Report.id).label("reports_count")
    ).join(Report, Inspection.id == Report.inspection_id).group_by(Inspection.inspector_id).all()
    report_map = {r[0]: int(r[1] or 0) for r in rep_rows}

    results = []
    for insp in inspectors:
        st = stats_map.get(insp.id, {})
        tot = st.get("total", 0)
        comp = st.get("completed", 0)
        pend = tot - comp
        results.append(
            SupervisorInspectorSummary(
                inspector_id=insp.id,
                officer_id=insp.officer_id,
                full_name=insp.full_name,
                designation=insp.designation,
                zone=insp.zone,
                email=insp.email,
                phone=insp.phone,
                total_inspections=tot,
                completed_inspections=comp,
                pending_inspections=pend,
                potential_non_compliance=st.get("non_compliant", 0),
                manual_verification_required=st.get("manual_verification", 0),
                reports_generated=report_map.get(insp.id, 0),
                last_active=st.get("last_active")
            )
        )

    return SupervisorInspectorsListResponse(inspectors=results, total_count=len(results))


@app.get("/api/supervisor/inspections", response_model=SupervisorInspectionsListResponse, tags=["Supervisor Management"])
def get_supervisor_inspections(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search across inspection number, product, brand, inspector name, officer ID, location"),
    inspector_id: Optional[str] = Query(None, description="Filter by specific inspector ID or officer ID"),
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    overall_status: Optional[str] = Query(None, description="Filter by compliance outcome"),
    category: Optional[str] = Query(None, description="Filter by commodity category"),
    has_report: Optional[bool] = Query(None, description="Filter by whether report is generated"),
    date_from: Optional[str] = Query(None, description="Filter inspections created on or after date (YYYY-MM-DD or ISO)"),
    date_to: Optional[str] = Query(None, description="Filter inspections created on or before date (YYYY-MM-DD or ISO)"),
    sort_by: str = Query("created_at", description="Sort field: created_at, inspection_number, inspector, status, compliance"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_admin)
):
    """
    Supervisor repository query endpoint.
    Protected strictly by SUPERVISOR or ADMIN authorization.
    Returns paginated lightweight summaries (omits heavy OCR/declarations) for responsive mobile viewing.
    """
    query = db.query(Inspection).outerjoin(Product, Inspection.id == Product.inspection_id).outerjoin(User, Inspection.inspector_id == User.id).outerjoin(Report, Inspection.id == Report.inspection_id)

    # Inspector filter
    if inspector_id and inspector_id.strip():
        insp_val = inspector_id.strip()
        query = query.filter(
            or_(
                Inspection.inspector_id == insp_val,
                User.officer_id == insp_val,
                User.id == insp_val
            )
        )

    # Status filters
    if status and status.strip():
        query = query.filter(Inspection.status == status.strip())
    if overall_status and overall_status.strip():
        query = query.filter(Inspection.overall_status == overall_status.strip())
    if category and category.strip():
        query = query.filter(Product.category == category.strip())

    if has_report is True:
        query = query.filter(Report.id.isnot(None))
    elif has_report is False:
        query = query.filter(Report.id.is_(None))

    # Date filters
    if date_from and date_from.strip():
        parsed_from = _parse_dashboard_date_filter(date_from, is_end_date=False)
        query = query.filter(Inspection.created_at >= parsed_from)
    if date_to and date_to.strip():
        parsed_to = _parse_dashboard_date_filter(date_to, is_end_date=True)
        query = query.filter(Inspection.created_at <= parsed_to)

    # Search filter
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Inspection.inspection_number.ilike(term),
                Inspection.id.ilike(term),
                Product.product_name.ilike(term),
                Product.brand_name.ilike(term),
                Product.batch_number.ilike(term),
                Inspection.location.ilike(term),
                User.officer_id.ilike(term),
                User.full_name.ilike(term)
            )
        )

    total_count = query.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 1

    # Sorting
    sort_dir = desc if sort_order.lower() == "desc" else asc
    if sort_by == "inspection_number":
        query = query.order_by(sort_dir(Inspection.inspection_number))
    elif sort_by == "inspector":
        query = query.order_by(sort_dir(User.full_name))
    elif sort_by == "status":
        query = query.order_by(sort_dir(Inspection.status))
    elif sort_by == "compliance":
        query = query.order_by(sort_dir(Inspection.overall_status))
    else:
        query = query.order_by(sort_dir(Inspection.created_at))

    offset = (page - 1) * page_size
    inspections = query.options(
        joinedload(Inspection.product),
        joinedload(Inspection.inspector),
        joinedload(Inspection.report),
        joinedload(Inspection.compliance_checks)
    ).offset(offset).limit(page_size).all()

    items: List[SupervisorInspectionSummaryItem] = []
    for insp in inspections:
        prod = insp.product
        p_name = prod.product_name if prod else "Unnamed Commodity"
        b_name = prod.brand_name if prod else None
        cat = prod.category if prod else "General"
        insp_user = insp.inspector
        i_name = insp_user.full_name if insp_user else "Unknown Inspector"
        i_officer_id = insp_user.officer_id if insp_user else (insp.inspector_id or "N/A")

        checks = insp.compliance_checks or []
        findings_count = len(checks)
        non_compliant_count = sum(1 for c in checks if c.result_state == "POTENTIAL_NON_COMPLIANCE")

        items.append(
            SupervisorInspectionSummaryItem(
                id=insp.id,
                inspection_number=insp.inspection_number,
                product_name=p_name,
                brand_name=b_name,
                category=cat,
                location=insp.location or "Not Specified",
                inspector_id=i_officer_id,
                inspector_name=i_name,
                status=insp.status,
                overall_status=insp.overall_status,
                created_at=insp.created_at,
                finalized_at=insp.finalized_at,
                has_report=insp.report is not None,
                report_id=insp.report.id if insp.report else None,
                findings_count=findings_count,
                non_compliant_count=non_compliant_count
            )
        )

    return SupervisorInspectionsListResponse(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@app.delete("/api/inspections/{inspection_id}", response_model=DeleteInspectionResponse, tags=["Supervisor Management"])
def delete_inspection(
    inspection_id: str,
    payload: Optional[DeleteInspectionRequest] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_admin)
):
    """
    Supervisor destructive inspection deletion.
    Enforces backend role verification (SUPERVISOR or ADMIN only; INSPECTOR rejected with 403).
    Requires matching confirmation inspection number.
    Cascades child records safely inside an atomic DB transaction, cleans physical files, and records an immutable audit log.
    Reference data (users, rule versions) and other inspections remain intact.
    """
    inspection = db.query(Inspection).filter(
        or_(Inspection.id == inspection_id, Inspection.inspection_number == inspection_id)
    ).first()

    if not inspection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection '{inspection_id}' not found."
        )

    # Validate confirmation inspection number
    if not payload or not payload.confirmation_inspection_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation inspection number is required. Please type the exact inspection number to confirm deletion."
        )

    entered_clean = payload.confirmation_inspection_number.strip().upper()
    actual_clean = inspection.inspection_number.strip().upper()
    if entered_clean != actual_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Confirmation mismatch: Typed '{payload.confirmation_inspection_number}', but actual inspection number is '{inspection.inspection_number}'. Deletion aborted."
        )

    saved_insp_id = inspection.id
    saved_insp_num = inspection.inspection_number
    product_name = inspection.product.product_name if inspection.product else "N/A"
    inspector_officer_id = inspection.inspector.officer_id if inspection.inspector else "N/A"
    reason_text = payload.reason.strip() if (payload and payload.reason and payload.reason.strip()) else "Supervisor management deletion"

    # Gather physical files to delete safely after successful database commit
    files_to_remove = []
    if inspection.report:
        for file_path in [inspection.report.pdf_path, inspection.report.docx_path]:
            if file_path and os.path.isfile(file_path):
                files_to_remove.append(file_path)

    for img in inspection.images:
        if img.file_path and os.path.isfile(img.file_path):
            files_to_remove.append(img.file_path)

    # Perform atomic DB transaction
    try:
        # Audit logging before deletion — record survives deletion because inspection_id is None
        # and full historical snapshot is preserved in details JSON
        audit = AuditLog(
            inspection_id=None,
            actor_id=current_user.officer_id,
            action="INSPECTION_DELETED",
            entity_type="inspection",
            entity_id=saved_insp_id,
            details=json.dumps({
                "inspection_uuid": saved_insp_id,
                "inspection_number": saved_insp_num,
                "product_name": product_name,
                "inspector_id": inspector_officer_id,
                "supervisor_id": current_user.officer_id,
                "supervisor_name": current_user.full_name,
                "reason": reason_text,
                "deleted_at": datetime.utcnow().isoformat(),
                "outcome": "SUCCESS"
            })
        )
        db.add(audit)

        # Explicitly decouple all historical audit logs for this inspection by setting inspection_id to NULL
        # This preserves the entire audit history while preventing FK constraint violation during deletion
        db.query(AuditLog).filter(AuditLog.inspection_id == saved_insp_id).update({"inspection_id": None})

        # Cascading database deletion (models specify cascade="all, delete-orphan")
        db.delete(inspection)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"[Supervisor Deletion Failed] Could not delete inspection {saved_insp_num}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed while deleting inspection {saved_insp_num}. Rollback executed; no changes saved."
        )

    # Post-commit failure-aware physical file cleanup
    for fp in files_to_remove:
        try:
            if os.path.isfile(fp):
                os.remove(fp)
        except Exception as file_err:
            logger.warning(f"[Supervisor Deletion Notice] Could not remove physical file '{fp}': {file_err}")

    logger.info(f"[Supervisor Audit] Inspection {saved_insp_num} deleted by Supervisor {current_user.officer_id}")

    return DeleteInspectionResponse(
        success=True,
        message=f"Inspection {saved_insp_num} and associated inspection data deleted successfully.",
        inspection_id=saved_insp_id,
        inspection_number=saved_insp_num
    )


@app.delete("/api/inspections/{inspection_id}/report", response_model=DeleteReportResponse, tags=["Supervisor Management"])
def delete_inspection_report(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_supervisor_or_admin)
):
    """
    Supervisor report deletion.
    Enforces backend role verification (SUPERVISOR or ADMIN only; INSPECTOR rejected with 403).
    Removes the Report database record and associated physical files inside an atomic transaction.
    The Inspection and all other inspection data remain completely intact.
    """
    inspection = db.query(Inspection).filter(
        or_(Inspection.id == inspection_id, Inspection.inspection_number == inspection_id)
    ).first()

    if not inspection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inspection '{inspection_id}' not found."
        )

    report = db.query(Report).filter(Report.inspection_id == inspection.id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No report found for inspection '{inspection.inspection_number}'."
        )

    saved_report_id = report.id
    files_to_remove = []
    for fp in [report.pdf_path, report.docx_path]:
        if fp and os.path.isfile(fp):
            files_to_remove.append(fp)

    try:
        # Create immutable audit log record
        audit = AuditLog(
            inspection_id=inspection.id,
            actor_id=current_user.officer_id,
            action="REPORT_DELETED",
            entity_type="report",
            entity_id=saved_report_id,
            details=json.dumps({
                "inspection_id": inspection.id,
                "inspection_number": inspection.inspection_number,
                "report_id": saved_report_id,
                "report_version": report.report_version,
                "pdf_hash": report.pdf_hash,
                "supervisor_id": current_user.officer_id,
                "supervisor_name": current_user.full_name,
                "deleted_at": datetime.utcnow().isoformat(),
                "outcome": "SUCCESS"
            })
        )
        db.add(audit)

        # Delete Report record (Inspection remains untouched)
        db.delete(report)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"[Supervisor Deletion Failed] Could not delete report {saved_report_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed while deleting report for inspection {inspection.inspection_number}. Rollback executed."
        )

    # Post-commit physical file cleanup
    for fp in files_to_remove:
        try:
            if os.path.isfile(fp):
                os.remove(fp)
        except Exception as e:
            logger.warning(f"Could not remove report file {fp}: {e}")

    logger.info(f"[Supervisor Audit] Report {saved_report_id} for inspection {inspection.inspection_number} deleted by Supervisor {current_user.officer_id}")

    return DeleteReportResponse(
        success=True,
        message=f"Report for inspection {inspection.inspection_number} deleted successfully. Inspection remains intact.",
        inspection_id=inspection.id,
        report_id=saved_report_id
    )


