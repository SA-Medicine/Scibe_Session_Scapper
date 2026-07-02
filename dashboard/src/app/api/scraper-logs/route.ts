import { NextRequest } from 'next/server';
import fs from 'fs';
import path from 'path';
import readline from 'readline';

// Path where the Docker backend writes its structured JSON log lines
// This is mounted as a read-only volume in docker-compose.yml
const JSONL_LOG_PATH = '/scraper-logs/heidi_exporter.jsonl';
// Fallback for local Windows dev (adjust path as needed)
const FALLBACK_LOG_PATH = path.join(process.cwd(), '..', 'backend', 'heidi_exporter', 'logs', 'heidi_exporter.jsonl');

function getLogPath(): string {
  if (fs.existsSync(JSONL_LOG_PATH)) return JSONL_LOG_PATH;
  if (fs.existsSync(FALLBACK_LOG_PATH)) return FALLBACK_LOG_PATH;
  return JSONL_LOG_PATH; // Will gracefully handle missing below
}

export async function GET(req: NextRequest) {
  const encoder = new TextEncoder();
  
  const stream = new ReadableStream({
    async start(controller) {
      const logPath = getLogPath();

      const send = (data: object) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      // Send initial connection message
      send({ type: 'connected', ts: Date.now(), msg: 'Live log stream connected' });

      // If log file doesn't exist yet, poll until it appears
      let attempts = 0;
      while (!fs.existsSync(logPath) && attempts < 60) {
        await new Promise(r => setTimeout(r, 2000));
        send({ type: 'waiting', ts: Date.now(), msg: 'Waiting for scraper to start...' });
        attempts++;
      }

      if (!fs.existsSync(logPath)) {
        send({ type: 'error', ts: Date.now(), msg: 'Log file not found. Is the scraper running?' });
        controller.close();
        return;
      }

      // Tail the last 100 lines to catch up on history
      try {
        const content = fs.readFileSync(logPath, 'utf-8');
        const lines = content.trim().split('\n').filter(Boolean);
        const history = lines.slice(-100);
        for (const line of history) {
          try {
            const parsed = JSON.parse(line);
            send({ type: 'log', ...parsed, historical: true });
          } catch { /* skip malformed lines */ }
        }
      } catch { /* file may not be readable yet */ }

      // Watch for new lines using a polling approach (compatible with Docker volumes)
      let lastSize = 0;
      try { lastSize = fs.statSync(logPath).size; } catch { lastSize = 0; }
      let buffer = '';

      const poll = async () => {
        try {
          const stat = fs.statSync(logPath);
          if (stat.size > lastSize) {
            const fd = fs.openSync(logPath, 'r');
            const chunkSize = stat.size - lastSize;
            const chunk = Buffer.alloc(chunkSize);
            fs.readSync(fd, chunk, 0, chunkSize, lastSize);
            fs.closeSync(fd);
            lastSize = stat.size;
            buffer += chunk.toString('utf-8');

            const newlineIdx = buffer.lastIndexOf('\n');
            if (newlineIdx >= 0) {
              const toProcess = buffer.slice(0, newlineIdx + 1);
              buffer = buffer.slice(newlineIdx + 1);
              for (const line of toProcess.split('\n').filter(Boolean)) {
                try {
                  const parsed = JSON.parse(line);
                  send({ type: 'log', ...parsed });
                } catch { /* skip malformed */ }
              }
            }
          }
        } catch { /* log file may have been rotated */ }
      };

      const interval = setInterval(poll, 500);

      // Keep alive ping every 25s
      const keepAlive = setInterval(() => {
        try {
          controller.enqueue(encoder.encode(': ping\n\n'));
        } catch {
          clearInterval(interval);
          clearInterval(keepAlive);
        }
      }, 25000);

      // Cleanup on disconnect
      req.signal.addEventListener('abort', () => {
        clearInterval(interval);
        clearInterval(keepAlive);
        controller.close();
      });
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
