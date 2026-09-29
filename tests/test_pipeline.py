"""Integration test suite for LangGraph StateGraph pipeline and checkpointing."""

import os
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from langgraph.checkpoint.memory import MemorySaver

from app.models import Base, Document, Extraction, Validation, Decision, Run
from app.storage import StorageService
from app.extractor import ExtractorAgent
from app.validator import ValidatorAgent
from app.router import RouterAgent
from app.pipeline import run_pipeline, resume_pipeline, create_pipeline_graph, PipelineState
from app.schemas import (
    CustomerRules,
    ConsigneeRule,
    HSCodeRule,
    PortRule,
    PortsRule,
    WeightToleranceRule,
    ValidationThresholdsRule,
    ExtractedDoc,
    ExtractedField,
    RunTrace,
    DecisionResult,
    DecisionType,
)


@pytest.fixture
def test_db_storage():
    """Hermetic SQLite storage service."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return StorageService(session_factory=session_factory)


@pytest.fixture
def mock_rules():
    """Deterministic test customer rules."""
    return CustomerRules(
        customer_id="CUST-001",
        customer_name="Global Logistics Corp",
        consignee=ConsigneeRule(
            primary_name="ACME LOGISTICS INC",
            aliases=["ACME LOGISTICS", "ACME CORP"],
            address_keywords=["NEW YORK"],
            min_fuzzy_threshold=0.80,
        ),
        allowed_hs_codes=[
            HSCodeRule(code="8479.50", description="Industrial robots"),
            HSCodeRule(code="8504.40", description="Static converters"),
        ],
        allowed_incoterms=["FOB", "CIF", "EXW"],
        ports=PortsRule(
            pol=PortRule(allowed_locodes=["CNSHA"], allowed_names=["SHANGHAI"]),
            pod=PortRule(allowed_locodes=["USLAX"], allowed_names=["LOS ANGELES"]),
        ),
        weight_tolerance=WeightToleranceRule(
            unit="KG",
            variance_percent=5.0,
            max_limit_kg=25000.0,
        ),
        validation_thresholds=ValidationThresholdsRule(
            min_confidence_auto_approve=0.85,
        ),
    )


@pytest.fixture
def sample_document_file():
    """Create a temporary text file simulating a trade document."""
    content = (
        "COMMERCIAL INVOICE\n"
        "Invoice No: INV-2026-999\n"
        "Consignee: ACME LOGISTICS INC, NEW YORK\n"
        "Port of Loading: CNSHA\n"
        "Port of Discharge: USLAX\n"
        "Incoterm: FOB\n"
        "HS Code: 8479.50\n"
        "Description: Industrial assembly robots\n"
        "Gross Weight: 12500 KG\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(content)
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)


def test_pipeline_end_to_end(test_db_storage, mock_rules, sample_document_file):
    """Test full multi-agent pipeline: Extractor -> Validator -> Router with telemetry logging."""
    # 1. Initialize Document in DB
    doc = test_db_storage.create_document(
        filename="test_invoice.txt",
        file_path=sample_document_file,
        file_hash="hash123",
        mime_type="text/plain",
        file_size_bytes=os.path.getsize(sample_document_file),
    )

    extractor = ExtractorAgent(mock_mode=True)
    validator = ValidatorAgent(rules=mock_rules)
    router = RouterAgent(mock_mode=True)
    checkpointer = MemorySaver()

    # 2. Run pipeline
    final_state = run_pipeline(
        document_id=doc.id,
        file_path=sample_document_file,
        mime_type="text/plain",
        file_name="test_invoice.txt",
        checkpointer=checkpointer,
        storage_service=test_db_storage,
        extractor_agent=extractor,
        validator_agent=validator,
        router_agent=router,
    )

    assert final_state["status"] == "COMPLETED"
    assert final_state["error"] is None
    assert final_state["extracted_doc"] is not None
    assert final_state["validation_result"] is not None
    assert final_state["decision_result"] is not None
    assert final_state["decision_result"]["decision"] in ["auto_approve", "human_review", "amendment_request"]

    # 3. Verify Database entities
    bundle = test_db_storage.get_document_bundle(doc.id)
    assert bundle is not None
    assert bundle["document"]["status"] == "COMPLETED"
    assert bundle["extraction"] is not None
    assert bundle["validation"] is not None
    assert bundle["decision"] is not None

    # 4. Verify Telemetry in runs table (OBS-01)
    runs = test_db_storage.list_runs()
    node_names = [r.node_name for r in runs]
    assert "extractor" in node_names
    assert "validator" in node_names
    assert "router" in node_names

    for r in runs:
        assert r.document_id == doc.id
        assert r.status == "SUCCESS"
        assert r.latency_ms >= 0.0


def test_pipeline_checkpoint_resumption(test_db_storage, mock_rules, sample_document_file):
    """Test crash resilience and checkpoint resumption without re-running upstream nodes."""
    doc = test_db_storage.create_document(
        filename="crash_test.txt",
        file_path=sample_document_file,
        file_hash="hash_crash",
        mime_type="text/plain",
        file_size_bytes=os.path.getsize(sample_document_file),
    )

    checkpointer = MemorySaver()
    extractor = ExtractorAgent(mock_mode=True)
    validator = ValidatorAgent(rules=mock_rules)

    class FlakyRouter(RouterAgent):
        def __init__(self):
            super().__init__(mock_mode=True)
            self.should_fail = True

        def route(self, validation_result, extracted_doc=None, document_id=None):
            if self.should_fail:
                raise RuntimeError("Simulated router crash")
            return super().route(validation_result, extracted_doc, document_id)

    flaky_router = FlakyRouter()

    # Step 1: Run graph where router fails
    graph = create_pipeline_graph(
        checkpointer=checkpointer,
        storage_service=test_db_storage,
        extractor_agent=extractor,
        validator_agent=validator,
        router_agent=flaky_router,
    )

    initial_state: PipelineState = {
        "document_id": doc.id,
        "file_path": sample_document_file,
        "mime_type": "text/plain",
        "file_name": "crash_test.txt",
        "status": "PENDING",
    }
    cfg = {"configurable": {"thread_id": doc.id}}
    res1 = graph.invoke(initial_state, config=cfg)
    assert res1["status"] == "FAILED"
    assert "Simulated router crash" in res1["error"]

    # Verify that extractor and validator succeeded and were saved to checkpoint
    saved_state = graph.get_state(cfg)
    assert saved_state.values["status"] == "FAILED"
    assert saved_state.values["extracted_doc"] is not None
    assert saved_state.values["validation_result"] is not None

    # Step 2: Fix router and resume using resume_pipeline
    flaky_router.should_fail = False
    fixed_graph = create_pipeline_graph(
        checkpointer=checkpointer,
        storage_service=test_db_storage,
        extractor_agent=extractor,
        validator_agent=validator,
        router_agent=flaky_router,
    )

    # Resume with fixed graph by clearing error status and invoking
    resume_update: PipelineState = {"status": "VALIDATED", "error": None}
    resumed_state = fixed_graph.invoke(resume_update, config=cfg)

    assert resumed_state["status"] == "COMPLETED"
    assert resumed_state["error"] is None
    assert resumed_state["decision_result"] is not None

    # Verify document bundle shows completed status
    bundle = test_db_storage.get_document_bundle(doc.id)
    assert bundle["document"]["status"] == "COMPLETED"
    assert bundle["decision"] is not None
