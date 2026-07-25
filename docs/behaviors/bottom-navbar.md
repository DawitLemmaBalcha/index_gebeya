# Bottom Navigation Bar

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

The webapp currently has no persistent navigation. Buyers browse the feed and search from the top bar, but alerts and channel management are inaccessible without knowing specific commands or navigating through product pages. A bottom navigation bar provides persistent, thumb-friendly access to the three core sections: Explore, Alerts, and Stores.

---

## Behavioral Rules

### 1. Tab Structure

| Tab | Icon | Label | Content |
|-----|------|-------|---------|
| **Explore** | 🔍 (Search icon) | Explore | The main feed + search + category browsing. This is the current home page experience. |
| **Alerts** | 🔔 (Bell icon) | Alerts | The user's saved alerts. Create new alert, view active alerts, see match history. |
| **Stores** | 🏪 (Store icon) | Stores | Channel/group management for owners. List of channels, stats, pause/resume indexing. |

### 2. Visibility Rules

**Rule 2.1 — Always Visible**
The bottom navbar is always visible when the user is inside the webapp (not on the onboarding/landing page). It persists across tab switches. It does not appear on the product detail page — only on the main tab views.

**Rule 2.2 — Stores Tab Visibility**
The Stores tab appears for ALL users, but the content differs:
- **Channel owners** (users with at least one channel where `registered_by` matches their Telegram ID): see their channel management dashboard.
- **Non-owners**: see a prompt: "Add your Telegram channel to appear here. Get your products indexed and reach thousands of buyers." with a link to the `/addchannel` instructions.

**Rule 2.3 — Active Tab Indication**
The currently active tab is visually highlighted — filled icon, brand-amber color, bold label. Inactive tabs use outline icons and muted gray.

### 3. Tab Switching Behavior

**Rule 3.1 — State Preservation**
Switching tabs does not discard the previous tab's state. The feed scroll position, active search query, and filter selections are preserved when switching back to Explore.

**Rule 3.2 — Tab Initialization**
Each tab loads its content only when first activated. Alerts are not fetched until the user taps the Alerts tab for the first time in a session. This avoids unnecessary API calls.

**Rule 3.3 — Deep Linking**
Navigating to a product detail page hides the bottom navbar. Tapping back restores the navbar and the previously active tab.

### 4. Explore Tab — Feed Entry Point

**Rule 4.1 — Default Tab**
Explore is the default tab. It is the first thing a user sees after onboarding or on return visits.

**Rule 4.2 — Same as Current Home**
The Explore tab content is identical to the current home page experience: infinite scroll feed, search bar, category bar, search filters. No behavioral changes — this is repackaging the existing home page into a tab.

### 5. Alerts Tab — Alert Management

**Rule 5.1 — Alert List**
Shows all active alerts for the user. Each alert card displays:
- The query text (e.g., "iPhone 13 Pro")
- Max price (or "Any Price")
- Smart filter toggles (Strict Brand, Strict Model)
- How many matches found so far (notification count)
- A "Pause" toggle (mark inactive without deleting)
- A "Delete" button (permanently remove)

**Rule 5.2 — Create Alert**
A "+" button in the header opens the same alert creation flow as the current "Alert Me" modal on product pages. The flow is identical — query text, max price, smart filters — but accessible from the Alerts tab without being on a specific product.

**Rule 5.3 — Match History**
Below the active alerts list, a "Recent Matches" section shows notifications the user has received, sorted by most recent. Each match card shows the product title, price, match tier (bullseye/ring), and a link to the product detail page.

**Rule 5.4 — Empty State**
If the user has no alerts: "You don't have any alerts yet. Create one to get notified when a product matching your search is posted." with a "Create Your First Alert" button.

### 6. Stores Tab — Channel Management

**Rule 6.1 — Owner View**
If the user owns channels (`registered_by` matches), display each channel as a card with:
- Channel @username and title
- Status badge: Active (green), Paused (amber), Removed (gray)
- Product count: "247 products indexed"
- View count: "1.2K views this month"
- Click-through count: "89 Telegram opens"
- Action buttons: Pause/Resume, Remove

**Rule 6.2 — Pause/Resume**
Tapping "Pause" stops ingestion from that channel. Products already indexed remain in the catalog. The channel card shows "Paused" status. Tapping "Resume" re-enables ingestion. The bot does not need to be re-added.

**Rule 6.3 — Remove**
Tapping "Remove" disconnects the channel from Index Gebeya. Products remain in the catalog but future posts are not ingested. The channel owner can re-add the bot at any time.

**Rule 6.4 — Add Channel Guide**
A persistent card at the bottom of the Stores tab: "Want to list another channel? Add our bot as admin and your products will appear here." with a "How to Add" link that shows the `/addchannel` instructions inline.

**Rule 6.5 — Non-Owner View**
If the user does not own any channels: a friendly prompt explaining the value of listing products on Index Gebeya, with a button to learn how to add the bot to their channel.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| Alerts API fails | Show "Could not load alerts" with retry button |
| Stores API fails | Show "Could not load stores" with retry button |
| User has no Telegram ID (anonymous browsing) | Alerts and Stores tabs prompt to "Open in Telegram" to use these features |
| Network loss during tab switch | Previously loaded tab content is shown from cache. New tab shows loading spinner and retries. |
