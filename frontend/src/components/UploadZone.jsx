import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2, Sparkles } from 'lucide-react';

const DOC_TYPES = [
  { id: 'commercial_invoice', label: 'Commercial Invoice' },
  { id: 'bill_of_lading', label: 'Bill of Lading' },
  { id: 'packing_list', label: 'Packing List' },
];

const SAMPLE_TEMPLATES = [
  {
    name: 'Sample Clean Invoice (FOB)',
    type: 'commercial_invoice',
    content: `COMMERCIAL INVOICE
Invoice No: INV-2026-8891
Date: 2026-03-15
Exporter: ACME Industrial Exports Ltd, Shanghai, China
Consignee: Global Freight Logistics Inc, 452 Harbor Way, Long Beach, CA 90802
Port of Loading: Shanghai Port, China (CNSHA)
Port of Discharge: Port of Los Angeles, USA (USLAX)
Incoterm: FOB (Free On Board)
Description of Goods: Lithium Iron Phosphate Battery Cells Grade-A 3.2V 280Ah
Gross Weight: 14,250.00 KGS
HS Code: 8507.60.0000
Total Amount: $142,500.00 USD`,
    filename: 'sample_clean_invoice.txt',
  },
  {
    name: 'Sample Discrepant POD Invoice',
    type: 'commercial_invoice',
    content: `COMMERCIAL INVOICE
Invoice No: INV-DISC-9902
Date: 2026-03-18
Exporter: Shenzhen Precision Electronics Ltd
Consignee: Global Freight Logistics Inc
Port of Loading: Shanghai Port, China (CNSHA)
Port of Discharge: Rotterdam Port, Netherlands (NLRTM)
Incoterm: CIF (Cost, Insurance and Freight)
Description of Goods: Precision Servo Motors 400W Industrial Automation
Gross Weight: 8,400.00 KGS
HS Code: 8501.52.0000
Total Amount: $98,400.00 USD`,
    filename: 'sample_discrepant_pod.txt',
  },
  {
    name: 'Sample Uncertain Weight Doc',
    type: 'bill_of_lading',
    content: `OCEAN BILL OF LADING
B/L Number: BL-2026-7712
Shipper: Nippon Heavy Machinery Corp, Yokohama, Japan
Consignee: Global Freight Logistics Inc
Port of Loading: Port of Yokohama, Japan
Port of Discharge: Port of Los Angeles, USA (USLAX)
Terms: CIF
Cargo: CNC Milling Machine Spare Parts
Weight: Approx net wt 3200 kgs (Gross weight pending re-weigh tare verification)
HS Code: 8466.93.0000`,
    filename: 'sample_uncertain_weight.txt',
  },
];

export default function UploadZone({ onUpload, isProcessing, currentStatus }) {
  const [docType, setDocType] = useState('commercial_invoice');
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelected = (file) => {
    setSelectedFile(file);
    onUpload(file, docType);
  };

  const handleLoadSample = (sample) => {
    const blob = new Blob([sample.content], { type: 'text/plain' });
    const file = new File([blob], sample.filename, { type: 'text/plain' });
    setDocType(sample.type);
    setSelectedFile(file);
    onUpload(file, sample.type);
  };

  return (
    <div className="bg-slate-800/80 rounded-xl border border-slate-700/80 p-5 shadow-lg">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <UploadCloud className="w-4 h-4 text-sky-400" />
            Document Ingestion & Execution
          </h2>
          <p className="text-xs text-slate-400">
            Upload PDF, PNG, JPG or TXT trade documents for automated verification
          </p>
        </div>

        {/* Document Type Selector */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-slate-400 whitespace-nowrap">Document Type:</label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value)}
            disabled={isProcessing}
            className="bg-slate-900 border border-slate-700 text-xs rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-sky-500 disabled:opacity-50"
          >
            {DOC_TYPES.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Drag & Drop Box */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => !isProcessing && fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
          dragActive
            ? 'border-sky-500 bg-sky-500/10'
            : isProcessing
            ? 'border-slate-700 bg-slate-900/40 cursor-not-allowed opacity-80'
            : 'border-slate-700 hover:border-slate-500 bg-slate-900/50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp,.txt"
          className="hidden"
          disabled={isProcessing}
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleFileSelected(e.target.files[0]);
            }
          }}
        />

        {isProcessing ? (
          <div className="flex flex-col items-center justify-center py-2 gap-2">
            <Loader2 className="w-8 h-8 text-sky-400 animate-spin" />
            <span className="text-sm font-medium text-slate-200">
              {currentStatus || 'Processing Document through Multi-Agent Pipeline...'}
            </span>
            <span className="text-xs text-slate-400">
              Extracting fields &bull; Validating customer rules &bull; Deciding outcome
            </span>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-2 gap-2">
            <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-sky-400 mb-1 border border-slate-700">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div className="text-sm text-slate-300">
              <span className="font-semibold text-sky-400 hover:underline">Click to browse</span> or drag & drop trade document
            </div>
            <p className="text-xs text-slate-500">
              Supports Commercial Invoices, Bills of Lading, Packing Lists (Max 25MB)
            </p>
            {selectedFile && (
              <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-md bg-slate-800 border border-slate-700 text-xs text-sky-300">
                <FileText className="w-3.5 h-3.5" />
                <span>Last uploaded: <strong>{selectedFile.name}</strong></span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Quick-load Sample Presets */}
      <div className="mt-3 flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/80">
        <span className="text-xs text-slate-400 flex items-center gap-1">
          <Sparkles className="w-3.5 h-3.5 text-amber-400" />
          Quick Test Presets:
        </span>
        {SAMPLE_TEMPLATES.map((sample, idx) => (
          <button
            key={idx}
            type="button"
            disabled={isProcessing}
            onClick={() => handleLoadSample(sample)}
            className="text-xs px-2.5 py-1 rounded-md bg-slate-900 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition disabled:opacity-40"
          >
            {sample.name}
          </button>
        ))}
      </div>
    </div>
  );
}
