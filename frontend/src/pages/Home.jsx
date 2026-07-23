import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useShop } from '../hooks/useShop';
import NavBar from '../components/home/NavBar';
import CategoryBar from '../components/home/CategoryBar';
import ProductGrid from '../components/home/ProductGrid';

const Home = () => {
  const navigate = useNavigate();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  const shop = useShop();

  const handleReset = () => {
    shop.setActiveCategory("All");
    shop.setSearchQuery("");
    shop.clearVisualSearch();
  };

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      <NavBar 
        searchQuery={shop.searchQuery}
        setSearchQuery={shop.setSearchQuery}
        onImageSearch={shop.handleImageSearch}
        onReset={handleReset}
        isMobileMenuOpen={isMobileMenuOpen}
        setIsMobileMenuOpen={setIsMobileMenuOpen}
        activeCategory={shop.activeCategory}
        setActiveCategory={shop.setActiveCategory}
      />
      
      {!shop.visualResults && !shop.searchResults && !shop.searchQuery && !isMobileMenuOpen && (
        <CategoryBar 
          activeCategory={shop.activeCategory}
          setActiveCategory={shop.setActiveCategory}
          activeSubCategory={shop.activeSubCategory}
          setActiveSubCategory={shop.setActiveSubCategory}
        />
      )}

      <ProductGrid 
        loading={shop.loading}
        error={shop.error}
        items={shop.displayItems}
        onRetry={shop.fetchItems}
        onNavigate={navigate}
        visualResults={shop.visualResults}
        searchResults={shop.searchResults}
        onClearVisual={shop.clearVisualSearch}
        activeCategory={shop.activeCategory}
        activeSubCategory={shop.activeSubCategory}
        hasMore={shop.hasMore}
        isFetchingMore={shop.isFetchingMore}
        onLoadMore={shop.fetchMore}
      />
    </div>
  );
};

export default Home;