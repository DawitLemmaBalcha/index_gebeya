import React, { useState, useEffect } from 'react';
import { X, ArrowLeft, ChevronRight } from 'lucide-react';

const CategorySheet = ({
  isOpen,
  onClose,
  activeCategory,
  setActiveCategory,
  activeSubCategory,
  setActiveSubCategory,
  TAXONOMY
}) => {
  const [view, setView] = useState("main");
  const [selectedCategory, setSelectedCategory] = useState(null);

  // Reset view when sheet opens
  useEffect(() => {
    if (isOpen) {
      setView("main");
      setSelectedCategory(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const mainCategories = ["All", ...Object.keys(TAXONOMY).filter(c => c !== "All")];
  const subcategories = selectedCategory && TAXONOMY[selectedCategory]
    ? TAXONOMY[selectedCategory]
    : [];

  const handleSelectCategory = (cat) => {
    if (cat === "All") {
      setActiveCategory("All");
      setActiveSubCategory("All");
      onClose();
    } else {
      setSelectedCategory(cat);
      setView("sub");
    }
  };

  const handleSelectSubcategory = (sub) => {
    setActiveCategory(selectedCategory);
    setActiveSubCategory(sub);
    onClose();
  };

  const handleBack = () => {
    if (view === "sub") {
      setView("main");
    } else {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {/* Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-gray-200 shrink-0">
        <button
          onClick={handleBack}
          className="p-2 -ml-2 hover:bg-gray-100 rounded-full flex items-center gap-1 text-gray-700"
        >
          {view === "sub" ? (
            <>
              <ArrowLeft size={20} />
              <span className="text-sm font-medium">Main</span>
            </>
          ) : (
            <X size={20} />
          )}
        </button>
        <span className="text-sm font-semibold text-gray-900">
          {view === "main" ? "Categories" : selectedCategory}
        </span>
        <div className="w-10" /> {/* Spacer for centering */}
      </div>

      {/* Content area with sliding panels */}
      <div className="flex-1 overflow-hidden relative">
        {/* Main categories panel */}
        <div
          className={`absolute inset-0 overflow-y-auto transition-transform duration-300 ease-in-out ${
            view === "main" ? "translate-x-0" : "-translate-x-full"
          }`}
        >
          {mainCategories.map((cat) => {
            const isActive = activeCategory === cat && view === "main";
            const hasSubs = cat !== "All" && TAXONOMY[cat] && TAXONOMY[cat].length > 0;
            return (
              <button
                key={cat}
                onClick={() => handleSelectCategory(cat)}
                className={`w-full flex items-center justify-between px-4 py-3 border-b border-gray-100 text-left text-sm transition-colors ${
                  isActive ? 'bg-blue-50 text-blue-700 font-medium' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                <span>{cat}</span>
                {hasSubs && (
                  <ChevronRight size={18} className={`${isActive ? 'text-blue-500' : 'text-gray-400'} shrink-0`} />
                )}
              </button>
            );
          })}
        </div>

        {/* Subcategories panel */}
        <div
          className={`absolute inset-0 overflow-y-auto transition-transform duration-300 ease-in-out ${
            view === "sub" ? "translate-x-0" : "translate-x-full"
          }`}
        >
          <button
            onClick={() => handleSelectSubcategory("All")}
            className={`w-full flex items-center justify-between px-4 py-3 border-b border-gray-100 text-left text-sm ${
              activeSubCategory === "All" && activeCategory === selectedCategory
                ? 'bg-blue-50 text-blue-700 font-medium'
                : 'text-gray-700 hover:bg-gray-50'
            }`}
          >
            <span>All Subcategories</span>
          </button>
          {subcategories.map((sub) => {
            const isActive =
              activeSubCategory === sub && activeCategory === selectedCategory;
            return (
              <button
                key={sub}
                onClick={() => handleSelectSubcategory(sub)}
                className={`w-full px-4 py-3 border-b border-gray-100 text-left text-sm transition-colors ${
                  isActive
                    ? 'bg-blue-50 text-blue-700 font-medium'
                    : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                {sub}
              </button>
            );
          })}
        </div>
      </div>

      {/* Safe area padding for iPhone notch */}
      <div className="h-safe pb-safe shrink-0" />
    </div>
  );
};

export default CategorySheet;
