"""Comprehensive test suite for Pydantic contracts, customer rules, and database models."""

import pytest
from pydantic import ValidationError
from app.schemas import (
    CustomerRules,
    DecisionResult,
    DecisionType,
    Discrepancy,
    ExtractedDoc,
    ExtractedField,
    FieldValidation,
    RunTrace,
    ValidationResult,
    ValidationStatus,
    load_customer_rules,
)
from app.models import Base, Decision, Document, Extraction, Run, Validation


def test_schemas_tracer():
    """Tracer test verifying contract instantiation, serialization, and validation rejection."""
    # 1. Valid ExtractedField with grounding
    grounded_field = ExtractedField(
        value="Meridian Robotics Inc.",
        confidence=0.98,
        source_quote="Meridian Robotics Inc.",
        is_grounded=True,
    )
    assert grounded_field.value == "Meridian Robotics Inc."
    assert grounded_field.confidence == 0.98
    assert grounded_field.is_grounded is True

    # 2. ExtractedDoc instantiation and serialization
    doc = ExtractedDoc(
        consignee=grounded_field,
        hs_code=ExtractedField(value="8479.50", confidence=0.95, source_quote="HS 8479.50", is_grounded=True),
        pol=ExtractedField(value="CNSHA", confidence=0.90, source_quote="Port of Loading: CNSHA", is_grounded=True),
        pod=ExtractedField(value="USLAX", confidence=0.92, source_quote="Port of Discharge: USLAX", is_grounded=True),
        incoterm=ExtractedField(value="FOB", confidence=0.97, source_quote="Terms: FOB", is_grounded=True),
        description=ExtractedField(value="Robotic Arms", confidence=0.95, source_quote="Robotic Arms", is_grounded=True),
        gross_weight=ExtractedField(value="12500 KG", confidence=0.88, source_quote="Gross Wt: 12500 KG", is_grounded=True),
        invoice_number=ExtractedField(value="INV-2026-001", confidence=0.99, source_quote="Invoice # INV-2026-001", is_grounded=True),
        extraction_method="text_layer",
        raw_text="Full invoice text...",
    )
    dumped_dict = doc.model_dump()
    assert dumped_dict["extraction_method"] == "text_layer"
    assert "consignee" in dumped_dict
    assert doc.model_dump_json() is not None

    # 3. Validation rejection on invalid confidence (> 1.0 or < 0.0)
    with pytest.raises(ValidationError):
        ExtractedField(value="Test", confidence=1.5, source_quote="Test", is_grounded=True)

    with pytest.raises(ValidationError):
        ExtractedField(value="Test", confidence=-0.1, source_quote="Test", is_grounded=True)

    # 4. Extra fields rejection (extra="forbid")
    with pytest.raises(ValidationError):
        ExtractedField(value="Test", confidence=0.9, source_quote="Test", is_grounded=True, unexpected_field="fail")  # type: ignore


def test_customer_rules():
    """Verify loading, parsing, and validating Meridian Robotics customer rules YAML."""
    rules = load_customer_rules("config/customer_rules.yaml")

    assert isinstance(rules, CustomerRules)
    assert rules.customer_id == "CUST-001"
    assert rules.customer_name == "Meridian Robotics"

    # Consignee checks
    assert rules.consignee.primary_name == "Meridian Robotics Inc."
    assert "Meridian Robotics LLC" in rules.consignee.aliases
    assert rules.consignee.min_fuzzy_threshold == 0.85

    # HS Codes & Incoterms
    hs_codes = [item.code for item in rules.allowed_hs_codes]
    assert "8479.50" in hs_codes
    assert "8479.89" in hs_codes
    assert "FOB" in rules.allowed_incoterms
    assert "CIF" in rules.allowed_incoterms

    # Ports
    assert "CNSHA" in rules.ports.pol.allowed_locodes
    assert "USLAX" in rules.ports.pod.allowed_locodes

    # Tolerance
    assert rules.weight_tolerance.variance_percent == 5.0
    assert rules.weight_tolerance.max_limit_kg == 50000.0
    assert rules.validation_thresholds.min_confidence_auto_approve == 0.85


def test_validation_result_tri_state():
    """Verify tri-state status logic ('match', 'mismatch', 'uncertain') in validation contracts."""
    valid_statuses = [ValidationStatus.MATCH, ValidationStatus.MISMATCH, ValidationStatus.UNCERTAIN]
    assert len(valid_statuses) == 3

    # Construct validation result with tri-state field validations
    field_vals = {
        "consignee": FieldValidation(
            field_name="consignee",
            status=ValidationStatus.MATCH,
            expected="Meridian Robotics Inc.",
            found="Meridian Robotics Inc.",
            reason="Exact primary name match",
        ),
        "hs_code": FieldValidation(
            field_name="hs_code",
            status=ValidationStatus.MISMATCH,
            expected="8479.50",
            found="8479.05",
            reason="HS code 8479.05 is not in customer allowed list",
        ),
        "incoterm": FieldValidation(
            field_name="incoterm",
            status=ValidationStatus.UNCERTAIN,
            expected="FOB, CIF, or DAP",
            found=None,
            reason="Incoterm could not be verified from source text",
        ),
    }

    discrepancies = [
        Discrepancy(
            field_name="hs_code",
            expected="8479.50",
            found="8479.05",
            severity="critical",
        )
    ]

    result = ValidationResult(
        overall_status=ValidationStatus.MISMATCH,
        field_validations=field_vals,
        discrepancies=discrepancies,
    )

    assert result.overall_status == ValidationStatus.MISMATCH
    assert result.field_validations["hs_code"].status == ValidationStatus.MISMATCH
    assert result.field_validations["incoterm"].status == ValidationStatus.UNCERTAIN
    assert len(result.discrepancies) == 1


def test_zero_silent_approval_schema_invariant():
    """Verify zero-silent-approval invariant: ungrounded or missing quote fields coerce value to None."""
    # Ungrounded field with purported value must have its value coerced to None
    ungrounded_field = ExtractedField(
        value="Meridian Robotics LLC",
        confidence=0.95,
        source_quote=None,
        is_grounded=False,
    )
    assert ungrounded_field.value is None

    # Ungrounded field with empty quote must also coerce value to None
    empty_quote_field = ExtractedField(
        value="FOB",
        confidence=0.85,
        source_quote="   ",
        is_grounded=True,
    )
    assert empty_quote_field.value is None

    # Properly grounded field must retain its value
    grounded_field = ExtractedField(
        value="FOB",
        confidence=0.99,
        source_quote="TERMS: FOB SHANGHAI",
        is_grounded=True,
    )
    assert grounded_field.value == "FOB"


def test_run_trace_token_metrics():
    """Verify RunTrace telemetric structure tracks latency, thinking tokens, and costs."""
    trace = RunTrace(
        run_id="run-test-001",
        document_id="doc-123",
        node_name="extractor",
        model_name="gemini-3.8-flash",
        latency_ms=1240.5,
        prompt_tokens=850,
        completion_tokens=210,
        thinking_tokens=64,
        cost_usd=0.00185,
        status="SUCCESS",
    )

    assert trace.node_name == "extractor"
    assert trace.thinking_tokens == 64
    assert trace.cost_usd > 0.0
    assert trace.status == "SUCCESS"

    # Reject invalid status
    with pytest.raises(ValidationError):
        RunTrace(
            run_id="run-test-002",
            node_name="router",
            latency_ms=100.0,
            status="UNKNOWN_STATUS",  # type: ignore
        )


def test_models_metadata():
    """Verify SQLAlchemy ORM models register tables, columns, and relationships in Base.metadata."""
    table_names = Base.metadata.tables.keys()
    expected_tables = {"documents", "extractions", "validations", "decisions", "runs"}
    assert expected_tables.issubset(table_names)

    # Inspect Document columns
    doc_cols = {col.name for col in Document.__table__.columns}
    assert {"id", "filename", "file_hash", "status", "uploaded_at"}.issubset(doc_cols)

    # Inspect Extraction columns
    ext_cols = {col.name for col in Extraction.__table__.columns}
    assert {"id", "document_id", "raw_json", "consignee", "hs_code", "extraction_method"}.issubset(ext_cols)

    # Inspect Validation columns
    val_cols = {col.name for col in Validation.__table__.columns}
    assert {"id", "document_id", "overall_status", "results_json"}.issubset(val_cols)

    # Inspect Decision columns
    dec_cols = {col.name for col in Decision.__table__.columns}
    assert {"id", "document_id", "decision", "reasoning", "email_draft"}.issubset(dec_cols)

    # Inspect Run columns
    run_cols = {col.name for col in Run.__table__.columns}
    assert {
        "id",
        "document_id",
        "node_name",
        "model_name",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "thinking_tokens",
        "cost_usd",
        "status",
    }.issubset(run_cols)
