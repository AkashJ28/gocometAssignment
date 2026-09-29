"""LangGraph StateGraph orchestration pipeline for GoComet Nova trade document verification."""

import os
import time
import uuid
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from app.database import DATABASE_URL
from app.extractor import ExtractorAgent
from app.router import RouterAgent
from app.schemas import (
    ExtractedDoc,
    ValidationResult,
    DecisionResult,
    RunTrace,
)
from app.storage import StorageService
from app.validator import ValidatorAgent


class PipelineState(TypedDict, total=False):
    """Unified state schema flowing through the LangGraph StateGraph pipeline."""
    document_id: str
    file_path: str
    file_name: str
    mime_type: str
    raw_text: Optional[str]
    extracted_doc: Optional[Dict[str, Any]]
    validation_result: Optional[Dict[str, Any]]
    decision_result: Optional[Dict[str, Any]]
    run_traces: List[Dict[str, Any]]
    status: str  # PENDING, EXTRACTED, VALIDATED, COMPLETED, FAILED
    error: Optional[str]


def get_checkpointer(db_url: Optional[str] = None) -> BaseCheckpointSaver:
    """Instantiate a durable checkpointer (PostgresSaver if DB is available, otherwise MemorySaver)."""
    target_url = db_url or os.getenv("DATABASE_URL", DATABASE_URL)
    if target_url and (target_url.startswith("postgresql") or target_url.startswith("postgres")):
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            # Use sync context or connection pool
            saver = PostgresSaver.from_conn_string(target_url)
            saver.setup()
            return saver
        except Exception:
            # Fall back to MemorySaver if PostgreSQL is unreachable (e.g. offline testing)
            return MemorySaver()
    return MemorySaver()


def create_pipeline_graph(
    checkpointer: Optional[BaseCheckpointSaver] = None,
    storage_service: Optional[StorageService] = None,
    extractor_agent: Optional[ExtractorAgent] = None,
    validator_agent: Optional[ValidatorAgent] = None,
    router_agent: Optional[RouterAgent] = None,
):
    """Build and compile the LangGraph StateGraph pipeline (Extractor -> Validator -> Router)."""
    storage = storage_service or StorageService()
    extractor = extractor_agent or ExtractorAgent()
    validator = validator_agent or ValidatorAgent()
    router = router_agent or RouterAgent()

    def extractor_node(state: PipelineState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Node 1: Extract required trade fields using ExtractorAgent with telemetry."""
        doc_id = state.get("document_id")
        file_path = state.get("file_path")
        file_name = state.get("file_name") or (os.path.basename(file_path) if file_path else "unknown.pdf")

        if state.get("status") == "FAILED" or state.get("error"):
            return {}

        t0 = time.perf_counter()
        try:
            if not file_path or not os.path.exists(file_path):
                raise FileNotFoundError(f"Source document file not found at: {file_path}")

            with open(file_path, "rb") as f:
                file_bytes = f.read()

            extracted_doc, run_trace = extractor.extract(
                file_bytes=file_bytes,
                filename=file_name,
                document_id=doc_id,
                mime_type=state.get("mime_type"),
            )

            # Persist extraction and run trace to database
            if doc_id:
                storage.save_extraction(
                    document_id=doc_id,
                    extracted_doc=extracted_doc,
                    extraction_method=extracted_doc.extraction_method,
                )
                storage.record_run_trace(document_id=doc_id, trace=run_trace)
                storage.update_document_status(document_id=doc_id, status="EXTRACTED")

            trace_dict = run_trace.model_dump(mode="json")
            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(trace_dict)

            return {
                "extracted_doc": extracted_doc.model_dump(mode="json"),
                "raw_text": extracted_doc.raw_text,
                "run_traces": existing_traces,
                "status": "EXTRACTED",
                "error": None,
            }
        except Exception as e:
            err_msg = str(e)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            fail_trace = RunTrace(
                run_id=str(uuid.uuid4()),
                document_id=doc_id,
                node_name="extractor",
                model_name=getattr(extractor, "model_name", None),
                latency_ms=round(latency_ms, 2),
                status="FAILED",
                error_message=err_msg,
            )
            if doc_id:
                storage.record_run_trace(document_id=doc_id, trace=fail_trace, status="FAILED", error_message=err_msg)
                storage.update_document_status(document_id=doc_id, status="FAILED")

            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(fail_trace.model_dump(mode="json"))

            return {
                "status": "FAILED",
                "error": err_msg,
                "run_traces": existing_traces,
            }

    def validator_node(state: PipelineState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Node 2: Validate extracted fields against customer compliance rules."""
        if state.get("status") == "FAILED" or state.get("error"):
            return {}

        doc_id = state.get("document_id")
        raw_extracted = state.get("extracted_doc")
        if not raw_extracted:
            return {"status": "FAILED", "error": "Missing extracted document payload for validation"}

        t0 = time.perf_counter()
        try:
            extracted_doc = ExtractedDoc.model_validate(raw_extracted)
            validation_result = validator.validate(extracted_doc)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            val_trace = RunTrace(
                run_id=str(uuid.uuid4()),
                document_id=doc_id,
                node_name="validator",
                model_name="deterministic_rules_engine",
                latency_ms=round(latency_ms, 2),
                prompt_tokens=0,
                completion_tokens=0,
                thinking_tokens=0,
                cost_usd=0.0,
                status="SUCCESS",
                error_message=None,
            )

            if doc_id:
                storage.save_validation(document_id=doc_id, validation_result=validation_result)
                storage.record_run_trace(document_id=doc_id, trace=val_trace)
                storage.update_document_status(document_id=doc_id, status="VALIDATED")

            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(val_trace.model_dump(mode="json"))

            return {
                "validation_result": validation_result.model_dump(mode="json"),
                "run_traces": existing_traces,
                "status": "VALIDATED",
                "error": None,
            }
        except Exception as e:
            err_msg = str(e)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            fail_trace = RunTrace(
                run_id=str(uuid.uuid4()),
                document_id=doc_id,
                node_name="validator",
                model_name="deterministic_rules_engine",
                latency_ms=round(latency_ms, 2),
                status="FAILED",
                error_message=err_msg,
            )
            if doc_id:
                storage.record_run_trace(document_id=doc_id, trace=fail_trace, status="FAILED", error_message=err_msg)
                storage.update_document_status(document_id=doc_id, status="FAILED")

            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(fail_trace.model_dump(mode="json"))

            return {
                "status": "FAILED",
                "error": err_msg,
                "run_traces": existing_traces,
            }

    def router_node(state: PipelineState, config: Optional[RunnableConfig] = None) -> Dict[str, Any]:
        """Node 3: Determine routing decision, operator rationale, and amendment draft."""
        if state.get("status") == "FAILED" or state.get("error"):
            return {}

        doc_id = state.get("document_id")
        raw_val = state.get("validation_result")
        if not raw_val:
            return {"status": "FAILED", "error": "Missing validation result payload for routing"}

        t0 = time.perf_counter()
        try:
            validation_result = ValidationResult.model_validate(raw_val)
            extracted_doc = (
                ExtractedDoc.model_validate(state["extracted_doc"])
                if state.get("extracted_doc")
                else None
            )

            decision_result, run_trace = router.route(
                validation_result=validation_result,
                extracted_doc=extracted_doc,
                document_id=doc_id,
            )

            if doc_id:
                storage.save_decision(document_id=doc_id, decision_result=decision_result)
                storage.record_run_trace(document_id=doc_id, trace=run_trace)
                storage.update_document_status(document_id=doc_id, status="COMPLETED")

            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(run_trace.model_dump(mode="json"))

            return {
                "decision_result": decision_result.model_dump(mode="json"),
                "run_traces": existing_traces,
                "status": "COMPLETED",
                "error": None,
            }
        except Exception as e:
            err_msg = str(e)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            fail_trace = RunTrace(
                run_id=str(uuid.uuid4()),
                document_id=doc_id,
                node_name="router",
                model_name=getattr(router, "model_name", None),
                latency_ms=round(latency_ms, 2),
                status="FAILED",
                error_message=err_msg,
            )
            if doc_id:
                storage.record_run_trace(document_id=doc_id, trace=fail_trace, status="FAILED", error_message=err_msg)
                storage.update_document_status(document_id=doc_id, status="FAILED")

            existing_traces = list(state.get("run_traces") or [])
            existing_traces.append(fail_trace.model_dump(mode="json"))

            return {
                "status": "FAILED",
                "error": err_msg,
                "run_traces": existing_traces,
            }

    builder = StateGraph(PipelineState)
    builder.add_node("extractor", extractor_node)
    builder.add_node("validator", validator_node)
    builder.add_node("router", router_node)

    builder.add_edge(START, "extractor")
    builder.add_edge("extractor", "validator")
    builder.add_edge("validator", "router")
    builder.add_edge("router", END)

    return builder.compile(checkpointer=checkpointer)


# Singleton pipeline graph instance
_default_checkpointer = MemorySaver()
_default_graph = None


def get_default_graph():
    """Retrieve or initialize the default pipeline graph."""
    global _default_graph
    if _default_graph is None:
        _default_graph = create_pipeline_graph(checkpointer=_default_checkpointer)
    return _default_graph


def run_pipeline(
    document_id: str,
    file_path: str,
    mime_type: str = "application/pdf",
    file_name: Optional[str] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    storage_service: Optional[StorageService] = None,
    extractor_agent: Optional[ExtractorAgent] = None,
    validator_agent: Optional[ValidatorAgent] = None,
    router_agent: Optional[RouterAgent] = None,
) -> PipelineState:
    """Execute the full agentic verification pipeline for a document."""
    saver = checkpointer or _default_checkpointer
    graph = create_pipeline_graph(
        checkpointer=saver,
        storage_service=storage_service,
        extractor_agent=extractor_agent,
        validator_agent=validator_agent,
        router_agent=router_agent,
    )

    initial_state: PipelineState = {
        "document_id": document_id,
        "file_path": file_path,
        "mime_type": mime_type,
        "file_name": file_name or os.path.basename(file_path),
        "raw_text": None,
        "extracted_doc": None,
        "validation_result": None,
        "decision_result": None,
        "run_traces": [],
        "status": "PENDING",
        "error": None,
    }

    config = {"configurable": {"thread_id": document_id}}
    result = graph.invoke(initial_state, config=config)
    return result


def resume_pipeline(
    document_id: str,
    checkpointer: Optional[BaseCheckpointSaver] = None,
    storage_service: Optional[StorageService] = None,
    extractor_agent: Optional[ExtractorAgent] = None,
    validator_agent: Optional[ValidatorAgent] = None,
    router_agent: Optional[RouterAgent] = None,
) -> PipelineState:
    """Resume an existing pipeline run from its last saved checkpoint without re-running completed nodes."""
    saver = checkpointer or _default_checkpointer
    graph = create_pipeline_graph(
        checkpointer=saver,
        storage_service=storage_service,
        extractor_agent=extractor_agent,
        validator_agent=validator_agent,
        router_agent=router_agent,
    )

    config = {"configurable": {"thread_id": document_id}}
    checkpoint_state = graph.get_state(config)
    if not checkpoint_state or not checkpoint_state.values:
        raise ValueError(f"No checkpoint found for document thread_id '{document_id}'")

    # Resume execution with empty update or current values
    result = graph.invoke(None, config=config)
    return result
