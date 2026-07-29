import React from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * Reusable status badge for inventory management.
 * Shows nothing when status is "active" and not paused.
 */
const StatusBadge = ({ status, indexingPaused }) => {
  // No badge for active items when indexing is not paused
  if (status === 'active' && !indexingPaused) {
    return null;
  }

  // Indexing paused takes priority
  if (indexingPaused) {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700">
        Paused
      </span>
    );
  }

  if (status === 'sold') {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-700">
        Sold
      </span>
    );
  }

  if (status === 'reported_sold') {
    return (
      <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-700 flex items-center gap-1">
        <AlertTriangle size={10} />
        Reported
      </span>
    );
  }

  return null;
};

export default StatusBadge;
