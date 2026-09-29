"""Unit test suite for database and storage persistence service."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.storage import StorageService
from app.schemas import (
    ExtractedDoc,
    ExtractedField,
    ValidationResult,
    ValidationStatus,
    FieldValidation,
    DecisionResult,
    DecisionType,
    RunTrace,
)


@pytest.fixture
def test_storage():
    """Create a hermetic in-memory SQLite storage service."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return StorageService(session_factory=session_factory)


def test_create_and_retrieve_document(test_storage):
    """Test creating a document and retrieving it via document bundle."""
    doc = test_storage.create_document(
        filename="invoice_101.pdf",
        file_path="/tmp/invoice_101.pdf",
        file_hash="abc123hash",
        mime_type="application/pdf",
        file_size_bytes=10240,
        doc_type="commercial_invoice",
    )

    assert doc.id is not None
    assert doc.status == "PENDING"
    assert doc.filename == "invoice_101.pdf"

    # Update document status
    updated = test_storage.update_document_status(doc.id, "COMPLETED")
    assert updated is not None
    assert updated.status == "COMPLETED"

    bundle = test_storage.get_document_bundle(doc.id)
    assert bundle is not None
    assert bundle["document"]["id"] == doc.id
    assert bundle["document"]["status"] == "COMPLETED"
    assert bundle["document"]["file_hash"] == "abc123hash"


def test_record_run_trace_telemetry(test_storage):
    """Test recording runs telemetry into the runs table (OBS-01)."""
    doc = test_storage.create_document(
        filename="test.pdf",
        file_path="/tmp/test.pdf",
        file_hash="hash999",
        mime_type="application/pdf",
        file_size_bytes=5000,
    )

    trace = RunTrace(
        run_id="run-trace-001",
        document_id=doc.id,
        node_name="extractor_node",
        model_name="gemini-3.8-flash",
        latency_ms=1250.5,
        prompt_tokens=850,
        completion_tokens=220,
        thinking_tokens=150,
        cost_usd=0.00045,
        status="SUCCESS",
        error_message=None,
    )

    run = test_storage.record_run_trace(doc.id, trace)
    assert run.id == "run-trace-001"
    assert run.document_id == doc.id
    assert run.node_name == "extractor_node"
    assert run.model_name == "gemini-3.8-flash"
    assert run.latency_ms == 1250.5
    assert run.prompt_tokens == 850
    assert run.completion_tokens == 220
    assert run.thinking_tokens == 150
    assert pytest.approx(run.cost_usd, rel=1e-5) == 0.00045
    assert run.status == "SUCCESS"

    runs = test_storage.list_runs()
    assert len(runs) == 1
    assert runs[0].id == "run-trace-001"


def test_persist_extraction_validation_decision_bundle(test_storage):
    """Test persisting full lifecycle artifacts and assembling document bundle."""
    doc = test_storage.create_document(
        filename="bol_sample.pdf",
        file_path="/tmp/bol_sample.pdf",
        file_hash="hash_bundle",
        mime_type="application/pdf",
        file_size_bytes=8192,
    )

    extracted_doc = ExtractedDoc(
        consignee=ExtractedField(value="ACME CORP", confidence=0.95, source_quote="ACME CORP", is_grounded=True),
        hs_code=ExtractedField(value="8504.40", confidence=0.92, source_quote="8504.40", is_grounded=True),
        pol=ExtractedField(value="INNSA", confidence=0.90, source_quote="INNSA", is_grounded=True),
        pod=ExtractedField(value="NLRTM", confidence=0.91, source_quote="NLRTM", is_grounded=True),
        incoterm=ExtractedField(value="FOB", confidence=0.98, source_quote="FOB", is_grounded=True),
        description=ExtractedField(value="Power supply units", confidence=0.88, source_quote="Power supply units", is_grounded=True),
        gross_weight=ExtractedField(value="1200 KG", confidence=0.85, source_quote="1200 KG", is_grounded=True),
        invoice_number=ExtractedField(value="INV-2026-001", confidence=0.96, source_quote="INV-2026-001", is_grounded=True),
        extraction_method="text_layer",
        raw_text="Sample raw text",
    )
    extraction = test_storage.save_extraction(doc.id, extracted_doc)
    assert extraction.document_id == doc.id
    assert extraction.consignee == "ACME CORP"
    assert extraction.hs_code == "8504.40"

    validation_result = ValidationResult(
        overall_status=ValidationStatus.MATCH,
        field_validations={
            "consignee": FieldValidation(
                field_name="consignee",
                status=ValidationStatus.MATCH,
                expected="ACME CORP",
                found="ACME CORP",
                reason="Exact match",
            )
        },
        discrepancies=[],
    )
    val = test_storage.save_validation(doc.id, validation_result)
    assert val.document_id == doc.id
    assert val.overall_status == "match"

    decision_result = DecisionResult(
        decision=DecisionType.AUTO_APPROVE,
        reasoning="All required trade fields verified against customer rules with high confidence.",
        draft_amendment_email=None,
    )
    dec = test_storage.save_decision(doc.id, decision_result)
    assert dec.document_id == doc.id
    assert dec.decision == "auto_approve"

    bundle = test_storage.get_document_bundle(doc.id)
    assert bundle is not None
    assert bundle["extraction"]["consignee"]["value"] == "ACME CORP"
    assert bundle["validation"]["overall_status"] == "match"
    assert bundle["decision"]["decision"] == "auto_approve"
    assert "All required trade fields" in bundle["decision"]["reasoning"]
