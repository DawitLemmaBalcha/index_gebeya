"""
NB-56: the ban primitive — one flag, enforced at the seams (Rule 3.1..3.5).

`users.banned` is reversible (no deletion, no derived state): unban restores
everything instantly because every query seam re-reads the flag (Rule 3.5).
Banned sellers keep their rows; banned buyers keep their existing alerts
(dispatch is NOT a v1 seam — documented in the blueprint §6).

The channels join resolves through `users.telegram_id ==
channels.registered_by` — registered_by is a plain BigInteger storing the
owner's TELEGRAM ID, not a users.id FK (models.py L135; main.py L283-284).
`owner_banned_pred()` is NULL-safe by construction: an ownerless channel
matches no row → never excluded (Rule 1.4).
"""

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from models import Channel, Item, User


def is_banned(db: Session, user: User) -> bool:
    """Rule 3.1: the single flag, read directly."""
    return bool(user.banned)


def ban_user(db: Session, user_id: int) -> User:
    """Set the flag; 404 when the user row is missing."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.banned = True
    db.commit()
    db.refresh(user)
    return user


def unban_user(db: Session, user_id: int) -> User:
    """Clear the flag; 404 when the user row is missing."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.banned = False
    db.commit()
    db.refresh(user)
    return user


def is_channel_banned(db: Session, channel: Channel) -> bool:
    """Rule 3.3: the channel's owner (resolved by TELEGRAM ID) is banned.
    Ownerless channels (registered_by NULL) are never banned (Rule 1.4)."""
    if channel.registered_by is None:
        return False
    owner = db.scalar(select(User).where(User.telegram_id == channel.registered_by))
    return bool(owner and owner.banned)


def owner_banned_pred():
    """SQLAlchemy exists() predicate for ORM query seams: a banned User owns
    this Channel (join via users.telegram_id == channels.registered_by).

    The ORM seams query Item directly (no channels join), so the predicate
    correlates through `Item.channel_id -> channels.registered_by ->
    users.telegram_id`; used negated (`~owner_banned_pred()`) so banned
    sellers' items are excluded from browse/feeds/pinned-boost at query
    time — never deleted. NULL-safe by construction: an ownerless channel
    yields NULL registered_by, `telegram_id = NULL` matches no row, and
    NOT EXISTS keeps the item visible (Rule 1.4)."""
    owner_telegram_id = (
        select(Channel.registered_by)
        .where(Channel.id == Item.channel_id)
        .correlate(Item)  # items lives in the ENCLOSING query's FROM
        .scalar_subquery()
    )
    return exists().where(
        User.telegram_id == owner_telegram_id,
        User.banned.is_(True),
    )
