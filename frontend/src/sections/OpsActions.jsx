// NB-59: Actions sub-view — engine verbs: re-run, retry, trigger (Rule 6).
// Three action cards, each with its own confirm dialog and result feedback
// (result payload rendered when the verb returns one). Dropped verbs are
// documented as disabled copy — honest v1 (blueprint §5.1): re-processing
// an ingestion post has no persisted payload (the listener queue is
// in-memory), and triggering photo-refresh has no backend→listener command
// seam (the refresher runs inside the listener).

import { useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';

const DROPPED_VERBS = [
  {
    title: 'Re-process an ingestion post',
    copy: 'Not available — the listener queue is in-memory (asyncio.Queue) and no persisted Telegram post exists in the DB, so there is nothing to re-process. Re-post the item instead.',
  },
  {
    title: 'Trigger photo refresh',
    copy: 'Not available — the refresher runs inside the listener and the only backend→listener signal is the one-way heartbeat. Restart the listener to refresh photos.',
  },
];

function ActionCard({ title, copy, children, dropped = false }) {
  return (
    <div className={`rounded-lg border bg-white p-4 ${dropped ? 'border-dashed border-gray-300 opacity-70' : 'border-gray-200'}`}>
      <div className="font-medium text-gray-800">{title}</div>
      <p className="mt-1 text-xs text-gray-500">{copy}</p>
      {dropped ? (
        <div className="mt-3 rounded bg-gray-100 px-3 py-2 text-xs text-gray-500">
          Dropped from v1 — documented in the ops-finalization blueprint §5.1.
        </div>
      ) : (
        <div className="mt-3">{children}</div>
      )}
    </div>
  );
}

export default function OpsActions({ setToast }) {
  const [reprocessId, setReprocessId] = useState('');
  const [retryId, setRetryId] = useState('');
  const [pending, setPending] = useState(null); // {label, verb, run}
  const [result, setResult] = useState(null); // {label, payload} from the last verb

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const confirm = (label, verb, run) => setPending({ label, verb, run });

  const runVerb = async () => {
    try {
      const payload = await pending.run();
      setResult({ label: pending.label, payload });
      toast(`${pending.verb} — done`);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setPending(null);
    }
  };

  const requireId = (raw, what) => {
    if (!raw.trim() || !/^\d+$/.test(raw.trim())) {
      toast(`Enter a numeric ${what} id`, 'error');
      return null;
    }
    return raw.trim();
  };

  return (
    <div className="space-y-4">
      <ActionCard
        title="Re-run the alert pipeline for an item"
        copy="Runs the same pipeline the ingestion path runs — matches, judge, dispatch, guardrails. Idempotent by design: duplicate suppression and the throttle guard re-dispatch."
      >
        <div className="flex items-center gap-2">
          <input
            value={reprocessId}
            onChange={(e) => setReprocessId(e.target.value)}
            placeholder="Item id"
            className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            onClick={() => {
              const id = requireId(reprocessId, 'item');
              if (!id) return;
              confirm(
                'Re-process item',
                'Reprocess',
                () => opsFetch(`/ops/actions/items/${id}/reprocess`, { method: 'POST' }),
              );
            }}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
          >
            Reprocess
          </button>
        </div>
      </ActionCard>

      <ActionCard
        title="Retry a failed notification"
        copy="Flips FAILED → PENDING; the listener poller picks it up on its next pass. The radar's dead-chat action uses this same shared verb."
      >
        <div className="flex items-center gap-2">
          <input
            value={retryId}
            onChange={(e) => setRetryId(e.target.value)}
            placeholder="Notification id"
            className="w-40 rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            onClick={() => {
              const id = requireId(retryId, 'notification');
              if (!id) return;
              confirm(
                'Retry notification',
                'Retry',
                () => opsFetch(`/ops/actions/notifications/${id}/retry`, { method: 'POST' }),
              );
            }}
            className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </ActionCard>

      <ActionCard
        title="Run the Star-payments reconciliation now"
        copy="Fetches recent Star transactions and replays unfulfilled ones (boosts + subscriptions). Records the scheduler run and the audit row."
      >
        <button
          type="button"
          onClick={() =>
            confirm(
              'Run reconciliation',
              'Reconcile',
              () => opsFetch('/ops/actions/reconcile', { method: 'POST' }),
            )
          }
          className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700"
        >
          Reconcile now
        </button>
      </ActionCard>

      {DROPPED_VERBS.map((v) => (
        <ActionCard key={v.title} title={v.title} copy={v.copy} dropped />
      ))}

      {result && (
        <div
          className="rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-gray-700"
          data-testid="action-result"
        >
          <span className="font-medium">{result.label}:</span>{' '}
          <code className="text-xs">{JSON.stringify(result.payload)}</code>
        </div>
      )}

      <OpsConfirmDialog
        open={pending !== null}
        title={pending?.label ?? ''}
        message={`Run "${pending?.verb}"? The action is audited.`}
        confirmLabel={pending?.verb ?? 'Confirm'}
        onConfirm={runVerb}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
