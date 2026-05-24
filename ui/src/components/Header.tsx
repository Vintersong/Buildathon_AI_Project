import { Bot, RefreshCcw, Search, Upload } from 'lucide-react';
import { Screen } from './Sidebar';

interface HeaderProps {
  activeScreen: Screen;
  searchQuery: string;
  isSyncing: boolean;
  pendingReviewsCount: number;
  onSearchChange: (value: string) => void;
  onRefresh: () => void;
  onOpenIngest: () => void;
  onToggleAssistant: () => void;
}

const titles: Record<Screen, { title: string; subtitle: string; searchable: boolean }> = {
  overview: {
    title: 'Overview',
    subtitle: 'Live pool health, review load, extraction quality, and recent audit activity.',
    searchable: false,
  },
  talent: {
    title: 'Talent Pool',
    subtitle: 'Search extracted profiles, inspect details, ingest new CVs, and refresh selected candidates.',
    searchable: true,
  },
  jobs: {
    title: 'Jobs & Shortlist',
    subtitle: 'Create job requirements, rank candidates, and send outreach drafts into review.',
    searchable: true,
  },
  review: {
    title: 'Outreach & Review',
    subtitle: 'Approve or reject compliance flags, identity conflicts, and outreach drafts.',
    searchable: false,
  },
  maintenance: {
    title: 'Maintenance',
    subtitle: 'Process intake files, find stale profiles, refresh selected records, and monitor audit health.',
    searchable: false,
  },
  settings: {
    title: 'Settings',
    subtitle: 'Configure local Gemma routing, external model fallback, thresholds, and API keys.',
    searchable: false,
  },
};

export default function Header({
  activeScreen,
  searchQuery,
  isSyncing,
  pendingReviewsCount,
  onSearchChange,
  onRefresh,
  onOpenIngest,
  onToggleAssistant,
}: HeaderProps) {
  const meta = titles[activeScreen];

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-normal text-slate-950">{meta.title}</h1>
              {pendingReviewsCount > 0 && (
                <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-800">
                  {pendingReviewsCount} pending review{pendingReviewsCount === 1 ? '' : 's'}
                </span>
              )}
            </div>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-500">{meta.subtitle}</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onRefresh}
              className="inline-flex h-10 items-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <RefreshCcw className={`h-4 w-4 ${isSyncing ? 'animate-spin' : ''}`} />
              Refresh
            </button>
            <button
              type="button"
              onClick={onOpenIngest}
              className="inline-flex h-10 items-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800"
            >
              <Upload className="h-4 w-4" />
              Ingest
            </button>
            <button
              type="button"
              aria-label="Open workflow assistant"
              onClick={onToggleAssistant}
              className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            >
              <Bot className="h-4 w-4" />
            </button>
          </div>
        </div>

        {meta.searchable && (
          <div className="relative max-w-2xl">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={searchQuery}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder={activeScreen === 'talent' ? 'Search candidates, skills, seniority, or status' : 'Search jobs, location, tags, or department'}
              className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-2 focus:ring-cyan-100"
            />
          </div>
        )}
      </div>
    </header>
  );
}
