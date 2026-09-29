"""Integration test suite for FastAPI backend endpoints."""

import io
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.main as main_module
from app.database import get_db
from app.models import Base
from app.query_service import QueryService
from app.storage import StorageService


@pytest.fixture
def test_client(tmp_path, monkeypatch):
    """Hermetic FastAPI test client using file-backed SQLite and mock services."""
    db_file = tmp_path / "test_api.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    import app.database as db_module
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)

    # Configure isolated upload dir
    upload_dir = str(tmp_path / "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    main_module.UPLOAD_DIR = upload_dir

    # Inject mock-mode services
    mock_storage = StorageService(session_factory=session_factory)
    mock_query = QueryService(mock_mode=True, session_factory=session_factory)

    main_module.storage_service = mock_storage
    main_module.query_service = mock_query

    def override_get_db():
        session = session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    main_module.app.dependency_overrides[get_db] = override_get_db

    # Ensure pipeline agents run in mock_mode
    from app.extractor import ExtractorAgent
    from app.router import RouterAgent
    monkeypatch.setattr(
        "app.pipeline.ExtractorAgent",
        lambda *args, **kwargs: ExtractorAgent(mock_mode=True),
    )
    monkeypatch.setattr(
        "app.pipeline.RouterAgent",
        lambda *args, **kwargs: RouterAgent(mock_mode=True),
    )

    client = TestClient(main_module.app)
    yield client
    main_module.app.dependency_overrides.clear()


def test_health_check(test_client):
    """Test GET /api/health endpoint returns 200, healthy status, and llm_configured flag."""
    response = test_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "ready"
    assert data["version"] == "1.0.0"
    assert "llm_configured" in data
    assert isinstance(data["llm_configured"], bool)


def test_resume_document_endpoint_not_found(test_client):
    """Test POST /api/documents/{document_id}/resume returns 404 for missing document."""
    response = test_client.post("/api/documents/non-existent-doc-uuid/resume")
    assert response.status_code == 404


def test_upload_document_endpoint(test_client, monkeypatch):
    """Test POST /api/documents/upload creates document, executes pipeline, and returns bundle."""
    # Ensure extractor runs in mock_mode hermetically
    from app.extractor import ExtractorAgent
    monkeypatch.setattr(
        "app.pipeline.ExtractorAgent",
        lambda *args, **kwargs: ExtractorAgent(mock_mode=True),
    )

    doc_content = (
        b"COMMERCIAL INVOICE\n"
        b"Invoice No: INV-1001\n"
        b"Consignee: ACME LOGISTICS\n"
        b"Port of Loading: CNSHA\n"
        b"Port of Discharge: USLAX\n"
        b"Incoterm: FOB\n"
        b"HS Code: 8504.40\n"
        b"Gross Weight: 5000 KG\n"
        b"Description: Static converters\n"
    )

    files = {
        "file": ("invoice_alpha.txt", io.BytesIO(doc_content), "text/plain"),
    }
    data = {"doc_type": "commercial_invoice"}

    response = test_client.post("/api/documents/upload", files=files, data=data)
    assert response.status_code == 200
    resp_data = response.json()
    assert "document_id" in resp_data
    assert resp_data["filename"] == "invoice_alpha.txt"
    assert resp_data["status"] == "COMPLETED"
    assert resp_data["bundle"] is not None
    assert resp_data["bundle"]["document"]["status"] == "COMPLETED"
    assert resp_data["bundle"]["extraction"] is not None
    assert resp_data["bundle"]["validation"] is not None
    assert resp_data["bundle"]["decision"] is not None


def test_upload_invalid_mime_type(test_client):
    """Test uploading an unsupported file type returns 400 Bad Request."""
    files = {
        "file": ("malicious.exe", io.BytesIO(b"MZBINARY"), "application/x-msdownload"),
    }
    response = test_client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "Unsupported media type" in response.json()["detail"]


def test_upload_empty_file(test_client):
    """Test uploading an empty document returns 400 Bad Request."""
    files = {
        "file": ("empty.pdf", io.BytesIO(b""), "application/pdf"),
    }
    response = test_client.post("/api/documents/upload", files=files)
    assert response.status_code == 400
    assert "empty document" in response.json()["detail"].lower()


def test_get_document_endpoint(test_client):
    """Test GET /api/documents/{id} returns bundle for existing document and 404 for missing."""
    # 1. Non-existent document
    response404 = test_client.get("/api/documents/non-existent-id")
    assert response404.status_code == 404

    # 2. Existing document
    doc = main_module.storage_service.create_document(
        filename="sample.pdf",
        file_path="/tmp/sample.pdf",
        file_hash="hash555",
        mime_type="application/pdf",
        file_size_bytes=4096,
    )
    response200 = test_client.get(f"/api/documents/{doc.id}")
    assert response200.status_code == 200
    bundle = response200.json()
    assert bundle["document"]["id"] == doc.id
    assert bundle["document"]["filename"] == "sample.pdf"


def test_list_documents_endpoint(test_client):
    """Test GET /api/documents returns list of documents with pagination."""
    for i in range(3):
        main_module.storage_service.create_document(
            filename=f"doc_{i}.pdf",
            file_path=f"/tmp/doc_{i}.pdf",
            file_hash=f"hash_{i}",
            mime_type="application/pdf",
            file_size_bytes=1000 + i,
        )

    response = test_client.get("/api/documents?limit=2&offset=0")
    assert response.status_code == 200
    docs = response.json()
    assert len(docs) == 2


def test_get_runs_endpoint(test_client):
    """Test GET /api/runs returns telemetry traces and aggregate summary metrics."""
    doc = main_module.storage_service.create_document(
        filename="telemetry_doc.pdf",
        file_path="/tmp/telemetry_doc.pdf",
        file_hash="hash_telemetry",
        mime_type="application/pdf",
        file_size_bytes=2048,
    )
    from app.schemas import RunTrace
    trace = RunTrace(
        run_id="run_101",
        document_id=doc.id,
        node_name="extractor",
        model_name="gemini-3.8-flash",
        latency_ms=1200.0,
        prompt_tokens=500,
        completion_tokens=200,
        thinking_tokens=100,
        cost_usd=0.0003,
        status="SUCCESS",
    )
    main_module.storage_service.record_run_trace(doc.id, trace)

    response = test_client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "runs" in data
    assert data["metrics"]["total_runs"] >= 1
    assert data["metrics"]["total_tokens"] >= 800
    assert data["metrics"]["total_cost_usd"] >= 0.0003
    assert len(data["runs"]) >= 1


def test_nl_query_endpoint(test_client):
    """Test POST /api/query returns 200 with generated SQL and answer for valid query."""
    doc = main_module.storage_service.create_document(
        filename="query_test.pdf",
        file_path="/tmp/query_test.pdf",
        file_hash="hash_q",
        mime_type="application/pdf",
        file_size_bytes=3000,
    )
    payload = {"query": "How many FOB shipments do we have?"}
    response = test_client.post("/api/query", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["natural_query"] == "How many FOB shipments do we have?"
    assert "sql_query" in result
    assert "grounded_answer" in result
    assert "rows" in result
    assert "columns" in result


def test_nl_query_unsafe(test_client):
    """Test POST /api/query rejects unsafe queries (DROP TABLE) with 400 Bad Request."""
    # Force raw query that fails validation
    class MaliciousQueryService(QueryService):
        def generate_sql(self, user_query):
            from app.query_service import SQLGenerationResponse
            return SQLGenerationResponse(sql_query="DROP TABLE documents;", explanation="Malicious")

    main_module.query_service = MaliciousQueryService(session_factory=main_module.storage_service.session_factory)

    payload = {"query": "Delete all our document history"}
    response = test_client.post("/api/query", json=payload)
    assert response.status_code == 400
    assert "SQL validation error" in response.json()["detail"] or "Only read-only" in response.json()["detail"]
