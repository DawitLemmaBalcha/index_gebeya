# Technical Backlog

---

## TECH-21 — Dedup Redesign + Alert Filter Badges

**Parent:** NB-40
**Priority:** HIGH

**Affected Files:**
- `backend/api/routes/ingestion.py` — replace edit-in-place with soft-delete + create
- `listener/worker.py` — update processing DM for replacement case
- `frontend/src/pages/AlertsPage.jsx` — show smart filter badges on alert cards

**Acceptance Criteria:**
- [ ] Dedup: soft-delete old (`is_active=False`), create new item with new `item_id`
- [ ] Alert matching fires on new item (fresh `item_id` bypasses dedup)
- [ ] Processing DM: "✅ Updated: Title — Price. ⚠️ Replaced previous listing. Use different images for different products."
- [ ] Old edit-in-place field updates removed from ingestion.py
- [ ] Alert cards show "Strict Brand" / "Strict Model" badges when preferences are set
