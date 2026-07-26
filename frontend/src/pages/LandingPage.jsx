import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import ItemCard from '../components/ItemCard';
import { TAXONOMY } from '../constants/taxonomy';

const faqs = [
  { q: "Why build this for Telegram instead of a separate website?", a: "Because that's where Ethiopian commerce already lives. Over 80% of digital selling in Ethiopia occurs inside Telegram channels. Rather than forcing thousands of sellers to create website accounts, we bring search technology directly to where they post every single day." },
  { q: "Do you sell products directly or process payments?", a: "No. We are strictly a search engine—an index. When you click on a product, Index Gebeya connects you directly to the original seller's post inside Telegram. You talk, negotiate, and inspect the item with the seller directly." },
  { q: "Is Index Gebeya free for buyers?", a: "Yes! It is 100% free for buyers. You can search unlimited products, set price alert notifications, and connect with sellers without paying any fees or subscriptions." },
  { q: "I own a Telegram channel. How do I get my products listed?", a: "It takes under 30 seconds. Simply add our Telegram bot (@IndexGebeyaBot) to your public Telegram channel as an admin. The bot automatically reads your new posts, extracts images and prices, and makes them searchable on Index Gebeya immediately." },
  { q: "Is this service only available in Ethiopia?", a: "Yes. Today, Index Gebeya is specifically built for Ethiopia. Prices are processed in Ethiopian Birr (ETB), search keywords support English and Amharic, and locations cover key commerce hubs across Addis Ababa and major regional cities." },
];

const LandingPage = ({ isTelegram = false, onGetStarted = null, compact = false }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState(null);
  const [priceFilter, setPriceFilter] = useState("all");
  const [openFaq, setOpenFaq] = useState(null);
  const [phoneTab, setPhoneTab] = useState("explore");
  const [viewMode, setViewMode] = useState("grid");

  const [searchResults, setSearchResults] = useState(null);
  const [trendingItems, setTrendingItems] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchingImage, setIsSearchingImage] = useState(false);
  const [stats, setStats] = useState(null);
  const [searchError, setSearchError] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/items/stats`);
        if (!res.ok) throw new Error("Stats fetch failed");
        setStats(await res.json());
      } catch {
        setStats({ product_count: null, channel_count: null, category_counts: {} });
      }
    };
    const fetchTrending = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/feed/foryou?limit=6`);
        if (!res.ok) throw new Error("Feed fetch failed");
        const data = await res.json();
        setTrendingItems(Array.isArray(data) ? data : []);
      } catch { setTrendingItems([]); }
    };
    fetchStats(); fetchTrending();
  }, []);

  const handleSearch = async (e) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) { setSearchResults(null); setActiveFilter(null); setSearchError(null); return; }
    if (isTelegram && onGetStarted) { onGetStarted({ searchQuery: q }); return; }
    setIsSearching(true); setSearchError(null); setActiveFilter(null);
    try {
      const body = { query: q, limit: 50 };
      if (priceFilter !== "all") {
        const ranges = { under10k: [0, 10000], "10k50k": [10000, 50000], "50k500k": [50000, 500000], over500k: [500000, null] };
        const [min, max] = ranges[priceFilter];
        if (min != null) body.min_price = min;
        if (max != null) body.max_price = max;
      }
      if (activeFilter) body.category = activeFilter;
      const res = await fetch(`${API_BASE_URL}/search/`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      setSearchResults(data.items || []);
    } catch (e) { setSearchError(e.message); setSearchResults([]); }
    finally { setIsSearching(false); }
  };

  const handleImageSearch = async (file) => {
    if (!file) return;
    setIsSearchingImage(true); setSearchError(null); setActiveFilter(null);
    try {
      const formData = new FormData(); formData.append("file", file);
      const res = await fetch(`${API_BASE_URL}/search/by-image`, { method: "POST", body: formData });
      if (!res.ok) throw new Error("Image search failed");
      const data = await res.json();
      setSearchResults(Array.isArray(data) ? data : data.items || []);
    } catch (e) { setSearchError(e.message); setSearchResults([]); }
    finally { setIsSearchingImage(false); }
  };

  const handleClear = () => { setSearchQuery(""); setSearchResults(null); setActiveFilter(null); setPriceFilter("all"); setSearchError(null); };
  const displayedItems = searchResults !== null ? searchResults : trendingItems.length > 0 ? trendingItems : null;

  return (
    <div className="min-h-screen bg-light-paper text-slate-900 flex flex-col antialiased selection:bg-amber-500 selection:text-white font-sans">
      {/* ── HEADER ── */}
      <header className="sticky top-0 z-50 glass-light border-b border-slate-200/80 transition-all duration-300">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <a href="#" className="flex items-center gap-3.5 group">
            <div className="w-11 h-11 rounded-2xl bg-slate-900 flex items-center justify-center text-amber-500 shadow-md group-hover:scale-105 transition-all duration-300">
              <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-xl tracking-tight text-slate-900">INDEX GEBEYA</span>
                <span className="inline-flex items-center gap-1.5 text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 animate-pulse"></span>LIVE INDEX
                </span>
              </div>
              <p className="text-[11px] text-slate-500 font-semibold tracking-wide -mt-0.5" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>ኢንዴክስ ገበያ — የቴሌግራም መፈለጊያ</p>
            </div>
          </a>
          <div className="flex items-center gap-3 sm:gap-6">
            <div className="hidden md:flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span>Monitoring <strong className="text-slate-900 font-bold">852</strong> Telegram Channels</span>
            </div>
            <a href="#sellers" className="hidden sm:inline-flex text-xs font-bold text-slate-700 hover:text-amber-600 transition-colors px-2 py-1">For Channel Admins</a>
            {!isTelegram && (
              <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 px-4 sm:px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-amber-600 text-white font-bold text-xs sm:text-sm shadow-md hover:shadow-lg transition-all transform active:scale-95">
                <svg className="w-4 h-4 fill-current text-amber-400" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-2.01 1.28-5.68 3.76-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.5-.85-.27-1.53-.42-1.47-.89.03-.25.38-.51 1.07-.78 4.2-1.82 7-3.03 8.4-3.61 4-.17 4.83 2.1 4.54 3.22z"/></svg>
                <span>Open in Telegram</span>
              </a>
            )}
          </div>
        </div>
      </header>

      {/* ── HERO ── */}
      <section className="relative pt-10 pb-16 md:pt-16 md:pb-24 border-b border-slate-200/80">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-amber-50 border border-amber-200/80 text-amber-900 text-xs font-medium shadow-sm mb-8">
            <span className="font-bold text-amber-700 text-sm" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>ምን ትፈልጋለህ?</span>
            <span className="text-amber-300">•</span>
            <span className="font-semibold">The Search Engine for Ethiopia's Telegram Marketplace</span>
          </div>
          <h1 className="text-3xl sm:text-5xl md:text-6xl font-black text-slate-900 tracking-tight leading-[1.12] max-w-4xl mx-auto mb-6">
            Every product posted on Ethiopian Telegram.<br className="hidden sm:inline"/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-600 via-amber-700 to-emerald-700">Indexed & Searchable in One Place.</span>
          </h1>
          <p className="text-base sm:text-lg md:text-xl text-slate-600 max-w-2xl mx-auto font-normal leading-relaxed mb-10">
            Thousands of sellers post cars, phones, shoes, and real estate inside disconnected Telegram channels every day. We monitor hundreds of channels, parse posts with AI, and bring everything into a single search bar.
          </p>

          {/* Search Bar + Filter Toolbar */}
          <div className="max-w-3xl mx-auto mb-8 text-left">
            <div className="bg-white p-3 sm:p-4 rounded-2xl sm:rounded-3xl border border-slate-200 shadow-xl focus-within:border-amber-500 focus-within:ring-4 focus-within:ring-amber-500/10 transition-all duration-300">
              <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3 items-center">
                <div className="relative flex-1 w-full flex items-center pl-3">
                  <svg className="w-6 h-6 text-amber-600 mr-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                  <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Try typing 'iPhone 13', 'Toyota Vitz', or 'Bole Apartment'..." className="w-full text-slate-900 placeholder-slate-400 font-medium text-base sm:text-lg focus:outline-none bg-transparent py-2" autoComplete="off"/>
                  {!searchQuery && (
                    <button type="button" onClick={() => fileInputRef.current?.click()} className="text-slate-400 hover:text-amber-600 p-1 mr-1 transition-colors" title="Search by image">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                    </button>
                  )}
                  {searchQuery && (
                    <button type="button" onClick={() => setSearchQuery("")} className="text-slate-400 hover:text-slate-600 p-1 mr-2 transition-colors">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                  )}
                </div>
                <input type="file" ref={fileInputRef} onChange={e => { if (e.target.files[0]) handleImageSearch(e.target.files[0]); e.target.value = ""; }} className="hidden" accept="image/*"/>
                <button type="submit" className="w-full sm:w-auto px-7 py-3.5 bg-slate-900 hover:bg-amber-600 text-white font-bold text-sm sm:text-base rounded-xl sm:rounded-2xl shadow-md hover:shadow-lg transition-all duration-300 flex items-center justify-center gap-2 shrink-0">
                  {isSearching || isSearchingImage ? "Searching…" : (<><span>Search Index</span><svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg></>)}
                </button>
              </form>
              {/* Filter Toolbar */}
              <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-1.5 overflow-x-auto pb-1 max-w-full no-scrollbar">
                  <span className="text-slate-400 font-bold uppercase text-[10px] tracking-wider shrink-0 mr-1">Category:</span>
                  {["All", "Phones", "Vehicles", "Real Estate", "Fashion", "Laptops", "Livestock"].map(cat => (
                    <button key={cat} onClick={() => { setActiveFilter(cat === "All" ? null : cat); }} className={`px-3 py-1 rounded-lg font-semibold transition-all text-[11px] shrink-0 ${(activeFilter || "All") === cat ? 'bg-amber-500 text-slate-950 font-bold shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-200'}`}>{cat}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-slate-400 font-bold uppercase text-[10px] tracking-wider">Price:</span>
                  <select value={priceFilter} onChange={e => setPriceFilter(e.target.value)} className="bg-slate-100 border border-slate-200 text-slate-700 text-xs rounded-lg px-2.5 py-1 focus:outline-none focus:border-amber-500 font-semibold">
                    <option value="all">Any Price</option>
                    <option value="under10k">&lt; 10,000 ETB</option>
                    <option value="10k50k">10,000 - 50,000 ETB</option>
                    <option value="50k500k">50,000 - 500,000 ETB</option>
                    <option value="over500k">&gt; 500,000 ETB</option>
                  </select>
                </div>
              </div>
            </div>
            {/* Quick Search Chips */}
            <div className="mt-4 flex flex-wrap items-center justify-center sm:justify-start gap-2 text-xs text-slate-600 px-1">
              <span className="text-slate-400 font-bold text-[10px] uppercase tracking-wider">Popular Searches:</span>
              {["iPhone 13", "Toyota Vitz 2019", "Nike Air Force", "Bole Apartment", "MacBook M1", "Borena Ox"].map(term => (
                <button key={term} onClick={() => { setSearchQuery(term); }} className="px-2.5 py-1 bg-white hover:bg-amber-50 border border-slate-200 hover:border-amber-400 rounded-lg text-slate-700 font-semibold transition-all text-xs shadow-xs">{term}</button>
              ))}
            </div>
          </div>

          {/* Results Section */}
          <div id="results-section" className="max-w-4xl mx-auto text-left mt-10 pt-2">
            {(isSearching || isSearchingImage) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {[1,2,3,4,5,6].map(i => (
                  <div key={i} className="bg-white rounded-2xl border border-slate-200 p-3 animate-pulse">
                    <div className="w-full h-40 bg-slate-200 rounded-xl mb-3"></div>
                    <div className="h-4 bg-slate-100 rounded w-3/4 mb-2"></div>
                    <div className="h-3 bg-slate-50 rounded w-1/2 mb-2"></div>
                    <div className="h-3 bg-slate-50 rounded w-1/4"></div>
                  </div>
                ))}
              </div>
            )}
            {displayedItems !== null && !isSearching && !isSearchingImage && (
              <>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5 px-1">
                  <div className="flex items-center gap-2.5">
                    <span className="px-2.5 py-0.5 rounded-md bg-slate-900 text-amber-400 font-bold text-xs">{searchResults !== null ? `${displayedItems.length} MATCHES` : "TRENDING"}</span>
                    <span className="text-xs sm:text-sm text-slate-500 font-medium">{activeFilter ? `Category: "${activeFilter}"` : searchResults !== null ? `Search: "${searchQuery}"` : "Showing featured posts across indexed channels"}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    {(activeFilter || searchQuery || priceFilter !== "all") && <button onClick={handleClear} className="text-xs font-bold text-amber-600 hover:underline">Reset Filters</button>}
                    {displayedItems !== null && (
                      <div className="flex items-center bg-white border border-slate-200 rounded-lg p-1 shadow-xs">
                        <button onClick={() => setViewMode("grid")} className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-amber-500 text-slate-950 font-bold' : 'text-slate-400 hover:text-slate-600'}`} title="Grid">
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2V5zM11 11a2 2 0 002-2h2a2 2 0 002 2v2a2 2 0 00-2 2h-2a2 2 0 00-2-2v-2z"/></svg>
                        </button>
                        <button onClick={() => setViewMode("list")} className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-amber-500 text-slate-950 font-bold' : 'text-slate-400 hover:text-slate-600'}`} title="List">
                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M3 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 4a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z" clipRule="evenodd"/></svg>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                {displayedItems.length === 0 ? (
                  <div className="bg-white rounded-3xl border border-slate-200 p-12 text-center text-slate-500 my-6 shadow-sm">
                    <div className="text-4xl mb-3">🔍</div>
                    <h4 className="font-bold text-slate-900 text-lg mb-1">No index matches found</h4>
                    <p className="text-xs text-slate-500 max-w-md mx-auto mb-5">Try clearing search filters or searching for "iPhone" or "Vitz".</p>
                    <button onClick={handleClear} className="px-5 py-2.5 bg-amber-500 text-slate-950 font-bold rounded-xl text-xs hover:bg-amber-400 transition-colors">Reset Search Filters</button>
                  </div>
                ) : viewMode === "list" ? (
                  <div className="space-y-3">
                    {displayedItems.map(item => (
                      <div key={item.id} className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-4 hover:border-amber-400 transition-all">
                        <div className="flex items-center gap-4 w-full sm:w-auto">
                          <img src={`${API_BASE_URL}/media/${item.image_path || item.images?.[0]}`} alt={item.title} className="w-16 h-16 rounded-xl object-cover shrink-0" onError={e => { e.target.src = 'https://placehold.co/400x400?text=No+Image'; }}/>
                          <div>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-bold text-amber-700">@{item.channel?.username || 'unknown'}</span>
                              <span className="text-[10px] text-slate-400">• {item.category}</span>
                            </div>
                            <h4 className="font-bold text-slate-900 text-sm sm:text-base leading-snug">{item.title}</h4>
                            <p className="text-xs text-slate-500 mt-0.5">📍 {item.location || 'Addis Ababa'}</p>
                          </div>
                        </div>
                        <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto pt-3 sm:pt-0 border-t sm:border-0 border-slate-100">
                          <div className="text-left sm:text-right"><span className="text-[10px] text-slate-400 block font-bold uppercase">Price</span><span className="text-base font-extrabold text-slate-900">{item.price?.toLocaleString?.() || item.price} {item.currency || 'ETB'}</span></div>
                          <a href={`https://t.me/${item.channel?.username}/${item.telegram_message_id}`} target="_blank" rel="noopener noreferrer" className="px-4 py-2 bg-slate-900 text-white text-xs font-bold rounded-xl hover:bg-amber-600 transition-colors">View Post</a>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                    {displayedItems.map(item => {
                      const imgSrc = item.image_path ? `${API_BASE_URL}/media/${item.image_path}` : (item.images?.[0] ? `${API_BASE_URL}/media/${item.images[0]}` : 'https://placehold.co/400x400?text=No+Image');
                      return (
                        <div key={item.id} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm hover:shadow-xl hover:border-amber-400 transition-all duration-300 group flex flex-col justify-between">
                          <div>
                            <div className="relative h-44 bg-slate-100 overflow-hidden">
                              <img src={imgSrc} alt={item.title} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" onError={e => { e.target.src = 'https://placehold.co/400x400?text=No+Image'; }}/>
                              <div className="absolute top-2.5 left-2.5 bg-slate-900/90 text-white text-[10px] font-bold px-2.5 py-1 rounded-md">{item.category || "General"}</div>
                              <div className="absolute top-2.5 right-2.5 bg-white/80 backdrop-blur-md text-slate-600 text-[10px] font-bold px-2 py-0.5 rounded-md">{item.created_at ? new Date(item.created_at).toLocaleDateString() : "Today"}</div>
                            </div>
                            <div className="p-4">
                              <div className="flex items-center justify-between gap-1 mb-1.5">
                                <span className="text-xs text-amber-700 font-bold">@{item.channel?.username || 'unknown'}</span>
                                <span className="text-[10px] text-slate-400 font-medium">{item.location || 'Addis Ababa'}</span>
                              </div>
                              <h4 className="font-bold text-slate-900 text-sm leading-snug line-clamp-2 group-hover:text-amber-600 transition-colors">{item.title}</h4>
                            </div>
                          </div>
                          <div className="px-4 pb-4 pt-3 border-t border-slate-100 flex items-center justify-between">
                            <div><span className="text-[10px] text-slate-400 block font-bold uppercase tracking-wider">Price</span><span className="text-base font-extrabold text-slate-900 tracking-tight">{item.price?.toLocaleString?.() || item.price || "Call"} <span className="text-xs font-semibold text-slate-500">{item.currency || 'ETB'}</span></span></div>
                            <a href={`https://t.me/${item.channel?.username}/${item.telegram_message_id}`} target="_blank" rel="noopener noreferrer" className="px-3.5 py-2 bg-slate-900 hover:bg-amber-600 text-white text-xs font-bold rounded-xl shadow-xs transition-colors flex items-center gap-1.5"><span>Open Post</span><svg className="w-3.5 h-3.5 fill-current text-amber-400" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-2.01 1.28-5.68 3.76-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.5-.85-.27-1.53-.42-1.47-.89.03-.25.38-.51 1.07-.78 4.2-1.82 7-3.03 8.4-3.61 4-.17 4.83 2.1 4.54 3.22z"/></svg></a>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Get Started button (Telegram onboarding) */}
          {isTelegram && onGetStarted && (
            <div className="mt-10 flex justify-center">
              <button onClick={() => onGetStarted({})} className="w-full sm:w-auto px-8 py-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-extrabold text-base rounded-2xl shadow-xl hover:shadow-amber-500/20 transition-all transform hover:-translate-y-0.5 active:scale-95">Get Started</button>
            </div>
          )}

          {/* Hero CTAs (open web) */}
          {!isTelegram && (
            <div className="mt-12 flex flex-col sm:flex-row items-center justify-center gap-4">
              <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto px-8 py-4 bg-slate-900 hover:bg-amber-600 text-white font-extrabold text-base rounded-2xl shadow-xl transition-all transform hover:-translate-y-0.5 flex items-center justify-center gap-3">
                <svg className="w-5 h-5 fill-current text-amber-400" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-2.01 1.28-5.68 3.76-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.5-.85-.27-1.53-.42-1.47-.89.03-.25.38-.51 1.07-.78 4.2-1.82 7-3.03 8.4-3.61 4-.17 4.83 2.1 4.54 3.22z"/></svg>
                <span>Open Index Gebeya Bot in Telegram</span>
              </a>
              <a href="#how-it-works" className="w-full sm:w-auto px-7 py-4 bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 font-bold text-base rounded-2xl shadow-xs transition-all text-center">See How Indexing Works</a>
            </div>
          )}
          <p className="text-xs text-slate-500 mt-4 font-medium">🔒 Free for all buyers • No app installation required • Direct Telegram chat</p>
        </div>
      </section>

      {/* ── STATS ── */}
      <section className="bg-slate-900 text-white py-12 border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 grid grid-cols-2 md:grid-cols-4 gap-6 text-center divide-y md:divide-y-0 md:divide-x divide-slate-800">
          <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-5xl font-black text-amber-400 tracking-tight">{stats?.product_count?.toLocaleString() || "--"}</p><p className="text-xs font-bold text-slate-400 mt-1 uppercase tracking-wider">Telegram Products Indexed</p></div>
          <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-5xl font-black text-emerald-400 tracking-tight">{stats?.channel_count?.toLocaleString() || "--"}</p><p className="text-xs font-bold text-slate-400 mt-1 uppercase tracking-wider">Active Channels Monitored</p></div>
          <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-5xl font-black text-sky-400 tracking-tight">0.3s</p><p className="text-xs font-bold text-slate-400 mt-1 uppercase tracking-wider">Average Search Speed</p></div>
          <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-5xl font-black text-white tracking-tight">0 Birr</p><p className="text-xs font-bold text-slate-400 mt-1 uppercase tracking-wider">Buyer Commission</p></div>
        </div>
      </section>

      {/* ── PROBLEM vs SOLUTION ── */}
      <section className="py-16 md:py-24 max-w-6xl mx-auto px-4">
        <div className="text-center max-w-3xl mx-auto mb-14">
          <span className="text-xs font-bold text-amber-700 uppercase tracking-widest block mb-2">The Structural Dilemma</span>
          <h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">Telegram is Ethiopia's digital market bazaar.<br/><span className="text-slate-500 font-normal">Except every shop is invisible from the street.</span></h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch">
          <div className="bg-red-50/70 border border-red-200/80 rounded-3xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-100 text-red-800 text-xs font-bold mb-6"><span>✕</span><span>Without Index Gebeya</span></div>
              <h3 className="text-xl font-extrabold text-slate-900 mb-4">The Endless Channel Maze</h3>
              <ul className="space-y-4 text-sm text-slate-700">
                {["You must manually join 30+ separate Telegram channels just to compare prices on a single phone.","Sellers post thousands of items daily that get buried under endless message threads within hours.","Global Telegram search only searches channel names—it cannot search product posts or prices inside Ethiopian channels.","You miss incredible deals simply because you weren't looking at the right channel at the right minute."].map((t,i) => (<li key={i} className="flex items-start gap-3 leading-relaxed"><span className="text-red-500 font-bold text-base shrink-0">✕</span><span>{t}</span></li>))}
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-red-200/60 text-xs text-red-800 font-bold uppercase tracking-wider">Result: Hours wasted scrolling, missed bargains, fragmented prices.</div>
          </div>
          <div className="bg-slate-900 text-white rounded-3xl p-6 sm:p-8 flex flex-col justify-between shadow-xl relative overflow-hidden">
            <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-amber-500/10 rounded-full blur-2xl pointer-events-none"></div>
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950 text-emerald-400 text-xs font-bold mb-6 border border-emerald-800"><span>✓</span><span>With Index Gebeya</span></div>
              <h3 className="text-xl font-extrabold text-white mb-4">One Search. Entire Marketplace.</h3>
              <ul className="space-y-4 text-sm text-slate-200">
                {["Search 852 channels at once. Type 'iPhone 13 128GB under 50,000 Birr' and see every match instantly.","AI extracts product specs, prices in ETB, and contact handles automatically from raw Amharic posts.","Set instant Telegram push notifications. Get alerted the exact second a matching item is posted anywhere.","Direct connection to the seller's original Telegram post. Zero middleman markup, zero extra app to install."].map((t,i) => (<li key={i} className="flex items-start gap-3 leading-relaxed"><span className="text-emerald-400 font-bold text-base shrink-0">✓</span><span>{t}</span></li>))}
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-slate-800 text-xs text-slate-300 font-bold flex items-center justify-between"><span>Result: Found in 5 seconds. Direct seller contact.</span><span className="text-amber-400">100% Free</span></div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how-it-works" className="py-16 md:py-24 bg-white border-y border-slate-200/80">
        <div className="max-w-6xl mx-auto px-4">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <span className="text-xs font-bold text-amber-700 uppercase tracking-widest">Simple & Fast</span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">How Index Gebeya Works</h2>
            <p className="text-slate-600 text-sm sm:text-base mt-2 font-medium">No passwords. No sign-up forms. Powered by Telegram Mini App technology.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[{ num:"01", title:"Search & Filter Across All Channels", desc:"Type what you need in plain text or Amharic. Filter by price range in Birr, location in Addis Ababa, or category.", icon:"🔍", note:"AI extracts raw channel posts instantly" },{ num:"02", title:"Set Instant Keyword Alerts", desc:'Looking for a specific item like "Toyota Vitz under 1.2M Birr"? Save an alert and get notified on Telegram the millisecond a channel posts it.', icon:"🔔", note:"Never miss rare or underpriced deals" },{ num:"03", title:"Deal Directly with the Seller", desc:"Tap any product result to open the original Telegram channel post. Call or message the seller directly on Telegram.", icon:"💬", note:"Direct Telegram chat connection" }].map((step,i) => (
              <div key={i} className="bg-light-paper rounded-2xl p-6 sm:p-8 border border-slate-200 flex flex-col justify-between hover:shadow-md transition-shadow">
                <div><div className="w-12 h-12 rounded-xl bg-slate-900 text-amber-400 font-extrabold text-xl flex items-center justify-center mb-6 shadow-sm">{step.num}</div><h3 className="text-xl font-bold text-slate-900 mb-2">{step.title}</h3><p className="text-sm text-slate-600 leading-relaxed">{step.desc}</p></div>
                <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 font-semibold flex items-center gap-2"><span className="text-base">{step.icon}</span><span>{step.note}</span></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CATEGORIES ── */}
      <section className="py-16 md:py-24 max-w-6xl mx-auto px-4">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-12">
          <div><span className="text-xs font-bold text-amber-700 uppercase tracking-widest">Marketplace Scope</span><h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">What You Can Find Today</h2></div>
          <p className="text-xs sm:text-sm text-slate-500 mt-2 sm:mt-0 font-medium">Click any category to filter results above</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(TAXONOMY).slice(0, 8).map(([cat, subs]) => {
            const catCount = stats?.category_counts?.[cat] || null;
            return (
              <button key={cat} onClick={() => { setActiveFilter(cat); setSearchQuery(""); document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth' }); }} className={`group p-5 bg-white border border-slate-200 rounded-2xl text-left transition-all duration-300 hover:border-amber-500 hover:shadow-md ${activeFilter === cat ? 'border-amber-500 ring-2 ring-amber-500/20 bg-amber-50/30' : ''}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-800 flex items-center justify-center text-xl group-hover:scale-110 transition-transform">
                    {cat === "Mobile Phones" ? "📱" : cat === "Laptops & Computers" ? "💻" : cat === "Electronics" ? "🔌" : cat === "Vehicles" ? "🚗" : cat === "Property" ? "🏠" : cat === "Shoes" ? "👟" : cat === "Men's Fashion" ? "👔" : cat === "Women's Fashion" ? "👗" : "📦"}
                  </div>
                  {catCount !== null && <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">{catCount.toLocaleString()}+</span>}
                </div>
                <h3 className="font-bold text-slate-900 text-sm sm:text-base group-hover:text-amber-700 transition-colors">{cat}</h3>
                <p className="text-xs text-slate-500 mt-1 line-clamp-1">{subs.slice(0, 3).join(", ")}</p>
              </button>
            );
          })}
        </div>
      </section>

      {/* ── FOR SELLERS ── */}
      <section id="sellers" className="py-16 md:py-24 bg-slate-900 text-white border-t border-slate-800">
        <div className="max-w-6xl mx-auto px-4">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7">
              <span className="text-xs font-bold text-amber-400 uppercase tracking-widest">For Telegram Channel Admins</span>
              <h2 className="text-3xl sm:text-5xl font-black text-white tracking-tight mt-2 mb-6 leading-tight">Run a Telegram Sales Channel?<br/><span className="text-amber-400">Get Found Beyond Your Subscribers.</span></h2>
              <p className="text-slate-300 text-base leading-relaxed mb-8">Most Telegram posts are only seen by people who already follow your channel. When you add Index Gebeya bot to your channel as an admin, your products are automatically indexed and presented to thousands of active buyers searching across Ethiopia every day.</p>
              <div className="space-y-4 mb-8">
                {["Zero Extra Effort: Post in your channel normally. Our AI automatically extracts your images, prices, and title.","Direct Traffic: Buyers tap your product and land directly on your original channel post to message you.","Live Stock Sync: Deleted or edited channel posts automatically sync in real-time."].map((t,i) => (<div key={i} className="flex items-start gap-3"><div className="w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">✓</div><p className="text-sm text-slate-200"><strong className="text-white">{t.split(':')[0]}:</strong>{t.split(':').slice(1).join(':')}</p></div>))}
              </div>
              <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-3 px-8 py-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-sm sm:text-base rounded-2xl shadow-lg transition-all"><span>+ Add Your Channel to Index</span></a>
            </div>
            <div className="lg:col-span-5 bg-slate-800/90 border border-slate-700 p-6 sm:p-8 rounded-3xl shadow-2xl">
              <h3 className="text-lg font-bold text-white mb-2">⚡ Estimated Reach</h3>
              <p className="text-xs text-slate-400 mb-6">Channels indexed with Index Gebeya see their products surfaced in thousands of buyer searches.</p>
              <div className="p-5 rounded-2xl bg-slate-900 border border-slate-700 text-center">
                <span className="text-xs text-slate-400 block mb-1 font-bold uppercase tracking-wider">Estimated Monthly Extra Reach</span>
                <span className="text-3xl font-black text-emerald-400 tracking-tight">18,500+</span>
                <span className="text-xs text-slate-400 block mt-1">active buyer searches in Ethiopia</span>
              </div>
              <div className="mt-4 text-[11px] text-slate-400 leading-relaxed bg-slate-900/60 p-3.5 rounded-xl border border-slate-700">💡 Channels indexed with Index Gebeya experience an average <strong className="text-white">+38% increase</strong> in direct Telegram buyer inquiries in Addis Ababa.</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── PHONE MOCKUP ── */}
      <section className="py-16 md:py-24 max-w-5xl mx-auto px-4">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <span className="text-xs font-bold text-amber-700 uppercase tracking-widest">Telegram Native Experience</span>
          <h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">Zero Web Apps to Install.<br/>Runs Inside Your Telegram App.</h2>
          <p className="text-sm text-slate-600 mt-2 font-medium">Tap below to switch views inside our live Telegram Mini App preview mockup.</p>
        </div>
        <div className="flex justify-center">
          <div className="w-full max-w-sm bg-slate-200 p-4 rounded-[40px] shadow-2xl border-4 border-slate-300 relative">
            <div className="w-28 h-5 bg-slate-300 rounded-b-xl mx-auto absolute top-4 left-1/2 -translate-x-1/2 z-20"></div>
            <div className="bg-white rounded-[30px] pt-8 pb-4 px-3 text-slate-900 overflow-hidden min-h-[500px] flex flex-col justify-between relative z-10 border border-slate-200">
              <div>
                <div className="flex items-center justify-between px-2 pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2"><div className="w-7 h-7 rounded-lg bg-amber-500 text-white font-black text-xs flex items-center justify-center">IG</div><div><h4 className="font-bold text-xs text-slate-900">Index Gebeya Bot</h4><p className="text-[10px] text-slate-400">Telegram Mini App</p></div></div>
                  <span className="text-[10px] bg-slate-100 border border-slate-200 text-amber-600 px-2 py-0.5 rounded-full font-mono">v2.4</span>
                </div>
                <div className="py-4 px-1 space-y-3">
                  {phoneTab === 'explore' && (<>
                    <div className="bg-slate-50 p-2.5 rounded-xl border border-slate-100 flex items-center gap-2 text-xs text-slate-500"><span>🔍</span><span className="text-slate-400 text-[11px]">Search 142k+ Telegram items...</span></div>
                    {[{ icon:"📱", title:"iPhone 13 128GB Gold", channel:"@EthioTechHub", price:"48,500 ETB" },{ icon:"🚗", title:"Toyota Vitz 2019", channel:"@AddisAutoDeals", price:"1.25M ETB" },{ icon:"💻", title:"MacBook Air M1 256GB", channel:"@LaptopsAddis", price:"52,000 ETB" }].map((p,i) => (
                      <div key={i} className="bg-white p-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center gap-2.5">
                        <div className="w-9 h-9 rounded-lg bg-amber-50 text-amber-600 border border-amber-100 flex items-center justify-center text-sm font-bold shrink-0">{p.icon}</div>
                        <div className="flex-1 min-w-0"><h5 className="text-xs font-bold truncate text-slate-900">{p.title}</h5><p className="text-[10px] text-slate-400">{p.channel} • {p.price}</p></div>
                        <span className="text-[9px] bg-emerald-50 text-emerald-600 border border-emerald-100 px-1.5 py-0.5 rounded font-bold">Match</span>
                      </div>
                    ))}
                  </>)}
                  {phoneTab === 'alerts' && (<>
                    <div className="text-xs text-amber-600 font-bold mb-2 flex items-center gap-1.5"><span>🔔</span><span>Active Telegram Keyword Alerts</span></div>
                    {[{ q:'"Toyota Vitz"', max:'1,300,000 Birr' },{ q:'"MacBook Air M1"', max:'55,000 Birr' }].map((a,i) => (
                      <div key={i} className="bg-white p-2.5 rounded-xl border border-slate-100 shadow-sm flex items-center justify-between mb-2"><div><span className="text-xs font-bold text-slate-900 block">{a.q}</span><span className="text-[10px] text-slate-400">Max limit: {a.max}</span></div><span className="text-[9px] bg-amber-50 text-amber-600 border border-amber-100 px-2 py-0.5 rounded-full font-bold">ACTIVE</span></div>
                    ))}
                  </>)}
                  {phoneTab === 'stores' && (<div className="p-4 bg-white rounded-xl border border-slate-100 shadow-sm text-center text-xs text-slate-500"><div className="text-2xl mb-1">🏪</div><p className="font-semibold text-slate-900 mb-1">Your Indexed Channels</p><p className="text-[11px] leading-relaxed text-slate-400">Add your Telegram channel to get products listed and reach thousands of buyers across Ethiopia.</p></div>)}
                </div>
              </div>
              <div className="bg-slate-50 rounded-2xl p-1.5 grid grid-cols-3 gap-1 text-center border border-slate-100">
                  {['explore','alerts','stores'].map(tab => (
                    <button key={tab} onClick={() => setPhoneTab(tab)} className={`py-1.5 px-2 rounded-xl text-xs font-bold transition-all ${phoneTab === tab ? 'bg-amber-500 text-slate-950' : 'text-slate-400 hover:text-white'}`}>{tab === 'explore' ? '🔍 Explore' : tab === 'alerts' ? '🔔 Alerts' : '🏪 Stores'}</button>
                  ))}
                </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="py-16 md:py-24 bg-light-paper border-t border-slate-200/80">
        <div className="max-w-4xl mx-auto px-4">
          <div className="text-center mb-14"><span className="text-xs font-bold text-amber-700 uppercase tracking-widest">Clear & Transparent</span><h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">Frequently Asked Questions</h2><p className="text-slate-600 text-sm mt-2 font-medium">Everything you need to know about Index Gebeya.</p></div>
          <div className="space-y-4">
            {faqs.map((faq, i) => (
              <div key={i} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-xs">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)} className="w-full p-5 sm:p-6 text-left font-bold text-slate-900 text-base sm:text-lg flex justify-between items-center hover:bg-slate-50 transition-colors">
                  <span className="pr-4">{faq.q}</span><span className="text-amber-600 text-2xl shrink-0">{openFaq === i ? '−' : '+'}</span>
                </button>
                {openFaq === i && <div className="p-5 sm:p-6 pt-0 text-sm text-slate-600 leading-relaxed border-t border-slate-100">{faq.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FINAL CTA (open web only) ── */}
      {!isTelegram && (
        <section className="py-16 bg-slate-900 text-white border-t border-slate-800">
          <div className="max-w-4xl mx-auto px-4 text-center">
            <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight mb-4">Stop Scrolling 50 Telegram Channels.<br/><span className="text-amber-400">Start Searching Index Gebeya.</span></h2>
            <p className="text-slate-400 text-sm sm:text-base max-w-xl mx-auto mb-8 leading-relaxed">Open our Mini App directly inside Telegram and find what you're looking for in seconds.</p>
            <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-3 px-8 py-4 bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-base rounded-2xl shadow-xl transition-all transform hover:-translate-y-0.5"><span>Open @IndexGebeyaBot</span></a>
          </div>
        </section>
      )}

      {/* ── FOOTER ── */}
      <footer className="bg-slate-950 text-slate-400 py-10 border-t border-slate-900 text-xs">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div><div className="flex items-center gap-2.5 mb-1.5"><span className="font-extrabold text-white text-sm tracking-tight">INDEX GEBEYA</span><span className="text-slate-700">•</span><span className="text-slate-400" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>የኢትዮጵያ ቴሌግራም ገበያ መፈለጊያ</span></div><p className="text-slate-500">© 2026 Index Gebeya. Built for the Ethiopian Telegram Community.</p></div>
          <div className="flex flex-wrap items-center gap-6 text-slate-400 font-medium">
            <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="hover:text-amber-400 transition-colors">Telegram Bot</a>
            <a href="#sellers" className="hover:text-amber-400 transition-colors">For Sellers</a>
            <a href="#how-it-works" className="hover:text-amber-400 transition-colors">About Indexing</a>
            <span className="text-slate-800">|</span>
            <span className="flex items-center gap-2 text-slate-300"><span className="w-2 h-2 rounded-full bg-emerald-500"></span><span>Addis Ababa, Ethiopia</span></span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
