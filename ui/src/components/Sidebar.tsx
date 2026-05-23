/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Users, Briefcase, ClipboardCheck, ScrollText, Settings, Plus, PawPrint } from 'lucide-react';

interface SidebarProps {
  activeScreen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings';
  onNavigate: (screen: 'candidates' | 'jobs' | 'review' | 'audit' | 'settings') => void;
  onOpenIngest: () => void;
  pendingReviewsCount: number;
}

export default function Sidebar({
  activeScreen,
  onNavigate,
  onOpenIngest,
  pendingReviewsCount
}: SidebarProps) {
  const menuItems = [
    {
      id: 'candidates' as const,
      label: 'Candidates',
      icon: Users
    },
    {
      id: 'jobs' as const,
      label: 'Job Requirements',
      icon: Briefcase
    },
    {
      id: 'review' as const,
      label: 'Review Queue',
      icon: ClipboardCheck,
      badge: pendingReviewsCount > 0 ? pendingReviewsCount : undefined
    },
    {
      id: 'audit' as const,
      label: 'Audit Logs',
      icon: ScrollText
    },
    {
      id: 'settings' as const,
      label: 'Settings',
      icon: Settings
    }
  ];

  return (
    <aside className="no-scrollbar flex flex-col h-screen w-64 border-r border-border-subtle bg-surface sticky top-0 overflow-y-auto">
      {/* Brand logo */}
      <div className="px-6 py-8 flex items-center gap-3">
        <div className="w-8 h-8 bg-bloodhound-crimson flex items-center justify-center rounded">
          <PawPrint className="w-5 h-5 text-white" />
        </div>
        <div>
          <div className="font-sans font-bold text-xl text-bloodhound-crimson leading-none">Bloodhound</div>
          <div className="text-xs text-on-surface-variant tracking-wider mt-0.5 font-sans">Precision Talent</div>
        </div>
      </div>

      {/* Navigation menu */}
      <nav className="flex-1 px-3 space-y-1">
        {menuItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeScreen === item.id;
          return (
            <button
              id={`nav-link-${item.id}`}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center justify-between px-4 py-3 text-sm font-medium transition-colors cursor-pointer rounded-md ${
                isActive
                  ? 'text-primary font-bold border-r-2 border-primary bg-surface-container-low'
                  : 'text-on-surface-variant hover:bg-surface-container-high hover:text-primary'
              }`}
            >
              <div className="flex items-center gap-3">
                <Icon className={`w-5 h-5 ${isActive ? 'text-primary' : 'text-on-surface-variant'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge !== undefined && (
                <span className="bg-bloodhound-crimson text-white text-[10px] px-1.5 py-0.5 rounded font-mono font-bold">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Action footer */}
      <div className="p-4 border-t border-border-subtle">
        <button
          id="sidebar-ingest-btn"
          onClick={onOpenIngest}
          className="w-full bg-slate-deep text-white py-3 px-4 font-sans font-semibold text-sm hover:bg-black transition-colors rounded flex items-center justify-center gap-2 cursor-pointer transition-transform active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>Ingest Candidate</span>
        </button>
      </div>
    </aside>
  );
}
