'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

interface LogEntry {
  type: 'log' | 'connected' | 'waiting' | 'error';
  ts: number;
  level?: string;
  msg: string;
  src?: string;
  historical?: boolean;
}

export function ScraperConsole({ className = '' }: { className?: string }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<string>('ALL');
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (esRef.current) esRef.current.close();
    setEntries([]);
    setConnected(false);

    const es = new EventSource('/api/scraper-logs');
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as LogEntry;
        setEntries(prev => {
          const next = [...prev, data];
          return next.length > 2000 ? next.slice(-2000) : next;
        });
        if (data.type === 'connected') setConnected(true);
      } catch { /* ignore parse errors */ }
    };

    es.onerror = () => {
      setConnected(false);
    };

    return () => es.close();
  }, []);

  useEffect(() => {
    const cleanup = connect();
    return cleanup;
  }, [connect]);

  // Auto-scroll unless paused
  useEffect(() => {
    if (!paused && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [entries, paused]);

  const downloadLogs = () => {
    const text = entries
      .filter(e => e.type === 'log')
      .map(e => `[${new Date(e.ts).toISOString()}] [${e.level}] ${e.msg}  (${e.src || ''})`)
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `heidi-scraper-${Date.now()}.log`;
    a.click();
  };

  const levelColor: Record<string, string> = {
    INFO: 'text-blue-400',
    WARNING: 'text-amber-400',
    ERROR: 'text-rose-400',
    waiting: 'text-zinc-600',
    connected: 'text-emerald-400',
    error: 'text-rose-400',
  };

  const filtered = filter === 'ALL'
    ? entries
    : entries.filter(e => (e.level || e.type).toUpperCase() === filter);

  return (
    <div className={`flex flex-col rounded-xl border border-[var(--color-surface-border)] bg-[var(--color-surface-1)] overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-surface-border)] bg-[var(--color-surface-0)]/60">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse-dot' : 'bg-zinc-600'}`} />
          <span className="text-xs font-bold text-[var(--color-text-secondary)] uppercase tracking-wider">
            Live Scraper Console
          </span>
          {entries.filter(e => e.type === 'log').length > 0 && (
            <span className="badge badge-neutral">
              {entries.filter(e => e.type === 'log').length} lines
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Filter */}
          {(['ALL', 'INFO', 'WARNING', 'ERROR'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={[
                'text-[10px] font-bold px-2 py-0.5 rounded transition-colors',
                filter === f
                  ? f === 'ALL' ? 'bg-[var(--color-brand-600)] text-white'
                    : f === 'INFO' ? 'bg-blue-600/80 text-white'
                    : f === 'WARNING' ? 'bg-amber-600/80 text-white'
                    : 'bg-rose-600/80 text-white'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)]',
              ].join(' ')}
            >
              {f}
            </button>
          ))}
          <div className="w-px h-3 bg-[var(--color-surface-border)]" />
          <button
            onClick={() => setPaused(p => !p)}
            className="text-[10px] font-bold px-2 py-0.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-3)] transition-colors"
            title={paused ? 'Resume auto-scroll' : 'Pause auto-scroll'}
          >
            {paused ? '▶ Resume' : '⏸ Pause'}
          </button>
          <button onClick={() => setEntries([])} className="text-[10px] font-bold px-2 py-0.5 rounded text-[var(--color-text-muted)] hover:text-rose-400 hover:bg-[var(--color-surface-3)] transition-colors">
            Clear
          </button>
          <button onClick={downloadLogs} className="text-[10px] font-bold px-2 py-0.5 rounded text-[var(--color-text-muted)] hover:text-[var(--color-brand-400)] hover:bg-[var(--color-surface-3)] transition-colors">
            ↓ Save
          </button>
          <button onClick={connect} className="text-[10px] font-bold px-2 py-0.5 rounded text-[var(--color-text-muted)] hover:text-emerald-400 hover:bg-[var(--color-surface-3)] transition-colors">
            ↺ Reconnect
          </button>
        </div>
      </div>

      {/* Log body */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto p-3 font-mono text-xs leading-relaxed"
        style={{ minHeight: 200, maxHeight: 340, background: '#050811' }}
      >
        {filtered.length === 0 && (
          <div className="text-[var(--color-text-muted)] text-center py-8">
            {connected
              ? 'Waiting for log entries...'
              : 'Connecting to scraper log stream...'}
          </div>
        )}
        {filtered.map((entry, i) => {
          const level = entry.level || entry.type;
          const col = levelColor[level] || 'text-zinc-400';
          const time = new Date(entry.ts).toLocaleTimeString('en-AU', { hour12: false });
          return (
            <div
              key={i}
              className={`console-line flex gap-2 ${entry.historical ? 'opacity-50' : ''} ${col}`}
            >
              <span className="text-zinc-700 flex-shrink-0 select-none">{time}</span>
              <span className={`flex-shrink-0 w-14 font-bold ${col}`}>[{level}]</span>
              <span className="flex-1 break-all">{entry.msg}</span>
              {entry.src && (
                <span className="text-zinc-700 flex-shrink-0 text-[10px] ml-2">{entry.src}</span>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
