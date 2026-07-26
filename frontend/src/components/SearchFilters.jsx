import React from 'react';
import { Filter } from 'lucide-react';
import { TAXONOMY } from '../constants/taxonomy';

const SearchFilters = ({
  searchQuery,
  minPrice,
  setMinPrice,
  maxPrice,
  setMaxPrice,
  filterCategory,
  setFilterCategory,
  excludeUnpriced,
  setExcludeUnpriced,
}) => {
  if (!searchQuery || searchQuery.trim().length === 0) {
    return null;
  }

  const activeFilterCount =
    (minPrice !== "" ? 1 : 0) +
    (maxPrice !== "" ? 1 : 0) +
    (filterCategory !== "All" && filterCategory !== "" ? 1 : 0) +
    (excludeUnpriced ? 1 : 0);

  return (
    <div className="max-w-6xl mx-auto px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {/* Min Price */}
        <input
          type="number"
          placeholder="Min Price (ETB)"
          min="0"
          step="1"
          value={minPrice}
          onChange={(e) => setMinPrice(e.target.value)}
          className="w-36 px-3 py-1.5 bg-gray-100 rounded-xl text-sm outline-none focus:bg-white focus:border-blue-500 border border-transparent transition-all"
        />

        {/* Max Price */}
        <input
          type="number"
          placeholder="Max Price (ETB)"
          min="0"
          step="1"
          value={maxPrice}
          onChange={(e) => setMaxPrice(e.target.value)}
          className="w-36 px-3 py-1.5 bg-gray-100 rounded-xl text-sm outline-none focus:bg-white focus:border-blue-500 border border-transparent transition-all"
        />

        {/* Category Dropdown */}
        <select
          value={filterCategory}
          onChange={(e) => setFilterCategory(e.target.value)}
          className="px-3 py-1.5 bg-gray-100 rounded-xl text-sm outline-none focus:bg-white focus:border-blue-500 border border-transparent transition-all"
        >
          {Object.keys(TAXONOMY).map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>

        {/* Exclude Unpriced Toggle */}
        <label className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-xl text-sm cursor-pointer hover:bg-gray-200 transition-all">
          <input
            type="checkbox"
            checked={excludeUnpriced}
            onChange={(e) => setExcludeUnpriced(e.target.checked)}
            className="accent-blue-600 w-4 h-4"
          />
          Only show items with price
        </label>

        {/* Active Filter Badge */}
        {activeFilterCount > 0 && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
            <Filter size={14} />
            {activeFilterCount} filter(s) active
          </span>
        )}
      </div>
    </div>
  );
};

export default SearchFilters;
