/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useRef, useState } from 'react';
import { X, Upload, Link, CheckCircle, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import * as api from '../api';
import { Candidate } from '../types';

interface ReingestPopoverProps {
  candidateId: string;
  candidateName: string;
  linkedinUrl?: string | null;
  onClose: () => void;
  onSuccess: (updated: Candidate) => void;
}

type ReingestTab = 'file' | 'linkedin';

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

export default function ReingestPopover({
  candidateId,
  candidateName,
  linkedinUrl,
  onClose,
  onSuccess,
}: ReingestPopoverProps) {
  const [tab, setTab] = useState<ReingestTab>(linkedinUrl ? 'linkedin' : 'file');
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [url, setUrl] = useState(linkedinUrl ?? '');
  const [urlError, setUrlError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = (f: File) => {
    if (f.type === 'application/pdf' || f.name.endsWith('.txt')) setFile(f);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFile(dropped);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (tab === 'linkedin') {
      if (!isValidLinkedInUrl(url)) {
        setUrlError('Enter a valid linkedin.com/in/… URL');
        return;
      }
      setUrlError(null);
    } else {
      if (!file) return;
    }

    setLoading(true);
    try {
      const source = tab === 'linkedin' ? url.trim() : file!;
      const updated = await api.reingestCandidate(candidateId, source);
      setDone(true);
      setTimeout(() => {
        onSuccess(updated);
        onClose();
      }, 1200);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const tabClass = (t: ReingestTab) =>
    `flex items-center gap-1.5 px-3 py-2 text-[10px] font-bold uppercase tracking-wider border-b-2 transition-colors cursor-pointer ${
      tab === t
        ? 'border-slate-deep text-slate-deep'
        : 'border-transparent text-on-surface-variant hover:text-slate-deep'
    }`;

  return (
    // Backdrop
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/40 backdrop-blur-xs p-4"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="bg-white border-2 border-slate-deep rounded-lg w-full max-w-sm shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 bg-slate-deep text-white">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-amber-400" />
            <div>
              <div className="text-xs font-bold">Update Profile</div>
              <div className="text-[10px] text-white/60 font-mono truncate max-w-[200px]">{candidateName}</div>
            </div>
          </div>
          <button onClick={onClose} className="text-white/70 hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border-subtle px-4 bg-white">
          <button className={tabClass('file')} onClick={() => setTab('file')}>
            <Upload className="w-3 h-3" />New CV
          </button>
          <button className={tabClass('linkedin')} onClick={() => setTab('linkedin')}>
            <Link className="w-3 h-3" />LinkedIn URL
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {tab === 'file' && (
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                dragOver ? 'border-slate-deep bg-surface-container-low' : 'border-border-subtle hover:border-slate-deep'
              }`}
              onClick={() => fileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <Upload className="w-6 h-6 mx-auto mb-2 text-on-surface-variant" />
              {file ? (
                <div>
                  <p className="font-semibold text-xs text-slate-deep">{file.name}</p>
                  <p className="text-[11px] text-on-surface-variant mt-0.5">{(file.size / 1024).toFixed(1)} KB — click to replace</p>
                </div>
              ) : (
                <div>
                  <p className="text-xs font-semibold text-on-surface-variant">Drop updated CV here or click to browse</p>
                  <p className="text-[11px] text-on-surface-variant mt-0.5">Accepted: .pdf, .txt — max 5 MB</p>
                </div>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.txt"
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
              />
            </div>
          )}

          {tab === 'linkedin' && (
            <div className="space-y-1.5">
              <label className="block text-[10px] font-bold font-mono uppercase tracking-wider text-on-surface-variant">
                LinkedIn Profile URL
              </label>
              <div className={`flex items-center border rounded px-3 py-2 gap-2 bg-surface-container-low transition-all ${
                urlError ? 'border-red-400' : 'border-border-subtle hover:border-slate-400 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-500/20'
              }`}>
                <Link className="w-3.5 h-3.5 text-[#0A66C2] shrink-0" />
                <input
                  type="url"
                  placeholder="https://www.linkedin.com/in/username"
                  className="bg-transparent border-none outline-none focus:ring-0 w-full font-mono text-xs focus-visible:outline-none"
                  value={url}
                  onChange={(e) => { setUrl(e.target.value); setUrlError(null); }}
                  autoComplete="off"
                />
                {url && (
                  <button type="button" onClick={() => { setUrl(''); setUrlError(null); }}
                    className="text-on-surface-variant hover:text-primary cursor-pointer">
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
              {urlError && (
                <p className="text-[11px] text-red-600 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3 shrink-0" />{urlError}
                </p>
              )}
              {linkedinUrl && url === linkedinUrl && (
                <p className="text-[11px] text-on-surface-variant font-mono">Current stored URL — update if changed.</p>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded text-xs text-red-800">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
              <span>{error}</span>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1 border-t border-border-subtle">
            <button type="button" onClick={onClose}
              className="px-3 py-1.5 border border-border-subtle rounded text-xs font-semibold hover:bg-surface-container transition-colors cursor-pointer">
              Cancel
            </button>
            <button
              type="submit"
              disabled={(tab === 'file' ? !file : !url.trim()) || loading || done}
              className="px-4 py-1.5 bg-slate-deep text-white rounded text-xs font-semibold hover:bg-black transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {done ? (
                <><CheckCircle className="w-3.5 h-3.5 text-green-400" />Updated!</>
              ) : loading ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" />Updating…</>
              ) : (
                <><RefreshCw className="w-3.5 h-3.5" />Re-ingest Profile</>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
