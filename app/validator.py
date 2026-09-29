"""Deterministic rule-based Validator Agent for GoComet Nova DAW trade documents."""

import difflib
import re
from typing import Dict, List, Optional, Union

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


LEGAL_FORMS = {
    "inc": "inc",
    "incorporated": "inc",
    "corp": "corp",
    "corporation": "corp",
    "ltd": "ltd",
    "limited": "ltd",
    "llc": "llc",
    "gmbh": "gmbh",
    "pvt ltd": "ltd",
    "private limited": "ltd",
    "sa": "sa",
    "bv": "bv",
    "plc": "plc",
    "co": "corp",
    "company": "corp",
}


def extract_legal_form(name: str) -> Optional[str]:
    """Extract canonical legal form suffix from an organization name."""
    norm = _normalize_text(name)
    for phrase in ["private limited", "pvt ltd"]:
        if norm.endswith(phrase):
            return "ltd"
    tokens = norm.split()
    if not tokens:
        return None
    return LEGAL_FORMS.get(tokens[-1])


def validate_consignee(
    field: ExtractedField, rule: ConsigneeRule, min_confidence: float
) -> FieldValidation:
    """Validate consignee against primary name and aliases with exact, legal form, and fuzzy matching."""
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

    # Check for conflicting legal form (e.g. Ltd vs Inc)
    found_legal = extract_legal_form(field.value)  # type: ignore[arg-type]
    primary_legal = extract_legal_form(rule.primary_name)
    alias_legals = {extract_legal_form(a) for a in rule.aliases if extract_legal_form(a)}
    allowed_legals = ({primary_legal} if primary_legal else set()) | alias_legals

    if found_legal and allowed_legals and found_legal not in allowed_legals:
        return FieldValidation(
            field_name="consignee",
            status=ValidationStatus.MISMATCH,
            expected=rule.primary_name,
            found=field.value,
            reason=(
                f"Conflicting legal entity form: '{found_legal.upper()}' is not an approved entity form "
                f"(expected {', '.join(sorted(l.upper() for l in allowed_legals))})"
            ),
        )

    # Fuzzy matching using SequenceMatcher
    targets = [norm_primary] + norm_aliases
    ratios = [
        difflib.SequenceMatcher(None, norm_found, target).ratio()
        for target in targets
    ]
    max_ratio = max(ratios) if ratios else 0.0

    if max_ratio >= rule.min_fuzzy_threshold:
        if getattr(rule, "allow_fuzzy_auto_approve", False):
            return FieldValidation(
                field_name="consignee",
                status=ValidationStatus.MATCH,
                expected=rule.primary_name,
                found=field.value,
                reason=f"Fuzzy match similarity {max_ratio:.2f} >= threshold {rule.min_fuzzy_threshold:.2f}",
            )
        else:
            return FieldValidation(
                field_name="consignee",
                status=ValidationStatus.UNCERTAIN,
                expected=rule.primary_name,
                found=field.value,
                reason=f"Consignee spelling variation detected (similarity {max_ratio:.2f}); operator review required",
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
    field: ExtractedField, allowed_rules: Union[HSCodeRule, List[HSCodeRule]], min_confidence: float
) -> FieldValidation:
    """Validate HS code by comparing normalized digits against customer approved classifications."""
    if isinstance(allowed_rules, HSCodeRule):
        allowed_rules = [allowed_rules]

    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name="hs_code"
    )
    if invariant_check is not None:
        return invariant_check

    raw_found = field.value or ""
    norm_found = re.sub(r"\D", "", raw_found)

    expected_codes_str = ", ".join(r.code for r in allowed_rules)

    # Require at least 6 digits for subheading classification
    if len(norm_found) < 6:
        return FieldValidation(
            field_name="hs_code",
            status=ValidationStatus.UNCERTAIN,
            expected=expected_codes_str,
            found=field.value,
            reason=f"HS code '{field.value}' has fewer than 6 digits; tariff subheading cannot be verified",
        )

    for rule in allowed_rules:
        norm_rule_code = re.sub(r"\D", "", rule.code)
        # Subheading (first 6 digits) must match exactly
        if len(norm_rule_code) >= 6:
            if norm_found[:6] == norm_rule_code[:6]:
                if len(norm_rule_code) > 6 and len(norm_found) >= len(norm_rule_code):
                    if norm_found[: len(norm_rule_code)] == norm_rule_code:
                        return FieldValidation(
                            field_name="hs_code",
                            status=ValidationStatus.MATCH,
                            expected=expected_codes_str,
                            found=field.value,
                            reason=f"HS code {field.value} matches approved tariff classification ({rule.code})",
                        )
                else:
                    return FieldValidation(
                        field_name="hs_code",
                        status=ValidationStatus.MATCH,
                        expected=expected_codes_str,
                        found=field.value,
                        reason=f"HS code {field.value} matches approved tariff classification ({rule.code})",
                    )
        elif len(norm_rule_code) == len(norm_found) and norm_found == norm_rule_code:
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
    """Validate port of loading/discharge against allowed LOCODEs and names with token and country precision."""
    invariant_check = check_field_grounding_and_confidence(
        field, min_confidence, field_name=port_type
    )
    if invariant_check is not None:
        return invariant_check

    val_upper = (field.value or "").strip().upper()
    allowed_locodes = [loc.strip().upper() for loc in port_rule.allowed_locodes]
    allowed_names = [name.strip().upper() for name in port_rule.allowed_names]

    expected_summary = (
        f"Allowed LOCODEs: {', '.join(port_rule.allowed_locodes)} / Names: {', '.join(port_rule.allowed_names)}"
    )

    # 1. Match allowed LOCODEs
    for loc in allowed_locodes:
        if re.search(r"\b" + loc + r"\b", val_upper):
            return FieldValidation(
                field_name=port_type,
                status=ValidationStatus.MATCH,
                expected=expected_summary,
                found=field.value,
                reason=f"{port_type.upper()} '{field.value}' matches approved UN/LOCODE ({loc})",
            )

    # 2. Check whole port name matches using word boundary
    for name in allowed_names:
        name_pattern = r"\b" + re.escape(name.upper()) + r"\b"
        if re.search(name_pattern, val_upper):
            foreign_indicators = [
                "NEW ZEALAND", "AUSTRALIA", "GERMANY", "NETHERLANDS",
                "UNITED KINGDOM", "FRANCE", "ROTTERDAM", "HAMBURG"
            ]
            if any(ind in val_upper for ind in foreign_indicators):
                return FieldValidation(
                    field_name=port_type,
                    status=ValidationStatus.MISMATCH,
                    expected=expected_summary,
                    found=field.value,
                    reason=f"{port_type.upper()} '{field.value}' specifies a foreign jurisdiction incompatible with approved ports",
                )

            return FieldValidation(
                field_name=port_type,
                status=ValidationStatus.MATCH,
                expected=expected_summary,
                found=field.value,
                reason=f"{port_type.upper()} '{field.value}' matches approved port name '{name}'",
            )

    # 3. Check for partial name overlap (e.g. SHA for Shanghai without LOCODE)
    for name in allowed_names:
        val_tokens = re.findall(r"\w+", val_upper)
        if any(tok in name.upper() and len(tok) >= 3 for tok in val_tokens):
            return FieldValidation(
                field_name=port_type,
                status=ValidationStatus.UNCERTAIN,
                expected=expected_summary,
                found=field.value,
                reason=f"{port_type.upper()} '{field.value}' has partial overlap with '{name}'; exact port name or LOCODE required",
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
