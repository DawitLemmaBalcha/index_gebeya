import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation, useParams } from 'react-router-dom';
import Home from './pages/Home';
import ProductPage from './pages/ProductPage';
import AlertsPage from './pages/AlertsPage';
import StoresPage from './pages/StoresPage';
import LandingPage from './pages/LandingPage';
import MonetizationHub from './pages/MonetizationHub';
import OpsConsole from './pages/OpsConsole';
import BottomNav from './components/BottomNav';

const isTelegramWebView = () => {
  try {
    return !!(window.Telegram?.WebApp?.initData);
  } catch {
    return false;
  }
};

function MainLayout({ initialSearchQuery = '', initialTab }) {
  const location = useLocation();
  const params = useParams();
  // NB-45: deep link from the DM boost button — /stores/:channelId/:itemId
  const deepLink = (params.channelId && params.itemId)
    ? { channelId: params.channelId, itemId: params.itemId }
    : null;
  // NB-48: /stores route lands the seller on the Stores tab
  const [activeTab, setActiveTab] = useState(initialTab || (deepLink ? 'stores' : 'explore'));
  const isProductPage = location.pathname.startsWith('/item/');

  return (
    <div className="min-h-screen bg-gray-50 font-sans flex flex-col">
      {/* Main content area — flex-grow to push bottom nav down */}
      <div className="flex-1">
        {/* Explore Tab — always mounted, shown when active and not on product page */}
        <div style={{ display: (!isProductPage && activeTab === 'explore') ? 'block' : 'none' }}>
          <Home embedded={true} initialSearchQuery={initialSearchQuery} />
        </div>

        {/* Alerts Tab — always mounted; active prop drives refetching
            subscription status when the tab is shown again (BUG 2) */}
        <div style={{ display: (!isProductPage && activeTab === 'alerts') ? 'block' : 'none' }}>
          <AlertsPage active={activeTab === 'alerts'} />
        </div>

        {/* Stores Tab — always mounted */}
        <div style={{ display: (!isProductPage && activeTab === 'stores') ? 'block' : 'none' }}>
          <StoresPage deepLink={deepLink} active={activeTab === 'stores'} />
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
  // NB-49 (D8): the ops console is a standalone page — guard BEFORE the
  // Telegram gate so non-Telegram visitors land on /ops, not LandingPage.
  if (window.location.pathname.startsWith('/ops')) {
    return <OpsConsole />;
  }

  // Capture Telegram user identity once — enables owner checks (report sold, re-list, inventory)
  try {
    const tgUser = window.Telegram?.WebApp?.initDataUnsafe?.user;
    if (tgUser?.id) {
      const stored = localStorage.getItem('index_user_id');
      if (stored !== String(tgUser.id)) {
        localStorage.setItem('index_user_id', String(tgUser.id));
      }
    }
  } catch {}

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
        {/* NB-48: Monetization Hub (renders outside MainLayout) + /stores
            pick-an-item target — registered BEFORE the /* catch-all */}
        <Route path="/hub/:tab?" element={<MonetizationHub />} />
        <Route path="/stores" element={<MainLayout initialTab="stores" />} />
        {/* NB-45: deep link target for the DM boost button (§2.8) */}
        <Route path="/stores/:channelId/:itemId" element={<MainLayout />} />
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </Router>
  );
};

export default App;
