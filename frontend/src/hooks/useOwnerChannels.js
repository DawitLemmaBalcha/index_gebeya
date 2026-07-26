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

  // TECH-19: Toggle pause/resume for a channel
  const togglePause = useCallback(async (channelId, pause) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(
        `${API_BASE_URL}/channels/${channelId}/pause?init_data=${encodeURIComponent(initData)}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            ...analyticsHeaders,
          },
          body: JSON.stringify({ indexing_paused: pause }),
        }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to ${pause ? 'pause' : 'resume'} channel: ${response.status}`);
      }

      await response.json();
      // Refresh the channel list
      await fetchChannels();
    } catch (e) {
      console.error('useOwnerChannels togglePause error:', e);
      setError(e.message);
      throw e;
    }
  }, [fetchChannels]);

  // TECH-19: Remove a channel (soft-delete with auto-leave)
  const removeChannel = useCallback(async (channelId) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(
        `${API_BASE_URL}/channels/${channelId}?init_data=${encodeURIComponent(initData)}`,
        {
          method: 'DELETE',
          headers: { ...analyticsHeaders },
        }
      );

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to remove channel: ${response.status}`);
      }

      await response.json();
      // Refresh the channel list (removed channel will disappear)
      await fetchChannels();
    } catch (e) {
      console.error('useOwnerChannels removeChannel error:', e);
      setError(e.message);
      throw e;
    }
  }, [fetchChannels]);

  return {
    channels,
    loading,
    error,
    fetchChannels,
    hasBeenFetched,
    togglePause,
    removeChannel,
  };
}
