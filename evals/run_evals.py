"""Offline evaluation benchmark runner for GoComet Nova DAW (EVAL-02).

Evaluates the multi-agent pipeline against the golden dataset (evals/ground_truth.json),
measures field-level extraction accuracy, grounding verification rate, validation fidelity,
and rigorously enforces the Zero Silent Approvals guarantee (False-Approve Rate == 0.0%).
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pymupdf as fitz

from app.schemas import (
    CustomerRules,
    DecisionResult,
    DecisionType,
    ExtractedDoc,
    ExtractedField,
    ValidationResult,
    ValidationStatus,
    load_customer_rules,
)
from app.validator import ValidatorAgent
from app.router import determine_decision_type, generate_fallback_reasoning


GROUND_TRUTH_FILE = os.path.join(os.path.dirname(__file__), "ground_truth.json")
DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
CUSTOMER_RULES_FILE = os.path.join(os.path.dirname(__file__), "..", "config", "customer_rules.yaml")
REPORT_FILE = os.path.join(os.path.dirname(__file__), "eval_report.md")


def load_ground_truth() -> List[Dict[str, Any]]:
    """Load ground truth records from JSON."""
    if not os.path.exists(GROUND_TRUTH_FILE):
        raise FileNotFoundError(f"Ground truth file not found: {GROUND_TRUTH_FILE}")
    with open(GROUND_TRUTH_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("documents", [])


def extract_deterministic_doc(pdf_path: str, spec_fields: Dict[str, Any]) -> ExtractedDoc:
    """Deterministic extractor for test evaluation when running offline or without API quota."""
    doc = fitz.open(pdf_path)
    full_text = "\n".join(page.get_text() for page in doc)
    doc.close()

    fields: Dict[str, ExtractedField] = {}

    for field_name in [
        "consignee",
        "hs_code",
        "pol",
        "pod",
        "incoterm",
        "gross_weight",
        "description",
        "invoice_number",
    ]:
        target_val = spec_fields.get(field_name)

        if not target_val or target_val == "None":
            # Missing or omitted field
            fields[field_name] = ExtractedField(
                value=None,
                confidence=0.0,
                source_quote=None,
                is_grounded=False,
            )
            continue

        # Look for the target value in the document text
        if str(target_val) in full_text:
            # Build verbatim quote around the value
            # Find the line containing the target value
            matching_line = None
            for line in full_text.splitlines():
                if str(target_val) in line:
                    matching_line = line.strip()
                    break

            quote = matching_line or f"{field_name}: {target_val}"
            fields[field_name] = ExtractedField(
                value=str(target_val),
                confidence=0.96,
                source_quote=quote,
                is_grounded=True,
            )
        else:
            # Value not in text
            fields[field_name] = ExtractedField(
                value=str(target_val),
                confidence=0.45,
                source_quote=None,
                is_grounded=False,
            )

    return ExtractedDoc(
        consignee=fields["consignee"],
        hs_code=fields["hs_code"],
        pol=fields["pol"],
        pod=fields["pod"],
        incoterm=fields["incoterm"],
        gross_weight=fields["gross_weight"],
        description=fields["description"],
        invoice_number=fields["invoice_number"],
        raw_text=full_text,
        extraction_method="text_layer",
    )


def run_evaluation(
    quick: bool = False,
    mode: str = "rules",
    write_report: bool = False,
) -> Dict[str, Any]:
    """Execute evaluation benchmark across dataset in 'rules' or 'live' mode."""
    documents = load_ground_truth()
    rules = load_customer_rules(CUSTOMER_RULES_FILE)
    validator = ValidatorAgent(rules)

    if quick:
        # Select 3 representative documents: 1 clean, 1 mismatch, 1 uncertain
        target_ids = {"doc_01", "doc_04", "doc_06"}
        documents = [d for d in documents if d["document_id"] in target_ids]

    is_live = mode == "live"
    extractor = None
    if is_live:
        from app.extractor import ExtractorAgent
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key and os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.split("=", 1)[1].strip().strip("\"'")
                        os.environ["GEMINI_API_KEY"] = api_key
                        break
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is required to run evaluation in --mode live."
            )
        extractor = ExtractorAgent(mock_mode=False)

    results = []
    total_fields = 0
    correct_fields = 0
    grounded_quotes = 0

    validation_matches = 0
    decision_matches = 0

    discrepant_or_uncertain_count = 0
    false_approve_count = 0

    total_latency_ms = 0.0
    total_cost_usd = 0.0

    mode_label = "LIVE (Full Multi-Agent Pipeline with Real LLM Extractor)" if is_live else "RULES (Deterministic Validator & Router Only)"

    print(f"\n========================================================")
    print(f"  GoComet Nova DAW Evaluation Benchmark (EVAL-02)")
    print(f"  Mode : {mode_label}")
    print(f"  Evaluating {len(documents)} document(s)...")
    print(f"========================================================\n")

    for doc_entry in documents:
        start_t = time.perf_counter()
        doc_id = doc_entry["document_id"]
        filename = doc_entry["filename"]
        pdf_path = os.path.join(DATASET_DIR, filename)

        expected_fields = doc_entry["expected_fields"]
        expected_validation = doc_entry["expected_validation"].lower()
        expected_decision = doc_entry["expected_decision"].lower()

        doc_cost = 0.0
        # Extract document
        if is_live:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            extracted_doc, run_trace = extractor.extract(
                file_bytes=pdf_bytes,
                filename=filename,
                document_id=doc_id,
            )
            doc_cost = run_trace.cost_usd
            total_cost_usd += doc_cost
        else:
            # Rules mode uses deterministic fixture
            extracted_doc = extract_deterministic_doc(pdf_path, expected_fields)

        # Field evaluation
        doc_field_correct = 0
        doc_field_total = 8

        for fname in [
            "consignee",
            "hs_code",
            "pol",
            "pod",
            "incoterm",
            "gross_weight",
            "description",
            "invoice_number",
        ]:
            total_fields += 1
            extracted_f = getattr(extracted_doc, fname)
            exp_val = expected_fields.get(fname)

            if exp_val is None:
                if extracted_f.value is None:
                    correct_fields += 1
                    doc_field_correct += 1
            else:
                if extracted_f.value and str(exp_val).strip().lower() == str(extracted_f.value).strip().lower():
                    correct_fields += 1
                    doc_field_correct += 1

            if extracted_f.is_grounded and extracted_f.source_quote:
                grounded_quotes += 1

        # Validate
        val_result = validator.validate(extracted_doc)
        actual_validation = val_result.overall_status.value.lower()

        # Decision
        dec_type = determine_decision_type(val_result)
        actual_decision = dec_type.value.lower()

        latency_ms = (time.perf_counter() - start_t) * 1000.0
        total_latency_ms += latency_ms

        val_correct = actual_validation == expected_validation
        dec_correct = actual_decision == expected_decision

        if val_correct:
            validation_matches += 1
        if dec_correct:
            decision_matches += 1

        # False-Approve check (Zero Silent Approvals guarantee)
        is_discrepant_expected = expected_decision != "auto_approve"
        if is_discrepant_expected:
            discrepant_or_uncertain_count += 1
            if actual_decision == "auto_approve":
                false_approve_count += 1
                print(f"❌ [CRITICAL SAFETY BREACH] {doc_id} was falsely auto-approved!")

        status_icon = "✅" if dec_correct and val_correct else "⚠️"
        print(
            f"{status_icon} [{doc_id}] {filename[:32]:32} | "
            f"Val: {actual_validation:9} (exp: {expected_validation:9}) | "
            f"Dec: {actual_decision:17} (exp: {expected_decision:17}) | "
            f"{latency_ms:.1f}ms"
            + (f" | ${doc_cost:.4f}" if is_live else "")
        )

        results.append({
            "document_id": doc_id,
            "filename": filename,
            "category": doc_entry["category"],
            "field_accuracy": round((doc_field_correct / doc_field_total) * 100, 1) if is_live else "N/A (rules mode)",
            "expected_validation": expected_validation,
            "actual_validation": actual_validation,
            "expected_decision": expected_decision,
            "actual_decision": actual_decision,
            "latency_ms": round(latency_ms, 2),
            "cost_usd": round(doc_cost, 6) if is_live else 0.0,
            "discrepancy_notes": doc_entry["discrepancy_notes"],
        })

    # Summary Metrics
    field_acc_pct = round((correct_fields / max(total_fields, 1)) * 100, 2) if is_live else None
    grounding_rate_pct = round((grounded_quotes / max(total_fields, 1)) * 100, 2) if is_live else None
    val_acc_pct = round((validation_matches / max(len(documents), 1)) * 100, 2)
    dec_acc_pct = round((decision_matches / max(len(documents), 1)) * 100, 2)

    false_approve_rate = (
        round((false_approve_count / discrepant_or_uncertain_count) * 100, 2)
        if discrepant_or_uncertain_count > 0
        else 0.0
    )
    avg_latency = round(total_latency_ms / max(len(documents), 1), 2)
    avg_cost = round(total_cost_usd / max(len(documents), 1), 6) if is_live else 0.0

    print(f"\n========================================================")
    print(f"  BENCHMARK SUMMARY RESULTS [{mode.upper()} MODE]")
    print(f"========================================================")
    print(f"  Total Documents Evaluated      : {len(documents)}")
    if is_live:
        print(f"  Field Extraction Accuracy      : {field_acc_pct}% ({correct_fields}/{total_fields})")
        print(f"  Grounding Quote Verification   : {grounding_rate_pct}%")
        print(f"  Average Cost per Document      : ${avg_cost:.4f}")
        print(f"  Total Cost (USD)               : ${total_cost_usd:.4f}")
    else:
        print(f"  Field Extraction Accuracy      : N/A (Rules mode tests Validator + Router)")
    print(f"  Validation Rule Accuracy       : {val_acc_pct}%")
    print(f"  Decision Routing Accuracy      : {dec_acc_pct}%")
    print(f"  Discrepant/Uncertain Test Docs : {discrepant_or_uncertain_count}")
    print(f"  False Approvals Detected       : {false_approve_count}")
    print(f"  FALSE-APPROVE RATE             : {false_approve_rate}%")
    print(f"  Average Latency                : {avg_latency} ms")
    print(f"========================================================\n")

    # Safety Guarantee Assertion
    if false_approve_count > 0:
        raise AssertionError(
            f"CRITICAL SAFETY VIOLATION: Zero Silent Approvals guarantee breached! "
            f"{false_approve_count} discrepant document(s) were auto-approved."
        )

    summary_data = {
        "mode": mode,
        "total_documents": len(documents),
        "field_extraction_accuracy_pct": field_acc_pct,
        "grounding_quote_rate_pct": grounding_rate_pct,
        "validation_accuracy_pct": val_acc_pct,
        "decision_routing_accuracy_pct": dec_acc_pct,
        "discrepant_or_uncertain_count": discrepant_or_uncertain_count,
        "false_approve_count": false_approve_count,
        "false_approve_rate_pct": false_approve_rate,
        "avg_latency_ms": avg_latency,
        "avg_cost_usd": avg_cost,
        "total_cost_usd": round(total_cost_usd, 6),
        "results": results,
    }

    if write_report:
        generate_markdown_report(summary_data)

    return summary_data


def generate_markdown_report(summary: Dict[str, Any]) -> None:
    """Generate comprehensive evaluation report in evals/eval_report.md."""
    is_live = summary.get("mode") == "live"
    mode_text = "Live LLM Extractor Pipeline" if is_live else "Deterministic Rules & Router Benchmark"

    lines = [
        f"# GoComet Nova DAW — Benchmark Report ({summary.get('mode', 'rules').upper()} MODE)",
        "",
        "## Executive Summary",
        f"- **Benchmark Status**: PASSED",
        f"- **Evaluation Mode**: {mode_text}",
        f"- **Zero Silent Approvals Guarantee**: **0.0% False-Approve Rate** (0 of {summary['discrepant_or_uncertain_count']} discrepant/uncertain documents approved)",
    ]

    if is_live:
        lines.extend([
            f"- **Field-Level Extraction Accuracy**: {summary['field_extraction_accuracy_pct']}%",
            f"- **Source Text Grounding Quote Rate**: {summary['grounding_quote_rate_pct']}%",
            f"- **Average Cost per Document**: ${summary['avg_cost_usd']:.4f}",
            f"- **Total Benchmark Cost**: ${summary['total_cost_usd']:.4f}",
        ])
    else:
        lines.append("- **Field-Level Extraction Accuracy**: N/A (Rules mode tests Validator + Router logic)")

    lines.extend([
        f"- **Rule Validation Accuracy**: {summary['validation_accuracy_pct']}%",
        f"- **Decision Routing Accuracy**: {summary['decision_routing_accuracy_pct']}%",
        f"- **Average Pipeline Latency**: {summary['avg_latency_ms']} ms",
        "",
        "## Golden Dataset Test Matrix",
        "",
        "| Doc ID | Category | Expected Validation | Actual Validation | Expected Decision | Actual Decision | Notes |",
        "|---|---|---|---|---|---|---|",
    ])

    for r in summary["results"]:
        lines.append(
            f"| `{r['document_id']}` | `{r['category']}` | `{r['expected_validation']}` | `{r['actual_validation']}` | `{r['expected_decision']}` | `{r['actual_decision']}` | {r['discrepancy_notes']} |"
        )

    lines.extend([
        "",
        "## Rigorous Safety Invariant: Zero Silent Approvals",
        "The primary risk in cargo trade document automation is releasing a shipment with silent non-compliance (incorrect consignee, prohibited tariff code, disallowed port, or excessive weight).",
        "",
        "Our multi-agent pipeline guarantees:",
        "1. Every extracted field is grounded by exact verbatim quote from the source document.",
        "2. If confidence falls below 0.85, or if quotes cannot be grounded, status collapses to `UNCERTAIN`.",
        "3. Any rule failure triggers `MISMATCH` and routes to `amendment_request`.",
        "4. **No discrepant or uncertain document is ever auto-approved** (`false_approve_rate == 0.0%`).",
    ])

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Generated comprehensive evaluation report at '{REPORT_FILE}'.")


def main():
    parser = argparse.ArgumentParser(description="Run evaluation benchmark on golden dataset.")
    parser.add_argument("--mode", choices=["rules", "live"], default="rules", help="Evaluation mode: 'rules' (validator + router only) or 'live' (full LLM extractor)")
    parser.add_argument("--quick", action="store_true", help="Run quick 3-document test suite")
    parser.add_argument("--report", action="store_true", help="Write evaluation report to evals/eval_report.md")
    args = parser.parse_args()

    run_evaluation(quick=args.quick, mode=args.mode, write_report=args.report)


if __name__ == "__main__":
    main()
