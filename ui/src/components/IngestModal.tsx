import { ChangeEvent, FormEvent, useMemo, useState } from 'react';
import { FileText, Link as LinkIcon, Loader2, ScanText, Upload, X } from 'lucide-react';
import * as api from '../api';
import { CandidatePreview } from '../types';

interface IngestModalProps {
  onClose: () => void;
  onIngestFile: (file: File) => Promise<void>;
  onIngestLinkedIn: (linkedinUrl: string) => Promise<void>;
}

type Mode = 'file' | 'text' | 'linkedin';

function Preview({ candidate }: { candidate: CandidatePreview | null }) {
  if (!candidate) {
    return (
      <div className="rounded-md border border-dashed border-slate-300 p-5 text-sm text-slate-500">
        Preview extraction before ingesting to confirm the candidate identity, seniority, and confidence.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-slate-950">{candidate.name}</p>
          <p className="mt-1 text-sm text-slate-500">{candidate.seniority}</p>
        </div>
        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
          {Math.round(candidate.matchScore * 100)}%
        </span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {candidate.topSkills.map((skill) => (
          <span key={skill} className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800">{skill}</span>
        ))}
      </div>
      <p className="mt-3 text-xs font-medium text-amber-700">{candidate.complianceStatus}</p>
    </div>
  );
}

export default function IngestModal({ onClose, onIngestFile, onIngestLinkedIn }: IngestModalProps) {
  const [mode, setMode] = useState<Mode>('file');
  const [file, setFile] = useState<File | null>(null);
  const [resumeText, setResumeText] = useState('');
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [preview, setPreview] = useState<CandidatePreview | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canPreview = useMemo(() => {
    if (mode === 'text') return resumeText.trim().length > 20;
    if (mode === 'linkedin') return linkedinUrl.trim().length > 0;
    return false;
  }, [linkedinUrl, mode, resumeText]);

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] || null;
    setFile(nextFile);
    setPreview(null);
    setError(null);
  };

  const runPreview = async () => {
    if (!canPreview) return;
    setLoadingPreview(true);
    setError(null);
    try {
      const result = mode === 'linkedin'
        ? await api.previewLinkedIn(linkedinUrl.trim())
        : await api.previewCV(resumeText.trim());
      setPreview(result.candidate);
    } catch (previewError) {
      setError(previewError instanceof Error ? previewError.message : 'Preview failed');
    } finally {
      setLoadingPreview(false);
    }
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (mode === 'linkedin') {
        await onIngestLinkedIn(linkedinUrl.trim());
      } else if (mode === 'text') {
        const blob = new Blob([resumeText], { type: 'text/plain' });
        await onIngestFile(new File([blob], 'pasted-cv.txt', { type: 'text/plain' }));
      } else if (file) {
        await onIngestFile(file);
      } else {
        setError('Choose a PDF or TXT file before ingesting.');
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Ingest failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="flex max-h-[92vh] w-full max-w-3xl flex-col overflow-hidden rounded-md bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">Ingest Candidate</h2>
            <p className="mt-1 text-sm text-slate-500">Add CV text, a supported file, or a provided LinkedIn profile URL.</p>
          </div>
          <button
            type="button"
            aria-label="Close ingest modal"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={submit} className="overflow-y-auto p-5">
          <div className="grid gap-2 sm:grid-cols-3">
            {[
              { id: 'file', label: 'File', icon: Upload },
              { id: 'text', label: 'Pasted CV', icon: ScanText },
              { id: 'linkedin', label: 'LinkedIn URL', icon: LinkIcon },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setMode(item.id as Mode);
                    setPreview(null);
                    setError(null);
                  }}
                  className={`flex h-11 items-center justify-center gap-2 rounded-md border text-sm font-medium ${
                    mode === item.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[1fr_280px]">
            <div>
              {mode === 'file' && (
                <label className="flex min-h-52 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-slate-300 bg-slate-50 p-6 text-center hover:bg-slate-100">
                  <FileText className="h-9 w-9 text-slate-400" />
                  <span className="mt-3 text-sm font-medium text-slate-700">{file ? file.name : 'Choose a PDF or TXT file'}</span>
                  <span className="mt-1 text-sm text-slate-500">The backend validates file type and stores provenance.</span>
                  <input type="file" accept=".pdf,.txt" onChange={selectFile} className="sr-only" />
                </label>
              )}

              {mode === 'text' && (
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">CV text</span>
                  <textarea
                    value={resumeText}
                    onChange={(event) => {
                      setResumeText(event.target.value);
                      setPreview(null);
                    }}
                    rows={12}
                    placeholder="Paste candidate CV text here"
                    className="mt-1 w-full rounded-md border border-slate-200 p-3 text-sm leading-6 outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                  />
                </label>
              )}

              {mode === 'linkedin' && (
                <label className="block">
                  <span className="text-xs font-medium uppercase tracking-wide text-slate-500">LinkedIn profile URL</span>
                  <input
                    value={linkedinUrl}
                    onChange={(event) => {
                      setLinkedinUrl(event.target.value);
                      setPreview(null);
                    }}
                    placeholder="https://www.linkedin.com/in/profile"
                    className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                  />
                  <p className="mt-2 text-sm leading-6 text-slate-500">
                    The app records the provided URL and creates a review item. It does not scrape LinkedIn.
                  </p>
                </label>
              )}
            </div>

            <div className="space-y-3">
              <Preview candidate={preview} />
              {mode !== 'file' && (
                <button
                  type="button"
                  disabled={!canPreview || loadingPreview}
                  onClick={runPreview}
                  className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {loadingPreview ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanText className="h-4 w-4" />}
                  Preview extraction
                </button>
              )}
            </div>
          </div>

          {error && <div className="mt-4 rounded-md bg-rose-50 p-3 text-sm text-rose-700">{error}</div>}

          <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-slate-200 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="h-10 rounded-md border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || (mode === 'file' && !file) || (mode === 'text' && resumeText.trim().length < 20) || (mode === 'linkedin' && !linkedinUrl.trim())}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
              Add to pool
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
