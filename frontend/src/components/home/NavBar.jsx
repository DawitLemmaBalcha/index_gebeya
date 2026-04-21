import React, { useRef } from 'react';
import { Search, ShoppingBag, Menu, X, Camera } from 'lucide-react';
import { TAXONOMY } from '../../constants/taxonomy';

const NavBar = ({ searchQuery, setSearchQuery, onImageSearch, onReset, isMobileMenuOpen, setIsMobileMenuOpen, setActiveCategory, activeCategory }) => {
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    if (e.target.files[0]) {
        onImageSearch(e.target.files[0]);
        setIsMobileMenuOpen(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept="image/*" />
        
        <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2 cursor-pointer" onClick={onReset}>
            <div className="bg-blue-600 p-2 rounded-lg"><ShoppingBag className="text-white" size={20} /></div>
            <span className="text-xl font-bold text-gray-900 tracking-tight">Suq<span className="text-blue-600">.et</span></span>
          </div>
          
          <div className="hidden md:flex flex-1 max-w-md mx-4 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
              <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-gray-100 rounded-xl outline-none focus:bg-white focus:border-blue-500 border border-transparent transition-all" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
              {!searchQuery ? (
                  <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600"><Camera size={20} /></button>
              ) : (
                  <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"><X size={14} /></button>
              )}
          </div>

          <button className="md:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-lg" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
            {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>

        {/* Mobile Search & Menu */}
        <div className="md:hidden px-4 pb-4">
            {!isMobileMenuOpen ? (
                 <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                    <input type="text" placeholder="Search..." className="w-full pl-10 pr-12 py-2 bg-gray-100 rounded-xl outline-none text-sm" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} />
                    {!searchQuery && <button onClick={() => fileInputRef.current?.click()} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-blue-600"><Camera size={18} /></button>}
                 </div>
            ) : (
                <div className="grid grid-cols-2 gap-2 mt-2">
                    <button onClick={() => {setActiveCategory("All"); setIsMobileMenuOpen(false);}} className={`p-3 rounded-lg text-sm font-medium text-left ${activeCategory === "All" ? 'bg-blue-50 text-blue-700' : 'bg-gray-50 text-gray-700'}`}>All</button>
                    {Object.keys(TAXONOMY).filter(c => c !== "All").map((cat) => (
                        <button key={cat} onClick={() => {setActiveCategory(cat); setIsMobileMenuOpen(false);}} className={`p-3 rounded-lg text-sm font-medium text-left ${activeCategory === cat ? 'bg-blue-50 text-blue-700' : 'bg-gray-50 text-gray-700'}`}>{cat}</button>
                    ))}
                </div>
            )}
        </div>
    </nav>
  );
};
export default NavBar;