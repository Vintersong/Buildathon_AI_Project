import { ArrowRight, ClipboardList, Database, ShieldCheck, TrendingUp } from 'lucide-react';
import { AuditEvent, Candidate, JobRequirement, ReviewTask } from '../types';
import { Screen } from './Sidebar';

interface OverviewPageProps {
  candidates: Candidate[];
  jobs: JobRequirement[];
  reviewTasks: ReviewTask[];
  auditEvents: AuditEvent[];
  isLoading: boolean;
  onNavigate: (screen: Screen) => void;
}

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function Metric({
  label,
  value,
  detail,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  detail: string;
  icon: typeof Database;
}) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-slate-500">{label}</p>
          <div className="mt-2 text-3xl font-semibold text-slate-950">{value}</div>
        </div>
        <div className="rounded-md bg-cyan-50 p-2 text-cyan-700">
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <p className="mt-4 text-sm leading-5 text-slate-500">{detail}</p>
    </section>
  );
}

export default function OverviewPage({
  candidates,
  jobs,
  reviewTasks,
  auditEvents,
  isLoading,
  onNavigate,
}: OverviewPageProps) {
  const pending = reviewTasks.filter((task) => task.status === 'pending');
  const activeJobs = jobs.filter((job) => job.status === 'MATCHING' || job.status === 'VALIDATING');
  const compliant = candidates.filter((candidate) => candidate.complianceStatus === 'COMPLIANT').length;
  const needsReview = candidates.filter((candidate) => candidate.complianceStatus !== 'COMPLIANT' || candidate.actionsRequired).length;
  const strongConfidence = candidates.filter((candidate) => candidate.matchScore >= 0.75).length;
  const mediumConfidence = candidates.filter((candidate) => candidate.matchScore >= 0.5 && candidate.matchScore < 0.75).length;
  const lowConfidence = candidates.filter((candidate) => candidate.matchScore < 0.5).length;
  const complianceRate = candidates.length ? compliant / candidates.length : 0;

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <div key={item} className="h-40 animate-pulse rounded-md border border-slate-200 bg-white" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-20 lg:pb-0">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Candidates"
          value={candidates.length}
          detail={`${needsReview} profile${needsReview === 1 ? '' : 's'} need human attention before high-impact use.`}
          icon={Database}
        />
        <Metric
          label="Open jobs"
          value={activeJobs.length}
          detail={`${jobs.reduce((sum, job) => sum + job.shortlist.length, 0)} shortlisted candidate rows are available.`}
          icon={ClipboardList}
        />
        <Metric
          label="Pending reviews"
          value={pending.length}
          detail="Compliance flags, identity conflicts, and outreach drafts share one queue."
          icon={ShieldCheck}
        />
        <Metric
          label="Compliant pool"
          value={pct(complianceRate)}
          detail="Derived from candidate consent, retention, and review status."
          icon={TrendingUp}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Extraction Confidence</h2>
              <p className="mt-1 text-sm text-slate-500">Distribution across candidate extraction scores.</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('talent')}
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Talent pool
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-5 space-y-4">
            {[
              { label: 'High confidence', value: strongConfidence, color: 'bg-emerald-500' },
              { label: 'Needs validation', value: mediumConfidence, color: 'bg-amber-500' },
              { label: 'Low confidence', value: lowConfidence, color: 'bg-rose-500' },
            ].map((row) => {
              const width = candidates.length ? Math.max(4, Math.round((row.value / candidates.length) * 100)) : 0;
              return (
                <div key={row.label}>
                  <div className="mb-1 flex items-center justify-between text-sm">
                    <span className="font-medium text-slate-700">{row.label}</span>
                    <span className="text-slate-500">{row.value}</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100">
                    <div className={`h-2 rounded-full ${row.color}`} style={{ width: `${width}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-md border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-slate-950">Recent Audit Events</h2>
              <p className="mt-1 text-sm text-slate-500">Latest recorded system and human actions.</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('maintenance')}
              className="rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Maintenance
            </button>
          </div>

          <div className="mt-5 divide-y divide-slate-100">
            {auditEvents.slice(0, 6).map((event) => (
              <div key={event.id || `${event.action}-${event.timestamp}`} className="py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium text-slate-800">{event.action || 'audit_event'}</p>
                  <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{event.actor}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-sm text-slate-500">{event.payloadSummary}</p>
              </div>
            ))}
            {auditEvents.length === 0 && (
              <p className="py-8 text-sm text-slate-500">No audit events have been recorded yet.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
