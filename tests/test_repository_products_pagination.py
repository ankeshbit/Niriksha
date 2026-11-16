"""
tests/test_repository_products_pagination.py

Confirms SQL-level pagination and filtering for:
1. GET /api/repository/products (and alias /api/products/search)
2. GET /api/repository/products/{product_key}/inspections (and alias /api/products/{product_key}/history)
"""

import uuid
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings
from backend.database import SessionLocal
from backend.models import User, Inspection, Product, Declaration
from backend.models import generate_product_key

client = TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    resp = client.post("/api/auth/login", json={
        "officer_id": settings.SEED_OFFICER_ID,
        "password": settings.SEED_OFFICER_PASSWORD
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def seeded_pagination_data():
    """Seeds 25 distinct products and 15 inspections for one repeated product."""
    db = SessionLocal()
    officer = db.query(User).filter(User.officer_id == settings.SEED_OFFICER_ID).first()
    assert officer is not None
    officer_id = officer.id

    now = datetime.utcnow()
    prefix = f"TestPag_{uuid.uuid4().hex[:6]}"

    # 1. Seed 25 distinct products (each with 1 inspection)
    created_product_keys = []
    for i in range(25):
        insp_id = str(uuid.uuid4())
        created_time = now - timedelta(minutes=(30 - i))
        cat = "Packaged Food" if i < 15 else "Personal Care / Household"
        status = "COMPLETED" if i % 2 == 0 else "DRAFT"
        overall = "NO_POTENTIAL_VIOLATIONS" if i % 2 == 0 else "POTENTIAL_NON_COMPLIANCE"
        p_name = f"{prefix}_Product_{i:02d}"
        b_name = f"{prefix}_Brand"
        pkey = generate_product_key(p_name, b_name, cat)

        insp = Inspection(
            id=insp_id,
            inspection_number=f"INSP-PAG-{i:03d}-{uuid.uuid4().hex[:4]}",
            inspector_id=officer_id,
            location="Warehouse 1",
            status=status,
            overall_status=overall,
            created_at=created_time
        )
        prod = Product(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            product_name=p_name,
            brand_name=b_name,
            category=cat,
            batch_number=f"BATCH-{i:02d}",
            product_key=pkey,
            created_at=created_time
        )
        decl = Declaration(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            field_name="manufacturer_name",
            extracted_value=f"Mfg_{prefix}_{i:02d}",
            confidence=0.95,
            created_at=created_time
        )
        db.add_all([insp, prod, decl])
        created_product_keys.append(pkey)

    # 2. Seed 15 chronological inspections for a SINGLE repeated product
    history_product_name = f"{prefix}_History_Product"
    history_brand_name = f"{prefix}_History_Brand"
    history_category = "Packaged Food"
    history_pkey = generate_product_key(history_product_name, history_brand_name, history_category)

    history_insp_ids = []
    for j in range(15):
        insp_id = str(uuid.uuid4())
        created_time = now - timedelta(hours=(20 - j))
        insp = Inspection(
            id=insp_id,
            inspection_number=f"INSP-HIST-{j:03d}-{uuid.uuid4().hex[:4]}",
            inspector_id=officer_id,
            location="Surveillance Hub",
            status="COMPLETED",
            overall_status="NO_POTENTIAL_VIOLATIONS",
            created_at=created_time
        )
        prod = Product(
            id=str(uuid.uuid4()),
            inspection_id=insp_id,
            product_name=history_product_name,
            brand_name=history_brand_name,
            category=history_category,
            batch_number=f"HIST-BATCH-{j:02d}",
            product_key=history_pkey,
            created_at=created_time
        )
        db.add_all([insp, prod])
        history_insp_ids.append(insp_id)

    db.commit()
    db.close()

    return {
        "prefix": prefix,
        "product_keys": created_product_keys,
        "history_pkey": history_pkey,
        "history_insp_ids": history_insp_ids
    }


def test_repository_products_pagination_limits_and_offsets(auth_headers, seeded_pagination_data):
    prefix = seeded_pagination_data["prefix"]

    # Filter to only our seeded test prefix so test assertions are deterministic
    # Page 1 (size 10)
    p1 = client.get(f"/api/repository/products?search={prefix}&page=1&page_size=10", headers=auth_headers).json()
    assert p1["page"] == 1
    assert p1["page_size"] == 10
    assert p1["total"] == 26  # 25 distinct + 1 repeated entity
    assert p1["total_pages"] == 3
    assert len(p1["items"]) == 10
    p1_keys = [item["product_key"] for item in p1["items"]]
    assert len(set(p1_keys)) == 10

    # Page 2 (size 10)
    p2 = client.get(f"/api/repository/products?search={prefix}&page=2&page_size=10", headers=auth_headers).json()
    assert p2["page"] == 2
    assert p2["page_size"] == 10
    assert p2["total"] == 26
    assert len(p2["items"]) == 10
    p2_keys = [item["product_key"] for item in p2["items"]]
    assert len(set(p2_keys)) == 10
    # No overlap between page 1 and page 2
    assert set(p1_keys).isdisjoint(set(p2_keys))

    # Page 3 (size 10) -> remaining 6 items
    p3 = client.get(f"/api/repository/products?search={prefix}&page=3&page_size=10", headers=auth_headers).json()
    assert p3["page"] == 3
    assert p3["page_size"] == 10
    assert len(p3["items"]) == 6
    p3_keys = [item["product_key"] for item in p3["items"]]
    assert len(set(p3_keys)) == 6
    assert set(p1_keys).isdisjoint(set(p3_keys))
    assert set(p2_keys).isdisjoint(set(p3_keys))


def test_repository_products_filters(auth_headers, seeded_pagination_data):
    prefix = seeded_pagination_data["prefix"]

    # Category filter
    resp_cat = client.get(
        f"/api/repository/products?search={prefix}&category=Personal+Care+/+Household",
        headers=auth_headers
    ).json()
    assert resp_cat["total"] == 10
    assert all(item["category"] == "Personal Care / Household" for item in resp_cat["items"])

    # Compliance status filter
    resp_comp = client.get(
        f"/api/repository/products?search={prefix}&compliance_status=no_potential_violations",
        headers=auth_headers
    ).json()
    assert resp_comp["total"] > 0
    assert all(item["latest_compliance_status"] == "NO_POTENTIAL_VIOLATIONS" for item in resp_comp["items"])

    # Manufacturer search filter
    resp_mfg = client.get(
        f"/api/repository/products?search=Mfg_{prefix}_05",
        headers=auth_headers
    ).json()
    assert resp_mfg["total"] == 1
    assert resp_mfg["items"][0]["manufacturer"] == f"Mfg_{prefix}_05"


def test_product_inspections_history_pagination(auth_headers, seeded_pagination_data):
    history_pkey = seeded_pagination_data["history_pkey"]

    # Page 1 (size 5)
    h1 = client.get(f"/api/repository/products/{history_pkey}/inspections?page=1&page_size=5", headers=auth_headers).json()
    assert h1["total"] == 15
    assert h1["page"] == 1
    assert h1["page_size"] == 5
    assert h1["total_pages"] == 3
    assert len(h1["items"]) == 5
    h1_ids = [item["id"] for item in h1["items"]]

    # Page 2 (size 5)
    h2 = client.get(f"/api/repository/products/{history_pkey}/inspections?page=2&page_size=5", headers=auth_headers).json()
    assert h2["page"] == 2
    assert len(h2["items"]) == 5
    h2_ids = [item["id"] for item in h2["items"]]
    assert set(h1_ids).isdisjoint(set(h2_ids))

    # Page 3 (size 5)
    h3 = client.get(f"/api/repository/products/{history_pkey}/inspections?page=3&page_size=5", headers=auth_headers).json()
    assert h3["page"] == 3
    assert len(h3["items"]) == 5
    h3_ids = [item["id"] for item in h3["items"]]
    assert set(h1_ids).isdisjoint(set(h3_ids))
    assert set(h2_ids).isdisjoint(set(h3_ids))
