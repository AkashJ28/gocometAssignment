"""Policy Router and Decision Agent for GoComet Nova DAW trade documents."""

import json
import os
import re
import time
from typing import Any, List, Optional, Tuple
import uuid

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

from app.schemas import (
    DecisionResult,
    DecisionType,
    Discrepancy,
    RunTrace,
    ValidationResult,
    ValidationStatus,
)

DEFAULT_LITE_MODEL = "gemini-2.5-flash-lite"
LITE_PROMPT_COST_PER_MILLION = 0.075
LITE_COMPLETION_COST_PER_MILLION = 0.30


class RouterLLMResponse(BaseModel):
    """Schema for structured reasoning and optional amendment email from LLM."""
    model_config = ConfigDict(extra="forbid")

    reasoning: str
    amendment_email: Optional[str] = None


def determine_decision_type(validation_result: ValidationResult) -> DecisionType:
    """Deterministically map validation outcomes to workflow routing decisions."""
    # If any discrepancies exist or overall status is MISMATCH -> Request Amendment
    if (
        validation_result.overall_status == ValidationStatus.MISMATCH
        or len(validation_result.discrepancies) > 0
    ):
        return DecisionType.AMENDMENT_REQUEST

    # If overall status is MATCH with 0 discrepancies -> Auto Approve
    if (
        validation_result.overall_status == ValidationStatus.MATCH
        and len(validation_result.discrepancies) == 0
    ):
        return DecisionType.AUTO_APPROVE

    # If overall status is UNCERTAIN -> Human Review
    if validation_result.overall_status == ValidationStatus.UNCERTAIN:
        return DecisionType.HUMAN_REVIEW

    # Default fail-safe
    return DecisionType.HUMAN_REVIEW


def generate_fallback_reasoning(
    decision: DecisionType, validation_result: ValidationResult
) -> str:
    """Generate concise, deterministic fallback rationale for Cargo Operations operators."""
    if decision == DecisionType.AUTO_APPROVE:
        return (
            "All 8 trade document fields strictly match customer compliance rules "
            "with high confidence and verified grounding quotes. Safe for automated approval."
        )

    if decision == DecisionType.HUMAN_REVIEW:
        uncertain_fields = [
            f"{fv.field_name} ({fv.reason})"
            for fv in validation_result.field_validations.values()
            if fv.status == ValidationStatus.UNCERTAIN
        ]
        fields_str = "; ".join(uncertain_fields) if uncertain_fields else "Unspecified ambiguity"
        return (
            f"Document routed for human review due to uncertain field grounding or confidence: {fields_str}. "
            "Operator verification required before clearance."
        )

    if decision == DecisionType.AMENDMENT_REQUEST:
        discrepancy_items = [
            f"{d.field_name} (found: '{d.found}', expected: '{d.expected}')"
            for d in validation_result.discrepancies
        ]
        disc_str = "; ".join(discrepancy_items) if discrepancy_items else "Compliance rule mismatch"
        return (
            f"Document rejected due to {len(validation_result.discrepancies)} compliance discrepancy(ies): {disc_str}. "
            "Supplier amendment required before processing."
        )

    return "Document routed based on system policy evaluation."


def generate_fallback_amendment_email(
    invoice_number: Optional[str],
    discrepancies: List[Discrepancy],
    document_id: Optional[str] = None,
) -> str:
    """Generate professional, itemized amendment request email for Shipper / Supplier."""
    inv_ref = invoice_number if invoice_number and invoice_number.strip() else "NOT SPECIFIED"
    doc_ref = f" (Ref Doc: {document_id})" if document_id else ""

    email_lines = [
        f"Subject: Urgent: Trade Document Discrepancy Notice - Invoice #{inv_ref}{doc_ref}",
        "",
        "Dear Shipping & Documentation Team,",
        "",
        f"During automated pre-clearance validation for Invoice #{inv_ref}, "
        "the following trade compliance discrepancies were detected against customer requirements:",
        "",
        "| Field Name | Found Value | Expected / Requirement | Severity |",
        "|---|---|---|---|",
    ]

    for d in discrepancies:
        email_lines.append(f"| {d.field_name} | {d.found} | {d.expected} | {d.severity.upper()} |")

    email_lines.extend(
        [
            "",
            "Action Required:",
            "1. Please review the itemized discrepancies above.",
            "2. Issue an amended trade document correcting these values.",
            "3. Re-upload or submit the revised document to Nova Cargo Operations immediately to prevent shipment clearance delays.",
            "",
            "Thank you,",
            "Nova Cargo Operations Team",
            "GoComet Automated Trade Logistics",
        ]
    )

    return "\n".join(email_lines)


class RouterAgent:
    """Policy decision agent with generative rationale and supplier amendment drafting."""

    def __init__(
        self,
        client: Optional[genai.Client] = None,
        model_name: Optional[str] = None,
        mock_mode: bool = False,
    ):
        self.model_name = (
            model_name
            or os.environ.get("LITE_MODEL")
            or DEFAULT_LITE_MODEL
        )
        self.mock_mode = mock_mode

        if mock_mode:
            self.client = None
        elif client is not None:
            self.client = client
        elif os.environ.get("GEMINI_API_KEY"):
            self.client = genai.Client()
        else:
            self.client = None
            self.mock_mode = True

    def decide(
        self,
        validation_result: ValidationResult,
        document_id: Optional[str] = None,
        invoice_number: Optional[str] = None,
    ) -> Tuple[DecisionResult, RunTrace]:
        """Evaluate validation outcomes and generate decision, reasoning, and optional amendment draft."""
        t0 = time.perf_counter()
        decision = determine_decision_type(validation_result)

        reasoning = ""
        draft_amendment_email: Optional[str] = None
        prompt_tokens = 0
        completion_tokens = 0
        thinking_tokens = 0
        cost_usd = 0.0
        status = "SUCCESS"
        error_msg: Optional[str] = None

        if self.mock_mode or self.client is None:
            reasoning = generate_fallback_reasoning(decision, validation_result)
            if decision == DecisionType.AMENDMENT_REQUEST:
                draft_amendment_email = generate_fallback_amendment_email(
                    invoice_number, validation_result.discrepancies, document_id
                )
        else:
            # Build prompt for Gemini
            prompt = self._build_router_prompt(
                decision=decision,
                validation_result=validation_result,
                document_id=document_id,
                invoice_number=invoice_number,
            )

            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        response_mime_type="application/json",
                        response_schema=RouterLLMResponse,
                    ),
                )

                if response.usage_metadata:
                    prompt_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    completion_tokens = (
                        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    )
                    thinking_tokens = (
                        getattr(response.usage_metadata, "thoughts_token_count", 0) or 0
                    )

                cost_usd = (prompt_tokens / 1_000_000 * LITE_PROMPT_COST_PER_MILLION) + (
                    (completion_tokens + thinking_tokens)
                    / 1_000_000
                    * LITE_COMPLETION_COST_PER_MILLION
                )

                parsed_json = json.loads(response.text)
                reasoning = parsed_json.get("reasoning", "")
                if decision == DecisionType.AMENDMENT_REQUEST:
                    draft_amendment_email = parsed_json.get("amendment_email")
                    if not draft_amendment_email:
                        draft_amendment_email = generate_fallback_amendment_email(
                            invoice_number, validation_result.discrepancies, document_id
                        )
                else:
                    draft_amendment_email = None

            except Exception as e:
                error_msg = str(e)
                # Graceful degradation to deterministic template fallback
                reasoning = generate_fallback_reasoning(decision, validation_result)
                if decision == DecisionType.AMENDMENT_REQUEST:
                    draft_amendment_email = generate_fallback_amendment_email(
                        invoice_number, validation_result.discrepancies, document_id
                    )
                else:
                    draft_amendment_email = None

        # Build results
        decision_result = DecisionResult(
            decision=decision,
            reasoning=reasoning,
            draft_amendment_email=draft_amendment_email,
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0

        run_trace = RunTrace(
            run_id=str(uuid.uuid4()),
            document_id=document_id,
            node_name="router",
            model_name=self.model_name,
            latency_ms=round(latency_ms, 2),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            thinking_tokens=thinking_tokens,
            cost_usd=round(cost_usd, 6),
            status=status,
            error_message=error_msg,
        )

        return decision_result, run_trace

    def route(
        self,
        validation_result: ValidationResult,
        extracted_doc: Optional[Any] = None,
        document_id: Optional[str] = None,
    ) -> Tuple[DecisionResult, RunTrace]:
        """Route based on validation outcome and optional extracted document metadata."""
        invoice_number = None
        if extracted_doc is not None:
            if hasattr(extracted_doc, "invoice_number") and extracted_doc.invoice_number:
                invoice_number = getattr(extracted_doc.invoice_number, "value", None)
            elif isinstance(extracted_doc, dict):
                invoice_number = (extracted_doc.get("invoice_number") or {}).get("value")

        return self.decide(
            validation_result=validation_result,
            document_id=document_id,
            invoice_number=invoice_number,
        )

    def _build_router_prompt(
        self,
        decision: DecisionType,
        validation_result: ValidationResult,
        document_id: Optional[str],
        invoice_number: Optional[str],
    ) -> str:
        """Construct prompt for Gemini 3.5 Flash-Lite."""
        discrepancies_data = [d.model_dump() for d in validation_result.discrepancies]
        uncertain_fields = {
            k: v.model_dump()
            for k, v in validation_result.field_validations.items()
            if v.status == ValidationStatus.UNCERTAIN
        }

        return f"""You are Nova's trade operations routing agent.
A document has completed deterministic rule validation with the following outcome:
- Prescribed Decision: {decision.value}
- Overall Validation Status: {validation_result.overall_status.value}
- Document ID: {document_id or 'N/A'}
- Invoice Number: {invoice_number or 'N/A'}
- Discrepancies: {json.dumps(discrepancies_data)}
- Uncertain Fields: {json.dumps(uncertain_fields)}

TASK:
1. Generate 'reasoning': A clear, professional, concise summary (2-4 sentences) explaining the decision rationale for the Cargo Operations (CG) team.
2. If decision is 'amendment_request': Generate 'amendment_email': A formal, courteous email draft to the Shipper/Supplier (SU) detailing each specific discrepancy with found vs expected values and instructions to provide an amended invoice.
3. If decision is NOT 'amendment_request': Set 'amendment_email' to null.
"""
