import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, Plus, Pause, Play, Trash2, History, AlertCircle, Loader2, RefreshCw, X } from 'lucide-react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';
import AlertModal from '../components/AlertModal';
import { useAlerts } from '../hooks/useAlerts';

const AlertsPage = () => {
  const navigate = useNavigate();
  const {
    alerts,
    matchHistory,
    loading,
    error,
    fetchAlerts,
    fetchMatchHistory,
    pauseAlert,
    deleteAlert,
    hasBeenFetched,
  } = useAlerts();

  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [submittingActionId, setSubmittingActionId] = useState(null);

  // Lazy load: fetch only on first activation
  useEffect(() => {
    if (!hasBeenFetched) {
      fetchAlerts();
      fetchMatchHistory();
    }
  }, [hasBeenFetched, fetchAlerts, fetchMatchHistory]);

  const handlePause = async (alertId) => {
    setSubmittingActionId(alertId);
    await pauseAlert(alertId);
    setSubmittingActionId(null);
  };

  const handleDelete = async (alertId) => {
    const performDelete = async () => {
      setSubmittingActionId(alertId);
      await deleteAlert(alertId);
      setSubmittingActionId(null);
    };

    // Use Telegram's native confirm popup instead of window.confirm().
    // window.confirm() shows an OS-level dialog that corrupts the Telegram
    // WebView's touch/focus state, making inputs non-writable afterward.
    if (window.Telegram?.WebApp?.showConfirm) {
      window.Telegram.WebApp.showConfirm('Delete this alert?', (confirmed) => {
        if (confirmed) performDelete();
      });
      return;
    }

    // Fallback for non-Telegram environments
    if (window.confirm('Delete this alert?')) {
      await performDelete();
    }
  };

  const handleModalClose = (success) => {
    setIsCreateModalOpen(false);
    if (success) {
      fetchAlerts();
    }
  };

  const formatPrice = (price) => {
    if (!price) return 'Any';
    return `${new Intl.NumberFormat('en-ET').format(price)} ETB`;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const parsePreferences = (prefsStr) => {
    try {
      if (typeof prefsStr === 'string') return JSON.parse(prefsStr);
      if (typeof prefsStr === 'object') return prefsStr;
    } catch {
      // ignore
    }
    return {};
  };

  // Not-in-Telegram state
  if (error === 'NOT_IN_TELEGRAM') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
        <Bell size={48} className="text-gray-300 mb-4" />
        <h2 className="text-lg font-bold text-gray-700 mb-2">Open in Telegram</h2>
        <p className="text-sm text-gray-500 max-w-xs">
          Alerts are only available inside the Telegram Mini App. Open @IndexGebeyaBot in Telegram to use this feature.
        </p>
      </div>
    );
  }

  // Loading state
  if (loading && alerts.length === 0) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Loader2 size={32} className="animate-spin text-brand-600" />
      </div>
    );
  }

  // Error state
  if (error && alerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
        <AlertCircle size={48} className="text-red-400 mb-4" />
        <h2 className="text-lg font-bold text-gray-700 mb-2">Could not load alerts</h2>
        <p className="text-sm text-gray-500 mb-4">{error}</p>
        <button
          onClick={() => { fetchAlerts(); fetchMatchHistory(); }}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors"
        >
          <RefreshCw size={16} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="px-4 pt-4 pb-24">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-gray-900">My Alerts</h1>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors shadow-sm"
        >
          <Plus size={16} />
          <span>New Alert</span>
        </button>
      </div>

      {/* Active Alerts Section */}
      {alerts.length > 0 ? (
        <div className="space-y-3 mb-6">
          {alerts.map((alert) => {
            const prefs = parsePreferences(alert.preferences);
            const isBusy = submittingActionId === alert.id;

            return (
              <div
                key={alert.id}
                className={`bg-white rounded-2xl p-4 shadow-sm border transition-all ${
                  alert.is_active ? 'border-gray-100' : 'border-gray-100 opacity-70'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 truncate">{alert.query_text}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Max: {formatPrice(alert.max_price)} &middot; Created {formatDate(alert.created_at)}
                    </p>
                  </div>
                  <span
                    className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                      alert.is_active
                        ? 'bg-green-100 text-green-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}
                  >
                    {alert.is_active ? 'ACTIVE' : 'PAUSED'}
                  </span>
                </div>

                {/* Smart filter toggles */}
                {Object.keys(prefs).length > 0 && (() => {
                  const strictEntries = Object.entries(prefs).filter(
                    ([key, val]) => (key === 'strict_brand' || key === 'strict_model') && val === true
                  );
                  if (strictEntries.length === 0) return null;
                  const labelMap = { strict_brand: 'Strict Brand', strict_model: 'Strict Model' };
                  return (
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {strictEntries.map(([key]) => (
                        <span
                          key={key}
                          className="px-2 py-0.5 rounded-lg text-[10px] font-medium bg-blue-100 text-blue-700"
                        >
                          {labelMap[key] || key.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  );
                })()}

                {/* Action buttons */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handlePause(alert.id)}
                    disabled={isBusy}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50"
                  >
                    {isBusy ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : alert.is_active ? (
                      <Pause size={14} />
                    ) : (
                      <Play size={14} />
                    )}
                    {alert.is_active ? 'Pause' : 'Resume'}
                  </button>
                  <button
                    onClick={() => handleDelete(alert.id)}
                    disabled={isBusy}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Empty state */
        <div className="flex flex-col items-center justify-center py-16 text-center bg-white rounded-2xl border border-gray-100 mb-6">
          <Bell size={40} className="text-gray-300 mb-3" />
          <h3 className="text-base font-bold text-gray-700 mb-1">No alerts yet</h3>
          <p className="text-sm text-gray-500 mb-4 max-w-xs">
            You don't have any alerts yet. Create one to get notified when matching items are posted.
          </p>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-4 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors"
          >
            Create Your First Alert
          </button>
        </div>
      )}

      {/* Match History Section */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <History size={18} className="text-gray-500" />
          <h2 className="text-base font-bold text-gray-900">Recent Matches</h2>
        </div>

        {matchHistory.length > 0 ? (
          <div className="space-y-2">
            {matchHistory.map((match) => (
              <button
                key={match.id}
                onClick={() => navigate(`/item/${match.item_id}`)}
                className="w-full bg-white rounded-2xl p-4 shadow-sm border border-gray-100 flex items-center gap-3 text-left hover:bg-gray-50 transition-colors"
              >
                {/* Match tier badge */}
                <div className="shrink-0">
                  {match.match_tier === 'bullseye' ? (
                    <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
                      <div className="w-5 h-5 rounded-full bg-green-500" />
                    </div>
                  ) : (
                    <div className="w-10 h-10 rounded-full border-2 border-amber-300 flex items-center justify-center">
                      <div className="w-3 h-3 rounded-full border-2 border-amber-400" />
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <h4 className="text-sm font-semibold text-gray-900 truncate">
                    {match.item_title || 'Untitled Item'}
                  </h4>
                  <p className="text-xs text-gray-500 mt-0.5 truncate">
                    {match.alert_query_text && `Alert: "${match.alert_query_text}"`}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    {match.item_price && (
                      <span className="text-xs font-bold text-green-600">
                        {formatPrice(match.item_price)}
                      </span>
                    )}
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold ${
                        match.match_tier === 'bullseye'
                          ? 'bg-green-100 text-green-700'
                          : 'bg-amber-100 text-amber-700'
                      }`}
                    >
                      {match.match_tier?.toUpperCase()}
                    </span>
                    <span className="text-[10px] text-gray-400 ml-auto">
                      {formatDate(match.created_at)}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 bg-white rounded-2xl border border-gray-100">
            <History size={32} className="text-gray-300 mx-auto mb-2" />
            <p className="text-sm text-gray-500">No matches yet</p>
            <p className="text-xs text-gray-400 mt-1">Matches will appear here when items matching your alerts are posted.</p>
          </div>
        )}
      </div>

      {/* Create Alert Modal — only rendered when open for fresh mount */}
      {isCreateModalOpen && (
        <AlertModal
          isOpen={isCreateModalOpen}
          onClose={handleModalClose}
          initialQuery=""
          currentPrice={null}
        />
      )}
    </div>
  );
};

export default AlertsPage;
