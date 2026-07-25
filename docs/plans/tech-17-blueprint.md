# TECH-17 — Bottom Navbar + Stores Dashboard: Implementation Blueprint

**Goal:** Add persistent three-tab bottom navigation (Explore, Alerts, Stores) with lazy loading, state preservation, and a new backend endpoint `GET /channels/mine`.

---

## Files to Modify/Create

### CREATE
- `frontend/src/components/BottomNav.jsx` — **REWRITE** existing stub for Explore/Alerts/Stores tabs
- `frontend/src/pages/AlertsPage.jsx` — **NEW** — alerts management tab
- `frontend/src/pages/StoresPage.jsx` — **NEW** — stores dashboard tab
- `frontend/src/hooks/useAlerts.js` — **NEW** — custom hook for alert CRUD and match history
- `frontend/src/hooks/useOwnerChannels.js` — **NEW** — custom hook for owner channels with stats

### MODIFY
- `frontend/src/App.jsx` — restructure routing to support persistent tab layout
- `frontend/src/pages/Home.jsx` — adapt as Explore tab (remove full-screen wrapper when embedded)
- `backend/api/routes/channels.py` — add `GET /channels/mine` endpoint
- `backend/api/routes/alerts.py` — add `PATCH /{alert_id}/pause` toggle and `GET /matches` endpoint
- `backend/main.py` — no new router needed (endpoints added to existing routers)

---

## Strict Import Map

### 1. BottomNav.jsx (rewrite)

**Exports:** `default function BottomNav({ activeTab, setActiveTab })`

**Imports from lucide-react:**
- `Compass` (Explore tab icon)
- `Bell` (Alerts tab icon)
- `Store` (Stores tab icon)

**Tailwind classes to use for brand colors:**
- Active state: `bg-brand-50 text-brand-600` (light amber background, dark amber text)
- Inactive state: `text-gray-400 hover:text-gray-600 hover:bg-gray-50`
- Active indicator: a 2px bar at top of active tab using `bg-brand-500`
- No external dependencies beyond lucide-react.

### 2. AlertsPage.jsx (new)

**Exports:** `default function AlertsPage({})`

**Imports (from existing codebase):**
- `React, { useState, useEffect }` from `react`
- `API_BASE_URL` from `../config`
- `getAnalyticsHeaders` from `../utils/analytics`
- `AlertModal` from `../components/AlertModal`
- `useAlerts` from `../hooks/useAlerts`
- lucide-react icons: `Bell, Plus, Pause, Play, Trash2, History, AlertCircle, Loader2, RefreshCw, X`

**Internal state (managed by useAlerts hook):**
- `alerts: Array<AlertResponse>` — active alerts from GET /alerts/
- `matchHistory: Array<NotificationResponse>` — from GET /alerts/matches
- `loading: boolean`
- `error: string | null`
- `isCreateModalOpen: boolean`
- `submittingActionId: number | null` — which alert is being paused/deleted

### 3. StoresPage.jsx (new)

**Exports:** `default function StoresPage({})`

**Imports (from existing codebase):**
- `React, { useState, useEffect }` from `react`
- `API_BASE_URL` from `../config`
- `getAnalyticsHeaders` from `../utils/analytics`
- `useOwnerChannels` from `../hooks/useOwnerChannels`
- lucide-react icons: `Store, Package, Eye, ExternalLink, Pause, Play, Trash2, PlusCircle, Loader2, RefreshCw, AlertCircle`

**Internal state (managed by useOwnerChannels hook):**
- `channels: Array<OwnerChannelResponse>` — from GET /channels/mine
- `loading: boolean`
- `error: string | null`

### 4. useAlerts.js (new hook)

**Exports:** `export function useAlerts()`

**Returns object:**
```ts
{
  alerts: Array,        // AlertResponse[]
  matchHistory: Array,  // NotificationResponse[] (recent matches)
  loading: boolean,
  error: string | null,
  fetchAlerts: () => Promise<void>,
  fetchMatchHistory: () => Promise<void>,
  pauseAlert: (alertId: number) => Promise<void>,
  deleteAlert: (alertId: number) => Promise<void>,
  hasBeenFetched: boolean,  // for lazy loading
}
```

**Module-level cache:** `let _alertsCache = null` and `let _matchesCache = null` — same pattern as useShop.js lines 6-7.

**API calls:**
- `GET ${API_BASE_URL}/alerts/?init_data=${window.Telegram?.WebApp?.initData}` — list active alerts (existing endpoint)
- `GET ${API_BASE_URL}/alerts/matches?init_data=${window.Telegram?.WebApp?.initData}` — new endpoint for match history
- `PATCH ${API_BASE_URL}/alerts/${id}/pause?init_data=${...}` — toggle is_active (new endpoint)
- `DELETE ${API_BASE_URL}/alerts/${id}?init_data=${...}` — delete alert (existing endpoint)

### 5. useOwnerChannels.js (new hook)

**Exports:** `export function useOwnerChannels()`

**Returns object:**
```ts
{
  channels: Array,       // OwnerChannelResponse[] (channel + stats)
  loading: boolean,
  error: string | null,
  fetchChannels: () => Promise<void>,
  hasBeenFetched: boolean,
}
```

**Module-level cache:** `let _channelsCache = null`

**API call:**
- `GET ${API_BASE_URL}/channels/mine?init_data=${window.Telegram?.WebApp?.initData}` — new endpoint

### 6. App.jsx modifications

**New imports:**
- `React, { useState, useMemo }` from `react`
- `BottomNav` from `./components/BottomNav`
- `AlertsPage` from `./pages/AlertsPage`
- `StoresPage` from `./pages/StoresPage`
- `TabContext` or inline state (see architecture below)

**Existing imports retained:**
- `Home` from `./pages/Home`
- `ProductPage` from `./pages/ProductPage`
- `LandingPage` from `./pages/LandingPage`
- `BrowserRouter, Routes, Route` from `react-router-dom`

### 7. Home.jsx modifications

No new imports. Remove `min-h-screen` from root div. Accept optional `embedded` prop (default false) to control whether the page wrapper applies full-screen background. When rendered inside the tab layout, the parent layout handles the background.

**New prop:** `embedded?: boolean`

### 8. Backend: channels.py additions

**New imports:**
- `from urllib.parse import parse_qs`
- `import json`
- `from models import User, Item`
- `from sqlalchemy import func, select`
- `from fastapi import Request, Header`
- `from typing import Optional`

**New response model** (add to `backend/schemas.py`):
```python
class OwnerChannelResponse(BaseModel):
    id: int
    username: str
    title: Optional[str]
    trust_score: float
    review_count: int
    is_verified: bool
    product_count: int
    is_active: bool = True  # placeholder for pause/resume state

    class Config:
        from_attributes = True
```

**New endpoint:**
- `GET /channels/mine` — accepts `init_data` query param for auth, returns `List[OwnerChannelResponse]`
- Auth logic: parse initData → extract telegram_id → look up User → query channels WHERE `registered_by = user.telegram_id`
- Product count: subquery `SELECT COUNT(*) FROM items WHERE channel_id = channel.id`

### 9. Backend: alerts.py additions

**New endpoints:**
- `PATCH /alerts/{alert_id}/pause` — toggles `is_active` between True/False (pause/resume). Accepts `init_data` for auth.
- `GET /alerts/matches` — returns list of Notification objects for the user's alerts, sorted by `created_at DESC`, limit 50. Accepts `init_data` for auth.

**New response model for matches** (add to `backend/schemas.py`):
```python
class MatchHistoryResponse(BaseModel):
    id: int
    alert_id: Optional[int]
    alert_query_text: Optional[str] = None
    match_tier: str
    match_score: float
    item_title: Optional[str] = None
    item_price: Optional[float] = None
    item_image_path: Optional[str] = None
    item_id: int
    created_at: datetime

    class Config:
        from_attributes = True
```

---

## Step-by-Step Execution

### PHASE 1 — Backend Endpoints

1. **Add `OwnerChannelResponse` schema to `backend/schemas.py`.** Define the new Pydantic model with fields: `id`, `username`, `title`, `trust_score`, `review_count`, `is_verified`, `product_count`, `is_active`. Use `from_attributes = True`.

2. **Add `GET /channels/mine` to `backend/api/routes/channels.py`.**
   - Create an `auth_user_from_init_data` helper function inside channels.py (or reuse the pattern from alerts.py lines 16-74). The function parses `init_data` query parameter, extracts `telegram_id`, looks up or auto-creates `User`, and returns the user object. If init_data is missing or invalid, raise 403.
   - Add the route handler: accepts `init_data` as required query param. Authenticates user. Queries `Channel` where `registered_by == user.telegram_id`. For each channel, counts products via `SELECT COUNT(*) FROM items WHERE channel_id = channel.id`. Returns list of `OwnerChannelResponse`.
   - If user has no channels, return empty list (HTTP 200 with `[]`).

3. **Add `PATCH /alerts/{alert_id}/pause` to `backend/api/routes/alerts.py`.**
   - Accept `init_data` query param for auth. Look up alert by id AND user_id. If not found, raise 404. Toggle `alert.is_active = not alert.is_active`. Commit. Return `{"status": "paused"}` or `{"status": "resumed"}` plus the updated `is_active` value.

4. **Add `GET /alerts/matches` to `backend/api/routes/alerts.py`.**
   - Accept `init_data` query param for auth. Look up user. Query `Notification` joined with `Alert` and `Item` where `Notification.user_id == user.id`, ordered by `created_at DESC`, limit 50. Return list of `MatchHistoryResponse` with fields: id, alert_id, alert_query_text (from Alert.query_text), match_tier, match_score, item_title (from Item.title), item_price, item_image_path, item_id, created_at.

5. **Add `MatchHistoryResponse` schema to `backend/schemas.py`.**

### PHASE 2 — Frontend Hooks

6. **Create `frontend/src/hooks/useAlerts.js`.**
   - Follow the module-level cache pattern from `useShop.js` (lines 6-7): `let _alertsCache = null; let _matchesCache = null;`.
   - Initialize state from cache if available, otherwise empty arrays.
   - Implement `fetchAlerts()`: calls `GET /alerts/` with initData from `window.Telegram?.WebApp?.initData`. On success, updates `_alertsCache` and state. On failure, sets error.
   - Implement `fetchMatchHistory()`: calls `GET /alerts/matches` (new endpoint). Same cache pattern.
   - Implement `pauseAlert(id)`: calls `PATCH /alerts/{id}/pause`. On success, toggles `is_active` locally and updates cache.
   - Implement `deleteAlert(id)`: calls `DELETE /alerts/{id}`. On success, removes from local array and updates cache.
   - Return all state and functions.
   - The hook does NOT auto-fetch on mount. Fetching is triggered by the AlertsPage when it becomes visible for the first time (lazy loading).

7. **Create `frontend/src/hooks/useOwnerChannels.js`.**
   - Module-level cache: `let _channelsCache = null;`.
   - Initialize state from cache or empty array.
   - Implement `fetchChannels()`: calls `GET /channels/mine` with initData. Updates cache and state.
   - Return state and fetch function. No auto-fetch on mount (lazy loading).
   - Handle the case where there is no initData (user not in Telegram): set a distinct error `"NOT_IN_TELEGRAM"` so the UI can show the "Open in Telegram" prompt.

### PHASE 3 — Bottom Navigation Component

8. **Rewrite `frontend/src/components/BottomNav.jsx`.**
   - Replace the existing Home/Visual/Saved/Profile tabs with three tabs:
     - `explore`: `Compass` icon from lucide-react, label "Explore"
     - `alerts`: `Bell` icon from lucide-react, label "Alerts"
     - `stores`: `Store` icon from lucide-react, label "Stores"
   - Active tab: filled icon style (use `strokeWidth={2.5}` or use filled variants), brand-amber color (`text-brand-600`), bold label.
   - Inactive tabs: outline icons, `text-gray-400`, regular weight label.
   - Visual active indicator: a subtle 2px rounded bar at top of active tab button.
   - Styling: fixed to bottom of viewport (`fixed bottom-0 left-0 right-0`), white background with top border, safe-area padding for mobile (`pb-safe` or `pb-[env(safe-area-inset-bottom)]`), z-40.
   - Accept props: `activeTab: string`, `setActiveTab: (tab: string) => void`.

### PHASE 4 — Page Components

9. **Create `frontend/src/pages/AlertsPage.jsx`.**
   - Initialize the `useAlerts` hook.
   - On first render, if `!hasBeenFetched`, call `fetchAlerts()` and `fetchMatchHistory()`.
   - Layout:
     - **Header row:** "My Alerts" title + "+" button (opens `AlertModal` for creating new alerts).
     - **Active alerts section:** List each alert as a card showing query text, max price, smart filter toggles (from `preferences` JSON), match count, "Pause"/"Resume" button, "Delete" button.
     - **Match history section:** "Recent Matches" heading, list of match cards showing product title, price, match tier badge (bullseye = green, ring = amber), tap to navigate to `/item/{item_id}`.
     - **Empty state:** If no alerts, show "You don't have any alerts yet" with a "Create Your First Alert" button that opens the AlertModal.
   - Loading state: centered spinner.
   - Error state: "Could not load alerts" with retry button.
   - Use `useNavigate` to navigate to product detail pages from match history.
   - The "+" button opens the existing `AlertModal` component. When the modal closes with success, refresh the alerts list.

10. **Create `frontend/src/pages/StoresPage.jsx`.**
    - Initialize the `useOwnerChannels` hook.
    - On first render, if `!hasBeenFetched`, call `fetchChannels()`.
    - **Owner view** (if `channels.length > 0`):
      - Header: "My Stores" title.
      - Channel cards list: each card shows:
        - Channel @username and title
        - Status badge (Active = green, Paused = amber)
        - Product count: "{count} products indexed"
        - View count and click-through count (use placeholder "—" for now)
        - Action buttons: "Pause"/"Resume" toggle, "Remove" button
      - Bottom card: "Want to list another channel?" with link/button to add channel instructions.
    - **Non-owner view** (if `channels.length === 0`):
      - Friendly prompt: "Add your Telegram channel to appear here. Get your products indexed and reach thousands of buyers."
      - A "How to Add" button that expands inline instructions for adding the bot as admin.
    - **Not in Telegram** (if error is "NOT_IN_TELEGRAM"):
      - "Open in Telegram to manage your stores."
    - Loading state: centered spinner.
    - Error state: "Could not load stores" with retry button.

11. **Modify `frontend/src/pages/Home.jsx`.**
    - Accept new optional prop `embedded` (boolean, default false).
    - When `embedded` is true (rendered inside tab layout):
      - Remove `min-h-screen` from the root div (replace with `h-full` or just remove the height constraint).
      - Remove `bg-gray-50` from the root div (the layout provides the background).
    - When `embedded` is false (standalone, backward compatible): keep current behavior.
    - All other logic (useShop, NavBar, SearchFilters, CategoryBar, ProductGrid) unchanged.

### PHASE 5 — App.jsx Restructuring

12. **Refactor `frontend/src/App.jsx` for persistent tab layout with state preservation.**

    The new architecture:
    ```
    <Router>
      <Routes>
        <Route path="/*" element={<MainLayout />} />
      </Routes>
    </Router>
    ```

    `MainLayout` is a component that:
    - Uses `useState` for `activeTab` (default `'explore'`).
    - Uses `useLocation` to determine if current path is a product page (`pathname.startsWith('/item/')`).
    - Renders ALL THREE tab content panels using `display: none` for inactive ones (so they NEVER unmount, preserving scroll and search state).
    - Renders nested `<Routes>` for the product page route.
    - Renders `<BottomNav>` conditionally (hidden when on product page).

    **Detailed MainLayout structure:**

    ```
    function MainLayout() {
      const location = useLocation();
      const [activeTab, setActiveTab] = useState('explore');
      const isProductPage = location.pathname.startsWith('/item/');

      return (
        <div className="min-h-screen bg-gray-50 font-sans flex flex-col">
          {/* Main content area — flex-grow to push bottom nav down */}
          <div className="flex-1">
            {/* Explore Tab — always mounted, shown when active and not on product page */}
            <div style={{ display: (!isProductPage && activeTab === 'explore') ? 'block' : 'none' }}>
              <Home embedded={true} />
            </div>

            {/* Alerts Tab — always mounted */}
            <div style={{ display: (!isProductPage && activeTab === 'alerts') ? 'block' : 'none' }}>
              <AlertsPage />
            </div>

            {/* Stores Tab — always mounted */}
            <div style={{ display: (!isProductPage && activeTab === 'stores') ? 'block' : 'none' }}>
              <StoresPage />
            </div>

            {/* Product Page Route */}
            <Routes>
              <Route path="/item/:id" element={<ProductPage />} />
            </Routes>
          </div>

          {/* Bottom Nav — hidden on product page */}
          {!isProductPage && (
            <BottomNav activeTab={activeTab} setActiveTab={setActiveTab} />
          )}
        </div>
      );
    }
    ```

    **Key behaviors:**
    - Tab-to-tab switching: instant, no data loss, scroll preserved (components stay in DOM).
    - Navigate to product page: BottomNav hides, tab content hides, ProductPage renders. Tab state remains in memory.
    - Navigate back from product page: BottomNav reappears, previous tab shown, all content intact. The `useNavigate` calls in Home.jsx and ProductPage.jsx already use `navigate('/')` which returns to the root path, where MainLayout restores the hidden tabs.
    - Deep link to `/item/:id`: BottomNav hidden, tabs hidden, works as expected.

    **Landing page gate preserved:**
    The `isTelegramWebView` check at the top of `App` component remains. If not in Telegram, render `<LandingPage />`. If in Telegram, render the Router with MainLayout.

### PHASE 6 — Integration and Polish

13. **Wire up navigation from match history.** In AlertsPage, each match history card is clickable and navigates to `/item/{item_id}`. This hides the bottom nav and shows ProductPage. On back, the Alerts tab restores.

14. **Wire up navigation from product page back button.** The existing `navigate('/')` in ProductPage's NavBar `onBack` handler already returns to root. Ensure the previous active tab is restored (it will be, because `activeTab` state is preserved in MainLayout).

15. **Ensure the "Alert Me" button on ProductPage still works.** The existing `AlertModal` component on ProductPage is unchanged. It calls `POST /alerts/` directly. After creating an alert from the product page, the user can later see it on the Alerts tab.

16. **Handle edge case: user not in Telegram.** The useAlerts and useOwnerChannels hooks should detect when `window.Telegram?.WebApp?.initData` is unavailable and set an appropriate error message. AlertsPage and StoresPage show "Open in Telegram to use this feature" messages in this case.

---

## Testing Requirements

### Backend Tests

1. **Test `GET /channels/mine` — owner with channels:**
   - Create a user (telegram_id = 12345).
   - Create 2 channels with `registered_by = 12345`.
   - Create several items for each channel.
   - Call endpoint with `?init_data=<user auth data>`.
   - Assert: response is list of 2 channels, each with correct `product_count`.

2. **Test `GET /channels/mine` — non-owner:**
   - Create a user with no channels.
   - Call endpoint.
   - Assert: HTTP 200 with empty list `[]`.

3. **Test `GET /channels/mine` — unauthenticated:**
   - Call without valid init_data.
   - Assert: HTTP 403.

4. **Test `PATCH /alerts/{id}/pause`:**
   - Create an alert (is_active = True).
   - Call pause endpoint.
   - Assert: is_active becomes False.
   - Call again.
   - Assert: is_active becomes True (toggle).

5. **Test `GET /alerts/matches`:**
   - Create user, alert, notification records.
   - Call endpoint.
   - Assert: returns notifications with correct fields (alert_query_text, item_title, match_tier, etc.).

### Frontend Tests

6. **BottomNav component:**
   - Renders three tabs: Explore, Alerts, Stores.
   - Clicking a tab fires `setActiveTab` with correct id.
   - Active tab has brand-amber styling, inactive tabs are gray.
   - Renders at bottom of viewport with safe-area padding.

7. **AlertsPage component:**
   - Shows loading spinner on first load.
   - Displays alert cards with query text, price, pause/delete buttons.
   - Displays match history section below alerts.
   - Empty state renders with "Create Your First Alert" button.
   - Error state shows retry button.
   - "+" button opens AlertModal.
   - Pause button toggles alert state and updates UI.

8. **StoresPage component:**
   - Shows loading spinner on first load.
   - Owner view: displays channel cards with @username, product count, status badge.
   - Non-owner view: displays educational prompt with "How to Add" button.
   - Error state shows retry button.

9. **App.jsx tab routing:**
   - Default active tab is Explore (Home page renders).
   - Switching to Alerts tab shows AlertsPage.
   - Switching to Stores tab shows StoresPage.
   - BottomNav hidden on `/item/:id` route.
   - BottomNav reappears when navigating back to `/`.
   - Previous active tab is preserved after returning from product page.
   - Tab content is lazy-loaded (fetch only on first activation).

10. **State preservation:**
    - Enter a search query on Explore tab, switch to Alerts, switch back to Explore — search query still visible.
    - Scroll down on Explore tab, switch tabs, switch back — scroll position preserved.
    - Navigate to product page, navigate back — previous tab is active and content is restored (cache-based for data).

---

## Sequence & Dependencies

| Step | Can Be Parallelized |
|------|--------------------|
| Phase 1 (Backend endpoints) | Can run in parallel with Phase 2 stubs |
| Phase 2 (Frontend hooks) | Depends on Phase 1 endpoint signatures being defined |
| Phase 3 (BottomNav) | Independent — can run anytime |
| Phase 4 (Page components) | Depends on Phase 2 hooks |
| Phase 5 (App.jsx) | Depends on Phase 3 + Phase 4 |
| Phase 6 (Integration) | Depends on Phase 5 |

**Recommended order:** Phase 1 → Phase 2 + Phase 3 (parallel) → Phase 4 → Phase 5 → Phase 6
