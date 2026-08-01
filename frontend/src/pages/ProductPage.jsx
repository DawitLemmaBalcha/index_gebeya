import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ShieldCheck, MessageCircle, Phone, Sparkles, AlertCircle, Star, User, Bell, AlertTriangle, Flag, RefreshCw, Clock, Loader2, CheckCircle } from 'lucide-react';
import { API_BASE_URL } from '../config';
import ItemCard from '../components/ItemCard';
import ReviewModal from '../components/ReviewModal';
import AlertModal from '../components/AlertModal';
import NavBar from '../components/home/NavBar';

const ProductPage = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    
    const [item, setItem] = useState(null);
    const [activeImage, setActiveImage] = useState(null); 
    const [relatedItems, setRelatedItems] = useState([]);
    const [reviews, setReviews] = useState([]); 
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    // Modal States
    const [isReviewOpen, setIsReviewOpen] = useState(false);
    const [isAlertOpen, setIsAlertOpen] = useState(false);

    // TECH-13: NavBar state
    const [searchQuery, setSearchQuery] = useState("");
    const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
    const [activeCategory, setActiveCategory] = useState("All");

    // Channel photo state for graceful fallback
    const [channelPhotoLoaded, setChannelPhotoLoaded] = useState(true);

    // TECH-22: Sold report state
    const [reportLoading, setReportLoading] = useState(false);
    const [reportError, setReportError] = useState(null);
    const [reportCount, setReportCount] = useState(null);
    const [currentUserId, setCurrentUserId] = useState(null);

    // Owner "can't report own product" modal — offers one-tap Mark as Sold
    const [showOwnerSoldModal, setShowOwnerSoldModal] = useState(false);
    const [ownerSoldLoading, setOwnerSoldLoading] = useState(false);
    const [ownerSoldError, setOwnerSoldError] = useState(null);

    // TECH-22: Get initData from Telegram WebApp (or dummy for dev)
    const getInitData = () => {
        if (window.Telegram?.WebApp?.initData) return window.Telegram.WebApp.initData;
        return "user=%7B%22id%22%3A%200%7D"; // dummy for dev
    };

    useEffect(() => {
        const fetchProductData = async () => {
            try {
                setLoading(true);
                // 1. Fetch Item
                const itemRes = await fetch(`${API_BASE_URL}/items/${id}`);
                if (!itemRes.ok) throw new Error("Item not found");
                const itemData = await itemRes.json();
                setItem(itemData);
                
                // TECH-22: Extract report_count and current user
                setReportCount(itemData.report_count ?? 0);

                // TECH-22: Read current user id from localStorage
                const storedUserId = localStorage.getItem('index_user_id');
                if (storedUserId) {
                    setCurrentUserId(Number(storedUserId));
                }

                if (itemData.images && itemData.images.length > 0) {
                    setActiveImage(itemData.images[0]);
                } else {
                    setActiveImage(itemData.image_path);
                }

                // 2. Fetch Related Items
                const relatedRes = await fetch(`${API_BASE_URL}/items/${id}/related`);
                if (relatedRes.ok) {
                    const relatedData = await relatedRes.json();
                    setRelatedItems(relatedData);
                }

                // 3. Fetch Reviews
                if (itemData.channel?.id) {
                    try {
                        const reviewsRes = await fetch(`${API_BASE_URL}/reviews/${itemData.channel.id}`);
                        if (reviewsRes.ok) {
                            const reviewsData = await reviewsRes.json();
                            setReviews(reviewsData);
                        }
                    } catch (e) {
                        console.error("Failed to fetch reviews", e);
                    }
                }

        } catch (err) {
            setReportError("Network error. Please try again.");
        } finally {
            setReportLoading(false);
        }
    };

    // Owner one-tap "Mark as Sold" from the modal
    const handleOwnerMarkSold = async () => {
        setOwnerSoldLoading(true);
        setOwnerSoldError(null);
        try {
            const res = await fetch(`${API_BASE_URL}/items/${id}/sold?init_data=${encodeURIComponent(getInitData())}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setOwnerSoldError(data.detail || "Failed to mark as sold.");
                return;
            }
            setItem(prev => ({ ...prev, status: 'sold' }));
            setShowOwnerSoldModal(false);
            if (window.Telegram?.WebApp?.showPopup) {
                window.Telegram.WebApp.showPopup({ message: "Marked as sold. It's no longer visible in search." });
            }
        } catch (err) {
            setOwnerSoldError("Network error. Please try again.");
        } finally {
            setOwnerSoldLoading(false);
        }
    };

        if (id) fetchProductData();
        window.scrollTo(0, 0); 
    }, [id]);

    const formatPrice = (price, currency) => {
        if (!price) return 'Call for Price';
        return `${new Intl.NumberFormat('en-ET').format(price)} ${currency || 'ETB'}`;
    };

    // TECH-22: Handle "Report as Sold"
    const handleReportSold = async () => {
        setReportLoading(true);
        setReportError(null);
        try {
            const res = await fetch(`${API_BASE_URL}/items/${id}/report`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: getInitData() }),
            });
            const data = await res.json();
            if (!res.ok) {
                if (res.status === 409) {
                    setReportError("You already reported this as sold.");
                } else if (res.status === 403) {
                    setShowOwnerSoldModal(true);
                } else {
                    setReportError(data.detail || "Failed to report item.");
                }
            } else {
                setReportCount(data.report_count);
                if (data.report_count >= 3) {
                    setItem(prev => ({ ...prev, status: 'reported_sold' }));
                }
                // Show success toast
                if (window.Telegram?.WebApp?.showPopup) {
                    window.Telegram.WebApp.showPopup({ message: "Reported! Thank you." });
                }
            }
        } catch (err) {
            setReportError("Network error. Please try again.");
        } finally {
            setReportLoading(false);
        }
    };

    // TECH-22: Handle "Re-list" (owner only)
    const handleRelist = async () => {
        setReportLoading(true);
        setReportError(null);
        try {
            const res = await fetch(`${API_BASE_URL}/items/${id}/relist`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ init_data: getInitData() }),
            });
            const data = await res.json();
            if (!res.ok) {
                setReportError(data.detail || "Failed to re-list item.");
            } else {
                setItem(prev => ({ ...prev, status: 'active' }));
                setReportCount(0);
                if (window.Telegram?.WebApp?.showPopup) {
                    window.Telegram.WebApp.showPopup({ message: "Item re-listed successfully!" });
                }
            }
        } catch (err) {
            setReportError("Network error. Please try again.");
        } finally {
            setReportLoading(false);
        }
    };

    // Skeleton loading layout for product page
    if (loading) return (
      <div className="min-h-screen bg-gray-50 font-sans pb-10">
        {/* NavBar skeleton */}
        <div className="bg-white/90 backdrop-blur-md border-b border-slate-200 sticky top-0 z-30 h-20 flex items-center px-4">
          <div className="w-10 h-10 rounded-full bg-gray-200 animate-pulse" />
        </div>

        <div className="max-w-6xl mx-auto p-4 grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* LEFT COL skeleton */}
          <div className="md:col-span-2 space-y-4">
            {/* Image placeholder */}
            <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-slate-200 animate-pulse">
              <div className="aspect-square md:aspect-video bg-gray-200" />
            </div>
            {/* Specs + Description skeleton */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 animate-pulse">
              <div className="h-5 bg-gray-200 rounded w-1/3 mb-4" />
              <div className="grid grid-cols-2 gap-4 mb-6">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="bg-gray-100 p-3 rounded-lg">
                    <div className="h-3 bg-gray-200 rounded w-1/2 mb-2" />
                    <div className="h-4 bg-gray-200 rounded w-3/4" />
                  </div>
                ))}
              </div>
              <div className="h-5 bg-gray-200 rounded w-1/4 mb-2" />
              <div className="space-y-2">
                <div className="h-4 bg-gray-200 rounded w-full" />
                <div className="h-4 bg-gray-200 rounded w-full" />
                <div className="h-4 bg-gray-200 rounded w-2/3" />
              </div>
            </div>
          </div>

          {/* RIGHT COL skeleton */}
          <div className="space-y-4">
            {/* Price card skeleton */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 animate-pulse">
              <div className="h-6 bg-gray-200 rounded w-3/4 mb-2" />
              <div className="h-10 bg-gray-200 rounded w-1/2 mb-4" />
              <div className="space-y-3">
                <div className="h-12 bg-gray-200 rounded-xl w-full" />
                <div className="h-12 bg-gray-200 rounded-xl w-full" />
              </div>
            </div>

            {/* Channel card skeleton */}
            <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-200 animate-pulse">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-full bg-gray-200" />
                <div className="space-y-2">
                  <div className="h-4 bg-gray-200 rounded w-24" />
                  <div className="h-3 bg-gray-200 rounded w-32" />
                </div>
              </div>
              <div className="bg-gray-100 p-3 rounded-xl mb-3">
                <div className="flex justify-between items-center">
                  <div className="h-4 bg-gray-200 rounded w-20" />
                  <div className="h-4 bg-gray-200 rounded w-24" />
                </div>
              </div>
              <div className="h-10 bg-gray-200 rounded-xl w-full mb-4" />
              <div className="space-y-2">
                <div className="h-12 bg-gray-100 rounded-lg" />
                <div className="h-12 bg-gray-100 rounded-lg" />
              </div>
            </div>
          </div>
        </div>
      </div>
    );

    if (error || !item) return (
        <div className="min-h-screen flex flex-col justify-center items-center text-center p-4">
             <h2 className="text-2xl font-bold text-gray-900 mb-2">Oops!</h2>
             <p className="text-gray-500 mb-4">{error || "Item not found"}</p>
             <button onClick={() => navigate('/')} className="px-6 py-2 bg-blue-600 text-white rounded-lg">Back to Home</button>
        </div>
    );

    let parsedSpecs = {};
    try {
        if (item.specs && typeof item.specs === 'string') {
             const jsonStr = item.specs.replace(/'/g, '"').replace(/None/g, 'null').replace(/False/g, 'false').replace(/True/g, 'true');
             parsedSpecs = JSON.parse(jsonStr);
        }
    } catch (e) { parsedSpecs = {}; }

    return (
        <div className="min-h-screen bg-gray-50 font-sans pb-10">
            {/* TECH-13: NavBar replaces old header */}
            <NavBar
              variant="product"
              onBack={() => navigate('/')}
              onReset={() => navigate('/')}
              searchQuery={searchQuery}
              setSearchQuery={setSearchQuery}
              onImageSearch={() => navigate('/')}
              isMobileMenuOpen={isMobileMenuOpen}
              setIsMobileMenuOpen={setIsMobileMenuOpen}
              activeCategory={activeCategory}
              setActiveCategory={(cat) => { setActiveCategory(cat); setIsMobileMenuOpen(false); navigate('/'); }}
              onSearchSubmit={(query) => navigate(`/?q=${encodeURIComponent(query)}`)}
            />

            <div className="max-w-6xl mx-auto p-4 grid grid-cols-1 md:grid-cols-3 gap-6">
                
                {/* LEFT COL: Content */}
                <div className="md:col-span-2 space-y-4">
                    <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100">
                        <div className="aspect-square md:aspect-video bg-gray-100 relative group flex items-center justify-center">
                             {activeImage ? (
                               <img src={`${API_BASE_URL}/media/${activeImage}`} className="w-full h-full object-contain transition-all duration-300" alt={item.title} onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'flex'; }} />
                             ) : null}
                             <div className={`${activeImage ? 'hidden' : 'flex'} flex-col items-center justify-center text-gray-400`}>
                               <svg className="w-16 h-16 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                               <span className="text-sm font-medium">No Image Available</span>
                             </div>
                        </div>
                        {item.images && item.images.length > 1 && (
                            <div className="flex gap-2 p-4 overflow-x-auto scrollbar-hide">
                                {item.images.map((img, idx) => (
                                    <button key={idx} onClick={() => setActiveImage(img)} className={`w-16 h-16 rounded-lg overflow-hidden flex-shrink-0 border-2 transition-all ${activeImage === img ? 'border-blue-600 opacity-100' : 'border-transparent opacity-60 hover:opacity-100'}`}>
                                        <img src={`${API_BASE_URL}/media/${img}`} className="w-full h-full object-cover" alt={`View ${idx}`} onError={(e) => { e.target.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect fill="%23f1f5f9" width="64" height="64"/><text x="32" y="36" text-anchor="middle" fill="%2394a3b8" font-size="8">No Img</text></svg>'; }} />
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                        <h3 className="text-lg font-bold text-gray-900 mb-4">Specifications</h3>
                        <div className="grid grid-cols-2 gap-4 mb-6">
                            {Object.entries(parsedSpecs).map(([key, val]) => (
                                <div key={key} className="bg-gray-50 p-3 rounded-lg">
                                    <span className="block text-xs text-gray-500 uppercase tracking-wide">{key}</span>
                                    <span className="block text-sm font-medium text-gray-900">{val}</span>
                                </div>
                            ))}
                        </div>
                        <div className="mb-6">
                             <h3 className="text-lg font-bold text-gray-900 mb-2">Description</h3>
                             <p className="text-gray-600 leading-relaxed whitespace-pre-line">{item.description}</p>
                        </div>
                        {item.original_caption && (
                            <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
                                <div className="flex items-center gap-2 mb-2 text-amber-800"><AlertCircle size={16} /><h4 className="font-bold text-sm">Seller's Note</h4></div>
                                <p className="text-sm text-gray-700 whitespace-pre-wrap font-mono leading-relaxed opacity-90">{item.original_caption}</p>
                            </div>
                        )}
                    </div>
                </div>

                {/* RIGHT COL: Actions & Trust */}
                <div className="space-y-4">
                    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                        <h1 className="text-xl font-bold text-gray-900 mb-2 line-clamp-2">{item.title}</h1>
                        
                        <div className="flex justify-between items-center mb-4">
                            <div className="text-3xl font-bold text-green-600">{formatPrice(item.price, item.currency)}</div>
                            
                            {/* ALERT BUTTON */}
                            <button 
                                onClick={() => setIsAlertOpen(true)}
                                className="flex flex-col items-center justify-center p-2 rounded-xl hover:bg-gray-50 transition-colors text-blue-600"
                            >
                                <div className="bg-blue-100 p-2 rounded-full mb-1">
                                    <Bell size={20} className="fill-blue-600" />
                                </div>
                                <span className="text-xs font-bold">Alert Me</span>
                            </button>
                        </div>

                        {/* TECH-22: Status Badge */}
                        {item.status && item.status !== 'active' && (
                            <div className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium mb-3 ${
                                item.status === 'sold' || item.status === 'soft_deleted' || item.status === 'removed'
                                    ? 'bg-red-50 text-red-700 border border-red-200'
                                    : item.status === 'reported_sold'
                                    ? 'bg-amber-50 text-amber-700 border border-amber-200'
                                    : item.status === 'stale'
                                    ? 'bg-gray-100 text-gray-600 border border-gray-200'
                                    : ''
                            }`}>
                                {item.status === 'reported_sold' && <AlertTriangle size={16} />}
                                {(item.status === 'sold' || item.status === 'soft_deleted' || item.status === 'removed') && <AlertTriangle size={16} />}
                                {item.status === 'stale' && <Clock size={16} />}
                                <span>
                                    {item.status === 'reported_sold'
                                        ? `⚠️ Reported Sold (${reportCount ?? 0} reports)`
                                        : item.status === 'sold'
                                        ? 'Sold'
                                        : item.status === 'stale'
                                        ? 'May be outdated'
                                        : 'Removed'}
                                </span>
                            </div>
                        )}
                        {item.is_stale && item.status === 'active' && (
                            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium mb-3 bg-gray-100 text-gray-600 border border-gray-200">
                                <Clock size={16} />
                                <span>May be outdated</span>
                            </div>
                        )}

                        {/* Live report count — visible as soon as any buyer reports, before threshold */}
                        {item.status === 'active' && reportCount > 0 && (
                            <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium mb-3 bg-amber-50 text-amber-700 border border-amber-200">
                                <AlertTriangle size={16} />
                                <span>{reportCount} {reportCount === 1 ? 'buyer reported' : 'buyers reported'} this as sold</span>
                            </div>
                        )}

                        {/* TECH-22: Report as Sold button (any authenticated buyer, active items, not the owner) */}
                        {item.status === 'active' && currentUserId && currentUserId !== item.channel?.registered_by && (
                            <div className="mb-3">
                                <button
                                    onClick={handleReportSold}
                                    disabled={reportLoading}
                                    className="w-full flex items-center justify-center gap-2 border border-gray-300 text-gray-700 py-2.5 rounded-xl hover:bg-gray-50 transition-all font-medium text-sm disabled:opacity-50"
                                >
                                    <Flag size={16} />
                                    {reportLoading ? 'Reporting...' : 'Report as Sold'}
                                </button>
                                {reportError && (
                                    <p className="text-red-500 text-xs mt-1 text-center">{reportError}</p>
                                )}
                            </div>
                        )}

                        {/* TECH-22: Re-list button (owner only, reported_sold items) */}
                        {item.status === 'reported_sold' && currentUserId && item.channel?.registered_by && currentUserId === item.channel.registered_by && (
                            <div className="mb-3">
                                <button
                                    onClick={handleRelist}
                                    disabled={reportLoading}
                                    className="w-full flex items-center justify-center gap-2 bg-green-600 text-white py-2.5 rounded-xl hover:bg-green-700 transition-all font-medium text-sm disabled:opacity-50"
                                >
                                    <RefreshCw size={16} />
                                    {reportLoading ? 'Re-listing...' : 'Re-list Item'}
                                </button>
                                {reportError && (
                                    <p className="text-red-500 text-xs mt-1 text-center">{reportError}</p>
                                )}
                            </div>
                        )}

                        <div className="flex flex-col gap-3">
                            <a href={`tel:${item.phone_number}`} className="flex items-center justify-center gap-2 bg-gray-900 text-white py-3 rounded-xl hover:bg-gray-800 transition-all font-medium"><Phone size={18} /> Call Seller</a>
                            <a href={`https://t.me/${item.channel?.username}`} target="_blank" rel="noreferrer" className="flex items-center justify-center gap-2 bg-blue-500 text-white py-3 rounded-xl hover:bg-blue-600 transition-all font-medium"><MessageCircle size={18} /> Telegram Chat</a>
                        </div>
                    </div>

                    {/* CHANNEL TRUST CARD */}
                    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
                        <div className="flex items-center gap-3 mb-4">
                            {item.channel?.id && channelPhotoLoaded ? (
                                <img
                                    src={`${API_BASE_URL}/channels/${item.channel.id}/photo`}
                                    alt={item.channel?.username || "Channel"}
                                    className="w-12 h-12 rounded-full object-cover"
                                    onLoad={() => setChannelPhotoLoaded(true)}
                                    onError={() => setChannelPhotoLoaded(false)}
                                />
                            ) : null}
                            {!channelPhotoLoaded || !item.channel?.id ? (
                                <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600 font-bold text-xl">
                                    {item.channel?.username?.[0]?.toUpperCase() || "S"}
                                </div>
                            ) : null}
                            <div>
                                <h3 className="font-bold text-gray-900">@{item.channel?.username || "Unknown"}</h3>
                                <div className="flex items-center gap-1 text-sm text-green-600">
                                    <ShieldCheck size={14} />
                                    <span>Verified Merchant</span>
                                </div>
                            </div>
                        </div>
                        
                        <div className="bg-gray-50 p-3 rounded-xl flex justify-between items-center mb-3">
                             <span className="text-sm text-gray-500">Trust Score</span>
                             <div className="flex items-center gap-1">
                                <Star size={16} className="fill-yellow-400 text-yellow-400" />
                                <span className="font-bold text-gray-900">{item.channel?.trust_score?.toFixed(1) || "0.0"} / 5.0</span>
                                <span className="text-xs text-gray-400">({item.channel?.review_count || 0})</span>
                             </div>
                        </div>

                        {/* Rate Seller Button */}
                        <button 
                            onClick={() => setIsReviewOpen(true)}
                            className="w-full py-2 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors mb-4"
                        >
                            Rate this Seller
                        </button>

                        {/* REVIEW LIST */}
                        {reviews.length > 0 && (
                            <div className="mt-4 border-t border-gray-100 pt-4">
                                <h4 className="font-bold text-sm text-gray-900 mb-3">Recent Reviews</h4>
                                <div className="space-y-3 max-h-60 overflow-y-auto pr-1 scrollbar-hide">
                                    {reviews.map((rev) => (
                                        <div key={rev.id} className="bg-gray-50 p-3 rounded-lg">
                                            <div className="flex justify-between items-start mb-1">
                                                <div className="flex items-center gap-1">
                                                    {rev.user_photo_url ? (
                                                        <img
                                                            src={rev.user_photo_url}
                                                            alt="Reviewer"
                                                            className="w-5 h-5 rounded-full object-cover"
                                                            onError={(e) => {
                                                                e.target.style.display = 'none';
                                                                e.target.nextSibling.style.display = 'inline';
                                                            }}
                                                        />
                                                    ) : null}
                                                    <User size={12} className={`text-gray-400 ${rev.user_photo_url ? 'hidden' : ''}`} />
                                                    <span className="text-xs font-bold text-gray-700">{rev.user_name || rev.user?.first_name || "User"}</span>
                                                </div>
                                                <div className="flex gap-0.5">
                                                    {[...Array(5)].map((_, i) => (
                                                        <Star key={i} size={10} className={i < rev.rating ? "fill-yellow-400 text-yellow-400" : "text-gray-300"} />
                                                    ))}
                                                </div>
                                            </div>
                                            {rev.comment && <p className="text-xs text-gray-600 leading-relaxed">{rev.comment}</p>}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Related */}
            {relatedItems.length > 0 && (
                <div className="max-w-6xl mx-auto px-4 mt-8">
                    <div className="flex items-center gap-2 mb-4"><Sparkles className="text-purple-600" /><h2 className="text-xl font-bold text-gray-900">Similar Items</h2></div>
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                        {relatedItems.map(rel => <ItemCard key={rel.id} item={rel} apiUrl={API_BASE_URL} onSelect={(itm) => navigate(`/item/${itm.id}`)} />)}
                    </div>
                </div>
            )}

            {/* MODALS */}
            <ReviewModal 
                isOpen={isReviewOpen} 
                onClose={(success) => {
                    setIsReviewOpen(false);
                    if (success) window.location.reload(); 
                }} 
                channelId={item.channel?.id}
                channelName={item.channel?.username}
            />

            {/* ALERT MODAL (NEW) */}
            <AlertModal
                isOpen={isAlertOpen}
                onClose={() => setIsAlertOpen(false)}
                initialQuery={item.title}
                currentPrice={item.price}
            />

            {/* OWNER CAN'T REPORT — modal with one-tap Mark as Sold */}
            {showOwnerSoldModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl w-full max-w-sm p-6 shadow-xl">
                        <div className="flex items-center gap-2 mb-3 text-amber-600">
                            <AlertTriangle size={22} />
                            <h3 className="text-lg font-bold text-gray-900">This is your product</h3>
                        </div>
                        <p className="text-sm text-gray-600 mb-2">
                            You can't report your own listing as sold. If it's no longer available,
                            mark it as sold to remove it from search.
                        </p>
                        <p className="text-xs text-gray-400 mb-5">
                            You can also manage it anytime from Stores → Manage → Edit.
                        </p>
                        {ownerSoldError && (
                            <p className="text-red-500 text-xs text-center mb-3 bg-red-50 p-2 rounded-lg">{ownerSoldError}</p>
                        )}
                        <button
                            onClick={handleOwnerMarkSold}
                            disabled={ownerSoldLoading || item.status === 'sold'}
                            className="w-full flex items-center justify-center gap-2 bg-green-600 text-white py-3 rounded-xl font-medium hover:bg-green-700 transition-colors disabled:opacity-50 mb-2"
                        >
                            {ownerSoldLoading ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle size={16} />}
                            {item.status === 'sold' ? 'Already Marked as Sold' : 'Mark as Sold'}
                        </button>
                        <button
                            onClick={() => setShowOwnerSoldModal(false)}
                            className="w-full py-3 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors"
                        >
                            Close
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default ProductPage;