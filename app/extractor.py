"""Extractor Agent implementation using Gemini structured outputs and execution telemetry."""

import json
import os
import re
import time
from typing import Any, List, Optional, Tuple
import uuid

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from app.grounding import ground_and_calibrate_document
from app.parser import ParsedDocument, parse_document
from app.schemas import ExtractedDoc, ExtractedField, RunTrace

DEFAULT_MODEL = "gemini-3.8-flash"
PROMPT_COST_PER_MILLION = 0.15
COMPLETION_COST_PER_MILLION = 0.60


class RawFieldExtraction(BaseModel):
    """Candidate field extraction from model before grounding verification."""
    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_quote: Optional[str] = None


class DocumentExtractionPayload(BaseModel):
    """Structured extraction payload enforced on Gemini response."""
    model_config = ConfigDict(extra="forbid")

    consignee: RawFieldExtraction
    hs_code: RawFieldExtraction
    pol: RawFieldExtraction
    pod: RawFieldExtraction
    incoterm: RawFieldExtraction
    description: RawFieldExtraction
    gross_weight: RawFieldExtraction
    invoice_number: RawFieldExtraction
    transcription: Optional[str] = None


SYSTEM_PROMPT = """You are Nova's expert trade document extraction agent.
Extract all 8 required trade fields from the provided document:
1. consignee: Name and optional address of the buyer/consignee.
2. hs_code: Harmonized System code (e.g. 8479.50).
3. pol: Port of Loading (e.g. CNSHA, Shanghai).
4. pod: Port of Discharge (e.g. USLAX, Los Angeles).
5. incoterm: Standard 3-letter Incoterm (e.g. FOB, CIF, EXW, DAP).
6. description: Description of merchandise or goods.
7. gross_weight: Total gross weight with unit (e.g. 12500 KG).
8. invoice_number: Commercial invoice or reference number.

CRITICAL GROUNDING RULES:
- For EVERY field, provide the exact verbatim 'source_quote' from the document where the value appears.
- Do NOT fabricate, rephrase, or infer quotes. If a field is not present in the document, set value=null, confidence=0.0, and source_quote=null.
- Assign an accurate confidence score between 0.0 and 1.0 for each field.
- If processing images (vision mode), transcribe the full document text into the 'transcription' field so verbatim quotes can be verified.
"""


def _sanitize_error(error_msg: str) -> str:
    """Sanitize error messages to avoid leaking API keys or sensitive paths."""
    sanitized = re.sub(r'(api[-_]?key|key=)[A-Za-z0-9_-]+', r'\1[REDACTED]', error_msg, flags=re.IGNORECASE)
    return sanitized


class ExtractorAgent:
    """Agent responsible for multi-modal document extraction with telemetry."""

    def __init__(
        self,
        client: Optional[Any] = None,
        model_name: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.model_name = model_name or os.environ.get("EXTRACTOR_MODEL", DEFAULT_MODEL)
        self.mock_mode = mock_mode
        self.client = client

        if not self.mock_mode and self.client is None:
            api_key = os.environ.get("GEMINI_API_KEY")
            if api_key:
                self.client = genai.Client(api_key=api_key)

    def extract_document(
        self,
        file_path: str,
        mime_type: Optional[str] = None,
        document_id: Optional[str] = None,
    ) -> Tuple[ExtractedDoc, RunTrace]:
        """Extract trade document fields directly from a file path."""
        with open(file_path, "rb") as f:
            file_bytes = f.read()
        filename = os.path.basename(file_path)
        return self.extract(file_bytes=file_bytes, filename=filename, document_id=document_id, mime_type=mime_type)

    def extract(
        self,
        file_bytes: bytes,
        filename: str,
        document_id: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Tuple[ExtractedDoc, RunTrace]:
        """Extract trade document fields and capture execution telemetry."""
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        doc_id = document_id or f"doc_{uuid.uuid4().hex[:8]}"
        start_time = time.perf_counter()

        parsed_doc: ParsedDocument = parse_document(file_bytes, filename, mime_type=mime_type)

        try:
            if self.mock_mode:
                # Mock response handling for offline testing
                payload = self._mock_extraction(parsed_doc)
                prompt_tokens = 450
                completion_tokens = 180
                thinking_tokens = 60
            else:
                if self.client is None:
                    raise RuntimeError("Gemini client is not initialized and mock_mode is False.")

                # Construct prompt contents
                config = types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=DocumentExtractionPayload,
                )

                if parsed_doc.extraction_method == "text_layer":
                    contents = [
                        f"Extract trade fields from this document text:\n\n{parsed_doc.raw_text}"
                    ]
                else:
                    contents = [
                        "Extract trade fields from the attached document pages. "
                        "Remember to provide full transcription in the transcription field."
                    ]
                    for img_bytes in parsed_doc.page_images:
                        contents.append(
                            types.Part.from_bytes(data=img_bytes, mime_type="image/png")
                        )

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )

                # Parse JSON output into DocumentExtractionPayload
                raw_response_text = response.text or "{}"
                data_dict = json.loads(raw_response_text)
                payload = DocumentExtractionPayload.model_validate(data_dict)

                # Extract token usage metadata
                usage = getattr(response, "usage_metadata", None)
                prompt_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
                completion_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
                thinking_tokens = getattr(usage, "thoughts_token_count", 0) if usage else 0

            # Calculate cost
            cost_usd = (
                (prompt_tokens * PROMPT_COST_PER_MILLION)
                + ((completion_tokens + thinking_tokens) * COMPLETION_COST_PER_MILLION)
            ) / 1_000_000.0

            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Record telemetry trace
            trace = RunTrace(
                run_id=run_id,
                document_id=doc_id,
                node_name="extractor",
                model_name=self.model_name,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                thinking_tokens=thinking_tokens,
                cost_usd=round(cost_usd, 6),
                status="SUCCESS",
            )

            # Enforce deterministic code-level grounding and confidence calibration
            raw_text = parsed_doc.raw_text or payload.transcription
            extracted_doc = ground_and_calibrate_document(
                payload=payload,
                raw_text=raw_text,
                extraction_method=parsed_doc.extraction_method,
            )

            return extracted_doc, trace

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            sanitized_err = _sanitize_error(str(e))
            failed_trace = RunTrace(
                run_id=run_id,
                document_id=doc_id,
                node_name="extractor",
                model_name=self.model_name,
                latency_ms=round(latency_ms, 2),
                prompt_tokens=0,
                completion_tokens=0,
                thinking_tokens=0,
                cost_usd=0.0,
                status="FAILED",
                error_message=sanitized_err,
            )
            # Re-raise with failed trace attached or return for caller inspection
            e.trace = failed_trace
            raise

    def _mock_extraction(self, parsed_doc: ParsedDocument) -> DocumentExtractionPayload:
        """Provide deterministic mock extraction payload for testing."""
        return DocumentExtractionPayload(
            consignee=RawFieldExtraction(
                value="Meridian Robotics Inc.",
                confidence=0.95,
                source_quote="Meridian Robotics Inc.",
            ),
            hs_code=RawFieldExtraction(
                value="8479.50",
                confidence=0.92,
                source_quote="8479.50.00",
            ),
            pol=RawFieldExtraction(
                value="CNSHA",
                confidence=0.90,
                source_quote="CNSHA Shanghai Port",
            ),
            pod=RawFieldExtraction(
                value="USLAX",
                confidence=0.90,
                source_quote="USLAX Los Angeles Port",
            ),
            incoterm=RawFieldExtraction(
                value="FOB",
                confidence=0.98,
                source_quote="Incoterm: FOB",
            ),
            description=RawFieldExtraction(
                value="Robotic Arms",
                confidence=0.94,
                source_quote="Industrial Robotic Arms",
            ),
            gross_weight=RawFieldExtraction(
                value="12500 KG",
                confidence=0.93,
                source_quote="12,500 KG",
            ),
            invoice_number=RawFieldExtraction(
                value="INV-2026-001",
                confidence=0.99,
                source_quote="INV-2026-001",
            ),
            transcription=parsed_doc.raw_text,
        )
