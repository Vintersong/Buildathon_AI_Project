/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState } from 'react';
import { Database, Download, RefreshCw, CheckCircle, Cpu, Gavel, Globe, Server, Code, FileCode, ArrowLeft, ArrowRight } from 'lucide-react';
import { AuditEvent } from '../types';

interface AuditLogsProps {
  events: AuditEvent[];
  searchQuery: string;
}

const PAGE_SIZE = 20;

export default function AuditLogs({ events, searchQuery }: AuditLogsProps) {
  const [actorFilter, setActorFilter] = useState<'all' | 'SYS' | 'HUMAN' | 'SEC'>('all');
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexStep, setReindexStep] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  // Filter events based on active selection and search parameters
  const filteredEvents = events.filter((evt) => {
    const matchesActor = actorFilter === 'all' || evt.actor === actorFilter;
    if (!matchesActor) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        evt.action.toLowerCase().includes(q) ||
        evt.payloadSummary.toLowerCase().includes(q) ||
        evt.timestamp.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const totalPages = Math.max(1, Math.ceil(filteredEvents.length / PAGE_SIZE));
  const pagedEvents = filteredEvents.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const handleReindex = () => {
    setIsReindexing(true);
    setReindexStep('Allocating direct memtable pointers...');
    
    setTimeout(() => {
      setReindexStep('Parsing local events.jsonl streams...');
    }, 600);

    setTimeout(() => {
      setReindexStep('Regenerating 1536HNSW vector dimensions...');
    }, 1200);

    setTimeout(() => {
      setReindexStep('Flushing verified index nodes to record_index.json.');
    }, 1800);

    setTimeout(() => {
      setIsReindexing(false);
      setReindexStep('');
    }, 2400);
  };

  return (
    <div className="space-y-12 animate-in fade-in duration-300">
      
      {/* Page Header and primary actions split */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-2xl font-bold text-primary font-sans leading-tight">Storage Transparency</h1>
          <p className="text-xs text-on-surface-variant font-sans mt-1.5 max-w-2xl">
            Audit the local storage layer. Bloodhound operates on human-readable JSONL and local vector indexes, ensuring complete provenance and zero black-box data processing.
          </p>
        </div>
        <div className="flex gap-4 shrink-0 font-sans">
          <button
            id="export-logs-btn"
            onClick={() => {
              const content = filteredEvents.map(e => JSON.stringify(e)).join('\n');
              const blob = new Blob([content], { type: 'application/jsonl' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'audit_events.jsonl';
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="px-4 py-2 border border-border-subtle rounded text-xs font-semibold text-on-surface hover:bg-surface-container transition-colors flex items-center gap-2 cursor-pointer"
          >
            <Download className="w-4 h-4 text-on-surface-variant" />
            <span>Export logs</span>
          </button>
          <button
            id="reindex-btn"
            disabled={isReindexing}
            onClick={handleReindex}
            className="px-4 py-2 bg-primary hover:opacity-90 disabled:opacity-50 text-white rounded text-xs font-semibold transition-opacity flex items-center justify-center gap-2 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${isReindexing ? 'animate-spin' : ''}`} />
            <span>{isReindexing ? 'Reindexing...' : 'Re-index'}</span>
          </button>
        </div>
      </div>

      {/* Simulated Reindex progress bar */}
      {isReindexing && (
        <div className="p-4 bg-slate-deep text-white border border-amber-500 rounded font-mono text-xs animate-pulse space-y-2">
          <div className="flex items-center gap-2 text-amber-500">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>SYSTEM CONVENING DIRECT INDEX SEQUENCE: ACTIVE</span>
          </div>
          <p className="text-slate-300">{reindexStep}</p>
        </div>
      )}

      {/* Health metrics grid row cards layout */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 font-sans">
        
        {/* Metric Card 1: Record Index */}
        <div className="p-6 bg-white border border-border-subtle rounded-lg space-y-4">
          <div className="flex justify-between items-start">
            <span className="text-[10px] font-bold font-sans text-on-surface-variant uppercase tracking-wider">RECORD INDEX HEALTH</span>
            <CheckCircle className="w-5 h-5 text-status-ok" />
          </div>
          <div>
            <div className="font-sans font-bold text-lg text-slate-800">record_index.json</div>
            <div className="font-mono text-[11px] text-on-surface-variant mt-1">CRC32: 0x8F2A1C94</div>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-100">
            <div>
              <div className="text-[9px] font-bold text-on-surface-variant opacity-65 uppercase tracking-wide">TOTAL OBJECTS</div>
              <div className="font-sans font-bold text-base text-primary">{events.length.toLocaleString()}</div>
            </div>
            <div>
              <div className="text-[9px] font-bold text-on-surface-variant opacity-65 uppercase tracking-wide">SIZE ON DISK</div>
              <div className="font-sans font-bold text-base text-primary">14.2 MB</div>
            </div>
          </div>
        </div>

        {/* Metric Card 2: Embedding Index */}
        <div className="p-6 bg-white border border-border-subtle rounded-lg space-y-4">
          <div className="flex justify-between items-start">
            <span className="text-[10px] font-bold font-sans text-on-surface-variant uppercase tracking-wider">EMBEDDING INDEX HEALTH</span>
            <CheckCircle className="w-5 h-5 text-status-ok" />
          </div>
          <div>
            <div className="font-sans font-bold text-lg text-slate-800">embedding_index.bin</div>
            <div className="font-mono text-[11px] text-on-surface-variant mt-1">HNSW / L2 Distance</div>
          </div>
          <div className="grid grid-cols-2 gap-4 pt-2 border-t border-slate-100">
            <div>
              <div className="text-[9px] font-bold text-on-surface-variant opacity-65 uppercase tracking-wide">DIMENSIONS</div>
              <div className="font-sans font-bold text-base text-primary">1,536</div>
            </div>
            <div>
              <div className="text-[9px] font-bold text-on-surface-variant opacity-65 uppercase tracking-wide">LATENCY (P95)</div>
              <div className="font-sans font-bold text-base text-primary">12ms</div>
            </div>
          </div>
        </div>

        {/* Metric Card 3: Compliance Residency */}
        <div className="p-6 bg-slate-deep text-white border border-primary rounded-lg space-y-4 relative overflow-hidden">
          <div className="flex justify-between items-start">
            <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest font-mono">COMPLIANCE & SOVEREIGNTY</span>
            <Gavel className="w-5 h-5 text-amber-500" />
          </div>
          <div className="space-y-1 relative z-10">
            <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-status-ok" />
              <span className="font-bold text-base">EEA (Dublin, IE)</span>
            </div>
            <div className="text-xs text-slate-300">Data residency locked to regional shard.</div>
          </div>
          <div className="pt-2 relative z-10">
            <div className="flex justify-between mb-2 text-[10px] font-mono select-none text-slate-400 font-bold">
              <span>RETENTION POLICY METRIC</span>
              <span>730 DAYS REMAINING</span>
            </div>
            <div className="w-full bg-white/10 h-1.5 rounded-full overflow-hidden">
              <div className="bg-white h-full w-4/5 rounded-full"></div>
            </div>
          </div>
        </div>
      </section>

      {/* Main Ledger Event Logs View */}
      <section className="space-y-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 select-none">
          <h2 className="font-sans font-bold text-base flex items-center gap-2.5 text-primary">
            <Code className="w-5 h-5 text-on-surface-variant" />
            <span>events.jsonl</span>
          </h2>
          <div className="flex gap-2">
            <select
              id="actor-filter-select"
              className="bg-white border border-border-subtle rounded font-sans text-xs font-semibold text-on-surface-variant px-3 py-1 cursor-pointer focus:ring-1 focus:ring-slate-deep"
              value={actorFilter}
              onChange={(e) => setActorFilter(e.target.value as any)}
            >
              <option value="all">FILTER: ALL ACTORS</option>
              <option value="SYS">ACTOR: SYSTEM ONLY</option>
              <option value="HUMAN">ACTOR: HUMAN ONLY</option>
              <option value="SEC">ACTOR: SEC COMPLETED</option>
            </select>
            <span className="px-3 py-1.5 rounded border border-border-subtle font-sans text-xs font-semibold bg-white text-on-surface-variant">
              LAST 24 HOURS
            </span>
          </div>
        </div>

        {/* Logs Tables Grid */}
        <div className="border border-border-subtle rounded bg-white overflow-hidden text-sm">
          {/* Table Header Row */}
          <div className="grid grid-cols-12 gap-4 px-6 py-3 bg-surface-container-low border-b border-border-subtle select-none">
            <div className="col-span-2 text-[10px] font-bold font-sans text-on-surface-variant tracking-wider">TIMESTAMP</div>
            <div className="col-span-2 text-[10px] font-bold font-sans text-on-surface-variant tracking-wider">TOOL/ACTION</div>
            <div className="col-span-1 text-[10px] font-bold font-sans text-on-surface-variant tracking-wider">ACTOR</div>
            <div className="col-span-12 sm:col-span-5 text-[10px] font-bold font-sans text-on-surface-variant tracking-wider">PAYLOAD SUMMARY</div>
            <div className="col-span-2 text-[10px] font-bold font-mono text-on-surface-variant text-right tracking-wider">CONFIDENCE</div>
          </div>

          {/* Table Body rows list */}
          <div className="divide-y divide-border-subtle font-mono text-xs">
            {filteredEvents.length === 0 ? (
              <div className="text-center py-12 text-on-surface-variant font-sans">
                No ledger events found matching local search credentials.
              </div>
            ) : (
              pagedEvents.map((evt) => {
                const isHumanActor = evt.actor === 'HUMAN';
                const isSecStatus = evt.actor === 'SEC';
                const isQuarantineHighlight = evt.action === 'manual_override';

                return (
                  <div
                    key={evt.id}
                    className={`grid grid-cols-12 gap-4 px-6 py-4 hover:bg-slate-50 transition-all items-center border-l-4 ${
                      isQuarantineHighlight
                        ? 'bg-red-50/40 border-l-status-error hover:bg-red-50/60 text-status-error'
                        : 'border-l-transparent'
                    }`}
                  >
                    {/* Timestamp */}
                    <div className="col-span-2 text-on-surface-variant font-mono">
                      {evt.timestamp}
                    </div>

                    {/* Tool Name Tag */}
                    <div className="col-span-2">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-tight ${
                        isQuarantineHighlight
                          ? 'bg-status-error text-white'
                          : isSecStatus
                          ? 'bg-stone-200 text-stone-800'
                          : 'bg-surface-container-high text-slate-800'
                      }`}>
                        {evt.action}
                      </span>
                    </div>

                    {/* Actor label */}
                    <div className="col-span-1 flex items-center gap-1.5">
                      <span className={`text-[10px] font-bold ${
                        isQuarantineHighlight ? 'text-status-error' : 'text-slate-800'
                      }`}>
                        {evt.actor}
                      </span>
                    </div>

                    {/* Summary Payload */}
                    <div className="col-span-12 sm:col-span-5 truncate text-on-surface font-sans text-xs">
                      {evt.payloadSummary}
                    </div>

                    {/* Confidence score */}
                    <div className="col-span-2 text-right font-mono font-bold text-xs">
                      <span className={isQuarantineHighlight ? 'text-status-error' : 'text-status-ok'}>
                        {evt.confidence.toFixed(2)}
                      </span>
                    </div>

                  </div>
                );
              })
            )}
          </div>

          {/* Footer Stream pagination */}
          <div className="flex items-center justify-between px-6 py-4 bg-white border-t border-border-subtle font-sans font-bold text-[10px] tracking-wide text-on-surface-variant select-none">
            <span>SHOWING {Math.min((currentPage - 1) * PAGE_SIZE + 1, filteredEvents.length)}–{Math.min(currentPage * PAGE_SIZE, filteredEvents.length)} OF {filteredEvents.length.toLocaleString()} EVENTS</span>
            <div className="flex gap-2 shrink-0">
              <button
                disabled={currentPage <= 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                className="p-1 px-2 border border-border-subtle rounded hover:bg-surface-container disabled:opacity-50 cursor-pointer"
              ><ArrowLeft className="w-3.5 h-3.5" /></button>
              <button
                disabled={currentPage >= totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                className="p-1 px-2 border border-border-subtle rounded hover:bg-surface-container disabled:opacity-50 cursor-pointer"
              ><ArrowRight className="w-3.5 h-3.5" /></button>
            </div>
          </div>

        </div>
      </section>

      {/* Bottom Retention Windows details policy */}
      <section className="grid grid-cols-1 md:grid-cols-2 gap-8 pb-12">
        
        {/* Retention policy details */}
        <div className="bg-white border border-border-subtle rounded-lg flex flex-col justify-between">
          <div className="p-6 border-b border-border-subtle font-sans">
            <h3 className="font-bold text-slate-900 text-sm">Data Retention Policy</h3>
            <p className="text-xs text-on-surface-variant mt-1">Automatic scrubbing cycles and safety compliance rules.</p>
          </div>
          
          <div className="p-6 space-y-5 font-sans font-semibold text-xs select-none">
            <div className="flex justify-between items-center">
              <span className="text-on-surface-variant font-mono text-[10px] uppercase">CANDIDATE PII SECTOR</span>
              <span className="font-mono text-status-review font-bold">365 DAYS LIMIT</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-on-surface-variant font-mono text-[10px] uppercase">AUDIT Trail LOGS</span>
              <span className="font-mono text-status-ok font-bold">PERMANENT DEPLOY</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-on-surface-variant font-mono text-[10px] uppercase">AI REASONING TRACES</span>
              <span className="font-mono text-slate-500 font-bold font-mono">90 DAYS RETENTION</span>
            </div>
          </div>

          <div className="p-4 bg-surface-container-low mt-auto">
            <button
              disabled
              className="w-full py-2 border border-primary text-primary font-bold font-sans text-xs leading-none uppercase tracking-wide opacity-50 cursor-not-allowed rounded"
            >
              CONFIGURE RETENTION WINDOWS
            </button>
          </div>
        </div>

        {/* Physical Infrastructure graphic thumbnail visual */}
        <div className="relative min-h-[300px] rounded-lg overflow-hidden border border-border-subtle group font-sans">
          <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(99,102,241,0.04)_2px,rgba(99,102,241,0.04)_4px)] bg-slate-900" />
          <div className="absolute inset-0 bg-gradient-to-t from-primary via-primary/40 to-transparent flex flex-col justify-end p-8 text-white">
            <div className="text-[10px] font-mono tracking-widest text-slate-300 font-bold uppercase mb-2">PHYSICAL INFRASTRUCTURE</div>
            <h4 className="font-sans font-bold text-base">Deterministic Hardware Anchors</h4>
            <p className="text-xs text-slate-200 mt-2 max-w-sm leading-relaxed">
              Every byte is mapped to verified local database sectors. Zero cloud-spill for sensitive PII records.
            </p>
          </div>
        </div>

      </section>

    </div>
  );
}
