import { useEffect, useState } from 'react';
import { CheckCircle, KeyRound, Loader2, RadioTower, Save, Server, XCircle } from 'lucide-react';
import * as api from '../api';

interface SettingsPageProps {
  candidatesCount: number;
  jobsCount: number;
  tasksCount: number;
}

export default function SettingsPage({ candidatesCount, jobsCount, tasksCount }: SettingsPageProps) {
  const [config, setConfig] = useState<api.AppConfig | null>(null);
  const [lmStatus, setLmStatus] = useState<api.LmStudioStatus | null>(null);
  const [geminiKey, setGeminiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.fetchConfig(), api.fetchLmStudioStatus()])
      .then(([cfg, lm]) => {
        setConfig(cfg);
        setLmStatus(lm);
      })
      .catch((error) => setMessage(error instanceof Error ? error.message : 'Settings failed to load'));
  }, []);

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveConfig({
        model: config.model,
        confidence_threshold: config.confidence_threshold,
        sovereign_cloud: config.sovereign_cloud,
        use_local_llm: config.use_local_llm,
        gemini_api_key: geminiKey || undefined,
      });
      setConfig(saved);
      setGeminiKey('');
      const lm = await api.fetchLmStudioStatus();
      setLmStatus(lm);
      setMessage('Settings saved.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Settings save failed');
    } finally {
      setSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="flex h-64 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Loading settings
      </div>
    );
  }

  return (
    <div className="grid gap-6 pb-20 xl:grid-cols-[1fr_360px] lg:pb-0">
      <section className="space-y-5">
        <div className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-cyan-700" />
            <h2 className="text-base font-semibold text-slate-950">LLM Routing</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Local LM Studio with Gemma is preferred when enabled and reachable. External Gemini is used only when local routing is disabled or unavailable.
          </p>

          <div className="mt-5 space-y-4">
            <label className="flex items-center justify-between gap-4 rounded-md border border-slate-200 p-4">
              <span>
                <span className="block text-sm font-medium text-slate-900">Use local LM Studio</span>
                <span className="mt-1 block text-sm text-slate-500">Routes extraction, chat, and drafting through the configured local endpoint when supported.</span>
              </span>
              <input
                type="checkbox"
                checked={config.use_local_llm}
                onChange={(event) => setConfig({ ...config, use_local_llm: event.target.checked })}
                className="h-5 w-5 rounded border-slate-300 text-slate-900 focus:ring-cyan-500"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">External model name</span>
              <input
                value={config.model}
                onChange={(event) => setConfig({ ...config, model: event.target.value })}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>

            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Confidence threshold</span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={config.confidence_threshold}
                onChange={(event) => setConfig({ ...config, confidence_threshold: Number(event.target.value) })}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>

            <label className="flex items-center justify-between gap-4 rounded-md border border-slate-200 p-4">
              <span>
                <span className="block text-sm font-medium text-slate-900">Sovereign cloud preference</span>
                <span className="mt-1 block text-sm text-slate-500">Marks the app preference for regional processing and audit review.</span>
              </span>
              <input
                type="checkbox"
                checked={config.sovereign_cloud}
                onChange={(event) => setConfig({ ...config, sovereign_cloud: event.target.checked })}
                className="h-5 w-5 rounded border-slate-300 text-slate-900 focus:ring-cyan-500"
              />
            </label>
          </div>
        </div>

        <div className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-cyan-700" />
            <h2 className="text-base font-semibold text-slate-950">External API Key</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            The key is stored in the local secrets file and never serialized into the visible config.
          </p>
          <label className="mt-4 block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Gemini key {config.gemini_api_key_set ? `(set, ending ${config.gemini_api_key_last4})` : '(not set)'}
            </span>
            <input
              type="password"
              value={geminiKey}
              onChange={(event) => setGeminiKey(event.target.value)}
              placeholder="Paste a replacement key"
              className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save settings
          </button>
          {message && <span className="text-sm text-slate-600">{message}</span>}
        </div>
      </section>

      <aside className="space-y-5">
        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2">
            <RadioTower className="h-5 w-5 text-cyan-700" />
            <h2 className="text-base font-semibold text-slate-950">LM Studio Status</h2>
          </div>
          <div className="mt-4 flex items-center gap-3 rounded-md bg-slate-50 p-4">
            {lmStatus?.available ? (
              <CheckCircle className="h-5 w-5 text-emerald-600" />
            ) : (
              <XCircle className="h-5 w-5 text-rose-600" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-900">{lmStatus?.available ? 'Reachable' : 'Not reachable'}</p>
              <p className="truncate text-sm text-slate-500">{lmStatus?.base_url || 'No endpoint reported'}</p>
            </div>
          </div>
          <dl className="mt-4 space-y-3">
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Local model</dt>
              <dd className="mt-1 break-words text-sm text-slate-800">{lmStatus?.model || 'Unknown'}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">External model</dt>
              <dd className="mt-1 break-words text-sm text-slate-800">{config.model}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-md border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-950">Current Data Surface</h2>
          <dl className="mt-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Candidates</dt>
              <dd className="text-sm font-semibold text-slate-950">{candidatesCount}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Matching jobs</dt>
              <dd className="text-sm font-semibold text-slate-950">{jobsCount}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Pending reviews</dt>
              <dd className="text-sm font-semibold text-slate-950">{tasksCount}</dd>
            </div>
          </dl>
        </section>
      </aside>
    </div>
  );
}
