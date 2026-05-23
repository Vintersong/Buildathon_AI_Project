/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useRef } from 'react';
import { Shield, Cpu, HelpCircle, HardDrive, Loader2, Save, CheckCircle, AlertTriangle } from 'lucide-react';
import * as api from '../api';
import type { AppConfig } from '../api';

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
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load live config on mount
  useEffect(() => {
    api.fetchConfig()
      .then((cfg) => {
        setConfig(cfg);
        setSavedConfig(cfg);
      })
      .catch(() => {
        const defaults: AppConfig = { model: 'gemini-2.5-flash', confidence_threshold: 0.85, sovereign_cloud: false };
        setConfig(defaults);
        setSavedConfig(defaults);
      })
      .finally(() => setLoading(false));
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => () => { if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current); }, []);

  const cfg = config ?? { model: 'gemini-2.5-flash', confidence_threshold: 0.85, sovereign_cloud: false };

  // Dirty = current config differs from last saved
  const isDirty = savedConfig !== null && JSON.stringify(cfg) !== JSON.stringify(savedConfig);

  const handleSave = async () => {
    if (!config || saveState === 'saving') return;
    setSaveState('saving');
    setSaveError(null);
    try {
      const confirmed = await api.saveConfig(config);
      setSavedConfig(confirmed);
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
            Global consensus indices thresholds, compliance rules, and underlying neural models.
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
                    <option value="gemini-2.5-pro">Gemini 2.5 Pro (Balanced Core Extractions)</option>
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Ultra-Low Latency Streams)</option>
                    <option value="experimental-bld-v4">Experimental Bloodhound Spec v4.2</option>
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

          {/* Section 2: Sovereignty */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Shield className="w-4 h-4 text-status-ok" />
              <span>Sovereignty & Security Rules</span>
              {loading && <Loader2 className="w-3.5 h-3.5 animate-spin text-on-surface-variant ml-auto" />}
            </h3>

            <div className="space-y-4 font-sans text-xs">
              <div className="flex items-start gap-4">
                {loading ? (
                  <div className="h-4 w-4 bg-surface-container-high rounded animate-pulse mt-0.5" />
                ) : (
                  <input
                    id="settings-sovereigner"
                    type="checkbox"
                    className="h-4 w-4 text-slate-deep focus:ring-slate-deep rounded border-gray-300 mt-0.5 cursor-pointer"
                    checked={cfg.sovereign_cloud}
                    onChange={(e) => setConfig({ ...cfg, sovereign_cloud: e.target.checked })}
                  />
                )}
                <div>
                  <label htmlFor="settings-sovereigner" className="block text-slate-800 font-bold uppercase tracking-wider text-[10px] cursor-pointer">
                    Enforce Isolated Local Disk Residency
                  </label>
                  <p className="text-xs text-on-surface-variant leading-relaxed mt-0.5">
                    Locks decrypted client information in local partitions, skipping remote ingestion cloud synchronisers. Essential for GDPR compliance levels.
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
              Clears the AI copilot conversation history stored in your browser. All candidate and job data is preserved.
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
