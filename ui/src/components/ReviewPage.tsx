import { useMemo, useState } from 'react';
import { AlertOctagon, CheckCircle, Clock, Copy, ShieldAlert, Trash2, X, XCircle } from 'lucide-react';
import { AuditEvent, ReviewTask } from '../types';

interface ReviewPageProps {
  tasks: ReviewTask[];
  auditEvents: AuditEvent[];
  onResolve: (taskId: string, resolution: 'approved' | 'rejected' | 'purged') => Promise<void>;
}

type Filter = 'pending' | 'all' | ReviewTask['type'];

const filterLabels: Array<{ id: Filter; label: string }> = [
  { id: 'pending', label: 'Pending' },
  { id: 'OUTREACH_DRAFT', label: 'Outreach drafts' },
  { id: 'COMPLIANCE_FLAG', label: 'Compliance flags' },
  { id: 'IDENTITY_CONFLICT', label: 'Identity conflicts' },
  { id: 'all', label: 'All cases' },
];

function taskSummary(task: ReviewTask) {
  if (task.type === 'OUTREACH_DRAFT') {
    return task.outreachDetails?.targetName || task.title;
  }
  if (task.type === 'COMPLIANCE_FLAG') {
    return task.complianceDetails?.candidateName || task.title;
  }
  return task.existingRecord?.name || task.title;
}

function taskDetail(task: ReviewTask) {
  if (task.type === 'OUTREACH_DRAFT') {
    return task.outreachDetails?.subject || 'Review generated outreach before sending.';
  }
  if (task.type === 'COMPLIANCE_FLAG') {
    return task.complianceDetails?.details || task.complianceDetails?.reason || 'Compliance review required.';
  }
  return task.recommendation || 'Potential duplicate or identity conflict requires a human decision.';
}

function ConfirmPurgeModal({
  task,
  busy,
  onCancel,
  onConfirm,
}: {
  task: ReviewTask;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [confirmText, setConfirmText] = useState('');
  const canPurge = confirmText.trim().toUpperCase() === 'PURGE' && !busy;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
      <form
        onSubmit={(event) => { event.preventDefault(); if (canPurge) onConfirm(); }}
        className="w-full max-w-md overflow-hidden rounded-md bg-white shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-md bg-rose-50 p-2 text-rose-600">
              <AlertOctagon className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-950">Purge record</h2>
              <p className="text-sm text-slate-500">This action is irreversible.</p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Cancel purge"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <p className="text-sm leading-6 text-slate-600">
            You are about to purge <span className="font-semibold text-slate-900">{taskSummary(task)}</span> and
            permanently remove the associated data. This cannot be undone.
          </p>
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              Type <span className="font-mono text-rose-600">PURGE</span> to confirm
            </span>
            <input
              value={confirmText}
              onChange={(event) => setConfirmText(event.target.value)}
              autoFocus
              placeholder="PURGE"
              className="mt-1 h-10 w-full rounded-md border border-slate-200 px-3 font-mono text-sm outline-none focus:border-rose-500 focus:ring-2 focus:ring-rose-100"
            />
          </label>
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-4">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="h-10 rounded-md border border-slate-200 px-4 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canPurge}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-rose-600 px-4 text-sm font-medium text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            Purge permanently
          </button>
        </div>
      </form>
    </div>
  );
}

export default function ReviewPage({ tasks, auditEvents, onResolve }: ReviewPageProps) {
  const [filter, setFilter] = useState<Filter>('pending');
  const [busyId, setBusyId] = useState<string | null>(null);
  const [purgeTask, setPurgeTask] = useState<ReviewTask | null>(null);

  const filtered = useMemo(() => {
    if (filter === 'all') return tasks;
    if (filter === 'pending') return tasks.filter((task) => task.status === 'pending');
    return tasks.filter((task) => task.type === filter);
  }, [filter, tasks]);

  const resolve = async (task: ReviewTask, resolution: 'approved' | 'rejected' | 'purged') => {
    setBusyId(task.id);
    try {
      await onResolve(task.id, resolution);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="grid gap-6 pb-20 xl:grid-cols-[1fr_360px] lg:pb-0">
      <section className="space-y-4">
        <div className="flex flex-wrap gap-2 rounded-md border border-slate-200 bg-white p-3">
          {filterLabels.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setFilter(item.id)}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                filter === item.id ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        {filtered.map((task) => (
          <article key={task.id} className="rounded-md border border-slate-200 bg-white p-5">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                    {task.type.replaceAll('_', ' ')}
                  </span>
                  <span className={task.status === 'pending' ? 'rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800' : 'rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-800'}>
                    {task.status}
                  </span>
                  <span className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <Clock className="h-3 w-3" />
                    {task.timeAgo || task.timestamp}
                  </span>
                </div>
                <h2 className="mt-3 text-lg font-semibold text-slate-950">{taskSummary(task)}</h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{taskDetail(task)}</p>
              </div>

              {task.status === 'pending' && (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => resolve(task, 'approved')}
                    className="inline-flex h-10 items-center gap-2 rounded-md bg-emerald-600 px-3 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-60"
                  >
                    <CheckCircle className="h-4 w-4" />
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => resolve(task, 'rejected')}
                    className="inline-flex h-10 items-center gap-2 rounded-md border border-slate-200 px-3 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    <XCircle className="h-4 w-4" />
                    Reject
                  </button>
                  <button
                    type="button"
                    disabled={busyId === task.id}
                    onClick={() => setPurgeTask(task)}
                    className="inline-flex h-10 items-center gap-2 rounded-md border border-rose-200 px-3 text-sm font-medium text-rose-700 hover:bg-rose-50 disabled:opacity-60"
                  >
                    <Trash2 className="h-4 w-4" />
                    Purge
                  </button>
                </div>
              )}
            </div>

            {task.type === 'OUTREACH_DRAFT' && task.outreachDetails && (
              <div className="mt-5 rounded-md border border-slate-200 bg-slate-50 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-slate-950">{task.outreachDetails.subject}</p>
                  <button
                    type="button"
                    onClick={() => navigator.clipboard?.writeText(task.outreachDetails?.draftBody || '')}
                    className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Copy className="h-4 w-4" />
                    Copy
                  </button>
                </div>
                <pre className="mt-3 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-700">
                  {task.outreachDetails.draftBody || 'No draft body was generated.'}
                </pre>
                {task.outreachDetails.signals.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {task.outreachDetails.signals.map((signal) => (
                      <span key={signal} className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">
                        {signal}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {task.type === 'IDENTITY_CONFLICT' && (
              <div className="mt-5 grid gap-4 md:grid-cols-2">
                <div className="rounded-md border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-950">Existing record</h3>
                  <p className="mt-2 text-sm text-slate-600">{task.existingRecord?.name || 'Unknown'}</p>
                  <p className="text-sm text-slate-500">{task.existingRecord?.currentRole || 'No role'}</p>
                  <p className="text-sm text-slate-500">{task.existingRecord?.location || 'No location'}</p>
                </div>
                <div className="rounded-md border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-950">Proposed update</h3>
                  <p className="mt-2 text-sm text-slate-600">{task.proposedRecord?.name || 'Unknown'}</p>
                  <p className="text-sm text-slate-500">{task.proposedRecord?.currentRole || 'No role'}</p>
                  <p className="text-sm text-slate-500">{task.proposedRecord?.source || 'Unknown source'}</p>
                </div>
              </div>
            )}
          </article>
        ))}

        {filtered.length === 0 && (
          <div className="rounded-md border border-dashed border-slate-300 bg-white p-10 text-center">
            <ShieldAlert className="mx-auto h-9 w-9 text-slate-300" />
            <p className="mt-3 text-sm font-medium text-slate-700">No review cases in this view.</p>
            <p className="mt-1 text-sm text-slate-500">Generated outreach and compliance flags will appear here.</p>
          </div>
        )}
      </section>

      <aside className="space-y-5">
        <section className="rounded-md border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-950">Queue Health</h2>
          <dl className="mt-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Pending</dt>
              <dd className="text-sm font-semibold text-slate-950">{tasks.filter((task) => task.status === 'pending').length}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Outreach drafts</dt>
              <dd className="text-sm font-semibold text-slate-950">{tasks.filter((task) => task.type === 'OUTREACH_DRAFT').length}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-sm text-slate-500">Compliance flags</dt>
              <dd className="text-sm font-semibold text-slate-950">{tasks.filter((task) => task.type === 'COMPLIANCE_FLAG').length}</dd>
            </div>
          </dl>
        </section>

        <section className="rounded-md border border-slate-200 bg-white p-5">
          <h2 className="text-base font-semibold text-slate-950">Latest Audit Trail</h2>
          <div className="mt-4 space-y-3">
            {auditEvents.slice(0, 5).map((event) => (
              <div key={event.id || event.timestamp} className="border-l-2 border-slate-200 pl-3">
                <p className="text-sm font-medium text-slate-800">{event.action || 'audit_event'}</p>
                <p className="mt-1 text-xs text-slate-500">{event.payloadSummary}</p>
              </div>
            ))}
            {auditEvents.length === 0 && <p className="text-sm text-slate-500">No audit events yet.</p>}
          </div>
        </section>
      </aside>

      {purgeTask && (
        <ConfirmPurgeModal
          task={purgeTask}
          busy={busyId === purgeTask.id}
          onCancel={() => setPurgeTask(null)}
          onConfirm={async () => {
            const target = purgeTask;
            await resolve(target, 'purged');
            setPurgeTask(null);
          }}
        />
      )}
    </div>
  );
}
