import { useState, useEffect } from 'react';
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

  // Initial Fetch
  useEffect(() => { fetchItems(); }, []);

  // Reset Subcat on Cat change
  useEffect(() => { setActiveSubCategory("All"); }, [activeCategory]);

  // Debounced Search
  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchQuery.trim().length > 0) {
        handleTextSearch(searchQuery);
      } else {
        setSearchResults(null);
      }
    }, 600); 
    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery]);

  const fetchItems = async () => {
    try {
      setLoading(true); setError(null);
      
      // --- CHANGED: USE 'FOR YOU' FEED WITH ANALYTICS HEADERS ---
      const analyticsHeaders = getAnalyticsHeaders();
      
      // We request 50 items to ensure client-side filtering (by category) 
      // still has enough data to display.
      const response = await fetch(`${API_BASE_URL}/feed/foryou?limit=50`, {
          headers: {
              ...analyticsHeaders
          }
      });
      // ----------------------------------------------------------

      if (!response.ok) throw new Error(`Server Error: ${response.status}`);
      const data = await response.json();
      setItems(data);
    } catch (error) {
      console.error("Error fetching items:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleTextSearch = async (query) => {
    setIsSearchingText(true); setVisualResults(null); setActiveCategory("All"); 
    
    const analyticsHeaders = getAnalyticsHeaders();

    try {
        const response = await fetch(`${API_BASE_URL}/search/`, {
            method: "POST",
            headers: { 
                "Content-Type": "application/json",
                ...analyticsHeaders 
            },
            body: JSON.stringify({ query: query, limit: 50 })
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
    displayItems, isSearchingText, isSearchingVisual
  };
};