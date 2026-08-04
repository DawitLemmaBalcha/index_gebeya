import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, Bell, Send, TrendingUp, BarChart3, Sparkles, Loader2, RefreshCw } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

/**
 * NB-47: Seller Intelligence dashboard (blueprint §2.8).
 * Core block renders for every channel owner; the Intelligence block only
 * when is_pro (active all-in-one subscription) — else an upgrade prompt
 * with an NB-48 unlock CTA that opens the Monetization Hub's All-in-One tab.
 */
const SellerIntelligenceDashboard = ({ channelId }) => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const fetchStats = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/channels/${channelId}/stats?init_data=${encodeURIComponent(initData)}`,
        { headers: { ...getAnalyticsHeaders() } }
      );
      if (!res.ok) throw new Error(`Stats unavailable (${res.status})`);
      setStats(await res.json());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  if (loading && !stats) {
    return (
      <div className="flex justify-center items-center py-20">
        <Loader2 size={28} className="animate-spin text-brand-600" />
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="py-16 text-center px-4">
        <p className="text-sm text-gray-500 mb-3">{error}</p>
        <button
          onClick={fetchStats}
          className="flex items-center gap-2 mx-auto px-4 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium"
        >
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );
  }

  if (!stats) return null;

  const fmt = (n) => (n == null ? '—' : new Intl.NumberFormat('en-ET').format(n));

  return (
    // UAT fix: the modal's content area is `overflow-hidden`, so this tab
    // must provide its own scroll container (h-full + overflow-y-auto,
    // same pattern as InventorySettingsTab) or long dashboards are clipped
    // with no way to scroll.
    <div className="h-full overflow-y-auto px-4 py-4 pb-8 space-y-4">
      {/* ============ CORE BLOCK (free) ============ */}
      <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100">
        <h2 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
          <BarChart3 size={16} className="text-brand-600" /> Overview
        </h2>

        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-gray-50 rounded-xl p-3 text-center">
            <Eye size={16} className="text-gray-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-gray-900">
              {fmt(stats.core.items.reduce((sum, i) => sum + (i.views_total || 0), 0))}
            </p>
            <p className="text-[10px] text-gray-500">Total Views</p>
          </div>
          <div className="bg-gray-50 rounded-xl p-3 text-center">
            <Bell size={16} className="text-gray-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-gray-900">{fmt(stats.core.matching_buyers)}</p>
            <p className="text-[10px] text-gray-500">Matching Buyers</p>
          </div>
          <div className="bg-gray-50 rounded-xl p-3 text-center">
            <Send size={16} className="text-gray-400 mx-auto mb-1" />
            <p className="text-lg font-bold text-gray-900">
              {fmt((stats.core.total_dispatched?.bullseye || 0) + (stats.core.total_dispatched?.ring || 0))}
            </p>
            <p className="text-[10px] text-gray-500">Dispatched</p>
          </div>
        </div>

        {/* Per-item rows with 7-day sparkline */}
        <div className="space-y-3">
          {(stats.core.items || []).map((item) => (
            <div key={item.item_id} className="border border-gray-100 rounded-xl p-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-gray-800 truncate max-w-[55%]">
                  {item.title || `Item #${item.item_id}`}
                </p>
                <span className="text-xs font-bold text-brand-700">{fmt(item.views_total)} views</span>
              </div>
              {/* 7-day sparkline */}
              <div className="flex items-end gap-1 h-8 mb-2">
                {(item.views_daily || []).map((day) => (
                  <div
                    key={day.date}
                    className="flex-1 rounded-sm bg-brand-100"
                    style={{ height: `${Math.max(8, Math.min(100, (day.count || 0) * 18))}%` }}
                    title={`${day.date}: ${day.count}`}
                  />
                ))}
              </div>
              <div className="flex items-center justify-between text-[10px] text-gray-500">
                <span>{fmt(item.alert_matches)} alert matches</span>
                <span>
                  🎯 {item.dispatched?.bullseye || 0} bullseye · 🔔 {item.dispatched?.ring || 0} ring
                </span>
              </div>
            </div>
          ))}
          {(stats.core.items || []).length === 0 && (
            <p className="text-xs text-gray-400 text-center py-4">No items in this channel yet.</p>
          )}
        </div>
      </div>

      {/* ============ INTELLIGENCE BLOCK (Pro-only) ============ */}
      {stats.is_pro ? (
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-amber-200">
          <h2 className="text-sm font-bold text-gray-900 mb-3 flex items-center gap-2">
            <Sparkles size={16} className="text-amber-500" /> Seller Intelligence
          </h2>

          {/* Price positioning */}
          <div className="mb-4">
            <h3 className="text-xs font-semibold text-gray-500 mb-2">Price Positioning</h3>
            <div className="space-y-2">
              {(stats.pro?.price_positioning || []).map((row) => (
                <div key={row.item_id} className="flex items-center justify-between text-xs">
                  <span className="text-gray-700 truncate max-w-[55%]">Item #{row.item_id}</span>
                  <span className={`font-bold ${row.pct_diff == null ? 'text-gray-400' : row.pct_diff <= 0 ? 'text-green-600' : 'text-red-500'}`}>
                    {row.pct_diff == null
                      ? '—'
                      : `${row.pct_diff > 0 ? '+' : ''}${row.pct_diff}% vs median ${fmt(row.median_price)}`}
                  </span>
                </div>
              ))}
              {(stats.pro?.price_positioning || []).length === 0 && (
                <p className="text-[10px] text-gray-400">No priced items yet.</p>
              )}
            </div>
          </div>

          {/* Category pulse */}
          <div className="mb-4">
            <h3 className="text-xs font-semibold text-gray-500 mb-2">Category Pulse</h3>
            <div className="space-y-2">
              {(stats.pro?.category_pulse || []).map((pulse) => (
                <div key={pulse.category} className="flex items-center justify-between text-xs">
                  <span className="text-gray-700">{pulse.category}</span>
                  <span className="text-gray-500">
                    <strong className="text-gray-900">{fmt(pulse.this_week)}</strong> this week ·{' '}
                    {fmt(pulse.last_week)} last week
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Top performers */}
          <div>
            <h3 className="text-xs font-semibold text-gray-500 mb-2">Top Performers</h3>
            <div className="space-y-2">
              {(stats.pro?.top_performers || []).map((perf, idx) => (
                <div key={perf.item_id} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-gray-400 font-bold">{idx + 1}</span>
                  <span className="text-gray-700 truncate flex-1">{perf.title || `Item #${perf.item_id}`}</span>
                  <span className="font-bold text-gray-900">{fmt(perf.views)} views</span>
                </div>
              ))}
              {(stats.pro?.top_performers || []).length === 0 && (
                <p className="text-[10px] text-gray-400">No view data yet.</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="bg-gradient-to-br from-amber-50 to-brand-50 rounded-2xl p-4 border border-amber-200">
          <div className="flex items-start gap-3">
            <TrendingUp size={20} className="text-amber-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-gray-900 mb-1">Unlock Seller Intelligence</h3>
              <p className="text-xs text-gray-600 leading-relaxed mb-3">
                Price positioning vs your category's median, weekly category pulse, and
                top-performer insights — included with the All-in-One subscription.
              </p>
              {/* NB-48 §2.4.3: the locked prompt leads to the hub FIRST
                  (Rule 10.1.1 — never a bare redirect to payment). */}
              <button
                onClick={() => navigate('/hub/all-in-one')}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-amber-500 text-white hover:bg-amber-600 transition-colors"
              >
                Unlock Seller Intelligence
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SellerIntelligenceDashboard;
