import { useEffect, useMemo, useState } from 'react';
import {
  Check,
  FileText,
  Link as LinkIcon,
  Loader2,
  RotateCcw,
  SearchX,
  ShieldAlert,
  Upload,
  X,
} from 'lucide-react';
import * as api from '../api';
import { Candidate, CandidateDetail } from '../types';
import CSVImportButton from './CSVImportButton';

interface TalentPoolPageProps {
  candidates: Candidate[];
  searchQuery: string;
  onOpenIngest: () => void;
  onRefresh: () => Promise<void>;
  onToast: (message: string, type?: 'success' | 'info' | 'error') => void;
}

const statusStyles: Record<Candidate['complianceStatus'], string> = {
  COMPLIANT: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  'PENDING REVIEW': 'bg-amber-50 text-amber-800 ring-amber-200',
  'EXPIRING (14D)': 'bg-rose-50 text-rose-700 ring-rose-200',
};

function includesQuery(candidate: Candidate, query: string) {
  const haystack = [
    candidate.name,
    candidate.seniority,
    candidate.complianceStatus,
    ...candidate.topSkills,
  ].join(' ').toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function DetailDrawer({
  candidateId,
  onClose,
  onRefresh,
  onToast,
}: {
  candidateId: string | null;
  onClose: () => void;
  onRefresh: () => Promise<void>;
  onToast: TalentPoolPageProps['onToast'];
}) {
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [linkedinUrl, setLinkedinUrl] = useState('');
  const [reingesting, setReingesting] = useState(false);

  useEffect(() => {
    if (!candidateId) return;
    setLoading(true);
    api.fetchCandidateDetail(candidateId)
      .then((candidate) => {
        setDetail(candidate);
        setLinkedinUrl(candidate.linkedinUrl || '');
      })
      .catch((error) => onToast(error.message, 'error'))
      .finally(() => setLoading(false));
  }, [candidateId, onToast]);

  if (!candidateId) return null;

  const updateLinkedIn = async () => {
    if (!detail || !linkedinUrl.trim()) return;
    setReingesting(true);
    try {
      await api.reingestCandidate(detail.id, linkedinUrl.trim());
      onToast('LinkedIn URL stored and audit event recorded.');
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'LinkedIn update failed', 'error');
    } finally {
      setReingesting(false);
    }
  };

  const markStatus = async (status: Candidate['complianceStatus']) => {
    if (!detail) return;
    try {
      await api.patchCandidateStatus(detail.id, status);
      onToast('Candidate review status updated.');
      await onRefresh();
      const updated = await api.fetchCandidateDetail(detail.id);
      setDetail(updated);
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Status update failed', 'error');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30">
      <button type="button" aria-label="Close candidate details" className="hidden flex-1 lg:block" onClick={onClose} />
      <aside className="h-full w-full max-w-2xl overflow-y-auto bg-white shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-950">{detail?.name || 'Candidate profile'}</h2>
            <p className="text-sm text-slate-500">Extracted profile, compliance state, and refresh controls.</p>
          </div>
          <button
            type="button"
            aria-label="Close details"
            onClick={onClose}
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {loading || !detail ? (
          <div className="flex h-64 items-center justify-center text-slate-500">
            <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            Loading profile
          </div>
        ) : (
          <div className="space-y-6 p-5">
            <section className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-md border border-slate-200 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Seniority</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{detail.seniority || 'Unknown'}</p>
              </div>
              <div className="rounded-md border border-slate-200 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Experience</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">
                  {detail.yearsOfExperience ?? 'Unknown'}{detail.yearsOfExperience === null ? '' : ' years'}
                </p>
              </div>
              <div className="rounded-md border border-slate-200 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Confidence</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{Math.round((detail.extractionConfidence ?? 0) * 100)}%</p>
              </div>
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-950">Profile Summary</h3>
              <p className="mt-2 rounded-md bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                {detail.summary || 'No summary has been extracted yet.'}
              </p>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              {[
                ['Location', detail.location || 'Unknown'],
                ['Emails', detail.emails.join(', ') || 'None stored'],
                ['Languages', detail.languagesSpoken.join(', ') || 'None extracted'],
                ['Degrees', detail.studyDegrees.join(', ') || 'None extracted'],
                ['Consent basis', detail.consentBasis || 'Not set'],
                ['Data region', detail.dataRegion || 'Not set'],
                ['Retention until', detail.retentionUntil || 'Not set'],
                ['Last updated', detail.updatedAt || 'Unknown'],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border border-slate-200 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
                  <p className="mt-2 break-words text-sm text-slate-800">{value}</p>
                </div>
              ))}
            </section>

            <section>
              <h3 className="text-sm font-semibold text-slate-950">Skills</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {(detail.allSkills.length ? detail.allSkills : detail.topSkills).map((skill) => (
                  <span key={skill} className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-800">
                    {skill}
                  </span>
                ))}
                {detail.allSkills.length === 0 && detail.topSkills.length === 0 && (
                  <span className="text-sm text-slate-500">No skills extracted.</span>
                )}
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">Previous Jobs</h3>
                <ul className="mt-3 space-y-2 text-sm text-slate-600">
                  {(detail.previousJobs.length ? detail.previousJobs : ['No previous jobs extracted.']).map((job) => (
                    <li key={job} className="rounded-md bg-slate-50 px-3 py-2">{job}</li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-950">Projects</h3>
                <ul className="mt-3 space-y-2 text-sm text-slate-600">
                  {(detail.projectsDeveloped.length ? detail.projectsDeveloped : ['No projects extracted.']).map((project) => (
                    <li key={project} className="rounded-md bg-slate-50 px-3 py-2">{project}</li>
                  ))}
                </ul>
              </div>
            </section>

            <section className="rounded-md border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-950">Human Review Controls</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => markStatus('COMPLIANT')} className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700">
                  <Check className="h-4 w-4" />
                  Mark compliant
                </button>
                <button type="button" onClick={() => markStatus('PENDING REVIEW')} className="inline-flex items-center gap-2 rounded-md border border-amber-200 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-50">
                  <ShieldAlert className="h-4 w-4" />
                  Request review
                </button>
              </div>
            </section>

            <section className="rounded-md border border-slate-200 p-4">
              <h3 className="text-sm font-semibold text-slate-950">LinkedIn Update</h3>
              <p className="mt-1 text-sm text-slate-500">Stores a provided URL or pasted profile source. The app does not scrape LinkedIn.</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                <input
                  value={linkedinUrl}
                  onChange={(event) => setLinkedinUrl(event.target.value)}
                  placeholder="https://www.linkedin.com/in/profile"
                  className="h-10 min-w-0 flex-1 rounded-md border border-slate-200 px-3 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
                />
                <button
                  type="button"
                  onClick={updateLinkedIn}
                  disabled={reingesting}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  {reingesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <LinkIcon className="h-4 w-4" />}
                  Save URL
                </button>
              </div>
            </section>
          </div>
        )}
      </aside>
    </div>
  );
}

export default function TalentPoolPage({
  candidates,
  searchQuery,
  onOpenIngest,
  onRefresh,
  onToast,
}: TalentPoolPageProps) {
  const [statusFilter, setStatusFilter] = useState<'all' | Candidate['complianceStatus']>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeCandidate, setActiveCandidate] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const filtered = useMemo(() => {
    return candidates
      .filter((candidate) => (statusFilter === 'all' ? true : candidate.complianceStatus === statusFilter))
      .filter((candidate) => (searchQuery.trim() ? includesQuery(candidate, searchQuery.trim()) : true));
  }, [candidates, searchQuery, statusFilter]);

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const bulkRefresh = async () => {
    if (selected.size === 0) return;
    setRefreshing(true);
    try {
      const result = await api.bulkRefreshCandidates([...selected]);
      onToast(`Refresh complete: ${result.success} succeeded, ${result.failed} failed.`, result.failed ? 'info' : 'success');
      setSelected(new Set());
      await onRefresh();
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Bulk refresh failed', 'error');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="space-y-5 pb-20 lg:pb-0">
      <div className="flex flex-col gap-3 rounded-md border border-slate-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-2">
          {(['all', 'COMPLIANT', 'PENDING REVIEW', 'EXPIRING (14D)'] as const).map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                statusFilter === status ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {status === 'all' ? 'All profiles' : status}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <CSVImportButton onDone={onRefresh} onToast={onToast} />
          <button
            type="button"
            onClick={bulkRefresh}
            disabled={selected.size === 0 || refreshing}
            className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            Refresh selected ({selected.size})
          </button>
          <button
            type="button"
            onClick={onOpenIngest}
            className="inline-flex items-center gap-2 rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            <Upload className="h-4 w-4" />
            Ingest profile
          </button>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="w-12 px-4 py-3 text-left">
                  <span className="sr-only">Select</span>
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Candidate</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Skills</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Quality</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Compliance</th>
                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {filtered.map((candidate) => (
                <tr key={candidate.id} className="hover:bg-slate-50">
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      checked={selected.has(candidate.id)}
                      onChange={() => toggleSelected(candidate.id)}
                      className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-cyan-500"
                    />
                  </td>
                  <td className="px-4 py-4">
                    <button type="button" onClick={() => setActiveCandidate(candidate.id)} className="flex min-w-52 items-center gap-3 text-left">
                      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-slate-900 text-sm font-semibold text-white">
                        {candidate.imageInitials}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-semibold text-slate-950">{candidate.name}</span>
                        <span className="block truncate text-sm text-slate-500">{candidate.seniority || 'Unknown seniority'}</span>
                      </span>
                    </button>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex max-w-sm flex-wrap gap-1.5">
                      {candidate.topSkills.slice(0, 4).map((skill) => (
                        <span key={skill} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium text-slate-600">{skill}</span>
                      ))}
                      {candidate.topSkills.length === 0 && <span className="text-sm text-slate-400">No skills</span>}
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-20 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-cyan-500" style={{ width: `${Math.round(candidate.matchScore * 100)}%` }} />
                      </div>
                      <span className="text-sm font-medium text-slate-700">{Math.round(candidate.matchScore * 100)}%</span>
                    </div>
                  </td>
                  <td className="px-4 py-4">
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ${statusStyles[candidate.complianceStatus]}`}>
                      {candidate.complianceStatus}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => setActiveCandidate(candidate.id)}
                      className="inline-flex items-center gap-2 rounded-md border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <FileText className="h-4 w-4" />
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
            <SearchX className="h-8 w-8 text-slate-300" />
            <p className="mt-3 text-sm font-medium text-slate-700">No candidates match the current view.</p>
            <p className="mt-1 text-sm text-slate-500">Adjust filters or ingest a new CV or LinkedIn URL.</p>
          </div>
        )}
      </div>

      <DetailDrawer
        candidateId={activeCandidate}
        onClose={() => setActiveCandidate(null)}
        onRefresh={onRefresh}
        onToast={onToast}
      />
    </div>
  );
}
