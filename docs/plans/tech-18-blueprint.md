# TECH-18 — Price UX, Bot Commands, Item Card Fallback

## 1. Price filter not working
**Root cause:** The backend `perform_hybrid_search` filters post-SQL. Items without price (None) are excluded by `min_price` filter (`item.price is None or item.price < min_price` — None < min_price is False in Python, but the `item.price is None` check explicitly continues). This is correct behavior — min_price excludes unpriced items. BUT the frontend sends `Number("")` which is NaN — causing no filter to match. Also the `handleTextSearch` in useShop checks `filters.minPrice && filters.minPrice !== ""` which rejects "0" as falsy.

**Fix:** In useShop.js, change the price condition: `if (filters.minPrice !== "" && !isNaN(Number(filters.minPrice)))` — allows "0" to pass through. Same for maxPrice.

## 2. "Ask for Price" on item cards
**Fix:** In ItemCard.jsx, when `item.price` is null/undefined/0, show "Ask for Price" in the price area instead of showing nothing or "0 ETB".

## 3. "Ignore products without price" toggle in search
**Fix:** Add a checkbox to SearchFilters.jsx: "Only show items with price". Sends `exclude_unpriced: true` to backend. Backend adds SQL WHERE clause: `i.price IS NOT NULL` when this flag is set. Or simpler: add a frontend-only filter that strips items with null price from results.

## 4. Stores "Add Channel" button → triggers /addchannel
**Fix:** In StoresPage.jsx, the "Add Channel" button currently links to `t.me/IndexGebeyaBot`. Change to: `t.me/IndexGebeyaBot?start=addchannel` which triggers the bot's /addchannel command automatically via deep linking.

## 5. Bot /start command — more informative
**Fix:** Update `listener/bot_ui.py` — the handle_start function. Current:
```python
"Welcome to **Index Gebeya**. Browse items instantly without leaving Telegram."
+ "Launch Store" button
```
New:
```python
"Welcome to Index Gebeya — Ethiopia's Telegram Marketplace Search Engine

🔍 *Browse & Search* — thousands of products from Ethiopian Telegram channels
🔔 *Set Alerts* — get notified when matching products are posted
🏪 *List Your Channel* — add your channel to be indexed and reach buyers

Use /addchannel to get started listing your products."
+ "🚀 Launch Store" button
+ "📋 /addchannel — Add your channel" button
```

## 6. Bot commands menu
**Fix:** In `listener/bot_ui.py` handle_start, after setting the menu button, call `bot.set_my_commands()` to register bot commands. Commands: `/start` — Open Index Gebeya, `/addchannel` — Add your channel or group, `/myalerts` — Manage your alerts, `/help` — Show help.
