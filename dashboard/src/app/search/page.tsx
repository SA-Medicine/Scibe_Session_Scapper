export const dynamic = 'force-dynamic';
import { PrismaClient } from '@prisma/client'
import { SearchIcon } from 'lucide-react'

const prisma = new PrismaClient()

export default async function SearchPage() {
  // In a real application, this would fetch from an API route using pgvector
  // e.g. await prisma.$queryRaw`SELECT * FROM transcripts ORDER BY embedding <-> ${embedding} LIMIT 5`
  
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold tracking-tight">Hybrid Semantic Search</h2>
        <p className="text-gray-500 dark:text-zinc-400">Search using PostgreSQL Full Text and pgvector semantic embeddings.</p>
      </div>

      <div className="max-w-2xl">
        <div className="relative">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <SearchIcon className="h-5 w-5 text-gray-400" />
          </div>
          <input 
            type="text" 
            className="block w-full pl-10 pr-3 py-3 border border-gray-300 dark:border-zinc-700 rounded-md leading-5 bg-white dark:bg-zinc-900 placeholder-gray-500 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm" 
            placeholder="Search for 'headache patients' or 'confusion cases'..." 
          />
          <button className="absolute inset-y-0 right-0 px-4 text-sm font-medium text-white bg-blue-600 rounded-r-md hover:bg-blue-700">
            Search
          </button>
        </div>
      </div>

      <div className="mt-8">
        <h3 className="text-lg font-medium mb-4">Search Results</h3>
        <div className="rounded-md border bg-white dark:bg-zinc-900 p-8 text-center text-gray-500">
          Enter a search query to see full-text and semantic search results across Transcripts and SOAP notes.
        </div>
      </div>
    </div>
  )
}

