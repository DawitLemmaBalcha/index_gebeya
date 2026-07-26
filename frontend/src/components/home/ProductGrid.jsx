import React, { useRef, useEffect, useState } from 'react';
import ItemCard from '../ItemCard';
import { WifiOff, Camera, Search } from 'lucide-react';
import { API_BASE_URL } from '../../config';

const ProductGrid = ({ loading, error, items, onRetry, onNavigate, visualResults, searchResults, onClearVisual, activeCategory, activeSubCategory, hasMore, isFetchingMore, onLoadMore, isSearchingText = false, isSearchingVisual = false }) => {
  
  const [viewMode, setViewMode] = useState('grid');

  // Status Line
  const StatusLine = () => (
    <div className="mb-6 flex items-baseline gap-2 text-sm text-gray-500">
       {visualResults ? (
           <div className="flex items-center gap-2 w-full">
               <span className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full font-bold flex items-center gap-1"><Camera size={14}/> Visual Results</span>
               <button onClick={onClearVisual} className="text-gray-400 underline hover:text-gray-700 text-xs">Clear</button>
           </div>
       ) : searchResults ? (
           <div className="flex items-center gap-2 w-full">
               <span className="bg-purple-100 text-purple-700 px-3 py-1 rounded-full font-bold flex items-center gap-1"><Search size={14}/> Results ({searchResults.length})</span>
           </div>
       ) : (
         <><span>Showing:</span><span className="font-semibold text-gray-900">{activeCategory}</span>{activeSubCategory !== "All" && <span className="font-semibold text-gray-900"> › {activeSubCategory}</span>}</>
       )}
    </div>
  );

  // Skeleton card for loading state
  const SkeletonCard = () => (
    <div className="bg-white rounded-2xl border border-slate-200 p-3 animate-pulse">
      <div className="w-full aspect-square bg-gray-200 rounded-xl mb-3" />
      <div className="h-3 bg-gray-200 rounded w-3/4 mb-2" />
      <div className="h-4 bg-gray-200 rounded w-1/2 mb-2" />
      <div className="h-4 bg-gray-200 rounded w-1/3" />
    </div>
  );

  // IntersectionObserver sentinel for infinite scroll
  const sentinelRef = useRef(null);
  useEffect(() => {
    if (!hasMore) return;
    
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isFetchingMore) {
          onLoadMore();
        }
      },
      { rootMargin: '200px' }
    );
    
    if (sentinelRef.current) {
      observer.observe(sentinelRef.current);
    }
    
    return () => observer.disconnect();
  }, [hasMore, isFetchingMore, onLoadMore]);

  // TECH-11: Search loading skeleton grid
  if (isSearchingText || isSearchingVisual) {
    return (
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-6">
          {isSearchingText ? (
            <p className="text-sm text-gray-500">Searching...</p>
          ) : (
            <p className="text-sm text-gray-500">Analyzing image...</p>
          )}
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl overflow-hidden border border-gray-100 shadow-sm animate-pulse">
              <div className="aspect-square bg-gray-200" />
              <div className="p-3 space-y-2">
                <div className="h-3 bg-gray-200 rounded w-3/4" />
                <div className="h-4 bg-gray-200 rounded w-1/2" />
                <div className="h-4 bg-gray-200 rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      </main>
    );
  }

  // Initial loading skeleton grid (6 cards)
  if (loading) return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {[...Array(6)].map((_, i) => (
          <SkeletonCard key={i} />
        ))}
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

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      {/* Results header with view toggle */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
        <StatusLine />
        {items.length > 0 && (
          <div className="flex items-center bg-white border border-slate-200 rounded-lg p-1 shadow-xs shrink-0">
            <button onClick={() => setViewMode("grid")} className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-brand-500 text-white' : 'text-slate-400 hover:text-slate-600'}`} title="Grid">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2V5zM11 11a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2v-2z"/></svg>
            </button>
            <button onClick={() => setViewMode("list")} className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-brand-500 text-white' : 'text-slate-400 hover:text-slate-600'}`} title="List">
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"/></svg>
            </button>
          </div>
        )}
      </div>

      {items.length > 0 ? (
        viewMode === 'list' ? (
          <div className="space-y-3">
            {items.map((item) => {
              const mainImage = item.images && item.images.length > 0 ? item.images[0] : item.image_path;
              return (
                <div key={item.id} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4 hover:border-brand-400 transition-all">
                  <div className="flex items-center gap-4 w-full sm:w-auto">
                    <img
                      src={`${API_BASE_URL}/media/${mainImage}`}
                      alt={item.title}
                      className="w-16 h-16 rounded-xl object-cover shrink-0"
                      onError={e => { e.target.src = 'https://placehold.co/400x400?text=No+Image'; }}
                    />
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-bold text-brand-700">@{item.channel?.username || 'unknown'}</span>
                        <span className="text-[10px] text-slate-400">• {item.category}</span>
                      </div>
                      <h4 className="font-bold text-slate-900 text-sm sm:text-base leading-snug">{item.title}</h4>
                    </div>
                  </div>
                  <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto pt-3 sm:pt-0 border-t sm:border-0 border-slate-100">
                    <div className="text-left sm:text-right">
                      <span className="text-[10px] text-slate-400 block font-bold uppercase">Price</span>
                      <span className="text-base font-extrabold text-slate-900">
                        {item.price?.toLocaleString?.() || item.price} {item.currency || 'ETB'}
                      </span>
                    </div>
                    <button
                      onClick={() => onNavigate(`/item/${item.id}`)}
                      className="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-brand-600 transition-colors"
                    >
                      View
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {items.map((item) => (
              <ItemCard key={item.id} item={item} apiUrl={API_BASE_URL} onSelect={(itm) => onNavigate(`/item/${itm.id}`)} />
            ))}
          </div>
        )
      ) : (
        <div className="text-center text-gray-500 py-10">No items found.</div>
      )}
      <div ref={sentinelRef} className="h-1" />
      {isFetchingMore && (
        <div className="flex justify-center items-center py-6">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      )}
      {!hasMore && items.length > 0 && (
        <p className="text-center text-gray-400 py-6 text-sm">You've seen everything!</p>
      )}
    </main>
  );
};
export default ProductGrid;