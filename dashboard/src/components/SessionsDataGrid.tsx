'use client';

import React, { useState, useMemo, useCallback } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  SortingState,
  ColumnFiltersState,
  VisibilityState,
  FilterFn,
} from '@tanstack/react-table';
import type { SessionFull } from './SessionDetailPanel';
import { SessionDetailPanel } from './SessionDetailPanel';

// ── Helpers ────────────────────────────────────────────────────────────────
function fmt(v: string | null | undefined, type: 'date' | 'time' | 'raw' = 'raw') {
  if (!v) return null;
  if (type === 'date') return new Date(v).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' });
  if (type === 'time') {
    try { return new Date(`1970-01-01T${v}`).toLocaleTimeString('en-AU', { hour: '2-digit', minute: '2-digit', hour12: true }); }
    catch { return v; }
  }
  return v;
}

function Badge({ children, variant = 'neutral' }: { children: React.ReactNode; variant?: string }) {
  return <span className={`badge badge-${variant}`}>{children}</span>;
}

function Cell({ v }: { v: React.ReactNode }) {
  return <span className="text-[var(--color-text-primary)]">{v ?? <span className="text-[var(--color-text-muted)] italic text-[10px]">—</span>}</span>;
}

// ── Column definition ──────────────────────────────────────────────────────
const ch = createColumnHelper<SessionFull>();

const ALL_COLUMNS = [
  ch.accessor('id', {
    header: 'ID', size: 60,
    cell: i => <span className="font-mono text-xs text-[var(--color-text-muted)]">{i.getValue()}</span>,
  }),
  ch.accessor('heidi_session_id', {
    header: 'Heidi Session ID', size: 220,
    cell: i => <span className="font-mono text-xs text-[var(--color-brand-400)]">{i.getValue()}</span>,
  }),
  ch.accessor('patient_name_fallback', {
    header: 'Patient Name', size: 160,
    cell: i => <Cell v={i.getValue() || '—'} />,
  }),
  ch.accessor('session_title', {
    header: 'Title', size: 180,
    cell: i => <Cell v={i.getValue()} />,
  }),
  ch.accessor('subtitle', {
    header: 'Subtitle', size: 160,
    cell: i => <Cell v={i.getValue()} />,
  }),
  ch.accessor('session_date', {
    header: 'Date', size: 120,
    cell: i => <Cell v={fmt(i.getValue(), 'date')} />,
    sortingFn: 'datetime',
  }),
  ch.accessor('session_time', {
    header: 'Time', size: 90,
    cell: i => <Cell v={fmt(i.getValue(), 'time')} />,
  }),
  ch.accessor('duration', {
    header: 'Duration', size: 90,
    cell: i => i.getValue() ? <Badge variant="neutral">{i.getValue()}</Badge> : <Cell v={null} />,
  }),
  ch.accessor('language', {
    header: 'Language', size: 90,
    cell: i => i.getValue() ? <Badge variant="info">{i.getValue()}</Badge> : <Cell v={null} />,
  }),
  ch.accessor(row => row.transcript ? (row.transcript.word_count ?? 0) : null, {
    id: 'word_count', header: 'Words', size: 75,
    cell: i => {
      const v = i.getValue();
      return v != null ? <span className="font-mono text-xs text-emerald-400">{v.toLocaleString()}</span> : <Cell v={null} />;
    },
  }),
  ch.accessor(row => row.transcript != null, {
    id: 'has_transcript', header: 'Transcript', size: 100,
    cell: i => i.getValue() ? <Badge variant="success">✓ Yes</Badge> : <Badge variant="danger">✗ No</Badge>,
  }),
  ch.accessor(row => row.note != null, {
    id: 'has_note', header: 'SOAP Note', size: 100,
    cell: i => i.getValue() ? <Badge variant="success">✓ Yes</Badge> : <Badge variant="danger">✗ No</Badge>,
  }),
  ch.accessor(row => row.audits?.[0]?.status ?? null, {
    id: 'audit_status', header: 'Audit Status', size: 110,
    cell: i => {
      const v = i.getValue() as string | null;
      if (!v) return <Cell v={null} />;
      const variant = v === 'success' ? 'success' : v === 'failed' ? 'danger' : 'warning';
      return <Badge variant={variant}>{v}</Badge>;
    },
  }),
  ch.accessor(row => row.audits?.[0]?.retries_used ?? null, {
    id: 'retries', header: 'Retries', size: 75,
    cell: i => {
      const v = i.getValue() as number | null;
      if (v == null) return <Cell v={null} />;
      return <span className={`font-mono text-xs ${v > 0 ? 'text-amber-400' : 'text-[var(--color-text-muted)]'}`}>{v}</span>;
    },
  }),
  ch.accessor('internal_identifier', {
    header: 'Internal ID', size: 140,
    cell: i => <span className="font-mono text-[10px] text-[var(--color-text-muted)]">{i.getValue() ?? '—'}</span>,
  }),
  ch.accessor('source_url', {
    header: 'Source URL', size: 200,
    cell: i => i.getValue()
      ? <a href={i.getValue()!} target="_blank" rel="noopener noreferrer" className="text-[var(--color-brand-400)] hover:underline text-xs truncate block max-w-xs">{i.getValue()!.replace('https://', '')}</a>
      : <Cell v={null} />,
  }),
  ch.accessor('created_at', {
    header: 'Archived At', size: 160,
    cell: i => <span className="text-xs text-[var(--color-text-muted)]">{new Date(i.getValue()).toLocaleString('en-AU')}</span>,
    sortingFn: 'datetime',
  }),
];

const DEFAULT_VISIBLE: VisibilityState = {
  id: true,
  heidi_session_id: true,
  patient_name_fallback: true,
  session_title: true,
  subtitle: false,
  session_date: true,
  session_time: true,
  duration: true,
  language: true,
  word_count: true,
  has_transcript: true,
  has_note: true,
  audit_status: true,
  retries: false,
  internal_identifier: false,
  source_url: false,
  created_at: false,
};

// ── Global fuzzy filter ────────────────────────────────────────────────────
const globalFilter: FilterFn<SessionFull> = (row, _colId, value: string) => {
  const q = value.toLowerCase();
  const fields = [
    row.original.heidi_session_id,
    row.original.patient_name_fallback,
    row.original.session_title,
    row.original.subtitle,
    row.original.language,
    row.original.duration,
  ];
  return fields.some(f => f?.toLowerCase().includes(q));
};

// ── Main component ─────────────────────────────────────────────────────────
interface Props { data: SessionFull[] }

export function SessionsDataGrid({ data }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: 'session_date', desc: true }]);
  const [colFilters, setColFilters] = useState<ColumnFiltersState>([]);
  const [globalQ, setGlobalQ] = useState('');
  const [colVisibility, setColVisibility] = useState<VisibilityState>(DEFAULT_VISIBLE);
  const [colPickerOpen, setColPickerOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [pageSize, setPageSize] = useState(25);

  const table = useReactTable({
    data,
    columns: ALL_COLUMNS,
    state: { sorting, columnFilters: colFilters, globalFilter: globalQ, columnVisibility: colVisibility },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColFilters,
    onGlobalFilterChange: setGlobalQ,
    onColumnVisibilityChange: setColVisibility,
    globalFilterFn: globalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  // Keep pagination in sync with pageSize state
  useMemo(() => { table.setPageSize(pageSize); }, [pageSize]);

  const exportCsv = useCallback(() => {
    const rows = table.getFilteredRowModel().rows;
    const visibleCols = table.getVisibleLeafColumns().map(c => c.id);
    const headers = visibleCols.join(',');
    const lines = rows.map(row =>
      visibleCols.map(colId => {
        const val = row.getValue(colId);
        const str = val == null ? '' : String(val);
        return `"${str.replace(/"/g, '""')}"`;
      }).join(',')
    );
    const csv = [headers, ...lines].join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    a.download = `heidi-sessions-${Date.now()}.csv`;
    a.click();
  }, [table]);

  const exportJson = useCallback(() => {
    const rows = table.getFilteredRowModel().rows.map(r => r.original);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' }));
    a.download = `heidi-sessions-${Date.now()}.json`;
    a.click();
  }, [table]);

  const totalFiltered = table.getFilteredRowModel().rows.length;
  const totalRows = data.length;

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Global search */}
        <div className="relative flex-1 min-w-52">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] text-sm">🔎</span>
          <input
            type="text"
            placeholder="Search sessions, patients, titles…"
            value={globalQ}
            onChange={e => setGlobalQ(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg border border-[var(--color-surface-border)] bg-[var(--color-surface-2)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-brand-500)] transition-colors"
          />
        </div>

        {/* Stats */}
        <span className="text-xs text-[var(--color-text-muted)]">
          {totalFiltered === totalRows ? `${totalRows} sessions` : `${totalFiltered} of ${totalRows} sessions`}
        </span>

        <div className="flex-1" />

        {/* Column picker */}
        <div className="relative">
          <button
            onClick={() => setColPickerOpen(o => !o)}
            className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-surface-border)] bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)] transition-colors"
          >
            ⊞ Columns
          </button>
          {colPickerOpen && (
            <div className="absolute right-0 top-full mt-1 z-30 glass rounded-xl p-3 shadow-2xl min-w-52 grid grid-cols-2 gap-1">
              {table.getAllLeafColumns().map(col => (
                <label key={col.id} className="flex items-center gap-2 text-xs text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] cursor-pointer py-0.5">
                  <input
                    type="checkbox"
                    checked={col.getIsVisible()}
                    onChange={col.getToggleVisibilityHandler()}
                    className="accent-[var(--color-brand-500)] w-3 h-3"
                  />
                  {String(col.columnDef.header)}
                </label>
              ))}
            </div>
          )}
        </div>

        {/* Export */}
        <button onClick={exportCsv} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-surface-border)] bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] hover:text-emerald-400 hover:border-emerald-500/40 transition-colors">
          ↓ CSV
        </button>
        <button onClick={exportJson} className="text-xs px-3 py-1.5 rounded-lg border border-[var(--color-surface-border)] bg-[var(--color-surface-2)] text-[var(--color-text-secondary)] hover:text-[var(--color-brand-400)] hover:border-[var(--color-brand-500)]/40 transition-colors">
          ↓ JSON
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-[var(--color-surface-border)] overflow-hidden glass">
        <div className="overflow-x-auto">
          <table className="data-table w-full border-collapse">
            <thead>
              {table.getHeaderGroups().map(hg => (
                <tr key={hg.id}>
                  {/* Expand col */}
                  <th style={{ width: 36 }} className="text-center">
                    <span className="text-[var(--color-text-muted)]">↕</span>
                  </th>
                  {hg.headers.map(header => (
                    <th
                      key={header.id}
                      style={{ width: header.getSize() }}
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <div className="flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getIsSorted() === 'asc' && <span className="text-[var(--color-brand-400)]">↑</span>}
                        {header.column.getIsSorted() === 'desc' && <span className="text-[var(--color-brand-400)]">↓</span>}
                        {!header.column.getIsSorted() && <span className="opacity-20">⇅</span>}
                      </div>
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.length === 0 && (
                <tr>
                  <td colSpan={table.getVisibleLeafColumns().length + 1}
                      className="py-16 text-center text-[var(--color-text-muted)]">
                    No sessions found. Run the scraper to populate data.
                  </td>
                </tr>
              )}
              {table.getRowModel().rows.map(row => {
                const session = row.original;
                const isExpanded = expandedId === session.id;
                const isSelected = selectedIds.has(session.id);
                return (
                  <React.Fragment key={row.id}>
                    <tr
                      className={isExpanded ? 'expanded' : ''}
                      style={{ background: isSelected ? 'rgba(59,130,246,0.05)' : undefined }}
                    >
                      {/* Expand button */}
                      <td className="text-center" style={{ width: 36 }}>
                        <button
                          onClick={() => setExpandedId(id => id === session.id ? null : session.id)}
                          className="text-[var(--color-text-muted)] hover:text-[var(--color-brand-400)] transition-colors text-base leading-none"
                          title={isExpanded ? 'Collapse' : 'Expand session details'}
                        >
                          {isExpanded ? '▼' : '▶'}
                        </button>
                      </td>
                      {row.getVisibleCells().map(cell => (
                        <td
                          key={cell.id}
                          style={{ width: cell.column.getSize() }}
                          onClick={() => {
                            const colId = cell.column.id;
                            if (colId === 'source_url') return; // let link handle
                            setExpandedId(id => id === session.id ? null : session.id);
                          }}
                          className="cursor-pointer"
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>

                    {/* Expanded detail panel */}
                    {isExpanded && (
                      <tr>
                        <td colSpan={table.getVisibleLeafColumns().length + 1} className="p-4 bg-[var(--color-surface-1)]">
                          <SessionDetailPanel session={session} onClose={() => setExpandedId(null)} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between px-4 py-2.5 border-t border-[var(--color-surface-border)] bg-[var(--color-surface-0)]/50 text-xs text-[var(--color-text-muted)]">
          <div className="flex items-center gap-2">
            <span>Rows per page:</span>
            {[25, 50, 100].map(n => (
              <button
                key={n}
                onClick={() => setPageSize(n)}
                className={[
                  'px-2 py-0.5 rounded transition-colors',
                  pageSize === n
                    ? 'bg-[var(--color-brand-600)] text-white font-bold'
                    : 'hover:bg-[var(--color-surface-3)] text-[var(--color-text-muted)]',
                ].join(' ')}
              >
                {n}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <span>
              Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount() || 1}
              {' '}({totalFiltered} total)
            </span>
            <div className="flex gap-1">
              <button onClick={() => table.firstPage()} disabled={!table.getCanPreviousPage()} className="px-2 py-0.5 rounded hover:bg-[var(--color-surface-3)] disabled:opacity-30 transition-colors">⟪</button>
              <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()} className="px-2 py-0.5 rounded hover:bg-[var(--color-surface-3)] disabled:opacity-30 transition-colors">‹</button>
              <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()} className="px-2 py-0.5 rounded hover:bg-[var(--color-surface-3)] disabled:opacity-30 transition-colors">›</button>
              <button onClick={() => table.lastPage()} disabled={!table.getCanNextPage()} className="px-2 py-0.5 rounded hover:bg-[var(--color-surface-3)] disabled:opacity-30 transition-colors">⟫</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
