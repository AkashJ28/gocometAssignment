# Product Requirements Document (PRD)
## GoComet Nova DAW — Multi-Agent Trade Document Pipeline (Part 1)

---

## 1. Executive Overview & Strategic Framing

### 1.1 Nova Context
GoComet Nova is an enterprise autonomous Digital Agentic Worker (DAW) platform built to automate mission-critical, friction-heavy workflows in international logistics and global freight. Rather than functioning as a passive copilot that merely offers suggestions, Nova deploys specialized, autonomous agents that take direct ownership of operational goals. In the international trade document domain, Nova ingests unstructured customs and shipping documents, parses complex tabular and legal notations, validates data against strict customer requirements, and determines downstream actions. By integrating stateful agent orchestration with deterministic enterprise controls, Nova eliminates manual operational backlogs, accelerates customs turnaround, and enforces end-to-end auditability.

### 1.2 Forward Deployed Engineer (FDE) Operational Model
The Forward Deployed Engineer (FDE) model serves as Nova’s operational and engineering bridge to enterprise customers. Rather than expecting logistics teams to adopt rigid out-of-the-box templates, FDEs embed directly within customer operations to map nuanced trade workflows, customer-specific freight contracts, and regional compliance mandates. FDEs translate these requirements into declarative, version-controlled rules (e.g., custom YAML rule definitions, consignee alias dictionaries, and port code mappings). Furthermore, FDEs analyze production edge cases, establish domain-specific golden evaluation sets, tune multi-signal confidence thresholds, and refine multi-modal extraction prompts. This high-touch engineering discipline guarantees day-one operational accuracy and accelerates time-to-value for enterprise rollouts.

### 1.3 System of Outcomes
Traditional enterprise logistics software functions as a "System of Record"—a passive repository where human coordinators manually re-key data, track statuses across disconnected portals, and bear full cognitive responsibility for catching errors. Nova transforms this paradigm into a "System of Outcomes." A System of Outcomes takes explicit responsibility for achieving concrete business results: clearing clean documents instantly, stopping compliance breaches before customs submission, and reducing demurrage liabilities. Nova achieves this through autonomous agents governed by deterministic policy rails: routine transactions clear automatically with 100% confidence, while high-risk exceptions are escalated to human operators with action-ready discrepancy breakdowns.

---

## 2. Operational Problem Statement & Failure Modes

### 2.1 The Operational Bottleneck
In global freight operations, Customer Operations Specialists (CG Operators) process hundreds of Commercial Invoices, Bills of Lading (BOL), and Packing Lists daily. Currently, every document must be manually reviewed to verify consignee legal entities, Harmonized System (HS) tariff classifications, delivery terms (Incoterms), port codes, and cargo weights against purchase orders and regulatory rules. 

Manual review suffers from significant operational vulnerabilities:
- **Fatigue and High Volume:** Human operators handling repetitive tabular documents miss subtle typographical errors.
- **Customs Holds and Demurrage Penalties:** Discrepancies identified after vessel discharge result in port customs holds. Port demurrage and container detention fees routinely range from **$150 to $500 per container per day**, rapidly accumulating into tens of thousands of dollars in avoidable losses.
- **Vessel Cut-off Misses:** In export documentation, unaddressed document mismatches lead to missed shipping line cut-offs, delaying global supply chains by weeks.

### 2.2 Critical Real-World Document Failure Modes
Nova’s trade document pipeline is specifically engineered to catch four high-frequency, high-impact document discrepancies:
1. **HS Code Digit Transposition:** A supplier invoice listing `8479.05` instead of the authorized tariff code `8479.50` (Industrial Robots). Transpositions alter duty rates and trigger regulatory penalties during customs entry filing.
2. **Subtle Consignee Entity Variations:** Invoices billed to `"Meridian Robotics LLC"` or `"Meridian Robotics Ltd."` when the legally registered customs bond requires `"Meridian Robotics Inc."`. Such discrepancies cause immediate customs bond filing rejections.
3. **Missing Incoterms:** Overseas suppliers omitting trade terms (e.g., leaving the Incoterm blank instead of specifying `FOB` or `CIF`), creating unresolved legal ambiguity regarding marine freight insurance liability and shipping cost allocation.
4. **Dual-Unit Gross Weight Discrepancies:** Documents presenting weights in imperial units (`lbs`) without unit tags, or conflicting gross weight values between header blocks and line items, causing container weight misdeclarations under SOLAS VGM (Verified Gross Mass) regulations.

### 2.3 The CG Operator 5-Minute Success Criterion
The primary operational performance benchmark for Nova Part 1 is the **5-Minute Resolution Window**:
> From the instant a trade document is ingested, the CG Operator must either:
> 1. Receive 100% verified auto-approval clearance without touching a field, OR
> 2. Receive an action-ready discrepancy summary detailing exact field mismatches (expected vs. found) alongside a pre-drafted supplier amendment email ready for single-click dispatch within **under 5 minutes**.

---

## 3. User Personas & Jobs-To-Be-Done (JTBD)

### 3.1 Target Personas

#### 1. Customer Operations Specialist (CG Operator)
- **Role:** Import/export logistics specialist at freight forwarding operations or enterprise cargo owners.
- **Responsibilities:** Auditing incoming commercial trade documents against customer master data, clearing clean shipments for customs filing, and resolving supplier discrepancies under strict port cut-off deadlines.
- **Pain Points:** Overwhelmed by repetitive data entry across fragmented PDF scans; terrified of silent approval errors that cause customs penalties; frustrated by drafting repetitive clarification emails.
- **Requirements:** Zero false approvals, transparent confidence scores with source quotes, clear tri-state validation badges, and single-click amendment actions.

#### 2. Supplier Shipping Coordinator (SU Supplier)
- **Role:** Shipping coordinator at overseas manufacturing facilities or supplier export depots.
- **Responsibilities:** Generating commercial invoices, packing lists, and transport documentation for international buyers.
- **Pain Points:** Receiving delayed, vague discrepancy inquiries days after vessel departure; multi-round email chains asking for clarifications without specifying required legal text.
- **Requirements:** Rapid, standardized, unambiguous feedback detailing exactly which field failed, the exact found value, the expected format, and the necessary corrective documentation.

### 3.2 Five Testable Jobs-To-Be-Done (JTBD) Statements

1. **JTBD 1 (Ingestion & Extraction):**
   When an SU submits a commercial trade document (PDF or scanned image),  
   I want to extract all critical customs fields with verbatim source text quotes and calibrated confidence scores,  
   so that I do not have to manually re-key shipping data into internal systems.

2. **JTBD 2 (Deterministic Rule Validation):**
   When trade document fields have been extracted,  
   I want to evaluate every field deterministically against declarative customer requirements and assign a tri-state status (`match`, `mismatch`, `uncertain`),  
   so that non-compliant shipments and subtle data discrepancies are flagged before customs filing.

3. **JTBD 3 (Zero Silent Approvals):**
   When an extracted field exhibits low confidence, ungrounded source quotes, or formatting ambiguity,  
   I want to escalate the document to human review rather than allowing the AI to guess,  
   so that no inaccurate or hallucinated trade data is ever silently approved.

4. **JTBD 4 (Automated Discrepancy Escalation):**
   When validation discrepancies or missing requirements are identified,  
   I want to generate an immediate discrepancy breakdown with expected versus found values and a pre-drafted amendment email,  
   so that I can resolve the issue with the supplier in a single click without manual drafting.

5. **JTBD 5 (Natural Language Shipment Inquiries):**
   When auditing historical trade document decisions or investigating clearance bottlenecks,  
   I want to query shipment records in plain conversational English and inspect the transparently generated SQL query,  
   so that I can verify compliance and analyze throughput without relying on database engineers.

---

## 4. Multi-Agent Architectural Boundaries

### 4.1 The Three-Agent Architecture
Nova Part 1 partitions the document pipeline into three specialized agents with distinct operational boundaries and trust profiles:

```
[ Ingested PDF / Image ]
          │
          ▼
┌────────────────────────────────────────┐
│           Extractor Agent              │
│   (Multi-Modal Perception Layer)       │
│  - Gemini 3.8 Flash (Structured JSON)  │
│  - Verbatim Text Source Quotes         │
│  - Code Grounding Verification         │
└──────────────────┬─────────────────────┘
                   │ ExtractedDoc (Pydantic)
                   ▼
┌────────────────────────────────────────┐
│           Validator Agent              │
│   (Deterministic Rule Engine)          │
│  - Pure Python Rules (YAML-driven)     │
│  - Scoped Fuzzy String Matching        │
│  - Tri-State: match/mismatch/uncertain │
└──────────────────┬─────────────────────┘
                   │ ValidationResult (Pydantic)
                   ▼
┌────────────────────────────────────────┐
│        Router / Decision Agent         │
│   (Policy Gate & Communication)        │
│  - Hard Invariant Decision Logic       │
│  - Gemini 3.5 Flash Lite (Drafting)    │
│  - Structured Reasoning Output         │
└──────────────────┬─────────────────────┘
                   │ DecisionResult (Pydantic)
                   ▼
┌────────────────────────────────────────┐
│    PostgreSQL Storage & StateSaver     │
│  - LangGraph State Checkpoint          │
│  - Documents, Extractions, Validations │
│  - Full Runs Telemetry & Audit Logs    │
└────────────────────────────────────────┘
```

### 4.2 Architectural Boundary Defense
We explicitly defend the choice of **3 agents** over both a monolithic (1-agent) architecture and an over-fragmented (5-agent) architecture:

#### Why NOT 1 Monolithic Agent?
1. **Conflated Perception and Policy:** Combining vision extraction, business rule validation, and routing decisions into a single prompt eliminates verifiable audit gates.
2. **Inability to Enforce Zero-Silent-Approval Invariants:** Monolithic LLMs hallucinate plausible field values and self-rationalize errors. Separating the Extractor from a deterministic Validator ensures the model never grades its own work.
3. **No Isolated Evaluation Surfaces:** In a monolithic architecture, a prompt change intended to improve invoice number extraction can silently degrade Incoterm validation accuracy. Isolated agents allow modular evals and independent regression testing.
4. **Inefficient Model Economics:** Perception requires multi-modal context windows (Gemini 3.8 Flash), while policy formatting and email drafting only require lightweight text models (Gemini 3.5 Flash Lite). A monolith forces top-tier pricing across all operations.

#### Why NOT 5 Fragmented Agents?
1. **Unnecessary Network and Latency Overhead:** Sub-dividing into separate OCR, Extractor, Normalizer, Validator, and Drafter agents introduces serial LLM hops, multiplying API round-trip latencies by 3x–5x.
2. **Absence of Distinct Trust Boundaries:** An agent boundary is only justified where there is a distinct trust model, execution modality, or failure regime. OCR and field parsing share the perception trust domain; policy decision and draft generation share the deterministic outcome domain.
3. **State Handoff Brittleness:** Every additional agent boundary increases the probability of schema serialization failure and compounding error propagation without providing additional safety.

---

## 5. Trust Engineering, Resilience & Failure Handling

### 5.1 Code-Level Grounding Verification
Hallucination prevention is enforced in code, not prompt instructions:
- For every extracted field, the Extractor must supply a `source_quote` representing the exact verbatim substring from the document.
- The pipeline executes an algorithmic verification check confirming that `source_quote` exists identically within the extracted raw document text.
- **The Grounding Invariant:** If `source_quote` is missing or cannot be verified in the raw document text, the system automatically sets `is_grounded = False`, coerces `value = None`, and assigns an `uncertain` validation status.

### 5.2 Multi-Signal Confidence Calibration
LLM self-reported confidence scores are notorious for overconfidence. Nova calibrates confidence by blending three independent signals:
1. **Model Self-Score:** The model's estimated confidence ($c \in [0.0, 1.0]$).
2. **Grounding Verification:** Binary outcome of code-level verbatim source quote matching.
3. **Syntactic & Format Validity:** Deterministic validation against domain syntaxes:
   - HS Code format regex (`^\d{4}\.\d{2}(\.\d{2})?$`)
   - UN/LOCODE international port registry lookup (5-letter alphanumeric code)
   - Incoterms 2020 enumeration (`FOB`, `CIF`, `DAP`, `EXW`, `CFR`, etc.)

### 5.3 LangGraph State Persistence & Crash Recovery
- The pipeline is constructed as a LangGraph `StateGraph` compiled with a persistent PostgreSQL checkpointer (`PostgresSaver` from `langgraph-checkpoint-postgres`).
- Every node execution (Extractor, Validator, Router) persists a transaction-safe state snapshot indexed by `thread_id` (document UUID).
- **Crash Recovery Protocol:** If an external LLM API times out, a worker process restarts, or a network partition occurs, the pipeline reloads state from the last committed checkpoint. It never re-extracts an already extracted document, saving latency, token expense, and preventing duplicate database records.

### 5.4 Deliberate LLM Tiering Strategy (Gemini 3.x)
In accordance with production cost and latency engineering, models are deliberately tiered:
- **Extractor Agent:** Primary model is `gemini-3.8-flash` utilizing native JSON structured schema output (`response_schema`). For degraded, low-resolution, or complex multi-column scans, the pipeline falls back to `gemini-3.1-pro-preview` or high-resolution Flash re-renders.
- **Router / Drafting Agent:** `gemini-3.5-flash-lite` generates discrepancy explanations and drafts professional supplier amendment emails. This tier is fast, exceptionally cheap, and well-suited for natural language synthesis from structured validation inputs.
- **Thinking Token Accounting:** Gemini 3.x reasoning tokens are tracked and logged explicitly in the database, ensuring full visibility into true token cost drivers.

---

## 6. Evaluation Framework & Operational Metrics

### 6.1 Core Metric Target Architecture

| Metric | Target | Measurement Methodology | Business Impact |
|---|---|---|---|
| **False-Approve Rate** | **0.0%** (Non-negotiable) | Golden eval dataset test containing known critical discrepancies. | Eliminates customs fines, detention, and demurrage penalties. |
| **Field-Level Extraction Accuracy** | **$\ge$ 95%** (Clean docs)<br>**$\ge$ 85%** (Degraded scans) | Exact match + semantic match against ground-truth field annotations. | Minimizes manual data re-keying and operator fatigue. |
| **Human Override Rate** | **$<$ 15%** | Production tracking of CG operators changing agent routing decisions. | Validates operator trust and operational automation efficiency. |
| **Pipeline Latency (P90)** | **$<$ 15 seconds** | Timestamp delta from document ingestion to final decision write. | Guarantees compliance with the 5-minute operator resolution SLA. |
| **Average Cost Per Document** | **$<$ $0.015 USD** | Cumulative token usage (input + output + thinking) logged in `runs`. | Ensures 90%+ margin over manual outsourced document processing. |

### 6.2 The North Star Metric
> **Automated Safe Clearance Rate:** The percentage of processed trade documents cleared or escalated with **zero manual field re-keying** and **zero wrongful approvals**.

---

## 7. Scope Boundaries (Part 1 vs. Part 2 Guardrails)

To preserve focus and ensure delivery of an enterprise-grade foundational pipeline, Part 1 enforces strict scope boundaries:

### In-Scope for Part 1:
- Multi-modal extraction of core trade fields (Consignee, HS Code, POL, POD, Incoterm, Description, Gross Weight, Invoice Number).
- Code-level verbatim grounding check and multi-signal confidence scoring.
- Declarative customer requirements validation (YAML rules) with tri-state status (`match`, `mismatch`, `uncertain`).
- Deterministic decision routing (`auto_approve`, `human_review`, `amendment_request`).
- Pre-drafted supplier amendment email generation for discrepancies.
- PostgreSQL persistence (Documents, Extractions, Validations, Decisions, Runs) with natural-language text-to-SQL query interface.
- Minimal operational UI displaying live pipeline state, confidence badges, validation breakdown, and agent reasoning.

### Explicitly Prohibited / Out-of-Scope (Part 2 Features — DO NOT BUILD):
- Background email polling, IMAP triggers, or automated mailbox watchers.
- Multi-document 3-way cross-validation (e.g., cross-reconciling BOL vs. Packing List vs. Commercial Invoice).
- Automated email sending or interactive in-app email client dispatch workflows.
