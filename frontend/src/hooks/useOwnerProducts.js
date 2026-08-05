import { useState, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

// Module-level cache for instant back navigation (house pattern)
let _productsCache = null;

/**
 * UAT round-2 (FIX 1): the hub Boost tab's "Your products" picker data.
 * Per-channel items come from the SAME endpoint useChannelInventory uses
 * (GET /channels/{channel_id}/items) with the same URL shape
 * (limit=20&offset=0&sort=recent — the endpoint defaults). The fan-out
 * across the owner's channels mirrors useBoosts.fetchBoosts. Kill-switch
 * surface: with MONETIZATION_ENABLED=0 the hub never renders (status is
 * null), so this hook is only exercised when monetization is on.
 */
export function useOwnerProducts() {
  const [products, setProducts] = useState(() => _productsCache ? _productsCache : []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasBeenFetched, setHasBeenFetched] = useState(() => !!_productsCache);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const fetchProducts = useCallback(async (channels) => {
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
            `${API_BASE_URL}/channels/${channel.id}/items?init_data=${encodeURIComponent(initData)}&limit=20&offset=0&sort=recent`,
            { headers: { ...getAnalyticsHeaders() } }
          );
          if (!res.ok) throw new Error(`Items unavailable (${res.status})`);
          return res.json();
        })
      );
      const merged = results.flat();
      _productsCache = merged;
      setProducts(merged);
      setHasBeenFetched(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return { products, loading, error, hasBeenFetched, fetchProducts };
}
