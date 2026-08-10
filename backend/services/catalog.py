"""
Catalog navigation, not relevance.

The browse seam (`GET /items/browse`): plain catalog queries over the items
table — active-only, recency-ordered, paginated. Deliberately deep and
Local-substitutable: the only app import is the Item model.

This module NEVER vectorizes and NEVER imports boost. The boost pin layer
is applied by the caller via `services.boost.compose_pinned_page` — see
Rule 3.1 (category browse is a real server-side surface).
"""

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models import Item
from services.ban import owner_banned_pred  # NB-56 Rule 3.3: browse excludes banned sellers


def browse_category(
    db: Session, category: str, limit: int = 20, offset: int = 0
) -> tuple[list[Item], int]:
    """Active items of `category`, newest first, paginated.

    Returns (items, total_count): the page slice plus the aggregate count of
    matching rows (used for the response's `total`). Filters:
    `category == :category AND status == 'active' AND is_active == True`.
    """
    conditions = (
        Item.category == category,
        Item.status == "active",
        Item.is_active == True,  # noqa: E712 — house style (models/boost.py)
        # NB-56 (Rule 3.3): banned sellers' items are excluded at query
        # time — never deleted; the predicate is NULL-safe so ownerless
        # channels stay visible (Rule 1.4).
        ~owner_banned_pred(),
    )
    items = list(
        db.scalars(
            select(Item)
            .where(*conditions)
            .order_by(Item.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    )
    total = db.scalar(select(func.count(Item.id)).where(*conditions)) or 0
    return items, total
