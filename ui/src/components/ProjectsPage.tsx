import { FormEvent, useEffect, useState } from 'react';
import { FilePlus2, Loader2 } from 'lucide-react';
import * as api from '../api';
import { ProjectProspect } from '../types';

interface ProjectsPageProps {
  onOpenProject: (id: string) => void;
  onToast: (msg: string, type?: 'success' | 'info' | 'error') => void;
}

const emptyForm = {
  title: '',
  client: '',
  domain: '',
  brief: '',
};

export default function ProjectsPage({ onOpenProject, onToast }: ProjectsPageProps) {
  const [projects, setProjects] = useState<ProjectProspect[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const refresh = async () => {
    setLoading(true);
    try {
      const data = await api.fetchProjects();
      setProjects(data);
    } catch (err) {
      onToast(err instanceof Error ? err.message : 'Failed to load projects', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const createProject = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!form.title.trim() || !form.brief.trim()) {
      onToast('Please add a title and brief before saving.', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await api.createProject({
        title: form.title.trim(),
        client: form.client.trim() || undefined,
        domain: form.domain.trim() || undefined,
        brief: form.brief.trim(),
      });
      onToast('Project prospect created.');
      setForm(emptyForm);
      await refresh();
      onOpenProject(created.id);
    } catch (err) {
      onToast(err instanceof Error ? err.message : 'Project creation failed', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-6 pb-20 lg:grid-cols-[360px_1fr] lg:pb-0">
      {/* Create form */}
      <section className="space-y-4 rounded-md border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2">
          <FilePlus2 className="h-5 w-5 text-cyan-700" />
          <h2 className="text-base font-semibold text-slate-950">New project prospect</h2>
        </div>
        <form className="space-y-3" onSubmit={createProject}>
          {([
            ['title', 'Project title', 'AI Talent Pool Manager'],
            ['client', 'Client / internal team', 'Linnify'],
            ['domain', 'Domain', 'SaaS / HRTech'],
          ] as const).map(([key, label, placeholder]) => (
            <label key={key} className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
              <input
                value={form[key]}
                onChange={(e) => setForm((cur) => ({ ...cur, [key]: e.target.value }))}
                placeholder={placeholder}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>
          ))}
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Project brief</span>
            <textarea
              value={form.brief}
              onChange={(e) => setForm((cur) => ({ ...cur, brief: e.target.value }))}
              placeholder="Paste the project description, RFP, or opportunity details…"
              rows={5}
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
          </label>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-slate-900 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />}
            Save project
          </button>
        </form>
      </section>

      {/* Projects list */}
      <section className="rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-base font-semibold text-slate-950">Projects</h2>
          <p className="mt-1 text-sm text-slate-500">Prospects you can match against your talent pool.</p>
        </div>
        <div className="divide-y divide-slate-100">
          {loading ? (
            <p className="px-4 py-6 text-sm text-slate-500">Loading projects…</p>
          ) : projects.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-500">No projects yet. Create one to start matching candidates.</p>
          ) : (
            projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => onOpenProject(p.id)}
                className="block w-full px-4 py-3 text-left hover:bg-slate-50"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold text-slate-950">{p.title}</span>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{p.status}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-500">
                      {p.client || 'Internal'} · {p.domain || 'Domain not set'}
                    </p>
                  </div>
                  <span className="shrink-0 text-xs text-slate-400">
                    {new Date(p.updatedAt).toLocaleDateString()}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
