import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Package, Settings, X, CheckCircle, AlertCircle } from 'lucide-react';
import StatusBadge from './StatusBadge';
import InventoryProductsTab from './InventoryProductsTab';
import InventorySettingsTab from './InventorySettingsTab';
import ProductEditPanel from './ProductEditPanel';
import { useChannelInventory } from '../hooks/useChannelInventory';
import { useOwnerChannels } from '../hooks/useOwnerChannels';

/**
 * TECH-23: Tab registry — add new tabs by pushing entries here.
 */
const TAB_REGISTRY = [
  { id: 'products', label: 'Products', icon: Package },
  { id: 'settings', label: 'Settings', icon: Settings },
];

/**
 * TECH-23: Full-page inventory modal with tab navigation.
 * Integrates product grid, edit panel, and settings tab.
 */
const ChannelInventory = ({ channel, onClose }) => {
  const [activeTab, setActiveTab] = useState('products');
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [toast, setToast] = useState(null); // { message, type } | null

  // Inventory hook for products tab
  const inventory = useChannelInventory();

  // Owner channels hook for settings tab (togglePause, removeChannel)
  const { togglePause, removeChannel } = useOwnerChannels();

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(timer);
  }, [toast]);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
  }, []);

  // Product edit panel callbacks
  const handleSelectProduct = useCallback((item) => {
    setSelectedProduct(item);
  }, []);

  const handleBackToGrid = useCallback(() => {
    setSelectedProduct(null);
  }, []);

  const handleSave = useCallback(async (updateData) => {
    try {
      await inventory.updateItem(channel.id, selectedProduct.id, updateData);
      showToast('Product updated successfully', 'success');
      setSelectedProduct(null);
    } catch (e) {
      showToast(e.message || 'Failed to save changes', 'error');
    }
  }, [channel.id, selectedProduct, inventory, showToast]);

  const handleMarkSold = useCallback(async (itemId) => {
    try {
      await inventory.markSold(channel.id, itemId);
      showToast('Item marked as sold', 'success');
      setSelectedProduct(null);
    } catch (e) {
      showToast(e.message || 'Failed to mark as sold', 'error');
    }
  }, [channel.id, inventory, showToast]);

  const handleRelist = useCallback(async (itemId) => {
    try {
      await inventory.relist(channel.id, itemId);
      showToast('Item re-listed successfully', 'success');
      setSelectedProduct(null);
    } catch (e) {
      showToast(e.message || 'Failed to re-list item', 'error');
    }
  }, [channel.id, inventory, showToast]);

  const handleClearReports = useCallback(async (itemId) => {
    try {
      await inventory.clearReports(channel.id, itemId);
      showToast('Reports cleared', 'success');
      setSelectedProduct(null);
    } catch (e) {
      showToast(e.message || 'Failed to clear reports', 'error');
    }
  }, [channel.id, inventory, showToast]);

  return (
    <div className="fixed inset-0 z-50 bg-white flex flex-col">
      {/* Header bar */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-gray-100 shrink-0">
        <button onClick={onClose} className="text-gray-600 hover:text-gray-900 transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-base font-semibold text-gray-900 truncate">
            @{channel.username}
          </h1>
        </div>
        <StatusBadge
          status={channel.indexing_paused ? 'paused' : 'active'}
          indexingPaused={channel.indexing_paused}
        />
      </div>

      {/* Tab bar (hidden when editing a product) */}
      {!selectedProduct && (
        <div className="flex border-b border-gray-100 shrink-0">
          {TAB_REGISTRY.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 flex-1 justify-center ${
                  isActive
                    ? 'text-brand-600 border-brand-600'
                    : 'text-gray-500 border-transparent hover:text-gray-700'
                }`}
              >
                <Icon size={16} />
                {tab.label}
                {tab.id === 'products' && (
                  <span className="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-gray-100 text-gray-600">
                    {channel.product_count || 0}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Toast notification */}
      {toast && (
        <div className={`absolute top-14 left-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-medium shadow-lg ${
          toast.type === 'success'
            ? 'bg-green-600 text-white'
            : 'bg-red-600 text-white'
        }`}>
          {toast.type === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {toast.message}
          <button onClick={() => setToast(null)} className="ml-auto">
            <X size={16} />
          </button>
        </div>
      )}

      {/* Content area */}
      <div className="flex-1 overflow-hidden">
        {selectedProduct ? (
          // Edit panel replaces tab content
          <ProductEditPanel
            item={selectedProduct}
            channel={channel}
            onBack={handleBackToGrid}
            onSave={handleSave}
            onMarkSold={handleMarkSold}
            onRelist={handleRelist}
            onClearReports={handleClearReports}
          />
        ) : activeTab === 'products' ? (
          <InventoryProductsTab
            channelId={channel.id}
            channel={channel}
            onSelectProduct={handleSelectProduct}
            inventory={inventory}
          />
        ) : (
          <InventorySettingsTab
            channel={channel}
            togglePause={togglePause}
            removeChannel={removeChannel}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  );
};

export default ChannelInventory;
