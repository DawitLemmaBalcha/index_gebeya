import { useState, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

/**
 * NB-46: Subscription status + purchase flow.
 * getStatus() powers the StoresPage subscription card (extra_alerts,
 * credit_remaining). createOrder opens the native Stars subscription
 * invoice; applyCreditBoost consumes one all-in-one monthly credit.
 */
export function useSubscription() {
  const [status, setStatus] = useState(null); // SubscriptionStatusResponse
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const getStatus = useCallback(async () => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return null;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/subscriptions/status?init_data=${encodeURIComponent(initData)}`,
        { headers: { ...getAnalyticsHeaders() } }
      );
      if (!res.ok) {
        setStatus(null);
        throw new Error(`Status unavailable (${res.status})`);
      }
      const data = await res.json();
      setStatus(data);
      return data;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const openInvoice = useCallback(async (product) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return false;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/subscriptions/order?init_data=${encodeURIComponent(initData)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAnalyticsHeaders() },
          body: JSON.stringify({ product }),
        }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Order failed (${res.status})`);
      }
      const order = await res.json();
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) throw new Error('Invoices unavailable outside Telegram');
      const invoiceStatus = await new Promise((resolve) => {
        tg.openInvoice(order.invoice_url, (s) => resolve(s));
      });
      if (invoiceStatus === 'paid') {
        await getStatus();
        return true;
      }
      return false; // canceled/failed — nothing charged
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [getStatus]);

  const applyCreditBoost = useCallback(async (itemId) => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return false;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE_URL}/items/${itemId}/boost-credit?init_data=${encodeURIComponent(initData)}`,
        { method: 'POST', headers: { ...getAnalyticsHeaders() } }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Credit boost failed (${res.status})`);
      }
      await getStatus();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setLoading(false);
    }
  }, [getStatus]);

  return { status, loading, error, getStatus, openInvoice, applyCreditBoost };
}
