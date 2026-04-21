import React, { useRef } from 'react';
import { Search, Camera, X } from 'lucide-react';

const SearchBar = ({ searchQuery, setSearchQuery, onClear, onImageSelect }) => {
  const fileInputRef = useRef(null);

  return (
    <div className="relative w-full">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
      <input 
          type="text" 
          placeholder="Search for anything..." 
          className="w-full pl-10 pr-12 py-2 bg-gray-100 border-transparent focus:bg-white focus:border-blue-500 rounded-xl outline-none transition-all"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
      />
      
      {/* Visual Search Button */}
      {!searchQuery && (
          <button 
            onClick={() => fileInputRef.current?.click()}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600 transition-colors"
            title="Search by Image"
          >
            <Camera size={20} />
          </button>
      )}
      
      {/* Clear Button */}
      {searchQuery && (
          <button 
            onClick={onClear}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X size={14} />
          </button>
      )}

      {/* Hidden Input */}
      <input 
          type="file" 
          ref={fileInputRef}
          onChange={onImageSelect}
          className="hidden" 
          accept="image/*"
      />
    </div>
  );
};

export default SearchBar;