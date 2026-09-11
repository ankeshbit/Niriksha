"""
backend/vlm_service.py

Qwen2.5-VL Vision-Language Model Service for Contextual Package Understanding.

Architecture:
Package Image -> PaddleOCR -> PP-Structure -> Qwen2.5-VL (Optional) -> Extraction -> Rule Engine -> Inspector

CRITICAL BOUNDARIES:
1. Qwen2.5-VL assists strictly with contextual region interpretation & candidate identification.
2. Qwen2.5-VL MUST NOT make the final Legal Metrology compliance decision.
3. Output is structured as candidate data with visual justifications and confidence.
4. Candidates are strictly validated against OCR evidence before entering the pipeline.
"""

import os
import re
import json
import time
import base64
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pathlib import Path

from backend.config import settings


class VLMCandidate(BaseModel):
    """Structured candidate declaration identified by the Vision-Language Model."""
    field: str
    candidate_value: str
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    source_image_id: Optional[str] = None
    bbox: Optional[List[int]] = None  # [x1, y1, x2, y2]
    reason: Optional[str] = None      # Visual context / region interpretation rationale


class VLMInterpretationResult(BaseModel):
    """Aggregate result from Qwen2.5-VL contextual package interpretation."""
    status: str  # 'SUCCESS', 'DISABLED', 'TIMEOUT', 'MALFORMED', 'UNAVAILABLE', 'ERROR'
    candidates: List[VLMCandidate] = []
    region_interpretations: Dict[str, str] = {}
    raw_response: Optional[str] = None
    latency_ms: float = 0.0
    model_name: str = ""
    error: Optional[str] = None


class BaseVLMProvider:
    """Abstract base provider for vision-language models."""
    def interpret(
        self,
        image_path: str,
        ocr_boxes: List[Any],
        layout_regions: List[Any],
        image_id: Optional[str] = None,
        timeout: float = 15.0
    ) -> VLMInterpretationResult:
        raise NotImplementedError


class MockQwenVLProvider(BaseVLMProvider):
    """
    Deterministic mock provider simulating Qwen2.5-VL outputs.
    Enables instant, offline, deterministic testing and CI/CD validation.
    """
    def __init__(self):
        self._custom_responses: Dict[str, VLMInterpretationResult] = {}
        self._simulate_timeout: bool = False
        self._simulate_malformed: bool = False
        self._simulate_error: Optional[str] = None

    def set_simulation_flags(
        self,
        simulate_timeout: bool = False,
        simulate_malformed: bool = False,
        simulate_error: Optional[str] = None
    ):
        self._simulate_timeout = simulate_timeout
        self._simulate_malformed = simulate_malformed
        self._simulate_error = simulate_error

    def set_custom_response(self, image_key: str, result: VLMInterpretationResult):
        self._custom_responses[image_key] = result

    def clear_overrides(self):
        self._custom_responses.clear()
        self._simulate_timeout = False
        self._simulate_malformed = False
        self._simulate_error = None

    def interpret(
        self,
        image_path: str,
        ocr_boxes: List[Any],
        layout_regions: List[Any],
        image_id: Optional[str] = None,
        timeout: float = 15.0
    ) -> VLMInterpretationResult:
        start_t = time.time()

        if self._simulate_timeout:
            return VLMInterpretationResult(
                status="TIMEOUT",
                latency_ms=round((time.time() - start_t) * 1000, 2),
                model_name=settings.VLM_MODEL,
                error="VLM request timed out after 15.0s"
            )

        if self._simulate_malformed:
            return VLMInterpretationResult(
                status="MALFORMED",
                raw_response="This package has MRP 50 and biscuits, not in json format",
                latency_ms=round((time.time() - start_t) * 1000, 2),
                model_name=settings.VLM_MODEL,
                error="Failed to parse structured JSON from VLM response"
            )

        if self._simulate_error:
            return VLMInterpretationResult(
                status="ERROR",
                latency_ms=round((time.time() - start_t) * 1000, 2),
                model_name=settings.VLM_MODEL,
                error=self._simulate_error
            )

        # Check custom canned response by image_id or filename
        img_name = Path(image_path).name if image_path else ""
        if image_id and image_id in self._custom_responses:
            return self._custom_responses[image_id]
        if img_name and img_name in self._custom_responses:
            return self._custom_responses[img_name]

        # Default intelligent mock based on actual OCR boxes & layout regions
        candidates: List[VLMCandidate] = []
        region_interps: Dict[str, str] = {}

        for reg in layout_regions:
            r_type = getattr(reg, "region_type", "")
            r_bbox = getattr(reg, "bbox", None)
            r_summary = getattr(reg, "summary_text", "")

            if r_type == "TABLE_REGION":
                region_interps[str(r_bbox)] = "This region appears to contain a nutrition facts table and ingredients list."
            elif r_type == "PRICE_DATE_REGION":
                region_interps[str(r_bbox)] = "This region appears to represent statutory price and packing date declarations."
            elif r_type == "QUANTITY_REGION":
                region_interps[str(r_bbox)] = "This region represents the declared net weight declaration."
            elif r_type == "MANUFACTURER_ADDRESS_REGION":
                region_interps[str(r_bbox)] = "This region represents the manufacturer and packing unit address."
            elif r_type == "CONSUMER_CARE_REGION":
                region_interps[str(r_bbox)] = "This region represents consumer care contact helpline details."

        return VLMInterpretationResult(
            status="SUCCESS",
            candidates=candidates,
            region_interpretations=region_interps,
            raw_response=json.dumps({"candidates": [c.model_dump() for c in candidates]}),
            latency_ms=round((time.time() - start_t) * 1000, 2),
            model_name=settings.VLM_MODEL
        )


class OpenAICompatibleVLMProvider(BaseVLMProvider):
    """
    Production HTTP provider for Qwen2.5-VL served via vLLM, SGLang, Ollama,
    or Hugging Face Inference Endpoints using the standard OpenAI Vision API format.
    """
    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None, model: Optional[str] = None):
        self.endpoint = (endpoint or settings.VLM_ENDPOINT or "http://localhost:8000/v1").rstrip("/")
        self.api_key = api_key or settings.VLM_API_KEY or "EMPTY"
        self.model = model or settings.VLM_MODEL

    def _encode_image(self, image_path: str) -> Optional[str]:
        try:
            if not os.path.isfile(image_path):
                return None
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            suffix = Path(image_path).suffix.lower().replace(".", "")
            mime = "jpeg" if suffix in ["jpg", "jpeg"] else "png"
            return f"data:image/{mime};base64,{b64}"
        except Exception:
            return None

    def interpret(
        self,
        image_path: str,
        ocr_boxes: List[Any],
        layout_regions: List[Any],
        image_id: Optional[str] = None,
        timeout: float = 15.0
    ) -> VLMInterpretationResult:
        import urllib.request
        import urllib.error

        start_t = time.time()
        img_data_url = self._encode_image(image_path)
        if not img_data_url:
            return VLMInterpretationResult(
                status="ERROR",
                latency_ms=0.0,
                model_name=self.model,
                error=f"Image could not be read or encoded: {image_path}"
            )

        # Contextual summary of OCR and Layout for the prompt
        ocr_summary = []
        for b in ocr_boxes[:40]:  # limit to top 40 boxes to manage prompt length
            t = getattr(b, "text", "") if hasattr(b, "text") else b.get("text", "")
            box = getattr(b, "bbox", []) if hasattr(b, "bbox") else b.get("bbox", [])
            ocr_summary.append(f"- '{t}' at bbox {box}")
        ocr_text_context = "\n".join(ocr_summary)

        system_instruction = (
            "You are an expert packaging visual analyst assistant for Legal Metrology inspections. "
            "Your role is STRICTLY to observe and interpret what specific regions of the package represent. "
            "You MUST NOT make legal compliance decisions (do not judge whether the package passes or fails rules). "
            "You MUST NOT invent or hallucinate any product name, address, quantity, date, or price not clearly visible. "
            "Return a strictly valid JSON object with the following schema:\n"
            "{\n"
            '  "region_interpretations": {"<region_description>": "<what_it_represents>"},\n'
            '  "candidates": [\n'
            '    {"field": "<mrp|net_quantity|manufacturer_details|date_of_manufacture_packing|consumer_care_details|country_of_origin|commodity_name|unit_sale_price>", '
            '"candidate_value": "<exact_text>", "confidence": 0.9, "bbox": [x1, y1, x2, y2], "reason": "<visual_justification>"}\n'
            '  ]\n'
            "}"
        )

        user_prompt = (
            "Analyze this package image. The optical character recognition found these text elements:\n"
            f"{ocr_text_context}\n\n"
            "Identify the functional statutory regions (MRP, Net Weight, Dates, Manufacturer, Consumer Care, Commodity Name) "
            "and return strictly the structured JSON object."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": img_data_url}}
                    ]
                }
            ],
            "temperature": 0.1,
            "max_tokens": 1024
        }

        url = f"{self.endpoint}/chat/completions"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                elapsed_ms = round((time.time() - start_t) * 1000, 2)

                # Parse JSON block from response
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if not json_match:
                    return VLMInterpretationResult(
                        status="MALFORMED",
                        raw_response=content,
                        latency_ms=elapsed_ms,
                        model_name=self.model,
                        error="No JSON structure found in VLM response"
                    )

                parsed = json.loads(json_match.group(0))
                candidates_list = []
                for c in parsed.get("candidates", []):
                    candidates_list.append(VLMCandidate(
                        field=c.get("field", ""),
                        candidate_value=str(c.get("candidate_value", "")).strip(),
                        confidence=float(c.get("confidence", 0.85)),
                        source_image_id=image_id,
                        bbox=c.get("bbox"),
                        reason=c.get("reason")
                    ))

                return VLMInterpretationResult(
                    status="SUCCESS",
                    candidates=candidates_list,
                    region_interpretations=parsed.get("region_interpretations", {}),
                    raw_response=content,
                    latency_ms=elapsed_ms,
                    model_name=self.model
                )

        except urllib.error.URLError as e:
            elapsed_ms = round((time.time() - start_t) * 1000, 2)
            is_timeout = "timed out" in str(e).lower()
            return VLMInterpretationResult(
                status="TIMEOUT" if is_timeout else "UNAVAILABLE",
                latency_ms=elapsed_ms,
                model_name=self.model,
                error=f"VLM server connection failed: {e}"
            )
        except json.JSONDecodeError as e:
            elapsed_ms = round((time.time() - start_t) * 1000, 2)
            return VLMInterpretationResult(
                status="MALFORMED",
                latency_ms=elapsed_ms,
                model_name=self.model,
                error=f"JSON decoding error: {e}"
            )
        except Exception as e:
            elapsed_ms = round((time.time() - start_t) * 1000, 2)
            return VLMInterpretationResult(
                status="ERROR",
                latency_ms=elapsed_ms,
                model_name=self.model,
                error=f"Unexpected VLM error: {e}"
            )


class QwenVLService:
    """
    Qwen2.5-VL Vision-Language Reasoning Service Facade.
    Gracefully coordinates model interpretation with strict fallback.
    """
    def __init__(self):
        self.mock_provider = MockQwenVLProvider()
        self.http_provider = OpenAICompatibleVLMProvider()

    def is_enabled(self) -> bool:
        return getattr(settings, "VLM_ENABLED", False)

    def get_provider(self) -> BaseVLMProvider:
        provider_type = getattr(settings, "VLM_PROVIDER", "mock").lower()
        if provider_type in ("openai_compatible", "vllm", "remote"):
            return self.http_provider
        return self.mock_provider

    def interpret_package(
        self,
        image_path: str,
        ocr_boxes: List[Any],
        layout_regions: List[Any],
        image_id: Optional[str] = None
    ) -> VLMInterpretationResult:
        """
        Interprets package regions using Qwen2.5-VL if enabled.
        Guarantees non-blocking execution and graceful degradation when disabled.
        """
        if not self.is_enabled():
            return VLMInterpretationResult(
                status="DISABLED",
                model_name=settings.VLM_MODEL,
                error="VLM is disabled via settings (VLM_ENABLED=False)"
            )

        timeout = getattr(settings, "VLM_TIMEOUT_SECONDS", 15.0)
        provider = self.get_provider()

        try:
            return provider.interpret(
                image_path=image_path,
                ocr_boxes=ocr_boxes,
                layout_regions=layout_regions,
                image_id=image_id,
                timeout=timeout
            )
        except Exception as e:
            return VLMInterpretationResult(
                status="ERROR",
                model_name=settings.VLM_MODEL,
                error=f"VLM execution failed: {str(e)}"
            )


qwen_vl_service = QwenVLService()
