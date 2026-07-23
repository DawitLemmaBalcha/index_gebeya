import { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../config';
import { TAXONOMY } from '../constants/taxonomy';
import { getAnalyticsHeaders } from '../utils/analytics'; 

export const useShop = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Selection
  const [activeCategory, setActiveCategory] = useState("All");
  const [activeSubCategory, setActiveSubCategory] = useState("All");
  
  // Search
  const [searchQuery, setSearchQuery] = useState("");
  const [visualResults, setVisualResults] = useState(null);
  const [searchResults, setSearchResults] = useState(null);
  const [isSearchingText, setIsSearchingText] = useState(false);
  const [isSearchingVisual, setIsSearchingVisual] = useState(false);

  // Filter state
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [filterCategory, setFilterCategory] = useState("All");

  // Infinite scroll state
  const LIMIT = 20;
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isFetchingMore, setIsFetchingMore] = useState(false);
  const [seenItemIds, setSeenItemIds] = useState(new Set());

  // Initial Fetch
  useEffect(() => { fetchItems(0); }, []);

  // Reset Subcat on Cat change
  useEffect(() => { setActiveSubCategory("All"); }, [activeCategory]);

  // Debounced Search
  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchQuery.trim().length > 0) {
        handleTextSearch(searchQuery, { minPrice, maxPrice, filterCategory });
      } else {
        setMinPrice("");
        setMaxPrice("");
        setFilterCategory("All");
        setSearchResults(null);
      }
    }, 600); 
    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery, minPrice, maxPrice, filterCategory]);

  const fetchItems = useCallback(async (pageOffset = 0) => {
    // Build URL with limit, offset, and exclude params
    let url = `${API_BASE_URL}/feed/foryou?limit=${LIMIT}&offset=${pageOffset}`;
    if (seenItemIds.size > 0) {
      url += `&exclude=${[...seenItemIds].join(',')}`;
    }

    try {
      if (pageOffset === 0) {
        setLoading(true);
      }
      setError(null);
      
      const analyticsHeaders = getAnalyticsHeaders();
      
      const response = await fetch(url, {
          headers: {
              ...analyticsHeaders
          }
      });

      if (!response.ok) throw new Error(`Server Error: ${response.status}`);
      const data = await response.json();
      
      if (pageOffset === 0) {
        setItems(data);
        setOffset(0);
      } else {
        setItems(prev => [...prev, ...data]);
      }
      
      if (data.length < LIMIT) {
        setHasMore(false);
      }
      if (data.length === 0) {
        setHasMore(false);
      }
      
      // Track seen IDs
      setSeenItemIds(prev => {
        const next = new Set(prev);
        data.forEach(item => next.add(item.id));
        return next;
      });
    } catch (error) {
      console.error("Error fetching items:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [LIMIT, seenItemIds]);

  const fetchMore = useCallback(async () => {
    if (!hasMore || isFetchingMore) return;
    const newOffset = offset + LIMIT;
    setIsFetchingMore(true);
    try {
      await fetchItems(newOffset);
      setOffset(newOffset);
    } finally {
      setIsFetchingMore(false);
    }
  }, [hasMore, isFetchingMore, offset, fetchItems]);

  const handleTextSearch = async (query, filters = {}) => {
    setIsSearchingText(true); setVisualResults(null); setActiveCategory("All"); 
    
    const body = { query, limit: 50 };
    if (filters.minPrice && filters.minPrice !== "") {
      body.min_price = Number(filters.minPrice);
    }
    if (filters.maxPrice && filters.maxPrice !== "") {
      body.max_price = Number(filters.maxPrice);
    }
    if (filters.filterCategory && filters.filterCategory !== "All") {
      body.category = filters.filterCategory;
    }

    const analyticsHeaders = getAnalyticsHeaders();

    try {
        const response = await fetch(`${API_BASE_URL}/search/`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                ...analyticsHeaders 
            },
            body: JSON.stringify(body)
        });
        if (response.ok) {
            const data = await response.json();
            setSearchResults(data.items);
        }
    } catch (error) { console.error("Search error:", error); } 
    finally { setIsSearchingText(false); }
  };

  const handleImageSearch = async (file) => {
    if (!file) return;
    setIsSearchingVisual(true); setActiveCategory("All"); setSearchQuery(""); setSearchResults(null);
    
    const formData = new FormData();
    formData.append('file', file);
    
    const analyticsHeaders = getAnalyticsHeaders();

    try {
        const response = await fetch(`${API_BASE_URL}/search/by-image`, {
            method: "POST",
            headers: {
                ...analyticsHeaders 
            },
            body: formData,
        });
        if (response.ok) {
            const data = await response.json();
            setVisualResults(data);
        } else {
            alert("Visual search failed.");
        }
    } catch (e) { console.error(e); alert("Visual search connection error."); } 
    finally { setIsSearchingVisual(false); }
  };

  // Filter Logic
  let displayItems = items;
  if (visualResults) displayItems = visualResults;
  else if (searchResults) displayItems = searchResults;
  else {
      displayItems = items.filter(item => {
        const matchesCategory = activeCategory === "All" || item.category === activeCategory;
        const matchesSubCategory = activeSubCategory === "All" || item.subcategory === activeSubCategory;
        if (activeSubCategory === "Other") {
             const knownSubs = TAXONOMY[activeCategory] || [];
             const isKnown = knownSubs.includes(item.subcategory);
             return matchesCategory && (!isKnown || item.subcategory === "Other" || item.subcategory === "Uncategorized");
        }
        return matchesCategory && matchesSubCategory;
      });
  }

  const clearVisualSearch = () => setVisualResults(null);
  
  return {
    items, loading, error, fetchItems,
    activeCategory, setActiveCategory,
    activeSubCategory, setActiveSubCategory,
    searchQuery, setSearchQuery,
    visualResults, searchResults,
    handleImageSearch, clearVisualSearch,
    displayItems, isSearchingText, isSearchingVisual,
    hasMore, isFetchingMore, fetchMore, LIMIT,
    minPrice, setMinPrice, maxPrice, setMaxPrice, filterCategory, setFilterCategory
  };
};