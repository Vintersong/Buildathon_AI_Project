import { useState } from 'react';
import { AlertTriangle, Check, ChevronDown, ChevronRight, Code2 } from 'lucide-react';
import { CandidateDetail } from '../types';

interface AiExtractionPanelProps {
  detail: CandidateDetail;
}

type ConfidenceTier = {
  label: string;
  bar: string;
  badge: string;
};

function confidenceTier(score: number | null): ConfidenceTier | null {
  if (score === null) return null;
  if (score >= 0.75) {
    return { label: 'HIGH', bar: 'bg-emerald-500', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200' };
  }
  if (score >= 0.5) {
    return { label: 'NEEDS VALIDATION', bar: 'bg-amber-500', badge: 'bg-amber-50 text-amber-800 ring-amber-200' };
  }
  return { label: 'LOW', bar: 'bg-rose-500', badge: 'bg-rose-50 text-rose-700 ring-rose-200' };
}

export default function AiExtractionPanel({ detail }: AiExtractionPanelProps) {
  const [showRaw, setShowRaw] = useState(false);

  const skills = detail.allSkills?.length ? detail.allSkills : (detail.topSkills || []);
  const score = detail.extractionConfidence;
  const tier = confidenceTier(score);
  const percent = Math.round((score ?? 0) * 100);

  // Frontend-derived structural completeness checks — these surface missing or
  // unverified fields directly from the extracted record (no backend call).
  const checks: { label: string; ok: boolean }[] = [
    { label: 'Seniority present', ok: Boolean(detail.seniority) },
    { label: 'Skills extracted', ok: skills.length > 0 },
    { label: 'Years of experience', ok: detail.yearsOfExperience !== null },
    { label: 'Location on file', ok: Boolean(detail.location) },
    { label: 'Contact email', ok: (detail.emails || []).length > 0 },
    { label: 'Education / degrees', ok: (detail.studyDegrees || []).length > 0 },
    { label: 'Profile summary', ok: Boolean(detail.summary) },
  ];
  const missingCount = checks.filter((check) => !check.ok).length;

  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-950">What the AI Extracted</h3>
        {tier && (
          <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${tier.badge}`}>
            {tier.label}
          </span>
        )}
      </div>

      <div className="mt-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Confidence</span>
          <div className="h-2 flex-1 rounded-full bg-slate-100">
            {tier ? (
              <div className={`h-2 rounded-full ${tier.bar}`} style={{ width: `${percent}%` }} />
            ) : null}
          </div>
          <span className="w-12 text-right text-sm font-semibold text-slate-700">
            {score === null ? 'N/A' : `${percent}%`}
          </span>
        </div>
        {score === null && (
          <p className="mt-1 text-xs text-slate-400">Extraction confidence was not scored for this record.</p>
        )}
      </div>

      <div className="mt-4">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Extracted skills</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {skills.length ? (
            skills.map((skill) => (
              <span key={skill} className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800">
                {skill}
              </span>
            ))
          ) : (
            <span className="text-sm text-slate-400">No skills extracted.</span>
          )}
        </div>
      </div>

      <div className="mt-4">
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Data completeness checks</p>
          {missingCount > 0 && (
            <span className="text-xs font-medium text-amber-700">{missingCount} need attention</span>
          )}
        </div>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2">
          {checks.map((check) => (
            <li key={check.label} className="flex items-center gap-2 text-sm">
              {check.ok ? (
                <Check className="h-4 w-4 shrink-0 text-emerald-600" />
              ) : (
                <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
              )}
              <span className={check.ok ? 'text-slate-700' : 'text-amber-800'}>{check.label}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4">
        <button
          type="button"
          onClick={() => setShowRaw((value) => !value)}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          {showRaw ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          <Code2 className="h-3.5 w-3.5" />
          {showRaw ? 'Hide raw extracted data' : 'Show raw extracted data'}
        </button>
        {showRaw && (
          <pre className="mt-2 max-h-72 overflow-auto rounded-md border border-slate-200 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100">
            {JSON.stringify(detail, null, 2)}
          </pre>
        )}
      </div>
    </section>
  );
}
