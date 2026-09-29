"""FastAPI application entrypoint for GoComet Nova trade document verification pipeline."""

import hashlib
import os
import shutil
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import init_db, get_db
from app.models import Document
from app.pipeline import run_pipeline
from app.query_service import QueryRequest, QueryResult, QueryService
from app.storage import StorageService

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "text/plain",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler initializing schema tables and directories."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    init_db()
    yield


app = FastAPI(
    title="GoComet Nova DAW Trade Document API",
    version="1.0.0",
    description="Multi-agent trade document extraction, verification, routing, and Text-to-SQL query service.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage_service = StorageService()
query_service = QueryService()


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    """System health and service readiness check."""
    return {
        "status": "healthy",
        "database": "ready",
        "version": "1.0.0",
    }


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form("commercial_invoice"),
) -> Dict[str, Any]:
    """Upload a trade document, store metadata, execute LangGraph pipeline, and return unified bundle."""
    raw_filename = file.filename or "document.pdf"
    safe_filename = os.path.basename(raw_filename)
    mime_type = file.content_type or "application/octet-stream"

    # Normalize mime type for common extensions if sent generically
    ext = os.path.splitext(safe_filename.lower())[1]
    if mime_type == "application/octet-stream":
        if ext == ".pdf":
            mime_type = "application/pdf"
        elif ext in (".png",):
            mime_type = "image/png"
        elif ext in (".jpg", ".jpeg"):
            mime_type = "image/jpeg"
        elif ext == ".txt":
            mime_type = "text/plain"

    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported media type '{mime_type}'. Allowed types: {', '.join(sorted(ALLOWED_MIME_TYPES))}",
        )

    # Read and buffer bytes
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(status_code=400, detail="Cannot upload an empty document.")

    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum size limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
        )

    # Compute SHA-256 hash
    file_hash = hashlib.sha256(content).hexdigest()

    # Save to disk
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    saved_path = os.path.join(UPLOAD_DIR, f"{file_hash[:16]}_{safe_filename}")
    with open(saved_path, "wb") as f:
        f.write(content)

    # Create initial Document record in DB
    doc = storage_service.create_document(
        filename=safe_filename,
        file_path=saved_path,
        file_hash=file_hash,
        mime_type=mime_type,
        file_size_bytes=file_size,
        doc_type=doc_type,
    )

    # Execute LangGraph pipeline
    pipeline_result = run_pipeline(
        document_id=doc.id,
        file_path=saved_path,
        mime_type=mime_type,
        file_name=safe_filename,
        storage_service=storage_service,
    )

    bundle = storage_service.get_document_bundle(doc.id)

    return {
        "document_id": doc.id,
        "status": pipeline_result.get("status", "COMPLETED"),
        "filename": doc.filename,
        "bundle": bundle,
    }


@app.get("/api/documents/{document_id}")
def get_document(document_id: str) -> Dict[str, Any]:
    """Retrieve complete unified state for a single document."""
    bundle = storage_service.get_document_bundle(document_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found.")
    return bundle


@app.get("/api/documents")
def list_documents(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """List documents with pagination."""
    docs = storage_service.list_documents(limit=limit, offset=offset)
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_hash": d.file_hash,
            "mime_type": d.mime_type,
            "file_size_bytes": d.file_size_bytes,
            "doc_type": d.doc_type,
            "status": d.status,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
        }
        for d in docs
    ]


@app.get("/api/runs")
def get_runs(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    """List agent execution traces and aggregate telemetry metrics (OBS-01)."""
    runs = storage_service.list_runs(limit=limit, offset=offset)
    total_cost = round(sum(r.cost_usd for r in runs), 6)
    total_tokens = sum(r.prompt_tokens + r.completion_tokens + r.thinking_tokens for r in runs)
    avg_latency = round(sum(r.latency_ms for r in runs) / max(len(runs), 1), 2)

    return {
        "metrics": {
            "total_runs": len(runs),
            "total_cost_usd": total_cost,
            "total_tokens": total_tokens,
            "avg_latency_ms": avg_latency,
        },
        "runs": [
            {
                "id": r.id,
                "document_id": r.document_id,
                "node_name": r.node_name,
                "model_name": r.model_name,
                "latency_ms": r.latency_ms,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "thinking_tokens": r.thinking_tokens,
                "cost_usd": r.cost_usd,
                "status": r.status,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in runs
        ],
    }


@app.post("/api/query")
def execute_nl_query(
    request: QueryRequest,
    db: Session = Depends(get_db),
) -> QueryResult:
    """Execute natural language Text-to-SQL query with strict read-only security enforcement."""
    try:
        return query_service.answer_query(request.query, session=db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution error: {str(e)}")
