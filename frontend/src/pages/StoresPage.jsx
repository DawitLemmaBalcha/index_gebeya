import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Store, Package, Eye, ExternalLink, Pause, Play, Trash2, Loader2, RefreshCw, AlertCircle, X, Sparkles, Star, Rocket } from 'lucide-react';
import { useOwnerChannels } from '../hooks/useOwnerChannels';
import { useSubscription } from '../hooks/useSubscription';
import { useBoosts } from '../hooks/useBoosts';
import { useRefetchOnActivation } from '../hooks/useRefetchOnActivation';
import AddChannelButton from '../components/AddChannelButton';
import { API_BASE_URL } from '../config';
import { getAnalyticsHeaders } from '../utils/analytics';
import ChannelInventory from '../components/ChannelInventory';

const StoresPage = ({ deepLink, active = true }) => {
  const navigate = useNavigate();
  const { channels, loading, error, fetchChannels, hasBeenFetched, togglePause, removeChannel } = useOwnerChannels();
  const { status: subStatus, loading: subLoading, error: subError, getStatus } = useSubscription();
  // NB-48: active boosts across the owner's channels (Stores boost card)
  const { boosts, error: boostsError, hasBeenFetched: boostsFetched, fetchBoosts } = useBoosts();
  const [howToExpanded, setHowToExpanded] = useState(false);
  const [modalState, setModalState] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [deepLinkItem, setDeepLinkItem] = useState(null);

  // Lazy load: fetch only on first activation
  useEffect(() => {
    if (!hasBeenFetched) {
      fetchChannels();
    }
  }, [hasBeenFetched, fetchChannels]);

  // NB-46: subscription status for the card. BUG 2: the page stays mounted
  // across tab switches (MainLayout toggles display only), so a single
  // mount fetch goes stale — refetch whenever the Stores tab becomes active.
  // TECH-39: the hasBeenFetched gate lives here (not in the hook) via the
  // stable wrapper — effect fires when hasBeenFetched flips false→true
  // (active only) and on activation (gate already true). Deps-equivalent to
  // the old [active, hasBeenFetched, getStatus] effect.
  const refetchSubscriptionStatus = useCallback(() => {
    if (hasBeenFetched) getStatus();
  }, [hasBeenFetched, getStatus]);

  useRefetchOnActivation(active, refetchSubscriptionStatus);

  // NB-48: active boosts for the boost management card — fan out per
  // channel. Runs for zero channels too (BUG 1): fetchBoosts([]) fans out
  // to nothing, resolves to an empty list, and renders the card's empty
  // state ("No active boosts").
  useEffect(() => {
    if (hasBeenFetched) {
      fetchBoosts(channels);
    }
  }, [hasBeenFetched, channels, fetchBoosts]);

  // NB-45: deep link handling — auto-open ChannelInventory for the channel,
  // then auto-open ProductEditPanel for the exact item (§2.8).
  useEffect(() => {
    if (!deepLink) return;
    let cancelled = false;

    (async () => {
      if (channels.length === 0 && !hasBeenFetched) {
        try { await fetchChannels(); } catch { /* error surfaces via hook */ }
      }
      const channel = channels.find((c) => String(c.id) === String(deepLink.channelId));
      if (!channel) return;
      setSelectedChannel(channel);
      try {
        const res = await fetch(`${API_BASE_URL}/items/${deepLink.itemId}`, {
          headers: { ...getAnalyticsHeaders() },
        });
        if (res.ok) {
          const item = await res.json();
          if (!cancelled) setDeepLinkItem(item);
        }
      } catch {
        // The inventory opens regardless; the product panel needs the item
        // fetch to succeed, which it will on retry from the grid.
      }
    })();

    return () => { cancelled = true; };
  }, [deepLink, channels, hasBeenFetched, fetchChannels]);

  const formatNumber = (num) => {
    if (num == null) return '—';
    return new Intl.NumberFormat('en-ET').format(num);
  };

  // NB-48: "time remaining" for the boost card (soonest-expiring first)
  const timeLeft = (endsAt) => {
    const diff = new Date(endsAt) - Date.now();
    if (diff <= 0) return 'Expiring now';
    const days = Math.ceil(diff / 86400000);
    if (days > 1) return `${days} days left`;
    if (days === 1) return '1 day left';
    return 'Less than a day left';
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

  // BUG 1: the monetization cards render for BOTH owner and zero-channel
  // (non-owner) users — they must NOT be gated on channels.length > 0.
  // Subscription card: needs only a successful status fetch (subStatus
  // !== null; when monetization is disabled the backend returns 503 and
  // getStatus leaves subStatus null — the whole card stays hidden).
  // Boost card: needs only the boosts fetch to succeed (empty state
  // included); hides on 503/failure.
  const subscriptionCard = subStatus !== null && (
    <div className="bg-gradient-to-br from-brand-50 to-amber-50 rounded-2xl p-4 border border-brand-100 mb-4">
      {subStatus?.product ? (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={16} className="text-amber-500" />
            <h3 className="text-sm font-bold text-gray-900 capitalize">
              {subStatus.product === 'all_in_one' ? 'All-in-One' : 'Alerts Only'} Subscription
            </h3>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-600 mb-2">
            <span>+{subStatus.extra_alerts} alerts</span>
            {subStatus.product === 'all_in_one' && (
              <span className="flex items-center gap-1">
                <Star size={12} className="text-amber-500" />
                {subStatus.credit_remaining}/{subStatus.credit_total} boost credits
              </span>
            )}
            {subStatus.current_period_end && (
              <span className="text-gray-400">
                renews {new Date(subStatus.current_period_end).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      ) : (
        <div>
          <h3 className="text-sm font-bold text-gray-900 mb-1 flex items-center gap-2">
            <Sparkles size={16} className="text-amber-500" />
            Boost your selling power
          </h3>
          <p className="text-xs text-gray-600 mb-3">
            Seller intelligence, monthly boost credits, and extra alert space — everything in one subscription.
          </p>
          {subError && subError !== 'NOT_IN_TELEGRAM' && (
            <p className="text-xs text-red-600 mb-2">{subError}</p>
          )}
          {/* NB-48 Rule 10.2.6: never a bare invoice — the hub explains
              first, then sells. */}
          <button
            onClick={() => navigate('/hub/all-in-one')}
            disabled={subLoading}
            className="w-full py-2 rounded-xl text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50"
          >
            {subLoading ? 'Loading...' : 'All-in-One'}
          </button>
        </div>
      )}
    </div>
  );

  // NB-48 §2.3: boost management card — active boosts across the owner's
  // channels (item + time remaining), "Boost a product", All-in-One upsell.
  const boostCard = boostsFetched && !boostsError && (
    <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <Rocket size={16} className="text-amber-500" />
        <h3 className="text-sm font-bold text-gray-900">Active Boosts</h3>
      </div>

      {boosts.length === 0 ? (
        <p className="text-xs text-gray-500 mb-3">No active boosts</p>
      ) : (
        <div className="space-y-2 mb-3">
          {boosts.map((boost) => (
            <div
              key={boost.item_id}
              className="flex items-center justify-between gap-2 bg-gray-50 rounded-xl px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-xs font-semibold text-gray-900 truncate">
                  {boost.title || `Item #${boost.item_id}`}
                </p>
                <p className="text-[10px] text-gray-500">{timeLeft(boost.ends_at)}</p>
              </div>
              <span className="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-700">
                BOOSTED
              </span>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => navigate('/hub/boost')}
          className="flex-1 py-2 rounded-xl text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 transition-colors"
        >
          Boost a product
        </button>
        <button
          onClick={() => navigate('/hub/all-in-one')}
          className="flex-1 py-2 rounded-xl text-xs font-semibold bg-white text-brand-700 border border-brand-200 hover:bg-brand-50 transition-colors"
        >
          All-in-One includes free boosts
        </button>
      </div>
    </div>
  );

  // Owner view (has channels)
  if (channels.length > 0) {
    // TECH-23: Show inventory modal when a channel is selected
    if (selectedChannel) {
      return (
        <ChannelInventory
          channel={selectedChannel}
          onClose={() => { setSelectedChannel(null); setDeepLinkItem(null); }}
          initialProduct={deepLinkItem}
        />
      );
    }

    return (
      <div className="px-4 pt-4 pb-24">
        <h1 className="text-xl font-bold text-gray-900 mb-4">My Stores</h1>

        {/* NB-46 subscription card — extracted above so it also renders
            for zero-channel users (BUG 1). */}
        {subscriptionCard}

        {/* NB-48 §2.3 boost management card — extracted above (BUG 1). */}
        {boostCard}

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
              onClick={() => setSelectedChannel(channel)}
              className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 cursor-pointer hover:shadow-md transition-shadow"
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
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedChannel(channel); }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-brand-50 text-brand-700 hover:bg-brand-100 transition-colors"
                >
                  Manage
                </button>
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
          <AddChannelButton />
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

  // Non-owner view (no channels) — BUG 1: the monetization sections stay
  // visible for zero-channel users (subscription card + Active Boosts card
  // with its empty state), followed by the educational prompt and a
  // persistent Add Channel CTA (triggers /addchannel in the bot).
  return (
    <div className="px-4 pt-4 pb-24">
      {subscriptionCard}
      {boostCard}

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

      {/* BUG 1: persistent Add Channel CTA for zero-channel users — the
          same /addchannel deep link as the owner view's CTA, visible
          without expanding "How to Add". */}
      <div className="bg-brand-50 rounded-2xl p-4 border border-brand-100 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold text-brand-800">Want to list a channel or group?</p>
          <p className="text-xs text-brand-600 mt-0.5">Add @IndexGebeyaBot as admin to your channel or group.</p>
        </div>
        <AddChannelButton />
      </div>
    </div>
  );
};

export default StoresPage;
