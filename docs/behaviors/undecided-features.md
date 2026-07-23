# Undecided Features — Parking Lot

> **Purpose:** Ideas that have been discussed but not yet locked into the gap ledger. These need further exploration before becoming actionable tickets.

---

## UF-1: Search Result Card Enhancements

**Source:** Vision session — "Description should be visible as in the original under the extracted specification when clicking on an item"

**Current State:** ItemCards in search results and feed show image, price, and title only. The product detail page shows full description, specs, and seller note.

**Open Questions:**
- Should the AI-generated description (2-3 sentence summary) appear on each card in grid view, or a shorter one-line excerpt?
- Should a "Call Seller" button appear directly on search result cards, or only on the detail page?
- Should each card show a visual indicator of whether it matched via image similarity vs text similarity (using `relevance_score` from the API)?

**Dependencies:** Search must be functional first (see NB-23).

---

## UF-2: "Other" Subcategory Display in Frontend

**Source:** Vision session — "i'm not sure if all the subcategories are listed in the front end, and if the AI is 100 percent surely only able to classify the products into those subcategories"

**Current State:** The frontend taxonomy in `constants/taxonomy.js` mirrors the backend taxonomy in `prompts.py`. The "Other" subcategory logic treats items whose subcategory isn't in the known list as belonging to "Other." But it's unclear if the frontend consistently shows the "Other" filter chip.

**Open Questions:**
- Are all subcategories from the backend taxonomy present in the frontend?
- Does the AI ever classify outside the taxonomy (despite strict prompting)?
- Should we audit the frontend taxonomy against the backend to ensure 100% parity?

---

## UF-3: Userbot Scraping as Alternative Data Source

**Source:** Vision session — "Userbot scraping instead aside from the listerbot to get data. Because initially there won't be that many channels who will be willing to make the bot an admin."

**Current State:** The listener bot captures posts from channels where it is an admin. This limits data acquisition to willing channel owners.

**Open Questions:**
- Is userbot scraping (using a regular Telegram account, not a bot) feasible? Telegram's ToS may prohibit this.
- What's the fallback if userbots are banned? The listener bot remains the primary method.
- Should this be a separate service or an alternative mode of the existing listener?

---

## UF-4: Seller Posting via Bot

**Source:** Vision session — "Functionality to post to a channel using the bot for sellers"

**Current State:** Sellers post directly to their Telegram channels. The bot passively monitors and ingests. There is no direct posting interface.

**Open Questions:**
- Would sellers use a bot interface to post, or do they prefer posting natively to their channels?
- If the bot posts on behalf of sellers, we control the format — could enforce structured data, accurate subcategories, and generate product IDs. But this requires seller adoption.
- Does this conflict with the userbot scraping idea, or complement it?

---

## UF-5: Telegram Stars for Monetization

**Source:** Vision session — "Telegram stars for payment needs (like boosting a post)"

**Current State:** No payment integration exists. Telegram Stars is a relatively new payment feature in the Telegram ecosystem.

**Open Questions:**
- What specific actions would cost Stars? Boosting a post? Pinning a category? Accessing seller analytics?
- Is Stars sufficient for all monetization, or do we need traditional payment gateways for larger transactions (e.g., subscription tiers)?
- What's the minimum viable monetization: a single "Boost Post" button that costs X Stars?

---

## UF-6: Monetization Tiers (Seller Dashboard, Targeted Ads, Post Boosting)

**Source:** Vision session — "Seller Intelligence Dashboard," "Targeted Advertising Engine," "Post Boosting & Category Pinning"

**Current State:** None implemented. These are future monetization features.

**Open Questions:**
- Which one ships first? Post Boosting is the simplest (a flag on items + search result priority).
- Seller Dashboard requires data aggregation — how much search/alert data do we need before insights are statistically meaningful?
- Targeted Ads require user segmentation vectors — do we have enough user interaction data yet?

---

## UF-7: Sort by Price and Date in Search Results

**Source:** Vision session — "UI toggles for Sort Order (Low-to-High, High-to-Low)"

**Current State:** The hybrid search ranks results exclusively by relevance score (combined semantic + lexical). The backend has no mechanism to sort by price or date because the SQL query orders by `total_score DESC`. The frontend has no sort UI.

**Open Questions:**
- Should sort options be: "Relevance" (default), "Price: Low to High", "Price: High to Low", "Newest First"?
- Does sorting by price override relevance entirely, or does it re-rank within relevance tiers?
- Should sort be a backend parameter (new SQL logic) or client-side re-sorting of the already-fetched results?
- If backend, does this significantly change the search query structure?
