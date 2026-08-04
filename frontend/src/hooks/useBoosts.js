import { useState, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

// Module-level cache for instant back navigation (house pattern)
let _boostsCache = null;

/**
 * NB-48: active boosts across the owner's channels for the Stores boost
 * management card (blueprint §3). fetchBoosts(channels) fans out to
 * GET /channels/{id}/boosts per channel, merges, and sorts by ends_at
 * ascending (soonest-expiring first). Kill-switch surface: when
 * MONETIZATION_ENABLED=0 the backend returns 503 and the card hides.
 */
export function useBoosts() {
  const [boosts, setBoosts] = useState(() => _boostsCache ? _boostsCache : []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasBeenFetched, setHasBeenFetched] = useState(() => !!_boostsCache);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const fetchBoosts = useCallback(async (channels) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const results = await Promise.all(
        (channels || []).map(async (channel) => {
          const res = await fetch(
            `${API_BASE_URL}/channels/${channel.id}/boosts?init_data=${encodeURIComponent(initData)}`,
            { headers: { ...getAnalyticsHeaders() } }
          );
          if (!res.ok) throw new Error(`Boosts unavailable (${res.status})`);
          return res.json();
        })
      );
      const merged = results
        .flat()
        .sort((a, b) => new Date(a.ends_at) - new Date(b.ends_at));
      _boostsCache = merged;
      setBoosts(merged);
      setHasBeenFetched(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return { boosts, loading, error, hasBeenFetched, fetchBoosts };
}
