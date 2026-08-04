import React, { useState, useEffect } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Star, Bell, Sparkles, Rocket, ChevronDown, Loader2 } from 'lucide-react';
import { useSubscription } from '../hooks/useSubscription';
import { useBoost } from '../hooks/useBoost';
import { useAlerts } from '../hooks/useAlerts';

/**
 * NB-48: Monetization Hub (behavior doc §10) — one page, three tabs:
 * Boost / Alerts / All-in-One. Deep-linkable per tab; the entry point
 * selects the default tab via the URL. Prices never appear as a rate card
 * (Rule 2.4) — "from X Stars" floor, or the exact price of a preselected
 * item. The Stars invoice (openInvoice) opens ONLY from this page's buy
 * actions (Rule 10.2.6). Renders outside MainLayout — no bottom nav.
 */
const TABS = ['boost', 'alerts', 'all-in-one'];

const TAB_LABELS = { boost: 'Boost', alerts: 'Alerts', 'all-in-one': 'All-in-One' };

// Rule 10.2.5: one trust-building explainer, shown on every tab
function HowStarsExplainer() {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3"
      >
        <span className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Star size={16} className="text-amber-500" />
          How Stars work
        </span>
        <ChevronDown size={16} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="px-4 pb-4 text-xs text-gray-600 space-y-2">
          <p>
            Stars are Telegram's in-app currency. You buy them inside the app
            and pay with one tap — no card details leave Telegram.
          </p>
          <p>
            Subscriptions are 30-day auto-renewing and can be cancelled
            anytime from Telegram's payment settings.
          </p>
          <p>
            Boosts are one-time purchases — 7 days of top placement, no
            auto-renewal.
          </p>
        </div>
      )}
    </div>
  );
}

function BoostTab({ status, itemId, boost, navigate }) {
  const { quote, activeBoost, boosting, error: boostError, payWithStars } = boost;
  const hasItem = !!itemId;

  // Preselected item (deep link from the product panel): exact price in
  // context (Rule 2.4). On quote failure fall back to the guide state.
  if (hasItem && quote) {
    return (
      <div data-testid="hub-tab-boost" className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-4">
        <div className="flex items-center gap-2 mb-2">
          <Rocket size={18} className="text-amber-500" />
          <h2 className="text-base font-bold text-gray-900">Boost this product</h2>
        </div>
        <p className="text-sm font-semibold text-gray-800 mb-1 truncate">
          {quote.title || `Item #${quote.item_id}`}
        </p>
        {activeBoost ? (
          <p className="text-sm text-amber-700 font-semibold mb-4">
            Boosted — active until {new Date(activeBoost.ends_at).toLocaleDateString()}
          </p>
        ) : (
          <>
            <p className="text-sm text-gray-600 mb-1">
              Appears at the top of its category and matching searches for {quote.duration_days} days.
            </p>
            <p className="text-2xl font-extrabold text-gray-900 mb-4">
              {quote.price_stars} Stars
            </p>
            <button
              onClick={payWithStars}
              disabled={boosting}
              className="w-full py-3 rounded-xl text-sm font-bold bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {boosting ? <Loader2 size={16} className="animate-spin" /> : <Rocket size={16} />}
              Boost this item
            </button>
          </>
        )}
        {boostError && boostError !== 'NOT_IN_TELEGRAM' && (
          <p className="mt-2 text-xs text-red-600">{boostError}</p>
        )}
        {/* Cross-sell (Rule 10.2.7) */}
        <p className="mt-4 text-xs text-gray-500">
          All-in-One includes 2 free boosts every period plus seller intelligence.
        </p>
      </div>
    );
  }

  // Guide state: no preselected item (or quote unavailable)
  return (
    <div data-testid="hub-tab-boost" className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Rocket size={18} className="text-amber-500" />
        <h2 className="text-base font-bold text-gray-900">Boost your products</h2>
      </div>
      <p className="text-sm text-gray-600 mb-2">
        Your item pinned at the top of its category and matching searches for{' '}
        {status.boost_duration_days} days, labeled Boosted.
      </p>
      <p className="text-2xl font-extrabold text-gray-900 mb-4">
        from {status.boost_floor_price_stars} Stars
      </p>
      <button
        onClick={() => navigate('/stores')}
        className="w-full py-3 rounded-xl text-sm font-bold bg-amber-500 text-white hover:bg-amber-600 transition-colors flex items-center justify-center gap-2"
      >
        <Rocket size={16} />
        Choose a product
      </button>
      {/* Cross-sell (Rule 10.2.7) */}
      <p className="mt-4 text-xs text-gray-500">
        All-in-One includes 2 free boosts every period plus seller intelligence.
      </p>
    </div>
  );
}

function AlertsTab({ status, alerts, openInvoice }) {
  const subscribed = !!status.product;
  return (
    <div data-testid="hub-tab-alerts" className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Bell size={18} className="text-brand-600" />
        <h2 className="text-base font-bold text-gray-900">More alerts, fewer missed buyers</h2>
      </div>
      <p className="text-sm text-gray-600 mb-1">
        You're at {alerts.length} of {status.effective_cap} active alerts.
      </p>
      {subscribed ? (
        <p className="text-sm text-green-700 font-semibold">
          Covered — {status.product === 'all_in_one' ? 'All-in-One' : 'Alerts Only'} subscription active
        </p>
      ) : (
        <>
          <p className="text-2xl font-extrabold text-gray-900 mb-4">
            {status.alerts_only_price_stars} Stars per month
          </p>
          <button
            onClick={() => openInvoice('alerts_only')}
            className="w-full py-3 rounded-xl text-sm font-bold bg-brand-600 text-white hover:bg-brand-700 transition-colors"
          >
            Buy Alerts Only
          </button>
        </>
      )}
      {/* Cross-sell (Rule 10.2.7) */}
      <p className="mt-4 text-xs text-gray-500">
        Want insights too? All-in-One includes everything.
      </p>
    </div>
  );
}

function AllInOneTab({ status, openInvoice, navigate }) {
  const subscribed = !!status.product;
  return (
    <div data-testid="hub-tab-all-in-one" className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles size={18} className="text-amber-500" />
        <h2 className="text-base font-bold text-gray-900">All-in-One — the complete toolkit</h2>
      </div>
      <p className="text-sm text-gray-600 mb-3">
        Everything in Alerts Only, plus the tools to sell smarter:
      </p>
      <ul className="space-y-2 mb-4">
        <li className="flex gap-2 text-sm text-gray-700">
          <span className="text-amber-500 shrink-0">•</span>
          Seller Intelligence: price positioning, category pulse, top performers
        </li>
        <li className="flex gap-2 text-sm text-gray-700">
          <span className="text-amber-500 shrink-0">•</span>
          {status.credit_total} free boosts every period (
          {status.credit_remaining}/{status.credit_total} left)
        </li>
        <li className="flex gap-2 text-sm text-gray-700">
          <span className="text-amber-500 shrink-0">•</span>
          Extra alert cap — everything in Alerts Only
        </li>
      </ul>
      {subscribed ? (
        <p className="text-sm text-green-700 font-semibold mb-4">
          Active — {status.product === 'all_in_one' ? 'All-in-One' : 'Alerts Only'} subscription
        </p>
      ) : (
        <>
          <p className="text-2xl font-extrabold text-gray-900 mb-4">
            {status.all_in_one_price_stars} Stars per month
          </p>
          <button
            onClick={() => openInvoice('all_in_one')}
            className="w-full py-3 rounded-xl text-sm font-bold bg-amber-500 text-white hover:bg-amber-600 transition-colors"
          >
            Get All-in-One
          </button>
        </>
      )}
      {/* Cross-sell (Rule 10.2.7) */}
      <button
        onClick={() => navigate('/hub/boost')}
        className="mt-4 w-full py-2.5 rounded-xl text-xs font-semibold bg-gray-100 text-gray-700 hover:bg-gray-200 transition-colors"
      >
        Need visibility now? Buy a boost
      </button>
    </div>
  );
}

const MonetizationHub = () => {
  const { tab } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // URL is the single source of truth — invalid/absent tab → all-in-one
  const activeTab = TABS.includes(tab) ? tab : 'all-in-one';

  const { status, loading: subLoading, getStatus, openInvoice } = useSubscription();
  const { alerts, fetchAlerts, hasBeenFetched } = useAlerts();

  const itemId = searchParams.get('item');
  const boost = useBoost(itemId);
  const { refreshQuote } = boost;

  // Hub data on mount: subscription context (caps + prices) + usage
  useEffect(() => {
    getStatus();
  }, [getStatus]);

  useEffect(() => {
    if (!hasBeenFetched) fetchAlerts();
  }, [hasBeenFetched, fetchAlerts]);

  // Preselected item → exact price quote
  useEffect(() => {
    if (itemId) refreshQuote();
  }, [itemId, refreshQuote]);

  const go = (nextTab) => navigate(`/hub/${nextTab}`);

  // Loading state
  if (subLoading && !status) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 size={32} className="animate-spin text-brand-600" />
      </div>
    );
  }

  // Kill switch: status null after getStatus (503) → unavailable, no buy actions
  if (!status) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col">
        <header className="sticky top-0 bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-3">
          <button onClick={() => navigate(-1)} aria-label="Back" className="p-1">
            <ArrowLeft size={20} className="text-gray-700" />
          </button>
          <h1 className="text-lg font-bold text-gray-900">Monetization Hub</h1>
        </header>
        <div className="flex-1 flex flex-col items-center justify-center px-6 text-center">
          <Star size={40} className="text-gray-300 mb-3" />
          <h2 className="text-base font-bold text-gray-700 mb-2">Monetization is currently unavailable</h2>
          <p className="text-sm text-gray-500 max-w-xs">
            Boost, subscriptions and Stars payments are disabled right now. Check back later.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 font-sans flex flex-col">
      {/* Header with back affordance (renders outside MainLayout — own nav) */}
      <header className="sticky top-0 bg-white border-b border-gray-100 px-4 py-3 flex items-center gap-3 z-10">
        <button onClick={() => navigate(-1)} aria-label="Back" className="p-1">
          <ArrowLeft size={20} className="text-gray-700" />
        </button>
        <h1 className="text-lg font-bold text-gray-900">Monetization Hub</h1>
      </header>

      {/* Tabs */}
      <div className="flex gap-2 px-4 py-3">
        {TABS.map((t) => (
          <button
            key={t}
            data-testid={`hub-tab-btn-${t}`}
            onClick={() => go(t)}
            className={`flex-1 py-2 rounded-xl text-sm font-semibold transition-colors ${
              activeTab === t
                ? 'bg-brand-600 text-white shadow-sm'
                : 'bg-white text-gray-600 border border-gray-200'
            }`}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="px-4 pb-10">
        {activeTab === 'boost' && <BoostTab status={status} itemId={itemId} boost={boost} navigate={navigate} />}
        {activeTab === 'alerts' && <AlertsTab status={status} alerts={alerts} openInvoice={openInvoice} />}
        {activeTab === 'all-in-one' && <AllInOneTab status={status} openInvoice={openInvoice} navigate={navigate} />}
        <HowStarsExplainer />
      </div>
    </div>
  );
};

export default MonetizationHub;
