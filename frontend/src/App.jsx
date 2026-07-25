import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import ProductPage from './pages/ProductPage';
import LandingPage from './pages/LandingPage';

const isTelegramWebView = () => {
  try {
    return !!(window.Telegram?.WebApp?.initData);
  } catch {
    return false;
  }
};

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

  const handleGetStarted = () => {
    try {
      localStorage.setItem('onboarding_seen', 'true');
    } catch {
      // localStorage unavailable — silently proceed
    }
    setShowOnboarding(false);
  };

  // Open web: always show landing page (no onboarding concept)
  if (!isTelegramWebView()) {
    return <LandingPage />;
  }

  // Telegram: onboarding not yet seen → show landing page as onboarding
  if (showOnboarding) {
    return <LandingPage isTelegram={true} onGetStarted={handleGetStarted} />;
  }

  // Telegram: already onboarded → show marketplace
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/item/:id" element={<ProductPage />} />
      </Routes>
    </Router>
  );
};

export default App;
