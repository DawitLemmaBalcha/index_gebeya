import React, { useRef, useState } from 'react';
import { Search, ShoppingBag, Menu, X, Camera, ArrowLeft } from 'lucide-react';
import { TAXONOMY } from '../../constants/taxonomy';
import CategorySheet from '../CategorySheet';

const NavBar = ({ searchQuery, setSearchQuery, onImageSearch, onReset, setActiveCategory, activeCategory, activeSubCategory, setActiveSubCategory, variant = "home", onBack, onSearchSubmit }) => {
  const fileInputRef = useRef(null);
  const [isSheetOpen, setIsSheetOpen] = useState(false);

  const handleFileChange = (e) => {
    if (e.target.files[0]) {
        onImageSearch(e.target.files[0]);
        if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
        
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          {variant === "product" ? (
            <button onClick={onBack} className="p-2 hover:bg-gray-100 rounded-full">
              <ArrowLeft size={24} className="text-gray-700" />
            </button>
          ) : (
            <div className="flex items-center gap-2 cursor-pointer" onClick={onReset}>
              <div className="bg-blue-600 p-2 rounded-lg"><ShoppingBag className="text-white" size={20} /></div>
              <span className="text-xl font-bold text-gray-900 tracking-tight">Index<span className="text-blue-600"> Gebeya</span></span>
            </div>
          )}
          
          <div className="hidden md:flex flex-1 max-w-md mx-4 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-gray-100 rounded-xl outline-none focus:bg-white focus:border-blue-500 border border-transparent transition-all" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }} />
              {!searchQuery ? (
                  <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600"><Camera size={20} /></button>
              ) : (
                  <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X size={14} /></button>
              )}
          </div>

          <button className="md:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-lg" onClick={() => setIsSheetOpen(true)}>
            <Menu size={24} />
          </button>
        </div>

        {/* Mobile Search */}
        <div className="md:hidden px-4 pb-4">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-gray-100 rounded-xl outline-none text-sm" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && onSearchSubmit) onSearchSubmit(searchQuery); }} />
                {!searchQuery && <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600"><Camera size={18} /></button>}
            </div>
        </div>

        <CategorySheet
          isOpen={isSheetOpen}
          onClose={() => setIsSheetOpen(false)}
          activeCategory={activeCategory}
          setActiveCategory={setActiveCategory}
          activeSubCategory={activeSubCategory}
          setActiveSubCategory={setActiveSubCategory}
          TAXONOMY={TAXONOMY}
        />
    </nav>
  );
};
export default NavBar;