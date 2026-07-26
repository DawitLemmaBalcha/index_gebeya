import React, { useState, useEffect } from 'react';
import { Store, Package, Eye, ExternalLink, Pause, Play, Trash2, PlusCircle, Loader2, RefreshCw, AlertCircle, X } from 'lucide-react';
import { useOwnerChannels } from '../hooks/useOwnerChannels';

const StoresPage = () => {
  const { channels, loading, error, fetchChannels, hasBeenFetched, togglePause, removeChannel } = useOwnerChannels();
  const [howToExpanded, setHowToExpanded] = useState(false);
  const [modalState, setModalState] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Lazy load: fetch only on first activation
  useEffect(() => {
    if (!hasBeenFetched) {
      fetchChannels();
    }
  }, [hasBeenFetched, fetchChannels]);

  const formatNumber = (num) => {
    if (num == null) return '—';
    return new Intl.NumberFormat('en-ET').format(num);
  };

  const handleAction = async () => {
    if (!modalState) return;

    setActionLoading(true);
    try {
      if (modalState.type === 'pause') {
        await togglePause(modalState.channel.id, true);
      } else if (modalState.type === 'resume') {
        await togglePause(modalState.channel.id, false);
      } else if (modalState.type === 'remove') {
        await removeChannel(modalState.channel.id);
      }
      setModalState(null);
    } catch (e) {
      // Error is set in the hook, keep modal open so user can retry
    } finally {
      setActionLoading(false);
    }
  };

  // Not-in-Telegram state
  if (error === 'NOT_IN_TELEGRAM') {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
        <Store size={48} className="text-gray-300 mb-4" />
        <h2 className="text-lg font-bold text-gray-700 mb-2">Open in Telegram</h2>
        <p className="text-sm text-gray-500 max-w-xs">
          Store management is only available inside the Telegram Mini App. Open @IndexGebeyaBot in Telegram to manage your stores.
        </p>
      </div>
    );
  }

  // Loading state
  if (loading && channels.length === 0) {
    return (
      <div className="flex justify-center items-center min-h-[60vh]">
        <Loader2 size={32} className="animate-spin text-brand-600" />
      </div>
    );
  }

  // Error state
  if (error && channels.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center">
        <AlertCircle size={48} className="text-red-400 mb-4" />
        <h2 className="text-lg font-bold text-gray-700 mb-2">Could not load stores</h2>
        <p className="text-sm text-gray-500 mb-4">{error}</p>
        <button
          onClick={fetchChannels}
          className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors"
        >
          <RefreshCw size={16} /> Retry
        </button>
      </div>
    );
  }

  // Owner view (has channels)
  if (channels.length > 0) {
    return (
      <div className="px-4 pt-4 pb-24">
        <h1 className="text-xl font-bold text-gray-900 mb-4">My Stores</h1>

        {/* Error toast for action failures */}
        {error && error !== 'NOT_IN_TELEGRAM' && channels.length > 0 && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700 flex items-center gap-2">
            <AlertCircle size={16} className="shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="space-y-3 mb-6">
          {channels.map((channel) => (
            <div
              key={channel.id}
              className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100"
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1 min-w-0">
                  <h3 className="font-semibold text-gray-900">@{channel.username}</h3>
                  {channel.title && (
                    <p className="text-sm text-gray-500 truncate">{channel.title}</p>
                  )}
                </div>
                <span
                  className={`ml-2 px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                    channel.indexing_paused
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-green-100 text-green-700'
                  }`}
                >
                  {channel.indexing_paused ? 'PAUSED' : 'ACTIVE'}
                </span>
              </div>

              {/* Stats row */}
              <div className="grid grid-cols-3 gap-3 mb-3">
                <div className="bg-gray-50 p-2 rounded-xl text-center">
                  <Package size={14} className="text-gray-400 mx-auto mb-1" />
                  <p className="text-xs font-bold text-gray-900">
                    {formatNumber(channel.product_count)}
                  </p>
                  <p className="text-[10px] text-gray-500">Products</p>
                </div>
                <div className="bg-gray-50 p-2 rounded-xl text-center">
                  <Eye size={14} className="text-gray-400 mx-auto mb-1" />
                  <p className="text-xs font-bold text-gray-900">—</p>
                  <p className="text-[10px] text-gray-500">Views</p>
                </div>
                <div className="bg-gray-50 p-2 rounded-xl text-center">
                  <ExternalLink size={14} className="text-gray-400 mx-auto mb-1" />
                  <p className="text-xs font-bold text-gray-900">—</p>
                  <p className="text-[10px] text-gray-500">Clicks</p>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-2">
                {channel.indexing_paused ? (
                  // Resume button — fires immediately, no modal
                  <button
                    onClick={() => togglePause(channel.id, false)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors"
                  >
                    <Play size={14} />
                    Resume
                  </button>
                ) : (
                  // Pause button — opens confirmation modal
                  <button
                    onClick={() => setModalState({ type: 'pause', channel })}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors"
                  >
                    <Pause size={14} />
                    Pause
                  </button>
                )}
                <button
                  onClick={() => setModalState({ type: 'remove', channel })}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 text-red-600 hover:bg-red-100 transition-colors"
                >
                  <Trash2 size={14} />
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Add another channel CTA */}
        <div className="bg-brand-50 rounded-2xl p-4 border border-brand-100 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-brand-800">Want to list another channel?</p>
            <p className="text-xs text-brand-600 mt-0.5">Add @IndexGebeyaBot as admin to your channel.</p>
          </div>
          <a
            href="https://t.me/IndexGebeyaBot?start=addchannel"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-2 bg-brand-600 text-white rounded-xl text-xs font-medium hover:bg-brand-700 transition-colors shrink-0"
          >
            <PlusCircle size={14} />
            Add Channel
          </a>
        </div>

        {/* Confirmation Modal */}
        {modalState && (
          <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/40" onClick={() => !actionLoading && setModalState(null)} />
            {/* Card */}
            <div className="relative bg-white rounded-2xl p-6 max-w-sm w-full mx-4 shadow-xl">
              {/* Close button */}
              {!actionLoading && (
                <button
                  onClick={() => setModalState(null)}
                  className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X size={20} />
                </button>
              )}

              {/* Pause Modal */}
              {modalState.type === 'pause' && (
                <>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">Pause Indexing</h3>
                  <p className="text-sm text-gray-600 mb-6">
                    Pause indexing for @{modalState.channel.username}? Your products stay in
                    the catalog but new posts won't appear. You can resume anytime.
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setModalState(null)}
                      disabled={actionLoading}
                      className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleAction}
                      disabled={actionLoading}
                      className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-brand-600 text-white hover:bg-brand-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {actionLoading && <Loader2 size={16} className="animate-spin" />}
                      Pause
                    </button>
                  </div>
                </>
              )}

              {/* Remove Modal */}
              {modalState.type === 'remove' && (
                <>
                  <h3 className="text-lg font-bold text-gray-900 mb-2">Remove Channel</h3>
                  <p className="text-sm text-gray-600 mb-6">
                    Remove @{modalState.channel.username} from Index Gebeya? The bot will
                    leave your channel. Existing products stay in the catalog but new posts
                    won't be indexed. You can add the bot back anytime.
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setModalState(null)}
                      disabled={actionLoading}
                      className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleAction}
                      disabled={actionLoading}
                      className="flex-1 py-2.5 rounded-xl text-sm font-medium bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {actionLoading && <Loader2 size={16} className="animate-spin" />}
                      Remove
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    );
  }

  // Non-owner view (no channels)
  return (
    <div className="px-4 pt-4 pb-24">
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <Store size={48} className="text-gray-300 mb-4" />
        <h2 className="text-lg font-bold text-gray-700 mb-2">Add Your Store</h2>
        <p className="text-sm text-gray-500 mb-6 max-w-sm">
          Add your Telegram channel to appear here. Get your products indexed and reach thousands of buyers.
        </p>

        <button
          onClick={() => setHowToExpanded(!howToExpanded)}
          className="px-5 py-3 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors shadow-sm mb-4"
        >
          How to Add
        </button>

        {howToExpanded && (
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 text-left max-w-sm">
            <h3 className="font-bold text-gray-900 mb-3 text-sm">Step-by-Step Instructions</h3>
            <ol className="space-y-3 text-sm text-gray-600">
              <li className="flex gap-2">
                <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-bold">1</span>
                <span>Open <strong>@IndexGebeyaBot</strong> on Telegram.</span>
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-bold">2</span>
                <span>Send the <strong>/start</strong> command to the bot.</span>
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-bold">3</span>
                <span>Add the bot as an <strong>admin</strong> to your public Telegram channel.</span>
              </li>
              <li className="flex gap-2">
                <span className="shrink-0 w-5 h-5 rounded-full bg-brand-100 text-brand-700 flex items-center justify-center text-xs font-bold">4</span>
                <span>The bot will automatically read your new posts and index your products.</span>
              </li>
            </ol>
            <a
              href="https://t.me/IndexGebeyaBot?start=addchannel"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 w-full mt-4 px-4 py-2.5 bg-brand-600 text-white rounded-xl text-sm font-medium hover:bg-brand-700 transition-colors"
            >
              <ExternalLink size={14} />
              Open @IndexGebeyaBot
            </a>
          </div>
        )}
      </div>
    </div>
  );
};

export default StoresPage;
