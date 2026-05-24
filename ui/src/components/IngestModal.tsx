/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef } from 'react';
import { X, Sparkles, HelpCircle, Upload, FileText, CheckCircle, AlertCircle, Linkedin, Link } from 'lucide-react';

interface IngestModalProps {
  onClose: () => void;
  onIngest: (file: File) => Promise<void>;
  onIngestLinkedIn?: (url: string) => Promise<void>;
}

type Tab = 'file' | 'paste' | 'linkedin';

interface ParsedPreview {
  name: string;
  seniority: string;
  topSkills: string[];
  matchScore: number;
  complianceStatus: string;
}

function isValidLinkedInUrl(url: string): boolean {
  try {
    const parsed = new URL(url.trim());
    return (
      (parsed.hostname === 'www.linkedin.com' || parsed.hostname === 'linkedin.com') &&
      parsed.pathname.startsWith('/in/')
    );
  } catch {
    return false;
  }
}

export default function IngestModal({ onClose, onIngest, onIngestLinkedIn }: IngestModalProps) {
  const [tab, setTab] = useState<Tab>('file');

  // File tab state
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Paste tab state
  const [cvText, setCvText] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ParsedPreview | null>(null);

  // LinkedIn tab state
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [linkedinError, setLinkedinError] = useState<string | null>(null);
  const [linkedinPreview, setLinkedinPreview] = useState<ParsedPreview | null>(null);
  const [linkedinParsing, setLinkedinParsing] = useState(false);

  const [loading, setLoading] = useState(false);

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

  const handleParseCV = async () => {
    if (!cvText.trim()) return;
    setParsing(true);
    setParseError(null);
    setPreview(null);
    try {
      const res = await fetch('/api/gemini/parse-cv', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resumeText: cvText }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setPreview(data.candidate);
    } catch (e: unknown) {
      setParseError(e instanceof Error ? e.message : String(e));
    } finally {
      setParsing(false);
    }
  };

  const handlePreviewLinkedIn = async () => {
    const url = linkedinUrl.trim();
    if (!isValidLinkedInUrl(url)) {
      setLinkedinError('Please enter a valid LinkedIn profile URL (e.g. https://www.linkedin.com/in/username)');
      return;
    }
    setLinkedinError(null);
    setLinkedinPreview(null);
    setLinkedinParsing(true);
    try {
      const res = await fetch('/api/gemini/parse-linkedin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ linkedinUrl: url }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setLinkedinPreview(data.candidate);
    } catch (e: unknown) {
      setLinkedinError(e instanceof Error ? e.message : String(e));
    } finally {
      setLinkedinParsing(false);
    }
  };

  const handleSubmitFile = async (e: React.FormEvent) => {
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

  const handleSubmitPaste = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cvText.trim()) return;
    setLoading(true);
    try {
      const blob = new Blob([cvText], { type: 'text/plain' });
      const name = (preview?.name ? preview.name.replace(/\s+/g, '_') : 'pasted_cv') + '.txt';
      const syntheticFile = new File([blob], name, { type: 'text/plain' });
      await onIngest(syntheticFile);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitLinkedIn = async (e: React.FormEvent) => {
    e.preventDefault();
    const url = linkedinUrl.trim();
    if (!isValidLinkedInUrl(url)) {
      setLinkedinError('Please enter a valid LinkedIn profile URL.');
      return;
    }
    setLoading(true);
    try {
      if (onIngestLinkedIn) {
        await onIngestLinkedIn(url);
      } else {
        // Fallback: pass URL as a synthetic text file
        const blob = new Blob([url], { type: 'text/plain' });
        const syntheticFile = new File([blob], 'linkedin_url.txt', { type: 'text/plain' });
        await onIngest(syntheticFile);
      }
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const tabClass = (t: Tab) =>
    `px-4 py-2 text-xs font-bold uppercase tracking-wider border-b-2 transition-colors cursor-pointer ${
      tab === t
        ? 'border-slate-deep text-slate-deep'
        : 'border-transparent text-on-surface-variant hover:text-slate-deep'
    }`;

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

        {/* Tabs */}
        <div className="flex border-b border-border-subtle px-6 bg-white">
          <button className={tabClass('file')} onClick={() => setTab('file')}>
            <span className="flex items-center gap-1.5"><Upload className="w-3 h-3" /> Upload File</span>
          </button>
          <button className={tabClass('paste')} onClick={() => setTab('paste')}>
            <span className="flex items-center gap-1.5"><FileText className="w-3 h-3" /> Paste CV Text</span>
          </button>
          <button className={tabClass('linkedin')} onClick={() => setTab('linkedin')}>
            <span className="flex items-center gap-1.5"><Link className="w-3 h-3" /> LinkedIn URL</span>
          </button>
        </div>

        {/* Info label */}
        <div className="bg-surface-container-low px-6 py-3 border-b border-border-subtle flex items-start gap-2 text-xs text-on-surface-variant leading-relaxed">
          <HelpCircle className="w-4 h-4 text-slate-deep shrink-0 mt-0.5" />
          {tab === 'file' && (
            <p>Upload a candidate CV (<strong>.pdf</strong> or <strong>.txt</strong>). The AI extraction pipeline will parse identity, skills, and compliance fields automatically.</p>
          )}
          {tab === 'paste' && (
            <p>Paste raw CV or resume text. The AI will <strong>pre-parse</strong> fields for preview before ingestion.</p>
          )}
          {tab === 'linkedin' && (
            <p>Enter a <strong>LinkedIn profile URL</strong> (e.g. <code className="font-mono bg-white/60 px-1 rounded">linkedin.com/in/username</code>). The agent will extract and map all profile fields automatically.</p>
          )}
        </div>

        {/* File Tab */}
        {tab === 'file' && (
          <form onSubmit={handleSubmitFile} className="p-6 space-y-5">
            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                dragOver ? 'border-slate-deep bg-surface-container-low' : 'border-border-subtle hover:border-slate-deep'
              }`}
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
            <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
              <button type="button" onClick={onClose} className="px-4 py-2 border border-border-subtle rounded text-xs font-semibold hover:bg-surface-container transition-colors cursor-pointer">
                Cancel
              </button>
              <button
                type="submit"
                disabled={!file || loading}
                className="px-6 py-2 bg-slate-deep text-white rounded text-xs font-semibold hover:bg-black transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loading ? (<><span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />Extracting...</>) : 'Finalize Ingestion'}
              </button>
            </div>
          </form>
        )}

        {/* Paste Tab */}
        {tab === 'paste' && (
          <form onSubmit={handleSubmitPaste} className="p-6 space-y-4">
            <textarea
              className="w-full h-36 px-3 py-2 text-xs font-mono border border-border-subtle rounded resize-none focus:outline-none focus:ring-1 focus:ring-slate-deep bg-slate-50"
              placeholder="Paste full CV or resume text here..."
              value={cvText}
              onChange={(e) => { setCvText(e.target.value); setPreview(null); setParseError(null); }}
            />

            {cvText.trim() && !preview && (
              <button
                type="button"
                onClick={handleParseCV}
                disabled={parsing}
                className="w-full py-2 border border-amber-400 bg-amber-50 hover:bg-amber-100 text-amber-800 rounded text-xs font-bold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50"
              >
                {parsing ? (
                  <><span className="inline-block w-3 h-3 border-2 border-amber-400/40 border-t-amber-600 rounded-full animate-spin" />AI Parsing...</>
                ) : (
                  <><Sparkles className="w-3.5 h-3.5" />Preview with AI Parse</>
                )}
              </button>
            )}

            {parseError && (
              <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                <span>{parseError} — you can still ingest without preview.</span>
              </div>
            )}

            {preview && (
              <div className="p-4 bg-surface-container-low border border-border-subtle rounded space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle className="w-4 h-4 text-status-ok" />
                  <span className="text-xs font-bold text-slate-deep uppercase tracking-wider">AI Parse Preview</span>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-sans">
                  <span className="text-on-surface-variant">Name</span>
                  <span className="font-semibold text-slate-deep">{preview.name}</span>
                  <span className="text-on-surface-variant">Seniority</span>
                  <span className="font-semibold text-slate-deep">{preview.seniority}</span>
                  <span className="text-on-surface-variant">Match Score</span>
                  <span className="font-semibold text-slate-deep">{(preview.matchScore * 100).toFixed(0)}%</span>
                  <span className="text-on-surface-variant">Status</span>
                  <span className="font-semibold text-slate-deep">{preview.complianceStatus}</span>
                </div>
                {preview.topSkills?.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {preview.topSkills.map((s) => (
                      <span key={s} className="px-2 py-0.5 bg-slate-deep/10 text-slate-deep rounded text-[10px] font-mono font-bold">{s}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
              <button type="button" onClick={onClose} className="px-4 py-2 border border-border-subtle rounded text-xs font-semibold hover:bg-surface-container transition-colors cursor-pointer">
                Cancel
              </button>
              <button
                type="submit"
                disabled={!cvText.trim() || loading}
                className="px-6 py-2 bg-slate-deep text-white rounded text-xs font-semibold hover:bg-black transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loading ? (<><span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />Ingesting...</>) : 'Finalize Ingestion'}
              </button>
            </div>
          </form>
        )}

        {/* LinkedIn Tab */}
        {tab === 'linkedin' && (
          <form onSubmit={handleSubmitLinkedIn} className="p-6 space-y-4">
            {/* URL Input */}
            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold font-mono uppercase tracking-wider text-on-surface-variant">
                LinkedIn Profile URL
              </label>
              <div className={`flex items-center border rounded px-3 py-2 transition-all bg-surface-container-low gap-2 ${
                linkedinError
                  ? 'border-red-400 focus-within:ring-1 focus-within:ring-red-400'
                  : 'border-border-subtle hover:border-slate-400 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500'
              }`}>
                <Linkedin className="w-4 h-4 text-[#0A66C2] shrink-0" />
                <input
                  id="linkedin-url-input"
                  type="url"
                  placeholder="https://www.linkedin.com/in/username"
                  className="bg-transparent border-none outline-none focus:ring-0 w-full font-mono text-xs text-on-surface placeholder:text-on-surface-variant/60 focus-visible:outline-none"
                  value={linkedinUrl}
                  onChange={(e) => {
                    setLinkedinUrl(e.target.value);
                    setLinkedinError(null);
                    setLinkedinPreview(null);
                  }}
                  autoComplete="off"
                />
                {linkedinUrl && (
                  <button
                    type="button"
                    onClick={() => { setLinkedinUrl(''); setLinkedinError(null); setLinkedinPreview(null); }}
                    className="text-on-surface-variant hover:text-primary p-0.5 rounded-full transition-colors cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
              {linkedinError && (
                <p className="text-[11px] text-red-600 font-sans flex items-center gap-1">
                  <AlertCircle className="w-3 h-3 shrink-0" />{linkedinError}
                </p>
              )}
            </div>

            {/* Preview trigger */}
            {linkedinUrl.trim() && !linkedinPreview && !linkedinError && (
              <button
                type="button"
                onClick={handlePreviewLinkedIn}
                disabled={linkedinParsing || !isValidLinkedInUrl(linkedinUrl)}
                className="w-full py-2 border border-amber-400 bg-amber-50 hover:bg-amber-100 text-amber-800 rounded text-xs font-bold flex items-center justify-center gap-2 transition-colors cursor-pointer disabled:opacity-50"
              >
                {linkedinParsing ? (
                  <><span className="inline-block w-3 h-3 border-2 border-amber-400/40 border-t-amber-600 rounded-full animate-spin" />Fetching Profile…</>
                ) : (
                  <><Sparkles className="w-3.5 h-3.5" />Preview LinkedIn Profile</>
                )}
              </button>
            )}

            {/* LinkedIn parse preview */}
            {linkedinPreview && (
              <div className="p-4 bg-surface-container-low border border-border-subtle rounded space-y-2">
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle className="w-4 h-4 text-status-ok" />
                  <span className="text-xs font-bold text-slate-deep uppercase tracking-wider">Profile Preview</span>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-sans">
                  <span className="text-on-surface-variant">Name</span>
                  <span className="font-semibold text-slate-deep">{linkedinPreview.name}</span>
                  <span className="text-on-surface-variant">Seniority</span>
                  <span className="font-semibold text-slate-deep">{linkedinPreview.seniority}</span>
                  <span className="text-on-surface-variant">Match Score</span>
                  <span className="font-semibold text-slate-deep">{(linkedinPreview.matchScore * 100).toFixed(0)}%</span>
                  <span className="text-on-surface-variant">Status</span>
                  <span className="font-semibold text-slate-deep">{linkedinPreview.complianceStatus}</span>
                </div>
                {linkedinPreview.topSkills?.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {linkedinPreview.topSkills.map((s) => (
                      <span key={s} className="px-2 py-0.5 bg-slate-deep/10 text-slate-deep rounded text-[10px] font-mono font-bold">{s}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2 border-t border-border-subtle">
              <button type="button" onClick={onClose} className="px-4 py-2 border border-border-subtle rounded text-xs font-semibold hover:bg-surface-container transition-colors cursor-pointer">
                Cancel
              </button>
              <button
                type="submit"
                disabled={!linkedinUrl.trim() || loading}
                className="px-6 py-2 bg-[#0A66C2] hover:bg-[#004182] text-white rounded text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {loading ? (
                  <><span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />Extracting…</>
                ) : (
                  <><Linkedin className="w-3.5 h-3.5" />Ingest from LinkedIn</>
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
