// NB-55/NB-60: Section 2 — Catalog → Quality Events (ops-console.md Rule 2)
// + Items Analytics. Every owner correction (the existing ItemEdit history)
// surfaced with a Revert verb — the operator watches and enforces; never
// reclassifies by hand. Two sub-tabs: Events | Analytics (P1 + P6).

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';
import OpsItems from './OpsItems';

const TABS = [
  { id: 'events', label: 'Events' },
  { id: 'analytics', label: 'Analytics' },
];

export default function OpsQuality({ setToast }) {
  const [tab, setTab] = useState('events');
  const [events, setEvents] = useState(null);
  const [revertPending, setRevertPending] = useState(null);

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const load = useCallback(async () => {
    try {
      setEvents(await opsFetch('/ops/quality/events'));
    } catch (err) {
      toast(err.message, 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doRevert = async () => {
    try {
      const res = await opsFetch(`/ops/quality/events/${revertPending.id}/revert`, {
        method: 'POST',
      });
      toast(`Reverted ${res.field} on item #${res.item_id}`);
      setRevertPending(null);
      await load();
    } catch (err) {
      toast(err.message, 'error');
      setRevertPending(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Quality Events</h2>
        <button
          type="button"
          onClick={load}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-t border-b-2 px-3 py-1.5 text-sm ${
              tab === t.id
                ? 'border-blue-600 font-medium text-blue-700'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div hidden={tab !== 'events'}>
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          {!events ? (
            <div className="text-sm text-gray-400">Loading events…</div>
          ) : events.length === 0 ? (
            <OpsEmptyState title="No owner corrections yet" />
          ) : (
            <OpsTable
              columns={[
                { key: 'id', label: 'ID' },
                { key: 'title', label: 'Item' },
                { key: 'field', label: 'Field' },
                { key: 'old_value', label: 'From', render: (r) => r.old_value ?? '—' },
                { key: 'new_value', label: 'To', render: (r) => r.new_value ?? '—' },
                { key: 'edited_by_username', label: 'Editor' },
                {
                  key: 'timestamp',
                  label: 'When',
                  render: (r) => (r.timestamp ? new Date(r.timestamp).toLocaleString() : '—'),
                },
                {
                  key: 'actions',
                  label: '',
                  render: (r) => (
                    <button
                      type="button"
                      onClick={() => setRevertPending(r)}
                      className="rounded bg-amber-500 px-2 py-1 text-xs font-medium text-white hover:bg-amber-600"
                    >
                      Revert
                    </button>
                  ),
                },
              ]}
              data={events}
            />
          )}
        </div>
      </div>

      <div hidden={tab !== 'analytics'}>
        <OpsItems setToast={setToast} />
      </div>

      <OpsConfirmDialog
        open={revertPending !== null}
        title="Revert owner correction"
        message={
          revertPending
            ? `Restore the previous ${revertPending.field} value on item #${revertPending.item_id}? The revert is itself recorded as an edit event and re-triggers alert matching for price/specs/category/subcategory.`
            : ''
        }
        confirmLabel="Revert"
        danger
        onConfirm={doRevert}
        onCancel={() => setRevertPending(null)}
      />
    </div>
  );
}
