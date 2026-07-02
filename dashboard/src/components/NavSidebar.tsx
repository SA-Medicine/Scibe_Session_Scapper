'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useState } from 'react';

const NAV = [
  { href: '/',                label: 'Dashboard',       icon: '⬛', short: 'DB' },
  { href: '/audit-explorer',  label: 'Audit Explorer',  icon: '🔍', short: 'AU' },
  { href: '/analytics',       label: 'Analytics',       icon: '📊', short: 'AN' },
  { href: '/diff-viewer',     label: 'Diff Viewer',     icon: '⚖️',  short: 'DV' },
  { href: '/export-center',   label: 'Export Center',   icon: '📦', short: 'EX' },
  { href: '/search',          label: 'Search',          icon: '🔎', short: 'SR' },
  { href: '/recovery-center', label: 'Recovery',        icon: '🔧', short: 'RC' },
];

export function NavSidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      style={{ width: collapsed ? 56 : 220, transition: 'width 0.2s ease' }}
      className="flex-shrink-0 flex flex-col h-full border-r border-[var(--color-surface-border)] bg-[var(--color-surface-1)] overflow-hidden"
    >
      {/* Logo / toggle */}
      <div className="flex items-center justify-between px-3 py-4 border-b border-[var(--color-surface-border)]">
        {!collapsed && (
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-[var(--color-brand-600)] flex items-center justify-center text-white text-xs font-black flex-shrink-0">
              H
            </div>
            <span className="text-sm font-bold text-[var(--color-text-primary)] truncate">Heidi Archive</span>
          </div>
        )}
        {collapsed && (
          <div className="w-7 h-7 rounded-lg bg-[var(--color-brand-600)] flex items-center justify-center text-white text-xs font-black mx-auto">
            H
          </div>
        )}
        <button
          onClick={() => setCollapsed(c => !c)}
          className="ml-auto p-1 rounded hover:bg-[var(--color-surface-3)] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors flex-shrink-0"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '›' : '‹'}
        </button>
      </div>

      {/* Nav links */}
      <nav className="flex-1 py-3 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {NAV.map(({ href, label, icon, short }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={[
                'flex items-center gap-3 mx-2 px-2.5 py-2 rounded-md text-sm font-medium transition-all duration-150 group',
                active
                  ? 'bg-[var(--color-brand-600)] text-white shadow-sm'
                  : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-text-primary)]',
              ].join(' ')}
            >
              <span className="text-base flex-shrink-0">{icon}</span>
              {!collapsed && (
                <span className="truncate leading-none">{label}</span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="p-3 border-t border-[var(--color-surface-border)]">
          <div className="text-[10px] text-[var(--color-text-muted)] leading-relaxed">
            <div className="font-semibold text-[var(--color-text-secondary)] mb-1">Run Scraper</div>
            <div>Docker: <code className="bg-[var(--color-surface-3)] px-1 rounded text-[9px]">docker-compose up backend</code></div>
            <div className="mt-1">Local: <code className="bg-[var(--color-surface-3)] px-1 rounded text-[9px]">.\run_local.ps1</code></div>
          </div>
        </div>
      )}
    </aside>
  );
}
