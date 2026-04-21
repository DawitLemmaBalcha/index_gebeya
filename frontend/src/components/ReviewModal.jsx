import React, { useState } from 'react';
import { Star, X, Loader2 } from 'lucide-react';
import { API_BASE_URL } from '../config';

const ReviewModal = ({ isOpen, onClose, channelId, channelName }) => {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleSubmit = async () => {
    if (rating === 0) return;
    setSubmitting(true);
    setError(null);

    const initData = window.Telegram?.WebApp?.initData;
    
    if (!initData) {
        setError("Please open in Telegram to rate.");
        setSubmitting(false);
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/reviews/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                channel_id: channelId,
                rating: rating,
                comment: comment,
                init_data: initData
            })
        });

        // 👇 SAFE ERROR HANDLING (Read once) 👇
        if (!response.ok) {
            const rawText = await response.text();
            let errMsg = "Failed to submit review";
            try {
                // Try to parse as JSON
                const jsonErr = JSON.parse(rawText);
                errMsg = jsonErr.detail || errMsg;
            } catch {
                // If not JSON, use the raw text (e.g. "Internal Server Error")
                errMsg = rawText || `Server Error (${response.status})`;
            }
            throw new Error(errMsg);
        }

        onClose(true);
        alert("Review Submitted! Trust Score updated.");
        
    } catch (e) {
        console.error("Submission Error:", e);
        setError(e.message);
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

        <h3 className="text-xl font-bold text-gray-900 mb-1">Rate Seller</h3>
        <p className="text-sm text-gray-500 mb-6">How was your experience with <span className="font-semibold text-blue-600">@{channelName}</span>?</p>

        <div className="flex justify-center gap-2 mb-6">
            {[1, 2, 3, 4, 5].map((star) => (
                <button 
                    key={star} 
                    onClick={() => setRating(star)}
                    className="transition-transform hover:scale-110 focus:outline-none"
                >
                    <Star 
                        size={32} 
                        className={star <= rating ? "fill-yellow-400 text-yellow-400" : "text-gray-300"} 
                    />
                </button>
            ))}
        </div>

        <textarea 
            placeholder="Write a comment (optional)..." 
            className="w-full bg-gray-50 border border-gray-200 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4 h-24 resize-none"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
        />

        {error && <div className="text-red-500 text-xs text-center mb-4 bg-red-50 p-2 rounded-lg">{error}</div>}

        <button 
            onClick={handleSubmit}
            disabled={submitting || rating === 0}
            className="w-full bg-gray-900 text-white py-3 rounded-xl font-medium hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-2"
        >
            {submitting && <Loader2 size={18} className="animate-spin" />}
            Submit Review
        </button>
      </div>
    </div>
  );
};

export default ReviewModal;