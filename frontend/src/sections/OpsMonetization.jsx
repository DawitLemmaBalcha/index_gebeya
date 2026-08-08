// NB-51: Section 6 — Monetization (ops-console.md §4).
// Pricing accordion with demand context + inline edit + bulk modal;
// feature toggles; subscription settings; revenue cards; boost
// moderation table with end-early confirm. All via the shared kit.

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';
import OpsInlineEdit from '../components/ops/OpsInlineEdit';

export default function OpsMonetization({ setToast }) {
  const [prices, setPrices] = useState(null);
  const [toggles, setToggles] = useState(null);
  const [settings, setSettings] = useState(null);
  const [revenue, setRevenue] = useState(null);
  const [boosts, setBoosts] = useState(null);
  const [bulkFor, setBulkFor] = useState(null); // {category, action}
  const [bulkPrice, setBulkPrice] = useState('');
  const [bulkPercent, setBulkPercent] = useState('');
  const [ending, setEnding] = useState(null); // boost row awaiting confirm
  const [expanded, setExpanded] = useState({});

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const loadAll = useCallback(async () => {
    try {
      const [p, t, s, r, b] = await Promise.all([
        opsFetch('/ops/monetization/prices'),
        opsFetch('/ops/monetization/toggles'),
        opsFetch('/ops/monetization/settings'),
        opsFetch('/ops/monetization/revenue'),
        opsFetch('/ops/monetization/boosts'),
      ]);
      setPrices(p);
      setToggles(t);
      setSettings(s);
      setRevenue(r);
      setBoosts(b);
    } catch (err) {
      toast(err.message, 'error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const savePrice = async (category, subcategory, raw) => {
    const price = parseInt(raw, 10);
    if (!Number.isInteger(price) || price < 1 || price > 10000) {
      toast('Price must be an integer between 1 and 10000', 'error');
      return;
    }
    try {
      await opsFetch(
        `/ops/monetization/prices/${encodeURIComponent(category)}/${encodeURIComponent(subcategory)}`,
        { method: 'PUT', body: { price_stars: price } },
      );
      toast(`Price for ${category}/${subcategory || '(category)'} → ${price} ⭐`);
      await loadAll();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const runBulk = async () => {
    try {
      const body = { action: bulkFor.action, category: bulkFor.category };
      if (bulkFor.action === 'set_category') body.price_stars = parseInt(bulkPrice, 10) || 0;
      if (bulkFor.action === 'percent') body.percent = parseInt(bulkPercent, 10) || 0;
      await opsFetch('/ops/monetization/prices/bulk', { method: 'POST', body });
      toast(`Bulk ${bulkFor.action} applied to ${bulkFor.category}`);
      setBulkFor(null);
      setBulkPrice('');
      setBulkPercent('');
      await loadAll();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const flipToggle = async (key, current) => {
    try {
      await opsFetch(`/ops/monetization/toggles/${key}`, {
        method: 'PUT',
        body: { value: !current },
      });
      toast(`${key} → ${!current ? 'ON' : 'OFF'}`);
      await loadAll();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const saveSetting = async (key, raw) => {
    try {
      await opsFetch(`/ops/monetization/settings/${key}`, {
        method: 'PUT',
        body: { value: raw },
      });
      toast(`${key} updated`);
      await loadAll();
    } catch (err) {
      toast(err.message, 'error');
    }
  };

  const endBoost = async () => {
    try {
      await opsFetch(`/ops/monetization/boosts/${ending.id}/end`, { method: 'POST' });
      toast(`Boost #${ending.id} ended early (no refund)`);
      setEnding(null);
      await loadAll();
    } catch (err) {
      toast(err.message, 'error');
      setEnding(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Monetization</h2>
        <button
          type="button"
          onClick={loadAll}
          className="rounded border border-gray-300 bg-white px-2 py-1 text-xs hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {/* Revenue cards */}
      {revenue && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            { label: 'Stars (30d)', value: revenue.stars_earned_last_30d, suffix: '⭐' },
            { label: 'Active subscriptions', value: revenue.active_subscriptions },
            { label: 'Active boosts', value: revenue.active_boosts },
            { label: 'Expiring in 24h', value: revenue.expiring_soon.length },
          ].map((card) => (
            <div key={card.label} className="rounded-lg border border-gray-200 bg-white p-4">
              <div className="text-xs text-gray-400">{card.label}</div>
              <div className="mt-1 text-2xl font-semibold text-gray-800">
                {card.value} {card.suffix || ''}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pricing accordion */}
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-4 py-3 font-medium text-gray-800">
          Boost pricing
        </div>
        {!prices ? (
          <div className="p-4 text-sm text-gray-400">Loading prices…</div>
        ) : (
          <div className="divide-y divide-gray-100">
            {prices.categories.map((cat) => {
              const open = expanded[cat.category];
              return (
                <div key={cat.category}>
                  <div className="flex items-center justify-between px-4 py-2.5">
                    <button
                      type="button"
                      className="text-sm font-medium text-gray-700 hover:text-blue-600"
                      onClick={() =>
                        setExpanded((prev) => ({ ...prev, [cat.category]: !prev[cat.category] }))
                      }
                    >
                      {open ? '▾' : '▸'} {cat.category}
                    </button>
                    <div className="flex gap-1.5">
                      {[
                        { label: 'Set all', action: 'set_category' },
                        { label: '+%', action: 'percent' },
                        { label: 'Reset', action: 'reset' },
                      ].map((b) => (
                        <button
                          key={b.action}
                          type="button"
                          onClick={() => setBulkFor({ category: cat.category, action: b.action })}
                          className="rounded border border-gray-300 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-50"
                        >
                          {b.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  {open && (
                    <div className="px-4 pb-3">
                      <OpsTable
                        columns={[
                          { key: 'subcategory', label: 'Subcategory', render: (r) => r.subcategory || '(category)' },
                          {
                            key: 'price_stars',
                            label: 'Price ⭐',
                            render: (r) => (
                              <OpsInlineEdit
                                value={r.price_stars}
                                inputType="number"
                                min={1}
                                onSave={(v) => savePrice(cat.category, r.subcategory, v)}
                                onCancel={() => {}}
                              />
                            ),
                          },
                          { key: 'source', label: 'Source' },
                          { key: 'active_boosts', label: 'Active' },
                          { key: 'boosts_this_week', label: 'This week' },
                        ]}
                        data={cat.rows}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Toggles */}
      {toggles && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 font-medium text-gray-800">Feature toggles</div>
          <div className="space-y-2">
            {toggles.map((t) => (
              <div key={t.key} className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm text-gray-700">{t.key}</div>
                  <div className="text-xs text-gray-400">{t.description}</div>
                </div>
                <button
                  type="button"
                  onClick={() => flipToggle(t.key, t.value)}
                  className={`rounded px-3 py-1 text-xs font-medium ${
                    t.value ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'
                  }`}
                >
                  {t.value ? 'ON' : 'OFF'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Subscription settings */}
      {settings && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <div className="mb-2 font-medium text-gray-800">Subscription settings</div>
          <OpsTable
            columns={[
              { key: 'key', label: 'Key' },
              { key: 'description', label: 'Description' },
              { key: 'source', label: 'Source' },
              {
                key: 'value',
                label: 'Value',
                render: (r) => (
                  <OpsInlineEdit
                    value={r.value}
                    onSave={(v) => saveSetting(r.key, v)}
                    onCancel={() => {}}
                  />
                ),
              },
            ]}
            data={settings}
          />
        </div>
      )}

      {/* Moderation */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-2 font-medium text-gray-800">Boost moderation</div>
        {!boosts ? (
          <div className="text-sm text-gray-400">Loading…</div>
        ) : boosts.length === 0 ? (
          <OpsEmptyState title="No active boosts" />
        ) : (
          <OpsTable
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'item_id', label: 'Item' },
              { key: 'title', label: 'Title' },
              { key: 'channel_username', label: 'Channel' },
              { key: 'source', label: 'Source' },
              { key: 'price_paid_stars', label: 'Paid ⭐' },
              { key: 'ends_at', label: 'Ends at' },
              {
                key: 'actions',
                label: '',
                render: (r) => (
                  <button
                    type="button"
                    onClick={() => setEnding(r)}
                    className="rounded bg-red-600 px-2 py-0.5 text-xs text-white hover:bg-red-700"
                  >
                    End early
                  </button>
                ),
              },
            ]}
            data={boosts}
          />
        )}
      </div>

      {/* Bulk modal */}
      <OpsConfirmDialog
        open={!!bulkFor}
        title={`Bulk ${bulkFor?.action} — ${bulkFor?.category}`}
        message={
          bulkFor?.action === 'set_category'
            ? 'One price for every subcategory in this category.'
            : bulkFor?.action === 'percent'
              ? 'Adjust every subcategory by a percentage (e.g. +50).'
              : 'Reset every subcategory to the constant floor.'
        }
        onConfirm={runBulk}
        onCancel={() => setBulkFor(null)}
        confirmLabel="Apply"
      >
        {bulkFor?.action === 'set_category' && (
          <div className="mt-3">
            <label className="text-sm text-gray-600">
              Price (Stars)
              <input
                type="number"
                min={1}
                value={bulkPrice}
                onChange={(e) => setBulkPrice(e.target.value)}
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </label>
          </div>
        )}
        {bulkFor?.action === 'percent' && (
          <div className="mt-3">
            <label className="text-sm text-gray-600">
              Percent (can be negative)
              <input
                type="number"
                value={bulkPercent}
                onChange={(e) => setBulkPercent(e.target.value)}
                className="mt-1 w-full rounded border border-gray-300 px-2 py-1 text-sm"
              />
            </label>
          </div>
        )}
      </OpsConfirmDialog>

      {/* End-early confirm */}
      <OpsConfirmDialog
        open={!!ending}
        title={`End boost #${ending?.id} early?`}
        message="This immediately ends the boost on the item. NO refund is granted (Rule 6.1)."
        confirmLabel="End boost"
        danger
        onConfirm={endBoost}
        onCancel={() => setEnding(null)}
      />
    </div>
  );
}
