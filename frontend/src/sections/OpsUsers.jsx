// NB-56/NB-60: Section 4 — Users: diagnosis + the ban lever (Rule 7.1/7.2)
// + the deep footprint. Lookup by telegram id → status card (banned flag +
// footprint counts) → Ban/Unban verb with confirmation. The footprint block
// adds the rating distribution (1..5), the recent 5 reviews, and the recent
// interaction activity — no row editing (Rule 7.3).

import { useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsConfirmDialog from '../components/ops/OpsConfirmDialog';
import OpsEmptyState from '../components/ops/OpsEmptyState';

const RATING_COLORS = ['bg-red-400', 'bg-amber-400', 'bg-yellow-400', 'bg-lime-400', 'bg-green-500'];

export default function OpsUsers({ setToast }) {
  const [telegramId, setTelegramId] = useState('');
  const [status, setStatus] = useState(null);
  const [footprint, setFootprint] = useState(null);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionPending, setActionPending] = useState(null); // 'ban' | 'unban'

  const toast = (message, type = 'success') => setToast?.({ message, type });

  const lookup = async (e) => {
    e?.preventDefault();
    const id = telegramId.trim();
    if (!id || !/^\d+$/.test(id)) {
      toast('Enter a numeric telegram id', 'error');
      return;
    }
    setBusy(true);
    setStatus(null);
    setFootprint(null);
    setSearched(false);
    try {
      const [st, fp] = await Promise.all([
        opsFetch(`/ops/users/${id}/status`),
        opsFetch(`/ops/users/${id}/footprint`),
      ]);
      setStatus(st);
      setFootprint(fp);
      setSearched(true);
    } catch (err) {
      setSearched(true);
      toast(err.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const doAction = async () => {
    try {
      const res = await opsFetch(`/ops/users/${status.telegram_id}/${actionPending}`, {
        method: 'POST',
      });
      toast(`User ${res.banned ? 'banned' : 'unbanned'} — ${res.banned ? 'items hidden and indexing paused' : 'everything restored instantly'}`);
      setActionPending(null);
      setStatus({ ...status, banned: res.banned });
    } catch (err) {
      toast(err.message, 'error');
      setActionPending(null);
    }
  };

  const counts = status?.footprint ?? {};
  const countItems = [
    { key: 'reviews', label: 'Reviews' },
    { key: 'alerts_active', label: 'Alerts active' },
    { key: 'alerts_total', label: 'Alerts total' },
    { key: 'subscriptions_active', label: 'Subscriptions' },
    { key: 'boosts', label: 'Boosts' },
    { key: 'sold_reports', label: 'Sold reports' },
  ];

  const ratingDist = footprint?.reviews?.rating_distribution ?? {};
  const maxRating = Math.max(...Object.values(ratingDist), 1);
  const recentReviews = footprint?.reviews?.recent ?? [];
  const interactions = footprint?.interactions ?? {};

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">Users</h2>
      </div>

      <form onSubmit={lookup} className="flex items-center gap-2">
        <input
          value={telegramId}
          onChange={(e) => setTelegramId(e.target.value)}
          placeholder="Telegram id"
          className="w-64 rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-blue-600 px-3 py-1 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? 'Looking up…' : 'Look up'}
        </button>
      </form>

      {searched && !status && (
        <OpsEmptyState title="User not found" hint="No users row has this telegram id." />
      )}

      {status && (
        <div className="space-y-4">
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-gray-800">
                  {status.username || 'no username'} <span className="text-gray-400">({status.telegram_id})</span>
                </div>
                <div className="mt-1 text-sm">
                  {status.banned ? (
                    <span className="rounded bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">BANNED</span>
                  ) : (
                    <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">active</span>
                  )}
                </div>
              </div>
              {status.banned ? (
                <button
                  type="button"
                  onClick={() => setActionPending('unban')}
                  className="rounded bg-green-600 px-3 py-1 text-sm font-medium text-white hover:bg-green-700"
                >
                  Unban
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setActionPending('ban')}
                  className="rounded bg-red-600 px-3 py-1 text-sm font-medium text-white hover:bg-red-700"
                >
                  Ban
                </button>
              )}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {countItems.map((c) => (
                <div key={c.key} className="rounded border border-gray-100 bg-gray-50 p-3 text-center">
                  <div className="text-xl font-semibold text-gray-800">{counts[c.key] ?? '—'}</div>
                  <div className="text-xs text-gray-400">{c.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* NB-60: the deep footprint */}
          {footprint && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-gray-800">
                  Reviews — {footprint.reviews.total} total
                </h3>
                <div className="mt-3 flex items-end gap-2">
                  {['1', '2', '3', '4', '5'].map((r, i) => (
                    <div key={r} className="flex flex-col items-center">
                      <div
                        className={`w-8 rounded-t ${RATING_COLORS[i]}`}
                        style={{
                          height: `${Math.max(4, Math.round(((ratingDist[r] ?? 0) / maxRating) * 48))}px`,
                        }}
                        data-testid={`rating-${r}`}
                      />
                      <span className="mt-1 text-[10px] text-gray-400">{r}★</span>
                      <span className="text-xs font-medium text-gray-700">{ratingDist[r] ?? 0}</span>
                    </div>
                  ))}
                </div>
                {recentReviews.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {recentReviews.map((rv, i) => (
                      <div key={i} className="rounded border border-gray-100 bg-gray-50 p-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-gray-700">@{rv.channel_username}</span>
                          <span className="text-amber-500">{'★'.repeat(rv.rating)}{'☆'.repeat(5 - rv.rating)}</span>
                        </div>
                        {rv.comment && <div className="mt-1 text-gray-500">{rv.comment}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-gray-800">Recent activity</h3>
                {Object.keys(interactions.counts_by_type ?? {}).length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400">No tracked interactions.</p>
                ) : (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {Object.entries(interactions.counts_by_type).map(([type, n]) => (
                      <span key={type} className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600">
                        {type}: <span className="font-medium">{n}</span>
                      </span>
                    ))}
                  </div>
                )}
                {(interactions.recent_50 ?? []).length > 0 && (
                  <div className="mt-3 space-y-1">
                    {(interactions.recent_50 ?? []).slice(0, 8).map((ix) => (
                      <div key={ix.id} className="flex justify-between text-xs text-gray-500">
                        <span>
                          {ix.interaction_type} on item #{ix.item_id ?? '—'}
                        </span>
                        <span className="text-gray-400">
                          {ix.created_at ? new Date(ix.created_at).toLocaleString() : ''}
                        </span>
                      </div>
                    ))}
                    <p className="text-[10px] text-gray-400">
                      showing 8 of {interactions.recent_50.length} recent interactions
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <OpsConfirmDialog
        open={actionPending !== null}
        title={actionPending === 'ban' ? 'Ban user' : 'Unban user'}
        message={
          actionPending === 'ban'
            ? `Ban ${status?.telegram_id}? Their channels pause indexing, their items hide from browse/search/feed, and they cannot create alerts, reviews, or sold reports. Evidence rows stay; unban restores everything instantly.`
            : `Unban ${status?.telegram_id}? Everything restores instantly — no side jobs.`
        }
        confirmLabel={actionPending === 'ban' ? 'Ban' : 'Unban'}
        danger={actionPending === 'ban'}
        onConfirm={doAction}
        onCancel={() => setActionPending(null)}
      />
    </div>
  );
}
