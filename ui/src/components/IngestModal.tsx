/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef } from 'react';
import { X, Sparkles, HelpCircle, Upload } from 'lucide-react';

interface IngestModalProps {
  onClose: () => void;
  onIngest: (file: File) => Promise<void>;
}

export default function IngestModal({ onClose, onIngest }: IngestModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (f.type === 'application/pdf' || f.name.endsWith('.txt')) {
      setFile(f);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setLoading(true);
    try {
      await onIngest(file);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-xs select-none p-4">
      <div
        id="ingest-modal"
        className="bg-white border-2 border-slate-deep rounded-lg w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200"
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 bg-slate-deep text-white border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-400" />
            <h3 className="font-sans font-bold text-lg">AI Ingest Protocol</h3>
          </div>
          <button onClick={onClose} className="text-white/80 hover:text-white transition-colors cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Info label */}
        <div className="bg-surface-container-low px-6 py-3 border-b border-border-subtle flex items-start gap-2 text-xs text-on-surface-variant leading-relaxed">
          <HelpCircle className="w-4 h-4 text-slate-deep shrink-0 mt-0.5" />
          <p>
            Upload a candidate CV (<strong>.pdf</strong> or <strong>.txt</strong>). The AI extraction pipeline will parse identity, skills, and compliance fields automatically.
          </p>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-5">

          {/* Drop zone */}
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${dragOver ? 'border-slate-deep bg-surface-container-low' : 'border-border-subtle hover:border-slate-deep'}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
          >
            <Upload className="w-8 h-8 mx-auto mb-3 text-on-surface-variant" />
            {file ? (
              <div>
                <p className="font-semibold text-sm text-slate-deep">{file.name}</p>
                <p className="text-xs text-on-surface-variant mt-1">{(file.size / 1024).toFixed(1)} KB &mdash; click to replace</p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-semibold text-on-surface-variant">Drop CV here or click to browse</p>
                <p className="text-xs text-on-surface-variant mt-1">Accepted: .pdf, .txt &mdash; max 5 MB</p>
              </div>
            )}
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
            />
          </div>

          {/* Form Actions */}
          <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-border-subtle rounded text-xs font-semibold hover:bg-surface-container transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!file || loading}
              className="px-6 py-2 bg-slate-deep text-white rounded text-xs font-semibold hover:bg-black transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <>
                  <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  Extracting...
                </>
              ) : 'Finalize Ingestion'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
