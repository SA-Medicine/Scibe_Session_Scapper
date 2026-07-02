export const dynamic = 'force-dynamic';
import { PrismaClient } from '@prisma/client';
import { SessionsDataGrid } from '@/components/SessionsDataGrid';
import { ScraperConsole } from '@/components/ScraperConsole';
import { ClearDatabaseButton } from '@/components/ClearDatabaseButton';
import { AnonymizeDatabaseButton } from '@/components/AnonymizeDatabaseButton';
import type { SessionFull } from '@/components/SessionDetailPanel';

const prisma = new PrismaClient();

async function getStats() {
  const [totalSessions, totalPatients, totalTranscripts, totalNotes, totalFailed, recentAudit] = await Promise.all([
    prisma.session.count(),
    prisma.patient.count(),
    prisma.transcript.count(),
    prisma.note.count(),
    prisma.failedExtraction.count(),
    prisma.auditLog.findFirst({ orderBy: { started_at: 'desc' } }),
  ]);
  return { totalSessions, totalPatients, totalTranscripts, totalNotes, totalFailed, recentAudit };
}

async function getSessions(): Promise<SessionFull[]> {
  const rows = await prisma.session.findMany({
    orderBy: { session_date: 'desc' },
    include: {
      transcript: { select: { raw_text: true, clean_text: true, word_count: true, sha256: true } },
      note: { select: { soap_note: true, assessment: true, plan: true, summary: true } },
      artifacts: { select: { id: true, type: true, clipboard_capture: true, ocr_text: true, copy_button_text: true, rendered_text: true }, take: 5 },
      audits: { select: { id: true, status: true, validation_status: true, retries_used: true, error_message: true, started_at: true, completed_at: true }, orderBy: { started_at: 'desc' }, take: 5 },
    },
  });

  return rows.map(r => ({
    ...r,
    session_date: r.session_date ? r.session_date.toISOString() : null,
    session_time: r.session_time ? r.session_time.toISOString().slice(11, 19) : null,
    created_at: r.created_at.toISOString(),
    updated_at: r.updated_at.toISOString(),
    audits: r.audits.map(a => ({
      ...a,
      started_at: a.started_at.toISOString(),
      completed_at: a.completed_at?.toISOString() ?? null,
    })),
  })) as SessionFull[];
}

function StatCard({
  label, value, icon, color, sub,
}: { label: string; value: number; icon: string; color: string; sub?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-xl border border-[var(--color-surface-border)] bg-[var(--color-surface-2)] p-5 group hover:border-${color}-500/30 transition-all duration-200`}>
      <div className={`absolute inset-0 bg-gradient-to-br from-${color}-500/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity`} />
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-2">{label}</div>
          <div className={`text-4xl font-black text-${color}-400 leading-none`}>{value.toLocaleString()}</div>
          {sub && <div className="text-[10px] text-[var(--color-text-muted)] mt-2">{sub}</div>}
        </div>
        <div className={`text-3xl opacity-60`}>{icon}</div>
      </div>
    </div>
  );
}

export default async function DashboardHome() {
  const [stats, sessions] = await Promise.all([getStats(), getSessions()]);

  const lastRunAt = stats.recentAudit
    ? new Date(stats.recentAudit.started_at).toLocaleString('en-AU')
    : null;

  return (
    <div className="space-y-8 animate-slide-in-up">
      {/* Page header */}
      <div>
        <h1 className="text-3xl font-black tracking-tight text-[var(--color-text-primary)]">
          Session Archive Dashboard
        </h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          Heidi Health Scribe — Production Archival Platform
          {lastRunAt && <span className="ml-3 text-[var(--color-text-muted)]">· Last scrape: {lastRunAt}</span>}
        </p>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard label="Total Sessions" value={stats.totalSessions} icon="🗂️" color="blue"
          sub={`${stats.totalTranscripts} with transcripts`} />
        <StatCard label="Patients" value={stats.totalPatients} icon="👤" color="emerald" />
        <StatCard label="Transcripts" value={stats.totalTranscripts} icon="📝" color="violet"
          sub="Extracted & stored" />
        <StatCard label="SOAP Notes" value={stats.totalNotes} icon="🩺" color="cyan"
          sub="Clinical notes archived" />
        <StatCard label="Failed" value={stats.totalFailed} icon="⚠️" color="rose"
          sub="Check Audit Explorer" />
      </div>

      {/* Live scraper console */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-bold text-[var(--color-text-primary)]">Live Scraper Console</h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              Streams logs from the backend container in real time. Run with Docker or locally.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <code className="text-[10px] bg-[var(--color-surface-3)] px-2 py-1 rounded text-[var(--color-text-secondary)] border border-[var(--color-surface-border)]">
              docker-compose up backend
            </code>
            <span className="text-[var(--color-text-muted)] text-xs">or</span>
            <code className="text-[10px] bg-[var(--color-surface-3)] px-2 py-1 rounded text-[var(--color-text-secondary)] border border-[var(--color-surface-border)]">
              .\run_local.ps1
            </code>
          </div>
        </div>
        <ScraperConsole />
      </div>

      {/* Sessions grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-base font-bold text-[var(--color-text-primary)]">Session Database</h2>
            <p className="text-xs text-[var(--color-text-muted)]">
              All {sessions.length} archived sessions. Click any row to expand full details.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <AnonymizeDatabaseButton />
            <ClearDatabaseButton />
          </div>
        </div>
        <SessionsDataGrid data={sessions} />
      </div>
    </div>
  );
}
