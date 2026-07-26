import React, { useRef, useState } from 'react';
import { Search, Menu, Camera, ArrowLeft, ShoppingBag } from 'lucide-react';
import { TAXONOMY } from '../../constants/taxonomy';
import CategorySheet from '../CategorySheet';

const NavBar = ({ searchQuery, setSearchQuery, onImageSearch, onReset, setActiveCategory, activeCategory, activeSubCategory, setActiveSubCategory, variant = "home", onBack, onSearchSubmit, onLogoClick, viewMode, setViewMode }) => {
  const fileInputRef = useRef(null);
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files[0]) {
        onImageSearch(e.target.files[0]);
        if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Product page: minimal header with back arrow + search
  if (variant === "product") {
    return (
      <nav className="bg-white/90 backdrop-blur-md border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-3 h-14 flex items-center gap-2">
          <button onClick={onBack} className="p-2 hover:bg-slate-100 rounded-full shrink-0">
            <ArrowLeft size={20} className="text-slate-700" />
          </button>
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
            <input type="text" placeholder="Search..." className="w-full pl-9 pr-10 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm outline-none focus:border-amber-500 focus:bg-white transition-all" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }}/>
            {!searchQuery ? (
              <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-600"><Camera size={16} /></button>
            ) : (
              <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600">✕</button>
            )}
          </div>
          <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
        </div>
      </nav>
    );
  }

  // Home/Explore: compact single-row header
  return (
    <>
    <nav className="bg-white/90 backdrop-blur-md border-b border-slate-200 sticky top-0 z-30">
      <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
      <div className="max-w-6xl mx-auto px-3 h-14 flex items-center gap-2">
        {/* Hamburger */}
        <button onClick={() => setIsSheetOpen(true)} className="p-2 hover:bg-slate-100 rounded-lg shrink-0">
          <Menu size={20} className="text-slate-600" />
        </button>

        {/* Compact brand — logo click */}
        <div className="flex items-center gap-1.5 cursor-pointer shrink-0" onClick={onLogoClick || onReset}>
          <div className="w-8 h-8 rounded-lg bg-slate-900 flex items-center justify-center">
            <ShoppingBag className="text-amber-500" size={16} />
          </div>
          <span className="hidden sm:inline font-extrabold text-base tracking-tight text-slate-900">Index<span className="text-amber-600">Gebeya</span></span>
        </div>

        {/* Search bar */}
        <div className="relative flex-1 max-w-lg">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={16} />
          <input type="text" placeholder="Search products..." className="w-full pl-9 pr-10 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm outline-none focus:border-amber-500 focus:bg-white transition-all" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }}/>
          {!searchQuery ? (
            <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-600"><Camera size={16} /></button>
          ) : (
            <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs">✕</button>
          )}
        </div>
      </div>

      {/* Active filter chip — only when category selected */}
      {activeCategory && activeCategory !== "All" && (
        <div className="max-w-6xl mx-auto px-3 pb-2 flex items-center gap-1.5">
          <span className="text-[10px] text-slate-400 font-medium">Filter:</span>
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 border border-amber-200 text-amber-800 text-[11px] font-bold">
            {activeCategory}
            {activeSubCategory && activeSubCategory !== "All" && <span className="text-amber-400">›</span>}
            {activeSubCategory && activeSubCategory !== "All" && activeSubCategory}
            <button onClick={() => { setActiveCategory("All"); setActiveSubCategory("All"); }} className="ml-0.5 text-amber-400 hover:text-amber-600">✕</button>
          </span>
        </div>
      )}
    </nav>

    <CategorySheet
      isOpen={isSheetOpen}
      onClose={() => setIsSheetOpen(false)}
      activeCategory={activeCategory}
      setActiveCategory={setActiveCategory}
      activeSubCategory={activeSubCategory}
      setActiveSubCategory={setActiveSubCategory}
      TAXONOMY={TAXONOMY}
    />
    </>
  );
};
export default NavBar;
