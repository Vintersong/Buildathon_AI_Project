/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import {
  AlertTriangle, Clock, MoreVertical, CheckCircle, History,
  Shield, UserPlus, Microscope, Search, X, Filter, ExternalLink,
  ChevronRight, Briefcase, GraduationCap, Globe, Languages, Layers,
  Calendar, Loader2, MapPin, RefreshCw, CheckSquare,
} from 'lucide-react';
import { Candidate, CandidateDetail, AuditEvent, ReviewTask } from '../types';
import * as api from '../api';

interface CandidatePoolProps {
  candidates: Candidate[];
  searchQuery: string;
  onNavigate: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
  onOpenReviewTask: (taskId: string) => void;
  onResolveCandidateDirectly: (id: string, newStatus: Candidate['complianceStatus']) => void;
  onBulkRefresh?: (ids: string[]) => Promise<void>;
  recentLogs: AuditEvent[];
  reviewTasks: ReviewTask[];
}

const PAGE_SIZE = 10;

// ─── Candidate Detail Drawer ──────────────────────────────────────────────────

function DetailTag({ label }: { label: string }) {
  return (
    <span className="px-2 py-0.5 bg-surface-container-low border border-border-subtle font-mono text-[10px] font-semibold text-primary rounded">
      {label}
    </span>
  );
}

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-1.5 text-[10px] font-bold font-mono uppercase tracking-wider text-on-surface-variant">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function CandidateDetailDrawer({ candidateId, onClose }: { candidateId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api.fetchCandidateDetail(candidateId)
      .then((d) => setDetail(d))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [candidateId]);

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-30 animate-in fade-in duration-200" onClick={onClose} />
      <aside className="fixed right-0 top-0 h-full w-full max-w-xl bg-white shadow-2xl z-40 flex flex-col animate-in slide-in-from-right duration-300 overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle shrink-0">
          <div>
            <h3 className="font-bold text-slate-900 text-base">{detail?.name ?? 'Candidate Profile'}</h3>
            <p className="font-mono text-[11px] text-on-surface-variant mt-0.5">ID: {candidateId}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-surface-container cursor-pointer text-on-surface-variant">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-6 space-y-7 font-sans text-xs">
          {loading && (
            <div className="flex items-center justify-center py-16 gap-2 text-on-surface-variant">
              <Loader2 className="w-5 h-5 animate-spin" /><span>Loading profile…</span>
            </div>
          )}
          {error && (
            <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700 text-xs">Failed to load: {error}</div>
          )}
          {detail && !loading && (
            <>
              <div className="p-4 bg-slate-deep text-white rounded-md space-y-1">
                <div className="font-bold text-sm">{detail.headline || detail.seniority}</div>
                {detail.summary && <p className="text-xs text-slate-300 leading-relaxed">{detail.summary}</p>}
                <div className="flex flex-wrap gap-3 pt-2 text-[11px] text-slate-300 font-mono">
                  {detail.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{detail.location}</span>}
                  {detail.yearsOfExperience != null && <span className="flex items-center gap-1"><Calendar className="w-3 h-3" />{detail.yearsOfExperience} yrs exp</span>}
                  {detail.linkedinUrl && (
                    <a href={detail.linkedinUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-300 hover:underline">
                      <ExternalLink className="w-3 h-3" />LinkedIn
                    </a>
                  )}
                </div>
              </div>
              {detail.allSkills.length > 0 && (
                <Section icon={<Layers className="w-3.5 h-3.5" />} title="Technologies Used">
                  <div className="flex flex-wrap gap-1.5">{detail.allSkills.map((s) => <DetailTag key={s} label={s} />)}</div>
                </Section>
              )}
              {detail.previousJobs.length > 0 && (
                <Section icon={<Briefcase className="w-3.5 h-3.5" />} title="Previous Positions">
                  <ul className="space-y-1.5">
                    {detail.previousJobs.map((job, i) => (
                      <li key={i} className="flex items-start gap-2 text-on-surface">
                        <ChevronRight className="w-3.5 h-3.5 shrink-0 mt-0.5 text-on-surface-variant" /><span>{job}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              {detail.studyDegrees.length > 0 && (
                <Section icon={<GraduationCap className="w-3.5 h-3.5" />} title="Education">
                  <ul className="space-y-1">{detail.studyDegrees.map((d, i) => <li key={i} className="text-on-surface">{d}</li>)}</ul>
                </Section>
              )}
              {detail.languagesSpoken.length > 0 && (
                <Section icon={<Languages className="w-3.5 h-3.5" />} title="Languages Spoken">
                  <div className="flex flex-wrap gap-1.5">{detail.languagesSpoken.map((l) => <DetailTag key={l} label={l} />)}</div>
                </Section>
              )}
              {detail.projectsDeveloped.length > 0 && (
                <Section icon={<Globe className="w-3.5 h-3.5" />} title="Projects Developed">
                  <ul className="space-y-1.5">
                    {detail.projectsDeveloped.map((p, i) => (
                      <li key={i} className="flex items-start gap-2 text-on-surface">
                        <ChevronRight className="w-3.5 h-3.5 shrink-0 mt-0.5 text-on-surface-variant" /><span>{p}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
              <Section icon={<Shield className="w-3.5 h-3.5" />} title="Compliance & Data">
                <div className="bg-surface-container-low border border-border-subtle rounded p-3 space-y-2 font-mono text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-on-surface-variant">Status</span>
                    <span className={`font-bold ${
                      detail.complianceStatus === 'COMPLIANT' ? 'text-status-ok'
                      : detail.complianceStatus === 'EXPIRING (14D)' ? 'text-status-error'
                      : 'text-status-review'
                    }`}>{detail.complianceStatus}</span>
                  </div>
                  <div className="flex justify-between"><span className="text-on-surface-variant">Data Region</span><span>{detail.dataRegion || '—'}</span></div>
                  <div className="flex justify-between"><span className="text-on-surface-variant">Consent Basis</span><span>{detail.consentBasis || '—'}</span></div>
                  {detail.retentionUntil && (
                    <div className="flex justify-between"><span className="text-on-surface-variant">Retention Until</span><span>{detail.retentionUntil.slice(0, 10)}</span></div>
                  )}
                  {detail.extractionConfidence != null && (
                    <div className="flex justify-between"><span className="text-on-surface-variant">Extraction Confidence</span><span>{(detail.extractionConfidence * 100).toFixed(0)}%</span></div>
                  )}
                  <div className="flex justify-between"><span className="text-on-surface-variant">Last Updated</span><span>{detail.updatedAt?.slice(0, 10) || '—'}</span></div>
                </div>
              </Section>
            </>
          )}
        </div>
      </aside>
    </>
  );
}

// ─── Main CandidatePool ───────────────────────────────────────────────────────

export default function CandidatePool({
  candidates,
  searchQuery,
  onNavigate,
  onOpenReviewTask,
  onResolveCandidateDirectly,
  onBulkRefresh,
  recentLogs,
  reviewTasks,
}: CandidatePoolProps) {
  const [activeFilter, setActiveFilter] = useState<'all' | 'high-risk' | 'expiring'>('all');
  const [sortBy, setSortBy] = useState<'match' | 'name' | 'id'>('match');
  const [localSearch, setLocalSearch] = useState('');
  const [selectedSeniority, setSelectedSeniority] = useState<string>('all');
  const [selectedSkill, setSelectedSkill] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [minMatchScore, setMinMatchScore] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [openActionCandidateId, setOpenActionCandidateId] = useState<string | null>(null);
  const [drawerCandidateId, setDrawerCandidateId] = useState<string | null>(null);

  // Bulk selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkRefreshing, setBulkRefreshing] = useState(false);
  const [bulkRefreshDone, setBulkRefreshDone] = useState(false);

  // Outside-click ref for action menu
  const actionMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!openActionCandidateId) return;
    function handleOutsideClick(e: MouseEvent) {
      if (actionMenuRef.current && !actionMenuRef.current.contains(e.target as Node)) {
        setOpenActionCandidateId(null);
      }
    }
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, [openActionCandidateId]);

  const handleOpenDrawer = useCallback((id: string) => {
    setOpenActionCandidateId(null);
    setDrawerCandidateId(id);
  }, []);

  const availableSeniorities = useMemo(() => {
    const sSet = new Set<string>();
    candidates.forEach((c) => { if (c.seniority) sSet.add(c.seniority.trim()); });
    return Array.from(sSet).sort();
  }, [candidates]);

  const availableSkills = useMemo(() => {
    const skSet = new Set<string>();
    candidates.forEach((c) => { c.topSkills.forEach((s) => { if (s) skSet.add(s.trim().toUpperCase()); }); });
    return Array.from(skSet).sort();
  }, [candidates]);

  const filteredCandidates = useMemo(() => {
    let result = candidates.filter((cand) => {
      const combinedQuery = (searchQuery.trim() + ' ' + localSearch.trim()).trim().toLowerCase();
      if (combinedQuery) {
        const queryTerms = combinedQuery.split(/\s+/);
        const matchesQuery = queryTerms.every(term =>
          cand.name.toLowerCase().includes(term) ||
          cand.id.toLowerCase().includes(term) ||
          cand.seniority.toLowerCase().includes(term) ||
          cand.topSkills.some((s) => s.toLowerCase().includes(term))
        );
        if (!matchesQuery) return false;
      }
      if (activeFilter === 'high-risk' && cand.complianceStatus !== 'PENDING REVIEW') return false;
      if (activeFilter === 'expiring' && cand.complianceStatus !== 'EXPIRING (14D)') return false;
      if (selectedSeniority !== 'all' && cand.seniority !== selectedSeniority) return false;
      if (selectedSkill !== 'all' && !cand.topSkills.some((s) => s.trim().toUpperCase() === selectedSkill)) return false;
      if (selectedStatus !== 'all' && cand.complianceStatus !== selectedStatus) return false;
      if (cand.matchScore < minMatchScore) return false;
      return true;
    });
    return [...result].sort((a, b) => {
      if (sortBy === 'match') return b.matchScore - a.matchScore;
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      return a.id.localeCompare(b.id);
    });
  }, [candidates, searchQuery, localSearch, activeFilter, selectedSeniority, selectedSkill, selectedStatus, minMatchScore, sortBy]);

  const hasActiveFilters = useMemo(() => (
    localSearch.trim() !== '' ||
    selectedSeniority !== 'all' ||
    selectedSkill !== 'all' ||
    selectedStatus !== 'all' ||
    minMatchScore > 0 ||
    activeFilter !== 'all'
  ), [localSearch, selectedSeniority, selectedSkill, selectedStatus, minMatchScore, activeFilter]);

  useEffect(() => {
    setCurrentPage(1);
    setSelectedIds(new Set()); // clear selection when filters change
  }, [searchQuery, localSearch, activeFilter, selectedSeniority, selectedSkill, selectedStatus, minMatchScore, sortBy]);

  const handleClearAllFilters = () => {
    setLocalSearch('');
    setSelectedSeniority('all');
    setSelectedSkill('all');
    setSelectedStatus('all');
    setMinMatchScore(0);
    setActiveFilter('all');
    setCurrentPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(filteredCandidates.length / PAGE_SIZE));
  const pagedCandidates = filteredCandidates.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // ─── Selection helpers ────────────────────────────────────────────────────
  const pageIds = pagedCandidates.map((c) => c.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const somePageSelected = pageIds.some((id) => selectedIds.has(id));

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const toggleSelectOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleBulkRefresh = async () => {
    if (selectedIds.size === 0) return;
    setBulkRefreshing(true);
    setBulkRefreshDone(false);
    try {
      if (onBulkRefresh) {
        await onBulkRefresh(Array.from(selectedIds));
      } else {
        // Stub: simulate a refresh call
        await fetch('/api/candidates/bulk-refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: Array.from(selectedIds) }),
        });
      }
      setBulkRefreshDone(true);
      setTimeout(() => {
        setSelectedIds(new Set());
        setBulkRefreshDone(false);
      }, 1800);
    } finally {
      setBulkRefreshing(false);
    }
  };

  const handleStatusOverride = (candidateId: string, status: Candidate['complianceStatus']) => {
    onResolveCandidateDirectly(candidateId, status);
    setOpenActionCandidateId(null);
  };

  const totals = useMemo(() => ({
    total: candidates.length,
    pendingReviews: candidates.filter((c) => c.complianceStatus === 'PENDING REVIEW').length,
    staleRecords: candidates.filter((c) => c.complianceStatus === 'EXPIRING (14D)').length,
    compliant: candidates.filter((c) => c.complianceStatus === 'COMPLIANT').length,
  }), [candidates]);

  return (
    <div className="space-y-12 animate-in fade-in duration-300">

      {drawerCandidateId && (
        <CandidateDetailDrawer candidateId={drawerCandidateId} onClose={() => setDrawerCandidateId(null)} />
      )}

      {/* Metric Cards Banner */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="p-6 bg-white border border-border-subtle rounded flex flex-col justify-between">
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-on-surface-variant mb-2">TOTAL CANDIDATES</div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">{totals.total.toLocaleString()}</span>
            <span className="text-xs font-mono font-bold text-status-ok">+4.2%</span>
          </div>
        </div>
        <div className="p-6 bg-white border border-border-subtle border-l-4 border-l-status-review rounded flex flex-col justify-between cursor-pointer hover:bg-amber-50/20"
             onClick={() => onNavigate('review')}>
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-status-review mb-2">Pending Reviews (HITL)</div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">{totals.pendingReviews}</span>
            <span className="text-xs font-mono font-bold text-status-review">{totals.pendingReviews > 0 ? 'Urgent' : 'Clear'}</span>
          </div>
        </div>
        <div className="p-6 bg-white border border-border-subtle border-l-4 border-l-status-error rounded flex flex-col justify-between">
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-status-error mb-2">STALE RECORDS (DECAY)</div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">{totals.staleRecords}</span>
            <span className="text-xs font-mono font-bold text-status-error">{totals.staleRecords > 0 ? 'Attention' : 'Clear'}</span>
          </div>
        </div>
        <div className="p-6 bg-white border border-border-subtle rounded flex flex-col justify-between cursor-pointer hover:bg-slate-50"
             onClick={() => onNavigate('jobs')}>
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-on-surface-variant mb-2">COMPLIANT RECORDS</div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">{totals.compliant}</span>
            <span className="text-xs font-mono font-bold text-status-ok">Jobs →</span>
          </div>
        </div>
      </section>

      {/* Search & Advanced Filters Panel */}
      <section id="candidate-filters-panel" className="bg-white border border-border-subtle rounded p-5 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
          <div className="lg:col-span-8 relative">
            <div id="local-search-input-wrapper" className="flex items-center w-full border border-border-subtle hover:border-slate-400 focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500 rounded bg-surface-container-low px-3 py-1.5 transition-all">
              <Search className="w-4 h-4 text-on-surface-variant mr-2.5 shrink-0" />
              <input
                id="candidate-local-search"
                type="text"
                placeholder="Search candidates list (e.g., Kovic, AWS, Principal, compliance)..."
                className="bg-transparent border-none outline-none focus:ring-0 w-full font-sans text-xs text-on-surface placeholder:text-on-surface-variant/75 focus-visible:outline-none"
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
              />
              {localSearch && (
                <button id="clear-local-search-btn" onClick={() => setLocalSearch('')}
                  className="p-1 hover:bg-surface-container rounded-full text-on-surface-variant cursor-pointer transition-colors" title="Clear search">
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
          <div className="lg:col-span-4 flex items-center justify-between lg:justify-end gap-3 pt-2 lg:pt-0">
            <div className="text-[11px] font-bold text-on-surface-variant font-sans tracking-wider uppercase shrink-0">SORT BY:</div>
            <select id="candidate-sort-select"
              className="bg-surface-container-low border border-border-subtle text-xs font-semibold text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2.5 py-1.5"
              value={sortBy} onChange={(e) => setSortBy(e.target.value as 'match' | 'name' | 'id')}>
              <option value="match">Match Score (Desc)</option>
              <option value="name">Candidate Name A-Z</option>
              <option value="id">Record Identifier ID</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 pt-3 border-t border-dashed border-border-subtle/40">
          <div>
            <label htmlFor="filter-seniority" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">Seniority Level</label>
            <select id="filter-seniority" className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedSeniority} onChange={(e) => setSelectedSeniority(e.target.value)}>
              <option value="all">All Seniorities</option>
              {availableSeniorities.map((sen) => <option key={sen} value={sen}>{sen}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="filter-skill" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">Top Skills</label>
            <select id="filter-skill" className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedSkill} onChange={(e) => setSelectedSkill(e.target.value)}>
              <option value="all">All Skills ({availableSkills.length})</option>
              {availableSkills.map((ski) => <option key={ski} value={ski}>{ski}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="filter-status" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">Consent Compliance</label>
            <select id="filter-status" className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedStatus} onChange={(e) => setSelectedStatus(e.target.value)}>
              <option value="all">All Statuses</option>
              <option value="COMPLIANT">Compliant</option>
              <option value="PENDING REVIEW">Pending Review</option>
              <option value="EXPIRING (14D)">Expiring (14D)</option>
            </select>
          </div>
          <div>
            <label htmlFor="filter-match" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">Minimum Match Score</label>
            <select id="filter-match" className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={String(minMatchScore)} onChange={(e) => setMinMatchScore(Number(e.target.value))}>
              <option value="0">Show All</option>
              <option value="0.5">≥ 0.50 Match</option>
              <option value="0.7">≥ 0.70 Match</option>
              <option value="0.8">≥ 0.80 Match</option>
              <option value="0.9">≥ 0.90 Match</option>
              <option value="0.95">≥ 0.95 (Ultra High Match)</option>
            </select>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-border-subtle bg-surface-container-low/30 px-3 py-1.5 rounded">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mr-1.5 flex items-center gap-1">
              <Filter className="w-3 h-3 text-slate-500" /><span>QUICK POOLS:</span>
            </span>
            <button id="filter-highrisk-btn"
              onClick={() => setActiveFilter(activeFilter === 'high-risk' ? 'all' : 'high-risk')}
              className={`px-2.5 py-1 border rounded text-[10px] font-bold flex items-center gap-1.5 cursor-pointer transition-colors ${
                activeFilter === 'high-risk' ? 'bg-status-review/15 border-status-review text-status-review shadow-xs' : 'bg-white border-border-subtle text-on-surface-variant hover:bg-surface-container-low'
              }`}>
              <AlertTriangle className="w-3 h-3 text-status-review shrink-0" /><span>Pending Reviews</span>
            </button>
            <button id="filter-expiring-btn"
              onClick={() => setActiveFilter(activeFilter === 'expiring' ? 'all' : 'expiring')}
              className={`px-2.5 py-1 border rounded text-[10px] font-bold flex items-center gap-1.5 cursor-pointer transition-colors ${
                activeFilter === 'expiring' ? 'bg-status-error/15 border-status-error text-status-error shadow-xs' : 'bg-white border-border-subtle text-on-surface-variant hover:bg-surface-container-low'
              }`}>
              <Clock className="w-3 h-3 text-status-error shrink-0" /><span>Consent Expiring</span>
            </button>
          </div>
          <div className="flex items-center gap-2.5 justify-between sm:justify-end">
            <span className="text-[11px] font-sans text-on-surface-variant">
              Found <strong>{filteredCandidates.length}</strong> of {candidates.length} candidates
            </span>
            {hasActiveFilters && (
              <button id="clear-all-filters-btn" onClick={handleClearAllFilters}
                className="text-[10px] font-mono font-bold text-bloodhound-crimson hover:underline cursor-pointer border border-dashed border-bloodhound-crimson/50 px-2 py-0.5 bg-red-50/50 hover:bg-red-50 rounded transition-colors">
                Reset Filters
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Main Candidate Table */}
      <section className="bg-white border border-border-subtle rounded overflow-hidden">

        {/* ── Bulk Action Toolbar (visible when rows selected) ── */}
        {selectedIds.size > 0 && (
          <div
            id="bulk-action-toolbar"
            className="flex items-center justify-between px-6 py-3 bg-slate-deep text-white border-b border-white/10 animate-in slide-in-from-top duration-200"
          >
            <div className="flex items-center gap-3">
              <CheckSquare className="w-4 h-4 text-amber-400 shrink-0" />
              <span className="text-xs font-bold font-mono uppercase tracking-wider">
                {selectedIds.size} candidate{selectedIds.size !== 1 ? 's' : ''} selected
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                id="bulk-refresh-btn"
                onClick={handleBulkRefresh}
                disabled={bulkRefreshing}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-white text-slate-deep rounded text-xs font-bold hover:bg-slate-100 transition-colors cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {bulkRefreshing ? (
                  <><Loader2 className="w-3.5 h-3.5 animate-spin" />Refreshing…</>
                ) : bulkRefreshDone ? (
                  <><CheckCircle className="w-3.5 h-3.5 text-status-ok" />Done!</>
                ) : (
                  <><RefreshCw className="w-3.5 h-3.5" />Bulk Refresh LinkedIn</>
                )}
              </button>
              <button
                onClick={() => setSelectedIds(new Set())}
                className="text-white/70 hover:text-white text-[11px] font-mono underline cursor-pointer transition-colors"
              >
                Deselect all
              </button>
            </div>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container border-b border-border-subtle">
                {/* Select-all checkbox */}
                <th className="pl-4 pr-2 py-3 w-10" onClick={(e) => e.stopPropagation()}>
                  <input
                    id="select-all-checkbox"
                    type="checkbox"
                    checked={allPageSelected}
                    ref={(el) => { if (el) el.indeterminate = somePageSelected && !allPageSelected; }}
                    onChange={toggleSelectAll}
                    className="w-3.5 h-3.5 cursor-pointer accent-slate-deep"
                    aria-label="Select all on this page"
                  />
                </th>
                <th className="px-4 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">NAME</th>
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">SENIORITY</th>
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">TOP SKILLS</th>
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">MATCH SCORE</th>
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">GDPR STATUS</th>
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle select-none">
              {filteredCandidates.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-sm text-on-surface-variant font-sans">
                    No candidates match the specified criteria. Try removing filters or changing your search terms.
                  </td>
                </tr>
              ) : (
                pagedCandidates.map((candidate) => {
                  const isReviewState = candidate.complianceStatus === 'PENDING REVIEW';
                  const isExpiringState = candidate.complianceStatus === 'EXPIRING (14D)';
                  const isSelected = selectedIds.has(candidate.id);
                  return (
                    <tr key={candidate.id}
                      onClick={() => handleOpenDrawer(candidate.id)}
                      className={`transition-all h-[56px] group cursor-pointer ${
                        isSelected
                          ? 'bg-indigo-50 border-l-4 border-l-indigo-400'
                          : isReviewState
                          ? 'bg-status-review/5 border-l-4 border-l-status-review hover:bg-status-review/10'
                          : 'hover:bg-slate-50'
                      }`}>

                      {/* Row checkbox */}
                      <td className="pl-4 pr-2 py-3 w-10" onClick={(e) => { e.stopPropagation(); toggleSelectOne(candidate.id); }}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectOne(candidate.id)}
                          onClick={(e) => e.stopPropagation()}
                          className="w-3.5 h-3.5 cursor-pointer accent-slate-deep"
                          aria-label={`Select ${candidate.name}`}
                        />
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-surface-dim flex items-center justify-center font-bold text-xs text-primary shrink-0">
                            {candidate.imageInitials}
                          </div>
                          <div>
                            <div className="font-sans font-bold text-sm text-primary group-hover:underline">{candidate.name}</div>
                            <div className="font-mono text-[11px] text-on-surface-variant">ID: {candidate.id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-3 text-sm text-on-surface-variant font-sans">{candidate.seniority}</td>
                      <td className="px-6 py-3">
                        <div className="flex flex-wrap gap-1.5 max-w-[280px]">
                          {candidate.topSkills.map((skill) => (
                            <span key={skill} className="px-2 py-0.5 bg-surface-container-low border border-border-subtle font-mono text-[10px] font-semibold text-primary rounded">{skill}</span>
                          ))}
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3 max-w-[140px]">
                          <div className="flex-grow bg-surface-container-high h-1.5 w-24 rounded-full overflow-hidden shrink-0">
                            <div className={`h-full rounded-full transition-all duration-500 ${
                              isReviewState ? 'bg-status-review' : 'bg-status-ok'
                            }`} style={{ width: `${candidate.matchScore * 100}%` }} />
                          </div>
                          <span className={`font-mono font-bold text-xs ${
                            isReviewState ? 'text-status-review' : 'text-status-ok'
                          }`}>{candidate.matchScore.toFixed(2)}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        {isReviewState ? (
                          <span className="inline-flex items-center px-2 py-1 bg-amber-50 text-status-review border border-status-review/30 rounded text-xs font-semibold gap-1">
                            <History className="w-3.5 h-3.5 shrink-0" />
                            <span className="text-[10px] tracking-wider uppercase font-mono">PENDING REVIEW</span>
                          </span>
                        ) : isExpiringState ? (
                          <span className="inline-flex items-center px-2 py-1 bg-red-50 text-status-error border border-status-error/30 rounded text-xs font-semibold gap-1">
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                            <span className="text-[10px] tracking-wider uppercase font-mono">EXPIRING (14D)</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-1 bg-green-50 text-status-ok border border-status-ok/30 rounded text-xs font-semibold gap-1">
                            <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                            <span className="text-[10px] tracking-wider uppercase font-mono">COMPLIANT</span>
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-3 relative" onClick={(e) => e.stopPropagation()}>
                        {isReviewState ? (() => {
                          const task = reviewTasks.find(t =>
                            t.status === 'pending' && (
                              t.complianceDetails?.candidateName === candidate.name ||
                              t.existingRecord?.name === candidate.name ||
                              t.outreachDetails?.targetName === candidate.name
                            )
                          );
                          return (
                            <button id={`resolve-btn-${candidate.id}`}
                              onClick={() => task && onOpenReviewTask(task.id)}
                              disabled={!task}
                              className="px-3 py-1 bg-primary text-on-primary font-mono text-[10px] tracking-wider font-bold hover:opacity-90 cursor-pointer rounded disabled:opacity-50 disabled:cursor-not-allowed">
                              RESOLVE
                            </button>
                          );
                        })() : (
                          <div className="relative inline-block" ref={openActionCandidateId === candidate.id ? actionMenuRef : undefined}>
                            <button type="button"
                              className="text-on-surface-variant hover:text-primary transition-colors cursor-pointer p-1 rounded hover:bg-surface-container"
                              onClick={() => setOpenActionCandidateId(openActionCandidateId === candidate.id ? null : candidate.id)}
                              aria-expanded={openActionCandidateId === candidate.id}
                              aria-label={`Open actions for ${candidate.name}`}>
                              <MoreVertical className="w-5 h-5" />
                            </button>
                            {openActionCandidateId === candidate.id && (
                              <div className="absolute right-0 top-8 z-20 w-52 bg-white border border-border-subtle rounded-md shadow-lg py-1 font-sans">
                                <button type="button" onClick={() => handleOpenDrawer(candidate.id)}
                                  className="block w-full text-left px-3 py-2 text-xs hover:bg-surface-container text-on-surface cursor-pointer font-semibold">View full profile</button>
                                <button type="button" onClick={() => handleStatusOverride(candidate.id, 'COMPLIANT')}
                                  className="block w-full text-left px-3 py-2 text-xs hover:bg-surface-container text-on-surface cursor-pointer">Mark compliant</button>
                                <button type="button" onClick={() => handleStatusOverride(candidate.id, 'PENDING REVIEW')}
                                  className="block w-full text-left px-3 py-2 text-xs hover:bg-surface-container text-on-surface cursor-pointer">Send to review</button>
                                <button type="button" onClick={() => handleStatusOverride(candidate.id, 'EXPIRING (14D)')}
                                  className="block w-full text-left px-3 py-2 text-xs hover:bg-surface-container text-on-surface cursor-pointer">Flag consent expiring</button>
                                <button type="button" onClick={() => { setOpenActionCandidateId(null); onNavigate('audit'); }}
                                  className="block w-full text-left px-3 py-2 text-xs hover:bg-surface-container text-on-surface cursor-pointer border-t border-border-subtle">View audit trail</button>
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="px-6 py-4 border-t border-border-subtle flex items-center justify-between font-sans">
          <span className="text-sm text-on-surface-variant">
            Showing {filteredCandidates.length === 0 ? 0 : Math.min((currentPage - 1) * PAGE_SIZE + 1, filteredCandidates.length)}–{Math.min(currentPage * PAGE_SIZE, filteredCandidates.length)} of {filteredCandidates.length} candidates
          </span>
          <div className="flex gap-2">
            <button disabled={currentPage <= 1} onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              className="px-3 py-1 border border-border-subtle text-xs rounded hover:bg-surface-container transition-colors disabled:opacity-50 cursor-pointer">Previous</button>
            <button disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              className="px-3 py-1 border border-border-subtle text-xs rounded hover:bg-surface-container transition-colors disabled:opacity-50 cursor-pointer">Next</button>
          </div>
        </div>
      </section>

      {/* Bento Bottom Row */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 pb-12">
        <div className="md:col-span-2 p-8 border border-border-subtle bg-slate-deep text-white relative overflow-hidden rounded-md flex flex-col justify-between min-h-[290px]">
          <div className="relative z-10 space-y-3">
            <div className="text-[10px] tracking-widest font-bold text-amber-500 font-mono uppercase">Ingestion Quality Metrics</div>
            <div className="text-2xl font-bold max-w-lg leading-tight">Automated Precision is at 98.4%</div>
            <p className="text-sm text-slate-300 max-w-md font-sans leading-relaxed">
              Our high-confidence ledger heuristics successfully verified 1,204 candidate profiles this week with only 14 requiring manual human intervention rules.
            </p>
          </div>
          <div className="relative z-10 flex gap-8 pt-6 border-t border-white/10 mt-6 font-mono">
            <div><div className="font-bold text-xl text-white">1.4s</div><div className="text-[10px] tracking-wider text-slate-400 mt-1 uppercase">AVG PROCESSING TIME</div></div>
            <div><div className="font-bold text-xl text-white">0.02%</div><div className="text-[10px] tracking-wider text-slate-400 mt-1 uppercase">MAPPING ERROR RATE</div></div>
          </div>
          <div className="absolute right-4 bottom-4 opacity-10 select-none pointer-events-none">
            <Microscope className="w-48 h-48 text-white" strokeWidth={1} />
          </div>
        </div>
        <div className="p-8 border border-border-subtle bg-surface rounded-md flex flex-col justify-between min-h-[290px]">
          <div>
            <div className="text-[10px] tracking-widest font-bold text-on-surface-variant font-mono mb-4 uppercase">RECENT ACTIVITY</div>
            <div className="space-y-6 select-none font-sans">
              {recentLogs.slice(0, 3).map((log, listIdx) => {
                const isSec = log.actor === 'SEC';
                const isHuman = log.actor === 'HUMAN';
                return (
                  <div key={log.id} className="flex gap-3">
                    <div className="shrink-0 mt-0.5">
                      {isSec ? <Shield className="w-5 h-5 text-indigo-700" /> : isHuman ? <Clock className="w-5 h-5 text-amber-600" /> : <UserPlus className="w-5 h-5 text-status-ok" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-primary text-slate-900 leading-tight">
                        {log.action === 'audit_sweep' ? 'Audit Log Synced' : log.payloadSummary}
                      </div>
                      <div className="font-mono text-[11px] text-on-surface-variant mt-1">
                        {listIdx === 0 ? '2 minutes ago' : listIdx === 1 ? '1 hour ago' : '4 hours ago'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <button onClick={() => onNavigate('audit')}
            className="w-full mt-6 py-2.5 bg-white border border-border-subtle rounded text-xs font-mono font-bold uppercase tracking-wider hover:bg-gray-50 transition-colors cursor-pointer">
            VIEW ALL LOGS
          </button>
        </div>
      </section>
    </div>
  );
}
