"""Unit tests for policy RouterAgent, decision engine, and amendment drafting."""

import json
from unittest.mock import MagicMock
import pytest

from app.router import (
    RouterAgent,
    determine_decision_type,
    generate_fallback_amendment_email,
    generate_fallback_reasoning,
)
from app.schemas import (
    DecisionType,
    Discrepancy,
    FieldValidation,
    ValidationResult,
    ValidationStatus,
)


@pytest.fixture
def clean_validation_result() -> ValidationResult:
    """Fixture providing a clean MATCH ValidationResult."""
    return ValidationResult(
        overall_status=ValidationStatus.MATCH,
        field_validations={
            "consignee": FieldValidation(
                field_name="consignee",
                status=ValidationStatus.MATCH,
                expected="Meridian Robotics Inc.",
                found="Meridian Robotics Inc.",
                reason="Exact match",
            )
        },
        discrepancies=[],
    )


@pytest.fixture
def mismatch_validation_result() -> ValidationResult:
    """Fixture providing a MISMATCH ValidationResult with discrepancies."""
    return ValidationResult(
        overall_status=ValidationStatus.MISMATCH,
        field_validations={
            "incoterm": FieldValidation(
                field_name="incoterm",
                status=ValidationStatus.MISMATCH,
                expected="FOB, CIF, DAP",
                found="EXW",
                reason="Incoterm EXW is not in customer approved list",
            )
        },
        discrepancies=[
            Discrepancy(
                field_name="incoterm",
                expected="FOB, CIF, DAP",
                found="EXW",
                severity="critical",
            )
        ],
    )


@pytest.fixture
def uncertain_validation_result() -> ValidationResult:
    """Fixture providing an UNCERTAIN ValidationResult."""
    return ValidationResult(
        overall_status=ValidationStatus.UNCERTAIN,
        field_validations={
            "description": FieldValidation(
                field_name="description",
                status=ValidationStatus.UNCERTAIN,
                expected="Confidence >= 0.85",
                found="Robotic Arms",
                reason="Field confidence 0.70 below auto-approval threshold 0.85",
            )
        },
        discrepancies=[],
    )


# --- Task 1 Tests: Deterministic Decision Logic ---

def test_determine_decision_type_auto_approve(clean_validation_result):
    """Clean MATCH validation with 0 discrepancies routes to AUTO_APPROVE."""
    decision = determine_decision_type(clean_validation_result)
    assert decision == DecisionType.AUTO_APPROVE


def test_determine_decision_type_amendment_request(mismatch_validation_result):
    """MISMATCH validation or non-zero discrepancies routes to AMENDMENT_REQUEST."""
    decision = determine_decision_type(mismatch_validation_result)
    assert decision == DecisionType.AMENDMENT_REQUEST


def test_determine_decision_type_human_review(uncertain_validation_result):
    """UNCERTAIN validation routes to HUMAN_REVIEW."""
    decision = determine_decision_type(uncertain_validation_result)
    assert decision == DecisionType.HUMAN_REVIEW


def test_fallback_reasoning(clean_validation_result, mismatch_validation_result, uncertain_validation_result):
    """Fallback reasoning generates distinct, informative texts for each decision type."""
    r_approve = generate_fallback_reasoning(DecisionType.AUTO_APPROVE, clean_validation_result)
    assert "safe for automated approval" in r_approve.lower()

    r_review = generate_fallback_reasoning(DecisionType.HUMAN_REVIEW, uncertain_validation_result)
    assert "human review" in r_review.lower()
    assert "description" in r_review

    r_amend = generate_fallback_reasoning(DecisionType.AMENDMENT_REQUEST, mismatch_validation_result)
    assert "rejected" in r_amend.lower()
    assert "incoterm" in r_amend


def test_fallback_amendment_email(mismatch_validation_result):
    """Fallback amendment email formats itemized discrepancies and invoice reference."""
    email = generate_fallback_amendment_email(
        invoice_number="INV-2026-9081",
        discrepancies=mismatch_validation_result.discrepancies,
        document_id="doc-abc-123",
    )
    assert "Invoice #INV-2026-9081" in email
    assert "doc-abc-123" in email
    assert "| incoterm | EXW | FOB, CIF, DAP | CRITICAL |" in email
    assert "Action Required:" in email


# --- Task 2 Tests: RouterAgent & RunTrace Telemetry ---

def test_router_agent_auto_approve_no_email(clean_validation_result):
    """Auto-approve decision in RouterAgent produces no amendment email draft."""
    agent = RouterAgent(mock_mode=True)
    decision_result, run_trace = agent.decide(clean_validation_result, document_id="doc-001")

    assert decision_result.decision == DecisionType.AUTO_APPROVE
    assert decision_result.draft_amendment_email is None
    assert "safe for automated approval" in decision_result.reasoning.lower()

    assert run_trace.node_name == "router"
    assert run_trace.document_id == "doc-001"
    assert run_trace.latency_ms >= 0.0
    assert run_trace.status == "SUCCESS"


def test_router_agent_amendment_request_with_email(mismatch_validation_result):
    """Amendment request decision in RouterAgent produces an itemized draft email."""
    agent = RouterAgent(mock_mode=True)
    decision_result, run_trace = agent.decide(
        mismatch_validation_result,
        document_id="doc-002",
        invoice_number="INV-8877",
    )

    assert decision_result.decision == DecisionType.AMENDMENT_REQUEST
    assert decision_result.draft_amendment_email is not None
    assert "Invoice #INV-8877" in decision_result.draft_amendment_email
    assert "EXW" in decision_result.draft_amendment_email

    assert run_trace.status == "SUCCESS"


def test_router_agent_human_review_no_email(uncertain_validation_result):
    """Human review decision produces reasoning without an amendment email."""
    agent = RouterAgent(mock_mode=True)
    decision_result, run_trace = agent.decide(uncertain_validation_result, document_id="doc-003")

    assert decision_result.decision == DecisionType.HUMAN_REVIEW
    assert decision_result.draft_amendment_email is None
    assert "human review" in decision_result.reasoning.lower()


def test_router_agent_with_mock_client(mismatch_validation_result):
    """RouterAgent parses LLM response and computes token metrics and cost."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "reasoning": "The document displays an unauthorized Incoterm EXW requiring supplier correction.",
        "amendment_email": "Subject: Please amend Incoterm to FOB.",
    })
    usage = MagicMock()
    usage.prompt_token_count = 500
    usage.candidates_token_count = 120
    usage.thoughts_token_count = 30
    mock_response.usage_metadata = usage

    mock_client.models.generate_content.return_value = mock_response

    agent = RouterAgent(client=mock_client, model_name="gemini-2.5-flash-lite")
    decision_result, run_trace = agent.decide(
        mismatch_validation_result,
        document_id="doc-004",
        invoice_number="INV-9999",
    )

    assert decision_result.decision == DecisionType.AMENDMENT_REQUEST
    assert "unauthorized Incoterm" in decision_result.reasoning
    assert decision_result.draft_amendment_email == "Subject: Please amend Incoterm to FOB."

    assert run_trace.prompt_tokens == 500
    assert run_trace.completion_tokens == 120
    assert run_trace.thinking_tokens == 30
    assert run_trace.cost_usd > 0.0


def test_router_agent_api_error_fallback(mismatch_validation_result):
    """When LLM API fails, RouterAgent gracefully reverts to deterministic template fallbacks."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API connection timeout")

    agent = RouterAgent(client=mock_client, model_name="gemini-2.5-flash-lite")
    decision_result, run_trace = agent.decide(
        mismatch_validation_result,
        document_id="doc-005",
        invoice_number="INV-1234",
    )

    # Must not crash!
    assert decision_result.decision == DecisionType.AMENDMENT_REQUEST
    assert "compliance discrepancy" in decision_result.reasoning.lower()
    assert decision_result.draft_amendment_email is not None
    assert "Invoice #INV-1234" in decision_result.draft_amendment_email
    assert run_trace.error_message == "API connection timeout"
    assert run_trace.status == "SUCCESS"
