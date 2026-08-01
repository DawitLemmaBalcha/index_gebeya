import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';

/**
 * TECH-23: Hook for fetching, filtering, paginating channel items.
 * Follows the useOwnerChannels / useShop pattern.
 */
export function useChannelInventory() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(true);
  const [offset, setOffset] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('recent');
  const [searchQuery, setSearchQuery] = useState('');

  const debounceTimer = useRef(null);

  const getInitData = () => {
    try {
      return window.Telegram?.WebApp?.initData || null;
    } catch {
      return null;
    }
  };

  const getUrl = (channelId, useOffset) => {
    const initData = getInitData();
    if (!initData) return null;

    let url = `${API_BASE_URL}/channels/${channelId}/items?init_data=${encodeURIComponent(initData)}`;
    url += `&limit=20&offset=${useOffset}&sort=${sortBy}`;
    if (statusFilter !== 'all') {
      url += `&status=${encodeURIComponent(statusFilter)}`;
    }
    if (searchQuery) {
      url += `&search=${encodeURIComponent(searchQuery)}`;
    }
    return url;
  };

  const fetchItems = useCallback(async (channelId, reset = false) => {
    const targetOffset = reset ? 0 : offset;
    const url = getUrl(channelId, targetOffset);
    if (!url) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const analyticsHeaders = getAnalyticsHeaders();
      const response = await fetch(url, { headers: { ...analyticsHeaders } });

      if (!response.ok) {
        throw new Error(`Failed to fetch items: ${response.status}`);
      }

      const data = await response.json();

      if (reset) {
        setItems(data);
        setOffset(0);
      } else {
        setItems(prev => [...prev, ...data]);
      }

      setHasMore(data.length === 20);
      setTotalCount(prev => reset ? data.length : prev + data.length);
    } catch (e) {
      console.error('useChannelInventory fetchItems error:', e);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [offset, sortBy, statusFilter, searchQuery]);

  const fetchMore = useCallback((channelId) => {
    if (loading || !hasMore) return;
    const newOffset = offset + 20;
    setOffset(newOffset);
    // We use the new offset directly to avoid stale closure
    const url = getUrl(channelId, newOffset);
    if (!url) return;

    setLoading(true);

    const analyticsHeaders = getAnalyticsHeaders();
    fetch(url, { headers: { ...analyticsHeaders } })
      .then(r => {
        if (!r.ok) throw new Error(`Failed: ${r.status}`);
        return r.json();
      })
      .then(data => {
        setItems(prev => [...prev, ...data]);
        setHasMore(data.length === 20);
      })
      .catch(e => {
        console.error('useChannelInventory fetchMore error:', e);
        setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [loading, hasMore, offset, sortBy, statusFilter, searchQuery]);

  const setStatusFilterAndRefresh = useCallback((channelId, val) => {
    setStatusFilter(val);
    setOffset(0);
    setItems([]);
    setHasMore(true);
    // Fetch immediately with new filter
    const initData = getInitData();
    if (!initData) return;
    let url = `${API_BASE_URL}/channels/${channelId}/items?init_data=${encodeURIComponent(initData)}`;
    url += `&limit=20&offset=0&sort=${sortBy}`;
    if (val !== 'all') url += `&status=${encodeURIComponent(val)}`;
    if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

    setLoading(true);
    const analyticsHeaders = getAnalyticsHeaders();
    fetch(url, { headers: { ...analyticsHeaders } })
      .then(r => r.json())
      .then(data => { setItems(data); setHasMore(data.length === 20); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [sortBy, searchQuery]);

  const setSortByAndRefresh = useCallback((channelId, val) => {
    setSortBy(val);
    setOffset(0);
    setItems([]);
    setHasMore(true);
    const initData = getInitData();
    if (!initData) return;
    let url = `${API_BASE_URL}/channels/${channelId}/items?init_data=${encodeURIComponent(initData)}`;
    url += `&limit=20&offset=0&sort=${val}`;
    if (statusFilter !== 'all') url += `&status=${encodeURIComponent(statusFilter)}`;
    if (searchQuery) url += `&search=${encodeURIComponent(searchQuery)}`;

    setLoading(true);
    const analyticsHeaders = getAnalyticsHeaders();
    fetch(url, { headers: { ...analyticsHeaders } })
      .then(r => r.json())
      .then(data => { setItems(data); setHasMore(data.length === 20); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, [statusFilter, searchQuery]);

  const handleSearchChange = useCallback((channelId, val) => {
    setSearchQuery(val);

    if (debounceTimer.current) clearTimeout(debounceTimer.current);

    debounceTimer.current = setTimeout(() => {
      setOffset(0);
      setItems([]);
      setHasMore(true);
      const initData = getInitData();
      if (!initData) return;
      let url = `${API_BASE_URL}/channels/${channelId}/items?init_data=${encodeURIComponent(initData)}`;
      url += `&limit=20&offset=0&sort=${sortBy}`;
      if (statusFilter !== 'all') url += `&status=${encodeURIComponent(statusFilter)}`;
      if (val) url += `&search=${encodeURIComponent(val)}`;

      setLoading(true);
      const analyticsHeaders = getAnalyticsHeaders();
      fetch(url, { headers: { ...analyticsHeaders } })
        .then(r => r.json())
        .then(data => { setItems(data); setHasMore(data.length === 20); })
        .catch(e => setError(e.message))
        .finally(() => setLoading(false));
    }, 400);
  }, [sortBy, statusFilter]);

  const postAction = useCallback(async (channelId, path, method = 'POST') => {
    const initData = getInitData();
    if (!initData) {
      setError('NOT_IN_TELEGRAM');
      return;
    }

    const analyticsHeaders = getAnalyticsHeaders();
    const response = await fetch(
      `${API_BASE_URL}${path}?init_data=${encodeURIComponent(initData)}`,
      {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...analyticsHeaders,
        },
        body: method !== 'GET' ? JSON.stringify({ init_data: initData }) : undefined,
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Action failed: ${response.status}`);
    }

    return response.json();
  }, []);

  const markSold = useCallback(async (channelId, itemId) => {
    // Optimistic UI update — mark as sold immediately
    setItems(prev => prev.map(item => 
      item.id === itemId ? { ...item, status: 'sold' } : item
    ));
    const result = await postAction(channelId, `/items/${itemId}/sold`);
    // Refresh to sync with backend
    await fetchItems(channelId, true);
    return result;
  }, [postAction, fetchItems]);

  const relist = useCallback(async (channelId, itemId) => {
    // Optimistic UI update — mark as active immediately
    setItems(prev => prev.map(item => 
      item.id === itemId ? { ...item, status: 'active' } : item
    ));
    const initData = getInitData();
    if (!initData) throw new Error('NOT_IN_TELEGRAM');

    const analyticsHeaders = getAnalyticsHeaders();
    const response = await fetch(
      `${API_BASE_URL}/items/${itemId}/relist`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...analyticsHeaders,
        },
        body: JSON.stringify({ init_data: initData }),
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Relist failed: ${response.status}`);
    }

    await fetchItems(channelId, true);
    return response.json();
  }, [fetchItems]);

  const clearReports = useCallback(async (channelId, itemId) => {
    const result = await postAction(channelId, `/items/${itemId}/clear-reports`);
    await fetchItems(channelId, true);
    return result;
  }, [postAction, fetchItems]);

  const updateItem = useCallback(async (channelId, itemId, updateData) => {
    const initData = getInitData();
    if (!initData) throw new Error('NOT_IN_TELEGRAM');

    const analyticsHeaders = getAnalyticsHeaders();
    const response = await fetch(
      `${API_BASE_URL}/items/${itemId}?init_data=${encodeURIComponent(initData)}`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...analyticsHeaders,
        },
        body: JSON.stringify(updateData),
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Update failed: ${response.status}`);
    }

    await fetchItems(channelId, true);
    return response.json();
  }, [fetchItems]);

  const deleteItem = useCallback(async (channelId, itemId) => {
    const initData = getInitData();
    if (!initData) throw new Error('NOT_IN_TELEGRAM');

    const analyticsHeaders = getAnalyticsHeaders();
    const response = await fetch(
      `${API_BASE_URL}/items/${itemId}?init_data=${encodeURIComponent(initData)}`,
      {
        method: 'DELETE',
        headers: { ...analyticsHeaders },
      }
    );

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `Delete failed: ${response.status}`);
    }

    // Remove from local list immediately + refresh from backend
    setItems(prev => prev.filter(item => item.id !== itemId));
    await fetchItems(channelId, true);
    return true;
  }, [fetchItems]);

  return {
    items,
    loading,
    error,
    hasMore,
    offset,
    totalCount,
    statusFilter,
    sortBy,
    searchQuery,
    fetchItems,
    fetchMore,
    setStatusFilter: (channelId, val) => setStatusFilterAndRefresh(channelId, val),
    setSortBy: (channelId, val) => setSortByAndRefresh(channelId, val),
    setSearchQuery: (channelId, val) => handleSearchChange(channelId, val),
    markSold,
    relist,
    clearReports,
    updateItem,
    deleteItem,
  };
}
