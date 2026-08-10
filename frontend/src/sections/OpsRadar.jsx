// NB-57: Section 3 — Trust & Moderation → the Anomaly Radar (Rule 4).
// Computed problems with action chaining: every anomaly carries one-click
// verbs (retry / dismiss / clear-reports / pause / hide / ban-owner) and the
// endpoint comes from the backend's own actions array — the frontend never
// hard-codes a verb's path. Mutations are deliberate: every verb opens the
// shared confirm dialog (Rule 1.7). GET actions (e.g. "View item") render
// as links — never as fetches. Refreshes on load (Rule 4.3).

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsEmptyState from '../components/ops/OpsEmptyState';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';

const SEVERITY_STYLES = {
  high: 'bg-red-100 text-red-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-blue-100 text-blue-700',
};

const ACTION_STYLES = {
  default: 'rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700',
  danger: 'rounded bg-red-600 px-2 py-1 text-xs font-medium text-white hover:bg-red-700',
  link: 'rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50',
};

// Enforcement verbs are red; dismiss/retry are neutral blue.
const DANGER_VERBS = ['Ban owner', 'Hide item', 'Pause indexing', 'Clear reports'];

export default function OpsRadar({ setToast }) {
  const [radar, setRadar] = useState(null);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null); // {verb, endpoint, body}

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const load = useCallback(async () => {
    try {
      setError(null);
      setRadar(await opsFetch('/ops/radar'));
    } catch (err) {
      setError(err.message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runAction = async () => {
    const { verb, endpoint, body } = pending;
    try {
      await opsFetch(endpoint, {
        method: 'POST',
        ...(body !== undefined ? { body } : {}),
      });
      toast(`${verb} — done`);
      setPending(null);
      await load();
    } catch (err) {
      toast(err.message, 'error');
      setPending(null);
    }
  };

  const anomalies = radar?.anomalies ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Anomaly Radar</h2>
        <button
          type="button"
          onClick={load}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {!radar && !error ? (
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-400">
          Scanning… (each detection is a live query over the DB)
        </div>
      ) : anomalies.length === 0 ? (
        <OpsEmptyState
          title="No anomalies"
          hint="All five detections came back clean. Refresh to re-scan."
        />
      ) : (
        <div className="space-y-3">
          {anomalies.map((a, i) => (
            <div
              key={`${a.type}-${a.entity_id}-${i}`}
              className="rounded-lg border border-gray-200 bg-white p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-gray-700">{a.summary}</p>
                <span
                  className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium uppercase ${
                    SEVERITY_STYLES[a.severity] ?? SEVERITY_STYLES.medium
                  }`}
                >
                  {a.severity}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {a.actions.map((act, j) =>
                  act.method === 'GET' ? (
                    <a
                      key={j}
                      href={act.endpoint}
                      className={ACTION_STYLES.link}
                    >
                      {act.verb}
                    </a>
                  ) : (
                    <button
                      key={j}
                      type="button"
                      onClick={() =>
                        setPending({
                          verb: act.verb,
                          endpoint: act.endpoint,
                          body:
                            act.endpoint === '/ops/radar/resolve'
                              ? { type: a.type, entity_id: a.entity_id }
                              : undefined,
                        })
                      }
                      className={ACTION_STYLES[DANGER_VERBS.includes(act.verb) ? 'danger' : 'default']}
                    >
                      {act.verb}
                    </button>
                  ),
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <OpsConfirmDialog
        open={pending !== null}
        title={pending?.verb ?? ''}
        message={
          pending
            ? `Run "${pending.verb}"? The action is audited and the radar refreshes when it completes.`
            : ''
        }
        confirmLabel={pending?.verb ?? 'Confirm'}
        danger={DANGER_VERBS.includes(pending?.verb)}
        onConfirm={runAction}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
