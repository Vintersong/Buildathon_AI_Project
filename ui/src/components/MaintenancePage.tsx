import { useEffect, useMemo, useState } from 'react';
import { Activity, DatabaseZap, FolderSync, Loader2, RotateCcw, ShieldCheck } from 'lucide-react';
import * as api from '../api';
import { AuditEvent, Candidate, ReviewTask, StaleCandidate } from '../types';

interface MaintenancePageProps {
  candidates: Candidate[];
  reviewTasks: ReviewTask[];
  auditEvents: AuditEvent[];
  onRefresh: () => Promise<void>;
  onToast: (message: string, type?: 'success' | 'info' | 'error') => void;
}

export default function MaintenancePage({
  candidates,
  reviewTasks,
  auditEvents,
  onRefresh,
  onToast,
}: MaintenancePageProps) {
  const [months, setMonths] = useState(6);
  const [stale, setStale] = useState<StaleCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loadingStale, setLoadingStale] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [intakeLimit, setIntakeLimit] = useState(25);

  const pending = reviewTasks.filter((task) => task.status === 'pending').length;
  const complianceCoverage = useMemo(() => {
    if (!candidates.length) return 0;
    return Math.round((candidates.filter((candidate) => candidate.complianceStatus === 'COMPLIANT').length / candidates.length) * 100);
  }, [candidates]);

  const scanStale = async () => {
    setLoadingStale(true);
    try {
      const result = await api.fetchStaleCandidates(months);
      setStale(result.candidates);
      setSelected(new Set());
      onToast(`Found ${result.candidates.length} stale profile${result.candidates.length === 1 ? '' : 's'}.`, 'info');
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Stale scan failed', 'error');
    } finally {
      setLoadingStale(false);
    }
  };

  useEffect(() => {
    scanStale();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const processIntake = async () => {
    setProcessing(true);
    try {
      const result = await api.processIntake(intakeLimit);
      onToast(`Intake processed ${result.processed}, skipped ${result.skipped}, failed ${result.failed}.`, result.failed ? 'info' : 'success');
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Intake processing failed', 'error');
    } finally {
      setProcessing(false);
    }
  };

  const refreshSelected = async () => {
    if (selected.size === 0) return;
    setRefreshing(true);
    try {
      const result = await api.bulkRefreshCandidates([...selected]);
      onToast(`Bulk refresh complete: ${result.success} succeeded, ${result.failed} failed.`, result.failed ? 'info' : 'success');
      await scanStale();
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Bulk refresh failed', 'error');
    } finally {
      setRefreshing(false);
    }
  };

  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="space-y-6 pb-20 lg:pb-0">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          { label: 'Pool size', value: candidates.length, detail: 'Active candidate records', icon: DatabaseZap },
          { label: 'Pending reviews', value: pending, detail: 'Human decisions waiting', icon: ShieldCheck },
          { label: 'Audit events', value: auditEvents.length, detail: 'Recorded provenance entries', icon: Activity },
          { label: 'Compliance coverage', value: `${complianceCoverage}%`, detail: 'Profiles currently compliant', icon: ShieldCheck },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <section key={item.label} className="rounded-md border border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-slate-500">{item.label}</p>
                  <p className="mt-2 text-3xl font-semibold text-slate-950">{item.value}</p>
                </div>
                <div className="rounded-md bg-cyan-50 p-2 text-cyan-700">
                  <Icon className="h-5 w-5" />
                </div>
              </div>
              <p className="mt-4 text-sm text-slate-500">{item.detail}</p>
            </section>
          );
        })}
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_1fr]">
        <section className="space-y-5">
          <div className="rounded-md border border-slate-200 bg-white p-5">
            <div className="flex items-center gap-2">
              <FolderSync className="h-5 w-5 text-cyan-700" />
              <h2 className="text-base font-semibold text-slate-950">Process Intake Folder</h2>
            </div>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Ingests supported files from the configured intake directory and records provenance for each attempt.
            </p>
            <label className="mt-4 block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Batch limit</span>
              <input
                type="number"
                min={1}
                max={500}
                value={intakeLimit}
                onChange={(event) => setIntakeLimit(Number(event.target.value))}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>
            <button
              type="button"
              onClick={processIntake}
              disabled={processing}
              className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md bg-slate-900 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {processing ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderSync className="h-4 w-4" />}
              Process intake
            </button>
          </div>

          <div className="rounded-md border border-slate-200 bg-white p-5">
            <h2 className="text-base font-semibold text-slate-950">Stale Profile Scan</h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Finds profiles not refreshed within the selected age. Refresh uses stored CV/profile text and provided URLs only.
            </p>
            <label className="mt-4 block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Older than months</span>
              <input
                type="number"
                min={1}
                max={60}
                value={months}
                onChange={(event) => setMonths(Number(event.target.value))}
                className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
              />
            </label>
            <button
              type="button"
              onClick={scanStale}
              disabled={loadingStale}
              className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {loadingStale ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              Scan stale profiles
            </button>
          </div>
        </section>

        <section className="rounded-md border border-slate-200 bg-white">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-5 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Stale Candidates</h2>
              <p className="mt-1 text-sm text-slate-500">Select candidates and run a reviewed refresh pass.</p>
            </div>
            <button
              type="button"
              onClick={refreshSelected}
              disabled={selected.size === 0 || refreshing}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              Refresh selected ({selected.size})
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {stale.map((candidate) => (
              <label key={candidate.id} className="flex cursor-pointer items-start gap-4 p-4 hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={selected.has(candidate.id)}
                  onChange={() => toggle(candidate.id)}
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-cyan-500"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-semibold text-slate-950">{candidate.name}</p>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{candidate.complianceStatus}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-500">{candidate.seniority || 'Unknown seniority'} - updated {candidate.updatedAt || 'unknown'}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {candidate.topSkills.slice(0, 4).map((skill) => (
                      <span key={skill} className="rounded-full bg-cyan-50 px-2 py-1 text-xs font-medium text-cyan-800">{skill}</span>
                    ))}
                  </div>
                </div>
              </label>
            ))}
            {stale.length === 0 && (
              <div className="p-10 text-center">
                <p className="text-sm font-medium text-slate-700">No stale candidates found for this threshold.</p>
                <p className="mt-1 text-sm text-slate-500">Adjust the month window or process intake for new profiles.</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
