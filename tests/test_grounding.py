"""Unit and integration tests for code-level quote grounding and confidence calibrator."""

import pytest
from app.extractor import ExtractorAgent, DocumentExtractionPayload, RawFieldExtraction
from app.grounding import (
    normalize_text,
    verify_source_quote,
    validate_domain_syntax,
    calibrate_confidence,
    ground_field,
    ground_and_calibrate_document,
)
from app.schemas import ExtractedDoc, ExtractedField


def test_grounding_quote_verification():
    """Verify 3-tier hierarchy quote matching and hallucination rejection."""
    doc_text = (
        "COMMERCIAL INVOICE\n"
        "Shipper: Global Automation Ltd, 50 Tech Park, Shenzhen, China\n"
        "Consignee: Meridian Robotics Inc.\n"
        "100 Technology Way, San Jose, CA\n"
        "Port of Loading: CNSHA Shanghai Port\n"
        "Port of Discharge: USLAX Los Angeles Port\n"
        "Incoterm: FOB Shanghai\n"
        "Description of Goods: Industrial Robotic Arms and Controllers\n"
        "Gross Weight: 12,500 KG\n"
        "HS Code: 8479.50.00\n"
        "Invoice No: INV-2026-9901"
    )

    # 1. Tier 1: Exact substring match
    assert verify_source_quote("Meridian Robotics Inc.", doc_text) is True
    assert verify_source_quote("8479.50.00", doc_text) is True

    # 2. Tier 2: Normalized whitespace & multi-line matching
    # Newlines within the quote or doc text
    assert verify_source_quote("Meridian Robotics Inc. 100 Technology Way", doc_text) is True
    # Extra internal spaces / tabs
    assert verify_source_quote("Consignee:   Meridian   Robotics  Inc.", doc_text) is True

    # 3. Tier 3: Case-insensitive normalized match
    assert verify_source_quote("fob shanghai", doc_text) is True
    assert verify_source_quote("industrial robotic arms", doc_text) is True

    # 4. Hallucinated quotes not present in doc text
    assert verify_source_quote("Acme Supplies Corp", doc_text) is False
    assert verify_source_quote("DDP Los Angeles", doc_text) is False

    # 5. Empty / None quote handling
    assert verify_source_quote(None, doc_text) is False
    assert verify_source_quote("", doc_text) is False
    assert verify_source_quote("   ", doc_text) is False
    assert verify_source_quote("Meridian", None) is False
    assert verify_source_quote("Meridian", "") is False


def test_ground_field_zero_silent_approval():
    """Verify that ungrounded fields coerce value to None and confidence to 0.0."""
    raw_doc = "Consignee: Meridian Robotics Inc. Incoterm: FOB"

    # Valid grounded field
    field_grounded = ground_field(
        field_name="consignee",
        value="Meridian Robotics Inc.",
        confidence=0.90,
        source_quote="Meridian Robotics Inc.",
        raw_text=raw_doc,
    )
    assert field_grounded.is_grounded is True
    assert field_grounded.value == "Meridian Robotics Inc."
    assert field_grounded.confidence >= 0.85

    # Hallucinated ungrounded field (Zero silent approval invariant)
    field_hallucinated = ground_field(
        field_name="consignee",
        value="Phantom Corporation",
        confidence=0.99,  # High LLM confidence must be discarded!
        source_quote="Phantom Corporation",
        raw_text=raw_doc,
    )
    assert field_hallucinated.is_grounded is False
    assert field_hallucinated.value is None
    assert field_hallucinated.confidence == 0.0

    # Missing quote
    field_no_quote = ground_field(
        field_name="incoterm",
        value="FOB",
        confidence=0.95,
        source_quote=None,
        raw_text=raw_doc,
    )
    assert field_no_quote.is_grounded is False
    assert field_no_quote.value is None
    assert field_no_quote.confidence == 0.0


def test_domain_syntax_validation():
    """Verify domain syntax rules for all trade fields."""
    # HS Code: 6-10 digits, optional dot formatting
    assert validate_domain_syntax("hs_code", "8479.50") is True
    assert validate_domain_syntax("hs_code", "8479.50.00") is True
    assert validate_domain_syntax("hs_code", "847950") is True
    assert validate_domain_syntax("hs_code", "8479.X") is False
    assert validate_domain_syntax("hs_code", "INVALID") is False

    # Ports: UN/LOCODE or >= 3 chars
    assert validate_domain_syntax("pol", "CNSHA") is True
    assert validate_domain_syntax("pol", "Shanghai Port") is True
    assert validate_domain_syntax("pod", "USLAX") is True
    assert validate_domain_syntax("pod", "NO") is False

    # Incoterms: Standard 11 (plus DAT)
    assert validate_domain_syntax("incoterm", "FOB") is True
    assert validate_domain_syntax("incoterm", "cif") is True
    assert validate_domain_syntax("incoterm", "DAP") is True
    assert validate_domain_syntax("incoterm", "XYZ") is False
    assert validate_domain_syntax("incoterm", "FREE") is False

    # Gross weight: numeric with valid units (KG, LBS, MT, etc.)
    assert validate_domain_syntax("gross_weight", "12500 KG") is True
    assert validate_domain_syntax("gross_weight", "12,500.50 KGS") is True
    assert validate_domain_syntax("gross_weight", "500 LBS") is True
    assert validate_domain_syntax("gross_weight", "Heavy") is False
    assert validate_domain_syntax("gross_weight", "12500") is False


def test_confidence_calibration():
    """Verify multi-signal confidence calibrator discounts defective syntax to <= 0.45."""
    # 1. Grounded + Valid Syntax -> Boosted confidence
    # 0.75 * 0.90 + 0.25 = 0.925 -> 0.93
    conf_valid = calibrate_confidence("hs_code", "8479.50", 0.90, is_grounded=True)
    assert conf_valid >= 0.85
    assert conf_valid == 0.93

    # 2. Grounded + Defective Syntax -> Discounted to <= 0.45
    # Malformed HS code 8479.X with raw confidence 0.90 -> min(round(0.90 * 0.5, 2), 0.45) = 0.45
    conf_bad_syntax = calibrate_confidence("hs_code", "8479.X", 0.90, is_grounded=True)
    assert conf_bad_syntax <= 0.45
    assert conf_bad_syntax == 0.45

    # Invalid Incoterm with raw confidence 0.80 -> min(0.40, 0.45) = 0.40
    conf_bad_incoterm = calibrate_confidence("incoterm", "UNKNOWN", 0.80, is_grounded=True)
    assert conf_bad_incoterm <= 0.45
    assert conf_bad_incoterm == 0.40

    # 3. Ungrounded -> Strictly 0.0
    conf_ungrounded = calibrate_confidence("consignee", "Meridian", 0.99, is_grounded=False)
    assert conf_ungrounded == 0.0


def test_ground_and_calibrate_document():
    """Verify full document payload transformation and hallucination coercion."""
    raw_doc = (
        "COMMERCIAL INVOICE\n"
        "Consignee: Meridian Robotics Inc.\n"
        "HS Code: 8479.50.00\n"
        "POL: CNSHA\n"
        "POD: USLAX\n"
        "Incoterm: FOB\n"
        "Description: Robotic Arms\n"
        "Gross Weight: 12500 KG\n"
        "Invoice: INV-2026-001\n"
    )

    payload = DocumentExtractionPayload(
        consignee=RawFieldExtraction(value="Meridian Robotics Inc.", confidence=0.90, source_quote="Meridian Robotics Inc."),
        hs_code=RawFieldExtraction(value="8479.50.00", confidence=0.90, source_quote="8479.50.00"),
        pol=RawFieldExtraction(value="CNSHA", confidence=0.90, source_quote="POL: CNSHA"),
        pod=RawFieldExtraction(value="USLAX", confidence=0.90, source_quote="POD: USLAX"),
        incoterm=RawFieldExtraction(value="FOB", confidence=0.90, source_quote="Incoterm: FOB"),
        description=RawFieldExtraction(value="Robotic Arms", confidence=0.90, source_quote="Robotic Arms"),
        gross_weight=RawFieldExtraction(value="12500 KG", confidence=0.90, source_quote="12500 KG"),
        # Hallucinated invoice number! Not present in document
        invoice_number=RawFieldExtraction(value="INV-9999-FAKE", confidence=0.95, source_quote="INV-9999-FAKE"),
        transcription=raw_doc,
    )

    extracted_doc = ground_and_calibrate_document(payload, raw_doc, "text_layer")

    assert extracted_doc.consignee.is_grounded is True
    assert extracted_doc.consignee.value == "Meridian Robotics Inc."
    assert extracted_doc.consignee.confidence >= 0.85

    # Hallucinated field must be ungrounded, value coerced to None, confidence 0.0
    assert extracted_doc.invoice_number.is_grounded is False
    assert extracted_doc.invoice_number.value is None
    assert extracted_doc.invoice_number.confidence == 0.0
