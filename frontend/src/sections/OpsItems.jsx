// NB-60: Items Analytics — the Catalog section's Analytics sub-tab.
// Three blocks over live rows: the 14-day views series (aggregate bar row +
// top-20 per-item rows), the per-category price-distribution histogram, and
// the per-active-channel aggregation. Pure GET — no verbs, no mutations.

import { useCallback, useEffect, useState } from 'react';
import { opsFetch } from '../utils/opsApi';
import OpsTable from '../components/ops/OpsTable';
import OpsEmptyState from '../components/ops/OpsEmptyState';

const BUCKET_COLORS = ['bg-blue-200', 'bg-blue-300', 'bg-blue-400', 'bg-blue-500', 'bg-blue-600'];

function Bar({ value, max }) {
  const pct = max > 0 ? Math.max(4, Math.round((value / max) * 100)) : 0;
  return (
    <div className="flex h-16 items-end gap-[2px]">
      <div className="w-6 rounded-t bg-blue-500" style={{ height: `${pct}%` }} />
      <span className="ml-1 self-center text-[10px] text-gray-400">{value}</span>
    </div>
  );
}

export default function OpsItems({ setToast }) {
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setAnalytics(await opsFetch('/ops/items/analytics'));
    } catch (err) {
      setError(err.message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }
  if (!analytics) {
    return <div className="text-sm text-gray-400">Loading analytics…</div>;
  }

  const { views_over_time: rawViews, price_distribution: dist, per_channel: channels } = analytics;
  const views = rawViews ?? { days: [], total: [], top_items: [] };
  const maxDay = Math.max(...(views.total ?? []), 1);
  const topItems = views.top_items ?? [];
  const maxTop = Math.max(...topItems.map((t) => t.total), 1);

  return (
    <div className="space-y-6">
      {/* Views over the last 14 days */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800">
          Views — last 14 days (aggregate)
        </h3>
        <div className="mt-3 flex items-end gap-1 overflow-x-auto">
          {views.days.map((d, i) => (
            <div key={d} className="flex flex-col items-center">
              <Bar value={views.total[i] ?? 0} max={maxDay} />
              <span className="mt-1 text-[10px] text-gray-400">{d.slice(5)}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Top-20 items by views */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800">
          Top items by views (live inventory)
        </h3>
        {topItems.length === 0 ? (
          <OpsEmptyState title="No views in the window" />
        ) : (
          <div className="mt-3 space-y-2">
            {topItems.map((t) => (
              <div key={t.item_id} className="flex items-center gap-3">
                <span className="w-40 truncate text-xs text-gray-600">
                  #{t.item_id} {t.title ?? ''}
                </span>
                <div className="flex flex-1 items-end gap-[2px]">
                  {t.daily.map((v, i) => (
                    <div
                      key={i}
                      className="rounded-t bg-blue-400"
                      style={{
                        height: `${Math.max(3, Math.round((v / maxTop) * 24))}px`,
                      }}
                      title={`${views.days[i]}: ${v}`}
                    />
                  ))}
                </div>
                <span className="text-xs font-medium text-gray-700">{t.total}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Price distribution per category */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800">
          Price distribution (active priced items)
        </h3>
        {dist.length === 0 ? (
          <OpsEmptyState title="No priced items" />
        ) : (
          <div className="mt-3 space-y-3">
            {dist.map((cat) => {
              const maxBucket = Math.max(...Object.values(cat.buckets), 1);
              return (
                <div key={cat.category}>
                  <div className="text-xs font-medium text-gray-600">{cat.category}</div>
                  <div className="mt-1 flex items-end gap-2">
                    {Object.entries(cat.buckets).map(([name, n], i) => (
                      <div key={name} className="flex flex-col items-center">
                        <div
                          className={`w-14 rounded-t ${BUCKET_COLORS[i]}`}
                          style={{ height: `${Math.max(4, Math.round((n / maxBucket) * 48))}px` }}
                          data-testid={`bucket-${name}`}
                        />
                        <span className="mt-1 text-[10px] text-gray-400">{name}</span>
                        <span className="text-xs font-medium text-gray-700">{n}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Per-channel aggregation */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="text-sm font-semibold text-gray-800">Per channel (active)</h3>
        {channels.length === 0 ? (
          <OpsEmptyState title="No active channels" />
        ) : (
          <OpsTable
            columns={[
              { key: 'username', label: 'Channel', render: (r) => `@${r.username}` },
              { key: 'title', label: 'Title' },
              { key: 'items', label: 'Items' },
              { key: 'views', label: 'Views' },
              { key: 'sold_reports', label: 'Sold reports' },
            ]}
            data={channels}
          />
        )}
      </div>
    </div>
  );
}
