import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

type ExportKind = 'sql' | 'json' | 'csv';

function candidateDirs(): string[] {
  const cwd = process.cwd();
  return [
    process.env.EXPORTS_DIR,          // explicit (docker: /app/exports)
    '/app/exports',                   // docker default mount point
    path.join(cwd, 'exports'),        // running from project root
    path.join(cwd, '..', 'exports'),  // running from ./dashboard
    path.join(cwd, '..', '..', 'exports'),
  ].filter(Boolean) as string[];
}

// Return the first candidate dir that exists and is readable, plus diagnostics.
function resolveDir(): { dir: string | null; tried: { path: string; error: string }[] } {
  const tried: { path: string; error: string }[] = [];
  for (const dir of candidateDirs()) {
    try {
      fs.readdirSync(dir);
      return { dir, tried };
    } catch (e: unknown) {
      const code = (e as NodeJS.ErrnoException)?.code || String(e);
      tried.push({ path: dir, error: code });
    }
  }
  return { dir: null, tried };
}

function kindFor(name: string): ExportKind | null {
  if (name.endsWith('.sql')) return 'sql';
  if (name.endsWith('.json')) return 'json';
  if (name.endsWith('.csv')) return 'csv';
  return null; // zips and everything else are intentionally excluded
}

export async function GET() {
  const { dir, tried } = resolveDir();
  if (!dir) {
    return NextResponse.json({ available: false, files: [], tried });
  }

  const files = fs
    .readdirSync(dir)
    .map((name) => {
      const kind = kindFor(name);
      if (!kind) return null;
      let size = 0;
      let mtime = 0;
      try {
        const stat = fs.statSync(path.join(dir, name));
        size = stat.size;
        mtime = stat.mtimeMs;
      } catch {
        return null;
      }
      const anonymized = name.includes('_anon') || name === 'all_sessions_anon.json';
      const containsPhi = /transcript|soap|note|session/i.test(name) && !anonymized;
      return { name, kind, size, mtime, anonymized, containsPhi };
    })
    .filter(Boolean);

  return NextResponse.json({ available: true, dir, files });
}
