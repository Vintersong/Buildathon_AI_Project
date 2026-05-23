/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useMemo } from 'react';
import { AlertTriangle, Clock, MoreVertical, CheckCircle, HelpCircle, History, RefreshCw, Layers, Shield, UserPlus, Microscope, Search, X, SlidersHorizontal, Filter } from 'lucide-react';
import { Candidate, AuditEvent, ReviewTask } from '../types';

interface CandidatePoolProps {
  candidates: Candidate[];
  searchQuery: string;
  onNavigate: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
  onOpenReviewTask: (taskId: string) => void;
  onResolveCandidateDirectly: (id: string, newStatus: Candidate['complianceStatus']) => void;
  recentLogs: AuditEvent[];
  reviewTasks: ReviewTask[];
}

const PAGE_SIZE = 10;

export default function CandidatePool({
  candidates,
  searchQuery,
  onNavigate,
  onOpenReviewTask,
  onResolveCandidateDirectly,
  recentLogs,
  reviewTasks
}: CandidatePoolProps) {
  const [activeFilter, setActiveFilter] = useState<'all' | 'high-risk' | 'expiring'>('all');
  const [sortBy, setSortBy] = useState<'match' | 'name' | 'id'>('match');
  const [localSearch, setLocalSearch] = useState('');
  const [selectedSeniority, setSelectedSeniority] = useState<string>('all');
  const [selectedSkill, setSelectedSkill] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [minMatchScore, setMinMatchScore] = useState<number>(0.5);
  const [currentPage, setCurrentPage] = useState(1);

  // Dynamic lists from all candidates
  const availableSeniorities = useMemo(() => {
    const sSet = new Set<string>();
    candidates.forEach((c) => {
      if (c.seniority) sSet.add(c.seniority.trim());
    });
    return Array.from(sSet).sort();
  }, [candidates]);

  const availableSkills = useMemo(() => {
    const skSet = new Set<string>();
    candidates.forEach((c) => {
      c.topSkills.forEach((s) => {
        if (s) skSet.add(s.trim().toUpperCase());
      });
    });
    return Array.from(skSet).sort();
  }, [candidates]);

  // Filter & sort candidates
  const filteredCandidates = useMemo(() => {
    let result = candidates.filter((cand) => {
      // 1. Text search filter (combining global list query and local candidate pool dashboard search)
      const combinedQuery = (searchQuery.trim() + ' ' + localSearch.trim()).trim().toLowerCase();
      if (combinedQuery) {
        const queryTerms = combinedQuery.split(/\s+/);
        // Candidate matches if all query terms match SOME candidate field
        const matchesQuery = queryTerms.every(term => 
          cand.name.toLowerCase().includes(term) ||
          cand.id.toLowerCase().includes(term) ||
          cand.seniority.toLowerCase().includes(term) ||
          cand.topSkills.some((s) => s.toLowerCase().includes(term))
        );
        if (!matchesQuery) return false;
      }

      // 2. High Risk / Expiring Quick Buttons
      if (activeFilter === 'high-risk' && cand.complianceStatus !== 'PENDING REVIEW') {
        return false;
      }
      if (activeFilter === 'expiring' && cand.complianceStatus !== 'EXPIRING (14D)') {
        return false;
      }

      // 3. Seniority Dropdown Filter
      if (selectedSeniority !== 'all' && cand.seniority !== selectedSeniority) {
        return false;
      }

      // 4. Skills Dropdown Filter
      if (selectedSkill !== 'all' && !cand.topSkills.some((s) => s.trim().toUpperCase() === selectedSkill)) {
        return false;
      }

      // 5. Status Dropdown Filter
      if (selectedStatus !== 'all' && cand.complianceStatus !== selectedStatus) {
        return false;
      }

      // 6. Minimum Match Score Filter
      if (cand.matchScore < minMatchScore) {
        return false;
      }

      return true;
    });

    // Sorting logic
    return [...result].sort((a, b) => {
      if (sortBy === 'match') {
        return b.matchScore - a.matchScore;
      }
      if (sortBy === 'name') {
        return a.name.localeCompare(b.name);
      }
      return a.id.localeCompare(b.id);
    });
  }, [candidates, searchQuery, localSearch, activeFilter, selectedSeniority, selectedSkill, selectedStatus, minMatchScore, sortBy]);

  const hasActiveFilters = useMemo(() => {
    return (
      localSearch.trim() !== '' ||
      selectedSeniority !== 'all' ||
      selectedSkill !== 'all' ||
      selectedStatus !== 'all' ||
      minMatchScore > 0.5 ||
      activeFilter !== 'all'
    );
  }, [localSearch, selectedSeniority, selectedSkill, selectedStatus, minMatchScore, activeFilter]);

  const handleClearAllFilters = () => {
    setLocalSearch('');
    setSelectedSeniority('all');
    setSelectedSkill('all');
    setSelectedStatus('all');
    setMinMatchScore(0.5);
    setActiveFilter('all');
    setCurrentPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(filteredCandidates.length / PAGE_SIZE));
  const pagedCandidates = filteredCandidates.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // Statistics summaries
  const totals = useMemo(() => {
    const total = candidates.length;
    const pendingReviews = candidates.filter((c) => c.complianceStatus === 'PENDING REVIEW').length;
    const staleRecords = candidates.filter((c) => c.complianceStatus === 'EXPIRING (14D)').length;
    const compliant = candidates.filter((c) => c.complianceStatus === 'COMPLIANT').length;
    return { total, pendingReviews, staleRecords, compliant };
  }, [candidates]);

  return (
    <div className="space-y-12 animate-in fade-in duration-300">
      {/* Metric Cards Banner */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Card 1 */}
        <div className="p-6 bg-white border border-border-subtle rounded flex flex-col justify-between">
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-on-surface-variant mb-2">
            TOTAL CANDIDATES
          </div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">
              {totals.total.toLocaleString()}
            </span>
            <span className="text-xs font-mono font-bold text-status-ok">+4.2%</span>
          </div>
        </div>

        {/* Card 2 */}
        <div className="p-6 bg-white border border-border-subtle border-l-4 border-l-status-review rounded flex flex-col justify-between cursor-pointer hover:bg-amber-50/20"
             onClick={() => onNavigate('review')}>
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-status-review mb-2">
            Pending Reviews (HITL)
          </div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">
              {totals.pendingReviews}
            </span>
            <span className="text-xs font-mono font-bold text-status-review">{totals.pendingReviews > 0 ? 'Urgent' : 'Clear'}</span>
          </div>
        </div>

        {/* Card 3 */}
        <div className="p-6 bg-white border border-border-subtle border-l-4 border-l-status-error rounded flex flex-col justify-between">
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-status-error mb-2">
            STALE RECORDS (DECAY)
          </div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">
              {totals.staleRecords}
            </span>
            <span className="text-xs font-mono font-bold text-status-error">{totals.staleRecords > 0 ? 'Attention' : 'Clear'}</span>
          </div>
        </div>

        {/* Card 4 */}
        <div className="p-6 bg-white border border-border-subtle rounded flex flex-col justify-between cursor-pointer hover:bg-slate-50"
             onClick={() => onNavigate('jobs')}>
          <div className="text-xs font-bold font-sans uppercase tracking-wider text-on-surface-variant mb-2">
            COMPLIANT RECORDS
          </div>
          <div className="flex items-end justify-between">
            <span className="text-3xl font-bold font-sans text-primary">{totals.compliant}</span>
            <span className="text-xs font-mono font-bold text-status-ok">Jobs →</span>
          </div>
        </div>
      </section>

      {/* Search & Advanced Filters Panel */}
      <section id="candidate-filters-panel" className="bg-white border border-border-subtle rounded p-5 space-y-4">
        {/* Row 1: Search and Primary Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-center">
          {/* Enhanced Local Search Bar */}
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
                <button
                  id="clear-local-search-btn"
                  onClick={() => setLocalSearch('')}
                  className="p-1 hover:bg-surface-container rounded-full text-on-surface-variant cursor-pointer transition-colors"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Sorting Dropdown */}
          <div className="lg:col-span-4 flex items-center justify-between lg:justify-end gap-3 pt-2 lg:pt-0">
            <div className="text-[11px] font-bold text-on-surface-variant font-sans tracking-wider uppercase shrink-0">SORT BY:</div>
            <select
              id="candidate-sort-select"
              className="bg-surface-container-low border border-border-subtle text-xs font-semibold text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2.5 py-1.5"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'match' | 'name' | 'id')}
            >
              <option value="match">Match Score (Desc)</option>
              <option value="name">Candidate Name A-Z</option>
              <option value="id">Record Identifier ID</option>
            </select>
          </div>
        </div>

        {/* Row 2: Advanced Filter Selectors Dropdowns */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 pt-3 border-t border-dashed border-border-subtle/40">
          {/* Seniority Dropdown Selector */}
          <div>
            <label htmlFor="filter-seniority" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">
              Seniority Level
            </label>
            <select
              id="filter-seniority"
              className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedSeniority}
              onChange={(e) => setSelectedSeniority(e.target.value)}
            >
              <option value="all">All Seniorities</option>
              {availableSeniorities.map((sen) => (
                <option key={sen} value={sen}>{sen}</option>
              ))}
            </select>
          </div>

          {/* Skills Dropdown Selector */}
          <div>
            <label htmlFor="filter-skill" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">
              Top Skills
            </label>
            <select
              id="filter-skill"
              className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedSkill}
              onChange={(e) => setSelectedSkill(e.target.value)}
            >
              <option value="all">All Skills ({availableSkills.length})</option>
              {availableSkills.map((ski) => (
                <option key={ski} value={ski}>{ski}</option>
              ))}
            </select>
          </div>

          {/* Compliance Status Dropdown Selector */}
          <div>
            <label htmlFor="filter-status" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">
              Consent Compliance
            </label>
            <select
              id="filter-status"
              className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
            >
              <option value="all">All Statuses</option>
              <option value="COMPLIANT">Compliant</option>
              <option value="PENDING REVIEW">Pending Review</option>
              <option value="EXPIRING (14D)">Expiring (14D)</option>
            </select>
          </div>

          {/* Match Score Range Selector */}
          <div>
            <label htmlFor="filter-match" className="block text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mb-1">
              Minimum Match Score
            </label>
            <select
              id="filter-match"
              className="w-full bg-surface-container-low border border-border-subtle text-xs text-primary focus:ring-1 focus:ring-indigo-500 cursor-pointer rounded px-2 py-1.5"
              value={String(minMatchScore)}
              onChange={(e) => setMinMatchScore(Number(e.target.value))}
            >
              <option value="0.5">Show All (≥ 0.50)</option>
              <option value="0.7">≥ 0.70 Match</option>
              <option value="0.8">≥ 0.80 Match</option>
              <option value="0.9">≥ 0.90 Match</option>
              <option value="0.95">≥ 0.95 (Ultra High Match)</option>
            </select>
          </div>
        </div>

        {/* Row 3: Quick Filter Toggles & Tags bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-border-subtle bg-surface-container-low/30 px-3 py-1.5 rounded">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-bold text-on-surface-variant font-mono uppercase tracking-wider mr-1.5 flex items-center gap-1">
              <Filter className="w-3 h-3 text-slate-500" />
              <span>QUICK POOLS:</span>
            </span>
            
            <button
              id="filter-highrisk-btn"
              onClick={() => setActiveFilter(activeFilter === 'high-risk' ? 'all' : 'high-risk')}
              className={`px-2.5 py-1 border rounded text-[10px] font-bold flex items-center gap-1.5 cursor-pointer transition-colors ${
                activeFilter === 'high-risk'
                  ? 'bg-status-review/15 border-status-review text-status-review shadow-xs'
                  : 'bg-white border-border-subtle text-on-surface-variant hover:bg-surface-container-low'
              }`}
            >
              <AlertTriangle className="w-3 h-3 text-status-review shrink-0" />
              <span>Pending Reviews</span>
            </button>

            <button
              id="filter-expiring-btn"
              onClick={() => setActiveFilter(activeFilter === 'expiring' ? 'all' : 'expiring')}
              className={`px-2.5 py-1 border rounded text-[10px] font-bold flex items-center gap-1.5 cursor-pointer transition-colors ${
                activeFilter === 'expiring'
                  ? 'bg-status-error/15 border-status-error text-status-error shadow-xs'
                  : 'bg-white border-border-subtle text-on-surface-variant hover:bg-surface-container-low'
              }`}
            >
              <Clock className="w-3 h-3 text-status-error shrink-0" />
              <span>Consent Expiring</span>
            </button>
          </div>

          {/* Active Filter Tags with Clear Button */}
          <div className="flex items-center gap-2.5 justify-between sm:justify-end">
            <span className="text-[11px] font-sans text-on-surface-variant">
              Found <strong>{filteredCandidates.length}</strong> of {candidates.length} candidates
            </span>
            {hasActiveFilters && (
              <button
                id="clear-all-filters-btn"
                onClick={handleClearAllFilters}
                className="text-[10px] font-mono font-bold text-bloodhound-crimson hover:underline cursor-pointer border border-dashed border-bloodhound-crimson/50 px-2 py-0.5 bg-red-50/50 hover:bg-red-50 rounded transition-colors"
              >
                Reset Filters
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Main Candidate Table */}
      <section className="bg-white border border-border-subtle rounded overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-surface-container border-b border-border-subtle">
                <th className="px-6 py-3 font-sans font-bold text-xs text-on-surface-variant tracking-wider">NAME</th>
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
                  <td colSpan={6} className="text-center py-12 text-sm text-on-surface-variant font-sans">
                    No candidates match the specified criteria. Try removing filters or changing your search terms.
                  </td>
                </tr>
              ) : (
                pagedCandidates.map((candidate) => {
                  const isReviewState = candidate.complianceStatus === 'PENDING REVIEW';
                  const isExpiringState = candidate.complianceStatus === 'EXPIRING (14D)';
                  
                  return (
                    <tr
                      key={candidate.id}
                      className={`transition-all h-[56px] group ${
                        isReviewState 
                          ? 'bg-status-review/5 border-l-4 border-l-status-review hover:bg-status-review/10' 
                          : 'hover:bg-slate-50'
                      }`}
                    >
                      {/* Name Details */}
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-surface-dim flex items-center justify-center font-bold text-xs text-primary shrink-0">
                            {candidate.imageInitials}
                          </div>
                          <div>
                            <div className="font-sans font-bold text-sm text-primary">{candidate.name}</div>
                            <div className="font-mono text-[11px] text-on-surface-variant">ID: {candidate.id}</div>
                          </div>
                        </div>
                      </td>

                      {/* Seniority */}
                      <td className="px-6 py-3 text-sm text-on-surface-variant font-sans">
                        {candidate.seniority}
                      </td>

                      {/* Top Skills Tag Chips */}
                      <td className="px-6 py-3">
                        <div className="flex flex-wrap gap-1.5 max-w-[280px]">
                          {candidate.topSkills.map((skill) => (
                            <span
                              key={skill}
                              className="px-2 py-0.5 bg-surface-container-low border border-border-subtle font-mono text-[10px] font-semibold text-primary rounded"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* Match score bar */}
                      <td className="px-6 py-3">
                        <div className="flex items-center gap-3 max-w-[140px]">
                          <div className="flex-grow bg-surface-container-high h-1.5 w-24 rounded-full overflow-hidden shrink-0">
                            <div
                              className={`h-full rounded-full transition-all duration-500 ${
                                isReviewState ? 'bg-status-review' : 'bg-status-ok'
                              }`}
                              style={{ width: `${candidate.matchScore * 100}%` }}
                            ></div>
                          </div>
                          <span className={`font-mono font-bold text-xs ${
                            isReviewState ? 'text-status-review' : 'text-status-ok'
                          }`}>
                            {candidate.matchScore.toFixed(2)}
                          </span>
                        </div>
                      </td>

                      {/* Compliance state */}
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

                      {/* Row actions */}
                      <td className="px-6 py-3">
                        {isReviewState ? (() => {
                          const task = reviewTasks.find(t =>
                            t.status === 'pending' && (
                              t.complianceDetails?.candidateName === candidate.name ||
                              t.existingRecord?.name === candidate.name ||
                              t.outreachDetails?.targetName === candidate.name
                            )
                          );
                          return (
                            <button
                              id={`resolve-btn-${candidate.id}`}
                              onClick={() => task && onOpenReviewTask(task.id)}
                              disabled={!task}
                              className="px-3 py-1 bg-primary text-on-primary font-mono text-[10px] tracking-wider font-bold hover:opacity-90 cursor-pointer rounded disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              RESOLVE
                            </button>
                          );
                        })() : (
                          <button className="text-on-surface-variant hover:text-primary transition-colors cursor-pointer">
                            <MoreVertical className="w-5 h-5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination details */}
        <div className="px-6 py-4 border-t border-border-subtle flex items-center justify-between font-sans">
          <span className="text-sm text-on-surface-variant">
            Showing {Math.min((currentPage - 1) * PAGE_SIZE + 1, filteredCandidates.length)}–{Math.min(currentPage * PAGE_SIZE, filteredCandidates.length)} of {filteredCandidates.length} candidates
          </span>
          <div className="flex gap-2">
            <button
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              className="px-3 py-1 border border-border-subtle text-xs rounded hover:bg-surface-container transition-colors disabled:opacity-50 cursor-pointer"
            >
              Previous
            </button>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              className="px-3 py-1 border border-border-subtle text-xs rounded hover:bg-surface-container transition-colors disabled:opacity-50 cursor-pointer"
            >
              Next
            </button>
          </div>
        </div>
      </section>

      {/* Bento-style Bottom Context row */}
      <section className="grid grid-cols-1 md:grid-cols-3 gap-6 pb-12">
        {/* Bento Quality Details Card */}
        <div className="md:col-span-2 p-8 border border-border-subtle bg-slate-deep text-white relative overflow-hidden rounded-md flex flex-col justify-between min-h-[290px]">
          <div className="relative z-10 space-y-3">
            <div className="text-[10px] tracking-widest font-bold text-amber-500 font-mono uppercase">
              Ingestion Quality Metrics
            </div>
            <div className="text-2xl font-bold max-w-lg leading-tight">
              Automated Precision is at 98.4%
            </div>
            <p className="text-sm text-slate-300 max-w-md font-sans leading-relaxed">
              Our high-confidence ledger heuristics successfully verified 1,204 candidate profiles this week with only 14 requiring manual human intervention rules.
            </p>
          </div>
          
          <div className="relative z-10 flex gap-8 pt-6 border-t border-white/10 mt-6 font-mono">
            <div>
              <div className="font-bold text-xl text-white">1.4s</div>
              <div className="text-[10px] tracking-wider text-slate-400 mt-1 uppercase">AVG PROCESSING TIME</div>
            </div>
            <div>
              <div className="font-bold text-xl text-white">0.02%</div>
              <div className="text-[10px] tracking-wider text-slate-400 mt-1 uppercase">MAPPING ERROR RATE</div>
            </div>
          </div>

          <div className="absolute right-4 bottom-4 opacity-10 select-none pointer-events-none">
            <Microscope className="w-48 h-48 text-white" strokeWidth={1} />
          </div>
        </div>

        {/* Bento Recent Activity Card */}
        <div className="p-8 border border-border-subtle bg-surface rounded-md flex flex-col justify-between min-h-[290px]">
          <div>
            <div className="text-[10px] tracking-widest font-bold text-on-surface-variant font-mono mb-4 uppercase">
              RECENT ACTIVITY
            </div>
            <div className="space-y-6 select-none font-sans">
              {recentLogs.slice(0, 3).map((log, listIdx) => {
                const isSec = log.actor === 'SEC';
                const isHuman = log.actor === 'HUMAN';
                return (
                  <div key={log.id} className="flex gap-3">
                    <div className="shrink-0 mt-0.5">
                      {isSec ? (
                        <Shield className="w-5 h-5 text-indigo-700" />
                      ) : isHuman ? (
                        <Clock className="w-5 h-5 text-amber-600" />
                      ) : (
                        <UserPlus className="w-5 h-5 text-status-ok" />
                      )}
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

          <button
            onClick={() => onNavigate('audit')}
            className="w-full mt-6 py-2.5 bg-white border border-border-subtle rounded text-xs font-mono font-bold uppercase tracking-wider hover:bg-gray-50 transition-colors cursor-pointer"
          >
            VIEW ALL LOGS
          </button>
        </div>
      </section>
    </div>
  );
}
