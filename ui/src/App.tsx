/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from 'react';
import { Sparkles, X } from 'lucide-react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import CandidatePool from './components/CandidatePool';
import JobRequirements from './components/JobRequirements';
import ReviewQueue from './components/ReviewQueue';
import AuditLogs from './components/AuditLogs';
import SettingsPage from './components/SettingsPage';
import IngestModal from './components/IngestModal';
import AIAgentSidebar from './components/AIAgentSidebar';
import { Candidate, AuditEvent, JobRequirement, ReviewTask } from './types';
import * as api from './api';

export default function App() {
  const [activeScreen, setActiveScreen] = useState<'candidates' | 'jobs' | 'review' | 'audit' | 'settings'>('candidates');
  const [searchQuery, setSearchQuery] = useState('');

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobs, setJobs] = useState<JobRequirement[]>([]);
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);

  const [isSynced, setIsSynced] = useState(true);
  const [notificationsCount, setNotificationsCount] = useState(0);
  const [showIngestModal, setShowIngestModal] = useState(false);
  const [focusedTaskId, setFocusedTaskId] = useState<string | undefined>(undefined);
  const [showAICopilot, setShowAICopilot] = useState(false);
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'info' | 'error' } | null>(null);

  const triggerToast = (message: string, type: 'success' | 'info' | 'error' = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const markSyncing = () => {
    setIsSynced(false);
    setTimeout(() => setIsSynced(true), 600);
  };

  const refreshAll = useCallback(async () => {
    markSyncing();
    const [c, j, r, a] = await Promise.allSettled([
      api.fetchCandidates(),
      api.fetchJobs(),
      api.fetchReviewTasks(),
      api.fetchAuditEvents(),
    ]);
    if (c.status === 'fulfilled') setCandidates(c.value);
    if (j.status === 'fulfilled') setJobs(j.value);
    if (r.status === 'fulfilled') {
      setReviewTasks(r.value);
      setNotificationsCount(r.value.filter((t) => t.status === 'pending').length);
    }
    if (a.status === 'fulfilled') setAuditEvents(a.value);
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  // 1. Ingest Candidate — receives File from the updated IngestModal
  const handleIngestCandidate = async (file: File) => {
    markSyncing();
    try {
      const newCand = await api.ingestCandidate(file);
      const [updatedCandidates, updatedAudit] = await Promise.all([
        api.fetchCandidates(),
        api.fetchAuditEvents(),
      ]);
      setCandidates(updatedCandidates);
      setAuditEvents(updatedAudit);
      setNotificationsCount((c) => c + 1);
      triggerToast(`Candidate ${newCand.name} Successfully Ingested! ID: ${newCand.id}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      triggerToast(`Ingest failed: ${msg}`, 'error');
    } finally {
      setIsSynced(true);
    }
  };

  // 2. Resolve review task
  const handleResolveTask = async (taskId: string, outcome: 'approved' | 'rejected' | 'purged') => {
    markSyncing();
    try {
      await api.resolveTask(taskId, outcome);
      const [updatedTasks, updatedAudit] = await Promise.all([
        api.fetchReviewTasks(),
        api.fetchAuditEvents(),
      ]);
      setReviewTasks(updatedTasks);
      setAuditEvents(updatedAudit);
      setNotificationsCount(updatedTasks.filter((t) => t.status === 'pending').length);
      triggerToast(`Decision Committed: Task #${taskId} has been successfully verified.`);
      if (focusedTaskId === taskId) setFocusedTaskId(undefined);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      triggerToast(`Resolve failed: ${msg}`, 'error');
    } finally {
      setIsSynced(true);
    }
  };

  // 3. Add Job Requirement
  const handleAddJob = async (newJob: Omit<JobRequirement, 'id' | 'candidatesProcessed' | 'shortlist'>) => {
    markSyncing();
    try {
      await api.createJob({ ...newJob, must_have: newJob.tags });
      const updatedJobs = await api.fetchJobs();
      setJobs(updatedJobs);
      triggerToast(`Requirement '${newJob.title}' deployed on matching matrix!`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      triggerToast(`Create job failed: ${msg}`, 'error');
    } finally {
      setIsSynced(true);
    }
  };

  // 4. Direct compliance status override (optimistic UI)
  const handleResolveCandidateDirectly = (id: string, newStatus: Candidate['complianceStatus']) => {
    setCandidates((prev) => prev.map((c) => (c.id === id ? { ...c, complianceStatus: newStatus } : c)));
    triggerToast('Direct status override completed for Candidate record.');
  };

  return (
    <div className="flex bg-canvas min-h-screen relative text-slate-800 antialiased selection:bg-surface-container-highest">

      <Sidebar
        activeScreen={activeScreen}
        onNavigate={(screen) => {
          setActiveScreen(screen);
          setFocusedTaskId(undefined);
        }}
        onOpenIngest={() => setShowIngestModal(true)}
        pendingReviewsCount={reviewTasks.filter((t) => t.status === 'pending').length}
      />

      <div className="flex-1 flex flex-col min-w-0 bg-white">

        <Header
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          activeScreen={activeScreen}
          isSynced={isSynced}
          onForceSync={() => {
            refreshAll().then(() => triggerToast('Manually flushed transactional nodes to record_index.json'));
          }}
          notificationsCount={notificationsCount}
          isAICopilotOpen={showAICopilot}
          onToggleAICopilot={() => setShowAICopilot((v) => !v)}
          onBellClick={() => setActiveScreen('review')}
        />

        <main className="flex-grow p-8 max-w-[1400px] mx-auto w-full overflow-y-auto">

          {activeScreen === 'candidates' && (
            <CandidatePool
              candidates={candidates}
              searchQuery={searchQuery}
              onNavigate={(sc) => { setActiveScreen(sc); setSearchQuery(''); }}
              onOpenReviewTask={(taskId) => { setFocusedTaskId(taskId); setActiveScreen('review'); }}
              onResolveCandidateDirectly={handleResolveCandidateDirectly}
              recentLogs={auditEvents}
              reviewTasks={reviewTasks}
            />
          )}

          {activeScreen === 'jobs' && (
            <JobRequirements
              jobs={jobs}
              searchQuery={searchQuery}
              onNavigate={(sc) => { setActiveScreen(sc); setSearchQuery(''); }}
              onOpenReviewTask={(taskId) => { setFocusedTaskId(taskId); setActiveScreen('review'); }}
              onAddJob={handleAddJob}
              reviewTasks={reviewTasks}
              onBulkDismiss={refreshAll}
            />
          )}

          {activeScreen === 'review' && (
            <ReviewQueue
              tasks={reviewTasks}
              onResolveTask={handleResolveTask}
              focusedTaskId={focusedTaskId}
              onClearFocus={() => setFocusedTaskId(undefined)}
              onNavigate={(sc) => { setActiveScreen(sc); setSearchQuery(''); }}
            />
          )}

          {activeScreen === 'audit' && (
            <AuditLogs
              events={auditEvents}
              searchQuery={searchQuery}
            />
          )}

          {activeScreen === 'settings' && (
            <SettingsPage
              candidatesCount={candidates.length}
              jobsCount={jobs.filter((j) => j.status === 'MATCHING').length}
              tasksCount={reviewTasks.filter((t) => t.status === 'pending').length}
            />
          )}

        </main>
      </div>

      {showIngestModal && (
        <IngestModal
          onClose={() => setShowIngestModal(false)}
          onIngest={handleIngestCandidate}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-[200] transform slide-in-from-bottom-5 duration-300 font-sans">
          <div className="bg-slate-deep border-l-4 border-l-amber-500 text-white font-sans p-4 rounded-lg shadow-2xl flex items-center gap-3 min-w-[320px] max-w-md">
            <Sparkles className="w-5 h-5 text-amber-500 shrink-0" />
            <div className="flex-1">
              <p className="text-xs">{toast.message}</p>
            </div>
            <button onClick={() => setToast(null)} className="text-white hover:text-amber-500 shrink-0 cursor-pointer">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <AIAgentSidebar
        isOpen={showAICopilot}
        onClose={() => setShowAICopilot(false)}
        candidates={candidates}
        jobs={jobs}
        reviewTasks={reviewTasks}
      />

    </div>
  );
}
