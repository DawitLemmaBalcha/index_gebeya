import { useState, useCallback, useEffect } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

/**
 * NB-43: Boost purchase flow — quote, Stars invoice, activation refresh.
 * Mirrors the getInitData / getAnalyticsHeaders patterns from
 * useChannelInventory.js. Quote fetch is the kill-switch surface: when
 * MONETIZATION_ENABLED=0 the backend returns 503 and the section hides.
 *
 * UAT round-2 (FIX 1): itemId is MUTABLE — the hub's inline product
 * picker re-quotes the newly tapped item by changing the itemId prop.
 * A reset effect clears the stale quote/active-boost/error on every item
 * change; the `?item` deep-link path is unchanged (initial mount resets
 * null → null, a no-op, then refreshQuote() fetches once).
 */
export function useBoost(itemId) {
  const [quote, setQuote] = useState(null);
  const [activeBoost, setActiveBoost] = useState(null);
  const [boosting, setBoosting] = useState(false);
  const [error, setError] = useState(null);

  // FIX 1: item switched (picker selection) → drop the previous item's
  // quote so the UI never shows stale price data for the new selection.
  useEffect(() => {
    setQuote(null);
    setActiveBoost(null);
    setError(null);
  }, [itemId]);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const refreshQuote = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }
    try {
      const res = await fetch(
        `${API_BASE_URL}/items/${itemId}/boost-quote?init_data=${encodeURIComponent(initData)}`,
        { headers: { ...getAnalyticsHeaders() } }
      );
      if (!res.ok) {
        setQuote(null);
        setActiveBoost(null);
        throw new Error(`Quote unavailable (${res.status})`);
      }
      const data = await res.json();
      setQuote(data);
      setActiveBoost(data.active_boost || null);
    } catch (e) {
      setError(e.message);
    }
  }, [itemId]);

  const payWithStars = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return false;
    }
    setBoosting(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/items/${itemId}/boost-order?init_data=${encodeURIComponent(initData)}`,
        { method: 'POST', headers: { ...getAnalyticsHeaders() } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Order failed (${res.status})`);
      }
      const order = await res.json();
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) throw new Error('Invoices unavailable outside Telegram');
      const status = await new Promise((resolve) => {
        tg.openInvoice(order.invoice_url, (s) => resolve(s));
      });
      if (status === 'paid') {
        await refreshQuote();
        return true;
      }
      return false; // canceled/failed — nothing was charged
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBoosting(false);
    }
  }, [itemId, refreshQuote]);

  return {
    quote,
    activeBoost,
    // NB-43 UAT: additive boostability signal from the quote endpoint —
    // false for sold/inactive/soft-deleted items (and 503 kill switch when
    // the quote never arrives). The UI hides the boost section on false.
    boostable: quote?.boostable ?? false,
    boosting,
    error,
    payWithStars,
    refreshQuote,
  };
}
