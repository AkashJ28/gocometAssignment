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


def value_supported_by_quote(
    field_name: str,
    value: Optional[str],
    quote: Optional[str],
) -> bool:
    """Verify that the extracted value is actually supported by the source quote."""
    if not value or not value.strip():
        return False
    if not quote or not quote.strip():
        return False

    val_str = value.strip()
    quote_str = quote.strip()

    if field_name == "hs_code":
        val_digits = re.sub(r"\D", "", val_str)
        quote_digits = re.sub(r"\D", "", quote_str)
        if not val_digits or not quote_digits:
            return False
        return val_digits in quote_digits or (
            len(val_digits) >= 6 and quote_digits.startswith(val_digits[:6])
        )

    if field_name == "gross_weight":
        val_num_match = re.search(r"[\d]+(?:[.,]\d+)?", val_str.replace(",", ""))
        if not val_num_match:
            return False
        val_num = val_num_match.group(0)
        val_int = val_num.split(".")[0]
        quote_clean = quote_str.replace(",", "")
        return val_int in quote_clean

    if field_name == "incoterm":
        val_upper = val_str.upper()
        pattern = r"\b" + re.escape(val_upper) + r"\b"
        return bool(re.search(pattern, quote_str.upper()))

    if field_name in ("pol", "pod"):
        val_clean = val_str.upper()
        if UN_LOCODE_REGEX.match(val_clean):
            return val_clean in quote_str.upper()
        val_tokens = re.findall(r"\w+", val_str.lower())
        quote_lower = quote_str.lower()
        if not val_tokens:
            return False
        return all(t in quote_lower for t in val_tokens if len(t) > 2)

    if field_name == "invoice_number":
        norm_val = re.sub(r"[^\w]", "", val_str).lower()
        norm_quote = re.sub(r"[^\w]", "", quote_str).lower()
        return norm_val in norm_quote

    if field_name in ("consignee", "description"):
        if normalize_text(val_str).lower() in normalize_text(quote_str).lower():
            return True
        val_tokens = re.findall(r"\w+", val_str.lower())
        meaningful_tokens = [t for t in val_tokens if len(t) > 2]
        if not meaningful_tokens:
            return True
        quote_lower = quote_str.lower()
        matching_tokens = [t for t in meaningful_tokens if t in quote_lower]
        return len(matching_tokens) / len(meaningful_tokens) >= 0.7

    return normalize_text(val_str).lower() in normalize_text(quote_str).lower()


def calibrate_confidence(
    field_name: str,
    raw_value: Optional[str],
    raw_confidence: float,
    is_grounded: bool,
) -> float:
    """Calibrate confidence score using grounding and domain syntax checks.
    Ungrounded -> 0.0
    Grounded but invalid domain syntax -> min(raw * 0.5, 0.45) (guarantees human review)
    Grounded with valid syntax -> min(round(raw_confidence, 2), 1.0) (strictly non-inflating)
    """
    if not is_grounded:
        return 0.0

    is_valid_syntax = validate_domain_syntax(field_name, raw_value)
    if not is_valid_syntax:
        return min(round(raw_confidence * 0.5, 2), 0.45)

    # Strictly non-inflating: can lower or preserve confidence, never raise it.
    return min(round(raw_confidence, 2), 1.0)


def ground_field(
    field_name: str,
    value: Optional[str],
    confidence: float,
    source_quote: Optional[str],
    raw_text: Optional[str],
    grounding_source: str = "text_layer",
) -> ExtractedField:
    """Ground and calibrate a single trade field."""
    quote_in_doc = verify_source_quote(source_quote, raw_text)
    value_in_quote = value_supported_by_quote(field_name, value, source_quote)
    is_grounded = quote_in_doc and value_in_quote
    calibrated_conf = calibrate_confidence(field_name, value, confidence, is_grounded)
    if grounding_source == "vision_unverified" and calibrated_conf > 0.60:
        calibrated_conf = 0.60
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
    grounding_source: Literal["text_layer", "ocr", "vision_unverified"] = "text_layer",
    grounding_note: Optional[str] = None,
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
        field = ground_field(
            field_name=name,
            value=raw_field.value,
            confidence=raw_field.confidence,
            source_quote=raw_field.source_quote,
            raw_text=raw_text,
        )
        # For unverified vision scans without independent text/OCR, cap confidence at 0.60 (Zero Silent Approvals A2)
        if grounding_source == "vision_unverified" and field.confidence > 0.60:
            field.confidence = 0.60
        field_kwargs[name] = field

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
        grounding_source=grounding_source,
        grounding_note=grounding_note,
        raw_text=raw_text,
    )
