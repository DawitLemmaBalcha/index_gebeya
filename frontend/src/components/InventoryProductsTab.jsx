import React, { useEffect, useRef } from 'react';
import { Search, Filter, ChevronDown, Loader2, Package, RefreshCw, AlertCircle } from 'lucide-react';
import ItemCard from './ItemCard';
import StatusBadge from './StatusBadge';

/**
 * TECH-23: Products tab within ChannelInventory modal.
 * Displays a filterable, sortable, infinitely-scrollable product grid.
 */
const InventoryProductsTab = ({ channelId, channel, onSelectProduct, inventory, onMarkSold }) => {
  const sentinelRef = useRef(null);

  const {
    items,
    loading,
    error,
    hasMore,
    statusFilter,
    sortBy,
    searchQuery,
    fetchItems,
    fetchMore,
    setStatusFilter,
    setSortBy,
    setSearchQuery,
  } = inventory;

  // Initial fetch
  useEffect(() => {
    fetchItems(channelId);
  }, [channelId]);

  // Infinite scroll observer
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !loading) {
          fetchMore(channelId);
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, loading, channelId, fetchMore]);

  const statusOptions = [
    { value: 'all', label: 'All' },
    { value: 'active', label: 'Active' },
    { value: 'sold', label: 'Sold' },
    { value: 'reported', label: 'Reported' },
  ];

  const sortOptions = [
    { value: 'recent', label: 'Most Recent' },
    { value: 'price_asc', label: 'Price: Low-High' },
    { value: 'price_desc', label: 'Price: High-Low' },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Search bar */}
      <div className="px-4 pt-3 pb-2">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search products..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(channelId, e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-gray-100 rounded-xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-200"
          />
        </div>
      </div>

      {/* Filter & Sort row */}
      <div className="px-4 pb-2 flex items-center gap-2 overflow-x-auto">
        <Filter size={14} className="text-gray-400 shrink-0" />
        <div className="flex gap-1.5">
          {statusOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatusFilter(channelId, opt.value)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium whitespace-nowrap transition-colors ${
                statusFilter === opt.value
                  ? 'bg-brand-100 text-brand-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Sort dropdown */}
        <div className="ml-auto relative">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(channelId, e.target.value)}
            className="appearance-none pl-2.5 pr-7 py-1 rounded-full text-[11px] font-medium bg-gray-100 text-gray-600 focus:outline-none cursor-pointer"
          >
            {sortOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
        </div>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {/* Loading state */}
        {loading && items.length === 0 && (
          <div className="flex justify-center items-center py-16">
            <Loader2 size={32} className="animate-spin text-brand-600" />
          </div>
        )}

        {/* Error state */}
        {error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <AlertCircle size={40} className="text-red-400 mb-3" />
            <p className="text-sm text-gray-600 mb-3">{error}</p>
            <button
              onClick={() => fetchItems(channelId)}
              className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium"
            >
              <RefreshCw size={14} /> Retry
            </button>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && items.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Package size={40} className="text-gray-300 mb-3" />
            <p className="text-sm text-gray-500">No products found</p>
          </div>
        )}

        {/* Product grid */}
        {items.length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-3">
              {items.map((item) => (
                <div key={item.id} className="relative cursor-pointer" onClick={() => onSelectProduct(item)}>
                  <ItemCard item={item} apiUrl="" variant="inventory" onSelect={() => {}} onMarkSold={onMarkSold} onEdit={onSelectProduct} />
                  <div className="absolute top-2 right-2 z-10">
                    <StatusBadge status={item.status} indexingPaused={channel?.indexing_paused} />
                  </div>
                </div>
              ))}
            </div>

            {/* Infinite scroll sentinel */}
            <div ref={sentinelRef} className="h-8 flex items-center justify-center mt-3">
              {loading && <Loader2 size={20} className="animate-spin text-gray-400" />}
              {!hasMore && items.length > 0 && (
                <p className="text-xs text-gray-400">All products loaded</p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default InventoryProductsTab;
