import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

function candidateDirs(): string[] {
  const cwd = process.cwd();
  return [
    process.env.EXPORTS_DIR,
    '/app/exports',
    path.join(cwd, 'exports'),
    path.join(cwd, '..', 'exports'),
    path.join(cwd, '..', '..', 'exports'),
  ].filter(Boolean) as string[];
}

const MIME: Record<string, string> = {
  '.sql': 'application/sql',
  '.json': 'application/json',
  '.csv': 'text/csv',
};

export async function GET(req: NextRequest) {
  const requested = req.nextUrl.searchParams.get('file') || '';
  // Hard guard against path traversal: only a bare filename is ever allowed.
  const name = path.basename(requested);
  if (!name || name !== requested) {
    return NextResponse.json({ error: 'Invalid file name' }, { status: 400 });
  }
  const ext = path.extname(name);
  if (!(ext in MIME)) {
    return NextResponse.json({ error: 'Unsupported file type' }, { status: 400 });
  }

  let filePath: string | null = null;
  for (const dir of candidateDirs()) {
    const candidate = path.join(dir, name);
    if (fs.existsSync(candidate)) {
      filePath = candidate;
      break;
    }
  }
  if (!filePath) {
    return NextResponse.json({ error: 'File not found' }, { status: 404 });
  }

  const data = fs.readFileSync(filePath);
  return new NextResponse(new Uint8Array(data), {
    headers: {
      'Content-Type': MIME[ext],
      'Content-Disposition': `attachment; filename="${name}"`,
      'Content-Length': String(data.length),
      'Cache-Control': 'no-store',
    },
  });
}
