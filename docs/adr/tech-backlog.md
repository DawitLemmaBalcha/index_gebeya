# Technical Backlog

---

## TECH-22 — Sold Reports + Product Status + Cleanup

**Parent:** NB-41
**Priority:** HIGH
**Affected Files:** `backend/models.py`, `backend/constants.py`, `backend/services/cleanup.py` (new), `frontend/src/pages/ProductPage.jsx`, `listener/notifications.py`

**Description:** Add Item.status column, SoldReport model, report endpoint, owner DM on status changes, configurable cleanup constants, daily cleanup background task.

---

## TECH-23 — Inventory Management

**Parent:** NB-42
**Priority:** HIGH
**Affected Files:** `frontend/src/pages/StoresPage.jsx`, new inventory modal + edit panel components, `backend/api/routes/channels.py`

**Description:** Channel inventory modal with Products/Settings tabs. Product grid with infinite scroll and status badges. Product edit panel with editable title, description, price, category, subcategory, specs. Status controls. Tab registry pattern for extensibility.
