import React, { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ExternalLink, Loader2, DollarSign, CheckCircle,
  AlertTriangle, RefreshCw, X, Plus, Trash2, Rocket, Star
} from 'lucide-react';
import { TAXONOMY } from '../constants/taxonomy';
import { API_BASE_URL } from '../config';
import { useBoost } from '../hooks/useBoost';
import { useSubscription } from '../hooks/useSubscription';

/**
 * TECH-23: Full-screen edit panel for a single product.
 * Slides in when a product is selected from the inventory grid.
 */
const ProductEditPanel = ({
  item,
  channel,
  onBack,
  onSave,
  onMarkSold,
  onRelist,
  onClearReports,
  onDelete,
  onBoosted,
}) => {
  // NB-48: hub link from the boost section (Rule 10.1.1 — explain before pay)
  const navigate = useNavigate();

  // Parse specs from item (handles both string and object formats)
  const parseSpecs = (rawSpecs) => {
    if (!rawSpecs) return [];
    if (typeof rawSpecs === 'string') {
      try {
        const parsed = JSON.parse(rawSpecs);
        return Object.entries(parsed).map(([key, value]) => ({ key, value: String(value) }));
      } catch {
        return [];
      }
    }
    if (typeof rawSpecs === 'object') {
      return Object.entries(rawSpecs).map(([key, value]) => ({ key, value: String(value) }));
    }
    return [];
  };

  const [title, setTitle] = useState(item.title || '');
  const [description, setDescription] = useState(item.description || '');
  const [price, setPrice] = useState(item.price || '');
  const [category, setCategory] = useState(item.category || '');
  const [subcategory, setSubcategory] = useState(item.subcategory || '');
  const [specsEntries, setSpecsEntries] = useState(() => parseSpecs(item.specs));
  const [saving, setSaving] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // 'sold' | 'relist' | 'reports'

  // NB-43: Boost purchase (quote in context, Rule 2.4 — never a rate card)
  const { quote, activeBoost, boosting, error: boostError, payWithStars, refreshQuote } = useBoost(item.id);
  const [boostPaid, setBoostPaid] = useState(false);

  // NB-46: subscription credit for the credit-boost path (Rule 7.3)
  const { status: subStatus, loading: subLoading, error: subError, getStatus, applyCreditBoost } = useSubscription();
  const [creditBoosted, setCreditBoosted] = useState(false);

  useEffect(() => {
    refreshQuote();
  }, [refreshQuote]);

  useEffect(() => {
    if (subStatus == null) {
      getStatus();
    }
  }, [subStatus, getStatus]);

  const handleBoost = async () => {
    const paid = await payWithStars();
    if (paid) {
      setBoostPaid(true);
      if (onBoosted) onBoosted();
    }
  };

  const handleCreditBoost = async () => {
    const ok = await applyCreditBoost(item.id);
    if (ok) {
      setCreditBoosted(true);
      refreshQuote();
      if (onBoosted) onBoosted();
    }
  };

  const categoryOptions = useMemo(() => Object.keys(TAXONOMY), []);
  const subcategoryOptions = useMemo(() => {
    if (!category || !TAXONOMY[category]) return [];
    return TAXONOMY[category];
  }, [category]);

  // Handle category change: reset subcategory
  const handleCategoryChange = (val) => {
    setCategory(val);
    setSubcategory('');
  };

  // Specs editor helpers
  const addSpecRow = () => {
    setSpecsEntries(prev => [...prev, { key: '', value: '' }]);
  };

  const removeSpecRow = (index) => {
    setSpecsEntries(prev => prev.filter((_, i) => i !== index));
  };

  const updateSpecRow = (index, field, val) => {
    setSpecsEntries(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: val };
      return updated;
    });
  };

  // Check if field changed from original
  const hasChanged = (field) => {
    switch (field) {
      case 'title': return title !== (item.title || '');
      case 'description': return description !== (item.description || '');
      case 'price': return String(price) !== String(item.price || '');
      case 'category': return category !== (item.category || '');
      case 'subcategory': return subcategory !== (item.subcategory || '');
      case 'specs': {
        const origEntries = parseSpecs(item.specs);
        if (origEntries.length !== specsEntries.length) return true;
        for (let i = 0; i < specsEntries.length; i++) {
          if (specsEntries[i].key !== origEntries[i]?.key ||
              specsEntries[i].value !== origEntries[i]?.value) return true;
        }
        return false;
      }
      default: return false;
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updateData = {};
      if (hasChanged('title')) updateData.title = title || null;
      if (hasChanged('description')) updateData.description = description || null;
      if (hasChanged('price')) updateData.price = parseFloat(price) || null;
      if (hasChanged('category')) updateData.category = category || null;
      if (hasChanged('subcategory')) updateData.subcategory = subcategory || null;
      if (hasChanged('specs')) {
        const specsObj = {};
        specsEntries.forEach(({ key, value }) => {
          if (key.trim()) {
            specsObj[key.trim()] = value;
          }
        });
        updateData.specs = specsObj;
      }

      await onSave(updateData);
    } finally {
      setSaving(false);
    }
  };

  const handleMarkSold = async () => {
    setActionLoading('sold');
    try {
      await onMarkSold(item.id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRelist = async () => {
    setActionLoading('relist');
    try {
      await onRelist(item.id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleClearReports = async () => {
    setActionLoading('reports');
    try {
      await onClearReports(item.id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.Telegram?.WebApp?.showConfirm
      ? await new Promise(resolve => { window.Telegram.WebApp.showConfirm(
          'Delete this item permanently? This cannot be undone.', resolve); })
      : window.confirm('Delete this item permanently? This cannot be undone.');
    if (!confirmed) return;
    setActionLoading('delete');
    try {
      await onDelete(item.id);
    } finally {
      setActionLoading(null);
    }
  };

  // Telegram post URL
  const telegramPostUrl = channel?.username && item?.telegram_message_id
    ? `https://t.me/${channel.username}/${item.telegram_message_id}`
    : null;

  const formatPriceDisplay = (val) => {
    if (!val) return '0';
    return new Intl.NumberFormat('en-ET').format(val);
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-100 shrink-0">
        <button onClick={onBack} className="text-gray-600 hover:text-gray-900 transition-colors">
          <ArrowLeft size={20} />
        </button>
        <h2 className="text-base font-semibold text-gray-900 flex-1">Edit Product</h2>
        {telegramPostUrl && (
          <a
            href={telegramPostUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium"
          >
            <ExternalLink size={12} />
            View Post
          </a>
        )}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* NB-43: Boost — at the VERY TOP of the panel (UAT directive).
            Compact + explanatory. Hidden entirely when the item is not
            boostable (sold/inactive/soft-deleted) or when monetization is
            disabled (quote fetch 503s -> quote stays null). */}
        {quote && (quote.boostable || activeBoost || boostPaid) && (
          <div className="bg-gradient-to-br from-amber-50 to-brand-50 rounded-2xl p-3 border border-amber-200">
            {activeBoost || boostPaid ? (
              <div className="flex items-center gap-2 text-sm font-semibold text-amber-700">
                <CheckCircle size={16} className="shrink-0" />
                {boostPaid
                  ? 'Your item is now boosted!'
                  : `Boosted — active until ${activeBoost?.ends_at ? new Date(activeBoost.ends_at).toLocaleDateString() : ''}`}
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-bold text-gray-900 flex items-center gap-1.5 mb-0.5">
                      <Rocket size={13} className="text-amber-600 shrink-0" />
                      Boost this product
                    </p>
                    <p className="text-[11px] leading-snug text-gray-600">
                      Appears at the top of its category and matching searches
                      for {quote.duration_days} days.
                    </p>
                  </div>
                  <button
                    onClick={handleBoost}
                    disabled={boosting}
                    className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
                  >
                    {boosting ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Star size={14} />
                    )}
                    {quote.price_stars} Stars
                  </button>
                </div>

                {/* NB-48 §2.4.4: one small hub link under the explanatory
                    copy — leads to the Boost tab with this item preselected.
                    Direct buy + credit buttons stay (Rule 10.2.6 allows
                    payment from an item's own boost section). */}
                <button
                  onClick={() => navigate(`/hub/boost?item=${item.id}`)}
                  className="mt-1.5 text-[11px] font-semibold text-brand-700 hover:text-brand-800 underline underline-offset-2"
                >
                  Learn more
                </button>

                {/* NB-46 Rule 7.3: subscription credit — only when credit remains */}
                {(subStatus?.credit_remaining || 0) > 0 && (
                  <button
                    onClick={handleCreditBoost}
                    disabled={subLoading || creditBoosted}
                    className="mt-2 flex items-center justify-center gap-1.5 w-full py-1.5 rounded-lg text-[11px] font-semibold bg-white text-brand-700 border border-brand-200 hover:bg-brand-50 transition-colors disabled:opacity-50"
                  >
                    {subLoading ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Star size={12} />
                    )}
                    {creditBoosted
                      ? 'Boosted with credit!'
                      : `Use free credit (${subStatus.credit_remaining} left)`}
                  </button>
                )}

                {((boostError && boostError !== 'NOT_IN_TELEGRAM') ||
                  (subError && subError !== 'NOT_IN_TELEGRAM')) && (
                  <p className="mt-1.5 text-[11px] text-red-600">
                    {boostError || subError}
                  </p>
                )}
              </>
            )}
          </div>
        )}

        {/* Thumbnail image */}
        <div className="bg-white rounded-2xl overflow-hidden shadow-sm border border-gray-100">
          {item.image_path || (item.images && item.images[0]) ? (
            <img
              src={`${API_BASE_URL}/media/${item.image_path || (item.images && item.images[0])}`}
              alt={item.title || 'Product'}
              className="w-full h-48 object-cover"
              onError={(e) => { e.target.src = '/placeholder.png'; }}
            />
          ) : (
            <div className="w-full h-48 flex flex-col items-center justify-center bg-gray-50 text-gray-400">
              <AlertTriangle size={32} className="mb-2" />
              <span className="text-sm">No Image Available</span>
            </div>
          )}
        </div>

        {/* Editable fields */}
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              className="w-full px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent resize-none"
            />
          </div>

          {/* Price */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Price (ETB)</label>
            <div className="relative">
              <DollarSign size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="number"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                step={1}
                min={0}
                className="w-full pl-9 pr-4 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-gray-500">ETB</span>
            </div>
          </div>

          {/* Category */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Category</label>
            <select
              value={category}
              onChange={(e) => handleCategoryChange(e.target.value)}
              className="w-full px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent"
            >
              <option value="">Select category</option>
              {categoryOptions.map((cat) => (
                <option key={cat} value={cat}>{cat}</option>
              ))}
            </select>
          </div>

          {/* Subcategory */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-1">Subcategory</label>
            <select
              value={subcategory}
              onChange={(e) => setSubcategory(e.target.value)}
              disabled={!category}
              className="w-full px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent disabled:opacity-50"
            >
              <option value="">Select subcategory</option>
              {subcategoryOptions.map((sub) => (
                <option key={sub} value={sub}>{sub}</option>
              ))}
            </select>
          </div>

          {/* Specs editor */}
          <div>
            <label className="block text-xs font-semibold text-gray-500 mb-2">Specifications</label>
            <div className="space-y-2">
              {specsEntries.map((entry, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Key (e.g., Brand)"
                    value={entry.key}
                    onChange={(e) => updateSpecRow(index, 'key', e.target.value)}
                    className="flex-1 px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent"
                  />
                  <input
                    type="text"
                    placeholder="Value (e.g., Samsung)"
                    value={entry.value}
                    onChange={(e) => updateSpecRow(index, 'value', e.target.value)}
                    className="flex-1 px-3 py-2 bg-gray-50 rounded-xl text-sm text-gray-800 border border-gray-200 focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-transparent"
                  />
                  <button
                    onClick={() => removeSpecRow(index)}
                    className="text-gray-400 hover:text-red-500 transition-colors p-1"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              <button
                onClick={addSpecRow}
                className="flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium py-1"
              >
                <Plus size={14} />
                Add Spec
              </button>
            </div>
          </div>
        </div>

        {/* Status controls */}
        <div className="bg-white rounded-2xl p-4 shadow-sm border border-gray-100 space-y-2">
          <h3 className="text-xs font-semibold text-gray-500 mb-2">Status Controls</h3>

          {/* Mark as Sold — disabled if already sold */}
          <button
            onClick={handleMarkSold}
            disabled={actionLoading !== null || item.status === 'sold'}
            className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium bg-green-50 text-green-700 hover:bg-green-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {actionLoading === 'sold' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <CheckCircle size={16} />
            )}
            {item.status === 'sold' ? 'Already Marked as Sold' : 'Mark as Sold'}
          </button>

          {/* Re-list — disabled if already active */}
          <button
            onClick={handleRelist}
            disabled={actionLoading !== null || item.status === 'active' || !item.status}
            className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {actionLoading === 'relist' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            {!item.status || item.status === 'active' ? 'Already Listed' : 'Re-list Item'}
          </button>

          {/* Clear Reports (only if reported_sold) */}
          {item.status === 'reported_sold' && (
            <button
              onClick={handleClearReports}
              disabled={actionLoading !== null}
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium bg-amber-50 text-amber-700 hover:bg-amber-100 transition-colors disabled:opacity-50"
            >
              {actionLoading === 'reports' ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <AlertTriangle size={16} />
              )}
              Clear Reports
            </button>
          )}

          {/* Delete item — permanent, with confirmation */}
          <button
            onClick={handleDelete}
            disabled={actionLoading === 'delete'}
            className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-medium bg-red-50 text-red-600 hover:bg-red-100 transition-colors disabled:opacity-50"
          >
            {actionLoading === 'delete' ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Trash2 size={16} />
            )}
            Delete Item
          </button>
        </div>
      </div>

      {/* Save button - fixed bottom */}
      <div className="shrink-0 px-4 py-3 bg-white border-t border-gray-100">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-semibold bg-brand-600 text-white hover:bg-brand-700 transition-colors disabled:opacity-50 shadow-sm"
        >
          {saving ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Saving...
            </>
          ) : (
            'Save Changes'
          )}
        </button>
      </div>
    </div>
  );
};

export default ProductEditPanel;
