"""
backend/ocr_job_service.py

Durable Asynchronous OCR Job Manager & Worker.
- PostgreSQL-backed persistent job state machine (survives container restarts, OOM kills, mobile disconnects).
- Atomic job claiming via PostgreSQL `FOR UPDATE SKIP LOCKED`.
- Active lease/heartbeat tracking with automated stale-job recovery.
- Idempotent start, processing, and declaration persistence.
- Memory safety telemetry logging with process RSS monitoring.
"""

import os
import sys
import time
import json
import uuid
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import psutil
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database import SessionLocal, engine
from backend.models import (
    OCRJob,
    Inspection,
    ProductImage,
    OCRResult,
    Declaration,
    AuditLog,
    User
)
from backend.config import settings
from backend.ocr_service import ocr_service
from backend.barcode_service import barcode_service
from backend.extraction_service import extraction_service, cross_image_verification
from backend.declaration_validation_service import declaration_validation_engine

logger = logging.getLogger("backend.ocr_job_service")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LEASE_TIMEOUT_SECONDS = 120.0
MAX_JOB_RETRIES = 2


def _get_process_rss_mb() -> float:
    """Returns current process Resident Set Size (RSS) in MB."""
    try:
        proc = psutil.Process(os.getpid())
        return round(proc.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        return 0.0


class OCRJobService:
    """
    Manages durable OCR Job lifecycle, atomic worker dispatching,
    heartbeats, crash recovery, and state transitions.
    """

    def __init__(self):
        self._worker_thread: Optional[threading.Thread] = None
        self._worker_running: bool = False
        self._worker_id: str = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"

    # ─── Public API: Job Creation & Status ────────────────────────────────────

    def create_or_get_job(
        self,
        inspection_id: str,
        db: Session,
        force: bool = False,
        inspector_id: Optional[str] = None
    ) -> Tuple[OCRJob, bool]:
        """
        Idempotently returns an existing active/completed job, or creates a new PENDING job.
        Returns (job, is_existing).
        """
        # 1. Check for existing active job (PENDING or PROCESSING)
        existing_active = (
            db.query(OCRJob)
            .filter(
                OCRJob.inspection_id == inspection_id,
                OCRJob.status.in_(["PENDING", "PROCESSING"])
            )
            .order_by(OCRJob.created_at.desc())
            .first()
        )

        if existing_active:
            # Check if active job has become stale (crashed worker)
            if self._is_job_stale(existing_active):
                logger.warning(
                    f"[STALE_JOB_DETECTED] job_id={existing_active.id} "
                    f"inspection_id={inspection_id} heartbeat={existing_active.heartbeat_at}"
                )
                self._handle_stale_job(existing_active, db)
                db.commit()
                # Reload refreshed state
                db.refresh(existing_active)
            else:
                logger.info(
                    f"[IDEMPOTENT_OCR_JOB_HIT] job_id={existing_active.id} "
                    f"status={existing_active.status} stage={existing_active.current_stage}"
                )
                return existing_active, True

        # 2. If not force, check if inspection already completed or declarations exist
        if not force:
            existing_completed = (
                db.query(OCRJob)
                .filter(
                    OCRJob.inspection_id == inspection_id,
                    OCRJob.status == "COMPLETED"
                )
                .order_by(OCRJob.completed_at.desc())
                .first()
            )
            if existing_completed:
                return existing_completed, True

            # Also check if inspection declarations are already present
            decl_count = db.query(Declaration).filter(Declaration.inspection_id == inspection_id).count()
            if decl_count > 0:
                insp = db.query(Inspection).filter(Inspection.id == inspection_id).first()
                if insp and insp.status in ["EXTRACTION_COMPLETE", "RULE_EVALUATION_COMPLETE", "COMPLETED"]:
                    synthetic_job = OCRJob(
                        id=f"synth-{inspection_id[:8]}",
                        inspection_id=inspection_id,
                        status="COMPLETED",
                        current_stage="COMPLETED",
                        progress_percent=100,
                        created_at=insp.created_at or datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                        ocr_summary_json=json.dumps({"declarations_count": decl_count})
                    )
                    return synthetic_job, True

        # 3. Verify that inspection has uploaded images
        img_count = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).count()
        if img_count == 0:
            raise ValueError("Cannot start OCR: No package images uploaded for this inspection.")

        # 4. Create new PENDING job
        new_job = OCRJob(
            id=str(uuid.uuid4()),
            inspection_id=inspection_id,
            status="PENDING",
            current_stage="QUEUED",
            progress_percent=5,
            created_at=datetime.utcnow(),
            max_retries=MAX_JOB_RETRIES,
            retry_count=0
        )
        db.add(new_job)

        # Update inspection status
        insp = db.query(Inspection).filter(Inspection.id == inspection_id).first()
        if insp:
            insp.status = "OCR_PROCESSING"

        db.commit()
        db.refresh(new_job)

        logger.info(
            f"[OCR_JOB_CREATED] job_id={new_job.id} inspection_id={inspection_id} "
            f"images={img_count} rss={_get_process_rss_mb()}MB"
        )

        # Proactively notify/kick background worker
        self.trigger_worker()

        return new_job, False

    def get_job_status(self, inspection_id: str, db: Session) -> Optional[OCRJob]:
        """
        Fetches the latest job for an inspection and performs on-the-fly stale check.
        """
        job = (
            db.query(OCRJob)
            .filter(OCRJob.inspection_id == inspection_id)
            .order_by(OCRJob.created_at.desc())
            .first()
        )
        if not job:
            return None

        # If job is in PROCESSING, check if it crashed
        if job.status == "PROCESSING" and self._is_job_stale(job):
            logger.warning(f"[POLL_RECOVER_STALE] job_id={job.id} stale lease detected on poll")
            self._handle_stale_job(job, db)
            db.commit()
            db.refresh(job)

        return job

    # ─── Stale Job & Crash Recovery ──────────────────────────────────────────

    def _is_job_stale(self, job: OCRJob) -> bool:
        """Determines if a job's lease has expired without a heartbeat."""
        if job.status != "PROCESSING":
            return False
        cutoff_time = job.heartbeat_at or job.started_at or job.created_at
        if not cutoff_time:
            return False
        age_seconds = (datetime.utcnow() - cutoff_time).total_seconds()
        return age_seconds > DEFAULT_LEASE_TIMEOUT_SECONDS

    def _handle_stale_job(self, job: OCRJob, db: Session):
        """
        Recovers a crashed/stale job:
        - If retry_count < max_retries: increments retry_count and sets status back to PENDING.
        - If retry_count >= max_retries: sets status to FAILED and inspection to OCR_FAILED.
        """
        if job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = "PENDING"
            job.current_stage = f"QUEUED_RETRY_{job.retry_count}"
            job.error_code = "WORKER_CRASH_RECOVERED"
            job.error_message = (
                f"Worker heartbeat timeout (container restart or OOM). "
                f"Automatically scheduling retry {job.retry_count} of {job.max_retries}."
            )
            job.heartbeat_at = None
            job.worker_id = None
            logger.info(
                f"[STALE_JOB_RETRY_SCHEDULED] job_id={job.id} "
                f"retry={job.retry_count}/{job.max_retries}"
            )
        else:
            job.status = "FAILED"
            job.current_stage = "FAILED"
            job.completed_at = datetime.utcnow()
            job.error_code = "OCR_OOM_TERMINATED"
            job.error_message = (
                "OCR analysis exceeded server memory limits after retry attempts. "
                "Your images are safely preserved. Please tap retry to re-analyze."
            )
            insp = db.query(Inspection).filter(Inspection.id == job.inspection_id).first()
            if insp:
                insp.status = "OCR_FAILED"
            logger.error(
                f"[STALE_JOB_TERMINAL_FAILURE] job_id={job.id} max retries exceeded."
            )

    def recover_stale_jobs_on_startup(self, db: Session) -> int:
        """
        Mandatory Startup Recovery:
        Sweeps the database on container boot for any jobs stranded in PROCESSING
        due to prior container OOM/SIGKILL or platform reboot.
        Safely increments retries and re-queues to PENDING, or transitions exhausted jobs to FAILED
        and sets inspection.status = 'OCR_FAILED'.
        Ensures inspections are NEVER left stranded in OCR_PROCESSING.
        """
        try:
            processing_jobs = (
                db.query(OCRJob)
                .filter(OCRJob.status == "PROCESSING")
                .all()
            )
            recovered_count = 0
            for job in processing_jobs:
                if self._is_job_stale(job):
                    logger.warning(
                        f"[STARTUP_STALE_JOB_FOUND] job_id={job.id} inspection_id={job.inspection_id} "
                        f"retries={job.retry_count}/{job.max_retries}"
                    )
                    self._handle_stale_job(job, db)
                    recovered_count += 1

            # Also ensure no inspections are stranded in OCR_PROCESSING if no active job exists
            stranded_inspections = (
                db.query(Inspection)
                .filter(Inspection.status == "OCR_PROCESSING")
                .all()
            )
            for insp in stranded_inspections:
                active_job = (
                    db.query(OCRJob)
                    .filter(
                        OCRJob.inspection_id == insp.id,
                        OCRJob.status.in_(["PENDING", "PROCESSING"])
                    )
                    .first()
                )
                if not active_job:
                    decls = db.query(Declaration).filter(Declaration.inspection_id == insp.id).count()
                    if decls > 0:
                        insp.status = "EXTRACTION_COMPLETE"
                        logger.info(f"[STARTUP_INSPECTION_RECOVERED] inspection_id={insp.id} -> EXTRACTION_COMPLETE")
                    else:
                        insp.status = "OCR_FAILED"
                        logger.warning(f"[STARTUP_INSPECTION_RECOVERED] inspection_id={insp.id} -> OCR_FAILED (no active job)")
                    recovered_count += 1

            db.commit()
            logger.info(f"[STARTUP_RECOVERY_COMPLETE] Checked {len(processing_jobs)} processing jobs; recovered {recovered_count}")
            return recovered_count
        except Exception as e:
            db.rollback()
            logger.error(f"[STARTUP_RECOVERY_ERROR] {e}", exc_info=True)
            return 0

    # ─── Atomic Worker Claiming (PostgreSQL SKIP LOCKED) ─────────────────────

    def claim_next_job(self, db: Session) -> Optional[Tuple[str, str, int]]:
        """
        Atomically claims a pending or stale job using PostgreSQL's `FOR UPDATE SKIP LOCKED`.
        Returns (job_id, inspection_id, retry_count) or None.
        """
        now = datetime.utcnow()
        stale_cutoff = now - timedelta(seconds=DEFAULT_LEASE_TIMEOUT_SECONDS)

        # Atomic PostgreSQL claim query
        # Works seamlessly across PostgreSQL / Neon
        claim_sql = text("""
            UPDATE ocr_jobs
            SET status = 'PROCESSING',
                started_at = :now,
                heartbeat_at = :now,
                worker_id = :worker_id
            WHERE id = (
                SELECT id FROM ocr_jobs
                WHERE status = 'PENDING'
                   OR (status = 'PROCESSING' AND heartbeat_at < :stale_cutoff AND retry_count < max_retries)
                ORDER BY created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING id, inspection_id, retry_count;
        """)

        try:
            res = db.execute(
                claim_sql,
                {
                    "now": now,
                    "stale_cutoff": stale_cutoff,
                    "worker_id": self._worker_id,
                }
            ).fetchone()
            db.commit()

            if res:
                job_id, inspection_id, retry_count = res[0], res[1], res[2]
                logger.info(
                    f"[JOB_CLAIMED_ATOMIC] job_id={job_id} inspection_id={inspection_id} "
                    f"worker_id={self._worker_id} retry={retry_count}"
                )
                return str(job_id), str(inspection_id), int(retry_count)
            return None
        except Exception as e:
            db.rollback()
            logger.error(f"[JOB_CLAIM_ERROR] {e}")
            return None

    # ─── Job Execution Pipeline ──────────────────────────────────────────────

    def process_job_execution(self, job_id: str, inspection_id: str):
        """
        Executes the complete OCR and declaration extraction pipeline for a claimed job.
        Maintains heartbeats and memory telemetry throughout.
        """
        rss_start = _get_process_rss_mb()
        t_start = time.time()
        logger.info(
            f"[EXECUTE_JOB_START] job_id={job_id} inspection_id={inspection_id} "
            f"initial_rss={rss_start}MB"
        )

        db: Session = SessionLocal()
        try:
            job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
            if not job or job.status != "PROCESSING":
                logger.warning(f"[EXECUTE_JOB_ABORT] job_id={job_id} status is no longer PROCESSING")
                return

            insp = db.query(Inspection).filter(Inspection.id == inspection_id).first()
            if not insp:
                self._fail_job(job, "INSPECTION_NOT_FOUND", "Associated inspection was not found.", db)
                return

            images = (
                db.query(ProductImage)
                .filter(ProductImage.inspection_id == inspection_id)
                .order_by(ProductImage.sequence_order.asc())
                .all()
            )
            if not images:
                self._fail_job(job, "NO_IMAGES", "No package images found for inspection.", db)
                return

            # Eagerly capture primitive values before detachment
            image_specs = [
                (img.id, img.file_path, img.view_type)
                for img in images
            ]
            _product = insp.product
            product_ctx = {
                "product_name": _product.product_name if _product else "",
                "brand_name": _product.brand_name if _product else "",
                "category": _product.category if _product else "Packaged Food"
            }
            inspector_officer_id = str(insp.inspector.officer_id) if (insp.inspector and insp.inspector.officer_id) else "SYSTEM"

            # Update stage: INITIALIZING
            job.current_stage = "INITIALIZING_OCR"
            job.progress_percent = 15
            job.heartbeat_at = datetime.utcnow()
            db.commit()

            # Eagerly close DB connection to return socket to pool during heavy OCR inference
            db.close()
            logger.info(f"[DB_CLOSED_FOR_INFERENCE] job_id={job_id} Session released to pool")

            all_raw_text_parts = []
            all_boxes = []
            per_image_declarations = {}
            per_image_barcodes = {}
            ocr_processed_items = []

            total_images = len(image_specs)
            for idx, (img_id, img_file_path, view_type) in enumerate(image_specs, 1):
                # Reconnect briefly to update heartbeat & stage
                db = SessionLocal()
                stage_name = f"OCR_IMAGE_{idx}"
                job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                if job:
                    job.current_stage = stage_name
                    # Genuine progress: 20% to 65% scaled across images
                    job.progress_percent = int(20 + (45 * (idx - 0.5) / total_images))
                    job.heartbeat_at = datetime.utcnow()
                    db.commit()
                db.close()

                clean_rel = img_file_path.lstrip("/\\")
                abs_path = BASE_DIR / clean_rel
                if not abs_path.exists():
                    logger.warning(f"[IMG_NOT_FOUND] job_id={job_id} path={abs_path}")
                    continue

                t_img_start = time.time()
                rss_pre = _get_process_rss_mb()

                # Process image through ModularOCRService (using MAX_OCR_DIMENSION=800)
                ocr_data = ocr_service.process_image(str(abs_path), image_id=img_id)
                t_img_dur = time.time() - t_img_start
                rss_post = _get_process_rss_mb()

                logger.info(
                    f"[OCR_TELEMETRY] job_id={job_id} img_idx={idx} img_id={img_id} "
                    f"duration={t_img_dur:.2f}s boxes={len(ocr_data.text_boxes)} "
                    f"mean_conf={ocr_data.mean_confidence:.2f} "
                    f"rss_before={rss_pre}MB rss_after={rss_post}MB delta={rss_post-rss_pre:.1f}MB"
                )

                # Barcode detection
                img_barcodes = barcode_service.detect_and_decode(str(abs_path), source_image_id=img_id, source_image_path=img_file_path)
                img_barcodes = barcode_service.cross_validate_with_ocr(img_barcodes, ocr_data.raw_text)
                per_image_barcodes[img_id] = img_barcodes

                # Declaration extraction per image
                img_ctx = dict(product_ctx)
                img_ctx["ocr_status"] = getattr(ocr_data, "ocr_status", "OCR_SUCCESS")
                img_items = extraction_service.extract_declarations(
                    full_text=(ocr_data.normalized_text or ocr_data.raw_text),
                    text_boxes=ocr_data.text_boxes,
                    product_context=img_ctx,
                    image_id=img_id,
                    image_path=img_file_path
                )
                per_image_declarations[img_id] = img_items

                norm_or_raw = ocr_data.normalized_text or ocr_data.raw_text
                if norm_or_raw:
                    all_raw_text_parts.append(norm_or_raw)
                all_boxes.extend(ocr_data.text_boxes)
                ocr_processed_items.append((img_id, ocr_data, img_barcodes))

            # Reconnect DB for persistence phase
            db = SessionLocal()
            job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
            if job:
                job.current_stage = "EXTRACTING_DECLARATIONS"
                job.progress_percent = 75
                job.heartbeat_at = datetime.utcnow()
                db.commit()

            # 1. Persist OCRResult records
            for img_id, ocr_data, img_barcodes in ocr_processed_items:
                boxes_dict = [b.model_dump() for b in ocr_data.text_boxes]
                existing_ocr = db.query(OCRResult).filter(OCRResult.image_id == img_id).first()
                if existing_ocr:
                    existing_ocr.raw_text = ocr_data.raw_text
                    existing_ocr.normalized_text = ocr_data.normalized_text
                    existing_ocr.confidence = ocr_data.mean_confidence
                    existing_ocr.bounding_boxes_json = json.dumps(boxes_dict)
                else:
                    db.add(OCRResult(
                        image_id=img_id,
                        raw_text=ocr_data.raw_text,
                        normalized_text=ocr_data.normalized_text,
                        confidence=ocr_data.mean_confidence,
                        bounding_boxes_json=json.dumps(boxes_dict)
                    ))
                try:
                    db_img = db.query(ProductImage).filter(ProductImage.id == img_id).first()
                    if db_img:
                        meta = json.loads(db_img.quality_metadata_json) if db_img.quality_metadata_json else {}
                        meta["barcodes"] = [b.model_dump() for b in img_barcodes]
                        db_img.quality_metadata_json = json.dumps(meta)
                except Exception:
                    pass
            db.flush()

            # 2. Cross-image consolidation
            merged_items, detected_conflicts = cross_image_verification(per_image_declarations)
            primary_image_id = image_specs[0][0] if image_specs else None
            combined_full_text = "\n".join(all_raw_text_parts)

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

            # 3. Persist Declarations (atomic delete and replace)
            db.query(Declaration).filter(Declaration.inspection_id == inspection_id).delete()
            db.flush()

            saved_declarations = []
            for item in merged_items:
                meta_dict = {}
                if item.has_conflict:
                    meta_dict = {"conflict": True, "candidates": item.conflicts, "source_images": item.source_images}
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
            db.flush()

            # 4. Unified Declaration Matrix & Compliance Evaluation
            if job:
                job.current_stage = "COMPLIANCE_EVALUATION"
                job.progress_percent = 90
                job.heartbeat_at = datetime.utcnow()
                db.commit()

            try:
                all_imgs = db.query(ProductImage).filter(ProductImage.inspection_id == inspection_id).all()
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
                logger.warning(f"[DECLARATION_MATRIX_WARN] {e}")

            # 5. Final Status Transitions & Audit Log
            db_inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
            if db_inspection:
                db_inspection.status = "EXTRACTION_COMPLETE"

            total_elapsed = round(time.time() - t_start, 2)
            rss_final = _get_process_rss_mb()

            summary = {
                "declarations_count": len(saved_declarations),
                "conflicts_count": len(detected_conflicts),
                "total_images": len(image_specs),
                "total_elapsed_seconds": total_elapsed,
                "peak_rss_mb": rss_final
            }

            job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
            if job:
                job.status = "COMPLETED"
                job.current_stage = "COMPLETED"
                job.progress_percent = 100
                job.completed_at = datetime.utcnow()
                job.heartbeat_at = datetime.utcnow()
                job.ocr_summary_json = json.dumps(summary)

            # Audit Log
            audit = AuditLog(
                inspection_id=inspection_id,
                actor_id=inspector_officer_id,
                action="OCR_JOB_COMPLETED",
                entity_type="ocr_job",
                entity_id=job_id,
                details=f"Extracted {len(saved_declarations)} declarations in {total_elapsed}s (peak RSS: {rss_final}MB)"
            )
            db.add(audit)
            db.commit()

            logger.info(
                f"[EXECUTE_JOB_SUCCESS] job_id={job_id} inspection_id={inspection_id} "
                f"decls={len(saved_declarations)} elapsed={total_elapsed}s peak_rss={rss_final}MB"
            )
            return True

        except Exception as err:
            logger.error(f"[EXECUTE_JOB_FAILED] job_id={job_id} error={err}", exc_info=True)
            db.rollback()
            try:
                fail_job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
                if fail_job:
                    self._fail_job(fail_job, "OCR_PIPELINE_ERROR", str(err), db)
            except Exception:
                pass
            return False
        finally:
            db.close()

    def _fail_job(self, job: OCRJob, code: str, msg: str, db: Session):
        """Sets job and inspection to failed state."""
        job.status = "FAILED"
        job.current_stage = "FAILED"
        job.completed_at = datetime.utcnow()
        job.error_code = code
        job.error_message = msg
        insp = db.query(Inspection).filter(Inspection.id == job.inspection_id).first()
        if insp:
            insp.status = "OCR_FAILED"
        db.commit()

    # ─── Worker Runner Loop ──────────────────────────────────────────────────

    def start_worker_loop(self):
        """Starts the background worker thread if not already running."""
        if self._worker_running:
            return
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            name="ocr-job-worker",
            daemon=True
        )
        self._worker_thread.start()
        logger.info(f"[OCR_WORKER_STARTED] worker_id={self._worker_id}")

    def stop_worker_loop(self):
        """Stops the background worker loop (for tests or clean shutdown)."""
        self._worker_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None
        logger.info("[OCR_WORKER_STOPPED]")

    def trigger_worker(self):
        """Ensures worker loop is alive and running."""
        if not self._worker_running or not self._worker_thread or not self._worker_thread.is_alive():
            self.start_worker_loop()

    def _run_worker(self):
        """Internal worker poll loop for asynchronous jobs."""
        logger.info("[OCR_WORKER_LOOP] Polling for jobs...")
        idle_cycles = 0
        while self._worker_running:
            try:
                db = SessionLocal()
                claimed = self.claim_next_job(db)
                db.close()

                if claimed:
                    job_id, inspection_id, retry_count = claimed
                    self.process_job_execution(job_id, inspection_id)
                    idle_cycles = 0
                else:
                    idle_cycles += 1
                    # Sleep 1.5s when active, backoff up to 5s if idle
                    sleep_time = min(5.0, 1.5 + (idle_cycles * 0.2))
                    time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"[OCR_WORKER_LOOP_ERROR] {e}", exc_info=True)
                time.sleep(3.0)


# Global singleton instance
ocr_job_service = OCRJobService()
