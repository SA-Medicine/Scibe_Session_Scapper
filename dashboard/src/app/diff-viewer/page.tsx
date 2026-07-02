export const dynamic = 'force-dynamic';
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()

export default async function DiffViewer() {
  const artifacts = await prisma.artifact.findMany({
    where: { type: 'transcript' },
    take: 10,
    orderBy: { created_at: 'desc' },
    include: { session: true }
  })

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Session Diff Viewer</h2>
        <p className="text-gray-500 dark:text-zinc-400">Compare extraction methods for each session.</p>
      </div>

      <div className="space-y-4">
        {artifacts.map((artifact) => (
          <div key={artifact.id} className="rounded-md border bg-white dark:bg-zinc-900 p-6">
            <h3 className="text-lg font-medium mb-2">Session: {artifact.session?.heidi_session_id}</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 text-sm">
              <div className="border p-3 rounded-md bg-gray-50 dark:bg-zinc-950">
                <span className="font-bold block mb-1">Copy Button</span>
                {artifact.copy_button_text ? <span className="text-green-600">Extracted</span> : <span className="text-gray-400">Missing</span>}
              </div>
              <div className="border p-3 rounded-md bg-gray-50 dark:bg-zinc-950">
                <span className="font-bold block mb-1">Clipboard</span>
                {artifact.clipboard_capture ? <span className="text-green-600">Extracted</span> : <span className="text-gray-400">Missing</span>}
              </div>
              <div className="border p-3 rounded-md bg-gray-50 dark:bg-zinc-950">
                <span className="font-bold block mb-1">DOM Extraction</span>
                {artifact.dom_text ? <span className="text-green-600">Extracted</span> : <span className="text-gray-400">Missing</span>}
              </div>
              <div className="border p-3 rounded-md bg-gray-50 dark:bg-zinc-950">
                <span className="font-bold block mb-1">OCR Fallback</span>
                {artifact.ocr_text ? <span className="text-green-600">Extracted</span> : <span className="text-gray-400">Missing</span>}
              </div>
            </div>
            <div className="mt-4">
              <button className="px-4 py-2 bg-zinc-800 text-white rounded-md text-sm hover:bg-zinc-700">
                View Full Diffs
              </button>
            </div>
          </div>
        ))}
        {artifacts.length === 0 && (
          <div className="p-8 text-center text-gray-500 border rounded-md">
            No session artifacts available yet.
          </div>
        )}
      </div>
    </div>
  )
}

