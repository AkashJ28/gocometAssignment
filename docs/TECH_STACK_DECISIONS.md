# GoComet Nova DAW, Part 1: Tech Stack & Design Decisions

Status as of 28 Sept 2026. Records what was decided **before** writing `schemas.py` and `customer_rules.yaml`.

---

## 1. Goal and what gets scored

Build a multi-agent trade-document pipeline: **Extractor -> Validator -> Router**, plus storage with natural-language query and a minimal UI.

| Dimension | Weight |
|---|---|
| Architecture & code quality | 20% |
| AI craft (hallucination, confidence, evals, cost/latency, observability) | 20% |
| End-to-end demo (behaviours A-E all run) | 20% |
| PRD depth & Nova understanding | 20% |
| Outcome & product thinking | 15% |
| Communication (write-up, video, README) | 5% |

Implication: spend hours on architecture, trust handling and a working chain. Keep the UI ugly but real.

---

## 2. Final tech stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Already known; Pydantic models double as agent handoff contracts |
| Orchestration | LangGraph | Explicit state handoffs between agents; built-in checkpointing |
| Crash recovery | LangGraph `PostgresSaver` (`langgraph-checkpoint-postgres`) | State checkpointed after every node; pipeline resumes from the last node |
| Database | PostgreSQL | Verified outputs, checkpoints and the `runs` trace table in one place |
| Frontend | React + Tailwind CSS | Minimal UI showing fields, per-field confidence, validation, decision, reasoning |
| Deployment | `docker-compose` (db + API + UI in one command) | Reviewers must be able to run it on a laptop |
| Observability | Own `runs` table in Postgres first; Langfuse optional | Langfuse self-hosting adds containers, cloud needs keys; a native table keeps setup simple |

### Changes from the original proposal
1. **Langfuse became optional.** Built-in `runs` table first (node, model, latency, input/output/**thinking** tokens, cost, status). Langfuse is mentioned in the write-up as the production path.
2. **Single LLM vendor (Gemini), but deliberately tiered per agent** (see section 3).
3. **Postgres kept**, shipped through `docker-compose` so reviewers need only Docker.

### Additional pieces added
- PDF **text layer first** (PyMuPDF or pdfplumber), vision only as fallback: lower cost, and a grounding source.
- **Grounding check in code** for every extracted field.
- **Rules as a YAML file** executed by plain Python, no rules library.
- **Text-to-SQL query layer**: read-only DB role, schema in the prompt, generated SQL shown next to the answer.
- **Pydantic models** as the contracts between agents.
- A small **eval script** running a golden set, reporting field accuracy and false-approve rate.

---

## 3. LLM tiering (Gemini 3.x)

All model IDs live in `.env` so they can be swapped without code changes.

| Role | Env var | Model | Notes |
|---|---|---|---|
| Extractor (default) | `EXTRACTOR_MODEL` | `gemini-3.8-flash` | Multimodal; current recommended Flash model |
| Extractor (fallback for messy docs) | `FALLBACK_MODEL` | `gemini-3.1-pro-preview` | If unavailable: retry on 3.8 Flash with a higher-resolution render and higher thinking level |
| Router reasoning, drafting, fuzzy name matching | `LITE_MODEL` | `gemini-3.5-flash-lite` | Cheapest current tier; tasks are easy |

Log which extraction path each document took (`text_layer`, `vision_default`, `vision_fallback`).

### Verified facts that forced changes (Sept 2026)
- **Gemini 1.0 and 1.5 are shut down**; requests to them return 404. The first proposal used 1.5, so it was replaced.
- **Gemini 2.5 (Pro, Flash, Flash-Lite) is scheduled to shut down on 16 Oct 2026** on the Gemini Developer API, so 2.5 was not used either.
- Google's models page recommends **3.5 Flash-Lite or 3.8 Flash** for new projects.
- **Gemini 3.x API conventions**: `temperature`, `top_k`, `top_p` are ignored by the backend, and `thinking_level="MINIMAL"` is rejected on 3.8 Flash.
- Reasoning ("thinking") tokens can dominate cost, so they are tracked separately.

### To verify before building
- Exact model IDs and free-tier access on Google's official models page. `gemini-3.1-pro-preview` was described as a preview model only by third-party sources.
- Current pricing per token, for the cost-per-document estimate.

### Consequences
- Do **not** rely on `temperature=0` for determinism. Enforce consistency with **structured output schemas** and code-level grounding checks.
- Use structured output (`response_schema`) for the Extractor. Use plain text for reasoning and email drafts.
- Add retry with backoff for rate limits, plus a hard cap on calls.

---

## 4. Why three agents

The three agents have different trust and failure profiles.

- **Extractor** is a perception task. It is the only place the LLM sees pixels, so it is the only place hallucination can enter.
- **Validator** should be mostly **deterministic code**. Rules like "Incoterm must be in {FOB, CIF}" are a rules engine. The LLM is only used for fuzzy matching such as "Acme Pvt Ltd" vs "ACME Private Limited". A separate validator also means the extractor doesn't grade its own work.
- **Router** is a policy layer. Outcome comes from deterministic thresholds. The LLM only writes the reasoning and the amendment draft.

**Why not one prompt:** a monolith can't be evaluated per stage, can't use different models per stage, and has no place to enforce "uncertain never approves."
**Why not five:** more agents add handoff cost without a new trust boundary. A separate Drafter is the natural next split.

---

## 5. Trust and failure-handling design

- **Grounding:** each field returns `value`, `confidence`, `source_quote`. Code verifies the quote exists in the document text. If not, the field becomes `null` and `uncertain`.
- **Confidence calibration:** LLM self-reported confidence is poorly calibrated. Blend three signals: model self-score, grounding check result, and format validity (HS-code regex, Incoterms enum, UN/LOCODE port lookup).
- **Null over guessing:** a missing Incoterm returns `null`, never a plausible value.
- **Routing rule:** any `uncertain` or `null` field means human review. Auto-approve requires every field to be a confident match.
- **Loop and cost control:** max 2 extraction retries, per-document token budget, LangGraph recursion limit, cost logged per run.
- **Fail loud:** pipeline errors set status `FAILED` and never fall through to approval.

---

## 6. Testing and evals

Plant failures on purpose so the write-up has real examples:
- Transposed digit in the HS code.
- "Ltd" vs "Limited" in the consignee name.
- Missing Incoterm (does the agent invent one?).
- Gross weight shown in both kg and lbs.

Documents needed: one clean PDF and one messy (photographed, rotated, low-resolution).

- **Offline eval:** golden set of about 10-15 labelled docs. Metrics: field-level accuracy and **false-approve rate** (bad docs auto-approved).
- **Online metric:** human-override rate.
- **North-star candidates** (pick one measurable number):
  - "% of shipments where the agent's decision matches the CG's final decision with no edits."
  - "% of docs cleared without a human reading fields, with zero wrong approvals" (bolder; needs the zero-wrong-approvals guardrail).

---

## 7. Design for Part 2 (built in from day one)

Model `shipment -> documents[]` with a `doc_type` field, even though Part 1 processes one document at a time. Cross-document validation in Part 2 then extends the design instead of rewriting it. Part 2 also requires that the agent never sends emails itself; CG always reviews and sends.

---

## 8. Rough time budget (about 12 hours)

| Hours | Work |
|---|---|
| 1 | Nova concepts and PRD skeleton |
| 3 | Extractor plus grounding |
| 2 | Validator and rules |
| 1.5 | Router and drafts |
| 1.5 | Storage and NL query |
| 1 | UI |
| 2 | Testing, demo video, write-up |

---

## 9. Reminders for the submission

- **Write the Nova / FDE / System of Outcomes answers yourself** (max 200 words each, in your own words). They count toward the 20% PRD weight and copy-paste is detectable.
- Deliverables: PRD (3-5 pages), working POC covering behaviours A-E, technical write-up (1-2 pages), README with laptop setup, 2+ sample documents (one messy), 2-3 minute demo video, sample queries.
- Avoid unsupported claims in the PRD (for example about matching GoComet's existing infrastructure) unless the JD says so. Justify each choice by design reasoning.
- Strip any leftover citation markers such as `[cite: 1, 2]` from copied text.

---

## 10. Files created so far

- `schemas.py`: Pydantic handoff contracts and the `RunLog` model.
- `customer_rules.yaml`: sample customer rule set (Meridian Robotics).

## 11. Next steps

1. Extractor with grounding check (riskiest piece, feeds everything else), or
2. Router's deterministic policy function (short).
3. Then Validator, storage + NL query, UI, eval script, docs.
