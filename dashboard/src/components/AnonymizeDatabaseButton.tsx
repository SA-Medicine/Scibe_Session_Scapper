'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export function AnonymizeDatabaseButton() {
  const [isAnonymizing, setIsAnonymizing] = useState(false);
  const router = useRouter();

  const handleAnonymize = async () => {
    if (!window.confirm('Are you sure you want to anonymize PHI in the database? This action will replace real patient data with fake data and cannot be undone.')) {
      return;
    }

    setIsAnonymizing(true);
    try {
      const res = await fetch('/api/database/anonymize', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to anonymize database');
      }
      alert('Anonymization complete!');
      router.refresh();
    } catch (err: any) {
      alert(`Error anonymizing database:\n\n${err.message}`);
    } finally {
      setIsAnonymizing(false);
    }
  };

  return (
    <button
      onClick={handleAnonymize}
      disabled={isAnonymizing}
      className="text-xs px-3 py-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/50 transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      title="Anonymize PHI in the database"
    >
      {isAnonymizing ? 'Anonymizing...' : '🛡️ Anonymize Data'}
    </button>
  );
}
