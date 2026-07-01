'use client';

import React, { useEffect, useState, useRef } from 'react';
import { Database, FileText, ClipboardList, Activity, Terminal, RefreshCw, Layers } from 'lucide-react';

interface Stats {
  total_sessions: string;
  total_transcripts: string;
  total_notes: string;
}

interface Session {
  id: number;
  heidi_session_id: string;
  session_date: string;
  session_time: string;
  has_transcript: boolean;
  has_note: boolean;
}

interface LogEntry {
  ts: number;
  level: string;
  msg: string;
  src: string;
  logger: string;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchSessions = async () => {
    try {
      const res = await fetch('/api/sessions');
      const data = await res.json();
      if (data.success) {
        setStats(data.stats);
        setSessions(data.recentSessions);
      }
    } catch (e) {
      console.error("Failed to fetch sessions", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const eventSource = new EventSource('/api/logs');
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLogs(prev => {
          const newLogs = [...prev, data];
          return newLogs.slice(-100); // keep last 100 logs
        });
      } catch (e) {
        // Handle raw string logs if not json
        setLogs(prev => {
          const newLogs = [...prev, { ts: Date.now(), level: 'INFO', msg: event.data, src: '', logger: '' }];
          return newLogs.slice(-100);
        });
      }
    };

    return () => eventSource.close();
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const getLogColor = (level: string) => {
    switch (level?.toUpperCase()) {
      case 'ERROR': return 'text-red-400';
      case 'WARNING': return 'text-yellow-400';
      case 'DEBUG': return 'text-gray-400';
      default: return 'text-blue-300';
    }
  };

  return (
    <div className="min-h-screen p-8 max-w-7xl mx-auto space-y-8">
      
      <header className="flex items-center justify-between mb-12">
        <div className="flex items-center space-x-4">
          <div className="p-3 bg-blue-500/20 rounded-2xl border border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.3)]">
            <Layers className="w-8 h-8 text-blue-400" />
          </div>
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
              Heidi Archival Platform
            </h1>
            <p className="text-slate-400 text-sm mt-1">Real-time Dashboard & System Overview</p>
          </div>
        </div>
        
        <button 
          onClick={() => fetchSessions()}
          className="flex items-center space-x-2 px-4 py-2 rounded-lg glass-panel hover:bg-slate-800/50 transition-all text-slate-300"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Refresh</span>
        </button>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="glass-panel p-6 rounded-2xl relative overflow-hidden group hover:border-blue-500/30 transition-all duration-300">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <Database className="w-24 h-24 text-blue-500" />
          </div>
          <div className="relative z-10">
            <div className="flex items-center space-x-3 mb-4">
              <div className="p-2 bg-blue-500/20 rounded-lg"><Database className="w-5 h-5 text-blue-400" /></div>
              <h3 className="font-medium text-slate-300">Total Sessions</h3>
            </div>
            <p className="text-5xl font-bold text-white tracking-tight">{loading ? '-' : stats?.total_sessions || '0'}</p>
          </div>
        </div>

        <div className="glass-panel p-6 rounded-2xl relative overflow-hidden group hover:border-purple-500/30 transition-all duration-300">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <FileText className="w-24 h-24 text-purple-500" />
          </div>
          <div className="relative z-10">
            <div className="flex items-center space-x-3 mb-4">
              <div className="p-2 bg-purple-500/20 rounded-lg"><FileText className="w-5 h-5 text-purple-400" /></div>
              <h3 className="font-medium text-slate-300">Transcripts Extracted</h3>
            </div>
            <p className="text-5xl font-bold text-white tracking-tight">{loading ? '-' : stats?.total_transcripts || '0'}</p>
          </div>
        </div>

        <div className="glass-panel p-6 rounded-2xl relative overflow-hidden group hover:border-emerald-500/30 transition-all duration-300">
          <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
            <ClipboardList className="w-24 h-24 text-emerald-500" />
          </div>
          <div className="relative z-10">
            <div className="flex items-center space-x-3 mb-4">
              <div className="p-2 bg-emerald-500/20 rounded-lg"><ClipboardList className="w-5 h-5 text-emerald-400" /></div>
              <h3 className="font-medium text-slate-300">Notes Extracted</h3>
            </div>
            <p className="text-5xl font-bold text-white tracking-tight">{loading ? '-' : stats?.total_notes || '0'}</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pt-4">
        
        {/* Recent Sessions Table */}
        <div className="glass-panel rounded-2xl lg:col-span-2 overflow-hidden flex flex-col h-[500px]">
          <div className="p-6 border-b border-white/5 flex items-center space-x-3 bg-slate-900/40">
            <Activity className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-semibold">Recent Archives</h2>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-slate-400 text-sm border-b border-white/5">
                  <th className="pb-3 px-4 font-medium">Session ID</th>
                  <th className="pb-3 px-4 font-medium">Date & Time</th>
                  <th className="pb-3 px-4 font-medium">Transcript</th>
                  <th className="pb-3 px-4 font-medium">Note</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map(session => (
                  <tr key={session.id} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                    <td className="py-4 px-4 text-sm font-mono text-slate-300">{session.heidi_session_id}</td>
                    <td className="py-4 px-4 text-sm text-slate-400">
                      {session.session_date ? new Date(session.session_date).toLocaleDateString() : 'N/A'} {session.session_time || ''}
                    </td>
                    <td className="py-4 px-4">
                      {session.has_transcript 
                        ? <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Saved</span>
                        : <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">Missing</span>}
                    </td>
                    <td className="py-4 px-4">
                      {session.has_note 
                        ? <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Saved</span>
                        : <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">Missing</span>}
                    </td>
                  </tr>
                ))}
                {sessions.length === 0 && !loading && (
                  <tr>
                    <td colSpan={4} className="py-12 text-center text-slate-500">No sessions archived yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Live Scraper Logs */}
        <div className="glass-panel rounded-2xl overflow-hidden flex flex-col h-[500px]">
          <div className="p-6 border-b border-white/5 flex items-center space-x-3 bg-slate-900/40">
            <Terminal className="w-5 h-5 text-purple-400" />
            <h2 className="text-xl font-semibold flex-1">Live Console</h2>
            <span className="flex h-3 w-3 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
          </div>
          <div className="flex-1 bg-black/60 p-4 overflow-y-auto terminal-scroll font-mono text-sm shadow-inner">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic">Waiting for scraper activity...</div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="mb-2 break-words leading-relaxed">
                  <span className="text-slate-500 text-xs mr-3">
                    {new Date(log.ts).toLocaleTimeString([], { hour12: false })}
                  </span>
                  <span className={`font-semibold mr-3 text-xs ${getLogColor(log.level)}`}>
                    [{log.level || 'INFO'}]
                  </span>
                  <span className="text-slate-300">{log.msg}</span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>

      </div>
    </div>
  );
}
