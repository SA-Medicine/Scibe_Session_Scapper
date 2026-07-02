'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export function ClearDatabaseButton() {
  const [isDeleting, setIsDeleting] = useState(false);
  const router = useRouter();

  const handleClear = async () => {
    if (!window.confirm('Are you sure you want to completely wipe the entire database? This action cannot be undone.')) {
      return;
    }

    setIsDeleting(true);
    try {
      const res = await fetch('/api/database/clear', { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to clear database');
      }
      router.refresh();
    } catch (err: any) {
      alert(`Error clearing database: ${err.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <button
      onClick={handleClear}
      disabled={isDeleting}
      className="text-xs px-3 py-1.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:border-red-500/50 transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      title="Delete all sessions and related data"
    >
      {isDeleting ? 'Deleting...' : '🗑 Clear Database'}
    </button>
  );
}
