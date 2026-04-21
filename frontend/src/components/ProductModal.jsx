import React from 'react';
import { X, Phone, MessageCircle, MapPin, Tag } from 'lucide-react';

const ProductModal = ({ item, onClose, apiUrl }) => {
  if (!item) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto shadow-xl relative">
        
        {/* Close Button */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 bg-white/80 p-2 rounded-full text-gray-800 hover:bg-white transition-colors z-10"
        >
          <X size={20} />
        </button>

        {/* Image */}
        <div className="relative aspect-square bg-gray-100">
          <img 
            src={`${apiUrl}/media/${item.image_path}`} 
            alt={item.item_name}
            className="w-full h-full object-cover"
            onError={(e) => { e.target.src = 'https://placehold.co/600x600?text=No+Image'; }}
          />
        </div>

        {/* Content */}
        <div className="p-6">
          <div className="flex justify-between items-start mb-2">
            <div>
               <h2 className="text-xl font-bold text-gray-900">{item.item_name}</h2>
               <div className="flex items-center gap-2 mt-1">
                  <span className="bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded-full font-medium">
                    {item.category}
                  </span>
                  {item.subcategory && (
                    <span className="text-gray-400 text-xs">• {item.subcategory}</span>
                  )}
               </div>
            </div>
          </div>

          <div className="text-2xl font-bold text-green-600 mb-6">
            {new Intl.NumberFormat('en-ET').format(item.price)} {item.currency || 'ETB'}
          </div>

          {/* Details Grid */}
          <div className="space-y-4 mb-8">
             <div className="flex items-start gap-3 text-sm text-gray-600">
                <Tag className="mt-0.5 text-gray-400" size={16} />
                <div>
                   <span className="block font-medium text-gray-900">Condition</span>
                   {item.condition || 'Used'}
                </div>
             </div>
             
             <div className="flex items-start gap-3 text-sm text-gray-600">
                <MapPin className="mt-0.5 text-gray-400" size={16} />
                <div>
                   <span className="block font-medium text-gray-900">Location</span>
                   {item.location || 'Addis Ababa'}
                </div>
             </div>

             {item.description && (
               <div className="mt-4 p-4 bg-gray-50 rounded-xl text-sm leading-relaxed text-gray-700">
                  {item.description}
               </div>
             )}
          </div>

          {/* Bottom Actions */}
          <div className="grid grid-cols-2 gap-3">
             {item.contact_phone && (
                <a 
                  href={`tel:${item.contact_phone}`}
                  className="flex items-center justify-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-900 py-3 rounded-xl font-medium transition-colors"
                >
                  <Phone size={18} />
                  Call Seller
                </a>
             )}
             <a 
                href={`https://t.me/${item.telegram_channel_username}/${item.telegram_message_id}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-xl font-medium transition-colors"
             >
                <MessageCircle size={18} />
                Open Telegram
             </a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProductModal;