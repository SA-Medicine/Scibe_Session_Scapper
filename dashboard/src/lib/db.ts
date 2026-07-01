import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://heidi_user:heidi_pass@localhost:5432/heidi_archive?schema=public',
});

export const query = (text: string, params?: any[]) => pool.query(text, params);
