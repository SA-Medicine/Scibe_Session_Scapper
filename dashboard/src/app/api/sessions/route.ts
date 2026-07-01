import { NextResponse } from 'next/server';
import { query } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    // Get total statistics
    const statsResult = await query(`
      SELECT 
        (SELECT COUNT(*) FROM sessions) as total_sessions,
        (SELECT COUNT(*) FROM transcripts) as total_transcripts,
        (SELECT COUNT(*) FROM notes) as total_notes
    `);

    // Get 10 most recent sessions
    const recentSessionsResult = await query(`
      SELECT s.id, s.heidi_session_id, s.session_date, s.session_time, 
             t.id as transcript_id, n.id as note_id,
             (CASE WHEN t.id IS NOT NULL THEN true ELSE false END) as has_transcript,
             (CASE WHEN n.id IS NOT NULL THEN true ELSE false END) as has_note
      FROM sessions s
      LEFT JOIN transcripts t ON s.id = t.session_id
      LEFT JOIN notes n ON s.id = n.session_id
      ORDER BY s.created_at DESC
      LIMIT 10
    `);

    return NextResponse.json({
      success: true,
      stats: statsResult.rows[0],
      recentSessions: recentSessionsResult.rows
    });
  } catch (error: any) {
    console.error('Error fetching sessions:', error);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
