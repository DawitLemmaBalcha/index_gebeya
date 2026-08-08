// NB-49: shared toast — transient result feedback for console actions.

import { useEffect } from 'react';

export default function OpsToast({ message, type = 'success', onDismiss }) {
  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(onDismiss, 4000);
    return () => clearTimeout(t);
  }, [message, onDismiss]);

  if (!message) return null;
  const styles =
    type === 'error'
      ? 'bg-red-600'
      : type === 'warn'
        ? 'bg-amber-500'
        : 'bg-emerald-600';
  return (
    <div
      className={`fixed bottom-4 right-4 z-50 rounded-md ${styles} px-4 py-2 text-sm text-white shadow-lg`}
      data-testid="ops-toast"
    >
      {message}
      <button
        type="button"
        onClick={onDismiss}
        className="ml-3 text-white/70 hover:text-white"
        aria-label="dismiss"
      >
        ✕
      </button>
    </div>
  );
}
