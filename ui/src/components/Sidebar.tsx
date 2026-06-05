import {
  Briefcase,
  ClipboardCheck,
  Database,
  FolderKanban,
  LayoutDashboard,
  MailCheck,
  Settings,
  Wrench,
} from 'lucide-react';

export type Screen = 'overview' | 'talent' | 'jobs' | 'projects' | 'review' | 'maintenance' | 'settings';

interface SidebarProps {
  activeScreen: Screen;
  pendingReviewsCount: number;
  onNavigate: (screen: Screen) => void;
}

const navItems: Array<{
  id: Screen;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'talent', label: 'Talent Pool', icon: Database },
  { id: 'jobs', label: 'Jobs & Shortlist', icon: Briefcase },
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'review', label: 'Outreach & Review', icon: MailCheck },
  { id: 'maintenance', label: 'Maintenance', icon: Wrench },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export default function Sidebar({ activeScreen, pendingReviewsCount, onNavigate }: SidebarProps) {
  return (
    <>
      <aside className="fixed left-0 top-0 z-30 hidden h-screen w-72 border-r border-slate-200 bg-white lg:block">
        <div className="flex h-full flex-col">
          <div className="border-b border-slate-200 px-6 py-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-cyan-700">Linnify challenge</div>
            <div className="mt-1 text-xl font-semibold text-slate-950">AI Talent Pool Manager</div>
            <p className="mt-2 text-sm leading-5 text-slate-500">
              Extraction, shortlisting, outreach drafts, and human-reviewed actions.
            </p>
          </div>

          <nav className="flex-1 space-y-1 px-3 py-4">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeScreen === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onNavigate(item.id)}
                  className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-medium transition ${
                    isActive
                      ? 'bg-slate-900 text-white shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-950'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="min-w-0 flex-1 truncate">{item.label}</span>
                  {item.id === 'review' && pendingReviewsCount > 0 && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        isActive ? 'bg-white text-slate-900' : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {pendingReviewsCount}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>

          <div className="border-t border-slate-200 p-4">
            <div className="flex items-start gap-3 rounded-md bg-emerald-50 p-3 text-emerald-900">
              <ClipboardCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <p className="text-xs leading-5">
                Consequential updates stay in the review queue until a person approves, rejects, or purges them.
              </p>
            </div>
          </div>
        </div>
      </aside>

      <nav className="fixed bottom-0 left-0 right-0 z-40 grid grid-cols-7 border-t border-slate-200 bg-white lg:hidden">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeScreen === item.id;
          return (
            <button
              key={item.id}
              type="button"
              aria-label={item.label}
              onClick={() => onNavigate(item.id)}
              className={`relative flex h-16 flex-col items-center justify-center gap-1 text-[10px] font-medium ${
                isActive ? 'text-slate-950' : 'text-slate-500'
              }`}
            >
              <Icon className="h-5 w-5" />
              <span className="max-w-full truncate px-1">{item.label.split(' ')[0]}</span>
              {item.id === 'review' && pendingReviewsCount > 0 && (
                <span className="absolute right-4 top-2 h-2 w-2 rounded-full bg-amber-500" />
              )}
            </button>
          );
        })}
      </nav>
    </>
  );
}
