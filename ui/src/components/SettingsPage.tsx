/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useRef } from 'react';
import { Shield, Cpu, HelpCircle, HardDrive, Loader2, Save, CheckCircle, AlertTriangle, Key } from 'lucide-react';
import * as api from '../api';
import type { AppConfig } from '../api';

const DEFAULT_CONFIG: AppConfig = {
  model: 'gemini-2.5-flash',
  confidence_threshold: 0.85,
  sovereign_cloud: false,
  use_local_llm: false,
  gemini_api_key_set: false,
  gemini_api_key_last4: null,
};

// Sentinel: distinguishes "user wants to clear the stored key" from "user
// hasn't typed anything yet" (which leaves the stored key alone).
const CLEAR_KEY = '__CLEAR__';

const LS_CHAT_KEY = 'bld_ai_chats';

interface SettingsPageProps {
  candidatesCount: number;
  jobsCount: number;
  tasksCount: number;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export default function SettingsPage({
  candidatesCount,
  jobsCount,
  tasksCount,
}: SettingsPageProps) {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [savedConfig, setSavedConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [chatCleared, setChatCleared] = useState(false);
  // Draft key the user has typed but not yet saved. Empty string = no pending
  // change; CLEAR_KEY = user clicked "Clear stored key"; other = new key.
  const [apiKeyDraft, setApiKeyDraft] = useState<string>('');
  // Live LM Studio reachability — refreshed on mount + when the user toggles.
  const [lmStatus, setLmStatus] = useState<api.LmStudioStatus | null>(null);
  const [lmStatusChecking, setLmStatusChecking] = useState(false);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshLmStatus = () => {
    setLmStatusChecking(true);
    api.fetchLmStudioStatus()
      .then(setLmStatus)
      .catch(() => setLmStatus(null))
      .finally(() => setLmStatusChecking(false));
  };

  // Load live config on mount
  useEffect(() => {
    api.fetchConfig()
      .then((cfg) => {
        setConfig(cfg);
        setSavedConfig(cfg);
      })
      .catch(() => {
        setConfig(DEFAULT_CONFIG);
        setSavedConfig(DEFAULT_CONFIG);
      })
      .finally(() => setLoading(false));
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current); }, []);

  // Probe LM Studio on mount so the badge reflects reality immediately.
  useEffect(() => { refreshLmStatus(); }, []);

  const cfg = config ?? DEFAULT_CONFIG;

  // Dirty = current config differs from last saved, OR a key change is pending.
  const isDirty =
    (savedConfig !== null && JSON.stringify(cfg) !== JSON.stringify(savedConfig)) ||
    apiKeyDraft !== '';

  const handleSave = async () => {
    if (!config || saveState === 'saving') return;
    setSaveState('saving');
    setSaveError(null);
    try {
      const payload: api.AppConfigUpdate = {
        model: config.model,
        confidence_threshold: config.confidence_threshold,
        sovereign_cloud: config.sovereign_cloud,
        use_local_llm: config.use_local_llm,
      };
      if (apiKeyDraft === CLEAR_KEY) {
        payload.gemini_api_key = '';
      } else if (apiKeyDraft !== '') {
        payload.gemini_api_key = apiKeyDraft;
      }
      const confirmed = await api.saveConfig(payload);
      setConfig(confirmed);
      setSavedConfig(confirmed);
      setApiKeyDraft('');
      setSaveState('saved');
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = setTimeout(() => setSaveState('idle'), 3000);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setSaveError(msg);
      setSaveState('error');
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      saveTimeoutRef.current = setTimeout(() => setSaveState('idle'), 5000);
    }
  };

  const handleResetChat = () => {
    localStorage.removeItem(LS_CHAT_KEY);
    setChatCleared(true);
    setTimeout(() => setChatCleared(false), 2500);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">

      {/* Header */}
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-on-surface">System Configuration</h2>
          <p className="text-xs font-sans text-on-surface-variant mt-1.5 max-w-2xl">
            Global confidence thresholds, compliance rules, and underlying neural models.
          </p>
        </div>

        {/* Save Config Button */}
        <button
          id="save-config-btn"
          onClick={handleSave}
          disabled={loading || saveState === 'saving' || (!isDirty && saveState === 'idle')}
          className={`flex items-center gap-2 px-5 py-2 rounded text-xs font-bold uppercase tracking-wider border transition-all cursor-pointer disabled:cursor-not-allowed
            ${saveState === 'saved'
              ? 'bg-emerald-50 border-emerald-300 text-emerald-700'
              : saveState === 'error'
              ? 'bg-red-50 border-red-300 text-red-700'
              : isDirty
              ? 'bg-slate-deep text-white border-slate-deep hover:bg-black'
              : 'bg-white border-border-subtle text-on-surface-variant opacity-50'
            }`}
        >
          {saveState === 'saving' && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {saveState === 'saved' && <CheckCircle className="w-3.5 h-3.5" />}
          {saveState === 'error' && <AlertTriangle className="w-3.5 h-3.5" />}
          {saveState === 'idle' && <Save className="w-3.5 h-3.5" />}
          <span>
            {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'Config Saved' : saveState === 'error' ? 'Save Failed' : 'Save Config'}
          </span>
        </button>
      </div>

      {/* Save error banner */}
      {saveState === 'error' && saveError && (
        <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700 font-sans">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span><strong>Config save failed:</strong> {saveError}</span>
        </div>
      )}

      {/* Unsaved changes banner */}
      {isDirty && saveState === 'idle' && (
        <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800 font-sans">
          <AlertTriangle className="w-4 h-4 shrink-0 text-amber-500" />
          <span>You have unsaved changes. Click <strong>Save Config</strong> to persist them to <code className="font-mono text-[10px] bg-amber-100 px-1 rounded">config.json</code>.</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-sm">

        {/* Left: controls */}
        <div className="md:col-span-2 space-y-6">

          {/* Section 1: Model + threshold */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-bloodhound-crimson" />
              <span>Matching & Extraction Engine</span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-on-surface-variant ml-auto" />}
            </h3>

            <div className="space-y-4 font-sans text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1 uppercase tracking-wider text-[10px]">
                  Reranking Neural Model
                </label>
                {loading ? (
                  <div className="h-8 bg-surface-container-high rounded animate-pulse" />
                ) : (
                  <select
                    id="settings-model"
                    className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface"
                    value={cfg.model}
                    onChange={(e) => setConfig({ ...cfg, model: e.target.value })}
                  >
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (highest quality, slowest)</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (balanced, recommended)</option>
                    <option value="gemini-2.5-flash-lite">Gemini 2.5 Flash-Lite (cheapest, lowest quota)</option>
                  </select>
                )}
                <p className="text-[10px] text-status-ok mt-1 font-semibold">
                  ✓ Live value from config.json
                </p>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-slate-700 font-bold uppercase tracking-wider text-[10px]">
                    Automatic Confidence Threshold:{' '}
                    {loading ? '—' : cfg.confidence_threshold.toFixed(2)}
                  </label>
                  <span className="text-status-review font-bold">Requires Verification Below</span>
                </div>
                {loading ? (
                  <div className="h-4 bg-surface-container-high rounded animate-pulse" />
                ) : (
                  <input
                    id="settings-threshold"
                    type="range"
                    min="0.50"
                    max="0.99"
                    step="0.01"
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-slate-deep"
                    value={cfg.confidence_threshold}
                    onChange={(e) => setConfig({ ...cfg, confidence_threshold: Number(e.target.value) })}
                  />
                )}
                <div className="flex justify-between font-mono text-[10px] text-slate-500 mt-1">
                  <span>0.50 (Relaxed)</span>
                  <span>0.85 (Recommended)</span>
                  <span>0.99 (Paranoid)</span>
                </div>
                <p className="text-[10px] text-status-ok mt-1 font-semibold">
                  ✓ Live value from config.json
                </p>
              </div>
            </div>
          </div>

          {/* Section 1b: API Key (BYO) */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Key className="w-4 h-4 text-bloodhound-crimson" />
              <span>Gemini API Key</span>
            </h3>

            <div className="space-y-3 font-sans text-xs">
              <p className="text-on-surface-variant">
                Bring your own Gemini key to lift the shared-quota cap. Stored locally in{' '}
                <code className="font-mono text-[10px] bg-slate-100 px-1 rounded">.secrets.json</code>{' '}
                (gitignored). The full key is never returned to the browser — only the last 4 digits are shown after save.
              </p>

              {loading ? (
                <div className="h-8 bg-surface-container-high rounded animate-pulse" />
              ) : (
                <>
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-700 shrink-0">
                      Current:
                    </span>
                    {cfg.gemini_api_key_set && cfg.gemini_api_key_last4 ? (
                      <code className="font-mono text-[11px] bg-emerald-50 border border-emerald-300 text-emerald-800 px-2 py-1 rounded">
                        ••••••••••••{cfg.gemini_api_key_last4}
                      </code>
                    ) : (
                      <span className="text-[11px] text-slate-500 italic">
                        none (falling back to <code className="font-mono text-[10px]">GEMINI_API_KEY</code> env var)
                      </span>
                    )}
                  </div>

                  <div>
                    <label htmlFor="settings-api-key" className="block text-slate-700 font-bold mb-1 uppercase tracking-wider text-[10px]">
                      {cfg.gemini_api_key_set ? 'Replace key' : 'Set key'}
                    </label>
                    <input
                      id="settings-api-key"
                      type="password"
                      autoComplete="off"
                      spellCheck={false}
                      placeholder="AIza…"
                      className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface font-mono text-[11px]"
                      value={apiKeyDraft === CLEAR_KEY ? '' : apiKeyDraft}
                      onChange={(e) => setApiKeyDraft(e.target.value)}
                    />
                  </div>

                  {cfg.gemini_api_key_set && (
                    <button
                      type="button"
                      onClick={() => setApiKeyDraft(apiKeyDraft === CLEAR_KEY ? '' : CLEAR_KEY)}
                      className={`text-[10px] font-bold uppercase tracking-wider px-3 py-1.5 rounded border transition-colors cursor-pointer ${
                        apiKeyDraft === CLEAR_KEY
                          ? 'bg-red-50 border-red-300 text-red-700'
                          : 'bg-white border-border-subtle text-on-surface-variant hover:border-red-300 hover:text-red-700'
                      }`}
                    >
                      {apiKeyDraft === CLEAR_KEY ? '✕ Will clear on save — click to undo' : 'Clear stored key'}
                    </button>
                  )}

                  {(apiKeyDraft !== '' && apiKeyDraft !== CLEAR_KEY) && (
                    <p className="text-[10px] text-amber-700 font-semibold">
                      ⚠ New key pending — click <strong>Save Config</strong> to persist.
                    </p>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Section 2: Sovereignty */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Shield className="w-4 h-4 text-status-ok" />
              <span>Sovereignty & Security Rules</span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-on-surface-variant ml-auto" />}
            </h3>

            <div className="space-y-4 font-sans text-xs">

              {/* Local LLM toggle — bypass Gemini, route everything through LM Studio */}
              <div className="flex items-start gap-4 p-3 border border-border-subtle rounded bg-surface-container-low">
                {loading ? (
                  <div className="h-4 w-4 bg-surface-container-high rounded animate-pulse mt-0.5" />
                ) : (
                  <input
                    id="settings-local-llm"
                    type="checkbox"
                    className="h-4 w-4 text-slate-deep focus:ring-slate-deep rounded border-gray-300 mt-0.5 cursor-pointer"
                    checked={cfg.use_local_llm}
                    onChange={(e) => setConfig({ ...cfg, use_local_llm: e.target.checked })}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <label htmlFor="settings-local-llm" className="block text-slate-800 font-bold uppercase tracking-wider text-[10px] cursor-pointer">
                      Use Local LLM (LM Studio)
                    </label>
                    {lmStatusChecking ? (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-mono font-bold rounded">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" /> probing…
                      </span>
                    ) : lmStatus?.available ? (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-300 text-[9px] font-mono font-bold rounded">
                        ● REACHABLE — {lmStatus.model}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 bg-red-50 text-red-700 border border-red-300 text-[9px] font-mono font-bold rounded">
                        ● UNREACHABLE
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={refreshLmStatus}
                      disabled={lmStatusChecking}
                      className="text-[9px] font-mono font-bold text-slate-600 hover:text-slate-900 underline cursor-pointer disabled:opacity-50"
                    >
                      recheck
                    </button>
                  </div>
                  <p className="text-xs text-on-surface-variant leading-relaxed mt-1">
                    Routes all extract / match / outreach calls through{' '}
                    <code className="font-mono text-[10px] bg-slate-100 px-1 rounded">{lmStatus?.base_url ?? 'http://localhost:1234/v1'}</code>{' '}
                    using model{' '}
                    <code className="font-mono text-[10px] bg-slate-100 px-1 rounded">{lmStatus?.model ?? 'gemma4be'}</code>.
                    Skips Gemini entirely — zero API quota consumed.
                  </p>
                  {cfg.use_local_llm && !lmStatus?.available && !lmStatusChecking && (
                    <p className="text-[10px] text-status-error mt-1 font-semibold">
                      ⚠ Toggle is on but LM Studio is not reachable. Calls will fall back to the heuristic / template path.
                    </p>
                  )}
                </div>
              </div>

              <div className="flex items-start gap-4">
                {loading ? (
                  <div className="h-4 w-4 bg-surface-container-high rounded animate-pulse mt-0.5" />
                ) : (
                  <input
                    id="settings-sovereign"
                    type="checkbox"
                    className="h-4 w-4 text-slate-deep focus:ring-slate-deep rounded border-gray-300 mt-0.5 cursor-pointer"
                    checked={cfg.sovereign_cloud}
                    onChange={(e) => setConfig({ ...cfg, sovereign_cloud: e.target.checked })}
                  />
                )}
                <div>
                  <label htmlFor="settings-sovereign" className="block text-slate-800 font-bold uppercase tracking-wider text-[10px] cursor-pointer">
                    Enforce Isolated Local Disk Residency
                  </label>
                  <p className="text-xs text-on-surface-variant leading-relaxed mt-0.5">
                    Locks decrypted client information in local partitions, skipping remote ingestion cloud synchronizers. Essential for GDPR compliance levels.
                  </p>
                  <p className="text-[10px] text-status-ok mt-1 font-semibold">
                    ✓ Live value from config.json
                  </p>
                </div>
              </div>

              <div className="bg-surface-container-low p-3.5 border border-border-subtle rounded text-xs leading-relaxed text-on-surface-variant flex items-start gap-2">
                <HelpCircle className="w-4 h-4 text-slate-600 shrink-0 mt-0.5" />
                <p>
                  Encryption mechanisms are derived using SHA-256 local salt sequences. High risk records are automatically flagged if name-matching indicators fail the CRC-check.
                </p>
              </div>
            </div>
          </div>

        </div>

        {/* Right column: stats + reset */}
        <div className="space-y-6">
          <div className="p-6 bg-slate-deep text-white rounded-md space-y-4 font-sans">
            <h3 className="font-bold border-b border-white/10 pb-2 flex items-center gap-2 text-sm">
              <HardDrive className="w-4 h-4 text-status-review" />
              <span>Substrate Footprint</span>
            </h3>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex justify-between">
                <span className="opacity-75">CANDIDATES MEMTABLE:</span>
                <span className="font-bold">{candidatesCount} entries</span>
              </div>
              <div className="flex justify-between">
                <span className="opacity-75">REQUIREMENT SHARDS:</span>
                <span className="font-bold">{jobsCount} active</span>
              </div>
              <div className="flex justify-between">
                <span className="opacity-75">OUTSTANDING DECISIONS:</span>
                <span className="font-bold">{tasksCount} items</span>
              </div>
              <div className="pt-2 border-t border-white/10 flex justify-between">
                <span className="opacity-75">LOCAL SHARD COMPILER:</span>
                <span className="font-bold text-status-ok">ONLINE</span>
              </div>
            </div>
          </div>

          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-2 text-xs font-sans">
            <h4 className="font-bold text-slate-800">Reset AI Chat History</h4>
            <p className="text-on-surface-variant leading-relaxed">
              Clears Bloodhounds conversation history stored in your browser. All candidate and job data is preserved.
            </p>
            <button
              onClick={handleResetChat}
              className={`mt-3 w-full py-2 font-bold border cursor-pointer transition-colors rounded uppercase text-[10px] ${
                chatCleared
                  ? 'bg-emerald-50 border-emerald-300 text-emerald-700'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-800 border-border-subtle'
              }`}
            >
              {chatCleared ? '✓ Chat History Cleared' : 'Reset AI Chat History'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
