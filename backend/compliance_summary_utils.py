"""
backend/compliance_summary_utils.py

Canonical Statutory Compliance Finding & Summary Aggregation.
Single source of truth for findings counts across:
- FindingsScreen (mobile)
- Compliance Summary API (/api/inspections/{id}/compliance-summary)
- PDF Report Generator (ReportLab)
- DOCX Report Generator
Guarantees strict mutual exclusivity and deterministic categorization.
"""

from typing import List, Dict, Any, Set


def compute_canonical_compliance_metrics(checks: List[Any]) -> Dict[str, int]:
    """
    Computes mutually exclusive compliance finding buckets from a list of compliance check records.

    Buckets:
    1. compliant_checks: PASS or NOT_APPLICABLE (not overridden by CONFIRMED/NEEDS_MORE_EVIDENCE),
       plus checks explicitly adjudicated DISMISSED or CORRECTED by the inspector.
    2. potential_non_compliance: POTENTIAL_NON_COMPLIANCE result not resolved favourably,
       plus any check explicitly CONFIRMED as a violation.
    3. needs_manual_verification: INSUFFICIENT_EVIDENCE or NEEDS_MANUAL_VERIFICATION,
       or adjudicated as NEEDS_MORE_EVIDENCE (excluding confirmed/dismissed/non-compliance).
    4. warnings: Data quality checks not falling into compliant, non-compliance, or manual verification.
    5. total_findings: Total number of evaluated rules.
    """
    if not checks:
        return {
            "compliant_checks": 0,
            "potential_non_compliance": 0,
            "needs_manual_verification": 0,
            "warnings": 0,
            "total_findings": 0,
        }

    # ── Bucket 2: Potential Non-Compliance ─────────────────────────────────────
    nc_ids: Set[str] = set()
    for c in checks:
        c_id = getattr(c, "id", None) or str(id(c))
        r_state = getattr(c, "result_state", "")
        adj_status = getattr(c, "adjudication_status", "PENDING") or "PENDING"

        is_nc_result = (
            r_state == "POTENTIAL_NON_COMPLIANCE"
            and adj_status not in ("DISMISSED", "NOT_APPLICABLE", "CORRECTED")
        )
        is_confirmed_extra = (
            adj_status == "CONFIRMED"
            and r_state != "POTENTIAL_NON_COMPLIANCE"
        )
        if is_nc_result or is_confirmed_extra:
            nc_ids.add(c_id)

    potential_non_compliance = len(nc_ids)

    # ── Bucket 3: Needs Manual Verification ────────────────────────────────────
    manual_ids: Set[str] = set()
    for c in checks:
        c_id = getattr(c, "id", None) or str(id(c))
        if c_id in nc_ids:
            continue
        r_state = getattr(c, "result_state", "")
        adj_status = getattr(c, "adjudication_status", "PENDING") or "PENDING"

        is_manual_result = (
            r_state in ("NEEDS_MANUAL_VERIFICATION", "INSUFFICIENT_EVIDENCE")
            and adj_status not in ("DISMISSED", "NOT_APPLICABLE", "CORRECTED", "CONFIRMED")
        )
        is_needs_more = (adj_status == "NEEDS_MORE_EVIDENCE")

        if is_manual_result or is_needs_more:
            manual_ids.add(c_id)

    needs_manual_verification = len(manual_ids)

    # ── Bucket 1: Compliant Checks ─────────────────────────────────────────────
    compliant_count = 0
    for c in checks:
        r_state = getattr(c, "result_state", "")
        adj_status = getattr(c, "adjudication_status", "PENDING") or "PENDING"

        is_pass_state = (
            r_state in ("PASS", "NOT_APPLICABLE")
            and adj_status not in ("CONFIRMED", "NEEDS_MORE_EVIDENCE")
        )
        is_resolved = adj_status in ("DISMISSED", "CORRECTED")

        if is_pass_state or is_resolved:
            compliant_count += 1

    compliant_checks = compliant_count

    # ── Bucket 4: Data Quality Warnings ────────────────────────────────────────
    warnings_count = 0
    for c in checks:
        c_id = getattr(c, "id", None) or str(id(c))
        if c_id in nc_ids or c_id in manual_ids:
            continue

        r_state = getattr(c, "result_state", "")
        adj_status = getattr(c, "adjudication_status", "PENDING") or "PENDING"
        if r_state in ("PASS", "NOT_APPLICABLE") or adj_status in ("DISMISSED", "CORRECTED"):
            continue

        # Check category
        rule_version = getattr(c, "rule_version", None)
        category = getattr(rule_version, "category", "") if rule_version else getattr(c, "category", "")
        if category in ("CATEGORY_B_DATA_QUALITY", "DATA_QUALITY"):
            warnings_count += 1

    warnings = warnings_count
    total_findings = len(checks)

    return {
        "compliant_checks": compliant_checks,
        "potential_non_compliance": potential_non_compliance,
        "needs_manual_verification": needs_manual_verification,
        "warnings": warnings,
        "total_findings": total_findings,
    }
