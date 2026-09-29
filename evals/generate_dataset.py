"""Synthetic trade document dataset generator using PyMuPDF (fitz).

Generates 12 realistic trade documents (clean, messy, and planted errors)
in evals/dataset/ and verifies their text layers for offline evaluation (EVAL-01).
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import pymupdf as fitz


DATASET_DIR = os.path.join(os.path.dirname(__file__), "dataset")
GROUND_TRUTH_FILE = os.path.join(os.path.dirname(__file__), "ground_truth.json")


DOCUMENTS_SPEC: List[Dict[str, Any]] = [
    {
        "document_id": "doc_01",
        "filename": "doc_01_clean_invoice_meridian_tokyo.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "clean",
        "header_info": [
            ("Invoice No:", "INV-2026-9001"),
            ("Invoice Date:", "March 15, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Minato-ku, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9001",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400 with Servo Controllers",
        },
        "expected_validation": "match",
        "expected_decision": "auto_approve",
        "discrepancy_notes": "Clean commercial invoice perfectly matching all customer baseline rules.",
    },
    {
        "document_id": "doc_02",
        "filename": "doc_02_clean_bol_meridian_yokohama.pdf",
        "title": "OCEAN BILL OF LADING",
        "category": "clean",
        "header_info": [
            ("B/L Number:", "BL-2026-8812"),
            ("Booking Ref:", "BKG-TYO-9912"),
            ("Shipper:", "Yokohama Industrial Mechatronics Ltd, Yokohama, Japan"),
        ],
        "fields": {
            "invoice_number": "BL-2026-8812",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.10",
            "pol": "Yokohama Port (JPYOK)",
            "pod": "Port of Long Beach (USLGB)",
            "incoterm": "CIF",
            "gross_weight": "12,200.00 KG",
            "description": "Multi-axis Industrial Welding Robots and Articulated Manipulators",
        },
        "expected_validation": "match",
        "expected_decision": "auto_approve",
        "discrepancy_notes": "Clean ocean bill of lading matching approved consignee, ports, and CIF terms.",
    },
    {
        "document_id": "doc_03",
        "filename": "doc_03_clean_invoice_meridian_usd.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "clean",
        "header_info": [
            ("Invoice No:", "INV-2026-9003"),
            ("Issue Date:", "March 18, 2026"),
            ("Exporter:", "Shanghai Advanced Automation Works, Pudong, Shanghai, China"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9003",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.89.90",
            "pol": "Shanghai Port (CNSHA)",
            "pod": "Port of Oakland (USOAK)",
            "incoterm": "DAP",
            "gross_weight": "9,800.00 KG",
            "description": "Automated Robotic Assembly Cells and Modular Feeder Units",
        },
        "expected_validation": "match",
        "expected_decision": "auto_approve",
        "discrepancy_notes": "Clean commercial invoice with DAP terms and Shanghai to Oakland routing.",
    },
    {
        "document_id": "doc_04",
        "filename": "doc_04_discrepancy_hs_transposition.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9004"),
            ("Date:", "March 20, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Minato-ku, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9004",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.05.00",  # Transposed from 8479.50.00
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "mismatch",
        "expected_decision": "amendment_request",
        "discrepancy_notes": "Planted tariff classification transposition (8479.05.00 not in approved 8479.50 / 8479.89).",
    },
    {
        "document_id": "doc_05",
        "filename": "doc_05_discrepancy_consignee_mismatch.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9005"),
            ("Date:", "March 21, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9005",
            "consignee": "Acme Global Industrial Logistics Ltd",  # Unauthorized consignee
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "mismatch",
        "expected_decision": "amendment_request",
        "discrepancy_notes": "Unauthorized third-party consignee Acme Global Industrial Logistics Ltd.",
    },
    {
        "document_id": "doc_06",
        "filename": "doc_06_discrepancy_missing_incoterm.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9006"),
            ("Date:", "March 22, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9006",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": None,  # Intentionally omitted
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "uncertain",
        "expected_decision": "human_review",
        "discrepancy_notes": "Mandatory trade Incoterm omitted from document text; tests zero guessing.",
    },
    {
        "document_id": "doc_07",
        "filename": "doc_07_discrepancy_weight_over_tolerance.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9007"),
            ("Date:", "March 23, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9007",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Yokohama Port (JPYOK)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "CIF",
            "gross_weight": "58,400.00 KG",  # Exceeds max 50,000 kg limit
            "description": "Industrial Heavy Forging Robot Gantry Structure",
        },
        "expected_validation": "mismatch",
        "expected_decision": "amendment_request",
        "discrepancy_notes": "Gross weight 58,400 KG exceeds customer maximum limit of 50,000 KG.",
    },
    {
        "document_id": "doc_08",
        "filename": "doc_08_discrepancy_disallowed_pol.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9008"),
            ("Date:", "March 24, 2026"),
            ("Exporter:", "Euro-Asian Maritime Logistics, Rotterdam, Netherlands"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9008",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Rotterdam Port (NLRTM)",  # Disallowed POL
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "mismatch",
        "expected_decision": "amendment_request",
        "discrepancy_notes": "Port of Loading NLRTM (Rotterdam) is not in customer approved POL list.",
    },
    {
        "document_id": "doc_09",
        "filename": "doc_09_edge_fuzzy_consignee_pass.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "edge_case",
        "header_info": [
            ("Invoice No:", "INV-2026-9009"),
            ("Date:", "March 25, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9009",
            "consignee": "Meridian Robotics LLC",  # Approved alias (fuzzy ratio >= 85%)
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "match",
        "expected_decision": "auto_approve",
        "discrepancy_notes": "Approved alias Meridian Robotics LLC correctly matches via fuzzy threshold >= 0.85.",
    },
    {
        "document_id": "doc_10",
        "filename": "doc_10_discrepancy_weight_unit_lbs.pdf",
        "title": "OCEAN BILL OF LADING",
        "category": "planted_discrepancy",
        "header_info": [
            ("B/L Number:", "BL-2026-9910"),
            ("Date:", "March 26, 2026"),
            ("Shipper:", "Yokohama Industrial Mechatronics Ltd, Yokohama, Japan"),
        ],
        "fields": {
            "invoice_number": "BL-2026-9910",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "Pending tare re-weigh verification",  # Non-numeric unparseable weight
            "description": "Articulated Industrial Robot Manipulators",
        },
        "expected_validation": "uncertain",
        "expected_decision": "human_review",
        "discrepancy_notes": "Unparseable non-numeric gross weight triggers UNCERTAIN validation status.",
    },
    {
        "document_id": "doc_11",
        "filename": "doc_11_multi_discrepancy_consignee_incoterm.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "planted_discrepancy",
        "header_info": [
            ("Invoice No:", "INV-2026-9011"),
            ("Date:", "March 27, 2026"),
            ("Exporter:", "Pacific Rim Cargo Ltd, Osaka, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9011",
            "consignee": "Pacific Rim Cargo Ltd",  # Unapproved consignee
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "EXW",  # Disallowed Incoterm
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "mismatch",
        "expected_decision": "amendment_request",
        "discrepancy_notes": "Compound discrepancies: unauthorized consignee and prohibited Incoterm EXW.",
    },
    {
        "document_id": "doc_12",
        "filename": "doc_12_messy_scanned_noisy_invoice.pdf",
        "title": "COMMERCIAL INVOICE",
        "category": "messy",
        "header_info": [
            ("Invoice No:", "INV-2026-9012"),
            ("Date:", "March 28, 2026"),
            ("Exporter:", "Tokyo Precision Robotics Corp, Tokyo, Japan"),
        ],
        "fields": {
            "invoice_number": "INV-2026-9012",
            "consignee": "Meridian Robotics Inc.",
            "hs_code": "8479.50.00",
            "pol": "Port of Tokyo (JPTYO)",
            "pod": "Port of Los Angeles (USLAX)",
            "incoterm": "FOB",
            "gross_weight": "12,500.00 KG",
            "description": "Industrial Robotic Arms model MR-400",
        },
        "expected_validation": "match",
        "expected_decision": "auto_approve",
        "discrepancy_notes": "Degraded visual styling with simulated scanner artifacts, but completely valid trade values.",
    },
]


def create_pdf_document(spec: Dict[str, Any], output_path: str) -> None:
    """Generate a clean, professional PDF trade document with PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # Standard A4: 595 x 842 points

    is_messy = spec.get("category") == "messy"

    # Color palette
    header_color = (0.2, 0.2, 0.3) if not is_messy else (0.4, 0.4, 0.4)
    text_color = (0.05, 0.05, 0.1) if not is_messy else (0.25, 0.25, 0.25)
    border_color = (0.7, 0.75, 0.8) if not is_messy else (0.8, 0.8, 0.8)
    table_header_bg = (0.92, 0.94, 0.97) if not is_messy else (0.95, 0.95, 0.95)

    # Document Title Header
    page.insert_text(
        fitz.Point(50, 60),
        spec["title"],
        fontsize=18,
        fontname="helv",
        color=header_color,
    )

    page.insert_text(
        fitz.Point(50, 78),
        "INTERNATIONAL TRADE CARGO DOCUMENTATION - SYSTEM OF RECORD",
        fontsize=8,
        fontname="helv",
        color=(0.5, 0.5, 0.6),
    )

    # Header horizontal line
    page.draw_line(fitz.Point(50, 88), fitz.Point(545, 88), color=border_color, width=1.5)

    # Meta Header Information
    y = 110
    for label, val in spec.get("header_info", []):
        page.insert_text(fitz.Point(50, y), label, fontsize=9, fontname="helv", color=(0.4, 0.4, 0.5))
        page.insert_text(fitz.Point(140, y), val, fontsize=9, fontname="helv", color=text_color)
        y += 18

    y += 10
    page.draw_line(fitz.Point(50, y), fitz.Point(545, y), color=border_color, width=0.8)
    y += 20

    # Section Title
    page.insert_text(fitz.Point(50, y), "TRADE PARTICULARS & SHIPMENT DETAILS", fontsize=11, fontname="helv", color=header_color)
    y += 15

    # Particulars Table Box
    fields = spec["fields"]
    table_items = [
        ("Invoice / Document Number:", fields.get("invoice_number", "")),
        ("Buyer / Consignee Name:", fields.get("consignee", "")),
        ("Harmonized Tariff (HS Code):", fields.get("hs_code", "")),
        ("Port of Loading (POL):", fields.get("pol", "")),
        ("Port of Discharge (POD):", fields.get("pod", "")),
        ("Delivery Terms (Incoterm):", fields.get("incoterm") or "TERMS NOT SPECIFIED"),
        ("Gross Cargo Weight:", fields.get("gross_weight", "")),
        ("Description of Merchandise:", fields.get("description", "")),
    ]

    for label, val in table_items:
        # Background stripe for row
        rect = fitz.Rect(50, y - 10, 545, y + 10)
        page.draw_rect(rect, color=border_color, width=0.5)

        page.insert_text(fitz.Point(60, y + 3), label, fontsize=9, fontname="helv", color=(0.35, 0.35, 0.45))
        page.insert_text(fitz.Point(220, y + 3), str(val), fontsize=9, fontname="helv", color=text_color)
        y += 24

    # Footer note & signature block
    y += 30
    page.draw_line(fitz.Point(50, y), fitz.Point(545, y), color=border_color, width=0.8)
    y += 20
    page.insert_text(
        fitz.Point(50, y),
        "Authorized Officer Signature & Corporate Seal:",
        fontsize=8,
        fontname="helv",
        color=(0.5, 0.5, 0.5),
    )
    page.insert_text(
        fitz.Point(400, y),
        "[DIGITALLY VERIFIED]",
        fontsize=8,
        fontname="helv",
        color=(0.2, 0.6, 0.3),
    )

    # Simulated visual noise for messy document
    if is_messy:
        for offset in range(10, 500, 45):
            page.draw_line(
                fitz.Point(45 + offset, 40),
                fitz.Point(50 + offset, 800),
                color=(0.92, 0.92, 0.92),
                width=0.3,
            )

    doc.save(output_path)
    doc.close()


def generate_all(dataset_dir: str = DATASET_DIR, verify: bool = False) -> None:
    """Generate all 12 dataset documents and dump ground truth metadata."""
    os.makedirs(dataset_dir, exist_ok=True)

    ground_truth_records = []

    print(f"Generating {len(DOCUMENTS_SPEC)} synthetic trade documents in '{dataset_dir}'...")

    for spec in DOCUMENTS_SPEC:
        pdf_path = os.path.join(dataset_dir, spec["filename"])
        create_pdf_document(spec, pdf_path)

        ground_truth_records.append({
            "document_id": spec["document_id"],
            "filename": spec["filename"],
            "category": spec["category"],
            "expected_fields": spec["fields"],
            "expected_validation": spec["expected_validation"],
            "expected_decision": spec["expected_decision"],
            "discrepancy_notes": spec["discrepancy_notes"],
        })
        print(f"  [+] Created {spec['filename']} ({spec['category']} -> {spec['expected_decision']})")

    # Write ground_truth.json
    gt_data = {
        "version": "1.0",
        "description": "GoComet Nova DAW Evaluation Ground Truth (Part 1)",
        "document_count": len(ground_truth_records),
        "documents": ground_truth_records,
    }

    with open(GROUND_TRUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(gt_data, f, indent=2)

    print(f"\nWrote ground truth metadata to '{GROUND_TRUTH_FILE}'.")

    if verify:
        print("\nVerifying generated PDF readability and text layers...")
        for rec in ground_truth_records:
            pdf_path = os.path.join(dataset_dir, rec["filename"])
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"Missing expected PDF: {pdf_path}")
            doc = fitz.open(pdf_path)
            if len(doc) == 0:
                raise ValueError(f"Empty PDF: {pdf_path}")
            text = doc[0].get_text()
            doc.close()

            # Ensure expected invoice number is in extracted text
            inv = rec["expected_fields"].get("invoice_number")
            if inv and inv not in text:
                raise ValueError(f"Invoice {inv} not found in text layer of {rec['filename']}")

        print(f"Verified all {len(ground_truth_records)} documents successfully.")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic trade document evaluation dataset.")
    parser.add_argument("--verify", action="store_true", help="Verify generated PDFs after generation")
    args = parser.parse_args()

    generate_all(verify=args.verify)


if __name__ == "__main__":
    main()
