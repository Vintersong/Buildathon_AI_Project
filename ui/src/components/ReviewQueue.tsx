/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useMemo, useEffect } from 'react';
import { GitMerge, Gavel, Mail, Check, X, Info, ExternalLink, Terminal } from 'lucide-react';
import { ReviewTask, AuditEvent } from '../types';

interface ReviewQueueProps {
  tasks: ReviewTask[];
  onResolveTask: (taskId: string, outcome: 'approved' | 'rejected' | 'purged') => void;
  focusedTaskId?: string;
  onClearFocus: () => void;
  onNavigate: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
  auditEvents?: AuditEvent[];
}

export default function ReviewQueue({
  tasks,
  onResolveTask,
  focusedTaskId,
  onClearFocus,
  onNavigate,
  auditEvents = [],
}: ReviewQueueProps) {
  const [activeTab, setActiveTab] = useState<'identity' | 'outreach' | 'compliance'>('identity');

  // B3 fix: side-effects belong in useEffect, not useMemo
  useEffect(() => {
    if (focusedTaskId) {
      const task = tasks.find((t) => t.id === focusedTaskId);
      if (task) {
        if (task.type === 'IDENTITY_CONFLICT') setActiveTab('identity');
        else if (task.type === 'OUTREACH_DRAFT') setActiveTab('outreach');
        else if (task.type === 'COMPLIANCE_FLAG') setActiveTab('compliance');
      }
    }
  }, [focusedTaskId, tasks]);

  const filteredTasks = useMemo(() => {
    return tasks.filter((t) => {
      if (t.status !== 'pending') return false;
      if (activeTab === 'identity') return t.type === 'IDENTITY_CONFLICT';
      if (activeTab === 'outreach') return t.type === 'OUTREACH_DRAFT';
      return t.type === 'COMPLIANCE_FLAG';
    });
  }, [tasks, activeTab]);

  const counts = useMemo(() => ({
    identity: tasks.filter((t) => t.type === 'IDENTITY_CONFLICT' && t.status === 'pending').length,
    outreach: tasks.filter((t) => t.type === 'OUTREACH_DRAFT' && t.status === 'pending').length,
    compliance: tasks.filter((t) => t.type === 'COMPLIANCE_FLAG' && t.status === 'pending').length,
  }), [tasks]);

  // B4 fix: derive live trail from real auditEvents prop (last 3)
  const liveTrail = auditEvents.slice(-3);

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      
      {/* Page Header banner */}
      <section className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div className="space-y-1.5">
          <h2 className="text-2xl font-bold text-primary">Human-in-the-Loop Review</h2>
          <p className="text-xs text-on-surface-variant font-sans max-w-2xl">
            Deterministic control center. All actions taken here are finalized to the production ledger and appended to <code className="bg-surface-container-low text-primary px-1.5 py-0.5 rounded font-mono text-[11px] font-bold">events.jsonl</code>.
          </p>
        </div>

        <div className="flex gap-4 self-stretch md:self-auto select-none font-sans">
          <div className="px-6 py-4 border border-border-subtle bg-white rounded text-center shrink-0 min-w-[120px]">
            <span className="block text-[10px] font-bold text-on-surface-variant mb-1 uppercase tracking-wider">PENDING APPROVAL</span>
            <span className="block text-2xl font-bold text-primary">{tasks.filter(t => t.status === 'pending').length}</span>
          </div>
          <div className="px-6 py-4 border border-border-subtle bg-white rounded text-center shrink-0 min-w-[120px]">
            <span className="block text-[10px] font-bold text-on-surface-variant mb-1 uppercase tracking-wider">AVG RESPONSE</span>
            <span className="block text-2xl font-bold text-primary">—</span>
          </div>
        </div>
      </section>

      {/* Toggles bar */}
      <div className="flex gap-8 border-b border-border-subtle overflow-x-auto pb-0 select-none font-sans text-sm font-semibold">
        <button
          id="tab-identity-btn"
          onClick={() => { setActiveTab('identity'); onClearFocus(); }}
          className={`pb-4 px-1 border-b-2 whitespace-nowrap cursor-pointer transition-colors ${
            activeTab === 'identity' ? 'border-primary text-primary font-bold' : 'border-transparent text-on-surface-variant hover:text-primary'
          }`}
        >
          Identity Conflicts ({counts.identity})
        </button>
        <button
          id="tab-outreach-btn"
          onClick={() => { setActiveTab('outreach'); onClearFocus(); }}
          className={`pb-4 px-1 border-b-2 whitespace-nowrap cursor-pointer transition-colors ${
            activeTab === 'outreach' ? 'border-primary text-primary font-bold' : 'border-transparent text-on-surface-variant hover:text-primary'
          }`}
        >
          Pending Outreach Drafts ({counts.outreach})
        </button>
        <button
          id="tab-compliance-btn"
          onClick={() => { setActiveTab('compliance'); onClearFocus(); }}
          className={`pb-4 px-1 border-b-2 whitespace-nowrap cursor-pointer transition-colors ${
            activeTab === 'compliance' ? 'border-primary text-primary font-bold' : 'border-transparent text-on-surface-variant hover:text-primary'
          }`}
        >
          Compliance Flags ({counts.compliance})
        </button>
      </div>

      {/* Main interactive Tasks container */}
      <div className="space-y-8">
        {filteredTasks.length === 0 ? (
          <div className="p-12 text-center border border-dashed border-border-subtle rounded-lg bg-surface min-h-[300px] flex flex-col items-center justify-center space-y-4 font-sans">
            <Check className="w-12 h-12 text-status-ok bg-green-50 p-2.5 rounded-full" />
            <h4 className="font-bold text-slate-800 text-sm">Review Category Complete</h4>
            <p className="text-xs text-on-surface-variant max-w-xs leading-relaxed">
              All outstanding records for this validation stage are synchronised and locked in local memory.
            </p>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isHighlighted = focusedTaskId === task.id;

            return (
              <article
                id={`task-article-${task.id}`}
                key={task.id}
                className={`border rounded-md overflow-hidden bg-white transition-all ${
                  isHighlighted ? 'ring-2 ring-primary border-primary shadow-md' : 'border-border-subtle'
                }`}
              >
                {isHighlighted && (
                  <div className="bg-primary text-white text-[10px] font-mono py-1.5 px-6 uppercase tracking-wider font-semibold flex items-center justify-between">
                    <span>⚡ Highlighted Context Triggered from Core Match Matrix</span>
                    <button onClick={onClearFocus} className="underline hover:text-amber-300">Clear Focus</button>
                  </div>
                )}

                {/* Card Header */}
                <div className="px-6 py-4 bg-surface border-b border-border-subtle flex flex-col sm:flex-row justify-between sm:items-center gap-2 select-none">
                  <div className="flex items-center gap-3">
                    {task.type === 'IDENTITY_CONFLICT' && <GitMerge className="w-5 h-5 text-bloodhound-orange" />}
                    {task.type === 'COMPLIANCE_FLAG' && <Gavel className="w-5 h-5 text-status-error" />}
                    {task.type === 'OUTREACH_DRAFT' && <Mail className="w-5 h-5 text-indigo-700" />}
                    <span className="text-xs font-mono font-bold uppercase tracking-wider text-on-surface-variant">
                      {task.type.replace('_', ' ')} — TASK ID: #{task.id}
                    </span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="px-3 py-0.5 bg-surface-container-high text-on-surface font-mono font-semibold text-[11px] rounded-full">
                      CONFIDENCE: {task.confidence.toFixed(2)}
                    </span>
                    <span className="text-on-surface-variant font-mono text-[11px] font-medium">{task.timeAgo}</span>
                  </div>
                </div>

                {/* Type A: IDENTITY_CONFLICT */}
                {task.type === 'IDENTITY_CONFLICT' && task.existingRecord && task.proposedRecord && (
                  <div>
                    <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border-subtle h-auto md:h-[320px] bg-white">
                      <div className="p-6 overflow-y-auto custom-scrollbar">
                        <div className="mb-4 flex justify-between items-center select-none">
                          <h4 className="text-[11px] font-mono uppercase font-bold text-on-surface-variant">EXISTING RECORD (A)</h4>
                          <span className="text-[10px] font-mono text-on-surface-variant opacity-65">UUID: {task.existingRecord.uuid.substring(0, 8)}...</span>
                        </div>
                        <div className="space-y-4 font-sans text-xs">
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">NAME</span>
                            <p className="text-primary font-bold text-sm text-slate-900">{task.existingRecord.name}</p>
                          </div>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">CURRENT ROLE</span>
                            <p className="text-on-surface text-xs">{task.existingRecord.currentRole}</p>
                          </div>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">LOCATION</span>
                            <p className="text-on-surface text-xs">{task.existingRecord.location}</p>
                          </div>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">LINKEDIN URL</span>
                            <a href={task.existingRecord.linkedin} target="_blank" rel="noreferrer" className="text-bloodhound-crimson hover:underline flex items-center gap-1">
                              <span>{task.existingRecord.linkedin}</span>
                              <ExternalLink className="w-3.5 h-3.5" />
                            </a>
                          </div>
                        </div>
                      </div>

                      <div className="p-6 overflow-y-auto bg-surface-container-low custom-scrollbar">
                        <div className="mb-4 flex justify-between items-center select-none">
                          <h4 className="text-[11px] font-mono uppercase font-bold text-on-surface-variant">PROPOSED RECORD (B)</h4>
                          <span className="text-[10px] font-mono text-status-review font-semibold">SOURCE: {task.proposedRecord.source}</span>
                        </div>
                        <div className="space-y-4 font-sans text-xs">
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">NAME</span>
                            <p className="text-slate-900 font-bold text-sm">{task.proposedRecord.name}</p>
                          </div>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">UPDATED ROLE DIFF</span>
                            <p className="bg-green-50 text-status-ok border-l-2 border-status-ok px-2 py-1 flex items-center gap-1 text-[11px] leading-tight select-none">
                              <span>+</span>
                              <span>{task.proposedRecord.addedRole}</span>
                            </p>
                            <p className="bg-red-50 text-bloodhound-crimson border-l-2 border-bloodhound-crimson px-2 py-0.5 flex items-center gap-1 text-[11px] line-through leading-tight opacity-75 select-none">
                              <span>-</span>
                              <span>{task.proposedRecord.removedRole}</span>
                            </p>
                          </div>
                          <div className="flex flex-col gap-1">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">LOCATION DIFF</span>
                            <p className="bg-green-50 text-status-ok border-l-2 border-status-ok px-2 py-1 text-[11px]">
                              + {task.proposedRecord.location}
                            </p>
                          </div>
                          <div className="flex flex-col gap-0.5">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-on-surface-variant">LINKEDIN PROVENANCE</span>
                            <p className="text-on-surface bg-white/50 border border-border-subtle p-1 px-2 rounded font-mono text-[11px] inline-block">
                              Same as Record A (Heuristic Match Approved)
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="px-6 py-4 bg-white border-t border-border-subtle flex flex-col sm:flex-row justify-between sm:items-center gap-4 font-sans text-xs">
                      <div className="flex items-center gap-2 select-none">
                        <Info className="w-4 h-4 text-status-review shrink-0" />
                        <span className="text-on-surface-variant">
                          <strong>Recommended Automation Heuristics:</strong> {task.recommendation}
                        </span>
                      </div>
                      <div className="flex gap-2.5 self-stretch sm:self-auto justify-end shrink-0">
                        <button
                          id={`reject-merge-${task.id}`}
                          onClick={() => onResolveTask(task.id, 'rejected')}
                          className="px-4 py-2 border border-border-subtle hover:bg-surface-container font-sans font-semibold rounded text-xs cursor-pointer transition-colors"
                        >
                          Reject Merge
                        </button>
                        <button
                          id={`approve-merge-${task.id}`}
                          onClick={() => onResolveTask(task.id, 'approved')}
                          className="px-6 py-2 bg-slate-deep hover:bg-black font-sans font-semibold text-white rounded text-xs cursor-pointer transition-colors flex items-center gap-1.5"
                        >
                          <Check className="w-4 h-4" />
                          <span>Approve & Merge</span>
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Type B: COMPLIANCE_FLAG */}
                {task.type === 'COMPLIANCE_FLAG' && task.complianceDetails && (
                  <div className="p-6 bg-status-error/5 border-l-4 border-l-status-error font-sans text-sm">
                    <div className="flex flex-col md:flex-row gap-6">
                      <div className="flex-1 space-y-4">
                        <h4 className="font-bold text-slate-900 font-sans text-base">
                          {task.complianceDetails.reason}
                        </h4>
                        <p className="text-xs text-on-surface-variant leading-relaxed">
                          {task.complianceDetails.reason === 'missing_consent'
                            ? <>No consent basis is recorded for <span className="font-semibold text-slate-800">{task.complianceDetails.candidateName}</span>. Upload consent proof to approve, or purge the record.</>
                            : task.complianceDetails.reason === 'low_extraction_confidence'
                            ? <>Extraction confidence for <span className="font-semibold text-slate-800">{task.complianceDetails.candidateName}</span> is below the required threshold. Review the extracted data and approve or purge.</>
                            : <>A compliance flag was raised for <span className="font-semibold text-slate-800">{task.complianceDetails.candidateName}</span>: {task.complianceDetails.reason}. Review the record before proceeding.</>}
                        </p>
                        <div className="bg-white border border-border-subtle p-4 font-mono text-xs text-status-error rounded block whitespace-pre overflow-x-auto select-all leading-relaxed">
                          {task.complianceDetails.details}
                        </div>
                      </div>

                      <div className="w-full md:w-72 bg-white border border-border-subtle p-5 rounded-md flex flex-col justify-between">
                        <div>
                          <span className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-2">
                            QUARANTINE DATA BLOCKED
                          </span>
                          <div className="p-2.5 bg-surface text-on-surface font-mono text-[11px] tracking-wide text-center blur-xs rounded select-none border border-slate-100">
                            {task.complianceDetails.quarantineValue}
                          </div>
                        </div>
                        <div className="space-y-3.5 mt-8">
                          <button
                            id={`purge-compliance-${task.id}`}
                            onClick={() => onResolveTask(task.id, 'purged')}
                            className="w-full py-2 bg-bloodhound-crimson hover:bg-red-800 text-white font-semibold text-xs rounded cursor-pointer transition-colors flex items-center justify-center gap-1.5"
                          >
                            <X className="w-4 h-4" />
                            <span>Purge Non-Compliant Data</span>
                          </button>
                          <button
                            id={`whitelist-compliance-${task.id}`}
                            onClick={() => onResolveTask(task.id, 'approved')}
                            className="w-full py-2 border border-border-subtle text-slate-700 hover:bg-slate-50 font-semibold text-xs rounded cursor-pointer transition-colors"
                          >
                            {task.complianceDetails.reason === 'missing_consent' ? 'Upload Consent Proof' : 'Approve Extracted Data'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Type C: OUTREACH_DRAFT */}
                {task.type === 'OUTREACH_DRAFT' && task.outreachDetails && (
                  <div className="p-6 font-sans">
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                      <div className="md:col-span-2 space-y-3 font-sans">
                        <label className="block text-[10px] font-bold font-mono tracking-wider text-on-surface-variant uppercase">
                          AI-GENERATED PERSUASION OUTREACH (DRAFT V2)
                        </label>
                        <div className="border border-border-subtle p-6 bg-surface-container-lowest font-sans italic text-sm text-slate-800 leading-relaxed rounded quotes border-l-4 border-l-slate-400">
                          {task.outreachDetails.draftBody}
                        </div>
                      </div>

                      <div className="space-y-6 flex flex-col justify-between">
                        <div>
                          <label className="block text-[10px] font-bold font-mono tracking-wider text-on-surface-variant uppercase mb-3">
                            PERSONALIZATION TRIGGERS
                          </label>
                          <ul className="space-y-2.5 text-xs text-status-ok font-semibold">
                            {task.outreachDetails.signals.map((sig) => (
                              <li key={sig} className="flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-status-ok shrink-0"></span>
                                <span>{sig}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="space-y-3">
                          <button
                            id={`send-outreach-${task.id}`}
                            onClick={() => onResolveTask(task.id, 'approved')}
                            className="w-full py-2.5 bg-slate-deep hover:bg-black text-white font-semibold text-xs rounded cursor-pointer transition-colors flex items-center justify-center gap-1.5"
                          >
                            <Mail className="w-4 h-4" />
                            <span>Commit & Send Outreach</span>
                          </button>
                          <button
                            id={`edit-outreach-${task.id}`}
                            onClick={() => navigator.clipboard.writeText(task.outreachDetails?.draftBody ?? '')}
                            className="w-full py-2 border border-border-subtle text-slate-700 hover:bg-slate-50 font-semibold text-xs rounded cursor-pointer transition-colors"
                          >
                            Copy Draft
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

              </article>
            );
          })
        )}
      </div>

      {/* B4 fix: Live Audit Log Stream — driven by real auditEvents prop */}
      <section className="border-t border-border-subtle pt-12 pb-8">
        <div className="flex justify-between items-center mb-6 select-none font-sans">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-on-surface-variant" />
            <h3 className="font-sans font-bold text-sm text-primary">Live Review Session Trail</h3>
          </div>
          <button
            onClick={() => onNavigate('audit')}
            className="text-bloodhound-crimson font-bold font-mono text-xs hover:underline cursor-pointer uppercase tracking-wider"
          >
            VIEW FULL events.jsonl
          </button>
        </div>

        <div className="bg-slate-deep text-white p-6 font-mono text-[12px] rounded-md space-y-2.5 shadow-xl">
          {liveTrail.length === 0 ? (
            <div className="flex gap-4 opacity-50">
              <span className="text-amber-400">ACTION: Human decision engine fully synchronized. Awaiting input for active session...</span>
            </div>
          ) : (
            liveTrail.map((evt, i) => (
              <div
                key={evt.id}
                className={`flex gap-4 ${i < liveTrail.length - 1 ? 'opacity-50' : ''}`}
              >
                <span className="text-status-ok shrink-0">[{evt.timestamp}]</span>
                <span className={i === liveTrail.length - 1 ? 'text-amber-400' : ''}>
                  {evt.actor}: {evt.payloadSummary}
                </span>
              </div>
            ))
          )}
        </div>
      </section>

    </div>
  );
}
