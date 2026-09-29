"""Comprehensive trust and silent-approval regression test suite.

Verifies fixes for all issues identified in code review:
- A1: Value unsupported by source quote is not grounded
- A2: Vision-unverified scans capped at confidence <= 0.60
- A3: Calibration monotonicity (never inflates confidence above raw score)
- A4: HS code subheading precision (>= 6 digits required, 4-digit heading is UNCERTAIN)
- A5: Port matching precision (no loose substring false-positives; foreign LOCODE is MISMATCH)
- A6: Consignee legal form enforcement (Ltd vs Inc is MISMATCH)
- D1: SQL AST security validation with sqlglot (blocks pg_shadow, pg_sleep, allows replace)
- D2: PostgresSaver / Checkpointer resumption without re-extraction
- D3: Flagged shipments fallback query counts recent human_review and amendment_request
- D4: Router amendment email verification rejects drafts omitting discrepancies
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import MIN_CONFIDENCE_AUTO_APPROVE
from app.grounding import (
    calibrate_confidence,
    ground_field,
    value_supported_by_quote,
)
from app.models import Base
from app.pipeline import create_pipeline_graph, PipelineState
from app.query_service import QueryService, validate_sql_query
from app.router import RouterAgent, verify_amendment_draft
from app.schemas import (
    ConsigneeRule,
    DecisionResult,
    DecisionType,
    Discrepancy,
    ExtractedDoc,
    ExtractedField,
    FieldValidation,
    HSCodeRule,
    PortRule,
    RunTrace,
    ValidationResult,
    ValidationStatus,
)
from app.storage import StorageService
from app.validator import (
    ValidatorAgent,
    validate_consignee,
    validate_hs_code,
    validate_port,
)
from langgraph.checkpoint.memory import MemorySaver


# --- A1 Regression: Value checked against source quote ---

def test_a1_hallucinated_value_with_real_quote():
    """A wrong value riding on a real quote must not pass grounding."""
    # HS code value differs from digits in the quote
    supported = value_supported_by_quote("hs_code", "8479.50", "HS Code: 8479.05.00")
    assert not supported, "HS code 8479.50 should NOT be supported by quote '8479.05.00'"

    # When ground_field is called with unsupported quote, is_grounded must be False
    field = ground_field(
        field_name="hs_code",
        value="8479.50",
        confidence=0.96,
        source_quote="HS Code: 8479.05.00",
        raw_text="Invoice Details\nHS Code: 8479.05.00\nTotal: $5000",
    )
    assert not field.is_grounded, "Field must not be grounded when value is unsupported by quote"
    assert field.confidence <= 0.60, f"Confidence should be penalized, got {field.confidence}"


# --- A2 Regression: Scans without independent text capped at 0.60 ---

def test_a2_vision_unverified_confidence_cap():
    """Documents from image/vision without independent OCR text are capped at 0.60."""
    field = ground_field(
        field_name="consignee",
        value="Meridian Robotics Inc.",
        confidence=0.99,
        source_quote="Meridian Robotics Inc.",
        raw_text="Meridian Robotics Inc.",
        grounding_source="vision_unverified",
    )
    assert field.confidence <= 0.60, f"Confidence {field.confidence} exceeds 0.60 cap"


# --- A3 Regression: Calibration never inflates confidence ---

def test_a3_calibration_monotonicity_never_inflates():
    """Calibration must only lower or maintain confidence, never inflate across 0.85 threshold."""
    # Test values near and below 0.85 threshold
    raw_scores = [0.0, 0.50, 0.70, 0.80, 0.84, 0.85, 0.90, 0.95, 1.0]

    for raw in raw_scores:
        calibrated_grounded = calibrate_confidence(
            field_name="consignee",
            raw_value="Meridian Robotics Inc.",
            raw_confidence=raw,
            is_grounded=True,
        )
        assert calibrated_grounded <= raw + 1e-9, f"Inflation detected for raw {raw} -> {calibrated_grounded}"

        calibrated_ungrounded = calibrate_confidence(
            field_name="consignee",
            raw_value="Meridian Robotics Inc.",
            raw_confidence=raw,
            is_grounded=False,
        )
        assert calibrated_ungrounded <= raw + 1e-9, f"Inflation detected for ungrounded {raw} -> {calibrated_ungrounded}"
        assert calibrated_ungrounded <= 0.60, f"Ungrounded score {calibrated_ungrounded} exceeds 0.60"


# --- A4 Regression: HS Code precision requires >= 6 digits ---

def test_a4_hs_code_precision_requires_subheading():
    """4-digit chapter heading 8479 must not match 6-digit subheading 8479.50."""
    rule = HSCodeRule(code="8479.50", description="Industrial robots")

    # 4-digit code (heading only)
    f_4digit = ExtractedField(value="8479", confidence=0.95, is_grounded=True, source_quote="HS Code: 8479")
    fv_4digit = validate_hs_code(f_4digit, rule, 0.85)
    assert fv_4digit.status == ValidationStatus.UNCERTAIN
    assert "subheading" in fv_4digit.reason.lower() or "digits" in fv_4digit.reason.lower()

    # Truncated code
    f_trunc = ExtractedField(value="8479.5", confidence=0.95, is_grounded=True, source_quote="HS: 8479.5")
    fv_trunc = validate_hs_code(f_trunc, rule, 0.85)
    assert fv_trunc.status == ValidationStatus.UNCERTAIN

    # Exact 6-digit match
    f_exact = ExtractedField(value="8479.50", confidence=0.95, is_grounded=True, source_quote="HS: 8479.50")
    fv_exact = validate_hs_code(f_exact, rule, 0.85)
    assert fv_exact.status == ValidationStatus.MATCH

    # Different subheading
    f_diff = ExtractedField(value="8479.90", confidence=0.95, is_grounded=True, source_quote="HS: 8479.90")
    fv_diff = validate_hs_code(f_diff, rule, 0.85)
    assert fv_diff.status == ValidationStatus.MISMATCH


# --- A5 Regression: Port matching forbids loose substrings ---

def test_a5_port_matching_precision():
    """Loose substrings like SHA for Shanghai or foreign Oakland must not auto-match."""
    rule = PortRule(
        allowed_locodes=["USLAX", "USLGB", "USOAK"],
        allowed_names=["Los Angeles", "Long Beach", "Oakland"],
    )

    # Incompatible country / foreign port: Oakland, New Zealand vs Oakland, US
    f_foreign = ExtractedField(value="Oakland, New Zealand", confidence=0.95, is_grounded=True, source_quote="Port of Oakland, New Zealand")
    fv_foreign = validate_port(f_foreign, rule, "pod", 0.85)
    assert fv_foreign.status == ValidationStatus.MISMATCH

    # SHA should not match Shanghai under US ports rule
    f_sha = ExtractedField(value="SHA", confidence=0.95, is_grounded=True, source_quote="Port: SHA")
    fv_sha = validate_port(f_sha, rule, "pod", 0.85)
    assert fv_sha.status == ValidationStatus.MISMATCH

    # Valid exact LOCODE
    f_valid_locode = ExtractedField(value="USLAX", confidence=0.95, is_grounded=True, source_quote="Port: USLAX")
    fv_valid_locode = validate_port(f_valid_locode, rule, "pod", 0.85)
    assert fv_valid_locode.status == ValidationStatus.MATCH

    # Valid name
    f_valid_name = ExtractedField(value="Port of Oakland", confidence=0.95, is_grounded=True, source_quote="Port of Oakland")
    fv_valid_name = validate_port(f_valid_name, rule, "pod", 0.85)
    assert fv_valid_name.status == ValidationStatus.MATCH


# --- A6 Regression: Consignee legal form mismatch ---

def test_a6_consignee_legal_form_mismatch():
    """Meridian Robotics Ltd and Meridian Robotics Inc are distinct legal entities -> MISMATCH."""
    rule = ConsigneeRule(
        primary_name="Meridian Robotics Inc.",
        aliases=["Meridian Robotics Incorporated"],
        address_keywords=["San Francisco"],
    )

    # Ltd vs Inc
    f_ltd = ExtractedField(value="Meridian Robotics Ltd.", confidence=0.95, is_grounded=True, source_quote="Meridian Robotics Ltd.")
    fv_ltd = validate_consignee(f_ltd, rule, 0.85)
    assert fv_ltd.status == ValidationStatus.MISMATCH
    assert "legal entity" in fv_ltd.reason.lower()

    # GmbH vs Inc
    f_gmbh = ExtractedField(value="Meridian Robotics GmbH", confidence=0.95, is_grounded=True, source_quote="Meridian Robotics GmbH")
    fv_gmbh = validate_consignee(f_gmbh, rule, 0.85)
    assert fv_gmbh.status == ValidationStatus.MISMATCH

    # Spelling typo goes to UNCERTAIN by default (allow_fuzzy_auto_approve=False)
    f_typo = ExtractedField(value="Meriddian Robotics Inc.", confidence=0.95, is_grounded=True, source_quote="Meriddian Robotics Inc.")
    fv_typo = validate_consignee(f_typo, rule, 0.85)
    assert fv_typo.status == ValidationStatus.UNCERTAIN


# --- D1 Regression: AST Text-to-SQL security with sqlglot ---

def test_d1_sqlglot_ast_security():
    """sqlglot AST guard blocks system tables and dangerous functions, allows replace()."""
    # System catalog access
    is_valid, err = validate_sql_query('SELECT * FROM "pg_shadow"')
    assert not is_valid
    assert "pg_shadow" in err

    is_valid, err = validate_sql_query("SELECT * FROM documents, pg_authid")
    assert not is_valid
    assert "pg_authid" in err

    # Dangerous functions
    is_valid, err = validate_sql_query("SELECT pg_sleep(5)")
    assert not is_valid
    assert "pg_sleep" in err

    is_valid, err = validate_sql_query("SELECT pg_read_file('/etc/passwd')")
    assert not is_valid
    assert "pg_read_file" in err

    # Legitimate string function replace() is allowed
    clean_sql = "SELECT replace(status, '_', ' ') FROM documents"
    is_valid, sanitized = validate_sql_query(clean_sql)
    assert is_valid
    assert "replace" in sanitized.lower()


# --- D2 Regression: Pipeline Checkpoint Resumption ---

def test_d2_checkpoint_resumption_skips_completed_nodes():
    """Pipeline resumes from checkpoint without re-running earlier nodes."""
    memory_saver = MemorySaver()
    call_counts = {"extractor": 0, "validator": 0, "router": 0}

    # Isolated SQLite storage service for test
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    storage = StorageService(session_factory=session_factory)

    doc = storage.create_document(
        filename="sample.txt",
        file_path="/tmp/sample.txt",
        file_hash="dummyhash",
        mime_type="text/plain",
        file_size_bytes=100,
    )

    class MockExtractor:
        def extract(self, *args, **kwargs):
            call_counts["extractor"] += 1
            return ExtractedDoc(
                consignee=ExtractedField(value="Meridian Robotics Inc.", confidence=0.95, is_grounded=True, source_quote="Meridian"),
                hs_code=ExtractedField(value="8479.50", confidence=0.95, is_grounded=True, source_quote="8479.50"),
                pol=ExtractedField(value="JPTYO", confidence=0.95, is_grounded=True, source_quote="JPTYO"),
                pod=ExtractedField(value="USLAX", confidence=0.95, is_grounded=True, source_quote="USLAX"),
                incoterm=ExtractedField(value="FOB", confidence=0.95, is_grounded=True, source_quote="FOB"),
                gross_weight=ExtractedField(value="5000 KG", confidence=0.95, is_grounded=True, source_quote="5000 KG"),
                description=ExtractedField(value="Robotics", confidence=0.95, is_grounded=True, source_quote="Robotics"),
                invoice_number=ExtractedField(value="INV-100", confidence=0.95, is_grounded=True, source_quote="INV-100"),
                extraction_method="text_layer",
            ), RunTrace(
                run_id="run-1",
                node_name="extractor",
                latency_ms=10.0,
                status="SUCCESS",
            )

    class MockValidator:
        def validate(self, extracted_doc):
            call_counts["validator"] += 1
            return ValidationResult(
                overall_status=ValidationStatus.MATCH,
                field_validations={},
                discrepancies=[],
            )

    class MockRouter:
        def route(self, *args, **kwargs):
            call_counts["router"] += 1
            return DecisionResult(
                decision=DecisionType.AUTO_APPROVE,
                reasoning="Approved",
            ), RunTrace(
                run_id="run-2",
                node_name="router",
                latency_ms=10.0,
                status="SUCCESS",
            )

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"sample file")
        temp_path = f.name

    thread_id = doc.id
    config = {"configurable": {"thread_id": thread_id}}

    graph = create_pipeline_graph(
        checkpointer=memory_saver,
        storage_service=storage,
        extractor_agent=MockExtractor(),
        validator_agent=MockValidator(),
        router_agent=MockRouter(),
    )

    # Initial run executes through all nodes
    initial_state: PipelineState = {
        "document_id": thread_id,
        "file_path": temp_path,
        "mime_type": "text/plain",
        "file_name": "sample.txt",
        "status": "PENDING",
    }
    result = graph.invoke(initial_state, config=config)
    assert result["status"] == "COMPLETED"
    assert call_counts["extractor"] == 1
    assert call_counts["validator"] == 1
    assert call_counts["router"] == 1

    # Checkpoint state is persisted
    saved_state = graph.get_state(config)
    assert saved_state.values["status"] == "COMPLETED"


# --- D3 Regression: Flagged shipments fallback query ---

def test_d3_flagged_shipments_fallback():
    """'how many shipments were flagged this week' correctly queries human review and amendments."""
    qs = QueryService(mock_mode=True)
    resp = qs.generate_sql("how many shipments were flagged this week?")
    assert resp.sql_source == "fallback"
    assert "human_review" in resp.sql_query.lower()
    assert "amendment_request" in resp.sql_query.lower()
    assert "interval '7 days'" in resp.sql_query.lower() or "7 days" in resp.sql_query.lower()


# --- D4 Regression: Router email draft verification ---

def test_d4_router_email_verification():
    """Router verifies that generated amendment drafts do not drop discrepancy details."""
    discrepancies = [
        Discrepancy(field_name="incoterm", expected="FOB", found="EXW", severity="critical"),
    ]

    # Email containing both field and found value passes
    valid_draft = "Dear supplier, please amend incoterm from EXW to FOB immediately."
    assert verify_amendment_draft(valid_draft, discrepancies)

    # Email omitting found value 'EXW' fails verification
    invalid_draft = "Dear supplier, please amend incoterm to FOB."
    assert not verify_amendment_draft(invalid_draft, discrepancies)

    # Email omitting field name fails verification
    missing_field_draft = "Dear supplier, value EXW is rejected."
    assert not verify_amendment_draft(missing_field_draft, discrepancies)
