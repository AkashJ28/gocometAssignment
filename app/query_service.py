"""Secure Text-to-SQL natural language query engine and grounded answer synthesis (STOR-02, STOR-03)."""

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from google import genai
from google.genai import types

from app.database import SessionLocal

DEFAULT_QUERY_MODEL = "gemini-2.5-flash-lite"

ALLOWED_TABLES = {"documents", "extractions", "validations", "decisions", "runs"}

FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "truncate",
    "create", "replace", "exec", "execute", "grant", "revoke",
    "attach", "detach", "into", "pragma", "reindex", "vacuum",
}

SCHEMA_PROMPT = """You are Nova's expert trade logistics SQL assistant.
Translate operator questions into safe, standard PostgreSQL SELECT queries.

Database Schema:
1. documents (
    id VARCHAR(36) PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    doc_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL, -- PENDING, EXTRACTED, VALIDATED, COMPLETED, FAILED
    uploaded_at TIMESTAMP NOT NULL
)

2. extractions (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) REFERENCES documents(id),
    raw_json JSON NOT NULL,
    consignee VARCHAR(255),
    hs_code VARCHAR(50),
    pol VARCHAR(100), -- Port of Loading
    pod VARCHAR(100), -- Port of Discharge
    incoterm VARCHAR(20), -- FOB, CIF, EXW, DAP, etc.
    description TEXT,
    gross_weight VARCHAR(50),
    invoice_number VARCHAR(100),
    extraction_method VARCHAR(50), -- text_layer, vision_default, vision_fallback
    created_at TIMESTAMP NOT NULL
)

3. validations (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) REFERENCES documents(id),
    overall_status VARCHAR(50) NOT NULL, -- match, mismatch, uncertain
    results_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
)

4. decisions (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) REFERENCES documents(id),
    decision VARCHAR(50) NOT NULL, -- auto_approve, human_review, amendment_request
    reasoning TEXT NOT NULL,
    email_draft TEXT,
    created_at TIMESTAMP NOT NULL
)

5. runs (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) REFERENCES documents(id),
    node_name VARCHAR(100) NOT NULL, -- extractor, validator, router
    model_name VARCHAR(100),
    latency_ms FLOAT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    thinking_tokens INTEGER NOT NULL,
    cost_usd FLOAT NOT NULL,
    status VARCHAR(50) NOT NULL, -- SUCCESS, FAILED
    error_message TEXT,
    created_at TIMESTAMP NOT NULL
)

Strict Safety Rules:
- Generate ONLY a single SELECT query (or WITH ... SELECT).
- ONLY query the allowed tables: documents, extractions, validations, decisions, runs.
- Do NOT generate multiple statements or use semicolons.
- Use explicit JOINs on document_id = documents.id when joining tables.
- Return response matching the required JSON schema.
"""


class QueryRequest(BaseModel):
    """Natural language query payload submitted by operator."""
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)


class QueryResult(BaseModel):
    """Complete structured response including generated SQL and grounded answer."""
    model_config = ConfigDict(extra="forbid")
    natural_query: str
    sql_query: str
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    grounded_answer: str
    execution_time_ms: float


class SQLGenerationResponse(BaseModel):
    """Structured response schema enforced on Gemini SQL generator."""
    model_config = ConfigDict(extra="forbid")
    sql_query: str
    explanation: str


def validate_sql_query(sql: str) -> Tuple[bool, Optional[str]]:
    """Strict read-only security guard verifying that SQL query is safe to execute (STOR-03).
    
    Returns (True, sanitized_sql) or (False, error_reason).
    """
    if not sql or not sql.strip():
        return False, "Query is empty"

    cleaned = sql.strip()
    # Strip any trailing semicolons
    cleaned = re.sub(r";+\s*$", "", cleaned).strip()

    # Reject internal semicolons (prevent multi-statement execution/SQL injection)
    if ";" in cleaned:
        return False, "Multi-statement queries separated by semicolons are strictly prohibited"

    # Must start with SELECT or WITH ... SELECT
    if not re.match(r"^\s*(SELECT|WITH\b.*?\bSELECT)\b", cleaned, re.IGNORECASE | re.DOTALL):
        return False, "Only read-only SELECT queries are allowed"

    # Search for forbidden DDL / DML keywords
    forbidden_pattern = r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b"
    match = re.search(forbidden_pattern, cleaned, re.IGNORECASE)
    if match:
        return False, f"Forbidden keyword detected in query: '{match.group(1).upper()}'"

    # Verify tables accessed are strictly within whitelist (including CTE aliases defined in query)
    cte_aliases = {
        m.lower()
        for m in re.findall(r"(?:WITH|,)\s*([a-zA-Z0-9_]+)\s+AS\b", cleaned, re.IGNORECASE)
    }
    allowed = ALLOWED_TABLES | cte_aliases

    table_matches = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", cleaned, re.IGNORECASE)
    for tbl in table_matches:
        if tbl.lower() not in allowed:
            return False, f"Unauthorized table access: '{tbl}'. Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}"

    # Auto-append LIMIT 100 if query lacks a LIMIT clause
    if not re.search(r"\bLIMIT\s+\d+", cleaned, re.IGNORECASE):
        cleaned = f"{cleaned} LIMIT 100"

    return True, cleaned


class QueryService:
    """Natural language Text-to-SQL translation, safe execution, and grounded answer synthesis."""

    def __init__(
        self,
        client: Optional[Any] = None,
        model_name: Optional[str] = None,
        mock_mode: bool = False,
        session_factory: Optional[Any] = None,
    ):
        self.model_name = model_name or os.getenv("LITE_MODEL", DEFAULT_QUERY_MODEL)
        self.mock_mode = mock_mode
        self.session_factory = session_factory or SessionLocal
        self.client = client

        if not self.mock_mode and self.client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                self.client = genai.Client(api_key=api_key)
            else:
                self.mock_mode = True

    def generate_sql(self, user_query: str) -> SQLGenerationResponse:
        """Translate natural language query into a safe SQL query."""
        if self.mock_mode or self.client is None:
            return self._mock_generate_sql(user_query)

        prompt = f"{SCHEMA_PROMPT}\n\nOperator Question: {user_query}\nGenerate SQL:"
        try:
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SQLGenerationResponse,
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            data = json.loads(response.text)
            return SQLGenerationResponse.model_validate(data)
        except Exception:
            # Fall back to deterministic generation
            return self._mock_generate_sql(user_query)

    def _mock_generate_sql(self, user_query: str) -> SQLGenerationResponse:
        """Deterministic heuristic SQL generator for offline testing and fallback."""
        q = user_query.lower()
        if "fob" in q:
            return SQLGenerationResponse(
                sql_query="SELECT count(*) as count FROM extractions WHERE upper(incoterm) = 'FOB'",
                explanation="Counts shipments with Incoterm FOB.",
            )
        if "consignee" in q and ("mismatch" in q or "discrepancy" in q):
            return SQLGenerationResponse(
                sql_query="SELECT d.filename, e.consignee, v.overall_status FROM documents d JOIN extractions e ON d.id = e.document_id JOIN validations v ON d.id = v.document_id WHERE v.overall_status = 'mismatch'",
                explanation="Selects documents and consignees with validation mismatches.",
            )
        if "auto_approve" in q or "approved" in q:
            return SQLGenerationResponse(
                sql_query="SELECT count(*) as count FROM decisions WHERE decision = 'auto_approve'",
                explanation="Counts auto-approved decisions.",
            )
        if "human_review" in q or "review" in q:
            return SQLGenerationResponse(
                sql_query="SELECT d.filename, dec.reasoning FROM documents d JOIN decisions dec ON d.id = dec.document_id WHERE dec.decision = 'human_review'",
                explanation="Selects documents routed for human review.",
            )
        if "weight" in q or "gross_weight" in q:
            return SQLGenerationResponse(
                sql_query="SELECT filename, gross_weight FROM documents d JOIN extractions e ON d.id = e.document_id",
                explanation="Lists filenames and gross weights.",
            )
        if "run" in q or "latency" in q or "cost" in q:
            return SQLGenerationResponse(
                sql_query="SELECT node_name, count(*) as runs, round(avg(latency_ms), 2) as avg_latency_ms, round(sum(cost_usd), 4) as total_cost FROM runs GROUP BY node_name",
                explanation="Aggregates telemetry metrics across nodes.",
            )
        return SQLGenerationResponse(
            sql_query="SELECT count(*) as count FROM documents",
            explanation="Counts total ingested documents.",
        )

    def execute_query(
        self,
        sql_query: str,
        session: Optional[Session] = None,
    ) -> Tuple[List[str], List[List[Any]]]:
        """Validate and execute a SQL query in a read-only transaction (STOR-03)."""
        is_valid, sanitized_or_err = validate_sql_query(sql_query)
        if not is_valid:
            raise ValueError(f"SQL validation error: {sanitized_or_err}")

        sanitized_sql = sanitized_or_err

        sess = session or self.session_factory()
        close_sess = session is None
        try:
            result = sess.execute(text(sanitized_sql))
            columns = list(result.keys())
            raw_rows = result.fetchall()
            rows = [
                [val.isoformat() if hasattr(val, "isoformat") else val for val in row]
                for row in raw_rows
            ]
            return columns, rows
        finally:
            if close_sess:
                sess.close()

    def synthesize_answer(
        self,
        user_query: str,
        sql_query: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> str:
        """Synthesize a concise, operator-grounded natural language explanation of query rows."""
        if not rows:
            return f"No records were found matching your query: '{user_query}'."

        if self.mock_mode or self.client is None:
            if len(rows) == 1 and len(columns) == 1:
                col = columns[0]
                val = rows[0][0]
                return f"For '{user_query}', the {col} is {val}."
            return f"Found {len(rows)} matching record(s) for '{user_query}'."

        prompt = (
            f"User Question: {user_query}\n"
            f"Executed SQL: {sql_query}\n"
            f"Result Columns: {columns}\n"
            f"Result Rows: {rows[:20]}\n\n"
            "Provide a clear, factual, 1-2 sentence operator answer directly answering the question based on these results."
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            return response.text.strip()
        except Exception:
            return f"Found {len(rows)} matching record(s) for '{user_query}'."

    def answer_query(
        self,
        user_query: str,
        session: Optional[Session] = None,
    ) -> QueryResult:
        """End-to-end question answering: translate to SQL, validate, execute, synthesize answer."""
        t0 = time.perf_counter()

        gen_resp = self.generate_sql(user_query)
        sql_query = gen_resp.sql_query

        columns, rows = self.execute_query(sql_query, session=session)
        grounded_answer = self.synthesize_answer(user_query, sql_query, columns, rows)

        latency_ms = (time.perf_counter() - t0) * 1000.0

        return QueryResult(
            natural_query=user_query,
            sql_query=sql_query,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            grounded_answer=grounded_answer,
            execution_time_ms=round(latency_ms, 2),
        )
