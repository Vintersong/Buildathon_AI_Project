/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Search, CloudCheck, Bell, User, Sparkles } from 'lucide-react';

interface HeaderProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  activeScreen: string;
  isSynced: boolean;
  onForceSync: () => void;
  notificationsCount: number;
  isAICopilotOpen: boolean;
  onToggleAICopilot: () => void;
  onBellClick?: () => void;
  onProfileClick?: () => void;
}

export default function Header({
  searchQuery,
  onSearchChange,
  activeScreen,
  isSynced,
  onForceSync,
  notificationsCount,
  isAICopilotOpen,
  onToggleAICopilot,
  onBellClick,
  onProfileClick
}: HeaderProps) {
  // Get screen-specific placeholder
  const getPlaceholder = () => {
    switch (activeScreen) {
      case 'candidates':
        return 'Search precision talent pool...';
      case 'jobs':
        return 'Search requirements, matches, or logs...';
      case 'review':
        return 'Search tasks, IDs, or audit trails...';
      case 'audit':
        return 'Search events, tools, or hash IDs...';
      default:
        return 'Search...';
    }
  };

  return (
    <header className="flex justify-between items-center w-full px-8 bg-white h-16 border-b border-border-subtle sticky top-0 z-50">
      {/* Search Input Container */}
      <div className="flex items-center flex-grow max-w-xl">
        <div id="search-container" className="flex items-center w-full border border-border-subtle rounded px-3 py-1.5 focus-within:ring-2 focus-within:ring-slate-deep focus-within:border-slate-deep transition-all">
          <Search className="w-5 h-5 text-on-surface-variant mr-3" />
          <input
            id="global-search-input"
            type="text"
            className="bg-transparent border-none outline-none focus:ring-0 w-full font-sans text-sm text-on-surface placeholder:text-on-surface-variant placeholder:opacity-75 focus-visible:outline-none"
            placeholder={getPlaceholder()}
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
      </div>

      {/* Utilities */}
      <div className="flex items-center gap-6 ml-4 select-none">
        {/* Sync Status Badge */}
        <button 
          onClick={onForceSync} 
          className="flex items-center gap-2 px-3 py-1 bg-surface-container rounded-md hover:bg-surface-container-high transition-colors text-xs font-semibold cursor-pointer"
        >
          <CloudCheck className={`w-4 h-4 text-status-ok ${isSynced ? '' : 'animate-spin'}`} />
          <span className="font-mono text-status-ok tracking-wide">
            {isSynced ? 'LOCAL STORAGE SYNCED' : 'SYNCING CHANGES...'}
          </span>
        </button>

        {/* Pulse Status */}
        <div className="flex items-center gap-2 border-l border-border-subtle pl-6">
          <span className="w-2 h-2 rounded-full bg-status-ok animate-pulse"></span>
          <span className="text-[11px] tracking-wider font-bold text-on-surface-variant uppercase">SYSTEM ONLINE</span>
        </div>

        {/* Action icons */}
        <div className="flex items-center gap-4 border-l border-border-subtle pl-6">
          {/* AI Copilot Toggle Button */}
          <button 
            id="toggle-ai-copilot-header-btn"
            onClick={onToggleAICopilot}
            className={`p-1.5 rounded-full border transition-all cursor-pointer relative flex items-center justify-center ${
              isAICopilotOpen 
                ? 'bg-amber-500 border-amber-500 text-white shadow-md shadow-amber-500/20' 
                : 'bg-amber-50 border-amber-200 text-amber-600 hover:bg-amber-100 hover:text-amber-700'
            }`}
            title="Toggle Bloodhound AI Copilot"
          >
            <Sparkles className="w-4 h-4" />
            {!isAICopilotOpen && (
              <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-500 rounded-full animate-ping"></span>
            )}
          </button>

          <button onClick={onBellClick} className="relative p-1 text-on-surface-variant hover:text-primary transition-colors cursor-pointer">
            <Bell className="w-5 h-5" />
            {notificationsCount > 0 && (
              <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-bloodhound-crimson rounded-full ring-2 ring-white animate-bounce"></span>
            )}
          </button>
          <button
            type="button"
            onClick={onProfileClick}
            className="p-1 h-8 w-8 rounded-full bg-surface-container flex items-center justify-center text-on-surface-variant hover:text-primary border border-border-subtle cursor-pointer font-sans text-xs font-bold"
            title="Open settings"
          >
            <User className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
