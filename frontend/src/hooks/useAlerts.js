import { useState, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

// Module-level cache for instant back navigation
let _alertsCache = null;
let _matchesCache = null;

export function useAlerts() {
  const [alerts, setAlerts] = useState(() => _alertsCache ? _alertsCache : []);
  const [matchHistory, setMatchHistory] = useState(() => _matchesCache ? _matchesCache : []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasBeenFetched, setHasBeenFetched] = useState(() => !!_alertsCache);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const fetchAlerts = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(`${API_BASE_URL}/alerts/?init_data=${encodeURIComponent(initData)}`, {
        headers: { ...analyticsHeaders },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch alerts: ${response.status}`);
      }

      const data = await response.json();
      _alertsCache = data;
      setAlerts(data);
      setHasBeenFetched(true);
    } catch (e) {
      console.error('useAlerts fetchAlerts error:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchMatchHistory = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(`${API_BASE_URL}/alerts/matches?init_data=${encodeURIComponent(initData)}`, {
        headers: { ...analyticsHeaders },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch match history: ${response.status}`);
      }

      const data = await response.json();
      _matchesCache = data;
      setMatchHistory(data);
    } catch (e) {
      console.error('useAlerts fetchMatchHistory error:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const pauseAlert = useCallback(async (alertId) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(
        `${API_BASE_URL}/alerts/${alertId}/pause?init_data=${encodeURIComponent(initData)}`,
        {
          method: 'PATCH',
          headers: { ...analyticsHeaders },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to toggle alert: ${response.status}`);
      }

      const data = await response.json();

      // Update local state and cache
      setAlerts((prev) => {
        const updated = prev.map((a) =>
          a.id === alertId ? { ...a, is_active: data.is_active } : a
        );
        _alertsCache = updated;
        return updated;
      });
    } catch (e) {
      console.error('useAlerts pauseAlert error:', e);
      setError(e.message);
    }
  }, []);

  const deleteAlert = useCallback(async (alertId) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(
        `${API_BASE_URL}/alerts/${alertId}?init_data=${encodeURIComponent(initData)}`,
        {
          method: 'DELETE',
          headers: { ...analyticsHeaders },
        }
      );

      if (!response.ok) {
        throw new Error(`Failed to delete alert: ${response.status}`);
      }

      // Remove from local state and update cache
      setAlerts((prev) => {
        const updated = prev.filter((a) => a.id !== alertId);
        _alertsCache = updated;
        return updated;
      });
    } catch (e) {
      console.error('useAlerts deleteAlert error:', e);
      setError(e.message);
    }
  }, []);

  return {
    alerts,
    matchHistory,
    loading,
    error,
    fetchAlerts,
    fetchMatchHistory,
    pauseAlert,
    deleteAlert,
    hasBeenFetched,
  };
}
