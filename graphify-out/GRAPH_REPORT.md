# Graph Report - index_gebeya  (2026-07-31)

## Corpus Check
- 160 files · ~128,624 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1645 nodes · 2590 edges · 120 communities (118 shown, 2 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 372 edges (avg confidence: 0.55)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7f5b1322`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 109|Community 109]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 112|Community 112]]
- [[_COMMUNITY_Community 113|Community 113]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 115|Community 115]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]
- [[_COMMUNITY_Community 118|Community 118]]
- [[_COMMUNITY_Community 119|Community 119]]

## God Nodes (most connected - your core abstractions)
1. `Item` - 41 edges
2. `Channel` - 40 edges
3. `User` - 39 edges
4. `Notification` - 31 edges
5. `Alert` - 30 edges
6. `authenticate()` - 24 edges
7. `ItemResponse` - 21 edges
8. `Session` - 20 edges
9. `_make_user()` - 20 edges
10. `Session` - 19 edges

## Surprising Connections (you probably didn't know these)
- `Request` --uses--> `ItemResponse`  [INFERRED]
  backend/api/routes/feed.py → backend/schemas.py
- `Session` --uses--> `ItemResponse`  [INFERRED]
  backend/api/routes/feed.py → backend/schemas.py
- `Session` --uses--> `User`  [INFERRED]
  backend/services/auth.py → backend/models.py
- `Any` --uses--> `UserInteraction`  [INFERRED]
  backend/services/analytics.py → backend/models.py
- `Session` --uses--> `Channel`  [INFERRED]
  backend/services/owner_dm.py → backend/models.py

## Import Cycles
- None detected.

## Communities (120 total, 2 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.23
Nodes (26): AuthenticationBackend, AdminAuth, AlertAdmin, ChannelAdmin, ItemAdmin, ItemImageAdmin, NotificationAdmin, Request (+18 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (66): BackgroundTasks, Request, Session, BackgroundTasks, Request, Session, TestItem, AlertNotification (+58 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (51): api_get(), api_patch(), api_post(), _count_item_edits(), _count_sold_reports(), _create_channel_with_bulk_items(), _create_owned_item(), _create_test_item() (+43 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (49): Synchronous LLM Judge with 3-Scenario Logic.     Decides which persona to adopt, verify_match_with_llm(), vectorize_text(), _normalize(), process_new_item(), Local helper for strict identity checks.     Removes all non-alphanumeric chars, THE ORCHESTRATOR (Synchronous 3-Stage Pipeline), api_delete() (+41 more)

### Community 4 - "Community 4"
Cohesion: 0.14
Nodes (32): BackgroundTasks, Request, Session, ItemEdit, TECH-22: Crowdsourced sold-reporting — one report per user per item., TECH-23: Edit history audit log for inventory management., SoldReport, ItemStatusResponse (+24 more)

### Community 5 - "Community 5"
Cohesion: 0.20
Nodes (8): get_channel_info(), Fetch channel metadata from the backend API.     Returns a dict with keys: id, r, Sends payload to Backend API (Ingestion). Returns dict with success, item_id, ti, send_to_api(), post_init(), background_worker(), Queue, Serial Worker with Fixed Heartbeat + Processing DM Lifecycle (TECH-19).     - Pr

### Community 6 - "Community 6"
Cohesion: 0.05
Nodes (37): dependencies, axios, lucide-react, react, react-dom, react-router-dom, @tailwindcss/postcss, devDependencies (+29 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (32): Exception, channel_photo_refresher(), Bot, Daily background task that fetches current channel profile photos from Telegram, _make_failing_mock_client(), _make_mock_client(), _MockBot, MockChat (+24 more)

### Community 8 - "Community 8"
Cohesion: 0.10
Nodes (33): api_get(), api_patch(), api_post(), Backend tests for TECH-07: Channel and User Profile Photos — Channel Photo Tests, T2: Ingest a second post from the same channel.     Verify the item is still cre, T3: Test with a channel that has no profile photo in Telegram.     Verify that t, T4: The photo fetch in ingestion is wrapped in try/except.     Verify that even, T5: Call GET /channels/{channel_id}/photo for a channel     that has a valid pho (+25 more)

### Community 9 - "Community 9"
Cohesion: 0.13
Nodes (33): api_get(), api_post(), _create_test_item(), _make_init_data(), Backend tests for TECH-22: Sold Reports + Product Status + Cleanup These tests h, T2: Report same item twice, verify 409 status., T3: Create channel with registered_by, report with same user, verify 403., T4: Report item 3 times (different users), verify status becomes reported_sold. (+25 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (20): extract_multimodal(), Uses Google Gemini for requests requiring vision capabilities or as backup., extract_text_only(), Uses Groq Llama 3.1 8B for fast, high-volume text extraction.     Supports 'Visu, TrafficCop, extract_product_info(), Hybrid Router:     1. Default: Sends to Groq (Fastest).        - Injects 'visual, get_image_model() (+12 more)

### Community 11 - "Community 11"
Cohesion: 0.06
Nodes (31): 1. `backend/constants.py` — NEW FILE, 2. `backend/models.py` — ALERT MODEL EXTENSION, 3. `backend/services/alerting.py` — IMPORT ADDITIONS, 3a. Max alerts per user check in `create_alert`, 3b. Replace hardcoded alert lifespan in `create_alert`, 3c. Replace hardcoded ring tolerance in `process_new_item`, 3d. Notification throttle for Ring matches, 3e. Duplicate suppression in `_dispatch_notification` (or before calling it) (+23 more)

### Community 12 - "Community 12"
Cohesion: 0.06
Nodes (30): 10. `frontend/src/components/ItemCard.jsx` — Status badges, 11. `backend/tests/test_tech22.py` — NEW FILE, 1. `backend/models.py` — New model imports already available, 2. `backend/constants.py` — New constants added inline, 3. `backend/main.py` — Schema migration block, 4. `backend/schemas.py` — New/modified Pydantic models, 5. `backend/api/routes/items.py` — New endpoints + auth helper + filter addition, 6. `backend/services/search.py` — Status filter in search SQL (+22 more)

### Community 13 - "Community 13"
Cohesion: 0.06
Nodes (30): Backend Routes — imports to add, Backend Tests, Files to Create, Files to Modify, Frontend New Files — import sources, Frontend Tests (manual QA checklist), Goal, Modified StoresPage.jsx — new imports (+22 more)

### Community 14 - "Community 14"
Cohesion: 0.10
Nodes (27): api_get(), Backend tests for TECH-03 Infinite Scroll / Waterfall Recommendation These tests, T4: Explorer state (3-10 interactions) should use 70/30 session/trending at any, T5: Cold Start (<3 interactions) should return trending items only., T6: Anonymous users (no headers) should get trending items at any offset., T7: Anonymous user with offset should still return items or empty., T8: When all available items have been excluded via the exclude parameter,     t, Helper to make HTTP GET requests to the API. (+19 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (26): 2a. Guard — only run dedup if we have a vector, 2b. Query candidate items, 2c. Brute-force comparison loop, 2d. Match branch — update existing item, 2e. No-match branch — log and proceed, Core Functional Tests, Existing imports already available (no change needed), Files to Modify/Create (+18 more)

### Community 16 - "Community 16"
Cohesion: 0.08
Nodes (25): 1. BottomNav.jsx (rewrite), 2. AlertsPage.jsx (new), 3. StoresPage.jsx (new), 4. useAlerts.js (new hook), 5. useOwnerChannels.js (new hook), 6. App.jsx modifications, 7. Home.jsx modifications, 8. Backend: channels.py additions (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.17
Nodes (21): Request, Session, Item, Session, get_personalized_feed(), Generates a personalized 'For You' feed based on the user's     interaction hist, build_feed(), get_discovery_feed() (+13 more)

### Community 18 - "Community 18"
Cohesion: 0.09
Nodes (22): Dependency Order, Existing imports in `main.py` — preserved, Files to Modify, Functions moved, Goal, New imports into `backend/database.py`, New imports into `backend/main.py`, Notes for @build (+14 more)

### Community 19 - "Community 19"
Cohesion: 0.09
Nodes (22): backend/api/routes/channels.py — New Endpoints & Models, backend/models.py — New Columns on `Channel`, backend/schemas.py — New Pydantic Models, Backend Tests (add to `backend/tests/test_channels.py` or create `backend/tests/test_tech19.py`), Files to Modify, frontend/src/hooks/useOwnerChannels.js — Extend Hook, frontend/src/pages/StoresPage.jsx — Modal & API Wiring, Frontend Tests (+14 more)

### Community 20 - "Community 20"
Cohesion: 0.09
Nodes (22): AlertsPage.jsx tests:, Files to Modify, Goal, ingestion.py tests:, New/modified imports (no new packages needed):, Schema migration test:, Step 1 — Add `is_active` to Item model (`backend/models.py`), Step 2 — Add schema migration (`backend/main.py`) (+14 more)

### Community 21 - "Community 21"
Cohesion: 0.15
Nodes (22): api_get(), api_post(), get_test_channel_id(), make_valid_init_data(), Backend tests for TECH-07: User Photo Capture During Review Submission These tes, Generate a unique Telegram user ID for test isolation., T14: Submit a review with initData that includes user.photo_url.     Verify the, T15: Submit a review with initData that does NOT include user.photo_url.     Ver (+14 more)

### Community 22 - "Community 22"
Cohesion: 0.19
Nodes (22): api_delete(), api_get(), api_patch(), api_post(), Backend tests for TECH-19: Processing DMs, Pause/Resume, Remove with Auto-Leave., Query a non-existent username → should return 404., Create a channel owned by a user, then pause it via PATCH.     Verify indexing_p, Pause a channel, then resume it. Verify indexing_paused becomes False. (+14 more)

### Community 23 - "Community 23"
Cohesion: 0.09
Nodes (21): 1. What Is This System?, 2.1 Channel (Seller), 2.2 Item (Product), 2.3 User (Buyer), 2.4 Alert (Saved Search), 2.5 Notification (Alert Dispatch), 2.6 Review (Seller Rating), 2.7 User Interaction (Analytics Event) (+13 more)

### Community 24 - "Community 24"
Cohesion: 0.09
Nodes (21): 1. `backend/models.py` — new column, 2. `backend/schemas.py` — new schema, 3. `backend/api/routes/channels.py` — new endpoint, 4. `listener/client.py` — new function, 5. `listener/bot_commands.py` — new command handler, 6. `listener/chat_member_handler.py` — new file, 7. `listener/main.py` — register handlers, Automated Test (if feasible) (+13 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (20): cancel(), _finalize_alert(), finish_filters(), DEFAULT_TYPE, Update, User clicks 'Any Price, Entry point: User types /alert, Saves the alert to the backend (+12 more)

### Community 26 - "Community 26"
Cohesion: 0.10
Nodes (20): Backend — No new imports needed; all types already available., Backend Tests (to be written by @build), Files to Modify, Frontend, Frontend Tests (to be written by @build), Implementation Blueprint: TECH-03 + TECH-04 (Infinite Scroll), Step 1: Add query parameters to the feed endpoint, Step 2: Extend build_feed signature and parse exclude IDs (+12 more)

### Community 27 - "Community 27"
Cohesion: 0.16
Nodes (20): api_delete(), api_get(), api_patch(), api_post(), Backend tests for TECH-17: Bottom Navbar + Stores Dashboard + Alert Management., A user with no channels should get HTTP 200 with empty list., Calling without valid init_data should return 403., Create an alert, pause it (is_active becomes False), pause again     (is_active (+12 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (18): 1. LandingPage.jsx — New Imports, 2. App.jsx — New Imports & Local State, 3. Backend — New Route & Registration, 4. TAXONOMY — Already Exists (No Changes), 5. No New Backend Schemas Required, Backend Tests, Files to Modify/Create, Frontend Tests (+10 more)

### Community 29 - "Community 29"
Cohesion: 0.20
Nodes (7): CategorySheet(), ProductEditPanel(), SearchFilters(), TAXONOMY, NavBar(), useShop(), Home()

### Community 30 - "Community 30"
Cohesion: 0.11
Nodes (17): 1. Hero Section — The First Impression, 2. How It Works — Three Steps, 3. Live Stats Bar, 4. Category Showcase, 5. FAQ — Answer the Silent Questions, 6. Footer, Content Structure, Creative Direction & Constraints (+9 more)

### Community 31 - "Community 31"
Cohesion: 0.21
Nodes (17): api_post(), Backend tests for TECH-06: Post Deduplication via Vector Matching These tests hi, T2: Ingesting visually distinct images from the same channel     should create s, T3: The same image posted to different channels should create     separate items, Helper to make HTTP POST requests to the API., T4: Text-only posts (no image) produce no visual_vector,     so the dedup block, T5: When a duplicate is matched, a NEW item is created (TECH-21).     The old it, Generate a unique channel name for test isolation. (+9 more)

### Community 32 - "Community 32"
Cohesion: 0.12
Nodes (16): Behavioural Tests (Manual / Interactive), Edge Cases, Files to Modify/Create, Modified File: `frontend/src/hooks/useShop.js`, Modified File: `frontend/src/pages/Home.jsx`, New File: `frontend/src/components/SearchFilters.jsx`, Step 1: Add filter state to `useShop.js`, Step 2: Modify `handleTextSearch` signature and body (+8 more)

### Community 33 - "Community 33"
Cohesion: 0.12
Nodes (15): NB-17: Product Gallery Inconsistency in API Responses (existing, low priority), NB-18: Expired Alerts Are Never Permanently Removed (existing, low priority), NB-19: Missing Product Condition and Location in Frontend Display (existing, low priority), NB-20: LLM Judge "Fail-Open" Does Not Distinguish Between Error Types (existing, low priority), NB-33: Landing Page — Full API Integration (Real Data) [IMPLEMENTED], NB-34: Landing Page as Telegram Mini App Onboarding [IMPLEMENTED], NB-35: Design System — Landing Page UI Adopted Across Webapp [IMPLEMENTED], NB-36: Bottom Navigation Bar — Explore, Alerts, Stores [IMPLEMENTED] (+7 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (15): backend/ai_engine/prompts.py, Backend Tests, Files to Modify, frontend/src/components/CategoryChips.jsx, frontend/src/constants/taxonomy.js, Frontend Tests, Step 1: Replace TAXONOMY_STRUCTURE in `backend/ai_engine/prompts.py`, Step 2: Replace TAXONOMY in `frontend/src/constants/taxonomy.js` (+7 more)

### Community 35 - "Community 35"
Cohesion: 0.12
Nodes (15): Combined Blueprint: TECH-10, TECH-11, TECH-12, TECH-13, Files to Modify, Files with ADDED imports or destructures, Files with NO import changes (internal logic only), Step-by-Step Execution, Strict Import Map, TECH-10, TECH-10 — Feed Caching for Instant Back Navigation (+7 more)

### Community 36 - "Community 36"
Cohesion: 0.14
Nodes (13): 1. Discovery — `/addchannel` Command, 2.1 Added as Admin — With Username (Successful Onboarding), 2.2 Added as Admin — Private Channel/Group (Rejected), 2.3 Added as Regular Member (Not Admin), 2.4 Demoted — Admin to Member, 2.5 Removed — Kicked or Left, 2. Auto-Detection — Status Change Events, 3. State Transitions Are Idempotent (+5 more)

### Community 37 - "Community 37"
Cohesion: 0.21
Nodes (13): api_get(), _get_db_conn(), Backend tests for TECH-16 Stats Endpoint These tests hit the running API at loca, Helper to make HTTP GET requests to the API., T4: Verify the stats endpoint returns consistent counts when queried.     We val, T1: GET /items/stats should return product_count and channel_count., T2: GET /items/stats should return category_counts dict., Create a direct database connection for test data setup/teardown. (+5 more)

### Community 38 - "Community 38"
Cohesion: 0.24
Nodes (13): api_post(), Backend tests for TECH-21: Dedup Redesign (soft-delete + recreate) These tests h, T2: Posting a unique image should create a new item normally     with replaced=F, T3: Even when there are candidates but none match,     the response should have, Helper to make HTTP POST requests to the API., Generate a unique channel name for test isolation., Generate a unique message_id to avoid pk conflicts., T1: Posting a duplicate image should soft-delete the old item     (is_active=Fal (+5 more)

### Community 39 - "Community 39"
Cohesion: 0.17
Nodes (11): 1. Alert Lifecycle, 2. Pre-Check Gates (Before Any Matching), 3. Stage 1 — Speed Pass (Identity Check), 4. Stage 2 — Hybrid Matcher (Candidate Generation), 5. Stage 3 — LLM Judge (Verification), 6. Dispatch Decision, 7. Notification Creation, Alert Matching (+3 more)

### Community 40 - "Community 40"
Cohesion: 0.17
Nodes (11): 1. Buyer Identity Resolution, 2. Buyer Maturity States, 3.1 Trending, 3.2 Session Context, 3.3 Category Discovery, 3. Feed Components, 4. Feed Assembly, Behavioral Rules (+3 more)

### Community 41 - "Community 41"
Cohesion: 0.36
Nodes (6): AlertModal(), useAlerts(), AlertsPage(), generateUUID(), getAnalyticsHeaders(), logEvent()

### Community 42 - "Community 42"
Cohesion: 0.24
Nodes (6): BottomNav(), faqs, LandingPage(), App(), isTelegramWebView(), mockStats

### Community 43 - "Community 43"
Cohesion: 0.18
Nodes (10): 1. Configuration, 2. Max Alerts Per User, 3. Auto-Pause After Matches, 4. Notification Throttle, 5. Duplicate Suppression, 6. Expiry, Alert Guardrails, Behavioral Rules (+2 more)

### Community 44 - "Community 44"
Cohesion: 0.18
Nodes (10): 1.1 Mini App (Web Frontend), 1.2 Bot Commands (/alert, /myalerts), 1.3 Anonymous Browsing, 1. Entry Points & Auth Methods, 2. Alert-Specific Authentication, 3. Frontend Identity Storage, Behavioral Rules, Error Behaviors (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.18
Nodes (10): 1. Tab Structure, 2. Visibility Rules, 3. Tab Switching Behavior, 4. Explore Tab — Feed Entry Point, 5. Alerts Tab — Alert Management, 6. Stores Tab — Channel Management, Behavioral Rules, Bottom Navigation Bar (+2 more)

### Community 46 - "Community 46"
Cohesion: 0.25
Nodes (6): InventoryProductsTab(), ItemCard(), StatusBadge(), ProductGrid(), defaultProps, sampleItems

### Community 47 - "Community 47"
Cohesion: 0.20
Nodes (9): 1. Post Capture, 2. Ingestion Worker, 3. AI Enrichment, 4. Channel Resolution, 5. Post-Ingestion Trigger, Behavioral Rules, Error Behaviors, Overview (+1 more)

### Community 48 - "Community 48"
Cohesion: 0.20
Nodes (9): 1. Channel-to-Inventory Navigation, 2. Products Tab, 3. Product Edit Panel, 4. Settings Tab, 5. Forward-Looking Architecture, Behavioral Rules, Error Behaviors, Inventory Management — Store Owner Product Control (+1 more)

### Community 49 - "Community 49"
Cohesion: 0.20
Nodes (9): 1. Notification Lifecycle, 2. The Poller (Mailman), 3. Delivery Format, 4. Acknowledgment, 5. Buyer Actions on Notification, Behavioral Rules, Error Behaviors, Notification Delivery (+1 more)

### Community 50 - "Community 50"
Cohesion: 0.20
Nodes (9): 1. Single Source of Truth, 2. Taxonomy Structure, 3. The Taxonomy (Locked), 4. AI Classification Behavior, 5. Frontend Behavior, Behavioral Rules, Error Behaviors, Overview (+1 more)

### Community 51 - "Community 51"
Cohesion: 0.20
Nodes (9): UF-1: Search Result Card Enhancements, UF-2: "Other" Subcategory Display in Frontend, UF-3: Userbot Scraping as Alternative Data Source, UF-4: Seller Posting via Bot, UF-5: Telegram Stars for Monetization, UF-6: Monetization Tiers (Seller Dashboard, Targeted Ads, Post Boosting), UF-7: Sort by Price and Date in Search Results, UF-8: Text-Only Items Invisible in Category-Level Searches (+1 more)

### Community 52 - "Community 52"
Cohesion: 0.38
Nodes (6): ChannelInventory(), TAB_REGISTRY, InventorySettingsTab(), useChannelInventory(), useOwnerChannels(), StoresPage()

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (8): 1. Review Submission, 2. Trust Score Calculation, 3. Review Visibility, 4. Review Moderation, Behavioral Rules, Error Behaviors, Overview, Seller Reviews & Trust

### Community 54 - "Community 54"
Cohesion: 0.22
Nodes (8): 1. Text Search, 2. Image Search, 3. Category Browsing, 4. Related Products, Behavioral Rules, Error Behaviors, Overview, Search

### Community 55 - "Community 55"
Cohesion: 0.22
Nodes (8): 1. Item Status Lifecycle, 2. Reporting a Product as Sold, 3. Transparent Owner DMs, 4. Cleanup, Behavioral Rules, Crowdsourced Sold Reports & Product Status, Error Behaviors, Overview

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (8): A. Backend calls Telegram API directly (not proxied through listener), Architectural Decisions, B. Photo serving uses HTTP 307 redirect to Telegram CDN, C. Photo fetch on first ingestion is fire-and-forget (non-blocking), D. Daily refresh runs as an asyncio background task in the listener, Files to Modify/Create, Rollback and Safety Notes, TECH-07: Channel and User Profile Photos — Implementation Blueprint

### Community 57 - "Community 57"
Cohesion: 0.22
Nodes (9): 1. New imports for `backend/api/routes/ingestion.py`, 2. New imports for `backend/api/routes/reviews.py`, 3. New imports for `backend/api/routes/channels.py` (NEW FILE), 4. New imports for `listener/photo_refresher.py` (NEW FILE), 5. New imports for `listener/main.py`, 6. New column additions — `backend/models.py`, 7. New fields in `backend/schemas.py`, 8. No new exports (+1 more)

### Community 58 - "Community 58"
Cohesion: 0.22
Nodes (9): PHASE 1: Database Models (`backend/models.py`), PHASE 5: Capture User Photo During Review Submission (`backend/api/routes/reviews.py`), PHASE 8: Database Migration, Step 12: Extract `photo_url` from initData, Step 13: Store `photo_url` on the Review record, Step 19: Run database migration, Step 1: Add `photo_file_id` to `Channel`, Step 2: Add `user_photo_url` to `Review` (+1 more)

### Community 59 - "Community 59"
Cohesion: 0.25
Nodes (7): 1. Event Capture, 2. Session Management, 3. Privacy & Ad-Blocker Avoidance, Behavioral Rules, Error Behaviors, Overview, User Interaction Tracking (Analytics)

### Community 60 - "Community 60"
Cohesion: 0.25
Nodes (7): 1. Soft-Delete + Recreate, 2. Seller Notification, 3. Cleanup, Behavioral Rules, Error Behaviors, Overview, Post Deduplication — Redesigned

### Community 61 - "Community 61"
Cohesion: 0.25
Nodes (7): 1. Landing Page Content — All Real Data, 2. Onboarding Flow — Telegram First Visit, 3. Design System Adoption, Behavioral Rules, Error Behaviors, Landing Page, Onboarding & Design System, Overview

### Community 62 - "Community 62"
Cohesion: 0.25
Nodes (7): 1. Processing Notification DM, 2. Pause/Resume Indexing, 3. Remove / Auto-Leave, Behavioral Rules, Error Behaviors, Overview, Processing Notifications & Store Management

### Community 63 - "Community 63"
Cohesion: 0.32
Nodes (5): ReviewModal(), ProductPage(), mockItem, mockRelated, mockReviews

### Community 64 - "Community 64"
Cohesion: 0.29
Nodes (7): handle_channel_post(), process_album_flush(), DEFAULT_TYPE, Queue, Update, Called after the buffer delay. Pushes the aggregated album to the Worker Queue., Receives Telegram Posts -> Downloads Media -> Buffers -> Pushes to Queue

### Community 65 - "Community 65"
Cohesion: 0.25
Nodes (7): Acceptance Criteria, CategorySheet.jsx — Full-Screen Overlay, Files to Modify, Home.jsx Changes, NavBar Changes, Styling, TECH-14 Blueprint — Full-Screen Category Sheet on Mobile

### Community 66 - "Community 66"
Cohesion: 0.25
Nodes (7): Acceptance Criteria, Files to Modify, Step 1 — Backend: Add user_name to ReviewResponse, Step 2 — Backend: Populate user_name in GET reviews, Step 3 — Frontend: Show username on review cards, Step 4 — Frontend: Add channel name to ItemCard, TECH-15 Blueprint — Show Usernames on Reviews + Channel Names on Item Cards

### Community 67 - "Community 67"
Cohesion: 0.25
Nodes (7): 1. Price filter not working, 2. "Ask for Price" on item cards, 3. "Ignore products without price" toggle in search, 4. Stores "Add Channel" button → triggers /addchannel, 5. Bot /start command — more informative, 6. Bot commands menu, TECH-18 — Price UX, Bot Commands, Item Card Fallback

### Community 68 - "Community 68"
Cohesion: 0.08
Nodes (33): Session, TECH-22: Daily background cleanup service.  Scheduled via threading.Timer in mai, Wrapper: runs cleanup and logs results., Execute all three cleanup phases synchronously.     Returns a summary dict with, run_cleanup_and_log(), run_daily_cleanup(), Owner DM delivery — notify a channel owner via the Telegram Bot API.  One domain, Send a DM to the channel owner via Telegram Bot API.     Best-effort: logs warni (+25 more)

### Community 69 - "Community 69"
Cohesion: 0.25
Nodes (6): mockAlerts, mockDeleteAlert, mockFetchAlerts, mockFetchMatchHistory, mockMatchHistory, mockPauseAlert

### Community 70 - "Community 70"
Cohesion: 0.29
Nodes (6): How to Use These Documents, Index Gebeya — Documentation, Related Documents, Structure, The Gap Ledger, What These Documents Are

### Community 71 - "Community 71"
Cohesion: 0.38
Nodes (6): handle_addchannel_callback(), handle_start(), DEFAULT_TYPE, Update, Responds to /start with a button to open the Mini App.     Supports deep link pa, Handles the inline button callback for /addchannel.     TECH-18: Added for the w

### Community 72 - "Community 72"
Cohesion: 0.33
Nodes (6): Channel Photo Tests, Daily Refresh Tests, Frontend Tests, Photo Serving Endpoint Tests, Testing Requirements, User Photo Tests

### Community 73 - "Community 73"
Cohesion: 0.33
Nodes (6): PHASE 4: New Channels Route (`backend/api/routes/channels.py` — CREATE), Step 10: Add `GET /channels/{channel_id}/photo` — Serve channel photo, Step 11: Register the channels router in `backend/main.py`, Step 7: Create the file with imports, Step 8: Add `GET /channels/` — List active channels, Step 9: Add `PATCH /channels/{channel_id}` — Update channel

### Community 74 - "Community 74"
Cohesion: 0.40
Nodes (5): api_post(), Backend tests for TECH-18: Price UX, Bot Commands, Item Card Fallback These test, Helper for POST requests to the API., T1: When exclude_unpriced=True, all returned items must have price > 0., test_search_exclude_unpriced_returns_only_priced_items()

### Community 75 - "Community 75"
Cohesion: 0.40
Nodes (3): CATEGORIES, FAQS, SAMPLE_PRODUCTS

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (3): _get_config(), Shared configuration constants for the Alert Guardrails system (TECH-20).  All v, Read an environment variable, parse it, and apply guardrail rules:     - None/mi

### Community 78 - "Community 78"
Cohesion: 0.50
Nodes (3): Expanding the ESLint configuration, React Compiler, React + Vite

### Community 79 - "Community 79"
Cohesion: 0.50
Nodes (4): PHASE 6: Listener Daily Photo Refresh, Step 14: Add config setting (`listener/config.py`), Step 15: Create `listener/photo_refresher.py` (NEW FILE), Step 16: Register the refresher in `listener/main.py`

### Community 80 - "Community 80"
Cohesion: 0.67
Nodes (3): PHASE 2: Schema Updates (`backend/schemas.py`), Step 3: Add `photo_file_id` to `ChannelResponse`, Step 4: Add `user_photo_url` to `ReviewResponse`

### Community 81 - "Community 81"
Cohesion: 0.67
Nodes (3): PHASE 3: Channel Photo Fetch on First Ingestion (`backend/api/routes/ingestion.py`), Step 5: Add `import httpx` and `import os`, Step 6: Fetch channel photo after channel resolution

### Community 82 - "Community 82"
Cohesion: 0.67
Nodes (3): PHASE 7: Frontend Changes, Step 17: Display channel photo on ProductPage (`frontend/src/pages/ProductPage.jsx`), Step 18: Display user photo on review cards (`frontend/src/pages/ProductPage.jsx`)

### Community 105 - "Community 105"
Cohesion: 0.14
Nodes (39): _edit_count(), _make_channel(), _make_item(), _make_user(), _patch_process_new_item(), Unit tests for services/item_status.py — item status-transition business rules., Second report by the same user is rejected with 409., The channel owner reporting their own item gets 403. (+31 more)

### Community 106 - "Community 106"
Cohesion: 0.10
Nodes (26): HMAC-SHA256 cryptographic verification of Mini App initData (reviews).      Rais, verify_init_data(), _make_crypto_init_data(), _make_init_data(), Unit tests for services/auth.py — the merged Telegram identity module.  Covers t, Malformed user JSON falls back to the generic failure message., Correct HMAC-SHA256 signature passes and returns the parsed user dict., Tampered hash is rejected with the exact 401 message. (+18 more)

### Community 107 - "Community 107"
Cohesion: 0.19
Nodes (18): BackgroundTasks, Session, Alert, Notification, Buyer Alert System - Updated for Unified Alert Engine, The Mailbox: Stores pending alerts for the Listener to pick up, IngestionResponse, TelegramPost (+10 more)

### Community 108 - "Community 108"
Cohesion: 0.28
Nodes (15): AlertCreate, BackgroundTasks, Request, Session, AlertCreate, AlertResponse, MatchHistoryResponse, create_new_alert() (+7 more)

### Community 109 - "Community 109"
Cohesion: 0.21
Nodes (14): Item, Session, User, clear_reports(), mark_sold(), Item status-transition business rules — the single home for lifecycle logic that, Owner-only. Set status to 'sold'., Owner-only. Delete SoldReports without changing status. (+6 more)

### Community 110 - "Community 110"
Cohesion: 0.14
Nodes (13): 1. Architecture Context, 2. The New Interfaces, 3. Strict Import Map, 4. Execution Steps, A. `backend/services/auth.py`, Architecture Deepening Blueprint — Identity, Owner DMs, Item Status, B. `backend/services/owner_dm.py`, C. `backend/services/item_status.py` (+5 more)

### Community 111 - "Community 111"
Cohesion: 0.23
Nodes (9): cosine_similarity(), evaluate_match(), MatchResult, MatchTier, normalize_string(), Removes spaces, punctuation, and casing for 'Speed Pass' matching., Cascading Logic:     1. Price Check (Hard Filter)     2. Speed Pass (Determinist, debug_matches() (+1 more)

### Community 112 - "Community 112"
Cohesion: 0.33
Nodes (8): handle_addchannel(), handle_alert_callback(), handle_my_alerts(), DEFAULT_TYPE, Update, Handles 'stop_123' callbacks from /myalerts OR notifications., Lists the user's active alerts with Delete buttons., Instructs a channel/group owner on how to add the bot as admin.

### Community 113 - "Community 113"
Cohesion: 0.32
Nodes (7): Item, Session, User, check_alerts(), notify_user(), Stub for Telegram Notification., Sync Alert Matcher (Alpha Version).

### Community 114 - "Community 114"
Cohesion: 0.25
Nodes (6): User, create_review(), get_reviews(), Securely posts a review and updates the Channel's Trust Score., Fetch recent reviews for a specific channel, Telegram identity verification — the single seam for resolving a Telegram identi

### Community 115 - "Community 115"
Cohesion: 0.25
Nodes (7): create_alert_api(), delete_alert_api(), get_active_alerts(), get_pending_notifications(), Sends Alert Data to Backend API., Fetches active alerts for a user., Fetches pending notifications from the Backend.

### Community 116 - "Community 116"
Cohesion: 0.32
Nodes (7): ack_notification(), Marks a notification as SENT in the Backend., notification_poller(), Bot, Sends a direct message to a user. Uses send_photo if image_url is provided,, Background Task: Checks for pending notifications and delivers them.     Runs ev, send_alert_dm()

### Community 117 - "Community 117"
Cohesion: 0.29
Nodes (6): handle_chat_member(), DEFAULT_TYPE, Update, Handles my_chat_member status changes for bot onboarding into channels/groups., Registers or updates a channel with the backend (owner onboarding)., upsert_channel_api()

### Community 118 - "Community 118"
Cohesion: 0.40
Nodes (5): Session, acknowledge_notification(), get_pending_notifications(), Called by Listener (Poller) to get undelivered alerts., Called by Listener after successful DM delivery.

### Community 119 - "Community 119"
Cohesion: 0.33
Nodes (5): db_session(), Shared fixtures for backend unit tests (test_auth, test_owner_dm, test_item_stat, Create all tables in the isolated test DB once per session., Fresh, empty session for each test (all tables truncated)., _test_db_schema()

## Knowledge Gaps
- **558 isolated node(s):** `Request`, `BackgroundTasks`, `LogRecord`, `Config`, `Any` (+553 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Channel` connect `Community 0` to `Community 1`, `Community 3`, `Community 4`, `Community 68`, `Community 105`, `Community 107`, `Community 109`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Why does `_make_channel()` connect `Community 105` to `Community 0`?**
  _High betweenness centrality (0.012) - this node is a cross-community bridge._
- **Why does `authenticate()` connect `Community 4` to `Community 1`, `Community 114`, `Community 108`, `Community 106`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **Are the 39 inferred relationships involving `Item` (e.g. with `AlertCreate` and `AdminAuth`) actually correct?**
  _`Item` has 39 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `Channel` (e.g. with `AdminAuth` and `AlertAdmin`) actually correct?**
  _`Channel` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `User` (e.g. with `AlertCreate` and `AdminAuth`) actually correct?**
  _`User` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `Notification` (e.g. with `AlertCreate` and `AdminAuth`) actually correct?**
  _`Notification` has 28 INFERRED edges - model-reasoned connections that need verification._