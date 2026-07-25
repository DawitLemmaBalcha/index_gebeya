import React, { useRef, useState } from 'react';
import { Search, ShoppingBag, Menu, X, Camera, ArrowLeft } from 'lucide-react';
import { TAXONOMY } from '../../constants/taxonomy';
import CategorySheet from '../CategorySheet';

const NavBar = ({ searchQuery, setSearchQuery, onImageSearch, onReset, setActiveCategory, activeCategory, activeSubCategory, setActiveSubCategory, variant = "home", onBack, onSearchSubmit, onLogoClick }) => {
  const fileInputRef = useRef(null);
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files[0]) {
        onImageSearch(e.target.files[0]);
        if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <>
    <nav className="bg-ethiopia-paper/90 backdrop-blur-md border-b border-ethiopia-border sticky top-0 z-30">
        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
        
        <div className="max-w-6xl mx-auto px-4 h-20 flex items-center justify-between">
          {variant === "product" ? (
            <button onClick={onBack} className="p-2 hover:bg-gray-100 rounded-full">
              <ArrowLeft size={24} className="text-gray-700" />
            </button>
          ) : (
            <div className="flex items-center gap-2 cursor-pointer" onClick={onLogoClick || onReset}>
              <div className="bg-slate-900 p-2 rounded-lg"><ShoppingBag className="text-brand-500" size={20} /></div>
              <span className="font-extrabold text-xl tracking-tight text-slate-900">Index<span className="text-brand-600"> Gebeya</span></span>
            </div>
          )}
          
          <div className="hidden md:flex flex-1 max-w-md mx-4 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-white border border-slate-200 rounded-xl outline-none focus:bg-white focus:border-brand-500 transition-all" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }} />
              {!searchQuery ? (
                  <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand-600"><Camera size={20} /></button>
              ) : (
                  <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X size={14} /></button>
              )}
          </div>

          <button className="md:hidden p-2 text-gray-600 hover:bg-ethiopia-border/50 rounded-lg" onClick={() => setIsSheetOpen(true)}>
            <Menu size={24} />
          </button>
        </div>

        {/* Mobile Search */}
        <div className="md:hidden px-4 pb-4">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-white border border-slate-200 rounded-xl outline-none text-sm focus:border-brand-500" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }} />
                {!searchQuery && <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand-600"><Camera size={18} /></button>}
            </div>
        </div>
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
  </>);
};
export default NavBar;