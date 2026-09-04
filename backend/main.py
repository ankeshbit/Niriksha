import os
import re
import json
import uuid
import shutil
import threading
from pathlib import Path
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
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.config import settings
from backend.database import get_db, engine, Base
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
    Report
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
    ChangePasswordRequest
)
from backend.auth_utils import verify_password, hash_password
from backend.auth_service import create_access_token, get_current_user
from backend.image_quality import assess_image_quality
from backend.ocr_service import ocr_service
from backend.extraction_service import extraction_service, cross_image_verification
from backend.rule_engine import rule_engine, get_rule_by_code
from backend.report_service import report_generator
from backend.supabase_storage import storage_service
from backend.seed import seed_database

# Initialize database schema and seeds on startup
Base.metadata.create_all(bind=engine)
try:
    seed_database()
except Exception as e:
    print(f"[Warning] Seed error on startup: {e}")

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

# ----------------- Helper Functions -----------------

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

# Thread-level lock to serialize inspection-number allocation.
# SQLite does not support sequences; this lock prevents a TOCTOU race where
# two threads both call db.query(Inspection).count() before either commits.
_inspection_number_lock = threading.Lock()

def _fetch_existing_draft(db: Session, inspector_id: str, draft_marker: str):
    """Re-query a draft inspection by its marker. Used for idempotent conflict recovery."""
    return db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.images),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.report)
    ).filter(
        Inspection.inspector_id == inspector_id,
        Inspection.notes.like(f"%{draft_marker}%")
    ).first()

def generate_inspection_number(db: Session) -> str:
    """Generates a sequential, official Legal Metrology inspection number.

    Must be called while holding _inspection_number_lock to prevent duplicate
    numbers under concurrent requests. The UNIQUE constraint on inspection_number
    is the final safety net; this lock prevents the majority of conflicts.
    """
    count = db.query(Inspection).count() + 1
    return f"LM-2026-{count:05d}"

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
    if img.quality_metadata_json:
        try:
            meta = json.loads(img.quality_metadata_json)
            quality_details = ImageQualityDetails(**meta)
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
    if decl.correction_reason and decl.correction_reason.startswith('{"conflict":'):
        try:
            cdata = json.loads(decl.correction_reason)
            has_conflict = cdata.get("conflict", has_conflict)
            conflicts = cdata.get("candidates", [])
            source_images = cdata.get("source_images", [])
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
        created_at=decl.created_at
    )

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
        evidence_items=evidence_items
    )

def serialize_report(rep: Report) -> ReportResponse:
    insp = rep.inspection
    return ReportResponse(
        id=rep.id,
        inspection_id=rep.inspection_id,
        report_version=rep.report_version,
        pdf_path=rep.pdf_path,
        download_url=f"/api/inspections/{rep.inspection_id}/report/pdf",
        legal_safety_statement=rep.legal_safety_statement,
        generated_at=rep.generated_at,
        inspection_number=insp.inspection_number if insp else None,
        product_name=insp.product.product_name if (insp and insp.product) else None,
        location=insp.location if insp else None,
        overall_status=insp.overall_status if insp else None
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

    return HealthCheckResponse(
        status="healthy" if db_status == "connected" else "degraded",
        app_name=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        database=db_status,
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

# ----------------- Dashboard Endpoint -----------------

@app.get("/api/dashboard", response_model=DashboardStatsResponse, tags=["Dashboard"])
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Returns real aggregate metric cards and recent inspections for the dashboard."""
    query = db.query(Inspection)
    if current_user.role != "ADMIN":
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

# ----------------- Inspection Endpoints -----------------

@app.post("/api/inspections", response_model=InspectionDetailResponse, status_code=status.HTTP_201_CREATED, tags=["Inspections"])
def create_inspection(
    req: CreateInspectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Creates a new inspection in DRAFT status with associated product details."""
    if not req.product_name.strip():
        raise HTTPException(status_code=400, detail="Product name is required")
    if not req.location.strip():
        raise HTTPException(status_code=400, detail="Inspection location is required")
    # NOTE: category is validated by Pydantic Literal — invalid values never reach here.

    # Build the draft marker string (used for both the fast-path and critical section).
    draft_marker: Optional[str] = None
    if req.client_draft_id and req.client_draft_id.strip():
        draft_marker = f"[client_draft_id:{req.client_draft_id.strip()}]"

    # --- Fast path (no lock) ---
    # If the inspection is already committed (e.g., a delayed retry) skip the lock entirely.
    if draft_marker:
        existing = _fetch_existing_draft(db, current_user.id, draft_marker)
        if existing:
            return existing

    # --- Critical section ---
    # The process-level lock serialises ALL inspection creation.  This means:
    #   • inspection numbers are generated strictly one-at-a-time (no TOCTOU on count).
    #   • the idempotency check is re-run INSIDE the lock so that, after Thread 1
    #     commits, Threads 2–N find the already-created record and return it instead
    #     of creating duplicates.
    # SQLite is effectively single-writer anyway, so this lock adds negligible latency.
    with _inspection_number_lock:
        # Re-check inside the lock: the winning thread may have committed while we waited.
        if draft_marker:
            existing = _fetch_existing_draft(db, current_user.id, draft_marker)
            if existing:
                return existing

        # Allocate the next sequential number while holding the lock.
        inspection_number = generate_inspection_number(db)

        notes_val = req.notes.strip() if req.notes else ""
        if draft_marker:
            notes_val = f"{notes_val} | {draft_marker}".strip(" |")

        new_inspection = Inspection(
            inspection_number=inspection_number,
            inspector_id=current_user.id,
            location=req.location.strip(),
            status="DRAFT",
            notes=notes_val if notes_val else None
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
            # Safety net: if the DB-level UNIQUE constraint fires despite the lock
            # (e.g., cross-process race), roll back and recover gracefully.
            db.rollback()
            if draft_marker:
                winner = _fetch_existing_draft(db, current_user.id, draft_marker)
                if winner:
                    return winner
            raise HTTPException(
                status_code=409,
                detail="Inspection number conflict — please retry."
            ) from exc

        db.refresh(new_inspection)

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
    if current_user.role != "ADMIN":
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
    if current_user.role != "ADMIN":
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
    """Retrieves single inspection details by ID."""
    inspection = db.query(Inspection).options(
        joinedload(Inspection.product),
        joinedload(Inspection.images),
        joinedload(Inspection.declarations),
        joinedload(Inspection.compliance_checks),
        joinedload(Inspection.report)
    ).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection record not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")
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
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

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
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

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
    if img.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this image")

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
    if img.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this image")

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
    if img.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this image")

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

# ----------------- OCR & Declaration Extraction Endpoints -----------------

@app.post("/api/inspections/{inspection_id}/ocr", response_model=RunOCRResponse, tags=["OCR & Declarations"])
def run_inspection_ocr_and_extraction(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Executes OCR and structured declaration parsing on uploaded package images."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    images = db.query(ProductImage).filter(
        ProductImage.inspection_id == inspection_id
    ).order_by(ProductImage.sequence_order.asc()).all()

    if not images:
        raise HTTPException(status_code=400, detail="Cannot run OCR: No images uploaded for this inspection")

    inspection.status = "OCR_PROCESSING"
    db.commit()

    all_raw_text_parts = []
    all_boxes = []
    saved_ocr_results = []
    per_image_declarations = {}

    product_ctx = {
        "product_name": inspection.product.product_name if inspection.product else "",
        "brand_name": inspection.product.brand_name if inspection.product else "",
        "category": inspection.product.category if inspection.product else "Packaged Food"
    }

    for img in images:
        clean_rel = img.file_path.lstrip("/")
        abs_path = BASE_DIR / clean_rel
        if not abs_path.exists():
            continue

        ocr_data = ocr_service.process_image(str(abs_path), image_id=img.id)
        existing_ocr = db.query(OCRResult).filter(OCRResult.image_id == img.id).first()
        boxes_dict = [b.model_dump() for b in ocr_data.text_boxes]
        
        if existing_ocr:
            existing_ocr.raw_text = ocr_data.raw_text
            existing_ocr.confidence = ocr_data.mean_confidence
            existing_ocr.bounding_boxes_json = json.dumps(boxes_dict)
            ocr_record = existing_ocr
        else:
            ocr_record = OCRResult(
                image_id=img.id,
                raw_text=ocr_data.raw_text,
                confidence=ocr_data.mean_confidence,
                bounding_boxes_json=json.dumps(boxes_dict)
            )
            db.add(ocr_record)

        db.flush()
        saved_ocr_results.append(ocr_record)

        if ocr_data.raw_text:
            all_raw_text_parts.append(ocr_data.raw_text)
        all_boxes.extend(ocr_data.text_boxes)

        # Extract declarations for this individual image
        img_ctx = dict(product_ctx)
        img_ctx["ocr_status"] = getattr(ocr_data, "ocr_status", "OCR_SUCCESS")
        img_items = extraction_service.extract_declarations(
            full_text=ocr_data.raw_text,
            text_boxes=ocr_data.text_boxes,
            product_context=img_ctx,
            image_id=img.id
        )
        per_image_declarations[img.id] = img_items

    combined_full_text = "\n".join(all_raw_text_parts)
    primary_image_id = images[0].id if images else None

    # Cross-image verification and conflict detection across all images
    merged_items, detected_conflicts = cross_image_verification(per_image_declarations)

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
        reason_val = None
        if item.has_conflict:
            reason_val = json.dumps({
                "conflict": True,
                "candidates": item.conflicts,
                "source_images": item.source_images
            })
            item.extraction_status = "CONFLICTING"
            v_status = "NEEDS_MANUAL_VERIFICATION"
        elif item.extraction_status in ["NOT_FOUND", "OCR_UNAVAILABLE"]:
            v_status = "NEEDS_MANUAL_VERIFICATION"
        else:
            v_status = "UNVERIFIED"

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

    inspection.status = "EXTRACTION_COMPLETE"
    log_audit(
        db,
        current_user.officer_id,
        "OCR_AND_EXTRACTION_COMPLETED",
        "inspection",
        inspection_id,
        inspection_id,
        details=f"Extracted {len(saved_declarations)} statutory declarations. Conflicts: {len(detected_conflicts)}"
    )
    db.commit()
    db.refresh(inspection)

    return RunOCRResponse(
        inspection_id=inspection.id,
        status=inspection.status,
        total_images_processed=len(images),
        declarations_count=len(saved_declarations),
        ocr_results=[serialize_ocr_result(r) for r in saved_ocr_results],
        declarations=[serialize_declaration(d) for d in saved_declarations],
        conflicts=detected_conflicts
    )

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
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

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
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    declarations = db.query(Declaration).filter(
        Declaration.inspection_id == inspection_id
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
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    decl = db.query(Declaration).filter(
        Declaration.inspection_id == inspection_id,
        Declaration.field_name == field_name
    ).first()

    if not decl:
        raise HTTPException(status_code=404, detail=f"Declaration field '{field_name}' not found")

    return serialize_declaration(decl)

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
    if decl.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this declaration")

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
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all()
    images = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).all()

    product_data = {
        "product_name": inspection.product.product_name if inspection.product else "",
        "brand_name": inspection.product.brand_name if inspection.product else "",
        "category": inspection.product.category if inspection.product else "Packaged Food"
    }

    # Execute deterministic rule engine
    eval_results = rule_engine.evaluate_inspection(inspection_id, product_data, declarations, images)

    # Idempotent replacement of previous checks and evidence for this inspection
    existing_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection_id).all()
    check_ids = [c.id for c in existing_checks]
    if check_ids:
        db.query(Evidence).filter(Evidence.check_id.in_(check_ids)).delete(synchronize_session=False)
        db.query(ComplianceCheck).filter(ComplianceCheck.id.in_(check_ids)).delete(synchronize_session=False)
    db.flush()

    saved_checks = []
    passed_count = 0
    non_comp_count = 0
    insufficient_count = 0

    for res in eval_results:
        rule_ver = db.query(RuleVersion).filter(RuleVersion.rule_code == res.rule_code).first()
        rule_version_id = rule_ver.id if rule_ver else "rule-ver-placeholder"

        check = ComplianceCheck(
            inspection_id=inspection_id,
            rule_version_id=rule_version_id,
            rule_code=res.rule_code,
            title=res.title,
            severity=res.severity.value,
            result_state=res.result_state.value,
            extracted_value=res.effective_value_used,
            explanation=res.explanation,
            adjudication_status="PENDING"
        )
        db.add(check)
        db.flush()

        for ev_data in res.evidence_items:
            evidence = Evidence(
                check_id=check.id,
                image_id=ev_data.image_id,
                bounding_box_json=json.dumps(ev_data.bounding_box) if ev_data.bounding_box else None,
                highlight_text=ev_data.highlight_text,
                reason=ev_data.reason
            )
            db.add(evidence)

        saved_checks.append(check)

        if res.result_state == "PASS":
            passed_count += 1
        elif res.result_state == "POTENTIAL_NON_COMPLIANCE":
            non_comp_count += 1
        elif res.result_state in ["INSUFFICIENT_EVIDENCE", "NEEDS_MANUAL_VERIFICATION"]:
            insufficient_count += 1

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
        findings=[serialize_finding(c) for c in saved_checks]
    )

@app.get("/api/inspections/{inspection_id}/findings", response_model=List[FindingResponse], tags=["Rule Engine & Adjudication"])
def get_inspection_findings(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieves all potential findings and compliance check results for an inspection."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    checks = db.query(ComplianceCheck).filter(
        ComplianceCheck.inspection_id == inspection_id
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
    if check.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this finding")

    return serialize_finding(check)

@app.patch("/api/findings/{finding_id}/adjudicate", response_model=FindingResponse, tags=["Rule Engine & Adjudication"])
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
    if check.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this finding")

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
    if check.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this finding")

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
    if check.inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this finding")

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
    current_user: User = Depends(get_current_user)
):
    """Generates an official Statutory Legal Metrology Inspection Report PDF from real database records."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    product = inspection.product
    inspector = inspection.inspector or current_user
    declarations = db.query(Declaration).filter(Declaration.inspection_id == inspection_id).all()
    compliance_checks = db.query(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection_id).all()
    evidence_items = db.query(Evidence).join(ComplianceCheck).filter(ComplianceCheck.inspection_id == inspection_id).all()

    existing_report = db.query(Report).filter(Report.inspection_id == inspection_id).first()
    new_version = (existing_report.report_version + 1) if existing_report else 1

    pdf_path = report_generator.generate_pdf(
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
            storage_service.upload_report_pdf(inspection_id, new_version, pdf_bytes)
        except Exception as e:
            print(f"[SupabaseStorage] Warning: Failed to upload report PDF to Supabase: {e}")

    safety_statement = (
        "This official inspection report was generated by the AI-Assisted Legal Metrology Packaged-Commodity Inspection System (DoCA). "
        "Compliance evaluations were executed via deterministic PCR 2011 rule verification under designated inspecting officer authority."
    )

    if existing_report:
        existing_report.report_version = new_version
        existing_report.pdf_path = pdf_path
        existing_report.legal_safety_statement = safety_statement
        existing_report.generated_at = datetime.utcnow()
        report_record = existing_report
    else:
        report_record = Report(
            inspection_id=inspection_id,
            report_version=new_version,
            pdf_path=pdf_path,
            legal_safety_statement=safety_statement
        )
        db.add(report_record)

    log_audit(
        db,
        current_user.officer_id,
        "REPORT_GENERATED",
        "report",
        report_record.id,
        inspection_id,
        details=f"Generated statutory PDF inspection report v{new_version} ({inspection.inspection_number})"
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
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    report_record = db.query(Report).filter(Report.inspection_id == inspection_id).first()
    if not report_record:
        # Auto-generate if not yet generated
        return generate_inspection_report(inspection_id, db, current_user)

    return serialize_report(report_record)

@app.get("/api/inspections/{inspection_id}/report/pdf", tags=["Reports"])
def stream_inspection_report_pdf(
    inspection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Streams the official PDF binary for viewing or download."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

    report_record = db.query(Report).filter(Report.inspection_id == inspection_id).first()
    if not report_record or not Path(report_record.pdf_path).exists():
        generate_inspection_report(inspection_id, db, current_user)
        report_record = db.query(Report).filter(Report.inspection_id == inspection_id).first()

    pdf_file = Path(report_record.pdf_path)
    if not pdf_file.exists():
        raise HTTPException(status_code=404, detail="Generated PDF report file not found on disk")

    filename = f"LM_Report_{inspection.inspection_number}.pdf"
    return FileResponse(
        str(pdf_file),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
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
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

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

    if req.final_status:
        inspection.overall_status = req.final_status
    elif has_confirmed_violations:
        inspection.overall_status = "POTENTIAL_NON_COMPLIANCE"
    elif has_insufficient:
        inspection.overall_status = "NEEDS_MANUAL_VERIFICATION"
    else:
        inspection.overall_status = "NO_POTENTIAL_VIOLATIONS"

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
    reports = db.query(Report).order_by(Report.generated_at.desc()).all()
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

    if inspection and inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this report")

    return serialize_report(report)


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
    if inspection.inspector_id != current_user.id and current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Unauthorized access to this inspection")

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

