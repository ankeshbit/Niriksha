from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum

class RuleResultState(str, Enum):
    PASS = "PASS"
    POTENTIAL_NON_COMPLIANCE = "POTENTIAL_NON_COMPLIANCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NEEDS_MANUAL_VERIFICATION = "NEEDS_MANUAL_VERIFICATION"
    WARNING = "WARNING"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class SeverityLevel(str, Enum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"

class EvidencePayload(BaseModel):
    image_id: Optional[str] = None
    bounding_box: Optional[List[int]] = None  # [x1, y1, x2, y2]
    highlight_text: str
    reason: str

class StatutoryRuleDefinition(BaseModel):
    rule_code: str
    rule_version: int = 1
    title: str
    category: str  # 'CATEGORY_A_LEGAL', 'CATEGORY_B_DATA_QUALITY'
    statutory_reference: str
    description: str
    severity: SeverityLevel = SeverityLevel.MAJOR
    required_fields: List[str]
    is_active: bool = True

class RuleEvaluationResult(BaseModel):
    rule_code: str
    rule_version: int
    title: str
    statutory_reference: str
    severity: SeverityLevel
    result_state: RuleResultState
    effective_value_used: Optional[str] = None
    original_ocr_value: Optional[str] = None
    is_verified_by_officer: bool = False
    explanation: str
    evidence_items: List[EvidencePayload] = []
