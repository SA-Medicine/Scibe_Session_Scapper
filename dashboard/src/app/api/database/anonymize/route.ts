import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import util from 'util';

const execPromise = util.promisify(exec);

export async function POST() {
  try {
    const isWindows = process.platform === 'win32';
    const pythonCmd = isWindows ? '.venv\\Scripts\\python' : '.venv/bin/python';
    // Fallback to global python if venv python fails
    const cmd = `cd ../backend/heidi_exporter && (${pythonCmd} main.py --anonymize-db || python main.py --anonymize-db)`;
    
    const { stdout, stderr } = await execPromise(cmd);

    return NextResponse.json({ success: true, log: stdout });
  } catch (error: any) {
    console.error('Failed to anonymize database:', error);
    return NextResponse.json({ 
        error: `Could not run python automatically (are you running in Docker?). Please run this command manually in your terminal: docker-compose run --rm backend python main.py --anonymize-db` 
    }, { status: 500 });
  }
}
