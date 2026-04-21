import React from 'react';

// You can move the huge TAXONOMY object to a separate file (e.g. src/constants.js) later
// For now, pass it as a prop or keep it here if it's static
import { TAXONOMY } from '../../pages/Home'; // We'll export it from Home for now

const CategoryNav = ({ activeCategory, setActiveCategory, activeSubCategory, setActiveSubCategory, getSubcategories }) => {
  return (
    <div className="bg-white border-b border-gray-200 sticky top-16 z-20 shadow-sm">
      <div className="hidden md:block border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-4 py-3 flex gap-2 overflow-x-auto no-scrollbar">
          <button
              onClick={() => setActiveCategory("All")}
              className={`whitespace-nowrap px-4 py-1.5 rounded-full text-sm font-medium transition-all ${
                activeCategory === "All" ? 'bg-gray-900 text-white shadow-md' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
          >
              All
          </button>
          {/* We assume TAXONOMY is available or passed down. Ideally move TAXONOMY to src/constants.js */}
        </div>
      </div>
      {/* ... Subcategory logic ... */}
    </div>
  );
};

// NOTE: To keep this refactor simple and safe without breaking imports, 
// I will keep the Category Logic inside Home.jsx for this specific step 
// and just clean up the Main Home file first. 
// Splitting CategoryNav requires moving the TAXONOMY constant to a shared file first.
// Let's focus on cleaning Home.jsx logic and fixing the API calls first.
export default CategoryNav;