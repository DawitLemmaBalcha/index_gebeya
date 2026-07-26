import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useShop } from '../hooks/useShop';
import NavBar from '../components/home/NavBar';
import SearchFilters from '../components/SearchFilters';
import ProductGrid from '../components/home/ProductGrid';

const Home = ({ embedded = false, initialSearchQuery = '' }) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const shop = useShop();

  useEffect(() => {
    const q = searchParams.get('q');
    if (q && q.trim().length > 0) {
      shop.setSearchQuery(q);
    } else if (initialSearchQuery && initialSearchQuery.trim().length > 0) {
      shop.setSearchQuery(initialSearchQuery);
    }
  }, [searchParams, initialSearchQuery, shop.setSearchQuery]);

  const handleReset = () => {
    shop.resetFeed();
    shop.setActiveCategory("All");
    shop.setSearchQuery("");
    shop.clearVisualSearch();
  };

  const rootClasses = embedded ? "font-sans" : "min-h-screen bg-ethiopia-paper font-sans";

  return (
    <div className={rootClasses}>
      <NavBar
        searchQuery={shop.searchQuery}
        setSearchQuery={shop.setSearchQuery}
        onImageSearch={shop.handleImageSearch}
        onReset={handleReset}
        onLogoClick={() => navigate('/welcome')}
        activeCategory={shop.activeCategory}
        setActiveCategory={shop.setActiveCategory}
        activeSubCategory={shop.activeSubCategory}
        setActiveSubCategory={shop.setActiveSubCategory}
        viewMode={shop.viewMode}
        setViewMode={shop.setViewMode}
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
        viewMode={shop.viewMode}
        setViewMode={shop.setViewMode}
      />
    </div>
  );
};

export default Home;
