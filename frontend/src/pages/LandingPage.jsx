import React, { useState, useEffect, useRef } from 'react';
import { API_BASE_URL } from '../config';
import ItemCard from '../components/ItemCard';
import { TAXONOMY } from '../constants/taxonomy';

// Emoji mapping for taxonomy categories (deterministic per-key lookup)
const CATEGORY_EMOJIS = {
  "Mobile Phones": "📱",
  "Laptops & Computers": "💻",
  "Tablets": "📟",
  "Electronics": "🔌",
  "Vehicles": "🚗",
  "Property": "🏠",
  "Home, Appliances & Furniture": "🛋️",
  "Men's Fashion": "👔",
  "Women's Fashion": "👗",
  "Shoes": "👟",
  "Health & Beauty": "💄",
  "Commercial & Tools": "🔧",
  "Sports, Arts & Outdoors": "⚽",
  "Babies & Kids": "👶",
  "Animals & Pets": "🐕",
  "Agriculture & Food": "🌾",
  "Services": "🛠️",
  "Other": "📦",
};

const faqs = [
  { q: "Why build this for Telegram instead of a separate website?", a: "Because that's where Ethiopian commerce already happens. Over 80% of digital selling in Ethiopia occurs inside Telegram channels. Rather than forcing thousands of sellers to create website accounts, we bring search technology directly to where they post every single day." },
  { q: "Do you sell products directly or process payments?", a: "No. We are strictly a search engine—an index. When you click on a product, Index Gebeya connects you directly to the original seller's post inside Telegram. You talk, negotiate, and inspect the item with the seller directly." },
  { q: "Is Index Gebeya free for buyers?", a: "Yes! It is 100% free for buyers. You can search unlimited products, set price alert notifications, and connect with sellers without paying any fees or subscriptions." },
  { q: "I own a Telegram channel. How do I get my products listed?", a: "It takes 30 seconds. Simply add our Telegram bot (@IndexGebeyaBot) to your public Telegram channel as an admin. The bot automatically reads your new posts, extracts images and prices, and makes them searchable on Index Gebeya immediately." },
  { q: "Is this service only available in Ethiopia?", a: "Yes. Today, Index Gebeya is specifically built for Ethiopia. Prices are processed in Ethiopian Birr (ETB), search keywords support English and Amharic, and locations cover key hubs across Addis Ababa and major regions." },
];

const LandingPage = ({ isTelegram = false, onGetStarted = null }) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState(null);
  const [openFaq, setOpenFaq] = useState(null);
  const [phoneTab, setPhoneTab] = useState("search");

  // Real API state
  const [searchResults, setSearchResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchingImage, setIsSearchingImage] = useState(false);
  const [stats, setStats] = useState(null);
  const [searchError, setSearchError] = useState(null);

  const fileInputRef = useRef(null);

  // Fetch stats on mount
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/items/stats`);
        if (!res.ok) throw new Error("Stats fetch failed");
        const data = await res.json();
        setStats(data);
      } catch {
        setStats({ product_count: null, channel_count: null, category_counts: {} });
      }
    };
    fetchStats();
  }, []);

  // Real API search
  const handleSearch = async (e) => {
    e.preventDefault();
    const q = searchQuery.trim();
    if (!q) { setSearchResults(null); setActiveFilter(null); setSearchError(null); return; }
    setIsSearching(true);
    setSearchError(null);
    setActiveFilter(null);
    try {
      const res = await fetch(`${API_BASE_URL}/search/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, limit: 50 }),
      });
      if (!res.ok) throw new Error("Search failed");
      const data = await res.json();
      setSearchResults(data.items || []);
    } catch (err) {
      setSearchError(err.message || "Search failed. Please try again.");
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // Image search handler
  const handleImageSearch = async (file) => {
    if (!file) return;
    setIsSearchingImage(true);
    setSearchError(null);
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch(`${API_BASE_URL}/search/by-image`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error("Image search failed");
      const data = await res.json();
      setSearchResults(Array.isArray(data) ? data : data.items || []);
      setActiveFilter(null);
    } catch (err) {
      setSearchError("Could not process image. Please try another photo.");
    } finally {
      setIsSearchingImage(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Category filter using taxonomy lookup
  const handleCategoryFilter = (catName) => {
    setSearchQuery(catName);
    setActiveFilter(catName);
    // Trigger a search with the category name
    setIsSearching(true);
    setSearchError(null);
    fetch(`${API_BASE_URL}/search/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: catName, limit: 50 }),
    })
      .then(res => res.json())
      .then(data => setSearchResults(data.items || []))
      .catch(() => setSearchError("Category search failed"))
      .finally(() => setIsSearching(false));
    document.getElementById('results-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleClear = () => {
    setSearchQuery("");
    setActiveFilter(null);
    setSearchResults(null);
    setSearchError(null);
  };

  const displayedItems = searchResults !== null
    ? searchResults
    : null;

  // Build category list from TAXONOMY with stats from API
  const categoryEntries = Object.entries(TAXONOMY).map(([catName, subcats]) => {
    const emoji = CATEGORY_EMOJIS[catName] || "📁";
    const description = subcats.slice(0, 3).join(", ") + (subcats.length > 3 ? "…" : "");
    const count = stats?.category_counts?.[catName] ?? null;
    return { name: catName, emoji, description, count };
  });

  return (
    <div className="bg-ethiopia-paper text-slate-900 selection:bg-brand-500 selection:text-white min-h-screen overflow-x-hidden antialiased font-sans">
      {/* ── HEADER ── */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-ethiopia-paper/90 border-b border-ethiopia-border transition-all">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <a href="#" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center text-brand-500 shadow-md transition-transform group-hover:scale-105">
              <svg className="w-6 h-6 fill-current" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-extrabold text-xl tracking-tight text-slate-900">INDEX GEBEYA</span>
                <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">LIVE</span>
              </div>
              <p className="text-[11px] text-slate-500 tracking-wider -mt-0.5" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>ኢንዴክስ ገበያ — ቴሌግራም መፈለጊያ</p>
            </div>
          </a>
          <div className="flex items-center gap-3 sm:gap-5">
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse-ring"></span>
              <span>Monitoring <strong className="text-slate-900 font-semibold">850+</strong> Channels</span>
            </div>
            {!isTelegram && (
              <>
                <a href="#sellers" className="hidden sm:inline-flex text-xs font-semibold text-slate-700 hover:text-brand-600 transition-colors px-3 py-2">For Sellers</a>
                <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-brand-600 text-white font-semibold text-xs sm:text-sm shadow-md hover:shadow-brand-500/20 transition-all transform active:scale-95">
                  <svg className="w-4 h-4 fill-current text-sky-400" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-2.01 1.28-5.68 3.76-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.5-.85-.27-1.53-.42-1.47-.89.03-.25.38-.51 1.07-.78 4.2-1.82 7-3.03 8.4-3.61 4-.17 4.83 2.1 4.54 3.22z"/></svg>
                  <span>Open in Telegram</span>
                </a>
              </>
            )}
            {isTelegram && (
              <span className="text-xs font-semibold text-slate-500 px-3 py-2">Welcome to Index Gebeya</span>
            )}
          </div>
        </div>
      </header>

      {/* ── HERO ── */}
      <section className="relative pt-8 pb-16 md:pt-14 md:pb-24 bg-mesh border-b border-ethiopia-border/60">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-brand-50 border border-brand-200/80 text-brand-800 text-xs font-medium mb-6 animate-fade-in">
            <span className="font-semibold text-sm" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>ምን ትፈልጋለህ?</span>
            <span className="text-brand-300">•</span>
            <span>The Search Engine for Ethiopia's Telegram Marketplace</span>
          </div>

          <h1 className="text-3xl sm:text-5xl md:text-6xl font-black text-slate-900 tracking-tight leading-[1.12] max-w-4xl mx-auto mb-6">
            Every product posted on Ethiopian Telegram.<br className="hidden sm:inline"/>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-brand-600 via-amber-700 to-ethiopia-green">Indexed & Searchable in One Place.</span>
          </h1>

          <p className="text-base sm:text-lg md:text-xl text-slate-600 max-w-2xl mx-auto font-normal leading-relaxed mb-10">
            Thousands of sellers post cars, phones, shoes, and real estate inside disconnected Telegram channels every day. We monitor hundreds of channels, parse their posts with AI, and bring everything into a single search bar.
          </p>

          {/* Search Bar */}
          <div className="max-w-3xl mx-auto mb-8 text-left">
            <div className="bg-white p-3 sm:p-4 rounded-2xl sm:rounded-3xl shadow-xl border border-slate-200/80 focus-within:border-brand-500 focus-within:ring-4 focus-within:ring-brand-500/10 transition-all">
              <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-3 items-center">
                <div className="relative flex-1 w-full flex items-center pl-3">
                  <svg className="w-6 h-6 text-slate-400 mr-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                  <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Try typing 'iPhone 13', 'Toyota Vitz', or 'Bole Apartment'..." className="w-full text-slate-800 placeholder-slate-400 font-medium text-base sm:text-lg focus:outline-none bg-transparent py-2" autoComplete="off"/>
                  {searchQuery && (
                    <button type="button" onClick={handleClear} className="text-slate-400 hover:text-slate-600 p-1 mr-2">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"/></svg>
                    </button>
                  )}
                </div>
                {/* Camera button for image search */}
                <button type="button" onClick={() => fileInputRef.current?.click()} className="w-full sm:w-auto px-4 py-3.5 bg-white border border-slate-200 hover:border-brand-500 text-slate-600 hover:text-brand-600 rounded-xl sm:rounded-2xl transition-all flex items-center justify-center gap-2" disabled={isSearchingImage}>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                  {isSearchingImage ? <span>Scanning…</span> : null}
                </button>
                <input type="file" ref={fileInputRef} onChange={e => { if (e.target.files?.[0]) handleImageSearch(e.target.files[0]); }} hidden accept="image/*" />
                <button type="submit" className="w-full sm:w-auto px-7 py-3.5 bg-brand-600 hover:bg-brand-700 text-white font-bold text-sm sm:text-base rounded-xl sm:rounded-2xl shadow-md transition-all flex items-center justify-center gap-2 shrink-0" disabled={isSearching}>
                  {isSearching ? (
                    <span>Searching…</span>
                  ) : (
                    <>
                      <span>Search Index</span>
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
                    </>
                  )}
                </button>
              </form>
            </div>
            {/* Quick Search Chips */}
            <div className="mt-4 flex flex-wrap items-center justify-center sm:justify-start gap-2 text-xs font-medium text-slate-600">
              <span className="text-slate-400 uppercase tracking-wider font-semibold text-[10px] sm:text-xs">Popular Searches:</span>
              {["iPhone 13","Toyota Vitz 2019","Nike Air Force","Bole Apartment","MacBook M1","Borena Ox"].map(q => (
                <button key={q} onClick={() => { setSearchQuery(q); }} className="px-2.5 py-1 bg-white hover:bg-brand-50 border border-slate-200 rounded-lg text-slate-700 hover:border-brand-300 transition-all">{q}</button>
              ))}
            </div>
          </div>

          {/* Results */}
          <div id="results-section" className="max-w-4xl mx-auto text-left mt-8">
            {/* Loading skeleton while search is in progress */}
            {(isSearching || isSearchingImage) && (
              <div className="space-y-4 mb-6">
                <div className="flex items-center gap-2 mb-4 px-1">
                  <div className="px-2.5 py-0.5 rounded-md bg-slate-200 animate-pulse h-6 w-24"></div>
                  <div className="h-4 bg-slate-100 animate-pulse rounded w-56"></div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {[1, 2, 3, 4, 5, 6].map(i => (
                    <div key={i} className="bg-white rounded-2xl border border-slate-200 p-3 animate-pulse">
                      <div className="w-full h-40 bg-slate-200 rounded-xl mb-3"></div>
                      <div className="h-4 bg-slate-100 rounded w-3/4 mb-2"></div>
                      <div className="h-3 bg-slate-50 rounded w-1/2 mb-2"></div>
                      <div className="h-3 bg-slate-50 rounded w-1/4"></div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {displayedItems !== null && (
              <>
                <div className="flex items-center justify-between mb-4 px-1">
                  <div className="flex items-center gap-2">
                    <span className="px-2.5 py-0.5 rounded-md bg-slate-900 text-brand-400 font-mono text-xs font-bold">{displayedItems.length} MATCHES</span>
                    <span className="text-xs sm:text-sm text-slate-500 font-medium">{activeFilter ? `Filtered by: "${activeFilter}"` : "Showing search results across indexed channels"}</span>
                  </div>
                  {activeFilter && <button onClick={handleClear} className="text-xs font-semibold text-brand-600 hover:underline">Show All</button>}
                </div>
                {displayedItems.length === 0 && !isSearching && !isSearchingImage ? (
                  <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
                    <p className="text-slate-500 text-base font-medium">No items match this search.</p>
                    <p className="text-slate-400 text-sm mt-1">Try different keywords or browse categories below.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {displayedItems.map(item => (
                      <ItemCard
                        key={item.id}
                        item={item}
                        apiUrl={API_BASE_URL}
                        onSelect={() => window.open(`https://t.me/${item.channel?.username}/${item.telegram_message_id}`, '_blank')}
                      />
                    ))}
                  </div>
                )}
              </>
            )}
            {searchError && (
              <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 font-medium text-center">
                {searchError}
              </div>
            )}
          </div>

          {/* Hero CTAs — hidden inside Telegram, shown on open web */}
          {!isTelegram && (
            <div className="mt-12 flex flex-col sm:flex-row items-center justify-center gap-4">
              <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto px-8 py-4 bg-slate-900 hover:bg-brand-600 text-white font-bold text-base rounded-2xl shadow-xl hover:shadow-brand-500/20 transition-all transform hover:-translate-y-0.5 flex items-center justify-center gap-3">
                <svg className="w-5 h-5 fill-current text-sky-400" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-2.01 1.28-5.68 3.76-.54.37-1.03.55-1.47.54-.48-.01-1.4-.27-2.09-.5-.85-.27-1.53-.42-1.47-.89.03-.25.38-.51 1.07-.78 4.2-1.82 7-3.03 8.4-3.61 4-.17 4.83 2.1 4.54 3.22z"/></svg>
                <span>Open Index Gebeya Bot in Telegram</span>
              </a>
              <a href="#how-it-works" className="w-full sm:w-auto px-6 py-4 bg-white hover:bg-slate-50 border border-slate-300 text-slate-800 font-semibold text-base rounded-2xl shadow-sm transition-all text-center">See How Indexing Works</a>
            </div>
          )}
          <p className="text-xs text-slate-500 mt-4">🔒 Free for all buyers. No app installation required. Works directly inside your Telegram app.</p>
        </div>
      </section>

      {/* ── STATS BAR ── */}
      <section className="bg-slate-900 text-white py-12 border-b border-slate-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6 md:gap-8 text-center divide-y md:divide-y-0 md:divide-x divide-slate-800/80">
            <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-4xl lg:text-5xl font-black text-brand-500 tracking-tight font-mono">{stats?.product_count?.toLocaleString() || "--"}</p><p className="text-xs sm:text-sm font-medium text-slate-400 mt-1 uppercase tracking-wider">Telegram Products Indexed</p></div>
            <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-4xl lg:text-5xl font-black text-emerald-400 tracking-tight font-mono">{stats?.channel_count?.toLocaleString() || "--"}</p><p className="text-xs sm:text-sm font-medium text-slate-400 mt-1 uppercase tracking-wider">Active Channels Monitored</p></div>
            <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-4xl lg:text-5xl font-black text-amber-400 tracking-tight font-mono">0.3s</p><p className="text-xs sm:text-sm font-medium text-slate-400 mt-1 uppercase tracking-wider">Average Search Speed</p></div>
            <div className="pt-4 md:pt-0"><p className="text-3xl sm:text-4xl lg:text-5xl font-black text-sky-400 tracking-tight font-mono">0 Birr</p><p className="text-xs sm:text-sm font-medium text-slate-400 mt-1 uppercase tracking-wider">Buyer Commission</p></div>
          </div>
        </div>
      </section>

      {/* ── PROBLEM vs SOLUTION ── */}
      <section className="py-16 md:py-24 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-xs font-bold text-brand-600 uppercase tracking-widest mb-2">The Structural Dilemma</h2>
          <h3 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">Telegram is Ethiopia's digital market bazaar.<br/><span className="text-slate-500 font-normal">Except every shop is invisible from the street.</span></h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch">
          <div className="bg-red-50/50 border border-red-200/80 rounded-3xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-100 text-red-700 text-xs font-bold mb-6"><span>✗</span><span>Without Index Gebeya</span></div>
              <h4 className="text-xl font-bold text-slate-900 mb-4">The Endless Channel Maze</h4>
              <ul className="space-y-4 text-sm text-slate-700">
                {["You must manually join 30+ separate Telegram channels just to compare prices on one phone.","Sellers post thousands of items daily that get buried under endless message threads within hours.","Global Telegram search only searches channel names—it cannot search product posts or prices inside Ethiopian channels.","You miss incredible deals simply because you weren't looking at the right channel at the right minute."].map((t,i) => (<li key={i} className="flex items-start gap-3"><span className="text-red-500 font-bold shrink-0">✗</span><span>{t}</span></li>))}
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-red-200/60 text-xs text-red-800 font-mono font-medium">RESULT: Hours wasted scrolling, missed bargains, fragmented prices.</div>
          </div>
          <div className="bg-emerald-950 text-white rounded-3xl p-6 sm:p-8 flex flex-col justify-between shadow-xl relative overflow-hidden">
            <div className="absolute -right-10 -bottom-10 w-40 h-40 bg-brand-500/10 rounded-full blur-2xl"></div>
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-800/80 text-emerald-200 text-xs font-bold mb-6 border border-emerald-700"><span>✓</span><span>With Index Gebeya</span></div>
              <h4 className="text-xl font-bold text-white mb-4">One Search. Entire Marketplace.</h4>
              <ul className="space-y-4 text-sm text-emerald-100">
                {["Search 800+ channels at once. Type 'iPhone 13 128GB under 50,000 Birr' and see every match instantly.","AI extracts product specs, prices in ETB, and contact handles automatically from raw Amharic posts.","Set instant Telegram push notifications. Get alerted the exact second a matching item is posted anywhere.","Direct connection to the seller's original Telegram post. Zero middleman markup, zero extra app to install."].map((t,i) => (<li key={i} className="flex items-start gap-3"><span className="text-emerald-400 font-bold shrink-0">✓</span><span>{t}</span></li>))}
              </ul>
            </div>
            <div className="mt-8 pt-6 border-t border-emerald-800/80 text-xs text-emerald-300 font-mono font-medium flex items-center justify-between"><span>RESULT: Found in 5 seconds. Direct contact with seller.</span><span className="text-brand-400 font-bold">100% Free</span></div>
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section id="how-it-works" className="py-16 md:py-24 bg-white border-y border-ethiopia-border/80">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <span className="text-xs font-bold text-brand-600 uppercase tracking-widest">Simple & Fast</span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">How Index Gebeya Works</h2>
            <p className="text-slate-600 text-sm sm:text-base mt-2">No passwords. No sign-up forms. Powered by Telegram Mini App technology.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {[{ num: "01", title: "Search & Filter Across All Channels", desc: "Type what you need in plain text or Amharic. Filter by price range in Birr, location in Addis Ababa, or category.", icon: "🔍", note: "AI extracts raw channel posts instantly" },
              { num: "02", title: "Set Instant Keyword Alerts", desc: "Looking for a specific item like \"Toyota Vitz under 1.2M Birr\"? Save an alert and get notified on Telegram the millisecond a channel posts it.", icon: "🔔", note: "Never miss rare or underpriced deals" },
              { num: "03", title: "Deal Directly with the Seller", desc: "Tap any product result to open the original Telegram channel post. Call or message the seller directly on Telegram.", icon: "💬", note: "Direct Telegram chat connection" }].map((step, i) => (
              <div key={i} className="bg-ethiopia-paper rounded-2xl p-6 sm:p-8 border border-slate-200/80 flex flex-col justify-between hover:shadow-md transition-shadow">
                <div>
                  <div className={`w-12 h-12 rounded-xl ${i === 0 ? 'bg-slate-900 text-brand-500' : i === 1 ? 'bg-brand-600 text-white' : 'bg-ethiopia-green text-white'} font-black text-xl flex items-center justify-center mb-6 shadow-sm`}>{step.num}</div>
                  <h3 className="text-xl font-bold text-slate-900 mb-2">{step.title}</h3>
                  <p className="text-sm text-slate-600 leading-relaxed">{step.desc}</p>
                </div>
                <div className="mt-6 pt-4 border-t border-slate-200 text-xs text-slate-500 font-medium flex items-center gap-2"><span>{step.icon}</span><span>{step.note}</span></div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CATEGORIES ── */}
      <section className="py-16 md:py-24 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-12">
          <div><span className="text-xs font-bold text-brand-600 uppercase tracking-widest">Marketplace Scope</span><h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">What You Can Find Today</h2></div>
          <p className="text-xs sm:text-sm text-slate-500 mt-2 sm:mt-0">Click any category to search the live index</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {categoryEntries.map(c => (
            <button key={c.name} onClick={() => handleCategoryFilter(c.name)} className="group p-5 bg-white border border-slate-200 hover:border-brand-500 rounded-2xl text-left transition-all hover:shadow-md">
              <div className="w-10 h-10 rounded-xl bg-amber-50 text-brand-600 flex items-center justify-center text-xl mb-3 group-hover:scale-110 transition-transform">{c.emoji}</div>
              <h3 className="font-bold text-slate-900 text-sm sm:text-base">{c.name}</h3>
              <p className="text-xs text-slate-500 mt-1 line-clamp-1">{c.description}</p>
              {c.count !== null && c.count > 0 && (
                <p className="text-[10px] font-mono font-bold text-brand-600 mt-1">{c.count.toLocaleString()} items</p>
              )}
            </button>
          ))}
        </div>
      </section>

      {/* ── FOR SELLERS ── */}
      <section id="sellers" className="py-16 md:py-24 bg-slate-900 text-white border-t border-slate-800">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7">
              <span className="text-xs font-bold text-brand-500 uppercase tracking-widest">For Telegram Channel Admins</span>
              <h2 className="text-3xl sm:text-5xl font-black text-white tracking-tight mt-2 mb-6">Run a Telegram Sales Channel?<br/><span className="text-brand-500">Get Found Beyond Your Subscribers.</span></h2>
              <p className="text-slate-300 text-base leading-relaxed mb-8">Most Telegram posts are only seen by people who already follow your channel. When you add Index Gebeya bot to your channel as an admin, your products are automatically indexed and presented to thousands of active buyers searching across Ethiopia every day.</p>
              <div className="space-y-4 mb-8">
                {["Zero Extra Effort: Post in your channel normally. Our AI automatically extracts your images, prices, and title.","Direct Traffic: Buyers tap your product and land directly on your original channel post to message you.","Live Stock Sync: Deleted or edited channel posts automatically sync in real-time."].map((t,i) => (
                  <div key={i} className="flex items-start gap-3"><div className="w-6 h-6 rounded-full bg-brand-500/20 text-brand-400 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">✓</div><p className="text-sm text-slate-200"><strong className="text-white">{t.split(':')[0]}:</strong>{t.split(':').slice(1).join(':')}</p></div>
                ))}
              </div>
              {!isTelegram ? (
                <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-3 px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white font-bold text-sm sm:text-base rounded-2xl shadow-lg transition-all"><span>+</span><span>Add Your Channel to Index</span></a>
              ) : (
                <span className="inline-flex items-center gap-3 px-8 py-4 bg-brand-600/50 text-brand-200 font-bold text-sm sm:text-base rounded-2xl cursor-default"><span>✓</span><span>You're already on Index Gebeya</span></span>
              )}
            </div>
            <div className="lg:col-span-5 bg-slate-800/90 border border-slate-700/80 p-6 sm:p-8 rounded-3xl shadow-2xl backdrop-blur-sm">
              <h3 className="text-lg font-bold text-white mb-2">⚡ What Sellers Get</h3>
              <p className="text-xs text-slate-400 mb-6">Your products seen by thousands of active buyers across Ethiopia.</p>
              <div className="space-y-6">
                <div className="p-4 rounded-2xl bg-slate-900/90 border border-slate-700/60 text-center">
                  <span className="text-xs text-slate-400 block mb-1">Active Buyer Searches Monthly</span>
                  <span className="text-3xl font-black text-emerald-400 font-mono tracking-tight">850,000+</span>
                  <span className="text-xs text-slate-400 block mt-1">across Ethiopian Telegram channels</span>
                </div>
                <div className="text-[11px] text-slate-400 leading-relaxed bg-slate-800 p-3 rounded-xl border border-slate-700">💡 Channels indexed with Index Gebeya experience an average <strong className="text-white">+38% increase</strong> in direct Telegram buyer inquiries in Addis Ababa.</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── PHONE MOCKUP ── */}
      <section className="py-16 md:py-24 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <span className="text-xs font-bold text-brand-600 uppercase tracking-widest">Telegram Native Experience</span>
          <h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">Zero Web Apps to Install.<br/>Runs Inside Your Telegram App.</h2>
          <p className="text-sm text-slate-600 mt-2">Tap below to switch views inside our live Telegram Mini App preview.</p>
        </div>
        <div className="flex justify-center">
          <div className="w-full max-w-sm bg-slate-900 p-4 rounded-[40px] shadow-2xl border-4 border-slate-800 relative">
            <div className="w-32 h-5 bg-slate-800 rounded-b-xl mx-auto absolute top-4 left-1/2 -translate-x-1/2 z-20"></div>
            <div className="bg-slate-950 rounded-[30px] pt-8 pb-4 px-3 text-white overflow-hidden min-h-[520px] flex flex-col justify-between relative z-10 border border-slate-800">
              <div>
                <div className="flex items-center justify-between px-2 pb-3 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-brand-600 text-white font-black text-xs flex items-center justify-center">IG</div>
                    <div><h4 className="font-bold text-xs">Index Gebeya Bot</h4><p className="text-[10px] text-slate-400">bot mini app</p></div>
                  </div>
                  <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full font-mono">v2.4</span>
                </div>
                <div className="py-4 px-1 space-y-3">
                  {phoneTab === 'search' && (<>
                    <div className="bg-slate-900 p-2 rounded-xl border border-slate-800 flex items-center gap-2 text-xs text-slate-300"><span>🔍</span><span className="font-mono text-slate-400 text-[11px]">Search 140k+ Telegram items...</span></div>
                    <div className="space-y-2">
                      {[{ icon:"📱", title:"iPhone 13 128GB Gold", channel:"@EthioTechHub", price:"48,500 Birr" },{ icon:"🚗", title:"Toyota Vitz 2019", channel:"@AddisAutoDeals", price:"1.25M Birr" }].map((p,i) => (
                        <div key={i} className="bg-slate-900/90 p-2.5 rounded-xl border border-slate-800 flex items-center gap-2">
                          <div className="w-10 h-10 rounded-lg bg-amber-950/80 text-amber-400 flex items-center justify-center text-xs font-bold">{p.icon}</div>
                          <div className="flex-1 min-w-0"><h5 className="text-xs font-bold truncate text-white">{p.title}</h5><p className="text-[10px] text-slate-400">{p.channel} • {p.price}</p></div>
                          <span className="text-[9px] bg-emerald-950 text-emerald-400 px-1.5 py-0.5 rounded font-bold">Match</span>
                        </div>
                      ))}
                    </div>
                  </>)}
                  {phoneTab === 'alerts' && (<>
                    <div className="text-xs text-slate-300 font-bold mb-2">🔔 Active Telegram Keyword Alerts</div>
                    {[{ q:'"Toyota Vitz"', max:'1,300,000 Birr' },{ q:'"MacBook Air M1"', max:'55,000 Birr' }].map((a,i) => (
                      <div key={i} className="bg-slate-900 p-2.5 rounded-xl border border-slate-800 flex items-center justify-between mb-2">
                        <div><span className="text-xs font-bold text-white block">{a.q}</span><span className="text-[10px] text-slate-400">Max: {a.max}</span></div>
                        <span className="text-[10px] bg-brand-500/20 text-brand-400 px-2 py-0.5 rounded-full font-bold">ACTIVE</span>
                      </div>
                    ))}
                  </>)}
                  {phoneTab === 'saved' && (
                    <div className="p-3 bg-slate-900 rounded-xl border border-slate-800 text-center text-xs text-slate-400"><span>Save Telegram deals to inspect or compare prices later.</span></div>
                  )}
                </div>
              </div>
              <div className="bg-slate-900 rounded-2xl p-2 grid grid-cols-3 gap-1 text-center border border-slate-800">
                {['search','alerts','saved'].map(tab => (
                  <button key={tab} onClick={() => setPhoneTab(tab)} className={`py-1.5 px-2 rounded-xl text-xs font-bold transition-all ${phoneTab === tab ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-white'}`}>{tab === 'search' ? '🔍 Search' : tab === 'alerts' ? '🔔 Alerts' : '⭐ Saved'}</button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="py-16 md:py-24 bg-ethiopia-paper border-t border-ethiopia-border/80">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-14"><span className="text-xs font-bold text-brand-600 uppercase tracking-widest">Clear & Transparent</span><h2 className="text-2xl sm:text-4xl font-extrabold text-slate-900 tracking-tight mt-1">Frequently Asked Questions</h2><p className="text-slate-600 text-sm mt-2">Everything you need to know about Index Gebeya.</p></div>
          <div className="space-y-4">
            {faqs.map((faq, i) => (
              <div key={i} className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
                <button onClick={() => setOpenFaq(openFaq === i ? null : i)} className="w-full p-5 text-left font-bold text-slate-900 text-base sm:text-lg flex justify-between items-center hover:bg-slate-50 transition-colors">
                  <span>{faq.q}</span>
                  <span className="text-brand-600 font-mono text-xl">{openFaq === i ? '−' : '+'}</span>
                </button>
                {openFaq === i && <div className="p-5 pt-0 text-sm text-slate-600 leading-relaxed border-t border-slate-100">{faq.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── TELEGRAM GET STARTED BUTTON (onboarding gate) ── */}
      {isTelegram && onGetStarted && (
        <section className="py-12 bg-slate-900 text-white border-t border-slate-800">
          <div className="max-w-lg mx-auto px-4 text-center">
            <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight mb-3">Ready to explore?</h2>
            <p className="text-slate-400 text-sm mb-6">Jump into the marketplace and start searching thousands of products across Ethiopian Telegram channels.</p>
            <button
              onClick={onGetStarted}
              className="w-full px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white font-extrabold text-base rounded-2xl shadow-xl hover:shadow-brand-500/20 transition-all transform hover:-translate-y-0.5 active:scale-95"
            >
              Get Started
            </button>
          </div>
        </section>
      )}

      {/* ── FINAL CTA (open web only) ── */}
      {!isTelegram && (
        <section className="py-16 bg-slate-900 text-white border-t border-slate-800">
          <div className="max-w-4xl mx-auto px-4 text-center">
            <h2 className="text-2xl sm:text-4xl font-extrabold tracking-tight mb-4">Stop Scrolling 50 Telegram Channels.<br/><span className="text-brand-500">Start Searching Index Gebeya.</span></h2>
            <p className="text-slate-400 text-sm sm:text-base max-w-xl mx-auto mb-8">Open our Mini App directly inside Telegram and find what you're looking for in seconds.</p>
            <a href="https://t.me/IndexGebeyaBot" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-3 px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white font-extrabold text-base rounded-2xl shadow-xl transition-all transform hover:-translate-y-0.5"><span>Open @IndexGebeyaBot</span></a>
          </div>
        </section>
      )}

      {/* ── FOOTER ── */}
      <footer className="bg-slate-950 text-slate-400 py-10 border-t border-slate-900 text-xs">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2 mb-1"><span className="font-black text-white text-sm tracking-tight">INDEX GEBEYA</span><span className="text-slate-600">•</span><span className="text-slate-400" style={{ fontFamily: "'Noto Sans Ethiopic', sans-serif" }}>የኢትዮጵያ ቴሌግራም ገበያ መፈለጊያ</span></div>
            <p className="text-slate-500">© 2026 Index Gebeya. Built for the Ethiopian Telegram Community.</p>
          </div>
          <div className="flex items-center gap-6">
            {!isTelegram && (
              <a href="https://t.me/IndexGebeyaBot" target="_blank" className="hover:text-white transition-colors">Telegram Bot</a>
            )}
            <a href="#sellers" className="hover:text-white transition-colors">For Sellers</a>
            <a href="#how-it-works" className="hover:text-white transition-colors">About Indexing</a>
            <span className="text-slate-600">|</span>
            <span className="flex items-center gap-1.5 text-slate-300"><span className="w-2 h-2 rounded-full bg-emerald-500"></span><span>Addis Ababa, Ethiopia</span></span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
