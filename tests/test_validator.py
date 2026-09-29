"""Unit tests for deterministic ValidatorAgent and field evaluators."""

import pytest
from app.schemas import (
    ConsigneeRule,
    CustomerRules,
    ExtractedDoc,
    ExtractedField,
    HSCodeRule,
    PortRule,
    PortsRule,
    ValidationResult,
    ValidationStatus,
    ValidationThresholdsRule,
    WeightToleranceRule,
    load_customer_rules,
)
from app.validator import (
    ValidatorAgent,
    check_field_grounding_and_confidence,
    validate_consignee,
    validate_gross_weight,
    validate_hs_code,
    validate_incoterm,
    validate_informational_field,
    validate_port,
)


@pytest.fixture
def default_rules() -> CustomerRules:
    """Fixture providing loaded customer rules from config."""
    return load_customer_rules("config/customer_rules.yaml")


@pytest.fixture
def valid_doc() -> ExtractedDoc:
    """Fixture providing a fully valid ExtractedDoc conforming to customer rules."""
    return ExtractedDoc(
        consignee=ExtractedField(
            value="Meridian Robotics Inc.",
            confidence=0.98,
            source_quote="Consignee: Meridian Robotics Inc.",
            is_grounded=True,
        ),
        hs_code=ExtractedField(
            value="8479.50.00",
            confidence=0.95,
            source_quote="HS Code: 8479.50.00",
            is_grounded=True,
        ),
        pol=ExtractedField(
            value="Shanghai Port (CNSHA)",
            confidence=0.92,
            source_quote="POL: Shanghai Port (CNSHA)",
            is_grounded=True,
        ),
        pod=ExtractedField(
            value="Port of Los Angeles (USLAX)",
            confidence=0.96,
            source_quote="POD: Port of Los Angeles (USLAX)",
            is_grounded=True,
        ),
        incoterm=ExtractedField(
            value="FOB",
            confidence=0.99,
            source_quote="Terms: FOB",
            is_grounded=True,
        ),
        gross_weight=ExtractedField(
            value="12,500.00 KG",
            confidence=0.91,
            source_quote="Gross Weight: 12,500.00 KG",
            is_grounded=True,
        ),
        description=ExtractedField(
            value="Industrial Robotic Arms model MR-400",
            confidence=0.94,
            source_quote="Cargo: Industrial Robotic Arms model MR-400",
            is_grounded=True,
        ),
        invoice_number=ExtractedField(
            value="INV-2026-9081",
            confidence=0.97,
            source_quote="Invoice No: INV-2026-9081",
            is_grounded=True,
        ),
        extraction_method="text_layer",
    )


# --- Task 1 Tests: Invariants & Grounding ---

def test_zero_silent_approvals_ungrounded():
    """Ungrounded field must evaluate to UNCERTAIN."""
    field = ExtractedField(
        value="Meridian Robotics Inc.",
        confidence=0.95,
        source_quote=None,
        is_grounded=False,
    )
    res = check_field_grounding_and_confidence(field, min_confidence=0.85, field_name="consignee")
    assert res is not None
    assert res.status == ValidationStatus.UNCERTAIN
    assert "ungrounded" in res.reason.lower()


def test_zero_silent_approvals_low_confidence():
    """Field with confidence below threshold must evaluate to UNCERTAIN."""
    field = ExtractedField(
        value="Meridian Robotics Inc.",
        confidence=0.72,
        source_quote="Meridian Robotics Inc.",
        is_grounded=True,
    )
    res = check_field_grounding_and_confidence(field, min_confidence=0.85, field_name="consignee")
    assert res is not None
    assert res.status == ValidationStatus.UNCERTAIN
    assert "below auto-approval threshold" in res.reason


def test_zero_silent_approvals_null_field():
    """Field with empty/null value evaluates to UNCERTAIN."""
    # When is_grounded is True but value is whitespace
    field = ExtractedField(
        value="   ",
        confidence=0.95,
        source_quote="Some quote",
        is_grounded=True,
    )
    res = check_field_grounding_and_confidence(field, min_confidence=0.85, field_name="test_field")
    assert res is not None
    assert res.status == ValidationStatus.UNCERTAIN
    assert "missing or null" in res.reason.lower()


# --- Task 1 Tests: Consignee Matching ---

def test_consignee_exact_match(default_rules):
    """Exact primary match returns MATCH."""
    field = ExtractedField(
        value="Meridian Robotics Inc.",
        confidence=0.95,
        source_quote="Meridian Robotics Inc.",
        is_grounded=True,
    )
    val = validate_consignee(field, default_rules.consignee, min_confidence=0.85)
    assert val.status == ValidationStatus.MATCH
    assert "exact match" in val.reason.lower()


def test_consignee_alias_match(default_rules):
    """Alias match returns MATCH."""
    field = ExtractedField(
        value="Meridian Robotics Corp",
        confidence=0.90,
        source_quote="Meridian Robotics Corp",
        is_grounded=True,
    )
    val = validate_consignee(field, default_rules.consignee, min_confidence=0.85)
    assert val.status == ValidationStatus.MATCH


def test_consignee_fuzzy_matching(default_rules):
    """Fuzzy matching above 0.85 threshold passes, 0.65-0.85 is uncertain, <0.65 is mismatch."""
    # High similarity (e.g. minor typo / omission like 'Meridian Robotics Incorporated' vs 'Meridian Robotics Incorp')
    field_high = ExtractedField(
        value="Meridian Robotics Incorprated",
        confidence=0.92,
        source_quote="Meridian Robotics Incorprated",
        is_grounded=True,
    )
    val_high = validate_consignee(field_high, default_rules.consignee, min_confidence=0.85)
    assert val_high.status == ValidationStatus.MATCH

    # Ambiguous similarity (0.65 <= ratio < 0.85)
    field_ambig = ExtractedField(
        value="Meridian Robot Systems Inc",
        confidence=0.90,
        source_quote="Meridian Robot Systems Inc",
        is_grounded=True,
    )
    val_ambig = validate_consignee(field_ambig, default_rules.consignee, min_confidence=0.85)
    assert val_ambig.status == ValidationStatus.UNCERTAIN
    assert "ambiguous" in val_ambig.reason.lower()

    # Low similarity (< 0.65) -> Mismatch
    field_mismatch = ExtractedField(
        value="Apex Industrial Automation Ltd.",
        confidence=0.95,
        source_quote="Apex Industrial Automation Ltd.",
        is_grounded=True,
    )
    val_mismatch = validate_consignee(field_mismatch, default_rules.consignee, min_confidence=0.85)
    assert val_mismatch.status == ValidationStatus.MISMATCH


# --- Task 1 Tests: HS Code Matching ---

def test_hs_code_match(default_rules):
    """HS Code matching 8479.50 with various punctuation formats passes."""
    field = ExtractedField(
        value="8479-50-90",
        confidence=0.95,
        source_quote="8479-50-90",
        is_grounded=True,
    )
    val = validate_hs_code(field, default_rules.allowed_hs_codes, min_confidence=0.85)
    assert val.status == ValidationStatus.MATCH


def test_hs_code_mismatch(default_rules):
    """Disallowed HS code produces MISMATCH."""
    field = ExtractedField(
        value="8501.10.00",
        confidence=0.95,
        source_quote="8501.10.00",
        is_grounded=True,
    )
    val = validate_hs_code(field, default_rules.allowed_hs_codes, min_confidence=0.85)
    assert val.status == ValidationStatus.MISMATCH
    assert "not in customer approved list" in val.reason


# --- Task 2 Tests: Incoterm, Port, Gross Weight ---

def test_incoterm_validation(default_rules):
    """Incoterm validation handles allowed vs disallowed terms."""
    f_match = ExtractedField(
        value="cif",
        confidence=0.90,
        source_quote="CIF",
        is_grounded=True,
    )
    assert validate_incoterm(f_match, default_rules.allowed_incoterms, 0.85).status == ValidationStatus.MATCH

    f_mismatch = ExtractedField(
        value="EXW",
        confidence=0.90,
        source_quote="EXW",
        is_grounded=True,
    )
    val = validate_incoterm(f_mismatch, default_rules.allowed_incoterms, 0.85)
    assert val.status == ValidationStatus.MISMATCH


def test_port_validation(default_rules):
    """Port validation handles LOCODE, port names, and mismatches."""
    # Matched by LOCODE
    f_locode = ExtractedField(
        value="CNSHA - Shanghai",
        confidence=0.91,
        source_quote="CNSHA - Shanghai",
        is_grounded=True,
    )
    assert validate_port(f_locode, default_rules.ports.pol, "pol", 0.85).status == ValidationStatus.MATCH

    # Matched by Name
    f_name = ExtractedField(
        value="Long Beach Port",
        confidence=0.89,
        source_quote="Long Beach Port",
        is_grounded=True,
    )
    assert validate_port(f_name, default_rules.ports.pod, "pod", 0.85).status == ValidationStatus.MATCH

    # Mismatch
    f_mismatch = ExtractedField(
        value="Hamburg Port (DEHAM)",
        confidence=0.90,
        source_quote="Hamburg Port (DEHAM)",
        is_grounded=True,
    )
    assert validate_port(f_mismatch, default_rules.ports.pod, "pod", 0.85).status == ValidationStatus.MISMATCH


def test_gross_weight_validation(default_rules):
    """Gross weight validates parsing, unit conversion, and weight limit."""
    # Under limit KG
    f_kg = ExtractedField(
        value="45,000.50 KGS",
        confidence=0.93,
        source_quote="45,000.50 KGS",
        is_grounded=True,
    )
    assert validate_gross_weight(f_kg, default_rules.weight_tolerance, 0.85).status == ValidationStatus.MATCH

    # Under limit LBS (100,000 lbs = ~45,359 kg <= 50,000 kg)
    f_lbs = ExtractedField(
        value="100000 LBS",
        confidence=0.92,
        source_quote="100000 LBS",
        is_grounded=True,
    )
    assert validate_gross_weight(f_lbs, default_rules.weight_tolerance, 0.85).status == ValidationStatus.MATCH

    # Exceeding limit KG (> 50,000 kg)
    f_exceed = ExtractedField(
        value="52,000 KG",
        confidence=0.95,
        source_quote="52,000 KG",
        is_grounded=True,
    )
    val_exceed = validate_gross_weight(f_exceed, default_rules.weight_tolerance, 0.85)
    assert val_exceed.status == ValidationStatus.MISMATCH

    # Unparseable weight
    f_invalid = ExtractedField(
        value="Not Available",
        confidence=0.90,
        source_quote="Not Available",
        is_grounded=True,
    )
    assert validate_gross_weight(f_invalid, default_rules.weight_tolerance, 0.85).status == ValidationStatus.UNCERTAIN


# --- Task 2 Tests: ValidatorAgent & Discrepancies ---

def test_validator_clean_document_all_match(default_rules, valid_doc):
    """A clean document conforming to all rules yields overall MATCH and 0 discrepancies."""
    agent = ValidatorAgent(rules=default_rules)
    result = agent.validate(valid_doc)

    assert result.overall_status == ValidationStatus.MATCH
    assert len(result.discrepancies) == 0
    assert all(fv.status == ValidationStatus.MATCH for fv in result.field_validations.values())


def test_validator_mismatch_creates_discrepancy(default_rules, valid_doc):
    """Document with mismatching Incoterm yields MISMATCH with itemized discrepancy."""
    valid_doc.incoterm = ExtractedField(
        value="DDP",
        confidence=0.95,
        source_quote="Terms: DDP",
        is_grounded=True,
    )
    agent = ValidatorAgent(rules=default_rules)
    result = agent.validate(valid_doc)

    assert result.overall_status == ValidationStatus.MISMATCH
    assert len(result.discrepancies) == 1
    disc = result.discrepancies[0]
    assert disc.field_name == "incoterm"
    assert disc.found == "DDP"
    assert disc.severity == "critical"


def test_validator_uncertain_field_yields_uncertain_overall(default_rules, valid_doc):
    """Document with low-confidence field yields UNCERTAIN overall and 0 discrepancies."""
    valid_doc.description = ExtractedField(
        value="Industrial Robotic Arms",
        confidence=0.60,
        source_quote="Industrial Robotic Arms",
        is_grounded=True,
    )
    agent = ValidatorAgent(rules=default_rules)
    result = agent.validate(valid_doc)

    assert result.overall_status == ValidationStatus.UNCERTAIN
    assert len(result.discrepancies) == 0
    assert result.field_validations["description"].status == ValidationStatus.UNCERTAIN


def test_validator_mismatch_precedence_over_uncertain(default_rules, valid_doc):
    """If both MISMATCH and UNCERTAIN exist, MISMATCH takes precedence."""
    # Incoterm is mismatched
    valid_doc.incoterm = ExtractedField(
        value="EXW",
        confidence=0.95,
        source_quote="Terms: EXW",
        is_grounded=True,
    )
    # Gross weight is uncertain
    valid_doc.gross_weight = ExtractedField(
        value="Unknown weight",
        confidence=0.90,
        source_quote="Unknown weight",
        is_grounded=True,
    )
    agent = ValidatorAgent(rules=default_rules)
    result = agent.validate(valid_doc)

    assert result.overall_status == ValidationStatus.MISMATCH
    assert len(result.discrepancies) == 1
    assert result.discrepancies[0].field_name == "incoterm"
    assert result.field_validations["gross_weight"].status == ValidationStatus.UNCERTAIN
