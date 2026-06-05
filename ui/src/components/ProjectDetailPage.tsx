import { useEffect, useState } from 'react';
import { ArrowLeft, Loader2, Play } from 'lucide-react';
import * as api from '../api';
import { ProjectMatchCandidate, ProjectProspect } from '../types';

interface ProjectDetailPageProps {
  projectId: string;
  onBack: () => void;
  onToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
}

export default function ProjectDetailPage({ projectId, onBack, onToast }: ProjectDetailPageProps) {
  const [project, setProject] = useState<ProjectProspect | null>(null);
  const [matches, setMatches] = useState<ProjectMatchCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [topN, setTopN] = useState(10);

  useEffect(() => {
    setLoading(true);
    api
      .fetchProject(projectId)
      .then(setProject)
      .catch((err) => onToast(err instanceof Error ? err.message : 'Failed to load project', 'error'))
      .finally(() => setLoading(false));
  }, [projectId]);

  const runMatch = async () => {
    if (!project) return;
    setRunning(true);
    try {
      const rows = await api.runProjectMatch(project.id, topN);
      setMatches(rows);
      onToast(`Generated ${rows.length} candidate match${rows.length === 1 ? '' : 'es'}.`);
    } catch (err) {
      onToast(err instanceof Error ? err.message : 'Matching failed', 'error');
    } finally {
      setRunning(false);
    }
  };

  if (loading || !project) {
    return (
      <div className="flex h-80 flex-col items-center justify-center text-center">
        <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        <p className="mt-3 text-sm text-slate-500">Loading project…</p>
      </div>
    );
  }

  return (
    <section className="space-y-5 rounded-md border border-slate-200 bg-white p-5">
      {/* Back + header */}
      <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onBack}
            className="mb-3 inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" />
            All projects
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-semibold text-slate-950">{project.title}</h1>
            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
              {project.status}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-500">
            {project.client || 'Internal'} · {project.domain || 'Domain not set'}
          </p>
          {project.tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {project.tags.map((tag) => (
                <span key={tag} className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800">
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <span className="whitespace-nowrap">Top N</span>
            <input
              type="number"
              min={1}
              max={100}
              value={topN}
              onChange={(e) => setTopN(Math.max(1, Math.min(100, Number(e.target.value) || 10)))}
              className="h-10 w-20 rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
          </label>
          <button
            type="button"
            onClick={runMatch}
            disabled={running}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Run matching
          </button>
        </div>
      </div>

      {/* Brief + requirements */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Project brief</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{project.brief}</p>
        </div>
        <div className="space-y-3 rounded-md bg-slate-50 p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Requirements</h3>
          {([
            ['Required skills', project.requiredSkills],
            ['Nice-to-have', project.niceToHaveSkills],
            ['Seniority', project.minSeniority ? [project.minSeniority] : []],
            ['Locations', project.locations],
            ['Languages', project.languages],
          ] as [string, string[]][]).map(([label, values]) => (
            <div key={label}>
              <div className="text-xs font-medium text-slate-500">{label}</div>
              <p className="mt-1 text-sm text-slate-700">{values.length ? values.join(', ') : '—'}</p>
            </div>
          ))}
          {project.constraintsSummary && (
            <div>
              <div className="text-xs font-medium text-slate-500">Constraints</div>
              <p className="mt-1 text-sm text-slate-700">{project.constraintsSummary}</p>
            </div>
          )}
        </div>
      </div>

      {/* Matches */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-950">Candidate matches</h2>
            <p className="mt-1 text-sm text-slate-500">
              Ranked by the AI using your talent pool and project requirements.
            </p>
          </div>
          <span className="text-sm text-slate-500">{matches.length} candidates</span>
        </div>
        {matches.length === 0 ? (
          <div className="rounded-md border border-dashed border-slate-300 p-8 text-center">
            <p className="text-sm font-medium text-slate-700">No matches generated yet.</p>
            <p className="mt-1 text-sm text-slate-500">
              Run matching to see which candidates best fit this project.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {matches.map((row, index) => (
              <article key={row.id} className="rounded-md border border-slate-200 p-4">
                <div className="flex gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-sm font-semibold text-white">
                    {row.initials}
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-950">#{index + 1} {row.name}</h3>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        {Math.round(row.confidence * 100)}%
                      </span>
                      {row.status === 'shortlisted' && (
                        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800">
                          Shortlisted
                        </span>
                      )}
                    </div>
                    <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                      {row.explanation || 'No explanation returned by the AI.'}
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
