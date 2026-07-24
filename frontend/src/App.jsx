import React from 'react';
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
  // Landing page for open web, marketplace for Telegram Mini App
  if (!isTelegramWebView()) {
    return <LandingPage />;
  }

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
