"""
tests/test_inspection_number_concurrency.py

Comprehensive Concurrency & Initialization Test Suite for AUDIT-CONCUR-01
(PostgreSQL Atomic Inspection Number Allocation).

Validates:
- Case 1: Brand new year with no existing inspections -> LM-YYYY-00001
- Case 2: Existing sequential inspections through 00005 -> LM-YYYY-00006
- Case 3: Historical gaps (00001, 00003, 00007) -> next is 00008 (gaps NOT filled)
- Case 4: Idempotent initialization (existing counter row is not reset)
- Case 5: Multi-year isolation (each year maintains independent counter)
- Concurrency 1: 10 concurrent creations across independent database sessions
- Concurrency 2: 25 concurrent creations under high contention across independent sessions
- Concurrency 3: 15 concurrent HTTP POST requests via FastAPI TestClient
- Rollback semantics: Transaction rollback rolls back the counter and prevents orphaned/corrupted state
"""

import os
import re
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.models import Base, Inspection, Product, InspectionNumberCounter, User
from backend.main import allocate_inspection_number, generate_inspection_number, app
from fastapi.testclient import TestClient

LM_PATTERN = re.compile(r"^LM-(\d{4})-(\d{5})$")


@pytest.fixture
def db_session():
    from backend.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# =============================================================================
# SECTION 13: COUNTER INITIALIZATION & EDGE CASES
# =============================================================================

def test_case_1_no_existing_inspections_for_year(db_session):
    """CASE 1: A new year with no prior records starts at LM-YYYY-00001."""
    test_year = 2030
    num = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert num == f"LM-{test_year}-00001"


def test_case_2_existing_inspections_through_00005(db_session):
    """CASE 2: When existing records end at 00005, the next allocation is 00006."""
    test_year = 2031
    # Seed records through 00005
    for i in range(1, 6):
        db_session.add(Inspection(
            inspection_number=f"LM-{test_year}-{i:05d}",
            inspector_id="temp-officer-id",
            location="Test Location",
            status="DRAFT"
        ))
    db_session.commit()

    next_num = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert next_num == f"LM-{test_year}-00006"


def test_case_3_existing_numbers_contain_gaps(db_session):
    """
    CASE 3: Historical gaps (e.g. 00001, 00003, 00007).
    The allocator must allocate 00008 and NEVER fill historical gaps.
    """
    test_year = 2032
    gapped_seqs = [1, 3, 7]
    for s in gapped_seqs:
        db_session.add(Inspection(
            inspection_number=f"LM-{test_year}-{s:05d}",
            inspector_id="temp-officer-id",
            location="Test Location",
            status="DRAFT"
        ))
    db_session.commit()

    next_num = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert next_num == f"LM-{test_year}-00008", f"Expected 00008, got {next_num}"


def test_case_4_existing_counter_row_not_reset(db_session):
    """
    CASE 4: When a counter row already exists with next_number = N,
    re-initialization / schema migration logic must NOT reset it to 1.
    """
    test_year = 2033
    # Manually establish counter row at 42
    db_session.add(InspectionNumberCounter(year=test_year, next_number=42))
    db_session.commit()

    # Call allocator — should allocate 42 and advance to 43
    num1 = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert num1 == f"LM-{test_year}-00042"

    num2 = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert num2 == f"LM-{test_year}-00043"


def test_case_5_multiple_years_independent(db_session):
    """
    CASE 5: Multiple years maintain independent, non-interfering counters.
    """
    y1, y2 = 2034, 2035
    num_y1_a = allocate_inspection_number(db_session, year=y1)
    num_y2_a = allocate_inspection_number(db_session, year=y2)
    num_y1_b = allocate_inspection_number(db_session, year=y1)
    db_session.commit()

    assert num_y1_a == f"LM-{y1}-00001"
    assert num_y2_a == f"LM-{y2}-00001"
    assert num_y1_b == f"LM-{y1}-00002"


# =============================================================================
# SECTION 14: TRANSACTION ROLLBACK BEHAVIOR
# =============================================================================

def test_transaction_rollback_behavior(db_session):
    """
    SECTION 14: Transaction Rollback Semantics.
    When an inspection transaction fails after number allocation and rolls back,
    the counter row update in the database transaction also rolls back.
    A subsequent transaction can then allocate cleanly without error.
    """
    test_year = 2036
    # 1. Start transaction, allocate number
    num_aborted = allocate_inspection_number(db_session, year=test_year)
    assert num_aborted == f"LM-{test_year}-00001"

    # 2. Add invalid inspection with missing required fields or simulate rollback
    db_session.rollback()

    # 3. Next transaction creates a valid inspection
    num_retry = allocate_inspection_number(db_session, year=test_year)
    new_insp = Inspection(
        inspection_number=num_retry,
        inspector_id="temp-officer-id",
        location="Valid Location After Rollback",
        status="DRAFT"
    )
    db_session.add(new_insp)
    db_session.commit()

    # In single-thread transactional DB, rollback reverted counter to 1
    assert num_retry == f"LM-{test_year}-00001"

    # Next number advances to 2
    num_next = allocate_inspection_number(db_session, year=test_year)
    db_session.commit()
    assert num_next == f"LM-{test_year}-00002"


# =============================================================================
# SECTION 12: CONCURRENCY TESTS (INDEPENDENT DATABASE SESSIONS)
# =============================================================================

def test_concurrent_inspection_creation_10_workers():
    """
    Test 10 simultaneous concurrent inspection creations across separate DB sessions.
    Validates that each worker gets a strictly unique inspection number.
    """
    from backend.database import SessionLocal

    init_session = SessionLocal()
    officer = init_session.query(User).filter(User.officer_id == "DOCA-INSP-842").first()
    officer_user_id = officer.id if officer else str(uuid.uuid4())
    init_session.close()

    def create_single_inspection(worker_id: int):
        session = SessionLocal()
        try:
            insp_num = allocate_inspection_number(session, year=2026)
            new_insp = Inspection(
                inspection_number=insp_num,
                inspector_id=officer_user_id,
                location=f"Concurrent Test Market {worker_id}",
                status="DRAFT",
                notes=f"Worker {worker_id}"
            )
            session.add(new_insp)
            session.commit()
            return insp_num
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    NUM_WORKERS = 10
    results = []
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = [executor.submit(create_single_inspection, i) for i in range(NUM_WORKERS)]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == NUM_WORKERS, f"Expected {NUM_WORKERS} results, got {len(results)}"
    unique_numbers = set(results)
    assert len(unique_numbers) == NUM_WORKERS, f"Duplicates detected in 10-worker test: {results}"

    for num in results:
        assert LM_PATTERN.match(num), f"Invalid format: {num}"


def test_concurrent_inspection_creation_25_workers():
    """
    High-contention test: 25 simultaneous concurrent inspection creations across separate DB sessions.
    Proves that database row-level locking safely handles high concurrent throughput
    without duplicate numbers or collision-induced failures.
    """
    from backend.database import SessionLocal

    init_session = SessionLocal()
    officer = init_session.query(User).filter(User.officer_id == "DOCA-INSP-842").first()
    officer_user_id = officer.id if officer else str(uuid.uuid4())
    init_session.close()

    def create_single_inspection(worker_id: int):
        session = SessionLocal()
        try:
            insp_num = allocate_inspection_number(session, year=2026)
            new_insp = Inspection(
                inspection_number=insp_num,
                inspector_id=officer_user_id,
                location=f"High Contention Store {worker_id}",
                status="DRAFT",
                notes=f"High Contention Worker {worker_id}"
            )
            session.add(new_insp)
            session.commit()
            return insp_num
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    NUM_WORKERS = 25
    results = []
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = [executor.submit(create_single_inspection, i) for i in range(NUM_WORKERS)]
        for f in as_completed(futures):
            results.append(f.result())

    assert len(results) == NUM_WORKERS, f"Expected {NUM_WORKERS} results, got {len(results)}"
    unique_numbers = set(results)
    assert len(unique_numbers) == NUM_WORKERS, f"Duplicates detected in 25-worker test: {results}"

    for num in results:
        assert LM_PATTERN.match(num), f"Malformed inspection number: {num}"

    seqs = [int(n.split("-")[2]) for n in results]
    assert len(set(seqs)) == NUM_WORKERS


def test_concurrent_http_endpoint_creations():
    """
    End-to-End concurrency test simulating 15 concurrent HTTP POST /api/inspections requests
    through FastAPI client with authenticated JWT tokens.
    """
    client = TestClient(app)

    # Login to get token
    login_resp = client.post("/api/auth/login", json={
        "officer_id": "DOCA-INSP-842",
        "password": "admin123"
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def post_inspection(idx: int):
        c = TestClient(app)
        payload = {
            "product_name": f"Concurrent Flour Batch {idx}",
            "category": "Packaged Food",
            "location": f"Zone {idx} Delhi Warehouse",
            "client_draft_id": f"draft-concurrent-http-{uuid.uuid4().hex[:8]}"
        }
        resp = c.post("/api/inspections", headers=headers, json=payload)
        return resp.status_code, resp.json()

    NUM_REQUESTS = 15
    statuses = []
    inspection_numbers = []

    with ThreadPoolExecutor(max_workers=NUM_REQUESTS) as executor:
        futures = [executor.submit(post_inspection, i) for i in range(NUM_REQUESTS)]
        for f in as_completed(futures):
            status_code, data = f.result()
            statuses.append(status_code)
            if status_code == 201:
                inspection_numbers.append(data.get("inspection_number"))

    # All requests must succeed with 201 Created
    assert all(s == 201 for s in statuses), f"Non-201 status found: {statuses}"
    assert len(inspection_numbers) == NUM_REQUESTS
    assert len(set(inspection_numbers)) == NUM_REQUESTS, f"Duplicate inspection numbers in HTTP test: {inspection_numbers}"
