# TECH-09 Implementation Blueprint — Taxonomy Restructuring

**Goal:** Replace the existing product taxonomy in the backend AI prompts and frontend constants with the locked taxonomy from `docs/behaviors/taxonomy.md` section 3, and eliminate the DRY violation in `CategoryChips.jsx` where an inline taxonomy duplicates the shared constant.

---

## Files to Modify

1. `backend/ai_engine/prompts.py`
2. `frontend/src/constants/taxonomy.js`
3. `frontend/src/components/CategoryChips.jsx`

No other files need changes. All downstream consumers (`vector_client.py`, `groq_client.py`, `gemini_client.py`, `useShop.js`, `CategoryBar.jsx`, `NavBar.jsx`, `SearchFilters.jsx`) iterate over the taxonomy keys/subcategories dynamically and require no logic adjustments.

---

## Strict Import Map

### backend/ai_engine/prompts.py
- **Exports changed:** `TAXONOMY_STRUCTURE` (dict — keys/values replaced entirely)
- **Exports unchanged:** `SYSTEM_PROMPT_TEXT` (generated dynamically at import time from `TAXONOMY_STRUCTURE` — the generation loop at lines 50-52 does NOT change)
- **Consumers (no changes needed):**
  - `backend/ai_engine/vector_client.py`: `from .prompts import TAXONOMY_STRUCTURE` — iterates `.items()` at line 88 to build the visual hints index. New keys and subcategories will be picked up automatically on next startup.
  - `backend/ai_engine/groq_client.py`: `from .prompts import SYSTEM_PROMPT_TEXT` — uses the dynamically-generated prompt string.
  - `backend/ai_engine/gemini_client.py`: `from .prompts import SYSTEM_PROMPT_TEXT` — same.

### frontend/src/constants/taxonomy.js
- **Export changed:** `TAXONOMY` (object — keys/values replaced; `"All"` key removed)
- **Downstream consumers (no code changes needed):**
  - `frontend/src/hooks/useShop.js`: `import { TAXONOMY } from '../constants/taxonomy';` — uses `TAXONOMY[activeCategory]` at line 188. When `activeCategory` is the string `"All"`, this evaluates to `undefined`, which is safely caught by `|| []`. The comparison `activeCategory === "All"` at line 185 is a hardcoded string check (not a key lookup), so it is unaffected.
  - `frontend/src/components/home/CategoryBar.jsx`: `import { TAXONOMY } from '../../constants/taxonomy';` — uses `TAXONOMY[cat]` at line 6 and `Object.keys(TAXONOMY).filter(c => c !== "All")` at line 17. Since `"All"` is no longer a key, the filter is a harmless no-op. The component continues to work.
  - `frontend/src/components/home/NavBar.jsx`: `import { TAXONOMY } from '../../constants/taxonomy';` — same `filter(c => c !== "All")` pattern at line 52. Same harmless outcome.
  - `frontend/src/components/SearchFilters.jsx`: `import { TAXONOMY } from '../constants/taxonomy';` — `Object.keys(TAXONOMY).map(...)` at line 54. Now correctly iterates only real categories, with no `"All"` entry showing in the dropdown.

### frontend/src/components/CategoryChips.jsx
- **New import added:** `import { TAXONOMY } from '../constants/taxonomy';` (relative path: `../constants/taxonomy`)
- **Imports removed:** `Smartphone`, `Laptop`, `Car`, `Home`, `Shirt`, `Sparkles`, `SprayCan`, `Heart`, `Armchair` from `lucide-react`
- **Import retained:** `Grid` from `lucide-react` (used by the "All" button)
- **Local variable removed:** The entire inline `TAXONOMY` object (lines 3-33 of the current file)
- **Shape change:** The imported `TAXONOMY` has shape `{ "CategoryName": ["sub1", "sub2", ...], ... }` — flat mapping of category name to array of strings. NOT `{ icon: ..., subs: [...] }`.

---

## Step-by-Step Execution

### Step 1: Replace TAXONOMY_STRUCTURE in `backend/ai_engine/prompts.py`

The `TAXONOMY_STRUCTURE` dict on lines 5-46 must be replaced in its entirety. The new dict must contain exactly the 18 main categories and their subcategories as declared in `docs/behaviors/taxonomy.md` section 3.

**Validation rule:** The new structure must be token-for-token identical to the taxonomy.md table. Do not alphabetize, reorder, or rename any keys or values. The order of main categories must be exactly as written in the taxonomy document.

The prompt generation code at lines 50-52 (`_taxonomy_string` loop and `SYSTEM_PROMPT_TEXT`) does NOT change — it dynamically iterates over the new dict. However, verify that the resulting prompt string correctly reflects all 18 categories and their subcategories.

### Step 2: Replace TAXONOMY in `frontend/src/constants/taxonomy.js`

The entire `TAXONOMY` export object (lines 1-17) must be replaced. The replacement must be structurally identical to the Python `TAXONOMY_STRUCTURE` from Step 1, but in JavaScript object literal syntax.

**Critical rules:**
- Do NOT include an `"All"` key. Downstream components handle "All" programmatically.
- Maintain the EXACT same category name strings and subcategory arrays as the Python dict.
- Preserve the single `export const TAXONOMY = { ... };` export format.

### Step 3: Fix `frontend/src/components/CategoryChips.jsx`

Three atomic sub-steps:

**3a. Remove the inline TAXONOMY object.** Delete the entire block from the first import line (line 1) through line 33 (the closing `};` of the inline TAXONOMY). Replace it with two imports:
- Import `Grid` from `lucide-react` (the only icon still needed for the "All" button)
- Import `TAXONOMY` from `../constants/taxonomy`

All other icon imports (`Smartphone`, `Laptop`, `Car`, `Home`, `Shirt`, `Sparkles`, `SprayCan`, `Heart`, `Armchair`) are no longer used and must be removed to avoid unused-import lint warnings.

**3b. Update the subcategory resolution.** On the line that reads:
```
const currentSubs = TAXONOMY[activeCategory]?.subs || [];
```
Change it to:
```
const currentSubs = TAXONOMY[activeCategory] || [];
```
The imported TAXONOMY maps directly from category name to subcategory array — there is no `.subs` wrapper.

**3c. Update the main category mapping loop.** The map over `Object.entries(TAXONOMY)` that destructures `([key, data])` and uses `data.icon` must change to a simple `Object.keys(TAXONOMY).map((key) => ...)`. Remove the `const Icon = data.icon;` line and the `<Icon />` JSX element inside each category button. The buttons should display only the category name text, matching the style of `CategoryBar.jsx` which renders category chips without icons.

The "All" button (currently lines 57-68) does NOT change — it remains hardcoded with the Grid icon.

### Step 4: Rebuild the API container

Run `docker compose build api --no-cache` followed by `docker compose up -d api`. The `--no-cache` flag ensures the new `prompts.py` is embedded in the image (since the API has a live volume mount at `./backend:/app`, a rebuild may not be strictly necessary for the code change, but a restart is required to trigger `initialize_taxonomy_index()` in `vector_client.py`, which rebuilds the visual hints index from the new subcategory list).

Verify the API starts successfully and logs the updated subcategory count in the message "Taxonomy Index Ready: N categories cached." The N value should equal the total number of subcategories in the new taxonomy.

### Step 5: Rebuild the frontend container

Run `docker compose build frontend --no-cache` followed by `docker compose up -d frontend`. Unlike the API, the frontend does not have a volume mount for source code — the code is baked into the image at build time. A full rebuild with `--no-cache` is required to pick up the changes to `taxonomy.js` and `CategoryChips.jsx`.

---

## Testing Requirements

### Backend Tests

1. **Prompt generation integrity:** After deployment, query the `/docs` or a debug endpoint (if one exists) to retrieve the generated SYSTEM_PROMPT_TEXT. Verify that all 18 main categories appear in the prompt string with correct subcategories. Verify that the old categories ("Mobile Phones & Tablets", "Fashion") do NOT appear.

2. **Visual hints index rebuild:** Check the API container logs after restart for the line `Taxonomy Index Ready: N categories cached`. Verify that N matches the total count of unique subcategories across all 18 main categories in the locked taxonomy. (The locked taxonomy has 98 subcategories total.)

3. **Classification enforcement:** Submit a test product that should map to one of the new standalone categories (e.g., a laptop, a pair of women's shoes, an iPhone). Verify the AI correctly classifies it under the new main category ("Laptops & Computers", "Women's Fashion", "Mobile Phones") and NOT under the old merged categories ("Electronics", "Fashion", "Mobile Phones & Tablets").

### Frontend Tests

4. **Category bar displays all 18 categories:** On the home page, the horizontal category bar and the mobile hamburger menu must display exactly 18 main categories (plus the hardcoded "All" button). Verify that stale categories ("Mobile Phones & Tablets", "Fashion") are absent and new categories ("Mobile Phones", "Laptops & Computers", "Tablets", "Men's Fashion", "Women's Fashion", "Shoes") are present.

5. **Subcategory chips render correctly:** Clicking any main category must reveal its correct subcategory chips from the locked taxonomy. Verify that "Other" appears as a subcategory option where defined in the taxonomy, and that the chip labels match the exact strings from the taxonomy document.

6. **CategoryChips component renders without icons:** The `CategoryChips.jsx` component must render all main categories as text-only chips (no icons), matching the new flat taxonomy structure. The "All" button retains its Grid icon. No console errors about missing imports or undefined icon components.

7. **Search filters dropdown:** The category dropdown in `SearchFilters.jsx` must list all 18 main categories without a blank or "All" entry. Selecting a category must correctly filter search results.

8. **Category filtering still works:** Selecting a main category and subcategory must correctly filter the displayed items. The `useShop.js` filter logic at line 185 uses hardcoded `"All"` string comparison, which must continue to work correctly alongside the new category string values.
