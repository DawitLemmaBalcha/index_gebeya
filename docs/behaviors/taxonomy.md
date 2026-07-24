# Product Taxonomy

> **Status:** ⚠️ NOT YET IMPLEMENTED

---

## Overview

The product taxonomy defines every category and subcategory the system recognizes. It is enforced at the AI extraction layer and surfaced in the frontend for browsing and filtering. The taxonomy must be identical in both the backend (AI prompts + visual hints) and the frontend (category bar, filters, item cards).

---

## Behavioral Rules

### 1. Single Source of Truth

**Rule 1.1 — Two files, one structure**
The taxonomy is defined in two files that must mirror each other exactly:
- `backend/ai_engine/prompts.py` — `TAXONOMY_STRUCTURE` dict — consumed by AI prompt generation and the visual hints index
- `frontend/src/constants/taxonomy.js` — `TAXONOMY` export — consumed by all frontend components

Any change to one file must be mirrored in the other. They are the same data in two languages (Python dict and JavaScript object).

**Rule 1.2 — No inline copies**
Frontend components must import from `taxonomy.js`. The `CategoryChips.jsx` component currently has its own inline copy of the taxonomy — this is forbidden.

### 2. Taxonomy Structure

**Rule 2.1 — Categories are exclusive**
Every product fits into exactly one main category and one subcategory. The AI must never assign a product to multiple main categories simultaneously.

**Rule 2.2 — Granular main categories**
Main categories are consumer-facing: a buyer browsing for a laptop should see "Laptops & Computers" as a standalone category, not buried under "Electronics." Similarly, "Shoes" is its own category, not a subcategory of Fashion.

**Rule 2.3 — Subcategories are specific**
Each main category has a defined list of subcategories. The AI may only use these subcategories. If a product fits the main category but no specific subcategory, the AI uses "Other" for that main category.

**Rule 2.4 — Fallback to "Other → Uncategorized"**
If a product does not fit any main category, the AI classifies it as "Other → Uncategorized." This is a safety valve, not a target — a high volume of "Uncategorized" products indicates a taxonomy gap that needs a new category.

### 3. The Taxonomy (Locked)

```
Mobile Phones
  → Android Phones, iPhones, Feature Phones, Phone Accessories

Laptops & Computers
  → Laptops, Desktop Computers, Computer Accessories, Printers & Scanners, Networking Products

Tablets
  → Tablets, E-Readers, Tablet Accessories

Electronics
  → TV & DVD Equipment, Audio & Music Equipment, Photo & Video Cameras, Security & Surveillance, Video Game Consoles, Smart Watches, Headphones

Vehicles
  → Cars, Buses & Microbuses, Motorcycles & Scooters, Trucks & Trailers, Heavy Machinery, Vehicle Parts & Accessories, Watercraft & Boats

Property
  → Houses & Apartments for Rent, Houses & Apartments for Sale, Land & Plots for Rent, Land & Plots for Sale, Commercial Property, Short Let

Home, Appliances & Furniture
  → Furniture, Home Appliances, Kitchen Appliances, Kitchenware & Cookware, Home Accessories, Garden Supplies, Cleaning Supplies

Men's Fashion
  → Men's Clothing, Men's Shoes, Watches, Men's Accessories

Women's Fashion
  → Women's Clothing, Women's Shoes, Bags, Jewelry, Women's Accessories

Shoes
  → Sneakers, Formal Shoes, Boots, Sandals, Sports Shoes

Health & Beauty
  → Fragrance, Makeup, Hair Beauty, Skin & Body Care, Tools & Accessories, Vitamins & Supplements, Sexual Wellness

Commercial & Tools
  → Industrial Equipment, Restaurant & Catering, Store Equipment, Medical Equipment, Power Tools, Hand Tools, Stationery

Sports, Arts & Outdoors
  → Sports Equipment, Musical Instruments, Art & Crafts, Camping & Hiking, Team Sports, Gym Equipment

Babies & Kids
  → Baby Gear, Toys, School Supplies, Prams & Strollers

Animals & Pets
  → Dogs, Cats, Birds, Livestock, Pet Supplies

Agriculture & Food
  → Feeds, Supplements & Seeds, Farm Machinery & Equipment, Livestock & Poultry, Foodstuffs

Services
  → Building & Trades, Repair & Construction, Cleaning Services, Logistics Services, Education & Classes, Web & Tech Services, Other Services

Other
  → Mixed, Uncategorized
```

### 4. AI Classification Behavior

**Rule 4.1 — Prompt Injects Full Taxonomy**
The AI extraction prompt is dynamically generated from `TAXONOMY_STRUCTURE`. It includes every main category and its subcategories. The prompt instructs the AI to classify strictly within this structure and never invent categories.

**Rule 4.2 — Visual Hints Guide Classification**
The visual hints index compares product images against pre-computed vectors for every subcategory. The top 3 matching subcategories are included in the AI prompt as hints. The AI uses these hints to resolve ambiguity (e.g., a photo that looks like a phone but could be a tablet).

**Rule 4.3 — Subcategory Precision**
The AI should prefer the most specific applicable subcategory. A Samsung Galaxy should be "Mobile Phones → Android Phones," not "Mobile Phones → Other."

### 5. Frontend Behavior

**Rule 5.1 — Category Bar Shows All Main Categories**
The horizontal category bar displays every main category as a scrollable chip. "All" is always the first option and the default.

**Rule 5.2 — Subcategory Chips Appear on Selection**
When a buyer selects a main category, a second row of subcategory chips appears below it. "All" is the default subcategory selection.

**Rule 5.3 — "Other" Subcategory Handling**
The "Other" subcategory chip displays items whose subcategory is "Other" or "Uncategorized," or whose subcategory is not in the known list for that main category. This is a catch-all for edge cases.

**Rule 5.4 — Filtering Is Client-Side**
Category/subcategory filtering is performed on the already-fetched feed data. It does not trigger a new API request. This means filtering is instant but limited to items already loaded by the infinite scroll feed.

---

## Error Behaviors

| Scenario | System Response |
|----------|----------------|
| AI classifies outside the taxonomy | The AI prompt is reinforced with strict taxonomy instructions. If it still violates, the product gets "Other → Uncategorized" |
| Frontend and backend taxonomies drift out of sync | Categories appear in the UI that the AI never uses, or vice versa. Manual process: both files must be updated simultaneously |
| New category needed but not in taxonomy | Products get "Other → Uncategorized" until the taxonomy is updated |
