# TECH-14 Blueprint — Full-Screen Category Sheet on Mobile

**Goal:** Replace the 2-column hamburger menu grid on mobile with a full-screen category browsing sheet that supports main category → subcategory drill-down with slide animation.

## Files to Modify

1. `frontend/src/components/home/NavBar.jsx` — replace mobile grid with overlay trigger + mount point
2. `frontend/src/components/CategorySheet.jsx` — **NEW** — full-screen overlay component
3. `frontend/src/pages/Home.jsx` — pass `activeSubCategory` + `setActiveSubCategory` to NavBar

## CategorySheet.jsx — Full-Screen Overlay

```
Props: isOpen, onClose, activeCategory, setActiveCategory, activeSubCategory, setActiveSubCategory, TAXONOMY

State: view = "main" | "sub"
       selectedCategory = null

Structure:
┌─────────────────────────────┐
│ ← Back (or ✕ if at main)   │  ← 56px sticky header
│ Categories / Subcategory    │
├─────────────────────────────┤
│                             │
│  [All]                      │  ← scrollable list
│  Mobile Phones         >    │
│  Laptops & Computers   >    │
│  Tablets               >    │
│  ...                       │
│                             │
└─────────────────────────────┘

Behavior:
- view="main": shows all main categories. "All" has no arrow.
  Non-"All" categories have a chevron (>) indicating drill-down.
- Tap non-"All": set selectedCategory, toggle view="sub"
- view="sub": header shows "← Main" back button.
  Shows "All Subcategories" + each subcategory of selectedCategory.
- Tap subcategory (or "All Subcategories"):
  - setActiveCategory(selectedCategory)
  - setActiveSubCategory(sub || "All")
  - onClose()
  - The feed auto-filters via existing useShop logic.
- Tap "All" from main view: setActiveCategory("All"), onClose()
- Back button or X: if view="sub" → view="main"
                   if view="main" → onClose()
- Swipe down to dismiss (optional stretch goal, skip if complex)
```

## NavBar Changes

- Remove the mobile hamburger grid (lines 56-61)
- When hamburger tapped, open the CategorySheet instead of toggling isMobileMenuOpen
- Add `activeSubCategory` and `setActiveSubCategory` props
- Import and render `<CategorySheet>` inside NavBar (so it has access to the same state)

## Home.jsx Changes

- Pass `activeSubCategory` and `setActiveSubCategory` to NavBar

## Styling

- Full-screen: `fixed inset-0 z-40 bg-white`
- Slide animation: `transition-transform duration-300`
- view="main" → translateX(0), view="sub" → translateX(-100%)
- Category items: full-width, `px-4 py-3`, bottom border, flex justify-between
- Active item: `bg-blue-50 text-blue-700`
- Safe area: `pb-safe` for iPhone notch

## Acceptance Criteria
- [ ] Hamburger opens full-screen sheet instead of 2-column grid
- [ ] All 18 main categories displayed in a scrollable vertical list
- [ ] "All" immediately applies and closes sheet
- [ ] Non-"All" categories drill down to subcategory view with slide-left animation
- [ ] Subcategory view has back arrow to return to main view
- [ ] Selecting a subcategory sets both activeCategory and activeSubCategory, closes sheet
- [ ] Feed filters correctly based on selection
