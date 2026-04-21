import React, { useState, useEffect } from 'react';
import { Bell, X, Loader2, DollarSign, Filter } from 'lucide-react';
import { API_BASE_URL } from '../config';

const AlertModal = ({ isOpen, onClose, initialQuery, currentPrice }) => {
  const [targetPrice, setTargetPrice] = useState("");
  const [preferences, setPreferences] = useState({
      strict_brand: false,
      strict_model: false // 👈 CHANGED from condition_new
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && currentPrice) {
        // Default target price is current price
        setTargetPrice(currentPrice.toString());
    }
  }, [isOpen, currentPrice]);

  if (!isOpen) return null;

  const togglePreference = (key) => {
      setPreferences(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);

    const initData = window.Telegram?.WebApp?.initData;
    const authData = initData || "user_id_placeholder"; 
    
    if (!authData && !initData) {
         setError("Please open in Telegram to create alerts.");
         setSubmitting(false);
         return;
    }

    try {
        // We send "None" (null) if input is empty, matching backend logic
        const finalPrice = targetPrice ? parseFloat(targetPrice) : null;

        const response = await fetch(`${API_BASE_URL}/alerts/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query_text: initialQuery,
                max_price: finalPrice,
                init_data: authData,
                preferences: preferences
            })
        });

        if (!response.ok) {
            const rawText = await response.text();
            throw new Error(rawText || "Failed to create alert");
        }

        onClose(true); // Success
        alert("Alert Created! We'll notify you when a match is found.");
        
    } catch (e) {
        console.error("Alert Error:", e);
        setError("Failed to save alert. Try again.");
    } finally {
        setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl w-full max-w-sm p-6 shadow-xl relative">
        <button onClick={() => onClose(false)} className="absolute top-4 right-4 text-gray-400 hover:text-gray-600">
            <X size={20} />
        </button>

        <div className="flex items-center gap-2 mb-2 text-blue-600">
            <Bell size={24} className="fill-blue-100" />
            <h3 className="text-xl font-bold text-gray-900">Create Alert</h3>
        </div>
        <p className="text-sm text-gray-500 mb-6">Notify me when <b>"{initialQuery}"</b> appears.</p>

        {/* PRICE INPUT */}
        <div className="mb-4">
            <label className="block text-xs font-bold text-gray-700 uppercase mb-1">Max Price (ETB)</label>
            <div className="relative">
                <DollarSign size={16} className="absolute left-3 top-3.5 text-gray-400" />
                <input 
                    type="number" 
                    value={targetPrice}
                    onChange={(e) => setTargetPrice(e.target.value)}
                    className="w-full pl-9 pr-3 py-3 bg-gray-50 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono font-medium"
                    placeholder="Any Price"
                />
            </div>
            <p className="text-xs text-gray-400 mt-1">Leave empty for any price.</p>
        </div>

        {/* TOGGLES */}
        <div className="mb-6">
            <div className="flex items-center gap-1 mb-2">
                <Filter size={14} className="text-gray-400" />
                <span className="text-xs font-bold text-gray-700 uppercase">Smart Filters</span>
            </div>
            <div className="flex flex-wrap gap-2">
                <button 
                    onClick={() => togglePreference('strict_brand')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${preferences.strict_brand ? 'bg-blue-100 border-blue-200 text-blue-700' : 'bg-white border-gray-200 text-gray-600'}`}
                >
                    Strict Brand Match
                </button>
                <button 
                    onClick={() => togglePreference('strict_model')}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${preferences.strict_model ? 'bg-blue-100 border-blue-200 text-blue-700' : 'bg-white border-gray-200 text-gray-600'}`}
                >
                    Strict Model Match
                </button>
            </div>
        </div>

        {error && <div className="text-red-500 text-xs text-center mb-4 bg-red-50 p-2 rounded-lg">{error}</div>}

        <button 
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 disabled:opacity-50 flex justify-center items-center gap-2 shadow-lg shadow-blue-200"
        >
            {submitting && <Loader2 size={18} className="animate-spin" />}
            Set Alert
        </button>
      </div>
    </div>
  );
};

export default AlertModal;