"""Grounding and confidence calibration engine enforcing zero silent approvals."""

import re
from typing import Any, Literal, Optional
from app.schemas import ExtractedDoc, ExtractedField

# Standard Incoterms 2020 (plus legacy DAT recognized in trade)
STANDARD_INCOTERMS = {
    "EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP", "DAT"
}

# Regex patterns for domain syntax validation
HS_CODE_REGEX = re.compile(r"^\d{4}\.\d{2}(\.\d{2})?$|^\d{6,10}$")
UN_LOCODE_REGEX = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}$")
GROSS_WEIGHT_REGEX = re.compile(r"^[\d\s,.]+\s*(?:KG|KGS|LBS|LB|MT|TONS?)$", re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Collapse consecutive whitespace into single spaces and strip outer whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def verify_source_quote(quote: Optional[str], raw_text: Optional[str]) -> bool:
    """Verify source quote against raw document text using 3-tier hierarchy:
    Tier 1: Exact substring match.
    Tier 2: Normalized whitespace match.
    Tier 3: Case-insensitive normalized whitespace match.
    """
    if not quote or not quote.strip():
        return False
    if not raw_text or not raw_text.strip():
        return False

    # Tier 1: Exact substring match
    if quote in raw_text:
        return True

    # Tier 2: Normalized whitespace match
    norm_quote = normalize_text(quote)
    norm_raw = normalize_text(raw_text)
    if norm_quote in norm_raw:
        return True

    # Tier 3: Case-insensitive normalized match
    if norm_quote.lower() in norm_raw.lower():
        return True

    return False


def validate_domain_syntax(field_name: str, value: Optional[str]) -> bool:
    """Validate domain syntax of extracted trade field values."""
    if value is None:
        return False

    cleaned = value.strip()
    if not cleaned:
        return False

    if field_name == "hs_code":
        return bool(HS_CODE_REGEX.match(cleaned))

    if field_name in ("pol", "pod"):
        # Valid if matches 5-char UN/LOCODE or reasonable port name string (>= 3 chars)
        if UN_LOCODE_REGEX.match(cleaned.upper()):
            return True
        return len(cleaned) >= 3 and any(c.isalpha() for c in cleaned)

    if field_name == "incoterm":
        return cleaned.upper() in STANDARD_INCOTERMS

    if field_name == "gross_weight":
        return bool(GROSS_WEIGHT_REGEX.match(cleaned))

    if field_name in ("consignee", "description", "invoice_number"):
        return len(cleaned) >= 2

    return True


def calibrate_confidence(
    field_name: str,
    raw_value: Optional[str],
    raw_confidence: float,
    is_grounded: bool,
) -> float:
    """Calibrate confidence score using grounding and domain syntax checks.
    Ungrounded -> 0.0
    Grounded but invalid domain syntax -> min(raw * 0.5, 0.45) (guarantees human review)
    Grounded with valid syntax -> min(round(0.75 * raw + 0.25, 2), 1.0)
    """
    if not is_grounded:
        return 0.0

    is_valid_syntax = validate_domain_syntax(field_name, raw_value)
    if not is_valid_syntax:
        return min(round(raw_confidence * 0.5, 2), 0.45)

    return min(round(0.75 * raw_confidence + 0.25, 2), 1.0)


def ground_field(
    field_name: str,
    value: Optional[str],
    confidence: float,
    source_quote: Optional[str],
    raw_text: Optional[str],
) -> ExtractedField:
    """Ground and calibrate a single trade field."""
    is_grounded = verify_source_quote(source_quote, raw_text)
    calibrated_conf = calibrate_confidence(field_name, value, confidence, is_grounded)
    return ExtractedField(
        value=value if is_grounded else None,
        confidence=calibrated_conf,
        source_quote=source_quote,
        is_grounded=is_grounded,
    )


def ground_and_calibrate_document(
    payload: Any,
    raw_text: Optional[str],
    extraction_method: Literal["text_layer", "vision_default", "vision_fallback"],
) -> ExtractedDoc:
    """Transform candidate extraction payload into grounded and calibrated ExtractedDoc."""
    field_names = [
        "consignee",
        "hs_code",
        "pol",
        "pod",
        "incoterm",
        "description",
        "gross_weight",
        "invoice_number",
    ]

    field_kwargs = {}
    for name in field_names:
        raw_field = getattr(payload, name)
        field_kwargs[name] = ground_field(
            field_name=name,
            value=raw_field.value,
            confidence=raw_field.confidence,
            source_quote=raw_field.source_quote,
            raw_text=raw_text,
        )

    return ExtractedDoc(
        consignee=field_kwargs["consignee"],
        hs_code=field_kwargs["hs_code"],
        pol=field_kwargs["pol"],
        pod=field_kwargs["pod"],
        incoterm=field_kwargs["incoterm"],
        description=field_kwargs["description"],
        gross_weight=field_kwargs["gross_weight"],
        invoice_number=field_kwargs["invoice_number"],
        extraction_method=extraction_method,
        raw_text=raw_text,
    )
