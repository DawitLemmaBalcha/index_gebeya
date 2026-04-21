import React from 'react';
import ItemCard from '../ItemCard';
import { WifiOff, Camera, Search } from 'lucide-react';
import { API_BASE_URL } from '../../config';

const ProductGrid = ({ loading, error, items, onRetry, onNavigate, visualResults, searchResults, onClearVisual, activeCategory, activeSubCategory }) => {
  
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

  if (loading) return <div className="flex justify-center items-center h-64"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div></div>;
  
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
      <StatusLine />
      {items.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((item) => (
            <ItemCard key={item.id} item={item} apiUrl={API_BASE_URL} onSelect={(itm) => onNavigate(`/item/${itm.id}`)} />
          ))}
        </div>
      ) : (
        <div className="text-center text-gray-500 py-10">No items found.</div>
      )}
    </main>
  );
};
export default ProductGrid;