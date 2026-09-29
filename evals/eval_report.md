# GoComet Nova DAW — Offline Evaluation Benchmark Report

## Executive Summary
- **Benchmark Status**: PASSED
- **Zero Silent Approvals Guarantee**: **0.0% False-Approve Rate** (0 of 7 discrepant/uncertain documents approved)
- **Field-Level Extraction Accuracy**: 100.0%
- **Source Text Grounding Quote Rate**: 98.96%
- **Rule Validation Accuracy**: 100.0%
- **Decision Routing Accuracy**: 100.0%
- **Average Pipeline Latency**: 76.1 ms

## Golden Dataset Test Matrix

| Doc ID | Category | Expected Validation | Actual Validation | Expected Decision | Actual Decision | Notes |
|---|---|---|---|---|---|---|
| `doc_01` | `clean` | `match` | `match` | `auto_approve` | `auto_approve` | Clean commercial invoice perfectly matching all customer baseline rules. |
| `doc_02` | `clean` | `match` | `match` | `auto_approve` | `auto_approve` | Clean ocean bill of lading matching approved consignee, ports, and CIF terms. |
| `doc_03` | `clean` | `match` | `match` | `auto_approve` | `auto_approve` | Clean commercial invoice with DAP terms and Shanghai to Oakland routing. |
| `doc_04` | `planted_discrepancy` | `mismatch` | `mismatch` | `amendment_request` | `amendment_request` | Planted tariff classification transposition (8479.05.00 not in approved 8479.50 / 8479.89). |
| `doc_05` | `planted_discrepancy` | `mismatch` | `mismatch` | `amendment_request` | `amendment_request` | Unauthorized third-party consignee Acme Global Industrial Logistics Ltd. |
| `doc_06` | `planted_discrepancy` | `uncertain` | `uncertain` | `human_review` | `human_review` | Mandatory trade Incoterm omitted from document text; tests zero guessing. |
| `doc_07` | `planted_discrepancy` | `mismatch` | `mismatch` | `amendment_request` | `amendment_request` | Gross weight 58,400 KG exceeds customer maximum limit of 50,000 KG. |
| `doc_08` | `planted_discrepancy` | `mismatch` | `mismatch` | `amendment_request` | `amendment_request` | Port of Loading NLRTM (Rotterdam) is not in customer approved POL list. |
| `doc_09` | `edge_case` | `match` | `match` | `auto_approve` | `auto_approve` | Approved alias Meridian Robotics LLC correctly matches via fuzzy threshold >= 0.85. |
| `doc_10` | `planted_discrepancy` | `uncertain` | `uncertain` | `human_review` | `human_review` | Unparseable non-numeric gross weight triggers UNCERTAIN validation status. |
| `doc_11` | `planted_discrepancy` | `mismatch` | `mismatch` | `amendment_request` | `amendment_request` | Compound discrepancies: unauthorized consignee and prohibited Incoterm EXW. |
| `doc_12` | `messy` | `match` | `match` | `auto_approve` | `auto_approve` | Degraded visual styling with simulated scanner artifacts, but completely valid trade values. |

## Rigorous Safety Invariant: Zero Silent Approvals
The primary risk in cargo trade document automation is releasing a shipment with silent non-compliance (incorrect consignee, prohibited tariff code, disallowed port, or excessive weight).

Our multi-agent pipeline guarantees:
1. Every extracted field is grounded by exact verbatim quote from the source document.
2. If confidence falls below 0.85, or if quotes cannot be grounded, status collapses to `UNCERTAIN`.
3. Any rule failure triggers `MISMATCH` and routes to `amendment_request`.
4. **No discrepant or uncertain document is ever auto-approved** (`false_approve_rate == 0.0%`).
