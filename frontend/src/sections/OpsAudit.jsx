// NB-52: Section 9 — Audit (ops-console.md §6).
// Read-only, filterable table of every console mutation.

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';

export default function OpsAudit({ setToast }) {
  const [rows, setRows] = useState(null);
  const [section, setSection] = useState('');
  const [admin, setAdmin] = useState('');

  const toast = (message, type = 'error') => setToast?.({ message, type });

  const load = useCallback(async () => {
    const params = new URLSearchParams();
    if (section) params.set('section', section);
    if (admin) params.set('admin', admin);
    const qs = params.toString();
    try {
      setRows(await opsFetch(`/ops/audit${qs ? `?${qs}` : ''}`));
    } catch (err) {
      toast(err.message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, admin]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [section, admin]);

  const fmt = (v) => {
    if (v === undefined || v === null) return '—';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Audit</h2>
        <div className="flex items-center gap-2 text-sm">
          <input
            placeholder="section"
            value={section}
            onChange={(e) => setSection(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-xs"
          />
          <input
            placeholder="admin"
            value={admin}
            onChange={(e) => setAdmin(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1 text-xs"
          />
          <button
            type="button"
            onClick={load}
            className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
          >
            Refresh
          </button>
        </div>
      </div>
      {!rows ? (
        <div className="text-sm text-gray-400">Loading audit…</div>
      ) : rows.length === 0 ? (
        <OpsEmptyState title="No audit rows" hint="Console mutations appear here." />
      ) : (
        <OpsTable
          columns={[
            { key: 'id', label: 'ID' },
            { key: 'admin_user', label: 'Admin' },
            { key: 'section', label: 'Section' },
            { key: 'action', label: 'Action' },
            { key: 'entity_type', label: 'Entity' },
            { key: 'entity_id', label: 'Entity ID' },
            { key: 'before', label: 'Before', render: (r) => fmt(r.before) },
            { key: 'after', label: 'After', render: (r) => fmt(r.after) },
            { key: 'created_at', label: 'When', render: (r) => new Date(r.created_at).toLocaleString() },
          ]}
          data={rows}
        />
      )}
    </div>
  );
}
