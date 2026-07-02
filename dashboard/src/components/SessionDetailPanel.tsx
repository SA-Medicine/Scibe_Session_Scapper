'use client';

import { useState } from 'react';

export type SessionFull = {
  id: number;
  heidi_session_id: string;
  patient_name_fallback: string | null;
  session_title: string | null;
  subtitle: string | null;
  session_date: string | null;
  session_time: string | null;
  language: string | null;
  duration: string | null;
  internal_identifier: string | null;
  source_url: string | null;
  created_at: string;
  transcript?: { raw_text: string | null; clean_text: string | null; word_count: number | null; sha256: string } | null;
  note?: { soap_note: string | null; assessment: string | null; plan: string | null; summary: string | null } | null;
  artifacts?: Array<{ id: number; type: string; clipboard_capture: string | null; ocr_text: string | null; copy_button_text: string | null; rendered_text: string | null }>;
  audits?: Array<{ id: number; status: string; validation_status: string | null; retries_used: number; error_message: string | null; started_at: string; completed_at: string | null }>;
};

const TABS = ['Overview', 'Transcript', 'SOAP Note', 'Artifacts', 'Audit Log'] as const;
type Tab = typeof TABS[number];

function Field({ label, value, mono = false, full = false }: { label: string; value: string | number | null | undefined; mono?: boolean; full?: boolean }) {
  return (
    <div className={full ? 'col-span-2' : ''}>
      <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-0.5">{label}</div>
      <div className={`text-sm text-[var(--color-text-primary)] break-all ${mono ? 'font-mono text-xs' : ''}`}>
        {value ?? <span className="text-[var(--color-text-muted)] italic">—</span>}
      </div>
    </div>
  );
}

export function SessionDetailPanel({ session, onClose }: { session: SessionFull; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('Overview');

  return (
    <div className="glass rounded-xl border border-[var(--color-brand-600)]/30 animate-slide-in-up overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-surface-border)] bg-[var(--color-surface-2)]">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-[var(--color-brand-500)]" />
          <span className="font-mono text-xs text-[var(--color-brand-400)]">
            {session.heidi_session_id}
          </span>
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">
            {session.session_title || session.patient_name_fallback || 'Unnamed Session'}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--color-text-muted)] hover:text-rose-400 transition-colors text-lg leading-none px-1"
        >
          ×
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-[var(--color-surface-border)] bg-[var(--color-surface-1)]">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={[
              'px-4 py-2 text-xs font-semibold transition-all border-b-2 -mb-px',
              tab === t
                ? 'border-[var(--color-brand-500)] text-[var(--color-brand-400)]'
                : 'border-transparent text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]',
            ].join(' ')}
          >
            {t}
            {t === 'Transcript' && session.transcript && (
              <span className="ml-1.5 badge badge-info">{session.transcript.word_count ?? '?'}w</span>
            )}
            {t === 'Artifacts' && session.artifacts && session.artifacts.length > 0 && (
              <span className="ml-1.5 badge badge-neutral">{session.artifacts.length}</span>
            )}
            {t === 'Audit Log' && session.audits && session.audits.length > 0 && (
              <span className="ml-1.5 badge badge-neutral">{session.audits.length}</span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-5 overflow-y-auto" style={{ maxHeight: 380 }}>
        {tab === 'Overview' && (
          <div className="grid grid-cols-2 gap-x-8 gap-y-4">
            <Field label="Database ID" value={session.id} />
            <Field label="Heidi Session ID" value={session.heidi_session_id} mono />
            <Field label="Patient Name" value={session.patient_name_fallback} />
            <Field label="Session Title" value={session.session_title} />
            <Field label="Subtitle" value={session.subtitle} />
            <Field label="Date" value={session.session_date ? new Date(session.session_date).toLocaleDateString('en-AU', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }) : null} />
            <Field label="Time" value={session.session_time ? new Date(`1970-01-01T${session.session_time}`).toLocaleTimeString('en-AU') : null} />
            <Field label="Duration" value={session.duration} />
            <Field label="Language" value={session.language} />
            <Field label="Internal ID" value={session.internal_identifier} mono />
            <Field label="Archived At" value={new Date(session.created_at).toLocaleString('en-AU')} />
            {session.source_url && (
              <div className="col-span-2">
                <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-0.5">Source URL</div>
                <a href={session.source_url} target="_blank" rel="noopener noreferrer"
                   className="text-xs font-mono text-[var(--color-brand-400)] hover:underline break-all">
                  {session.source_url}
                </a>
              </div>
            )}
          </div>
        )}

        {tab === 'Transcript' && (
          <div className="space-y-3">
            {session.transcript ? (
              <>
                <div className="flex items-center gap-4 text-xs text-[var(--color-text-muted)]">
                  <span>{session.transcript.word_count ?? 0} words</span>
                  <span className="font-mono">SHA256: {session.transcript.sha256.slice(0, 16)}…</span>
                </div>
                <pre className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-secondary)] bg-[var(--color-surface-0)] rounded-lg p-4 overflow-y-auto max-h-60 font-mono border border-[var(--color-surface-border)]">
                  {session.transcript.clean_text || session.transcript.raw_text || '(empty)'}
                </pre>
              </>
            ) : (
              <div className="text-[var(--color-text-muted)] text-center py-8 text-sm">
                No transcript available for this session.
              </div>
            )}
          </div>
        )}

        {tab === 'SOAP Note' && (
          <div className="space-y-4">
            {session.note ? (
              <>
                {session.note.soap_note && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-brand-400)] mb-2">Full SOAP Note</div>
                    <pre className="whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-text-secondary)] bg-[var(--color-surface-0)] rounded-lg p-4 overflow-y-auto max-h-48 font-mono border border-[var(--color-surface-border)]">
                      {session.note.soap_note}
                    </pre>
                  </div>
                )}
                {session.note.assessment && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-amber-400 mb-1">Assessment</div>
                    <p className="text-xs text-[var(--color-text-secondary)]">{session.note.assessment}</p>
                  </div>
                )}
                {session.note.plan && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-emerald-400 mb-1">Plan</div>
                    <p className="text-xs text-[var(--color-text-secondary)]">{session.note.plan}</p>
                  </div>
                )}
                {session.note.summary && (
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-widest text-[var(--color-text-muted)] mb-1">Summary</div>
                    <p className="text-xs text-[var(--color-text-secondary)]">{session.note.summary}</p>
                  </div>
                )}
              </>
            ) : (
              <div className="text-[var(--color-text-muted)] text-center py-8 text-sm">
                No SOAP note available for this session.
              </div>
            )}
          </div>
        )}

        {tab === 'Artifacts' && (
          <div className="space-y-3">
            {session.artifacts && session.artifacts.length > 0 ? (
              session.artifacts.map(a => (
                <div key={a.id} className="rounded-lg border border-[var(--color-surface-border)] p-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="badge badge-info">{a.type}</span>
                    <span className="text-[10px] text-[var(--color-text-muted)]">ID: {a.id}</span>
                  </div>
                  {a.clipboard_capture && <pre className="text-xs font-mono text-[var(--color-text-secondary)] bg-[var(--color-surface-0)] rounded p-2 overflow-x-auto whitespace-pre-wrap max-h-32">{a.clipboard_capture.slice(0, 500)}</pre>}
                  {a.copy_button_text && !a.clipboard_capture && <pre className="text-xs font-mono text-[var(--color-text-secondary)] bg-[var(--color-surface-0)] rounded p-2 overflow-x-auto whitespace-pre-wrap max-h-32">{a.copy_button_text.slice(0, 500)}</pre>}
                  {a.ocr_text && <div className="text-[10px] text-[var(--color-text-muted)]">OCR: {a.ocr_text.slice(0, 100)}…</div>}
                </div>
              ))
            ) : (
              <div className="text-[var(--color-text-muted)] text-center py-8 text-sm">No artifacts captured.</div>
            )}
          </div>
        )}

        {tab === 'Audit Log' && (
          <div className="space-y-2">
            {session.audits && session.audits.length > 0 ? (
              session.audits.map(a => (
                <div key={a.id} className="flex items-start gap-3 rounded-lg border border-[var(--color-surface-border)] p-3">
                  <span className={`badge ${a.status === 'success' ? 'badge-success' : a.status === 'failed' ? 'badge-danger' : 'badge-warning'}`}>
                    {a.status}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                      <span>Started: {new Date(a.started_at).toLocaleString('en-AU')}</span>
                      {a.completed_at && <span>Ended: {new Date(a.completed_at).toLocaleString('en-AU')}</span>}
                      <span>Retries: {a.retries_used}</span>
                      {a.validation_status && <span className={`badge ${a.validation_status === 'passed' ? 'badge-success' : 'badge-warning'}`}>{a.validation_status}</span>}
                    </div>
                    {a.error_message && (
                      <div className="mt-1 text-xs text-rose-400 font-mono break-all">{a.error_message}</div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-[var(--color-text-muted)] text-center py-8 text-sm">No audit entries.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
