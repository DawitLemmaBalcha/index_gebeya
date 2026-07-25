import { useState, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

// Module-level cache for instant back navigation
let _channelsCache = null;

export function useOwnerChannels() {
  const [channels, setChannels] = useState(() => _channelsCache ? _channelsCache : []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasBeenFetched, setHasBeenFetched] = useState(() => !!_channelsCache);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const fetchChannels = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(`${API_BASE_URL}/channels/mine?init_data=${encodeURIComponent(initData)}`, {
        headers: { ...analyticsHeaders },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch channels: ${response.status}`);
      }

      const data = await response.json();
      _channelsCache = data;
      setChannels(data);
      setHasBeenFetched(true);
    } catch (e) {
      console.error('useOwnerChannels fetchChannels error:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    channels,
    loading,
    error,
    fetchChannels,
    hasBeenFetched,
  };
}
