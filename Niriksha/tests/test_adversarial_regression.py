"""
tests/test_adversarial_regression.py

Regression tests for the three adversarial QA fixes:

  R-1  Concurrent idempotency — same client_draft_id under concurrent requests
       must NOT produce HTTP 500, must produce exactly ONE inspection.
  S-1  GET /api/rules and GET /api/rules/{code} must return 401 without JWT.
  S-2  CreateInspectionRequest.category must reject values outside the allowed
       Literal ("Packaged Food", "Household/Personal Care").

All tests run against test_legal_metrology.db (enforced by conftest.py).
"""

import uuid
import threading
from typing import List, Dict, Any

import pytest
from fastapi.testclient import TestClient
from backend.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Single TestClient instance shared across the module."""
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client):
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": "DOCA-INSP-842", "password": "admin123"}
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _post_inspection(client: TestClient, payload: dict, headers: dict) -> Dict[str, Any]:
    resp = client.post("/api/inspections", json=payload, headers=headers)
    return {"status_code": resp.status_code, "body": resp.json()}


# ---------------------------------------------------------------------------
# R-1: Concurrent Idempotency
# ---------------------------------------------------------------------------

class TestConcurrentIdempotency:
    """All concurrent requests with the same client_draft_id must:
    - Return HTTP 200 or 201 (never 500)
    - Return exactly ONE unique inspection ID
    - Return exactly ONE unique inspection_number
    """

    def _run_concurrent(self, client, auth_headers, n_threads, draft_id):
        payload = {
            "product_name": "Concurrent Idempotency Test Product",
            "category": "Packaged Food",
            "location": "Test Warehouse — Concurrent",
            "client_draft_id": draft_id,
        }
        results: List[Dict[str, Any]] = []
        lock = threading.Lock()

        def worker():
            result = _post_inspection(client, payload, auth_headers)
            with lock:
                results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def test_5_concurrent_same_draft_id_no_500(self, client, auth_headers):
        """5 concurrent requests with identical draft_id — none must return 500."""
        draft_id = f"regression-5x-{uuid.uuid4()}"
        results = self._run_concurrent(client, auth_headers, 5, draft_id)

        statuses = [r["status_code"] for r in results]
        assert len(results) == 5, "Expected 5 results, some threads may have crashed"
        assert 500 not in statuses, (
            f"One or more threads returned 500. Statuses: {statuses}"
        )
        for r in results:
            assert r["status_code"] in (200, 201), (
                f"Unexpected status {r['status_code']}: {r['body']}"
            )

    def test_5_concurrent_same_draft_id_one_inspection(self, client, auth_headers):
        """5 concurrent requests with identical draft_id — exactly 1 inspection created."""
        draft_id = f"regression-5x-single-{uuid.uuid4()}"
        results = self._run_concurrent(client, auth_headers, 5, draft_id)

        ids = set(r["body"].get("id") for r in results if r["status_code"] in (200, 201))
        numbers = set(
            r["body"].get("inspection_number")
            for r in results
            if r["status_code"] in (200, 201)
        )
        assert len(ids) == 1, f"Expected 1 unique inspection ID, got {len(ids)}: {ids}"
        assert len(numbers) == 1, (
            f"Expected 1 unique inspection_number, got {len(numbers)}: {numbers}"
        )

    def test_10_concurrent_same_draft_id_no_500(self, client, auth_headers):
        """10 concurrent requests with identical draft_id — none must return 500."""
        draft_id = f"regression-10x-{uuid.uuid4()}"
        results = self._run_concurrent(client, auth_headers, 10, draft_id)

        statuses = [r["status_code"] for r in results]
        assert len(results) == 10, "Expected 10 results"
        assert 500 not in statuses, f"500s detected! Statuses: {statuses}"
        for r in results:
            assert r["status_code"] in (200, 201), (
                f"Unexpected status {r['status_code']}"
            )

    def test_10_concurrent_same_draft_id_one_inspection(self, client, auth_headers):
        """10 concurrent requests with identical draft_id — exactly 1 inspection created."""
        draft_id = f"regression-10x-single-{uuid.uuid4()}"
        results = self._run_concurrent(client, auth_headers, 10, draft_id)

        ids = set(r["body"].get("id") for r in results if r["status_code"] in (200, 201))
        numbers = set(
            r["body"].get("inspection_number")
            for r in results
            if r["status_code"] in (200, 201)
        )
        assert len(ids) == 1, f"Expected 1 unique ID, got {len(ids)}: {ids}"
        assert len(numbers) == 1, (
            f"Expected 1 unique number, got {len(numbers)}: {numbers}"
        )

    def test_3_concurrent_different_draft_ids_create_3_distinct(self, client, auth_headers):
        """3 concurrent requests each with a DIFFERENT draft_id — 3 distinct inspections."""
        draft_ids = [f"regression-diff-{i}-{uuid.uuid4()}" for i in range(3)]
        payloads = [
            {
                "product_name": f"Distinct Draft Product {i}",
                "category": "Packaged Food",
                "location": f"Site {i}",
                "client_draft_id": did,
            }
            for i, did in enumerate(draft_ids)
        ]

        results: List[Dict[str, Any]] = []
        lock = threading.Lock()

        def worker(p):
            r = _post_inspection(client, p, auth_headers)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3
        statuses = [r["status_code"] for r in results]
        assert 500 not in statuses, f"500 detected: {statuses}"

        ids = set(r["body"].get("id") for r in results if r["status_code"] in (200, 201))
        numbers = set(
            r["body"].get("inspection_number")
            for r in results
            if r["status_code"] in (200, 201)
        )
        assert len(ids) == 3, f"Expected 3 distinct IDs, got {len(ids)}: {ids}"
        assert len(numbers) == 3, f"Expected 3 distinct numbers, got {len(numbers)}: {numbers}"

    def test_sequential_idempotency_still_works(self, client, auth_headers):
        """Sequential repeated sync with same draft_id must still be idempotent."""
        draft_id = f"regression-seq-{uuid.uuid4()}"
        payload = {
            "product_name": "Sequential Idempotency Guard",
            "category": "Household/Personal Care",
            "location": "Sequential Test Site",
            "client_draft_id": draft_id,
        }
        first = client.post("/api/inspections", json=payload, headers=auth_headers)
        assert first.status_code == 201
        first_id = first.json()["id"]
        first_num = first.json()["inspection_number"]

        for i in range(5):
            repeat = client.post("/api/inspections", json=payload, headers=auth_headers)
            assert repeat.status_code in (200, 201), (
                f"Retry #{i+1} returned {repeat.status_code}: {repeat.text}"
            )
            assert repeat.json()["id"] == first_id, (
                f"Retry #{i+1} returned different ID: {repeat.json()['id']}"
            )
            assert repeat.json()["inspection_number"] == first_num, (
                f"Retry #{i+1} returned different number: {repeat.json()['inspection_number']}"
            )


# ---------------------------------------------------------------------------
# S-1: Rules Endpoint Authentication
# ---------------------------------------------------------------------------

class TestRulesAuth:
    """Both /api/rules endpoints must require a valid JWT."""

    def test_list_rules_no_auth_returns_401(self, client):
        resp = client.get("/api/rules")
        assert resp.status_code == 401, (
            f"Expected 401 (no auth), got {resp.status_code}: {resp.text}"
        )

    def test_list_rules_with_auth_returns_200(self, client, auth_headers):
        resp = client.get("/api/rules", headers=auth_headers)
        assert resp.status_code == 200
        rules = resp.json()
        assert len(rules) >= 7
        codes = [r["rule_code"] for r in rules]
        assert "PCR_RULE_06_1_A" in codes

    def test_get_rule_by_code_no_auth_returns_401(self, client):
        resp = client.get("/api/rules/PCR_RULE_06_1_A")
        assert resp.status_code == 401, (
            f"Expected 401 (no auth), got {resp.status_code}: {resp.text}"
        )

    def test_get_rule_by_code_with_auth_returns_200(self, client, auth_headers):
        resp = client.get("/api/rules/PCR_RULE_06_1_A", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["rule_code"] == "PCR_RULE_06_1_A"

    def test_get_rule_by_code_invalid_code_returns_404(self, client, auth_headers):
        resp = client.get("/api/rules/NONEXISTENT_RULE", headers=auth_headers)
        assert resp.status_code == 404

    def test_fake_token_on_rules_returns_401(self, client):
        resp = client.get("/api/rules", headers={"Authorization": "Bearer fake.jwt.here"})
        assert resp.status_code == 401

    def test_malformed_auth_header_on_rules_returns_401(self, client):
        resp = client.get("/api/rules", headers={"Authorization": "NotBearer abc123"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# S-2: Category Validation
# ---------------------------------------------------------------------------

class TestCategoryValidation:
    """CreateInspectionRequest.category must reject arbitrary strings."""

    def test_valid_packaged_food_accepted(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={
                "product_name": "Wheat Flour 1kg",
                "category": "Packaged Food",
                "location": "Delhi Market",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    def test_valid_household_accepted(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={
                "product_name": "Shampoo 200ml",
                "category": "Household/Personal Care",
                "location": "Mumbai Store",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    def test_invalid_category_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={
                "product_name": "Test Product",
                "category": "INVALID_CATEGORY",
                "location": "Test Site",
            },
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422), (
            f"Expected 400/422 for invalid category, got {resp.status_code}: {resp.text}"
        )

    def test_arbitrary_string_category_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={"product_name": "Test", "category": "Electronics", "location": "x"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)

    def test_empty_category_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={"product_name": "Test", "category": "", "location": "x"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)

    def test_sql_injection_in_category_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inspections",
            json={
                "product_name": "Test",
                "category": "'; DROP TABLE inspections; --",
                "location": "x",
            },
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)

    def test_case_sensitivity_rejected(self, client, auth_headers):
        """'packaged food' (lowercase) must be rejected — values are case-sensitive."""
        resp = client.post(
            "/api/inspections",
            json={"product_name": "Test", "category": "packaged food", "location": "x"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)
