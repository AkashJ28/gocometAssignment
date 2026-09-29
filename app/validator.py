"""Deterministic rule-based Validator Agent for GoComet Nova DAW trade documents."""

import difflib
import re
from typing import Dict, List, Optional

from app.schemas import (
    ConsigneeRule,
    CustomerRules,
    Discrepancy,
    ExtractedDoc,
    ExtractedField,
    FieldValidation,
    HSCodeRule,
    PortRule,
    ValidationResult,
    ValidationStatus,
    WeightToleranceRule,
    load_customer_rules,
)


def _normalize_text(text: str) -> str:
    """Normalize string by removing punctuation, lowercasing, and normalizing whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def check_field_grounding_and_confidence(
    field: ExtractedField, min_confidence: float, field_name: str = "field"
) -> Optional[FieldValidation]:
    """Ensure field is grounded, non-null, and confident; returns UNCERTAIN if invariant fails."""
    if not field.is_grounded or not field.source_quote or not field.source_quote.strip():
        return FieldValidation(
            field_name=field_name,
            status=ValidationStatus.UNCERTAIN,
            expected="Grounded quote from source document",
            found=field.value,
            reason="Field ungrounded: quote not verified in source document",
        )

    if field.value is None or not field.value.strip():
        return FieldValidation(
            field_name=field_name,
            status=ValidationStatus.UNCERTAIN,
            expected="Non-empty field value",
            found=None,
            reason="Field missing or null in extracted document",
        )

    if field.confidence < min_confidence:
        return FieldValidation(
            field_name=field_name,
            status=ValidationStatus.UNCERTAIN,
            expected=f"Confidence >= {min_confidence:.2f}",
            found=field.value,
            reason=f"Field confidence {field.confidence:.2f} below auto-approval threshold {min_confidence:.2f}",
        )

    return None


def validate_consignee(
    field: ExtractedField, rule: ConsigneeRule, min_confidence: float
) -> FieldValidation:
    """Validate consignee against primary name and aliases with exact and fuzzy matching."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name="consignee"
    )
    if invariant_check is not None:
        return invariant_check

    norm_found = _normalize_text(field.value)  # type: ignore[arg-type]
    norm_primary = _normalize_text(rule.primary_name)
    norm_aliases = [_normalize_text(alias) for alias in rule.aliases]

    # Exact match check against primary or aliases
    if norm_found == norm_primary or norm_found in norm_aliases:
        return FieldValidation(
            field_name="consignee",
            status=ValidationStatus.MATCH,
            expected=rule.primary_name,
            found=field.value,
            reason="Exact match with customer primary name or approved alias",
        )

    # Fuzzy matching using SequenceMatcher
    targets = [norm_primary] + norm_aliases
    ratios = [
        difflib.SequenceMatcher(None, norm_found, target).ratio()
        for target in targets
    ]
    max_ratio = max(ratios) if ratios else 0.0

    if max_ratio >= rule.min_fuzzy_threshold:
        return FieldValidation(
            field_name="consignee",
            status=ValidationStatus.MATCH,
            expected=rule.primary_name,
            found=field.value,
            reason=f"Fuzzy match similarity {max_ratio:.2f} >= threshold {rule.min_fuzzy_threshold:.2f}",
        )
    elif max_ratio >= 0.65:
        return FieldValidation(
            field_name="consignee",
            status=ValidationStatus.UNCERTAIN,
            expected=rule.primary_name,
            found=field.value,
            reason=f"Ambiguous consignee variation (similarity {max_ratio:.2f}); manual review required",
        )
    else:
        return FieldValidation(
            field_name="consignee",
            status=ValidationStatus.MISMATCH,
            expected=rule.primary_name,
            found=field.value,
            reason=f"Consignee mismatch (similarity {max_ratio:.2f} < threshold)",
        )


def validate_hs_code(
    field: ExtractedField, allowed_rules: List[HSCodeRule], min_confidence: float
) -> FieldValidation:
    """Validate HS code by comparing normalized digits against customer approved classifications."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name="hs_code"
    )
    if invariant_check is not None:
        return invariant_check

    raw_found = field.value or ""
    # Strip dots, spaces, hyphens
    norm_found = re.sub(r"[\s.\-]", "", raw_found)

    expected_codes_str = ", ".join(r.code for r in allowed_rules)

    for rule in allowed_rules:
        norm_rule_code = re.sub(r"[\s.\-]", "", rule.code)
        # Check prefix match (e.g., 6 digits) or full normalized match
        match_len = min(len(norm_rule_code), len(norm_found))
        if match_len >= 4 and norm_found[:match_len] == norm_rule_code[:match_len]:
            return FieldValidation(
                field_name="hs_code",
                status=ValidationStatus.MATCH,
                expected=expected_codes_str,
                found=field.value,
                reason=f"HS code {field.value} matches approved tariff classification ({rule.code})",
            )

    return FieldValidation(
        field_name="hs_code",
        status=ValidationStatus.MISMATCH,
        expected=expected_codes_str,
        found=field.value,
        reason=f"HS code {field.value} is not in customer approved list",
    )


def validate_incoterm(
    field: ExtractedField, allowed_incoterms: List[str], min_confidence: float
) -> FieldValidation:
    """Validate Incoterm against allowed list."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name="incoterm"
    )
    if invariant_check is not None:
        return invariant_check

    val_upper = (field.value or "").strip().upper()
    allowed_upper = [term.strip().upper() for term in allowed_incoterms]

    if val_upper in allowed_upper:
        return FieldValidation(
            field_name="incoterm",
            status=ValidationStatus.MATCH,
            expected=", ".join(allowed_incoterms),
            found=field.value,
            reason=f"Incoterm {field.value} matches approved term",
        )

    return FieldValidation(
        field_name="incoterm",
        status=ValidationStatus.MISMATCH,
        expected=", ".join(allowed_incoterms),
        found=field.value,
        reason=f"Incoterm {field.value} is not in customer approved list",
    )


def validate_port(
    field: ExtractedField, port_rule: PortRule, port_type: str, min_confidence: float
) -> FieldValidation:
    """Validate port of loading/discharge against allowed LOCODEs and names."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name=port_type
    )
    if invariant_check is not None:
        return invariant_check

    val_upper = (field.value or "").strip().upper()
    allowed_locodes = [loc.strip().upper() for loc in port_rule.allowed_locodes]
    allowed_names = [name.strip().upper() for name in port_rule.allowed_names]

    matched = False
    for loc in allowed_locodes:
        if loc in val_upper:
            matched = True
            break

    if not matched:
        for name in allowed_names:
            if name in val_upper or val_upper in name:
                matched = True
                break

    expected_summary = (
        f"Allowed LOCODEs: {', '.join(port_rule.allowed_locodes)} / Names: {', '.join(port_rule.allowed_names)}"
    )

    if matched:
        return FieldValidation(
            field_name=port_type,
            status=ValidationStatus.MATCH,
            expected=expected_summary,
            found=field.value,
            reason=f"{port_type.upper()} '{field.value}' matches approved customer port",
        )

    return FieldValidation(
        field_name=port_type,
        status=ValidationStatus.MISMATCH,
        expected=expected_summary,
        found=field.value,
        reason=f"{port_type.upper()} '{field.value}' is not in customer approved port list",
    )


def validate_gross_weight(
    field: ExtractedField, weight_rule: WeightToleranceRule, min_confidence: float
) -> FieldValidation:
    """Validate gross weight with regex parsing, unit conversion (LBS -> KG), and limit check."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name="gross_weight"
    )
    if invariant_check is not None:
        return invariant_check

    raw_val = field.value or ""
    # Safe regex to parse numeric weight and optional unit
    match = re.search(r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?)\s*([A-Za-z]+)?", raw_val)
    if not match:
        return FieldValidation(
            field_name="gross_weight",
            status=ValidationStatus.UNCERTAIN,
            expected=f"Numeric weight <= {weight_rule.max_limit_kg} KG",
            found=field.value,
            reason=f"Could not parse numeric gross weight from '{field.value}'",
        )

    try:
        numeric_str = match.group(1).replace(",", "")
        weight_val = float(numeric_str)
        unit = (match.group(2) or "KG").strip().upper()

        if unit in ("LBS", "LB"):
            weight_kg = weight_val * 0.45359237
        elif unit in ("MT", "TON", "TONS"):
            weight_kg = weight_val * 1000.0
        else:
            weight_kg = weight_val

    except (ValueError, TypeError):
        return FieldValidation(
            field_name="gross_weight",
            status=ValidationStatus.UNCERTAIN,
            expected=f"Numeric weight <= {weight_rule.max_limit_kg} KG",
            found=field.value,
            reason=f"Failed numeric conversion for gross weight '{field.value}'",
        )

    expected_limit = f"<= {weight_rule.max_limit_kg} KG"

    if weight_kg <= weight_rule.max_limit_kg:
        return FieldValidation(
            field_name="gross_weight",
            status=ValidationStatus.MATCH,
            expected=expected_limit,
            found=field.value,
            reason=f"Gross weight {weight_kg:.2f} KG is within allowable limit ({weight_rule.max_limit_kg} KG)",
        )

    return FieldValidation(
        field_name="gross_weight",
        status=ValidationStatus.MISMATCH,
        expected=expected_limit,
        found=field.value,
        reason=f"Gross weight {weight_kg:.2f} KG exceeds customer max limit of {weight_rule.max_limit_kg} KG",
    )


def validate_informational_field(
    field: ExtractedField, field_name: str, min_confidence: float
) -> FieldValidation:
    """Validate descriptive and identification fields that require presence, grounding, and confidence."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name=field_name
    )
    if invariant_check is not None:
        return invariant_check

    return FieldValidation(
        field_name=field_name,
        status=ValidationStatus.MATCH,
        expected="Non-empty grounded field",
        found=field.value,
        reason=f"Field {field_name} is grounded and confident",
    )


class ValidatorAgent:
    """Deterministic, rule-based verification agent for trade documents."""

    def __init__(
        self,
        rules: Optional[CustomerRules] = None,
        rules_path: str = "config/customer_rules.yaml",
    ):
        if rules is not None:
            self.rules = rules
        else:
            self.rules = load_customer_rules(rules_path)

    def validate(self, extracted_doc: ExtractedDoc) -> ValidationResult:
        """Run all deterministic compliance rules against extracted document fields."""
        min_conf = self.rules.validation_thresholds.min_confidence_auto_approve

        field_validations: Dict[str, FieldValidation] = {
            "consignee": validate_consignee(
                extracted_doc.consignee, self.rules.consignee, min_conf
            ),
            "hs_code": validate_hs_code(
                extracted_doc.hs_code, self.rules.allowed_hs_codes, min_conf
            ),
            "pol": validate_port(extracted_doc.pol, self.rules.ports.pol, "pol", min_conf),
            "pod": validate_port(extracted_doc.pod, self.rules.ports.pod, "pod", min_conf),
            "incoterm": validate_incoterm(
                extracted_doc.incoterm, self.rules.allowed_incoterms, min_conf
            ),
            "gross_weight": validate_gross_weight(
                extracted_doc.gross_weight, self.rules.weight_tolerance, min_conf
            ),
            "description": validate_informational_field(
                extracted_doc.description, "description", min_conf
            ),
            "invoice_number": validate_informational_field(
                extracted_doc.invoice_number, "invoice_number", min_conf
            ),
        }

        # Itemize discrepancies for any MISMATCH
        discrepancies: List[Discrepancy] = []
        for fv in field_validations.values():
            if fv.status == ValidationStatus.MISMATCH:
                discrepancies.append(
                    Discrepancy(
                        field_name=fv.field_name,
                        expected=fv.expected or "Valid rule requirement",
                        found=fv.found or "Unknown",
                        severity="critical",
                    )
                )

        # Strict overall status computation:
        # Zero silent approvals: Any discrepancy/mismatch -> MISMATCH
        # Else Any uncertain -> UNCERTAIN
        # Only when all 8 match -> MATCH
        if len(discrepancies) > 0 or any(
            fv.status == ValidationStatus.MISMATCH for fv in field_validations.values()
        ):
            overall_status = ValidationStatus.MISMATCH
        elif any(
            fv.status == ValidationStatus.UNCERTAIN for fv in field_validations.values()
        ):
            overall_status = ValidationStatus.UNCERTAIN
        else:
            overall_status = ValidationStatus.MATCH

        return ValidationResult(
            overall_status=overall_status,
            field_validations=field_validations,
            discrepancies=discrepancies,
        )
