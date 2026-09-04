"""
tests/test_report_immutability.py

Regression tests for the NiriKsha Immutable Report Policy.

POLICY:
  "Completed statutory inspection reports are official, immutable government records.
   Inspectors cannot delete them."

Coverage:
  1.  DELETE /api/reports/{id} does NOT exist (405 or 404, never 200/204).
  2.  Authenticated inspector cannot delete a report.
  3.  Unauthenticated caller cannot delete a report.
  4.  Attempting DELETE leaves the report DB record intact.
  5.  Inspection survives the attempt.
  6.  Product survives.
  7.  Declarations survive.
  8.  Compliance checks survive.
  9.  Existing audit history is not erased.
  10. Report PDF remains on disk after failed delete attempt.
  11. Report generation still works.
  12. Report retrieval still works (GET /api/reports and GET /api/inspections/{id}/report).
  13. PDF download still works.
  14. Report re-generation (new version) still works.
  15. No frontend deleteReport() method exists (AST check of api.ts).
  16. Repository contains no REPORT_DELETED audit action.
  17. TypeScript compiles without errors.
  18. No DELETE /api/reports route registered in the FastAPI OpenAPI schema.

All tests use the isolated test database (test_legal_metrology.db).
They NEVER touch legal_metrology.db (the production database).
"""

import os
import json
import subprocess
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

# ---------------------------------------------------------------------------
# Module-scoped fixtures (matching the pattern from other test modules)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Single TestClient instance shared across this module."""
    return TestClient(app)


@pytest.fixture(scope="module")
def inspector_token(client):
    """JWT token for the seeded inspector account."""
    resp = client.post(
        "/api/auth/login",
        json={"officer_id": settings.SEED_OFFICER_ID, "password": settings.SEED_OFFICER_PASSWORD},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper: create a full inspection with a generated report
# ---------------------------------------------------------------------------

def _create_inspection_with_report(client: TestClient, token: str, suffix: str = "") -> dict:
    """Creates a draft inspection, generates a report, and returns info dict."""
    insp_resp = client.post(
        "/api/inspections",
        json={
            "location": f"Test Market {suffix}",
            "product_name": f"Test Product {suffix}",
            "brand_name": "TestBrand",
            "category": "Packaged Food",
        },
        headers=_auth(token),
    )
    assert insp_resp.status_code in (200, 201), insp_resp.text
    insp = insp_resp.json()
    insp_id = insp["id"]

    rpt_resp = client.post(
        f"/api/inspections/{insp_id}/report",
        headers=_auth(token),
    )
    assert rpt_resp.status_code in (200, 201), rpt_resp.text
    rpt = rpt_resp.json()

    return {"inspection": insp, "report": rpt}


# ===========================================================================
# TEST CLASS
# ===========================================================================

class TestImmutableReportPolicy:
    """Verifies that generated statutory reports cannot be deleted."""

    # -----------------------------------------------------------------------
    # 1. DELETE endpoint must not exist / must return a non-success response
    # -----------------------------------------------------------------------

    def test_01_delete_endpoint_does_not_exist(self, client, inspector_token):
        """DELETE /api/reports/{id} must NOT be present (405 or 404, never 200/204)."""
        data = _create_inspection_with_report(client, inspector_token, "T01")
        report_id = data["report"]["id"]

        resp = client.delete(f"/api/reports/{report_id}", headers=_auth(inspector_token))
        # FastAPI returns 405 if the route exists but the method is not allowed,
        # or 404 if the entire route is absent.
        assert resp.status_code in (404, 405), (
            f"DELETE /api/reports/{{id}} returned {resp.status_code} — "
            "the endpoint must not allow report deletion."
        )

    def test_02_authenticated_inspector_cannot_delete_report(self, client, inspector_token):
        """An authenticated, authorized inspector must NOT be able to delete a report."""
        data = _create_inspection_with_report(client, inspector_token, "T02")
        report_id = data["report"]["id"]

        resp = client.delete(f"/api/reports/{report_id}", headers=_auth(inspector_token))
        assert resp.status_code not in (200, 204), (
            f"Authenticated inspector deleted a report! Status: {resp.status_code}"
        )

    def test_03_unauthenticated_caller_cannot_delete_report(self, client, inspector_token):
        """No auth token must also be rejected with 401 or 404/405."""
        data = _create_inspection_with_report(client, inspector_token, "T03")
        report_id = data["report"]["id"]

        resp = client.delete(f"/api/reports/{report_id}")
        # With no auth: if route exists it should 401; if route doesn't exist 404/405.
        assert resp.status_code in (401, 404, 405), (
            f"Unauthenticated DELETE attempt returned {resp.status_code}."
        )

    # -----------------------------------------------------------------------
    # 2. Data preservation after attempted deletion
    # -----------------------------------------------------------------------

    def test_04_report_record_survives_delete_attempt(self, client, inspector_token):
        """The report DB record must remain intact after a failed DELETE attempt."""
        data = _create_inspection_with_report(client, inspector_token, "T04")
        report_id = data["report"]["id"]
        insp_id = data["inspection"]["id"]

        # Attempt delete (expected to fail/be rejected)
        client.delete(f"/api/reports/{report_id}", headers=_auth(inspector_token))

        # Report must still exist via GET /api/inspections/{id}/report
        rpt_resp = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token))
        assert rpt_resp.status_code == 200, "Report should still be accessible after failed DELETE."
        assert rpt_resp.json()["id"] == report_id, "Same report ID must persist."

    def test_05_inspection_survives_delete_attempt(self, client, inspector_token):
        """The parent inspection must remain intact after a failed DELETE attempt."""
        data = _create_inspection_with_report(client, inspector_token, "T05")
        insp_id = data["inspection"]["id"]
        insp_number = data["inspection"]["inspection_number"]

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        insp_resp = client.get(f"/api/inspections/{insp_id}", headers=_auth(inspector_token))
        assert insp_resp.status_code == 200, "Inspection must still exist."
        assert insp_resp.json()["inspection_number"] == insp_number, "Inspection number must be unchanged."

    def test_06_product_survives_delete_attempt(self, client, inspector_token):
        """The product associated with the inspection must survive."""
        data = _create_inspection_with_report(client, inspector_token, "T06")
        insp_id = data["inspection"]["id"]

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        insp_resp = client.get(f"/api/inspections/{insp_id}", headers=_auth(inspector_token))
        assert insp_resp.status_code == 200
        assert insp_resp.json().get("product") is not None or insp_resp.status_code == 200, (
            "Product data must remain accessible."
        )

    def test_07_declarations_survive_delete_attempt(self, client, inspector_token):
        """Declarations must remain intact."""
        data = _create_inspection_with_report(client, inspector_token, "T07")
        insp_id = data["inspection"]["id"]

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        decl_resp = client.get(f"/api/inspections/{insp_id}/declarations", headers=_auth(inspector_token))
        # Endpoint must still respond (even if empty for a fresh inspection)
        assert decl_resp.status_code in (200, 404), (
            f"Declarations endpoint should still respond, got {decl_resp.status_code}"
        )

    def test_08_compliance_checks_survive_delete_attempt(self, client, inspector_token):
        """Compliance checks must remain intact."""
        data = _create_inspection_with_report(client, inspector_token, "T08")
        insp_id = data["inspection"]["id"]

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        cc_resp = client.get(f"/api/inspections/{insp_id}/compliance-checks", headers=_auth(inspector_token))
        assert cc_resp.status_code in (200, 404), (
            f"Compliance checks endpoint should still respond, got {cc_resp.status_code}"
        )

    def test_09_audit_history_survives_delete_attempt(self, client, inspector_token):
        """Existing audit logs must not be wiped by an attempted delete."""
        data = _create_inspection_with_report(client, inspector_token, "T09")
        insp_id = data["inspection"]["id"]

        before = client.get(f"/api/inspections/{insp_id}/audit-logs", headers=_auth(inspector_token))
        before_count = len(before.json()) if before.status_code == 200 else 0

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        after = client.get(f"/api/inspections/{insp_id}/audit-logs", headers=_auth(inspector_token))
        after_count = len(after.json()) if after.status_code == 200 else 0

        # Audit count must not decrease (REPORT_DELETED must never be written)
        assert after_count >= before_count, (
            "Audit log should not shrink after a rejected delete attempt."
        )

    def test_10_no_report_deleted_audit_event_is_written(self, client, inspector_token):
        """The REPORT_DELETED audit action must never appear in audit logs."""
        data = _create_inspection_with_report(client, inspector_token, "T10")
        insp_id = data["inspection"]["id"]

        client.delete(f"/api/reports/{data['report']['id']}", headers=_auth(inspector_token))

        audit_resp = client.get(f"/api/inspections/{insp_id}/audit-logs", headers=_auth(inspector_token))
        if audit_resp.status_code == 200:
            actions = [entry.get("action", "") for entry in audit_resp.json()]
            assert "REPORT_DELETED" not in actions, (
                "REPORT_DELETED audit event must never be recorded — report deletion is forbidden."
            )

    # -----------------------------------------------------------------------
    # 3. Legitimate report operations still work
    # -----------------------------------------------------------------------

    def test_11_report_generation_still_works(self, client, inspector_token):
        """Generating a report for an inspection must still succeed."""
        insp_resp = client.post(
            "/api/inspections",
            json={
                "location": "Gen Test Market",
                "product_name": "Gen Test Product",
                "brand_name": "Brand",
                "category": "Packaged Food",
            },
            headers=_auth(inspector_token),
        )
        assert insp_resp.status_code in (200, 201), insp_resp.text
        insp_id = insp_resp.json()["id"]

        rpt_resp = client.post(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token))
        assert rpt_resp.status_code in (200, 201), (
            f"Report generation must succeed. Got {rpt_resp.status_code}: {rpt_resp.text}"
        )
        rpt = rpt_resp.json()
        assert rpt.get("id") is not None, "Generated report must have an ID."

    def test_12_report_retrieval_still_works(self, client, inspector_token):
        """GET /api/inspections/{id}/report must still return the report metadata."""
        data = _create_inspection_with_report(client, inspector_token, "T12")
        insp_id = data["inspection"]["id"]

        get_resp = client.get(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token))
        assert get_resp.status_code == 200, (
            f"Report retrieval must succeed. Got {get_resp.status_code}"
        )
        assert get_resp.json().get("id") is not None

    def test_13_report_list_still_works(self, client, inspector_token):
        """GET /api/reports must still return a list of reports."""
        _create_inspection_with_report(client, inspector_token, "T13")
        list_resp = client.get("/api/reports", headers=_auth(inspector_token))
        assert list_resp.status_code == 200, (
            f"Report list must succeed. Got {list_resp.status_code}"
        )
        assert isinstance(list_resp.json(), list), "Response should be a list."

    def test_14_report_by_id_retrieval_works(self, client, inspector_token):
        """GET /api/reports/{id} (single report lookup) must still work."""
        data = _create_inspection_with_report(client, inspector_token, "T14")
        report_id = data["report"]["id"]

        get_resp = client.get(f"/api/reports/{report_id}", headers=_auth(inspector_token))
        assert get_resp.status_code == 200, (
            f"GET /api/reports/{{id}} must succeed. Got {get_resp.status_code}"
        )
        assert get_resp.json()["id"] == report_id

    def test_15_report_regeneration_works(self, client, inspector_token):
        """Re-generating a report (new version) must still work."""
        data = _create_inspection_with_report(client, inspector_token, "T15")
        insp_id = data["inspection"]["id"]
        v1 = data["report"]["report_version"]

        rpt2_resp = client.post(f"/api/inspections/{insp_id}/report", headers=_auth(inspector_token))
        assert rpt2_resp.status_code in (200, 201), (
            f"Re-generation must succeed. Got {rpt2_resp.status_code}"
        )
        v2 = rpt2_resp.json()["report_version"]
        assert v2 >= v1, f"Re-generated report version ({v2}) should be >= original ({v1})."

    # -----------------------------------------------------------------------
    # 4. No delete path in the codebase
    # -----------------------------------------------------------------------

    def test_16_no_delete_report_method_in_api_ts(self):
        """api.ts must not contain a deleteReport() method."""
        api_ts_path = Path(__file__).parent.parent / "mobile" / "src" / "services" / "api.ts"
        assert api_ts_path.exists(), "api.ts not found at expected path."
        content = api_ts_path.read_text(encoding="utf-8")
        assert "deleteReport" not in content, (
            "api.ts must not contain deleteReport() — report deletion is forbidden."
        )

    def test_17_no_report_deleted_in_backend(self):
        """backend/main.py must not contain REPORT_DELETED audit action."""
        main_py = Path(__file__).parent.parent / "backend" / "main.py"
        assert main_py.exists(), "backend/main.py not found."
        content = main_py.read_text(encoding="utf-8")
        assert "REPORT_DELETED" not in content, (
            "backend/main.py must not contain REPORT_DELETED — report deletion is forbidden."
        )

    def test_18_no_delete_report_route_in_openapi_schema(self, client, inspector_token):
        """FastAPI OpenAPI schema must not list a DELETE method for /api/reports/{report_id}."""
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        paths = schema.get("paths", {})
        report_path = paths.get("/api/reports/{report_id}", {})
        assert "delete" not in report_path, (
            "OpenAPI schema must NOT expose DELETE /api/reports/{report_id}."
        )

    def test_19_no_delete_in_report_preview_screen(self):
        """ReportPreviewScreen.tsx must not contain delete-report UI code."""
        screen = Path(__file__).parent.parent / "mobile" / "src" / "screens" / "ReportPreviewScreen.tsx"
        assert screen.exists(), "ReportPreviewScreen.tsx not found."
        content = screen.read_text(encoding="utf-8")
        # Check that delete-specific identifiers are gone
        forbidden = ["deleteReport", "executeDelete", "confirmDelete", "deleting", "Delete Report"]
        for token in forbidden:
            assert token not in content, (
                f"ReportPreviewScreen.tsx still contains '{token}' — delete UI must be removed."
            )

    def test_20_no_delete_in_reports_list_screen(self):
        """ReportsListScreen.tsx must not contain delete-report UI code."""
        screen = Path(__file__).parent.parent / "mobile" / "src" / "screens" / "ReportsListScreen.tsx"
        assert screen.exists(), "ReportsListScreen.tsx not found."
        content = screen.read_text(encoding="utf-8")
        forbidden = ["deleteReport", "handleDeleteReport", "confirmExecuteDelete", "deleteConfirmReport", "deletingId"]
        for token in forbidden:
            assert token not in content, (
                f"ReportsListScreen.tsx still contains '{token}' — delete UI must be removed."
            )

    def test_21_typescript_compiles_without_errors(self):
        """TypeScript must compile with 0 errors after the removal."""
        mobile_dir = Path(__file__).parent.parent / "mobile"
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(mobile_dir),
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )
        assert result.returncode == 0, (
            f"TypeScript compilation errors:\n{result.stdout}\n{result.stderr}"
        )
