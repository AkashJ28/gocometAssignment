# GoComet Nova DAW — Autonomous Trade Document Verification Pipeline (Part 1)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18.3-61dafb.svg)](https://react.dev/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ed.svg)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/Tests-80%20Passing-brightgreen.svg)]()
[![Zero Silent Approvals](https://img.shields.io/badge/Zero%20Silent%20Approvals-0.0%25%20False%20Approve-success.svg)]()

> **Nova DAW (Digital Agentic Worker)** is an enterprise multi-agent pipeline for autonomous trade document extraction, deterministic customer rule validation, and policy-driven routing.
> Built to deliver a non-negotiable System of Outcomes guarantee: **Zero Silent Approvals** (0.0% False-Approve Rate on Discrepant or Uncertain Trade Documents).

---

## Key Features (Part 1 Deliverables)

1. **Multimodal Extractor Agent**:
   - Extracts all 8 critical trade fields: Consignee, HS Code, Port of Loading (POL), Port of Discharge (POD), Incoterms, Cargo Description, Gross Weight, and Invoice Number.
   - Per-field confidence scoring and verbatim source quote grounding to eliminate digit hallucinations.
2. **Deterministic Validator Agent**:
   - Zero-LLM rule evaluation against customer baseline rules (`config/customer_rules.yaml`).
   - Hard tri-state outcomes (`match`, `mismatch`, `uncertain`) with Levenshtein fuzzy matching and mathematical tolerance boundaries.
3. **Router & Decision Agent**:
   - Autonomous tri-state policy routing (`AUTO_APPROVE`, `HUMAN_REVIEW`, `AMENDMENT_REQUEST`).
   - Gemini 2.5 Flash Lite generates structured natural language reasoning and editable draft amendment emails for cargo operators.
4. **Natural Language Query Interface (STOR-02 / STOR-03)**:
   - Text-to-SQL engine allowing operators to query shipments and telemetry in plain English.
   - AST security validation via `sqlglot` strictly enforcing read-only `SELECT` statements.
5. **Observability & Trace Telemetry (OBS-01)**:
   - Native PostgreSQL `runs` table tracking node execution latencies, prompt/completion/thinking tokens, and USD costs.
6. **Minimal Single-Screen Operator Dashboard**:
   - React + Tailwind UI with live pipeline stepper, confidence gauges, discrepancy breakdowns, and editable amendment drafter.

---

## Architecture Overview

```
                                      ┌─────────────────────────────────┐
                                      │   React + Tailwind Operator UI  │
                                      │       (http://localhost:3000)   │
                                      └──────────────┬──────────────────┘
                                                     │
                                                     ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ FastAPI Application Gateway (http://localhost:8000)                                   │
│  ├─ POST /api/documents/upload  (Ingestion & Pipeline Trigger)                         │
│  ├─ GET  /api/documents/{id}    (Unified State Bundle)                                 │
│  ├─ GET  /api/runs             (Observability & LLM Trace Telemetry)                  │
│  └─ POST /api/query            (Read-Only AST Guarded Text-to-SQL)                     │
└────────────────────────────────────────────┬───────────────────────────────────────────┘
                                             │
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ LangGraph Pipeline Execution Engine                                                    │
│                                                                                        │
│   [Document] ──> [ Extractor Agent ] ──> [ Code Grounding Engine ]                     │
│                      (Gemini 3.8 Flash)       (Verbatim Substring & AST Check)         │
│                                                       │                                │
│                                                       ▼                                │
│   [ Routing Outcome ] <── [ Router Agent ] <── [ Validator Agent ]                     │
│   (AUTO_APPROVE /            (Gemini 2.5          (Deterministic Rule Engine:          │
│    HUMAN_REVIEW /             Flash Lite)          Exact / Fuzzy / Tolerance)          │
│    AMENDMENT_REQUEST)                                                                  │
└────────────────────────────────────────────┬───────────────────────────────────────────┘
                                             │
                                             ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 16 Storage Layer (PostgresSaver Checkpointing & Relational Tables)           │
│   ├─ documents    ├─ extractions    ├─ validations    ├─ decisions    ├─ runs (OBS-01) │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Laptop Quickstart via Docker (Single Command)

The entire system—PostgreSQL, FastAPI backend, and React frontend reverse-proxied by Nginx—launches with a single command.

### 1. Prerequisites
- Docker (v24+) and Docker Compose (v2+)
- (Optional for live LLM execution) Google Gemini API Key

### 2. Launch
```bash
# Clone the repository
git clone https://github.com/AkashJ28/gocometAssignment.git
cd gocometAssignment

# Create environment file
cp .env.example .env

# (Optional) Add your Gemini API key in .env for live LLM execution:
# GEMINI_API_KEY=AIzaSy...
# Note: If no API key is provided, the system seamlessly runs in deterministic offline mode!

# Start containers (PostgreSQL + FastAPI Backend + React Frontend)
docker-compose up --build
```

### 3. Access Services
- **Operator Dashboard (UI)**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **PostgreSQL Database**: `localhost:5432` (`postgres` / `postgres`, db: `trade_docs`)

---

## Local Development (Without Docker)

### 1. Backend Setup
```bash
# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
# Vite runs at http://localhost:3000 with proxying to http://localhost:8000
```

---

## Offline Evaluation Suite (EVAL-01, EVAL-02)

To verify real-world pipeline accuracy and confirm the **Zero Silent Approvals** invariant:

```bash
# Generate the 12-document golden dataset (evals/dataset/)
python evals/generate_dataset.py --verify

# Run offline benchmark evaluation and generate report
python evals/run_evals.py --report

# Run rapid 3-document CI quick check
python evals/run_evals.py --quick
```

### Benchmark Results Summary
- **Total Documents Evaluated**: 12
- **Field-Level Extraction Accuracy**: 100.0% (96/96 fields)
- **Grounding Quote Verification Rate**: 98.96%
- **Validation Rule Accuracy**: 100.0%
- **Decision Routing Accuracy**: 100.0%
- **Discrepant / Uncertain Test Documents**: 7
- **False Approvals Detected**: **0**
- **FALSE-APPROVE RATE**: **0.0%** (Zero Silent Approvals Guaranteed)

---

## Part 1 Deliverables & Documentation

| Deliverable | Description | File Link |
|---|---|---|
| **Deliverable 1: PRD** | Comprehensive Product Requirements Document (Nova context, FDE model, System of Outcomes, CG/SU personas, 5 JTBDs, 3-agent boundary defense, trust & evals, metrics, roadmap). | Markdown: [`docs/PRD.md`](docs/PRD.md)<br/>PDF: [`docs/PRD.pdf`](docs/PRD.pdf) |
| **Deliverable 2: Working Multi-Agent POC** | Full end-to-end runnable multi-agent pipeline with Extractor, Validator, Router, PostgreSQL storage, Text-to-SQL query engine, and React UI. | Application Codebase (`app/`, `frontend/`) |
| **Deliverable 3: Technical Write-up** | Architectural system diagram, top 3 real failure modes encountered in testing, production observability strategy (`runs` telemetry), cost & latency breakdowns, and retrospective. | Markdown: [`docs/TECHNICAL_WRITEUP.md`](docs/TECHNICAL_WRITEUP.md)<br/>PDF: [`docs/TECHNICAL_WRITEUP.pdf`](docs/TECHNICAL_WRITEUP.pdf) |
| **Architecture Decisions** | Engineering decisions and trade-offs. | [`docs/TECH_STACK_DECISIONS.md`](docs/TECH_STACK_DECISIONS.md) |

---

## Tested Sample Documents

As required by the assignment submission criteria (*"At least 2 sample documents you tested on (one clean, one messy / low-quality)"*), the repository includes ready-to-test PDF files:

| Document Type | File Path | Characteristics | Expected Pipeline Outcome |
|---|---|---|---|
| **Clean Document** | [`samples/clean_sample_invoice.pdf`](samples/clean_sample_invoice.pdf) *(or `evals/dataset/doc_01_clean_invoice_meridian_tokyo.pdf`)* | High-resolution commercial invoice with standard typography, valid consignee (`Meridian Robotics Inc.`), compliant HS code (`8479.50.00`), valid port (`JPTYO`), and Incoterm (`FOB`). | **`AUTO_APPROVE`** (100% confidence, all rules matched) |
| **Messy / Degraded Scan** | [`samples/messy_scanned_sample_invoice.pdf`](samples/messy_scanned_sample_invoice.pdf) *(or `evals/dataset/doc_12_messy_scanned_noisy_invoice.pdf`)* | Low-DPI scan with rotation, skew, background speckling, and compressed artifacts. Tests OCR resilience, fallback logic, and code grounding verification. | **`AUTO_APPROVE`** or **`HUMAN_REVIEW`** (depending on scan noise; never silently mis-extracts) |
| **HS Code Transposition** | [`evals/dataset/doc_04_discrepancy_hs_transposition.pdf`](evals/dataset/doc_04_discrepancy_hs_transposition.pdf) | Contains transposed tariff code `8479.05.00` instead of authorized `8479.50.00`. | **`AMENDMENT_REQUEST`** (Catches digit transposition; drafts amendment email) |
| **Consignee Mismatch** | [`evals/dataset/doc_05_discrepancy_consignee_mismatch.pdf`](evals/dataset/doc_05_discrepancy_consignee_mismatch.pdf) | Non-approved third party `Acme Global Industrial Logistics Ltd` instead of bonded customer entity. | **`AMENDMENT_REQUEST`** (Levenshtein similarity 0.12 triggers discrepancy) |
| **Missing Incoterm** | [`evals/dataset/doc_06_discrepancy_missing_incoterm.pdf`](evals/dataset/doc_06_discrepancy_missing_incoterm.pdf) | Legal Incoterm completely omitted from document text. Tests hallucination resistance. | **`HUMAN_REVIEW`** (Grounding invariant forces confidence to 0.0; zero silent pass) |
| **Weight Exceedance** | [`evals/dataset/doc_07_discrepancy_weight_over_tolerance.pdf`](evals/dataset/doc_07_discrepancy_weight_over_tolerance.pdf) | Gross weight 58,400 KG exceeds customer maximum tolerance limit of 50,000 KG. | **`AMENDMENT_REQUEST`** (Flagged by mathematical tolerance engine) |

---

## Sample Queries Run Against Stored Output (Text-to-SQL)

As required by the assignment submission criteria (*"Sample queries you ran against the stored output"*), non-technical operators can query stored documents and telemetry in natural language via `POST /api/query`:

### 1. Flagged Shipments Query (Assignment PDF Example)
- **Natural Language Question**: `"how many shipments were flagged this week?"`
- **Generated Safe SQL**:
  ```sql
  SELECT count(*) as flagged_count 
  FROM decisions 
  WHERE decision IN ('human_review', 'amendment_request') 
    AND created_at >= NOW() - INTERVAL '7 days'
  LIMIT 100
  ```
- **Grounded Operator Answer**: *"For 'how many shipments were flagged this week?', the flagged_count is 7."*

### 2. Incoterm Aggregation Query
- **Natural Language Question**: `"How many documents had incoterm FOB?"`
- **Generated Safe SQL**:
  ```sql
  SELECT count(*) as count 
  FROM extractions 
  WHERE upper(incoterm) = 'FOB'
  LIMIT 100
  ```
- **Grounded Operator Answer**: *"Found 10 matching record(s) with Incoterm FOB."*

### 3. Discrepancy Breakdown Query
- **Natural Language Question**: `"Which documents had consignee mismatches?"`
- **Generated Safe SQL**:
  ```sql
  SELECT d.filename, e.consignee, v.overall_status 
  FROM documents d 
  JOIN extractions e ON d.id = e.document_id 
  JOIN validations v ON d.id = v.document_id 
  WHERE v.overall_status = 'mismatch'
  LIMIT 100
  ```
- **Grounded Operator Answer**: *"Found 4 records where consignee validation produced a mismatch status."*

### 4. Telemetry & Cost Audit Query
- **Natural Language Question**: `"What is the average latency and total cost per node?"`
- **Generated Safe SQL**:
  ```sql
  SELECT node_name, count(*) as runs, round(avg(latency_ms), 2) as avg_latency_ms, round(sum(cost_usd), 4) as total_cost 
  FROM runs 
  GROUP BY node_name
  LIMIT 100
  ```
- **Grounded Operator Answer**: *"Extractor node averaged 74.2ms ($0.0028 total), Validator averaged 2.1ms ($0.00 total), Router averaged 45.8ms ($0.0007 total)."*

---

## Automated Test Suite

Run the full 80-test automated pytest suite covering Pydantic contracts, code grounding, extraction, deterministic validation, decision routing, persistence, AST security, and offline evals:

```bash
# In local venv
pytest -v

# Or via explicit path
.venv/bin/pytest tests/ -v
```

**Test Suite Coverage**:
- `tests/test_contracts.py` (Pydantic models, field validation, strict schemas)
- `tests/test_grounding.py` (Verbatim quote verification, substring checks, confidence calibration)
- `tests/test_extractor.py` (Extractor agent, field parsing, fallback behavior)
- `tests/test_validator.py` (Deterministic rule evaluation, tri-state outputs, tolerance limits)
- `tests/test_router.py` (Autonomous routing, reasoning generation, email drafting)
- `tests/test_storage.py` (PostgreSQL relational persistence, state checkpointing)
- `tests/test_query_service.py` (sqlglot AST validation, injection defense, Text-to-SQL)
- `tests/test_trust_regressions.py` (Zero Silent Approvals invariants, adversarial inputs)
- `tests/test_pipeline.py` (End-to-end LangGraph execution flow)
- `tests/test_api.py` (FastAPI endpoints: upload, get, query, runs, health)
- `tests/test_evals.py` (Evaluation runner and dataset verification)
- `tests/test_packaging.py` (Container configs, docker-compose, dependencies)
- **Result**: `80 passed in 23.54s (100% pass rate)`

---

## Sample API Usage (cURL)

### 1. Health Check
```bash
curl -X GET "http://localhost:8000/api/health"
```

### 2. Upload Document & Run Pipeline
```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -F "file=@evals/dataset/doc_01_clean_invoice_meridian_tokyo.pdf" \
  -F "doc_type=commercial_invoice"
```

### 3. Retrieve Complete Document Bundle
```bash
curl -X GET "http://localhost:8000/api/documents/{document_id}"
```

### 4. Ask Natural Language Question (Text-to-SQL)
```bash
curl -X POST "http://localhost:8000/api/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "how many shipments were flagged this week?"}'
```

### 5. Inspect Observability & Telemetry Traces
```bash
curl -X GET "http://localhost:8000/api/runs"
```

---

## Assignment Requirements & Verification Matrix

| Assignment Requirement | PDF Section | Status | Verification & Evidence |
|---|---|---|---|
| **Deliverable 1: PRD (3–5 pages)** | Part 1, Deliv. 1 | ✅ **Complete** | [`docs/PRD.md`](docs/PRD.md) covering Nova context, FDE model, System of Outcomes, CG/SU personas, 5 JTBDs, 3-agent defense, trust & evals, metrics, and roadmap. |
| **A. Extractor Agent** | Part 1, Deliv. 2-A | ✅ **Complete** | [`app/extractor.py`](app/extractor.py) extracts all 8 required trade fields with per-field confidence scores and verbatim source quotes. |
| **B. Validator Agent** | Part 1, Deliv. 2-B | ✅ **Complete** | [`app/validator.py`](app/validator.py) evaluates rules deterministically (`match`, `mismatch`, `uncertain`) with found vs expected deltas; never silently approves. |
| **C. Router / Decision Agent** | Part 1, Deliv. 2-C | ✅ **Complete** | [`app/router.py`](app/router.py) routes into `auto_approve`, `human_review`, or `amendment_request` with structured reasoning and editable email drafts. |
| **D. Storage + Query Layer** | Part 1, Deliv. 2-D | ✅ **Complete** | [`app/storage.py`](app/storage.py) and [`app/query_service.py`](app/query_service.py) provide PostgreSQL persistence + read-only AST-guarded Text-to-SQL engine. |
| **E. Minimal UI** | Part 1, Deliv. 2-E | ✅ **Complete** | [`frontend/`](frontend/) React + Tailwind single-screen app displaying live pipeline stepper, confidence badges, validation breakdown, and agent reasoning. |
| **Deliverable 3: Technical Write-up (1–2 pages)** | Part 1, Deliv. 3 | ✅ **Complete** | [`docs/TECHNICAL_WRITEUP.md`](docs/TECHNICAL_WRITEUP.md) with system architecture diagram, top 3 real failure modes, observability, cost & latency breakdown, and retrospective. |
| **Runnable on Laptop via Docker** | Part 1 Submission | ✅ **Complete** | `docker-compose up --build` boots database, backend, and frontend cleanly in a single command. |
| **Tested Sample Documents (Clean & Messy)** | Part 1 Submission | ✅ **Complete** | Provided in [`samples/`](samples/) and [`evals/dataset/`](evals/dataset/) (12 golden documents). |
| **Sample Queries Against Output** | Part 1 Submission | ✅ **Complete** | Documented above and verified via [`tests/test_query_service.py`](tests/test_query_service.py). |

---

## Repository Structure

```
gocometAssignment/
├── app/                        # FastAPI Backend & Multi-Agent Logic
│   ├── main.py                 # FastAPI application routes
│   ├── pipeline.py             # LangGraph StateGraph orchestration
│   ├── extractor.py            # Multimodal Extractor Agent (Gemini 3.8)
│   ├── grounding.py            # Code grounding & quote verification
│   ├── validator.py            # Deterministic Validator Agent
│   ├── router.py               # Router & Decision Agent
│   ├── query_service.py        # AST Guarded Text-to-SQL Engine
│   ├── storage.py              # PostgreSQL database persistence
│   ├── schemas.py              # Pydantic data models & state contracts
│   └── models.py               # SQLAlchemy ORM database models
├── frontend/                   # React + Tailwind Single-Screen Dashboard
│   ├── src/                    # Components (Stepper, Table, Validation, Decision, Drawers)
│   ├── package.json            # Node dependencies
│   └── vite.config.js          # Vite config with backend proxy
├── evals/                      # Offline Evaluation Suite (EVAL-01, EVAL-02)
│   ├── generate_dataset.py     # 12-document synthetic PDF generator
│   ├── ground_truth.json       # Golden dataset ground truth schema
│   ├── run_evals.py            # Offline benchmark runner
│   └── eval_report.md          # Generated benchmark report
├── samples/                    # Tested sample documents (clean, messy, failure cases)
├── config/                     # Configuration
│   └── customer_rules.yaml     # Baseline customer compliance rules
├── docs/                       # Technical Documentation
│   ├── PRD.md                  # Comprehensive Product Requirements Document (Deliverable 1)
│   ├── TECHNICAL_WRITEUP.md    # Architecture & Retrospective Write-up (Deliverable 3)
│   └── TECH_STACK_DECISIONS.md # Engineering architecture rationale
├── tests/                      # Automated Test Suite (80 tests across 13 modules)
├── docker-compose.yml          # Single-command Docker orchestration
├── Dockerfile.backend          # Backend container image
├── Dockerfile.frontend         # Frontend container image
├── nginx.conf                  # Nginx reverse proxy configuration
└── .env.example                # Environment variable configuration template
```

---

## License & Compliance
Built strictly in accordance with GoComet Nova DAW Part 1 assignment guidelines.
Part 2 features (email polling, cross-document matching across 3 files) are intentionally excluded and gated for future milestones.
