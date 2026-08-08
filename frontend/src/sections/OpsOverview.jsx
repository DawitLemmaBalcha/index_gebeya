// NB-50: Section 1 — Overview (ops-console.md §3).
// Polls /ops/health every 30s; every signal is age-labeled via
// generated_at (stale > 90s labeled "stale"); "unavailable" renders
// verbatim — never fabricated.

import { useCallback, useEffect, useRef, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsEmptyState from '../components/ops/OpsEmptyState';

const POLL_MS = 30000;
const STALE_MS = 90000;

export function ageLabel(generatedAt, now) {
  const gen = generatedAt ? new Date(generatedAt).getTime() : null;
  if (!gen || Number.isNaN(gen)) return '—';
  const age = now - gen;
  if (age > STALE_MS) return 'stale';
  return `${Math.round(age / 1000)}s old`;
}

function SignalRow({ name, signal, generatedAt, now }) {
  const { status, value, source, note } = signal || {};
  const stale = ageLabel(generatedAt, now) === 'stale';
  const badge =
    status === 'up' || status === 'ok'
      ? 'bg-emerald-100 text-emerald-700'
      : status === 'down' || status === 'error'
        ? 'bg-red-100 text-red-700'
        : status === 'unavailable'
          ? 'bg-gray-100 text-gray-500'
          : 'bg-amber-100 text-amber-700';

  return (
    <tr className={`border-t border-gray-100 ${stale ? 'bg-amber-50' : ''}`}>
      <td className="px-3 py-2 font-mono text-xs text-gray-700">{name}</td>
      <td className="px-3 py-2">
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge}`}>{status}</span>
      </td>
      <td className="px-3 py-2 font-mono text-xs text-gray-600">
        {value !== undefined && value !== null ? JSON.stringify(value) : '—'}
      </td>
      <td className="px-3 py-2 text-xs text-gray-400">{source || note || '—'}</td>
      <td className={`px-3 py-2 text-xs ${stale ? 'font-semibold text-amber-600' : 'text-gray-400'}`}>
        {ageLabel(generatedAt, now)}
      </td>
    </tr>
  );
}

export default function OpsOverview({ setToast }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [now, setNow] = useState(Date.now());
  const timerRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const d = await opsFetch('/ops/health');
      setData(d);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
    timerRef.current = setInterval(() => {
      setNow(Date.now());
      load();
    }, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, [load]);

  if (error && !data) {
    return (
      <OpsEmptyState
        title="Health unavailable"
        hint={error}
      />
    );
  }
  if (!data) {
    return <div className="text-sm text-gray-400">Loading health…</div>;
  }

  const services = data.services || {};
  const names = Object.keys(services);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Overview</h2>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          <span>Generated {ageLabel(data.generated_at, now)}</span>
          <button
            type="button"
            onClick={load}
            className="rounded border border-gray-300 px-2 py-1 hover:bg-gray-50"
          >
            Refresh
          </button>
        </div>
      </div>
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Signal</th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Status</th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Value</th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Source</th>
              <th className="px-3 py-2 text-left text-xs font-semibold uppercase text-gray-500">Age</th>
            </tr>
          </thead>
          <tbody>
            {names.map((name) => (
              <SignalRow
                key={name}
                name={name}
                signal={services[name]}
                generatedAt={data.generated_at}
                now={now}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
