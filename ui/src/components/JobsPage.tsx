import { FormEvent, useMemo, useState } from 'react';
import { Briefcase, Loader2, MailPlus, Play, Plus, Trash2 } from 'lucide-react';
import * as api from '../api';
import { JobRequirement, ShortlistCandidate } from '../types';
import { Screen } from './Sidebar';

interface JobsPageProps {
  jobs: JobRequirement[];
  searchQuery: string;
  onRefresh: () => Promise<void>;
  onToast: (message: string, type?: 'success' | 'info' | 'error') => void;
  onNavigate: (screen: Screen) => void;
}

const emptyForm = {
  title: '',
  department: 'Engineering',
  location: 'Remote',
  tags: '',
  mustHave: '',
  niceToHave: '',
};

function splitCsv(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}

function matchesQuery(job: JobRequirement, query: string) {
  const haystack = [job.title, job.department, job.location, ...job.tags].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}

export default function JobsPage({
  jobs,
  searchQuery,
  onRefresh,
  onToast,
  onNavigate,
}: JobsPageProps) {
  const [selectedId, setSelectedId] = useState<string | null>(jobs[0]?.id || null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [draftingId, setDraftingId] = useState<string | null>(null);

  const filteredJobs = useMemo(() => {
    return searchQuery.trim() ? jobs.filter((job) => matchesQuery(job, searchQuery.trim())) : jobs;
  }, [jobs, searchQuery]);

  const selectedJob = jobs.find((job) => job.id === selectedId) || filteredJobs[0] || jobs[0] || null;

  const createJob = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form.title.trim()) {
      onToast('Add a job title before saving.', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await api.createJob({
        title: form.title.trim(),
        department: form.department.trim() || 'Engineering',
        location: form.location.trim() || 'Remote',
        status: 'MATCHING',
        tags: splitCsv(form.tags),
        must_have: splitCsv(form.mustHave),
        nice_to_have: splitCsv(form.niceToHave),
      });
      onToast('Job requirement created.');
      setForm(emptyForm);
      setSelectedId(created.id);
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Job creation failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  const runShortlist = async (job: JobRequirement) => {
    setRunningId(job.id);
    try {
      const rows = await api.runShortlist(job.id);
      onToast(`Shortlist generated with ${rows.length} candidate${rows.length === 1 ? '' : 's'}.`);
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Shortlist failed', 'error');
    } finally {
      setRunningId(null);
    }
  };

  const deleteJob = async (job: JobRequirement) => {
    try {
      await api.deleteJob(job.id);
      onToast('Job requirement removed.');
      setSelectedId(null);
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Delete failed', 'error');
    }
  };

  const createDraft = async (job: JobRequirement, row: ShortlistCandidate) => {
    setDraftingId(`${job.id}:${row.id}`);
    try {
      await api.createOutreachDraft(row.id, job.id, row.name, job.title);
      onToast('Outreach draft added to human review.');
      await onRefresh();
      onNavigate('review');
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Outreach draft failed', 'error');
    } finally {
      setDraftingId(null);
    }
  };

  return (
    <div className="grid gap-6 pb-20 lg:grid-cols-[360px_1fr] lg:pb-0">
      <div className="space-y-5">
        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2">
            <Plus className="h-5 w-5 text-cyan-700" />
            <h2 className="text-base font-semibold text-slate-950">New Job Requirement</h2>
          </div>
          <form className="mt-4 space-y-3" onSubmit={createJob}>
            {[
              ['title', 'Role title', 'Senior Backend Engineer'],
              ['department', 'Department', 'Engineering'],
              ['location', 'Location', 'Cluj-Napoca / Remote'],
              ['tags', 'Tags', 'Python, FastAPI'],
              ['mustHave', 'Must-have skills', 'Python, PostgreSQL, Docker'],
              ['niceToHave', 'Nice-to-have skills', 'LLMs, Kubernetes'],
            ].map(([key, label, placeholder]) => (
              <label key={key} className="block">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
                <input
                  value={form[key as keyof typeof form]}
                  onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))}
                  placeholder={placeholder}
                  className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                />
              </label>
            ))}
            <button
              type="submit"
              disabled={saving}
              className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-slate-900 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Briefcase className="h-4 w-4" />}
              Save job
            </button>
          </form>
        </section>

        <section className="rounded-md border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <h2 className="text-base font-semibold text-slate-950">Requirements</h2>
          </div>
          <div className="divide-y divide-slate-100">
            {filteredJobs.map((job) => (
              <button
                key={job.id}
                type="button"
                onClick={() => setSelectedId(job.id)}
                className={`block w-full px-4 py-3 text-left hover:bg-slate-50 ${
                  selectedJob?.id === job.id ? 'bg-cyan-50' : 'bg-white'
                }`}
              >
                <span className="block truncate text-sm font-semibold text-slate-950">{job.title}</span>
                <span className="mt-1 block truncate text-sm text-slate-500">{job.location || 'No location'} - {job.shortlist.length} shortlisted</span>
              </button>
            ))}
            {filteredJobs.length === 0 && (
              <p className="px-4 py-8 text-sm text-slate-500">No job requirements match the current search.</p>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-md border border-slate-200 bg-white">
        {selectedJob ? (
          <div>
            <div className="flex flex-col gap-4 border-b border-slate-200 p-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="truncate text-xl font-semibold text-slate-950">{selectedJob.title}</h2>
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">{selectedJob.status}</span>
                </div>
                <p className="mt-1 text-sm text-slate-500">{selectedJob.department} - {selectedJob.location || 'Location not set'}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedJob.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-cyan-50 px-2.5 py-1 text-xs font-medium text-cyan-800">{tag}</span>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => runShortlist(selectedJob)}
                  disabled={runningId === selectedJob.id}
                  className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  {runningId === selectedJob.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  Run shortlist
                </button>
                <button
                  type="button"
                  onClick={() => deleteJob(selectedJob)}
                  className="inline-flex h-10 items-center gap-2 rounded-md border border-rose-200 px-3 text-sm font-medium text-rose-700 hover:bg-rose-50"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete
                </button>
              </div>
            </div>

            <div className="p-5">
              <div className="mb-4 flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-base font-semibold text-slate-950">Ranked Candidates</h3>
                  <p className="mt-1 text-sm text-slate-500">Evidence is generated from stored profiles and job requirements.</p>
                </div>
                <span className="text-sm text-slate-500">{selectedJob.candidatesProcessed} processed</span>
              </div>

              <div className="space-y-3">
                {selectedJob.shortlist.map((row, index) => (
                  <article key={`${selectedJob.id}-${row.id}`} className="rounded-md border border-slate-200 p-4">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div className="flex gap-3">
                        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-sm font-semibold text-white">
                          {row.initials}
                        </span>
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h4 className="font-semibold text-slate-950">#{index + 1} {row.name}</h4>
                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{Math.round(row.confidence * 100)}%</span>
                            {row.status === 'pending_review' && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Review required</span>
                            )}
                          </div>
                          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                            {row.explanation || 'No evidence returned yet.'}
                          </p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => createDraft(selectedJob, row)}
                        disabled={draftingId === `${selectedJob.id}:${row.id}`}
                        className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        {draftingId === `${selectedJob.id}:${row.id}` ? <Loader2 className="h-4 w-4 animate-spin" /> : <MailPlus className="h-4 w-4" />}
                        Draft outreach
                      </button>
                    </div>
                  </article>
                ))}
                {selectedJob.shortlist.length === 0 && (
                  <div className="rounded-md border border-dashed border-slate-300 p-8 text-center">
                    <p className="text-sm font-medium text-slate-700">No shortlist has been generated yet.</p>
                    <p className="mt-1 text-sm text-slate-500">Run the shortlist to rank active candidates for this role.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex h-80 flex-col items-center justify-center text-center">
            <Briefcase className="h-9 w-9 text-slate-300" />
            <p className="mt-3 text-sm font-medium text-slate-700">Create a job requirement to begin shortlisting.</p>
          </div>
        )}
      </section>
    </div>
  );
}
