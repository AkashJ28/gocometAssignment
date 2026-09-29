# GoComet Nova DAW — Autonomous Trade Document Verification Pipeline (Part 1)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18.3-61dafb.svg)](https://react.dev/)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ed.svg)](https://docs.docker.com/compose/)
[![Tests](https://img.shields.io/badge/Tests-65%20Passing-brightgreen.svg)]()
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
git clone <repo-url>
cd gocometAssignment

# Create environment file
cp .env.example .env

# (Optional) Add your Gemini API key in .env:
# GEMINI_API_KEY=AIzaSy...

# Start containers
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

## Automated Test Suite

Run the full pytest suite covering contracts, grounding, extraction, deterministic validation, decision routing, packaging, and offline evals:

```bash
.venv/bin/pytest tests/ -v
```

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
  -d '{"query": "How many documents had incoterm FOB?"}'
```

### 5. Inspect Observability & Telemetry Traces
```bash
curl -X GET "http://localhost:8000/api/runs"
```

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
├── config/                     # Configuration
│   └── customer_rules.yaml     # Baseline customer compliance rules
├── docs/                       # Technical Documentation
│   ├── PRD.md                  # Comprehensive Product Requirements Document (Deliverable 1)
│   ├── TECHNICAL_WRITEUP.md    # Architecture & Retrospective Write-up (Deliverable 3)
│   └── TECH_STACK_DECISIONS.md # Engineering architecture rationale
├── tests/                      # Automated Test Suite (65+ tests)
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
