"""Unit and security test suite for Text-to-SQL query service and read-only guard (STOR-02, STOR-03)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Document, Extraction, Validation, Decision, Run
from app.query_service import (
    QueryService,
    validate_sql_query,
    QueryRequest,
    QueryResult,
)


def test_validate_sql_query_valid():
    """Test that valid read-only SELECT queries pass and receive automatic LIMIT if missing."""
    valid_query = "SELECT filename, status FROM documents WHERE status = 'COMPLETED'"
    is_valid, sanitized = validate_sql_query(valid_query)
    assert is_valid is True
    assert "LIMIT 100" in sanitized
    assert sanitized.startswith("SELECT filename, status FROM documents")

    # Query with existing LIMIT
    query_with_limit = "SELECT count(*) FROM extractions WHERE incoterm = 'FOB' LIMIT 10"
    is_valid2, sanitized2 = validate_sql_query(query_with_limit)
    assert is_valid2 is True
    assert "LIMIT 10" in sanitized2
    assert sanitized2.count("LIMIT") == 1

    # CTE query
    cte_query = "WITH approved AS (SELECT document_id FROM decisions WHERE decision = 'auto_approve') SELECT * FROM approved"
    is_valid3, sanitized3 = validate_sql_query(cte_query)
    assert is_valid3 is True
    assert "LIMIT 100" in sanitized3


def test_validate_sql_query_blocks_attacks():
    """Test that SQL guard blocks injection, multi-statement queries, DDL, DML, and forbidden tables."""
    # 1. Multi-statement injection
    is_valid, err = validate_sql_query("SELECT * FROM documents; DROP TABLE documents;")
    assert is_valid is False
    assert "Multi-statement" in err or "DROP" in err

    # 2. DROP TABLE
    is_valid, err = validate_sql_query("DROP TABLE extractions")
    assert is_valid is False
    assert "Only read-only SELECT queries" in err or "Forbidden keyword" in err

    # 3. DELETE FROM
    is_valid, err = validate_sql_query("DELETE FROM documents WHERE id = '123'")
    assert is_valid is False

    # 4. UPDATE
    is_valid, err = validate_sql_query("UPDATE documents SET status = 'HACKED'")
    assert is_valid is False

    # 5. INSERT
    is_valid, err = validate_sql_query("INSERT INTO documents (filename) VALUES ('evil.exe')")
    assert is_valid is False

    # 6. Unauthorized table access
    is_valid, err = validate_sql_query("SELECT * FROM users")
    assert is_valid is False
    assert "Unauthorized table access" in err

    # 7. System table access
    is_valid, err = validate_sql_query("SELECT * FROM sqlite_master")
    assert is_valid is False
    assert "Unauthorized table access" in err


def test_query_service_answer_query_end_to_end():
    """Test end-to-end question answering against seeded database."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Seed data
    session = session_factory()
    doc1 = Document(
        id="doc-001",
        filename="invoice_alpha.pdf",
        file_path="/tmp/invoice_alpha.pdf",
        file_hash="hash111",
        mime_type="application/pdf",
        file_size_bytes=12000,
        status="COMPLETED",
    )
    doc2 = Document(
        id="doc-002",
        filename="invoice_beta.pdf",
        file_path="/tmp/invoice_beta.pdf",
        file_hash="hash222",
        mime_type="application/pdf",
        file_size_bytes=15000,
        status="COMPLETED",
    )
    session.add_all([doc1, doc2])

    ext1 = Extraction(
        id="ext-001",
        document_id="doc-001",
        raw_json={},
        consignee="ACME CORP",
        incoterm="FOB",
        extraction_method="text_layer",
    )
    ext2 = Extraction(
        id="ext-002",
        document_id="doc-002",
        raw_json={},
        consignee="GLOBAL TRADE LLC",
        incoterm="CIF",
        extraction_method="vision_default",
    )
    session.add_all([ext1, ext2])

    dec1 = Decision(
        id="dec-001",
        document_id="doc-001",
        decision="auto_approve",
        reasoning="All rules matched",
    )
    dec2 = Decision(
        id="dec-002",
        document_id="doc-002",
        decision="human_review",
        reasoning="Incoterm CIF requires insurance review",
    )
    session.add_all([dec1, dec2])
    session.commit()

    service = QueryService(mock_mode=True, session_factory=session_factory)

    # Query 1: How many FOB shipments?
    result1: QueryResult = service.answer_query("How many FOB shipments do we have?", session=session)
    assert result1.natural_query == "How many FOB shipments do we have?"
    assert "extractions" in result1.sql_query
    assert "FOB" in result1.sql_query
    assert result1.row_count == 1
    assert result1.rows[0][0] == 1  # Exactly 1 FOB extraction
    assert "1" in result1.grounded_answer
    assert result1.execution_time_ms >= 0.0

    # Query 2: Auto approved decisions
    result2: QueryResult = service.answer_query("How many documents were auto_approved?", session=session)
    assert result2.row_count == 1
    assert result2.rows[0][0] == 1

    session.close()
