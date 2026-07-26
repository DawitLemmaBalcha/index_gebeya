import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Home from './pages/Home';
import ProductPage from './pages/ProductPage';
import AlertsPage from './pages/AlertsPage';
import StoresPage from './pages/StoresPage';
import LandingPage from './pages/LandingPage';
import BottomNav from './components/BottomNav';

const isTelegramWebView = () => {
  try {
    return !!(window.Telegram?.WebApp?.initData);
  } catch {
    return false;
  }
};

function MainLayout({ initialSearchQuery = '' }) {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState('explore');
  const isProductPage = location.pathname.startsWith('/item/');

  return (
    <div className="min-h-screen bg-gray-50 font-sans flex flex-col">
      {/* Main content area — flex-grow to push bottom nav down */}
      <div className="flex-1">
        {/* Explore Tab — always mounted, shown when active and not on product page */}
        <div style={{ display: (!isProductPage && activeTab === 'explore') ? 'block' : 'none' }}>
          <Home embedded={true} initialSearchQuery={initialSearchQuery} />
        </div>

        {/* Alerts Tab — always mounted */}
        <div style={{ display: (!isProductPage && activeTab === 'alerts') ? 'block' : 'none' }}>
          <AlertsPage />
        </div>

        {/* Stores Tab — always mounted */}
        <div style={{ display: (!isProductPage && activeTab === 'stores') ? 'block' : 'none' }}>
          <StoresPage />
        </div>

        {/* Product Page Route */}
        <Routes>
          <Route path="/item/:id" element={<ProductPage />} />
        </Routes>
      </div>

      {/* Bottom Nav — hidden on product page */}
      {!isProductPage && (
        <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} onExploreClick={() => { window.location.href = '/'; }} />
      )}
    </div>
  );
}

const App = () => {
  // Onboarding gate state — only relevant inside Telegram WebView
  const [showOnboarding, setShowOnboarding] = useState(() => {
    if (!isTelegramWebView()) return false; // Open web never shows onboarding
    try {
      return localStorage.getItem('onboarding_seen') !== 'true';
    } catch {
      return true; // localStorage unavailable → always show onboarding (graceful degradation)
    }
  });

  // Initial search query passed from landing page onboarding search
  const [initialSearchQuery, setInitialSearchQuery] = useState('');

  const handleGetStarted = (params) => {
    try {
      localStorage.setItem('onboarding_seen', 'true');
    } catch {}
    setShowOnboarding(false);
    if (params?.searchQuery) {
      window.location.href = `/?q=${encodeURIComponent(params.searchQuery)}`;
    } else {
      // Navigate to explore tab — Router picks up and renders MainLayout at /*
      window.location.href = '/';
    }
  };

  // Open web: always show landing page
  if (!isTelegramWebView()) {
    return <LandingPage />;
  }

  // Telegram: onboarding not yet seen
  if (showOnboarding) {
    return <LandingPage isTelegram={true} onGetStarted={handleGetStarted} />;
  }

  // Telegram: already onboarded
  return (
    <Router>
      <Routes>
        <Route path="/welcome" element={<LandingPage isTelegram={true} compact={true} onGetStarted={handleGetStarted} />} />
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </Router>
  );
};

export default App;
