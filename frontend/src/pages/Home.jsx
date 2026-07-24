import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useShop } from '../hooks/useShop';
import NavBar from '../components/home/NavBar';
import SearchFilters from '../components/SearchFilters';
import CategoryBar from '../components/home/CategoryBar';
import ProductGrid from '../components/home/ProductGrid';

const Home = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  const shop = useShop();

  // TECH-13: Handle ?q= query parameter from ProductPage search
  useEffect(() => {
    const q = searchParams.get('q');
    if (q && q.trim().length > 0) {
      shop.setSearchQuery(q);
    }
  }, []); // Run once on mount

  // TECH-10: Include resetFeed to clear cache
  const handleReset = () => {
    shop.resetFeed();
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
      
      {shop.searchQuery && !shop.visualResults && (
        <SearchFilters
          searchQuery={shop.searchQuery}
          minPrice={shop.minPrice}
          setMinPrice={shop.setMinPrice}
          maxPrice={shop.maxPrice}
          setMaxPrice={shop.setMaxPrice}
          filterCategory={shop.filterCategory}
          setFilterCategory={shop.setFilterCategory}
        />
      )}

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
        isSearchingText={shop.isSearchingText}
        isSearchingVisual={shop.isSearchingVisual}
      />
    </div>
  );
};

export default Home;