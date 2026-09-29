"""Typed Pydantic contracts for GoComet Nova multi-agent pipeline."""

from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExtractedField(BaseModel):
    """Represents an extracted trade document field with grounding metadata."""
    model_config = ConfigDict(extra="forbid")

    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_quote: Optional[str] = None
    is_grounded: bool = False

    @model_validator(mode="after")
    def enforce_grounding_invariant(self) -> "ExtractedField":
        """If ungrounded or missing source quote, force value to None to prevent silent hallucination."""
        if not self.is_grounded or self.source_quote is None or not self.source_quote.strip():
            self.value = None
        return self


class ExtractedDoc(BaseModel):
    """Normalized payload output by the Extractor Agent."""
    model_config = ConfigDict(extra="forbid")

    consignee: ExtractedField
    hs_code: ExtractedField
    pol: ExtractedField
    pod: ExtractedField
    incoterm: ExtractedField
    description: ExtractedField
    gross_weight: ExtractedField
    invoice_number: ExtractedField
    extraction_method: Literal["text_layer", "vision_default", "vision_fallback"]
    grounding_source: Literal["text_layer", "ocr", "vision_unverified"] = "text_layer"
    grounding_note: Optional[str] = None
    raw_text: Optional[str] = None


class ValidationStatus(str, Enum):
    """Tri-state validation outcome for fields and documents."""
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"


class FieldValidation(BaseModel):
    """Detailed validation evaluation for a single field."""
    model_config = ConfigDict(extra="forbid")

    field_name: str
    status: ValidationStatus
    expected: Optional[str] = None
    found: Optional[str] = None
    reason: str


class Discrepancy(BaseModel):
    """Actionable discrepancy identified between document and customer rules."""
    model_config = ConfigDict(extra="forbid")

    field_name: str
    expected: str
    found: str
    severity: Literal["critical", "warning"]


class ValidationResult(BaseModel):
    """Payload output by the Validator Agent."""
    model_config = ConfigDict(extra="forbid")

    overall_status: ValidationStatus
    field_validations: Dict[str, FieldValidation]
    discrepancies: List[Discrepancy]


class DecisionType(str, Enum):
    """Deterministic routing actions."""
    AUTO_APPROVE = "auto_approve"
    HUMAN_REVIEW = "human_review"
    AMENDMENT_REQUEST = "amendment_request"


class DecisionResult(BaseModel):
    """Payload output by the Router Agent."""
    model_config = ConfigDict(extra="forbid")

    decision: DecisionType
    reasoning: str
    draft_amendment_email: Optional[str] = None
    text_source: Literal["llm", "template"] = "llm"


class RunTrace(BaseModel):
    """Telemetry and observability record for individual agent and node executions."""
    model_config = ConfigDict(extra="forbid")

    run_id: str
    document_id: Optional[str] = None
    node_name: str
    model_name: Optional[str] = None
    latency_ms: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float = 0.0
    status: Literal["SUCCESS", "FAILED", "RUNNING", "DEGRADED"]
    error_message: Optional[str] = None


# Customer Rules Declarative Schema

class ConsigneeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_name: str
    aliases: List[str] = Field(default_factory=list)
    address_keywords: List[str] = Field(default_factory=list)
    min_fuzzy_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    allow_fuzzy_auto_approve: bool = Field(default=False)


class HSCodeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    description: str


class PortRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_locodes: List[str]
    allowed_names: List[str]


class PortsRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pol: PortRule
    pod: PortRule


class WeightToleranceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit: str = "KG"
    variance_percent: float = Field(ge=0.0)
    max_limit_kg: float = Field(gt=0.0)


class ValidationThresholdsRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence_auto_approve: float = Field(default=0.85, ge=0.0, le=1.0)


class CustomerRules(BaseModel):
    """Declarative customer requirements for trade document validation."""
    model_config = ConfigDict(extra="forbid")

    customer_id: str
    customer_name: str
    consignee: ConsigneeRule
    allowed_hs_codes: List[HSCodeRule]
    allowed_incoterms: List[str]
    ports: PortsRule
    weight_tolerance: WeightToleranceRule
    validation_thresholds: ValidationThresholdsRule


def load_customer_rules(yaml_path: str = "config/customer_rules.yaml") -> CustomerRules:
    """Load and validate declarative customer rules from a YAML file."""
    path = Path(yaml_path)
    if not path.is_file():
        raise FileNotFoundError(f"Customer rules configuration not found at: {yaml_path}")
    
    with open(path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f)
    
    return CustomerRules.model_validate(raw_data)
