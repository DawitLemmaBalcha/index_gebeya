import { useState, useEffect, useCallback, useRef } from 'react';
import { API_BASE_URL } from '../config';
import { TAXONOMY } from '../constants/taxonomy';
import { getAnalyticsHeaders } from '../utils/analytics'; 

// TECH-10: Module-level feed cache for instant back navigation
let _feedCache = null;

export const useShop = () => {
  const [items, setItems] = useState(() => _feedCache ? _feedCache.items : []);
  const [loading, setLoading] = useState(() => !_feedCache);
  const [error, setError] = useState(null);
  
  // Selection
  const [activeCategory, setActiveCategory] = useState("All");
  const [activeSubCategory, setActiveSubCategory] = useState("All");
  
  // View mode — persisted to localStorage
  const [viewMode, setViewMode] = useState(() => {
    try { return localStorage.getItem('viewMode') || 'grid'; }
    catch { return 'grid'; }
  });
  
  // Persist viewMode changes
  const setViewModePersisted = (mode) => {
    setViewMode(mode);
    try { localStorage.setItem('viewMode', mode); } catch {}
  };
  
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
  const [excludeUnpriced, setExcludeUnpriced] = useState(false);

  // Infinite scroll state
  const LIMIT = 20;
  const [offset, setOffset] = useState(() => _feedCache ? _feedCache.offset : 0);
  const [hasMore, setHasMore] = useState(() => _feedCache ? _feedCache.hasMore : true);
  const [isFetchingMore, setIsFetchingMore] = useState(false);
  const [seenItemIds, setSeenItemIds] = useState(() => _feedCache ? new Set(_feedCache.seenItemIds) : new Set());

  // TECH-10: Reset feed cache and force fresh fetch
  const resetFeed = useCallback(() => {
    _feedCache = null;
    setItems([]);
    setLoading(true);
    setOffset(0);
    setHasMore(true);
    setSeenItemIds(new Set());
    fetchItems(0);
  }, []);

  // Initial Fetch — the cached page only serves the FIRST PAINT (TECH-10
  // instant back-navigation). The feed is always re-derived from the server
  // so hasMore tracks the CURRENT catalog: a stale hasMore=false cache
  // previously froze Explore at a limited set forever (user-verified bug).
  useEffect(() => {
    // Always reset transient search states on mount
    setSearchResults(null);
    setVisualResults(null);
    setSearchQuery("");
    setMinPrice("");
    setMaxPrice("");
    setFilterCategory("All");

    fetchItems(0);
  }, []);

  // Reset Subcat on Cat change
  useEffect(() => { setActiveSubCategory("All"); }, [activeCategory]);

  // Debounced Search
  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchQuery.trim().length > 0) {
        handleTextSearch(searchQuery, { minPrice, maxPrice, filterCategory, excludeUnpriced });
      } else {
        setMinPrice("");
        setMaxPrice("");
        setFilterCategory("All");
        setSearchResults(null);
      }
    }, 600); 
    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery, minPrice, maxPrice, filterCategory, excludeUnpriced]);

  const fetchItems = useCallback(async (pageOffset = 0) => {
    // Every page-0 fetch is a FRESH feed session: the accumulated seen-set
    // only dedupes continuation pages. Cache hits (revisits) therefore
    // re-derive the canonical first page + hasMore from the current catalog
    // instead of freezing at a stale <LIMIT page (user-verified bug).
    const freshSession = pageOffset === 0;
    let url = `${API_BASE_URL}/feed/foryou?limit=${LIMIT}&offset=${pageOffset}`;
    if (!freshSession && seenItemIds.size > 0) {
      url += `&exclude=${[...seenItemIds].join(',')}`;
    }

    try {
      // Cache hits keep the instant paint (TECH-10); only the very first
      // load in a JS session shows the skeleton.
      if (freshSession && !_feedCache) {
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
      
      if (freshSession) {
        setItems(data);
        setOffset(0);
        // Fresh session: reset the seen-set to this page's ids.
        setSeenItemIds(new Set(data.map(item => item.id)));
      } else {
        setItems(prev => [...prev, ...data]);
        setSeenItemIds(prev => {
          const next = new Set(prev);
          data.forEach(item => next.add(item.id));
          return next;
        });
      }
      
      // Re-derive hasMore from the ACTUAL response — a full page restores
      // scrolling, a short page ends it.
      setHasMore(data.length >= LIMIT);
      
      if (freshSession) {
        // Populate module-level cache for instant back navigation (TECH-10)
        _feedCache = {
          items: data,
          offset: 0,
          hasMore: data.length >= LIMIT,
          seenItemIds: data.map(item => item.id),
        };
      }
    } catch (error) {
      console.error("Error fetching items:", error);
      // A failed background refresh of a cached feed keeps the cached items
      // visible instead of masking them with the error screen (TECH-10).
      if (pageOffset !== 0 || !_feedCache) setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [LIMIT, seenItemIds]);

  // Browse seam (browse-seam blueprint §2.4): server-side category browse.
  // Deliberately does NOT touch seenItemIds or _feedCache — browse results
  // must never pollute feed state or the module-level feed cache.
  const fetchBrowseCategory = useCallback(async (category, pageOffset = 0) => {
    const url = `${API_BASE_URL}/items/browse?category=${encodeURIComponent(category)}&limit=${LIMIT}&offset=${pageOffset}`;

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
      const pageItems = data.items || [];

      if (pageOffset === 0) {
        setItems(pageItems);
        setOffset(0);
      } else {
        setItems(prev => [...prev, ...pageItems]);
      }

      if (pageItems.length < LIMIT || pageItems.length === 0) {
        setHasMore(false);
      }
    } catch (error) {
      console.error("Error fetching browse items:", error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [LIMIT]);

  const fetchMore = useCallback(async () => {
    if (!hasMore || isFetchingMore) return;
    const newOffset = offset + LIMIT;
    setIsFetchingMore(true);
    try {
      // Mode-aware: browse mode pages the catalog seam, otherwise the feed.
      const isBrowseMode = activeCategory !== "All" && activeCategory !== "all";
      if (isBrowseMode) {
        await fetchBrowseCategory(activeCategory, newOffset);
      } else {
        await fetchItems(newOffset);
      }
      setOffset(newOffset);
    } finally {
      setIsFetchingMore(false);
    }
  }, [hasMore, isFetchingMore, offset, activeCategory, fetchItems, fetchBrowseCategory, LIMIT]);

  // Mode-aware retry: re-fetch the CURRENT surface (browse seam in browse
  // mode, feed otherwise) — ProductGrid's onRetry must never fire the feed
  // fetcher while the user is browsing a category.
  const retry = useCallback(() => {
    const isBrowseMode = activeCategory !== "All" && activeCategory !== "all";
    if (isBrowseMode) {
      setOffset(0);
      setHasMore(true);
      fetchBrowseCategory(activeCategory, 0);
    } else {
      fetchItems(0);
    }
  }, [activeCategory, fetchBrowseCategory, fetchItems]);

  // Browse-mode source switching: entering a real category fetches the
  // server-side catalog seam; leaving it refetches a fresh feed; neutral ->
  // neutral (including search's setActiveCategory("All")) is a no-op.
  const prevCategoryRef = useRef(activeCategory);
  useEffect(() => {
    const prev = prevCategoryRef.current;
    prevCategoryRef.current = activeCategory;
    // No-op unless the category actually CHANGED (identity churn in other
    // deps — e.g. fetchItems after a feed seenItemIds update — must not
    // refetch the current surface).
    if (prev === activeCategory) return;
    const isRealCategory = (c) => !!c && c !== "All" && c !== "all";
    if (!isRealCategory(prev) && !isRealCategory(activeCategory)) return;
    setOffset(0);
    setHasMore(true);
    if (isRealCategory(activeCategory)) {
      // Entering browse mode must drop stale transient search state: a text
      // search performed before browsing keeps searchResults set, and
      // displayItems would render those old results instead of the browse
      // page (displayItems: searchResults/visualResults override `items`).
      setSearchResults(null);
      setVisualResults(null);
      fetchBrowseCategory(activeCategory, 0);
    } else {
      fetchItems(0);
    }
  }, [activeCategory, fetchBrowseCategory, fetchItems]);

  const handleTextSearch = async (query, filters = {}) => {
    setIsSearchingText(true); setVisualResults(null); setActiveCategory("All"); 
    
    const body = { query, limit: 50 };
    if (filters.minPrice !== "" && !isNaN(Number(filters.minPrice))) {
      body.min_price = Number(filters.minPrice);
    }
    if (filters.maxPrice !== "" && !isNaN(Number(filters.maxPrice))) {
      body.max_price = Number(filters.maxPrice);
    }
    if (filters.filterCategory && filters.filterCategory !== "All") {
      body.category = filters.filterCategory;
    }
    if (filters.excludeUnpriced) {
      body.exclude_unpriced = true;
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
        // Browse mode (real category): the server already filtered by
        // category, so the category clause is skipped; neutral passes
        // everything — "All" AND lowercase "all" (Deviation 5). The
        // subcategory clause and the "Other" branch stay client-side.
        const isBrowseMode = activeCategory !== "All" && activeCategory !== "all";
        const matchesCategory = isBrowseMode || activeCategory === "All" || activeCategory === "all";
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
    fetchBrowseCategory, retry,
    minPrice, setMinPrice, maxPrice, setMaxPrice, filterCategory, setFilterCategory,
    excludeUnpriced, setExcludeUnpriced,
    viewMode, setViewMode: setViewModePersisted,
    resetFeed
  };
};