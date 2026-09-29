"""Unit and integration tests for document parsing and extractor agent."""

import json
from unittest.mock import MagicMock
import pymupdf
import pytest
from app.extractor import ExtractorAgent, DocumentExtractionPayload, RawFieldExtraction
from app.parser import parse_document, ParsedDocument
from app.schemas import ExtractedDoc, RunTrace


def create_sample_pdf(text: str) -> bytes:
    """Helper to generate an in-memory PDF with the provided text string."""
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((50, 50), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_parser_density_fallback():
    """Verify parser switches between digital text layer and vision fallback based on density."""
    # 1. High-density digital PDF (> 80 characters, high alpha ratio)
    high_density_text = (
        "COMMERCIAL INVOICE\n"
        "Invoice Number: INV-2026-001\n"
        "Consignee: Meridian Robotics Inc., 100 Tech Boulevard, San Jose, CA 95134\n"
        "Port of Loading: CNSHA Shanghai Port\n"
        "Port of Discharge: USLAX Los Angeles Port\n"
        "Incoterm: FOB\n"
        "Description of Goods: Industrial Robotic Arms and Automation Units\n"
        "Gross Weight: 12,500 KG\n"
        "HS Code: 8479.50.00"
    )
    pdf_bytes = create_sample_pdf(high_density_text)
    parsed = parse_document(pdf_bytes, "invoice.pdf")

    assert parsed.extraction_method == "text_layer"
    assert parsed.mime_type == "application/pdf"
    assert parsed.raw_text is not None
    assert "Meridian Robotics Inc." in parsed.raw_text
    assert len(parsed.page_images) == 0
    assert parsed.page_count == 1

    # 2. Sparse / scanned PDF (< 80 characters)
    sparse_text = "Scan page 1"
    scanned_bytes = create_sample_pdf(sparse_text)
    parsed_scan = parse_document(scanned_bytes, "scanned_doc.pdf")

    assert parsed_scan.extraction_method == "vision_fallback"
    assert parsed_scan.mime_type == "application/pdf"
    assert len(parsed_scan.page_images) == 1
    assert parsed_scan.page_images[0].startswith(b"\x89PNG")  # Rendered PNG header
    assert parsed_scan.page_count == 1

    # 3. Empty PDF (0 characters)
    empty_bytes = create_sample_pdf("")
    parsed_empty = parse_document(empty_bytes, "empty.pdf")
    assert parsed_empty.extraction_method == "vision_fallback"
    assert len(parsed_empty.page_images) == 1

    # 4. Image file (PNG)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02"
        b"\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    parsed_img = parse_document(png_bytes, "bol_scan.png")
    assert parsed_img.extraction_method == "vision_default"
    assert parsed_img.mime_type == "image/png"
    assert parsed_img.raw_text is None
    assert len(parsed_img.page_images) == 1
    assert parsed_img.page_images[0] == png_bytes


def test_extractor_structured_output_mock_mode():
    """Verify ExtractorAgent in mock_mode extracts all 8 required trade fields and captures telemetry."""
    invoice_text = (
        "COMMERCIAL INVOICE\n"
        "Invoice Number: INV-2026-001\n"
        "Consignee: Meridian Robotics Inc.\n"
        "Port of Loading: CNSHA Shanghai Port\n"
        "Port of Discharge: USLAX Los Angeles Port\n"
        "Incoterm: FOB\n"
        "Description of Goods: Industrial Robotic Arms\n"
        "Gross Weight: 12,500 KG\n"
        "HS Code: 8479.50.00"
    )
    pdf_bytes = create_sample_pdf(invoice_text)

    agent = ExtractorAgent(mock_mode=True)
    extracted_doc, trace = agent.extract(pdf_bytes, "invoice.pdf", document_id="doc_test_123")

    # Verify structured payload adherence
    assert isinstance(extracted_doc, ExtractedDoc)
    assert extracted_doc.consignee.value == "Meridian Robotics Inc."
    assert extracted_doc.hs_code.value == "8479.50"
    assert extracted_doc.pol.value == "CNSHA"
    assert extracted_doc.pod.value == "USLAX"
    assert extracted_doc.incoterm.value == "FOB"
    assert extracted_doc.description.value == "Robotic Arms"
    assert extracted_doc.gross_weight.value == "12500 KG"
    assert extracted_doc.invoice_number.value == "INV-2026-001"
    assert extracted_doc.extraction_method == "text_layer"

    # Verify telemetry in RunTrace
    assert isinstance(trace, RunTrace)
    assert trace.document_id == "doc_test_123"
    assert trace.node_name == "extractor"
    assert trace.status == "SUCCESS"
    assert trace.latency_ms > 0
    assert trace.prompt_tokens == 450
    assert trace.completion_tokens == 180
    assert trace.thinking_tokens == 60
    assert trace.cost_usd > 0.0


def test_extractor_structured_output_mock_client():
    """Verify ExtractorAgent parses LLM response with real client interface mock."""
    sample_payload = {
        "consignee": {"value": "Acme Global Trading", "confidence": 0.96, "source_quote": "Acme Global Trading"},
        "hs_code": {"value": "8504.40", "confidence": 0.91, "source_quote": "8504.40"},
        "pol": {"value": "SGSIN", "confidence": 0.95, "source_quote": "Port of Loading: SGSIN"},
        "pod": {"value": "NLRTM", "confidence": 0.94, "source_quote": "Port of Discharge: NLRTM"},
        "incoterm": {"value": "CIF", "confidence": 0.99, "source_quote": "Incoterms 2020: CIF"},
        "description": {"value": "Power Converters", "confidence": 0.92, "source_quote": "Static Power Converters"},
        "gross_weight": {"value": "5400 KG", "confidence": 0.97, "source_quote": "GW: 5400 KG"},
        "invoice_number": {"value": "EXP-9921", "confidence": 0.99, "source_quote": "Invoice No: EXP-9921"},
        "transcription": None
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(sample_payload)
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 600
    mock_usage.candidates_token_count = 200
    mock_usage.thoughts_token_count = 100
    mock_response.usage_metadata = mock_usage

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    doc_text = (
        "COMMERCIAL INVOICE\n"
        "Consignee: Acme Global Trading\n"
        "HS Code: 8504.40\n"
        "Port of Loading: SGSIN\n"
        "Port of Discharge: NLRTM\n"
        "Incoterms 2020: CIF\n"
        "Description: Static Power Converters\n"
        "GW: 5400 KG\n"
        "Invoice No: EXP-9921\n"
    )
    pdf_bytes = create_sample_pdf(doc_text)

    agent = ExtractorAgent(client=mock_client, model_name="gemini-3.8-flash")
    extracted_doc, trace = agent.extract(pdf_bytes, "test_doc.pdf")

    assert extracted_doc.consignee.value == "Acme Global Trading"
    assert extracted_doc.incoterm.value == "CIF"
    assert extracted_doc.hs_code.value == "8504.40"
    assert trace.status == "SUCCESS"
    assert trace.prompt_tokens == 600
    assert trace.completion_tokens == 200
    assert trace.thinking_tokens == 100
    # Cost = (600 * 0.75 + (200 + 100) * 3.75) / 1M = (450 + 1125) / 1M = 0.001575 USD
    assert abs(trace.cost_usd - 0.001575) < 1e-6


def test_extractor_error_handling():
    """Verify ExtractorAgent catches failures, sanitizes errors, and attaches failed trace."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("API key key=AIzaSyD-SecretKey-123 expired")

    doc_text = "Sample commercial document content for error test."
    pdf_bytes = create_sample_pdf(doc_text * 3)

    agent = ExtractorAgent(client=mock_client)
    with pytest.raises(RuntimeError) as exc_info:
        agent.extract(pdf_bytes, "error.pdf")

    err = exc_info.value
    assert hasattr(err, "trace")
    failed_trace: RunTrace = err.trace
    assert failed_trace.status == "FAILED"
    assert failed_trace.node_name == "extractor"
    # Ensure key was sanitized
    assert "AIzaSyD-SecretKey-123" not in failed_trace.error_message
    assert "[REDACTED]" in failed_trace.error_message
