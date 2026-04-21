import React from 'react';
import { TAXONOMY } from '../../constants/taxonomy';

const CategoryBar = ({ activeCategory, setActiveCategory, activeSubCategory, setActiveSubCategory }) => {
  const getSubcategories = (cat) => {
      const subs = TAXONOMY[cat] || [];
      return (subs.length > 0 && !subs.includes("Other")) ? [...subs, "Other"] : subs;
  };

  const subs = activeCategory !== "All" ? getSubcategories(activeCategory) : [];

  return (
      <div className="bg-white border-b border-gray-200 sticky top-16 z-20 shadow-sm hidden md:block">
        <div className="border-b border-gray-100">
          <div className="max-w-6xl mx-auto px-4 py-3 flex gap-2 overflow-x-auto no-scrollbar">
            <button onClick={() => setActiveCategory("All")} className={`whitespace-nowrap px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeCategory === "All" ? 'bg-gray-900 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>All</button>
            {Object.keys(TAXONOMY).filter(c => c !== "All").map((cat) => (
              <button key={cat} onClick={() => setActiveCategory(cat)} className={`whitespace-nowrap px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeCategory === cat ? 'bg-gray-900 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}>{cat}</button>
            ))}
          </div>
        </div>
        {subs.length > 0 && (
          <div className="bg-gray-50 animate-in slide-in-from-top-2 duration-200">
            <div className="max-w-6xl mx-auto px-4 py-2 flex gap-2 overflow-x-auto no-scrollbar items-center">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider mr-2 shrink-0">Filter:</span>
              <button onClick={() => setActiveSubCategory("All")} className={`whitespace-nowrap px-3 py-1 rounded-lg text-xs font-medium transition-all border ${activeSubCategory === "All" ? 'bg-white border-blue-500 text-blue-600 shadow-sm' : 'bg-transparent border-transparent text-gray-500 hover:bg-gray-200'}`}>All</button>
              {subs.map((sub) => (
                <button key={sub} onClick={() => setActiveSubCategory(sub)} className={`whitespace-nowrap px-3 py-1 rounded-lg text-xs font-medium transition-all border ${activeSubCategory === sub ? 'bg-blue-100 border-blue-200 text-blue-700 shadow-sm' : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'}`}>{sub}</button>
              ))}
            </div>
          </div>
        )}
      </div>
  );
};
export default CategoryBar;