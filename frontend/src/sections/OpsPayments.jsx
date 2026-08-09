// NB-53: Section 7 — Payments (ops-console.md §7).
// Star ledger, balance, last reconciliation + run-now, refund form with
// a warning dialog (refunds are irreversible in Telegram).

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';

export default function OpsPayments({ setToast }) {
  const [ledger, setLedger] = useState(null);
  const [balance, setBalance] = useState(null);
  const [recon, setRecon] = useState(null);
  const [running, setRunning] = useState(false);
  const [chargeId, setChargeId] = useState('');
  const [refundPending, setRefundPending] = useState(false);

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const load = useCallback(async () => {
    try {
      const [l, b, r] = await Promise.all([
        opsFetch('/ops/payments/ledger'),
        opsFetch('/ops/payments/balance'),
        opsFetch('/ops/payments/reconciliation'),
      ]);
      setLedger(l);
      setBalance(b);
      setRecon(r);
    } catch (err) {
      toast(err.message, 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runNow = async () => {
    setRunning(true);
    try {
      const summary = await opsFetch('/ops/payments/reconciliation/run', { method: 'POST' });
      toast(`Reconciliation done: ${summary.replayed_boost ?? 0} boosts, ${summary.replayed_subscription ?? 0} subs replayed`);
      await load();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      setRunning(false);
    }
  };

  const doRefund = async () => {
    try {
      const res = await opsFetch('/ops/payments/refund', {
        method: 'POST',
        body: { telegram_payment_charge_id: chargeId },
      });
      toast(`Refund ${res.result ? 'submitted' : 'failed'} for ${chargeId}`);
      setRefundPending(false);
      setChargeId('');
    } catch (err) {
      toast(err.message, 'error');
      setRefundPending(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Payments</h2>
        <button
          type="button"
          onClick={load}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {/* Balance + reconciliation */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="text-xs text-gray-400">Star balance</div>
          <div className="mt-1 text-2xl font-semibold text-gray-800">
            {typeof balance?.balance_stars === 'number' ? balance.balance_stars : '—'} ⭐
          </div>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <div className="text-xs text-gray-400">Last reconciliation</div>
            <button
              type="button"
              onClick={runNow}
              disabled={running}
              className="rounded bg-blue-600 px-3 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {running ? 'Running…' : 'Run now'}
            </button>
          </div>
          {recon?.status === 'never run' ? (
            <div className="mt-2 text-sm text-gray-400">never run</div>
          ) : (
            <div className="mt-2 text-sm text-gray-700">
              <div>
                {recon?.last_run_at ? `Ran ${new Date(recon.last_run_at).toLocaleString()}` : 'never run'}
              </div>
              {recon?.last_error && (
                <div className="text-red-600">error: {recon.last_error}</div>
              )}
              {recon?.last_result && (
                <div className="mt-1 font-mono text-xs text-gray-500">
                  {JSON.stringify(recon.last_result)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Refund form */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-2 font-medium text-gray-800">Refund (operator tool)</div>
        <div className="flex items-center gap-2">
          <input
            placeholder="telegram_payment_charge_id"
            value={chargeId}
            onChange={(e) => setChargeId(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            disabled={!chargeId}
            onClick={() => setRefundPending(true)}
            className="rounded bg-red-600 px-3 py-1 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            Refund
          </button>
        </div>
      </div>

      {/* Ledger */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-2 font-medium text-gray-800">Star ledger (last 100)</div>
        {!ledger ? (
          <div className="text-sm text-gray-400">Loading ledger…</div>
        ) : ledger.length === 0 ? (
          <OpsEmptyState title="No transactions" />
        ) : (
          <OpsTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'date', label: 'Date', render: (r) => (r.date ? new Date(r.date * 1000).toLocaleString() : '—') },
              { key: 'amount', label: 'Amount ⭐', render: (r) => (typeof r.amount === 'number' ? r.amount : '—') },
              { key: 'transaction_type', label: 'Type' },
              { key: 'payload_prefix', label: 'Prefix' },
              { key: 'user_id', label: 'User' },
            ]}
            data={ledger}
          />
        )}
      </div>

      <OpsConfirmDialog
        open={refundPending}
        title="Irreversible refund"
        message={`Refund charge ${chargeId}? Refunds are IRREVERSIBLE in Telegram. An audit row records this action.`}
        confirmLabel="Refund"
        danger
        onConfirm={doRefund}
        onCancel={() => setRefundPending(false)}
      />
    </div>
  );
}
