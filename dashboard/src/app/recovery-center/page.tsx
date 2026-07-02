export const dynamic = 'force-dynamic';
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

export default async function RecoveryCenter() {
  const failedExtractions = await prisma.failedExtraction.findMany({
    orderBy: { last_attempt: 'desc' }
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight text-red-600">Recovery Center</h2>
        <p className="text-gray-500 dark:text-zinc-400">Manage and recover failed session extractions.</p>
      </div>

      <div className="rounded-md border bg-white dark:bg-zinc-900">
        <table className="w-full text-sm text-left">
          <thead className="text-xs uppercase bg-gray-50 dark:bg-zinc-800 border-b">
            <tr>
              <th className="px-6 py-3">Session ID</th>
              <th className="px-6 py-3">Failure Reason</th>
              <th className="px-6 py-3">Retry Count</th>
              <th className="px-6 py-3">Last Attempt</th>
              <th className="px-6 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {failedExtractions.map((failure) => (
              <tr key={failure.id} className="border-b dark:border-zinc-800">
                <td className="px-6 py-4 font-mono text-xs">{failure.session_id}</td>
                <td className="px-6 py-4 text-red-600 truncate max-w-xs" title={failure.failure_reason}>{failure.failure_reason}</td>
                <td className="px-6 py-4">{failure.retry_count}</td>
                <td className="px-6 py-4">{new Date(failure.last_attempt).toLocaleString()}</td>
                <td className="px-6 py-4">
                  <button className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded">
                    Reprocess
                  </button>
                </td>
              </tr>
            ))}
            {failedExtractions.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-gray-500">
                  <div className="flex flex-col items-center">
                    <span className="text-green-500 text-3xl mb-2">✓</span>
                    <p>No failed extractions to recover!</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

