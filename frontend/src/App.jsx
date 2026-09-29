import React, { useState, useEffect } from 'react';
import {
  checkHealth,
  uploadDocument,
  getDocument,
  listDocuments,
  getRunsTelemetry,
} from './api';
import Header from './components/Header';
import UploadZone from './components/UploadZone';
import PipelineStepper from './components/PipelineStepper';
import ExtractedFieldsTable from './components/ExtractedFieldsTable';
import ValidationPanel from './components/ValidationPanel';
import DecisionCard from './components/DecisionCard';
import QueryDrawer from './components/QueryDrawer';
import TelemetryDrawer from './components/TelemetryDrawer';
import {
  FileText,
  Clock,
  CheckCircle2,
  AlertTriangle,
  MailQuestion,
  RefreshCw,
  FolderOpen,
  XCircle,
  Hash,
  Database,
  Layers,
  ArrowUpRight,
} from 'lucide-react';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function App() {
  const [healthStatus, setHealthStatus] = useState('checking');
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [activeBundle, setActiveBundle] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStatus, setProcessingStatus] = useState('');
  const [telemetry, setTelemetry] = useState(null);
  const [queryDrawerOpen, setQueryDrawerOpen] = useState(false);
  const [telemetryDrawerOpen, setTelemetryDrawerOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  // Initial load: check health and fetch documents + telemetry
  useEffect(() => {
    async function init() {
      try {
        const health = await checkHealth();
        setHealthStatus(health.status === 'healthy' ? 'healthy' : 'degraded');
      } catch (err) {
        setHealthStatus('offline');
      }

      await refreshDocumentList();
      await refreshTelemetry();
    }
    init();
  }, []);

  const refreshTelemetry = async () => {
    try {
      const data = await getRunsTelemetry(50, 0);
      setTelemetry(data.metrics);
    } catch (err) {
      console.warn('Telemetry poll failed:', err);
    }
  };

  const refreshDocumentList = async () => {
    try {
      const docs = await listDocuments(50, 0);
      setDocuments(docs);
      if (docs.length > 0 && !selectedDocId) {
        loadDocumentDetails(docs[0].id);
      }
    } catch (err) {
      console.warn('Document list poll failed:', err);
    }
  };

  const loadDocumentDetails = async (docId) => {
    setSelectedDocId(docId);
    setErrorMessage(null);
    try {
      const bundle = await getDocument(docId);
      setActiveBundle(bundle);
    } catch (err) {
      setErrorMessage(err.message || 'Failed to fetch document bundle');
    }
  };

  const handleUpload = async (file, docType) => {
    setIsProcessing(true);
    setProcessingStatus('Uploading and parsing document...');
    setErrorMessage(null);

    try {
      setProcessingStatus('Executing Multi-Agent Pipeline (Extractor -> Validator -> Router)...');
      const res = await uploadDocument(file, docType);

      if (res.bundle) {
        setActiveBundle(res.bundle);
        setSelectedDocId(res.document_id);
      } else {
        await loadDocumentDetails(res.document_id);
      }

      await refreshDocumentList();
      await refreshTelemetry();
    } catch (err) {
      setErrorMessage(err.message || 'Failed to process document');
    } finally {
      setIsProcessing(false);
      setProcessingStatus('');
    }
  };

  const getDocStatusBadge = (status) => {
    const s = (status || '').toLowerCase();
    if (s.includes('fail') || s.includes('error')) {
      return { bg: 'bg-rose-500/10 text-rose-400 border-rose-500/20', icon: XCircle, label: 'FAILED' };
    }
    if (s.includes('approve')) {
      return { bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', icon: CheckCircle2, label: 'APPROVED' };
    }
    if (s.includes('amendment')) {
      return { bg: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: MailQuestion, label: 'AMENDMENT' };
    }
    if (s.includes('complete') || s.includes('success')) {
      return { bg: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20', icon: CheckCircle2, label: 'COMPLETED' };
    }
    if (s.includes('pending')) {
      return { bg: 'bg-sky-500/10 text-sky-400 border-sky-500/20', icon: Clock, label: 'PENDING' };
    }
    return { bg: 'bg-amber-500/10 text-amber-400 border-amber-500/20', icon: AlertTriangle, label: status || 'PROCESSED' };
  };

  const activeDoc = activeBundle?.document;
  const activeStatusBadge = activeDoc ? getDocStatusBadge(activeDoc.status) : null;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-sky-500 selection:text-white">
      {/* Top Header */}
      <Header
        healthStatus={healthStatus}
        telemetry={telemetry}
        onOpenQueryDrawer={() => setQueryDrawerOpen(true)}
        onOpenTelemetryDrawer={() => setTelemetryDrawerOpen(true)}
      />

      {/* Main Workspace Layout */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Upload & Recent Documents Sidebar (4 cols) */}
        <section className="lg:col-span-4 space-y-6">
          {/* Upload Ingestion Zone */}
          <UploadZone
            onUpload={handleUpload}
            isProcessing={isProcessing}
            currentStatus={processingStatus}
          />

          {/* Document Ingestion History Sidebar */}
          <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-4 shadow-lg">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-700/60">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <FolderOpen className="w-3.5 h-3.5 text-sky-400" />
                Processed Trade Documents ({documents.length})
              </h3>
              <button
                onClick={refreshDocumentList}
                className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700 transition"
                title="Refresh Documents"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            </div>

            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
              {documents.length === 0 ? (
                <div className="p-4 text-center text-xs text-slate-500 italic">
                  No documents in database yet. Upload a document or load a sample preset.
                </div>
              ) : (
                documents.map((doc) => {
                  const isSelected = doc.id === selectedDocId;
                  const statusBadge = getDocStatusBadge(doc.status);
                  const StatusIcon = statusBadge.icon;

                  return (
                    <div
                      key={doc.id}
                      onClick={() => !isProcessing && loadDocumentDetails(doc.id)}
                      className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-slate-900 border-sky-500 shadow-sm shadow-sky-500/20 ring-1 ring-sky-500/30'
                          : 'bg-slate-900/40 border-slate-700/60 hover:bg-slate-700/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 truncate">
                          <FileText className="w-4 h-4 text-sky-400 flex-shrink-0" />
                          <span className="text-xs font-medium text-slate-200 truncate" title={doc.filename}>
                            {doc.filename}
                          </span>
                        </div>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded border flex items-center gap-1 flex-shrink-0 font-sans font-medium ${statusBadge.bg}`}
                        >
                          <StatusIcon className="w-2.5 h-2.5" />
                          {statusBadge.label}
                        </span>
                      </div>

                      <div className="mt-2 flex items-center justify-between text-[11px] text-slate-400 font-mono">
                        <span className="truncate max-w-[130px] uppercase text-[10px] text-slate-400">
                          {doc.doc_type ? doc.doc_type.replace('_', ' ') : 'document'}
                        </span>
                        <span className="text-[10px]">
                          {doc.uploaded_at ? doc.uploaded_at.replace('T', ' ').slice(0, 16) : ''}
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>

        {/* Right Column: Active Document Execution Workspace (8 cols) */}
        <section className="lg:col-span-8 space-y-6">
          {/* Global Alert Notification */}
          {errorMessage && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-start gap-2 shadow-lg">
              <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1 leading-relaxed">
                <strong>Pipeline Notice:</strong> {errorMessage}
              </div>
              <button
                onClick={() => setErrorMessage(null)}
                className="text-slate-400 hover:text-white"
              >
                &times;
              </button>
            </div>
          )}

          {/* Active Document Overview Ribbon */}
          {activeDoc && (
            <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-4 shadow-lg flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
                  <FileText className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-sm font-bold text-white tracking-tight">{activeDoc.filename}</h2>
                    {activeStatusBadge && (
                      <span className={`text-[10px] px-2 py-0.5 rounded border font-sans font-medium flex items-center gap-1 ${activeStatusBadge.bg}`}>
                        <activeStatusBadge.icon className="w-3 h-3" />
                        {activeStatusBadge.label}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                    <span>ID: <code className="text-sky-300">{activeDoc.id.slice(0, 8)}...</code></span>
                    <span>&bull;</span>
                    <span>Size: <strong className="text-slate-200">{formatBytes(activeDoc.file_size_bytes)}</strong></span>
                    <span>&bull;</span>
                    <span>Format: <strong className="text-slate-200">{activeDoc.mime_type}</strong></span>
                    {activeDoc.uploaded_at && (
                      <>
                        <span>&bull;</span>
                        <span>Uploaded: {activeDoc.uploaded_at.replace('T', ' ').slice(0, 19)}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Stepper (UI-01) */}
          <PipelineStepper bundle={activeBundle} isProcessing={isProcessing} />

          {/* Extracted Fields Table (UI-02) */}
          <ExtractedFieldsTable extraction={activeBundle?.extraction} />

          {/* Validation Panel (UI-03) */}
          <ValidationPanel validation={activeBundle?.validation} />

          {/* Decision Card (UI-04) */}
          <DecisionCard decision={activeBundle?.decision} />
        </section>
      </main>

      {/* Drawers */}
      <QueryDrawer
        isOpen={queryDrawerOpen}
        onClose={() => setQueryDrawerOpen(false)}
      />

      <TelemetryDrawer
        isOpen={telemetryDrawerOpen}
        onClose={() => setTelemetryDrawerOpen(false)}
      />
    </div>
  );
}
