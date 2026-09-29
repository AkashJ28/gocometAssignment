"""Automated evaluation test suite verifying benchmark logic and the Zero Silent Approvals guarantee (EVAL-01, EVAL-02)."""

import os
import pytest
from evals.run_evals import (
    load_ground_truth,
    run_evaluation,
    extract_deterministic_doc,
    DATASET_DIR,
    CUSTOMER_RULES_FILE,
)
from app.schemas import load_customer_rules, ValidationStatus, DecisionType
from app.validator import ValidatorAgent
from app.router import determine_decision_type


@pytest.fixture
def ground_truth_docs():
    """Load ground truth records."""
    return load_ground_truth()


@pytest.fixture
def validator():
    """Load validator with baseline rules."""
    rules = load_customer_rules(CUSTOMER_RULES_FILE)
    return ValidatorAgent(rules)


def test_dataset_generation_completeness(ground_truth_docs):
    """Verify that all 12 documents exist in the dataset directory."""
    assert len(ground_truth_docs) >= 10, "Dataset must contain at least 10 documents"

    for doc_entry in ground_truth_docs:
        pdf_path = os.path.join(DATASET_DIR, doc_entry["filename"])
        assert os.path.exists(pdf_path), f"Missing dataset PDF file: {pdf_path}"
        assert os.path.getsize(pdf_path) > 500, f"PDF file suspiciously small: {pdf_path}"


def test_zero_silent_approvals():
    """CRITICAL SAFETY TEST: Assert that false-approve rate is strictly 0.0%."""
    summary = run_evaluation(quick=False, write_report=False)

    assert summary["false_approve_count"] == 0, (
        f"SAFETY FAILURE: {summary['false_approve_count']} discrepant/uncertain document(s) "
        f"were silently auto-approved!"
    )
    assert summary["false_approve_rate_pct"] == 0.0, (
        f"False approve rate must be exactly 0.0%, found {summary['false_approve_rate_pct']}%"
    )
    assert summary["discrepant_or_uncertain_count"] > 0, "Evaluation must test discrepant documents"


def test_quick_eval_mode():
    """Test that quick evaluation runs cleanly and verifies representative documents."""
    quick_summary = run_evaluation(quick=True, write_report=False)
    assert quick_summary["total_documents"] == 3
    assert quick_summary["false_approve_count"] == 0
    assert quick_summary["false_approve_rate_pct"] == 0.0


def test_planted_discrepancies_detected(ground_truth_docs, validator):
    """Verify that specific planted discrepancies trigger MISMATCH or UNCERTAIN, never MATCH."""
    discrepant_ids = {"doc_04", "doc_05", "doc_06", "doc_07", "doc_08", "doc_10", "doc_11"}

    for doc_entry in ground_truth_docs:
        doc_id = doc_entry["document_id"]
        if doc_id not in discrepant_ids:
            continue

        pdf_path = os.path.join(DATASET_DIR, doc_entry["filename"])
        extracted_doc = extract_deterministic_doc(pdf_path, doc_entry["expected_fields"])

        val_result = validator.validate(extracted_doc)
        decision = determine_decision_type(val_result)

        # Invariant: Discrepant documents must never be MATCH or AUTO_APPROVE
        assert val_result.overall_status != ValidationStatus.MATCH, (
            f"Planted error in {doc_id} was falsely validated as MATCH!"
        )
        assert decision != DecisionType.AUTO_APPROVE, (
            f"Planted error in {doc_id} was falsely routed to AUTO_APPROVE!"
        )

        expected_decision = doc_entry["expected_decision"].lower()
        assert decision.value.lower() == expected_decision, (
            f"Routing mismatch for {doc_id}: expected {expected_decision}, got {decision.value}"
        )
