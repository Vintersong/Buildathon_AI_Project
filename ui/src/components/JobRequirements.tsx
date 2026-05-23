/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useMemo, useEffect } from 'react';
import { User, Plus, FileDown, Briefcase, Trash, RotateCcw } from 'lucide-react';
import { JobRequirement, ReviewTask } from '../types';

interface JobRequirementsProps {
  jobs: (JobRequirement & { _dismissedCount?: number })[];
  searchQuery: string;
  onNavigate: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
  onOpenReviewTask: (taskId: string) => void;
  onAddJob: (job: Omit<JobRequirement, 'id' | 'candidatesProcessed' | 'shortlist'>) => void;
  reviewTasks: ReviewTask[];
  onBulkDismiss?: (jobId: string) => void;
  onRestoreDismissed?: (jobId: string) => void;
}

export default function JobRequirements({
  jobs,
  searchQuery,
  onNavigate,
  onOpenReviewTask,
  onAddJob,
  reviewTasks,
  onBulkDismiss,
  onRestoreDismissed,
}: JobRequirementsProps) {
  const [selectedJobId, setSelectedJobId] = useState<string>(jobs[0]?.id || '');
  const [showAddJobForm, setShowAddJobForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDeps, setNewDeps] = useState('Fintech Core Platform');
  const [newLoc, setNewLoc] = useState('Austin/Remote');

  // B3 fix: reset selection when current job disappears from the list
  useEffect(() => {
    if (jobs.length === 0) {
      setSelectedJobId('');
      return;
    }
    const stillExists = jobs.some((j) => j.id === selectedJobId);
    if (!stillExists) {
      setSelectedJobId(jobs[0].id);
    }
  }, [jobs, selectedJobId]);

  const filteredJobs = useMemo(() => {
    return jobs.filter((job) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          job.title.toLowerCase().includes(q) ||
          job.department.toLowerCase().includes(q) ||
          job.location.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [jobs, searchQuery]);

  const activeJob = useMemo(() => {
    return jobs.find((j) => j.id === selectedJobId) || jobs[0];
  }, [jobs, selectedJobId]);

  const handleCreateJob = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    onAddJob({
      title: newTitle.trim(),
      department: newDeps,
      location: newLoc,
      status: 'MATCHING',
      tags: ['MATCHING', 'NEW']
    });
    setNewTitle('');
    setShowAddJobForm(false);
  };

  const activeDismissedCount = (activeJob as any)?._dismissedCount ?? 0;

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-on-surface">Job Match Matrix</h2>
          <p className="text-sm font-sans text-on-surface-variant mt-1.5 max-w-2xl">
            Precision alignment engine leveraging LLM re-ranking for elite technical placements.
          </p>
        </div>
        <div className="flex gap-4">
          <button
            id="export-report-btn"
            onClick={() => {
              const blob = new Blob([JSON.stringify(jobs, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'jobs_export.json';
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="border border-border-subtle hover:bg-surface-container px-6 py-2 rounded text-xs font-semibold text-on-surface transition-colors cursor-pointer flex items-center gap-2"
          >
            <FileDown className="w-4 h-4 text-on-surface-variant" />
            <span>Export Report</span>
          </button>
          <button
            id="create-job-btn"
            onClick={() => setShowAddJobForm(!showAddJobForm)}
            className="bg-primary hover:opacity-90 text-white px-6 py-2 rounded text-xs font-semibold transition-colors cursor-pointer flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Create New Job</span>
          </button>
        </div>
      </header>

      {/* Add Job Form */}
      {showAddJobForm && (
        <form onSubmit={handleCreateJob} className="p-6 bg-surface border border-slate-deep rounded-md space-y-4 font-sans max-w-md animate-in slide-in-from-top-6 duration-200">
          <h4 className="font-bold text-sm text-slate-900 font-sans">Initialize Technical Requirement</h4>
          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-700 font-bold mb-1">JOB REQUIREMENT TITLE</label>
              <input
                id="new-job-title"
                type="text"
                required
                placeholder="e.g. Senior Backend / Rust Engineer"
                className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-slate-700 font-bold mb-1">DEPARTMENT</label>
                <input
                  id="new-job-dept"
                  type="text"
                  className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface"
                  value={newDeps}
                  onChange={(e) => setNewDeps(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-slate-700 font-bold mb-1">LOCATION TYPE</label>
                <input
                  id="new-job-location"
                  type="text"
                  className="w-full px-3 py-2 border border-border-subtle rounded focus:outline-none focus:ring-1 focus:ring-slate-deep bg-white text-on-surface"
                  value={newLoc}
                  onChange={(e) => setNewLoc(e.target.value)}
                />
              </div>
            </div>
          </div>
          <div className="flex gap-2 justify-end pt-2">
            <button id="cancel-job-form" type="button" onClick={() => setShowAddJobForm(false)} className="px-3 py-1.5 border border-border-subtle rounded text-xs hover:bg-white cursor-pointer">Cancel</button>
            <button id="submit-job-form" type="submit" className="px-4 py-1.5 bg-slate-deep text-white rounded text-xs font-semibold hover:bg-black cursor-pointer">Confirm Deployment</button>
          </div>
        </form>
      )}

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-8 h-[calc(100vh-220px)] min-h-[500px]">

        {/* Left: Job List */}
        <div className="md:col-span-4 flex flex-col gap-4 h-full overflow-hidden select-none">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold font-sans uppercase tracking-wider text-on-surface-variant">
              ACTIVE REQUIREMENTS ({filteredJobs.length})
            </h3>
            <span className="text-[10px] font-mono tracking-wide bg-surface-container-high px-2 py-0.5 rounded font-bold">AUTO-REFRESH: ON</span>
          </div>

          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar flex flex-col gap-3">
            {filteredJobs.length === 0 ? (
              <div className="text-center py-12 text-xs text-on-surface-variant border border-dashed border-border-subtle rounded-lg">No active jobs. Click 'Create New Job' above.</div>
            ) : (
              filteredJobs.map((job) => {
                const isActive = job.id === selectedJobId;
                const isMatching = job.status === 'MATCHING';
                const isValidating = job.status === 'VALIDATING';
                const isArchived = job.status === 'ARCHIVED';
                const jobDismissedCount = (job as any)._dismissedCount ?? 0;

                let badgeColor = 'bg-surface-container-high text-on-surface-variant';
                if (isMatching) badgeColor = 'bg-status-ok/10 text-status-ok border border-status-ok/20';
                if (isValidating) badgeColor = 'bg-status-review/10 text-status-review border border-status-review/20';
                if (isArchived) badgeColor = 'bg-status-archived/10 text-status-archived border border-status-archived/20';

                return (
                  <div
                    id={`job-card-${job.id}`}
                    key={job.id}
                    onClick={() => setSelectedJobId(job.id)}
                    className={`p-5 rounded-lg cursor-pointer transition-all ${
                      isActive ? 'bg-white border-2 border-primary shadow-xs' : 'bg-white border border-border-subtle hover:border-slate-400'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2 gap-2">
                      <h4 className={`text-sm font-sans font-bold leading-tight ${isActive ? 'text-primary' : 'text-on-surface'}`}>{job.title}</h4>
                      <span className={`font-mono font-bold text-[10px] uppercase px-1.5 py-0.5 rounded shrink-0 ${badgeColor}`}>{job.status}</span>
                    </div>
                    <p className="text-xs text-on-surface-variant font-sans mt-1">{job.department} • {job.location}</p>
                    {jobDismissedCount > 0 && (
                      <p className="text-[10px] font-mono text-amber-600 mt-1">{jobDismissedCount} match{jobDismissedCount > 1 ? 'es' : ''} hidden</p>
                    )}
                    {job.tags && job.tags.length > 0 && (
                      <div className="flex gap-1.5 mt-4">
                        {job.tags.map((tg) => (
                          <span key={tg} className="bg-surface text-on-surface-variant font-sans text-[10px] font-semibold tracking-wider px-2 py-0.5 rounded border border-border-subtle uppercase">{tg}</span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right: Shortlist */}
        <div className="md:col-span-8 bg-white border border-border-subtle rounded-lg flex flex-col h-full overflow-hidden shrink-0">

          <div className="p-6 border-b border-border-subtle bg-surface-container-lowest flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h3 className="font-sans font-bold text-base text-primary">Candidate Shortlist</h3>
                <span className="text-on-surface-variant font-sans text-xs opacity-60">/ {activeJob ? activeJob.title : 'Details'}</span>
              </div>
              <p className="text-xs text-on-surface-variant font-sans">Top candidates ranked by Precision Reranking Engine v4.2</p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-[10px] font-sans font-bold text-on-surface-variant mb-1 uppercase tracking-wide">CANDIDATES PROCESSED</p>
              <p className="font-mono font-bold text-lg text-primary">{activeJob ? activeJob.candidatesProcessed.toLocaleString() : '1,482'}</p>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 custom-scrollbar text-sm">
            {!activeJob || !activeJob.shortlist || activeJob.shortlist.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center text-on-surface-variant font-sans space-y-4 py-12">
                <Briefcase className="w-12 h-12 text-slate-300" strokeWidth={1} />
                <p className="text-xs leading-relaxed max-w-xs">
                  No matches synced. This role is currently processed under the initial heuristic validator sequence.
                </p>
                {activeDismissedCount > 0 && (
                  <button
                    onClick={() => activeJob && onRestoreDismissed?.(activeJob.id)}
                    className="flex items-center gap-1.5 text-[11px] font-bold text-amber-700 border border-amber-300 bg-amber-50 hover:bg-amber-100 px-3 py-1.5 rounded transition-colors cursor-pointer"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Restore {activeDismissedCount} hidden match{activeDismissedCount > 1 ? 'es' : ''}
                  </button>
                )}
              </div>
            ) : (
              <table className="w-full text-left border-collapse font-sans">
                <thead>
                  <tr className="bg-surface-container-low">
                    <th className="py-3 px-4 font-sans font-bold text-[11px] text-on-surface-variant border-b border-border-subtle uppercase tracking-wider">RANK</th>
                    <th className="py-3 px-4 font-sans font-bold text-[11px] text-on-surface-variant border-b border-border-subtle uppercase tracking-wider">CANDIDATE</th>
                    <th className="py-3 px-4 font-sans font-bold text-[11px] text-on-surface-variant border-b border-border-subtle uppercase tracking-wider">CONFIDENCE</th>
                    <th className="py-3 px-4 font-sans font-bold text-[11px] text-on-surface-variant border-b border-border-subtle uppercase tracking-wider">LLM EXPLANATION</th>
                    <th className="py-3 px-4 font-sans font-bold text-[11px] text-on-surface-variant border-b border-border-subtle uppercase tracking-wider">ACTIONS</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle font-sans font-medium">
                  {activeJob.shortlist.map((candidate, rankIdx) => {
                    const rankNum = String(rankIdx + 1).padStart(2, '0');
                    const isRankOne = rankIdx === 0;
                    const isActionRequired = candidate.status === 'pending_review';

                    return (
                      <tr key={candidate.id} className={`hover:bg-slate-50 transition-colors ${isActionRequired ? 'bg-status-review/5' : ''}`}>
                        <td className={`py-4 px-4 font-mono font-bold text-xs ${isRankOne ? 'text-bloodhound-crimson' : 'text-on-surface-variant'}`}>#{rankNum}</td>

                        <td className="py-4 px-4">
                          <div className="flex items-center gap-3">
                            <div className={`w-8 h-8 rounded-full bg-surface-container-high flex items-center justify-center shrink-0 border ${isActionRequired ? 'border-status-review/50' : 'border-transparent'}`}>
                              {isActionRequired ? (
                                <span className="text-xs font-bold text-status-review">{candidate.initials}</span>
                              ) : (
                                <User className="w-4 h-4 text-on-surface-variant" />
                              )}
                            </div>
                            <div>
                              <p className="font-bold text-slate-800 leading-tight text-xs">{candidate.name}</p>
                              <p className="text-[10px] text-on-surface-variant font-mono mt-0.5">UID: {candidate.id}</p>
                            </div>
                          </div>
                        </td>

                        <td className="py-4 px-4">
                          <div className="flex items-center gap-2 max-w-[130px]">
                            <div className="flex-1 bg-surface-container-high h-1.5 w-16 rounded-full overflow-hidden shrink-0">
                              <div className={`h-full rounded-full ${isActionRequired ? 'bg-status-review' : 'bg-status-ok'}`} style={{ width: `${candidate.confidence * 100}%` }}></div>
                            </div>
                            <span className={`font-mono font-bold text-xs shrink-0 ${isActionRequired ? 'text-status-review' : 'text-status-ok'}`}>{candidate.confidence.toFixed(3)}</span>
                          </div>
                        </td>

                        <td className="py-4 px-4 max-w-xs">
                          <div className={`p-2.5 rounded border ${
                            isActionRequired
                              ? 'bg-status-review/5 border-dashed border-status-review/30 text-status-review'
                              : 'bg-surface-container-low border-border-subtle text-on-surface-variant'
                          }`}>
                            <p className="text-[11px] leading-relaxed italic font-medium font-sans">"{candidate.explanation}"</p>
                          </div>
                        </td>

                        <td className="py-4 px-4">
                          {isActionRequired ? (() => {
                            const task = reviewTasks.find(t =>
                              t.status === 'pending' && (
                                t.existingRecord?.name === candidate.name ||
                                t.complianceDetails?.candidateName === candidate.name
                              )
                            );
                            return (
                              <button
                                id={`queue-link-${candidate.id}`}
                                onClick={() => { onNavigate('review'); task && onOpenReviewTask(task.id); }}
                                disabled={!task}
                                className="bg-bloodhound-crimson hover:opacity-95 text-white px-3 py-1.5 rounded text-[10px] font-mono tracking-wider font-bold transition-all shrink-0 cursor-pointer disabled:opacity-50"
                              >
                                Review Queue
                              </button>
                            );
                          })() : (() => {
                            const task = reviewTasks.find(t =>
                              t.status === 'pending' &&
                              t.type === 'OUTREACH_DRAFT' &&
                              t.outreachDetails?.targetName === candidate.name
                            );
                            return (
                              <button
                                id={`draft-outreach-${candidate.id}`}
                                onClick={() => { onNavigate('review'); task && onOpenReviewTask(task.id); }}
                                disabled={!task}
                                className="bg-slate-deep hover:bg-black text-white px-3 py-1.5 rounded text-[10px] font-sans font-bold tracking-wider uppercase transition-all shrink-0 cursor-pointer disabled:opacity-50"
                              >
                                Draft Outreach
                              </button>
                            );
                          })()}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Bulk Actions Footer */}
          <div className="p-4 bg-surface-container-low border-t border-border-subtle flex items-center justify-between font-sans select-none shrink-0 text-xs">
            <div className="flex items-center gap-4">
              <span className="font-bold text-on-surface-variant uppercase tracking-wider text-[10px]">BULK ACTIONS:</span>
              <button
                id="bulk-dismiss-low"
                className="text-on-surface-variant hover:text-primary transition-colors flex items-center gap-1 cursor-pointer font-semibold"
                onClick={() => activeJob && onBulkDismiss?.(activeJob.id)}
              >
                <Trash className="w-3.5 h-3.5" />
                <span>Dismiss Low Matches</span>
              </button>
              {activeDismissedCount > 0 && (
                <button
                  id="restore-dismissed-btn"
                  className="text-amber-600 hover:text-amber-800 transition-colors flex items-center gap-1 cursor-pointer font-semibold"
                  onClick={() => activeJob && onRestoreDismissed?.(activeJob.id)}
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Restore {activeDismissedCount} Hidden</span>
                </button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-on-surface-variant">
                {activeJob?.shortlist?.length
                  ? `Showing ${activeJob.shortlist.length} top matches`
                  : 'No matches synced'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
