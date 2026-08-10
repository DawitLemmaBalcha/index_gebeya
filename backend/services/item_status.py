"""
Item status-transition business rules — the single home for lifecycle logic
that previously lived inside the items.py route handlers.

Rules preserved verbatim from the route implementations:
  - report_sold: crowdsourced reporting, one report per user per item,
    owner cannot report their own item, CROWDSOURCE_SOLD_THRESHOLD flips
    status to 'reported_sold' and notifies the owner via send_owner_dm.
  - relist_item: owner-only; clears all SoldReports and resets to 'active';
    no-op (already_active) for never-reported items.
  - mark_sold: owner-only authoritative status set.
  - clear_reports: owner-only; deletes reports WITHOUT changing status.
  - update_item: owner-only partial update; exactly one ItemEdit record per
    changed field; re-triggers process_new_item when price or specs change.

Route handlers in api/routes/items.py are thin adapters over these functions.
"""

import json
import logging
from datetime import datetime  # noqa: F401  (module import map — see blueprint)
from sqlalchemy.orm import Session
from sqlalchemy import select, delete, func
from fastapi import HTTPException

from models import Item, Channel, SoldReport, ItemEdit, ItemImage, Notification, User
from services.alerting import process_new_item
from services.owner_dm import send_owner_dm
from services.boost import end_boost_for_item  # NB-43 Rule 6.1: sold -> boost ends
from constants import CROWDSOURCE_SOLD_THRESHOLD

logger = logging.getLogger("index_item_status")


async def report_sold(db: Session, item_id: int, user: User) -> dict:
    """
    Create SoldReport (one per user per item). At CROWDSOURCE_SOLD_THRESHOLD,
    flip status to 'reported_sold', notify owner.
    """
    # 1. Find item
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 2. Check ownership — owner cannot report their own item
    channel = db.get(Channel, item.channel_id)
    if channel and channel.registered_by and channel.registered_by == user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot report your own product"
        )

    # 3. Check duplicate report
    existing = db.scalar(
        select(SoldReport).where(
            SoldReport.user_id == user.id,
            SoldReport.item_id == item_id,
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="You already reported this as sold."
        )

    # 4. Create SoldReport
    report = SoldReport(user_id=user.id, item_id=item_id)
    db.add(report)
    db.commit()

    # 5. Count reports
    report_count = db.scalar(
        select(func.count(SoldReport.id)).where(SoldReport.item_id == item_id)
    )
    report_count = report_count or 0

    # Build inline keyboard for the owner DM: clear reports / mark sold
    markup = {
        "inline_keyboard": [[
            {"text": "✅ It's not sold", "callback_data": f"sold_report_clear_{item_id}"},
            {"text": "❌ It is sold", "callback_data": f"sold_report_mark_{item_id}"},
        ]]
    }

    # 5b. Notify owner on FIRST report — early warning with action buttons
    channel_username = channel.username if channel else "unknown"
    if report_count == 1:
        msg = (
            f"⚠️ Your listing '{item.title}' on @{channel_username} "
            f"has been reported as sold by a buyer. Users can now see the report.\n\n"
            f"If it reaches {CROWDSOURCE_SOLD_THRESHOLD} reports, "
            f"the product will be taken down.\n\n"
            f"Use the buttons below to confirm or clear this."
        )
        await send_owner_dm(db, item.channel_id, msg, reply_markup=markup)

    # 6. Check threshold
    if report_count >= CROWDSOURCE_SOLD_THRESHOLD:
        if item.status == "active":
            item.status = "reported_sold"
            db.commit()

            # NB-43 Rule 6.1: reported_sold -> boost ends immediately, no refund.
            end_boost_for_item(db, item.id)

            # 7. Send owner DM
            msg = (
                f"⚠️ Your listing '{item.title}' on @{channel_username} "
                f"has been reported as sold by {report_count} buyers. "
                f"It has been hidden from search.\n\n"
                f"Use the buttons below to confirm it is sold "
                f"or clear the reports if this is incorrect."
            )
            await send_owner_dm(db, item.channel_id, msg, reply_markup=markup)

    return {"status": "reported", "report_count": report_count}


def relist_item(db: Session, item_id: int, user: User) -> dict:
    """
    Owner-only. Clear SoldReports, reset status to 'active'.
    """
    # 1. Find item
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # 2. Check ownership
    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can re-list this item"
        )

    # 3. Check if item was ever reported
    report_count = db.scalar(
        select(func.count(SoldReport.id)).where(SoldReport.item_id == item_id)
    )

    if item.status == "active" and (report_count is None or report_count == 0):
        return {"status": "already_active", "message": "Item was never reported"}

    # 4. Delete all sold reports
    db.execute(delete(SoldReport).where(SoldReport.item_id == item_id))

    # 5. Reset status
    item.status = "active"
    db.commit()

    return {"status": "active", "message": "Item re-listed successfully"}


def mark_sold(db: Session, item_id: int, user: User) -> dict:
    """
    Owner-only. Set status to 'sold'.
    """
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can mark items as sold"
        )

    item.status = "sold"
    db.commit()

    # NB-43 Rule 6.1: sold -> boost ends immediately, no refund.
    end_boost_for_item(db, item_id)

    return {"status": "sold", "message": "Item marked as sold"}


def clear_reports(db: Session, item_id: int, user: User) -> dict:
    """
    Owner-only. Delete SoldReports without changing status.
    """
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can clear reports"
        )

    deleted = db.execute(delete(SoldReport).where(SoldReport.item_id == item_id))
    db.commit()

    return {
        "status": item.status,
        "message": f"{deleted.rowcount} report(s) cleared",
    }


def update_item(db: Session, item_id: int, user: User, payload: "ItemUpdateRequest") -> Item:
    """
    Owner-only. Apply field changes, log ItemEdit history, re-trigger
    process_new_item if price/specs changed.
    """
    # Find and verify ownership
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit items in your own channels"
        )

    # Edit history logging helper
    def _log_edit(field_name: str, old_val, new_val):
        """Log a field change to item_edits. No-op if values are equal."""
        if isinstance(old_val, dict):
            old_str = json.dumps(old_val, sort_keys=True) if old_val else None
        else:
            old_str = str(old_val) if old_val is not None else None

        if isinstance(new_val, dict):
            new_str = json.dumps(new_val, sort_keys=True) if new_val else None
        else:
            new_str = str(new_val) if new_val is not None else None

        if old_str == new_str:
            return

        edit = ItemEdit(
            item_id=item_id,
            field=field_name,
            old_value=old_str,
            new_value=new_str,
            edited_by=user.id,
        )
        db.add(edit)

    # Apply updates using exclude_unset
    update_data = payload.model_dump(exclude_unset=True)
    needs_reprocess = False

    if "title" in update_data and payload.title != item.title:
        _log_edit("title", item.title, payload.title)
        item.title = payload.title

    if "description" in update_data and payload.description != item.description:
        _log_edit("description", item.description, payload.description)
        item.description = payload.description

    if "price" in update_data:
        if item.price is None or abs(payload.price - item.price) > 0.001:
            _log_edit("price", item.price, payload.price)
            item.price = payload.price
            needs_reprocess = True

    if "category" in update_data and payload.category != item.category:
        _log_edit("category", item.category, payload.category)
        item.category = payload.category
        # NB-55 (Rule 1.3): category corrections re-trigger the pipeline —
        # browse reads live rows, so the item moves in the catalog
        # immediately and matching must re-evaluate it.
        needs_reprocess = True

    if "subcategory" in update_data and payload.subcategory != item.subcategory:
        _log_edit("subcategory", item.subcategory, payload.subcategory)
        item.subcategory = payload.subcategory
        # NB-55 (Rule 1.3): subcategory corrections re-trigger the pipeline.
        needs_reprocess = True

    if "specs" in update_data:
        old_specs = {}
        if item.specs:
            try:
                old_specs = json.loads(item.specs) if isinstance(item.specs, str) else item.specs
            except (json.JSONDecodeError, TypeError):
                old_specs = {}
        new_specs = payload.specs or {}

        _log_edit("specs", old_specs, new_specs)
        item.specs = json.dumps(new_specs)
        needs_reprocess = True

    db.commit()
    db.refresh(item)

    # Re-trigger alert matching (Rule 3.3)
    if needs_reprocess:
        try:
            process_new_item(db, item.id)
        except Exception as e:
            logger.warning(f"Alert re-processing failed for item {item_id}: {e}")

    return item


def delete_item(db: Session, item_id: int, user: User) -> dict:
    """
    Owner-only. Permanently delete an item from the catalog.
    Cleans up related records: SoldReports, ItemEdits, ItemImages, Notifications.
    """
    item = db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    channel = db.get(Channel, item.channel_id)
    if not channel or channel.registered_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Only the channel owner can delete this item"
        )

    # Clean up dependent records
    db.execute(delete(SoldReport).where(SoldReport.item_id == item_id))
    db.execute(delete(ItemEdit).where(ItemEdit.item_id == item_id))
    db.execute(delete(Notification).where(Notification.item_id == item_id))
    db.execute(delete(ItemImage).where(ItemImage.item_id == item_id))

    db.delete(item)
    db.commit()

    return {"status": "deleted", "item_id": item_id}
