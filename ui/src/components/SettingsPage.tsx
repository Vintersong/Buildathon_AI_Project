import { useEffect, useState } from 'react';
import { CheckCircle, KeyRound, Loader2, RadioTower, Save, Server, XCircle } from 'lucide-react';
import * as api from '../api';

interface SettingsPageProps {
  candidatesCount: number;
  jobsCount: number;
  tasksCount: number;
}

type KeyProvider = 'gemini' | 'openai' | 'anthropic';

const PROVIDER_LABELS: Record<api.LlmProvider, string> = {
  gemini: 'Google Gemini',
  openai: 'OpenAI (GPT)',
  anthropic: 'Anthropic (Claude)',
  local: 'Local / OpenAI-compatible',
};

const DEFAULT_MODELS: Record<api.LlmProvider, string> = {
  gemini: 'gemini-2.5-flash',
  openai: 'gpt-4o-mini',
  anthropic: 'claude-sonnet-4-6',
  local: 'local-model',
};

const KEY_PROVIDERS: KeyProvider[] = ['gemini', 'openai', 'anthropic'];

export default function SettingsPage({ candidatesCount, jobsCount, tasksCount }: SettingsPageProps) {
  const [config, setConfig] = useState<api.AppConfig | null>(null);
  const [lmStatus, setLmStatus] = useState<api.LmStudioStatus | null>(null);
  const [keys, setKeys] = useState<Record<KeyProvider, string>>({ gemini: '', openai: '', anthropic: '' });
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

  const changeProvider = (provider: api.LlmProvider) => {
    if (!config) return;
    setConfig({
      ...config,
      provider,
      use_local_llm: provider === 'local',
      // Default the model to a sensible value for the chosen provider.
      model: DEFAULT_MODELS[provider],
    });
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setMessage(null);
    try {
      const saved = await api.saveConfig({
        provider: config.provider,
        model: config.model,
        confidence_threshold: config.confidence_threshold,
        sovereign_cloud: config.sovereign_cloud,
        use_local_llm: config.provider === 'local',
        gemini_api_key: keys.gemini || undefined,
        openai_api_key: keys.openai || undefined,
        anthropic_api_key: keys.anthropic || undefined,
      });
      setConfig(saved);
      setKeys({ gemini: '', openai: '', anthropic: '' });
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

  const keyStatus = (p: KeyProvider): { set: boolean; last4: string | null } => {
    if (p === 'gemini') return { set: config.gemini_api_key_set, last4: config.gemini_api_key_last4 };
    if (p === 'openai') return { set: config.openai_api_key_set, last4: config.openai_api_key_last4 };
    return { set: config.anthropic_api_key_set, last4: config.anthropic_api_key_last4 };
  };

  return (
    <div className="grid gap-6 pb-20 xl:grid-cols-[1fr_360px] lg:pb-0">
      <section className="space-y-5">
        <div className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-cyan-700" />
            <h2 className="text-base font-semibold text-slate-950">AI Provider</h2>
          </div>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Choose which agent powers extraction, matching, outreach, and chat. Bring your own key —
            it is stored locally in the secrets file and never serialized into the visible config.
          </p>

          <div className="mt-5 space-y-4">
            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Provider</span>
              <select
                value={config.provider}
                onChange={(event) => changeProvider(event.target.value as api.LlmProvider)}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              >
                {(Object.keys(PROVIDER_LABELS) as api.LlmProvider[]).map((p) => (
                  <option key={p} value={p}>
                    {PROVIDER_LABELS[p]}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                Model name {config.provider === 'local' ? '(local server model)' : `(for ${PROVIDER_LABELS[config.provider]})`}
              </span>
              <input
                value={config.model}
                onChange={(event) => setConfig({ ...config, model: event.target.value })}
                placeholder={DEFAULT_MODELS[config.provider]}
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

        {config.provider === 'local' ? (
          <div className="rounded-md border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2">
              <RadioTower className="h-5 w-5 text-cyan-700" />
              <h2 className="text-base font-semibold text-slate-950">Local Endpoint</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              The local provider talks to any OpenAI-compatible server (LM Studio, Ollama, …) at the
              configured base URL. No API key is required. Status is shown on the right.
            </p>
          </div>
        ) : (
          <div className="rounded-md border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-cyan-700" />
              <h2 className="text-base font-semibold text-slate-950">API Key — {PROVIDER_LABELS[config.provider]}</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Paste the key for the selected provider. Leave blank to keep the existing key.
            </p>
            <label className="mt-4 block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                {(() => {
                  const s = keyStatus(config.provider as KeyProvider);
                  return s.set ? `Key (set, ending ${s.last4})` : 'Key (not set)';
                })()}
              </span>
              <input
                type="password"
                value={keys[config.provider as KeyProvider]}
                onChange={(event) => setKeys({ ...keys, [config.provider as KeyProvider]: event.target.value })}
                placeholder="Paste a replacement key"
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>

            <div className="mt-4 flex flex-wrap gap-2">
              {KEY_PROVIDERS.map((p) => {
                const s = keyStatus(p);
                return (
                  <span
                    key={p}
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
                      s.set ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {s.set ? <CheckCircle className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                    {PROVIDER_LABELS[p]} {s.set ? `••${s.last4}` : 'unset'}
                  </span>
                );
              })}
            </div>
          </div>
        )}

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
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Active provider</dt>
              <dd className="mt-1 break-words text-sm text-slate-800">{PROVIDER_LABELS[config.provider]}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Active model</dt>
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
