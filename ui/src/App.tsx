import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle, Sparkles, X } from 'lucide-react';
import * as api from './api';
import { AuditEvent, Candidate, JobRequirement, ReviewTask } from './types';
import Sidebar, { Screen } from './components/Sidebar';
import Header from './components/Header';
import OverviewPage from './components/OverviewPage';
import TalentPoolPage from './components/TalentPoolPage';
import JobsPage from './components/JobsPage';
import ReviewPage from './components/ReviewPage';
import MaintenancePage from './components/MaintenancePage';
import SettingsPage from './components/SettingsPage';
import IngestModal from './components/IngestModal';
import AIAgentSidebar from './components/AIAgentSidebar';
import RouteSkeleton from './components/RouteSkeleton';

type Toast = { message: string; type: 'success' | 'info' | 'error' };

export default function App() {
  const [activeScreen, setActiveScreen] = useState<Screen>('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [jobs, setJobs] = useState<JobRequirement[]>([]);
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [showIngestModal, setShowIngestModal] = useState(false);
  const [showAssistant, setShowAssistant] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [focusCandidateId, setFocusCandidateId] = useState<string | null>(null);

  const pendingReviews = useMemo(
    () => reviewTasks.filter((task) => task.status === 'pending'),
    [reviewTasks],
  );

  const showToast = (message: string, type: Toast['type'] = 'success') => {
    setToast({ message, type });
    window.setTimeout(() => setToast(null), 3600);
  };

  const refreshAll = useCallback(async () => {
    setIsSyncing(true);
    const [candidateResult, jobResult, reviewResult, auditResult] = await Promise.allSettled([
      api.fetchCandidates(),
      api.fetchJobs(),
      api.fetchReviewTasks(),
      api.fetchAuditEvents(),
    ]);
    if (candidateResult.status === 'fulfilled') setCandidates(candidateResult.value);
    if (jobResult.status === 'fulfilled') setJobs(jobResult.value);
    if (reviewResult.status === 'fulfilled') setReviewTasks(reviewResult.value);
    if (auditResult.status === 'fulfilled') setAuditEvents(auditResult.value);
    setIsLoading(false);
    setIsSyncing(false);
  }, []);

  useEffect(() => {
    refreshAll();
  }, [refreshAll]);

  const handleIngestFile = async (file: File) => {
    const candidate = await api.ingestCandidate(file);
    showToast(`Candidate ${candidate.name} added to the talent pool.`);
    setShowIngestModal(false);
    // Keep momentum: route straight to the new candidate's detail view.
    setActiveScreen('talent');
    await refreshAll();
    setFocusCandidateId(candidate.id);
  };

  const handleIngestLinkedIn = async (linkedinUrl: string) => {
    const candidate = await api.ingestLinkedInCandidate(linkedinUrl);
    showToast(`LinkedIn profile for ${candidate.name} added for review.`);
    setShowIngestModal(false);
    // LinkedIn ingest creates a review item — send the operator to the queue.
    setActiveScreen('review');
    await refreshAll();
  };

  const handleResolveTask = async (taskId: string, resolution: 'approved' | 'rejected' | 'purged') => {
    await api.resolveTask(taskId, resolution);
    showToast(`Review task ${taskId.slice(0, 8)} resolved.`);
    await refreshAll();
  };

  const renderScreen = () => {
    if (isLoading) {
      return <RouteSkeleton screen={activeScreen} />;
    }
    if (activeScreen === 'overview') {
      return (
        <OverviewPage
          candidates={candidates}
          jobs={jobs}
          reviewTasks={reviewTasks}
          auditEvents={auditEvents}
          isLoading={isLoading}
          onNavigate={setActiveScreen}
        />
      );
    }
    if (activeScreen === 'talent') {
      return (
        <TalentPoolPage
          candidates={candidates}
          searchQuery={searchQuery}
          initialCandidateId={focusCandidateId}
          onOpenIngest={() => setShowIngestModal(true)}
          onRefresh={refreshAll}
          onToast={showToast}
          onConsumeInitial={() => setFocusCandidateId(null)}
        />
      );
    }
    if (activeScreen === 'jobs') {
      return (
        <JobsPage
          jobs={jobs}
          searchQuery={searchQuery}
          onRefresh={refreshAll}
          onToast={showToast}
          onNavigate={setActiveScreen}
        />
      );
    }
    if (activeScreen === 'review') {
      return (
        <ReviewPage
          tasks={reviewTasks}
          auditEvents={auditEvents}
          onResolve={handleResolveTask}
        />
      );
    }
    if (activeScreen === 'maintenance') {
      return (
        <MaintenancePage
          candidates={candidates}
          reviewTasks={reviewTasks}
          auditEvents={auditEvents}
          onRefresh={refreshAll}
          onToast={showToast}
        />
      );
    }
    return (
      <SettingsPage
        candidatesCount={candidates.length}
        jobsCount={jobs.filter((job) => job.status === 'MATCHING').length}
        tasksCount={pendingReviews.length}
      />
    );
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Sidebar
        activeScreen={activeScreen}
        pendingReviewsCount={pendingReviews.length}
        onNavigate={(screen) => {
          setActiveScreen(screen);
          setSearchQuery('');
        }}
      />

      <div className="min-h-screen pl-0 lg:pl-72">
        <Header
          activeScreen={activeScreen}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          isSyncing={isSyncing}
          pendingReviewsCount={pendingReviews.length}
          onRefresh={refreshAll}
          onOpenIngest={() => setShowIngestModal(true)}
          onToggleAssistant={() => setShowAssistant((value) => !value)}
        />

        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {renderScreen()}
        </main>
      </div>

      {showIngestModal && (
        <IngestModal
          onClose={() => setShowIngestModal(false)}
          onIngestFile={handleIngestFile}
          onIngestLinkedIn={handleIngestLinkedIn}
        />
      )}

      <AIAgentSidebar
        isOpen={showAssistant}
        activeScreen={activeScreen}
        candidates={candidates}
        jobs={jobs}
        reviewTasks={reviewTasks}
        onClose={() => setShowAssistant(false)}
        onActionCompleted={refreshAll}
      />

      {toast && (
        <div className="fixed bottom-5 right-5 z-50 max-w-sm rounded-md border border-slate-200 bg-white p-4 shadow-lg">
          <div className="flex gap-3">
            {toast.type === 'error' ? (
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
            ) : toast.type === 'info' ? (
              <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-blue-600" />
            ) : (
              <CheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
            )}
            <p className="text-sm text-slate-700">{toast.message}</p>
            <button
              type="button"
              aria-label="Dismiss notification"
              className="ml-auto rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              onClick={() => setToast(null)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
