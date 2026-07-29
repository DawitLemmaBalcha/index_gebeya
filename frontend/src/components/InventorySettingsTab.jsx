import React, { useState } from 'react';
import { Package, Pause, Play, Trash2, Loader2, Store, ExternalLink } from 'lucide-react';

/**
 * TECH-23: Settings tab within ChannelInventory modal.
 * Mirrors channel card actions: pause/resume toggle, remove channel, stats.
 */
const InventorySettingsTab = ({ channel, togglePause, removeChannel, onClose }) => {
  const [actionLoading, setActionLoading] = useState(null); // 'pause' | 'resume' | 'remove' | null

  const formatNumber = (num) => {
    if (num == null) return '—';
    return new Intl.NumberFormat('en-ET').format(num);
  };

  const handleTogglePause = async () => {
    setActionLoading(channel.indexing_paused ? 'resume' : 'pause');
    try {
      await togglePause(channel.id, !channel.indexing_paused);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRemove = async () => {
    setActionLoading('remove');
    try {
      await removeChannel(channel.id);
      onClose();
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-y-auto px-4 py-4">
      {/* Channel info header */}
      <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-4">
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 bg-brand-100 rounded-full flex items-center justify-center">
            <Store size={20} className="text-brand-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">@{channel.username}</h3>
            {channel.title && (
              <p className="text-sm text-gray-500">{channel.title}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm text-gray-600">
          <span>Trust: {channel.trust_score?.toFixed(1) || 'N/A'}</span>
          <span>Reviews: {channel.review_count || 0}</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-50 p-3 rounded-xl text-center">
          <Package size={16} className="text-gray-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-gray-900">
            {formatNumber(channel.product_count)}
          </p>
          <p className="text-[10px] text-gray-500">Products</p>
        </div>
        <div className="bg-gray-50 p-3 rounded-xl text-center">
          <ExternalLink size={16} className="text-gray-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-gray-900">—</p>
          <p className="text-[10px] text-gray-500">Views</p>
        </div>
        <div className="bg-gray-50 p-3 rounded-xl text-center">
          <ExternalLink size={16} className="text-gray-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-gray-900">—</p>
          <p className="text-[10px] text-gray-500">Clicks</p>
        </div>
      </div>

      {/* Pause/Resume toggle */}
      <button
        onClick={handleTogglePause}
        disabled={actionLoading !== null}
        className={`flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium mb-3 transition-colors disabled:opacity-50 ${
          channel.indexing_paused
            ? 'bg-amber-50 text-amber-700 hover:bg-amber-100'
            : 'bg-brand-50 text-brand-700 hover:bg-brand-100'
        }`}
      >
        {actionLoading === 'pause' || actionLoading === 'resume' ? (
          <Loader2 size={16} className="animate-spin" />
        ) : channel.indexing_paused ? (
          <Play size={16} />
        ) : (
          <Pause size={16} />
        )}
        {channel.indexing_paused ? 'Resume Indexing' : 'Pause Indexing'}
      </button>

      {/* Remove channel button */}
      <button
        onClick={handleRemove}
        disabled={actionLoading !== null}
        className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium bg-red-50 text-red-600 hover:bg-red-100 transition-colors disabled:opacity-50"
      >
        {actionLoading === 'remove' ? (
          <Loader2 size={16} className="animate-spin" />
        ) : (
          <Trash2 size={16} />
        )}
        Remove Channel
      </button>

      <p className="text-xs text-gray-400 text-center mt-4">
        Removing the channel stops indexing. Existing products stay in the catalog.
      </p>
    </div>
  );
};

export default InventorySettingsTab;
