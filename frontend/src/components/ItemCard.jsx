import React from 'react';
import { Phone, MessageCircle, Sparkles, Ban, AlertTriangle, Clock } from 'lucide-react';
import { getAnalyticsHeaders } from '../utils/analytics'; // IMPORT (for URL param only if needed, otherwise use headers)

const ItemCard = ({ item, onSelect, apiUrl, variant, onMarkSold, onEdit }) => {
  
  const formatPrice = (price, currency) => {
    if (!price) return 'Ask for Price';
    return `${new Intl.NumberFormat('en-ET').format(price)} ${currency || 'ETB'}`;
  };

  const handleActionClick = (e) => {
    e.stopPropagation(); 
  };

  // WRAPPER FOR SELECTION
  const handleCardClick = () => {
    // 1. Trigger the visual UI change
    onSelect(item); 

    // 2. Fire-and-forget the view event via fetch
    // We construct the headers manually here to keep ItemCard simple
    // Note: We are hitting the GET /items/{id} endpoint implicitly if the modal fetches details.
    // BUT, if the Modal just displays the data passed to it, we need to explicitly log the view.
    // Assuming the Modal displays existing data, we fire a separate log event.
    // However, the cleanest way is actually to let the Backend handle it via the /items/{id} call 
    // IF the modal fetches fresh data. 
    
    // Checking previous context: The ProductModal usually fetches details? 
    // If not, we should fire the logEvent utility.
    // Let's use the explicit logEvent for robustness.
    
    // Dynamically import to avoid circular dependency issues if any, 
    // or just fetch directly.
    import('../utils/analytics').then(({ logEvent }) => {
        logEvent('view_item_card', item.id, { source: 'feed' });
    });
  };

  // --- MATCH CONFIDENCE BADGE ---
  const getMatchBadge = () => {
      const score = item.total_score || item.relevance_score || 0;
      if (score > 0.6) {
          return (
              <div className="absolute top-2 left-2 bg-purple-600 text-white text-[10px] font-bold px-2 py-1 rounded-full shadow-lg flex items-center gap-1 animate-pulse z-10">
                  <Sparkles size={10} /> BEST MATCH
              </div>
          );
      }
      if (score > 0.4) {
          return (
              <div className="absolute top-2 left-2 bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded-full shadow-md z-10">
                  High Match
              </div>
          );
      }
      return null;
  };

  // TECH-22: Status badge for non-active or stale items
  const getStatusBadge = () => {
      if (item.status === 'sold') {
          return (
              <div className="absolute top-2 right-2 bg-red-600/80 text-white text-[10px] font-bold px-2 py-1 rounded-full backdrop-blur-sm flex items-center gap-1 z-10">
                  <Ban size={10} /> Sold
              </div>
          );
      }
      if (item.status === 'reported_sold') {
          return (
              <div className="absolute top-2 right-2 bg-amber-500/80 text-white text-[10px] font-bold px-2 py-1 rounded-full backdrop-blur-sm flex items-center gap-1 z-10">
                  <AlertTriangle size={10} /> Reported
              </div>
          );
      }
      if (item.status === 'stale' || item.is_stale) {
          return (
              <div className="absolute top-2 right-2 bg-gray-400/70 text-white text-[10px] font-bold px-2 py-1 rounded-full backdrop-blur-sm flex items-center gap-1 z-10">
                  <Clock size={10} /> Stale
              </div>
          );
      }
      return null;
  };

  const mainImage = (item.images && item.images.length > 0) ? item.images[0] : item.image_path;

  return (
    <div 
      onClick={handleCardClick} // CHANGED from () => onSelect(item)
      className="bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-soft hover:shadow-warm transition-all cursor-pointer group relative"
    >
      {getMatchBadge()}
      {getStatusBadge()}

      {/* Image Area */}
      <div className="relative aspect-square bg-ethiopia-paper overflow-hidden">
        <img 
          src={`${apiUrl}/media/${mainImage}`} 
          alt={item.title || item.description}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
          onError={(e) => { e.target.src = 'https://placehold.co/400x400?text=No+Image'; }}
        />
        
        {/* Condition Badge — only for active items */}
        {(!item.status || item.status === 'active') && !item.is_stale && (
          <div className="absolute top-2 right-2 bg-slate-900/70 text-white text-xs px-2 py-1 rounded-full backdrop-blur-sm">
            {item.condition || 'Used'}
          </div>
        )}

        {/* Gallery Indicator */}
        {item.images && item.images.length > 1 && (
           <div className="absolute bottom-2 right-2 bg-black/60 text-white text-[10px] px-2 py-0.5 rounded backdrop-blur-sm">
             +{item.images.length - 1} more
           </div>
        )}
      </div>

      {/* Content Area */}
      <div className="p-3">
        <div className="flex justify-between items-start mb-1">
          <h3 className="font-semibold text-gray-900 line-clamp-1 text-sm" title={item.title || item.description}>
            {item.title || item.description}
          </h3>
        </div>
        
        <div className={`font-bold text-sm mb-2 ${!item.price ? 'text-green-600' : 'text-ethiopia-green'}`}>
          {formatPrice(item.price, item.currency)}
        </div>

        {/* TECH-15: Channel username */}
        {item.channel?.username && (
          <div className="flex items-center gap-1 mb-1">
            <span className="text-[10px] text-gray-400 truncate">@{item.channel.username}</span>
          </div>
        )}

        <div className="flex items-center justify-between text-xs text-gray-500 mb-3">
          <span className="bg-ethiopia-paper border border-ethiopia-border/50 px-2 py-1 rounded truncate max-w-[60%]">{item.category || "General"}</span>
          <span className="line-clamp-1">{item.location || 'Addis Ababa'}</span>
        </div>

        {/* Action Buttons */}
        {variant === 'inventory' ? (
          <div className="flex gap-2 mt-auto">
            <button
              onClick={(e) => { e.stopPropagation(); onMarkSold?.(item); }}
              className="flex-1 flex items-center justify-center gap-1 bg-amber-50 hover:bg-amber-100 text-amber-700 py-2 rounded-lg transition-colors border border-amber-200"
            >
              <span className="font-medium text-xs">Mark Sold</span>
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onEdit?.(item); }}
              className="flex-1 flex items-center justify-center gap-1 bg-gray-50 hover:bg-gray-100 text-gray-700 py-2 rounded-lg transition-colors border border-slate-200"
            >
              <span className="font-medium text-xs">Edit</span>
            </button>
          </div>
        ) : (
          <div className="flex gap-2 mt-auto">
          {item.phone_number && (
            <a 
              href={`tel:${item.phone_number}`}
              onClick={handleActionClick}
              className="flex-1 flex items-center justify-center gap-1 bg-gray-50 hover:bg-ethiopia-green/5 text-gray-700 hover:text-ethiopia-green py-2 rounded-lg transition-colors border border-slate-200"
            >
              <Phone size={14} />
              <span className="font-medium text-xs">Call</span>
            </a>
          )}
          <a 
            href={`https://t.me/${item.channel?.username}/${item.telegram_message_id}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleActionClick}
            className="flex-1 flex items-center justify-center gap-1 bg-gray-50 hover:bg-brand-50 text-gray-700 hover:text-brand-600 py-2 rounded-lg transition-colors border border-slate-200"
          >
            <MessageCircle size={14} />
            <span className="font-medium text-xs">Chat</span>
          </a>
        </div>
        )}
      </div>
    </div>
  );
};

export default ItemCard;