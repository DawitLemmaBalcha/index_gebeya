// NB-58: Diagnostics sub-view — per-item decision traces (Rule 5).
// Item id input → the side-effect-free pipeline replay: every per-alert
// stage as data (expiry, price gate, match, judge, dispatch decision,
// throttle, dedup). Drill-down on a stage shows the full reason. The
// trace NEVER dispatches — it only replays the pipeline's decisions.

import { useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';

const OUTCOME_STYLES = {
  dispatched: 'bg-green-100 text-green-700',
  speed_pass: 'bg-green-100 text-green-700',
  threshold_miss: 'bg-gray-100 text-gray-500',
  price_gate: 'bg-gray-100 text-gray-500',
  expired: 'bg-gray-100 text-gray-500',
  judge_rejected: 'bg-amber-100 text-amber-700',
  judge_errored: 'bg-amber-100 text-amber-700',
  unknown_verdict: 'bg-amber-100 text-amber-700',
  high_water_suppressed: 'bg-blue-100 text-blue-700',
  throttled: 'bg-blue-100 text-blue-700',
  dedup_suppressed: 'bg-blue-100 text-blue-700',
};

export default function OpsDiagnostics({ setToast }) {
  const [itemId, setItemId] = useState('');
  const [trace, setTrace] = useState(null);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [openStage, setOpenStage] = useState(null); // index of the drilled stage

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const run = async (e) => {
    e?.preventDefault();
    const id = itemId.trim();
    if (!id || !/^\d+$/.test(id)) {
      toast('Enter a numeric item id', 'error');
      return;
    }
    setBusy(true);
    setTrace(null);
    setSearched(false);
    setOpenStage(null);
    try {
      setTrace(await opsFetch(`/ops/diagnostics/items/${id}/trace`));
      setSearched(true);
    } catch (err) {
      setSearched(true);
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const stages = trace?.stages ?? [];

  return (
    <div className="space-y-4">
      <form onSubmit={run} className="flex items-center gap-2">
        <input
          value={itemId}
          onChange={(e) => setItemId(e.target.value)}
          placeholder="Item id"
          className="w-48 rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? 'Tracing…' : 'Trace item'}
        </button>
      </form>
      <p className="text-xs text-gray-400">
        Read-only replay of the alert pipeline for one item — the trace never
        dispatches, never writes counters, never commits. The LLM judge call
        is the only external side effect.
      </p>

      {searched && !trace && (
        <OpsEmptyState title="Item not found" hint="No items row has this id." />
      )}

      {trace && (
        <div className="space-y-4">
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>
              Item <span className="font-medium text-gray-800">#{trace.item_id}</span>
            </span>
            <span>
              {trace.alerts_evaluated} alert{trace.alerts_evaluated === 1 ? '' : 's'} evaluated
            </span>
            <span className="text-gray-300">·</span>
            <span>generated {new Date(trace.generated_at).toLocaleString()}</span>
          </div>

          {stages.length === 0 ? (
            <OpsEmptyState title="No active alerts" hint="No active alerts exist to evaluate." />
          ) : (
            <div className="space-y-2">
              <OpsTable
                columns={[
                  { key: 'alert_id', label: 'Alert' },
                  { key: 'query_text', label: 'Query' },
                  {
                    key: 'outcome',
                    label: 'Outcome',
                    render: (r) => (
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-medium ${
                          OUTCOME_STYLES[r.outcome] ?? 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {r.outcome}
                      </span>
                    ),
                  },
                  { key: 'score', label: 'Score', render: (r) => r.score ?? '—' },
                  { key: 'tier', label: 'Tier', render: (r) => r.tier ?? '—' },
                ]}
                data={stages}
              />
              <div className="flex gap-2">
                {stages.map((s, i) => (
                  <button
                    key={s.alert_id}
                    type="button"
                    onClick={() => setOpenStage(openStage === i ? null : i)}
                    className={`rounded border px-2 py-1 text-xs ${
                      openStage === i
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : 'border-gray-300 bg-white text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Alert #{s.alert_id}
                  </button>
                ))}
              </div>
              {openStage !== null && stages[openStage] && (
                <div
                  className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-gray-700"
                  data-testid="trace-drill-down"
                >
                  <span className="font-medium">Alert #{stages[openStage].alert_id}:</span>{' '}
                  {stages[openStage].reason}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
