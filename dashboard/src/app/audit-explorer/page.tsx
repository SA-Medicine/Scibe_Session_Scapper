export const dynamic = 'force-dynamic';
import { PrismaClient } from '@prisma/client'
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

const prisma = new PrismaClient()

function cn(...inputs: string[]) {
  return twMerge(clsx(inputs));
}

export default async function AuditExplorer() {
  const audits = await prisma.auditLog.findMany({
    orderBy: { started_at: 'desc' },
    take: 50,
    include: { session: true }
  })

  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      <div>
        <h2 className="text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-zinc-100 to-zinc-500">Audit Explorer</h2>
        <p className="text-zinc-400 mt-2 font-medium">View detailed extraction metrics, validation status, and retries.</p>
      </div>

      <div className="w-full overflow-hidden rounded-xl border border-glass-border bg-glass-bg shadow-2xl backdrop-blur-md">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="bg-zinc-900/50 text-xs uppercase text-zinc-400">
              <tr className="border-b border-zinc-800">
                <th className="px-6 py-4">Session ID</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Validation</th>
                <th className="px-6 py-4 text-center">Retries</th>
                <th className="px-6 py-4">Started At</th>
                <th className="px-6 py-4">Completed At</th>
                <th className="px-6 py-4">Error</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/50">
              {audits.map((audit) => (
                <tr key={audit.id} className="hover:bg-zinc-800/30 transition-colors duration-200">
                  <td className="px-6 py-4 font-mono text-xs text-blue-400">{audit.session?.heidi_session_id || 'Unknown'}</td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className={cn(
                      "inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset",
                      audit.status === 'success' ? 'bg-emerald-400/10 text-emerald-400 ring-emerald-400/20' : 
                      audit.status === 'failed' ? 'bg-rose-400/10 text-rose-400 ring-rose-400/20' : 
                      'bg-amber-400/10 text-amber-400 ring-amber-400/20'
                    )}>
                      {audit.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    {audit.validation_status ? (
                      <span className={cn(
                        "inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset",
                        audit.validation_status === 'passed' ? 'bg-emerald-400/10 text-emerald-400 ring-emerald-400/20' : 'bg-amber-400/10 text-amber-400 ring-amber-400/20'
                      )}>
                        {audit.validation_status}
                      </span>
                    ) : (
                      <span className="text-zinc-500">-</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-center text-zinc-300">{audit.retries_used}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-zinc-300">{new Date(audit.started_at).toLocaleString()}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-zinc-300">{audit.completed_at ? new Date(audit.completed_at).toLocaleString() : '-'}</td>
                  <td className="px-6 py-4 text-rose-400 text-xs truncate max-w-xs" title={audit.error_message || ''}>{audit.error_message || '-'}</td>
                </tr>
              ))}
              {audits.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center text-zinc-500">
                    No audits found. Run the scraper to generate logs!
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="p-4 border-t border-zinc-800 bg-zinc-900/30 text-xs text-zinc-500 flex justify-between items-center">
          <div>Showing {audits.length} logs</div>
        </div>
      </div>
    </div>
  )
}
