/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Settings, Shield, Cpu, Key, HelpCircle, HardDrive } from 'lucide-react';

const LS_CHAT_KEY = 'bld_ai_chats';

interface SettingsPageProps {
  candidatesCount: number;
  jobsCount: number;
  tasksCount: number;
}

export default function SettingsPage({
  candidatesCount,
  jobsCount,
  tasksCount
}: SettingsPageProps) {
  const [modelType, setModelType] = useState('gemini-2.5-pro');
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.85);
  const [useSovereignCloud, setUseSovereignCloud] = useState(true);
  const [chatCleared, setChatCleared] = useState(false);

  const handleResetChat = () => {
    localStorage.removeItem(LS_CHAT_KEY);
    setChatCleared(true);
    setTimeout(() => setChatCleared(false), 2500);
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-on-surface">System Configuration</h2>
        <p className="text-xs font-sans text-on-surface-variant mt-1.5 max-w-2xl">
          Global consensus indices thresholds, compliance rules, and underlying neural models.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-sm">
        
        {/* State details column */}
        <div className="md:col-span-2 space-y-6">
          
          {/* Section 1: Algorithmic routing */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-bloodhound-crimson" />
              <span>Matching & Extraction Engine</span>
            </h3>

            <div className="space-y-4 font-sans text-xs">
              <div>
                <label className="block text-slate-700 font-bold mb-1 uppercase tracking-wider text-[10px]">
                  Reranking Neural Model
                </label>
                <select
                  id="settings-model"
                  className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface"
                  value={modelType}
                  onChange={(e) => setModelType(e.target.value)}
                >
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro (Balanced Core Extractions)</option>
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash (Ultra-Low Latency Streams)</option>
                  <option value="experimental-bld-v4">Experimental Bloodhound Spec v4.2</option>
                </select>
                <p className="text-[10px] text-on-surface-variant mt-1">⚠ Model selection is display-only until backend config API is wired.</p>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="text-slate-700 font-bold uppercase tracking-wider text-[10px]">
                    Automatic Confidence Threshold: {confidenceThreshold.toFixed(2)}
                  </label>
                  <span className="text-status-review font-bold">Requires Verification Below</span>
                </div>
                <input
                  id="settings-threshold"
                  type="range"
                  min="0.50"
                  max="0.99"
                  step="0.01"
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-slate-deep"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                />
                <div className="flex justify-between font-mono text-[10px] text-slate-500 mt-1">
                  <span>0.50 (Relaxed)</span>
                  <span>0.85 (Recommended)</span>
                  <span>0.99 (Paranoid)</span>
                </div>
                <p className="text-[10px] text-on-surface-variant mt-1">⚠ Threshold is display-only until backend config API is wired.</p>
              </div>
            </div>
          </div>

          {/* Section 2: Privacy boundaries */}
          <div className="p-6 bg-white border border-border-subtle rounded-md space-y-4">
            <h3 className="font-bold text-slate-900 border-b border-slate-100 pb-2 flex items-center gap-2">
              <Shield className="w-4 h-4 text-status-ok" />
              <span>Sovereignty & Security Rules</span>
            </h3>

            <div className="space-y-4 font-sans text-xs">
              <div className="flex items-start gap-4">
                <input
                  id="settings-sovereigner"
                  type="checkbox"
                  className="h-4 w-4 text-slate-deep focus:ring-slate-deep rounded border-gray-300 mt-0.5 cursor-pointer"
                  checked={useSovereignCloud}
                  onChange={(e) => setUseSovereignCloud(e.target.checked)}
                />
                <div>
                  <label htmlFor="settings-sovereigner" className="block text-slate-800 font-bold uppercase tracking-wider text-[10px] cursor-pointer">
                    Enforce Isolated Local Disk Residency
                  </label>
                  <p className="text-xs text-on-surface-variant leading-relaxed mt-0.5">
                    Locks decrypted client information in local partitions, skipping remote ingestion cloud synchronisers. Essential for GDPR compliance levels.
                  </p>
                  <p className="text-[10px] text-on-surface-variant mt-1">⚠ Toggle is display-only until backend config API is wired.</p>
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

        {/* Right column: Storage stats */}
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
