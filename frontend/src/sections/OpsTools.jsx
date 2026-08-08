// NB-54: Section 10 — Support Toolkit (ops-console.md §8).
// Test boosts, test subscriptions (grant/revoke), the payment-webhook
// simulator (the primary UAT tool), deep-link generator. Every action
// is confirmed + audited; clearly labeled TEST.

import { useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';

export default function OpsTools({ setToast }) {
  const [boostItemId, setBoostItemId] = useState('');
  const [subUserId, setSubUserId] = useState('');
  const [subProduct, setSubProduct] = useState('alerts_only');
  const [sim, setSim] = useState({
    telegram_payment_charge_id: '',
    invoice_payload: '',
    total_amount: '',
    subscription_expiration_date: '',
    is_recurring: false,
    is_first_recurring: false,
  });
  const [deepItemId, setDeepItemId] = useState('');
  const [deepChannelId, setDeepChannelId] = useState('');
  const [deepLinks, setDeepLinks] = useState(null);
  const [confirming, setConfirming] = useState(null); // {kind, run}

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const grantTestBoost = async () => {
    try {
      const res = await opsFetch('/ops/tools/test-boost', {
        method: 'POST',
        body: { item_id: parseInt(boostItemId, 10) },
      });
      toast(`Test boost #${res.boost_id} granted on item ${res.item_id} (source=test)`);
      setBoostItemId('');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const grantTestSubscription = async () => {
    try {
      const res = await opsFetch('/ops/tools/test-subscription', {
        method: 'POST',
        body: { user_id: parseInt(subUserId, 10), product: subProduct },
      });
      toast(`Test subscription #${res.subscription_id} granted (${res.product})`);
      setSubUserId('');
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const revokeTestSubscription = async (id) => {
    try {
      const res = await opsFetch(`/ops/tools/test-subscription/${id}/revoke`, { method: 'POST' });
      toast(`Test subscription #${res.subscription_id} revoked`);
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const runSimulator = async () => {
    try {
      const body = {
        telegram_payment_charge_id: sim.telegram_payment_charge_id,
        invoice_payload: sim.invoice_payload,
        total_amount: parseInt(sim.total_amount, 10) || 0,
        subscription_expiration_date: sim.subscription_expiration_date || null,
        is_recurring: sim.is_recurring,
        is_first_recurring: sim.is_first_recurring,
      };
      const res = await opsFetch('/ops/tools/simulate-payment', { method: 'POST', body });
      const id = res.boost_id ? `boost #${res.boost_id}` : `subscription #${res.subscription_id}`;
      toast(`Simulated payment fulfilled → ${id} (charge ${sim.telegram_payment_charge_id})`);
      setSim({ ...sim, telegram_payment_charge_id: '', invoice_payload: '', total_amount: '' });
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const generateDeepLinks = async () => {
    try {
      const params = new URLSearchParams();
      if (deepItemId) params.set('item_id', deepItemId);
      if (deepChannelId) params.set('channel_id', deepChannelId);
      setDeepLinks(await opsFetch(`/ops/tools/deep-links?${params.toString()}`));
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const section = (title, children) => (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 font-medium text-gray-800">{title}</div>
      {children}
    </div>
  );

  const input = (label, value, onChange, placeholder = '') => (
    <label className="block text-sm text-gray-600">
      {label}
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
      />
    </label>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Support Toolkit</h2>
        <span className="rounded bg-amber-100 px-2 py-1 text-xs font-medium text-amber-700">
          TEST actions write real rows — audit-logged
        </span>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {section('Grant test boost', (
          <div className="space-y-3">
            <p className="text-xs text-gray-400">
              Creates a real Boost row with source=test (no payment, no credit consumed).
            </p>
            {input('Item ID', boostItemId, setBoostItemId, 'e.g. 123')}
            <button
              type="button"
              disabled={!boostItemId}
              onClick={() => setConfirming({ kind: 'boost', run: grantTestBoost })}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Grant test boost
            </button>
          </div>
        ))}

        {section('Test subscription', (
          <div className="space-y-3">
            <p className="text-xs text-gray-400">
              Grants a real active subscription (Telegram user id); revoke cancels it and
              lapses extras beyond the free cap.
            </p>
            <div className="grid grid-cols-2 gap-3">
              {input('Telegram user id', subUserId, setSubUserId, 'e.g. 111')}
              <label className="block text-sm text-gray-600">
                Product
                <select
                  value={subProduct}
                  onChange={(e) => setSubProduct(e.target.value)}
                  className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
                >
                  <option value="alerts_only">alerts_only</option>
                  <option value="all_in_one">all_in_one</option>
                </select>
              </label>
            </div>
            <button
              type="button"
              disabled={!subUserId}
              onClick={() => setConfirming({ kind: 'sub', run: grantTestSubscription })}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Grant test subscription
            </button>
            {subUserId && (
              <div className="text-xs text-gray-400">
                Revoke: <button
                  type="button"
                  className="text-red-600 underline"
                  onClick={() => setConfirming({ kind: 'revoke', run: () => revokeTestSubscription(0) })}
                >
                  (see audit rows for the subscription id)
                </button>
              </div>
            )}
          </div>
        ))}
      </div>

      {section('Payment-webhook simulator', (
        <div className="space-y-3">
          <p className="text-xs text-gray-400">
            Drives the EXACT fulfillment path the listener calls — no Telegram needed.
            Idempotent by charge id. Payload prefix b: fulfills a boost; s: a subscription.
          </p>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {input('Telegram payment charge id', sim.telegram_payment_charge_id,
              (v) => setSim({ ...sim, telegram_payment_charge_id: v }), 'e.g. chg_abc123')}
            {input('Invoice payload', sim.invoice_payload,
              (v) => setSim({ ...sim, invoice_payload: v }), 'e.g. b:123:nonce or s:1:alerts_only:nonce')}
            {input('Total amount (Stars)', sim.total_amount,
              (v) => setSim({ ...sim, total_amount: v }), 'e.g. 150')}
            {input('Subscription expiration date (s: only)', sim.subscription_expiration_date,
              (v) => setSim({ ...sim, subscription_expiration_date: v }), 'ISO date, optional')}
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={sim.is_recurring}
              onChange={(e) => setSim({ ...sim, is_recurring: e.target.checked })}
            />
            is_recurring
          </label>
          <button
            type="button"
            disabled={!sim.telegram_payment_charge_id || !sim.invoice_payload}
            onClick={() => setConfirming({ kind: 'sim', run: runSimulator })}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Simulate payment
          </button>
        </div>
      ))}

      {section('Deep-link generator', (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            {input('Item ID', deepItemId, setDeepItemId)}
            {input('Channel ID (optional)', deepChannelId, setDeepChannelId)}
          </div>
          <button
            type="button"
            disabled={!deepItemId && !deepChannelId}
            onClick={generateDeepLinks}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            Generate
          </button>
          {deepLinks && (
            <div className="space-y-1 rounded bg-gray-50 p-3 font-mono text-xs text-gray-700">
              <div>stores: {deepLinks.stores_url}</div>
              {deepLinks.item_url && <div>item: {deepLinks.item_url}</div>}
            </div>
          )}
        </div>
      ))}

      <OpsConfirmDialog
        open={!!confirming}
        title={
          confirming?.kind === 'sim'
            ? 'Simulate this payment?'
            : confirming?.kind === 'revoke'
              ? 'Revoke test subscription?'
              : 'Confirm TEST action?'
        }
        message={
          confirming?.kind === 'sim'
            ? 'This drives the real fulfillment path — a real Boost/Subscription row is created. Audit-logged.'
            : 'This creates/cancels a REAL production row, clearly marked test in the audit log.'
        }
        confirmLabel={confirming?.kind === 'sim' ? 'Simulate' : 'Confirm'}
        onConfirm={async () => {
          const run = confirming?.run;
          setConfirming(null);
          await run?.();
        }}
        onCancel={() => setConfirming(null)}
      />
    </div>
  );
}
