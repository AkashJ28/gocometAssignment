"""Persistence and storage service for trade documents, agent artifacts, and run telemetry."""

from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import sessionmaker, Session
from app.database import SessionLocal
from app.models import Document, Extraction, Validation, Decision, Run, generate_uuid
from app.schemas import ExtractedDoc, ValidationResult, DecisionResult, RunTrace


class StorageService:
    """Provides transactional persistence for documents, extractions, validations, decisions, and runs."""

    def __init__(self, session_factory: Optional[sessionmaker] = None):
        self.session_factory = session_factory or SessionLocal

    def _get_session(self) -> Session:
        return self.session_factory()

    def create_document(
        self,
        filename: str,
        file_path: str,
        file_hash: str,
        mime_type: str,
        file_size_bytes: int,
        doc_type: str = "commercial_invoice",
    ) -> Document:
        """Create and persist a new Document record."""
        session = self._get_session()
        try:
            doc = Document(
                id=generate_uuid(),
                filename=filename,
                file_path=file_path,
                file_hash=file_hash,
                mime_type=mime_type,
                file_size_bytes=file_size_bytes,
                doc_type=doc_type,
                status="PENDING",
            )
            session.add(doc)
            session.commit()
            session.refresh(doc)
            return doc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_document_status(self, document_id: str, status: str) -> Optional[Document]:
        """Update the status of an existing document."""
        session = self._get_session()
        try:
            doc = session.query(Document).filter(Document.id == document_id).first()
            if not doc:
                return None
            doc.status = status
            session.commit()
            session.refresh(doc)
            return doc
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_document(self, document_id: str) -> Optional[Document]:
        """Fetch a single Document record by id."""
        session = self._get_session()
        try:
            return session.query(Document).filter(Document.id == document_id).first()
        finally:
            session.close()

    def list_incomplete_documents(self) -> List[Document]:
        """List documents that are in an incomplete pipeline state."""
        session = self._get_session()
        try:
            return (
                session.query(Document)
                .filter(Document.status.in_(["PENDING", "EXTRACTED", "VALIDATED"]))
                .all()
            )
        finally:
            session.close()

    def save_extraction(
        self,
        document_id: str,
        extracted_doc: Union[ExtractedDoc, Dict[str, Any]],
        extraction_method: Optional[str] = None,
    ) -> Extraction:
        """Persist structured extraction results linked to a document."""
        if isinstance(extracted_doc, ExtractedDoc):
            doc_dict = extracted_doc.model_dump(mode="json")
            method = extraction_method or extracted_doc.extraction_method
            consignee_val = extracted_doc.consignee.value if extracted_doc.consignee else None
            hs_code_val = extracted_doc.hs_code.value if extracted_doc.hs_code else None
            pol_val = extracted_doc.pol.value if extracted_doc.pol else None
            pod_val = extracted_doc.pod.value if extracted_doc.pod else None
            incoterm_val = extracted_doc.incoterm.value if extracted_doc.incoterm else None
            desc_val = extracted_doc.description.value if extracted_doc.description else None
            gross_weight_val = extracted_doc.gross_weight.value if extracted_doc.gross_weight else None
            invoice_num_val = extracted_doc.invoice_number.value if extracted_doc.invoice_number else None
        else:
            doc_dict = extracted_doc
            method = extraction_method or doc_dict.get("extraction_method", "text_layer")
            consignee_val = (doc_dict.get("consignee") or {}).get("value")
            hs_code_val = (doc_dict.get("hs_code") or {}).get("value")
            pol_val = (doc_dict.get("pol") or {}).get("value")
            pod_val = (doc_dict.get("pod") or {}).get("value")
            incoterm_val = (doc_dict.get("incoterm") or {}).get("value")
            desc_val = (doc_dict.get("description") or {}).get("value")
            gross_weight_val = (doc_dict.get("gross_weight") or {}).get("value")
            invoice_num_val = (doc_dict.get("invoice_number") or {}).get("value")

        session = self._get_session()
        try:
            extraction = Extraction(
                id=generate_uuid(),
                document_id=document_id,
                raw_json=doc_dict,
                consignee=consignee_val,
                hs_code=hs_code_val,
                pol=pol_val,
                pod=pod_val,
                incoterm=incoterm_val,
                description=desc_val,
                gross_weight=gross_weight_val,
                invoice_number=invoice_num_val,
                extraction_method=method,
            )
            session.add(extraction)
            session.commit()
            session.refresh(extraction)
            return extraction
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_validation(
        self,
        document_id: str,
        validation_result: Union[ValidationResult, Dict[str, Any]],
    ) -> Validation:
        """Persist validation results linked to a document."""
        if isinstance(validation_result, ValidationResult):
            val_dict = validation_result.model_dump(mode="json")
            status = validation_result.overall_status.value if hasattr(validation_result.overall_status, "value") else str(validation_result.overall_status)
        else:
            val_dict = validation_result
            status = str(val_dict.get("overall_status", "uncertain"))

        session = self._get_session()
        try:
            val = Validation(
                id=generate_uuid(),
                document_id=document_id,
                overall_status=status,
                results_json=val_dict,
            )
            session.add(val)
            session.commit()
            session.refresh(val)
            return val
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_decision(
        self,
        document_id: str,
        decision_result: Union[DecisionResult, Dict[str, Any]],
    ) -> Decision:
        """Persist decision results and drafted responses linked to a document."""
        if isinstance(decision_result, DecisionResult):
            dec_type = decision_result.decision.value if hasattr(decision_result.decision, "value") else str(decision_result.decision)
            reasoning = decision_result.reasoning
            email_draft = decision_result.draft_amendment_email
        else:
            dec_type = str(decision_result.get("decision", "human_review"))
            reasoning = str(decision_result.get("reasoning", ""))
            email_draft = decision_result.get("draft_amendment_email")

        session = self._get_session()
        try:
            dec = Decision(
                id=generate_uuid(),
                document_id=document_id,
                decision=dec_type,
                reasoning=reasoning,
                email_draft=email_draft,
            )
            session.add(dec)
            session.commit()
            session.refresh(dec)
            return dec
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def record_run_trace(
        self,
        document_id: Optional[str],
        trace: Union[RunTrace, Dict[str, Any]],
        status: str = "SUCCESS",
        error_message: Optional[str] = None,
    ) -> Run:
        """Record fine-grained LLM and node execution telemetry in the runs table (OBS-01)."""
        if isinstance(trace, RunTrace):
            run_id = trace.run_id or generate_uuid()
            doc_id = document_id or trace.document_id
            node = trace.node_name
            model = trace.model_name
            latency = trace.latency_ms
            prompt = trace.prompt_tokens
            completion = trace.completion_tokens
            thinking = trace.thinking_tokens
            cost = trace.cost_usd
            run_status = status or trace.status
            err = error_message or trace.error_message
        else:
            run_id = trace.get("run_id") or generate_uuid()
            doc_id = document_id or trace.get("document_id")
            node = trace.get("node_name", "unknown")
            model = trace.get("model_name")
            latency = float(trace.get("latency_ms", 0.0))
            prompt = int(trace.get("prompt_tokens", 0))
            completion = int(trace.get("completion_tokens", 0))
            thinking = int(trace.get("thinking_tokens", 0))
            cost = float(trace.get("cost_usd", 0.0))
            run_status = status or trace.get("status", "SUCCESS")
            err = error_message or trace.get("error_message")

        session = self._get_session()
        try:
            run = Run(
                id=run_id,
                document_id=doc_id,
                node_name=node,
                model_name=model,
                latency_ms=latency,
                prompt_tokens=prompt,
                completion_tokens=completion,
                thinking_tokens=thinking,
                cost_usd=cost,
                status=run_status,
                error_message=err,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_document_bundle(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete unified document state including extractions, validations, decisions, and runs."""
        session = self._get_session()
        try:
            doc = session.query(Document).filter(Document.id == document_id).first()
            if not doc:
                return None

            extraction = (
                session.query(Extraction)
                .filter(Extraction.document_id == document_id)
                .order_by(Extraction.created_at.desc())
                .first()
            )
            validation = (
                session.query(Validation)
                .filter(Validation.document_id == document_id)
                .order_by(Validation.created_at.desc())
                .first()
            )
            decision = (
                session.query(Decision)
                .filter(Decision.document_id == document_id)
                .order_by(Decision.created_at.desc())
                .first()
            )
            runs = (
                session.query(Run)
                .filter(Run.document_id == document_id)
                .order_by(Run.created_at.asc())
                .all()
            )

            return {
                "document": {
                    "id": doc.id,
                    "filename": doc.filename,
                    "file_path": doc.file_path,
                    "file_hash": doc.file_hash,
                    "mime_type": doc.mime_type,
                    "file_size_bytes": doc.file_size_bytes,
                    "doc_type": doc.doc_type,
                    "status": doc.status,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                },
                "extraction": extraction.raw_json if extraction else None,
                "validation": validation.results_json if validation else None,
                "decision": {
                    "decision": decision.decision,
                    "reasoning": decision.reasoning,
                    "email_draft": decision.email_draft,
                    "created_at": decision.created_at.isoformat() if decision.created_at else None,
                }
                if decision
                else None,
                "runs": [
                    {
                        "id": r.id,
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
        finally:
            session.close()

    def list_documents(self, limit: int = 50, offset: int = 0) -> List[Document]:
        """List documents with pagination."""
        session = self._get_session()
        try:
            return (
                session.query(Document)
                .order_by(Document.uploaded_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
        finally:
            session.close()

    def list_runs(self, limit: int = 50, offset: int = 0) -> List[Run]:
        """List execution runs with pagination."""
        session = self._get_session()
        try:
            return (
                session.query(Run)
                .order_by(Run.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
        finally:
            session.close()
