// NB-52: Section 8 — Settings & Flags (ops-console.md §5).
// Registry table: description, live value, source badge (db/env).
// DB-sourced editable with confirm; env-sourced rows are labeled
// "requires deploy to change" and non-editable (Rule 5.2).

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsInlineEdit from '../components/ops/OpsInlineEdit';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';

export default function OpsSettings({ setToast }) {
  const [rows, setRows] = useState(null);
  const [pending, setPending] = useState(null); // {key, value} awaiting confirm

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const load = useCallback(async () => {
    try {
      setRows(await opsFetch('/ops/settings'));
    } catch (err) {
      toast(err.message, 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const save = async () => {
    try {
      await opsFetch(`/ops/settings/${pending.key}`, {
        method: 'PUT',
        body: { value: pending.value },
      });
      toast(`${pending.key} → ${pending.value}`);
      setPending(null);
      await load();
    } catch (err) {
      toast(err.message, 'error');
      setPending(null);
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Settings & Flags</h2>
        <button
          type="button"
          onClick={load}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>
      {!rows ? (
        <div className="text-sm text-gray-400">Loading settings…</div>
      ) : (
        <OpsTable
          columns={[
            { key: 'key', label: 'Key' },
            { key: 'description', label: 'Description' },
            {
              key: 'value',
              label: 'Live value',
              render: (r) => (
                <span className="font-mono text-gray-800">{String(r.value)}</span>
              ),
            },
            {
              key: 'source',
              label: 'Source',
              render: (r) => (
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    r.source === 'db'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                >
                  {r.source}
                </span>
              ),
            },
            {
              key: 'edit',
              label: 'Edit',
              render: (r) =>
                r.source === 'db' ? (
                  <OpsInlineEdit
                    value={r.value}
                    onSave={(v) => setPending({ key: r.key, value: v })}
                    onCancel={() => {}}
                  />
                ) : (
                  <span className="text-xs italic text-gray-400">
                    requires deploy to change
                  </span>
                ),
            },
          ]}
          data={rows}
        />
      )}

      <OpsConfirmDialog
        open={!!pending}
        title={`Update ${pending?.key}?`}
        message="This writes a DB override — the setting takes effect immediately for all users."
        confirmLabel="Update"
        onConfirm={save}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}
