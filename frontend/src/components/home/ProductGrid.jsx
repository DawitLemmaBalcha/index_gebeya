import React, { useRef, useEffect, useState } from 'react';
import ItemCard from '../ItemCard';
import { WifiOff, Camera, Search, ArrowDown } from 'lucide-react';
import { API_BASE_URL } from '../../config';

const ProductGrid = ({ loading, error, items, onRetry, onNavigate, visualResults, searchResults, onClearVisual, activeCategory, activeSubCategory, hasMore, isFetchingMore, onLoadMore, isSearchingText = false, isSearchingVisual = false, viewMode = 'grid', setViewMode }) => {
  
  const [refreshing, setRefreshing] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const touchStartY = useRef(0);
  const mainRef = useRef(null);

  // Pull-to-refresh touch handlers
  const handleTouchStart = (e) => {
    if (window.scrollY === 0) touchStartY.current = e.touches[0].clientY;
  };
  const handleTouchMove = (e) => {
    if (touchStartY.current) {
      const d = e.touches[0].clientY - touchStartY.current;
      if (d > 0) setPullDistance(Math.min(d, 80));
    }
  };
  const handleTouchEnd = async () => {
    if (pullDistance > 60) {
      setRefreshing(true);
      await onRetry();
      setRefreshing(false);
    }
    setPullDistance(0);
    touchStartY.current = 0;
  };

  // Compact results bar
  const CompactBar = () => (
    <div className="flex items-center justify-between mb-4 px-1">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        {visualResults ? (
          <span className="flex items-center gap-1 bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-bold text-[11px]"><Camera size={12}/> Visual ({items.length})</span>
        ) : searchResults ? (
          <span className="flex items-center gap-1 bg-purple-50 text-purple-700 px-2 py-0.5 rounded-full font-bold text-[11px]"><Search size={12}/> Results ({items.length})</span>
        ) : activeCategory !== "All" ? (
          <span className="text-[11px] font-medium">{activeCategory}{activeSubCategory !== "All" && ` › ${activeSubCategory}`}</span>
        ) : (
          <span className="text-[11px] text-slate-400">Explore</span>
        )}
        {visualResults && <button onClick={onClearVisual} className="text-slate-400 hover:text-slate-600 underline text-[10px]">Clear</button>}
      </div>
      {items.length > 0 && (
        <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5 shadow-xs shrink-0">
          <button onClick={() => setViewMode("grid")} className={`p-1 rounded ${viewMode === 'grid' ? 'bg-amber-500 text-white' : 'text-slate-400 hover:text-slate-600'}`} title="Grid">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2V5zM11 11a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2v-2z"/></svg>
          </button>
          <button onClick={() => setViewMode("list")} className={`p-1 rounded ${viewMode === 'list' ? 'bg-amber-500 text-white' : 'text-slate-400 hover:text-slate-600'}`} title="List">
            <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"/></svg>
          </button>
        </div>
      )}
    </div>
  );

  // Grid skeleton card
  const SkeletonGrid = () => (
    <div className="bg-white rounded-2xl border border-slate-200 p-3 animate-pulse">
      <div className="w-full aspect-square bg-gray-200 rounded-xl mb-3" />
      <div className="h-3 bg-gray-200 rounded w-3/4 mb-2" />
      <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
      <div className="h-4 bg-gray-200 rounded w-1/3" />
    </div>
  );

  // List skeleton card
  const SkeletonList = () => (
    <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4 animate-pulse">
      <div className="w-16 h-16 rounded-xl bg-gray-200 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3 bg-gray-200 rounded w-1/3" />
        <div className="h-4 bg-gray-200 rounded w-3/4" />
        <div className="h-3 bg-gray-200 rounded w-1/2" />
      </div>
      <div className="w-16 h-8 bg-gray-200 rounded-lg shrink-0" />
    </div>
  );

  // Infinite scroll sentinel
  const sentinelRef = useRef(null);
  useEffect(() => {
    if (!hasMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && !isFetchingMore) onLoadMore();
    }, { rootMargin: '200px' });
    if (sentinelRef.current) observer.observe(sentinelRef.current);
    return () => observer.disconnect();
  }, [hasMore, isFetchingMore, onLoadMore]);

  if (loading) return (
    <main className="max-w-6xl mx-auto px-4 py-4">
      <CompactBar />
      <div className={viewMode === 'list' ? 'space-y-3' : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4'}>
        {[...Array(8)].map((_, i) => viewMode === 'list' ? <SkeletonList key={i} /> : <SkeletonGrid key={i} />)}
      </div>
    </main>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center h-64 text-center p-4 bg-red-50 rounded-2xl border border-red-100">
      <div className="bg-red-100 p-3 rounded-full mb-3"><WifiOff className="text-red-500" size={32} /></div>
      <h3 className="text-lg font-bold text-red-900">Connection Failed</h3>
      <p className="text-red-600 mb-4 text-sm">{error}</p>
      <button onClick={onRetry} className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 font-medium text-sm">Try Again</button>
    </div>
  );

  // Search loading skeleton
  if (isSearchingText || isSearchingVisual) {
    return (
      <main className="max-w-6xl mx-auto px-4 py-4">
        <div className="mb-4"><p className="text-sm text-gray-500">{isSearchingText ? "Searching..." : "Analyzing image..."}</p></div>
        <div className={viewMode === 'list' ? 'space-y-3' : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4'}>
          {[...Array(6)].map((_, i) => viewMode === 'list' ? <SkeletonList key={i} /> : <SkeletonGrid key={i} />)}
        </div>
      </main>
    );
  }

  return (
    <main ref={mainRef} className="max-w-6xl mx-auto px-4 py-4"
      onTouchStart={handleTouchStart} onTouchMove={handleTouchMove} onTouchEnd={handleTouchEnd}>
      {/* Pull-to-refresh indicator */}
      {pullDistance > 0 && (
        <div className="flex justify-center py-2" style={{ opacity: Math.min(pullDistance / 60, 1) }}>
          <ArrowDown size={20} className={`text-amber-500 transition-transform ${pullDistance > 60 ? 'rotate-180' : ''}`} />
          <span className="text-xs text-slate-400 ml-2">{pullDistance > 60 ? 'Release to refresh' : 'Pull to refresh'}</span>
        </div>
      )}
      {refreshing && (
        <div className="flex justify-center py-2">
          <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-amber-500"></div>
        </div>
      )}
      <CompactBar />
      {items.length === 0 ? (
        <div className="text-center text-gray-400 py-12">No items found.</div>
      ) : viewMode === 'list' ? (
        <div className="space-y-3">
          {items.map(item => (
            <div key={item.id} onClick={() => onNavigate(`/item/${item.id}`)} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex items-center gap-4 hover:border-amber-400 transition-all cursor-pointer">
              <img src={`${API_BASE_URL}/media/${item.image_path || item.images?.[0]}`} alt={item.title} className="w-16 h-16 rounded-xl object-cover shrink-0" onError={e => { e.target.src = 'https://placehold.co/400x400?text=No+Image'; }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-amber-700">@{item.channel?.username || 'unknown'}</span>
                  <span className="text-[10px] text-slate-400">{item.category}</span>
                </div>
                <h4 className="font-bold text-slate-900 text-sm leading-snug truncate">{item.title}</h4>
                <span className="text-sm font-bold text-green-600 mt-1">{item.price ? `${item.price.toLocaleString()} ETB` : 'Ask for Price'}</span>
              </div>
              <button className="px-3 py-1.5 bg-slate-900 text-white text-xs font-bold rounded-lg shrink-0">View</button>
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map(item => <ItemCard key={item.id} item={item} apiUrl={API_BASE_URL} onSelect={(itm) => onNavigate(`/item/${itm.id}`)} />)}
        </div>
      )}
      {isFetchingMore && (
        <div className={viewMode === 'list' ? 'space-y-3 mt-4' : 'grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mt-4'}>
          {[...Array(4)].map((_, i) => viewMode === 'list' ? <SkeletonList key={i} /> : <SkeletonGrid key={i} />)}
        </div>
      )}
      <div ref={sentinelRef} className="h-1" />
      {!hasMore && items.length > 0 && (
        <p className="text-center text-gray-400 py-6 text-sm">You've seen everything!</p>
      )}
    </main>
  );
};
export default ProductGrid;
