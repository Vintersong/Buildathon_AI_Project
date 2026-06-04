import { useEffect, useState } from 'react';
import { CheckCircle, KeyRound, Loader2, RadioTower, Save, Server, XCircle } from 'lucide-react';
import * as api from '../api';

interface SettingsPageProps {
  candidatesCount: number;
  jobsCount: number;
  tasksCount: number;
}

type KeyProvider = 'gemini' | 'openai' | 'anthropic';
type ModelOption = {
  id: string;
  label: string;
  detail: string;
};

const PROVIDER_LABELS: Record<api.LlmProvider, string> = {
  gemini: 'Google Gemini',
  openai: 'OpenAI (GPT)',
  anthropic: 'Anthropic (Claude)',
  local: 'Local / OpenAI-compatible',
};

const DEFAULT_MODELS: Record<api.LlmProvider, string> = {
  gemini: 'gemini-3.5-flash',
  openai: 'gpt-5.4-mini',
  anthropic: 'claude-sonnet-4-6',
  local: 'local-model',
};

const MODEL_OPTIONS: Record<api.LlmProvider, ModelOption[]> = {
  gemini: [
    { id: 'gemini-3.5-flash', label: 'Gemini 3.5 Flash', detail: 'Stable default for agentic and coding workflows' },
    { id: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro Preview', detail: 'Higher reasoning for complex tool use' },
    { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', detail: 'Preview model with computer-use capability' },
    { id: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite', detail: 'Lower-cost lightweight extraction and classification' },
    { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', detail: 'Previous advanced reasoning model' },
    { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', detail: 'Previous price-performance model' },
  ],
  openai: [
    { id: 'gpt-5.5', label: 'GPT-5.5', detail: 'Flagship model for complex reasoning and coding' },
    { id: 'gpt-5.4', label: 'GPT-5.4', detail: 'Strong general model for professional work' },
    { id: 'gpt-5.4-mini', label: 'GPT-5.4 mini', detail: 'Recommended balance of capability, latency, and cost' },
    { id: 'gpt-5.4-nano', label: 'GPT-5.4 nano', detail: 'Fastest low-cost option for simple tasks' },
    { id: 'gpt-4.1', label: 'GPT-4.1', detail: 'Legacy non-reasoning option' },
  ],
  anthropic: [
    { id: 'claude-opus-4-8', label: 'Claude Opus 4.8', detail: 'Highest capability for complex reasoning and agentic coding' },
    { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', detail: 'Recommended balance of speed and intelligence' },
    { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', detail: 'Fastest Claude option for lightweight tasks' },
  ],
  local: [
    { id: 'local-model', label: 'Local model', detail: 'Use the active model served by LM Studio or another OpenAI-compatible server' },
  ],
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
  const modelOptions = MODEL_OPTIONS[config.provider];
  const selectedModel = modelOptions.some((option) => option.id === config.model) ? config.model : '__custom__';

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
              <select
                value={selectedModel}
                onChange={(event) => {
                  const value = event.target.value;
                  setConfig({ ...config, model: value === '__custom__' ? config.model : value });
                }}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              >
                {modelOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label} - {option.id}
                  </option>
                ))}
                <option value="__custom__">Custom model id</option>
              </select>
            </label>

            <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <div className="flex flex-wrap gap-2">
                {modelOptions.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => setConfig({ ...config, model: option.id })}
                    className={`rounded-md border px-3 py-2 text-left text-xs ${
                      config.model === option.id
                        ? 'border-cyan-500 bg-cyan-50 text-cyan-800'
                        : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    <span className="block font-semibold">{option.label}</span>
                    <span className="mt-1 block text-slate-500">{option.detail}</span>
                  </button>
                ))}
              </div>
              <label className="mt-3 block">
                <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Custom model id</span>
                <input
                  value={config.model}
                  onChange={(event) => setConfig({ ...config, model: event.target.value })}
                  placeholder={DEFAULT_MODELS[config.provider]}
                  className="mt-1 h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                />
              </label>
            </div>

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
