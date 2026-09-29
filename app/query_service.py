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

import sqlglot
from sqlglot import exp

DEFAULT_QUERY_MODEL = "gemini-3.5-flash-lite"

ALLOWED_TABLES = {"documents", "extractions", "validations", "decisions", "runs"}

FORBIDDEN_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_write_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "query_to_xml",
    "dblink",
    "lo_import",
    "lo_export",
    "system",
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
    sql_source: str = "llm"


class SQLGenerationResponse(BaseModel):
    """Structured response schema enforced on Gemini SQL generator."""

    sql_query: str
    explanation: str
    sql_source: str = "llm"


def validate_sql_query(sql: str) -> Tuple[bool, Optional[str]]:
    """Strict read-only AST security guard verifying that SQL query is safe to execute via sqlglot (STOR-03).
    
    Returns (True, sanitized_sql) or (False, error_reason).
    """
    if not sql or not sql.strip():
        return False, "Query is empty"

    cleaned = sql.strip().rstrip(";")

    # Reject internal semicolons (prevent multi-statement execution/SQL injection)
    if ";" in cleaned:
        return False, "Multi-statement queries separated by semicolons are strictly prohibited"

    try:
        expression = sqlglot.parse_one(cleaned, read="postgres")
    except Exception as parse_err:
        return False, f"SQL syntax error: {str(parse_err)}"

    # 1. Enforce read-only SELECT query root statement
    if not isinstance(expression, exp.Select):
        return False, f"Only read-only SELECT queries are allowed; found {expression.key.upper()}"

    # 2. Extract CTE aliases defined in query
    cte_aliases = {cte.alias_or_name.lower() for cte in expression.ctes}
    allowed_table_identifiers = ALLOWED_TABLES | cte_aliases

    # 3. Verify all tables accessed belong to allowed tables (no system tables or schemas)
    for table_expr in expression.find_all(exp.Table):
        table_name = table_expr.name.lower() if table_expr.name else ""
        schema_name = table_expr.db.lower() if table_expr.db else ""

        if schema_name in ("pg_catalog", "information_schema", "pg_toast"):
            return False, f"Access to system catalog '{schema_name}.{table_name}' is strictly prohibited"

        if table_name in ("pg_shadow", "pg_authid", "pg_user", "pg_database", "pg_tables"):
            return False, f"Unauthorized system table access: '{table_name}'"

        if table_name and table_name not in allowed_table_identifiers:
            return (
                False,
                f"Unauthorized table access: '{table_name}'. Allowed tables: {', '.join(sorted(ALLOWED_TABLES))}"
            )

    # 4. Check for forbidden function calls (e.g. pg_sleep, pg_read_file)
    for func in expression.find_all(exp.Func):
        func_name = func.sql_name().lower() if hasattr(func, "sql_name") else func.key.lower()
        if func_name in FORBIDDEN_FUNCTIONS:
            return False, f"Forbidden function detected in query: '{func_name}'"

    for anon in expression.find_all(exp.Anonymous):
        anon_name = anon.name.lower() if anon.name else ""
        if anon_name in FORBIDDEN_FUNCTIONS:
            return False, f"Forbidden function detected in query: '{anon_name}'"

    # 5. Check for disallowed DDL/DML statements
    forbidden_ast_nodes = (
        exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop,
        exp.Alter, exp.Command, exp.Transaction,
    )
    for node_type in forbidden_ast_nodes:
        if expression.find(node_type):
            return False, f"Forbidden statement type detected: {node_type.__name__}"

    # 6. Enforce LIMIT 100
    limit_expr = expression.args.get("limit")
    if not limit_expr:
        expression = expression.limit(100)

    sanitized_sql = expression.sql(dialect="postgres")
    return True, sanitized_sql


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
            resp = SQLGenerationResponse.model_validate(data)
            resp.sql_source = "llm"
            return resp
        except Exception:
            # Fall back to deterministic generation
            return self._mock_generate_sql(user_query)

    def _mock_generate_sql(self, user_query: str) -> SQLGenerationResponse:
        """Deterministic heuristic SQL generator for offline testing and fallback."""
        q = user_query.lower()
        if "flagged" in q or "flag" in q or ("shipment" in q and "week" in q):
            return SQLGenerationResponse(
                sql_query="SELECT count(*) as flagged_count FROM decisions WHERE decision IN ('human_review', 'amendment_request') AND created_at >= NOW() - INTERVAL '7 days'",
                explanation="Counts shipments flagged for human review or amendment request in the last 7 days.",
                sql_source="fallback",
            )
        if "fob" in q:
            return SQLGenerationResponse(
                sql_query="SELECT count(*) as count FROM extractions WHERE upper(incoterm) = 'FOB'",
                explanation="Counts shipments with Incoterm FOB.",
                sql_source="fallback",
            )
        if "consignee" in q and ("mismatch" in q or "discrepancy" in q):
            return SQLGenerationResponse(
                sql_query="SELECT d.filename, e.consignee, v.overall_status FROM documents d JOIN extractions e ON d.id = e.document_id JOIN validations v ON d.id = v.document_id WHERE v.overall_status = 'mismatch'",
                explanation="Selects documents and consignees with validation mismatches.",
                sql_source="fallback",
            )
        if "auto_approve" in q or "approved" in q:
            return SQLGenerationResponse(
                sql_query="SELECT count(*) as count FROM decisions WHERE decision = 'auto_approve'",
                explanation="Counts auto-approved decisions.",
                sql_source="fallback",
            )
        if "human_review" in q or "review" in q:
            return SQLGenerationResponse(
                sql_query="SELECT d.filename, dec.reasoning FROM documents d JOIN decisions dec ON d.id = dec.document_id WHERE dec.decision = 'human_review'",
                explanation="Selects documents routed for human review.",
                sql_source="fallback",
            )
        if "weight" in q or "gross_weight" in q:
            return SQLGenerationResponse(
                sql_query="SELECT filename, gross_weight FROM documents d JOIN extractions e ON d.id = e.document_id",
                explanation="Lists filenames and gross weights.",
                sql_source="fallback",
            )
        if "run" in q or "latency" in q or "cost" in q:
            return SQLGenerationResponse(
                sql_query="SELECT node_name, count(*) as runs, round(avg(latency_ms), 2) as avg_latency_ms, round(sum(cost_usd), 4) as total_cost FROM runs GROUP BY node_name",
                explanation="Aggregates telemetry metrics across nodes.",
                sql_source="fallback",
            )
        return SQLGenerationResponse(
            sql_query="SELECT count(*) as count FROM documents",
            explanation="Counts total ingested documents.",
            sql_source="fallback",
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
            # Set read-only transaction and statement timeout for safety on Postgres
            bind = getattr(sess, "bind", None)
            dialect = getattr(bind.dialect, "name", "") if bind and hasattr(bind, "dialect") else ""
            if "postgres" in dialect:
                sess.execute(text("SET TRANSACTION READ ONLY"))
                sess.execute(text("SET LOCAL statement_timeout = '5000ms'"))

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
        sql_source = gen_resp.sql_source

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
            sql_source=sql_source,
        )
